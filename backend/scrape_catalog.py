"""Scrape a Wheelmania brand category page into the local wheel catalog.

  .venv\\Scripts\\python.exe scrape_catalog.py <category-url> <brand-slug> [display-name]
  e.g.  scrape_catalog.py https://wheelmania.co.uk/alloy-wheels/oz-racing/ oz-racing "OZ Racing"

Downloads each product image to wheel_catalog/<brand>/<slug>.jpg and writes
wheel_catalog/<brand>/manifest.json with [{id, brand, model, finish, file}].

NOTE: product imagery is the supplier's copyright — fine for local prototyping;
license it before any public/commercial deployment.
"""
import html as htmllib
import json
import re
import sys
import urllib.request

from app import config

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PAT = re.compile(r'src="([^"]+?/full\.jpg)"\s+alt="([^"]+?) alloy wheel"')


def slugify(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main(url: str, brand: str, display: str | None = None):
    display = display or brand.upper()
    out_dir = config.WHEEL_CATALOG_DIR / brand
    out_dir.mkdir(parents=True, exist_ok=True)

    page = fetch(url).decode("utf-8", errors="ignore")
    seen, items = set(), []
    for img_url, raw_name in PAT.findall(page):
        name = htmllib.unescape(raw_name).strip()
        if name in seen:
            continue
        seen.add(name)
        # "BBS LeMans (LM) - Gold With Polished Rim" -> model / finish
        model, _, finish = name.partition(" - ")
        slug = slugify(name)
        dest = out_dir / f"{slug}.jpg"
        if not dest.exists():
            try:
                dest.write_bytes(fetch(img_url))
            except Exception as e:
                print(f"  !! download failed for {name}: {e}", flush=True)
                continue
        items.append(
            {
                "id": f"cat:{brand}:{slug}",
                "brand": display,
                "model": model.strip(),
                "finish": finish.strip() or "Standard",
                "file": f"{brand}/{slug}.jpg",
            }
        )
        print(f"  ok {name}", flush=True)

    (out_dir / "manifest.json").write_text(json.dumps(items, indent=1))
    print(f"{len(items)} wheels -> {out_dir / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
