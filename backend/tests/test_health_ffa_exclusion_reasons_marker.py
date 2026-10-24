"""The /health word that distinguishes the FFA early-leave grace build.

The grace batch adds no route and no key to a GET answer both builds serve.
The release train therefore reads ffa_exclusion_reasons: absent before this
landing, 1 when the settlement INSERT names the column, on both health arms.
The value is DERIVED from that compiled literal (#342), and nothing except
health_check reads it (#306). Restoring controls exercise a copy of main.py
in fresh interpreters, with no database and no edits to the worktree.
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

import pytest
from pydantic import ValidationError

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import main                                                      # noqa: E402
import schemas                                                   # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
BACKEND = MAIN_PY.parent.parent
T1 = "test_the_marker_is_derived_from_the_literal_and_reads_1_here"


class _Up:
    async def execute(self, *args, **kwargs):
        return None


class _Down:
    async def execute(self, *args, **kwargs):
        raise OSError("database unreachable")


def _run(awaitable):
    return asyncio.run(awaitable)


def _health():
    """Connected and degraded answers rendered by the response model."""
    return (_run(main.health_check(db=_Up())).model_dump(),
            _run(main.health_check(db=_Down())).model_dump())


def _module_tree():
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def _consts_of(source):
    namespace = {}
    exec(compile(source, "<marker-probe>", "exec"), namespace)
    return namespace["f"].__code__


def test_the_marker_is_derived_from_the_literal_and_reads_1_here():
    """The one binding calls the derivation over the endpoint's own literal."""
    tree = _module_tree()
    stores = [n for n in ast.walk(tree)
              if isinstance(n, ast.Name) and n.id == "_FFA_EXCLUSION_REASONS"
              and isinstance(n.ctx, ast.Store)]
    assert len(stores) == 1, len(stores)
    assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "_FFA_EXCLUSION_REASONS"
                           for t in n.targets)]
    assert len(assignments) == 1, len(assignments)
    value = assignments[0].value
    assert isinstance(value, ast.Call), ast.dump(value)
    assert ast.unparse(value.func) == "_ffa_exclusion_reasons_marker"
    assert [ast.unparse(a) for a in value.args] == [
        "_ffa_match_players_insert_literal(submit_ffa_match.__code__)"]
    assert not value.keywords
    assert not [n for n in ast.walk(value)
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, bool))]
    insert = main._ffa_match_players_insert_literal(main.submit_ffa_match.__code__)
    assert insert.lstrip().startswith("INSERT INTO ffa_match_players (")
    assert main._FFA_EXCLUSION_REASONS == 1
    assert main._ffa_exclusion_reasons_marker(insert) == 1


def test_the_derivation_reads_the_column_and_nothing_beside_it():
    """Removing the column reads 0; comments and value bindings do not count."""
    marker = main._ffa_exclusion_reasons_marker
    extract = main._ffa_match_players_insert_literal
    insert = extract(main.submit_ffa_match.__code__)
    assert marker(insert) == 1
    old = "kill_timeline, absent, exclusion_reasons, end_stats,"
    new = "kill_timeline, absent, end_stats,"
    assert insert.count(old) == 1
    without_column = insert.replace(old, new, 1)
    assert marker(without_column) == 0
    assert marker("") == 0
    assert marker("INSERT INTO ffa_match_players (id) VALUES (:exclusion_reasons)") == 0
    assert marker(without_column + "\n-- exclusion_reasons") == 0
    assert marker("INSERT INTO ffa_match_players (exclusion_reasons_extra) VALUES (:x)") == 0

    commented = _consts_of(
        "def f():\n"
        "    # exclusion_reasons: a comment beside the settlement literal\n"
        "    return " + repr(insert) + "\n")
    assert extract(commented) == insert
    assert marker(extract(commented)) == 1
    misleading_comment = _consts_of(
        "def f():\n"
        "    # INSERT INTO ffa_match_players (exclusion_reasons) VALUES (:er)\n"
        "    return " + repr(without_column) + "\n")
    assert extract(misleading_comment) == without_column
    assert marker(extract(misleading_comment)) == 0
    ambiguous = _consts_of(
        "def f(x):\n"
        "    if x:\n"
        "        return 'INSERT INTO ffa_match_players (exclusion_reasons) VALUES (:a)'\n"
        "    return 'INSERT INTO ffa_match_players (exclusion_reasons) VALUES (:b)'\n")
    assert extract(ambiguous) == ""
    other_table = _consts_of(
        "def f():\n"
        "    return 'INSERT INTO ffa_matches (exclusion_reasons) VALUES (:er)'\n")
    assert extract(other_table) == ""
    assert extract(_consts_of("def f():\n    return None\n")) == ""


