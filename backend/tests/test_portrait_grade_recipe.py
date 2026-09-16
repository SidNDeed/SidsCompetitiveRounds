"""The portrait grade table, its probe marker, the RECIPE ledger, and the
portrait renderer's load-bearing guards.

plugin/PortraitGrade.cs grades every portrait through a table pasted from a
bake. A stored portrait whose descriptor matches the client's is never
re-rendered, and the descriptor carries r=RECIPE but nothing derived from the
table or the rig pins. So a different table, or a different particle snapshot
length, at a RECIPE that has already stored pictures leaves every stored
portrait on the old look, and only subjects whose other inputs change pick up
the new one.

The client refuses a table that RECIPE_GRADE_FNV (plugin/PortraitRender.cs)
does not name. LEDGER below is what makes naming a DIFFERENT table or length
at the same RECIPE fail here; it is the only control on the particle length
(there is no runtime "provisional length" state).

LEDGER maps RECIPE -> (GRADE_LUT_FNV digest, particle snapshot seconds). Every
change to an entry present in the COMMITTED version of this file fails
test_committed_ledger_entries_are_unchanged. A new table, a new length or any
other change to the rig, framing, matte, pins or grade after pictures are
stored needs a RECIPE bump and a new entry. A placeholder build (no table)
refuses every upload, so it stores nothing and has no entry.

The marker checks keep the DLL byte probe able to tell the two builds apart:
the literal SCR_GRADE_TABLE=PLACEHOLDER is in the plugin's code exactly while
the table is the placeholder, SCR_GRADE_TABLE=BAKED exactly while it is baked,
never both (#306).

The structure checks pin the guards a later fold could move without any other
test noticing: the upload gate, LoadGrade's acceptance terms and their order,
the grade bake's negative control, the product render's refusals, arguments,
start and capture flow, the rig and particle pins and the settle watch, the
colour and effect readiness, the animated colour loop's host and the
inactive-player colour defer's, the dev levers' state predicate after every
yield, the force-abort paths, the mechanisms they rest on and the lifecycle
writes method by method, what the grade levers make, and the sweep's work cap.
A guard is read as a statement of a statement list on the target's path, and
"unconditional" as a path with no conditional clause and no earlier exit,
never as a brace depth.

The readers of statements, guards, exits, fences, paths, refusal returns,
runs, leaves, pinned bodies and Own arguments are also run against synthetic
inputs that break them (#391). The other structure helpers are checked
through the real-source checks and their negative controls.
"""

import ast
import base64
import functools
import re
import subprocess
from pathlib import Path

import pytest

from _cs_structure import CsParseError, and_terms
from _cs_structure import cs_block as library_cs_block, mask_code as _mask_code, strip_comments_only as _strip_comments_only


HERE = Path(__file__).resolve().parent
PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
GRADE_CS = PLUGIN / "PortraitGrade.cs"
RENDER_CS = PLUGIN / "PortraitRender.cs"
EFFECT_CS = PLUGIN / "PlayerEffectCosmetic.cs"
COLOR_CS = PLUGIN / "PlayerColorCosmetic.cs"
PLUGIN_CS = PLUGIN / "Plugin.cs"

# The readers are pure functions of their text, and these checks read the same
# few files, and each negative control's copy of one, many times over: a text's
# mask and comment-stripped copy are cached (the last 256 texts of each), and
# every block of a text is read off its one mask.
# test_the_host_and_a_scene_unload_force_abort_everything holds cs_block to
# _cs_structure's.
mask_code = functools.lru_cache(maxsize=256)(_mask_code)
strip_comments_only = functools.lru_cache(maxsize=256)(_strip_comments_only)


def block_span(text: str, signature: str):
    """The span of the brace-balanced block following `signature`, found on
    the text's mask; raises when the signature is not found, or is found
    again after that block's end (as _cs_structure.cs_block does)."""
    masked = mask_code(text)
    spans, search = [], 0
    while True:
        start = masked.find(signature, search)
        if start < 0:
            break
        open_brace = masked.find("{", start + len(signature))
        if open_brace < 0:
            raise CsParseError(f"no block opens after {signature!r}")
        spans.append((open_brace, _close(masked, open_brace, "{", "}")))
        search = spans[-1][1]
    if not spans:
        raise CsParseError(f"signature not found: {signature!r}")
    if len(spans) > 1:
        raise CsParseError(f"{len(spans)} blocks match {signature!r}; name the one you mean")
    return spans[0]


def cs_block(source, signature: str) -> str:
    """_cs_structure.cs_block, read off the text's one mask."""
    text = source.read_text(encoding="utf-8") if isinstance(source, Path) else source
    a, b = block_span(text, signature)
    return text[a:b]

LUT_N = 17
LUT_BYTES = LUT_N * LUT_N * LUT_N * 3
MARK_PLACEHOLDER = "SCR_GRADE_TABLE=PLACEHOLDER"
MARK_BAKED = "SCR_GRADE_TABLE=BAKED"

# RECIPE -> (digest, particle snapshot seconds). See the module docstring for
# what may change. 3: the particle pin reaches sub-emitters and steps in fixed
# increments with prewarm off and path-only seeds; the table and the length are
# RECIPE 2's. The length was picked in game under RECIPE 2's simulation, so it
# is re-checked in game with `sweep` before a RECIPE 3 build that uploads is
# published; once RECIPE 3 pictures are stored, a different length is RECIPE 4.
LEDGER = {2: (0xfad306d7, 5.5), 3: (0xfad306d7, 5.5)}


# ── the digest, as PortraitGrade.GradeDigest computes it ────────────────────

def fnv1a32(data: bytes, h: int = 2166136261) -> int:
    for b in data:
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def grade_digest(table: bytes, key: str) -> int:
    return fnv1a32(key.encode("utf-8"), fnv1a32(table))


# ── reading the constants ───────────────────────────────────────────────────

def _initialiser(masked: str, code: str, name: str) -> str:
    """The text between `name =` and the `;` that ends the declaration,
    skipping any `;` inside string literals (a baked-from key is full of
    them). The declaration is found in `masked` (literals blanked, offsets
    kept), so CsLiteral's own emitted text cannot be mistaken for it; the
    value is read from `code` (literals kept)."""
    decl = masked.find(" " + name + " =")
    assert decl >= 0, f"no declaration of {name}"
    assert masked.find(" " + name + " =", decl + 1) < 0, f"two declarations of {name}"
    i = code.index("=", decl) + 1
    start = i
    while i < len(code):
        ch = code[i]
        if ch == '"':
            i += 1
            while code[i] != '"':
                i += 2 if code[i] == "\\" else 1
        elif ch == ";":
            return code[start:i]
        i += 1
    raise AssertionError(f"unterminated declaration of {name}")


def _string_value(init: str) -> str:
    """Concatenated `"..." + "..."` pieces, the only form CsLiteral emits."""
    out, i = [], 0
    rest = init.strip()
    while i < len(rest):
        ch = rest[i]
        if ch == '"':
            j = i + 1
            piece = []
            while rest[j] != '"':
                assert rest[j] != "\\", "escapes are never emitted"
                piece.append(rest[j])
                j += 1
            out.append("".join(piece))
            i = j + 1
        elif ch in " \t\r\n+":
            i += 1
        else:
            raise AssertionError(f"not a plain string concatenation: {rest[:60]!r}")
    return "".join(out)


def _uint_value(init: str) -> int:
    t = init.strip()
    assert t.endswith("u"), f"not a uint literal: {t!r}"
    return int(t[:-1], 0)


def _float_value(init: str) -> float:
    t = init.strip()
    assert re.fullmatch(r"[0-9]+(\.[0-9]+)?f", t), f"not a plain float literal: {t!r}"
    return float(t[:-1])


def _int_value(init: str) -> int:
    t = init.strip()
    assert re.fullmatch(r"[0-9]+", t), f"not a plain int literal: {t!r}"
    return int(t)


def read_constants(grade_src: str, render_src: str) -> dict:
    gm, g = mask_code(grade_src), strip_comments_only(grade_src)
    rm, r = mask_code(render_src), strip_comments_only(render_src)
    return {
        "marker": _string_value(_initialiser(gm, g, "GRADE_TABLE_MARKER")),
        "b64": _string_value(_initialiser(gm, g, "GRADE_LUT_B64")),
        "fnv": _uint_value(_initialiser(gm, g, "GRADE_LUT_FNV")),
        "key": _string_value(_initialiser(gm, g, "GRADE_BAKED_FROM")),
        "recipe": _int_value(_initialiser(rm, r, "RECIPE")),
        "recipe_fnv": _uint_value(_initialiser(rm, r, "RECIPE_GRADE_FNV")),
        "sim_secs": _float_value(_initialiser(rm, r, "PARTICLE_SIM_SECS")),
    }


def render_int(name: str) -> int:
    src = RENDER_CS.read_text(encoding="utf-8")
    return _int_value(_initialiser(mask_code(src), strip_comments_only(src), name))


def render_float(name: str) -> float:
    src = RENDER_CS.read_text(encoding="utf-8")
    return _float_value(_initialiser(mask_code(src), strip_comments_only(src), name))


def aura_max_lifetime(effect_src: str) -> float:
    """The longest `startLifetime = <float>f` the effect cosmetic configures.
    Those auras are not prewarmed, so a snapshot shorter than a lifetime holds
    fewer particles than the aura does in game."""
    code = mask_code(effect_src)
    literal = strip_comments_only(effect_src)
    values = [float(literal[m.start(1):m.end(1)])
              for m in re.finditer(r"startLifetime\s*=\s*([0-9]+(?:\.[0-9]+)?)f\s*;", code)]
    assert values, "no startLifetime assignment found in the effect cosmetic"
    return max(values)


# ── the verifier ────────────────────────────────────────────────────────────

def verify(c: dict, ledger: dict, aura_life: float = 0.0) -> list:
    problems = []
    if any(k > c["recipe"] for k in ledger):
        problems.append(f"RECIPE {c['recipe']} is below a ledger entry: RECIPE never goes down")
    if c["b64"] == "":
        if c["marker"] != MARK_PLACEHOLDER:
            problems.append("placeholder table but the marker is " + repr(c["marker"]))
        if c["fnv"] != 0 or c["key"] != "" or c["recipe_fnv"] != 0:
            problems.append("placeholder table but GRADE_LUT_FNV, GRADE_BAKED_FROM or RECIPE_GRADE_FNV is set")
        return problems
    if c["marker"] != MARK_BAKED:
        problems.append("baked table but the marker is " + repr(c["marker"]))
    try:
        table = base64.b64decode(c["b64"], validate=True)
    except Exception as ex:  # noqa: BLE001 - the message is the finding
        return problems + [f"GRADE_LUT_B64 does not decode: {ex}"]
    if len(table) != LUT_BYTES:
        return problems + [f"table is {len(table)} bytes, want {LUT_BYTES}"]
    if c["key"] == "":
        problems.append("baked table with no GRADE_BAKED_FROM key")
    d = grade_digest(table, c["key"])
    if d != c["fnv"]:
        problems.append(f"digest of table+key is {d:08x}, GRADE_LUT_FNV says {c['fnv']:08x} (mixed or edited paste)")
    if c["recipe_fnv"] != d:
        problems.append(f"RECIPE_GRADE_FNV is {c['recipe_fnv']:08x}, the table is {d:08x}")
    entry = ledger.get(c["recipe"])
    if entry is None:
        problems.append(f"no ledger entry for RECIPE {c['recipe']}: append {c['recipe']}: (0x{d:08x}, {c['sim_secs']!r})")
        return problems
    have, have_sim = entry
    if have != d:
        problems.append(
            f"RECIPE {c['recipe']} already renders table {have:08x}; a different table ({d:08x}) "
            "needs a RECIPE bump and a new ledger entry")
    if have_sim is None:
        problems.append(f"the ledger entry for RECIPE {c['recipe']} has no particle length")
    elif have_sim != c["sim_secs"]:
        problems.append(
            f"RECIPE {c['recipe']} already renders particles at {have_sim} s; a different length "
            f"({c['sim_secs']} s) needs a RECIPE bump and a new ledger entry")
    if c["sim_secs"] < aura_life:
        problems.append(
            f"PARTICLE_SIM_SECS {c['sim_secs']} s is shorter than the longest aura start lifetime "
            f"({aura_life} s): an equipped aura would be captured below its steady count")
    return problems


def ledger_regressions(head: dict, now: dict) -> list:
    """What changed in entries the committed ledger already had: any change
    at all (see the module docstring)."""
    problems = []
    for recipe, (head_fnv, head_sim) in sorted(head.items()):
        if recipe not in now:
            problems.append(f"RECIPE {recipe} was removed from the ledger")
            continue
        now_fnv, now_sim = now[recipe]
        if now_fnv != head_fnv:
            problems.append(f"RECIPE {recipe}: committed table {head_fnv:08x}, now {now_fnv:08x}")
        if now_sim != head_sim:
            problems.append(f"RECIPE {recipe}: committed particle length {head_sim} s, now {now_sim}")
    return problems


def parse_ledger(module_text: str) -> dict:
    """LEDGER from a version of this file. An older shape whose values are
    bare digests reads as (digest, None)."""
    for node in ast.parse(module_text).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LEDGER" for t in node.targets):
            raw = ast.literal_eval(node.value)
            return {k: (v, None) if isinstance(v, int) else tuple(v) for k, v in raw.items()}
    raise AssertionError("no LEDGER assignment")


def marker_problems(plugin_code: str, baked: bool) -> list:
    """`plugin_code`: every plugin .cs file with comments stripped and string
    literals kept."""
    problems = []
    n_placeholder = plugin_code.count(MARK_PLACEHOLDER)
    n_baked = plugin_code.count(MARK_BAKED)
    want = (0, 1) if baked else (1, 0)
    if (n_placeholder, n_baked) != want:
        problems.append(
            f"marker literals in code: PLACEHOLDER x{n_placeholder}, BAKED x{n_baked}; want x{want[0]}, x{want[1]}")
    return problems


# ── negative controls first ─────────────────────────────────────────────────

def _baked(table: bytes, key: str, recipe: int, **over) -> dict:
    d = grade_digest(table, key)
    c = {"marker": MARK_BAKED, "b64": base64.b64encode(table).decode(), "fnv": d,
         "key": key, "recipe": recipe, "recipe_fnv": d, "sim_secs": 3.0}
    c.update(over)
    return c


TABLE_A = bytes((i * 7) % 256 for i in range(LUT_BYTES))
TABLE_B = bytes((i * 11) % 256 for i in range(LUT_BYTES))
KEY_A = "break=0;vol=Post_Main,global=1,weight=1,priority=0;postExposure=1.5;"
KEY_B = "break=0;vol=Post_Main,global=1,weight=1,priority=0;postExposure=1.25;"
PLACEHOLDER = {"marker": MARK_PLACEHOLDER, "b64": "", "fnv": 0, "key": "", "recipe": 2, "recipe_fnv": 0,
               "sim_secs": 3.0}


def test_fnv_is_standard_fnv1a32():
    assert fnv1a32(b"") == 0x811C9DC5
    assert fnv1a32(b"a") == 0xE40C292C
    assert fnv1a32(b"foobar") == 0xBF9CF968


def test_verifier_passes_the_legal_states():
    dA = grade_digest(TABLE_A, KEY_A)
    assert verify(PLACEHOLDER, {}) == []
    assert verify(_baked(TABLE_A, KEY_A, 2), {2: (dA, 3.0)}, aura_life=2.2) == []
    # a rig-only RECIPE bump keeps the table and the length, with its own entry
    assert verify(_baked(TABLE_A, KEY_A, 3), {2: (dA, 3.0), 3: (dA, 3.0)}, aura_life=2.2) == []


def test_verifier_refuses_a_new_table_at_a_ledgered_recipe():
    dA = grade_digest(TABLE_A, KEY_A)
    p = verify(_baked(TABLE_B, KEY_A, 2), {2: (dA, 3.0)})
    assert any("needs a RECIPE bump" in x for x in p), p


def test_verifier_refuses_a_table_with_no_ledger_entry():
    p = verify(_baked(TABLE_B, KEY_A, 3), {2: (grade_digest(TABLE_A, KEY_A), 3.0)})
    assert any("no ledger entry" in x for x in p), p


def test_verifier_refuses_a_mixed_paste():
    mixed = dict(_baked(TABLE_A, KEY_A, 2), key=KEY_B)   # table A, GRADE_LUT_FNV from A+keyA, key from B
    p = verify(mixed, {2: (grade_digest(TABLE_A, KEY_A), 3.0)})
    assert any("mixed or edited paste" in x for x in p), p


def test_verifier_refuses_an_unnamed_table_and_a_stale_marker():
    d = grade_digest(TABLE_A, KEY_A)
    p = verify(_baked(TABLE_A, KEY_A, 2, recipe_fnv=0), {2: (d, 3.0)})
    assert any("RECIPE_GRADE_FNV is 00000000" in x for x in p), p
    p = verify(_baked(TABLE_A, KEY_A, 2, marker=MARK_PLACEHOLDER), {2: (d, 3.0)})
    assert any("baked table but the marker" in x for x in p), p
    p = verify(dict(PLACEHOLDER, marker=MARK_BAKED), {})
    assert any("placeholder table but the marker" in x for x in p), p


def test_verifier_refuses_a_short_table_and_a_lowered_recipe():
    short = _baked(TABLE_A[:-3], KEY_A, 2)
    assert any("bytes, want" in x for x in verify(short, {2: (short["fnv"], 3.0)}))
    d = grade_digest(TABLE_A, KEY_A)
    assert any("never goes down" in x for x in verify(_baked(TABLE_A, KEY_A, 2), {2: (d, 3.0), 3: (d, 3.0)}))


def test_verifier_refuses_every_particle_length_mismatch():
    d = grade_digest(TABLE_A, KEY_A)
    picked = _baked(TABLE_A, KEY_A, 2, sim_secs=3.0)
    p = verify(picked, {2: (d, 2.5)}, aura_life=2.2)
    assert any("already renders particles at 2.5 s" in x for x in p), p
    p = verify(picked, {2: (d, None)}, aura_life=2.2)
    assert any("has no particle length" in x for x in p), p
    short = _baked(TABLE_A, KEY_A, 2, sim_secs=2.0)
    p = verify(short, {2: (d, 2.0)}, aura_life=2.2)
    assert any("shorter than the longest aura start lifetime" in x for x in p), p


def test_ledger_regressions_refuse_any_change_to_a_committed_entry():
    assert ledger_regressions({}, {2: (1, 3.0)}) == []
    assert ledger_regressions({2: (1, 3.0)}, {2: (1, 3.0)}) == []
    assert ledger_regressions({2: (1, 3.0)}, {2: (1, 3.0), 3: (1, 3.0)}) == []
    assert any("committed table" in x for x in ledger_regressions({2: (1, 3.0)}, {2: (5, 3.0)}))
    assert any("committed particle length" in x for x in ledger_regressions({2: (1, 3.0)}, {2: (1, 3.5)}))
    assert any("committed particle length" in x for x in ledger_regressions({2: (1, None)}, {2: (1, 3.0)}))
    assert any("committed particle length" in x for x in ledger_regressions({2: (1, 3.0)}, {2: (1, None)}))
    assert any("removed" in x for x in ledger_regressions({2: (1, 3.0)}, {}))


def test_parse_ledger_reads_both_shapes():
    assert parse_ledger("LEDGER = {2: 0xfad306d7}\n") == {2: (0xfad306d7, None)}
    assert parse_ledger("X = 1\nLEDGER = {2: (0x1, 2.5), 3: (0x2, 3.5)}\n") == {2: (1, 2.5), 3: (2, 3.5)}
    with pytest.raises(AssertionError):
        parse_ledger("LEDGE = {}\n")


def test_aura_lifetime_reader_takes_the_largest_code_assignment():
    src = ("class A {\n  void C() {\n    main.startLifetime = 1.2f;\n"
           "    // main.startLifetime = 9.9f;\n    main.startLifetime = 2.2f; main.startSpeed = 0.6f;\n  }\n}\n")
    assert aura_max_lifetime(src) == 2.2
    with pytest.raises(AssertionError):
        aura_max_lifetime("class A { }")


def test_marker_check_refuses_both_or_neither():
    assert marker_problems('x = "' + MARK_PLACEHOLDER + '";', baked=False) == []
    assert marker_problems('x = "' + MARK_BAKED + '";', baked=True) == []
    assert marker_problems('x = "' + MARK_PLACEHOLDER + '"; y = "' + MARK_BAKED + '";', baked=False)
    assert marker_problems('x = "SCR_GRADE_TABLE", "=", "BAKED";', baked=True)
    assert marker_problems("", baked=False)


def test_reader_round_trips_what_csliteral_emits():
    b64 = base64.b64encode(TABLE_A).decode()
    wrapped_b64 = " +\n".join('            "' + b64[i:i + 100] + '"' for i in range(0, len(b64), 100))
    wrapped_key = " +\n".join('            "' + KEY_A[i:i + 20] + '"' for i in range(0, len(KEY_A), 20))
    grade = (
        "class X {\n"
        '        internal const string GRADE_TABLE_MARKER = "' + MARK_BAKED + '";\n'
        "        internal const string GRADE_LUT_B64 =\n" + wrapped_b64 + ";\n"
        "        internal const uint GRADE_LUT_FNV = 0x1234abcdu;\n"
        "        internal const string GRADE_BAKED_FROM =\n" + wrapped_key + ";\n"
        "}\n"
    )
    render = ("class Y {\n        internal const int RECIPE = 7;\n        internal const uint RECIPE_GRADE_FNV = 0u;\n"
              "        internal const float PARTICLE_SIM_SECS = 3.5f;\n}\n")
    c = read_constants(grade, render)
    assert c == {"marker": MARK_BAKED, "b64": b64, "fnv": 0x1234ABCD, "key": KEY_A, "recipe": 7, "recipe_fnv": 0,
                 "sim_secs": 3.5}


# ── the real source: constants ──────────────────────────────────────────────

def _real_constants() -> dict:
    return read_constants(GRADE_CS.read_text(encoding="utf-8"), RENDER_CS.read_text(encoding="utf-8"))


def test_source_grade_constants_are_consistent_with_the_ledger():
    aura = aura_max_lifetime(EFFECT_CS.read_text(encoding="utf-8"))
    assert verify(_real_constants(), LEDGER, aura_life=aura) == []


def test_committed_ledger_entries_are_unchanged():
    """Against `git show HEAD:` of this file. Vacuous while the file is not
    committed (no entries at HEAD); skipped where there is no git checkout."""
    try:
        inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=HERE,
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available here")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not a git checkout")
    shown = subprocess.run(["git", "show", "HEAD:./" + Path(__file__).name], cwd=HERE,
                           capture_output=True, text=True, timeout=30, encoding="utf-8")
    head = parse_ledger(shown.stdout) if shown.returncode == 0 else {}
    assert ledger_regressions(head, LEDGER) == []


def test_source_marker_literal_discriminates_the_builds():
    c = _real_constants()
    code = "\n".join(strip_comments_only(p.read_text(encoding="utf-8")) for p in sorted(PLUGIN.glob("*.cs")))
    assert marker_problems(code, baked=c["b64"] != "") == []


def test_source_marker_is_referenced_from_code():
    # An unreferenced const may never reach the literal heap (#306); the LoadGrade
    # log line is the reference.
    masked = mask_code(GRADE_CS.read_text(encoding="utf-8"))
    assert masked.count("GRADE_TABLE_MARKER") >= 2


def test_source_digest_matches_the_python_mirror():
    code = strip_comments_only(GRADE_CS.read_text(encoding="utf-8"))
    assert "return Fnv32(Encoding.UTF8.GetBytes(key ?? \"\"), Fnv32(table));" in code
    assert "private static uint Fnv32(byte[] d, uint h = 2166136261u)" in code
    assert "{ h ^= d[i]; h *= 16777619u; }" in code


def test_no_runtime_provisional_length_gate_remains():
    # The ledger is the only control on the particle length (module docstring):
    # a runtime boolean with no writer is a gate that cannot close.
    for p in sorted(PLUGIN.glob("*.cs")):
        assert "PARTICLE_SIM_PROVISIONAL" not in mask_code(p.read_text(encoding="utf-8")), p.name


# ── the grade lookup, mirrored ──────────────────────────────────────────────
# PortraitGrade.LutSample/Tri in Python. The source pins below fail when the
# C# lines the mirror copies change, so the mirror cannot drift silently.

def _lut_lo(c: int) -> int:
    return c >> 4 if c < 240 else 15


def _lut_w(c: int) -> int:
    return (c & 15) * 16 if c < 240 else ((c - 240) * 256 + 7) // 15


def _node_value(k: int) -> int:
    return 255 if k >= LUT_N - 1 else k * 16


def _tri(lut, i, wr, wg, wb, rounding=True):
    dB, dG, dR = 3, LUT_N * 3, LUT_N * LUT_N * 3
    c00 = lut[i] * (256 - wb) + lut[i + dB] * wb
    c01 = lut[i + dG] * (256 - wb) + lut[i + dG + dB] * wb
    c10 = lut[i + dR] * (256 - wb) + lut[i + dR + dB] * wb
    c11 = lut[i + dR + dG] * (256 - wb) + lut[i + dR + dG + dB] * wb
    c0 = c00 * (256 - wg) + c01 * wg
    c1 = c10 * (256 - wg) + c11 * wg
    v = c0 * (256 - wr) + c1 * wr
    return (v + (1 << 23)) >> 24 if rounding else v >> 24


def lut_sample(lut, r, g, b, rounding=True):
    o = ((_lut_lo(r) * LUT_N + _lut_lo(g)) * LUT_N + _lut_lo(b)) * 3
    wr, wg, wb = _lut_w(r), _lut_w(g), _lut_w(b)
    return tuple(_tri(lut, o + k, wr, wg, wb, rounding) for k in range(3))


def identity_table() -> bytes:
    t = bytearray(LUT_BYTES)
    for ri in range(LUT_N):
        for gi in range(LUT_N):
            for bi in range(LUT_N):
                o = ((ri * LUT_N + gi) * LUT_N + bi) * 3
                t[o], t[o + 1], t[o + 2] = _node_value(ri), _node_value(gi), _node_value(bi)
    return bytes(t)


def identity_problems(sample) -> list:
    """Each channel through the identity table must come back unchanged for
    all 256 levels. Through the identity table a channel's output depends on
    its own input only (every corner of a cell along the other two axes holds
    the same value for it), so each level is checked against a spread of
    values on the other two axes."""
    ident = identity_table()
    others = (0, 1, 15, 16, 128, 239, 240, 254, 255)
    bad = []
    for c in range(256):
        for o1 in others:
            for o2 in others:
                if sample(ident, c, o1, o2)[0] != c or sample(ident, o1, c, o2)[1] != c or sample(ident, o1, o2, c)[2] != c:
                    bad.append((c, o1, o2))
    return bad


def test_lut_index_and_weight_bounds_hold_for_every_level():
    # the lower node is at most 15 (so every +1 corner exists) and the weight is
    # a fraction of 256: every Tri value is a convex combination of eight table
    # bytes with weights summing to 2^24, so it lies between their min and max
    for c in range(256):
        assert 0 <= _lut_lo(c) <= 15
        assert 0 <= _lut_w(c) <= 256
    assert _lut_w(255) == 256 and _lut_lo(255) == 15
    assert all(_lut_w(c) == (c & 15) * 16 for c in range(240))


def test_identity_table_is_a_no_op_and_the_broken_mirror_is_caught():
    assert identity_problems(lut_sample) == []
    # negative control: dropping the final rounding must be caught
    assert identity_problems(lambda lut, r, g, b: lut_sample(lut, r, g, b, rounding=False)) != []


def test_lut_output_stays_between_the_corner_bytes():
    import random
    rng = random.Random(0x5C)
    for table in (bytes([255]) * LUT_BYTES, bytes(LUT_BYTES), bytes(rng.randrange(256) for _ in range(LUT_BYTES))):
        for _ in range(4000):
            r, g, b = rng.randrange(256), rng.randrange(256), rng.randrange(256)
            out = lut_sample(table, r, g, b)
            o = ((_lut_lo(r) * LUT_N + _lut_lo(g)) * LUT_N + _lut_lo(b)) * 3
            for k in range(3):
                corners = [table[o + k + dr + dg + db] for dr in (0, LUT_N * LUT_N * 3)
                           for dg in (0, LUT_N * 3) for db in (0, 3)]
                assert min(corners) <= out[k] <= max(corners), (r, g, b, k)


def test_source_lookup_matches_the_python_mirror():
    code = re.sub(r"\s+", " ", strip_comments_only(GRADE_CS.read_text(encoding="utf-8")))
    for line in (
        "a[c] = (byte)(c < 240 ? c >> 4 : 15);",
        "a[c] = (short)(c < 240 ? (c & 15) * 16 : ((c - 240) * 256 + 7) / 15);",
        "int o = ((s_lutLo[r] * LUT_N + s_lutLo[g]) * LUT_N + s_lutLo[b]) * 3;",
        "const int dB = 3, dG = LUT_N * 3, dR = LUT_N * LUT_N * 3;",
        "int c00 = lut[i] * (256 - wb) + lut[i + dB] * wb;",
        "int c01 = lut[i + dG] * (256 - wb) + lut[i + dG + dB] * wb;",
        "int c10 = lut[i + dR] * (256 - wb) + lut[i + dR + dB] * wb;",
        "int c11 = lut[i + dR + dG] * (256 - wb) + lut[i + dR + dG + dB] * wb;",
        "int c0 = c00 * (256 - wg) + c01 * wg;",
        "int c1 = c10 * (256 - wg) + c11 * wg;",
        "long v = (long)c0 * (256 - wr) + (long)c1 * wr;",
        "return (byte)((v + (1L << 23)) >> 24);",
        "private const int LUT_N = 17;",
    ):
        assert line in code, line


# ── structure: reading statements and guards ────────────────────────────────

def _depths(masked: str) -> list:
    """Brace depth before each offset of `masked` (a block's own `{` makes 1)."""
    out, d = [], 0
    for ch in masked:
        out.append(d)
        if ch == "{":
            d += 1
        elif ch == "}":
            d -= 1
    out.append(d)
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _close(m: str, i: int, open_ch: str, close_ch: str) -> int:
    """`m[i]` is `open_ch`: the offset just past its matching `close_ch`."""
    d = 0
    for k in range(i, len(m)):
        if m[k] == open_ch:
            d += 1
        elif m[k] == close_ch:
            d -= 1
            if d == 0:
                return k + 1
    raise CsParseError(f"unbalanced {open_ch!r} at {i}")


def _skip_ws(m: str, i: int) -> int:
    while i < len(m) and m[i].isspace():
        i += 1
    return i


