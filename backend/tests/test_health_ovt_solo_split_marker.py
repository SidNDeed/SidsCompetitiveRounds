"""The /health word that says this build refuses a mid-series solo-seat change.

The bug 391 batch adds no route and no key to any GET answer both builds
serve: its refusal rides only the 1v2 report answer, which needs a signed
report. So `ovt_solo_split` is the release train's build discriminator for the
batch -- absent on the build before it, 1 on this one, on both roles -- and the
train reads any other value as the old build.

The value is DERIVED from two string constants the batch introduced (#342): 1
when submit_ovt_match's compiled constants carry the refusal's HTTPException
detail AND the trailing literal segment of its log line, 0 when either one is
edited or gone. That makes it a statement about the code that ships rather
than a stamp beside it, and the last test here runs the statement on a COPY of
main.py in both directions: an edited detail reads 0 and reddens both round-4
refusal tests that assert that detail, an edited log segment reads 0, and a
comment-only edit beside both keeps 1 and reddens nothing. The copy is what
keeps the controls off the tree a running suite is reading (conftest.py's
tree-movement check says why that matters).
"""
import ast
import hashlib
import inspect
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

from test_player_cards_server import _run                        # noqa: E402
import main                                                      # noqa: E402
import schemas                                                   # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
BACKEND = MAIN_PY.parent.parent

# The two literals the marker reads, exactly as the binding names them.
DETAIL = "Reported solo seat does not match the series"
SEGMENT = " recorded game(s); a series keeps one solo-versus-duo split for every game"

# The round-4 tests that assert the refusal's detail, both live (they need
# BUG391_TEST_PG_DSN): the report arm and the settled arm.
SUITE = "tests/test_ovt_abandoned_horizon.py"
REFUSAL_TESTS = {
    "report-arm": "test_a_report_moving_a_player_into_the_solo_seat_mid_series_is_refused",
    "settled-arm": "test_a_settled_series_refuses_a_report_moving_the_solo_seat_too",
}
LIVE_DSN = "BUG391_TEST_PG_DSN"


class _Up:
    async def execute(self, *a, **k):
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


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


def _binding(tree):
    assigns = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "_OVT_SOLO_SPLIT"
                       for t in n.targets)]
    assert len(assigns) == 1, len(assigns)
    return assigns[0]


def test_the_marker_is_derived_from_the_two_literals_and_reads_1_here():
    """Derived, bound once, and 1 at this tip.

    A literal `_OVT_SOLO_SPLIT = 1` would read 1 on a build that had lost the
    refusal, which is the one deploy this word exists to tell apart -- a check
    that cannot fail (#342/#441). So the binding has to be a CALL of the
    derivation over the endpoint's own compiled constants, with no number
    anywhere in it, and nothing may rebind the name afterwards."""
    tree = _module_tree()
    stores = [n for n in ast.walk(tree)
              if isinstance(n, ast.Name) and n.id == "_OVT_SOLO_SPLIT"
              and isinstance(n.ctx, ast.Store)]
    assert len(stores) == 1, len(stores)
    value = _binding(tree).value
    assert isinstance(value, ast.Call), ast.dump(value)
    assert not [n for n in ast.walk(value)
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, bool))]
    assert ast.unparse(value.func) == "_ovt_solo_split_marker"
    assert [ast.unparse(a) for a in value.args] == [
        "_ovt_const_literal(submit_ovt_match.__code__, %r)" % DETAIL,
        "_ovt_const_literal(submit_ovt_match.__code__, %r)" % SEGMENT]
    assert not value.keywords
    # What it reads is what the endpoint runs: the detail the refusal raises,
    # and the one compiled segment of the refusal's log line that carries the
    # series rule -- the f-string's literal text after its last expression.
    consts = main.submit_ovt_match.__code__.co_consts
    assert DETAIL in consts and SEGMENT in consts
    source = inspect.getsource(main.submit_ovt_match)
    assert source.count('raise HTTPException(403, "%s")' % DETAIL) == 1
    ruled = [c for c in consts if isinstance(c, str) and "solo-versus-duo split" in c]
    assert ruled == [SEGMENT], ruled
    assert main._OVT_SOLO_SPLIT == 1
    code = main.submit_ovt_match.__code__
    assert main._ovt_solo_split_marker(main._ovt_const_literal(code, DETAIL),
                                       main._ovt_const_literal(code, SEGMENT)) == 1


