"""Scrape EVERY brand from wheelmania.co.uk into the local wheel catalog.

  .venv\\Scripts\\python.exe scrape_all.py

Discovers brand category links on /alloy-wheels/, derives display names, and
runs scrape_catalog for each. Already-downloaded images are skipped, so re-runs
only fetch what's new.
"""
import re
import sys

import scrape_catalog

INDEX = "https://wheelmania.co.uk/alloy-wheels/"

# Slugs that aren't brand categories.
SKIP = {"alloy-wheels", "custom-forged-wheels", "used-refurbished-wheels"}

# Display-name overrides where simple title-casing reads wrong.
NAME_FIX = {
    "oz-racing": "OZ Racing", "bbs": "BBS", "1av": "1AV", "1form": "1FORM",
    "momo": "MOMO", "xd": "XD", "msw": "MSW", "atm": "ATM", "ac-schnitzer": "AC Schnitzer",
    "3sdm": "3SDM", "2forge": "2Forge", "kw": "KW", "oem": "OEM", "tsw": "TSW",
}


def display_name(slug: str) -> str:
    if slug in NAME_FIX:
        return NAME_FIX[slug]
    words = slug.split("-")
    out = []
    for w in words:
        # short all-consonant tokens are usually initialisms (e.g. "bbs")
        if len(w) <= 3 and not any(v in w for v in "aeiou"):
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def main():
    page = scrape_catalog.fetch(INDEX).decode("utf-8", errors="ignore")
    # Brand tiles use RELATIVE links (href="bbs/") on the category page; also
    # accept absolute /alloy-wheels/<slug>/ forms for robustness.
    rel = {m.group(1).lower() for m in re.finditer(r'href="([a-z0-9][a-z0-9-]{1,40})/"', page)}
    abs_ = {
        m.group(1).lower()
        for m in re.finditer(r'href="(?:https://wheelmania\.co\.uk)?/alloy-wheels/([a-z0-9-]+)/?"', page)
    }
    junk = {s for s in rel if s.startswith(("wp-", "page", "cart", "checkout", "my-account", "contact", "about"))}
    slugs = sorted((rel | abs_) - SKIP - junk)
    print(f"{len(slugs)} brand categories found", flush=True)

    total = 0
    for i, slug in enumerate(slugs, 1):
        name = display_name(slug)
        print(f"[{i}/{len(slugs)}] {name} ({slug})", flush=True)
        try:
            scrape_catalog.main(f"{INDEX}{slug}/", slug, name)
        except Exception as e:
            print(f"  !! {slug} failed: {e}", flush=True)
    print("ALL BRANDS DONE", flush=True)


if __name__ == "__main__":
    main()
