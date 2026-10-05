"""The motion upload's container, table and content checks (dance cards design
S2.3-S2.5; build brief B2-B4; tests T1-T6, T43 and the decode half of T46).

Every assertion here has a mutation that must turn it red and a control that
stays green on correct code (#391); the mutation runs are recorded in the
lane's dance-cards-server-*.log files, not in this file.
"""
import asyncio
import os
import re
import threading
import time

import pytest
from PIL import Image

import pc_motion as pcm
import pc_motion_fixtures as fx

HERE = os.path.dirname(os.path.abspath(__file__))
DANCE_EMOTES = os.path.join(HERE, "..", "..", "plugin", "DanceEmotes.cs")


def _refusal(fn, *args):
    with pytest.raises(pcm.MotionRefusal) as caught:
        fn(*args)
    return caught.value


# -- T1 ------------------------------------------------------------------------
def test_motion_container_exact():
    """S2.3: the one accepted shape parses to its header and its frames; a
    trailing byte, and every other shape, is 422 motion_container."""
    frames = [bytes([k % 251 + 1]) * (k + 1) for k in range(80)]
    body = fx.container("dance_bounce", frames)
    header, got = pcm.parse_container(body)
    assert got == frames
    assert (header["dance"], header["recipe"], header["frames"], header["ms"], header["static"]) == \
        ("dance_bounce", 1, 80, 50, fx.STATIC)
    for bad in (body + b"\x00",                                   # a trailing byte
                b"SCRMOT2\n" + body[8:],                          # magic
                body[:8] + (0).to_bytes(4, "big") + body[12:],    # header length 0
                body[:8] + (513).to_bytes(4, "big") + body[12:],  # header length 513
                body[:-1]):                                       # truncated last frame
        assert _refusal(pcm.parse_container, bad).detail["error"] == "motion_container"
    zero = pcm.build_container(pcm.header_text("dance_bounce", 1, 80, 50, fx.STATIC),
                               [b"x"] * 79 + [b""])
    assert _refusal(pcm.parse_container, zero).detail["error"] == "motion_container"
    big = pcm.build_container(pcm.header_text("dance_bounce", 1, 80, 50, fx.STATIC),
                              [b"x"] * 79 + [b"y" * (pcm.FRAME_MAX_BYTES + 1)])
    assert _refusal(pcm.parse_container, big).detail["error"] == "motion_container"
    edge = pcm.build_container(pcm.header_text("dance_bounce", 1, 80, 50, fx.STATIC),
                               [b"x"] * 79 + [b"y" * pcm.FRAME_MAX_BYTES])
    assert len(pcm.parse_container(edge)[1]) == 80
    for text in ("dance=dance_bounce;recipe=1;frames=80;ms=50;static=" + "AB" * 32,
                 "dance=dance_bounce;recipe=1;frames=80;ms=50;static=" + fx.STATIC + "\n",
                 "recipe=1;dance=dance_bounce;frames=80;ms=50;static=" + fx.STATIC,
                 "dance=dance_bounce;recipe=01;frames=80;ms=50;static=" + fx.STATIC):
        bad = pcm.build_container(text, frames)
        assert _refusal(pcm.parse_container, bad).detail["error"] == "motion_container", text


# -- T2 ------------------------------------------------------------------------
def test_motion_frame_header_refusals():
    """Wrong size, RGB, 16-bit, interlaced and an acTL chunk: each 422
    motion_frame_invalid with the frame's index; a valid frame passes."""
    good = fx.png_bytes(fx.figure(0.25))
    canonical, frame = pcm.check_frame(good, 5)
    assert frame.size == (590, 590) and canonical[:8] == b"\x89PNG\r\n\x1a\n"
    cases = {
        "size": fx.raw_png(589, 590),
        "rgb": fx.raw_png(590, 590, colour=2),
        "16-bit": fx.raw_png(590, 590, depth=16),
        "interlaced": fx.raw_png(590, 590, interlace=1),
        "acTL": fx.with_chunk_after_ihdr(good, b"acTL", b"\x00\x00\x00\x02\x00\x00\x00\x00"),
        "fcTL": fx.with_chunk_after_ihdr(good, b"fcTL", b"\x00" * 26),
        "not a png": b"GIF89a" + b"\x00" * 64,
    }
    for name, png in cases.items():
        refusal = _refusal(pcm.check_frame, png, 7)
        assert refusal.status == 422, name
        assert refusal.detail == {"error": "motion_frame_invalid", "frame": 7}, name
    rgb_real = fx.png_bytes(fx.figure(0.25).convert("RGB"))
    assert _refusal(pcm.check_frame, rgb_real, 3).detail["error"] == "motion_frame_invalid"
    # DECODABLE frames whose only fault is the header: Pillow reads a 16-bit
    # RGBA and an Adam7-interlaced RGBA frame as 590x590 mode RGBA, so the
    # IHDR comparison is the one check that refuses them.
    for name, png in (("16-bit decodable", fx.decodable_png(fx.figure(0.25), depth=16)),
                      ("interlaced decodable", fx.decodable_png(fx.figure(0.25), interlace=1))):
        refusal = _refusal(pcm.check_frame, png, 4)
        assert refusal.detail == {"error": "motion_frame_invalid", "frame": 4}, name


