"""Wheels FastAPI backend.

Run:  .venv\\Scripts\\python.exe -m uvicorn app.server:app --port 8000
The heavy model loads lazily on the first /api/edit call.
"""
from __future__ import annotations

import itertools
import json
import queue as queue_mod
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, engine, library
from .imageio import data_url_to_pil, pil_to_data_url

MAX_BODY_BYTES = 16 * 1024 * 1024  # ~16MB JSON body ≈ a 12MB image as base64
MAX_QUEUE = 5                      # max renders waiting (positions are shown in the UI)

# ---------------------------------------------------------------- usage stats
# Requests arriving through the Cloudflare tunnel carry Cf-Connecting-Ip (the
# visitor's real IP); local requests don't. That cleanly splits external vs
# local usage. Persisted to stats.json so counts survive restarts.
STATS_PATH = config.BACKEND_DIR / "stats.json"
GALLERY_DIR = config.BACKEND_DIR / "gallery"
_STATS_LOCK = threading.Lock()


def _load_stats() -> dict:
    base = {
        "visits_local": 0,
        "visits_external": 0,
        "renders_local": 0,
        "renders_external": 0,
        "unique_external_ips": [],
        "by_day": {},
    }
    try:
        base.update(json.loads(STATS_PATH.read_text()))
    except Exception:
        pass
    return base


STATS = _load_stats()


def _visitor(request: Request) -> tuple[str, str | None]:
    """('external', ip) for tunnel traffic, ('local', None) otherwise."""
    ip = request.headers.get("cf-connecting-ip")
    return ("external", ip) if ip else ("local", None)


def _bump(kind: str, request: Request) -> str:
    src, ip = _visitor(request)
    with _STATS_LOCK:
        STATS[f"{kind}_{src}"] = STATS.get(f"{kind}_{src}", 0) + 1
        day = STATS["by_day"].setdefault(time.strftime("%Y-%m-%d"), {})
        day[f"{kind}_{src}"] = day.get(f"{kind}_{src}", 0) + 1
        if ip and ip not in STATS["unique_external_ips"]:
            STATS["unique_external_ips"].append(ip)
        try:
            STATS_PATH.write_text(json.dumps(STATS, indent=1))
        except Exception:
            pass
    return src


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm the model in the background so the server is responsive immediately
    # and the first user edit isn't blocked on the ~50s load.
    threading.Thread(target=engine.get_editor, daemon=True).start()
    threading.Thread(target=_render_worker, daemon=True).start()
    yield


app = FastAPI(title="Wheels API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static/samples", StaticFiles(directory=str(config.SAMPLES_DIR)), name="samples")
app.mount("/static/catalog", StaticFiles(directory=str(config.WHEEL_CATALOG_DIR)), name="catalog")
# (outputs deliberately NOT mounted — results travel as data URLs; smaller public surface)


class EditRequest(BaseModel):
    image: str
    body_color: str | None = None
    body_finish: str | None = None  # gloss | metallic | matte | satin | pearl
    wheel_id: str | None = None
    wheel_color: str | None = None
    wheel_size: int | None = None   # 17-24 (inches)
    seed: int = 0


def _base_url() -> str:
    # Relative URLs: assets load through the frontend's same-origin proxy, which
    # works identically on localhost and through a share tunnel.
    return ""


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/stats")
def stats():
    with _STATS_LOCK:
        s = dict(STATS)
    gallery_pairs = len(list(GALLERY_DIR.glob("*/*-result.jpg"))) if GALLERY_DIR.exists() else 0
    return {
        **s,
        "unique_external_visitors": len(s.get("unique_external_ips", [])),
        "gallery_renders_saved": gallery_pairs,
    }


@app.get("/readyz")
def readyz():
    return {"ready": engine.is_ready(), "waiting": _queue_depth()}


@app.get("/api/progress")
def progress():
    return engine.PROGRESS


@app.get("/api/stock-cars")
def stock_cars(request: Request):
    _bump("visits", request)  # fetched once per page load — a good visit proxy
    return library.stock_cars(_base_url())


@app.get("/api/wheels")
def wheels():
    return library.wheel_library(_base_url())


