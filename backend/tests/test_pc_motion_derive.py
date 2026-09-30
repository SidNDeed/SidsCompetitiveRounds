"""Dance cards: the derivation (design S4.2-S4.5; section 12 M5, M8) -- T19,
T20, T21, T22, T23, T24 and T67.

Each test is one named assertion; the mutation that must fail it is planted
by the lane's mutation runner and recorded in its log, and the test's own
passing case is the control (#391). T21 and T22 draw with the real,
unchanged renderer; the encoder tests (T23, T24) use the fixtures' fast
stand-in with the renderer's geometry, so they measure the encoder and not
the face. Frames from a captured corpus (PC_MOTION_CORPUS_DIR) join T22 when
the directory is set.
"""
import glob
import io
import os
import shutil
import subprocess
import sys

import pytest
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, "..", "api")
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import pc_face  # noqa: E402
import pc_motion as pcm  # noqa: E402
import pc_motion_fixtures as fx  # noqa: E402
import pc_portrait  # noqa: E402

RFP = "0123456789abcdef"


def rgba(png):
    with Image.open(io.BytesIO(png)) as source:
        source.load()
        return source.convert("RGBA")


# -- T19: the revisions ----------------------------------------------------------------

def test_motion_rev_inputs():
    """T19 (S4.3): each input of motion_rev and motion_preview_rev moves it --
    the motion fingerprint, the face (or preview) revision, the motion hash
    -- and nothing else is an input, so another player's motion cannot move
    this print's rev (the live half: T30). Control: identical inputs give one
    rev. Mutation: face_rev dropped from the rev."""
    fp, face, mh = "1" * 16, "2" * 16, "3" * 64
    base = pcm.motion_rev(fp, face, mh)
    assert base == pcm.motion_rev(fp, face, mh) and len(base) == 16
    assert pcm.motion_rev("4" * 16, face, mh) != base
    assert pcm.motion_rev(fp, "5" * 16, mh) != base
    assert pcm.motion_rev(fp, face, "6" * 64) != base
    prev = pcm.motion_preview_rev(fp, face, mh)
    assert prev != base, "the preview key is its own namespace"
    assert pcm.motion_preview_rev("4" * 16, face, mh) != prev
    assert pcm.motion_preview_rev(fp, "5" * 16, mh) != prev
    assert pcm.motion_preview_rev(fp, face, "6" * 64) != prev
    # nothing is keyed on a placeholder
    assert pcm.motion_rev(None, face, mh) is None and pcm.motion_rev(fp, None, mh) is None
    assert pcm.motion_rev(fp, face, None) is None and pcm.motion_fingerprint(None) is None


# -- T20: the fingerprint covers the module ----------------------------------------------

def test_motion_fp_covers_module(tmp_path):
    """T20 (S4.3): a comment-only edit of pc_motion.py moves motion_fp, as do
    renderer_fp and the encoder parameters. Control: two reads of an
    unchanged tree agree. Mutation: the hash without the module bytes."""
    src = os.path.join(API, "pc_motion.py")
    a = tmp_path / "a" / "pc_motion.py"
    b = tmp_path / "b" / "pc_motion.py"
    a.parent.mkdir()
    b.parent.mkdir()
    shutil.copyfile(src, a)
    shutil.copyfile(src, b)
    with open(b, "ab") as fh:
        fh.write(b"# a comment and nothing else\n")
    fa = pcm.motion_fingerprint(RFP, path=str(a))
    assert fa == pcm.motion_fingerprint(RFP, path=str(a)) and len(fa) == 16
    assert pcm.motion_fingerprint(RFP, path=str(b)) != fa
    assert pcm.motion_fingerprint("fedcba9876543210", path=str(a)) != fa
    live = pcm.motion_fingerprint(RFP)
    assert live == pcm.motion_fingerprint(RFP, path=src)
    old = pcm.CARD_CELL
    try:
        pcm.CARD_CELL = old + 1
        assert pcm.motion_fingerprint(RFP) != live, "the encoder parameters are an input"
    finally:
        pcm.CARD_CELL = old
    assert pcm.motion_fingerprint(RFP) == live


# -- T21: reconstruction outside the window (M8) -------------------------------------------

VARIANTS = (("plain", {}), ("foil", {"foil": True}), ("signed", {"signed": True}),
            ("badge", {"top_card": "Poison", "top_card_rgb": (120, 200, 60)}))


def test_window_reconstruction():
    """T21 (S4.4, M8): for every band, plain, foil, signed and badge, two
    locales, card and tile, the face drawn from the still with its window
    replaced by the window of the face drawn from frame k equals the face
    drawn from frame k, pixel for pixel. The fixture's still reaches its own
    edge and the frames reach the first index they may change, so the strip
    a shrunk window drops differs between the two faces. Control: the full
    window. Mutations: the card window shrunk 2 px; the tile window shrunk
    2 px."""
    still = fx.edge_still()
    frame = pcm.frame_portrait(fx.edge_frame(0.25))
    for band in pc_face.BANDS:
        for _name, extra in VARIANTS:
            for labels in ({}, fx.LABELS_XX):
                s = fx.spec(band=band, **extra)
                for size, window in (("card", pcm.CARD_WINDOW), ("tile", pcm.TILE_WINDOW)):
                    r_s = rgba(pc_face.render_face(s, labels, still, size))
                    r_k = rgba(pc_face.render_face(s, labels, frame, size))
                    assert r_s.tobytes() != r_k.tobytes()
                    rebuilt = r_s.copy()
                    rebuilt.paste(r_k.crop(window), window[:2])
                    assert rebuilt.tobytes() == r_k.tobytes(), (band, _name, bool(labels), size)


