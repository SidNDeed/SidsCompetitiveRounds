"""v1.41.0 item 21 - damage and heal numbers: group B, the eighteen
production-span structure invariants (design section 5, rows B1-B14, and
the build round 1 fix rows B15-B18: the correction funnel's feed and the
direct-writer census, the delta-to-emit bridge, the draw and driver wiring,
and the draw budget at saturation).

Every row is one test, and every test does three things in the same run:

* the invariant holds on the PRODUCTION member the row names;
* each of the row's named mutations, applied in memory to that production
  span, reds it (and each mutation is asserted to have changed the text
  before it is measured - a replace whose anchor missed is a check that
  cannot fail, #342/#391/#431);
* the row's control - the sibling span that must stay green, or the
  structure the matcher must still find - holds in the same mutated text,
  which is what proves the assertion is span-scoped rather than file-wide
  (#432, #279).

Members are resolved by their literal declaration text through
`_cs_structure._single_span`, which raises on an absent or ambiguous
signature. A raise is reported by each row as RED with its reason, never as
"the invariant is satisfied".

Nothing under plugin/ is written: every mutation is an in-memory string.
"""

from __future__ import annotations

import re
from pathlib import Path

from _cs_structure import (CsParseError, RELEASE_SYMBOLS, _single_span,
                           guard_chain, mask_code, strip_comments_only)

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"


def _text(name):
    return (PLUGIN / name).read_text(encoding="utf-8")


def texts():
    return {
        "DN": _text("DamageNumbers.cs"),
        "DR": _text("DamageNumberRules.cs"),
        "PS": _text("PoisonSync.cs"),
        "NU": _text("NativeUI.cs"),
        "VF": _text("VanillaFixes.cs"),
        "CU": _text("CompetitiveUI.cs"),
        "PL": _text("Plugin.cs"),
    }


def mutate(t, key, old, new, count=1):
    """A copy of the text dict with exactly `count` occurrences of `old` in
    t[key] replaced; asserts the anchor matched and the text changed."""
    src = t[key]
    n = src.count(old)
    assert n == count, "mutation anchor matched %d times, want %d: %r" % (n, count, old[:80])
    out = dict(t)
    out[key] = src.replace(old, new)
    assert out[key] != src, "the mutation did not change the source"
    return out


def run(check, t, *args):
    """(green, detail). A parse refusal is RED with its reason."""
    try:
        return check(t, *args)
    except CsParseError as e:
        return False, "CsParseError: %s" % e


# ── structure helpers (all decisions on the mask; offsets shared) ───────────

SIG = {
    "ddpre": "internal static void DoDamagePrefix(HealthHandler __instance, out float __state)",
    "ddpost": "internal static void DoDamagePostfix(HealthHandler __instance, float __state)",
    "hpre": "internal static void HealPrefix(HealthHandler __instance, out float __state)",
    "hpost": "internal static void HealPostfix(HealthHandler __instance, float __state)",
    "draw": "internal static void Draw()",
    "note": "internal static bool Note(int subject, DamageNumberRules.Kind kind, float magnitude, float now)",
    "tick": "internal static void Tick(float now)",
    "rtick": "internal static Emission[] Tick(float now)",
    "compose": "internal static string Compose(Kind kind, float magnitude, string fmt)",
    "selftest": "internal static SelfTestResult SelfTest()",
    # the notify site: on this lane Apply(...) delegates the committed tick to
    # ApplyCommitted, where the inner try and the bar companion live
    "apply": "private static void ApplyCommitted(PhotonView view, StreamRec rec,",
    # the correction funnel: the second direct writer, on fighter and spectator seats
    "corrective": "private static void ApplyCorrective(PhotonView view, StreamRec rec)",
    "paint": "private static void PaintDamageNumbers(object t, string level)",
    "driver": "internal sealed class DamageNumberDriver : MonoBehaviour",
    "emit": "private static void Emit(int subject, DamageNumberRules.Kind kind, float magnitude, Vector3 bodyPosition)",
    "bridge": "internal static void NoteDirectDrop(PhotonView view, float pre, float post)",
    "drawui": "public static void DrawUI()",
    "update": "private void Update()",
}


def _w(m, i):
    return 0 <= i < len(m) and (m[i].isalnum() or m[i] == "_")


def _ws(m, i):
    while i < len(m) and m[i].isspace():
        i += 1
    return i


def _match(m, i, o="{", c="}"):
    """Index just past the bracket matching the one at i."""
    assert m[i] == o, "expected %r at %d, got %r" % (o, i, m[i])
    d = 0
    for k in range(i, len(m)):
        if m[k] == o:
            d += 1
        elif m[k] == c:
            d -= 1
            if d == 0:
                return k + 1
    raise CsParseError("unbalanced %s at %d" % (o, i))


def member(src, sig):
    """(inner_text, inner_mask, offset) of the member body, braces excluded."""
    o, e = _single_span(src, sig, RELEASE_SYMBOLS)
    return src[o + 1:e - 1], mask_code(src)[o + 1:e - 1], o + 1