# -- T3 ------------------------------------------------------------------------
def test_motion_shape_from_server_table():
    """Frame count, period and sku come from the server's table: a header
    that disagrees with its row is 422 motion_shape; each row is accepted."""
    for dance, (ms, count) in pcm.MOTION_TABLE[pcm.MOTION_RECIPE].items():
        frames = [b"f"] * count
        header, got = pcm.parse_container(fx.container(dance, frames))
        assert (header["ms"], header["frames"], len(got)) == (ms, count, count), dance
    frames80 = [b"f"] * 80
    for body in (fx.container("dance_bounce", [b"f"] * 79, count=79),      # frames off by one
                 fx.container("dance_bounce", frames80, ms=40),            # period
                 fx.container("dance_robot", frames80, count=80),          # another row's count
                 fx.container("dance_moonwalk", frames80, count=80, ms=50),  # no such sku
                 fx.container("dance_bounce", frames80, recipe=2, count=80, ms=50)):  # no such recipe
        assert _refusal(pcm.parse_container, body).detail["error"] == "motion_shape"


# -- T4 ------------------------------------------------------------------------
def test_motion_coverage_every_frame():
    """An empty frame at k = 37 is refused with its index; a frame whose
    coverage is above 0.60 is refused; the all-valid sequence decodes."""
    frames = fx.smooth_frames(80)
    header, _ = pcm.parse_container(fx.container("dance_bounce", frames))
    container, motion_hash, stats = pcm.decode_frames(header, frames)
    assert stats["frames"] == 80 and len(motion_hash) == 64
    empty = list(frames)
    empty[37] = fx.png_bytes(fx.blank())
    refusal = _refusal(pcm.decode_frames, header, empty)
    assert refusal.detail["error"] == "motion_coverage" and refusal.detail["frame"] == 37
    full = list(frames)
    full[52] = fx.png_bytes(fx.block((10, 10, 579, 579), (90, 90, 90, 255)))
    refusal = _refusal(pcm.decode_frames, header, full)
    assert refusal.detail["error"] == "motion_coverage" and refusal.detail["frame"] == 52


# -- T5 ------------------------------------------------------------------------
def test_motion_edge_margin():
    """Alpha at 1 px from any edge is refused (motion_edge); alpha at 3 px
    is accepted."""
    for x, y in ((1, 300), (300, 1), (588, 300), (300, 588), (0, 0)):
        image = fx.figure(0.1)
        image.putpixel((x, y), (255, 255, 255, 40))
        refusal = _refusal(pcm.check_frame, fx.png_bytes(image), 9)
        assert refusal.detail == {"error": "motion_edge", "frame": 9}, (x, y)
    for x, y in ((3, 300), (300, 3), (586, 300), (300, 586)):
        image = fx.figure(0.1)
        image.putpixel((x, y), (255, 255, 255, 40))
        pcm.check_frame(fx.png_bytes(image), 9)


def test_alpha_zero_pixels_are_canonicalised():
    """Colour under alpha 0 is not carried: two frames that differ only
    there canonicalise to the same bytes."""
    a = fx.figure(0.3)
    b = a.copy()
    b.putpixel((20, 20), (255, 0, 0, 0))
    ca, _ = pcm.check_frame(fx.png_bytes(a), 0)
    cb, _ = pcm.check_frame(fx.png_bytes(b), 0)
    assert ca == cb


# -- T6 (rewritten by M7) --------------------------------------------------------
# Term-isolating fixtures, each otherwise content-valid (coverage in range,
# clear of the edge band):
#   CHANGED ALONE  two disjoint dim blocks: about 0.83 of the frame changes by
#                  ~0.09 luma -- changed fraction far above 0.35, mean |dY|
#                  well below 0.20;
#   MEAN ALONE     one block, white in one frame and black in the next: 0.30 of
#                  the frame changes by ~1.0 -- changed fraction below 0.35,
#                  mean |dY| above 0.20.
DIM = (40, 42, 44, 255)
LEFT = (4, 4, 244, 585)
RIGHT = (345, 4, 585, 585)
MID = (100, 120, 420, 440)


