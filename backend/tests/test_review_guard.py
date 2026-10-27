"""A10 and design report finding 5: the no-tunables guard
(backend/tools/review_guard.py) passes the real tree and refuses every
planted form of a deciding value -- inline, hoisted, imported, encoded, in SQL
or text, in a comment, as a settings or environment read, as a changed pinned
bound -- and, in range mode, one that lived only in an earlier commit.

Every planted value is synthetic. Each mutant runs against a copy of the
review modules, with the unaltered copy as its negative control."""

import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
API = os.path.join(REPO, "backend", "api")
sys.path.insert(0, os.path.join(REPO, "backend", "tools"))

import review_guard as g  # noqa: E402

MODULES = ("review_boot", "review_measures", "review_rules", "seat_evidence")


def _copy(tmp):
    dst = os.path.join(str(tmp), "backend", "api")
    os.makedirs(dst)
    for m in MODULES:
        shutil.copy(os.path.join(API, m + ".py"), dst)
    return str(tmp), dst


def _edit(dst, mod, old, new, count=1):
    p = os.path.join(dst, mod + ".py")
    with open(p, encoding="utf-8") as f:
        s = f.read()
    assert s.count(old) == count, (mod, old)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s.replace(old, new))


def _classes(repo):
    """The finding classes of a tree (an ambiguity's binding sites dropped:
    `ambiguous (m:1 m:2)` is the class `ambiguous`), and the findings whole."""
    findings, _n = g.tree_mode(repo)
    return sorted({cls.split(" ")[0] for _l, _line, cls in findings}), findings


def test_a10_the_real_tree_is_clean():
    findings, n = g.tree_mode(REPO)
    assert findings == [] and n == 1


def test_the_copied_tree_is_clean(tmp_path):
    repo, _dst = _copy(tmp_path)
    assert _classes(repo)[0] == []


MEASURE = 'return ctx.r["rec"]["imp"][2]\n'

MUTANTS = [
    ("inline", "review_measures", MEASURE, 'return ctx.r["rec"]["imp"][2] + 7\n', "number"),
    ("float", "review_measures", MEASURE, 'return ctx.r["rec"]["imp"][2] * 0.7\n', "number"),
    ("encoded_int", "review_measures", MEASURE, 'return ctx.r["rec"]["imp"][2] + int("7")\n', "call"),
    ("encoded_len", "review_measures", MEASURE,
     'return ctx.r["rec"]["imp"][2] + len("abcdefg")\n', "call"),
    ("encoded_ord", "review_measures", MEASURE, 'return ctx.r["rec"]["imp"][2] + ord("x")\n', "call"),
    ("text", "review_measures", 'POP_BASE = ("m.is_ranked IS TRUE',
     'POP_BASE = ("m.p1_bullets_fired > 17 AND m.is_ranked IS TRUE', "text"),
    ("comment", "review_rules", "def eval_expr(node, ctx, memo, rs):\n",
     "def eval_expr(node, ctx, memo, rs):\n    # a slack of 7 is tolerated\n", "text"),
    ("env", "review_rules", "def rules_root() -> str:\n",
     'def rules_root() -> str:\n    os.environ.get("SCR_SYNTHETIC_SLACK")\n', "env"),
    ("pinned", "review_rules", '"work_max": 200000,', '"work_max": 200000, "slack": 0,', "pinned"),
    ("hoisted_rooted", "seat_evidence", "async def evaluate_one(db, key: str, lo, hi, registry, rs) -> tuple:\n",
     "SYNTHETIC_FLOOR = 7\n\n\nasync def evaluate_one(db, key: str, lo, hi, registry, rs) -> tuple:\n"
     "    _unused = SYNTHETIC_FLOOR\n", "number"),
    ("setting", "seat_evidence", 'if await setting(db, "seat_evidence_worker") != "1":\n            return {"off": 1}\n        cands',
     'if await setting(db, "review_post_synthetic") != "1":\n            return {"off": 1}\n        cands', "setting"),
    ("rooted_sql", "seat_evidence", '"WHERE id = :i FOR UPDATE"), {"i": finding_id})',
     '"WHERE id = :i AND 17 > 1 FOR UPDATE"), {"i": finding_id})', "text"),
]


