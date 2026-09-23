"""The /health word that says this build keys an FFA game on its number.

The rejoin live-defects batch adds no route and no key to any GET answer both
builds serve: its new progress fields ride only the FFA report answer, which
needs a signed report. So `ffa_game_number` is the release train's build
discriminator for the batch -- absent on the build before it, 1 on this one,
on both roles -- and the train reads any other value as the old build.

The value is DERIVED from the two SQL literals the batch introduced (#342): 1
when the ffa_matches insert names game_number AND the prior-game lookup binds
(lobby_id, game_number), 0 when either literal loses the column. That makes it
a statement about the code that ships rather than a stamp beside it, and the
last test here runs the statement on a COPY of main.py in both directions:
each literal with its game_number deleted reads 0 and reddens the existing
test about that literal, and a comment-only edit beside both keeps 1 and
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

from test_player_cards_server import _run                        # noqa: E402
import main                                                      # noqa: E402
import schemas                                                   # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
BACKEND = MAIN_PY.parent.parent

# The two existing tests that pin the literals the marker reads, one each.
LITERAL_TESTS = {
    "insert": "test_the_stored_number_is_the_one_the_anchor_and_the_bet_settle_use",
    "lookup": "test_the_lookup_asks_about_the_number_the_report_named",
}


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


def test_the_marker_is_derived_from_the_two_literals_and_reads_1_here():
    """Derived, bound once, and 1 at this tip.

    A literal `_FFA_GAME_NUMBER = 1` would read 1 on a build that had lost
    the column, which is the one deploy this word exists to tell apart -- a
    check that cannot fail (#342/#441). So the binding has to be a CALL of the
    derivation over the endpoint's own insert and the lookup constant, with no
    number anywhere in it, and nothing may rebind the name afterwards."""
    tree = _module_tree()
    stores = [n for n in ast.walk(tree)
              if isinstance(n, ast.Name) and n.id == "_FFA_GAME_NUMBER"
              and isinstance(n.ctx, ast.Store)]
    assert len(stores) == 1, len(stores)
    assigns = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "_FFA_GAME_NUMBER"
                       for t in n.targets)]
    assert len(assigns) == 1, len(assigns)
    value = assigns[0].value
    assert isinstance(value, ast.Call), ast.dump(value)
    assert not [n for n in ast.walk(value)
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, bool))]
    assert ast.unparse(value.func) == "_ffa_game_number_marker"
    assert [ast.unparse(a) for a in value.args] == [
        "_ffa_match_insert_literal(submit_ffa_match.__code__)", "_FFA_PRIOR_GAME_SQL"]
    assert not value.keywords
    # The two things it reads are the ones the endpoint executes: the insert is
    # the endpoint's own compiled constant, and the lookup is the constant the
    # endpoint passes to text().
    insert = main._ffa_match_insert_literal(main.submit_ffa_match.__code__)
    assert insert.lstrip().startswith("INSERT INTO ffa_matches (")
    assert "text(_FFA_PRIOR_GAME_SQL)" in inspect.getsource(main.submit_ffa_match)
    assert main._FFA_GAME_NUMBER == 1
    assert main._ffa_game_number_marker(insert, main._FFA_PRIOR_GAME_SQL) == 1


def test_the_derivation_reads_each_literal_and_nothing_beside_it():
    """Each literal without game_number reads 0; prose never reads anything.

    The in-process half of the controls: the derivation over edited copies of
    the two strings. The subprocess half below runs the same deletions against
    a copy of the FILE, where the existing literal tests can see them too."""
    marker = main._ffa_game_number_marker
    insert = main._ffa_match_insert_literal(main.submit_ffa_match.__code__)
    lookup = main._FFA_PRIOR_GAME_SQL
    assert marker(insert, lookup) == 1

    unnumbered = insert.replace("elapsed_seconds, game_number,", "elapsed_seconds,", 1)
    assert unnumbered != insert and marker(unnumbered, lookup) == 0
    unbound = lookup.replace("AND game_number = CAST(:g AS SMALLINT)", "", 1)
    assert unbound != lookup and marker(insert, unbound) == 0
    # The pair is the rule, not the number alone: a lookup that stopped keying
    # on the lobby reads 0 as well.
    lobbyless = lookup.replace("lobby_id = CAST(:lid AS uuid)", "TRUE", 1)
    assert lobbyless != lookup and marker(insert, lobbyless) == 0
    # The lookup's SELECT list names game_number too; only the WHERE counts.
    assert "game_number" in lookup.partition("WHERE")[0]
    assert marker("", "") == 0

    def consts_of(source):
        namespace = {}
        exec(compile(source, "<marker-probe>", "exec"), namespace)
        return namespace["f"].__code__

    # A comment carrying the whole numbered statement, beside a string that
    # lacks the column: the compiled constant is what is read, so it reads 0.
    commented = consts_of(
        "def f():\n"
        "    # INSERT INTO ffa_matches (id, lobby_id, game_number) VALUES (:id, :lid, :gn)\n"
        "    return 'INSERT INTO ffa_matches (id, lobby_id) VALUES (:id, :lid)'\n")
    got = main._ffa_match_insert_literal(commented)
    assert got == "INSERT INTO ffa_matches (id, lobby_id) VALUES (:id, :lid)"
    assert marker(got, lookup) == 0
    # Two candidate inserts are refused rather than guessed between, and
    # another table's insert is not this one.
    two = consts_of(
        "def f(x):\n"
        "    if x:\n"
        "        return 'INSERT INTO ffa_matches (id, game_number) VALUES (:id, :a)'\n"
        "    return 'INSERT INTO ffa_matches (id, game_number) VALUES (:id, :b)'\n")
    assert main._ffa_match_insert_literal(two) == ""
    other = consts_of(
        "def f():\n"
        "    return 'INSERT INTO ffa_bets (id, game_number) VALUES (:id, :g)'\n")
    assert main._ffa_match_insert_literal(other) == ""


def test_both_health_arms_report_the_constant(monkeypatch):
    """ok AND degraded, and what they report is the constant, not a 1 typed
    beside it: moved to 0, both answers move with it."""
    up, down = _health()
    assert (up["status"], down["status"]) == ("ok", "degraded")
    assert (up["ffa_game_number"], down["ffa_game_number"]) == (1, 1)
    monkeypatch.setattr(main, "_FFA_GAME_NUMBER", 0)
    up0, down0 = _health()
    assert (up0["ffa_game_number"], down0["ffa_game_number"]) == (0, 0)


def test_the_marker_is_declared_and_read_by_nothing_else():
    """Declared on the model, passed in exactly the two arms, read nowhere else.

    `HealthResponse` drops what it does not declare, so the handler passing the
    word is not by itself enough; the negative control is a name that is NOT
    declared and must be missing from the same dump. The word exists only to
    be probed (#306): the constant is read by the two health arms and nothing
    else, and the two helpers that derive it are called once, by that
    derivation."""
    field = schemas.HealthResponse.model_fields.get("ffa_game_number")
    assert field is not None and field.annotation is int and field.is_required()
    up, _ = _health()
    assert "ffa_game_number" in up
    assert "ffa_game_number_not_a_field" not in schemas.HealthResponse.model_fields
    assert "ffa_game_number_not_a_field" not in up

    tree = _module_tree()
    health = _top_level_function(tree, "health_check")
    tries = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for h in tries[0].handlers for n in ast.walk(h)}

    loads = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
             and n.id == "_FFA_GAME_NUMBER" and isinstance(n.ctx, ast.Load)]
    assert len(loads) == 2, len(loads)
    assert sum(id(n) in ok_arm for n in loads) == 1
    assert sum(id(n) in degraded_arm for n in loads) == 1

    keywords = [k for k in ast.walk(tree)
                if isinstance(k, ast.keyword) and k.arg == "ffa_game_number"]
    assert len(keywords) == 2, len(keywords)
    assert sum(id(k) in ok_arm for k in keywords) == 1
    assert sum(id(k) in degraded_arm for k in keywords) == 1
    assert all(ast.unparse(k.value) == "_FFA_GAME_NUMBER" for k in keywords)

    for helper in ("_ffa_game_number_marker", "_ffa_match_insert_literal"):
        calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Name) and c.func.id == helper]
        assert len(calls) == 1, (helper, len(calls))


# ── the controls, on a copy of the file ─────────────────────────────────────

# Run in a fresh interpreter over the copied tree: import main from the copy,
# print the marker it derived, then run the two literal tests from the copy.
_DRIVER = (
    "import sys\n"
    "api = sys.argv[1]\n"
    "sys.path.insert(0, api)\n"
    "import main\n"
    "print('MARKER=%d' % main._FFA_GAME_NUMBER, flush=True)\n"
    "import pytest\n"
    "sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '-rA'] + sys.argv[2:]))\n"
)
_OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR) \S*::(\w+)", re.MULTILINE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_tree(dst: pathlib.Path) -> pathlib.Path:
    """The smallest tree the two literal tests run from: the api modules, the
    migrations the suite's autouse fixture reads, and three test-side files."""
    api = dst / "backend" / "api"
    sql = dst / "backend" / "sql"
    tests = dst / "backend" / "tests"
    for d in (api, sql, tests):
        d.mkdir(parents=True)
    for p in (BACKEND / "api").glob("*.py"):
        shutil.copyfile(p, api / p.name)
    for p in (BACKEND / "sql").glob("*.sql"):
        shutil.copyfile(p, sql / p.name)
    for name in ("conftest.py", "pc_themes_data.py", "test_ffa_game_number_anchor.py"):
        shutil.copyfile(BACKEND / "tests" / name, tests / name)
    return api / "main.py"


def _controls(nl):
    """(name, [(old, new)], marker wanted, {literal: outcome wanted}).

    Each (old, new) is applied once, and `old` must occur exactly once in the
    file, so a control can neither miss its target nor hit a second one."""
    return [
        ("insert-loses-game-number",
         [("battles_total, paid_battles, elapsed_seconds, game_number," + nl,
           "battles_total, paid_battles, elapsed_seconds," + nl),
          (":bt, :pb, :es, CAST(:gn AS SMALLINT)," + nl,
           ":bt, :pb, :es," + nl)],
         0, {"insert": "FAILED", "lookup": "PASSED"}),
        ("lookup-loses-game-number",
         [("       AND game_number = CAST(:g AS SMALLINT)" + nl + "     ORDER BY ended_at" + nl,
           "     ORDER BY ended_at" + nl)],
         0, {"insert": "PASSED", "lookup": "FAILED"}),
        ("comment-beside-both-literals",
         [('_FFA_PRIOR_GAME_SQL = """' + nl,
           "# game_number, lobby_id: a comment beside the lookup changes none of it" + nl
           + '_FFA_PRIOR_GAME_SQL = """' + nl),
          ('        await db.execute(text("""' + nl + "            INSERT INTO ffa_matches (",
           "        # game_number: a comment beside the insert changes none of it" + nl
           + '        await db.execute(text("""' + nl + "            INSERT INTO ffa_matches (")],
         1, {"insert": "PASSED", "lookup": "PASSED"}),
    ]


def test_the_controls_run_on_a_copy_in_both_directions(tmp_path):
    """RED: each literal with its game_number deleted reads 0 AND reddens the
    existing test about that literal -- only that one, so the red is the
    literal's and not the copy's. GREEN: a comment-only edit beside both reads
    1 and reddens neither, which is also what proves the copied tree runs the
    two tests at all. Every mutation lands on the COPY, is restored byte for
    byte (sha256), and the worktree's main.py is the same bytes at the end."""
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
    anchor_file = "tests/test_ffa_game_number_anchor.py"
    tests = ["%s::%s" % (anchor_file, LITERAL_TESTS[k]) for k in ("insert", "lookup")]

    for name, edits, want_marker, want_outcomes in _controls(nl):
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
        outcomes = {test: result for result, test in _OUTCOME.findall(out)}
        got = {k: outcomes.get(LITERAL_TESTS[k]) for k in LITERAL_TESTS}
        assert got == want_outcomes, (name, got, out[-3000:])
        assert proc.returncode == (1 if "FAILED" in want_outcomes.values() else 0), \
            (name, proc.returncode, out[-3000:])
        print("control %-30s marker %d  insert-test %s  lookup-test %s  rc %d  "
              "mutated sha256 %s  restored sha256 %s == original"
              % (name, want_marker, got["insert"], got["lookup"], proc.returncode,
                 _sha256(mutated_bytes)[:16], restored[:16]))

    assert _sha256(MAIN_PY.read_bytes()) == before
    print("worktree main.py sha256 %s, unchanged by the controls" % before[:16])
