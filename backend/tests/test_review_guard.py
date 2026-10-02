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

MODULES = ("review_measures", "review_rules", "review_module", "review_module_runner", "seat_evidence",
           "combat_measures", "combat_evidence")


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
        assert isinstance(line, int) and c in ("number", "text", "call", "setting", "env", "pinned")


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
    _edit(dst, "review_measures", "import textwrap\n", "import textwrap\n\nimport synthetic_values\n")
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
