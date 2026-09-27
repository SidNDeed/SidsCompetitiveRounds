"""Player Card dance motion: the upload's container and content checks, the
decode pool and its admission (dance cards design S2.3-S2.6).

No FastAPI and no SQL here: main.py owns the routes and every statement.
pc_face.py is read and never edited -- its bytes are part of renderer_fp, so
an edit there would re-key every static face URL in the fleet (S4.1). This
module reuses its PNG walk, its IHDR reader, its portrait background and its
pinned encoder, read-only.
"""
# Every import is bound under a private name: the route manifest gate folds a
# module-level name of ANY api module into the fingerprint of every route that
# references that name, so a public `time` or `re` here would move every route
# in main.py that uses its own `time` or `re` (backend/tests/
# test_route_manifest_net_seat.py, _walk_bindings).
import asyncio as _asyncio
import concurrent.futures as _futures
import hashlib as _hashlib
import io as _pcm_io                  # not _io / _re: main.py binds both
import re as _pcm_re
import threading as _threading
import time as _time
import warnings as _warnings

from PIL import Image as _Image, ImageChops as _ImageChops

import pc_face as _face
import pc_portrait as _pcm_portrait

# -- the table (S2.4) --------------------------------------------------------
# The capture recipe this build derives and accepts. A header naming another
# recipe has no table row and is refused as motion_shape.
MOTION_RECIPE = 1
# recipe -> dance sku -> (frame period in ms, frame count). For every row,
# frames = the client's Defs duration x 1000 / period, against the client's
# own capture table (DanceEmotes.CaptureMs): test T43 reads all three.
MOTION_TABLE = {
    1: {
        "dance_bounce": (50, 80),
        "dance_wave": (50, 80),
        "dance_jacks": (50, 90),
        "dance_shimmy": (40, 100),
        "dance_disco": (50, 100),
        "dance_helicopter": (50, 110),
        "dance_robot": (50, 120),
        "dance_floss": (50, 100),
    },
}


def table_row(recipe, sku):
    """(period ms, frames) of one dance under one recipe, or None."""
    return MOTION_TABLE.get(recipe, {}).get(sku)


def recipe_known(recipe):
    return recipe in MOTION_TABLE


# -- transport and container (S2.2, S2.3) -------------------------------------
MOTION_CONTENT_TYPE = "application/x-scr-motion"
MOTION_MAX_BYTES = 12 << 20          # declared, received and canonical (== the table's CHECK)
MOTION_MAGIC = b"SCRMOT1\n"
HEADER_MAX = 512
FRAME_MAX_BYTES = 262144             # one frame, received and canonical
FRAME_EDGE = 590
MOTION_DAY_CAP = 8                   # charged decode attempts per player per UTC day (S2.6 step 9)
MOTION_CAPACITY_BYTES = 1 << 30      # every stored source together (S2.6 phase C, S10 Q7)

_HEADER_RE = _pcm_re.compile(
    r"dance=(?P<dance>dance_[a-z]{1,24});recipe=(?P<recipe>[1-9][0-9]{0,2});"
    r"frames=(?P<frames>[1-9][0-9]{0,2});ms=(?P<ms>[1-9][0-9]{0,3});"
    r"static=(?P<static>[0-9a-f]{64})")


class MotionRefusal(Exception):
    """A refusal: its HTTP status and its JSON detail ({"error": ..., ...})."""

    def __init__(self, status, error, **extra):
        super().__init__(error)
        self.status = int(status)
        self.detail = dict(error=error, **extra)


def content_type_ok(value):
    """M2: the normalised Content-Type EQUALS application/x-scr-motion.

    Never the static writer's prefix test: `application/x-scr-motionjunk`
    and a parameter suffix (`...; charset=x`) are both 415."""
    return (value or "").strip().lower() == MOTION_CONTENT_TYPE


