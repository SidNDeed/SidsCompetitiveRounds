"""Bug report 463: the player-stats answer carries `current_casual_streak`.

The profile's casual "Streak" was counted on the client over the cached head
of the match history (400 rows, ranked and casual together), so it could
never pass the number of casual rows in that head. The server already walks
the WHOLE casual history for `best_casual_streak`; the walk's second value,
the signed current streak (negative = loss streak, the same form as
`current_ranked_game_streak`), is now kept and returned beside it.

The production pieces are EXECUTED, not re-typed: the casual statement is
taken from get_player_stats' source and run against an in-memory SQLite
`matches` table, and its rows go through the handler's own nested
_walk_streak. Each filter test carries its own negative control: the same
fixture through the statement with that one predicate removed gives a
different answer, so the fixture can see the predicate. The scope control
asserts the rows the statement selects, not a walked value.

Two structure tests pin what a value test on these fixtures cannot see: the
handler stores current_casual_streak exactly once (the walk's), and each of
its three walk statements ends in a complete ORDER BY, the match history's
three columns with each direction reversed. The handler itself is run
against PostgreSQL in test_casual_current_streak_pg.py.

The /health `casual_streak_build` word follows the music_delist_build test's
form (test_music_delist_build_health_word.py).

Run: python -m pytest backend/tests/test_casual_current_streak.py -q
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import random
import textwrap
import uuid
from datetime import datetime, timedelta

import pydantic
import pytest
from sqlalchemy import create_engine, text

import main
import schemas

PID = str(uuid.uuid4())
OPP = str(uuid.uuid4())
THIRD = str(uuid.uuid4())
BASE = datetime(2026, 1, 1, 0, 0, 0)

INVALIDATED = "AND m.invalidated_at IS NULL"
CASUAL_ONLY = "AND m.is_ranked = false"
SCOPE = "(m.player1_id = :pid OR m.player2_id = :pid)"
ORDER = "ORDER BY m.ended_at ASC"


def _handler_tree():
    src = textwrap.dedent(inspect.getsource(main.get_player_stats))
    (fn,) = ast.parse(src).body
    return fn


def _statement(target: str) -> str:
    """The text() literal assigned (through execute) to `target` in the handler."""
    fn = _handler_tree()
    (assign,) = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                 and [ast.unparse(t) for t in n.targets] == [target]]
    (sql,) = [c.args[0].value for c in ast.walk(assign)
              if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
              and c.func.id == "text" and c.args
              and isinstance(c.args[0], ast.Constant)]
    return sql


def _casual_statement() -> str:
    return _statement("casual_streak_rows")


def _history_statement() -> str:
    """get_player_matches' one text(f"...") statement, its interpolations
    written as {} (only literal text is read from it)."""
    src = textwrap.dedent(inspect.getsource(main.get_player_matches))
    (fn,) = ast.parse(src).body
    (assign,) = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                 and [ast.unparse(t) for t in n.targets] == ["query"]]
    (arg,) = [c.args[0] for c in ast.walk(assign)
              if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
              and c.func.id == "text" and len(c.args) == 1]
    assert isinstance(arg, ast.JoinedStr), ast.unparse(arg)
    return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in arg.values)


def _walk():
    """The handler's own nested _walk_streak, compiled on its own."""
    fn = _handler_tree()
    (node,) = [n for n in ast.walk(fn)
               if isinstance(n, ast.FunctionDef) and n.name == "_walk_streak"]
    ns: dict = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<_walk_streak>", "exec"), ns)
    return ns["_walk_streak"]


def _without(sql: str, fragment: str, replacement: str = "") -> str:
    assert sql.count(fragment) == 1, (fragment, sql)
    return sql.replace(fragment, replacement)


def _select(spec, sql=None):
    """spec: a chronological list of (won, is_ranked, invalidated, players).
    Rows are inserted shuffled, so the order must come from ORDER BY. Row i
    (0-based) gets id i + 1 and created_at equal to its ended_at. Returns the
    statement's rows."""
    sql = sql or _casual_statement()
    eng = create_engine("sqlite://")
    rows = []
    for i, (won, ranked, invalidated, players) in enumerate(spec):
        p1, p2 = players
        rows.append({
            "id": i + 1, "p1": p1, "p2": p2,
            "w": p1 if won else p2,
            "r": 1 if ranked else 0,
            "inv": (BASE + timedelta(days=30)).isoformat() if invalidated else None,
            "at": (BASE + timedelta(minutes=i)).isoformat(),
        })
    random.Random(463).shuffle(rows)
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE matches (id INTEGER, player1_id TEXT, player2_id TEXT,"
            " winner_id TEXT, is_ranked BOOLEAN, invalidated_at TEXT, ended_at TEXT,"
            " created_at TEXT, photon_room_id TEXT)"))
        if rows:
            conn.execute(text(
                "INSERT INTO matches (id, player1_id, player2_id, winner_id, is_ranked,"
                " invalidated_at, ended_at, created_at)"
                " VALUES (:id, :p1, :p2, :w, :r, :inv, :at, :at)"), rows)
        return conn.execute(text(sql), {"pid": PID}).mappings().all()


