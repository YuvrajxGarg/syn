"""Draws the panel and plugin-list icons (five lime waveform bars, SYN's mark).

Run: python premiere/tools/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "plugin" / "icons"
LIME = (204, 255, 77, 255)
HEIGHTS = [0.40, 0.70, 0.95, 0.58, 0.32]  # same rhythm as the in-panel mark


def draw(size: int, bg: bool) -> Image.Image:
    scale = 8  # supersample, then downscale for clean edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = s * 0.12  # keep everything inside the canvas: nothing touches the edge
    if bg:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.22, fill=(24, 24, 27, 255))
        pad = s * 0.22
    inner = s - 2 * pad
    n = len(HEIGHTS)
    gap = inner / (n * 2 - 1)
    for i, h in enumerate(HEIGHTS):
        x0 = pad + i * 2 * gap
        bh = inner * h
        y0 = (s - bh) / 2
        d.rounded_rectangle([x0, y0, x0 + gap, y0 + bh], radius=gap / 2, fill=LIME)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size, bg in [("panel", 23, False), ("plugin", 48, True)]:
        draw(size, bg).save(OUT / f"{name}.png")
        draw(size * 2, bg).save(OUT / f"{name}@2x.png")
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