def test_both_health_arms_report_the_constant(monkeypatch):
    """Both arms follow the derived constant, including when moved to 0."""
    up, down = _health()
    assert (up["status"], down["status"]) == ("ok", "degraded")
    assert (up["ffa_exclusion_reasons"], down["ffa_exclusion_reasons"]) == (1, 1)
    monkeypatch.setattr(main, "_FFA_EXCLUSION_REASONS", 0)
    up0, down0 = _health()
    assert (up0["ffa_exclusion_reasons"], down0["ffa_exclusion_reasons"]) == (0, 0)


def test_the_marker_is_declared_and_read_by_nothing_else():
    """The required model field is supplied only by the two health arms."""
    field = schemas.HealthResponse.model_fields.get("ffa_exclusion_reasons")
    assert field is not None and field.annotation is int and field.is_required()
    tree = _module_tree()
    stores = [n for n in ast.walk(tree)
              if isinstance(n, ast.Name) and n.id == "_FFA_EXCLUSION_REASONS"
              and isinstance(n.ctx, ast.Store)]
    assert len(stores) == 1, len(stores)
    functions = [n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "health_check"]
    assert len(functions) == 1, len(functions)
    tries = [n for n in ast.walk(functions[0]) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for handler in tries[0].handlers for n in ast.walk(handler)}
    loads = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
             and n.id == "_FFA_EXCLUSION_REASONS" and isinstance(n.ctx, ast.Load)]
    assert len(loads) == 2, len(loads)
    assert sum(id(n) in ok_arm for n in loads) == 1
    assert sum(id(n) in degraded_arm for n in loads) == 1
    keywords = [n for n in ast.walk(tree)
                if isinstance(n, ast.keyword) and n.arg == "ffa_exclusion_reasons"]
    assert len(keywords) == 2, len(keywords)
    assert sum(id(n) in ok_arm for n in keywords) == 1
    assert sum(id(n) in degraded_arm for n in keywords) == 1
    assert all(ast.unparse(n.value) == "_FFA_EXCLUSION_REASONS" for n in keywords)
    for helper in ("_ffa_exclusion_reasons_marker", "_ffa_match_players_insert_literal"):
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == helper]
        assert len(calls) == 1, (helper, len(calls))


def test_health_response_requires_the_field():
    """Removing just this field from a valid answer must fail validation."""
    valid, _ = _health()
    schemas.HealthResponse.model_validate(valid)
    missing = dict(valid)
    del missing["ffa_exclusion_reasons"]
    with pytest.raises(ValidationError) as exc:
        schemas.HealthResponse.model_validate(missing)
    assert [(error["loc"], error["type"]) for error in exc.value.errors()] == [
        (("ffa_exclusion_reasons",), "missing")]


