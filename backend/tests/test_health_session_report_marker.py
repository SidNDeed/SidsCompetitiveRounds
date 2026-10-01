"""The /health word that says the session report route is bound and the
database it reads has what its statements name (`session_report`).

Board rows 30a, 30d and 30g change what GET /api/v1/report answers and add no
route, so `session_report` is the release train's build discriminator for
them: absent on the build before, and on this build 1 on both roles when the
database has every table and column that the route's statements name.

NAMED and held complete (#342): the statements are the report's own
`_REPORT_*` constants, named in main._SESSION_REPORT_NAMED - never collected
from globals(), which makes the janitor SQL walker refuse the whole module
(#613). The first tests hold that set equal to what the _report_rows call
sites run and to the same rules run over every `_REPORT_*` constant of the
module, and check that nothing else in the report code runs a statement, so
a statement added outside the named set fails here. The probe's error
mapping runs against fakes below; the live half (the lab database, one
column the gold statement names renamed, and a control rename of a column no
statement names) is test_the_health_word_reads_what_the_labs_database_has in
test_session_report_pg.py.
"""
import ast
import os
import pathlib
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

from test_player_cards_server import _run                        # noqa: E402
import main                                                      # noqa: E402
import schemas                                                   # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()


def _tree():
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def _top_level_function(tree, name):
    found = [n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(found) == 1, (name, len(found))
    return found[0]


def _run_statements():
    """Every statement a _report_rows call site can run, resolved from the
    call's own argument: a constant, a `{where}` template formatted with a
    fragment of a table, or an entry of a table of statements."""
    got, sites = set(), 0
    for node in ast.walk(_tree()):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_report_rows"):
            continue
        sites += 1
        arg = node.args[1]
        if isinstance(arg, ast.Name):
            got.add(getattr(main, arg.id))
        elif (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)
              and arg.func.attr == "format" and isinstance(arg.func.value, ast.Name)):
            template = arg.func.value.id
            (kw,) = arg.keywords
            assert kw.arg == "where" and isinstance(kw.value, ast.Subscript), ast.unparse(arg)
            table = kw.value.value.id
            assert table == template[:-len("_SQL")] + "_WHERE", (template, table)
            got.update(getattr(main, template).format(where=w)
                       for w in getattr(main, table).values())
        elif isinstance(arg, ast.Subscript) and isinstance(arg.value, ast.Name):
            got.update(getattr(main, arg.value.id).values())
        else:
            raise AssertionError("a statement the derivation cannot see: " + ast.unparse(arg))
    return got, sites


# -- the derivation -------------------------------------------------------------

def test_the_derived_statements_are_exactly_what_the_route_runs():
    run, sites = _run_statements()
    assert sites >= 16, sites
    derived = main._SESSION_REPORT_STATEMENTS
    assert len(derived) == len(set(derived))
    assert set(derived) == run, (sorted(set(derived) - run)[:1], sorted(run - set(derived))[:1])
    # each kind of site is in it: plain constants (the rows' own new ones
    # among them), every fragment of each template, every card statement
    for s in (main._REPORT_KIND_SQL, main._REPORT_FFA_LOBBY_SQL, main._REPORT_GOLD_SQL,
              main._REPORT_CALLER_SQL):
        assert s in run
    for template, table in ((main._REPORT_1V1_SQL, main._REPORT_1V1_WHERE),
                            (main._REPORT_TEAM_SQL, main._REPORT_TEAM_WHERE),
                            (main._REPORT_OVT_SQL, main._REPORT_OVT_WHERE)):
        assert len(table) >= 2
        for w in table.values():
            assert template.format(where=w) in run
    assert len(main._REPORT_CARD_STATEMENTS) == len(main._REPORT_CARD_TABLES) == 4
    for s in main._REPORT_CARD_STATEMENTS.values():
        assert s in run


def test_the_named_set_is_every_report_constant_of_the_module():
    """_SESSION_REPORT_NAMED names the module's own objects, report constants
    only, and the same rules run over EVERY `_REPORT_*` constant of the module
    give exactly the named set: a statement left out of the names fails here,
    and so does a table (a template without its table empties the set)."""
    named = main._SESSION_REPORT_NAMED
    assert len(named) >= 19, len(named)
    for name, value in named.items():
        assert name.startswith("_REPORT_"), name
        assert value is getattr(main, name), name
    everything = {k: v for k, v in vars(main).items() if k.startswith("_REPORT_")}
    assert main._SESSION_REPORT_STATEMENTS
    assert main._SESSION_REPORT_STATEMENTS == main._session_report_statements(named)
    assert main._session_report_statements(everything) == main._SESSION_REPORT_STATEMENTS


