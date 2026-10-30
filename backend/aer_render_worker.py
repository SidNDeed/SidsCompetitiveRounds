"""Admin evidence report: the PNG render worker (design 5.2, phase 1a).

discord_bot.py starts this file as its own long-lived python process (a fresh
interpreter, so no copy of the bot's state) and talks to it over stdin and
stdout. It imports
matplotlib itself and shares no lock, figure or state with the bot's
/compare charts (`_mpl_render_lock`).

Protocol, one plan at a time: the bot writes a 4-byte big-endian length and
that many bytes of UTF-8 JSON, a list of `[kind, text]` items (the bot's
`_aer_plan`, whose text is already encoded display text); the worker answers
the same way with `{"png": <base64>, "drawn": [[i, text, [x0, y0, x1, y1]],
...]}` or `{"error": <exception class name>}`. `drawn` is each item's drawn
text and bounding box, so a test can compare what was drawn with the plan.

Phase 1a: one neutral fill for every cell, no class, mark or swatch item
kind; font, sizes, weight and colors are fixed chrome, never read from the
plan's values; every text call passes `parse_math=False`.
"""

import base64
import io
import json
import sys

BACKGROUND = "#2b2d31"         # Discord dark grey
CELL_FILL = "#3a3c42"          # the one neutral 1a fill
TEXT_COLOR = "#e6e6e6"
FONT_FAMILY = "DejaVu Sans Mono"
FONT_SIZES = {"title": 13, "status": 9, "subject": 9, "game": 11, "seat": 10, "cell": 9,
              "flag": 9, "window": 10, "summary_head": 10, "summary": 9, "label": 8,
              "population": 9, "baseline": 9, "census": 8, "legend": 8, "footer": 8}
FILLED_KINDS = frozenset({"cell", "summary"})
LINE_H = 0.22                  # inches per plan line
WIDTH_IN = 14.0


def render(plan):
    """Draw every plan item once, in plan order, one line each: `(png bytes,
    drawn)`. An unknown kind is refused rather than drawn in a guessed
    style."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for kind, _text in plan:
        if kind not in FONT_SIZES:
            raise ValueError("unknown item kind %r" % (kind,))
    n = max(len(plan), 1)
    fig = plt.figure(figsize=(WIDTH_IN, 0.6 + n * LINE_H), dpi=100)
    try:
        fig.patch.set_facecolor(BACKGROUND)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_axis_off()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, n + 1)
        texts = []
        for i, (kind, text) in enumerate(plan):
            filled = kind in FILLED_KINDS
            bbox = ({"boxstyle": "square,pad=0.15", "facecolor": CELL_FILL,
                     "edgecolor": CELL_FILL} if filled else None)
            t = ax.text(0.04 if filled else 0.01, n - i, text, ha="left", va="center",
                        color=TEXT_COLOR, fontsize=FONT_SIZES[kind], fontweight="bold",
                        family=FONT_FAMILY, bbox=bbox, parse_math=False)
            texts.append((i, t))
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        drawn = []
        for i, t in texts:
            ext = t.get_window_extent(renderer=renderer)
            drawn.append((i, t.get_text(), (ext.x0, ext.y0, ext.x1, ext.y1)))
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=BACKGROUND)
        return buf.getvalue(), drawn
    finally:
        plt.close(fig)


def _read_exact(stream, n):
    data = b""
    while len(data) < n:
        chunk = stream.read(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def serve(inp, out, draw=render):
    """Answer plans until the input closes."""
    while True:
        head = _read_exact(inp, 4)
        if head is None:
            return
        body = _read_exact(inp, int.from_bytes(head, "big"))
        if body is None:
            return
        try:
            plan = [(str(kind), str(text)) for kind, text in json.loads(body.decode("utf-8"))]
            png, drawn = draw(plan)
            reply = {"png": base64.b64encode(png).decode("ascii"),
                     "drawn": [[i, text, list(box)] for i, text, box in drawn]}
        except Exception as ex:
            reply = {"error": type(ex).__name__}
        data = json.dumps(reply).encode("utf-8")
        out.write(len(data).to_bytes(4, "big") + data)
        out.flush()


if __name__ == "__main__":
    serve(sys.stdin.buffer, sys.stdout.buffer)