def top_try(m):
    """The first `try` at brace depth 0 of a masked body, with its clauses."""
    depth = 0
    i = 0
    while i < len(m):
        ch = m[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and m.startswith("try", i) and not _w(m, i - 1) and not _w(m, i + 3):
            j = _ws(m, i + 3)
            if j < len(m) and m[j] == "{":
                tend = _match(m, j)
                clauses = []
                k = tend
                while True:
                    k2 = _ws(m, k)
                    if m.startswith("catch", k2) and not _w(m, k2 + 5):
                        k3 = _ws(m, k2 + 5)
                        if k3 < len(m) and m[k3] == "(":
                            k3 = _ws(m, _match(m, k3, "(", ")"))
                        cend = _match(m, k3)
                        clauses.append(("catch", k3, cend))
                        k = cend
                    elif m.startswith("finally", k2) and not _w(m, k2 + 7):
                        k3 = _ws(m, k2 + 7)
                        fend = _match(m, k3)
                        clauses.append(("finally", k3, fend))
                        k = fend
                    else:
                        break
                return {"start": i, "open": j, "tend": tend, "clauses": clauses, "end": k}
        i += 1
    return None


def outside_of_try(m):
    t = top_try(m)
    if t is None:
        return None, re.sub(r"\s+", "", m), m
    out = m[:t["start"]] + m[t["end"]:]
    return t, re.sub(r"\s+", "", out), out


def whole_body_guard(m):
    """The body is one try with at least one catch and nothing outside it."""
    t, outside, _ = outside_of_try(m)
    has_catch = bool(t) and any(c[0] == "catch" for c in t["clauses"])
    return t is not None and has_catch and outside == "", t, outside, has_catch


def top_level_counts(outside_masked):
    """(top-level statements, semicolons) of a masked text at brace depth 0."""
    stmts = 0
    depth = 0
    paren = 0
    pending = False
    for ch in outside_masked:
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                stmts += 1
                pending = False
                continue
        elif ch == ";" and depth == 0 and paren == 0:
            stmts += 1
            pending = False
            continue
        if depth == 0 and not ch.isspace():
            pending = True
    return stmts, outside_masked.count(";")


def finally_spans(m):
    out = []
    for mm in re.finditer(r"\bfinally\s*\{", m):
        o = mm.end() - 1
        out.append((o, _match(m, o)))
    return out


def enclosing_try(m, pos):
    """(open, end) of the innermost `try {` block enclosing pos, or None."""
    stack = []
    for i in range(pos):
        if m[i] == "{":
            stack.append(i)
        elif m[i] == "}" and stack:
            stack.pop()
    for o in reversed(stack):
        j = o - 1
        while j >= 0 and m[j].isspace():
            j -= 1
        if j >= 2 and m[j - 2:j + 1] == "try" and not _w(m, j - 3):
            return o, _match(m, o)
    return None


def norm(s):
    return re.sub(r"\s+", "", s)


# ── B1: each hook body is one try/catch, armed sentinel, Exit in finally ────

def hook_shape(t, key):
    inner, m, _ = member(t["DN"], SIG[key])
    ok, tr, outside, has_catch = whole_body_guard(m)
    if not ok:
        return False, "%s: whole-body guard missing (outside=%r catch=%s)" % (key, outside[:40], has_catch)
    tblock = m[tr["open"] + 1:tr["tend"] - 1]
    if key.endswith("pre"):
        first = re.match(r"\s*__state\s*=\s*float\.MinValue\s*;", tblock)
        cat = [m[c[1]:c[2]] for c in tr["clauses"] if c[0] == "catch"]
        armed = any(re.search(r"__state\s*=\s*float\.MinValue\s*;", c) for c in cat)
        if not (first and armed):
            return False, "%s: the sentinel is not armed first and in the catch" % key
    else:
        exits = [mm.start() for mm in re.finditer(r"Fence\.Exit\s*\(", m)]
        fins = finally_spans(m)
        if len(exits) != 1 or not any(o < exits[0] < e for o, e in fins):
            return False, "%s: Exit is not exactly once inside a finally (%d exits, %d finally)" % (
                key, len(exits), len(fins))
    return True, "%s ok" % key


def unwrap(t, key):
    """Mutation: the member body becomes its try block's inner text."""
    src = t["DN"]
    inner, m, off = member(src, SIG[key])
    tr = top_try(m)
    new_inner = inner[tr["open"] + 1:tr["tend"] - 1]
    out = dict(t)
    out["DN"] = src[:off] + new_inner + src[off + len(inner):]
    assert out["DN"] != src
    return out


HOOKS = ("ddpre", "ddpost", "hpre", "hpost")


def test_B1_each_hook_body_is_one_try_catch_with_an_armed_sentinel_and_exit_in_finally():
    t = texts()
    for k in HOOKS:
        ok, why = run(hook_shape, t, k)
        assert ok, why
    # mutation: unwrap ONE body; the other three stay green in the same run
    for victim in HOOKS:
        mt = unwrap(t, victim)
        ok, why = run(hook_shape, mt, victim)
        assert not ok, "unwrapping %s stayed green" % victim
        for other in HOOKS:
            if other != victim:
                ok, why = run(hook_shape, mt, other)
                assert ok, "control %s reddened when %s was unwrapped: %s" % (other, victim, why)
    # mutation: the Postfix's Exit leaves its finally
    mt = mutate(t, "DN", "                    finally\n                    {\n                        DamageNumberRules.DamageFence.Exit(subject);\n                    }\n",
                "                    finally { }\n                    DamageNumberRules.DamageFence.Exit(subject);\n")
    assert not run(hook_shape, mt, "ddpost")[0]
    assert run(hook_shape, mt, "hpost")[0]
    # rejection: an absent signature is RED with its reason, not green
    mt = mutate(t, "DN", SIG["ddpre"], SIG["ddpre"].replace("DoDamagePrefix", "DoDamagePrefixX"))
    ok, why = run(hook_shape, mt, "ddpre")
    assert not ok and "signature not found" in why, why


# ── B2: Enter once in each Prefix, Exit once in each Postfix ────────────────

def fence_pair(t, which):
    fence, pre, post = ("DamageFence", "ddpre", "ddpost") if which == "dd" else ("HealFence", "hpre", "hpost")
    _, mpre, _ = member(t["DN"], SIG[pre])
    _, mpost, _ = member(t["DN"], SIG[post])
    ne = len(re.findall(re.escape(fence) + r"\.Enter\s*\(", mpre))
    nx = len(re.findall(re.escape(fence) + r"\.Exit\s*\(", mpost))
    return (ne == 1 and nx == 1), "%s enter=%d exit=%d" % (which, ne, nx)


def test_B2_enter_once_per_prefix_span_and_exit_once_per_postfix_span():
    t = texts()
    assert run(fence_pair, t, "dd")[0] and run(fence_pair, t, "heal")[0]
    enter = "DamageNumberRules.DamageFence.Enter(data.view.ViewID, Time.unscaledTime)"
    mt = mutate(t, "DN", enter, "default(DamageNumberRules.FenceResult)")
    assert not run(fence_pair, mt, "dd")[0], "deleting Enter stayed green"
    assert run(fence_pair, mt, "heal")[0], "the heal pair reddened: the matcher is not span-keyed"
    ex = "DamageNumberRules.DamageFence.Exit(subject);"
    mt = mutate(t, "DN", ex, ex + " " + ex)
    ok, why = run(fence_pair, mt, "dd")
    assert not ok and "exit=2" in why, why
    assert run(fence_pair, mt, "heal")[0]
    hex_ = "DamageNumberRules.HealFence.Exit(subject);"
    mt = mutate(t, "DN", hex_, "")
    assert not run(fence_pair, mt, "heal")[0]
    assert run(fence_pair, mt, "dd")[0]


# ── B3: the heal's subject is its own __instance's ──────────────────────────

def reads_damage_fence(m):
    return re.search(r"\bDamageFence\b(?!\s*\.\s*Exit\b)|\bDamageFence\s*\.\s*Current", m) is not None


def own_subject(t, key):
    _, m, _ = member(t["DN"], SIG[key])
    init = re.search(r"\bvar\s+data\s*=\s*__instance\s*!=\s*null\s*\?\s*__instance\.data\s*:\s*null\s*;", m)
    subj = re.search(r"\bint\s+subject\s*=\s*([^;]*);", m)
    from_data = bool(subj) and re.search(r"\bdata\.view\.ViewID\b", subj.group(1)) is not None \
        and not re.search(r"Fence|_victim|Current", subj.group(1))
    return bool(init) and from_data, "%s init=%s subject=%r" % (key, bool(init), subj.group(1) if subj else None)


def test_B3_the_heal_subject_comes_from_its_own_instance_never_the_damage_fence():
    t = texts()
    _, mh, _ = member(t["DN"], SIG["hpost"])
    assert run(own_subject, t, "hpost")[0] and not reads_damage_fence(mh)
    old = "int subject = data != null && data.view != null ? data.view.ViewID : 0;\n                    try\n                    {\n                        if (data != null && !float.IsNegativeInfinity(__state))\n                        {\n                            float rise"
    new = "int subject = DamageNumberRules.DamageFence.CurrentSubject;\n                    try\n                    {\n                        if (data != null && !float.IsNegativeInfinity(__state))\n                        {\n                            float rise"
    mt = mutate(t, "DN", old, new)
    _, mh2, _ = member(mt["DN"], SIG["hpost"])
    assert not run(own_subject, mt, "hpost")[0] and reads_damage_fence(mh2), "the damage-fence subject stayed green"
    # control: the DoDamage postfix legitimately touches the damage fence (its
    # Exit) and still derives its subject from its own instance - green
    _, md, _ = member(mt["DN"], SIG["ddpost"])
    assert run(own_subject, mt, "ddpost")[0]
    assert re.search(r"\bDamageFence\.Exit\s*\(", md), "the control span lost the fence it legitimately uses"


# ── B4: the heal magnitude is the observed rise, never healAmount ───────────

def observed_rise(t):
    inner, m, _ = member(t["DN"], SIG["hpost"])
    code = strip_comments_only(inner)
    rise = re.search(r"\bfloat\s+rise\s*=\s*data\.health\s*-\s*__state\s*;", m)
    emit = re.search(r"\bEmit\s*\(([^;]*)\)\s*;", m)
    args = emit.group(1) if emit else ""
    return bool(rise) and bool(emit) and "rise" in args and "healAmount" not in code, \
        "rise=%s emit_args=%r" % (bool(rise), args)


def prefix_captures_pre(t):
    _, m, _ = member(t["DN"], SIG["hpre"])
    return re.search(r"__state\s*=\s*f\.Outermost\s*\?\s*data\.health\b", m) is not None and "healAmount" not in m, "hpre"


def test_B4_the_heal_magnitude_is_post_minus_pre_and_never_heal_amount():
    t = texts()
    assert run(observed_rise, t)[0] and run(prefix_captures_pre, t)[0]
    mt = mutate(t, "DN", "Emit(subject, DamageNumberRules.Kind.Heal, rise, __instance.transform.position);",
                "Emit(subject, DamageNumberRules.Kind.Heal, healAmount, __instance.transform.position);")
    assert not run(observed_rise, mt)[0], "healAmount in the emit stayed green"
    assert run(prefix_captures_pre, mt)[0], "the Prefix control reddened"


# ── B5: the poison notify is inside the inner try and under the drop predicate

BRIDGE = "DamageNumbers.NoteDirectDrop("
NOTIFY = "DamageNumbers.NoteDirectDrop(view, preTick, cds.health);"
BAR = "hbBar.TakeDamage("

# The two direct writers PoisonSync lowers health with (neither calls
# DoDamage, so W1 cannot see them): the committed spectator tick and the
# correction funnel. Each must hand the bridge its observed drop, once, inside
# its bar companion's try and under its own drop predicate (fix 1: the
# correction funnel was missing from the feed).
FUNNELS = {
    "committed": {
        "sig": SIG["apply"], "notify": NOTIFY, "bar": BAR, "pred": "cds.health<preTick",
        "args": ["view", "preTick", "cds.health"], "outer": "rec.Applied++;",
        "slice": r"float\s+nh\s*=\s*cds\.health\s*-\s*rec\.Slice\.magnitude\s*;",
    },
    "corrective": {
        "sig": SIG["corrective"], "notify": "DamageNumbers.NoteDirectDrop(view, pre, cd.health);",
        "bar": "if (bar != null) bar.TakeDamage(", "pred": "cd.health<pre",
        "args": ["view", "pre", "cd.health"], "outer": "rec.Applied++;",
        "slice": r"float\s+nh\s*=\s*pre\s*-\s*rec\.Slice\.magnitude\s*;",
    },
}


def poison_halves(t, which="committed"):
    f = FUNNELS[which]
    src = t["PS"]
    o, e = _single_span(src, f["sig"], RELEASE_SYMBOLS)
    m = mask_code(src)[o:e]
    bar_at = m.find(f["bar"])
    at = m.find(BRIDGE)
    if bar_at < 0 or at < 0:
        return (False, False), "%s: anchor missing bar=%d at=%d" % (which, bar_at, at)
    tr = enclosing_try(m, bar_at)
    span_ok = tr is not None and tr[0] < at < tr[1]
    conds = guard_chain(src, f["sig"], BRIDGE)
    pred_ok = any(norm(c) == f["pred"] for c in conds)
    return (span_ok, pred_ok), "%s: span=%s predicate=%s conds=%r" % (which, span_ok, pred_ok, conds)


def test_B5_the_poison_notify_sits_inside_the_bar_companions_try_and_under_its_drop_predicate():
    t = texts()
    (s, p), why = poison_halves(t)
    assert s and p, why
    # mutation 1: below the try, keeping its own predicate inline -> span half alone
    mt = mutate(t, "PS", "                                " + NOTIFY + "\n", "")
    mt = mutate(mt, "PS", "                        catch { }\n                        // Bug 202",
                "                        catch { }\n                        if (cds.health < preTick) " + NOTIFY + "\n                        // Bug 202")
    (s1, p1), why = poison_halves(mt)
    assert (s1, p1) == (False, True), "moving below the try: " + why
    # mutation 2: above the if, inside the try -> predicate half alone
    mt = mutate(t, "PS", "                                " + NOTIFY + "\n", "")
    mt = mutate(mt, "PS", "                        try\n                        {\n                            if (cds.health < preTick)",
                "                        try\n                        {\n                            " + NOTIFY + "\n                            if (cds.health < preTick)")
    (s2, p2), why = poison_halves(mt)
    assert (s2, p2) == (True, False), "moving above the if: " + why
    # control: the bar companion resolves inside the same try and under the same
    # condition; Apply's outer body (rec.Applied++) is not inside that try
    src = t["PS"]
    o, e = _single_span(src, SIG["apply"], RELEASE_SYMBOLS)
    m = mask_code(src)[o:e]
    tr = enclosing_try(m, m.find(BAR))
    conds = guard_chain(src, SIG["apply"], BAR)
    assert any(norm(c) == "cds.health<preTick" for c in conds)
    outer = m.find("rec.Applied++;")
    assert outer >= 0 and not (tr[0] < outer < tr[1]), "the outer body resolved into the try"


# ── B6: the pause gate fails closed and is one of six early returns ─────────

def pause_gate(t):
    inner, m, _ = member(t["DN"], SIG["draw"])
    at = m.find("EscapeMenuHandler.isEscMenu")
    if at < 0:
        return False, "no pause read"
    tr = enclosing_try(m, at)
    if tr is None:
        return False, "the pause read is outside any try"
    k = _ws(m, tr[1])
    if not m.startswith("catch", k):
        return False, "no catch after the pause try"
    k3 = _ws(m, k + 5)
    if m[k3] == "(":
        k3 = _ws(m, _match(m, k3, "(", ")"))
    cblock = m[k3:_match(m, k3)]
    if re.search(r"\bthrow\b", cblock):
        return False, "the pause catch rethrows"
    if not re.search(r"\bpaused\s*=\s*true\s*;", cblock):
        return False, "the pause catch does not fail closed"
    gates = [norm(g.group(1)) for g in re.finditer(r"\bif\s*\(([^;{]*)\)\s*return\s*;", m)
             if m.count("{", 0, g.start()) == m.count("}", 0, g.start())]   # brace depth 0
    return ("paused" in gates and len(gates) == 6), "gates=%r" % gates


def other_gates(t):
    _, m, _ = member(t["DN"], SIG["draw"])
    want = ["Event.current==null||Event.current.type!=EventType.Repaint",
            "CurrentMode==DamageNumberRules.Mode.Off", "!VanillaFixSupport.AnyGameScope()",
            "NativeUI.IsOpen", "CompetitiveUI.IsChatInputOpen"]
    got = [norm(g) for g in re.findall(r"\bif\s*\(([^;{]*)\)\s*return\s*;", m)]
    return all(w in got for w in want), "five=%r" % [w in got for w in want]


def test_B6_the_draw_pause_gate_reads_inside_a_try_whose_catch_fails_closed():
    t = texts()
    assert run(pause_gate, t)[0] and run(other_gates, t)[0]
    for old, new, label in (
            ("catch { paused = true; }", "catch { paused = false; }", "flip the catch"),
            ("bool paused = true;\n            try { paused = EscapeMenuHandler.isEscMenu; } catch { paused = true; }",
             "bool paused = EscapeMenuHandler.isEscMenu;", "hoist the read"),
            ("catch { paused = true; }", "catch { throw; }", "a rethrowing catch")):
        mt = mutate(t, "DN", old, new)
        assert not run(pause_gate, mt)[0], label + " stayed green"
        assert run(other_gates, mt)[0], label + " reddened the other five gates"


# ── B7: both refusals are reported from Note's own span ─────────────────────

def refusals_reported(t):
    inner, _, _ = member(t["DN"], SIG["note"])
    code = strip_comments_only(inner)
    cap = len(re.findall(r'DiagLimited\s*\(\s*"DmgNum-subject-cap"', code))
    exp = len(re.findall(r'DiagLimited\s*\(\s*"DmgNum-fence-expired"', code))
    return (cap == 1 and exp == 1), "cap=%d expired=%d" % (cap, exp)


def test_B7_both_refusals_are_reported_inside_note():
    t = texts()
    assert run(refusals_reported, t)[0]
    cap_old = 'VanillaFixSupport.DiagLimited("DmgNum-subject-cap",'
    mt = mutate(t, "DN", cap_old, "VanillaFixSupport.DiagLimitedX(\"gone\",")
    ok, why = run(refusals_reported, mt)
    assert not ok and "cap=0" in why and "expired=1" in why, why
    exp_old = 'VanillaFixSupport.DiagLimited("DmgNum-fence-expired",'
    mt = mutate(t, "DN", exp_old, "VanillaFixSupport.DiagLimitedX(\"gone\",")
    ok, why = run(refusals_reported, mt)
    assert not ok and "cap=1" in why and "expired=0" in why, why
    # scope control: the cap report removed from Note and parked in Tick - a
    # file-wide matcher would stay green; this row must red
    mt = mutate(t, "DN", cap_old, "VanillaFixSupport.DiagLimitedX(\"gone\",")
    mt = mutate(mt, "DN", "            _localView = ResolveLocalView();",
                "            _localView = ResolveLocalView();\n            VanillaFixSupport.DiagLimited(\"DmgNum-subject-cap\", \"x\", 1);")
    assert not run(refusals_reported, mt)[0], "the row is file-wide, not Note-scoped"


# ── B8: whole files minus exactly one SelfTest span ─────────────────────────

STATE_LITERALS = {
    "EVERYONE": 'I18n.Tr("Damage numbers: <color=#88FF88>EVERYONE</color>")',
    "ME": 'I18n.Tr("Damage numbers: <color=#DDDD66>ME</color>")',
    "OFF": 'I18n.Tr("Damage numbers: <color=#FF9966>OFF</color>")',
}


def scanned(t):
    """DamageNumbers.cs whole + DamageNumberRules.cs with exactly the one
    SelfTest span blanked (same length). Raises when the exclusion does not
    resolve to exactly one span."""
    dr = t["DR"]
    o, e = _single_span(dr, SIG["selftest"], RELEASE_SYMBOLS)
    blank = "".join(ch if ch == "\n" else " " for ch in dr[o:e])
    return t["DN"] + "\n" + dr[:o] + blank + dr[e:]


def b8(t):
    bad = []
    # (a) the three state literals, each inside its own I18n.Tr("...")
    pinner, _, _ = member(t["NU"], SIG["paint"])
    pcode = strip_comments_only(pinner)
    for word, lit in STATE_LITERALS.items():
        if pcode.count(lit) != 1:
            bad.append("Tr literal %s x%d" % (word, pcode.count(lit)))
    if re.search(r"\bTr\s*\(\s*[^\"\s]", pcode):
        bad.append("Tr(variable) in the painter")
    s = scanned(t)
    code = strip_comments_only(s)
    # (b) no format literal and no comparison against one
    if re.search(r'"[Ff][0-2]"', code):
        bad.append("format literal %r" % re.search(r'"[Ff][0-2]"', code).group(0))
    # (c) no label string carries two letters: Compose's own literals and every
    # class-scope string it references
    dr_scan = s[len(t["DN"]) + 1:]
    cinner, cm, _ = member(dr_scan, SIG["compose"])
    for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', strip_comments_only(cinner)):
        if sum(ch.isalpha() for ch in lit) >= 2:
            bad.append("label literal %r" % lit)
    for name, lit in re.findall(r'\b(?:const|readonly)\s+string\s+(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"', code):
        if re.search(r"\b" + re.escape(name) + r"\b", cm) and sum(ch.isalpha() for ch in lit) >= 2:
            bad.append("class-scope label %s=%r" % (name, lit))
    return not bad, "; ".join(bad) or "clean"


def test_B8_whole_files_minus_one_selftest_carry_no_format_literal_or_worded_label():
    t = texts()
    ok, why = run(b8, t)
    assert ok, why
    # controls: the shipped MinShowFromFormat is digit arithmetic, and the
    # A12/A13 F0/F1/F2 fixtures inside SelfTest are present yet unseen
    st = strip_comments_only(member(t["DR"], SIG["selftest"])[0])
    assert all(('"%s"' % f) in st for f in ("F0", "F1", "F2")), "the SelfTest fixtures are gone"
    assert re.search(r"Math\.Pow\(10,\s*-FormatDigits\(fmt\)\)", t["DR"])
    # 1: one state literal becomes Tr(variable)
    mt = mutate(t, "NU", STATE_LITERALS["ME"], "I18n.Tr(_v)")
    assert not run(b8, mt)[0]
    # 2: "F1" inlined in a production member
    mt = mutate(t, "DN", "DamageNumberRules.SetFormat(TabStatsOverlay.HealthPrecisionSetting.Fmt);",
                'DamageNumberRules.SetFormat("F1");')
    ok, why = run(b8, mt)
    assert not ok and "format literal" in why, why
    # 3: a worded unit parked at CLASS scope, composed into the label
    plant = "        internal const int SpectatorSentinel = -1;\n"
    compose_ret = "magnitude.ToString(f, CultureInfo.CurrentCulture);"
    mt = mutate(t, "DR", plant, plant + '        private const string Unit = " HP";\n')
    mt = mutate(mt, "DR", compose_ret, "magnitude.ToString(f, CultureInfo.CurrentCulture) + Unit;")
    ok, why = run(b8, mt)
    assert not ok and "class-scope label Unit" in why, why
    # control for 3: the same const moved INSIDE the excluded SelfTest goes green
    mt = mutate(t, "DR", "            var r = new SelfTestResult();\n            const string F0 = \"F0\";",
                "            var r = new SelfTestResult();\n            const string F0 = \"F0\";\n            const string Unit = \" HP\";")
    mt = mutate(mt, "DR", compose_ret, "magnitude.ToString(f, CultureInfo.CurrentCulture) + Unit;")
    ok, why = run(b8, mt)
    assert ok, "the exclusion was not applied: " + why
    # 4: the exclusion resolves to zero spans
    mt = mutate(t, "DR", SIG["selftest"], "internal static SelfTestResult SelfTestGone()")
    ok, why = run(b8, mt)
    assert not ok and "signature not found" in why, why


# ── B9: the poison magnitude is the APPLIED drop ────────────────────────────

def notify_args(t, which="committed"):
    f = FUNNELS[which]
    src = t["PS"]
    o, e = _single_span(src, f["sig"], RELEASE_SYMBOLS)
    m = mask_code(src)[o:e]
    at = m.find(BRIDGE)
    if at < 0:
        return False, "%s: no notify" % which
    po = at + len(BRIDGE) - 1
    args = src[o:e][po + 1:_match(m, po, "(", ")") - 1]
    parts = [norm(a) for a in args.split(",")]
    ok = parts == f["args"] and "rec.Slice.magnitude" not in args
    return ok, "%s: args=%r" % (which, parts)


def test_B9_the_poison_notify_passes_the_applied_drop_not_the_slice_magnitude():
    t = texts()
    assert run(notify_args, t)[0]
    mt = mutate(t, "PS", NOTIFY, "DamageNumbers.NoteDirectDrop(view, preTick + rec.Slice.magnitude, preTick);")
    assert not run(notify_args, mt)[0]
    # control: the method legitimately reads the slice magnitude for its own
    # write, and the argument-scoped row stays green beside it
    apply_code = mask_code(t["PS"])
    o, e = _single_span(t["PS"], SIG["apply"], RELEASE_SYMBOLS)
    assert re.search(r"float\s+nh\s*=\s*cds\.health\s*-\s*rec\.Slice\.magnitude\s*;", apply_code[o:e])


# ── B10: the Unity tick formats nothing ─────────────────────────────────────

def formats(code_with_literals):
    return bool(re.search(r"\.ToString\s*\(|\$\"|\$@\"|string\.Format\s*\(|\"[FfNn][0-9]\"|\"0\.0", code_with_literals))


def unity_tick_formats_nothing(t):
    inner, _, _ = member(t["DN"], SIG["tick"])
    return not formats(strip_comments_only(inner)), "unity tick"


def test_B10_the_unity_tick_does_no_numeric_formatting():
    t = texts()
    assert run(unity_tick_formats_nothing, t)[0]
    mt = mutate(t, "DN", "_text[slot] = em[i].Text;", '_text[slot] = em[i].Signed.ToString("F1");')
    assert not run(unity_tick_formats_nothing, mt)[0]
    # controls: the rules side legitimately formats (Compose), and neither
    # tick's declaration resolves in the other file
    assert formats(strip_comments_only(member(t["DR"], SIG["compose"])[0]))
    assert member(t["DR"], SIG["rtick"])
    for src, sig in ((t["DR"], SIG["tick"]), (t["DN"], SIG["rtick"])):
        try:
            _single_span(src, sig, RELEASE_SYMBOLS)
            raise AssertionError("%r resolved in the other file" % sig)
        except CsParseError as e:
            assert "signature not found" in str(e)


# ── B11: the targets carry their declaring type ─────────────────────────────

def target_typed(t, method):
    code = strip_comments_only(t["DN"])
    attrs = re.findall(r"\[HarmonyPatch\s*\(([^\]]*)\)\]", code)
    typed = [a for a in attrs if re.fullmatch(r'\s*typeof\(HealthHandler\)\s*,\s*"%s"\s*' % method, a)]
    bare = [a for a in attrs if re.fullmatch(r'\s*"%s"\s*' % method, a)]
    acc_bare = re.findall(r'AccessTools\.Method\s*\(\s*"%s"' % method, code)
    return (len(typed) == 1 and not bare and not acc_bare), "%s typed=%d bare=%d" % (method, len(typed), len(bare))


def test_B11_each_target_is_resolved_with_typeof_health_handler():
    t = texts()
    assert run(target_typed, t, "DoDamage")[0] and run(target_typed, t, "Heal")[0]
    mt = mutate(t, "DN", '[HarmonyPatch(typeof(HealthHandler), "DoDamage")]', '[HarmonyPatch("DoDamage")]')
    assert not run(target_typed, mt, "DoDamage")[0]
    assert run(target_typed, mt, "Heal")[0], "the Heal control reddened"
    # control: DamagableEvent named outside the patch span does not red it
    assert "DamagableEvent" in t["DN"], "the doc-comment control is gone"
    mt = mutate(t, "DN", "            _localView = ResolveLocalView();",
                "            _localView = ResolveLocalView();\n            var de = typeof(DamagableEvent);")
    assert run(target_typed, mt, "DoDamage")[0]


# ── B12: the driver's whole Update body is one try/catch ────────────────────

def driver_guard(t):
    blocks = []
    src = t["DN"]
    o, e = _single_span(src, SIG["driver"], RELEASE_SYMBOLS)   # exactly one class
    cls = src[o:e]
    inner, m, _ = member(cls, SIG["update"])
    ok, tr, outside, has_catch = whole_body_guard(m)
    return ok, "outside=%r catch=%s" % (outside[:40], has_catch)


def test_B12_the_driver_update_body_is_entirely_one_try_catch():
    t = texts()
    ok, why = run(driver_guard, t)
    assert ok, why
    # mutation: copy the precedent's preamble literally
    mt = mutate(t, "DN", "        private void Update()\n        {\n            try\n            {\n                DamageNumbers.Tick(Time.unscaledTime);",
                "        private void Update()\n        {\n            float now = Time.unscaledTime;\n            try\n            {\n                DamageNumbers.Tick(now);")
    ok, why = run(driver_guard, mt)
    assert not ok and "floatnow" in why, why
    # mutation: delete the catch (a bare try fails on the catch assertion)
    old = "            catch (Exception ex)\n            {\n                VanillaFixSupport.DiagLimited(\"DmgNum-tick\", \"[DMGNUM] tick failed: \" + ex.Message, 5);\n            }\n"
    mt = mutate(t, "DN", old, "            finally { }\n")
    ok, why = run(driver_guard, mt)
    assert not ok and "catch=False" in why, why
    # control: the precedent's Update, unique in VanillaFixes.cs, is NOT
    # whole-body: four top-level statements and five semicolons outside its try
    vi, vm, _ = member(t["VF"], SIG["update"])
    vok, vtr, voutside, vcatch = whole_body_guard(vm)
    _, _, raw_out = outside_of_try(vm)
    stmts, semis = top_level_counts(raw_out)
    assert not vok and vcatch and (stmts, semis) == (4, 5), (stmts, semis, voutside[:60])
    # resolution mutation: a second MonoBehaviour with its own Update in the file
    plant = ("\n    internal sealed class OtherDriver : MonoBehaviour\n    {\n        private void Update()\n"
             "        {\n            int x = 0;\n        }\n    }\n")
    mt = mutate(t, "DN", "    internal sealed class DamageNumberDriver : MonoBehaviour", plant + "    internal sealed class DamageNumberDriver : MonoBehaviour")
    assert run(driver_guard, mt)[0], "the class-first resolution lost the driver"
    try:
        _single_span(mt["DN"], SIG["update"], RELEASE_SYMBOLS)
        raise AssertionError("a bare Update() against the file resolved")
    except CsParseError as e:
        assert "2 blocks match" in str(e), str(e)


# ── B13: the patched set is exactly {DoDamage, Heal}; no lifecycle member ───

LIFECYCLE = ("ResetStats", "Revive", "AbyssalCountdown", "StatsAfterDealingDamage",
             "StatsWhenFullHP", "ToggleStats")


def patch_set(t):
    targets = set()
    accessed = set()
    lifecycle = []
    for key in ("DN", "DR"):
        lit = strip_comments_only(t[key])
        for a in re.findall(r"\[HarmonyPatch\s*\(([^\]]*)\)\]", lit):
            ty = re.search(r"typeof\(\s*(\w+)\s*\)", a)
            nm = re.search(r'"(\w+)"', a)
            targets.add(((ty.group(1) if ty else "?"), (nm.group(1) if nm else "?")))
        for ty, nm in re.findall(r'AccessTools\.Method\s*\(\s*typeof\(\s*(\w+)\s*\)\s*,\s*"(\w+)"', lit):
            accessed.add((ty, nm))
        code = mask_code(t[key])
        for name in LIFECYCLE:
            if re.search(r"\b%s\b" % name, code):
                lifecycle.append("%s:%s" % (key, name))
        for a in re.findall(r"\[HarmonyPatch\s*\(([^\]]*)\)\]", lit):
            for name in LIFECYCLE:
                if name in a:
                    lifecycle.append("%s:patch:%s" % (key, name))
    want = {("HealthHandler", "DoDamage"), ("HealthHandler", "Heal")}
    ok = targets == want and accessed <= want and not lifecycle
    return ok, "targets=%r accessed=%r lifecycle=%r" % (sorted(targets), sorted(accessed), lifecycle)


def test_B13_no_emit_the_patch_set_is_exactly_damage_and_heal_and_no_lifecycle_member():
    t = texts()
    ok, why = run(patch_set, t)
    assert ok, why
    # mutation: the exact build section 2.2 says C1/C2/C3/B11 cannot see - a
    # ResetStats Postfix that notes a heal
    plant = ("        [HarmonyPatch(typeof(CharacterStatModifiers), \"ResetStats\")]\n"
             "        internal static class ResetHooks\n        {\n            [HarmonyPostfix]\n"
             "            internal static void ResetPostfix(CharacterStatModifiers __instance)\n            {\n"
             "                try { Note(0, DamageNumberRules.Kind.Heal, 100f, Time.unscaledTime); } catch { }\n"
             "            }\n        }\n\n")
    anchor = "        // ------------------------------------------------------------ W3: direct poison writers\n"
    mt = mutate(t, "DN", anchor, plant + anchor)
    ok, why = run(patch_set, mt)
    assert not ok and "ResetStats" in why, why
    assert run(target_typed, mt, "DoDamage")[0] and run(target_typed, mt, "Heal")[0], "B11 moved with B13"
    # mutation: one required target deleted
    mt = mutate(t, "DN", '[HarmonyPatch(typeof(HealthHandler), "Heal")]\n', "")
    assert not run(patch_set, mt)[0]
    assert run(target_typed, mt, "DoDamage")[0]
    # control: a SelfTest fixture naming ResetStats as a STRING stays green
    mt = mutate(t, "DR", "            const string F0 = \"F0\";",
                "            const string F0 = \"F0\";\n            string lifecycleName = \"ResetStats\";")
    ok, why = run(patch_set, mt)
    assert ok, "the row is name-grepping the file: " + why


# ── B14: no assignment through a vanilla reference ──────────────────────────

ROOTS = {"__instance", "__result", "__args", "cds", "view"}
_CHAIN = re.compile(r"([A-Za-z_]\w*(?:\s*(?:\.\s*[A-Za-z_]\w*|\[[^\]]*\]))*)\s*$")


def _assignments(m):
    """(lhs_chain, op_pos) for every assignment operator in a masked text."""
    out = []
    n = len(m)
    for i, ch in enumerate(m):
        if ch != "=":
            continue
        nxt = m[i + 1] if i + 1 < n else ""
        if nxt in "=>":
            continue
        prv = m[i - 1] if i else ""
        start = i
        if prv in "=!":
            continue
        if prv in "<>":
            if i >= 2 and m[i - 2] == prv:
                start = i - 2
            else:
                continue
        elif prv in "+-*/%&|^":
            start = i - 1
        elif prv == "?" and i >= 2 and m[i - 2] == "?":
            start = i - 2
        b = max(m.rfind(";", 0, start), m.rfind("{", 0, start), m.rfind("}", 0, start),
                m.rfind("(", 0, start), m.rfind(",", 0, start))
        mm = _CHAIN.search(m[b + 1:start])
        if mm:
            out.append((re.sub(r"\s+", "", mm.group(1)), i))
    for mm in re.finditer(r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]*\])+)\s*(\+\+|--)", m):
        out.append((mm.group(1), mm.start()))
    return out


