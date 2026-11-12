"""Builds the panel's icons from SYN's brand art so Premiere shows the same logo as the app.

- plugin.png (plugin list): the app icon, scaled down.
- mark.png (panel header): the "syn" wordmark + sync link cut straight out of the app icon,
  so the panel's logo is pixel-identical to the app's (no font or CSS alignment drift).
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


def wordmark(app: Image.Image, height: int) -> Image.Image:
    """Lifts the white "syn" and the lime link off the icon's dark tile onto transparency."""
    rgb = app.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    bg = px[w // 2, int(h * 0.3)]  # plain tile above the wordmark
    inner = (int(w * 0.18), int(h * 0.18), int(w * 0.82), int(h * 0.82))  # skip the tile's edge
    xs, ys = [], []
    for y in range(inner[1], inner[3]):
        for x in range(inner[0], inner[2]):
            if max(px[x, y]) - max(bg) > 60:
                xs.append(x)
                ys.append(y)
    pad = max(2, w // 128)
    box = (min(xs) - pad, min(ys) - pad, max(xs) + pad + 1, max(ys) + pad + 1)
    crop = rgb.crop(box)
    cp = crop.load()
    out = Image.new("RGBA", crop.size)
    op = out.load()
    for y in range(crop.size[1]):
        for x in range(crop.size[0]):
            r, g, b = cp[x, y]
            target = LIME[:3] if g - b > 40 else (255, 255, 255)
            a = max((r - bg[0]) / max(1, target[0] - bg[0]), (g - bg[1]) / max(1, target[1] - bg[1]))
            a = max(0.0, min(1.0, a))
            op[x, y] = target + (round(a * 255),) if a > 0.02 else (0, 0, 0, 0)
    ratio = height / out.size[1]
    return out.resize((round(out.size[0] * ratio), height), Image.LANCZOS)


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "brand" / "icon.png"
    OUT.mkdir(parents=True, exist_ok=True)
    app = Image.open(src).convert("RGBA")
    for size, name in [(48, "plugin.png"), (96, "plugin@2x.png")]:
        app.resize((size, size), Image.LANCZOS).save(OUT / name)
    wordmark(app, 72).save(OUT / "mark.png")  # shown at 24 px tall, 3x for retina
    link(23).save(OUT / "panel.png")
    link(46).save(OUT / "panel@2x.png")
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
