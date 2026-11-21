"""Every database test file of the ban sweep runs under ban_sweep_pg_bounds.

The lane's database files are the test_ban_sweep_*_pg.py files and
test_ban_sweep_live.py (which holds their shared database fixture). Each
must import the autouse fixture `bounded_pg`; a file that imports it and is
not one of them is a stale entry. Both directions are checked, each with a
planted control. The bound itself is read from a live session in
test_ban_sweep_locks_pg.py (test_every_lane_session_runs_under_its_own_bounds).
"""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_MODULE = "ban_sweep_pg_bounds"
FIXTURE = "bounded_pg"


def _lane_database_files(names):
    return {n for n in names
            if n.startswith("test_ban_sweep_") and (n.endswith("_pg.py") or n == "test_ban_sweep_live.py")}


def _imports_fixture(src):
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module == FIXTURE_MODULE \
                and any(a.name == FIXTURE for a in node.names):
            return True
    return False


def _importers(sources):
    return {n for n, src in sources.items() if _imports_fixture(src)}


def _failures(sources):
    want = _lane_database_files(set(sources))
    have = _importers(sources)
    return sorted(("unbounded", n) for n in want - have) + sorted(("stale", n) for n in have - want)


def _tree_sources():
    out = {}
    for n in sorted(os.listdir(HERE)):
        if n.startswith("test_") and n.endswith(".py"):
            with open(os.path.join(HERE, n), encoding="utf-8") as fh:
                out[n] = fh.read()
    return out


def test_every_lane_database_file_imports_the_bounds():
    sources = _tree_sources()
    assert len(_lane_database_files(set(sources))) >= 7, sorted(_lane_database_files(set(sources)))
    assert _failures(sources) == []


def test_the_check_refuses_an_unbounded_file_and_a_stale_importer():
    sources = _tree_sources()
    planted = dict(sources)
    planted["test_ban_sweep_planted_pg.py"] = "import main\n"
    planted["test_not_the_lane.py"] = ("from ban_sweep_pg_bounds import bounded_pg  # noqa\n")
    assert _failures(planted) == [("unbounded", "test_ban_sweep_planted_pg.py"),
                                  ("stale", "test_not_the_lane.py")]