def _casual(spec, sql=None):
    return _walk()(_select(spec, sql), PID)


def _g(won, ranked=False, invalidated=False, players=(PID, OPP)):
    return (won, ranked, invalidated, players)


W, L = True, False


def test_wins_loss_then_three_wins_gives_best_3_current_3():
    spec = [_g(W), _g(W), _g(L), _g(W), _g(W), _g(W)]
    assert _casual(spec) == (3, 3)
    # Control: the statement read newest-first walks W W W L W W.
    assert _casual(spec, _without(_casual_statement(), ORDER, "ORDER BY m.ended_at DESC")) == (3, 2)


def test_history_ending_in_a_loss_gives_a_signed_current():
    """The walk's current value is signed, as current_ranked_game_streak is:
    one trailing loss is -1, two are -2; best is untouched."""
    assert _casual([_g(W), _g(W), _g(L)]) == (2, -1)
    assert _casual([_g(W), _g(L), _g(L)]) == (1, -2)


def test_an_invalidated_match_is_skipped():
    spec = [_g(W), _g(W), _g(L, invalidated=True), _g(W)]
    assert _casual(spec) == (3, 3)
    # Control: without the invalidated predicate the loss breaks the run.
    assert _casual(spec, _without(_casual_statement(), INVALIDATED)) == (2, 1)


def test_a_ranked_match_does_not_count():
    spec = [_g(W), _g(L, ranked=True), _g(W), _g(W)]
    assert _casual(spec) == (3, 3)
    # Control: without the casual predicate the ranked loss breaks the run.
    assert _casual(spec, _without(_casual_statement(), CASUAL_ONLY)) == (2, 2)


def test_no_matches_gives_0_and_0():
    assert _casual([]) == (0, 0)
    others = [_g(W, players=(OPP, THIRD)), _g(L, players=(THIRD, OPP))]
    assert _casual(others) == (0, 0)


def test_the_scope_selects_only_the_players_rows():
    """The scope control reads WHICH rows the statement selects (count, then
    ids), with and without the scope predicate; no walked value is read.
    The projection gains m.id for the read; nothing else changes."""
    spec = [_g(W), _g(L, players=(OPP, THIRD)), _g(L),
            _g(W, players=(THIRD, OPP)), _g(W, players=(OPP, PID))]
    with_id = _without(_casual_statement(), "SELECT m.winner_id", "SELECT m.id, m.winner_id")
    scoped = [r["id"] for r in _select(spec, with_id)]
    assert len(scoped) == 3, scoped
    assert scoped == [1, 3, 5], scoped
    # Control: without the scope predicate every casual row is selected.
    unscoped = [r["id"] for r in _select(spec, _without(with_id, SCOPE, "true"))]
    assert len(unscoped) == 5 and unscoped == [1, 2, 3, 4, 5], unscoped


def test_the_answer_carries_the_walks_current_value():
    """get_player_stats keeps the casual walk's second value as
    current_casual_streak and passes it, beside best_casual_streak, into its
    one PlayerStatsResponse; the schema declares it as it declares
    current_ranked_game_streak (int, default 0)."""
    fn = _handler_tree()
    walks = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
             and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == "_walk_streak"
             and ast.unparse(n.value.args[0]) == "casual_streak_rows"]
    assert [ast.unparse(w.targets[0]) for w in walks] == [
        "(best_casual_streak, current_casual_streak)"], [ast.unparse(w) for w in walks]
    # The walk's store is the ONLY store of the name in the handler: any
    # later assignment, augmented assignment, loop target, walrus or del of
    # current_casual_streak would change what the answer carries.
    stores = [n for n in ast.walk(fn) if isinstance(n, ast.Name)
              and n.id == "current_casual_streak" and not isinstance(n.ctx, ast.Load)]
    assert len(stores) == 1, [(n.lineno, type(n.ctx).__name__) for n in stores]
    assert stores[0] in list(ast.walk(walks[0].targets[0]))
    (answer,) = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and ast.unparse(n.func) == "PlayerStatsResponse"]
    kw = {k.arg: ast.unparse(k.value) for k in answer.keywords}
    assert kw.get("current_casual_streak") == "current_casual_streak", kw.get("current_casual_streak")
    assert kw.get("best_casual_streak") == "best_casual_streak", kw.get("best_casual_streak")
    fields = schemas.PlayerStatsResponse.model_fields
    new, ref = fields.get("current_casual_streak"), fields["current_ranked_game_streak"]
    assert new is not None and new.annotation is int and new.default == 0, new
    assert (new.annotation, new.default) == (ref.annotation, ref.default)