def tainted_writes(t):
    bad = []
    for key in ("DN", "DR"):
        m = mask_code(t[key])
        taint = set(ROOTS)
        changed = True
        while changed:
            changed = False
            for name, init in re.findall(r"\b(?:var|[A-Z]\w*)\s+([A-Za-z_]\w*)\s*=\s*([^;]*);", m):
                if name not in taint and any(re.search(r"(?<![\w.])%s\b" % re.escape(r), init) for r in taint):
                    taint.add(name)
                    changed = True
        for lhs, pos in _assignments(m):
            root = re.match(r"[A-Za-z_]\w*", lhs).group(0)
            if root in taint and ("." in lhs or "[" in lhs):
                bad.append("%s:%d %s" % (key, m.count("\n", 0, pos) + 1, lhs))
    return not bad, "; ".join(bad) or "clean"


HEALTH_WRITE = re.compile(r"\.health\s*(=|\+=|-=|\*=|/=)[^=]")


def test_B14_no_left_hand_side_is_rooted_at_a_harmony_parameter_or_its_taint():
    t = texts()
    ok, why = run(tainted_writes, t)
    assert ok, why
    anchor = "                    if (data == null || data.view == null) return;\n                    var f = DamageNumberRules.DamageFence.Enter"
    for plant, label in (("__instance.data.dead = true;", "direct"),
                         ("var hh = __instance; hh.data.MaxHealth = 100f;", "one hop"),
                         ("var hh = __instance; var d2 = hh.data; d2.MaxHealth = 100f;", "two hops (residual 16)")):
        mt = mutate(t, "DN", anchor, "                    " + plant + "\n" + anchor)
        ok, why = run(tainted_writes, mt)
        assert not ok, "%s plant stayed green" % label
    # the health plant reds B14 AND the C3 health-write matcher, independently
    mt = mutate(t, "DN", anchor, "                    __instance.data.health = 0f;\n" + anchor)
    assert not run(tainted_writes, mt)[0]
    assert HEALTH_WRITE.search(mask_code(mt["DN"])) and not HEALTH_WRITE.search(mask_code(t["DN"]))
    # controls: writes rooted at the new types' own statics, and __state itself
    m = mask_code(t["DN"])
    lhs = {l for l, _ in _assignments(m)}
    for own in ("_text[slot]", "_mode", "__state", "_anchors[subject]", "_world[slot]"):
        assert own in lhs, "control write %s not seen by the scanner" % own