def next_statement(m: str, i: int):
    """(start, end) of the statement at or after offset `i` of the masked
    text `m`, or None at the `}` that closes the enclosing block (or the end
    of the text). Understands blocks, `if`/`else`, the parenthesised loop and
    `using`/`lock`/`switch` heads, `do`, `try`/`catch`/`finally`, and simple
    statements ending at a `;` outside parentheses and braces (so a lambda's
    body inside an argument list stays inside its statement)."""
    i = _skip_ws(m, i)
    if i >= len(m) or m[i] == "}":
        return None
    if m[i] == "{":
        return (i, _close(m, i, "{", "}"))
    head = re.match(r"(if|while|for|foreach|using|lock|switch|catch)\b", m[i:])
    if head:
        j = _skip_ws(m, i + len(head.group(1)))
        if m[j] == "(":
            j = _close(m, j, "(", ")")
        body = next_statement(m, j)
        if body is None:
            raise CsParseError(f"{head.group(1)} without a body at {i}")
        end = body[1]
        if head.group(1) == "if":
            k = _skip_ws(m, end)
            if re.match(r"else\b", m[k:]):
                end = next_statement(m, k + 4)[1]
        return (i, end)
    head = re.match(r"(try|finally|do|else)\b", m[i:])
    if head:
        body = next_statement(m, i + len(head.group(1)))
        end = body[1]
        if head.group(1) == "try":
            while True:
                k = _skip_ws(m, end)
                nxt = re.match(r"(catch|finally)\b", m[k:])
                if not nxt:
                    break
                end = next_statement(m, k)[1] if nxt.group(1) == "catch" else next_statement(m, k + 7)[1]
        if head.group(1) == "do":
            end = m.index(";", end) + 1
        return (i, end)
    dp = db = 0
    for k in range(i, len(m)):
        ch = m[k]
        if ch in "([":
            dp += 1
        elif ch in ")]":
            dp -= 1
        elif ch == "{":
            db += 1
        elif ch == "}":
            if db == 0:
                raise CsParseError(f"statement at {i} runs into the end of its block")
            db -= 1
        elif ch == ";" and dp == 0 and db == 0:
            return (i, k + 1)
    raise CsParseError(f"unterminated statement at {i}")


def statements(m: str, start: int, end: int) -> list:
    """The top-level statements of the statement list m[start:end]."""
    out, i = [], start
    while True:
        s = next_statement(m[:end], i)
        if s is None:
            return out
        out.append(s)
        i = s[1]


def if_parts(m: str, stmt):
    """(condition span, body span, has_else) of an `if` statement, or None."""
    a, b = stmt
    if not re.match(r"if\b", m[a:b]):
        return None
    j = _skip_ws(m, a + 2)
    cond_end = _close(m, j, "(", ")")
    body = next_statement(m, cond_end)
    k = _skip_ws(m, body[1])
    has_else = k < b and re.match(r"else\b", m[k:b]) is not None
    return (j + 1, cond_end - 1), body, has_else


def last_statement_is(m: str, body, exit_stmt: str) -> bool:
    """The body's last statement is exactly `exit_stmt`: `return;`,
    `yield break;`, or `return` (a return with or without a value). A body
    that is a single statement is its own last statement."""
    a, b = body
    if m[a] == "{":
        inner_stmts = statements(m, a + 1, b - 1)
        if not inner_stmts:
            return False
        a, b = inner_stmts[-1]
    text = _norm(m[a:b])
    if exit_stmt == "return":
        return re.fullmatch(r"return\b[^;]*;", text) is not None
    return text == exit_stmt


def find_guards(block: str, cond: str) -> list:
    """Every `if (<cond>)` in `block` whose condition equals `cond` (whitespace
    normalised), as (if_offset, body_text, depth, body_span). The body is the
    braced block or the single statement that follows."""
    masked = mask_code(block)
    code = strip_comments_only(block)
    depths = _depths(masked)
    found = []
    for m in re.finditer(r"\bif\s*\(", masked):
        open_paren = m.end() - 1
        k = _close(masked, open_paren, "(", ")") - 1
        if _norm(code[open_paren + 1:k]) != _norm(cond):
            continue
        body = next_statement(masked, k + 1)
        a, b = body
        text = code[a + 1:b - 1] if masked[a] == "{" else code[a:b]
        found.append((m.start(), _norm(text), depths[m.start()], body))
    return found


# ── structure: clauses, paths and exits ─────────────────────────────────────

LOOPS = ("while", "for", "foreach", "do")
# The clauses whose statements run whenever their statement runs.
PLAIN = ("body", "block", "try", "using", "lock")


def body_span(m: str):
    """The span of the first braced block of `m` (a method's body)."""
    o = m.index("{")
    return (o, _close(m, o, "{", "}"))


def inner(m: str, span) -> list:
    """The statements of a braced span, or the span alone when it is a single
    statement."""
    a, b = span
    return statements(m, a + 1, b - 1) if m[a] == "{" else [span]


def slots(m: str, stmt) -> list:
    """The clauses directly inside statement `stmt` of the masked text `m`,
    in order, as (kind, head span or None, body span): `block` for a bare
    block; `if` and its `else`; a loop, `using`, `lock` or `switch` with its
    head; `do`; `try` with each `catch` (and its head) and its `finally`. A
    simple statement has none: a lambda inside it is part of its expression."""
    a, b = stmt
    if m[a] == "{":
        return [("block", None, stmt)]
    kw = re.match(r"(if|while|for|foreach|using|lock|switch|try|do)\b", m[a:b])
    if not kw:
        return []
    kind = kw.group(1)
    j = _skip_ws(m, a + len(kind))
    head = None
    if kind not in ("try", "do"):
        if m[j] != "(":
            raise CsParseError(f"{kind} without a head at {a}")
        k = _close(m, j, "(", ")")
        head, j = (j + 1, k - 1), k
    body = next_statement(m, j)
    out = [(kind, head, body)]
    end = body[1]
    if kind == "if":
        k = _skip_ws(m, end)
        if k < b and re.match(r"else\b", m[k:b]):
            out.append(("else", None, next_statement(m, k + 4)))
    elif kind == "try":
        while True:
            k = _skip_ws(m, end)
            nxt = re.match(r"(catch|finally)\b", m[k:b]) if k < b else None
            if not nxt:
                break
            j = _skip_ws(m, k + len(nxt.group(1)))
            head = None
            if nxt.group(1) == "catch" and m[j] == "(":
                c = _close(m, j, "(", ")")
                head, j = (j + 1, c - 1), c
            part = next_statement(m, j)
            out.append((nxt.group(1), head, part))
            end = part[1]
    return out


def clause(m: str, stmt, kind: str, n: int = 0):
    """(head span or None, statements) of the n-th `kind` clause of `stmt`."""
    got = [(h, body) for k, h, body in slots(m, stmt) if k == kind]
    if len(got) <= n:
        raise CsParseError(f"no {kind} clause #{n} in {_norm(m[stmt[0]:stmt[1]])[:60]!r}")
    return got[n][0], inner(m, got[n][1])


def all_statements(m: str, stmts):
    """Every statement of `stmts`, nested ones included, in text order."""
    for s in stmts:
        yield s
        for _, _, body in slots(m, s):
            yield from all_statements(m, inner(m, body))


def stmt_path(m: str, offset: int) -> list:
    """From the method body down to the innermost statement that holds
    `offset`: one (statements, index, clause kind, head span) per level, the
    first level being the body's own statements (kind `body`)."""
    stmts, kind, head = inner(m, body_span(m)), "body", None
    path = []
    while True:
        idx = next((i for i, (a, b) in enumerate(stmts) if a <= offset < b), None)
        if idx is None:
            raise CsParseError(f"offset {offset} is in no statement")
        path.append((stmts, idx, kind, head))
        for k, h, body in slots(m, stmts[idx]):
            if body[0] <= offset < body[1]:
                if k == "switch":
                    raise CsParseError("a switch is not read")
                stmts, kind, head = inner(m, body), k, h
                break
        else:
            return path


EXIT_HEAD = re.compile(r"(?:return|throw|goto)\b|yield\s+break\b")


def exits_in(m: str, stmt, owned: frozenset = frozenset()) -> list:
    """The statements inside `stmt` (itself included) that can leave the
    statement list holding `stmt`: return, throw (a statement or an
    expression), goto, yield break, and a break or continue that no loop
    inside `stmt` owns. A lambda's return is part of an expression, not a
    statement, and is not one."""
    subs = slots(m, stmt)
    if not subs:
        t = _norm(m[stmt[0]:stmt[1]])
        jump = re.match(r"(break|continue)\b", t)
        if EXIT_HEAD.match(t) or re.search(r"\bthrow\b", t) or (jump and jump.group(1) not in owned):
            return [t]
        return []
    out = []
    for kind, _, body in subs:
        if kind == "switch":
            raise CsParseError("a switch is not read")
        mine = frozenset(("break", "continue")) if kind in LOOPS else owned
        for s in inner(m, body):
            out += exits_in(m, s, mine)
    return out


def earlier_exits(m: str, code: str, offset: int, allowed=()) -> list:
    """The exits (exits_in) of every statement that runs before control
    reaches `offset`: in each list on its path, the statements before the one
    on the path. A statement whose normalised code is in `allowed` is
    skipped."""
    allowed = {_norm(x) for x in allowed}
    out = []
    for stmts, idx, _, _ in stmt_path(m, offset):
        for s in stmts[:idx]:
            if _norm(code[s[0]:s[1]]) not in allowed:
                out += exits_in(m, s)
    return out


def path_conditions(m: str, code: str, offset: int) -> list:
    """The clauses on the path to `offset` that do not run whenever their
    statement runs -- `if (cond)`, `else`, a loop, `catch`, `finally` -- as
    normalised code, outermost first."""
    out = []
    for _, _, kind, head in stmt_path(m, offset):
        if kind not in PLAIN:
            out.append(kind + (" (" + _norm(code[head[0]:head[1]]) + ")" if head else ""))
    return out


def leaf_code(m: str, code: str, offset: int) -> str:
    """The normalised code of the innermost statement that holds `offset`."""
    stmts, idx, _, _ = stmt_path(m, offset)[-1]
    return _norm(code[stmts[idx][0]:stmts[idx][1]])


def list_position(m: str, offset: int):
    """(statement list, index) of the innermost statement holding `offset`."""
    stmts, idx, _, _ = stmt_path(m, offset)[-1]
    return stmts, idx


def unconditional_problems(block: str, offset: int, allowed_exits=()) -> list:
    """Problems with "the statement at `offset` runs whenever the method runs
    (an exception aside)": no conditional clause on its path, no exit before
    it other than the statements in `allowed_exits`, and inside its own
    statement no `&&`, `||`, `?` or `=>` before it."""
    m, code = mask_code(block), strip_comments_only(block)
    problems = [f"under {c}" for c in path_conditions(m, code, offset)]
    problems += [f"after an exit: {e[:80]!r}" for e in earlier_exits(m, code, offset, allowed_exits)]
    stmts, idx, _, _ = stmt_path(m, offset)[-1]
    if re.search(r"&&|\|\||\?|=>", m[stmts[idx][0]:offset]):
        problems.append(f"within {_norm(code[stmts[idx][0]:stmts[idx][1]])[:100]!r}")
    return problems


def exits_before(block: str, cond: str, exit_stmt: str, target: str, target_in_literal: bool = False) -> list:
    """Problems with "an `if (cond)` whose body's last statement is exactly
    `exit_stmt` runs before the first `target` whenever the target runs":
    exactly one such guard, its body ends with the exit statement (tokenised,
    not a text prefix), and the guard is itself a statement, with no else, of
    a statement list on the target's path, before the statement at that level
    that holds the target. A guard nested in another statement (a brace-less
    `if`, an `else if`, a block, a loop) is not one."""
    problems = []
    guards = find_guards(block, cond)
    if len(guards) != 1:
        return [f"want one `if ({cond})`, found {len(guards)}"]
    at, body_text, _, body = guards[0]
    m = mask_code(block)
    if not last_statement_is(m, body, exit_stmt):
        problems.append(f"`if ({cond})` does not end with {exit_stmt!r}: {body_text[-80:]!r}")
    hay = strip_comments_only(block) if target_in_literal else m
    t = hay.find(target)
    if t < 0:
        return problems + [f"{target!r} not found"]
    if t < at:
        return problems + [f"`if ({cond})` comes after {target!r}"]
    for stmts, idx, _, _ in stmt_path(m, t):
        hit = [s for s in stmts[:idx] if s[0] == at]
        if hit:
            if if_parts(m, hit[0])[2]:
                problems.append(f"`if ({cond})` has an else branch")
            return problems
    return problems + [f"`if ({cond})` is not a statement of a list that holds {target!r}"]


def dominating_exit(block: str, cond: str, exit_stmt: str, targets: tuple) -> list:
    """Problems with "`if (cond)` is a top-level statement of the method whose
    body ends with exactly `exit_stmt`, and every occurrence of every target
    comes after it": a top-level exit runs before everything after it,
    nested or not."""
    guards = find_guards(block, cond)
    if len(guards) != 1:
        return [f"want one `if ({cond})`, found {len(guards)}"]
    at, body_text, depth, body = guards[0]
    masked = mask_code(block)
    open_brace = masked.index("{")
    top = statements(masked, open_brace + 1, _close(masked, open_brace, "{", "}") - 1)
    problems = []
    if not any(s[0] == at for s in top):
        problems.append(f"`if ({cond})` is not a top-level statement of the method")
    if not last_statement_is(masked, body, exit_stmt):
        problems.append(f"`if ({cond})` does not end with {exit_stmt!r}: {body_text[-80:]!r}")
    for target in targets:
        hits = [m.start() for m in re.finditer(re.escape(target), masked)]
        if not hits:
            problems.append(f"{target!r} not found")
        elif min(hits) < body[1]:
            problems.append(f"{target!r} occurs before `if ({cond})` ends")
    return problems


# The claim beats a fence may skip: its own generation's heartbeat, with a
# budget, and nothing else.
BEAT = r"_renderClaim\.Beat\(gen, (?:DEV_BUDGET|RENDER_BUDGET)\);"


def fence_problems(block: str, fence: str) -> list:
    """After every `yield return` in `block`, the next statement other than
    the run's own claim beat (exactly `_renderClaim.Beat(gen, DEV_BUDGET);`
    or `..., RENDER_BUDGET);`) must be an exit fenced on `fence` (a call such
    as `DevLeverBlocked(gen)`), in one of two forms, in the yield's own block:
        if ((X = <fence>) != null) { ...; yield break; }
        [string] X = <fence>;  if (X != null) { ...; yield break; }
    with no `else`, and the if's body ending with exactly `yield break;`. An
    assignment whose result nothing tests, a call whose result is discarded,
    a test of the wrong polarity or of another variable, an exit that is not
    the body's last statement, and anything between the yield and the fence
    all fail."""
    masked = mask_code(block)
    fence_re = re.escape(_norm(fence))
    problems = []
    for y in re.finditer(r"\byield\s+return\b", masked):
        yend = next_statement(masked, y.start())[1]
        s = next_statement(masked, yend)
        while s is not None and re.fullmatch(BEAT, _norm(masked[s[0]:s[1]])):
            s = next_statement(masked, s[1])
        where = f"yield at {y.start()}"
        if s is None:
            problems.append(f"{where}: nothing follows it in its block")
            continue
        text = _norm(masked[s[0]:s[1]])
        parts = if_parts(masked, s)
        cond_ok = False
        if parts is not None:
            (ca, cb), body, has_else = parts
            cond = _norm(masked[ca:cb])
            cond_ok = re.fullmatch(r"\(\s*\w+\s*=\s*" + fence_re + r"\s*\)\s*!=\s*null", cond) is not None
        else:
            assign = re.fullmatch(r"(?:string\s+)?(\w+)\s*=\s*" + fence_re + r"\s*;", text)
            if assign:
                s = next_statement(masked, s[1])
                parts = if_parts(masked, s) if s is not None else None
                if parts is not None:
                    (ca, cb), body, has_else = parts
                    cond_ok = _norm(masked[ca:cb]) == assign.group(1) + " != null"
        if parts is None or not cond_ok:
            problems.append(f"{where} is followed by {text[:90]!r}, not a fenced exit on {fence}")
            continue
        if has_else:
            problems.append(f"{where}: the fence has an else branch")
        if not last_statement_is(masked, body, "yield break;"):
            problems.append(f"{where}: the fence's body does not end with `yield break;`")
    return problems


def finally_block(block: str) -> str:
    """The body of the method's `finally` clause (text, braces included)."""
    masked = mask_code(block)
    hits = [m for m in re.finditer(r"\bfinally\b", masked)]
    if len(hits) != 1:
        raise CsParseError(f"want one finally, found {len(hits)}")
    j = _skip_ws(masked, hits[0].end())
    return block[j:_close(masked, j, "{", "}")]


def _flat(m: str, a: int, b: int) -> str:
    """m[a:b] with everything inside brackets blanked (the brackets kept)."""
    out, depth = [], 0
    for ch in m[a:b]:
        if ch in ")]}":
            depth -= 1
        out.append(ch if depth == 0 else " ")
        if ch in "([{":
            depth += 1
    return "".join(out)


def or_terms(expr: str) -> list:
    """Split a boolean expression on top-level `||`; a top-level `&&` raises
    (its precedence would make the terms something else)."""
    masked = mask_code(expr)
    flat = _flat(masked, 0, len(masked))
    if "&&" in flat:
        raise CsParseError(f"top-level `&&` in a disjunction: {expr!r}")
    terms, start = [], 0
    for mo in re.finditer(r"\|\|", flat):
        terms.append(expr[start:mo.start()].strip())
        start = mo.end()
    terms.append(expr[start:].strip())
    return [_norm(t) for t in terms if t.strip()]


def refusal_return_problems(block: str, allowed=()) -> list:
    """Every `return` statement of the method (a lambda's return is part of
    an expression, not a statement) is the one success `return null;`, a
    statement in `allowed`, or returns a string that cannot be null: a string
    literal is one of its top-level `+` operands and it has no top-level `?`."""
    m, code = mask_code(block), strip_comments_only(block)
    allowed = {_norm(x) for x in allowed}
    problems, nulls = [], 0
    for s in all_statements(m, inner(m, body_span(m))):
        if slots(m, s) or not re.match(r"return\b", m[s[0]:s[1]]):
            continue
        text = _norm(code[s[0]:s[1]])
        if text == "return null;":
            nulls += 1
            continue
        if text in allowed:
            continue
        a, b = s[0] + len("return"), m.rindex(";", s[0], s[1])
        flat = _flat(m, a, b)
        if "?" in flat:
            problems.append(f"{text[:80]!r} may return null (a top-level conditional)")
            continue
        literal = False
        start = a
        for mo in list(re.finditer(r"(?<![+])\+(?![+=])", flat)) + [None]:
            end = b if mo is None else a + mo.start()
            op_code, op_mask = code[start:end].strip(), m[start:end]
            if re.match(r'(?:\$@|@\$|\$|@)?"', op_code) and not op_mask.strip():
                literal = True
            if mo is not None:
                start = a + mo.end()
        if not literal:
            problems.append(f"{text[:80]!r} may return null (no string literal operand)")
    if nulls != 1:
        problems.append(f"want one `return null;`, found {nulls}")
    return problems


def _texts(code: str, stmts) -> list:
    return [_norm(code[a:b]) for a, b in stmts]


def list_problems(where: str, got: list, want: list) -> list:
    """Normalised statement texts `got` against `want`, in order; a None in
    `want` matches any one statement."""
    for i, w in enumerate(want):
        if i >= len(got):
            return [f"{where}: {len(got)} statements, want {len(want)}"]
        if w is not None and got[i] != _norm(w):
            return [f"{where}: statement {i} is {got[i][:140]!r}, want {_norm(w)[:140]!r}"]
    if len(got) != len(want):
        return [f"{where}: {len(got)} statements, want {len(want)}"]
    return []


def _mut(text: str, old: str, new: str, count: int = -1) -> str:
    """`text` with `old` replaced by `new`: the input of a negative control.
    A control whose `old` is not in the text would test the unmutated text,
    so that raises."""
    if old not in text:
        raise AssertionError(f"negative control target not found: {old[:80]!r}")
    return text.replace(old, new, count)


# ── the readers' negative controls ──────────────────────────────────────────

SYNTH = """
void Upload() {
    if (!GradeBaked)
    {
        LastResult = "x";
        return;
    }
    if (tooBig) { LastResult = "y"; return; }
    ApiClient.PcPortraitUpload(id, d, p, (ok, r) => { });
}
"""
UPLOAD_CALL = "ApiClient.PcPortraitUpload("


def test_guard_reader_negative_controls():
    assert exits_before(SYNTH, "!GradeBaked", "return;", UPLOAD_CALL) == []
    assert exits_before(SYNTH, "tooBig", "return;", UPLOAD_CALL) == []
    after = _mut(_mut(SYNTH, "    if (tooBig) { LastResult = \"y\"; return; }\n", ""),
                 "(ok, r) => { });\n", "(ok, r) => { });\n    if (tooBig) { return; }\n")
    assert any("comes after" in x for x in exits_before(after, "tooBig", "return;", UPLOAD_CALL))
    nested = _mut(_mut(SYNTH, "if (!GradeBaked)", "if (other) { if (!GradeBaked)"), "        return;\n    }\n", "        return;\n    } }\n", 1)
    assert any("is not a statement of a list" in x for x in exits_before(nested, "!GradeBaked", "return;", UPLOAD_CALL))
    no_exit = _mut(SYNTH, "        return;\n", "", 1)
    assert any("does not end with" in x for x in exits_before(no_exit, "!GradeBaked", "return;", UPLOAD_CALL))
    renamed = _mut(SYNTH, "!GradeBaked", "GradeBaked")
    assert any("found 0" in x for x in exits_before(renamed, "!GradeBaked", "return;", UPLOAD_CALL))
    commented = _mut(SYNTH, "    if (!GradeBaked)", "    // if (!GradeBaked)\n    if (true)")
    assert any("found 0" in x for x in exits_before(commented, "!GradeBaked", "return;", UPLOAD_CALL))
    # a brace-less outer `if`: the guard runs only when the outer condition holds
    braceless = _mut(SYNTH, "    if (!GradeBaked)\n", "    if (why != \"retry\") if (!GradeBaked)\n")
    assert any("is not a statement of a list" in x for x in exits_before(braceless, "!GradeBaked", "return;", UPLOAD_CALL))
    # an `else if`: the guard runs only when the previous condition fails
    else_if = _mut(SYNTH, "    if (tooBig)", "    else if (tooBig)")
    assert any("is not a statement of a list" in x for x in exits_before(else_if, "tooBig", "return;", UPLOAD_CALL))
    assert any("has an else branch" in x for x in exits_before(else_if, "!GradeBaked", "return;", UPLOAD_CALL))
    # a guard inside a loop the target is not in
    looped = _mut(SYNTH, "    if (tooBig) { LastResult = \"y\"; return; }\n",
                  "    foreach (var x in xs) { if (tooBig) { LastResult = \"y\"; return; } }\n")
    assert any("is not a statement of a list" in x for x in exits_before(looped, "tooBig", "return;", UPLOAD_CALL))
    # a guard in a list that encloses the target's own list still runs first
    wrapped = _mut(SYNTH, "    ApiClient.PcPortraitUpload(id, d, p, (ok, r) => { });\n",
                   "    try { ApiClient.PcPortraitUpload(id, d, p, (ok, r) => { }); } catch { }\n")
    assert exits_before(wrapped, "!GradeBaked", "return;", UPLOAD_CALL) == []
    # ...but not one in the try when the target is in its catch
    caught = _mut(SYNTH, "    if (tooBig) { LastResult = \"y\"; return; }\n    ApiClient.PcPortraitUpload(id, d, p, (ok, r) => { });\n",
                  "    try { if (tooBig) { LastResult = \"y\"; return; } Work(); }\n    catch { ApiClient.PcPortraitUpload(id, d, p, (ok, r) => { }); }\n")
    assert any("is not a statement of a list" in x for x in exits_before(caught, "tooBig", "return;", UPLOAD_CALL))


def test_exit_statement_is_tokenised_not_prefix_matched():
    # a statement that merely starts with the letters of `return`
    value = _mut(SYNTH, "        return;\n", "        returnValue = true;\n", 1)
    assert any("does not end with" in x for x in exits_before(value, "!GradeBaked", "return;", UPLOAD_CALL))
    single = "void F() { if (c) returnValue = true; Go(); }"
    assert any("does not end with" in x for x in exits_before(single, "c", "return", "Go("))
    assert exits_before("void F() { if (c) return x; Go(); }", "c", "return", "Go(") == []
    assert exits_before("void F() { if (c) { a(); return \"a;b\"; } Go(); }", "c", "return", "Go(") == []
    # the exit is not the last statement
    assert any("does not end with" in x for x in exits_before("void F() { if (c) { return; a(); } Go(); }", "c", "return;", "Go("))
    # the last statement is a nested if that exits only sometimes
    assert any("does not end with" in x for x in exits_before("void F() { if (c) { if (d) return; } Go(); }", "c", "return;", "Go("))
    assert any("does not end with" in x for x in exits_before("IEnumerator F() { if (c) { yield breaker(); } Go(); }", "c", "yield break;", "Go("))


FENCED = """
IEnumerator R(int gen) {
    string blocked;
    try {
        yield return new WaitForEndOfFrame();
        _renderClaim.Beat(gen, DEV_BUDGET);
        string first = DevLeverBlocked(gen);
        if (first != null) { outcome = "aborted: " + first; yield break; }
        for (int i = 0; i < 4; i++)
        {
            yield return null;
            _renderClaim.Beat(gen, DEV_BUDGET);
            if ((blocked = DevLeverBlocked(gen)) != null) { rep.Append("x;y").Append(blocked); yield break; }
            Work();
        }
    }
    finally { Done(); }
}
"""


def test_fence_reader_negative_controls():
    fence = "DevLeverBlocked(gen)"
    assert fence_problems(FENCED, fence) == []
    # assignment only: the result is tested by nothing
    assign_only = _mut(FENCED, '        if (first != null) { outcome = "aborted: " + first; yield break; }\n', "")
    assert fence_problems(assign_only, fence) != []
    # a discarded call, with the old variable still tested
    discarded = _mut(FENCED, "if ((blocked = DevLeverBlocked(gen)) != null)", "DevLeverBlocked(gen); if (blocked != null)")
    assert fence_problems(discarded, fence) != []
    # the exit removed
    no_exit = _mut(FENCED, "rep.Append(\"x;y\").Append(blocked); yield break; }", "rep.Append(\"x;y\").Append(blocked); }")
    assert fence_problems(no_exit, fence) != []
    # the exit not last, the polarity reversed, another variable tested, an else branch
    assert fence_problems(_mut(FENCED, "Append(blocked); yield break; }", "Append(blocked); yield break; Work(); }"), fence) != []
    assert fence_problems(_mut(FENCED, "(blocked = DevLeverBlocked(gen)) != null", "(blocked = DevLeverBlocked(gen)) == null"), fence) != []
    assert fence_problems(_mut(FENCED, "if (first != null)", "if (blocked != null)"), fence) != []
    assert fence_problems(_mut(FENCED, "yield break; }\n            Work();", "yield break; } else { Other(); }\n            Work();"), fence) != []
    # a statement between the yield and the fence, and a yield with nothing after it
    assert fence_problems(_mut(FENCED, "            _renderClaim.Beat(gen, DEV_BUDGET);\n            if ((blocked",
                               "            _renderClaim.Beat(gen, DEV_BUDGET);\n            Mutate();\n            if ((blocked"), fence) != []
    assert fence_problems("IEnumerator R() { for (;;) { yield return null; } }", fence) != []
    # another predicate
    assert fence_problems(_mut(FENCED, "DevLeverBlocked(gen)", "GradeLeverBlocked()"), fence) != []
    # a beat that is not the run's own heartbeat is a statement like any other
    for beat in ("_renderClaim.Beat(0, DEV_BUDGET);", "_renderClaim.Beat(gen + 1, DEV_BUDGET);", "_renderClaim.Beat(gen, 1e9f);"):
        other = _mut(FENCED, "            _renderClaim.Beat(gen, DEV_BUDGET);\n            if ((blocked",
                     "            " + beat + "\n            if ((blocked")
        assert any("not a fenced exit" in x for x in fence_problems(other, fence)), beat


DISPATCH = """
void DevRun(string spec) {
    if (busy) { return; }
    string blocked = DevLeverBlocked(0);
    if (blocked != null) { Log("refused"); return; }
    if (spec == "upload") { StartProduct("lever", true, true); return; }
    Plugin.Instance.StartCoroutine(Run(spec));
}
"""


def test_dominating_exit_reader_negative_controls():
    targets = ("StartProduct(", "StartCoroutine(")
    assert dominating_exit(DISPATCH, "blocked != null", "return;", targets) == []
    moved = _mut(_mut(DISPATCH, '    if (spec == "upload") { StartProduct("lever", true, true); return; }\n', ""),
                 "    string blocked", '    if (spec == "upload") { StartProduct("lever", true, true); return; }\n    string blocked')
    assert any("occurs before" in x for x in dominating_exit(moved, "blocked != null", "return;", targets))
    nested = _mut(DISPATCH, '    if (blocked != null) { Log("refused"); return; }', '    if (other) { if (blocked != null) { Log("refused"); return; } }')
    assert any("not a top-level statement" in x for x in dominating_exit(nested, "blocked != null", "return;", targets))
    no_exit = _mut(DISPATCH, 'Log("refused"); return; }', 'Log("refused"); }')
    assert any("does not end with" in x for x in dominating_exit(no_exit, "blocked != null", "return;", targets))


def test_statement_reader_handles_the_shapes_the_sources_use():
    m = mask_code("{ try { a(); } catch (E e) { b(); } finally { c(); } do { d(); } while (x); "
                  "if (p) q(); else if (r) { s(); } else t(); f((u) => { v(); }); }")
    top = statements(m, 1, len(m) - 1)
    got = [_norm(m[a:b]) for a, b in top]
    assert len(got) == 4 and got[0].startswith("try") and got[1].startswith("do") and got[2].startswith("if") and got[3].startswith("f(")
    assert [(k, _norm(m[h[0]:h[1]]) if h else None) for k, h, _ in slots(m, top[0])] == [("try", None), ("catch", "E e"), ("finally", None)]
    assert [k for k, _, _ in slots(m, top[1])] == ["do"]
    assert [k for k, _, _ in slots(m, top[2])] == ["if", "else"]
    assert slots(m, top[3]) == []
    _, else_stmts = clause(m, top[2], "else")
    assert [k for k, _, _ in slots(m, else_stmts[0])] == ["if", "else"]


