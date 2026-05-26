"""Self-host the 3 webfonts used by the design system.

Fetches the Google Fonts CSS, downloads every referenced woff2 (latin +
cyrillic + cyrillic-ext subsets for all weights / italics), saves them to
<project-root>/fonts/, and writes <project-root>/fonts.css — a rewritten
@font-face block that points at the local files.

Run once:
    python -m scripts.download_fonts
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Playfair+Display:ital,wght@0,400;0,500;0,600;1,400;1,500"
    "&family=Golos+Text:wght@400;500;600"
    "&family=JetBrains+Mono:wght@400;500"
    "&display=swap"
)

# Modern UA → Google returns woff2 (with `unicode-range` blocks per subset).
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)

ROOT = Path(__file__).resolve().parent.parent.parent  # project root (above scoring/)
FONTS_DIR = ROOT / "fonts"
OUTPUT_CSS = ROOT / "fonts.css"


def http_get(url: str, *, binary: bool = False) -> bytes | str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def main() -> int:
    FONTS_DIR.mkdir(exist_ok=True)
    print(f"[fonts] fetching CSS …")
    css = http_get(CSS_URL)
    if not isinstance(css, str):
        css = css.decode("utf-8")

    urls = re.findall(r"url\((https://[^)]+\.woff2)\)", css)
    if not urls:
        print("[fonts] no woff2 urls found — Google may have served woff1.")
        return 2

    seen: dict[str, str] = {}  # remote_url -> local_filename
    rewritten = css
    for url in urls:
        if url in seen:
            continue
        fname = url.rsplit("/", 1)[-1]
        # Same filename can appear under multiple subsets — make unique by prefixing
        # the parent path's last segment (the version hash).
        parent = url.rsplit("/", 2)[-2]
        local_name = f"{parent}-{fname}"
        seen[url] = local_name
        dest = FONTS_DIR / local_name
        if dest.exists():
            print(f"[fonts] cached  {local_name}")
        else:
            print(f"[fonts] fetch   {local_name}")
            data = http_get(url, binary=True)
            dest.write_bytes(data)
        # rewrite the CSS to point at the local file (relative to fonts.css at root)
        rewritten = rewritten.replace(url, f"fonts/{local_name}")

    OUTPUT_CSS.write_text(rewritten, encoding="utf-8")
    print(f"[fonts] wrote {OUTPUT_CSS.relative_to(ROOT)}  ({len(seen)} files)")
    print(f"[fonts] dir   {FONTS_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
