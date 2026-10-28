"""The /health word that says this build carries the 2v2 and 1v2 mid-game
readmission (Stage 2 design V3, NX5).

`match_hold` is a marker whose only purpose is to be probed (#306), as
`ffa_hold_fences` is: 1 on this build, on both roles and in both health
arms, absent on the build before it, and read by nothing else. Both boxes
must answer it before any client sends the rjs1 capability (bug 266: a
stale standby answers 200 and silently drops what it does not know).

The last test runs the controls on a COPY of main.py in both directions:
the constant moved to 0 reddens the value test, the degraded arm without
the word reddens the arms test (the field has no default, so that answer
cannot be built), and a comment-only edit beside both keeps every test
green. The copy keeps the controls off the tree a running suite reads.
"""
import ast
import asyncio
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import main                                                      # noqa: E402
import schemas                                                   # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
BACKEND = MAIN_PY.parent.parent
THIS = pathlib.Path(__file__).resolve()

VALUE_TEST = "test_the_marker_reads_1_here"
ARMS_TEST = "test_both_health_arms_report_the_constant"


class _Up:
    async def execute(self, *a, **k):
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


def _run(coro):
    return asyncio.run(coro)


def _health():
    """(connected answer, degraded answer) as the response model renders them."""
    return (_run(main.health_check(db=_Up())).model_dump(),
            _run(main.health_check(db=_Down())).model_dump())


def _module_tree():
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def _top_level_function(tree, name):
    found = [n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(found) == 1, (name, len(found))
    return found[0]


def test_the_marker_reads_1_here():
    assert main._MATCH_HOLD == 1


def test_both_health_arms_report_the_constant(monkeypatch):
    """ok AND degraded, and what they report is the constant, not a 1 typed
    beside it: moved to 0, both answers move with it."""
    up, down = _health()
    assert (up["status"], down["status"]) == ("ok", "degraded")
    assert (up["match_hold"], down["match_hold"]) == (1, 1)
    monkeypatch.setattr(main, "_MATCH_HOLD", 0)
    up0, down0 = _health()
    assert (up0["match_hold"], down0["match_hold"]) == (0, 0)


def test_the_marker_is_declared_and_read_by_nothing_else():
    """Declared on the model with no default, passed in exactly the two arms
    and read nowhere else. The negative control is a name that is NOT
    declared and must be missing from the same dump."""
    field = schemas.HealthResponse.model_fields.get("match_hold")
    assert field is not None and field.annotation is int and field.is_required()
    up, _ = _health()
    assert "match_hold" in up
    assert "match_hold_not_a_field" not in schemas.HealthResponse.model_fields
    assert "match_hold_not_a_field" not in up

    tree = _module_tree()
    health = _top_level_function(tree, "health_check")
    tries = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for h in tries[0].handlers for n in ast.walk(h)}

    loads = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
             and n.id == "_MATCH_HOLD" and isinstance(n.ctx, ast.Load)]
    assert len(loads) == 2, len(loads)
    assert sum(id(n) in ok_arm for n in loads) == 1
    assert sum(id(n) in degraded_arm for n in loads) == 1

    keywords = [k for k in ast.walk(tree)
                if isinstance(k, ast.keyword) and k.arg == "match_hold"]
    assert len(keywords) == 2, len(keywords)
    assert sum(id(k) in ok_arm for k in keywords) == 1
    assert sum(id(k) in degraded_arm for k in keywords) == 1
    assert all(ast.unparse(k.value) == "_MATCH_HOLD" for k in keywords)


# -- the controls, on a copy of the file ----------------------------------------

_DRIVER = (
    "import sys\n"
    "api = sys.argv[1]\n"
    "sys.path.insert(0, api)\n"
    "import main\n"
    "print('MARKER=%d' % main._MATCH_HOLD, flush=True)\n"
    "import pytest\n"
    "sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '-rA'] + sys.argv[2:]))\n"
)
_OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR) \S*::(\w+)", re.MULTILINE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_tree(dst: pathlib.Path) -> pathlib.Path:
    """The api modules, the migrations the suite's autouse fixture reads,
    conftest.py with its data file, and this test file."""
    api = dst / "backend" / "api"
    sql = dst / "backend" / "sql"
    tests = dst / "backend" / "tests"
    for d in (api, sql, tests):
        d.mkdir(parents=True)
    for p in (BACKEND / "api").glob("*.py"):
        shutil.copyfile(p, api / p.name)
    for p in (BACKEND / "sql").glob("*.sql"):
        shutil.copyfile(p, sql / p.name)
    for name in ("conftest.py", "pc_themes_data.py"):
        shutil.copyfile(BACKEND / "tests" / name, tests / name)
    shutil.copyfile(THIS, tests / THIS.name)
    return api / "main.py"