def canon_motion(steam_id, nonce, body_sha256, descriptor):
    """The motion writer's signed line (S2.1), beside canon_portrait."""
    return f"pcmotion:{steam_id}:{nonce}:{body_sha256}:{descriptor}"


def canon_dance(steam_id, nonce, item_id):
    """The selection route's signed line (S2.10); item_id exactly as sent."""
    return f"pcdance:{steam_id}:{nonce}:{item_id}"


def header_text(dance, recipe, frames, ms, static_hash):
    return f"dance={dance};recipe={int(recipe)};frames={int(frames)};ms={int(ms)};static={static_hash}"


def build_container(header, frames):
    """The one accepted layout: magic, 4-byte BE header length, the ASCII
    header, then per frame a 4-byte BE length and the PNG."""
    head = header.encode("ascii")
    out = [MOTION_MAGIC, len(head).to_bytes(4, "big"), head]
    for png in frames:
        out.append(len(png).to_bytes(4, "big"))
        out.append(bytes(png))
    return b"".join(out)


def parse_container(body):
    """(header, frames) of the one accepted shape (S2.3), else MotionRefusal
    422 motion_container; a header whose dance, recipe, frame count or period
    is not its table row is 422 motion_shape (S2.4).

    The walk takes the frame count from the TABLE, never from the header
    (T3): the header must equal the row before a single frame is walked."""
    raw = bytes(body)
    if len(raw) < 12 or raw[:8] != MOTION_MAGIC:
        raise MotionRefusal(422, "motion_container")
    hlen = int.from_bytes(raw[8:12], "big")
    if not 1 <= hlen <= HEADER_MAX or 12 + hlen > len(raw):
        raise MotionRefusal(422, "motion_container")
    try:
        text = raw[12:12 + hlen].decode("ascii")
    except UnicodeDecodeError:
        raise MotionRefusal(422, "motion_container") from None
    m = _HEADER_RE.fullmatch(text)
    if m is None:
        raise MotionRefusal(422, "motion_container")
    header = {"dance": m["dance"], "recipe": int(m["recipe"]), "frames": int(m["frames"]),
              "ms": int(m["ms"]), "static": m["static"], "text": text}
    row = table_row(header["recipe"], header["dance"])
    if row is None or (header["ms"], header["frames"]) != row:
        raise MotionRefusal(422, "motion_shape")
    count = row[1]
    frames = []
    off = 12 + hlen
    for _k in range(count):
        if off + 4 > len(raw):
            raise MotionRefusal(422, "motion_container")
        size = int.from_bytes(raw[off:off + 4], "big")
        off += 4
        if not 1 <= size <= FRAME_MAX_BYTES or off + size > len(raw):
            raise MotionRefusal(422, "motion_container")
        frames.append(raw[off:off + size])
        off += size
    if off != len(raw):
        raise MotionRefusal(422, "motion_container")
    return header, frames


# -- content checks (S2.5) ----------------------------------------------------
MOTION_COVERAGE_MIN, MOTION_COVERAGE_MAX = 0.02, 0.60
EDGE_MARGIN = 2                      # the band of pixels along each edge that must stay clear
FLASH_DY = 0.05                      # a pixel is "changed" when |dY| exceeds this
FLASH_CHANGED_MAX = 0.35             # a pair is refused above this changed fraction
FLASH_MEAN_MAX = 0.20                # ... or above this mean |dY|
DECODE_DEADLINE_S = 20.0             # checked after every frame (overrun <= one frame step, L7)

_FRAME_IHDR = (FRAME_EDGE, FRAME_EDGE, 8, 6, 0)
_FORBIDDEN_CHUNKS = frozenset({b"acTL", b"fcTL", b"fdAT"})
# Rec. 709 luma of gamma-encoded RGB, as an RGB -> L matrix (Pillow, the api's
# only image library; the result is 8-bit, so |dY| is compared in 1/255 steps).
_LUMA709 = (0.2126, 0.7152, 0.0722, 0.0)
# |dY| > FLASH_DY on the 8-bit luma: a difference of at least this many steps.
_CHANGED_STEPS = int(FLASH_DY * 255) + 1