RUNS = """
void M() {
    a();
    if (x) { b(); c(); }
    b();
    d();
}
"""
OWNS = ('var a = Own(new Material(s)); var b = Own(x ? new Material(s) : null); var c = new Material(s); '
        'var d = Own( new Texture2D(1, 1) ); var e = Owner(new Mesh()); var f = g.Own(new Mesh()); '
        'var h = Own(new GameObject("x")).transform; var i = Own(UnityEngine.Object.Instantiate<Material>(s)); '
        'var j = Own(new Material(s) ?? m); var k = Own(Wrap(new Material(s)));')


def test_run_body_leaf_and_owner_readers_negative_controls():
    # a run of the body's own list and of a nested one; a run split across
    # lists, found twice, or nested when the body's own list is asked for
    assert run_problems("top", RUNS, ["b();", "d();"], top=True) == []
    assert run_problems("nested", RUNS, ["b();", "c();"]) == []
    assert "found 0" in run_problems("split", RUNS, ["a();", "b();"])[0]
    assert "found 2" in run_problems("twice", _mut(RUNS, "d();", "c();"), ["b();", "c();"])[0]
    assert "found 0" in run_problems("top only", RUNS, ["b();", "c();"], top=True)[0]
    # the innermost statement holding an offset: a nested one, and the if whose head holds it
    m, code = mask_code(RUNS), strip_comments_only(RUNS)
    stmts, idx = list_position(m, m.index("c();"))
    assert leaf_code(m, code, m.index("c();")) == "c();" and _texts(code, stmts) == ["b();", "c();"] and idx == 1
    assert leaf_code(m, code, m.index("(x)") + 1) == "if (x) { b(); c(); }" and list_position(m, m.index("(x)") + 1)[1] == 1
    # a pinned body that matches whatever its whitespace and comments, one that
    # differs, and a masked block in which a commented-out statement is not code
    noted = {"k": _mut(RUNS, "    d();\n", "    // b();\n    d(); /* b(); */\n")}
    assert body_problems(noted, {("k", "void M()"): "{ a(); if (x) { b(); c(); } b(); d(); }"}) == []
    assert body_problems(noted, {("k", "void M()"): "{ a(); if (x) { b(); } b(); d(); }"}) != []
    assert len(re.findall(r"\bb\(\);", _masked_block(noted["k"], "void M()"))) == 2
    # the made object is the whole argument of Own(...): not under a ternary, not
    # a bare make, not a call named Owner or a member named Own, not followed by
    # more of the argument, not wrapped in another call
    om = mask_code(OWNS)
    assert [_owned(om, h) for h in GRADE_MAKES.finditer(om)] == [True, False, False, True, False, False, True, True, False, False]


PATHS = """
byte[] F(Camera cam, byte[] lut) {
    lit = 0f;
    try
    {
        var o = Read(cam);
        Grade(o, lut);
        pixels = o;
        return Encode(o);
    }
    catch (Exception ex) { Log(ex); return null; }
}
"""


def _grade_offset(text: str) -> int:
    at = mask_code(text).find("Grade(o, lut)")
    assert at >= 0
    return at


def test_path_reader_negative_controls():
    assert unconditional_problems(PATHS, _grade_offset(PATHS)) == []
    shapes = {
        "if (lut != null) Grade(o, lut);": "under if (lut != null)",
        "if (lut == null) { } else Grade(o, lut);": "under else",
        "if (lut == null) { } else { Grade(o, lut); }": "under else",
        "for (int i = 0; i < 1; i++) Grade(o, lut);": "under for",
        "while (o == null) { Grade(o, lut); }": "under while",
        "Run(() => Grade(o, lut));": "within",
        "var ok = lut != null && Grade(o, lut);": "within",
        "var q = lut == null ? null : Grade(o, lut);": "within",
    }
    for shape, want in shapes.items():
        text = _mut(PATHS, "        Grade(o, lut);", "        " + shape)
        assert any(want in x for x in unconditional_problems(text, _grade_offset(text))), shape
    # an exit before it, in its own list or an enclosing one
    for early in ("        if (o == null) return null;\n", "        if (o == null) { Log(o); throw new X(); }\n",
                  "        var q = o ?? throw new X();\n", "        if (o == null) { break; }\n"):
        text = _mut(PATHS, "        Grade(o, lut);", early + "        Grade(o, lut);")
        assert any("after an exit" in x for x in unconditional_problems(text, _grade_offset(text))), early
    outer = _mut(PATHS, "    lit = 0f;\n", "    lit = 0f;\n    if (cam == null) return null;\n")
    assert any("after an exit" in x for x in unconditional_problems(outer, _grade_offset(outer)))
    assert unconditional_problems(outer, _grade_offset(outer), allowed_exits=("if (cam == null) return null;",)) == []
    # exits a nested loop owns, a lambda's return, and the plain clauses are not problems
    for fine in ("        foreach (var x in xs) { if (x) break; if (!x) continue; }\n        Grade(o, lut);",
                 "        Func<int> f = () => { return 1; };\n        Grade(o, lut);",
                 "        using (var s = Open()) { Grade(o, lut); }",
                 "        lock (gate) { { Grade(o, lut); } }"):
        text = _mut(PATHS, "        Grade(o, lut);", fine)
        assert unconditional_problems(text, _grade_offset(text)) == [], fine
    # the catch is a clause of its own
    caught = _mut(PATHS, "{ Log(ex); return null; }", "{ Log(ex); Grade(o, lut); return null; }")
    m = mask_code(caught)
    assert any("under catch (Exception ex)" in x for x in unconditional_problems(caught, m.rfind("Grade(o, lut)")))
    assert path_conditions(m, strip_comments_only(caught), m.rfind("Grade(o, lut)")) == ["catch (Exception ex)"]


REFUSALS = """
string Why(int gen) {
    if (gen < 0) return "negative gen " + gen;
    if (gen == 0) return Name(gen) + " is zero";
    Func<string> f = () => { return null; };
    foreach (var x in xs) if (x == gen) return $"seen {gen}";
    return null;
}
"""


def test_refusal_return_reader_negative_controls():
    assert refusal_return_problems(REFUSALS) == []
    for bad in ("return (string)null;", "return default(string);", "return why;", "return gen < -5 ? \"far\" : null;",
                "return null;", "return 'x' + gen;"):
        text = _mut(REFUSALS, 'return "negative gen " + gen;', bad)
        assert refusal_return_problems(text) != [], bad
    assert refusal_return_problems(_mut(REFUSALS, "    return null;\n}", "    return \"done\";\n}")) != []
    assert refusal_return_problems(_mut(REFUSALS, 'return Name(gen) + " is zero";', "return Name(gen);"),
                                   allowed=("return Name(gen);",)) == []


# ── the real source: the upload and the grade table ─────────────────────────

UPLOAD = "private static void Upload(string key, string descriptor, byte[] png, string why)"
PRODUCT_RUN = "private static IEnumerator ProductRun(string why, bool upload, int gen, bool lever)"
RUN = "private static IEnumerator Run(string spec, int gen)"
LOAD_GRADE = "private static void LoadGrade()"
FINISH_BAKE = "private static string FinishBake(GradeSource src, RenderTexture rtG, RenderTexture rtR, StringBuilder rep, bool negativeControl)"
GRADE_BAKE_RUN = "private static IEnumerator GradeBakeRun(string spec, int gen)"
GRADE_SWATCH_RUN = "private static IEnumerator GradeSwatchRun(string spec, int gen)"
GRADE_PIXELS = "internal static void GradePixels(Color32[] px, byte[] lut)"
MATTE_BYTES = "private static byte[] MatteBytes(Camera cam, int size, byte[] lut, out float lit, out float partial, out Color32[] pixels)"
DEV_RUN = "internal static void DevRun(string spec)"
LEVER_BLOCKED = "internal static string DevLeverBlocked(int gen)"
RUN_ENDED = "private static string RunEnded(int gen, bool lever)"
START = "private static bool Start(string why, bool upload)"
START_PRODUCT = "private static bool StartProduct(string why, bool upload, bool lever)"
TICK = "internal static void Tick()"
PIN_PARTICLES = "private static ParticlePin PinParticles(StringBuilder rep, ParticlePlan plan, float simSecs, int salt, bool detail)"
PLAN_PARTICLES = "private static ParticlePlan PlanParticles(bool all)"
PLAN_VISIT = "private static bool PlanVisit("
PIN_FREE_ARMS = "private static void PinFreeArms(ref GunPin g)"
HOLD_GUN = "private static bool HoldGun()"
PIN_FRAMES = "private static FramePin PinFrames()"
TEARDOWN = "private static void Teardown(StringBuilder rep)"
FORCE_ABORT = "private static void ForceAbort(string why)"
ON_HOST_DESTROYED = "internal static void OnHostDestroyed(MonoBehaviour host)"
ON_SCENE_UNLOADED = "private static void OnSceneUnloaded(Scene scene)"
ENSURE_SCENE_HOOK = "private static void EnsureSceneHook()"
RECLAIM = "private static void Reclaim()"
RIG_LOST = "private static bool RigLost()"
GONE = "private static bool Gone(UnityEngine.Object o)"
CLAIM = "private sealed class Claim"
SWEEP_REFUSAL = "private static string SweepRefusal(int size, List<int> lengths, List<int> salts)"
SWEEP_ENTRY = "private static void SweepEntry("
BODY_LUMINANCE = "private static double BodyLuminance(Color32[] px, MeasureBuffers buf, out int bodyPx, out float cx, out float cyTop)"
PARSE_MILLIS = "private static List<int> ParseMillis(string list, int minMs, int maxMs, int cap, StringBuilder rep)"
PARSE_INTS = "private static List<int> ParseInts(string list, int min, int max, int cap, StringBuilder rep)"
SECS_OF_MS = "private static string SecsOfMs(int ms)"
COLOUR_READY = "private static bool ColourReady(string hex, int token)"
APPLY_COLOR_EXACT = "private static int ApplyColorExact(StringBuilder rep, GameObject clone, string sku, string hex)"
EFFECT_READY = "private static bool EffectReady(string sku, GameObject aura, GameObject clone)"
APPLY_EFFECT = "private static GameObject ApplyEffect(StringBuilder rep, GameObject clone, string overrideSku, out string sku)"
APPLY_EFFECT_EXACT = "private static GameObject ApplyEffectExact(StringBuilder rep, GameObject clone, string sku)"
REGISTERED_AURA = "private static GameObject RegisteredAura(int actor)"
DESTROY_GRADE_OBJECTS = "private static void DestroyGradeObjects()"
START_LIGHT_PROBE = "private static void StartLightProbe()"
STOP_LIGHT_PROBE = "private static void StopLightProbe()"
FRAME_READY = "internal static bool PortraitFrameReady(int actor, int token)"
APPLY_FOR_PORTRAIT = "internal static int ApplyForPortrait(Transform rigRoot, int actor, string sku, string colorHex)"
APPLY_TO_PLAYER = "private static void ApplyToPlayer(Transform playerRoot, int actor, string sku, string colorHex)"
EFFECT_APPLY_TO_PLAYER = "private static void ApplyToPlayer(Transform playerRoot, int actor, string sku)"
WRITE_FRAME = "private static int WriteFrame(AnimState st, float now)"
ENSURE_ANIM_LOOP = "private static void EnsureAnimLoop(string why)"
STOP_ANIM_LOOP = "private static void StopAnimLoop()"
ANIM_TICK_LOOP = "private static IEnumerator AnimTickLoop(int gen)"
ON_HOST_RESPAWNED = "internal static void OnHostRespawned()"
ON_DESTROY = "private void OnDestroy()"
RIG_ROOTS = "private static IEnumerable<GameObject> RigRoots()"
PARTICLE_SEED = "private static uint ParticleSeed(string path, int salt)"
RIG_PATH = "private static string RigPath(Transform t)"
FNV32 = "private static uint Fnv32(byte[] d, uint h = 2166136261u)"
PIN_GUN_SPRINGS = "private static void PinGunSprings(ref GunPin g)"
PARTICLE_WATCH = "private sealed class ParticleWatch"
ENCODE_PNG = "private static byte[] EncodePng(Color32[] px, int size)"
RENDERING = "private static bool Rendering"
UPLOAD_IN_FLIGHT = "internal static bool UploadInFlight"
BUILD_RIG = "private static string BuildRig(StringBuilder rep, out GameObject clone, out CharacterData data, bool pinLegs = true)"
AFTER_ACTIVATE = "private static bool AfterActivate(StringBuilder rep, GameObject clone, CharacterData data, PlayerFace captured, string faceOverride)"
MAKE_GROUND = "private static void MakeGround(StringBuilder rep, GameObject clone)"
MAKE_CAMERA = "private static Camera MakeCamera(Bounds fit, int size)"
SWAP_UNLIT = "private static void SwapUnlit(StringBuilder rep, GameObject clone)"
OWN = "private static T Own<T>(T o) where T : UnityEngine.Object"
GRADE_TABLE = "private static byte[] GradeTable"
GRADE_BAKED = "internal static bool GradeBaked"
LUT_SAMPLE = "internal static void LutSample(byte[] lut, int r, int g, int b, out byte ro, out byte go, out byte bo)"
TRI = "private static byte Tri(byte[] lut, int i, int wr, int wg, int wb)"
BUILD_LUT_LO = "private static byte[] BuildLutLo()"
BUILD_LUT_W = "private static short[] BuildLutW()"
GRADE_DIGEST = "internal static uint GradeDigest(byte[] table, string key)"
READ_TARGET = "private static Color32[] ReadTarget(RenderTexture rt, int w, int h)"
ENCODE_PNG_WH = "private static byte[] EncodePngWH(Color32[] px, int w, int h)"
MEASURE_SWATCHES = "private static string MeasureSwatches(Vector2[] centres, byte[] table, string tableName, StringBuilder rep)"
APPLY_OR_DEFER = "private static bool ApplyOrDefer(Transform playerRoot, int actor, string sku, string colorHex)"
APPLY_WHEN_ACTIVE = "private static IEnumerator ApplyWhenActive(Transform playerRoot, int actor, string sku, string colorHex, int gen)"
DROP_PENDING = "private static void DropPending(int actor, int gen)"
PENDING_APPLY = "private struct PendingApply"


def _masked_norm(source, signature: str) -> str:
    return _norm(mask_code(cs_block(source, signature)))


def _code_norm(source, signature: str) -> str:
    return _norm(strip_comments_only(cs_block(source, signature)))


def call_texts(block: str, name: str) -> list:
    """Every call of `name` in `block` (code only), from the name to its
    balanced closing parenthesis, whitespace normalised."""
    masked = mask_code(block)
    return [_norm(masked[m.start():_close(masked, m.end() - 1, "(", ")")])
            for m in re.finditer(r"\b" + re.escape(name) + r"\s*\(", masked)]


def _return_terms(block: str) -> list:
    """The `&&` terms of a method whose body is exactly one return statement."""
    ret = _norm(strip_comments_only(block)).strip("{} ")
    assert ret.startswith("return ") and ret.endswith(";"), ret
    return and_terms(ret[len("return "):-1])


def _sources() -> dict:
    return {"render": RENDER_CS.read_text(encoding="utf-8"), "grade": GRADE_CS.read_text(encoding="utf-8"),
            "color": COLOR_CS.read_text(encoding="utf-8"), "effect": EFFECT_CS.read_text(encoding="utf-8"),
            "plugin": PLUGIN_CS.read_text(encoding="utf-8")}


def body_problems(sources: dict, bodies: dict) -> list:
    """Each (source key, signature) block, comments stripped and whitespace
    normalised, against its pinned text."""
    problems = []
    for (key, sig), want in bodies.items():
        got = _norm(strip_comments_only(cs_block(sources[key], sig)))
        if got != _norm(want):
            problems.append(f"{sig}: {got[:200]!r}")
    return problems


def body_controls_problems(sources: dict, bodies: dict, controls) -> list:
    """Each control (source key, signature, old, new) mutates its own block:
    the pin of that block must then report it. Returns the controls that
    went unreported."""
    missed = []
    for key, sig, old, new in controls:
        mutated = dict(sources, **{key: _mut(sources[key], old, new)})
        if not any(sig in x for x in body_problems(mutated, {(key, sig): bodies[(key, sig)]})):
            missed.append((sig, new))
    return missed


def run_problems(where: str, block: str, want: list, top: bool = False) -> list:
    """`want` (statement texts) is a run of consecutive statements of one
    statement list of `block` -- of the method body's own list when `top` --
    and occurs as such exactly once."""
    m, code = mask_code(block), strip_comments_only(block)
    body = inner(m, body_span(m))
    lists = [body]
    if not top:
        lists = []

        def walk(stmts):
            lists.append(stmts)
            for s in stmts:
                for _, _, clause_body in slots(m, s):
                    walk(inner(m, clause_body))
        walk(body)
    want = [_norm(w) for w in want]
    hits = 0
    for stmts in lists:
        texts = _texts(code, stmts)
        hits += sum(1 for i in range(len(texts) - len(want) + 1) if texts[i:i + len(want)] == want)
    if hits != 1:
        return [f"{where}: want {want[0][:70]!r} .. {want[-1][:50]!r} as {len(want)} statements in a row once, found {hits}"]
    return []


def test_upload_is_gated_on_the_baked_table():
    block = cs_block(RENDER_CS, UPLOAD)
    assert exits_before(block, "!GradeBaked", "return;", UPLOAD_CALL) == []
    # negative control: the gate asked only on some uploads
    some = _mut(block, "if (!GradeBaked)", "if (why != \"retry\") if (!GradeBaked)")
    assert any("is not a statement of a list" in x for x in exits_before(some, "!GradeBaked", "return;", UPLOAD_CALL))


LOAD_GRADE_MEMO = "if (_gradeLut != null) return;"
# LoadGrade's settle, as consecutive statements of its own body in this order:
# the flag and the table both read the one `t`, and the table falls back to
# IdentityTable() exactly when the flag is false. A log block follows it.
LOAD_GRADE_CLOSE = ["_gradeBaked = t != null;", "_gradeLut = t ?? IdentityTable();", "_gradeState = why;"]
# Every line of LoadGrade that mentions `t` in code, once per mention: declared
# null, decoded from the compiled string, measured, digested, nulled by a failed
# acceptance term or by the catch, and read by the settle. GradeDigest and
# Fnv32 (both pinned) read the table without writing it.
LOAD_GRADE_T_LINES = (
    ["byte[] t = null;", "t = Convert.FromBase64String(GRADE_LUT_B64);"]
    + ['if (t.Length != LUT_BYTES) { why = "invalid: " + t.Length + " bytes"; t = null; }'] * 3
    + ["uint h = GradeDigest(t, GRADE_BAKED_FROM);",
       'if (h != GRADE_LUT_FNV) { why = "invalid: digest " + h.ToString("x8") + " != " + GRADE_LUT_FNV.ToString("x8"); t = null; }',
       'else if (GRADE_BAKED_FROM.Length == 0) { why = "invalid: no baked-from key"; t = null; }',
       'else if (h != RECIPE_GRADE_FNV) { why = "invalid: table " + h.ToString("x8") + " is not the one RECIPE " + RECIPE + " names (" '
       '+ RECIPE_GRADE_FNV.ToString("x8") + ")"; t = null; }',
       'else if (GRADE_TABLE_MARKER != MarkerBaked()) { why = "invalid: the marker still says placeholder"; t = null; }',
       'catch (Exception ex) { why = "invalid: " + ex.Message; t = null; }',
       "_gradeBaked = t != null;", "_gradeLut = t ?? IdentityTable();"])
# Every mention, in code or in a string, of the grade's settled state and of the
# lookup's per-byte arrays in the renderer's two files -- the table, the flag,
# the state, the table's getter, s_lutLo and s_lutW -- as (source key, the
# mention's line), once per mention: the fields' declarations, LoadGrade's
# memo, settle and log, the two getters and GradeTag, the product capture, the
# dev table's copy and LutSample's reads. Only the lines are checked here, not
# where they sit: the settle's run, the product capture's check and the pinned
# getters and LutSample hold where those sit.
GRADE_STATE_MENTIONS = {
    "_gradeLut": [("grade", "private static byte[] _gradeLut;"), ("grade", LOAD_GRADE_MEMO), ("grade", "_gradeLut = t ?? IdentityTable();"),
                  ("grade", "private static byte[] GradeTable { get { LoadGrade(); return _gradeLut; } }")],
    "_gradeBaked": [("grade", "private static bool _gradeBaked;"), ("grade", "_gradeBaked = t != null;"),
                    ("grade", "if (!_gradeBaked && GRADE_LUT_B64.Length > 0) Plugin.Log.LogWarning(line);"),
                    ("grade", "internal static bool GradeBaked { get { LoadGrade(); return _gradeBaked; } }")],
    "_gradeState": [("grade", 'private static string _gradeState = "";'), ("grade", "_gradeState = why;"),
                    ("grade", "private static string GradeTag() { LoadGrade(); return _gradeState; }")],
    "GradeTable": [("grade", "private static byte[] GradeTable { get { LoadGrade(); return _gradeLut; } }"),
                   ("grade", "t = (byte[])GradeTable.Clone();"),
                   ("render", "matte = MatteBytes(cam, DEFAULT_SIZE, GradeTable, out lit, out partial, out px);")],
    "s_lutLo": [("grade", "private static readonly byte[] s_lutLo = BuildLutLo();")]
               + [("grade", "int o = ((s_lutLo[r] * LUT_N + s_lutLo[g]) * LUT_N + s_lutLo[b]) * 3;")] * 3,
    "s_lutW": [("grade", "private static readonly short[] s_lutW = BuildLutW();")]
              + [("grade", "int wr = s_lutW[r], wg = s_lutW[g], wb = s_lutW[b];")] * 3,
}


def load_grade_problems(block: str) -> list:
    """Every acceptance term nulls the table, and `_gradeBaked` is assigned
    once, on every path through LoadGrade but the memo's exit, after every
    one of them; the flag, the table and the state are set by consecutive
    statements of LoadGrade's own body, and `t` is mentioned only on the
    lines of LOAD_GRADE_T_LINES."""
    problems = []
    masked = mask_code(block)
    code = strip_comments_only(block)
    assign = "_gradeBaked = t != null;"
    hits = [m.start() for m in re.finditer(re.escape(assign), masked)]
    if len(hits) != 1:
        return [f"want one {assign!r}, found {len(hits)}"]
    at = hits[0]
    problems += [f"{assign!r} is conditional: {p}" for p in unconditional_problems(block, at, allowed_exits=(LOAD_GRADE_MEMO,))]
    for cond in ("t.Length != LUT_BYTES", "h != GRADE_LUT_FNV", "GRADE_BAKED_FROM.Length == 0",
                 "h != RECIPE_GRADE_FNV", "GRADE_TABLE_MARKER != MarkerBaked()"):
        guards = find_guards(block, cond)
        if len(guards) != 1:
            problems.append(f"want one `if ({cond})`, found {len(guards)}")
            continue
        if "t = null;" not in guards[0][1]:
            problems.append(f"`if ({cond})` does not null the table")
        if guards[0][0] > at:
            problems.append(f"`if ({cond})` comes after {assign!r}")
    problems += run_problems("LoadGrade's settle", block, LOAD_GRADE_CLOSE, top=True)
    lines = [_line_at(code, w.start()) for w in re.finditer(r"(?<![\w.])t\b", masked)]
    if sorted(lines) != sorted(LOAD_GRADE_T_LINES):
        problems.append(f"the table is mentioned by {lines!r}, want {LOAD_GRADE_T_LINES!r}")
    return problems


def _line_at(code: str, offset: int) -> str:
    """The normalised line of `code` that holds `offset`."""
    a, b = code.rfind("\n", 0, offset) + 1, code.find("\n", offset)
    return _norm(code[a:b if b >= 0 else len(code)])


def mention_problems(mentions: dict, sources: dict, others: dict) -> list:
    """Every mention of a `mentions` name, in code or in a string, in `sources`
    is exactly its list of (source key, line), and no file in `others` (file
    name to text) mentions one outside a comment. A write, an element write, a
    reference handed on and a reflection lookup that spells the name out are
    each a mention; reflection that does not spell the name out is not seen by
    this check."""
    problems = []
    for name, want in mentions.items():
        word = rf"(?<!\w){re.escape(name)}(?!\w)"
        found = []
        for key, text in sources.items():
            code = strip_comments_only(text)
            found += [(key, _line_at(code, w.start())) for w in re.finditer(word, code)]
        if sorted(found) != sorted(want):
            problems.append(f"{name} is mentioned by {found!r}, want {want!r}")
        problems += [f"{other} mentions {name}" for other, text in others.items()
                     if re.search(word, text) and re.search(word, strip_comments_only(text))]
    return problems


def test_load_grade_keeps_every_acceptance_term_before_the_baked_flag():
    block = cs_block(GRADE_CS, LOAD_GRADE)
    assert load_grade_problems(block) == []
    # negative control: the flag assigned before the table is validated
    early = _mut(block, "            _gradeBaked = t != null;\n", "")
    early = _mut(early, "            byte[] t = null;\n", "            byte[] t = null;\n            _gradeBaked = t != null;\n", 1)
    assert any("comes after" in x for x in load_grade_problems(early))
    # negative controls: the flag assigned under a condition, in an else, after another exit
    for shape in ("if (why != null) { _gradeBaked = t != null; }", "if (why == null) { } else _gradeBaked = t != null;"):
        cond = _mut(block, "            _gradeBaked = t != null;\n", "            " + shape + "\n")
        assert any("conditional" in x for x in load_grade_problems(cond)), shape
    exited = _mut(block, "            _gradeBaked = t != null;\n", "            if (t == null) return;\n            _gradeBaked = t != null;\n")
    assert any("after an exit" in x for x in load_grade_problems(exited))
    # negative controls: the table always the identity (N08), the table kept
    # from before the flag, the state not recorded, a rejected table replaced
    # by the identity before the flag (N09), a table decoded from elsewhere,
    # coalesced, refilled by ref, written in place or handed to a method
    assert any("LoadGrade's settle" in x for x in load_grade_problems(_mut(block, "_gradeLut = t ?? IdentityTable();", "_gradeLut = IdentityTable();")))
    assert any("LoadGrade's settle" in x for x in load_grade_problems(_mut(block, "            _gradeState = why;\n", "")))
    swapped = _mut(_mut(block, "            _gradeLut = t ?? IdentityTable();\n", ""), "            byte[] t = null;\n",
                   "            byte[] t = null;\n            _gradeLut = t ?? IdentityTable();\n")
    assert any("LoadGrade's settle" in x for x in load_grade_problems(swapped))
    identity = _mut(block, "            _gradeBaked = t != null;\n", "            if (t == null) t = IdentityTable();\n            _gradeBaked = t != null;\n")
    assert any("t = IdentityTable();" in x for x in load_grade_problems(identity))
    for other in ("t = Convert.FromBase64String(GRADE_BAKED_FROM);", "t ??= IdentityTable();", "Refill(ref t);", "t[0] ^= 1;", "Patch(t);"):
        wrote = _mut(block, "            _gradeBaked = t != null;\n", "            " + other + "\n            _gradeBaked = t != null;\n")
        assert any("the table is mentioned by" in x and other in x for x in load_grade_problems(wrote)), other
    # the mentions of the grade's settled state and of the lookup's arrays:
    # exactly GRADE_STATE_MENTIONS in the two files, and none outside a comment
    # in any other plugin file
    sources = {"render": RENDER_CS.read_text(encoding="utf-8"), "grade": GRADE_CS.read_text(encoding="utf-8")}
    others = {p.name: p.read_text(encoding="utf-8") for p in sorted(PLUGIN.glob("*.cs")) if p.name not in (RENDER_CS.name, GRADE_CS.name)}
    assert mention_problems(GRADE_STATE_MENTIONS, sources, others) == []
    # negative controls: the table replaced after the settle, inside LoadGrade;
    # the flag or-ed in a getter; the state's initialiser changed; the table
    # handed out by ref, and the state appended to, from the other file; the
    # table written in place in GradeTag; the dev table no longer a copy; a
    # lookup weight written by a method of its own; the flag and the state set
    # by a deconstruction from the other file
    grade, render = sources["grade"], sources["render"]
    stray = "\n    internal static class StrayGrade { static void Reset() { Refill(ref PortraitRender._gradeLut); PortraitRender._gradeState += \"x\"; } }\n"
    bake = "\n    internal static class StrayBake { static void Set() { (PortraitRender._gradeBaked, PortraitRender._gradeState) = (true, \"\"); } }\n"
    controls = (
        ({"render": render, "grade": _mut(grade, "            _gradeState = why;\n",
                                          "            _gradeState = why;\n            _gradeLut = IdentityTable();\n")}, "_gradeLut"),
        ({"render": render, "grade": _mut(grade, "{ get { LoadGrade(); return _gradeBaked; } }", "{ get { LoadGrade(); _gradeBaked |= false; return _gradeBaked; } }")},
         "_gradeBaked"),
        ({"render": render, "grade": _mut(grade, 'private static string _gradeState = "";', 'private static string _gradeState = "baked";')}, "_gradeState"),
        ({"render": render + stray, "grade": grade}, "_gradeLut"),
        ({"render": render + stray, "grade": grade}, "_gradeState"),
        ({"render": render, "grade": _mut(grade, "{ LoadGrade(); return _gradeState; }", "{ LoadGrade(); _gradeLut[0] ^= 1; return _gradeState; }")}, "_gradeLut"),
        ({"render": render, "grade": _mut(grade, "t = (byte[])GradeTable.Clone();", "t = GradeTable;")}, "GradeTable"),
        ({"render": render, "grade": _mut(grade, "        private static readonly short[] s_lutW = BuildLutW();\n",
                                          "        private static readonly short[] s_lutW = BuildLutW();\n"
                                          "        private static void StrayWeight() { s_lutW[255] = 256; }\n")}, "s_lutW"),
        ({"render": render + bake, "grade": grade}, "_gradeBaked"),
    )
    for srcs, name in controls:
        assert any(x.startswith(name + " is mentioned by") for x in mention_problems(GRADE_STATE_MENTIONS, srcs, {})), name
    # negative control: the table looked up by name from another plugin file;
    # and a comment in another file is not a mention
    by_name = {"Stray.cs": 'class S { static object T() { return typeof(PortraitRender).GetField("_gradeLut", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null); } }'}
    assert "Stray.cs mentions _gradeLut" in mention_problems(GRADE_STATE_MENTIONS, sources, by_name)
    assert mention_problems(GRADE_STATE_MENTIONS, sources, {"Doc.cs": "// GradeTable is what the capture grades with\nclass D { }\n"}) == []