@pytest.mark.parametrize("name,mod,old,new,cls", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_each_planted_form_is_refused(tmp_path, name, mod, old, new, cls):
    repo, dst = _copy(tmp_path)
    count = 1 if name not in ("inline", "float", "encoded_int", "encoded_len", "encoded_ord") else None
    if count is None:
        with open(os.path.join(dst, mod + ".py"), encoding="utf-8") as f:
            count = f.read().count(old)
        assert count >= 1
    _edit(dst, mod, old, new, count)
    classes, findings = _classes(repo)
    assert cls in classes, (name, findings)
    # the report names the line and class only, never the text
    for label, line, c in findings:
        assert isinstance(line, int) and c.split(" ")[0] in (
            "number", "text", "call", "setting", "env", "pinned", "select", "bool", "unresolved", "ambiguous")


def test_a_hoisted_module_constant_in_a_judging_module_is_refused(tmp_path):
    repo, dst = _copy(tmp_path)
    _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\nSYNTHETIC_SLACK = 7\n")
    _edit(dst, "review_measures", 'return ctx.r["rec"]["imp"][2]\n',
          'return ctx.r["rec"]["imp"][2] + SYNTHETIC_SLACK\n',
          count=open(os.path.join(dst, "review_measures.py"), encoding="utf-8").read().count(
              'return ctx.r["rec"]["imp"][2]\n'))
    assert "number" in _classes(repo)[0]


def test_an_imported_local_module_is_followed_and_scanned_whole(tmp_path):
    repo, dst = _copy(tmp_path)
    with open(os.path.join(dst, "synthetic_values.py"), "w", encoding="utf-8") as f:
        f.write("FLOOR = 7\n")
    _edit(dst, "review_measures", "from __future__ import annotations\n",
          "from __future__ import annotations\n\nimport synthetic_values\n")
    classes, findings = _classes(repo)
    assert "number" in classes
    assert any("synthetic_values.py" in label for label, _l, _c in findings)


def test_a_module_imported_by_a_rooted_function_is_followed(tmp_path):
    repo, dst = _copy(tmp_path)
    with open(os.path.join(dst, "synthetic_cut.py"), "w", encoding="utf-8") as f:
        f.write("CUT = 7\n")
    _edit(dst, "seat_evidence", "async def evaluate_one(db, key: str, lo, hi, registry, rs) -> tuple:\n",
          "async def evaluate_one(db, key: str, lo, hi, registry, rs) -> tuple:\n"
          "    from synthetic_cut import CUT  # noqa: F401\n")
    classes, findings = _classes(repo)
    assert any("synthetic_cut.py" in label and c == "number" for label, _l, c in findings)


def test_a_constant_no_review_root_reaches_is_not_judged_in_a_rooted_module(tmp_path):
    """Negative control for the reach: contract bounds of the ingestion path
    (not reachable from any review root) carry numbers and are not refused."""
    repo, dst = _copy(tmp_path)
    _edit(dst, "seat_evidence", "SEAT_HOURLY_CAP = 40\n", "SEAT_HOURLY_CAP = 41\n")
    assert _classes(repo)[0] == []


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t",
                           *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def test_range_mode_sees_a_value_that_lived_only_in_an_earlier_commit(tmp_path):
    repo, dst = _copy(tmp_path)
    subprocess.run(["git", "init", "-q", repo], check=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\nSYNTHETIC_SLACK = 7\n")
    _git(repo, "commit", "-q", "-am", "add")
    _edit(dst, "review_measures", "REGISTRY: dict = {}\nSYNTHETIC_SLACK = 7\n", "REGISTRY: dict = {}\n")
    _git(repo, "commit", "-q", "-am", "remove")
    tip = _git(repo, "rev-parse", "HEAD")
    assert g.tree_mode(repo)[0] == []                       # the tip alone is clean
    findings, n = g.range_mode(repo, base, tip)
    assert n == 2 and len(findings) == 1 and findings[0][2] == "number"
    clean, _ = g.range_mode(repo, base, base)
    assert clean == []


def test_the_command_line_exit_codes(tmp_path, capsys):
    repo, dst = _copy(tmp_path)
    assert g.main(["tree", repo]) == 0
    _edit(dst, "review_rules", '"work_max": 200000,', '"work_max": 200001,')
    assert g.main(["tree", repo]) == 1
    out = capsys.readouterr().out
    assert "pinned" in out and "200001" not in out
    assert g.main([]) == 2
    # an unresolved value reaching a decision is no verdict (3), over a finding (1)
    ind = _measure_indent(dst)
    _edit(dst, "review_measures", ind + MEASURE,
          ind + "cut = sum(x for x in (0, 0))\n" + ind + V.replace("@@", ind) + "return v if v > cut else None\n")
    assert g.main(["tree", repo]) == 3
    assert "no verdict" in capsys.readouterr().out


# -- design finding M-5: structural numbers, selectors and booleans BY CONTEXT --
# Each planted form is refused, and its control -- the same shape with a
# structural use -- is not, so the context (not the token) decides.
CONTEXT = [
    ("threshold_two",
     'v = ctx.r["rec"]["imp"][2]\n@@return v if v > 2 else None\n',
     'v = ctx.r["rec"]["imp"][2]\n@@return v if v > 0 else None\n', "number"),
    ("scaled_two",
     'return ctx.r["rec"]["imp"][2] * 2\n',
     'return ctx.r["rec"]["imp"][2] // 2\n', "number"),
    ("equality_two",
     'return None if ctx.r["rec"]["imp"][2] == 2 else ctx.r["rec"]["imp"][2]\n',
     'return None if ctx.r["rec"]["imp"][2] == 1 else ctx.r["rec"]["imp"][2]\n', "number"),
    ("selector",
     'return None if ctx.r.get("kind") == "synthetic_kind" else ctx.r["rec"]["imp"][2]\n',
     'return None if ctx.r.get("kind") == "seat" else ctx.r["rec"]["imp"][2]\n', "select"),
    ("selector_member",
     'return None if ctx.r.get("kind") in ("seat", "synthetic_kind") else ctx.r["rec"]["imp"][2]\n',
     'return None if ctx.r.get("kind") in ("seat", "game") else ctx.r["rec"]["imp"][2]\n', "select"),
    ("bool_compare",
     'return None if ctx.two == False else ctx.r["rec"]["imp"][2]\n',
     'return None if ctx.two is False else ctx.r["rec"]["imp"][2]\n', "bool"),
    ("bool_operand",
     'return ctx.r["rec"]["imp"][2] if (ctx.two or True) else None\n',
     'return ctx.r["rec"]["imp"][2] if (ctx.two or ctx.i) else None\n', "bool"),
]


def _measure_indent(dst):
    with open(os.path.join(dst, "review_measures.py"), encoding="utf-8") as f:
        src = f.read()
    i = src.index(MEASURE)
    return src[src.rindex("\n", 0, i) + 1:i]


@pytest.mark.parametrize("name,planted,control,cls", CONTEXT, ids=[c[0] for c in CONTEXT])
def test_m5_context_decides_and_the_control_passes(tmp_path, name, planted, control, cls):
    for body, want in ((planted, [cls]), (control, [])):
        repo, dst = _copy(tmp_path / ("planted" if want else "control"))
        ind = _measure_indent(dst)
        _edit(dst, "review_measures", ind + MEASURE, ind + body.replace("@@", ind))
        assert _classes(repo)[0] == want, (name, want)


def test_m5_a_module_level_boolean_toggle_is_refused_unless_pinned(tmp_path, monkeypatch):
    repo, dst = _copy(tmp_path)
    _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\nSYNTHETIC_STRICT = True\n")
    assert _classes(repo)[0] == ["bool"]
    monkeypatch.setitem(g.PINNED, ("review_measures", "SYNTHETIC_STRICT"), True)
    assert _classes(repo)[0] == []


def test_m5_no_number_is_structural_everywhere():
    """The global allowlist is gone: every structural set is tied to a context."""
    assert not hasattr(g, "ALLOWED_NUMBERS")
    assert set(g.STRUCTURAL) == {"compare_any", "compare_eq", "binop", "wrap", "augassign", "call",
                                 "plain"}


# -- round 2 M5: a decision is judged at its USE, following the binding --------------
# Each alias form hoists the deciding value out of the comparison; the planted
# form is refused and its control (the same binding used structurally, or a
# binding that is not a constant) is not. `top` goes in at module level,
# `body` replaces the measure's return line.
V = 'v = ctx.r["rec"]["imp"][2]\n@@'
ALIASES = [
    ("module_constant",
     ("SYNTHETIC_CUT = 1\n", V + "return v if v > SYNTHETIC_CUT else None\n"),
     ("SYNTHETIC_CUT = 1\n", V + "return v if v == SYNTHETIC_CUT else None\n"), "number"),
    ("local_constant",
     ("", "cut = 1\n@@" + V + "return v if v > cut else None\n"),
     ("", "cut = 1\n@@" + V + "return v if v == cut else None\n"), "number"),
    ("class_attribute",
     ("class _Synthetic:\n    CUT = 1\n", V + "return v if v > _Synthetic.CUT else None\n"),
     ("class _Synthetic:\n    CUT = 1\n", V + "return v if v == _Synthetic.CUT else None\n"), "number"),
    ("self_attribute",
     ("class _Synthetic:\n    CUT = 1\n\n    def keep(self, v):\n        return v if v > self.CUT else None\n",
      'return ctx.r["rec"]["imp"][2]\n'),
     ("class _Synthetic:\n    CUT = 1\n\n    def keep(self, v):\n        return v if v == self.CUT else None\n",
      'return ctx.r["rec"]["imp"][2]\n'), "number"),
    ("dict_value",
     ('SYNTHETIC_CUTS = {"cut": 1}\n', V + 'return v if v > SYNTHETIC_CUTS["cut"] else None\n'),
     ('SYNTHETIC_CUTS = {"cut": 1}\n', V + 'return v if v == SYNTHETIC_CUTS["cut"] else None\n'), "number"),
    ("string_alias",
     ('SYNTHETIC_KIND = "synthetic_kind"\n',
      'return None if ctx.r.get("kind") == SYNTHETIC_KIND else ctx.r["rec"]["imp"][2]\n'),
     ('SYNTHETIC_KIND = "seat"\n',
      'return None if ctx.r.get("kind") == SYNTHETIC_KIND else ctx.r["rec"]["imp"][2]\n'), "select"),
    ("local_boolean",
     ("", "strict = True\n@@" + 'return ctx.r["rec"]["imp"][2] if strict else None\n'),
     ("", "strict = bool(ctx.two)\n@@" + 'return ctx.r["rec"]["imp"][2] if strict else None\n'), "bool"),
    ("default_boolean",
     ("def _synthetic(v, strict=True):\n    return v if strict else None\n", 'return ctx.r["rec"]["imp"][2]\n'),
     ("def _synthetic(v, strict):\n    return v if strict else None\n", 'return ctx.r["rec"]["imp"][2]\n'),
     "bool"),
    ("returned_boolean",
     ("def _synthetic_strict():\n    return True\n",
      'return ctx.r["rec"]["imp"][2] if _synthetic_strict() else None\n'),
     ("def _synthetic_strict():\n    return bool(REGISTRY)\n",
      'return ctx.r["rec"]["imp"][2] if _synthetic_strict() else None\n'), "bool"),
]


@pytest.mark.parametrize("name,planted,control,cls", ALIASES, ids=[a[0] for a in ALIASES])
def test_m5_round2_an_aliased_decision_is_judged_at_its_use(tmp_path, name, planted, control, cls):
    for (top, body), want in ((planted, [cls]), (control, [])):
        repo, dst = _copy(tmp_path / ("planted" if want else "control"))
        ind = _measure_indent(dst)
        _edit(dst, "review_measures", ind + MEASURE, ind + body.replace("@@", ind))
        if top:
            _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\n\n\n" + top + "\n\n")
        assert _classes(repo)[0] == want, (name, want, _classes(repo)[1])


REBOUND = [
    # (name, the binding lines, the classes a decision `v > cut` gets). Fix
    # pass 5: more than one binding with a closed one does not resolve to one
    # binding -- AMBIGUOUS, the exit-3 refusal -- and every closed member is
    # still judged as if it stood alone.
    ("constant_then_runtime", "cut = 1\n@@cut = ctx.i\n@@", ["ambiguous", "number"]),
    ("two_constants", "cut = 0\n@@cut = -1\n@@", ["ambiguous", "number"]),
    ("constant_in_a_loop", "for cut in ctx.items:\n@@    pass\n@@cut = 1\n@@", ["ambiguous", "number"]),
    # every closed binding structural where the decision uses it: still two
    # bindings, still ambiguous (no member finding)
    ("two_structural_constants", "cut = 0\n@@cut = 0\n@@", ["ambiguous"]),
    # controls: bindings that all read runtime input, and a counter
    ("runtime_twice", "cut = ctx.i\n@@cut = ctx.j\n@@", []),
    ("counter", "cut = 0\n@@cut += ctx.i\n@@", []),
    ("step_by_assignment", "cut = 0\n@@cut = cut + ctx.i\n@@", []),
]


@pytest.mark.parametrize("name,binds,want", REBOUND, ids=[r[0] for r in REBOUND])
def test_m5_fix4_a_rebound_name_is_decided_over_every_binding(tmp_path, name, binds, want):
    """Fix pass 4, M5(a): a name bound more than once is never silently
    runtime when any binding is closed; fix pass 5, M5(i): it is AMBIGUOUS at
    the decision (exit 3), and EVERY closed value is judged there too."""
    repo, dst = _copy(tmp_path)
    ind = _measure_indent(dst)
    _edit(dst, "review_measures", ind + MEASURE,
          ind + (binds + V).replace("@@", ind) + "return v if v > cut else None\n")
    assert _classes(repo)[0] == want, _classes(repo)[1]


def test_m5_fix4_a_module_name_rebound_through_global_is_refused(tmp_path):
    repo, dst = _copy(tmp_path)
    _edit(dst, "review_measures", "REGISTRY: dict = {}\n",
          "REGISTRY: dict = {}\nSYNTHETIC_CUT = None\n\n\ndef _synthetic_set():\n"
          "    global SYNTHETIC_CUT\n    SYNTHETIC_CUT = 1\n\n\n")
    ind = _measure_indent(dst)
    _edit(dst, "review_measures", ind + MEASURE,
          ind + V.replace("@@", ind) + "return v if v > SYNTHETIC_CUT else None\n")
    assert _classes(repo)[0] == ["ambiguous", "number"], _classes(repo)[1]


@pytest.mark.parametrize("decl, want", [("", []), ("    global SYNTHETIC_CUT\n", ["ambiguous", "number"])],
                         ids=["a_local_of_the_same_name", "control_declared_global"])
def test_m5_fix4_a_top_level_functions_locals_are_not_module_bindings(tmp_path, decl, want):
    """A top-level function's local binds in the function's scope only: it is
    not a second binding of the module name it shares (without `global`, the
    module value stays the one binding); the control declares it global."""
    repo, dst = _copy(tmp_path)
    _edit(dst, "review_measures", "REGISTRY: dict = {}\n",
          "REGISTRY: dict = {}\nSYNTHETIC_CUT = None\n\n\ndef _synthetic_local():\n"
          + decl + "    SYNTHETIC_CUT = 1\n    return SYNTHETIC_CUT\n\n\n")
    ind = _measure_indent(dst)
    _edit(dst, "review_measures", ind + MEASURE,
          ind + V.replace("@@", ind) + "return v if v > SYNTHETIC_CUT else None\n")
    assert _classes(repo)[0] == want, _classes(repo)[1]


# -- fix pass 4, M5(a): attributes resolve by OWNER and use site ---------------------
# The round-4 input: two unrelated classes store `self.cut`; a decision on one
# class's `self.cut` is judged by that class's binding, never dropped. Each
# planted shape has a control whose deciding binding reads runtime input.
OWNER = "class _SyntheticA:\n    def __init__(self, ctx):\n        self.cut = %s\n\n" \
        "    def keep(self, v):\n        return v if v > self.cut else None\n\n\n" \
        "class _SyntheticB:\n    def __init__(self, ctx):\n        self.cut = %s\n"
OWNERS = [
    ("reviewers_input_both_constant", OWNER % ("1", "1"), OWNER % ("ctx.i", "1"), ["number"]),
    ("other_owner_runtime", OWNER % ("1", "ctx.i"), OWNER % ("ctx.i", "ctx.j"), ["number"]),
    # an unnamed receiver's store may be either class's: the class's own closed
    # binding is still judged beside it
    ("unnamed_receiver_store", OWNER % ("1", "1") + "\n\ndef _synthetic_set(o, ctx):\n    o.cut = ctx.i\n",
     OWNER % ("ctx.i", "1") + "\n\ndef _synthetic_set(o, ctx):\n    o.cut = ctx.j\n", ["ambiguous", "number"]),
    # a read on an unnamed receiver sees every binding of the name: B's closed
    # binding is judged at A-blind reads although A's binding is runtime
    ("unnamed_receiver_read", OWNER % ("ctx.i", "1") + "\n\ndef _synthetic_read(o, v):\n    return v > o.cut\n",
     OWNER % ("ctx.i", "ctx.j") + "\n\ndef _synthetic_read(o, v):\n    return v > o.cut\n",
     ["ambiguous", "number"]),
    # a subclass's binding is one the base class's read can see
    ("subclass_binding", OWNER.replace("class _SyntheticB:", "class _SyntheticB(_SyntheticA):") % ("ctx.i", "1"),
     OWNER.replace("class _SyntheticB:", "class _SyntheticB(_SyntheticA):") % ("ctx.i", "ctx.j"),
     ["ambiguous", "number"]),
    # two methods of one name a call may reach, returning different constants
    ("method_by_owner",
     "class _SyntheticA:\n    def cut(self):\n        return 1\n\n    def keep(self, v):\n"
     "        return v > self.cut()\n\n\nclass _SyntheticB:\n    def cut(self):\n        return -1\n",
     "class _SyntheticA:\n    def cut(self):\n        return 0\n\n    def keep(self, v):\n"
     "        return v > self.cut()\n\n\nclass _SyntheticB:\n    def cut(self):\n        return -1\n",
     ["number"]),
]


@pytest.mark.parametrize("name,planted,control,want", OWNERS, ids=[o[0] for o in OWNERS])
def test_m5_fix4_an_attribute_is_resolved_by_owner_or_refused(tmp_path, name, planted, control, want):
    for top, expect in ((planted, want), (control, [])):
        repo, dst = _copy(tmp_path / ("planted" if expect else "control"))
        _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\n\n\n" + top + "\n\n")
        assert _classes(repo)[0] == expect, (name, _classes(repo)[1])


def test_m5_fix4_a_peer_modules_binding_counts_for_an_unnamed_receiver(tmp_path):
    """A store in another judged module on a receiver whose class cannot be
    named is one the read can see."""
    for rr_line, want in (("o.cut = 1", ["ambiguous", "number"]), ("o.other_attr = 1", [])):
        repo, dst = _copy(tmp_path / rr_line.split(" ")[0].replace(".", "_"))
        _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\n\n\n"
              + OWNER % ("ctx.i", "ctx.j") + "\n\n")
        _edit(dst, "review_rules", RR_ANCHOR, RR_ANCHOR + "\n\ndef _synthetic_set(o, ctx):\n"
              "    %s\n\n\n" % rr_line)
        assert _classes(repo)[0] == want, (rr_line, _classes(repo)[1])


def _decision_line(dst):
    with open(os.path.join(dst, "review_measures.py"), encoding="utf-8") as f:
        return [i for i, ln in enumerate(f.read().splitlines(), 1) if "return v if v > cut else None" in ln][0]


# A value chosen at run time between a closed value and runtime input, by a
# conditional expression or a boolean operator: the closed value is judged AT
# THE DECISION (the finding names the decision's line). Each has a control
# whose closed value is structural there.
CHOSEN = [
    ("conditional_arm", "cut = 1 if ctx.i else ctx.j\n@@", "cut = 0 if ctx.i else ctx.j\n@@"),
    ("or_default", "cut = ctx.i or 1\n@@", "cut = ctx.i or 0\n@@"),
    ("and_operand", "cut = ctx.i and -1\n@@", "cut = ctx.i and 0\n@@"),
]


@pytest.mark.parametrize("name,planted,control", CHOSEN, ids=[c[0] for c in CHOSEN])
def test_m5_fix4_a_closed_value_chosen_at_run_time_is_judged_at_the_decision(tmp_path, name, planted, control):
    for binds, want in ((planted, ["number"]), (control, [])):
        repo, dst = _copy(tmp_path / ("p" if want else "c"))
        ind = _measure_indent(dst)
        _edit(dst, "review_measures", ind + MEASURE,
              ind + (binds + V).replace("@@", ind) + "return v if v > cut else None\n")
        line = _decision_line(dst)
        assert [c for _l, n, c in _classes(repo)[1] if n == line] == want, (name, _classes(repo)[1])


# An attribute bound to a container: what its writes put in it decides its
# value, on any receiver -- runtime writes make it runtime, constant-only
# writes leave it unresolved (never the empty container it started as).
CONTAINER = "class _SyntheticC:\n    def __init__(self):\n        self.cuts = {}\n\n" \
            "    def put(self, ctx):\n        self.cuts[\"k\"] = %s\n\n" \
            "    def keep(self, v):\n        return v if v > self.cuts.get(\"k\", 0) else None\n"


def test_m5_fix4_an_attribute_container_is_judged_by_its_writes(tmp_path):
    for value, want in (("ctx.i", []), ("1", ["unresolved"])):
        repo, dst = _copy(tmp_path / ("runtime" if not want else "closed"))
        _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\n\n\n"
              + CONTAINER % value + "\n\n")
        assert _classes(repo)[0] == want, (value, _classes(repo)[1])