def _edge_boxes(edge=FRAME_EDGE, margin=EDGE_MARGIN):
    if margin <= 0:
        return ()
    return ((0, 0, edge, margin), (0, edge - margin, edge, edge),
            (0, 0, margin, edge), (edge - margin, 0, edge, edge))


def _frame_refusal(reason, index, **extra):
    return MotionRefusal(422, reason, frame=int(index), **extra)


def check_frame(png, index):
    """One frame's S2.5 checks, in order. Returns (canonical PNG bytes, the
    RGBA frame with every alpha-zero pixel (0,0,0,0)); else MotionRefusal 422
    motion_frame_invalid / motion_coverage / motion_edge with the index."""
    try:
        chunks = _face.png_chunks(png)            # <= 4096 chunks, CRCs, IEND last, nothing after
    except ValueError:
        raise _frame_refusal("motion_frame_invalid", index) from None
    if any(kind in _FORBIDDEN_CHUNKS for kind, _size in chunks):
        raise _frame_refusal("motion_frame_invalid", index)
    try:
        ihdr = _face.png_ihdr(png)
    except ValueError:
        raise _frame_refusal("motion_frame_invalid", index) from None
    if tuple(ihdr) != _FRAME_IHDR:
        raise _frame_refusal("motion_frame_invalid", index)
    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("error", _Image.DecompressionBombWarning)
            with _Image.open(_pcm_io.BytesIO(bytes(png))) as source:
                if (source.format or "").upper() != "PNG" or source.size != (FRAME_EDGE, FRAME_EDGE):
                    raise ValueError("decode")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("animated")
                source.load()
                if source.mode != "RGBA":
                    raise ValueError("mode")
                frame = _Image.frombytes("RGBA", source.size, source.tobytes())
    except Exception:
        raise _frame_refusal("motion_frame_invalid", index) from None
    alpha = frame.getchannel("A")
    coverage = 1.0 - alpha.histogram()[0] / float(FRAME_EDGE * FRAME_EDGE)
    if not MOTION_COVERAGE_MIN <= coverage <= MOTION_COVERAGE_MAX:
        raise _frame_refusal("motion_coverage", index)
    for box in _edge_boxes():
        if alpha.crop(box).getextrema()[1] > 0:
            raise _frame_refusal("motion_edge", index)
    hidden = alpha.point(lambda value: 255 if value == 0 else 0)
    frame.paste((0, 0, 0, 0), (0, 0, FRAME_EDGE, FRAME_EDGE), hidden)
    try:
        canonical = _face._encode_rgba(frame)
    except Exception:
        raise _frame_refusal("motion_frame_invalid", index) from None
    if len(canonical) > FRAME_MAX_BYTES:
        raise _frame_refusal("motion_frame_invalid", index, reason="canonical_too_large")
    return canonical, frame


def luma(frame):
    """The frame composited over the portrait background, as 8-bit Rec. 709
    luma: what the pairwise flash check compares."""
    over = _Image.alpha_composite(_Image.new("RGBA", frame.size, _face._portrait_bg()), frame)
    return over.convert("RGB").convert("L", _LUMA709)


def flash_pair(y_a, y_b):
    """(changed fraction, mean |dY|) of two luma images."""
    hist = _ImageChops.difference(y_a, y_b).histogram()
    n = float(y_a.size[0] * y_a.size[1])
    changed = sum(hist[_CHANGED_STEPS:]) / n
    mean = sum(i * c for i, c in enumerate(hist)) / (n * 255.0)
    return changed, mean


def flash_refused(changed, mean):
    return changed > FLASH_CHANGED_MAX or mean > FLASH_MEAN_MAX


