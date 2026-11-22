"""Every database test file of the ban sweep runs under ban_sweep_pg_bounds.

Which files MUST import the autouse fixture `bounded_pg`: the ban sweep's
database files, that is the test_ban_sweep_*_pg.py files and
test_ban_sweep_live.py (which holds their shared database fixture).

Which files MAY import it: the named set OTHER_LANE_IMPORTERS, files of other
lanes whose sessions are to run under the same bounds. It holds one name,
test_lfp_casual_pg.py: its sessions take a per-player advisory lock, and they
are to run bounded like the ban sweep's.

The census is exact in both directions. A ban sweep database file that does
not import the fixture is unbounded. A file that imports it and is neither a
ban sweep database file nor in the named set is a stale entry. A name in the
named set whose file does not import the fixture is a stale entry too; a named
file absent from the tree does not import it, so it is refused the same way.
Each check has a planted control. The bound itself is read from a live session
in test_ban_sweep_locks_pg.py
(test_every_lane_session_runs_under_its_own_bounds).
"""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_MODULE = "ban_sweep_pg_bounds"
FIXTURE = "bounded_pg"
OTHER_LANE_IMPORTERS = frozenset({"test_lfp_casual_pg.py"})


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


def _failures(sources, named=OTHER_LANE_IMPORTERS):
    want = _lane_database_files(set(sources))
    have = _importers(sources)
    return (sorted(("unbounded", n) for n in want - have)
            + sorted(("stale", n) for n in (have - want - named) | (named - have)))


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


IMPORT_LINE = "from ban_sweep_pg_bounds import bounded_pg  # noqa\n"


def test_the_named_set_refuses_an_unnamed_importer():
    planted = {n: IMPORT_LINE for n in OTHER_LANE_IMPORTERS}
    planted["test_other_lane_planted_pg.py"] = IMPORT_LINE
    assert _failures(planted) == [("stale", "test_other_lane_planted_pg.py")]


def test_the_named_set_refuses_a_named_file_that_does_not_import():
    # One named file is present without the import, one is absent from the tree: both are refused.
    named = {"test_named_planted_pg.py", "test_named_absent_pg.py"}
    planted = {"test_named_planted_pg.py": "import main\n"}
    assert _failures(planted, named) == [("stale", "test_named_absent_pg.py"),
                                         ("stale", "test_named_planted_pg.py")]