def test_the_derivation_reads_each_literal_and_nothing_beside_it():
    """Either literal absent reads 0, both absent reads 0, an unrelated pair
    reads 0, and prose never reads anything.

    The in-process half of the controls: the derivation over code objects
    that lack one literal or both. The subprocess half below makes the same
    edits to a copy of the FILE, where the refusal's own tests can see them
    too."""
    marker = main._ovt_solo_split_marker
    literal = main._ovt_const_literal
    code = main.submit_ovt_match.__code__
    assert marker(literal(code, DETAIL), literal(code, SEGMENT)) == 1

    def code_of(source):
        namespace = {}
        exec(compile(source, "<marker-probe>", "exec"), namespace)
        return namespace["f"].__code__

    both = code_of(
        "def f(solo, games):\n"
        "    print(f'series {solo} has {games} recorded game(s); a '\n"
        "          f'series keeps one solo-versus-duo split for every game')\n"
        "    raise ValueError('Reported solo seat does not match the series')\n")
    # The probe reproduces the endpoint's shape: the f-string's trailing text
    # compiles to exactly the segment the binding names.
    assert marker(literal(both, DETAIL), literal(both, SEGMENT)) == 1

    no_detail = code_of(
        "def f(solo, games):\n"
        "    print(f'series {solo} has {games} recorded game(s); a '\n"
        "          f'series keeps one solo-versus-duo split for every game')\n"
        "    raise ValueError('reported solo seat does not match the series')\n")
    assert literal(no_detail, DETAIL) == "" and literal(no_detail, SEGMENT) == SEGMENT
    assert marker(literal(no_detail, DETAIL), literal(no_detail, SEGMENT)) == 0

    no_segment = code_of(
        "def f(solo, games):\n"
        "    print(f'series {solo} has {games} recorded game(s), a '\n"
        "          f'series keeps one solo-versus-duo split for every game')\n"
        "    raise ValueError('Reported solo seat does not match the series')\n")
    assert literal(no_segment, SEGMENT) == "" and literal(no_segment, DETAIL) == DETAIL
    assert marker(literal(no_segment, DETAIL), literal(no_segment, SEGMENT)) == 0

    neither = code_of("def f():\n    return 'a report was recorded'\n")
    assert marker(literal(neither, DETAIL), literal(neither, SEGMENT)) == 0

    # An unrelated pair: the two literals looked up in another endpoint's
    # constants, and two unrelated texts looked up in this endpoint's.
    other = main.submit_ffa_match.__code__
    assert marker(literal(other, DETAIL), literal(other, SEGMENT)) == 0
    assert marker(literal(code, "Series already resolved."),
                  literal(code, "no such constant in this endpoint")) == 0

    # A comment carrying both literals whole, beside strings that differ by
    # one character: the compiled constants are what is read, so it reads 0.
    commented = code_of(
        "def f(solo, games):\n"
        "    # Reported solo seat does not match the series\n"
        "    #  recorded game(s); a series keeps one solo-versus-duo split for every game\n"
        "    print(f'series {solo} has {games} recorded game(s), a '\n"
        "          f'series keeps one solo-versus-duo split for every game')\n"
        "    raise ValueError('Reported solo seat does not match the series.')\n")
    assert marker(literal(commented, DETAIL), literal(commented, SEGMENT)) == 0
    assert marker("", "") == 0


def test_both_health_arms_report_the_constant(monkeypatch):
    """ok AND degraded, and what they report is the constant, not a 1 typed
    beside it: moved to 0, both answers move with it."""
    up, down = _health()
    assert (up["status"], down["status"]) == ("ok", "degraded")
    assert (up["ovt_solo_split"], down["ovt_solo_split"]) == (1, 1)
    monkeypatch.setattr(main, "_OVT_SOLO_SPLIT", 0)
    up0, down0 = _health()
    assert (up0["ovt_solo_split"], down0["ovt_solo_split"]) == (0, 0)


