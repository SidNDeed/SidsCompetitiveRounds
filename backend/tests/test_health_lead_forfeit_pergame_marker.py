"""The /health word that says this build settles a 2v2 lead-forfeit from the
server's own per-game record.

The lead-forfeit hotfix adds no route and no key to any GET answer both builds
serve: the per-game record (team_series_games, migration 348) is raised by the
signed team live-points POST and read by the signed DC report. So
`lead_forfeit_pergame` is the release train's build discriminator for the
batch -- absent on the build before it, 1 on this one, on both roles -- and the
train reads any other value as the old build.

The value is DERIVED from the two wirings the batch introduced (#342): 1 when
update_team_live_points' compiled code loads _record_team_game_points AND
team_series_report_dc's loads _team_game_crossed_two, 0 when either endpoint
stops loading its helper. That makes it a statement about the code that ships
rather than a stamp beside it, and the last test here runs the statement on a
COPY of main.py in both directions: the DC report put back on its own point
snapshot reads 0 and reddens the settlement tests that pin the record, the
live-points POST without its writer reads 0 and reddens the tests that need a
recorded crossing, and a comment-only edit beside both calls keeps 1 and
reddens nothing. The copy is what keeps the controls off the tree a running
suite is reading (conftest.py's tree-movement check says why that matters).
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

# The two names the marker reads, exactly as the binding names them: the
# writer the team live-points POST calls, and the reader the DC report calls.
WRITER = "_record_team_game_points"
READER = "_team_game_crossed_two"

# The live tests whose outcomes the controls predict (they need
# TEAM_DC_TEST_PG_DSN): one abandoned game settled from both report orders,
# once with the game crossed and once without; the DC report before migration
# 348 exists; and a record raised and re-read without the DC report.
SUITE = "tests/test_team_series_report_dc.py"
LIVE_TESTS = {
    "order-played":
        "test_the_settlement_is_the_same_whichever_survivor_reports_first[game-crossed-two]",
    "order-unplayed":
        "test_the_settlement_is_the_same_whichever_survivor_reports_first[game-did-not]",
    "no-table": "test_without_the_table_nothing_fails_and_nothing_auto_completes",
    "below-two": "test_a_post_below_two_never_clears_a_crossing",
}
LIVE_DSN = "TEAM_DC_TEST_PG_DSN"
LIVE_REQUIRED = "TEAM_DC_TESTS_REQUIRED"


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
               and any(isinstance(t, ast.Name) and t.id == "_LEAD_FORFEIT_PERGAME"
                       for t in n.targets)]
    assert len(assigns) == 1, len(assigns)
    return assigns[0]


def test_the_marker_is_derived_from_the_two_wirings_and_reads_1_here():
    """Derived, bound once, and 1 at this tip.

    A literal `_LEAD_FORFEIT_PERGAME = 1` would read 1 on a build that had lost
    the per-game record, which is the one deploy this word exists to tell
    apart -- a check that cannot fail (#342/#441). So the binding has to be a
    CALL of the derivation over the two endpoints' own compiled code, with no
    number anywhere in it, and nothing may rebind the name afterwards."""
    tree = _module_tree()
    stores = [n for n in ast.walk(tree)
              if isinstance(n, ast.Name) and n.id == "_LEAD_FORFEIT_PERGAME"
              and isinstance(n.ctx, ast.Store)]
    assert len(stores) == 1, len(stores)
    value = _binding(tree).value
    assert isinstance(value, ast.Call), ast.dump(value)
    assert not [n for n in ast.walk(value)
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, bool))]
    assert ast.unparse(value.func) == "_lead_forfeit_pergame_marker"
    assert [ast.unparse(a) for a in value.args] == [
        "_lead_forfeit_loaded_name(update_team_live_points.__code__, %r)" % WRITER,
        "_lead_forfeit_loaded_name(team_series_report_dc.__code__, %r)" % READER]
    assert not value.keywords
    # What it reads is what the endpoints run: each awaits its own helper
    # exactly once, and each helper is the one that touches the table.
    live = main.update_team_live_points
    dc = main.team_series_report_dc
    assert inspect.getsource(live).count("await %s(" % WRITER) == 1
    assert inspect.getsource(dc).count("await %s(" % READER) == 1
    assert WRITER in live.__code__.co_names and READER in dc.__code__.co_names
    assert "INSERT INTO team_series_games" in main._TEAM_GAME_POINTS_UPSERT_SQL
    assert "FROM team_series_games" in main._TEAM_GAME_CROSSED_SQL
    assert "_TEAM_GAME_POINTS_UPSERT_SQL" in main._record_team_game_points.__code__.co_names
    assert "_TEAM_GAME_CROSSED_SQL" in main._team_game_crossed_two.__code__.co_names
    assert main._LEAD_FORFEIT_PERGAME == 1
    assert main._lead_forfeit_pergame_marker(
        main._lead_forfeit_loaded_name(live.__code__, WRITER),
        main._lead_forfeit_loaded_name(dc.__code__, READER)) == 1


def test_the_derivation_reads_each_wiring_and_nothing_beside_it():
    """Either name not loaded reads 0, neither reads 0, the names swapped
    between the two endpoints read 0, and a comment or a string never reads.

    The in-process half of the controls: the derivation over code objects
    that lack one wiring or both. The subprocess half below makes the same
    edits to a copy of the FILE, where the settlement's own tests can see them
    too."""
    marker = main._lead_forfeit_pergame_marker
    loaded = main._lead_forfeit_loaded_name
    live = main.update_team_live_points.__code__
    dc = main.team_series_report_dc.__code__
    assert marker(loaded(live, WRITER), loaded(dc, READER)) == 1

    def code_of(source):
        namespace = {}
        exec(compile(source, "<marker-probe>", "exec"), namespace)
        return namespace["f"].__code__

    writer = code_of(
        "async def f(db, sid, t1_points, t2_points):\n"
        "    await _record_team_game_points(db, sid, t1_points, t2_points)\n"
        "    await db.commit()\n")
    reader = code_of(
        "async def f(db, sid, s, total_points, wins):\n"
        "    if ((wins or 0) >= 1\n"
        "            and await _team_game_crossed_two(db, sid, s, total_points)):\n"
        "        return 'lead-forfeit'\n"
        "    return 'dc_incomplete'\n")
    # The probes reproduce the endpoints' shapes and read 1 together.
    assert marker(loaded(writer, WRITER), loaded(reader, READER)) == 1

    # The DC report put back on its own snapshot: no reader loaded.
    pre_fix = code_of(
        "async def f(db, sid, s, total_points, wins):\n"
        "    if (wins or 0) >= 1 and total_points >= 2:\n"
        "        return 'lead-forfeit'\n"
        "    return 'dc_incomplete'\n")
    assert loaded(pre_fix, READER) == ""
    assert marker(loaded(writer, WRITER), loaded(pre_fix, READER)) == 0

    # The live-points POST without its writer.
    no_writer = code_of(
        "async def f(db, sid, t1_points, t2_points):\n"
        "    await db.commit()\n")
    assert loaded(no_writer, WRITER) == ""
    assert marker(loaded(no_writer, WRITER), loaded(reader, READER)) == 0
    assert marker(loaded(no_writer, WRITER), loaded(pre_fix, READER)) == 0

    # The names swapped: each real endpoint loads only its own helper.
    assert loaded(live, READER) == "" and loaded(dc, WRITER) == ""
    assert marker(loaded(dc, WRITER), loaded(live, READER)) == 0

    # An unrelated endpoint: the FFA live-points POST loads neither.
    other = main.update_ffa_live_points.__code__
    assert marker(loaded(other, WRITER), loaded(other, READER)) == 0

    # Both names whole in comments AND quoted in a string, beside calls that
    # are not theirs: comments are not compiled and a string is a constant,
    # not a loaded name, so it reads 0.
    quoted = code_of(
        "async def f(db, sid, s, total_points):\n"
        "    # await _record_team_game_points(db, sid, t1_points, t2_points)\n"
        "    # and await _team_game_crossed_two(db, sid_uuid, s, total_points)\n"
        "    print('_record_team_game_points', '_team_game_crossed_two')\n"
        "    await db.commit()\n")
    assert WRITER in quoted.co_consts and READER in quoted.co_consts
    assert loaded(quoted, WRITER) == "" and loaded(quoted, READER) == ""
    assert marker(loaded(quoted, WRITER), loaded(quoted, READER)) == 0
    assert marker("", "") == 0


def test_both_health_arms_report_the_constant(monkeypatch):
    """ok AND degraded, and what they report is the constant, not a 1 typed
    beside it: moved to 0, both answers move with it."""
    up, down = _health()
    assert (up["status"], down["status"]) == ("ok", "degraded")
    assert (up["lead_forfeit_pergame"], down["lead_forfeit_pergame"]) == (1, 1)
    monkeypatch.setattr(main, "_LEAD_FORFEIT_PERGAME", 0)
    up0, down0 = _health()
    assert (up0["lead_forfeit_pergame"], down0["lead_forfeit_pergame"]) == (0, 0)


def test_the_marker_is_declared_and_read_by_nothing_else():
    """Declared on the model, passed in exactly the two arms, read nowhere else.

    `HealthResponse` drops what it does not declare, so the handler passing the
    word is not by itself enough; the negative control is a name that is NOT
    declared and must be missing from the same dump. The word exists only to
    be probed (#306): the constant is read by the two health arms and nothing
    else, and the helpers that derive it are called by that derivation alone --
    the marker helper once, the name helper once per wiring."""
    field = schemas.HealthResponse.model_fields.get("lead_forfeit_pergame")
    assert field is not None and field.annotation is int and field.is_required()
    up, _ = _health()
    assert "lead_forfeit_pergame" in up
    assert "lead_forfeit_pergame_not_a_field" not in schemas.HealthResponse.model_fields
    assert "lead_forfeit_pergame_not_a_field" not in up

    tree = _module_tree()
    health = _top_level_function(tree, "health_check")
    tries = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for h in tries[0].handlers for n in ast.walk(h)}

    loads = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
             and n.id == "_LEAD_FORFEIT_PERGAME" and isinstance(n.ctx, ast.Load)]
    assert len(loads) == 2, len(loads)
    assert sum(id(n) in ok_arm for n in loads) == 1
    assert sum(id(n) in degraded_arm for n in loads) == 1

    keywords = [k for k in ast.walk(tree)
                if isinstance(k, ast.keyword) and k.arg == "lead_forfeit_pergame"]
    assert len(keywords) == 2, len(keywords)
    assert sum(id(k) in ok_arm for k in keywords) == 1
    assert sum(id(k) in degraded_arm for k in keywords) == 1
    assert all(ast.unparse(k.value) == "_LEAD_FORFEIT_PERGAME" for k in keywords)

    inside = {id(n) for n in ast.walk(_binding(tree).value)}
    for helper, times in (("_lead_forfeit_pergame_marker", 1),
                          ("_lead_forfeit_loaded_name", 2)):
        calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Name) and c.func.id == helper]
        assert len(calls) == times, (helper, len(calls))
        assert all(id(c) in inside for c in calls), helper


# -- the controls, on a copy of the file -------------------------------------

# Run in a fresh interpreter over the copied tree: import main from the copy,
# print the marker it derived, then run the four live tests from the copy.
_DRIVER = (
    "import sys\n"
    "api = sys.argv[1]\n"
    "sys.path.insert(0, api)\n"
    "import main\n"
    "print('MARKER=%d' % main._LEAD_FORFEIT_PERGAME, flush=True)\n"
    "import pytest\n"
    "sys.exit(pytest.main(['-v', '-p', 'no:cacheprovider'] + sys.argv[2:]))\n"
)
_OUTCOME = re.compile(
    r"^(?:\S*[\\/])?tests[\\/]test_team_series_report_dc\.py::(\S+) "
    r"(PASSED|FAILED|ERROR|SKIPPED)", re.MULTILINE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_tree(dst: pathlib.Path) -> pathlib.Path:
    """The smallest tree the live tests run from: the api modules, the
    migrations the suite reads (348 among them), and the test-side files."""
    api = dst / "backend" / "api"
    sql = dst / "backend" / "sql"
    tests = dst / "backend" / "tests"
    for d in (api, sql, tests):
        d.mkdir(parents=True)
    for p in (BACKEND / "api").glob("*.py"):
        shutil.copyfile(p, api / p.name)
    for p in (BACKEND / "sql").glob("*.sql"):
        shutil.copyfile(p, sql / p.name)
    for name in ("conftest.py", "pc_themes_data.py", "test_team_series_report_dc.py"):
        shutil.copyfile(BACKEND / "tests" / name, tests / name)
    return api / "main.py"


def _controls(nl):
    """(name, [(old, new)], marker wanted, {live test: outcome wanted}).

    Each (old, new) is applied once, and `old` must occur exactly once in the
    file, so a control can neither miss its target nor hit a second one --
    which is also why each anchor names an endpoint's own call line, never the
    binding's copy of the name."""
    writer_call = "    await %s(db, sid, t1_points, t2_points)" % WRITER
    reader_line = "            and await %s(db, sid_uuid, s, total_points)):" % READER
    reader_cond = "    if ((other_team_existing_wins or 0) >= 1" + nl + reader_line
    pre_fix_cond = "    if (other_team_existing_wins or 0) >= 1 and total_points >= 2:"
    return [
        # The pre-fix condition: the report's snapshot decides. The two
        # orders then settle differently whether or not the game crossed, and
        # a DC report with no table completes the series on a 2-point snapshot.
        # The writer is untouched, so the record test stays green.
        ("reader-on-the-snapshot",
         [(reader_cond, pre_fix_cond)],
         0, {"order-played": "FAILED", "order-unplayed": "FAILED",
             "no-table": "FAILED", "below-two": "PASSED"}),
        # The POST no longer raises the record: a crossed game reads as not
        # played in both orders, and the record test finds no row. The two
        # tests whose answer is dc_incomplete either way stay green.
        ("writer-not-called",
         [(writer_call + nl, "")],
         0, {"order-played": "FAILED", "order-unplayed": "PASSED",
             "no-table": "PASSED", "below-two": "FAILED"}),
        ("comment-beside-both",
         [(writer_call,
           "    # the writer's call: a comment beside it changes none of it" + nl
           + writer_call),
          (reader_line,
           "            # the reader's call: a comment beside it changes none of it" + nl
           + reader_line)],
         1, {k: "PASSED" for k in LIVE_TESTS}),
    ]


def test_the_controls_run_on_a_copy_in_both_directions(tmp_path):
    """RED: the DC report put back on its own snapshot reads 0 AND reddens
    both report-order tests and the no-table test, while the record test
    stays green; the live-points POST without its writer reads 0 AND reddens
    the crossed-game order test and the record test, while the two tests whose
    answer is dc_incomplete either way stay green. GREEN: a comment-only edit
    beside both calls reads 1 and reddens nothing, which is also what proves
    the copied tree runs the four tests at all. Every mutation lands on the
    COPY, is restored byte for byte (sha256), and the worktree's main.py is
    the same bytes at the end.

    The four tests are live. With TEAM_DC_TEST_PG_DSN unset they SKIP in the
    copy, the marker half is still asserted, and this test then SKIPS rather
    than passing: a skipped live half is an unrun test, not an acceptance
    (the suite's own rule)."""
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
           and k not in ("PYTEST_ADDOPTS", "BUG392_TESTS_REQUIRED")
           and not (k == LIVE_REQUIRED and not live)}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    tests = ["%s::%s" % (SUITE, LIVE_TESTS[k]) for k in LIVE_TESTS]

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
        got = {k: outcomes.get(LIVE_TESTS[k]) for k in LIVE_TESTS}
        want = want_live if live else {k: "SKIPPED" for k in LIVE_TESTS}
        assert got == want, (name, got, out[-3000:])
        assert proc.returncode == (1 if "FAILED" in want.values() else 0), \
            (name, proc.returncode, out[-3000:])
        print("control %-22s marker %d  %s  rc %d  mutated sha256 %s  "
              "restored sha256 %s == original"
              % (name, want_marker,
                 "  ".join("%s %s" % (k, got[k]) for k in LIVE_TESTS),
                 proc.returncode, _sha256(mutated_bytes)[:16], restored[:16]))

    assert _sha256(MAIN_PY.read_bytes()) == before
    print("worktree main.py sha256 %s, unchanged by the controls" % before[:16])
    if not live:
        pytest.skip("marker half asserted on the copy; the settlement tests' half "
                    "needs %s (live PostgreSQL), so the controls are not "
                    "accepted by this run" % LIVE_DSN)