def test_the_bake_control_returns_before_any_table_is_written():
    block = cs_block(GRADE_CS, FINISH_BAKE)
    assert exits_before(block, "negativeControl", "return", 'TryWrite(rep, "pc_grade_lut', target_in_literal=True) == []
    code = strip_comments_only(block)
    m = mask_code(block)
    passed = code.find("NEGATIVE CONTROL PASSED")
    assert passed >= 0 and code.find("NEGATIVE CONTROL PASSED", passed + 1) < 0
    assert path_conditions(m, code, passed) == ["if (meanDelta < GRADE_MIN_MEAN_DELTA)"]
    assert leaf_code(m, code, passed) == ('return negativeControl ? "NEGATIVE CONTROL PASSED (refused by the grade-ran check: " '
                                          '+ why + ")" : "refused: " + why;')


def test_an_unknown_bake_option_refuses_before_anything_is_deleted():
    block = cs_block(GRADE_CS, GRADE_BAKE_RUN)
    assert exits_before(block, "unknown != null", "yield break;", "if (!ungraded)") == []
    m, code = mask_code(block), strip_comments_only(block)
    delete = m.find("File.Delete(sp)")
    assert delete >= 0 and m.find("File.Delete(", delete + 1) < 0
    assert path_conditions(m, code, delete)[0] == "if (!ungraded)"


# ── the real source: the product capture is graded before it is encoded ─────

PRODUCT_CAPTURE = "matte = MatteBytes(cam, DEFAULT_SIZE, GradeTable, out lit, out partial, out px);"


def capture_flow_problems(product: str, matte: str) -> list:
    """ProductRun captures once, through MatteBytes with the compiled table;
    MatteBytes reads the matte, grades it and encodes it, each exactly once,
    in that order, each on every path through its try (no condition, no
    else, no earlier exit), and writes nothing else into the pixels."""
    problems = []
    pm = _norm(mask_code(product))
    calls = re.findall(r"\bMatteBytes\([^;]*\);", pm)
    if calls != [PRODUCT_CAPTURE[len("matte = "):]] or PRODUCT_CAPTURE not in pm:
        problems.append(f"ProductRun's capture is {calls}")
    mm = mask_code(matte)
    order = []
    for call in ("MattePixels(cam, size, out lit, out partial)", "GradePixels(o, lut);", "return EncodePng(o, size);"):
        hits = [m.start() for m in re.finditer(re.escape(call), mm)]
        if len(hits) != 1:
            problems.append(f"MatteBytes: want one {call!r}, found {len(hits)}")
            continue
        order.append(hits[0])
        problems += [f"MatteBytes: {call!r} {p}" for p in unconditional_problems(matte, hits[0])]
    if len(order) == 3 and order != sorted(order):
        problems.append("MatteBytes does not read, grade and encode in that order")
    if len(re.findall(r"\bGradePixels\(", mm)) != 1 or len(re.findall(r"\bEncodePng\(", mm)) != 1:
        problems.append("MatteBytes grades or encodes more than once")
    if re.search(r"\bo\s*\[", mm):
        problems.append("MatteBytes writes pixels itself")
    return problems


# The chain behind the product's capture, whole: MatteBytes reads, grades and
# encodes one matte; GradeTable is the table LoadGrade settled, and GradeDigest,
# which LoadGrade's acceptance calls, reads that table without writing it;
# GradePixels writes the r, g and b of every pixel whose alpha is not 0 from the
# lookup, and nothing else; LutSample and Tri compute the lookup from the table
# and the per-byte arrays BuildLutLo and BuildLutW fill, writing only their own
# locals and outputs; and EncodePng encodes the pixels it is given as they are.
CAPTURE_CHAIN_BODIES = {
    ("render", MATTE_BYTES): (
        '{ lit = 0f; partial = 0f; pixels = null; try { var o = MattePixels(cam, size, out lit, out partial); GradePixels(o, lut); '
        'pixels = o; return EncodePng(o, size); } catch (Exception ex) { Plugin.Log.LogWarning("[PORTRAIT] matte threw: " + ex.Message); return null; } }'),
    ("render", ENCODE_PNG): (
        "{ Texture2D outTex = null; try { outTex = new Texture2D(size, size, TextureFormat.RGBA32, false); outTex.SetPixels32(px); "
        "outTex.Apply(); return outTex.EncodeToPNG(); } finally { if (outTex != null) UnityEngine.Object.Destroy(outTex); } }"),
    ("grade", GRADE_PIXELS): (
        '{ if (px == null) return; if (lut == null || lut.Length != LUT_BYTES) throw new ArgumentException("grade table must be " + LUT_BYTES + " bytes"); '
        "for (int i = 0; i < px.Length; i++) { if (px[i].a == 0) continue; byte r, g, b; LutSample(lut, px[i].r, px[i].g, px[i].b, out r, out g, out b); "
        "px[i].r = r; px[i].g = g; px[i].b = b; } }"),
    ("grade", GRADE_TABLE): "{ get { LoadGrade(); return _gradeLut; } }",
    ("grade", GRADE_BAKED): "{ get { LoadGrade(); return _gradeBaked; } }",
    ("grade", LUT_SAMPLE): (
        "{ int o = ((s_lutLo[r] * LUT_N + s_lutLo[g]) * LUT_N + s_lutLo[b]) * 3; int wr = s_lutW[r], wg = s_lutW[g], wb = s_lutW[b]; "
        "ro = Tri(lut, o, wr, wg, wb); go = Tri(lut, o + 1, wr, wg, wb); bo = Tri(lut, o + 2, wr, wg, wb); }"),
    ("grade", TRI): (
        "{ const int dB = 3, dG = LUT_N * 3, dR = LUT_N * LUT_N * 3; int c00 = lut[i] * (256 - wb) + lut[i + dB] * wb; "
        "int c01 = lut[i + dG] * (256 - wb) + lut[i + dG + dB] * wb; int c10 = lut[i + dR] * (256 - wb) + lut[i + dR + dB] * wb; "
        "int c11 = lut[i + dR + dG] * (256 - wb) + lut[i + dR + dG + dB] * wb; int c0 = c00 * (256 - wg) + c01 * wg; "
        "int c1 = c10 * (256 - wg) + c11 * wg; long v = (long)c0 * (256 - wr) + (long)c1 * wr; return (byte)((v + (1L << 23)) >> 24); }"),
    ("grade", BUILD_LUT_LO): "{ var a = new byte[256]; for (int c = 0; c < 256; c++) a[c] = (byte)(c < 240 ? c >> 4 : 15); return a; }",
    ("grade", BUILD_LUT_W): "{ var a = new short[256]; for (int c = 0; c < 256; c++) a[c] = (short)(c < 240 ? (c & 15) * 16 : ((c - 240) * 256 + 7) / 15); return a; }",
    ("grade", GRADE_DIGEST): '{ return Fnv32(Encoding.UTF8.GetBytes(key ?? ""), Fnv32(table)); }',
}


def test_the_product_capture_is_graded_with_the_compiled_table_before_encoding():
    product = cs_block(RENDER_CS, PRODUCT_RUN)
    matte = cs_block(RENDER_CS, MATTE_BYTES)
    assert capture_flow_problems(product, matte) == []
    sources = _sources()
    assert body_problems(sources, CAPTURE_CHAIN_BODIES) == []
    # negative controls on the chain: the grade skipped for every non-empty
    # matte (N07), the lookup's output never written back (N16), alpha forced
    # opaque before the encode (N10), the table getter handing out the
    # identity, the flag read without settling the table, a second capture
    # encoded in place of the graded one, the lookup writing into the table, a
    # weight clamped in Tri, an entry patched in each per-byte array, the digest
    # writing into the table it has read
    assert body_controls_problems(sources, CAPTURE_CHAIN_BODIES, (
        ("grade", GRADE_PIXELS, "            if (px == null) return;\n            if (lut == null",
         "            if (px == null || px.Length > 0) return;\n            if (lut == null"),
        ("grade", GRADE_PIXELS, "LutSample(lut, px[i].r, px[i].g, px[i].b, out r, out g, out b);", "r = px[i].r; g = px[i].g; b = px[i].b;"),
        ("render", ENCODE_PNG, "outTex.SetPixels32(px); outTex.Apply();",
         "for (int i = 0; i < px.Length; i++) px[i].a = 255; outTex.SetPixels32(px); outTex.Apply();"),
        ("grade", GRADE_TABLE, "get { LoadGrade(); return _gradeLut; }", "get { LoadGrade(); return IdentityTable(); }"),
        ("grade", GRADE_BAKED, "get { LoadGrade(); return _gradeBaked; }", "get { return _gradeBaked; }"),
        ("render", MATTE_BYTES, "                return EncodePng(o, size);", "                return EncodePng(MattePixels(cam, size, out lit, out partial), size);"),
        ("grade", LUT_SAMPLE, "bo = Tri(lut, o + 2, wr, wg, wb);", "bo = Tri(lut, o + 2, wr, wg, wb); lut[o] = bo;"),
        ("grade", TRI, "long v = (long)c0 * (256 - wr) + (long)c1 * wr;", "if (wr > 250) wr = 256; long v = (long)c0 * (256 - wr) + (long)c1 * wr;"),
        ("grade", BUILD_LUT_LO, "a[c] = (byte)(c < 240 ? c >> 4 : 15);", "a[c] = (byte)(c < 240 ? c >> 4 : 15); a[255] = 14;"),
        ("grade", BUILD_LUT_W, "a[c] = (short)(c < 240 ? (c & 15) * 16 : ((c - 240) * 256 + 7) / 15);",
         "a[c] = (short)(c < 240 ? (c & 15) * 16 : ((c - 240) * 256 + 7) / 15); a[255] = 256;"),
        ("grade", GRADE_DIGEST, 'return Fnv32(Encoding.UTF8.GetBytes(key ?? ""), Fnv32(table));',
         'var h = Fnv32(Encoding.UTF8.GetBytes(key ?? ""), Fnv32(table)); table[0] ^= 1; return h;'),
    )) == []
    # the table GradePixels refuses to run without
    grade = _masked_norm(GRADE_CS, GRADE_PIXELS)
    assert "if (lut == null || lut.Length != LUT_BYTES) throw new ArgumentException(" in grade
    # negative controls: an ungraded product argument, a removed grade, a
    # conditional grade, a grade in an else (brace-less and braced), a grade
    # after an early return, a grade after the encode
    assert capture_flow_problems(_mut(product, "GradeTable, out lit", "null, out lit"), matte) != []
    assert any("found 0" in x for x in capture_flow_problems(product, _mut(matte, "GradePixels(o, lut);", ";")))
    for shape, want in (("if (lut != null) GradePixels(o, lut);", "under if (lut != null)"),
                        ("if (lut == null) { } else GradePixels(o, lut);", "under else"),
                        ("if (o == null) { } else { GradePixels(o, lut); }", "under else"),
                        ("if (o == null) return null; GradePixels(o, lut);", "after an exit")):
        problems = capture_flow_problems(product, _mut(matte, "GradePixels(o, lut);", shape))
        assert any("GradePixels" in x and want in x for x in problems), (shape, problems)
    moved = _mut(_mut(matte, "                GradePixels(o, lut);", ""),
                 "return EncodePng(o, size);", "var png = EncodePng(o, size); GradePixels(o, lut); return EncodePng(o, size);")
    assert capture_flow_problems(product, moved) != []


PX = r"\bpx\s*\[[^\]]*\]"
WRITE_OP = r"(?:=(?!=)|[-+*/%&|^]=|<<=|>>=|\+\+|--)"


def alpha_write_problems(grade_pixels: str) -> list:
    """GradePixels writes the r, g and b of a pixel and nothing else: never
    alpha (by assignment, compound assignment, increment, decrement or a
    ref/out argument), never a whole Color32, and skips a == 0 pixels."""
    m = _norm(mask_code(grade_pixels))
    problems = []
    members = set(re.findall(PX + r"\s*\.\s*(\w+)\s*" + WRITE_OP, m))
    members |= set(re.findall(r"(?:\+\+|--)\s*" + PX + r"\s*\.\s*(\w+)", m))
    members |= set(re.findall(r"\b(?:ref|out)\s+" + PX + r"\s*\.\s*(\w+)", m))
    if members != {"r", "g", "b"}:
        problems.append(f"GradePixels writes the members {sorted(members)}")
    if (re.search(PX + r"\s*" + WRITE_OP, m) or re.search(r"(?:\+\+|--)\s*" + PX + r"(?!\s*\.)", m)
            or re.search(r"\b(?:ref|out)\s+" + PX + r"(?!\s*\.)", m)):
        problems.append("GradePixels writes a whole pixel")
    if "if (px[i].a == 0) continue;" not in m:
        problems.append("GradePixels does not skip transparent pixels")
    return problems


def test_grading_never_writes_alpha():
    block = cs_block(GRADE_CS, GRADE_PIXELS)
    assert alpha_write_problems(block) == []
    tail = "px[i].r = r; px[i].g = g; px[i].b = b;"
    assert tail in _norm(block)
    for alpha in ("px[i].a = 255;", "px[i].a |= 255;", "px[i].a += 1;", "px[i].a++;", "--px[i].a;", "Touch(ref px[i].a);"):
        wrote = _mut(block, "px[i].b = b;", "px[i].b = b; " + alpha)
        assert any("writes the members" in x and "'a'" in x for x in alpha_write_problems(wrote)), alpha
    for whole in ("px[i] = new Color32(r, g, b, 255);", "Fill(out px[i]);"):
        assert any("whole pixel" in x for x in alpha_write_problems(_mut(block, "px[i].b = b;", "px[i].b = b; " + whole))), whole
    unskipped = _mut(block, "if (px[i].a == 0) continue;", "")
    assert any("transparent" in x for x in alpha_write_problems(unskipped))


# ── the real source: the product render's refusals ──────────────────────────

PRODUCT_REFUSALS = ("!watch.Steady", "!particles.Ok", "!ColourReady(inp.colorHex, colour)", "!EffectReady(inp.effectSku, aura, clone)",
                    "!LegsPlanted(out _legSummary)", "!rig.Pinned(gunStill)")


def product_refusal_problems(block: str) -> list:
    problems = []
    for cond in PRODUCT_REFUSALS:
        problems += [f"{cond}: {p}" for p in exits_before(block, cond, "yield break;", "matte = MatteBytes(")]
    return problems


def test_product_run_refuses_before_the_capture_and_pins_as_the_product():
    block = cs_block(RENDER_CS, PRODUCT_RUN)
    assert product_refusal_problems(block) == []
    masked = mask_code(block)
    norm = _norm(masked)
    assert len(re.findall(r"\bBuildRig\(", masked)) == 1 and "BuildRig(rep, out clone, out data);" in norm
    assert call_texts(block, "PinParticles") == ["PinParticles(rep, PlanParticles(false), PARTICLE_SIM_SECS, 0, false)"]
    assert call_texts(block, "PlanParticles") == ["PlanParticles(false)"]
    assert "var particles = PinParticles(rep, PlanParticles(false), PARTICLE_SIM_SECS, 0, false);" in norm
    assert "int colour = ApplyColorExact(rep, clone, inp.colorSku, inp.colorHex);" in norm
    for dev_only in ("PoseProbe(", "SweepEntry(", "ParticleDetail(", "DEFAULT_SETTLE)", "PlanParticles(true)"):
        assert dev_only not in masked, dev_only
    # no frame passes between the final pins and the capture (a refusal's `yield break` ends the run)
    final_pin = masked.find("var rig = PinRig(rep, true);")
    particles = masked.find("var particles = PinParticles(")
    capture = masked.find("matte = MatteBytes(")
    assert 0 <= final_pin < particles < capture and not re.search(r"\byield\s+return\b", masked[final_pin:capture])
    # negative controls: a refusal nested under a brace-less if, chained as an
    # else-if, placed after the capture, or with its polarity reversed
    nested = _mut(block, "if (!particles.Ok)", "if (lever) if (!particles.Ok)")
    assert any("!particles.Ok" in x and "is not a statement of a list" in x for x in product_refusal_problems(nested))
    chained = _mut(block, "if (!ColourReady(inp.colorHex, colour))", "else if (!ColourReady(inp.colorHex, colour))")
    assert any("ColourReady" in x and "is not a statement of a list" in x for x in product_refusal_problems(chained))
    effect_line = '                if (!EffectReady(inp.effectSku, aura, clone)) { LastResult = "render failed: effect not applied as captured"; yield break; }\n'
    late = _mut(_mut(block, effect_line, ""), "                if (matte == null)", effect_line + "                if (matte == null)")
    assert any("EffectReady" in x and "comes after" in x for x in product_refusal_problems(late))
    flipped = _mut(block, "if (!rig.Pinned(gunStill))", "if (rig.Pinned(gunStill))")
    assert any("rig.Pinned" in x and "found 0" in x for x in product_refusal_problems(flipped))
    unwatched = _mut(block, "if (!watch.Steady)", "if (watch.reads < 0)")
    assert any("watch.Steady" in x and "found 0" in x for x in product_refusal_problems(unwatched))


# ── the real source: the particle watch over the settle ─────────────────────

PARTICLE_WATCH_BODY = (
    "{ private readonly Dictionary<ParticleSystem, int> _first = new Dictionary<ParticleSystem, int>(); "
    "internal int reads, changes; internal string change; "
    "internal bool Steady { get { return reads >= 2 && changes == 0; } } "
    "internal void Read() { reads++; try { var owned = new HashSet<ParticleSystem>(); string diff = null; "
    "foreach (var root in RigRoots()) foreach (var ps in root.GetComponentsInChildren<ParticleSystem>(true)) { "
    "if (ReferenceEquals(ps, null) || ps == null || !owned.Add(ps)) continue; "
    "int state = !ps.gameObject.activeInHierarchy ? 0 : (ps.isStopped && ps.particleCount == 0) ? 1 : 2; int was; "
    "if (reads == 1) _first[ps] = state; "
    'else if (!_first.TryGetValue(ps, out was)) { if (diff == null) diff = "a new system " + PsName(ps); } '
    'else if (was != state) { if (diff == null) diff = PsName(ps) + " " + was + "->" + state; } } '
    'if (reads > 1 && diff == null && owned.Count != _first.Count) diff = "a system is gone"; '
    "if (diff != null) Changed(diff); } "
    'catch (Exception ex) { Changed("threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 80)); } } '
    'private void Changed(string what) { changes++; if (change == null) change = "reading " + reads + ": " + what; } '
    'internal string Summary() { return "reads=" + reads + " systems=" + _first.Count + " changes=" + changes + (change != null ? " first=" + change : ""); } }')
# The product's settle: every frame reads the watch last, after the gun.
PRODUCT_SETTLE = [
    "frames++;",
    "yield return null;",
    "_renderClaim.Beat(gen, RENDER_BUDGET);",
    'if ((ended = RunEnded(gen, lever)) != null) { LastResult = "aborted: " + ended; yield break; }',
    "if (Stale(key)) { Abandon(key); yield break; }",
    "gunStill = HoldGun() ? gunStill + 1 : 0;",
    "watch.Read();",
]
PRODUCT_SETTLE_HEAD = "while (Time.realtimeSinceStartup - ts < DEFAULT_SETTLE || frames < 10)"
# After the settle: the last reading directly before the plan the pin takes,
# and the watch's refusal first among the refusals.
PRODUCT_WATCH_TAIL = [
    "var rig = PinRig(rep, true);",
    "_gunSummary = rig.Summary(gunStill);",
    "watch.Read();",
    "var particles = PinParticles(rep, PlanParticles(false), PARTICLE_SIM_SECS, 0, false);",
    '_particleSummary = particles.Summary() + " watch " + watch.Summary();',
    'if (!watch.Steady) { LastResult = "render failed: particles changed during the settle " + watch.Summary(); yield break; }',
]
RUN_WATCH_TAIL = [
    "watch.Read();",
    r"""rep.Append("particle watch steady=").Append(watch.Steady).Append(' ').Append(watch.Summary()).Append('\n');""",
    "ParticlePlan plan = nopin ? null : PlanParticles(pinall);",
]


def particle_watch_problems(render: str) -> list:
    """The watch reads the plan's liveness inputs as PlanParticles reads them
    (every system under the rig roots, each once, whether it is active and
    whether it is live) and is steady only when at least two readings all
    matched the first. ProductRun creates one before its settle, reads it on
    every settle frame and directly before its plan, and refuses unless it is
    steady. In Run a reading follows the gun, as in the product's settle, and
    the last reading precedes the plan with only its report of the watch
    between."""
    problems = body_problems({"render": render}, {("render", PARTICLE_WATCH): PARTICLE_WATCH_BODY})
    plan = _norm(strip_comments_only(cs_block(render, PLAN_PARTICLES)))
    for shared in ("foreach (var root in RigRoots()) foreach (var ps in root.GetComponentsInChildren<ParticleSystem>(true)) "
                   "if (!ReferenceEquals(ps, null) && ps != null && owned.Add(ps)) inventory.Add(ps);",
                   "if (ps.gameObject.activeInHierarchy) live[ps] = !(ps.isStopped && ps.particleCount == 0);"):
        if shared not in plan:
            problems.append(f"the plan no longer reads the systems as the watch does: {shared[:80]!r}")
    if len(re.findall(r"\bnew\s+ParticleWatch\s*\(", mask_code(render))) != 2:
        problems.append("a ParticleWatch is created other than once by ProductRun and once by Run")
    product = cs_block(render, PRODUCT_RUN)
    pm, pc = mask_code(product), strip_comments_only(product)
    at = pc.find(PRODUCT_SETTLE_HEAD)
    if at < 0 or pc.find(PRODUCT_SETTLE_HEAD, at + 1) >= 0:
        return problems + ["ProductRun's settle loop is not the one pinned"]
    stmts, idx = list_position(pm, at)
    texts = _texts(pc, stmts)
    if idx == 0 or texts[idx - 1] != "var watch = new ParticleWatch();":
        problems.append("ProductRun does not create its watch directly before the settle")
    problems += list_problems("ProductRun's settle", _texts(pc, clause(pm, stmts[idx], "while")[1]), PRODUCT_SETTLE)
    problems += run_problems("ProductRun's last reading", product, PRODUCT_WATCH_TAIL, top=False)
    if len(re.findall(r"\bwatch\s*\.\s*Read\s*\(", pm)) != 2 or len(re.findall(r"\bwatch\s*=(?!=)", pm)) != 1:
        problems.append("ProductRun reads its watch other than in the settle and before the plan, or assigns it twice")
    run = cs_block(render, RUN)
    problems += run_problems("Run's settle reading", run, ["gunStill = HoldGun() ? gunStill + 1 : 0;", "watch.Read();"])
    problems += run_problems("Run's last reading", run, RUN_WATCH_TAIL)
    return problems


def test_the_plan_liveness_inputs_are_watched_over_the_whole_settle():
    render = RENDER_CS.read_text(encoding="utf-8")
    assert particle_watch_problems(render) == []
    product = cs_block(render, PRODUCT_RUN)
    watch = cs_block(render, PARTICLE_WATCH)
    # negative controls: the settle's reading dropped, the last reading moved
    # after the plan, the steady term dropped, liveness read otherwise than
    # the plan reads it, every reading taken as the reference, a new system
    # not counted, the watch recreated after the settle
    settle_read = "                    watch.Read();                                // every settle frame; below, the capture is refused unless every reading matched the first\n"
    controls = (
        (lambda r: r.replace(product, _mut(product, settle_read, "")), "ProductRun's settle"),
        (lambda r: r.replace(product, _mut(_mut(product, "                watch.Read();\n                var particles", "                var particles"),
                                           "                _particleSummary = particles", "                watch.Read();\n                _particleSummary = particles")),
         "ProductRun's last reading"),
        (lambda r: r.replace(watch, _mut(watch, "return reads >= 2 && changes == 0;", "return reads >= 2;")), PARTICLE_WATCH),
        (lambda r: r.replace(watch, _mut(watch, "(ps.isStopped && ps.particleCount == 0) ? 1 : 2", "ps.isStopped ? 1 : 2")), PARTICLE_WATCH),
        (lambda r: r.replace(watch, _mut(watch, "if (reads == 1) _first[ps] = state;", "if (reads >= 1) _first[ps] = state;")), PARTICLE_WATCH),
        (lambda r: r.replace(watch, _mut(watch, '{ if (diff == null) diff = "a new system " + PsName(ps); }', "{ }")), PARTICLE_WATCH),
        (lambda r: r.replace(product, _mut(product, "                _gunSummary = rig.Summary(gunStill);\n",
                                           "                _gunSummary = rig.Summary(gunStill);\n                watch = new ParticleWatch();\n")),
         "ParticleWatch is created"),
    )
    for mutate, want in controls:
        problems = particle_watch_problems(mutate(render))
        assert any(want in x for x in problems), (want, problems)


def start_problems(render: str) -> list:
    """A product run is started in exactly one place: StartProduct, which
    reclaims before it reads the claim, refuses a busy, in-match, prefab-less
    or identity-less start, and starts ProductRun with its own `lever`."""
    problems = []
    got = _norm(strip_comments_only(cs_block(render, START_PRODUCT)))
    if got != _norm(START_PRODUCT_BODY):
        problems.append(f"StartProduct is {got[:200]!r}")
    masked = mask_code(render)
    if len(re.findall(r"\bProductRun\s*\(", masked)) != 2:
        problems.append("ProductRun is started, or declared, other than once each")
    if _norm(strip_comments_only(cs_block(render, START))) != "{ return StartProduct(why, upload, false); }":
        problems.append("Start does not start a player's run")
    starts = sorted(call_texts(render, "StartProduct"))
    if starts != sorted(["StartProduct(string why, bool upload, bool lever)", "StartProduct( , true, true)",
                         "StartProduct( , false, true)", "StartProduct(why, upload, false)"]):
        problems.append(f"StartProduct is called as {starts}")
    dev = _norm(strip_comments_only(cs_block(render, DEV_RUN)))
    for lever_start in ('StartProduct("lever", true, true);', 'StartProduct("lever-preview", false, true);'):
        if lever_start not in dev:
            problems.append(f"DevRun lacks {lever_start!r}")
    return problems


START_PRODUCT_BODY = (
    '{ EnsureSceneHook(); Reclaim(); if (Rendering || Plugin.Instance == null) return false; '
    'if (GameStateWatcher.IsInMatch) { LastResult = "skipped: in a match"; return false; } '
    'if (PlayerAssigner.instance == null || PlayerAssigner.instance.playerPrefab == null) { LastResult = "skipped: no player prefab yet"; return false; } '
    'if (string.IsNullOrEmpty(MatchTracker.LocalSteamId) || MatchTracker.LocalSteamId == "unknown") { LastResult = "skipped: no identity"; return false; } '
    'int gen = _renderClaim.Take(Plugin.Instance, RENDER_BUDGET); '
    'Plugin.Instance.StartCoroutine(ProductRun(why, upload, gen, lever)); return true; }')

RUN_ENDED_BODY = ('{ if (lever) return DevLeverBlocked(gen); '
                  'if (!_renderClaim.Owns(gen)) return "the run no longer holds its claim (aborted or superseded)"; '
                  'if (RigLost()) return "the rig was destroyed"; return null; }')


def test_every_product_yield_is_fenced_and_a_lever_run_asks_the_lever_predicate():
    block = cs_block(RENDER_CS, PRODUCT_RUN)
    assert len(re.findall(r"\byield\s+return\b", mask_code(block))) == 4
    assert fence_problems(block, "RunEnded(gen, lever)") == []
    ended = cs_block(RENDER_CS, RUN_ENDED)
    assert _norm(strip_comments_only(ended)) == _norm(RUN_ENDED_BODY)
    assert refusal_return_problems(ended, allowed=("return DevLeverBlocked(gen);",)) == []
    render = RENDER_CS.read_text(encoding="utf-8")
    assert start_problems(render) == []
    # negative controls: a lever's run started as a player's, a second start
    # site, and the claim read before the owed cleanup is reclaimed
    assert any("StartProduct is" in x for x in start_problems(_mut(render, "ProductRun(why, upload, gen, lever)", "ProductRun(why, upload, gen, false)")))
    second = _mut(render, "            return StartProduct(why, upload, false);",
                  "            Plugin.Instance.StartCoroutine(ProductRun(why, upload, 0, false));\n            return StartProduct(why, upload, false);")
    assert any("other than once" in x for x in start_problems(second))
    swapped = _mut(render, "            EnsureSceneHook();\n            Reclaim();\n            if (Rendering || Plugin.Instance == null) return false;",
                   "            EnsureSceneHook();\n            if (Rendering || Plugin.Instance == null) return false;\n            Reclaim();")
    assert any("StartProduct is" in x for x in start_problems(swapped))


# ── the real source: the effect readiness ───────────────────────────────────

EFFECT_READY_BODY = (
    "{ if (string.IsNullOrEmpty(sku)) return ReferenceEquals(aura, null); "
    "if (aura == null || clone == null) return false; "
    "if (!ReferenceEquals(RegisteredAura(PORTRAIT_ACTOR), aura)) return false; "
    "if (aura.transform.parent != clone.transform || !aura.activeInHierarchy) return false; "
    "var ps = aura.GetComponent<ParticleSystem>(); "
    "if (ps == null) return false; "
    "foreach (var p in _pinned) if (ReferenceEquals(p.ps, ps)) return true; "
    "return false; }")

APPLY_EFFECT_EXACT_BODY = (
    r'''{ try { if (string.IsNullOrEmpty(sku)) { rep.Append("effect: none equipped\n"); return null; } '''
    r'''var before = RegisteredAura(PORTRAIT_ACTOR); '''
    r'''PlayerEffectCosmetic.ApplyForPortrait(clone.transform, PORTRAIT_ACTOR, sku, false); '''
    r'''var aura = RegisteredAura(PORTRAIT_ACTOR); '''
    r'''if (ReferenceEquals(aura, before)) aura = null; '''
    r'''if (aura != null) aura.transform.localPosition = new Vector3(0f, 0f, 0.6f); '''
    r'''rep.Append("effect applied sku=").Append(sku).Append(" aura=").Append(aura != null).Append('\n'); '''
    r'''return aura; } '''
    r'''catch (Exception ex) { rep.Append("effect threw: ").Append(ex.Message).Append('\n'); return null; } }''')

REGISTERED_AURA_BODY = (
    "{ try { var auras = EFFECT_AURAS != null ? EFFECT_AURAS.GetValue(null) as Dictionary<int, GameObject> : null; "
    "GameObject go; return auras != null && auras.TryGetValue(actor, out go) ? go : null; } catch { return null; } }")