_DRIVER = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import main\n"
    "print('MARKER=%d' % main._FFA_EXCLUSION_REASONS, flush=True)\n"
    "import pytest\n"
    "sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '-rA'] + sys.argv[2:]))\n"
)
_OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR) \S*::(\w+)", re.MULTILINE)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _copy_tree(dst):
    """Only api modules and this test; the child runs t1 alone."""
    api = dst / "backend" / "api"
    tests = dst / "backend" / "tests"
    api.mkdir(parents=True)
    tests.mkdir(parents=True)
    for source in (BACKEND / "api").glob("*.py"):
        shutil.copyfile(source, api / source.name)
    shutil.copyfile(pathlib.Path(__file__), tests / pathlib.Path(__file__).name)
    return api / "main.py"


def test_the_controls_run_on_a_copy_in_both_directions(tmp_path):
    """Original GREEN, column deletion RED, adjacent comment GREEN; restored."""
    original = MAIN_PY.read_bytes()
    before = _sha256(original)
    copy = _copy_tree(tmp_path)
    assert copy.read_bytes() == original
    source = original.decode("utf-8")
    nl = "\r\n" if "\r\n" in source else "\n"
    column = "damage_dealt, damage_dealt_timeline, kill_timeline, absent, exclusion_reasons, end_stats," + nl
    column_removed = "damage_dealt, damage_dealt_timeline, kill_timeline, absent, end_stats," + nl
    beside = ('        await db.execute(text("""' + nl
              + "            INSERT INTO ffa_match_players (")
    commented = ("        # exclusion_reasons: a comment changes no settlement column" + nl
                 + beside)
    for old in (column, beside):
        assert source.count(old) == 1, (old, source.count(old))
    controls = [
        ("original", source, 1, "PASSED"),
        ("insert-loses-exclusion-reasons", source.replace(column, column_removed, 1), 0, "FAILED"),
        ("comment-beside-literal", source.replace(beside, commented, 1), 1, "PASSED"),
    ]
    driver = tmp_path / "marker_driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    env = {key: value for key, value in os.environ.items()
           if "DSN" not in key.upper()
           and key.upper() not in ("DATABASE_URL", "DB_URL", "SQLALCHEMY_DATABASE_URI",
                                   "PYTEST_ADDOPTS", "BUG392_TESTS_REQUIRED")}
    env.update(FFA_TEST_PG_OPTOUT="1", FFA_TROPHIES_TEST_PG_OPTOUT="1",
               RJ_TRIAGE_TEST_PG_OPTOUT="1", CF_TEST_PG_OPTOUT="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    backend_copy = (tmp_path / "backend").resolve()
    test_node = str(backend_copy / "tests" / pathlib.Path(__file__).name) + "::" + T1
    try:
        for index, (name, changed, want_marker, want_outcome) in enumerate(controls):
            changed_bytes = changed.encode("utf-8")
            if name != "original":
                assert changed_bytes != original, name
            copy.write_bytes(changed_bytes)
            try:
                proc = subprocess.run(
                    [sys.executable, "-B", str(driver), str(copy.parent),
                     "--basetemp", str((tmp_path / ("child-pytest-%d" % index)).resolve()),
                     "--rootdir", str(backend_copy), "--confcutdir", str(backend_copy), test_node],
                    cwd=str(backend_copy), env=env, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=900)
            finally:
                copy.write_bytes(original)
            assert copy.read_bytes() == original, name
            output = proc.stdout + proc.stderr
            markers = re.findall(r"^MARKER=(\d+)$", output, re.MULTILINE)
            assert markers == [str(want_marker)], (name, markers, output[-3000:])
            outcomes = _OUTCOME.findall(output)
            assert outcomes == [(want_outcome, T1)], (name, outcomes, output[-3000:])
            assert proc.returncode == (1 if want_outcome == "FAILED" else 0), (
                name, proc.returncode, output[-3000:])
            print("control %s marker %d t1 %s rc %d restored sha256 %s == original"
                  % (name, want_marker, want_outcome, proc.returncode, before[:16]))
    finally:
        copy.write_bytes(original)
        assert copy.read_bytes() == original
        assert MAIN_PY.read_bytes() == original, "worktree main.py changed"
    print("worktree main.py sha256 %s, unchanged by the controls" % before[:16])
