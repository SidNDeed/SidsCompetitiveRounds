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

MODULES = ("review_measures", "review_rules", "seat_evidence")


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
    findings, _n = g.tree_mode(repo)
    return sorted({cls for _l, _line, cls in findings}), findings


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
        assert isinstance(line, int) and c in ("number", "text", "call", "setting", "env", "pinned",
                                                 "select", "bool")


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


def test_m5_round2_a_rebound_name_is_not_a_constant(tmp_path):
    """Control for the binding rule: a name bound twice is a variable."""
    repo, dst = _copy(tmp_path)
    ind = _measure_indent(dst)
    _edit(dst, "review_measures", ind + MEASURE,
          ind + "cut = 1\n" + ind + "cut = ctx.i\n" + ind + V.replace("@@", ind)
          + "return v if v > cut else None\n")
    assert _classes(repo)[0] == []