# -- T22: the nearest-neighbour identity ----------------------------------------------------

def corpus_frames():
    root = os.environ.get("PC_MOTION_CORPUS_DIR")
    if not root:
        return []
    out = []
    for path in sorted(glob.glob(os.path.join(root, "*.scrmotion"))):
        with open(path, "rb") as fh:
            _header, frames = pcm.parse_container(fh.read())
        out.extend(frames[::20])
    return out


def test_nn_upscale_identity():
    """T22 (S4.2): the renderer's portrait path over the x2 nearest-neighbour
    upscale draws the frame itself at card (reduce 2) and the frame reduced
    by 2 at tile (reduce 4): alpha_composite(bg, frame) and its reduce(2),
    exactly, on the fixture frames and on captured frames when a corpus is
    set. Control: nearest passes. Mutation: the upscale bilinear."""
    frames = [fx.edge_frame(t) for t in (0.0, 0.3, 0.7)] + fx.smooth_frames(2) + corpus_frames()
    for png in frames:
        frame = rgba(png)
        over = Image.alpha_composite(Image.new("RGBA", frame.size, pc_face._portrait_bg()), frame)
        up = pcm.frame_portrait(png)
        assert pc_face.png_ihdr(up) == pc_face._PORTRAIT_IHDR
        assert pc_face._portrait_image(up, pc_face.PORTRAIT_CARD).tobytes() == over.tobytes()
        assert pc_face._portrait_image(up, pc_face.PORTRAIT_TILE).tobytes() == over.reduce(2).tobytes()


# -- T67: the atlas layout and its caps --------------------------------------------------------

def test_atlas_layout_and_caps(monkeypatch):
    """T67 (S4.4): the card and tile atlases hold frame k in row-major cell
    k of eight columns, each cell the LANCZOS resize of R_k's window; an
    encoded atlas above its cap is not published (None, the key's 404
    motion_too_large) while the other size still is. Control: both
    published under the real caps. Mutations: the cells column-major; the
    cap not applied."""
    frames = [fx.edge_frame(k / 80.0) for k in range(80)]
    body = fx.container("dance_bounce", frames)
    s = fx.spec()
    card, tile = pcm.derive_atlases(s, {}, body, render=fx.fake_render)
    assert card is not None and tile is not None
    c, t = rgba(card), rgba(tile)
    assert c.size == (8 * pcm.CARD_CELL, 10 * pcm.CARD_CELL) and t.size == (8 * pcm.TILE_CELL, 10 * pcm.TILE_CELL)
    for k in (0, 1, 7, 8, 9, 79):
        col, row = k % 8, k // 8
        for atlas, size, window, cell in ((c, "card", pcm.CARD_WINDOW, pcm.CARD_CELL),
                                          (t, "tile", pcm.TILE_WINDOW, pcm.TILE_CELL)):
            want = rgba(fx.fake_render(s, {}, pcm.frame_portrait(frames[k]), size)).crop(window).resize(
                (cell, cell), Image.Resampling.LANCZOS)
            got = atlas.crop((col * cell, row * cell, (col + 1) * cell, (row + 1) * cell))
            assert got.tobytes() == want.tobytes(), (k, size)
    monkeypatch.setattr(pcm, "CARD_ATLAS_MAX_BYTES", len(card) - 1)
    assert pcm.derive_atlases(s, {}, body, render=fx.fake_render) == (None, tile)
    monkeypatch.setattr(pcm, "CARD_ATLAS_MAX_BYTES", 12 << 20)
    monkeypatch.setattr(pcm, "TILE_ATLAS_MAX_BYTES", len(tile) - 1)
    assert pcm.derive_atlases(s, {}, body, render=fx.fake_render) == (card, None)


# -- T23: the preview GIF is deterministic -------------------------------------------------------

def gif_blocks(data):
    """(global table?, loop count, [(local table?, delay cs, disposal, transparent index)])
    read from the GIF's own blocks."""
    assert data[:6] == b"GIF89a"
    flags = data[10]
    pos = 13 + (3 * (2 << (flags & 7)) if flags & 0x80 else 0)
    loop, frames, gce = None, [], None
    while pos < len(data):
        kind = data[pos]
        if kind == 0x3B:
            break
        if kind == 0x21:
            label = data[pos + 1]
            pos += 2
            body = b""
            while data[pos]:
                body += data[pos + 1:pos + 1 + data[pos]]
                pos += 1 + data[pos]
            pos += 1
            if label == 0xF9:
                gce = (body[1] | (body[2] << 8), (body[0] >> 2) & 7, body[3] if body[0] & 1 else None)
            elif label == 0xFF and body[:11] == b"NETSCAPE2.0":
                loop = body[12] | (body[13] << 8)
            continue
        assert kind == 0x2C, hex(kind)
        packed = data[pos + 9]
        pos += 10
        if packed & 0x80:
            pos += 3 * (2 << (packed & 7))
        pos += 1                                  # LZW minimum code size
        while data[pos]:
            pos += 1 + data[pos]
        pos += 1
        frames.append((bool(packed & 0x80),) + (gce or (0, 0, None)))
        gce = None
    return bool(flags & 0x80), loop, frames