# What builds the aura before ApplyToPlayer registers it: its configuration,
# its renderer and material, and its animation state, each an earlier
# statement of the list that holds the registry write.
AURA_BUILT = ("ConfigureForSku(ps, sku);", "if (psr != null)", "ApplyAnimationState(ps,")


def effect_readiness_problems(render: str, effect: str) -> list:
    """The product refuses a capture whose effect is not the one its apply
    built: EffectReady's terms, ApplyEffectExact's aura (only what this call
    registered), the registry read by reflection on the field
    PlayerEffectCosmetic declares and writes only after an aura is built, and
    ProductRun's refusal after the particle pin and before the capture."""
    problems = []
    for sig, want in ((EFFECT_READY, EFFECT_READY_BODY), (APPLY_EFFECT_EXACT, APPLY_EFFECT_EXACT_BODY),
                      (REGISTERED_AURA, REGISTERED_AURA_BODY)):
        got = _norm(strip_comments_only(cs_block(render, sig)))
        if got != _norm(want):
            problems.append(f"{sig}: {got[:200]!r}")
    code = _norm(strip_comments_only(render))
    reflect = ('private static readonly FieldInfo EFFECT_AURAS = typeof(PlayerEffectCosmetic).GetField("auraByActor", '
               'BindingFlags.NonPublic | BindingFlags.Static);')
    if code.count(reflect) != 1:
        problems.append("the registry is not read from PlayerEffectCosmetic.auraByActor")
    em = mask_code(effect)
    if _norm(em).count("private static readonly Dictionary<int, GameObject> auraByActor = new Dictionary<int, GameObject>();") != 1:
        problems.append("PlayerEffectCosmetic does not declare auraByActor as the registry")
    writes = [x.start() for x in re.finditer(r"\bauraByActor\s*\[[^\]]*\]\s*=(?!=)", em)]
    if re.search(r"\bauraByActor\s*\.\s*(?:Add|TryAdd)\s*\(", em) or len(writes) != 1:
        problems.append(f"the registry is written {len(writes)} times, or added to")
    else:
        apply = cs_block(effect, EFFECT_APPLY_TO_PLAYER)
        am, ac = mask_code(apply), strip_comments_only(apply)
        at = am.find("auraByActor[actor] = go;")
        steps = [am.find(x) for x in AURA_BUILT]
        if at < 0 or min(steps) < 0 or any(am.find(x, s + 1) >= 0 for x, s in zip(AURA_BUILT, steps)):
            problems.append("ApplyToPlayer does not register the aura it built")
        else:
            (lr, ir) = list_position(am, at)
            for x, s in zip(AURA_BUILT, steps):
                (l1, i1) = list_position(am, s)
                if l1 != lr or i1 >= ir:
                    problems.append(f"the registry is written before its aura is built: {x!r} is not an earlier statement of its list")
            if path_conditions(am, ac, at) != []:
                problems.append("the registry is written before its aura is built: the write is conditional")
    product = cs_block(render, PRODUCT_RUN)
    pmask = mask_code(product)
    if call_texts(product, "ApplyEffectExact") != ["ApplyEffectExact(rep, clone, inp.effectSku)"] or \
            "var aura = ApplyEffectExact(rep, clone, inp.effectSku);" not in _norm(pmask):
        problems.append("ProductRun does not keep the aura its apply returned")
    problems += exits_before(product, "!EffectReady(inp.effectSku, aura, clone)", "yield break;", "matte = MatteBytes(")
    guards = find_guards(product, "!EffectReady(inp.effectSku, aura, clone)")
    pin = pmask.find("var particles = PinParticles(")
    if len(guards) == 1 and pin >= 0:
        (l1, i1), (l2, i2) = list_position(pmask, pin), list_position(pmask, guards[0][0])
        if l1 != l2 or i1 >= i2:
            problems.append("EffectReady is asked before the particle pin it reads")
    return problems


def test_the_effect_readiness_fails_closed():
    render = RENDER_CS.read_text(encoding="utf-8")
    effect = EFFECT_CS.read_text(encoding="utf-8")
    assert effect_readiness_problems(render, effect) == []
    run = _norm(strip_comments_only(cs_block(render, RUN)))
    assert "GameObject aura = effect ? ApplyEffect(rep, clone, effectOverride, out effectSku) : null;" in run
    assert 'rep.Append("effect ready=").Append(EffectReady(effectSku, aura, clone))' in run
    assert _norm(strip_comments_only(cs_block(render, APPLY_EFFECT))).endswith("return ApplyEffectExact(rep, clone, sku); }")
    # negative controls: a term removed, the no-effect polarity reversed, the
    # final answer reversed, the aura not the one this call built, the check
    # after the capture or before the pin, the registry misnamed or written
    # before its aura is built
    controls = (
        (lambda r, e: (_mut(r, "if (!ReferenceEquals(RegisteredAura(PORTRAIT_ACTOR), aura)) return false;", ""), e), EFFECT_READY),
        (lambda r, e: (_mut(r, "return ReferenceEquals(aura, null);", "return !ReferenceEquals(aura, null);"), e), EFFECT_READY),
        (lambda r, e: (_mut(r, "if (ReferenceEquals(p.ps, ps)) return true;\n            return false;",
                            "if (ReferenceEquals(p.ps, ps)) return true;\n            return true;"), e), EFFECT_READY),
        (lambda r, e: (_mut(r, "if (ReferenceEquals(aura, before)) aura = null;", ""), e), APPLY_EFFECT_EXACT),
        (lambda r, e: (_mut(r, '"auraByActor"', '"auraMatByActor"'), e), "auraByActor"),
        (lambda r, e: (r, _mut(_mut(e, "                auraByActor[actor] = go;\n", ""),
                               '                var go = new GameObject("cr_effect");\n',
                               '                var go = new GameObject("cr_effect");\n                auraByActor[actor] = go;\n')),
         "before its aura is built"),
        # registered, with its animation state, before it is configured and given its material (N13)
        (lambda r, e: (r, _mut(_mut(e, "                ApplyAnimationState(ps,\n                    Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value);\n"
                                       "                auraByActor[actor] = go;\n", ""),
                               "                ConfigureForSku(ps, sku);\n",
                               "                ApplyAnimationState(ps,\n                    Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value);\n"
                               "                auraByActor[actor] = go;\n                ConfigureForSku(ps, sku);\n")),
         "'ConfigureForSku(ps, sku);' is not an earlier statement"),
        (lambda r, e: (r, _mut(_mut(e, "                auraByActor[actor] = go;\n", ""), "                var psr = go.GetComponent<ParticleSystemRenderer>();\n",
                               "                auraByActor[actor] = go;\n                var psr = go.GetComponent<ParticleSystemRenderer>();\n")),
         "'if (psr != null)' is not an earlier statement"),
        (lambda r, e: (_mut(r, "var aura = ApplyEffectExact(rep, clone, inp.effectSku);", "var aura = (GameObject)null; ApplyEffectExact(rep, clone, inp.effectSku);"), e),
         "keep the aura"),
    )
    for mutate, want in controls:
        r2, e2 = mutate(render, effect)
        assert any(want in x for x in effect_readiness_problems(r2, e2)), want
    line = '                if (!EffectReady(inp.effectSku, aura, clone)) { LastResult = "render failed: effect not applied as captured"; yield break; }\n'
    after = _mut(_mut(render, line, ""), "                if (matte == null) { LastResult = \"render failed: matte\"; yield break; }\n",
                 "                if (matte == null) { LastResult = \"render failed: matte\"; yield break; }\n" + line)
    assert any("comes after" in x for x in effect_readiness_problems(after, effect))
    before = _mut(_mut(render, line, ""), "                var particles = PinParticles(rep, PlanParticles(false), PARTICLE_SIM_SECS, 0, false);\n",
                  line + "                var particles = PinParticles(rep, PlanParticles(false), PARTICLE_SIM_SECS, 0, false);\n")
    assert any("before the particle pin" in x for x in effect_readiness_problems(before, effect))


# ── the real source: the particle pin ───────────────────────────────────────

STEP_LOOP = ("for (int s = 0; s < stepCount; s++) { float dt = s < full ? step : last; "
             "for (int k = 0; k < systems.Length; k++) systems[k].Simulate(dt, false, s == 0, false); r.steps++; }")

PIN_TOP = ["var r = new ParticlePin();", "_pinned.Clear();", "_leftOut.Clear();", "float heldMax = 0f;", "bool held = false;",
           None,
           r"""if (rep != null) rep.Append("particles ").Append(r.Summary()).Append(" secs=").Append(Secs(simSecs)).Append(" salt=").Append(salt).Append('\n');""",
           "return r;"]
PIN_SETUP = ["r.inventory = plan.inventory;", "r.planned = plan.order.Count;", "r.left = plan.left.Count;", "r.dups = plan.dups;",
             "_leftOut.AddRange(plan.left);", "int totalMs = Mathf.RoundToInt(simSecs * 1000f);", None]
PIN_RUN = ["var systems = new ParticleSystem[plan.order.Count];", "var seeds = new uint[plan.order.Count];", None, None]
# Each planned system, once: stopped and cleared before anything is set,
# local space, prewarm off, then the seed (settable only while stopped).
PIN_CONFIGURE = [
    "var p = plan.order[k];",
    "if (p.sub) r.subs++;",
    'if (p.ps == null) { r.failure = "a planned system was destroyed: " + p.path; break; }',
    "systems[k] = p.ps;",
    "seeds[k] = ParticleSeed(p.path, salt);",
    "p.ps.Stop(false, ParticleSystemStopBehavior.StopEmittingAndClear);",
    "var main = p.ps.main;",
    "if (main.simulationSpace != ParticleSystemSimulationSpace.Local) { main.simulationSpace = ParticleSystemSimulationSpace.Local; r.respaced++; }",
    "if (main.prewarm) { main.prewarm = false; r.unprewarmed++; }",
    "p.ps.useAutoRandomSeed = false;",
    "p.ps.randomSeed = seeds[k];",
    "r.pinned++;",
]
PIN_STEPS = [
    "int full = totalMs / PARTICLE_STEP_MS, remMs = totalMs % PARTICLE_STEP_MS;",
    "int stepCount = full + (remMs > 0 ? 1 : 0);",
    "float step = PARTICLE_STEP_MS / 1000f, last = remMs / 1000f;",
    "heldMax = Time.maximumParticleDeltaTime;",
    "held = true;",
    "Time.maximumParticleDeltaTime = PARTICLE_MAX_DELTA;",
    STEP_LOOP,
    None,
]
# Each system paused, then read back; a failed read-back ends the pass
# before the system counts as completed.
PIN_READBACK = [
    "var p = plan.order[k];",
    "systems[k].Pause(false);",
    "var main = systems[k].main;",
    None,
    "p.seed = seeds[k];",
    "_pinned.Add(p);",
    "r.completed++;",
    r"if (detail && rep != null) rep.Append(ParticleDetail(p)).Append('\n');",
]
READBACK_TERMS = ["systems[k].isPlaying", "systems[k].useAutoRandomSeed", "systems[k].randomSeed != seeds[k]",
                  "main.simulationSpace != ParticleSystemSimulationSpace.Local", "main.prewarm"]


def _branch(m: str, code: str, stmt, where: str, cond: str, want: list):
    """Problems with "`stmt` is `if (cond)` whose body is `want`", and its else
    clause's statements (None when there is none)."""
    parts = if_parts(m, stmt)
    if parts is None:
        return [f"{where}: {_norm(code[stmt[0]:stmt[1]])[:80]!r} is not an if"], None
    (ca, cb), body, has_else = parts
    problems = []
    if _norm(code[ca:cb]) != _norm(cond):
        problems.append(f"{where}: the condition is {_norm(code[ca:cb])!r}, want {cond!r}")
    problems += list_problems(where, _texts(code, inner(m, body)), want)
    return problems, (clause(m, stmt, "else")[1] if has_else else None)


def _head(m: str, code: str, stmt, kind: str) -> str:
    head, _ = clause(m, stmt, kind)
    return _norm(code[head[0]:head[1]]) if head else ""


def particle_pin_problems(pin: str) -> list:
    """The pin's statements, level by level: the plan's own failure first,
    every planned system configured once (stopped, local, prewarm off,
    seeded) with a destroyed one failing the pass, the steps in
    PARTICLE_STEP_MS increments with withChildren and fixedTimeStep off and
    no other clock read, each system paused and read back on every term
    before it counts as completed, every catch recording a failure, seeds
    path-only."""
    m, code = mask_code(pin), strip_comments_only(pin)
    top = inner(m, body_span(m))
    problems = list_problems("PinParticles", _texts(code, top), PIN_TOP)
    if problems:
        return problems
    tr = top[5]
    kinds = [(k, _norm(code[h[0]:h[1]]) if h else None) for k, h, _ in slots(m, tr)]
    if kinds != [("try", None), ("catch", "Exception ex"), ("finally", None)]:
        return [f"PinParticles: the try's clauses are {kinds}"]
    problems += list_problems("the pin's catch", _texts(code, clause(m, tr, "catch")[1]),
                              ['r.failure = "threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 120);'])
    problems += list_problems("the pin's finally", _texts(code, clause(m, tr, "finally")[1]),
                              ["if (held) Time.maximumParticleDeltaTime = heldMax;"])
    body = clause(m, tr, "try")[1]
    if len(body) != 1:
        return problems + [f"the pin's try holds {len(body)} statements, want 1"]
    p, setup = _branch(m, code, body[0], "no plan", "plan == null", ['r.failure = "no plan";'])
    problems += p
    if setup is None:
        return problems + ["no plan: no else"]
    problems += list_problems("the pin's setup", _texts(code, setup), PIN_SETUP)
    p, rest = _branch(m, code, setup[-1], "the plan's failure", "plan.failure != null", ["r.failure = plan.failure;"])
    problems += p
    if rest is None or len(rest) != 1:
        return problems + ["the plan's failure is not followed by the length check alone"]
    p, run = _branch(m, code, rest[0], "the length check", "totalMs <= 0", ['r.failure = "length " + Secs(simSecs) + " s is not positive";'])
    problems += p
    if run is None:
        return problems + ["the length check: no else"]
    problems += list_problems("the pin's run", _texts(code, run), PIN_RUN)
    if len(run) != len(PIN_RUN):
        return problems
    if _head(m, code, run[2], "for") != "int k = 0; k < plan.order.Count && r.failure == null; k++":
        problems.append(f"the configure loop's head is {_head(m, code, run[2], 'for')!r}")
    problems += list_problems("the configure loop", _texts(code, clause(m, run[2], "for")[1]), PIN_CONFIGURE)
    p, other = _branch(m, code, run[3], "the steps", "r.failure == null", PIN_STEPS)
    problems += p
    if other is not None:
        problems.append("the steps have an else branch")
    steps = clause(m, run[3], "if")[1]
    if len(steps) == len(PIN_STEPS):
        pause = steps[-1]
        if _head(m, code, pause, "for") != "int k = 0; k < systems.Length; k++":
            problems.append(f"the read-back loop's head is {_head(m, code, pause, 'for')!r}")
        readback = clause(m, pause, "for")[1]
        problems += list_problems("the read-back loop", _texts(code, readback), PIN_READBACK)
        if len(readback) == len(PIN_READBACK):
            parts = if_parts(m, readback[3])
            if parts is None:
                problems.append("the read-back is not an if")
            else:
                (ca, cb), rb, has_else = parts
                terms = or_terms(code[ca:cb])
                if sorted(terms) != sorted(_norm(t) for t in READBACK_TERMS):
                    problems.append(f"the read-back asks {terms}")
                if has_else:
                    problems.append("the read-back has an else branch")
                problems += list_problems("the read-back failure", _texts(code, inner(m, rb)),
                                          ['r.failure = "read-back failed on " + p.path;', "break;"])
    # whole-method properties
    flat = _norm(m)
    if len(re.findall(r"\.Simulate\(", flat)) != 1:
        problems.append(f"want one Simulate call, found {len(re.findall(r'.Simulate[(]', flat))}")
    clocks = re.findall(r"\bTime\s*\.\s*(\w+)", m)
    if clocks != ["maximumParticleDeltaTime"] * 3:
        problems.append(f"the pin reads the clock as {clocks}")
    writes = re.findall(r"\bseeds\s*\[[^\]]*\]\s*(?:=(?!=)|\+\+|--|[-+*/%&|^]=|<<=|>>=)|(?:\+\+|--)\s*seeds\s*\[", flat)
    if len(writes) != 1:
        problems.append(f"want one write to seeds[], found {len(writes)}")
    for banned in ("seeds.Add(", "seed++", "clashes", "DEFAULT_SETTLE"):
        if banned in flat:
            problems.append(f"{banned!r} is in the particle pin")
    catches = 0
    for s in all_statements(m, top):
        for k, _, cb in slots(m, s):
            if k != "catch":
                continue
            catches += 1
            if not any(re.match(r'r\.failure = "', t) for t in _texts(code, inner(m, cb))):
                problems.append(f"a catch that records no failure: {_norm(code[s[0]:s[1]])[-80:]!r}")
    if catches == 0:
        problems.append("the particle pin catches nothing")
    return problems


def test_the_particle_pin_steps_every_planned_system_together_in_fixed_increments():
    pin = cs_block(RENDER_CS, PIN_PARTICLES)
    assert particle_pin_problems(pin) == []
    # the step and the particle delta cap the steps run under: a change to either can change the steps' output
    assert render_int("PARTICLE_STEP_MS") == 20
    assert render_float("PARTICLE_MAX_DELTA") == 0.03
    code = _norm(strip_comments_only(RENDER_CS.read_text(encoding="utf-8")))
    assert "internal const int PARTICLE_STEP_MS = 20;" in code and "private const float PARTICLE_MAX_DELTA = 0.03f;" in code
    # the only Simulate call in the renderer is the pin's
    assert len(re.findall(r"\.Simulate\(", mask_code(RENDER_CS.read_text(encoding="utf-8")))) == 1
    controls = {
        # the step options
        "Simulate(dt, false, s == 0, true)": ("Simulate(dt, false, s == 0, false)", "the steps"),
        "Simulate(dt, true, s == 0, false)": ("Simulate(dt, false, s == 0, false)", "the steps"),
        # a catch that swallows the failure (A15b)
        'catch (Exception ex) { r.failure = null; }': ('catch (Exception ex) { r.failure = "threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 120); }',
                                                      "records no failure"),
        # a seed bumped away from its path
        "seeds[k] = ParticleSeed(p.path, salt); while (!seen.Add(seeds[k])) seeds[k]++;": ("seeds[k] = ParticleSeed(p.path, salt);", "configure loop"),
        # the plan's failure ignored when it planned something (B13)
        "if (plan.failure != null && plan.order.Count == 0) r.failure = plan.failure;": ("if (plan.failure != null) r.failure = plan.failure;", "the plan's failure"),
        # the step count, the step sizes and the ambient clock (A19)
        "int stepCount = full;": ("int stepCount = full + (remMs > 0 ? 1 : 0);", "the steps"),
        "float step = PARTICLE_STEP_MS / 1000f, last = step;": ("float step = PARTICLE_STEP_MS / 1000f, last = remMs / 1000f;", "the steps"),
        "float dt = Time.deltaTime;": ("float dt = s < full ? step : last;", "the steps"),
        # a read-back term dropped (MA), its failure swallowed (A17), prewarm not read back
        "if (systems[k].isPlaying || systems[k].randomSeed != seeds[k]": ("if (systems[k].isPlaying || systems[k].useAutoRandomSeed || systems[k].randomSeed != seeds[k]", "the read-back asks"),
        "|| main.simulationSpace != ParticleSystemSimulationSpace.Local)": ("|| main.simulationSpace != ParticleSystemSimulationSpace.Local || main.prewarm)", "the read-back asks"),
        '{ }\n                                p.seed = seeds[k];': ('{ r.failure = "read-back failed on " + p.path; break; }\n                                p.seed = seeds[k];', "the read-back failure"),
        # prewarm left on; local space not written
        "if (main.prewarm) { r.unprewarmed++; }": ("if (main.prewarm) { main.prewarm = false; r.unprewarmed++; }", "configure loop"),
        "{ r.respaced++; }": ("{ main.simulationSpace = ParticleSystemSimulationSpace.Local; r.respaced++; }", "configure loop"),
    }
    for new, (old, want) in controls.items():
        problems = particle_pin_problems(_mut(pin, old, new))
        assert any(want in x for x in problems), (new, problems)
    # the seed set before the stop (MQ), counted complete before the read-back (MR)
    seeded_first = _mut(_mut(pin, "                            p.ps.useAutoRandomSeed = false;\n", ""),
                        "                            p.ps.Stop(", "                            p.ps.useAutoRandomSeed = false;\n                            p.ps.Stop(")
    assert any("configure loop" in x for x in particle_pin_problems(seeded_first))
    counted_first = _mut(_mut(pin, "                                r.completed++;\n", ""),
                         "                                systems[k].Pause(false);\n", "                                r.completed++;\n                                systems[k].Pause(false);\n")
    assert any("read-back loop" in x for x in particle_pin_problems(counted_first))


def test_the_particle_result_gates_the_capture_on_every_term():
    ok = cs_block(cs_block(RENDER_CS, "private struct ParticlePin"), "internal bool Ok")
    ret = _norm(strip_comments_only(ok))
    body = re.fullmatch(r"\{ get \{ return (.*); \} \}", ret)
    assert body, ret
    assert sorted(and_terms(body.group(1))) == sorted(["failure == null", "planned > 0", "completed == planned"])
    summary = _norm(strip_comments_only(cs_block(cs_block(RENDER_CS, "private struct ParticlePin"), "internal string Summary()")))
    assert '.Append(" unprewarmed=").Append(unprewarmed)' in summary and '.Append(" respaced=").Append(respaced)' in summary


# What the plan and the pin read, whole: the roots every inventory walks, the
# path a seed hashes and the seed itself. The pin's read-back compares a
# system's seed with ParticleSeed's own return value, so it cannot see a change
# to what a seed is computed from; these pins hold that computation to its text.
PLAN_INPUT_BODIES = {
    ("render", RIG_ROOTS): "{ if (_clone != null) yield return _clone; if (_holdable != null) yield return _holdable; "
                           "foreach (var u in _unparented) if (u != null) yield return u; }",
    ("render", RIG_PATH): '{ var parts = new List<string>(); for (var q = t; q != null; q = q.parent) parts.Add(q.name); parts.Reverse(); '
                          'return string.Join("/", parts.ToArray()); }',
    ("render", PARTICLE_SEED): ('{ uint h = Fnv32(Encoding.UTF8.GetBytes(path ?? "")); '
                                "if (salt != 0) h = Fnv32(new[] { (byte)salt, (byte)(salt >> 8), (byte)(salt >> 16), (byte)(salt >> 24) }, h); return h; }"),
    ("grade", FNV32): "{ for (int i = 0; i < d.Length; i++) { h ^= d[i]; h *= 16777619u; } return h; }",
}


def test_the_plan_inputs_are_pinned_whole():
    sources = _sources()
    assert body_problems(sources, PLAN_INPUT_BODIES) == []
    # negative controls: the gun's root dropped (N12), the lifted roots dropped
    # (N17) or inverted (G4), the salt applied at 0 too (G2), a seed that also
    # hashes the frame (G2b), the path reversed (G3) or carrying an instance id
    # (G3b), the hash's multiplier changed
    assert body_controls_problems(sources, PLAN_INPUT_BODIES, (
        ("render", RIG_ROOTS, "            if (_holdable != null) yield return _holdable;\n", ""),
        ("render", RIG_ROOTS, "            foreach (var u in _unparented) if (u != null) yield return u;\n", ""),
        ("render", RIG_ROOTS, "if (u != null) yield return u;", "if (u == null) yield return u;"),
        ("render", PARTICLE_SEED, "if (salt != 0) h = Fnv32(", "h = Fnv32("),
        ("render", PARTICLE_SEED, "            return h;\n        }\n\n        /// <summary>Names from",
         "            return h + (uint)Time.frameCount;\n        }\n\n        /// <summary>Names from"),
        ("render", RIG_PATH, "            parts.Reverse();\n", ""),
        ("render", RIG_PATH, "parts.Add(q.name);", "parts.Add(q.name + q.GetInstanceID());"),
        ("grade", FNV32, "h *= 16777619u;", "h *= 16777618u;"),
    )) == []


PLAN_TRY = [
    "var inventory = new List<ParticleSystem>();",
    "var owned = new HashSet<ParticleSystem>();",
    "foreach (var root in RigRoots()) foreach (var ps in root.GetComponentsInChildren<ParticleSystem>(true)) "
    "if (!ReferenceEquals(ps, null) && ps != null && owned.Add(ps)) inventory.Add(ps);",
    "plan.inventory = inventory.Count;",
    "var paths = new Dictionary<ParticleSystem, string>();",
    "var seenPaths = new Dictionary<string, int>(StringComparer.Ordinal);",
    "var live = new Dictionary<ParticleSystem, bool>();",
    # every path fixed from the hierarchy before any liveness is read
    'foreach (var ps in inventory) { string path = RigPath(ps.transform); int dup; '
    'if (seenPaths.TryGetValue(path, out dup)) { seenPaths[path] = dup + 1; path += "#" + (dup + 1); plan.dups++; } '
    'else seenPaths[path] = 0; paths[ps] = path; '
    'if (ps.gameObject.activeInHierarchy) live[ps] = !(ps.isStopped && ps.particleCount == 0); }',
    "plan.active = live.Count;",
    "var state = new Dictionary<ParticleSystem, int>();",
    "var subs = new HashSet<ParticleSystem>();",
    # planning starts only from an active system that is live (or every active one with `all`)
    "foreach (var ps in inventory) { bool isLive; if (!live.TryGetValue(ps, out isLive) || !(isLive || all)) continue; "
    "if (!PlanVisit(ps, plan, owned, live, paths, state, subs)) break; }",
    "if (plan.failure == null) { for (int k = 0; k < plan.order.Count; k++) { var p = plan.order[k]; p.sub = subs.Contains(p.ps); plan.order[k] = p; } "
    "foreach (var ps in inventory) if (live.ContainsKey(ps) && !state.ContainsKey(ps)) "
    "plan.left.Add(new PinnedParticle { ps = ps, name = PsName(ps), path = paths[ps], live = live[ps], before = ps.particleCount }); }",
]
VISIT_TOP = [
    "int s;",
    # a system being planned (1) is a cycle and fails the plan; a planned one (2) is not planned again
    'if (state.TryGetValue(ps, out s)) { if (s == 1) { plan.failure = "a sub-emitter cycle through " + paths[ps]; return false; } return true; }',
    "state[ps] = 1;",
    "var se = ps.subEmitters;",
    None,
    "state[ps] = 2;",
    "plan.order.Add(new PinnedParticle { ps = ps, name = PsName(ps), path = paths[ps], live = live[ps], before = ps.particleCount });",
    "return true;",
]
VISIT_SLOTS = [
    "var sub = se.GetSubEmitterSystem(i);",
    "if (ReferenceEquals(sub, null) || sub == null) continue;",
    'if (!owned.Contains(sub)) { plan.failure = "a sub-emitter of " + paths[ps] + " is outside the rig (" + sub.name + ")"; return false; }',
    "if (!live.ContainsKey(sub)) { plan.inactiveSubs++; continue; }",
    "subs.Add(sub);",
    "if (!PlanVisit(sub, plan, owned, live, paths, state, subs)) return false;",
]


def plan_problems(plan: str, visit: str) -> list:
    """The plan's statements: the whole inventory (inactive included) with its
    path suffixes assigned before any liveness is read; planning from each
    live active system; each system planned once, after every sub-emitter
    slot it has (the count Unity reports, every slot in order), where a slot
    outside the rig or a cycle fails the plan with a reason, an inactive
    system is counted and skipped, and an empty slot is skipped; the catch
    records a failure."""
    problems = []
    pm, pc = mask_code(plan), strip_comments_only(plan)
    top = inner(pm, body_span(pm))
    problems += list_problems("PlanParticles", _texts(pc, top), ["var plan = new ParticlePlan();", None, "return plan;"])
    if len(top) == 3:
        kinds = [(k, _norm(pc[h[0]:h[1]]) if h else None) for k, h, _ in slots(pm, top[1])]
        if kinds != [("try", None), ("catch", "Exception ex")]:
            problems.append(f"PlanParticles: the try's clauses are {kinds}")
        else:
            problems += list_problems("PlanParticles' try", _texts(pc, clause(pm, top[1], "try")[1]), PLAN_TRY)
            problems += list_problems("PlanParticles' catch", _texts(pc, clause(pm, top[1], "catch")[1]),
                                      ['plan.failure = "plan threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 120);'])
    vm, vc = mask_code(visit), strip_comments_only(visit)
    vtop = inner(vm, body_span(vm))
    problems += list_problems("PlanVisit", _texts(vc, vtop), VISIT_TOP)
    if len(vtop) == len(VISIT_TOP):
        p, other = _branch(vm, vc, vtop[4], "the sub-emitter module", "se.enabled", ["int n = se.subEmittersCount;", None])
        problems += p
        if other is not None:
            problems.append("the sub-emitter module has an else branch")
        slots_list = clause(vm, vtop[4], "if")[1]
        if len(slots_list) == 2:
            if _head(vm, vc, slots_list[1], "for") != "int i = 0; i < n; i++":
                problems.append(f"the slot loop's head is {_head(vm, vc, slots_list[1], 'for')!r}")
            problems += list_problems("the slot loop", _texts(vc, clause(vm, slots_list[1], "for")[1]), VISIT_SLOTS)
    return problems


