#!/usr/bin/env python3
"""Dance cards - the focused client suite: reference vectors, the clean run,
the server-side checks of what the client wrote, and the mutation arms.

    python tools/tests/dance-cards-client/run_tests.py [--no-mutants] [--only NAME ...]

1. References. The server's own code writes what the client must equal:
   pc_motion.luma (Pillow alpha_composite + the Rec. 709 matrix) over every
   opaque RGB triple and every (value, alpha) pair, pc_motion.flash_pair on
   pairs built at the 13-step and 35 % edges, pc_motion.build_container, and
   an atlas encoded by pc_face._encode_rgba.
2. The clean run: every case of Program.cs against the clean plugin files.
3. The server reads the client's bytes: the C# PNG writer's output opened by
   Pillow, a synthetic 590 frame from ProcessPair through
   pc_motion.check_frame, an 80-frame container through parse_container.
4. Mutants: one per named statement, each a find/replace asserted to occur
   EXACTLY ONCE inside the named member (never file-wide), compiled from a
   copy under work/ through the csproj's source properties. A mutant is
   CAUGHT when every target case FAILS and every control case PASSES.

Everything generated lives under work/ (gitignored). Paths in the output are
relative to the repository. The exit code is 0 only when the clean run
passes, the server accepts the client's bytes and every mutant is caught.
"""
import argparse
import hashlib
import io
import os
import random
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
API = os.path.join(REPO, "backend", "api")
PLUGIN = os.path.join(REPO, "plugin")
PROJ = os.path.join(HERE, "DanceCardsClientTests.csproj")
WORK = os.path.join(HERE, "work")
REF = os.path.join(WORK, "ref")
OUT = os.path.join(WORK, "out")

sys.path.insert(0, API)
from PIL import Image  # noqa: E402
import pc_face  # noqa: E402
import pc_motion  # noqa: E402

SOURCES = {"ScrPng.cs": "PngSource", "DanceMotionCore.cs": "CoreSource", "PlayerCardMotionCore.cs": "MotionSource"}


def rel(path):
    return os.path.relpath(path, REPO).replace(os.sep, "/")


def clean(text):
    """Build output with the repository prefix and the home directory
    replaced, so a log carries no local path."""
    home = os.path.expanduser("~")
    out = text
    for p, tag in ((REPO, "<repo>"), (REPO.replace("\\", "/"), "<repo>"), (home, "<home>"), (home.replace("\\", "/"), "<home>")):
        out = out.replace(p, tag)
    return out


# -- references ----------------------------------------------------------------

def write(name, data):
    with open(os.path.join(REF, name), "wb") as fh:
        fh.write(data)