def _pair_measure(a, b):
    ya = pcm.luma(pcm.check_frame(fx.png_bytes(a), 0)[1])
    yb = pcm.luma(pcm.check_frame(fx.png_bytes(b), 1)[1])
    return pcm.flash_pair(ya, yb)


def test_motion_flash_gate_changed_term_alone():
    a, b = fx.block(LEFT, DIM), fx.block(RIGHT, DIM)
    changed, mean = _pair_measure(a, b)
    assert changed > pcm.FLASH_CHANGED_MAX and mean <= pcm.FLASH_MEAN_MAX, (changed, mean)
    frames = [fx.png_bytes(a)] * 40 + [fx.png_bytes(b)] * 40
    header, _ = pcm.parse_container(fx.container("dance_bounce", frames))
    refusal = _refusal(pcm.decode_frames, header, frames)
    assert refusal.detail["error"] == "motion_flash" and refusal.detail["pair"] == [39, 40]


def test_motion_flash_gate_mean_term_alone():
    a, b = fx.block(MID, (255, 255, 255, 255)), fx.block(MID, (0, 0, 0, 255))
    changed, mean = _pair_measure(a, b)
    assert changed <= pcm.FLASH_CHANGED_MAX and mean > pcm.FLASH_MEAN_MAX, (changed, mean)
    frames = [fx.png_bytes(a)] * 40 + [fx.png_bytes(b)] * 40
    header, _ = pcm.parse_container(fx.container("dance_bounce", frames))
    refusal = _refusal(pcm.decode_frames, header, frames)
    assert refusal.detail["error"] == "motion_flash" and refusal.detail["pair"] == [39, 40]


def test_motion_flash_gate_alternating_and_wrap():
    """An alternating full-frame flash is refused at its first pair; a
    sequence whose every step is gentle but whose last frame is far from its
    first is refused at the loop wrap (N-1, 0)."""
    bright = fx.png_bytes(fx.block((4, 4, 585, 355), (230, 230, 230, 255)))
    dark = fx.png_bytes(fx.block((4, 4, 585, 355), (20, 20, 20, 255)))
    frames = [bright, dark] * 40
    header, _ = pcm.parse_container(fx.container("dance_bounce", frames))
    refusal = _refusal(pcm.decode_frames, header, frames)
    assert refusal.detail["error"] == "motion_flash" and refusal.detail["pair"] == [0, 1]
    drift = []
    for k in range(80):
        x = 6 + int(k * 5.8)
        drift.append(fx.png_bytes(fx.block((x, 4, x + 112, 585), (200, 200, 200, 255))))
    refusal = _refusal(pcm.decode_frames, header, drift)
    assert refusal.detail["error"] == "motion_flash" and refusal.detail["pair"] == [79, 0]


def test_motion_flash_gate_smooth_sequence_passes():
    """The synthetic control: a dancer whose arms swing over one period."""
    frames = fx.smooth_frames(80)
    header, _ = pcm.parse_container(fx.container("dance_bounce", frames))
    _container, _hash, stats = pcm.decode_frames(header, frames)
    assert stats["worst_changed"] < pcm.FLASH_CHANGED_MAX


def test_motion_flash_gate_corpus_control():
    """M7's passing control on REAL captures: one legitimate capture of each
    of the eight recipe-1 dances (the verification seat's portrait lever in
    LOCAL mode, PC_MOTION_CORPUS_DIR/*.scrmotion) passes every content check,
    the flash gate included, and stays green under each T6 mutant, whose red
    comes from the term-isolating fixtures above. SKIPS, naming the variable,
    when it is unset."""
    root = os.environ.get("PC_MOTION_CORPUS_DIR")
    if not root:
        pytest.skip("PC_MOTION_CORPUS_DIR unset: the eight-capture control reads the seat's corpus")
    table = pcm.MOTION_TABLE[pcm.MOTION_RECIPE]
    by_dance = {}
    for name in sorted(os.listdir(root)):
        if not name.endswith(".scrmotion"):
            continue
        with open(os.path.join(root, name), "rb") as fh:
            header, frames = pcm.parse_container(fh.read())
        assert header["dance"] not in by_dance, "two captures of " + header["dance"]
        by_dance[header["dance"]] = (header, frames)
    assert sorted(by_dance) == sorted(table)
    for dance, (header, frames) in sorted(by_dance.items()):
        _container, _hash, stats = pcm.decode_frames(header, frames, deadline_s=600.0)
        assert stats["frames"] == table[dance][1], (dance, stats)
        assert stats["worst_changed"] <= pcm.FLASH_CHANGED_MAX, (dance, stats)


