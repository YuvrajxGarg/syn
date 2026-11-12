"""Renders the SYN icon: "syn" in a heavy grotesk with the lime sync link, on the same tile as Dwn, Tag and Lut.
    python assets/make_icon.py        (writes icon.png, icon.ico, AppIcon.icns and docs/icon-256.png)
Needs Pillow and the Inter Display Black font (https://rsms.me/inter/); pass a font path to override.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
LIME = (204, 255, 77, 255)
S = 1024
X0, Y0, X1, Y1 = 70, 67, 954, 951   # tile bounds, same as the Tag icon
R = 200


def tile():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((X0, Y0, X1, Y1), R, fill=255)
    grad = Image.new("RGBA", (S, S))
    d = ImageDraw.Draw(grad)
    for y in range(S):
        t = min(1, max(0, (y - Y0) / (Y1 - Y0)))
        c = round(43 + (18 - 43) * t)
        d.line([(0, y), (S, y)], fill=(c, c, c + 2, 255))
    img.paste(grad, (0, 0), mask)
    ImageDraw.Draw(img).rounded_rectangle((X0, Y0, X1, Y1), R, outline=(255, 255, 255, 36), width=4)
    # soft drop shadow underneath
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((X0, Y0 + 14, X1, Y1 + 14), R, fill=(0, 0, 0, 90))
    from PIL import ImageFilter

    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    return Image.alpha_composite(shadow, img)


def mark(img):
    """ "syn" plus the lime sync link: two dots joined by a line, from the baseline to the x-height."""
    size = 360
    font = ImageFont.truetype(FONT, size)
    kern = -0.055 * size
    widths = [font.getlength(ch) for ch in "syn"]
    link_gap, dot = 0.09 * size, 0.17 * size
    total = sum(widths) + kern * 3 + link_gap + dot
    x0 = (S - total) / 2
    asc, _ = font.getmetrics()
    xh = font.getbbox("x", anchor="ls")[1] * -1          # x-height above the baseline
    desc = font.getbbox("y", anchor="ls")[3]
    baseline = (Y0 + Y1) / 2 + (xh - desc) / 2
    d = ImageDraw.Draw(img)
    x = x0
    for ch, w in zip("syn", widths):
        d.text((x, baseline), ch, font=font, fill=(255, 255, 255, 245), anchor="ls")
        x += w + kern
    cx = x + link_gap + dot / 2
    top, bot = baseline - xh, baseline
    lw = 0.062 * size
    d.rounded_rectangle((cx - lw / 2, top + dot / 2, cx + lw / 2, bot - dot / 2), lw / 2, fill=LIME)
    d.ellipse((cx - dot / 2, top, cx + dot / 2, top + dot), fill=LIME)
    d.ellipse((cx - dot / 2, bot - dot, cx + dot / 2, bot), fill=LIME)
    return img


img = mark(tile())
img.save(os.path.join(HERE, "icon.png"))
img.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "..", "docs", "icon-256.png"))
img.save(os.path.join(HERE, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(os.path.join(HERE, "AppIcon.icns"))
print("icons written")