# ── B15: every direct poison writer enters the feed exactly once (fix 1) ────

_NOT_MEMBERS = ("if", "for", "foreach", "while", "switch", "catch", "using", "lock", "fixed")


def member_name(m, pos):
    """The innermost named member (method, local function) whose braces
    enclose pos on a masked text, or '?'."""
    stack = []
    for i in range(pos):
        if m[i] == "{":
            stack.append(i)
        elif m[i] == "}" and stack:
            stack.pop()
    for o in reversed(stack):
        b = max(m.rfind(";", 0, o), m.rfind("{", 0, o), m.rfind("}", 0, o))
        head = m[b + 1:o]
        mm = re.search(r"(\w+)\s*\([^()]*(?:\([^()]*\)[^()]*)*\)\s*$", head)
        if mm and mm.group(1) not in _NOT_MEMBERS:
            return mm.group(1)
    return "?"


def corrective_feed(t):
    (s, p), why = poison_halves(t, "corrective")
    a, why2 = notify_args(t, "corrective")
    return s and p and a, why + "; " + why2


def writer_census(t):
    """Exact set: the members of PoisonSync.cs holding a direct health write
    are exactly the two funnels, one write each, and each holds exactly one
    bridge call; no other member calls the bridge."""
    m = mask_code(t["PS"])
    writes, bridges = {}, {}
    for mm in HEALTH_WRITE.finditer(m):
        k = member_name(m, mm.start())
        writes[k] = writes.get(k, 0) + 1
    for mm in re.finditer(re.escape(BRIDGE), m):
        k = member_name(m, mm.start())
        bridges[k] = bridges.get(k, 0) + 1
    want = {"ApplyCommitted": 1, "ApplyCorrective": 1}
    return writes == want and bridges == want, "writes=%r bridges=%r" % (writes, bridges)


