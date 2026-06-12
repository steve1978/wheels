"""Scrape fifteen52 wheels (Shopify JSON feed) into the local wheel catalog.

  .venv\\Scripts\\python.exe scrape_fifteen52.py

Product titles are "MODEL _ Finish" (e.g. "Holeshot RSR _ Asphalt Black").
"""
import json
import re
import urllib.request

from app import config

COLLECTIONS = [
    "rsr-series",
    "rally-sport-series",
    "super-touring-wheels",
    "off-road-truck-wheels",
    "52outlaw",
]
BRAND_SLUG = "fifteen52"
BRAND_NAME = "fifteen52"

# Design descriptions for bold/simple wheels: the AI tends to substitute a
# generic sporty wheel for these unless the geometry is spelled out in words
# alongside the product photo (proven dramatically better for the Tarmac).
DESCS = {
    "tarmac-evo": None,  # different design — don't inherit the plain-tarmac desc
    "tarmac": (
        "exactly FIVE wide flat solid spokes forming a bold star, chunky retro "
        "rally style with a circular lip, completely unlike thin multi-spoke wheels"
    ),
    "turbomac": (
        "exactly FIVE wide flat solid spokes, each with one small round hole, "
        "chunky retro rally style, completely unlike thin multi-spoke wheels"
    ),
    "integrale": "six-spoke rally design with a deep concave face and chunky squared spokes",
}


def design_desc(slug: str) -> str | None:
    for pat, d in DESCS.items():
        if pat in slug:
            return d
    return None
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def slugify(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def main():
    out_dir = config.WHEEL_CATALOG_DIR / BRAND_SLUG
    out_dir.mkdir(parents=True, exist_ok=True)
    items, seen = [], set()

    for coll in COLLECTIONS:
        page = 1
        while True:
            url = f"https://fifteen52.com/collections/{coll}/products.json?limit=250&page={page}"
            try:
                products = json.loads(fetch(url)).get("products", [])
            except Exception as e:
                print(f"  !! {coll} page {page}: {e}", flush=True)
                break
            if not products:
                break
            for p in products:
                title = p["title"].strip()
                if title in seen or not p.get("images"):
                    continue
                # Collections mix in merch (shift knobs, apparel): wheels have an
                # empty product_type; skip anything typed as something else.
                ptype = (p.get("product_type") or "").strip().lower()
                if ptype and "wheel" not in ptype:
                    continue
                seen.add(title)
                model, _, finish = title.partition(" _ ")
                slug = slugify(title)
                dest = out_dir / f"{slug}.jpg"
                if not dest.exists():
                    try:
                        img_url = p["images"][0]["src"].split("?")[0] + "?width=900"
                        dest.write_bytes(fetch(img_url))
                    except Exception as e:
                        print(f"  !! image failed for {title}: {e}", flush=True)
                        continue
                entry = {
                    "id": f"cat:{BRAND_SLUG}:{slug}",
                    "brand": BRAND_NAME,
                    "model": model.strip(),
                    "finish": finish.strip() or "Standard",
                    "file": f"{BRAND_SLUG}/{slug}.jpg",
                }
                desc = design_desc(slug)
                if desc:
                    entry["desc"] = desc
                items.append(entry)
                print(f"  ok {title}", flush=True)
            page += 1

    (out_dir / "manifest.json").write_text(json.dumps(items, indent=1))
    print(f"{len(items)} wheels -> {out_dir / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