def test_m5_fix4_a_recursive_function_is_judged_by_its_own_returns():
    """A recursive call yields one of the function's own returns: it adds no
    value, so the closed return is judged and a runtime-only function stays
    runtime (never unresolved through its own recursion)."""
    src = ("def _synthetic(n):\n    if n:\n        return _synthetic(n - 1)\n    return %s\n\n\n"
           "def f(value, n):\n    return value > _synthetic(n)\n")
    s = g._Scan("review_rules", "synthetic", src % "-1")
    s.check_nodes(s.tree.body)
    assert [c for _l, line, c in s.findings if line == 8] == ["number"]
    clean = g._Scan("review_rules", "synthetic", src % "n")
    clean.check_nodes(clean.tree.body)
    assert clean.findings == []


def test_m5_fix4_differing_constant_returns_are_each_judged():
    src = ("def _synthetic(flag):\n    if flag:\n        return 0\n    return 2\n\n\n"
           "def f(value, flag):\n    return value > _synthetic(flag)\n")
    s = g._Scan("review_rules", "synthetic", src)
    s.check_nodes(s.tree.body)
    assert [c for _l, line, c in s.findings if line == 8] == ["number"]    # the 2, at the decision
    # a return reading runtime input does not hide the closed one
    mixed = g._Scan("review_rules", "synthetic", src.replace("return 0", "return flag"))
    mixed.check_nodes(mixed.tree.body)
    assert [c for _l, line, c in mixed.findings if line == 8] == ["number"]
    same = g._Scan("review_rules", "synthetic", src.replace("return 2", "return 1").replace("value >", "value =="))
    same.check_nodes(same.tree.body)
    assert same.findings == []