def test_B15_the_correction_funnel_notes_its_observed_drop_and_the_writer_set_is_exact():
    t = texts()
    ok, why = run(corrective_feed, t)
    assert ok, why
    ok, why = run(writer_census, t)
    assert ok, why
    corr = FUNNELS["corrective"]["notify"]
    line = "                    " + corr + "\n"
    # mutation 1: the corrective notify deleted (the feed before fix 1) -> both red
    gone = mutate(t, "PS", line, "")
    assert not run(corrective_feed, gone)[0], "a funnel with no notify stayed green"
    assert not run(writer_census, gone)[0], "the census missed a writer with no bridge call"
    # mutation 2: the slice magnitude in place of the observed post-write health
    mt = mutate(t, "PS", corr, "DamageNumbers.NoteDirectDrop(view, pre, pre - rec.Slice.magnitude);")
    assert not run(corrective_feed, mt)[0], "the slice magnitude passed as the observed drop"
    # mutation 3: moved above the drop predicate, outside the bar's try -> both halves red
    mt = mutate(gone, "PS", "            cd.health = nh < floor ? floor : nh;\n",
                "            cd.health = nh < floor ? floor : nh;\n            " + corr + "\n")
    (s3, p3), why = poison_halves(mt, "corrective")
    assert (s3, p3) == (False, False), "moving outside the try and the predicate: " + why
    # mutation 4: a third direct writer with no bridge call -> the census reds
    mt = mutate(t, "PS", "        private static Player FindPlayer(int playerId)\n",
                "        private static void PlantWriter(CharacterData cd) { cd.health = 1f; }\n\n"
                "        private static Player FindPlayer(int playerId)\n")
    assert not run(writer_census, mt)[0], "a third writer stayed green"
    # mutation 5: the corrective notes twice -> not exactly once
    mt = mutate(t, "PS", line, line + line)
    assert not run(writer_census, mt)[0], "a doubled notify stayed green"
    # controls: the committed funnel stays green under mutation 1 (the row is
    # span-scoped), and the funnel's own slice read still resolves beside it
    assert poison_halves(gone, "committed")[0] == (True, True)
    assert run(notify_args, gone)[0]
    o, e = _single_span(t["PS"], SIG["corrective"], RELEASE_SYMBOLS)
    assert re.search(FUNNELS["corrective"]["slice"], mask_code(t["PS"])[o:e])