def test_the_marker_is_declared_and_read_by_nothing_else():
    """Declared on the model, passed in exactly the two arms, read nowhere else.

    `HealthResponse` drops what it does not declare, so the handler passing the
    word is not by itself enough; the negative control is a name that is NOT
    declared and must be missing from the same dump. The word exists only to
    be probed (#306): the constant is read by the two health arms and nothing
    else, and the helpers that derive it are called by that derivation alone --
    the marker helper once, the literal helper once per literal."""
    field = schemas.HealthResponse.model_fields.get("ovt_solo_split")
    assert field is not None and field.annotation is int and field.is_required()
    up, _ = _health()
    assert "ovt_solo_split" in up
    assert "ovt_solo_split_not_a_field" not in schemas.HealthResponse.model_fields
    assert "ovt_solo_split_not_a_field" not in up

    tree = _module_tree()
    health = _top_level_function(tree, "health_check")
    tries = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for h in tries[0].handlers for n in ast.walk(h)}

    loads = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
             and n.id == "_OVT_SOLO_SPLIT" and isinstance(n.ctx, ast.Load)]
    assert len(loads) == 2, len(loads)
    assert sum(id(n) in ok_arm for n in loads) == 1
    assert sum(id(n) in degraded_arm for n in loads) == 1

    keywords = [k for k in ast.walk(tree)
                if isinstance(k, ast.keyword) and k.arg == "ovt_solo_split"]
    assert len(keywords) == 2, len(keywords)
    assert sum(id(k) in ok_arm for k in keywords) == 1
    assert sum(id(k) in degraded_arm for k in keywords) == 1
    assert all(ast.unparse(k.value) == "_OVT_SOLO_SPLIT" for k in keywords)

    inside = {id(n) for n in ast.walk(_binding(tree).value)}
    for helper, times in (("_ovt_solo_split_marker", 1), ("_ovt_const_literal", 2)):
        calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Name) and c.func.id == helper]
        assert len(calls) == times, (helper, len(calls))
        assert all(id(c) in inside for c in calls), helper


# -- the controls, on a copy of the file -------------------------------------