def test_the_particle_plan_covers_the_sub_emitter_graph():
    plan = cs_block(RENDER_CS, PLAN_PARTICLES)
    visit = cs_block(RENDER_CS, PLAN_VISIT)
    assert plan_problems(plan, visit) == []
    visit_controls = {
        # pre-order planning
        "            state[ps] = 1;\n            plan.order.Add(new PinnedParticle { ps = ps });\n": ("            state[ps] = 1;\n", "PlanVisit"),
        # no outside check, and an outside slot that fails without a reason (A14)
        "if (false)": ("if (!owned.Contains(sub))", "the slot loop"),
        "{ return false; }": ('{ plan.failure = "a sub-emitter of " + paths[ps] + " is outside the rig (" + sub.name + ")"; return false; }', "the slot loop"),
        # no slot visited (A11), the last slot skipped, an inactive guard that never skips (A13)
        "int n = 0;": ("int n = se.subEmittersCount;", "the sub-emitter module"),
        "for (int i = 0; i < n - 1; i++)": ("for (int i = 0; i < n; i++)", "the slot loop's head"),
        "if (!live.ContainsKey(sub) && sub == null) { plan.inactiveSubs++; continue; }": ("if (!live.ContainsKey(sub)) { plan.inactiveSubs++; continue; }", "the slot loop"),
        # the reached system not planned
        "if (!PlanVisit(sub, plan, owned, live, paths, state, subs)) { }": ("if (!PlanVisit(sub, plan, owned, live, paths, state, subs)) return false;", "the slot loop"),
    }
    for new, (old, want) in visit_controls.items():
        problems = plan_problems(plan, _mut(visit, old, new))
        assert any(want in x for x in problems), (new, problems)
    plan_controls = {
        "root.GetComponentsInChildren<ParticleSystem>(false)": "root.GetComponentsInChildren<ParticleSystem>(true)",
        # the liveness filter dropped (MH) or reversed
        "if (!live.TryGetValue(ps, out isLive) || !all) continue;": "if (!live.TryGetValue(ps, out isLive) || !(isLive || all)) continue;",
        "if (!live.TryGetValue(ps, out isLive) || (isLive || all)) continue;": "if (!live.TryGetValue(ps, out isLive) || !(isLive || all)) continue;",
        'catch (Exception ex) { plan.failure = null; }': 'catch (Exception ex) { plan.failure = "plan threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 120); }',
    }
    for new, old in plan_controls.items():
        assert any("PlanParticles" in x for x in plan_problems(_mut(plan, old, new), visit)), new


# ── the real source: the rig pins ───────────────────────────────────────────

FREE_ARM = [
    "if (a == null || !seen.Add(a)) continue;",
    "g.arms++;",
    "if (a.target == null || a.holding == null || a.rig == null || a.transform.parent == null) { g.skipped++; continue; }",
    "var h = a.holding.holdable;",
    "if (h == null || h.rig == null) { g.skipped++; continue; }",
    "float rx = a.rig.transform.position.x;",
    "if ((h.rig.transform.position.x > rx) == (a.transform.position.x > rx)) { g.gunSide++; continue; }",
    "Vector3 rest = a.transform.parent.TransformPoint(a.startPos);",
    None,   # armMoved: read before the writes below
    "a.target.position = rest;",
    "a.velolcity = Vector3.zero;",
    "if (a.sinceRaise < 0.3f) a.sinceRaise = 0.3f;",
    "g.free++;",
]
ARM_MOVED_TERMS = ["(a.target.position - rest).sqrMagnitude > e2", "a.velolcity.sqrMagnitude > e2", "a.sinceRaise < 0.3f"]


def free_arm_problems(arms: str) -> list:
    m, code = mask_code(arms), strip_comments_only(arms)
    top = inner(m, body_span(m))
    problems = list_problems("PinFreeArms", _texts(code, top), ["float e2 = GUN_STILL_EPS * GUN_STILL_EPS;", "var seen = new HashSet<IKArmMove>();", None])
    if len(top) != 3:
        return problems
    roots = clause(m, top[2], "foreach")[1]
    if len(roots) != 1 or [k for k, _, _ in slots(m, roots[0])] != ["foreach"]:
        return problems + ["PinFreeArms does not visit every arm under every rig root"]
    arm = clause(m, roots[0], "foreach")[1]
    problems += list_problems("the free arm", _texts(code, arm), FREE_ARM)
    if len(arm) == len(FREE_ARM):
        parts = if_parts(m, arm[8])
        if parts is None:
            problems.append("armMoved is not an if")
        else:
            (ca, cb), body, has_else = parts
            if sorted(or_terms(code[ca:cb])) != sorted(ARM_MOVED_TERMS):
                problems.append(f"armMoved asks {or_terms(code[ca:cb])}")
            if has_else or _texts(code, inner(m, body)) != ["g.armMoved = true;"]:
                problems.append("armMoved is not set when an arm moved")
    return problems


RIG_PIN_BODIES = {
    ("render", PIN_GUN_SPRINGS): (
        "{ foreach (var root in RigRoots()) { "
        "foreach (var s in root.GetComponentsInChildren<RightLeftMirrorSpring>(true)) { if (s == null) continue; var h = s.holdable; "
        "if (h == null || h.holder == null) { g.inert++; continue; } "
        "bool left = s.transform.root.position.x - 0.1f < h.holder.transform.position.x; float r = left ? s.leftRot : s.rightRot; "
        "s.posVel = Vector3.zero; s.rotVel = 0f; s.currentRot = r; s.transform.localPosition = left ? s.leftPos : s.rightPos; "
        "s.transform.localEulerAngles = new Vector3(0f, 0f, r); s.enabled = false; g.mirror++; } "
        "foreach (var s in root.GetComponentsInChildren<RotSpring>(true)) { if (s == null) continue; s.vel = 0f; s.currentValue = s.target; "
        "s.transform.localEulerAngles = new Vector3(s.x ? s.target : 0f, s.y ? s.target : 0f, s.z ? s.target : 0f); s.enabled = false; g.rot++; } } "
        "foreach (var root in RigRoots()) { foreach (var s in root.GetComponentsInChildren<RightLeftMirrorSpring>(true)) "
        "if (s != null && s.enabled && s.holdable != null && s.holdable.holder != null) g.live++; "
        "foreach (var s in root.GetComponentsInChildren<RotSpring>(true)) if (s != null && s.enabled) g.live++; } }"),
    ("render", PIN_FRAMES): (
        "{ var f = new FramePin(); try { var cyclers = new List<CustomCosmetics.CosmeticFrameCycler>(); "
        "var seen = new HashSet<CustomCosmetics.CosmeticFrameCycler>(); "
        "foreach (var root in RigRoots()) foreach (var c in root.GetComponentsInChildren<CustomCosmetics.CosmeticFrameCycler>(true)) "
        "if (!ReferenceEquals(c, null) && seen.Add(c)) cyclers.Add(c); f.found = cyclers.Count; "
        'foreach (var c in cyclers) { try { if (c == null) { FrameFailed(ref f, "a destroyed cycler"); continue; } c.enabled = false; '
        'if (c.frames == null || c.frames.Length == 0) { if (!c.enabled) f.still++; else FrameFailed(ref f, c.name + " did not disable"); continue; } '
        'var sr = c.GetComponent<SpriteRenderer>(); if (sr == null) { FrameFailed(ref f, c.name + " has frames and no SpriteRenderer"); continue; } '
        'sr.sprite = c.frames[0]; if (!c.enabled && sr.sprite == c.frames[0]) f.pinned++; else FrameFailed(ref f, c.name + " does not read back disabled on frame 0"); } '
        'catch (Exception ex) { FrameFailed(ref f, ex.GetType().Name + ": " + Trunc(ex.Message, 80)); } } f.ran = true; } '
        'catch (Exception ex) { FrameFailed(ref f, "enumeration threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 80)); } return f; }'),
}


def test_the_gun_pin_predicate_keeps_every_term_of_the_rig_contract():
    gun = cs_block(cs_block(RENDER_CS, "private struct GunPin"), "internal bool Pinned(int stillFrames)")
    assert sorted(_return_terms(gun)) == sorted([
        "hand", "!moved", "!armMoved", "stillFrames >= GUN_STILL_FRAMES",
        "arms == RIG_ARMS", "gunSide == 1", "free == 1", "skipped == 0",
        "mirror == RIG_MIRROR_SPRINGS", "inert == 0", "live == 0", "error == null"])
    assert render_int("RIG_ARMS") == 2 and render_int("RIG_MIRROR_SPRINGS") == 5
    hold = _norm(strip_comments_only(cs_block(RENDER_CS, HOLD_GUN)))
    assert ("return g.hand && !g.moved && !g.armMoved && g.arms == RIG_ARMS && g.gunSide == 1 && g.free == 1 && g.skipped == 0;"
            in hold)
    arms = cs_block(RENDER_CS, PIN_FREE_ARMS)
    # no gun rig to classify by: skipped, never free
    assert exits_before(arms, "h == null || h.rig == null", "continue;", "g.free++;") == []
    assert exits_before(arms, "a.target == null || a.holding == null || a.rig == null || a.transform.parent == null", "continue;", "g.free++;") == []
    assert free_arm_problems(arms) == []
    # negative controls: a movement term dropped (MW), the rest written before it is compared
    dropped = _mut(arms, " || a.sinceRaise < 0.3f) g.armMoved = true;", ") g.armMoved = true;")
    assert any("armMoved asks" in x for x in free_arm_problems(dropped))
    written = _mut(_mut(arms, "                    a.target.position = rest;\n", ""),
                   "                    if ((a.target.position - rest)", "                    a.target.position = rest;\n                    if ((a.target.position - rest)")
    assert any("the free arm" in x for x in free_arm_problems(written))
    # The springs, whole. A mirror spring's side is its own Update's test (the
    # root 0.1 left of the holder is the left side), and its rest pose is what
    # that Update settles to on that side: position, rotation, no velocity. A
    # rot spring rests at its target on the axes it drives.
    sources = _sources()
    assert body_problems(sources, RIG_PIN_BODIES) == []
    # negative controls: the side flipped (G5), the rest position of the other
    # side, a rot spring rested at 0, a spring left enabled, a live spring not counted
    assert body_controls_problems(sources, RIG_PIN_BODIES, (
        ("render", PIN_GUN_SPRINGS, "s.transform.root.position.x - 0.1f < h.holder.transform.position.x",
         "s.transform.root.position.x - 0.1f > h.holder.transform.position.x"),
        ("render", PIN_GUN_SPRINGS, "s.transform.localPosition = left ? s.leftPos : s.rightPos;", "s.transform.localPosition = left ? s.rightPos : s.leftPos;"),
        ("render", PIN_GUN_SPRINGS, "s.currentValue = s.target;", "s.currentValue = 0f;"),
        ("render", PIN_GUN_SPRINGS, "s.enabled = false;\n                    g.mirror++;", "g.mirror++;"),
        ("render", PIN_GUN_SPRINGS, "if (s != null && s.enabled) g.live++;", "if (s != null && s.enabled && s.x) g.live++;"),
    )) == []


def test_the_rig_pin_requires_the_face_frames_and_counts_every_cycler():
    rig = cs_block(cs_block(RENDER_CS, "private struct RigPin"), "internal bool Pinned(int stillFrames)")
    assert sorted(_return_terms(rig)) == sorted(["gun.Pinned(stillFrames)", "frames.Pinned()"])
    frames = cs_block(cs_block(RENDER_CS, "private struct FramePin"), "internal bool Pinned()")
    assert sorted(_return_terms(frames)) == sorted(["ran", "failed == 0", "pinned + still == found"])
    pin = _norm(mask_code(cs_block(RENDER_CS, PIN_FRAMES)))
    # one failure per cycler, and the pass goes on; nothing is swallowed
    assert pin.count("catch (Exception ex) { FrameFailed(ref f,") == 2
    assert not re.search(r"\bcatch\s*\{", pin)
    assert "if (!c.enabled && sr.sprite == c.frames[0]) f.pinned++;" in pin
    assert "f.ran = true;" in pin
    # the discovery whole: every cycler under every rig root, each once, counted
    sources = _sources()
    assert body_problems(sources, {("render", PIN_FRAMES): RIG_PIN_BODIES[("render", PIN_FRAMES)]}) == []
    # negative controls: cyclers found on the roots only (N15), the count not
    # the cyclers found, a cycler counted twice
    assert body_controls_problems(sources, RIG_PIN_BODIES, (
        ("render", PIN_FRAMES, "foreach (var c in root.GetComponentsInChildren<CustomCosmetics.CosmeticFrameCycler>(true))",
         "foreach (var c in root.GetComponents<CustomCosmetics.CosmeticFrameCycler>())"),
        ("render", PIN_FRAMES, "f.found = cyclers.Count;", "f.found = 0;"),
        ("render", PIN_FRAMES, "if (!ReferenceEquals(c, null) && seen.Add(c)) cyclers.Add(c);", "if (!ReferenceEquals(c, null)) cyclers.Add(c);"),
    )) == []


# ── the real source: the colour readiness ───────────────────────────────────

FRAME_READY_LINES = (
    "if (token == 0 || !animByActor.TryGetValue(actor, out st) || st == null) return false;",
    "if (st.portraitToken != token || !st.clockPinned || st.passFailures != 0) return false;",
    "if (st.tintedSkins.Count + st.tintedParticles.Count + st.tintedSprites.Count == 0) return false;",
    "return !IsAnimatedSku(st.sku) || (st.staticFrameApplied && st.frameWrites > 0);",
)
# What a frame wrote: the sku's colour at the animation clock `now` and at no
# other clock, and one count per target written, nothing else.
WRITE_FRAME_TOP = [
    "int writes = 0;",
    "Color c = st.baseColor;",
    'if (st.sku == "pcolor_prismatic") { float h = (now * 0.25f) % 1f; c = Color.HSVToRGB(h, 0.85f, 1f); } '
    'else if (st.sku == "pcolor_chrome") { float t = (Mathf.Sin(now * 0.7f) + 1f) * 0.5f; '
    "c = Color.Lerp(new Color(0.78f, 0.78f, 0.86f), new Color(0.92f, 0.92f, 0.96f), t); }",
    "for (int i = 0; i < st.tintedSkins.Count; i++) { st.skinColorFields[i].SetValue(st.tintedSkins[i], c); writes++; }",
    "foreach (var sr in st.tintedSprites) if (sr != null) { sr.color = c; writes++; }",
    "foreach (var ps in st.tintedParticles) { if (ps == null) continue; var main = ps.main; main.startColor = new ParticleSystem.MinMaxGradient(c); writes++; }",
    "return writes;",
]


def colour_token_problems(color: str) -> list:
    """The frame count PortraitFrameReady requires is the targets written, and
    every portrait application gets a token no earlier one had."""
    problems = []
    wf = cs_block(color, WRITE_FRAME)
    m, code = mask_code(wf), strip_comments_only(wf)
    problems += list_problems("WriteFrame", _texts(code, inner(m, body_span(m))), WRITE_FRAME_TOP)
    if len(re.findall(r"\bwrites\b", m)) != 5:
        problems.append("WriteFrame touches `writes` other than declaring, counting three writes and returning it")
    if re.search(r"\b(?:Time|DateTime|Environment|Stopwatch)\s*\.", m):
        problems.append("WriteFrame reads a clock other than `now`")
    ap = cs_block(color, APPLY_FOR_PORTRAIT)
    am, ac = mask_code(ap), strip_comments_only(ap)
    problems += list_problems("ApplyForPortrait", _texts(ac, inner(am, body_span(am)))[:2],
                              ["int token = ++_portraitSerial;", "if (token <= 0) { _portraitSerial = 1; token = 1; }"])
    if len(re.findall(r"\b_portraitSerial\b", mask_code(color))) != 3:
        problems.append("_portraitSerial is written outside ApplyForPortrait's two statements")
    return problems


def test_the_colour_readiness_fails_closed():
    ready = _norm(strip_comments_only(cs_block(COLOR_CS, FRAME_READY)))
    assert ready == "{ AnimState st; " + " ".join(FRAME_READY_LINES) + " }", ready
    apply = _norm(strip_comments_only(cs_block(COLOR_CS, APPLY_FOR_PORTRAIT)))
    assert "if (!animByActor.TryGetValue(actor, out st) || st == null || st.portraitToken != token) return 0;" in apply
    assert "try { st.frameWrites = WriteFrame(st, 0f); st.staticFrameApplied = true; }" in apply
    to_player = _norm(mask_code(cs_block(COLOR_CS, APPLY_TO_PLAYER)))
    assert "portraitToken = _portraitApply ? _portraitToken : 0" in to_player
    # the baseline sniff and the three tint passes each count a failure
    assert to_player.count("st.passFailures++;") == 4
    colour = _norm(strip_comments_only(cs_block(RENDER_CS, COLOUR_READY)))
    assert colour == "{ if (string.IsNullOrEmpty(hex)) return token == 0; return token != 0 && PlayerColorCosmetic.PortraitFrameReady(PORTRAIT_ACTOR, token); }", colour
    exact = _norm(strip_comments_only(cs_block(RENDER_CS, APPLY_COLOR_EXACT)))
    assert "int token = PlayerColorCosmetic.ApplyForPortrait(clone.transform, PORTRAIT_ACTOR, sku, hex);" in exact
    assert 'catch (Exception ex) { rep.Append("colour threw: ").Append(ex.Message).Append(\'\\n\'); return 0; }' in exact
    color = COLOR_CS.read_text(encoding="utf-8")
    assert colour_token_problems(color) == []
    # negative controls: a write counted that did not happen (A35), a write
    # counted whether or not it happened, a token every call shares (A36), a
    # colour read from the live clock (N11), a chrome colour changed
    assert any("WriteFrame" in x for x in colour_token_problems(_mut(color, "            return writes;\n", "            return writes + 1;\n")))
    live = colour_token_problems(_mut(color, "float h = (now * 0.25f) % 1f;", "float h = (Time.time * 0.25f) % 1f;"))
    assert any("WriteFrame: statement 2" in x for x in live) and any("a clock other than" in x for x in live), live
    assert any("WriteFrame: statement 2" in x for x in colour_token_problems(_mut(color, "float t = (Mathf.Sin(now * 0.7f) + 1f) * 0.5f;", "float t = 0.5f;")))
    assert any("WriteFrame" in x for x in colour_token_problems(_mut(color, "if (sr != null) { sr.color = c; writes++; }", "{ if (sr != null) sr.color = c; writes++; }")))
    assert any("ApplyForPortrait" in x for x in colour_token_problems(_mut(color, "int token = ++_portraitSerial;", "int token = 1; ++_portraitSerial;")))


# ── the real source: the animated colour loop and its host ──────────────────

COLOUR_LOOP_BODIES = {
    ENSURE_ANIM_LOOP: ('{ if (animLoop != null && animLoopHost != null) return; if (Plugin.Instance == null) return; bool need = false; '
                       'foreach (var st in animByActor.Values) if (st != null && IsAnimatedSku(st.sku)) { need = true; break; } '
                       'if (!need) return; int gen = ++animLoopGen; animLoopHost = Plugin.Instance; '
                       'animLoop = Plugin.Instance.StartCoroutine(AnimTickLoop(gen)); '
                       'Plugin.Log.LogInfo($"[PCOLOR] Started anim tick loop ({why})"); }'),
    STOP_ANIM_LOOP: "{ if (animLoop != null && animLoopHost != null) { try { animLoopHost.StopCoroutine(animLoop); } catch { } } animLoop = null; animLoopHost = null; }",
    ON_HOST_DESTROYED: ("{ if (ReferenceEquals(host, null)) return; var stopped = new List<int>(); "
                        "foreach (var kv in _pendingInactiveApplies) if (ReferenceEquals(kv.Value.host, host)) stopped.Add(kv.Key); "
                        "foreach (var actor in stopped) _pendingInactiveApplies.Remove(actor); "
                        "if (!ReferenceEquals(animLoopHost, host)) return; animLoop = null; animLoopHost = null; }"),
    ON_HOST_RESPAWNED: ('{ try { EnsureAnimLoop("host respawned"); } '
                        'catch (Exception ex) { Plugin.Log.LogWarning($"[PCOLOR] anim loop restart failed: {ex.Message}"); } }'),
}


def colour_loop_problems(color: str, plugin: str) -> list:
    """The animated colour loop is taken as running only while the behaviour
    it runs on is not destroyed; the host's OnDestroy forgets it, and the
    respawned host starts it again once it is Plugin.Instance."""
    problems = []
    for sig, want in COLOUR_LOOP_BODIES.items():
        got = _norm(strip_comments_only(cs_block(color, sig)))
        if got != _norm(want):
            problems.append(f"{sig}: {got[:160]!r}")
    loop = cs_block(color, ANIM_TICK_LOOP)
    lm, lc = mask_code(loop), strip_comments_only(loop)
    lt = inner(lm, body_span(lm))
    if not lt or _norm(lc[lt[-1][0]:lt[-1][1]]) != "if (gen == animLoopGen) { animLoop = null; animLoopHost = null; }":
        problems.append("AnimTickLoop clears a handle a later start owns")
    cm = mask_code(color)
    counts = {r"StartCoroutine\(AnimTickLoop\(": 1, r"\bStopCoroutine\(": 1, r"\banimLoop\s*=(?!=)": 4,
              r"\banimLoopHost\s*=(?!=)": 4, r"\bStopAnimLoop\(\);": 2, r"\banimLoopGen\s*=(?!=)": 0, r"\+\+animLoopGen\b": 1}
    for pattern, want in counts.items():
        if len(re.findall(pattern, cm)) != want:
            problems.append(f"PlayerColorCosmetic: {pattern} occurs {len(re.findall(pattern, cm))} times, want {want}")
    od = cs_block(plugin, ON_DESTROY)
    om, oc = mask_code(od), strip_comments_only(od)
    top = inner(om, body_span(om))
    problems += list_problems("OnDestroy", _texts(oc, top)[:2],
                              ["try { PortraitRender.OnHostDestroyed(this); } catch { }", "try { PlayerColorCosmetic.OnHostDestroyed(this); } catch { }"])
    respawn = [s for s in top if slots(om, s) and slots(om, s)[0][0] == "try"
               and "Plugin.Instance = newInstance;" in _texts(oc, clause(om, s, "try")[1])]
    if len(respawn) != 1:
        problems.append("OnDestroy has no single respawn")
    else:
        texts = _texts(oc, clause(om, respawn[0], "try")[1])
        want = ["Plugin.Instance = newInstance;", "Plugin.AttachPersistentCompanions(go);", "try { PlayerColorCosmetic.OnHostRespawned(); } catch { }"]
        at = [texts.index(w) if w in texts else -1 for w in want]
        if -1 in at or at != sorted(at):
            problems.append(f"the respawn does not restart the colour loop from the new host: {at}")
    pm = mask_code(plugin)
    for hook in (r"PlayerColorCosmetic\.OnHostRespawned\(", r"PlayerColorCosmetic\.OnHostDestroyed\("):
        if len(re.findall(hook, pm)) != 1:
            problems.append(f"Plugin.cs: {hook} occurs {len(re.findall(hook, pm))} times, want 1")
    return problems


def test_the_animated_colour_loop_follows_the_host():
    color, plugin = COLOR_CS.read_text(encoding="utf-8"), PLUGIN_CS.read_text(encoding="utf-8")
    assert colour_loop_problems(color, plugin) == []
    # negative controls: the destroyed host's handle kept, a handle alone taken
    # as a running loop, a finished loop clearing its successor's handle, no
    # hook in OnDestroy, the restart before the new host is Plugin.Instance
    assert any(ON_HOST_DESTROYED in x for x in colour_loop_problems(
        _mut(color, "if (!ReferenceEquals(animLoopHost, host)) return;", "return;"), plugin))
    assert any(ENSURE_ANIM_LOOP in x for x in colour_loop_problems(
        _mut(color, "            if (animLoop != null && animLoopHost != null) return;\n            if (Plugin.Instance == null) return;",
             "            if (animLoop != null) return;\n            if (Plugin.Instance == null) return;"), plugin))
    assert any("AnimTickLoop" in x for x in colour_loop_problems(
        _mut(color, "if (gen == animLoopGen) { animLoop = null; animLoopHost = null; }", "animLoop = null; animLoopHost = null;"), plugin))
    assert any("OnDestroy" in x for x in colour_loop_problems(
        color, _mut(plugin, "            try { PlayerColorCosmetic.OnHostDestroyed(this); } catch { }\n", "")))
    early = _mut(_mut(plugin, "                try { PlayerColorCosmetic.OnHostRespawned(); } catch { }\n", ""),
                 "                Plugin.Instance = newInstance;\n",
                 "                try { PlayerColorCosmetic.OnHostRespawned(); } catch { }\n                Plugin.Instance = newInstance;\n")
    assert any("respawn" in x for x in colour_loop_problems(color, early))


# ── the real source: the inactive-player colour defer and its host ──────────

# How a deferred apply's record ends: the coroutine drops its own record
# whichever way its wait ends, a failed start drops it, the host's destruction
# drops the records on that host (the host hook is pinned above), and a record
# past its time or on a destroyed host holds back no new defer and is replaced
# by it.
DEFER_BODIES = {
    PENDING_APPLY: "{ internal MonoBehaviour host; internal int gen; internal float until; }",
    APPLY_OR_DEFER: ('{ if (playerRoot == null) return false; int g; _applyGen.TryGetValue(actor, out g); g++; _applyGen[actor] = g; '
                     "if (playerRoot.gameObject.activeInHierarchy) { ApplyToPlayer(playerRoot, actor, sku, colorHex); return true; } "
                     "PendingApply pending; if (_pendingInactiveApplies.TryGetValue(actor, out pending) && pending.host != null "
                     "&& Time.realtimeSinceStartup <= pending.until) return false; var host = Plugin.Instance; "
                     "_pendingInactiveApplies[actor] = new PendingApply { host = host, gen = g, "
                     "until = Time.realtimeSinceStartup + DEFER_WAIT_SECS + DEFER_SLACK_SECS }; "
                     'Plugin.Log.LogInfo($"[PCOLOR] deferred (player inactive) actor={actor}"); '
                     "try { host.StartCoroutine(ApplyWhenActive(playerRoot, actor, sku, colorHex, g)); } "
                     'catch (Exception ex) { DropPending(actor, g); Plugin.Log.LogWarning($"[PCOLOR] defer failed: {ex.Message}"); } return false; }'),
    DROP_PENDING: "{ PendingApply pending; if (_pendingInactiveApplies.TryGetValue(actor, out pending) && pending.gen == gen) _pendingInactiveApplies.Remove(actor); }",
    APPLY_WHEN_ACTIVE: ("{ float deadline = Time.realtimeSinceStartup + DEFER_WAIT_SECS; "
                        "while (playerRoot != null && !playerRoot.gameObject.activeInHierarchy && Time.realtimeSinceStartup < deadline) yield return null; "
                        "DropPending(actor, gen); int cur; "
                        'if (_applyGen.TryGetValue(actor, out cur) && cur != gen) { Plugin.Log.LogInfo($"[PCOLOR] deferred apply superseded actor={actor}"); yield break; } '
                        "if (playerRoot == null || !playerRoot.gameObject.activeInHierarchy) yield break; ApplyToPlayer(playerRoot, actor, sku, colorHex); }"),
}
# The wait, and the slack by which the record outlives it (a positive slack,
# so the record is still held while a steady coroutine finishes its wait).
DEFER_CONSTANTS = {"DEFER_WAIT_SECS": 10.0, "DEFER_SLACK_SECS": 2.0}
# Every occurrence in the file of the record map, its release, its constructor
# and the generation map: their declarations and the pinned bodies (the host
# hook's included), and nowhere else.
DEFER_COUNTS = {r"\b_pendingInactiveApplies\b": 7, r"\bDropPending\s*\(": 3, r"\bnew\s+PendingApply\b": 1, r"\b_applyGen\b": 4}


def defer_problems(color: str) -> list:
    problems = []
    for sig, want in DEFER_BODIES.items():
        got = _norm(strip_comments_only(cs_block(color, sig)))
        if got != _norm(want):
            problems.append(f"{sig}: {got[:200]!r}")
    cm, cc = mask_code(color), strip_comments_only(color)
    for name, want in DEFER_CONSTANTS.items():
        got = _float_value(_initialiser(cm, cc, name))
        if got != want:
            problems.append(f"{name} is {got}, want {want}")
    for pattern, want in DEFER_COUNTS.items():
        n = len(re.findall(pattern, cm))
        if n != want:
            problems.append(f"PlayerColorCosmetic: {pattern} occurs {n} times, want {want}")
    return problems


def test_a_deferred_colour_apply_is_released_with_its_host():
    color = COLOR_CS.read_text(encoding="utf-8")
    assert defer_problems(color) == []
    # negative controls: the host's records kept (on the host hook's pin, above),
    # the hold without its time or its host term, a record that outlives no
    # wait, a failed start that keeps its record, a coroutine that ends without
    # dropping its record, a drop that removes a later defer's record, the
    # record map written outside the bodies, the slack gone
    assert any(ON_HOST_DESTROYED in x for x in colour_loop_problems(
        _mut(color, "            foreach (var actor in stopped) _pendingInactiveApplies.Remove(actor);\n", ""),
        PLUGIN_CS.read_text(encoding="utf-8")))
    controls = (
        ("\n                && Time.realtimeSinceStartup <= pending.until)", ")", APPLY_OR_DEFER),
        (" && pending.host != null\n", "\n", APPLY_OR_DEFER),
        ("until = Time.realtimeSinceStartup + DEFER_WAIT_SECS + DEFER_SLACK_SECS", "until = Time.realtimeSinceStartup", APPLY_OR_DEFER),
        ("                DropPending(actor, g);\n", "", APPLY_OR_DEFER),
        ("                yield return null;\n            DropPending(actor, gen);\n", "                yield return null;\n", APPLY_WHEN_ACTIVE),
        (" && pending.gen == gen)", ")", DROP_PENDING),
        ("            animByActor.Clear();\n", "            animByActor.Clear();\n            _pendingInactiveApplies.Clear();\n", "_pendingInactiveApplies"),
        ("private const float DEFER_SLACK_SECS = 2f;", "private const float DEFER_SLACK_SECS = 0f;", "DEFER_SLACK_SECS"),
    )
    for old, new, want in controls:
        assert any(want in x for x in defer_problems(_mut(color, old, new))), new


# ── the real source: the dev levers ─────────────────────────────────────────

LEVER_STATEMENTS = [
    # a run's own claim and rig, asked only by a run (gen 0 is DevRun's dispatch)
    'if (gen != 0) { if (!_renderClaim.Owns(gen)) return "the run no longer holds its claim (aborted or superseded)"; '
    'if (RigLost()) return "the rig was destroyed"; }',
    'if (!Photon.Pun.PhotonNetwork.OfflineMode) { if (Photon.Pun.PhotonNetwork.InRoom) return "in an online room"; '
    'var cs = Photon.Pun.PhotonNetwork.NetworkClientState; '
    'if (cs != Photon.Realtime.ClientState.PeerCreated && cs != Photon.Realtime.ClientState.Disconnected '
    '&& cs != Photon.Realtime.ClientState.ConnectedToMasterServer && cs != Photon.Realtime.ClientState.JoinedLobby) '
    'return "the Photon client is " + cs + ", which may be entering or leaving a room"; }',
    'if (SpectatorSession.IsLocalSpectator) return "spectating";',
    'if (SpectatorJoiner.JoinOpUnsettled) return "a spectate join is in flight";',
    'if (GameStateWatcher.IsInMatch) return "a match is tracked";',
    "var gm = GameManager.instance;",
    'if (gm != null && (gm.isPlaying || gm.battleOngoing)) return "a game has started in this scene";',
    "var pm = PlayerManager.instance;",
    'if (pm != null && pm.players != null && pm.players.Count > 0) return pm.players.Count + " player(s) spawned";',
    "return null;",
]


