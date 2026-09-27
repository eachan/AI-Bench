#!/usr/bin/env python3
"""Generate AI-Bench branding assets from a single source image.

Produces, from ``installer/brand/logo-source.png``:
  * installer/aibench.ico          - multi-size app/installer icon
  * installer/wizard-large.bmp     - Inno Setup Welcome/Finish side image (164x314)
  * installer/wizard-small.bmp     - Inno Setup header image (55x58)
  * frontend/public/favicon.ico    - web UI favicon
  * frontend/public/logo.png       - web UI sidebar logo (square, trimmed)

Re-run after replacing the source image:  python installer/gen_assets.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "installer" / "brand" / "logo-source.png"


def _bg_color(img: Image.Image) -> tuple[int, int, int]:
    # Sample a corner pixel to match the source's background (cream).
    return img.convert("RGB").getpixel((3, 3))


def _fit_onto(canvas_size: tuple[int, int], img: Image.Image, bg, pad_frac=0.06) -> Image.Image:
    cw, ch = canvas_size
    canvas = Image.new("RGB", canvas_size, bg)
    max_w = int(cw * (1 - 2 * pad_frac))
    max_h = int(ch * (1 - 2 * pad_frac))
    scaled = img.copy()
    scaled.thumbnail((max_w, max_h), Image.LANCZOS)
    x = (cw - scaled.width) // 2
    y = (ch - scaled.height) // 2
    canvas.paste(scaled, (x, y))
    return canvas


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"source image not found: {SRC}")
    img = Image.open(SRC).convert("RGB")
    bg = _bg_color(img)

    # Square logo for the web UI (kept as-is, moderate size).
    logo = img.copy()
    logo.thumbnail((256, 256), Image.LANCZOS)
    (ROOT / "frontend" / "public").mkdir(parents=True, exist_ok=True)
    logo.save(ROOT / "frontend" / "public" / "logo.png")

    # Multi-size ICOs (square, centered on background to keep 1:1).
    square = _fit_onto((max(img.size),) * 2, img, bg, pad_frac=0.02)
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    square.save(ROOT / "installer" / "aibench.ico", sizes=ico_sizes)
    square.save(ROOT / "frontend" / "public" / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    # Inno Setup wizard images (BMP).
    _fit_onto((164, 314), img, bg, pad_frac=0.08).save(ROOT / "installer" / "wizard-large.bmp")
    _fit_onto((55, 58), img, bg, pad_frac=0.04).save(ROOT / "installer" / "wizard-small.bmp")

    print("Generated:")
    for p in [
        "installer/aibench.ico",
        "installer/wizard-large.bmp",
        "installer/wizard-small.bmp",
        "frontend/public/favicon.ico",
        "frontend/public/logo.png",
    ]:
        f = ROOT / p
        print(f"  {p}  ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
