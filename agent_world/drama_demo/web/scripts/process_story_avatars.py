#!/usr/bin/env python3
"""Batch green-screen removal for story mode avatars (yellow-green + pure green)."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

AVATAR_DIR = Path(__file__).resolve().parents[1] / "public" / "assets" / "story" / "avatars"


def _hue_deg(r: float, g: float, b: float) -> float:
    mx = max(r, g, b)
    mn = min(r, g, b)
    d = mx - mn
    if d < 1e-6:
        return 0.0
    if mx == g:
        h = 60.0 * ((b - r) / d + 2.0)
    elif mx == r:
        h = 60.0 * (((g - b) / d) % 6.0)
    else:
        h = 60.0 * ((r - g) / d + 4.0)
    return h % 360.0


def green_screen_alpha(r: int, g: int, b: int) -> int:
    """Return alpha 0-255; 0 = fully transparent background."""
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx = max(rf, gf, bf)
    mn = min(rf, gf, bf)
    delta = mx - mn
    if delta < 0.025:
        return 255

    hue = _hue_deg(r, g, b)
    sat = delta / mx if mx > 0 else 0.0
    green_excess = gf - max(rf, bf)

    is_green_hue = 48.0 <= hue <= 168.0
    if not is_green_hue or gf < 0.22:
        return 255

    score = 0.0
    score += min(1.0, green_excess / 0.35)
    score += min(0.45, sat * 0.9)
    if 70.0 <= hue <= 145.0:
        score += 0.25
    if gf > rf and gf > bf:
        score += 0.15

    if score >= 0.72:
        return 0
    if score >= 0.42:
        t = (score - 0.42) / 0.30
        return max(0, min(255, int(255 * (1.0 - t))))
    return 255


def despill(r: int, g: int, b: int, alpha: int) -> tuple[int, int, int]:
    if alpha >= 250:
        return r, g, b
    cap = max(r, b) + 8
    return r, min(g, cap), b


def process_image(src: Path, dest: Path) -> None:
    im = Image.open(src).convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            alpha = green_screen_alpha(r, g, b)
            alpha = min(a, alpha)
            r, g, b = despill(r, g, b, alpha)
            px[x, y] = (r, g, b, alpha)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="PNG", optimize=True)
    print(f"  {src.name} -> {dest.name}")


def main() -> None:
    sources = sorted(AVATAR_DIR.glob("*.webp")) + sorted(AVATAR_DIR.glob("*.jpg"))
    if not sources:
        print(f"No sources in {AVATAR_DIR}")
        return
    print(f"Processing {len(sources)} avatars in {AVATAR_DIR}")
    for src in sources:
        dest = src.with_suffix(".png")
        process_image(src, dest)
    print("Done.")


if __name__ == "__main__":
    main()