def luma_refs():
    cases = []
    # every opaque RGB triple: pixel i = r * 65536 + g * 256 + b of a 4096 x 4096 image
    rows_r = b"".join(bytes([y // 16]) * 4096 for y in range(4096))
    g_rows = [bytes(((yy % 16) * 16 + x // 256) for x in range(4096)) for yy in range(16)]
    rows_g = b"".join(g_rows[y % 16] for y in range(4096))
    rows_b = bytes(range(256)) * (16 * 4096)
    size = (4096, 4096)
    bands = [Image.frombytes("L", size, d) for d in (rows_r, rows_g, rows_b)] + [Image.new("L", size, 255)]
    cases.append(Image.merge("RGBA", bands))
    # every (value, alpha) pair on all three channels: x = value, y = alpha
    grey = bytes(range(256)) * 256
    alpha = b"".join(bytes([y]) * 256 for y in range(256))
    g = Image.frombytes("L", (256, 256), grey)
    cases.append(Image.merge("RGBA", (g, g, g, Image.frombytes("L", (256, 256), alpha))))
    # independent channels and a skewed alpha
    rnd = random.Random(20260927)
    px = bytearray()
    for _ in range(512 * 512):
        a = rnd.choice((0, 1, 2, 3, 127, 128, 129, 253, 254, 255, rnd.randrange(256), rnd.randrange(256)))
        px += bytes((rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), a))
    cases.append(Image.frombytes("RGBA", (512, 512), bytes(px)))
    total = 0
    for i, img in enumerate(cases):
        write("luma_%d.rgba" % i, img.tobytes())
        y = pc_motion.luma(img)
        write("luma_%d.y" % i, y.tobytes())
        total += img.size[0] * img.size[1]
    write("luma_count.txt", str(len(cases)).encode())
    return total


def flash_refs():
    pairs = []
    n_side = 100
    n = n_side * n_side
    rnd = random.Random(7)

    def img(values):
        return Image.frombytes("L", (n_side, n_side), bytes(values))

    base = [rnd.randrange(40, 200) for _ in range(n)]
    # exactly 35 % changed by exactly 13 steps: not refused; one more pixel: refused
    for extra in (0, 1):
        b = list(base)
        for i in range(3500 + extra):
            b[i] = base[i] + 13
        pairs.append((img(base), img(b)))
    # 12 steps everywhere: nothing counts as changed
    pairs.append((img(base), img([v + 12 for v in base])))
    # 35 % changed by 146: changed at its bound, mean just above 0.20
    low = [rnd.randrange(0, 100) for _ in range(n)]
    b = list(low)
    for i in range(3500):
        b[i] = low[i] + 146
    pairs.append((img(low), img(b)))
    # small noise, and a half-image step
    pairs.append((img(base), img([max(0, min(255, v + rnd.randrange(-20, 21))) for v in base])))
    pairs.append((img(base), img([min(255, v + 60) if i % 2 else v for i, v in enumerate(base)])))
    # two real luma images: a disc and the disc moved
    frames = []
    for shift in (0, 9):
        f = Image.new("RGBA", (590, 590), (0, 0, 0, 0))
        disc = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        for y in range(300):
            for x in range(300):
                if (x - 150) ** 2 + (y - 150) ** 2 < 140 ** 2:
                    disc.putpixel((x, y), ((x * 3) % 256, (y * 2) % 256, 180, 255))
        f.paste(disc, (140 + shift, 140), disc)
        frames.append(pc_motion.luma(f))
    pairs.append((frames[0], frames[1]))
    for i, (a, b) in enumerate(pairs):
        changed, mean = pc_motion.flash_pair(a, b)
        write("flash_%d_a.y" % i, a.tobytes())
        write("flash_%d_b.y" % i, b.tobytes())
        write("flash_%d.txt" % i, ("%r %r %d" % (changed, mean, 1 if pc_motion.flash_refused(changed, mean) else 0)).encode())
    write("flash_count.txt", str(len(pairs)).encode())
    return len(pairs)


def container_refs():
    rnd = random.Random(3)
    header = pc_motion.header_text("dance_bounce", 1, 80, 50, hashlib.sha256(b"ref").hexdigest())
    frames = [bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 3000))) for _ in range(80)]
    for k, f in enumerate(frames):
        write("container_frame_%d.bin" % k, f)
    write("container_header.txt", header.encode("ascii"))
    write("container_count.txt", b"80")
    write("container.bin", pc_motion.build_container(header, frames))


def atlas_refs():
    w, h, cell = 2048, 512, 256
    rnd = random.Random(11)
    px = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            p = (y * w + x) * 4
            a = 0 if (x // 37 + y // 29) % 5 == 0 else 255 if (x + y) % 3 else rnd.randrange(256)
            px[p:p + 4] = bytes(((x * 7 + y) % 256, (y * 3) % 256, rnd.randrange(256) if x % 64 < 8 else (x ^ y) % 256, a))
    image = Image.frombytes("RGBA", (w, h), bytes(px))
    write("atlas.png", pc_face._encode_rgba(image))
    write("atlas.rgba", image.tobytes())
    write("atlas.txt", ("%d %d %d" % (w, h, cell)).encode())


def gen_refs():
    shutil.rmtree(REF, ignore_errors=True)
    os.makedirs(REF)
    t = time.time()
    px = luma_refs()
    pairs = flash_refs()
    container_refs()
    atlas_refs()
    print("references: luma over %d pixels, %d flash pairs, one container, one atlas (%.1f s)" % (px, pairs, time.time() - t))


# -- build and run ---------------------------------------------------------------

def build(variant, props=None):
    root = os.path.join(WORK, variant)
    shutil.rmtree(root, ignore_errors=True)
    # forward slashes: a trailing backslash would escape a quote on the command line
    obj, bindir = root.replace("\\", "/") + "/obj/", root.replace("\\", "/") + "/bin/"
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + obj, "-p:OutDir=" + bindir]
    for k, v in (props or {}).items():
        cmd.append("-p:%s=%s" % (k, v))
    r = subprocess.run(cmd, capture_output=True, text=True)
    dll = os.path.join(bindir, "DanceCardsClientTests.dll")
    if r.returncode != 0 or not os.path.exists(dll):
        lines = [ln for ln in (r.stdout + r.stderr).splitlines() if "error" in ln]
        raise RuntimeError("build of %s failed: %s" % (variant, clean(" | ".join(lines[:5]))))
    return dll


def run(dll, cases=(), out=None):
    cmd = ["dotnet", dll, "--ref", REF]
    if out:
        cmd += ["--out", out]
    cmd += list(cases)
    r = subprocess.run(cmd, capture_output=True, text=True)
    verdicts = {}
    for ln in r.stdout.splitlines():
        m = re.match(r"^(PASS|FAIL) ([A-Za-z0-9_]+)", ln)
        if m:
            verdicts[m.group(2)] = m.group(1)
    return r.returncode, clean(r.stdout), verdicts


# -- the server reads the client's bytes ------------------------------------------

def server_checks():
    ok = True
    for i in range(3):
        png = open(os.path.join(OUT, "enc_%d.png" % i), "rb").read()
        raw = open(os.path.join(OUT, "enc_%d.rgba" % i), "rb").read()
        w, h = (int(v) for v in open(os.path.join(OUT, "enc_%d.txt" % i)).read().split())
        pc_face.png_chunks(png)
        with Image.open(io.BytesIO(png)) as im:
            im.load()
            same = im.mode == "RGBA" and im.size == (w, h) and im.tobytes() == raw
        print("%s pillow_reads_client_png_%d: %dx%d, %d bytes" % ("PASS" if same else "FAIL", i, w, h, len(png)))
        ok &= same
    png = open(os.path.join(OUT, "frame_590.png"), "rb").read()
    size, cov = open(os.path.join(OUT, "frame_590.txt")).read().split()
    try:
        canonical, frame = pc_motion.check_frame(png, 0)
        hist = frame.getchannel("A").histogram()
        server_cov = 1.0 - hist[0] / float(590 * 590)
        same = abs(server_cov - float(cov)) < 1e-12
        print("%s check_frame_accepts_client_frame: client %s bytes, server canonical %d bytes, coverage client %s server %r"
              % ("PASS" if same else "FAIL", size, len(canonical), cov, server_cov))
        ok &= same
    except pc_motion.MotionRefusal as exc:
        print("FAIL check_frame_accepts_client_frame: refused %r" % (exc.args,))
        ok = False
    body = open(os.path.join(OUT, "container_80.bin"), "rb").read()
    try:
        header, frames = pc_motion.parse_container(body)
        good = header["dance"] == "dance_bounce" and header["frames"] == 80 and len(frames) == 80
        print("%s parse_container_accepts_client_container: %d frames, %d bytes" % ("PASS" if good else "FAIL", len(frames), len(body)))
        ok &= good
    except pc_motion.MotionRefusal as exc:
        print("FAIL parse_container_accepts_client_container: refused %r" % (exc.args,))
        ok = False
    return ok


# -- mutants ---------------------------------------------------------------------

def member_span(text, signature):
    """(start, end) of the member whose declaration begins with `signature`:
    from the signature to its matching closing brace, skipping strings,
    character literals and comments. The signature must occur exactly once."""
    if text.count(signature) != 1:
        raise RuntimeError("signature %r occurs %d times" % (signature, text.count(signature)))
    start = text.index(signature)
    i = text.index("{", start)
    depth = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "/" and text.startswith("//", i):
            i = text.index("\n", i)
            continue
        if c == "/" and text.startswith("/*", i):
            i = text.index("*/", i) + 2
            continue
        if c == '"':
            i += 1
            while text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            continue
        if c == "'":
            i += 1
            while text[i] != "'":
                i += 2 if text[i] == "\\" else 1
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    raise RuntimeError("no closing brace for %r" % signature)


def make_mutant(spec):
    path = os.path.join(PLUGIN, spec["file"])
    text = open(path, "rb").read().decode("ascii")
    crlf = "\r\n" in text
    for member, find, replace in spec["edits"]:
        if crlf:
            find, replace = find.replace("\n", "\r\n"), replace.replace("\n", "\r\n")
        a, b = member_span(text, member)
        count = text.count(find, a, b)
        if count != 1:
            raise RuntimeError("%s: %r occurs %d times inside %r" % (spec["name"], find, count, member))
        at = text.index(find, a, b)
        text = text[:at] + replace + text[at + len(find):]
    root = os.path.join(WORK, "src_" + spec["name"])
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    out = os.path.join(root, spec["file"])
    with open(out, "wb") as fh:
        fh.write(text.encode("ascii"))
    return out


L2_BLOCK = (
    "            string header = DanceMotionCore.HeaderText(_sku, _recipe, _frames.Count, _ms, a.PortraitHash);\n"
    "            if (header == null) { Finish(DanceUploadResult.Invalid); return; }\n"
    "            try { _container = DanceMotionCore.BuildContainer(header, _frames); }\n"
    "            catch (ArgumentException ex) { _port.Note(\"container refused: \" + ex.Message); Finish(DanceUploadResult.Invalid); return; }\n"
    "            Header = header;\n"
    "            BoundHash = a.PortraitHash;\n"
    "            Trace.Add(\"container:\" + a.PortraitHash.Substring(0, 12));\n")

PREBUILD = (
    "string pre = DanceMotionCore.HeaderText(_sku, _recipe, _frames.Count, _ms, DanceMotionCore.Sha256Hex(_still));\n"
    "            _container = DanceMotionCore.BuildContainer(pre, _frames);\n"
    "            Header = pre;\n"
    "            BoundHash = DanceMotionCore.HeaderStr(pre, \"static\");\n"
    "            Trace.Add(\"container:\" + BoundHash.Substring(0, 12));\n"
    "            SendStill();")

MUTANTS = [
    # ScrPng
    {"name": "png_unfilter_average", "file": "ScrPng.cs",
     "edits": [("private static void Unfilter(", "+ prev[i]) >> 1)", "+ prev[i]) >> 2)")],
     "targets": ["png_roundtrip"], "controls": ["png_rejects"]},
    {"name": "png_skip_chunk_crc", "file": "ScrPng.cs",
     "edits": [("private static byte[] Idat(", "if (crc != GetBE(d, off + 8 + n)) return null;", "if (false && crc != GetBE(d, off + 8 + n)) return null;")],
     "targets": ["png_rejects"], "controls": ["png_roundtrip"]},
    {"name": "png_skip_adler", "file": "ScrPng.cs",
     "edits": [("internal static List<byte[]> DecodeBandsRgba8(", "if (((s << 16) | a) != want) return null;", "if (false && ((s << 16) | a) != want) return null;")],
     "targets": ["png_rejects"], "controls": ["png_roundtrip"]},
    # DanceMotionCore
    {"name": "luma_no_rounding_bias", "file": "DanceMotionCore.cs",
     "edits": [("private static int Comp(", " + (0x80u << 7)", "")],
     "targets": ["luma_pillow"], "controls": ["flash_pillow"]},
    {"name": "flash_changed_strict", "file": "DanceMotionCore.cs",
     "edits": [("internal static void FlashPair(", "d >= FLASH_CHANGED_STEPS", "d > FLASH_CHANGED_STEPS")],
     "targets": ["flash_bounds", "flash_pillow"], "controls": ["header_grammar"]},
    {"name": "matte_unpremultiply_unrounded", "file": "DanceMotionCore.cs",
     "edits": [("internal static byte Un(", "(c * 255 + a / 2) / a", "(c * 255) / a")],
     "targets": ["matte_arith"], "controls": ["edge_band"]},
    {"name": "grade_before_matte", "file": "DanceMotionCore.cs",
     "edits": [("internal static FrameOut ProcessPair(",
                "Matte(black, white, work, out f.Lit, out f.Partial, out f.Covered);\n            Grade(work, grade);",
                "Grade(black, grade);\n            Grade(white, grade);\n            Matte(black, white, work, out f.Lit, out f.Partial, out f.Covered);")],
     "targets": ["grade_after_matte"], "controls": ["matte_arith"]},
    {"name": "edge_band_one_short", "file": "DanceMotionCore.cs",
     "edits": [("internal static bool EdgeClear(", "bool band = y < margin ||", "bool band = y < margin - 1 ||")],
     "targets": ["edge_band"], "controls": ["matte_arith"]},
    {"name": "selfcheck_no_wrap", "file": "DanceMotionCore.cs",
     "edits": [("internal static string SelfCheck(", "if (frames.Count > 1)", "if (frames.Count > 1 && false)")],
     "targets": ["selfcheck_order"], "controls": ["classify_motion"]},
    {"name": "nonce_replay_not_resent", "file": "DanceMotionCore.cs",
     "edits": [("internal static Act ClassifyMotion(", "if (e == \"nonce_replayed\") return Act.Resend;", "if (e == \"nonce_replayed\") return Act.Stop;")],
     "targets": ["classify_motion", "upload_retries_once"], "controls": ["classify_still"]},
    {"name": "container_count_unchecked", "file": "DanceMotionCore.cs",
     "edits": [("internal static byte[] BuildContainer(", "if (!header.Contains(\";frames=\"", "if (false && !header.Contains(\";frames=\"")],
     "targets": ["container_layout"], "controls": ["header_grammar"]},
    {"name": "t57_container_before_still", "file": "DanceMotionCore.cs",
     "edits": [("internal void Start()", "SendStill();", PREBUILD),
               ("private void OnStill(", L2_BLOCK, "            // (mutant: the container was built in Start)\n")],
     "targets": ["t57_l2_container_after_still"], "controls": ["t57_still_refusal_sends_no_motion", "upload_retries_once"]},
    # the S1.2 decision (T48's pure half)
    {"name": "t48_memory_ignored", "file": "DanceMotionCore.cs",
     "edits": [("internal static Need Decide(", "if (!canDance || remembered) return Need.Fallback;", "if (!canDance) return Need.Fallback;")],
     "targets": ["t48_decide_truth_table"], "controls": ["motion_current_terms", "remember_key_stable"]},
    {"name": "motion_current_skips_recipe", "file": "DanceMotionCore.cs",
     "edits": [("internal static bool MotionCurrent(", "r == recipe && ", "")],
     "targets": ["motion_current_terms"], "controls": ["still_current_rows"]},
    {"name": "still_current_suffix_always", "file": "DanceMotionCore.cs",
     "edits": [("internal static bool StillCurrent(", "danceDescriptor != null && portraitDescriptor == danceDescriptor", "portraitDescriptor != null")],
     "targets": ["still_current_rows"], "controls": ["remember_key_stable", "t48_decide_truth_table"]},
    {"name": "remember_key_by_visit", "file": "DanceMotionCore.cs",
     "edits": [("internal static string RememberKey(", "return (steamId ?? \"\") + \"|\" + (danceDescriptor ?? \"\");", "return (steamId ?? \"\") + \"|\" + System.Guid.NewGuid().ToString(\"N\");")],
     "targets": ["remember_key_stable"], "controls": ["t48_decide_truth_table"]},
    # PlayerCardMotionCore
    {"name": "t39_clip_keyed_by_binding", "file": "PlayerCardMotionCore.cs",
     "edits": [("internal Clip Get(string printId, int bindSeq)", "string key = printId;", "string key = printId + \"#\" + bindSeq;")],
     "targets": ["t39_truth_table"], "controls": ["t41_high_fps"]},
    {"name": "t39_rebase_ignored", "file": "PlayerCardMotionCore.cs",
     "edits": [("internal void PageShown(string key, double now)", "&& !_rebase ", "")],
     "targets": ["t39_truth_table"], "controls": ["t49_no_429_one_read_per_visit"]},
    {"name": "t41_frame_by_ticks", "file": "PlayerCardMotionCore.cs",
     "edits": [("internal static int Frame(Clip c, double now)", "int k = el <= 0 ? 0 : (int)Math.Floor(el * 1000.0 / c.Ms);", "int k = c.Ticks - 1;")],
     "targets": ["t41_low_fps", "t41_high_fps"], "controls": ["t41_tick_equals_period"]},
    {"name": "t49_no_cooldown", "file": "PlayerCardMotionCore.cs",
     "edits": [("internal Next OnAnswer(", "_coolUntil = now + PlayerCardMotionCore.COOLDOWN_429_S;", "")],
     "targets": ["t49_429_cooldown_across_visits"], "controls": ["t49_no_429_one_read_per_visit"]},
    {"name": "t40_eviction_not_released", "file": "PlayerCardMotionCore.cs",
     "edits": [("internal void Admit(", "Remove(oldest, release);", "Remove(oldest, null);")],
     "targets": ["t40_budget_cycles"], "controls": ["t40_single_visit"]},
    {"name": "t50_two_steps_per_frame", "file": "PlayerCardMotionCore.cs",
     "edits": [("internal sealed class FrameGate", "internal int Max = 1;", "internal int Max = 2;")],
     "targets": ["t50_largest_card_gate"], "controls": ["t50_tile_alone"]},
    {"name": "read_order_unchecked", "file": "PlayerCardMotionCore.cs",
     "edits": [("internal static bool ParseRead(", "f[0] != asked[i]", "!asked.Contains(f[0])")],
     "targets": ["read_parse"], "controls": ["atlas_shape"]},
    {"name": "atlas_interlace_unchecked", "file": "PlayerCardMotionCore.cs",
     "edits": [("internal static bool AtlasHeaderOk(", " && il == 0", "")],
     "targets": ["atlas_ihdr"], "controls": ["atlas_shape"]},
]


def run_mutants(only):
    caught = 0
    chosen = [m for m in MUTANTS if not only or m["name"] in only]
    for spec in chosen:
        src = make_mutant(spec)
        dll = build("m_" + spec["name"], {SOURCES[spec["file"]]: src.replace("\\", "/")})
        _code, _out, v = run(dll, spec["targets"] + spec["controls"])
        t_ok = all(v.get(t) == "FAIL" for t in spec["targets"])
        c_ok = all(v.get(c) == "PASS" for c in spec["controls"])
        verdict = "CAUGHT" if t_ok and c_ok else "NOT CAUGHT"
        caught += verdict == "CAUGHT"
        print("%s mutant %s (%s): targets %s; controls %s" % (
            verdict, spec["name"], spec["file"],
            ", ".join("%s=%s" % (t, v.get(t, "missing")) for t in spec["targets"]),
            ", ".join("%s=%s" % (c, v.get(c, "missing")) for c in spec["controls"])))
    print("mutants: %d of %d caught" % (caught, len(chosen)))
    return caught == len(chosen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mutants", action="store_true")
    ap.add_argument("--only", nargs="*", default=[])
    args = ap.parse_args()
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--", "plugin/ScrPng.cs", "plugin/DanceMotionCore.cs",
                            "plugin/PlayerCardMotionCore.cs", "tools/tests/dance-cards-client"],
                           capture_output=True, text=True).stdout.strip()
    print("commit %s%s" % (head, " (the tested files carry uncommitted changes)" if dirty else ""))
    for name in SOURCES:
        data = open(os.path.join(PLUGIN, name), "rb").read()
        print("  %s sha256 %s" % (rel(os.path.join(PLUGIN, name)), hashlib.sha256(data).hexdigest()))
    data = open(os.path.join(HERE, "Program.cs"), "rb").read()
    print("  %s sha256 %s" % (rel(os.path.join(HERE, "Program.cs")), hashlib.sha256(data).hexdigest()))
    os.makedirs(WORK, exist_ok=True)
    gen_refs()
    shutil.rmtree(OUT, ignore_errors=True)
    dll = build("clean")
    code, out, verdicts = run(dll, (), OUT)
    print(out.rstrip())
    ok = code == 0
    ok &= server_checks()
    if not args.no_mutants:
        ok &= run_mutants(set(args.only))
    print("RESULT %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