def test_m5_fix4_a_closed_call_into_a_library_is_refused():
    """A library function given only constants has no runtime input: its
    result reaching a decision is refused, never read as runtime."""
    src = "import math\n\nCUT = math.floor(%s)\n\n\ndef f(value, ctx):\n    return value > CUT\n"
    s = g._Scan("review_rules", "synthetic", src % "2.5")
    s.check_nodes(s.tree.body)
    assert [c for _l, _line, c in s.findings if c == "unresolved"] == ["unresolved"]
    # control: the same call on runtime input, and a method of a runtime object
    for arg in ("ctx.i", "ctx.cut.floor(2)"):
        clean = g._Scan("review_rules", "synthetic", (src % arg).replace("CUT = math.floor(ctx.cut.floor(2))",
                                                                         "CUT = ctx.cut.floor(2)"))
        clean.check_nodes(clean.tree.body)
        assert [c for _l, _line, c in clean.findings if c == "unresolved"] == [], arg



# -- fix pass 3, M5(b): constants resolve TRANSITIVELY at their use, or refuse ----
# Round 3's carry: chained and annotated bindings, container accessors,
# instance and imported attributes and constant-return calls are followed to
# their value; a value with no runtime input the guard cannot evaluate is
# refused as `unresolved` wherever it reaches a decision. Each form is planted
# with a threshold use (refused) and its control (the same binding used
# structurally, or fed by runtime input) is clean. `top` goes in at module
# level of review_measures, `body` replaces the measure's return line, `rr`
# (when given) is appended to review_rules.
TRANSITIVE = [
    ("chained_verbatim",
     ("base = 1\ncut = base\n", V + "return v if v > cut else None\n"),
     ("base = 1\ncut = base\n", V + "return v if v == cut else None\n"), "number"),
    ("chained_local",
     ("", "base = 1\n@@cut = base\n@@" + V + "return v if v > cut else None\n"),
     ("", "base = 1\n@@cut = base\n@@" + V + "return v if v == cut else None\n"), "number"),
    ("chained_three",
     ("SYNTHETIC_A = 1\nSYNTHETIC_B = SYNTHETIC_A\nSYNTHETIC_C = SYNTHETIC_B\n",
      V + "return v if v > SYNTHETIC_C else None\n"),
     ("SYNTHETIC_A = 1\nSYNTHETIC_B = SYNTHETIC_A\nSYNTHETIC_C = SYNTHETIC_B\n",
      V + "return v if v == SYNTHETIC_C else None\n"), "number"),
    ("annotated_module",
     ("SYNTHETIC_CUT: int = 1\n", V + "return v if v > SYNTHETIC_CUT else None\n"),
     ("SYNTHETIC_CUT: int = 1\n", V + "return v if v == SYNTHETIC_CUT else None\n"), "number"),
    ("annotated_local",
     ("", "cut: int = 1\n@@" + V + "return v if v > cut else None\n"),
     ("", "cut: int = 1\n@@" + V + "return v if v == cut else None\n"), "number"),
    ("tuple_index",
     ("SYNTHETIC_CUTS = (0, 1)\n", V + "return v if v > SYNTHETIC_CUTS[1] else None\n"),
     ("SYNTHETIC_CUTS = (0, 1)\n", V + "return v if v == SYNTHETIC_CUTS[1] else None\n"), "number"),
    ("dict_get",
     ('SYNTHETIC_CUTS = {"cut": 1}\n', V + 'return v if v > SYNTHETIC_CUTS.get("cut") else None\n'),
     ('SYNTHETIC_CUTS = {"cut": 1}\n', V + 'return v if v == SYNTHETIC_CUTS.get("cut") else None\n'),
     "number"),
    ("tuple_member",
     ('SYNTHETIC_KINDS = ("seat", "synthetic_kind")\n',
      'return None if ctx.r.get("kind") in SYNTHETIC_KINDS else ctx.r["rec"]["imp"][2]\n'),
     ('SYNTHETIC_KINDS = ("seat", "game")\n',
      'return None if ctx.r.get("kind") in SYNTHETIC_KINDS else ctx.r["rec"]["imp"][2]\n'), "select"),
    ("instance_attribute",
     ("class _Synthetic:\n    def __init__(self):\n        self.cut = 1\n\n"
      "    def keep(self, v):\n        return v if v > self.cut else None\n", 'return ctx.r["rec"]["imp"][2]\n'),
     ("class _Synthetic:\n    def __init__(self):\n        self.cut = 1\n\n"
      "    def keep(self, v):\n        return v if v == self.cut else None\n", 'return ctx.r["rec"]["imp"][2]\n'),
     "number"),
    ("constant_return_call",
     ("def _synthetic_cut(x):\n    return 1\n", V + "return v if v > _synthetic_cut(v) else None\n"),
     ("def _synthetic_cut(x):\n    return 1\n", V + "return v if v == _synthetic_cut(v) else None\n"),
     "number"),
    ("constant_return_method",
     ("class _Synthetic:\n    @staticmethod\n    def cut():\n        return 1\n",
      V + "return v if v > _Synthetic.cut() else None\n"),
     ("class _Synthetic:\n    @staticmethod\n    def cut():\n        return 1\n",
      V + "return v if v == _Synthetic.cut() else None\n"), "number"),
    # unresolved: closed (no runtime input) but not evaluable -> refused at a decision
    ("unresolved_call",
     ("def _synthetic_plus(x):\n    return x + 1\n", V + "return v if v > _synthetic_plus(1) else None\n"),
     ("def _synthetic_plus(x):\n    return x + 1\n", V + "return v if v > _synthetic_plus(v) else None\n"),
     "unresolved"),
    ("unresolved_comprehension",
     ("", "cut = [x for x in (0, 1)][1]\n@@" + V + "return v if v == cut else None\n"),
     ("", "cut = [x for x in ctx.r][1]\n@@" + V + "return v if v == cut else None\n"), "unresolved"),
    ("unresolved_written_container",
     ("SYNTHETIC_CUTS = []\nSYNTHETIC_CUTS.append(1)\n",
      V + "return v if v == SYNTHETIC_CUTS[0] else None\n"),
     ("SYNTHETIC_CUTS = []\nSYNTHETIC_CUTS.append(1)\n",
      V + "return v, SYNTHETIC_CUTS\n"), "unresolved"),
]