def decode_frames(header, frames, deadline_s=DECODE_DEADLINE_S, clock=_time.monotonic):
    """Phase B (S2.5): every frame's checks, then its pair with the previous
    frame, in order; the loop wrap (N-1, 0) last. Returns (canonical
    container, motion_hash, stats). The deadline is checked AFTER every
    frame, so a decode ends at most one frame step past it (L7): 503
    motion_busy. A canonical container above 12 MiB is 413."""
    t0 = clock()
    canonical = []
    first = prev = None
    worst = (0.0, 0.0, -1)
    step_max = 0.0
    for k, png in enumerate(frames):
        t_step = clock()
        data, frame = check_frame(png, k)
        y = luma(frame)
        del frame
        if prev is not None:
            changed, mean = flash_pair(prev, y)
            if changed > worst[0]:
                worst = (changed, max(mean, worst[1]), k - 1)
            if flash_refused(changed, mean):
                raise _frame_refusal("motion_flash", k - 1, pair=[k - 1, k],
                                     changed=round(changed, 4), mean=round(mean, 4))
        else:
            first = y
        prev = y
        canonical.append(data)
        now = clock()
        step_max = max(step_max, now - t_step)
        if now - t0 > deadline_s:
            raise MotionRefusal(503, "motion_busy", reason="deadline", frame=k)
    n = len(canonical)
    if n > 1:
        changed, mean = flash_pair(prev, first)
        if flash_refused(changed, mean):
            raise _frame_refusal("motion_flash", n - 1, pair=[n - 1, 0],
                                 changed=round(changed, 4), mean=round(mean, 4))
    container = build_container(header["text"], canonical)
    if len(container) > MOTION_MAX_BYTES:
        raise MotionRefusal(413, "motion_too_large")
    return container, _hashlib.sha256(container).hexdigest(), {
        "frames": n, "bytes": len(container), "secs": round(clock() - t0, 3),
        "step_max": round(step_max, 4), "worst_changed": round(worst[0], 4)}


# -- the decode pool and its admission (S2.5, S2.6 step 11) ---------------------
# ONE worker, separate from pc_portrait.POOL (the two static render workers):
# a motion decode must never hold a static face's worker.
DECODE_POOL = _futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="pc-motion-decode")
DECODE_WAITING = 2                   # at most this many claims waiting behind the one running


class DecodeAdmission:
    """Non-blocking claims on the decode pool: one running plus at most
    DECODE_WAITING waiting, and at most one per player. A claim is taken in
    phase A before the charge commits and is released by the decode's own
    worker when it ends (or by phase A itself when it never reaches the
    pool), never by a request that stopped waiting."""

    def __init__(self, capacity=1 + DECODE_WAITING):
        self._lock = _threading.Lock()
        self._held = {}
        self.capacity = int(capacity)

    def try_claim(self, player_key):
        with self._lock:
            if player_key in self._held or len(self._held) >= self.capacity:
                return None
            token = object()
            self._held[player_key] = token
            return token

    def release(self, player_key, token):
        with self._lock:
            if token is not None and self._held.get(player_key) is token:
                del self._held[player_key]

    def held(self):
        with self._lock:
            return len(self._held)


DECODE_ADMISSION = DecodeAdmission()


def _decode_guarded(admission, player_key, token, header, frames, deadline_s):
    """Runs IN the decode pool; the claim is released here, by the worker."""
    try:
        return decode_frames(header, frames, deadline_s)
    finally:
        admission.release(player_key, token)


def submit_decode(admission, player_key, token, header, frames, deadline_s=DECODE_DEADLINE_S):
    """Queue phase B on the one decode worker; the claim travels with the job.

    The worker releases the claim when the decode ends. A job cancelled before
    it ever ran releases it from the done-callback instead, so no path can
    strand a claim: a stranded claim would refuse that player, and hold one of
    the three slots, until the process restarts."""
    job = DECODE_POOL.submit(_decode_guarded, admission, player_key, token, header, frames, deadline_s)
    job.add_done_callback(lambda f: admission.release(player_key, token) if f.cancelled() else None)
    return job


