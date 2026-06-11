"""Stock-car and wheel-library manifests served to the frontend."""
from __future__ import annotations

import json

from . import config

# Stock cars = the bundled sample photos (served via /static/samples/...).
STOCK_CARS = [
    {"id": "cadillac", "name": "1972 Cadillac", "file": "cadillac.jpg"},
    {"id": "sentra", "name": "Nissan Sentra", "file": "sentra.jpg"},
]


def stock_cars(base_url: str):
    out = []
    for c in STOCK_CARS:
        if (config.SAMPLES_DIR / c["file"]).exists():
            url = f"{base_url}/static/samples/{c['file']}"
            out.append({"id": c["id"], "name": c["name"], "thumb": url, "image": url})
    return out


# --- Real product wheels (scraped by scrape_catalog.py, one dir per brand) ----
def _load_catalog() -> list[dict]:
    out = []
    for mf in sorted(config.WHEEL_CATALOG_DIR.glob("*/manifest.json")):
        try:
            out.extend(json.loads(mf.read_text()))
        except Exception:
            pass
    return out


CATALOG = _load_catalog()
_CATALOG_BY_ID = {w["id"]: w for w in CATALOG}


def catalog_lookup(wheel_id: str | None) -> dict | None:
    """Catalog entry (+ resolved image path) for ids like 'cat:bbs:bbs-lemans-...'."""
    w = _CATALOG_BY_ID.get(wheel_id) if wheel_id else None
    if not w:
        return None
    path = config.WHEEL_CATALOG_DIR / w["file"]
    return {**w, "path": path} if path.exists() else None


def wheel_library(base_url: str):
    # Real product wheels only — the generated style archetypes (WHEEL_STYLES) are
    # no longer served; the picker is a manufacturer catalog.
    out = []
    for w in CATALOG:
        out.append(
            {
                "id": w["id"],
                "name": w["model"],
                "finish": w["finish"],
                "group": w["brand"],
                "thumb": f"{base_url}/static/catalog/{w['file']}",
            }
        )
    return out