@pytest.mark.parametrize("name,planted,control,cls", TRANSITIVE, ids=[a[0] for a in TRANSITIVE])
def test_m5_round3_a_decision_is_followed_transitively_or_refused(tmp_path, name, planted, control, cls):
    for (top, body), want in ((planted, [cls]), (control, [])):
        repo, dst = _copy(tmp_path / ("planted" if want else "control"))
        ind = _measure_indent(dst)
        _edit(dst, "review_measures", ind + MEASURE, ind + body.replace("@@", ind))
        if top:
            _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\n\n\n" + top + "\n\n")
        assert _classes(repo)[0] == want, (name, want, _classes(repo)[1])


RR_ANCHOR = "import review_measures as rm\n"
IMPORTED = [
    ("module_attribute", "SYNTHETIC_CUT = 1\n",
     "\n\ndef _synthetic(v):\n    return v > rm.SYNTHETIC_CUT\n",
     "\n\ndef _synthetic(v):\n    return v == rm.SYNTHETIC_CUT\n"),
    ("from_import", "SYNTHETIC_CUT = 1\n",
     "from review_measures import SYNTHETIC_CUT\n\n\ndef _synthetic(v):\n    return v > SYNTHETIC_CUT\n",
     "from review_measures import SYNTHETIC_CUT\n\n\ndef _synthetic(v):\n    return v == SYNTHETIC_CUT\n"),
    ("imported_constant_call", "def synthetic_cut():\n    return 1\n",
     "\n\ndef _synthetic(v):\n    return v > rm.synthetic_cut()\n",
     "\n\ndef _synthetic(v):\n    return v == rm.synthetic_cut()\n"),
]