# ── B16: the observed delta reaches the engine (fix 1: a deletion guard) ────

EMIT_DAMAGE = "if (drop > 0f) Emit(subject, DamageNumberRules.Kind.Damage, drop, __instance.transform.position);"


def emit_bridge(t):
    """The damage-delta-to-emit bridge, link by link: each Postfix measures
    its observed delta and emits it with its own kind, only when positive;
    the direct-writer bridge emits Damage; Emit hands every emission to Note
    after the visibility test; Note hands it to the rules engine. Returns
    (green, problems)."""
    dn = t["DN"]
    problems = []
    for key, var, expr, kind in (("ddpost", "drop", "__state-data.health", "Damage"),
                                 ("hpost", "rise", "data.health-__state", "Heal")):
        _, m, _ = member(dn, SIG[key])
        decl = [norm(d) for d in re.findall(r"\bfloat\s+%s\s*=\s*([^;]+);" % var, m)]
        if decl != [expr]:
            problems.append("%s: %s = %r, want [%r]" % (key, var, decl, expr))
        calls = [norm(c) for c in re.findall(r"\bEmit\s*\(([^;]*)\)\s*;", m)]
        want = "subject,DamageNumberRules.Kind.%s,%s,__instance.transform.position" % (kind, var)
        if calls != [want]:
            problems.append("%s: Emit calls %r, want [%r]" % (key, calls, want))
        elif not re.search(r"\bif\s*\(\s*%s\s*>\s*0f\s*\)\s*Emit\s*\(" % var, m):
            problems.append("%s: Emit is not under %s > 0f" % (key, var))
    _, m, _ = member(dn, SIG["bridge"])
    calls = [norm(c) for c in re.findall(r"\bEmit\s*\(([^;]*)\)\s*;", m)]
    if calls != ["view.ViewID,DamageNumberRules.Kind.Damage,applied,view.transform.position"]:
        problems.append("bridge: Emit calls %r" % calls)
    if [norm(d) for d in re.findall(r"\bfloat\s+applied\s*=\s*([^;]+);", m)] != ["DamageNumberRules.AppliedDrop(pre,post)"]:
        problems.append("bridge: applied is not AppliedDrop(pre, post)")
    _, m, _ = member(dn, SIG["emit"])
    notes = [norm(c) for c in re.findall(r"(?<![\w.])Note\s*\(([^;]*)\)\s*;", m)]
    show = m.find("ShouldShow(")
    if notes != ["subject,kind,magnitude,Time.unscaledTime"]:
        problems.append("emit: Note calls %r" % notes)
    elif not (0 <= show < m.find("Note(subject")):
        problems.append("emit: Note is not after the visibility test")
    _, m, _ = member(dn, SIG["note"])
    if len(re.findall(r"\bDamageNumberRules\.Shared\.Note\s*\(\s*subject\s*,\s*kind\s*,\s*magnitude\s*,\s*now\s*,", m)) != 1:
        problems.append("note: the engine call is not exactly once")
    return not problems, problems