async def await_decode(job):
    """Await a submitted decode, shielded: a request that stops waiting (its
    client went away) never cancels the queued job, which still runs and
    releases its own claim."""
    return await _asyncio.shield(_asyncio.wrap_future(job))


async def decode_in_pool(admission, player_key, token, header, frames, deadline_s=DECODE_DEADLINE_S):
    """Phase B on the one decode worker (submit, then await shielded)."""
    return await await_decode(submit_decode(admission, player_key, token, header, frames, deadline_s))


# -- ownership, the selection and the servable predicate (S2.6 step 6, S4.9) --
# Each term has ONE spelling, used by every surface that asks it: the motion
# upload, the selection route, /pc/me, the atlas route, the per-visit read and
# the bot's GIF route. The rows come from main's `_pc_motion_servable_cols`
# (or, for the upload and the selection, from statements that name the same
# columns). The shop-owner exemption is main's `_auto_owned`, passed in as
# `auto_owned`: this module cannot import main, and a second spelling of the
# exemption here is the defect `_auto_owned`'s docstring records (#279, #341).

def owns_dance(row, steam_id, auto_owned):
    """A player_items row for the subject and the item (`dance_bought`), or
    the exemption for the item's sku."""
    return bool(row.get("dance_bought")) or bool(auto_owned(steam_id, row.get("dance_sku")))


def dance_held(row, steam_id, auto_owned):
    """S4.9's selection terms: the selected item is a ready dance the subject
    owns. /pc/me's `pc_dance_sku` is non-empty exactly when this holds (S2.9)."""
    return (row.get("active_dance_id") is not None and row.get("dance_kind") == "dance"
            and bool(row.get("dance_ready")) and owns_dance(row, steam_id, auto_owned))


def servable(row, steam_id, auto_owned):
    """S4.9: a motion row exists for the subject; the subject is neither
    deleted nor banned and its still's kind is `game` (pc_portrait.portrait_for,
    the face readers' own resolution); the S3.4 binding holds -- the motion's
    still hash and descriptor equal the subject's current ones; the selection
    is the motion's item; and `dance_held`."""
    if row is None or not row.get("m_hash"):
        return False
    kind, still = _pcm_portrait.portrait_for(row)
    if kind != "game" or row.get("m_static") != still or row.get("m_descriptor") != row.get("portrait_descriptor"):
        return False
    if row.get("m_item") is None or row.get("m_item") != row.get("active_dance_id"):
        return False
    return dance_held(row, steam_id, auto_owned)


# -- derivation: the fingerprint, the revisions and the jobs (S4.2-S4.5) -------
import functools as _pcm_functools
import os as _pcm_os

ATLAS_COLUMNS = 8                    # row-major cells, eight per atlas row (S4.4)
CARD_CELL, TILE_CELL = 256, 96       # a cell's edge in the card atlas and the tile atlas
# The portrait window of a rendered face, (left, top, right, bottom): the
# only pixels of a face that its portrait moves (S4.4; T21 proves every other
# pixel equal). If a fixture ever fails that, the window grows -- never the
# tolerance.
CARD_WINDOW = (80, 150, 670, 740)
TILE_WINDOW = (40, 75, 335, 370)
CARD_ATLAS_MAX_BYTES = 12 << 20      # an encoded atlas above its cap is not published;
TILE_ATLAS_MAX_BYTES = 6 << 20       # its key answers 404 motion_too_large
GIF_COLOURS = 255                    # one fixed palette by median cut, plus one transparent index
GIF_ALPHA_THRESHOLD = 128            # a pixel under this alpha is the transparent index
# M5: ONE 4 MiB card-GIF ceiling end to end -- the bot's face cap
# (_PC_FACE_MAX_BYTES) and the face route's card ceiling. Above it the tile
# GIF is tried at 3 MiB, then none. No path carries 8 MiB.
CARD_GIF_MAX_BYTES = 4 << 20
TILE_GIF_MAX_BYTES = 3 << 20
JOB_DEADLINE_S = 120.0               # checked after every frame render and every encode step (S4.6)