# Renders run as background jobs: the POST returns a job id instantly and the
# client polls. Long-held responses died at proxies (Cloudflare caps ~100s) and
# tied up the frontend proxy — never hold a request open for GPU work.
# One GPU -> ONE worker thread consuming a FIFO queue, so ordering is fair and
# every waiting job has a well-defined position ("you're #2 in line").
JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_JOB_QUEUE: "queue_mod.Queue[str]" = queue_mod.Queue()
_TICKETS = itertools.count(1)


def _prune_jobs():
    done = [k for k, v in JOBS.items() if v["status"] in ("done", "error")]
    if len(done) > 30:
        for k in sorted(done, key=lambda k: JOBS[k]["t"])[: len(done) - 30]:
            JOBS.pop(k, None)


def _queue_depth() -> int:
    return sum(1 for v in JOBS.values() if v["status"] in ("queued", "rendering"))


def _position(jid: str) -> int | None:
    """0 = rendering now; N>=1 = jobs ahead of you; None once finished."""
    j = JOBS.get(jid)
    if not j or j["status"] not in ("queued", "rendering"):
        return None
    if j["status"] == "rendering":
        return 0
    return sum(
        1
        for v in JOBS.values()
        if v["status"] == "rendering"
        or (v["status"] == "queued" and v["ticket"] < j["ticket"])
    )


def _save_to_gallery(jid: str, req: "EditRequest", src: str, ip: str | None, img, out):
    """Archive the upload + result pair so the host can browse them later."""
    try:
        day_dir = GALLERY_DIR / time.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%H%M%S")
        base = f"{stamp}-{jid[:6]}"
        img.convert("RGB").save(day_dir / f"{base}-original.jpg", "JPEG", quality=90)
        out.convert("RGB").save(day_dir / f"{base}-result.jpg", "JPEG", quality=92)
        entry = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "job": jid[:6],
            "source": src,
            "ip": ip,
            "edits": {
                k: v
                for k, v in {
                    "body_color": req.body_color,
                    "body_finish": req.body_finish,
                    "wheel_id": req.wheel_id,
                    "wheel_color": req.wheel_color,
                    "wheel_size": req.wheel_size,
                }.items()
                if v
            },
            "files": [f"{base}-original.jpg", f"{base}-result.jpg"],
        }
        with open(GALLERY_DIR / "index.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # archiving must never break a render


def _render_worker():
    while True:
        jid = _JOB_QUEUE.get()
        j = JOBS.get(jid)
        if not j:
            continue
        t0 = time.perf_counter()
        try:
            j["status"] = "rendering"
            req = j.pop("req")
            img = data_url_to_pil(req.image)
            out = engine.apply_edit(
                img,
                body_color=req.body_color,
                body_finish=req.body_finish,
                wheel_id=req.wheel_id,
                wheel_color=req.wheel_color,
                wheel_size=(req.wheel_size if req.wheel_size in range(17, 25) else None),
                seed=req.seed,
            )
            j.update(
                status="done",
                image=pil_to_data_url(out, fmt="JPEG", quality=92),
                ms=int((time.perf_counter() - t0) * 1000),
            )
            _save_to_gallery(jid, req, j.get("src", "local"), j.get("ip"), img, out)
        except Exception as e:  # surfaced to the client via job status
            j.update(status="error", error=str(e)[:300])


@app.post("/api/edit")
def edit(req: EditRequest, request: Request):
    if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
        raise HTTPException(413, "Image too large — please upload a smaller photo.")
    if _queue_depth() >= MAX_QUEUE:
        raise HTTPException(429, "The GPU queue is full — try again in a minute.")

    src = _bump("renders", request)
    _, ip = _visitor(request)
    jid = uuid.uuid4().hex
    with _JOBS_LOCK:
        JOBS[jid] = {
            "status": "queued",
            "image": None,
            "error": None,
            "ms": 0,
            "t": time.time(),
            "ticket": next(_TICKETS),
            "req": req,
            "src": src,
            "ip": ip,
        }
        _prune_jobs()
    _JOB_QUEUE.put(jid)
    return {"job_id": jid, "position": _position(jid)}


@app.get("/api/job/{jid}")
def job_status(jid: str):
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, "unknown job")
    return {
        "status": j["status"],
        "error": j["error"],
        "ms": j["ms"],
        "image": j["image"] if j["status"] == "done" else None,
        "position": _position(jid),
        "progress": engine.PROGRESS,
    }