def test_B16_the_observed_delta_reaches_the_engine_and_each_deletion_reds():
    t = texts()
    ok, why = run(emit_bridge, t)
    assert ok, why
    cases = [
        ("the ordinary damage emission deleted (DoDamagePostfix)", "DN", EMIT_DAMAGE, "", "ddpost"),
        ("the damage emitted as a heal", "DN", EMIT_DAMAGE,
         EMIT_DAMAGE.replace("Kind.Damage", "Kind.Heal"), "ddpost"),
        ("the damage delta reversed", "DN", "float drop = __state - data.health;",
         "float drop = data.health - __state;", "ddpost"),
        ("the heal emission deleted", "DN",
         "if (rise > 0f) Emit(subject, DamageNumberRules.Kind.Heal, rise, __instance.transform.position);", "", "hpost"),
        ("the direct-writer bridge emits nothing", "DN",
         "Emit(view.ViewID, DamageNumberRules.Kind.Damage, applied, view.transform.position);", "", "bridge"),
        ("Emit stops handing to Note", "DN", "Note(subject, kind, magnitude, Time.unscaledTime);", "", "emit"),
        ("Note stops handing to the engine", "DN", "DamageNumberRules.Shared.Note(", "DamageNumberRules.Shared.Equals(", "note"),
    ]
    for label, key, old, new, where in cases:
        mt = mutate(t, key, old, new)
        ok, problems = run(emit_bridge, mt)
        assert not ok, "%s stayed green" % label
        # span-scoped: only the link the mutation touched is reported
        assert all(p.startswith(where + ":") for p in problems), "%s: %r" % (label, problems)
    # control: an unconditional emission (the > 0f test dropped) is red too,
    # while the matcher still sees the heal row green beside it
    mt = mutate(t, "DN", EMIT_DAMAGE, "Emit(subject, DamageNumberRules.Kind.Damage, drop, __instance.transform.position);")
    ok, problems = run(emit_bridge, mt)
    assert not ok and problems == ["ddpost: Emit is not under drop > 0f"], problems


# ── B17: the draw is wired and the driver ticks (fix 1: a deletion guard) ───

DRAW_CALL = "DamageNumbers.Draw();"


def _depth_at(m, pos):
    d = 0
    for i in range(pos):
        if m[i] == "{":
            d += 1
        elif m[i] == "}":
            d -= 1
    return d


def draw_wiring(t):
    """DrawUI calls DamageNumbers.Draw exactly once, unconditionally (brace
    depth 0 of its body, on the mask, so a comment is not a call); the driver
    is added exactly once and its Update ticks; the Unity tick reads the
    rules' flush and stamps its text; Draw paints that text."""
    problems = []
    _, m, _ = member(t["CU"], SIG["drawui"])
    at = [mm.start() for mm in re.finditer(re.escape(DRAW_CALL), m)]
    if len(at) != 1:
        problems.append("drawui: %d DamageNumbers.Draw() calls" % len(at))
    elif _depth_at(m, at[0]) != 0:
        problems.append("drawui: DamageNumbers.Draw() sits inside a block")
    pl = mask_code(t["PL"])
    n = len(re.findall(r"\bAddComponent\s*<\s*DamageNumberDriver\s*>\s*\(\s*\)", pl))
    if n != 1:
        problems.append("plugin: AddComponent<DamageNumberDriver>() %d times" % n)
    src = t["DN"]
    o, e = _single_span(src, SIG["driver"], RELEASE_SYMBOLS)
    _, m, _ = member(src[o:e], SIG["update"])
    if len(re.findall(r"\bDamageNumbers\.Tick\s*\(\s*Time\.unscaledTime\s*\)\s*;", m)) != 1:
        problems.append("driver: Update does not tick exactly once")
    _, m, _ = member(src, SIG["tick"])
    if len(re.findall(r"\bvar\s+em\s*=\s*DamageNumberRules\.Tick\s*\(\s*now\s*\)\s*;", m)) != 1 \
            or len(re.findall(r"_text\[slot\]\s*=\s*em\[i\]\.Text\s*;", m)) != 1:
        problems.append("tick: the rules' flush is not read and stamped exactly once")
    _, m, _ = member(src, SIG["draw"])
    if len(re.findall(r"\bGUI\.Label\s*\(\s*rect\s*,\s*_text\[i\]\s*,\s*_style\s*\)\s*;", m)) != 1:
        problems.append("draw: the number itself is not painted exactly once per entry")
    return not problems, problems


