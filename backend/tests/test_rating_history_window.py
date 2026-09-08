"""Sept 6 item f — the rating-history window is the NEWEST 500 rows, ascending.

Both history feeds (the full /players/{steam_id} payload and the lean
/players/{steam_id}/rating-history) used to take the OLDEST 500 rows, so a
long-lived player's graph froze in the past. The two helpers that now serve
them are EXECUTED here against an in-memory SQLite database through a facade
with the AsyncSession surface they use — the window rule is proven by running
the production statement, not by reading it. The old shape (ORDER BY ASC
LIMIT 500) runs as the negative control: it returns the oldest rows, exactly
what the assertions reject.

Run: python -m pytest backend/tests/test_rating_history_window.py -q
"""
from __future__ import annotations

import asyncio
import inspect
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select, text

import main
from models import RatingHistory

PLAYER = uuid.uuid4()
OTHER = uuid.uuid4()
BASE = datetime(2026, 1, 1, 0, 0, 0)
WINDOW = 500


class _Mappings:
    """asyncpg hands the helpers typed values; sqlite3 hands back TEXT for the
    raw-SQL path. Decoding the timestamp columns here is the facade doing the
    driver's job — the rows themselves are untouched."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        out = []
        for row in self._rows:
            d = dict(row._mapping)
            for key in ("created_at", "period_end"):
                if isinstance(d.get(key), str):
                    d[key] = datetime.fromisoformat(d[key])
            out.append(d)
        return out


class _Result:
    def __init__(self, result):
        self._rows = result.all()

    def all(self):
        return self._rows

    def mappings(self):
        return _Mappings(self._rows)


class SqliteAsyncSession:
    """Exactly the surface the two window helpers use: `await db.execute(stmt[, params])`
    then `.all()` or `.mappings().all()`."""

    def __init__(self, conn):
        self.conn = conn
        self.statements = []

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return _Result(self.conn.execute(statement, params or {}))


def _history_engine(n_rows: int, other_rows: int = 7):
    eng = create_engine("sqlite://")
    RatingHistory.__table__.create(eng)
    rows = [
        {"id": uuid.uuid4(), "player_id": PLAYER, "rating": 1000.0 + i,
         "rating_deviation": 60.0 + (i % 7), "volatility": 0.06,
         "period_end": BASE + timedelta(hours=i), "created_at": BASE}
        for i in range(n_rows)
    ] + [
        {"id": uuid.uuid4(), "player_id": OTHER, "rating": 5000.0 + i,
         "rating_deviation": 90.0, "volatility": 0.06,
         "period_end": BASE + timedelta(hours=10_000 + i), "created_at": BASE}
        for i in range(other_rows)
    ]
    random.Random(6).shuffle(rows)      # the window must come from ORDER BY, not insertion order
    with eng.begin() as conn:
        conn.execute(RatingHistory.__table__.insert(), rows)
    return eng


def _window(eng, limit=None):
    with eng.connect() as conn:
        session = SqliteAsyncSession(conn)
        if limit is None:
            hist = asyncio.run(main._rating_history_window(session, PLAYER))
        else:
            hist = asyncio.run(main._rating_history_window(session, PLAYER, limit))
    return hist, session.statements


def test_1v1_window_is_the_newest_500_in_ascending_order():
    hist, statements = _window(_history_engine(600))
    # the window and the plot order break period_end ties on created_at then id
    assert "created_at DESC" in statements[0] and "id DESC" in statements[0]
    assert "created_at ASC" in statements[0] and "id ASC" in statements[0]
    assert len(hist) == WINDOW
    assert [h["rating"] for h in hist] == [1000 + i for i in range(100, 600)]
    dates = [h["period_end"] for h in hist]
    assert dates == sorted(dates)
    assert dates[0] == (BASE + timedelta(hours=100)).isoformat()
    assert dates[-1] == (BASE + timedelta(hours=599)).isoformat()
    # additive contract: the v1.26.8 keys are untouched, period_end is the same instant
    assert all(set(h) == {"rating", "rd", "date", "period_end"} for h in hist)
    assert all(h["date"] == h["period_end"] for h in hist)
    assert hist[-1]["rd"] == round(60.0 + (599 % 7))
    # the statement itself: newest-first inner window, ascending outer order
    assert len(statements) == 1
    sql = statements[0]
    assert "ORDER BY rating_history.period_end DESC" in sql
    assert " LIMIT " in sql
    assert sql.rstrip().endswith("ORDER BY newest.period_end ASC, newest.created_at ASC, newest.id ASC")


def test_1v1_window_short_history_returns_every_row():
    hist, _ = _window(_history_engine(3))
    assert [h["rating"] for h in hist] == [1000, 1001, 1002]
    assert [h["period_end"] for h in hist] == [(BASE + timedelta(hours=i)).isoformat() for i in range(3)]


def test_1v1_window_honours_the_limit_parameter_from_the_newest_end():
    hist, _ = _window(_history_engine(600), limit=10)
    assert [h["rating"] for h in hist] == [1000 + i for i in range(590, 600)]


def test_1v1_window_is_scoped_to_the_player():
    hist, _ = _window(_history_engine(20, other_rows=30))
    assert len(hist) == 20
    assert all(h["rating"] < 5000 for h in hist)


def test_negative_control_the_old_oldest_first_shape_returns_the_oldest_rows():
    """The pre-Sept-6 statement (ASC + LIMIT) on the same fixture: it yields the
    OLDEST 500, which test_1v1_window_is_the_newest_500 would reject. The fixture
    therefore discriminates the two shapes; the assertions above cannot pass by
    accident."""
    eng = _history_engine(600)
    with eng.connect() as conn:
        old = conn.execute(
            select(RatingHistory.rating)
            .where(RatingHistory.player_id == PLAYER)
            .order_by(RatingHistory.period_end.asc())
            .limit(WINDOW)
        ).scalars().all()
    assert [int(r) for r in old] == [1000 + i for i in range(0, 500)]
    assert [int(r) for r in old] != [1000 + i for i in range(100, 600)]


# ── FFA counterpart: the per-player game rows ARE the history ────────────────

def _ffa_engine(n_ranked: int):
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE ffa_matches (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
            "is_ranked BOOLEAN NOT NULL, invalidated_at TEXT)"))
        conn.execute(text(
            "CREATE TABLE ffa_match_players (match_id TEXT NOT NULL, player_id TEXT NOT NULL, "
            "rating_after REAL, rating_before REAL, absent BOOLEAN NOT NULL DEFAULT 0)"))

        def game(i, *, ranked=True, invalidated=None, absent=False, rating=None, player=PLAYER,
                 before="auto"):
            # rating_before mirrors the settlement: the pre-update value, 5 below the
            # result here so a test can tell the two apart; None = a NULL column.
            if before == "auto":
                before = None if rating is None else rating - 5.0
            mid = str(uuid.uuid4())
            conn.execute(text("INSERT INTO ffa_matches VALUES (:id, :c, :r, :inv)"),
                         {"id": mid, "c": (BASE + timedelta(hours=i)).isoformat(),
                          "r": ranked, "inv": invalidated})
            conn.execute(text("INSERT INTO ffa_match_players VALUES (:m, :p, :ra, :rb, :ab)"),
                         {"m": mid, "p": str(player), "ra": rating, "rb": before, "ab": absent})

        order = list(range(n_ranked))
        random.Random(7).shuffle(order)
        for i in order:
            # one in-window row with a NULL rating_before: the key must simply be absent
            game(i, rating=1500.0 + i, before=None if i == 350 else "auto")
        # Every excluded class sits at the NEWEST end, where a leaky filter would
        # surface it inside the window.
        game(n_ranked + 1, ranked=False, rating=None)                    # casual: rating_after NULL
        game(n_ranked + 2, ranked=False, rating=9000.0)                  # casual with a stray rating_after
        game(n_ranked + 3, invalidated=BASE.isoformat(), rating=9001.0)  # invalidated match
        game(n_ranked + 4, absent=True, rating=9002.0)                   # roster ghost (#227)
        game(n_ranked + 5, rating=9003.0, player=OTHER)                  # someone else
    return eng


def _ffa_window(eng):
    with eng.connect() as conn:
        session = SqliteAsyncSession(conn)
        hist = asyncio.run(main._ffa_rating_history_window(session, str(PLAYER)))
    return hist, session.statements


def test_ffa_window_is_the_newest_500_rated_games_ascending_with_every_filter_kept():
    hist, statements = _ffa_window(_ffa_engine(600))
    assert len(hist) == WINDOW
    assert [h["rating"] for h in hist] == [1500.0 + i for i in range(100, 600)]
    stamps = [h["period_end"] for h in hist]
    assert stamps == sorted(stamps)
    # review f-M1: the FFA row snapshots the pre-update rating, so it rides along;
    # a NULL column leaves the key out rather than sending null
    assert all(set(h) == {"rating", "rating_before", "recorded_at", "date", "period_end"}
               for h in hist if h["rating"] != 1850.0)
    assert all(h["rating_before"] == h["rating"] - 5.0 for h in hist if "rating_before" in h)
    null_row = [h for h in hist if h["rating"] == 1850.0]
    assert len(null_row) == 1 and "rating_before" not in null_row[0]
    assert hist[0]["rating_before"] == 1595.0          # the window's first drawn point (F-L)
    assert all(h["recorded_at"] == h["date"] == h["period_end"] for h in hist)
    assert all(h["rating"] < 9000 for h in hist)      # none of the excluded classes leaked
    sql = statements[0]
    for predicate in ("fm.is_ranked IS TRUE", "fm.invalidated_at IS NULL",
                      "NOT fmp.absent", "fmp.rating_after IS NOT NULL", "fmp.rating_before",
                      "ORDER BY fm.created_at DESC, fm.id DESC", "ORDER BY created_at ASC, match_id ASC"):
        assert predicate in sql, f"FFA window lost: {predicate}"


def test_ffa_window_short_history_returns_every_rated_row():
    hist, _ = _ffa_window(_ffa_engine(3))
    assert [h["rating"] for h in hist] == [1500.0, 1501.0, 1502.0]
    assert [h["rating_before"] for h in hist] == [1495.0, 1496.0, 1497.0]


# ── the handlers are pinned to the helpers (no second copy of the query) ─────

def test_both_history_feeds_use_the_shared_window_helpers():
    assert main.RATING_HISTORY_WINDOW == WINDOW
    stats_src = inspect.getsource(main.get_player_stats)
    assert "await _rating_history_window(db, player.id)" in stats_src
    assert "await _ffa_rating_history_window(db, player.id)" in stats_src
    assert "select(RatingHistory)" not in stats_src
    assert "LIMIT 500" not in stats_src
    lean_src = inspect.getsource(main.get_player_rating_history)
    assert "await _rating_history_window(db, pid, limit)" in lean_src
    assert "select(RatingHistory)" not in lean_src
    # the writer still records no pre-update rating, which is why both clients'
    # baseline rule falls to the first row's rating (design F-L)
    assert not hasattr(RatingHistory, "rating_before")