class MotionDeadline(Exception):
    """A derivation passed its deadline and stopped at the step that noticed:
    it overran by at most that one step (S4.6)."""


def encoder_params():
    """Every encoder choice a derived byte depends on, as one string (S4.3):
    the cells, windows and columns of the atlas, the resampling, the palette
    method, dither, transparency, disposal, loop, delay and the caps."""
    return ";".join((
        "upscale=nearest-x2", "atlas-cols=%d" % ATLAS_COLUMNS,
        "card=%d@%s" % (CARD_CELL, ",".join(str(v) for v in CARD_WINDOW)),
        "tile=%d@%s" % (TILE_CELL, ",".join(str(v) for v in TILE_WINDOW)),
        "resample=lanczos", "png=pc_face-encoder",
        "atlas-max=%d,%d" % (CARD_ATLAS_MAX_BYTES, TILE_ATLAS_MAX_BYTES),
        "gif-colours=%d" % GIF_COLOURS, "gif-quantize=median-cut", "gif-dither=none", "gif-table=global",
        "gif-alpha=%d" % GIF_ALPHA_THRESHOLD, "gif-disposal=1", "gif-loop=0", "gif-delay=period",
        "gif-max=%d,%d" % (CARD_GIF_MAX_BYTES, TILE_GIF_MAX_BYTES)))


@_pcm_functools.lru_cache(maxsize=8)
def _motion_fp_cached(renderer_fp, path, _size, _mtime_ns, params):
    with open(path, "rb") as source:
        code = source.read()
    return _pcm_portrait.h16("motion_fp", renderer_fp, code, MOTION_RECIPE, params)


def motion_fingerprint(renderer_fp, path=None):
    """h16("motion_fp", renderer_fp, the bytes of this module, MOTION_RECIPE,
    the encoder parameters) (S4.3), cached on the module file's path, size
    and mtime the way renderer_fp is (#744) -- any edit of this file, a
    comment included, moves every motion URL. None when renderer_fp is None:
    a box that cannot key a face cannot key a motion."""
    if renderer_fp is None:
        return None
    path = _pcm_os.path.abspath(path or __file__)
    stat = _pcm_os.stat(path)
    return _motion_fp_cached(renderer_fp, path, stat.st_size, stat.st_mtime_ns, encoder_params())


def motion_rev(motion_fp, face_rev, motion_hash):
    """One print's motion at one locale (S4.3). face_rev covers the
    renderer, the locale's catalogue, the whole print spec and the still;
    motion_hash covers the dance, recipe, frame count, period and every
    frame. None when any input is missing: nothing is keyed on a
    placeholder."""
    if not (motion_fp and face_rev and motion_hash):
        return None
    return _pcm_portrait.h16("motion_rev", motion_fp, face_rev, motion_hash)


def motion_preview_rev(motion_fp, preview_rev, motion_hash):
    """The /card preview's key (S4.3): the same rule over preview_rev."""
    if not (motion_fp and preview_rev and motion_hash):
        return None
    return _pcm_portrait.h16("motion_preview_rev", motion_fp, preview_rev, motion_hash)


def _motion_rgba(png):
    with _Image.open(_pcm_io.BytesIO(png)) as source:
        source.load()
        rgba = source if source.mode == "RGBA" else source.convert("RGBA")
        return _Image.frombytes("RGBA", rgba.size, rgba.tobytes())