@pytest.mark.parametrize("name,rm_top,planted,control", IMPORTED, ids=[a[0] for a in IMPORTED])
def test_m5_round3_an_imported_attribute_is_followed_into_its_module(tmp_path, name, rm_top, planted, control):
    for rr_add, want in ((planted, ["number"]), (control, [])):
        repo, dst = _copy(tmp_path / ("planted" if want else "control"))
        _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\n\n\n" + rm_top + "\n\n")
        _edit(dst, "review_rules", RR_ANCHOR, RR_ANCHOR + rr_add + "\n\n")
        assert _classes(repo)[0] == want, (name, want, _classes(repo)[1])


def test_m5_round3_the_reviewers_form_verbatim_inside_the_loader():
    """`base = 1; cut = base; value > cut`, as written in the round-3 report,
    at module level of a judged module: refused at the comparison."""
    src = "base = 1\ncut = base\n\n\ndef f(value):\n    return value > cut\n"
    s = g._Scan("review_rules", "synthetic", src)
    s.check_nodes(s.tree.body)
    assert [(line, c) for _l, line, c in s.findings] == [(6, "number")]
    clean = g._Scan("review_rules", "synthetic", src.replace("value > cut", "value == cut"))
    clean.check_nodes(clean.tree.body)
    assert clean.findings == []


