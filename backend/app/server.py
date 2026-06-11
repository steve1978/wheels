"""Wheels FastAPI backend.

Run:  .venv\\Scripts\\python.exe -m uvicorn app.server:app --port 8000
The heavy model loads lazily on the first /api/edit call.
"""
from __future__ import annotations

import itertools
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
    seed: int = 0


def _base_url() -> str:
    # Relative URLs: assets load through the frontend's same-origin proxy, which
    # works identically on localhost and through a share tunnel.
    return ""


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/readyz")
def readyz():
    return {"ready": engine.is_ready(), "waiting": _queue_depth()}


@app.get("/api/progress")
def progress():
    return engine.PROGRESS


@app.get("/api/stock-cars")
def stock_cars():
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
                seed=req.seed,
            )
            j.update(
                status="done",
                image=pil_to_data_url(out, fmt="JPEG", quality=92),
                ms=int((time.perf_counter() - t0) * 1000),
            )
        except Exception as e:  # surfaced to the client via job status
            j.update(status="error", error=str(e)[:300])


@app.post("/api/edit")
def edit(req: EditRequest, request: Request):
    if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
        raise HTTPException(413, "Image too large — please upload a smaller photo.")
    if _queue_depth() >= MAX_QUEUE:
        raise HTTPException(429, "The GPU queue is full — try again in a minute.")

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