def lever_predicate_problems(block: str) -> list:
    """DevLeverBlocked is one try: its statements, in order, are the terms
    above (each refusal a non-null string), then its only `return null;`;
    its catch refuses."""
    m, code = mask_code(block), strip_comments_only(block)
    problems = []
    top = inner(m, body_span(m))
    if len(top) != 1 or [k for k, _, _ in slots(m, top[0])] != ["try", "catch"]:
        return ["DevLeverBlocked is not one try with one catch"]
    problems += list_problems("DevLeverBlocked", _texts(code, clause(m, top[0], "try")[1]), LEVER_STATEMENTS)
    head, catch = clause(m, top[0], "catch")
    if head is None or _norm(code[head[0]:head[1]]) != "Exception ex" or \
            _texts(code, catch) != [_norm('return "state unreadable (" + ex.GetType().Name + ")";')]:
        problems.append("an exception does not refuse")
    for cached in ("IsInOnlineRoom", "RoomActors.LocalIsSpectator"):
        if cached in _norm(code):
            problems.append(f"{cached} is a polled copy, not the state itself")
    problems += refusal_return_problems(block)
    return problems


def test_one_predicate_reads_the_state_itself_and_refuses_on_doubt():
    block = cs_block(RENDER_CS, LEVER_BLOCKED)
    assert lever_predicate_problems(block) == []
    # negative controls: a run's own terms reached only for some runs (gen < 0)
    # or dropped, a term disabled, a polled copy, a refusal that returns null,
    # an exception that does not refuse
    assert any("statement 0" in x for x in lever_predicate_problems(_mut(block, "if (gen != 0)", "if (gen < 0)")))
    assert any("statement 0" in x for x in lever_predicate_problems(
        _mut(block, '                    if (!_renderClaim.Owns(gen)) return "the run no longer holds its claim (aborted or superseded)";\n', "")))
    assert lever_predicate_problems(_mut(block, "if (SpectatorJoiner.JoinOpUnsettled)", "if (false)")) != []
    assert any("polled copy" in x for x in lever_predicate_problems(_mut(block, "Photon.Pun.PhotonNetwork.InRoom", "GameStateWatcher.IsInOnlineRoom")))
    assert any("may return null" in x for x in lever_predicate_problems(_mut(block, 'return "spectating";', "return (string)null;")))
    assert any("does not refuse" in x for x in lever_predicate_problems(_mut(block, 'return "state unreadable (" + ex.GetType().Name + ")";', "return null;")))
    for p in sorted(PLUGIN.glob("*.cs")):
        assert "GradeLeverBlocked" not in mask_code(p.read_text(encoding="utf-8")), p.name


# DevRun, whole: the scene hook and the reclaim first, the busy and host
# refusals, the lever predicate, then one start per verb, each coroutine
# started with the generation of the claim taken for it.
DEV_RUN_STATEMENTS = [
    'spec = (spec ?? "").Trim();',
    "EnsureSceneHook();",
    "Reclaim();",
    "if (Rendering || UploadInFlight) { Plugin.Log.LogInfo(\"[PORTRAIT] busy; ignoring '\" + spec + \"'\"); return; }",
    'if (Plugin.Instance == null) { Plugin.Log.LogWarning("[PORTRAIT] no Plugin.Instance"); return; }',
    "string blocked = DevLeverBlocked(0);",
    "if (blocked != null) { Plugin.Log.LogInfo(\"[PORTRAIT] refused: \" + blocked + \"; ignoring '\" + spec + \"'\"); return; }",
    'if (spec.Equals("upload", StringComparison.OrdinalIgnoreCase)) { StartProduct("lever", true, true); return; }',
    'if (spec.Equals("preview", StringComparison.OrdinalIgnoreCase)) { StartProduct("lever-preview", false, true); return; }',
    "string verb = spec.Split(',')[0].Trim().ToLowerInvariant();",
    'if (verb == "gradebake") { Plugin.Instance.StartCoroutine(GradeBakeRun(spec, _renderClaim.Take(Plugin.Instance, DEV_BUDGET))); return; }',
    'if (verb == "gradeswatch") { Plugin.Instance.StartCoroutine(GradeSwatchRun(spec, _renderClaim.Take(Plugin.Instance, DEV_BUDGET))); return; }',
    "Plugin.Instance.StartCoroutine(Run(spec, _renderClaim.Take(Plugin.Instance, DEV_BUDGET)));",
]


def dev_run_problems(dev: str) -> list:
    m, code = mask_code(dev), strip_comments_only(dev)
    return list_problems("DevRun", _texts(code, inner(m, body_span(m))), DEV_RUN_STATEMENTS)


def test_every_lever_is_refused_at_dispatch():
    dev = cs_block(RENDER_CS, DEV_RUN)
    assert dominating_exit(dev, "blocked != null", "return;", ("StartProduct(", "StartCoroutine(")) == []
    m = mask_code(dev)
    guard = find_guards(dev, "blocked != null")[0]
    before = [s for s in statements(m, 1, len(m) - 1) if s[1] <= guard[0]]
    assert _norm(m[before[-1][0]:before[-1][1]]) == "string blocked = DevLeverBlocked(0);"
    assert len(re.findall(r"\bStartCoroutine\(", m)) == 3 and len(re.findall(r"\bStartProduct\(", m)) == 2
    assert dev_run_problems(dev) == []
    # negative controls: a run started with generation 0 beside the claim taken
    # for it (N01), no scene hook (N04, GL2), a grade run started with a claim
    # of its own, the preview verb started as an upload
    controls = (
        ("Plugin.Instance.StartCoroutine(Run(spec, _renderClaim.Take(Plugin.Instance, DEV_BUDGET)));",
         "_renderClaim.Take(Plugin.Instance, DEV_BUDGET); Plugin.Instance.StartCoroutine(Run(spec, 0));", "DevRun: statement 12"),
        ('            spec = (spec ?? "").Trim();\n            EnsureSceneHook();\n', '            spec = (spec ?? "").Trim();\n', "DevRun: statement 1"),
        ("StartCoroutine(GradeSwatchRun(spec, _renderClaim.Take(Plugin.Instance, DEV_BUDGET)));",
         "StartCoroutine(GradeSwatchRun(spec, StartGrade()));", "DevRun: statement 11"),
        ('StartProduct("lever-preview", false, true);', 'StartProduct("lever-preview", true, true);', "DevRun: statement 8"),
    )
    for old, new, want in controls:
        assert any(want in x for x in dev_run_problems(_mut(dev, old, new))), new


@pytest.mark.parametrize("source,signature,yields", [
    (RENDER_CS, RUN, 6),
    (GRADE_CS, GRADE_BAKE_RUN, 3),
    (GRADE_CS, GRADE_SWATCH_RUN, 4),
])
def test_every_lever_coroutine_asks_the_predicate_after_every_yield(source, signature, yields):
    block = cs_block(source, signature)
    assert len(re.findall(r"\byield\s+return\b", mask_code(block))) == yields
    assert fence_problems(block, "DevLeverBlocked(gen)") == []
    # negative control: a beat that is not this run's own is not skipped
    other = _mut(block, "_renderClaim.Beat(gen, DEV_BUDGET);", "_renderClaim.Beat(gen + 1, DEV_BUDGET);")
    assert any("not a fenced exit" in x for x in fence_problems(other, "DevLeverBlocked(gen)"))


# ── the real source: force-abort and the claim ──────────────────────────────

# The mechanisms every release rests on, whole: a change to any of them is a
# change to what releases what, and is made here on purpose.
MECHANISM_BODIES = {
    ("render", CLAIM): (
        "{ private MonoBehaviour _host; private int _gen; private float _until; "
        "internal bool Held { get { return _host != null && Time.realtimeSinceStartup <= _until; } } "
        "internal bool Owns(int gen) { return gen == _gen && Held; } "
        "internal bool HeldByOther(int gen) { return gen != _gen && Held; } "
        "internal bool HeldBy(MonoBehaviour host) { return !ReferenceEquals(host, null) && ReferenceEquals(_host, host) && Time.realtimeSinceStartup <= _until; } "
        "internal int Take(MonoBehaviour host, float budget) { _host = host; _until = Time.realtimeSinceStartup + budget; return ++_gen; } "
        "internal void Beat(int gen, float budget) { if (gen == _gen && !ReferenceEquals(_host, null)) _until = Time.realtimeSinceStartup + budget; } "
        "internal void Drop(int gen) { if (gen != _gen) return; _host = null; _until = -1f; } "
        "internal void Clear() { _host = null; _until = -1f; } }"),
    ("render", FORCE_ABORT): (
        "{ _renderClaim.Clear(); _cleanupOwed = false; try { Application.logMessageReceived -= OnLog; } catch { } "
        "try { Teardown(new StringBuilder()); } catch { } try { DestroyGradeObjects(); } catch { } "
        'try { Plugin.Log.LogInfo("[PORTRAIT] force-abort: " + why); } catch { } }'),
    ("render", ON_HOST_DESTROYED): (
        '{ try { if (_renderClaim.HeldBy(host) || (_cleanupOwed && !_renderClaim.Held)) ForceAbort("the coroutine host was destroyed"); } catch { } }'),
    ("render", ON_SCENE_UNLOADED): (
        '{ try { if (RigLost() || (_cleanupOwed && !_renderClaim.Held)) ForceAbort("a scene unloaded under the rig"); } catch { } }'),
    ("render", RECLAIM): '{ if (!_cleanupOwed || _renderClaim.Held) return; ForceAbort("reclaimed a run that did not unwind"); }',
    ("render", ENSURE_SCENE_HOOK): "{ if (_sceneHooked) return; try { SceneManager.sceneUnloaded += OnSceneUnloaded; _sceneHooked = true; } catch { } }",
    ("render", RIG_LOST): ("{ if (Gone(_clone) || Gone(_holdable) || Gone(_ground) || Gone(_camGO)) return true; "
                           "foreach (var u in _unparented) if (Gone(u)) return true; return false; }"),
    ("render", GONE): "{ return !ReferenceEquals(o, null) && o == null; }",
    ("render", RENDERING): "{ get { return _renderClaim.Held; } }",
    ("render", UPLOAD_IN_FLIGHT): "{ get { return _uploadClaim.Held; } }",
    ("grade", OWN): "{ if (o != null) _gradeObjs.Add(o); return o; }",
    ("grade", DESTROY_GRADE_OBJECTS): (
        "{ for (int i = _gradeObjs.Count - 1; i >= 0; i--) { var o = _gradeObjs[i]; try { if (o == null) continue; "
        "var go = o as GameObject; if (go != null) { var cam = go.GetComponent<Camera>(); if (cam != null) cam.targetTexture = null; } "
        "var rt = o as RenderTexture; if (rt != null) rt.Release(); UnityEngine.Object.Destroy(o); } catch { } } _gradeObjs.Clear(); }"),
    ("grade", START_LIGHT_PROBE): "{ if (_lightProbeOn) return; _lightProbeSeen.Clear(); Camera.onPreRender += OnLightProbe; _lightProbeOn = true; }",
    ("grade", STOP_LIGHT_PROBE): "{ if (!_lightProbeOn) return; Camera.onPreRender -= OnLightProbe; _lightProbeOn = false; }",
}


def mechanism_blocks(sources: dict) -> dict:
    """Every pinned mechanism block and the host's OnDestroy, read once."""
    blocks = {(key, sig): cs_block(sources[key], sig) for key, sig in MECHANISM_BODIES}
    blocks[("plugin", ON_DESTROY)] = cs_block(sources["plugin"], ON_DESTROY)
    return blocks


def mechanism_problems(blocks: dict) -> list:
    problems = []
    for (key, sig), want in MECHANISM_BODIES.items():
        got = _norm(strip_comments_only(blocks[(key, sig)]))
        if got != _norm(want):
            problems.append(f"{sig}: {got[:200]!r}")
    on_destroy = blocks[("plugin", ON_DESTROY)]
    om, oc = mask_code(on_destroy), strip_comments_only(on_destroy)
    first = _texts(oc, inner(om, body_span(om)))[:1]
    if first != ["try { PortraitRender.OnHostDestroyed(this); } catch { }"]:
        problems.append(f"the host's OnDestroy does not release the renderer first: {first}")
    return problems


# The lifecycle state the mechanisms rest on, counted method by method: the
# owed-cleanup flag, the log hook, the claim calls, the scene hook, the flags
# and subscriptions the pinned mechanisms own, and the rig's references and the
# objects they hold. Each pattern maps to its count inside each method named,
# and its file holds exactly their sum, so it occurs in no other method. A
# count says how often and in which method, not where in it: the pinned
# bodies, statement lists and runs say where.
LIFECYCLE_COUNTS = {
    ("render", r"\b_cleanupOwed\s*=\s*true\s*;"): {PRODUCT_RUN: 1, RUN: 1},
    ("render", r"\b_cleanupOwed\s*=\s*false\s*;"): {FORCE_ABORT: 1, PRODUCT_RUN: 1, RUN: 1},
    ("render", r"\b_cleanupOwed\s*=(?!=)"): {FORCE_ABORT: 1, PRODUCT_RUN: 2, RUN: 2},
    ("grade", r"\b_cleanupOwed\s*=\s*true\s*;"): {GRADE_BAKE_RUN: 1, GRADE_SWATCH_RUN: 1},
    ("grade", r"\b_cleanupOwed\s*=\s*false\s*;"): {GRADE_BAKE_RUN: 1, GRADE_SWATCH_RUN: 1},
    ("grade", r"\b_cleanupOwed\s*=(?!=)"): {GRADE_BAKE_RUN: 2, GRADE_SWATCH_RUN: 2},
    ("render", r"\blogMessageReceived\s*\+="): {PRODUCT_RUN: 1, RUN: 1},
    ("render", r"\blogMessageReceived\s*-="): {FORCE_ABORT: 1, PRODUCT_RUN: 2, RUN: 2},
    ("render", r"\blogMessageReceived\b"): {FORCE_ABORT: 1, PRODUCT_RUN: 3, RUN: 3},
    ("grade", r"\blogMessageReceived\b"): {},
    ("render", r"\b_renderClaim\s*\.\s*Take\s*\("): {DEV_RUN: 3, START_PRODUCT: 1},
    ("render", r"\b_renderClaim\s*\.\s*Drop\s*\("): {PRODUCT_RUN: 1, RUN: 1},
    ("render", r"\b_renderClaim\s*\.\s*Clear\s*\("): {FORCE_ABORT: 1},
    ("grade", r"\b_renderClaim\s*\.\s*Drop\s*\("): {GRADE_BAKE_RUN: 1, GRADE_SWATCH_RUN: 1},
    ("grade", r"\b_renderClaim\s*\.\s*(?:Take|Clear)\s*\("): {},
    ("render", r"\b_uploadClaim\s*\.\s*Take\s*\("): {UPLOAD: 1},
    ("render", r"\b_uploadClaim\s*\.\s*Drop\s*\("): {UPLOAD: 1},
    ("render", r"\b_uploadClaim\s*\.\s*Clear\s*\("): {},
    ("grade", r"\b_uploadClaim\b"): {},
    ("render", r"\bEnsureSceneHook\s*\(\s*\)\s*;"): {DEV_RUN: 1, START_PRODUCT: 1},
    ("render", r"\b_sceneHooked\s*=(?!=)"): {ENSURE_SCENE_HOOK: 1},
    ("render", r"\bsceneUnloaded\s*\+="): {ENSURE_SCENE_HOOK: 1},
    ("render", r"\bsceneUnloaded\s*-="): {},
    ("grade", r"\b_lightProbeOn\s*=(?!=)"): {START_LIGHT_PROBE: 1, STOP_LIGHT_PROBE: 1},
    ("grade", r"\bonPreRender\s*\+=\s*OnLightProbe\b"): {START_LIGHT_PROBE: 1},
    ("grade", r"\bonPreRender\s*-=\s*OnLightProbe\b"): {STOP_LIGHT_PROBE: 1},
    ("render", r"\b_clone\s*=(?!=)"): {PRODUCT_RUN: 1, RUN: 1, TEARDOWN: 1},
    ("render", r"\b_root\s*=(?!=)"): {PRODUCT_RUN: 1, RUN: 1, BUILD_RIG: 1, TEARDOWN: 1},
    ("render", r"\b_hold\s*=(?!=)"): {AFTER_ACTIVATE: 1, TEARDOWN: 1},
    ("render", r"\b_holdable\s*=(?!=)"): {AFTER_ACTIVATE: 1, TEARDOWN: 1},
    ("render", r"\b_ground\s*=(?!=)"): {MAKE_GROUND: 1, TEARDOWN: 1},
    ("render", r"\b_camGO\s*=(?!=)"): {MAKE_CAMERA: 1, TEARDOWN: 1},
    ("render", r"\b_rt\s*=(?!=)"): {MAKE_CAMERA: 1, TEARDOWN: 1},
    ("render", r"\b_unparented\s*\.\s*(?!Contains\b|Count\b)\w+"): {BUILD_RIG: 2, TEARDOWN: 1},
    ("render", r"\b_madeMats\s*\.\s*(?!Contains\b|Count\b)\w+"): {SWAP_UNLIT: 1, TEARDOWN: 1},
    ("render", r"\bnew\s+GameObject\s*\("): {BUILD_RIG: 1, MAKE_GROUND: 1, MAKE_CAMERA: 1},
    ("render", r"\bnew\s+RenderTexture\s*\("): {MAKE_CAMERA: 1},
    ("render", r"\bnew\s+Material\s*\("): {SWAP_UNLIT: 1},
    ("render", r"\bInstantiate\s*[<(]"): {BUILD_RIG: 1},
}
PARTIAL_RENDER = r"\bpartial\s+class\s+PortraitRender\b"


def _masked_block(text: str, signature: str) -> str:
    """The masked text of cs_block(text, signature), off the text's one mask."""
    a, b = block_span(text, signature)
    return mask_code(text)[a:b]


def lifecycle_count_problems(sources: dict) -> list:
    problems = []
    for (key, pattern), per_method in LIFECYCLE_COUNTS.items():
        for sig, want in per_method.items():
            n = len(re.findall(pattern, _masked_block(sources[key], sig)))
            if n != want:
                problems.append(f"{sig}: {pattern} occurs {n} times, want {want}")
        total, want = len(re.findall(pattern, mask_code(sources[key]))), sum(per_method.values())
        if total != want:
            problems.append(f"{key}: {pattern} occurs {total} times in the file, want {want}, all in the methods named")
    return problems


def partial_render_problems(files: dict) -> list:
    """No plugin file but the renderer's two declares a part of the renderer,
    so the counts above cover every method that can reach its state."""
    return [f"{name} declares a part of PortraitRender" for name, text in files.items()
            if "PortraitRender" in text and re.search(PARTIAL_RENDER, mask_code(text))]


# The lifecycle writes whose place is the point, each a run of consecutive
# statements of one statement list, found once in its method.
LIFECYCLE_RUNS = (
    ("ProductRun owes its cleanup as it hooks the log", "render", PRODUCT_RUN, True,
     ["_cleanupOwed = true;", "Application.logMessageReceived -= OnLog;", "Application.logMessageReceived += OnLog;"]),
    ("Run owes its cleanup as it hooks the log", "render", RUN, True,
     ["_cleanupOwed = true;", "Application.logMessageReceived -= OnLog;", "Application.logMessageReceived += OnLog;"]),
    ("ProductRun registers its clone as it unparents it", "render", PRODUCT_RUN, False,
     ["clone.transform.SetParent(null, true);", "_clone = clone;", "UnityEngine.Object.Destroy(_root);", "_root = null;"]),
    ("Run registers its clone as it unparents it", "render", RUN, False,
     ["clone.transform.SetParent(null, true);", "_clone = clone;", "UnityEngine.Object.Destroy(_root);", "_root = null;"]),
    ("BuildRig registers its root as it makes it", "render", BUILD_RIG, False, ['_root = new GameObject("CR_PortraitRoot");']),
    ("BuildRig registers every Unparent carrier", "render", BUILD_RIG, False,
     ["_unparented.Clear();",
      'foreach (var c in clone.GetComponentsInChildren<Component>(true)) if (c != null && c.GetType().Name == "Unparent" '
      "&& !_unparented.Contains(c.gameObject)) _unparented.Add(c.gameObject);"]),
    ("AfterActivate registers the holder and its gun as scene instances only", "render", AFTER_ACTIVATE, False,
     ["bool instance = h != null && h.gameObject.scene.IsValid();", "_hold = instance ? hold : null;", "_holdable = instance ? h.gameObject : null;"]),
    ("MakeGround registers the ground as it makes it", "render", MAKE_GROUND, False, ['_ground = new GameObject("CR_PortraitGround");']),
    ("MakeCamera registers the camera as it makes it", "render", MAKE_CAMERA, False, ['_camGO = new GameObject("CR_PortraitCam");']),
    ("MakeCamera registers the render texture as it makes it", "render", MAKE_CAMERA, False, ["_rt = new RenderTexture(size, size, 24);"]),
)
UPLOAD_DROP_FIRST = "(ok, resp) => { _uploadClaim.Drop(ugen);"


def lifecycle_run_problems(sources: dict) -> list:
    problems = []
    for label, key, sig, top, want in LIFECYCLE_RUNS:
        problems += run_problems(label, cs_block(sources[key], sig), want, top=top)
    if UPLOAD_DROP_FIRST not in _norm(_masked_block(sources["render"], UPLOAD)):
        problems.append("Upload's callback does not drop its claim before anything else")
    return problems


def test_the_host_and_a_scene_unload_force_abort_everything():
    sources = _sources()
    blocks = mechanism_blocks(sources)
    assert mechanism_problems(blocks) == []
    # this module's one-mask cs_block is _cs_structure's, on every block the
    # lifecycle checks read, on a text whose comment and literal carry the
    # signature, and on a signature found twice, never, or with no block
    read = {(key, sig) for (key, _), per_method in LIFECYCLE_COUNTS.items() for sig in per_method}
    read |= {(key, sig) for _, key, sig, _, _ in LIFECYCLE_RUNS} | {("render", UPLOAD)}
    for key, sig in sorted(read):
        assert cs_block(sources[key], sig) == library_cs_block(sources[key], sig), sig
    decoy = 'class A {\n    // void M() { }\n    string s = "void M() {";\n    void M() { if (x) { y(); } }\n}\n'
    assert cs_block(decoy, "void M()") == library_cs_block(decoy, "void M()") == "{ if (x) { y(); } }"
    for text in (decoy.replace("}\n}", "}\n    void M() { }\n}"), decoy.replace("void M() { if", "void K() { if"), "void M();"):
        for reader in (cs_block, library_cs_block):
            with pytest.raises(CsParseError):
                reader(text, "void M()")
    assert lifecycle_count_problems(sources) == []
    assert lifecycle_run_problems(sources) == []
    others = {p.name: p.read_text(encoding="utf-8") for p in sorted(PLUGIN.glob("*.cs")) if p.name not in (RENDER_CS.name, GRADE_CS.name)}
    assert len(others) > 50 and partial_render_problems(others) == []
    claim = blocks[("render", CLAIM)]
    assert sorted(_return_terms(cs_block(claim, "internal bool Held {"))) == sorted(["_host != null", "Time.realtimeSinceStartup <= _until"])
    assert sorted(_return_terms(cs_block(claim, "internal bool HeldBy(MonoBehaviour host)"))) == sorted(
        ["!ReferenceEquals(host, null)", "ReferenceEquals(_host, host)", "Time.realtimeSinceStartup <= _until"])
    # negative controls, one per mechanism: the claim that never expires, a
    # host that holds nothing, a generation every take shares, the rig never
    # lost, the scene never hooked, a force-abort that keeps the grade objects
    # while a claim is held, a teardown skipped, a grade object never
    # destroyed, the light probe never unsubscribed, the renderer's host hook
    # after something that can throw, a busy getter that reads no claim (GL4,
    # GL5), a grade object never registered (N03); each mutates its own block
    controls = (
        ("render", RENDERING, "return _renderClaim.Held;", "return false;"),
        ("render", UPLOAD_IN_FLIGHT, "return _uploadClaim.Held;", "return false;"),
        ("grade", OWN, "if (o != null) _gradeObjs.Add(o); ", ""),
        ("render", CLAIM, "internal bool Held { get { return _host != null && Time.realtimeSinceStartup <= _until; } }",
         "internal bool Held { get { return _host != null; } }"),
        ("render", CLAIM, "return !ReferenceEquals(host, null) && ReferenceEquals(_host, host) && Time.realtimeSinceStartup <= _until;",
         "return false;"),
        ("render", CLAIM, "return ++_gen;", "_gen = 1; return _gen;"),
        ("render", RIG_LOST, "if (Gone(_clone) || Gone(_holdable) || Gone(_ground) || Gone(_camGO)) return true;", "if (Gone(_clone)) return true;"),
        ("render", RIG_LOST, "foreach (var u in _unparented) if (Gone(u)) return true;\n            return false;", "return false;"),
        ("render", ENSURE_SCENE_HOOK, "try { SceneManager.sceneUnloaded += OnSceneUnloaded; _sceneHooked = true; } catch { }", "try { _sceneHooked = true; } catch { }"),
        ("render", ENSURE_SCENE_HOOK, "if (_sceneHooked) return;", "if (!_sceneHooked) return;"),
        ("render", FORCE_ABORT, "try { DestroyGradeObjects(); } catch { }", "try { if (!_renderClaim.Held) DestroyGradeObjects(); } catch { }"),
        ("render", FORCE_ABORT, "try { Teardown(new StringBuilder()); } catch { }", "try { if (_clone != null) Teardown(new StringBuilder()); } catch { }"),
        ("render", ON_HOST_DESTROYED, "if (_renderClaim.HeldBy(host) || (_cleanupOwed && !_renderClaim.Held))", "if (_renderClaim.HeldBy(host))"),
        ("render", ON_SCENE_UNLOADED, "if (RigLost() || (_cleanupOwed && !_renderClaim.Held))", "if (RigLost())"),
        ("grade", DESTROY_GRADE_OBJECTS, "                    UnityEngine.Object.Destroy(o);\n", ""),
        ("grade", STOP_LIGHT_PROBE, "            Camera.onPreRender -= OnLightProbe;\n", ""),
        ("plugin", ON_DESTROY, "            try { PortraitRender.OnHostDestroyed(this); } catch { }\n",
         "            MainMenuInjector.Reset();\n            try { PortraitRender.OnHostDestroyed(this); } catch { }\n"),
    )
    for key, sig, old, new in controls:
        mutated = dict(blocks)
        mutated[(key, sig)] = _mut(blocks[(key, sig)], old, new)
        want = "OnDestroy" if key == "plugin" else sig
        assert any(want in x for x in mechanism_problems(mutated)), (key, new)
    # negative controls on the counts: a second probe subscription, a scene
    # flag written outside its hook; the owed cleanup forgiven right after it
    # is owed (GL1a), by every tick (GL1b, N05), after the rig is built (GL1c),
    # in both grade runs (GL7b); the log hook subscribed twice (GL3); a lever
    # that does not hook the scene (GL2, N04); a claim dropped before the
    # settle (GL6), cleared outside ForceAbort; an upload claim never dropped
    # or taken twice; a carrier list, a ground reference or a camera written
    # outside their methods; a rig object made in a method that registers none
    product_top = ("            _cleanupOwed = true;\n            Application.logMessageReceived -= OnLog;\n"
                   "            Application.logMessageReceived += OnLog;\n            float t0 = Time.realtimeSinceStartup;\n            _legSummary")
    count_controls = (
        ("grade", "Camera.onPreRender += OnLightProbe;", "Camera.onPreRender += OnLightProbe; Camera.onPreRender += OnLightProbe;", "onPreRender"),
        ("render", "            _renderClaim.Clear();\n", "            _renderClaim.Clear();\n            _sceneHooked = false;\n", "_sceneHooked"),
        ("render", product_top, product_top.replace("_cleanupOwed = true;\n", "_cleanupOwed = true;\n            _cleanupOwed = false;\n"), PRODUCT_RUN),
        ("render", "        internal static void Tick()\n        {\n            Reclaim();",
         "        internal static void Tick()\n        {\n            _cleanupOwed = false;\n            Reclaim();", "in the file"),
        ("render", "                AfterActivate(rep, clone, data, PickFace(preset, rep), faceOverride);",
         "                _cleanupOwed = false;\n                AfterActivate(rep, clone, data, PickFace(preset, rep), faceOverride);", RUN),
        ("grade", "            _cleanupOwed = true;\n", "            _cleanupOwed = true;\n            _cleanupOwed = false;\n", GRADE_SWATCH_RUN),
        ("render", product_top, product_top.replace("+= OnLog;\n", "+= OnLog;\n            Application.logMessageReceived += OnLog;\n"), PRODUCT_RUN),
        ("render", '            spec = (spec ?? "").Trim();\n            EnsureSceneHook();\n', '            spec = (spec ?? "").Trim();\n', DEV_RUN),
        ("render", "                int colour = ApplyColorExact(rep, clone, inp.colorSku, inp.colorHex);",
         "                _renderClaim.Drop(gen);\n                int colour = ApplyColorExact(rep, clone, inp.colorSku, inp.colorHex);", PRODUCT_RUN),
        ("render", "            if (!_cleanupOwed || _renderClaim.Held) return;", "            if (!_cleanupOwed || _renderClaim.Held) { _renderClaim.Clear(); return; }", "in the file"),
        ("render", "                _uploadClaim.Drop(ugen);\n", "", UPLOAD),
        ("render", '            LastResult = "uploading";\n', '            LastResult = "uploading";\n            _uploadClaim.Take(Plugin.Instance, UPLOAD_BUDGET);\n', UPLOAD),
        ("render", "            _renderClaim.Clear();\n", "            _renderClaim.Clear();\n            _unparented.Clear();\n", "_unparented"),
        ("render", "            _renderClaim.Clear();\n", "            _renderClaim.Clear();\n            _ground = null;\n", "_ground"),
        ("render", '            _camGO = new GameObject("CR_PortraitCam");', '            _camGO = new GameObject("CR_PortraitCam"); _camGO = new GameObject("CR_PortraitCam");', MAKE_CAMERA),
        ("render", "            _renderClaim.Clear();\n", '            _renderClaim.Clear();\n            new GameObject("CR_Stray");\n', "in the file"),
    )
    for key, old, new, want in count_controls:
        mutated = dict(sources, **{key: _mut(sources[key], old, new)})
        assert any(want in x for x in lifecycle_count_problems(mutated)), (key, new)
    # another file declaring a part of the renderer, and one naming it only in a comment
    assert partial_render_problems({"Stray.cs": "namespace X { internal static partial class PortraitRender { } }"}) == [
        "Stray.cs declares a part of PortraitRender"]
    assert partial_render_problems({"Note.cs": "// internal static partial class PortraitRender\nnamespace X { }"}) == []
    # negative controls on the runs: the clone registered after the next yield
    # (N02), the Unparent carriers never registered (N06), the gun registered
    # whether or not it is a scene instance, the log hooked before the cleanup
    # is owed, the camera made before it is registered, the upload callback
    # leaving before it drops its claim
    n02 = _mut(_mut(sources["render"],
                    "                clone.transform.SetParent(null, true);\n                _clone = clone;\n"
                    "                UnityEngine.Object.Destroy(_root); _root = null;\n                if (!AfterActivate(rep, clone, data, inp.face, null))",
                    "                clone.transform.SetParent(null, true);\n"
                    "                UnityEngine.Object.Destroy(_root); _root = null;\n                if (!AfterActivate(rep, clone, data, inp.face, null))"),
               "                if (Stale(key)) { Abandon(key); yield break; }\n                int colour = ApplyColorExact(",
               "                if (Stale(key)) { Abandon(key); yield break; }\n                _clone = clone;\n                int colour = ApplyColorExact(")
    run_controls = (
        (n02, "ProductRun registers its clone"),
        (_mut(sources["render"], "!_unparented.Contains(c.gameObject)) _unparented.Add(c.gameObject);", "!_unparented.Contains(c.gameObject)) { }"),
         "every Unparent carrier"),
        (_mut(sources["render"], "_holdable = instance ? h.gameObject : null;", "_holdable = h != null ? h.gameObject : null;"), "scene instances only"),
        (_mut(sources["render"], "            _cleanupOwed = true;\n            Application.logMessageReceived -= OnLog;\n            Application.logMessageReceived += OnLog;\n",
              "            Application.logMessageReceived -= OnLog;\n            Application.logMessageReceived += OnLog;\n            _cleanupOwed = true;\n"),
         "owes its cleanup as it hooks the log"),
        (_mut(sources["render"], '            _camGO = new GameObject("CR_PortraitCam");', '            var made = new GameObject("CR_PortraitCam");\n            _camGO = made;'),
         "registers the camera"),
        (_mut(sources["render"], "                _uploadClaim.Drop(ugen);\n                if (Stale(key)) { Abandon(key); return; }\n",
              "                if (Stale(key)) { Abandon(key); return; }\n                _uploadClaim.Drop(ugen);\n"),
         "drop its claim before anything else"),
    )
    for render, want in run_controls:
        assert any(want in x for x in lifecycle_run_problems(dict(sources, render=render))), want


