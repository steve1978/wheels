"""APEX wheels (apexwheels.com) -> local wheel catalog.

apexwheels.com sits behind a Vercel bot checkpoint, so the product list below
was captured via a real browser session (listing pages of /wheels/flow-formed
and /wheels/forged). The hero images live on Sanity's public CDN and download
fine. Re-capture the mapping if APEX adds models.

  .venv\\Scripts\\python.exe scrape_apex.py
"""
import json
import urllib.request

from app import config

BRAND_SLUG = "apex"
BRAND_NAME = "APEX"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"
CDN = "https://cdn.sanity.io/images/c8ihu5xk/production/"

# (model, line, image-hash-file)
WHEELS = [
    ("VS-5",    "Flow Formed", "44b269299ab6be39fdc341e880768b70a471adc5-2000x2000.png"),
    ("SM-10",   "Flow Formed", "a13c8118fe4883fb06476fa1e65308b867c3dff4-2000x2000.png"),
    ("FL-5",    "Flow Formed", "5a5bceb34da25e5cd855e708a5eb72fb6d279f3e-2000x2000.png"),
    ("ARC-8",   "Flow Formed", "239076efec1498e17b51d413f541558f1fffd19e-2000x2000.png"),
    ("EC-7",    "Flow Formed", "6bdaa6139ec4fe6deef7db7e305e41672d1640b9-2000x2000.png"),
    ("VS-5RS",  "Forged",      "61b7ab955d9794a6a593b18c8dd6a66007dfd5f7-2000x2000.png"),
    ("SM-10RS", "Forged",      "4685e2911b3b89c763b98756cb0dabe5a1887835-2000x2000.png"),
    ("EC-7RS",  "Forged",      "00c7f50ab45c6ed1f064b08e35afe74dde64cd66-2000x2000.png"),
    ("SM-8RS",  "Forged",      "df650e9c3ef110976c14f903e8ba12d42dbbd46a-2000x2000.png"),
    ("ML-7RT",  "Forged",      "5ce03a28e9c36770e1c5fc058030a8dc64f09836-2000x2000.png"),
    ("SL-12RT", "Forged",      "9ed4a74695838ebc2142e4d9c69a36aec6c931ed-2000x2000.png"),
    ("ML-10RT", "Forged",      "0718ff4a2f292027ed137969dd6c030e357d0030-2000x2000.png"),
    ("ARC-8RT", "Forged",      "7aeef78d01bf9ac960800d3282632056fdaa72ed-1800x1800.png"),
    ("TC-10RT", "Forged",      "8584f6870ea075cdcc06013f008553942478a772-2000x2000.png"),
    ("VS-5RX",  "Forged",      "774fce97c4cce13e6a95250749af7da52adaa6f1-2000x2000.png"),
    ("VS-5RE",  "Forged",      "d88e797f9a48a3af13ae2ebf3e2fc35f7918ada1-2000x2000.png"),
    ("SM-10RE", "Forged",      "2fb8d44f05da6241c300026d0e9197b6f447b665-2000x2000.png"),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    out_dir = config.WHEEL_CATALOG_DIR / BRAND_SLUG
    out_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for model, line, img in WHEELS:
        slug = model.lower()
        dest = out_dir / f"{slug}.jpg"
        if not dest.exists():
            try:
                # ?fm=jpg&w=900 keeps files compact and JPEG for the engine.
                dest.write_bytes(fetch(f"{CDN}{img}?fm=jpg&w=900&bg=ffffff"))
            except Exception as e:
                print(f"  !! {model}: {e}", flush=True)
                continue
        items.append(
            {
                "id": f"cat:{BRAND_SLUG}:{slug}",
                "brand": BRAND_NAME,
                "model": f"APEX {model}",
                "finish": line,
                "file": f"{BRAND_SLUG}/{slug}.jpg",
            }
        )
        print(f"  ok {model}", flush=True)
    (out_dir / "manifest.json").write_text(json.dumps(items, indent=1))
    print(f"{len(items)} wheels -> {out_dir / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