# -- fix pass 3, M2: the bound-bytes proof's dynamic forms are exempt by NAME ------

def test_m2_the_dynamic_exemption_is_per_function_and_per_form(tmp_path):
    repo, dst = _copy(tmp_path)
    assert _classes(repo)[0] == []                                  # control: the real loader
    assert set(g.DYNAMIC_ALLOWED) == {("review_boot", "SourceOnly.exec_module"),
                                      ("review_boot", "SourceOnly.find_spec"),
                                      ("review_boot", "executed_elsewhere")}
    # an exempt form in ANOTHER method of the same class is refused
    repo3, dst3 = _copy(tmp_path / "three")
    _edit(dst3, "review_boot", "    def create_module(self, spec):\n",
          "    def create_module(self, spec):\n        compile(\"pass\", \"x\", \"exec\")\n")
    assert _classes(repo3)[0] == ["call"]
    # a form the exemption does not name for that function is refused
    _edit(dst, "review_boot", "    out = set()\n", "    out = set()\n    exec(\"pass\")\n")
    assert _classes(repo)[0] == ["call"]
    # an exempt form outside its function is refused
    repo2, dst2 = _copy(tmp_path / "two")
    _edit(dst2, "review_rules", "def rules_root() -> str:\n",
          "def rules_root() -> str:\n    getattr(os, \"sep\")\n")
    assert _classes(repo2)[0] == ["call"]