def test_only_report_rows_runs_a_statement_in_the_report_code():
    """The derivation sees what _report_rows runs, so nothing else in the
    route or its helpers may run or build a statement of its own."""
    tree = _tree()
    first = min(n.lineno for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_REPORT_CALLER_SQL" for t in n.targets))
    functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.lineno > first
                 and (n.name.startswith("_report_") or n.name == "get_set_report")]
    assert len(functions) > 20, len(functions)
    assert "_report_load_cards" in {f.name for f in functions}
    for f in functions:
        if f.name == "_report_rows":
            continue
        for n in ast.walk(f):
            if isinstance(n, ast.Attribute) and n.attr in ("execute", "scalar", "scalars", "stream"):
                raise AssertionError(f.name + " runs a statement of its own")
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "text":
                raise AssertionError(f.name + " builds a statement of its own")


def test_every_report_constant_is_bound_before_the_derivation_reads_them():
    tree = _tree()
    at = [n.lineno for n in tree.body if isinstance(n, ast.Assign)
          and any(isinstance(t, ast.Name) and t.id == "_SESSION_REPORT_STATEMENTS" for t in n.targets)]
    assert len(at) == 1, at
    late = [t.id for n in tree.body if isinstance(n, ast.Assign) and n.lineno > at[0]
            for t in n.targets if isinstance(t, ast.Name) and t.id.startswith("_REPORT_")]
    assert not late, late


def test_the_derivation_rules_on_a_namespace_of_its_own():
    ns = {"_REPORT_X_SQL": "SELECT 1 FROM t WHERE {where}", "_REPORT_Y_SQL": "SELECT 2"}
    derive = main._session_report_statements
    assert derive(ns) == (), "a template without its table: incomplete, nothing asked"
    ns["_REPORT_X_WHERE"] = {"a": "t.a = 1", "b": "t.b = 2"}
    assert derive(ns) == ("SELECT 1 FROM t WHERE t.a = 1", "SELECT 1 FROM t WHERE t.b = 2", "SELECT 2")
    ns["_REPORT_Z_SQL"] = {"m": "WITH q AS (SELECT 1) SELECT * FROM q", "n": "  SELECT 3"}
    assert "  SELECT 3" in derive(ns) and "WITH q AS (SELECT 1) SELECT * FROM q" in derive(ns)
    ns["_REPORT_MIXED"] = {"m": "SELECT 5", "n": "t.a = 1"}      # not all statements
    ns["OTHER_SQL"] = "SELECT 4"                                  # not the report's
    ns["_REPORT_NOT_FOUND"] = "not_found"                         # prose
    ns["_REPORT_WRITE_SQL"] = "UPDATE t SET a = 1"                # not a read
    got = derive(ns)
    for absent in ("SELECT 5", "SELECT 4", "not_found", "UPDATE t SET a = 1"):
        assert absent not in got, absent
    assert main._session_report_probe_sql(()) == ""
    assert main._session_report_probe_sql(("SELECT 2", "SELECT 3")) == (
        "SELECT 1 WHERE false AND EXISTS (SELECT 2) AND EXISTS (SELECT 3)")


# -- the probe ------------------------------------------------------------------

class _Db:
    def __init__(self, exc=None):
        self.exc, self.calls, self.rolled_back = exc, [], 0

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        if self.exc is not None and "EXISTS" in str(stmt):
            raise self.exc

    async def rollback(self):
        self.rolled_back += 1


class _State(Exception):
    def __init__(self, sqlstate):
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class _Wrapped(Exception):
    """SQLAlchemy's shape: the driver's error on .orig."""
    def __init__(self, orig):
        super().__init__("wrapped")
        self.orig = orig


def _caused(inner):
    outer = RuntimeError("outer")
    outer.__cause__ = inner
    return outer


def _contexted(inner):
    outer = RuntimeError("outer")
    outer.__context__ = inner
    return outer


def test_the_probe_analyses_every_statement_with_every_bind_null():
    db = _Db()
    assert _run(main._session_report_probe(db)) == 1
    ((sql, params),) = db.calls
    assert sql == main._SESSION_REPORT_PROBE
    assert sql.startswith("SELECT 1 WHERE false AND EXISTS (")
    for s in main._SESSION_REPORT_STATEMENTS:
        assert " AND EXISTS (" + s + ")" in sql
    assert params and set(params.values()) == {None}
    assert {"key", "cpid", "lim", "sid", "mids", "pids", "refs", "reasons"} <= set(params)


@pytest.mark.parametrize("exc", [
    _State("42703"), _State("42P01"), _State("42601"), _State("42P18"),
    _Wrapped(_State("42703")), _caused(_State("42P01")), _Wrapped(_caused(_State("42501")))])