GIF_SCRIPT = r"""
import hashlib, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
import pc_motion as pcm
import pc_motion_fixtures as fx
body = fx.container("dance_bounce", fx.smooth_frames(80))
size, gif = pcm.derive_preview_gif(fx.spec(), {}, fx.edge_still(), body, render=fx.fake_render)
sys.stdout.write(size + " " + hashlib.sha256(gif).hexdigest())
"""


def test_gif_deterministic():
    """T23 (S4.5): two runs in two processes are byte-equal; the GIF carries
    one global palette and no local one, loop 0, disposal 1 on every frame,
    the transparent index; the delays sum to N x period (merged identical
    frames sum theirs). Control: the fixed palette passes. Mutation:
    per-frame palettes."""
    import hashlib
    body = fx.container("dance_bounce", fx.smooth_frames(80))
    size, gif = pcm.derive_preview_gif(fx.spec(), {}, fx.edge_still(), body, render=fx.fake_render)
    assert size == "card"
    mine = size + " " + hashlib.sha256(gif).hexdigest()
    other = subprocess.run([sys.executable, "-c", GIF_SCRIPT, os.path.abspath(API), HERE],
                           capture_output=True, text=True, timeout=600)
    assert other.returncode == 0, other.stderr[-2000:]
    assert other.stdout.strip() == mine
    global_table, loop, frames = gif_blocks(gif)
    assert global_table and loop == 0 and frames
    assert not any(local for local, _d, _p, _t in frames), "a frame carries its own palette"
    assert all(disposal == 1 and transparent == pcm.GIF_COLOURS for _l, _d, disposal, transparent in frames)
    period = pcm.table_row(pcm.MOTION_RECIPE, "dance_bounce")[0]
    assert sum(delay for _l, delay, _p, _t in frames) * 10 == 80 * period


# -- T24: the size ladder, one 4 MiB card ceiling (M5) -------------------------------------------------

def test_gif_size_ladder():
    """T24 (S4.5, M5): a card GIF above 4 MiB falls to the tile GIF; a tile
    GIF above 3 MiB falls to none (the key's 404 motion_too_large); exactly
    at a cap is inside it; the tile GIF is encoded only when the card GIF did
    not fit. The 4 MiB card ceiling is ONE number end to end -- this module's,
    the face route's card cap, the bot's face fetch cap -- and no 8 MiB cap
    is carried. A real noisy capture overflows the card rung and lands on a
    later one. Control: a small fixture stays card. Mutation: the tile rung
    skipped."""
    mib = 1 << 20
    calls = []

    def enc(tag, n):
        def go():
            calls.append(tag)
            return b"x" * n
        return go
    assert pcm.gif_ladder(enc("c", 4 * mib), enc("t", 1)) == ("card", b"x" * (4 * mib)) and calls == ["c"]
    assert pcm.gif_ladder(enc("c", 4 * mib + 1), enc("t", 3 * mib)) == ("tile", b"x" * (3 * mib))
    assert pcm.gif_ladder(enc("c", 4 * mib + 1), enc("t", 3 * mib + 1)) == (None, None)
    # M5: one ceiling end to end
    assert pcm.CARD_GIF_MAX_BYTES == 4 * mib == pc_portrait.PC_FACE_MAX_BYTES
    assert pcm.TILE_GIF_MAX_BYTES == 3 * mib
    with open(os.path.join(HERE, "..", "discord_bot.py"), encoding="utf-8") as fh:
        bot = fh.read()
    assert "_PC_FACE_MAX_BYTES = 4 * 1024 * 1024" in bot
    with open(os.path.join(API, "pc_motion.py"), encoding="utf-8") as fh:
        mine = fh.read()
    assert "8 << 20" not in mine and "8 * 1024 * 1024" not in mine
    # a real overflow: noisy dancers on the card rung
    body = fx.container("dance_robot", fx.noise_frames(120))
    card = pcm._gif_at("card", fx.spec(), {}, fx.edge_still(), body, None, None, fx.fake_render)
    assert len(card) > pcm.CARD_GIF_MAX_BYTES, len(card)
    size, gif = pcm.derive_preview_gif(fx.spec(), {}, fx.edge_still(), body, render=fx.fake_render)
    assert size != "card" and (gif is None or len(gif) <= pcm.TILE_GIF_MAX_BYTES), (size, gif and len(gif))
    # control: a small fixture stays card
    small = fx.container("dance_bounce", fx.smooth_frames(80))
    assert pcm.derive_preview_gif(fx.spec(), {}, fx.edge_still(), small, render=fx.fake_render)[0] == "card"
