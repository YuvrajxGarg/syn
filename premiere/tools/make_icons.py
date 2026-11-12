"""Builds the panel's icons from SYN's brand art so Premiere shows the same logo as the app.

- plugin.png (plugin list): the app icon, scaled down.
- panel.png (panel tab): the lime sync link from the mark (two dots joined by a line),
  drawn with padding so no edge touches the canvas.

    python premiere/tools/make_icons.py [path/to/app-icon.png]

The app icon defaults to brand/icon.png in the repo.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "premiere" / "plugin" / "icons"
LIME = (204, 255, 77, 255)


def link(size: int) -> Image.Image:
    s = size * 8
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    dot = s * 0.30  # dot diameter
    top, bottom = s * 0.10, s * 0.90
    cx = s / 2
    line = s * 0.11
    d.rounded_rectangle([cx - line / 2, top + dot / 2, cx + line / 2, bottom - dot / 2], radius=line / 2, fill=LIME)
    d.ellipse([cx - dot / 2, top, cx + dot / 2, top + dot], fill=LIME)
    d.ellipse([cx - dot / 2, bottom - dot, cx + dot / 2, bottom], fill=LIME)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "brand" / "icon.png"
    OUT.mkdir(parents=True, exist_ok=True)
    app = Image.open(src).convert("RGBA")
    for size, name in [(48, "plugin.png"), (96, "plugin@2x.png")]:
        app.resize((size, size), Image.LANCZOS).save(OUT / name)
    link(23).save(OUT / "panel.png")
    link(46).save(OUT / "panel@2x.png")
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