def test_a_refused_analysis_reads_0_and_rolls_back(exc):
    db = _Db(exc)
    assert _run(main._session_report_probe(db)) == 0
    assert db.rolled_back == 1


@pytest.mark.parametrize("exc", [
    OSError("database unreachable"), _State("08006"), _State("57P01"), _State("40001"),
    _contexted(_State("42703")), _State("4270"), _State("")])
def test_any_other_failure_is_left_to_the_health_catch(exc):
    db = _Db(exc)
    with pytest.raises(type(exc)):
        _run(main._session_report_probe(db))
    assert db.rolled_back == 0


def test_the_route_unbound_reads_0_without_asking(monkeypatch):
    assert main._session_report_bound() is True
    routes = main.app.router.routes
    kept = [r for r in routes if getattr(r, "path", None) != "/api/v1/report"]
    assert len(kept) == len(routes) - 1
    monkeypatch.setattr(main.app.router, "routes", kept)
    assert main._session_report_bound() is False
    db = _Db()
    assert _run(main._session_report_probe(db)) == 0 and db.calls == []
    # bound to another handler is not bound either
    other = [r for r in routes if getattr(r, "path", None) == "/api/v1/report"][0]
    monkeypatch.setattr(other, "endpoint", main.health_check)
    monkeypatch.setattr(main.app.router, "routes", routes)
    assert main._session_report_bound() is False


def test_an_incomplete_set_reads_0_without_asking(monkeypatch):
    monkeypatch.setattr(main, "_SESSION_REPORT_PROBE", "")
    db = _Db()
    assert _run(main._session_report_probe(db)) == 0 and db.calls == []


# -- the route ------------------------------------------------------------------

class _Up:
    async def execute(self, *a, **k):
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


class _Unmigrated:
    async def execute(self, stmt, *a, **k):
        if "EXISTS" in str(stmt):
            raise _Wrapped(_State("42703"))

    async def rollback(self):
        return None


def test_both_health_arms_carry_the_word(monkeypatch):
    up = _run(main.health_check(db=_Up())).model_dump()
    assert (up["status"], up["session_report"]) == ("ok", 1)
    down = _run(main.health_check(db=_Down())).model_dump()
    assert (down["status"], down["session_report"]) == ("degraded", 0)
    # an unmigrated database answers "ok" with 0, never "database disconnected"
    bare = _run(main.health_check(db=_Unmigrated())).model_dump()
    assert (bare["status"], bare["database"], bare["session_report"]) == ("ok", "connected", 0)
    assert _run(main.health_check(db=_Down())).model_dump()["session_report"] == 0


def test_a_degraded_answer_after_a_successful_probe_reads_0():
    """Round 2 L9: once a probe on this worker has read 1, a database outage
    answers status=degraded, database=disconnected and session_report=0 -
    never the earlier 1. Control: the same worker's next connected answer
    reads 1 again, so the 0 is the outage's and not a stuck value."""
    up = _run(main.health_check(db=_Up())).model_dump()
    assert (up["status"], up["database"], up["session_report"]) == ("ok", "connected", 1)
    down = _run(main.health_check(db=_Down())).model_dump()
    assert (down["status"], down["database"], down["session_report"]) == ("degraded", "disconnected", 0)
    again = _run(main.health_check(db=_Up())).model_dump()
    assert (again["status"], again["database"], again["session_report"]) == ("ok", "connected", 1)
    assert not hasattr(main, "_SESSION_REPORT_LAST"), "no worker-local copy of the word is kept"


def test_the_word_is_declared_required_and_read_by_nothing_else():
    field = schemas.HealthResponse.model_fields.get("session_report")
    assert field is not None and field.annotation is int and field.is_required()
    assert "session_report" in _run(main.health_check(db=_Up())).model_dump()

    tree = _tree()
    health = _top_level_function(tree, "health_check")
    tries = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for h in tries[0].handlers for n in ast.walk(h)}
    probes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "_session_report_probe"]
    assert len(probes) == 1 and id(probes[0]) in ok_arm
    ok_src = ast.unparse(tries[0].body[0]) if tries[0].body else ""
    assert "SELECT 1" in ok_src, "the probe runs after the connectivity check"
    keywords = [k for k in ast.walk(tree) if isinstance(k, ast.keyword) and k.arg == "session_report"]
    assert len(keywords) == 2
    assert sum(id(k) in ok_arm for k in keywords) == 1
    assert sum(id(k) in degraded_arm for k in keywords) == 1
    # Round 2 L9: the degraded arm's word is the constant 0
    (down,) = [k for k in keywords if id(k) in degraded_arm]
    assert isinstance(down.value, ast.Constant) and down.value.value == 0, ast.unparse(down.value)