def _controls(nl):
    """(name, [(old, new, count)], marker wanted, {test: outcome wanted})."""
    return [
        ("constant-moved-to-0",
         [("_MATCH_HOLD = 1" + nl, "_MATCH_HOLD = 0" + nl, 1)],
         0, {VALUE_TEST: "FAILED", ARMS_TEST: "FAILED"}),
        ("degraded-arm-loses-the-word",
         [("                              ffa_readmit=_FFA_READMIT," + nl
           + "                              match_hold=_MATCH_HOLD," + nl,
           "                              ffa_readmit=_FFA_READMIT," + nl, 2)],
         1, {VALUE_TEST: "PASSED", ARMS_TEST: "FAILED"}),
        ("comment-beside-both",
         [("_MATCH_HOLD = 1" + nl,
           "# match_hold: a comment beside the constant changes none of it" + nl
           + "_MATCH_HOLD = 1" + nl, 1)],
         1, {VALUE_TEST: "PASSED", ARMS_TEST: "PASSED"}),
    ]


def _apply(text, edits, name):
    out = text
    for old, new, want in edits:
        assert text.count(old) == want, (name, old, text.count(old))
        if want == 2:
            # the degraded arm is the second occurrence: keep the first
            first = out.index(old) + len(old)
            out = out[:first] + out[first:].replace(old, new, 1)
        else:
            out = out.replace(old, new, 1)
    return out


def test_the_controls_run_on_a_copy_in_both_directions(tmp_path):
    """RED: the constant at 0 reads 0 and reddens both tests that read it;
    the degraded arm without the word reddens the arms test only. GREEN: a
    comment-only edit reads 1 and reddens nothing, which also proves the
    copied tree runs the two tests at all. Every mutation lands on the COPY,
    is restored byte for byte (sha256), and the worktree's main.py is the
    same bytes at the end."""
    original = MAIN_PY.read_bytes()
    before = _sha256(original)
    copy = _copy_tree(tmp_path)
    assert _sha256(copy.read_bytes()) == before
    text = original.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    driver = tmp_path / "marker_driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if not k.endswith("_PG_DSN") and k not in ("PYTEST_ADDOPTS", "BUG392_TESTS_REQUIRED")}
    env.update(FFA_TEST_PG_OPTOUT="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    tests = ["tests/%s::%s" % (THIS.name, t) for t in (VALUE_TEST, ARMS_TEST)]

    for name, edits, want_marker, want_outcomes in _controls(nl):
        mutated_bytes = _apply(text, edits, name).encode("utf-8")
        assert _sha256(mutated_bytes) != before, name
        copy.write_bytes(mutated_bytes)
        try:
            proc = subprocess.run(
                [sys.executable, str(driver), str(copy.parent), *tests],
                cwd=str(tmp_path / "backend"), env=env, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=900)
        finally:
            copy.write_bytes(original)
        restored = _sha256(copy.read_bytes())
        assert restored == before, (name, restored, before)

        out = proc.stdout + proc.stderr
        markers = re.findall(r"^MARKER=(\d+)$", out, re.MULTILINE)
        assert markers == [str(want_marker)], (name, markers, out[-3000:])
        outcomes = {test: result for result, test in _OUTCOME.findall(out)}
        got = {t: outcomes.get(t) for t in want_outcomes}
        assert got == want_outcomes, (name, got, out[-3000:])
        assert proc.returncode == (1 if "FAILED" in want_outcomes.values() else 0), \
            (name, proc.returncode, out[-3000:])
        print("control %-28s marker %d  %s  rc %d  mutated sha256 %s  restored == original"
              % (name, want_marker, got, proc.returncode, _sha256(mutated_bytes)[:16]))

    assert _sha256(MAIN_PY.read_bytes()) == before
    print("worktree main.py sha256 %s, unchanged by the controls" % before[:16])