def frame_portrait(png):
    """S4.2: a canonical 590-pixel frame, upscaled x2 by nearest neighbour to
    1180 and encoded by the renderer's own PNG writer -- a rig portrait for
    the UNCHANGED render_face, which composites it over the portrait
    background and box-reduces it by 2 (card) or 4 (tile). By the
    nearest-neighbour identity the card draws the frame at native 590 and
    the tile draws it reduced by 2 (T22)."""
    frame = _motion_rgba(png)
    if frame.size != (FRAME_EDGE, FRAME_EDGE):
        raise ValueError("frame_size")
    return _face._encode_rgba(frame.resize((2 * FRAME_EDGE, 2 * FRAME_EDGE), _Image.Resampling.NEAREST))


def _check_deadline(deadline, clock):
    if deadline is not None and clock() > deadline:
        raise MotionDeadline()


def atlas_rows(count):
    return (count + ATLAS_COLUMNS - 1) // ATLAS_COLUMNS


def derive_atlases(spec, labels, container, *, deadline=None, clock=_time.monotonic, render=None):
    """The print atlas job, both sizes in one job (S4.4): for every frame k,
    R_k = render_face(spec, labels, U_k, size) at card and at tile, its
    window LANCZOS-resized into cell k of an eight-column, row-major atlas;
    each atlas encoded as canonical PNG. Returns (card PNG or None, tile PNG
    or None): None where the encoded atlas is above its cap -- that key
    answers 404 motion_too_large. The deadline is checked after every frame
    render and every encode step (MotionDeadline)."""
    render = _face.render_face if render is None else render
    _header, frames = parse_container(container)
    rows = atlas_rows(len(frames))
    card = _Image.new("RGBA", (ATLAS_COLUMNS * CARD_CELL, rows * CARD_CELL), (0, 0, 0, 0))
    tile = _Image.new("RGBA", (ATLAS_COLUMNS * TILE_CELL, rows * TILE_CELL), (0, 0, 0, 0))
    for k, png in enumerate(frames):
        portrait = frame_portrait(png)
        _check_deadline(deadline, clock)
        col, row = k % ATLAS_COLUMNS, k // ATLAS_COLUMNS
        for size, window, cell, atlas in (("card", CARD_WINDOW, CARD_CELL, card),
                                          ("tile", TILE_WINDOW, TILE_CELL, tile)):
            face = _motion_rgba(render(spec, labels, portrait, size))
            _check_deadline(deadline, clock)
            atlas.paste(face.crop(window).resize((cell, cell), _Image.Resampling.LANCZOS),
                        (col * cell, row * cell))
    card_png = _face._encode_rgba(card)
    _check_deadline(deadline, clock)
    tile_png = _face._encode_rgba(tile)
    _check_deadline(deadline, clock)
    return (card_png if len(card_png) <= CARD_ATLAS_MAX_BYTES else None,
            tile_png if len(tile_png) <= TILE_ATLAS_MAX_BYTES else None)


def _fast_png(image):
    out = _pcm_io.BytesIO()
    image.save(out, format="PNG", compress_level=1)
    return out.getvalue()


def _opaque_rgb(image):
    """The RGB of an RGBA image with every pixel under the alpha threshold
    black: the palette is built from what the GIF can show."""
    rgb = image.convert("RGB")
    clear = image.getchannel("A").point(lambda a: 255 if a < GIF_ALPHA_THRESHOLD else 0)
    rgb.paste((0, 0, 0), (0, 0) + image.size, clear)
    return rgb