# -- fix pass 5, M5(i): a decision binding resolves uniquely or is refused --------------
# The round-5 input: owner candidates assigning a boolean drive `if o.flag`. A
# read that more than one binding reaches is AMBIGUOUS at a decision: the
# exit-3 refusal with every binding site listed, and its boolean member is
# judged too (never skipped). Each planted shape has a control whose bindings
# all read runtime input.
FLAG = ("class _SyntheticF:\n    def __init__(self, ctx):\n        self.flag = %s\n\n"
        "    def keep(self, v):\n        return v if self.flag else None\n\n\n"
        "def _synthetic_set(o, ctx):\n    o.flag = %s\n")
AMBIGUOUS = [
    ("boolean_owner_candidates", FLAG % ("True", "ctx.i"), FLAG % ("ctx.j", "ctx.i")),
    ("two_boolean_bindings", FLAG % ("True", "False"), FLAG % ("ctx.j", "ctx.i")),
    ("boolean_local_rebound", "def _synthetic_local(ctx, v):\n    flag = True\n    if ctx.i:\n"
     "        flag = ctx.j\n    return v if flag else None\n",
     "def _synthetic_local(ctx, v):\n    flag = ctx.k\n    if ctx.i:\n        flag = ctx.j\n"
     "    return v if flag else None\n"),
]


@pytest.mark.parametrize("name,planted,control", AMBIGUOUS, ids=[a[0] for a in AMBIGUOUS])
def test_m5_fix5_an_ambiguous_decision_binding_is_the_exit_3_refusal(tmp_path, name, planted, control, capsys):
    for top, want in ((planted, 3), (control, 0)):
        repo, dst = _copy(tmp_path / ("planted" if want else "control"))
        _edit(dst, "review_measures", "REGISTRY: dict = {}\n", "REGISTRY: dict = {}\n\n\n" + top + "\n\n")
        with open(os.path.join(dst, "review_measures.py"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        sites = ["review_measures:%d" % i for i, ln in enumerate(lines, 1)
                 if ln.strip().startswith(("self.flag = ", "o.flag = ", "flag = "))]
        assert len(sites) == 2, sites
        assert g.main(["tree", repo]) == want, (name, _classes(repo)[1])
        out = capsys.readouterr().out
        if want:
            amb = [ln for ln in out.splitlines() if " ambiguous (" in ln]
            assert amb and all(s in amb[0] for s in sites), out        # every binding site listed
            assert " bool" in out                                       # the boolean member is judged
            assert "no verdict" in out.splitlines()[-1]
        else:
            assert "ambiguous" not in out


def test_m5_fix5_decide_never_turns_several_bindings_into_a_plain_choice():
    """decide() over more than one binding with a closed one returns an
    AMBIGUOUS value (binding sites attached), never an unowned choice; one
    function's differing returns stay a choice of that function's own flow."""
    s = g._Scan("review_rules", "synthetic", "X = 1\n")
    v = s.decide([1, s._NONE], 0, 0, ["review_rules:1", "review_rules:2"])
    assert isinstance(v, g._Choice) and v.owners == ("review_rules:1", "review_rules:2")
    assert s.decide([1], 0, 0, ["review_rules:1"]) == 1                  # one binding: its value
    assert s.decide([s._NONE, s._NONE], 0, 0, ["a", "b"]) is s._NONE     # all runtime: runtime
    flow = g._Scan("review_rules", "synthetic", "def f(x):\n    if x:\n        return 0\n    return 2\n")
    rv = flow.return_value(flow.defs["f"])
    assert isinstance(rv, g._Choice) and rv.owners == ()
