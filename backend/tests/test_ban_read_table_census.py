"""Every test file that builds its own table list and runs a function or
route of main that reaches a read of player_bans carries the ban read's
tables from ban_read_tables (or a ruled whole-schema build), and no other
file imports that module (bans part 2a, D1). The rules are in
ban_read_table_census.py; the planted controls below show each direction
fails.
"""
import ban_read_table_census as C

_MAIN = '''
from fastapi import Depends

def _gate(db):
    return db.execute("SELECT 1 FROM player_bans WHERE steam_id = :s")

def _session(request):
    return _gate(None)

def _helper(db):
    return _gate(db)

@app.post("/api/v1/thing/{tid}/do")
async def do_thing(tid: str, steam_id: str = Depends(_session)):
    return tid

def quiet(db):
    return 1
'''


def test_the_census_holds_on_the_tree():
    reads, reach, paths = C.reaching(C.main_source())
    # the lane's own gate reads are among the reads, and the census sees routes
    assert {"_is_banned", "_ban_gate_any_or_raise"} <= reads, sorted(reads)
    assert len(paths) >= 100, len(paths)
    classes = C.classify(C.tree_sources(), reach, paths)
    builders = sorted(n for n, (b, r, _, _) in classes.items() if b and r)
    print("[ban-read-census] reads", len(reads), "reach", len(reach), "paths", len(paths),
          "builders", len(builders))
    assert len(builders) >= 10, builders
    assert C.failures(classes) == []


def test_the_reach_follows_body_calls_and_route_dependencies():
    reads, reach, paths = C.reaching(_MAIN)
    assert reads == {"_gate"}
    assert reach == {"_gate", "_session", "_helper"}
    # do_thing's body runs nothing that reads; its Depends(_session) does
    assert "do_thing" not in reach
    assert paths == {"/api/v1/thing/{tid}/do"}


def test_planted_builder_without_the_tables_fails():
    _, reach, paths = C.reaching(_MAIN)
    planted = {"test_planted.py": (
        "import main\n"
        "DDL = 'CREATE TABLE players (id UUID PRIMARY KEY)'\n"
        "async def t(c):\n"
        "    await c.post(f'/api/v1/thing/{1}/do')\n")}
    classes = C.classify(planted, reach, paths)
    assert C.failures(classes, rulings={}) == [
        ("test_planted.py", "runs the ban read on a database built without player_bans")]
    planted["test_planted.py"] = "from ban_read_tables import ban_read_ddl\n" + planted["test_planted.py"]
    assert C.failures(C.classify(planted, reach, paths), rulings={}) == []


def test_planted_carrier_that_runs_nothing_fails():
    _, reach, paths = C.reaching(_MAIN)
    planted = {"test_planted.py": (
        "import inspect\nimport main\n"
        "from ban_read_tables import with_ban_read_tables\n"
        "DDL = 'CREATE TABLE players (id UUID PRIMARY KEY)'\n"
        "SRC = inspect.getsource(main._helper)\n"
        "X = main.quiet\n")}
    assert C.failures(C.classify(planted, reach, paths), rulings={}) == [
        ("test_planted.py", "carries the ban read tables but is no builder that runs the ban read")]