def _gif_palette(static, crops):
    """One palette of GIF_COLOURS colours by median cut, no dither, over a
    mosaic of the static face and every window crop reduced by 4 (S4.5)."""
    small = [_motion_rgba(png).reduce(4) for png in crops]
    edge = small[0].width if small else 1
    per_row = max(1, static.width // edge)
    mosaic = _Image.new("RGB", (static.width, static.height + atlas_rows_of(len(small), per_row) * edge),
                        (0, 0, 0))
    mosaic.paste(_opaque_rgb(static), (0, 0))
    for k, crop in enumerate(small):
        mosaic.paste(_opaque_rgb(crop), ((k % per_row) * edge, static.height + (k // per_row) * edge))
    return mosaic.quantize(colors=GIF_COLOURS, method=_Image.Quantize.MEDIANCUT, dither=_Image.Dither.NONE)


def atlas_rows_of(count, per_row):
    return (count + per_row - 1) // per_row


def _gif_frame(image, palette):
    """One frame on the fixed palette: nearest colour, no dither, and every
    pixel under the alpha threshold on the transparent index (GIF_COLOURS)."""
    frame = _opaque_rgb(image).quantize(palette=palette, dither=_Image.Dither.NONE)
    frame.paste(GIF_COLOURS, (0, 0) + image.size,
                image.getchannel("A").point(lambda a: 255 if a < GIF_ALPHA_THRESHOLD else 0))
    return frame


def _encode_gif(static, crops, window, period, deadline, clock):
    palette = _gif_palette(static, crops)
    _check_deadline(deadline, clock)
    # Exactly GIF_COLOURS entries (a median cut may return fewer; the rest pad
    # as black) and the transparent slot last, so index GIF_COLOURS is always
    # the transparent one.
    lut = (palette.getpalette() + [0, 0, 0] * GIF_COLOURS)[:3 * GIF_COLOURS] + [0, 0, 0]
    frames = []
    for png in crops:
        full = static.copy()
        full.paste(_motion_rgba(png), window[:2])
        frame = _gif_frame(full, palette)
        frame.putpalette(lut)
        frames.append(frame)
        _check_deadline(deadline, clock)
    out = _pcm_io.BytesIO()
    # `palette` makes the fixed palette the ONE global table: without it the
    # writer gives every delta frame a local copy of its own.
    frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:], loop=0,
                   duration=int(period), disposal=1, transparency=GIF_COLOURS, optimize=False,
                   palette=bytes(lut))
    _check_deadline(deadline, clock)
    return out.getvalue()


def _gif_at(size, spec, labels, still, container, deadline, clock, render):
    header, frames = parse_container(container)
    window = CARD_WINDOW if size == "card" else TILE_WINDOW
    static = _motion_rgba(render(spec, labels, still, size))
    _check_deadline(deadline, clock)
    crops = []
    for png in frames:
        face = _motion_rgba(render(spec, labels, frame_portrait(png), size))
        crops.append(_fast_png(face.crop(window)))
        _check_deadline(deadline, clock)
    return _encode_gif(static, crops, window, header["ms"], deadline, clock)


def gif_ladder(card_gif, tile_gif):
    """M5's ladder, deterministic from the source (S4.5): (size, bytes) of the
    card GIF when it is at or below 4 MiB, else of the tile GIF at or below 3
    MiB, else (None, None) -- no GIF, and the key answers 404
    motion_too_large. Each argument is a callable that encodes its size, so
    the tile GIF is encoded only when the card GIF did not fit."""
    card = card_gif()
    if len(card) <= CARD_GIF_MAX_BYTES:
        return "card", card
    tile = tile_gif()
    if len(tile) <= TILE_GIF_MAX_BYTES:
        return "tile", tile
    return None, None


def derive_preview_gif(spec, labels, still, container, *, deadline=None, clock=_time.monotonic, render=None):
    """The preview GIF job (S4.5) for the /card surface: the preview spec's
    per-frame renders, a mosaic pass for the one palette, then the full
    faces (the static face with crop k pasted, which T21 proves equal to
    R_k) through the pinned Pillow's multi-frame writer -- loop 0, one
    uniform duration (the period), disposal 1, the fixed palette. The
    writer may merge consecutive identical frames and sum their delays; the
    total stays N x period. Returns gif_ladder's (size, bytes)."""
    render = _face.render_face if render is None else render
    return gif_ladder(
        lambda: _gif_at("card", spec, labels, still, container, deadline, clock, render),
        lambda: _gif_at("tile", spec, labels, still, container, deadline, clock, render))
