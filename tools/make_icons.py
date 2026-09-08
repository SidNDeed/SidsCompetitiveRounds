"""Draws the two utility-strip icons (mail, music) as 64x64 RGBA white glyphs.

Supersampled 4x and downscaled with Lanczos so the edges are antialiased, matching
the style of the existing plugin/assets/mus_ic_*.png transport icons (64x64 RGBA,
white shape on a transparent ground; the UI tints them at runtime).

Run from anywhere:  python tools/make_icons.py
Writes plugin/assets/ic_mail.png and plugin/assets/ic_music.png.
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "plugin", "assets")
S = 4                      # supersample factor
N = 64 * S
WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)       # ImageDraw replaces pixels, so drawing CLEAR erases


def canvas():
    im = Image.new("RGBA", (N, N), CLEAR)
    return im, ImageDraw.Draw(im)


def save(im, name):
    im = im.resize((64, 64), Image.LANCZOS)
    path = os.path.join(OUT, name)
    im.save(path)
    print("wrote", path, im.size, im.mode)


def mail():
    """Filled envelope with the flap cut out as two transparent strokes."""
    im, d = canvas()
    x0, y0, x1, y1 = 5 * S, 14 * S, 59 * S, 50 * S
    d.rounded_rectangle([x0, y0, x1, y1], radius=5 * S, fill=WHITE)
    cx, cy = (x0 + x1) // 2, 35 * S
    w = 4 * S
    d.line([(x0 + 2 * S, y0 + 2 * S), (cx, cy)], fill=CLEAR, width=w)
    d.line([(x1 - 2 * S, y0 + 2 * S), (cx, cy)], fill=CLEAR, width=w)
    save(im, "ic_mail.png")


def music():
    """Beamed pair of eighth notes: two heads, two stems, one slanted beam."""
    im, d = canvas()
    r = 8 * S
    h1 = (19 * S, 47 * S)
    h2 = (45 * S, 41 * S)
    for hx, hy in (h1, h2):
        d.ellipse([hx - r, hy - int(r * 0.72), hx + r, hy + int(r * 0.72)], fill=WHITE)
    sw = 4 * S
    top1, top2 = 17 * S, 11 * S
    d.rectangle([h1[0] + r - sw, top1, h1[0] + r, h1[1]], fill=WHITE)
    d.rectangle([h2[0] + r - sw, top2, h2[0] + r, h2[1]], fill=WHITE)
    bw = 7 * S
    d.polygon([(h1[0] + r - sw, top1), (h2[0] + r, top2),
               (h2[0] + r, top2 + bw), (h1[0] + r - sw, top1 + bw)], fill=WHITE)
    save(im, "ic_music.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    mail()
    music()