# ── the real source: what a grade lever makes ───────────────────────────────

# The makes this check finds in PortraitGrade.cs: a GameObject, a texture, a
# material, a mesh, an asset instance, a sprite, a copy. A component added to a
# GameObject is not one of them: it is destroyed with its GameObject.
GRADE_MAKES = re.compile(
    r"\bnew\s+(?:GameObject|RenderTexture|Material|Texture2D|Texture3D|Cubemap|Mesh)\s*\("
    r"|\bScriptableObject\s*\.\s*CreateInstance\s*[<(]"
    r"|\bSprite\s*\.\s*Create\s*\("
    r"|(?:\bUnityEngine\s*\.\s*)?(?:\bObject\s*\.\s*)?\bInstantiate\s*[<(]")
# The objects not registered with Own, each a texture made in the try clause of
# a try directly preceded by the null declaration of the local that holds it,
# destroyed by that try's finally, and assigned nothing else.
GRADE_TRANSIENT = (READ_TARGET, ENCODE_PNG_WH, MEASURE_SWATCHES)
# Every mention of the grade objects' registry, in code or in a string, in the
# renderer's two files, as (source key, line), once per mention: its
# declaration, Own's add, and DestroyGradeObjects' walk and clear (Own and
# DestroyGradeObjects are pinned whole in MECHANISM_BODIES).
GRADE_REGISTRY_MENTIONS = {"_gradeObjs": [
    ("grade", "private static readonly List<UnityEngine.Object> _gradeObjs = new List<UnityEngine.Object>();"),
    ("grade", "private static T Own<T>(T o) where T : UnityEngine.Object { if (o != null) _gradeObjs.Add(o); return o; }"),
    ("grade", "for (int i = _gradeObjs.Count - 1; i >= 0; i--)"),
    ("grade", "var o = _gradeObjs[i];"),
    ("grade", "_gradeObjs.Clear();"),
]}


def _made_end(m: str, hit) -> int:
    """The offset just past the call a GRADE_MAKES match opens."""
    j = hit.end() - 1
    if m[j] == "<":
        j = _skip_ws(m, _close(m, j, "<", ">"))
    return _close(m, j, "(", ")")


def _owned(m: str, hit) -> bool:
    """The made object is the whole argument of an `Own(...)` call."""
    k = hit.start() - 1
    while k >= 0 and m[k].isspace():
        k -= 1
    if k < 0 or m[k] != "(" or not re.search(r"(?<![\w.])Own\s*$", m[max(0, k - 40):k]):
        return False
    e = _skip_ws(m, _made_end(m, hit))
    return e < len(m) and m[e] == ")"


def transient_problems(sig: str, block: str) -> list:
    m, code = mask_code(block), strip_comments_only(block)
    hits = list(GRADE_MAKES.finditer(m))
    if len(hits) != 1:
        return [f"{sig}: want one object made, found {len(hits)}"]
    at = hits[0].start()
    made = re.fullmatch(r"(\w+) = new Texture2D\(.*\);", leaf_code(m, code, at))
    if not made:
        return [f"{sig}: the texture is not made by an assignment of its own: {leaf_code(m, code, at)[:80]!r}"]
    name = made.group(1)
    top = inner(m, body_span(m))
    idx = next(i for i, s in enumerate(top) if s[0] <= at < s[1])
    kinds = [k for k, _, _ in slots(m, top[idx])]
    if kinds[:1] != ["try"] or "finally" not in kinds:
        return [f"{sig}: the texture is not made in a try with a finally"]
    problems = []
    body = slots(m, top[idx])[0][2]
    if not body[0] <= at < body[1]:
        problems.append(f"{sig}: the texture is not made in the try clause")
    if idx == 0 or _texts(code, top)[idx - 1] != f"Texture2D {name} = null;":
        problems.append(f"{sig}: `Texture2D {name} = null;` does not directly precede the try")
    if f"if ({name} != null) UnityEngine.Object.Destroy({name});" not in _texts(code, clause(m, top[idx], "finally")[1]):
        problems.append(f"{sig}: the try's finally does not destroy {name}")
    if len(re.findall(r"\b" + re.escape(name) + r"\s*=(?!=)", m)) != 2:
        problems.append(f"{sig}: {name} is assigned other than its null declaration and the texture")
    return problems


def grade_made_problems(grade: str) -> list:
    """Every make GRADE_MAKES finds in PortraitGrade.cs is registered with Own
    as it is made, into the registry DestroyGradeObjects (pinned) destroys,
    except the transient textures, each destroyed where it is made. What else
    may mention the registry is GRADE_REGISTRY_MENTIONS, checked beside this."""
    m = mask_code(grade)
    loose = [h for h in GRADE_MAKES.finditer(m) if not _owned(m, h)]
    problems = []
    if len(loose) != len(GRADE_TRANSIENT):
        problems.append(f"{len(loose)} objects made outside Own(...), want {len(GRADE_TRANSIENT)}: "
                        + "; ".join(_norm(m[h.start():h.start() + 50]) for h in loose))
    for sig in GRADE_TRANSIENT:
        problems += transient_problems(sig, cs_block(grade, sig))
    return problems


def test_every_grade_object_is_owned_or_destroyed_where_it_is_made():
    grade = GRADE_CS.read_text(encoding="utf-8")
    assert grade_made_problems(grade) == []
    m = mask_code(grade)
    assert len(list(GRADE_MAKES.finditer(m))) == 18 and len(re.findall(r"(?<![\w.])Own\s*\(", m)) == 15
    # the registry: exactly GRADE_REGISTRY_MENTIONS in the two files, and none
    # outside a comment in any other plugin file
    render = RENDER_CS.read_text(encoding="utf-8")
    others = {p.name: p.read_text(encoding="utf-8") for p in sorted(PLUGIN.glob("*.cs")) if p.name not in (RENDER_CS.name, GRADE_CS.name)}
    assert mention_problems(GRADE_REGISTRY_MENTIONS, {"render": render, "grade": grade}, others) == []
    # negative controls: the registry cleared by a method of its own; the
    # registry read by name from another plugin file
    decl = "        private static readonly List<UnityEngine.Object> _gradeObjs = new List<UnityEngine.Object>();\n"
    forget = _mut(grade, decl, decl + "        private static void StrayForget() { _gradeObjs.Clear(); }\n")
    assert any(x.startswith("_gradeObjs is mentioned by") for x in mention_problems(GRADE_REGISTRY_MENTIONS, {"render": render, "grade": forget}, {}))
    by_name = {"Stray.cs": 'class S { static object R() { return AccessTools.Field(typeof(PortraitRender), "_gradeObjs").GetValue(null); } }'}
    assert "Stray.cs mentions _gradeObjs" in mention_problems(GRADE_REGISTRY_MENTIONS, {"render": render, "grade": grade}, by_name)
    # negative controls: the bake volume made outside Own (N14), a sprite and a
    # copy made outside Own, an Own whose argument is more than the object, a
    # transient texture never destroyed, handed away before its finally, or
    # joined by a second object
    controls = (
        ('var volGO = Own(new GameObject("CR_GradeBakeVolume"));', 'var volGO = new GameObject("CR_GradeBakeVolume");', "4 objects made outside"),
        ("var sprite = Own(Sprite.Create(tex, new Rect(0, 0, 4, 4), new Vector2(0.5f, 0.5f), 4f, 0, SpriteMeshType.FullRect));",
         "var sprite = Sprite.Create(tex, new Rect(0, 0, 4, 4), new Vector2(0.5f, 0.5f), 4f, 0, SpriteMeshType.FullRect);", "4 objects made outside"),
        ("Own(UnityEngine.Object.Instantiate(src.grades[0]))", "UnityEngine.Object.Instantiate(src.grades[0])", "4 objects made outside"),
        ("sr.sharedMaterial = Own(new Material(sh));", "sr.sharedMaterial = Own(sh != null ? new Material(sh) : null);", "4 objects made outside"),
        ("            finally { if (t != null) UnityEngine.Object.Destroy(t); }", "            finally { }", "does not destroy t"),
        ("                tex.Apply();\n                return tex.GetPixels32();", "                tex.Apply();\n                var px = tex.GetPixels32(); tex = null; return px;",
         "assigned other than"),
        ("                t.SetPixels32(px); t.Apply();", "                t.SetPixels32(px); t.Apply(); Texture2D.Destroy(new Texture2D(1, 1));", "want one object made"),
    )
    for old, new, want in controls:
        assert any(want in x for x in grade_made_problems(_mut(grade, old, new))), new


def reclaim_first_problems(block: str) -> list:
    """`Reclaim();` is one statement of the method's body, with no exit
    before it, and ends before the method first reads `Rendering`."""
    m = mask_code(block)
    calls = [x.start() for x in re.finditer(r"\bReclaim\s*\(\s*\)\s*;", m)]
    if len(calls) != 1:
        return [f"want one `Reclaim();`, found {len(calls)}"]
    top = inner(m, body_span(m))
    idx = next((i for i, s in enumerate(top) if s[0] == calls[0]), None)
    if idx is None:
        return ["`Reclaim();` is not a statement of the method's body"]
    problems = [f"an exit before `Reclaim();`: {e!r}" for s in top[:idx] for e in exits_in(m, s)]
    reads = [x.start() for x in re.finditer(r"\bRendering\b", m)]
    if not reads:
        problems.append("the method reads no `Rendering`")
    elif min(reads) < top[idx][1]:
        problems.append("`Rendering` is read before `Reclaim();`")
    return problems


def test_every_entry_reclaims_before_it_reads_the_claim():
    for sig in (DEV_RUN, TICK, START_PRODUCT):
        block = cs_block(RENDER_CS, sig)
        assert reclaim_first_problems(block) == [], sig
    # negative controls: removed, after the read, under a condition, after an exit
    block = cs_block(RENDER_CS, TICK)
    assert any("found 0" in x for x in reclaim_first_problems(_mut(block, "            Reclaim();\n", "")))
    assert any("read before" in x for x in reclaim_first_problems(
        _mut(_mut(block, "            Reclaim();\n", ""), "            if (!_pendingCheck || Rendering || UploadInFlight) return;\n",
             "            if (!_pendingCheck || Rendering || UploadInFlight) return;\n            Reclaim();\n")))
    assert any("not a statement" in x for x in reclaim_first_problems(_mut(block, "            Reclaim();\n", "            if (_pendingCheck) Reclaim();\n")))
    assert any("exit before" in x for x in reclaim_first_problems(_mut(block, "            Reclaim();\n", "            if (_refreshAt > 1e9f) return;\n            Reclaim();\n")))


def owed_first_problems(block: str) -> list:
    """`_cleanupOwed = true;` is one statement of the coroutine's body, with
    no exit before it, before any yield, and before the try whose finally
    settles it."""
    m = mask_code(block)
    owed = [x.start() for x in re.finditer(r"\b_cleanupOwed\s*=\s*true\s*;", m)]
    if len(owed) != 1:
        return [f"want one `_cleanupOwed = true;`, found {len(owed)}"]
    top = inner(m, body_span(m))
    idx = next((i for i, s in enumerate(top) if s[0] == owed[0]), None)
    if idx is None:
        return ["`_cleanupOwed = true;` is not a statement of the coroutine's body"]
    problems = [f"an exit before `_cleanupOwed = true;`: {e!r}" for s in top[:idx] for e in exits_in(m, s)]
    first_yield = re.search(r"\byield\b", m)
    if first_yield is None or first_yield.start() < owed[0]:
        problems.append("a yield comes before `_cleanupOwed = true;`")
    tries = [i for i, s in enumerate(top) if any(k == "finally" for k, _, _ in slots(m, s))]
    if len(tries) != 1 or tries[0] < idx:
        problems.append("the try whose finally settles the cleanup does not follow it")
    return problems


@pytest.mark.parametrize("source,signature", [(RENDER_CS, PRODUCT_RUN), (RENDER_CS, RUN), (GRADE_CS, GRADE_BAKE_RUN), (GRADE_CS, GRADE_SWATCH_RUN)])
def test_every_run_owes_its_cleanup_before_its_first_yield(source, signature):
    block = cs_block(source, signature)
    assert owed_first_problems(block) == []
    # negative controls: removed, after the first yield, under a condition
    assert any("found 0" in x for x in owed_first_problems(_mut(block, "            _cleanupOwed = true;\n", "")))
    late = _mut(_mut(block, "            _cleanupOwed = true;\n", ""), "_renderClaim.Beat(gen, ", "_cleanupOwed = true; _renderClaim.Beat(gen, ", 1)
    assert owed_first_problems(late) != []
    assert any("not a statement" in x for x in owed_first_problems(_mut(block, "            _cleanupOwed = true;\n", "            if (gen > 0) _cleanupOwed = true;\n")))


TEARDOWN_STATEMENTS = [
    r"""try { PlayerColorCosmetic.RevertPlayer(PORTRAIT_ACTOR); } catch (Exception ex) { rep.Append("colour revert threw: ").Append(ex.Message).Append('\n'); }""",
    r"""try { PlayerEffectCosmetic.ClearForPortrait(_clone != null ? _clone.transform : null, PORTRAIT_ACTOR); } catch (Exception ex) { rep.Append("effect clear threw: ").Append(ex.Message).Append('\n'); }""",
    "try { foreach (var m in _madeMats) if (m != null) UnityEngine.Object.Destroy(m); } catch { }",
    "_madeMats.Clear();",
    "try { if (_camGO != null) { var c = _camGO.GetComponent<Camera>(); if (c != null) c.targetTexture = null; UnityEngine.Object.Destroy(_camGO); } } catch { }",
    "_camGO = null;",
    "try { if (_rt != null) { _rt.Release(); UnityEngine.Object.Destroy(_rt); } } catch { }",
    "_rt = null;",
    "try { if (_holdable != null) UnityEngine.Object.Destroy(_holdable); } catch { }",
    "_holdable = null;",
    "_hold = null;",
    "try { if (_ground != null) UnityEngine.Object.Destroy(_ground); } catch { }",
    "_ground = null;",
    "try { foreach (var u in _unparented) if (u != null) UnityEngine.Object.Destroy(u); } catch { }",
    "_unparented.Clear();",
    "try { if (_clone != null) UnityEngine.Object.Destroy(_clone); } catch { }",
    "_clone = null;",
    "try { if (_root != null) UnityEngine.Object.Destroy(_root); } catch { }",
    "_root = null;",
    "_legs.Clear();",
    "_groundTop = float.NaN;",
    "_pinned.Clear();",
    "_leftOut.Clear();",
    "try { StopLightProbe(); } catch { }",
]


def teardown_problems(teardown: str) -> list:
    """Teardown's statements, in order: every release in its own try, every
    reference dropped after its object's release whatever the release did,
    and nothing that can leave early."""
    m, code = mask_code(teardown), strip_comments_only(teardown)
    top = inner(m, body_span(m))
    problems = list_problems("Teardown", _texts(code, top), TEARDOWN_STATEMENTS)
    for s in top:
        problems += [f"Teardown can leave early: {e!r}" for e in exits_in(m, s)]
    return problems


def test_teardown_releases_everything_unconditionally():
    block = cs_block(RENDER_CS, TEARDOWN)
    assert teardown_problems(block) == []
    # negative controls: an early exit (A45), a release removed, a revert under
    # a flag, a reference dropped only when its object still exists
    early = _mut(block, "{\n            try { PlayerColorCosmetic.RevertPlayer", "{\n            if (_clone == null) return;\n            try { PlayerColorCosmetic.RevertPlayer", 1)
    assert any("leave early" in x for x in teardown_problems(early))
    assert any("Teardown: statement 15" in x for x in teardown_problems(
        _mut(block, "            try { if (_clone != null) UnityEngine.Object.Destroy(_clone); } catch { }\n", "")))
    assert teardown_problems(_mut(block, "try { PlayerColorCosmetic.RevertPlayer(PORTRAIT_ACTOR); }",
                                  "try { if (_colorApplied) PlayerColorCosmetic.RevertPlayer(PORTRAIT_ACTOR); }")) != []
    assert any("statement 16" in x for x in teardown_problems(_mut(block, "            _clone = null;\n", "            if (_clone != null) _clone = null;\n")))


FINALLY_GUARDED = {
    PRODUCT_RUN: (RENDER_CS, ("_cleanupOwed = false;", "Application.logMessageReceived -= OnLog;", "Teardown(rep);")),
    RUN: (RENDER_CS, ("_cleanupOwed = false;", "Application.logMessageReceived -= OnLog;", "Teardown(rep);")),
    GRADE_BAKE_RUN: (GRADE_CS, ("_cleanupOwed = false;", "DestroyGradeObjects();")),
    GRADE_SWATCH_RUN: (GRADE_CS, ("_cleanupOwed = false;", "DestroyGradeObjects();")),
}
SUCCESSOR_GUARD = "if (!_renderClaim.HeldByOther(gen))"


def finally_problems(fin: str, releases: tuple) -> list:
    """Each release is a statement of `if (!_renderClaim.HeldByOther(gen))`,
    itself a statement of the finally, with nothing before it that can
    leave; the claim is dropped by a statement of the finally itself."""
    problems = []
    m, code = mask_code(fin), strip_comments_only(fin)
    for stmt in releases:
        hits = [x.start() for x in re.finditer(re.escape(stmt), m)]
        if len(hits) != 1:
            problems.append(f"want one {stmt!r} in finally, found {len(hits)}")
            continue
        path = stmt_path(m, hits[0])
        conds = path_conditions(m, code, hits[0])
        if conds != [SUCCESSOR_GUARD] or len(path) != 2 or path[-1][0][path[-1][1]][0] != hits[0]:
            problems.append(f"{stmt!r} is not a statement of `{SUCCESSOR_GUARD}` in the finally: {conds}")
        problems += [f"{stmt!r} comes after an exit: {e!r}" for e in earlier_exits(m, code, hits[0])]
    drops = [x.start() for x in re.finditer(re.escape("_renderClaim.Drop(gen);"), m)]
    if len(drops) != 1 or len(stmt_path(m, drops[0])) != 1:
        problems.append("the finally does not drop its claim in a statement of its own")
    return problems


@pytest.mark.parametrize("signature", sorted(FINALLY_GUARDED))
def test_a_finally_never_releases_a_successors_objects(signature):
    source, releases = FINALLY_GUARDED[signature]
    fin = finally_block(cs_block(source, signature))
    assert finally_problems(fin, releases) == []
    for new in ("if (true)", "if (_renderClaim.HeldByOther(gen)) { } else", "if (!_renderClaim.HeldByOther(gen)) if (gen > 0)"):
        mutated = _mut(fin, SUCCESSOR_GUARD, new)
        assert any("is not a statement of" in x for x in finally_problems(mutated, releases)), new


# ── the real source: the sweep ──────────────────────────────────────────────

def secs_of_ms(ms: int) -> str:
    whole, frac = ms // 1000, ms % 1000
    return str(whole) if frac == 0 else f"{whole}.{frac:03d}".rstrip("0")


def test_sweep_labels_are_unique_per_length_and_inputs_are_deduplicated():
    labels = [secs_of_ms(ms) for ms in range(100, 60001)]
    assert len(set(labels)) == len(labels)
    assert secs_of_ms(5500) == "5.5" and secs_of_ms(10000) == "10" and secs_of_ms(1234) == "1.234" and secs_of_ms(100) == "0.1"
    code = _norm(strip_comments_only(cs_block(RENDER_CS, SECS_OF_MS)))
    assert "int whole = ms / 1000, frac = ms % 1000;" in code
    assert 'frac.ToString("000", System.Globalization.CultureInfo.InvariantCulture).TrimEnd(\'0\')' in code
    millis = cs_block(RENDER_CS, PARSE_MILLIS)
    assert exits_before(millis, "o.Contains(ms)", "continue;", "o.Add(ms);") == []
    assert "int ms = (int)Math.Round(v * 1000.0);" in _norm(mask_code(millis))
    ints = cs_block(RENDER_CS, PARSE_INTS)
    assert exits_before(ints, "o.Contains(v)", "continue;", "o.Add(v);") == []
    entry = _norm(strip_comments_only(cs_block(RENDER_CS, SWEEP_ENTRY)))
    assert "string secs = SecsOfMs(ms);" in entry
    assert 'string file = "pc_portrait_" + tag + "_sim" + secs + "_s" + salt + ".png";' in entry


# The work a sweep asks for, counted in 64-bit: every length once per salt.
SWEEP_REFUSAL_STATEMENTS = [
    "int saltCount = salts == null ? 1 : salts.Count;",
    "long entries = (long)lengths.Count * saltCount;",
    "long simMs = 0;",
    "foreach (var ms in lengths) simMs += (long)ms * saltCount;",
    'if (size != DEFAULT_SIZE) return "size=" + size + " is not the product size " + DEFAULT_SIZE + " the body measure is calibrated on";',
    'if (entries > SWEEP_MAX_ENTRIES) return entries + " entries (lengths x salts), over the cap of " + SWEEP_MAX_ENTRIES;',
    'if (simMs > SWEEP_MAX_SIM_MS) return SecsOfMs((int)Math.Min(simMs, int.MaxValue)) + " s of particle simulation over all entries, '
    'over the cap of " + SecsOfMs(SWEEP_MAX_SIM_MS) + " s";',
    "return null;",
]
SWEEP_ASK = "string sweepRefused = sweep != null ? SweepRefusal(size, sweep, salts) : null;"


def sweep_cap_problems(refusal: str, run: str) -> list:
    """SweepRefusal's statements; every refusal a non-null string; Run asks
    it for every sweep (`nopin` included) and refuses before the rig is
    built; a `nopin` sweep runs no entry."""
    rm, rc = mask_code(refusal), strip_comments_only(refusal)
    problems = list_problems("SweepRefusal", _texts(rc, inner(rm, body_span(rm))), SWEEP_REFUSAL_STATEMENTS)
    problems += [f"SweepRefusal: {p}" for p in refusal_return_problems(refusal)]
    problems += exits_before(run, "sweepRefused != null", "yield break;", "BuildRig(")
    m, code = mask_code(run), strip_comments_only(run)
    asks = [x.start() for x in re.finditer(re.escape("SweepRefusal("), m)]
    guard = find_guards(run, "sweepRefused != null")
    if len(asks) != 1 or leaf_code(m, code, asks[0]) != SWEEP_ASK:
        problems.append("Run does not ask SweepRefusal for every sweep")
    elif len(guard) == 1:
        (l1, i1), (l2, i2) = list_position(m, asks[0]), list_position(m, guard[0][0])
        if l1 != l2 or i2 != i1 + 1:
            problems.append("Run does not test SweepRefusal's answer right after asking")
    branches = [s for s in all_statements(m, inner(m, body_span(m))) if _norm(code[s[0]:s[1]]).startswith("if (sweep != null")]
    skips = [s for s in branches if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in branches)]
    if len(skips) != 1:
        problems.append(f"want one sweep branch, found {len(skips)}")
    else:
        p, other = _branch(m, code, skips[0], "the nopin skip", "sweep != null && nopin",
                           [r'rep.Append("sweep: skipped (nopin leaves the particles unpinned)\n");'])
        problems += p
        if other is None or len(other) != 1 or if_parts(m, other[0]) is None or \
                _norm(code[if_parts(m, other[0])[0][0]:if_parts(m, other[0])[0][1]]) != "sweep != null":
            problems.append("the sweep's entries do not run only for a pinned sweep")
    return problems


def test_the_sweep_is_refused_over_its_work_cap_before_the_rig_is_built():
    refusal = cs_block(RENDER_CS, SWEEP_REFUSAL)
    run = cs_block(RENDER_CS, RUN)
    assert sweep_cap_problems(refusal, run) == []
    entries, sim_ms, size = render_int("SWEEP_MAX_ENTRIES"), render_int("SWEEP_MAX_SIM_MS"), render_int("DEFAULT_SIZE")
    # the worst sweep the cap admits, against the one the finding measured (64 entries at 2048 px, 60 s each)
    assert entries * size * size <= 24 * 1180 * 1180 < 64 * 2048 * 2048
    assert sim_ms <= 240000 < 64 * 60000
    # negative controls: the size term, the entry count without salts (A48),
    # the simulation sum without salts (B14), a refusal that returns null (A49),
    # the answer ignored, the nopin exemption back, the skip reversed (A68)
    refusal_controls = (
        ("if (size != DEFAULT_SIZE)", "if (size > 4096)", "SweepRefusal: statement 4"),
        ("long entries = (long)lengths.Count * saltCount;", "long entries = lengths.Count;", "SweepRefusal: statement 1"),
        ("simMs += (long)ms * saltCount;", "simMs += ms;", "SweepRefusal: statement 3"),
        ('return entries + " entries (lengths x salts), over the cap of " + SWEEP_MAX_ENTRIES;', "return (string)null;", "may return null"),
    )
    for old, new, want in refusal_controls:
        assert any(want in x for x in sweep_cap_problems(_mut(refusal, old, new), run)), new
    run_controls = (
        ("if (sweepRefused != null)", "if (sweepRefused == \"never\")", "found 0"),
        (SWEEP_ASK, "string sweepRefused = sweep != null && !nopin ? SweepRefusal(size, sweep, salts) : null;", "every sweep"),
        ("if (sweep != null && nopin)", "if (sweep != null && !nopin)", "the nopin skip"),
    )
    for old, new, want in run_controls:
        assert any(want in x for x in sweep_cap_problems(refusal, _mut(run, old, new))), new


def test_the_body_measure_reuses_one_set_of_buffers():
    run = mask_code(cs_block(RENDER_CS, RUN))
    assert run.count("new MeasureBuffers(size)") == 1
    assert run.find("new MeasureBuffers(size)") < run.find("for (int si = 0;")
    for signature in (BODY_LUMINANCE, "private static bool[] Erode(bool[] m, bool[] scratch, int size, int passes)",
                      "private static void LargestComponent(bool[] m, bool[] o, int[] label, int[] queue, int size)"):
        body = mask_code(cs_block(RENDER_CS, signature))
        assert not re.search(r"\bnew\s+(bool|int)\s*\[", body), signature
        assert ".Clone()" not in body, signature
    entry = cs_block(RENDER_CS, SWEEP_ENTRY)
    assert entry_buffer_problems(entry) == []
    # negative controls: a fresh set of buffers per entry (C04), a work array per entry
    assert entry_buffer_problems(_mut(entry, "BodyLuminance(px, buffers,", "BodyLuminance(px, new MeasureBuffers(size),")) != []
    assert entry_buffer_problems(_mut(entry, "int bodyPx; float cx, cyTop;", "int bodyPx; float cx, cyTop; var scratch = new bool[size * size];")) != []


def entry_buffer_problems(entry: str) -> list:
    """A sweep entry measures on the run's buffers and allocates no measure
    buffers or work arrays of its own."""
    m = _norm(mask_code(entry))
    problems = []
    if m.count("double lum = BodyLuminance(px, buffers, out bodyPx, out cx, out cyTop);") != 1 or m.count("BodyLuminance(") != 1:
        problems.append("the entry does not measure on the run's buffers")
    if "new MeasureBuffers(" in m or re.search(r"\bnew\s+(?:bool|int|float|double|byte|Color32)\s*\[", m):
        problems.append("the entry allocates buffers of its own")
    return problems


def test_the_sweep_and_its_restore_pin_the_runs_own_plan():
    run = cs_block(RENDER_CS, RUN)
    m = _norm(mask_code(run))
    assert m.count("PlanParticles(") == 1 and "ParticlePlan plan = nopin ? null : PlanParticles(pinall);" in m
    assert call_texts(run, "PinParticles") == ["PinParticles(rep, plan, PARTICLE_SIM_SECS, 0, psinfo)",
                                               "PinParticles(rep, plan, PARTICLE_SIM_SECS, 0, false)"]
    assert call_texts(run, "PlanParticles") == ["PlanParticles(pinall)"]
    assert "SweepEntry(rep, tsv, buffers, cam, size, tag, devTable, gradeName, plan, sweep[si], salts[ki]);" in m
    assert "var pp = PinParticles(null, plan, ms / 1000f, salt, false);" in _norm(mask_code(cs_block(RENDER_CS, SWEEP_ENTRY)))
    assert "back to the product snapshot" not in run