# --- the walks' order (review round 1, M1)

FLIP = {"ASC": "DESC", "DESC": "ASC"}
HISTORY_TAIL = "LIMIT :limit OFFSET :offset"
# The series walk reads ranked_series: its end column is completed_at.
SERIES_COLUMNS = {"m.ended_at": "rs.completed_at", "m.created_at": "rs.created_at",
                  "m.id": "rs.id"}


def _order_by(sql: str):
    """The statement's last ORDER BY, as (column, direction) pairs. The
    clause must be the statement's end: every item is exactly a column and
    an explicit ASC or DESC, so a trailing clause is refused."""
    assert sql.count("ORDER BY ") >= 1, sql
    tail = sql.rstrip().rpartition("ORDER BY ")[2]
    pairs = []
    for item in tail.split(","):
        words = item.split()
        assert len(words) == 2 and words[1] in FLIP, (item, tail)
        pairs.append((words[0], words[1]))
    return pairs


def test_each_walk_orders_by_the_history_columns_reversed():
    """The match history orders by ended_at, created_at, id, all DESC
    (get_player_matches). Each walk statement ends in the same three columns,
    all ASC (the series walk with ranked_series' columns), so rows with
    equal end times are walked in one fixed order: the reverse of the
    history's."""
    history = _history_statement().rstrip()
    assert history.endswith(HISTORY_TAIL), history[-200:]
    history_order = _order_by(history[: -len(HISTORY_TAIL)])
    assert history_order == [("m.ended_at", "DESC"), ("m.created_at", "DESC"),
                             ("m.id", "DESC")], history_order
    reversed_ = [(col, FLIP[d]) for col, d in history_order]
    got = {name: _order_by(_statement(name)) for name in
           ("ranked_streak_rows", "ranked_game_rows", "casual_streak_rows")}
    for name in got:
        assert _statement(name).count("ORDER BY ") == 1, name
    assert got["casual_streak_rows"] == reversed_, got["casual_streak_rows"]
    assert got["ranked_game_rows"] == reversed_, got["ranked_game_rows"]
    assert got["ranked_streak_rows"] == [(SERIES_COLUMNS[c], d) for c, d in reversed_], \
        got["ranked_streak_rows"]


def test_the_order_reader_refuses_an_incomplete_or_trailing_clause():
    """Negative controls for _order_by: a missing direction and a clause
    after the ORDER BY are refused."""
    with pytest.raises(AssertionError):
        _order_by("SELECT 1 FROM matches m ORDER BY m.ended_at")
    with pytest.raises(AssertionError):
        _order_by("SELECT 1 FROM matches m ORDER BY m.ended_at ASC LIMIT 5")
    assert _order_by("SELECT 1 FROM matches m ORDER BY m.ended_at ASC, m.id DESC\n") == [
        ("m.ended_at", "ASC"), ("m.id", "DESC")]


# --- /health casual_streak_build (form of test_music_delist_build_health_word.py)

KEY = "casual_streak_build"
CONST = "_CASUAL_STREAK_BUILD"


class _DownSession:
    """A session whose server is gone: every statement raises."""

    async def execute(self, *a, **k):
        raise OSError("casual_streak_build: the database is down")

    async def rollback(self):
        pass


def _main_tree():
    with open(main.__file__, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def test_both_health_arms_carry_the_build_marker():
    """Both arms pass the constant and nothing else in main.py passes the
    key; the constant is bound once, to 1."""
    tree = _main_tree()
    (health,) = [n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                 if isinstance(k, ast.keyword) and k.arg == KEY]
    degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == KEY]
    assert (connected, degraded) == ([CONST], [CONST])
    everywhere = [k for k in ast.walk(tree)
                  if isinstance(k, ast.keyword) and k.arg == KEY]
    assert len(everywhere) == 2, len(everywhere)
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
              and n.id == CONST and isinstance(n.ctx, ast.Store)]
    (binding,) = [n for n in tree.body if isinstance(n, ast.Assign)
                  and [ast.unparse(t) for t in n.targets] == [CONST]]
    assert len(stores) == 1 and ast.unparse(binding.value) == "1", ast.unparse(binding)


def test_the_health_schema_requires_the_word_and_the_answer_carries_it():
    """HealthResponse declares it an int with no default; the degraded
    answer, built for real, reads 1, and without the key it does not
    validate."""
    field = schemas.HealthResponse.model_fields.get(KEY)
    assert field is not None and field.annotation is int and field.is_required(), field
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded" and answer[KEY] == 1, answer
    answer.pop(KEY)
    with pytest.raises(pydantic.ValidationError):
        schemas.HealthResponse(**answer)