def test_B17_the_draw_call_and_the_driver_are_wired_and_each_deletion_reds():
    t = texts()
    ok, why = run(draw_wiring, t)
    assert ok, why
    line = "            " + DRAW_CALL
    cases = [
        ("the sole draw call deleted (CompetitiveUI.DrawUI)", "CU", line, "", "drawui"),
        ("the draw call commented out", "CU", line, "            // " + DRAW_CALL, "drawui"),
        ("the draw call put under a dead branch", "CU", line, "            if (PageImguiHidden && !PageImguiHidden) { " + DRAW_CALL + " }", "drawui"),
        ("the draw call doubled", "CU", line, line + " " + DRAW_CALL, "drawui"),
        ("the driver never added", "PL", "go.AddComponent<DamageNumberDriver>();", "", "plugin"),
        ("the driver stops ticking", "DN", "DamageNumbers.Tick(Time.unscaledTime);", "", "driver"),
        ("the tick drops the rules' text", "DN", "_text[slot] = em[i].Text;", "_text[slot] = null;", "tick"),
        ("the number is never painted", "DN", "GUI.Label(rect, _text[i], _style);", "", "draw"),
    ]
    for label, key, old, new, where in cases:
        mt = mutate(t, key, old, new)
        ok, problems = run(draw_wiring, mt)
        assert not ok, "%s stayed green" % label
        assert all(p.startswith(where + ":") for p in problems), "%s: %r" % (label, problems)
    # control: the same matcher finds the hold-Tab board's call beside it at
    # depth 0, and a commented copy of the draw call elsewhere changes nothing
    _, m, _ = member(t["CU"], SIG["drawui"])
    tab = m.find("TabStatsOverlay.Draw();")
    assert tab >= 0 and _depth_at(m, tab) == 0
    mt = mutate(t, "CU", "            TabStatsOverlay.Draw();", "            // " + DRAW_CALL + "\n            TabStatsOverlay.Draw();")
    assert run(draw_wiring, mt)[0]


# ── B18: the draw budget at saturation (fix 1) ──────────────────────────────

LOOP_HEAD = re.compile(r"\bfor\s*\(\s*int\s+i\s*=\s*0\s*;\s*i\s*<\s*DamageNumberRules\.MaxLive\s*;\s*i\+\+\s*\)")
PROJ = re.compile(r"\bcam\.WorldToScreenPoint\s*\(")
REUSE = re.compile(r"\bi\s*==\s*first\s*\?\s*a\s*:\s*cam\.WorldToScreenPoint\s*\(\s*_world\[i\]\s*\)")
LABEL = re.compile(r"\bGUI\.Label\s*\(")
VALUE_TYPES = {"Rect", "Color"}


def _stmt_end(m, i):
    """End of the statement starting at i: a block, an if with its body, or
    up to the next semicolon."""
    i = _ws(m, i)
    if m[i] == "{":
        return _match(m, i)
    if m.startswith("if", i) and not _w(m, i + 2):
        j = _ws(m, i + 2)
        return _stmt_end(m, _match(m, j, "(", ")"))
    return m.index(";", i) + 1


def draw_budget(t):
    """(projections, labels, problems) for one Repaint with MaxLive live
    labels, counted from Draw's own span: a call outside every per-entry loop
    runs once; a call inside one runs MaxLive times, less one when it is the
    else-arm of `i == first ? a :` (the first entry reuses the scale's own
    projection of _world[first])."""
    max_live = int(re.search(r"internal const int MaxLive = (\d+);", t["DR"]).group(1))
    _, m, _ = member(t["DN"], SIG["draw"])
    loops = []
    for mm in LOOP_HEAD.finditer(m):
        loops.append((mm.start(), _stmt_end(m, mm.end())))
    problems = []
    proj = 0
    for mm in PROJ.finditer(m):
        inside = any(o < mm.start() < e for o, e in loops)
        if not inside:
            proj += 1
            continue
        reused = any(r.start() <= mm.start() < r.end() for r in REUSE.finditer(m))
        proj += max_live - 1 if reused else max_live
    labels = 0
    for mm in LABEL.finditer(m):
        labels += max_live if any(o < mm.start() < e for o, e in loops) else 1
    for o, e in loops:
        for nm in re.finditer(r"\bnew\s+(\w+)", m[o:e]):
            if nm.group(1) not in VALUE_TYPES:
                problems.append("a managed allocation per entry: new %s" % nm.group(1))
    styles = [mm.start() for mm in re.finditer(r"\bnew\s+GUIStyle\s*\(", m)]
    if len(styles) != 1:
        problems.append("%d GUIStyle constructions" % len(styles))
    else:
        conds = guard_chain(t["DN"], SIG["draw"], "new GUIStyle(")
        if not any(norm(c) == "_style==null||_styleScreenH!=Screen.height" for c in conds):
            problems.append("the style is not cached (conds %r)" % conds)
    if proj > 25:
        problems.append("%d projections at MaxLive %d, budget 25" % (proj, max_live))
    if labels > 48:
        problems.append("%d labels at MaxLive %d, budget 48" % (labels, max_live))
    return proj, labels, problems


def test_B18_a_saturated_repaint_makes_at_most_25_projections_and_48_labels_and_allocates_nothing():
    t = texts()
    proj, labels, problems = draw_budget(t)
    assert (proj, labels, problems) == (25, 48, []), (proj, labels, problems)
    reuse = "Vector3 sp = i == first ? a : cam.WorldToScreenPoint(_world[i]);"
    cases = [
        ("no reuse (the form before fix 1)", "DN", reuse, "Vector3 sp = cam.WorldToScreenPoint(_world[i]);", 26, 48),
        ("the reuse keyed on the wrong entry", "DN", reuse, "Vector3 sp = i == 0 ? a : cam.WorldToScreenPoint(_world[i]);", 26, 48),
        ("an extra projection per entry", "DN", reuse, reuse + " Vector3 sp2 = cam.WorldToScreenPoint(_world[i]);", 49, 48),
        ("a third label per entry", "DN", "GUI.Label(rect, _text[i], _style);",
         "GUI.Label(rect, _text[i], _style); GUI.Label(rect, _text[i], _style);", 25, 72),
        ("MaxLive raised to 25", "DR", "internal const int MaxLive = 24;", "internal const int MaxLive = 25;", 26, 50),
    ]
    for label, key, old, new, wp, wl in cases:
        mt = mutate(t, key, old, new)
        p, l, pr = draw_budget(mt)
        assert (p, l) == (wp, wl) and pr, "%s: %d projections, %d labels, %r" % (label, p, l, pr)
    # allocation mutations: counts unchanged, the allocation reds alone
    mt = mutate(t, "DN", "Color c = _color[i];", "Color c = _color[i]; var gc = new GUIContent(_text[i]);")
    p, l, pr = draw_budget(mt)
    assert (p, l) == (25, 48) and pr == ["a managed allocation per entry: new GUIContent"], pr
    mt = mutate(t, "DN", "if (_style == null || _styleScreenH != Screen.height)", "if (true)")
    p, l, pr = draw_budget(mt)
    assert (p, l) == (25, 48) and len(pr) == 1 and pr[0].startswith("the style is not cached"), pr
    # control: the search loop runs MaxLive times but projects nothing, and a
    # projection planted there is multiplied (so the loop scoping is real)
    mt = mutate(t, "DN", "if (_text[i] != null && ring.IsLive(i, now)) { first = i; break; }",
                "if (_text[i] != null && ring.IsLive(i, now)) { cam.WorldToScreenPoint(_world[i]); first = i; break; }")
    p, l, pr = draw_budget(mt)
    assert p == 25 + 24 and pr, (p, pr)