# -- T46, the decode's deadline (L7) ------------------------------------------------
def test_motion_decode_deadline_overrun_is_one_step(monkeypatch):
    """The deadline is checked after every frame: a decode whose frame 10
    takes 0.6 s against a 0.5 s deadline ends right after frame 10 with 503
    motion_busy, and the worker was held for the deadline plus that one
    step -- never for the rest of the frames (L7)."""
    frames = fx.smooth_frames(80)
    header, _ = pcm.parse_container(fx.container("dance_bounce", frames))
    real = pcm.check_frame
    calls = []

    def slow(png, index):
        calls.append(index)
        if index == 10:
            time.sleep(0.6)
        return real(png, index)

    monkeypatch.setattr(pcm, "check_frame", slow)
    t0 = time.monotonic()
    refusal = _refusal(pcm.decode_frames, header, frames, 0.5)
    held = time.monotonic() - t0
    assert refusal.status == 503 and refusal.detail["error"] == "motion_busy"
    assert refusal.detail["frame"] == 10 and max(calls) == 10
    assert held < 0.5 + 0.6 + 0.5, held


def test_motion_decode_worst_frame_step_is_bounded():
    """L7's measured bound: one frame step (checks, canonical encode, luma,
    pair) on the largest frame the gate admits (canonical just under
    262,144 bytes of incompressible colour) stays under one second on this
    seat. The value is printed for the build log."""
    import random
    rnd = random.Random(7)
    image = fx.blank()
    px = image.load()
    for y in range(120, 470):
        for x in range(150, 340):
            px[x, y] = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), 255)
    png = fx.png_bytes(image, level=9)
    canonical, frame = pcm.check_frame(png, 0)
    assert 150_000 < len(canonical) <= pcm.FRAME_MAX_BYTES, len(canonical)
    y0 = pcm.luma(fx.figure(0.0))
    t0 = time.perf_counter()
    canonical, frame = pcm.check_frame(png, 1)
    pcm.flash_pair(y0, pcm.luma(frame))
    step = time.perf_counter() - t0
    print("L7-STEP worst-frame step %.4f s, canonical %d bytes" % (step, len(canonical)))
    assert step < 1.0, step


# -- T43 ---------------------------------------------------------------------------
_DEF_RE = re.compile(r'new DanceDef\("(dance_[a-z]+)",\s*"[^"]*",\s*([0-9.]+)f\)')
_CAPTURE_RE = re.compile(r"CaptureMs\s*=\s*\{([0-9,\s]+)\}")


def test_dance_table_contract():
    """The client's Defs durations and capture table and the server's table
    agree: same skus in the same order, the same period, and frames =
    duration x 1000 / period for every row (#635)."""
    src = open(DANCE_EMOTES, encoding="utf-8").read()
    defs = [(sku, float(dur)) for sku, dur in _DEF_RE.findall(src)]
    capture = [int(v) for v in _CAPTURE_RE.search(src).group(1).split(",") if v.strip()]
    table = pcm.MOTION_TABLE[pcm.MOTION_RECIPE]
    assert [sku for sku, _ in defs] == list(table), "sku order differs from the client's Defs"
    assert len(capture) == len(defs) == 8
    for (sku, duration), ms in zip(defs, capture):
        period, frames = table[sku]
        assert period == ms, sku
        assert frames == round(duration * 1000.0 / ms), sku
        assert frames <= 120 and period in (40, 50), sku


def test_decode_admission_one_per_player_and_three_in_all():
    admission = pcm.DecodeAdmission()
    a = admission.try_claim("a")
    assert a is not None and admission.try_claim("a") is None
    b, c = admission.try_claim("b"), admission.try_claim("c")
    assert b is not None and c is not None and admission.try_claim("d") is None
    admission.release("a", a)
    assert admission.try_claim("d") is not None
    admission.release("b", object())          # a stale token releases nothing
    assert admission.held() == 3


def test_decode_claim_is_released_when_the_waiter_goes():
    """A request that stops waiting (its client went away) while its decode
    is still QUEUED behind another must not strand the claim phase A took:
    the job still runs and releases it. A stranded claim would refuse that
    player, and hold one of the three slots, until the process restarts."""
    admission = pcm.DecodeAdmission()
    header, frames = pcm.parse_container(fx.container("dance_bounce", fx.smooth_frames(80)))
    gate = threading.Event()

    async def scenario():
        blocker = pcm.DECODE_POOL.submit(gate.wait, 30)     # the one worker, busy
        token = admission.try_claim("p1")
        waiter = asyncio.ensure_future(pcm.decode_in_pool(admission, "p1", token, header, frames))
        await asyncio.sleep(0.2)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        queued = admission.held()
        gate.set()
        await asyncio.wrap_future(blocker)
        for _ in range(400):
            if admission.held() == 0:
                break
            await asyncio.sleep(0.05)
        return queued, admission.held()
    queued, after = asyncio.run(scenario())
    assert (queued, after) == (1, 0)