# Run in a fresh interpreter over the copied tree: import main from the copy,
# print the marker it derived, then run the two refusal tests from the copy.
_DRIVER = (
    "import sys\n"
    "api = sys.argv[1]\n"
    "sys.path.insert(0, api)\n"
    "import main\n"
    "print('MARKER=%d' % main._OVT_SOLO_SPLIT, flush=True)\n"
    "import pytest\n"
    "sys.exit(pytest.main(['-v', '-p', 'no:cacheprovider'] + sys.argv[2:]))\n"
)
_OUTCOME = re.compile(r"^tests/test_ovt_abandoned_horizon\.py::(\w+) (PASSED|FAILED|ERROR|SKIPPED)",
                      re.MULTILINE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_tree(dst: pathlib.Path) -> pathlib.Path:
    """The smallest tree the refusal tests run from: the api modules, the
    migrations the suite reads, and the test-side files they import."""
    api = dst / "backend" / "api"
    sql = dst / "backend" / "sql"
    tests = dst / "backend" / "tests"
    for d in (api, sql, tests):
        d.mkdir(parents=True)
    for p in (BACKEND / "api").glob("*.py"):
        shutil.copyfile(p, api / p.name)
    for p in (BACKEND / "sql").glob("*.sql"):
        shutil.copyfile(p, sql / p.name)
    for name in ("conftest.py", "pc_themes_data.py", "test_ovt_abandoned_horizon.py"):
        shutil.copyfile(BACKEND / "tests" / name, tests / name)
    return api / "main.py"


def _controls(nl):
    """(name, [(old, new)], marker wanted, {refusal test: outcome wanted}).

    Each (old, new) is applied once, and `old` must occur exactly once in the
    file, so a control can neither miss its target nor hit a second one --
    which is also why each anchor names the refusal's own line, never the
    binding's copy of the literal."""
    raise_line = 'raise HTTPException(403, "%s")' % DETAIL
    log_head = 'print(f"[OVT-REPORT] series {series_uuid}: report refused, nothing written: "'
    return [
        ("detail-string-edited",
         [(raise_line, raise_line.replace('"Reported', '"reported', 1))],
         0, {"report-arm": "FAILED", "settled-arm": "FAILED"}),
        ("log-segment-edited",
         [("recorded game(s); a \"" + nl, "recorded game(s), a \"" + nl)],
         0, {"report-arm": "PASSED", "settled-arm": "PASSED"}),
        ("comment-beside-both",
         [("            " + log_head,
           "            # the refusal's words: a comment beside them changes none of it" + nl
           + "            " + log_head),
          ("            " + raise_line,
           "            # the detail the client is shown: a comment changes none of it" + nl
           + "            " + raise_line)],
         1, {"report-arm": "PASSED", "settled-arm": "PASSED"}),
    ]


def test_the_controls_run_on_a_copy_in_both_directions(tmp_path):
    """RED: the detail with one character changed reads 0 AND reddens both
    refusal tests, which assert that exact detail; the log segment with one
    character changed reads 0 and reddens neither (no test reads that
    segment -- it is the marker's own second witness). GREEN: a comment-only
    edit beside both reads 1 and reddens neither, which is also what proves
    the copied tree runs the two tests at all. Every mutation lands on the
    COPY, is restored byte for byte (sha256), and the worktree's main.py is
    the same bytes at the end.

    The refusal tests are live. With BUG391_TEST_PG_DSN unset they SKIP in
    the copy, the marker half is still asserted, and this test then SKIPS
    rather than passing: a skipped live half is an unrun test, not an
    acceptance (the suite's own rule)."""
    original = MAIN_PY.read_bytes()
    before = _sha256(original)
    copy = _copy_tree(tmp_path)
    assert _sha256(copy.read_bytes()) == before
    text = original.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    driver = tmp_path / "marker_driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    live = bool(os.environ.get(LIVE_DSN))
    env = {k: v for k, v in os.environ.items()
           if not (k.endswith("_PG_DSN") and k != LIVE_DSN)
           and k not in ("PYTEST_ADDOPTS", "BUG392_TESTS_REQUIRED")}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    tests = ["%s::%s" % (SUITE, REFUSAL_TESTS[k]) for k in ("report-arm", "settled-arm")]

    for name, edits, want_marker, want_live in _controls(nl):
        mutated = text
        for old, new in edits:
            assert text.count(old) == 1, (name, old, text.count(old))
            mutated = mutated.replace(old, new, 1)
        mutated_bytes = mutated.encode("utf-8")
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
        outcomes = {test: result for test, result in _OUTCOME.findall(out)}
        got = {k: outcomes.get(REFUSAL_TESTS[k]) for k in REFUSAL_TESTS}
        want = want_live if live else {k: "SKIPPED" for k in REFUSAL_TESTS}
        assert got == want, (name, got, out[-3000:])
        assert proc.returncode == (1 if "FAILED" in want.values() else 0), \
            (name, proc.returncode, out[-3000:])
        print("control %-22s marker %d  report-arm %s  settled-arm %s  rc %d  "
              "mutated sha256 %s  restored sha256 %s == original"
              % (name, want_marker, got["report-arm"], got["settled-arm"],
                 proc.returncode, _sha256(mutated_bytes)[:16], restored[:16]))

    assert _sha256(MAIN_PY.read_bytes()) == before
    print("worktree main.py sha256 %s, unchanged by the controls" % before[:16])
    if not live:
        pytest.skip("marker half asserted on the copy; the refusal tests' half "
                    "needs %s (live PostgreSQL), so the controls are not "
                    "accepted by this run" % LIVE_DSN)
