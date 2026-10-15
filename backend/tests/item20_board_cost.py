"""Item 20 section 3.2: build the fixture and measure both statements.

NOT a pytest module -- no leading `test_`, so nothing collects it, in the shape
of `steamid64_pg_parity.py` and `net_seat_contract.py` beside it. It is here,
tracked, because the design now states measured milliseconds and a chosen TTL,
and a number in a document that nobody can re-derive is a claim rather than a
measurement (#302). Run it and you get the same table.

    python backend/tests/item20_board_cost.py --build      # fixture, ~1 minute
    python backend/tests/item20_board_cost.py              # measure only

It also leaves behind the database `test_binder_rating_sort.py` wants, which is
why `--build` exists at all: that suite skips unless BINDER_SORT_TEST_PG_DSN
points at a schema this builds.

WHAT IT PROVES AND WHAT IT DOES NOT
-----------------------------------
It proves the PLAN and the shape of the cost at a stated row count. It holds
none of the primary's data, so it says nothing about how many production rows
either statement touches -- that stays a `sql-readonly:` question. The row
counts below were chosen to be at or above plausible production scale rather
than read off the primary, and the direction matters: over-sizing a cost bound
is the safe error.

WHY THE BUILD ORDER IS MIGRATIONS-THEN-ORM
------------------------------------------
`players`, `matches` and `ranked_series` are declared in `models.py`; the pc_*
tables exist only in `backend/sql`. Both halves are needed. Doing the ORM half
FIRST is wrong and silently so: `create_all` makes `players` from models.py,
every later `ALTER TABLE players ADD COLUMN IF NOT EXISTS x ... DEFAULT y` then
finds the column present and is a no-op, and the DEFAULT never lands -- measured
on this seat, thirty-two NOT NULL columns with no DB default and a table no raw
INSERT could fill. SQL schema defaults override ORM defaults, and the build
order is how they get the chance to.

`create_all` also never ADDS a column to a table that exists, so after the ORM
pass the columns that live only in models.py are reconciled explicitly --
`matches.is_ranked` and `matches.series_id` among them, which is precisely what
the board's `legacy` CTE aggregates on. Then the migrations run once more, for
the `ALTER`s whose table did not exist on the first pass.
"""
import argparse
import asyncio
import os
import shutil
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
SQL_DIR = os.path.join(BACKEND, "sql")
sys.path.insert(0, os.path.join(BACKEND, "api"))

HOST, PORT, USER, DB = "127.0.0.1", "55432", "postgres", "item20test"
DSN = "postgresql+asyncpg://%s@%s:%s/%s" % (USER, HOST, PORT, DB)

# The fixture's size, and WHY each number is what it is. Production was read on
# 2026-09-20 through the read-only wrapper on the primary (`sql-readonly:`,
# which is NOT refused on this seat -- an earlier note in the design said it was
# and that was wrong). It stood at: 5,130 players, all live, 5,130 glicko rows,
# 16,401 matches of which ZERO are legacy ranked, 2,217 ranked_series of which
# 1,878 are completed, and an eligible board of 98.
#
# A cost bound is only a bound if the fixture DOMINATES production on every axis
# that the statement's cost scales on, so the defaults below are all above those
# numbers -- `players` and `glicko_ratings` by ~1.75x, and the rest by a wide
# margin. The first fixture this file shipped used 3,000 players and 2,400
# glicko rows, which is BELOW production on both, and those are the outer side
# of the `legacy` nested loop; its numbers are kept in the design as a
# lower-reference run and are not what the bound is set against.
N_PLAYERS, N_RATED = 9000, 9000
N_SERIES, N_COMPLETED, N_MATCHES = 38000, 35000, 40000
SUBJECT_IDS = 300


def _psql():
    exe = shutil.which("psql") or r"C:\pg16\pgsql\bin\psql.exe"
    if not os.path.exists(exe) and not shutil.which("psql"):
        raise SystemExit("psql not found; set it on PATH or install PG 16 at C:\\pg16")
    return exe


def _run(db, args):
    return subprocess.run([_psql(), "-h", HOST, "-p", PORT, "-U", USER, "-d", db,
                           "-v", "ON_ERROR_STOP=0"] + args,
                          capture_output=True, text=True)


BIG_SQL_TEMPLATE = """
TRUNCATE matches, ranked_series, glicko_ratings, match_cards CASCADE;

INSERT INTO glicko_ratings (player_id, rating, rating_deviation, volatility,
                            games_in_period, last_calculated, updated_at)
SELECT CAST(md5('p' || n) AS uuid),
       1100.0 + ((n * 37) %% 900) + (n %% 7) * 0.5,
       60.0 + (n %% 100), 0.06, 0, NOW(), NOW()
FROM generate_series(1, %(rated)d) AS n;

INSERT INTO ranked_series (id, player1_id, player2_id, winner_id, status,
                           p1_series_wins, p2_series_wins, created_at, completed_at,
                           live_p1_points, live_p2_points, is_tournament, is_private,
                           invalidated_at)
SELECT CAST(md5('s' || n) AS uuid),
       CAST(md5('p' || (1 + (n %% 900))) AS uuid),
       CAST(md5('p' || (1 + ((n * 7 + 13) %% 900))) AS uuid),
       CASE WHEN n %% 2 = 0 THEN CAST(md5('p' || (1 + (n %% 900))) AS uuid)
            ELSE CAST(md5('p' || (1 + ((n * 7 + 13) %% 900))) AS uuid) END,
       CASE WHEN n <= %(completed)d THEN 'completed'
            WHEN n %% 3 = 0 THEN 'active' ELSE 'abandoned' END,
       2, 1,
       NOW() - make_interval(days => (n %% 300)),
       CASE WHEN n <= %(completed)d THEN NOW() - make_interval(days => (n %% 300)) END,
       0, 0, false, false,
       -- 0.5%% invalidated: they count for the BOARD, which does not filter
       -- them, and not for the card's W/L, which does. The two series CTEs in
       -- the snapshot exist for exactly that difference.
       CASE WHEN n %% 200 = 3 THEN NOW() END
FROM generate_series(1, %(series)d) AS n
WHERE (1 + (n %% 900)) <> (1 + ((n * 7 + 13) %% 900));

INSERT INTO matches (id, player1_id, player2_id, p1_rounds_won, p2_rounds_won,
                     p1_points_total, p2_points_total, is_ranked, series_id,
                     ended_at, created_at)
SELECT CAST(md5('m' || n) AS uuid),
       CAST(md5('p' || (1 + (n %% 1500))) AS uuid),
       CAST(md5('p' || (1 + ((n * 11 + 5) %% 1500))) AS uuid),
       5, 3, 12, 9,
       (n %% 100) < 40,
       CASE WHEN (n %% 100) < 40 AND (n %% 100) >= 18
            THEN CAST(md5('s' || (1 + (n %% %(completed)d))) AS uuid) END,
       NOW() - make_interval(days => (n %% 365)),
       NOW() - make_interval(days => (n %% 365))
FROM generate_series(1, %(matches)d) AS n
WHERE (1 + (n %% 1500)) <> (1 + ((n * 11 + 5) %% 1500));

ANALYZE players; ANALYZE glicko_ratings; ANALYZE ranked_series; ANALYZE matches;
"""


def _big_sql(rated, series, completed, matches):
    return BIG_SQL_TEMPLATE % {"rated": rated, "series": series,
                               "completed": completed, "matches": matches}


BIG_SQL = _big_sql(N_RATED, N_SERIES, N_COMPLETED, N_MATCHES)


def build():
    subprocess.run([_psql(), "-h", HOST, "-p", PORT, "-U", USER, "-d", "postgres",
                    "-c", "DROP DATABASE IF EXISTS %s" % DB], capture_output=True)
    subprocess.run([_psql(), "-h", HOST, "-p", PORT, "-U", USER, "-d", "postgres",
                    "-c", "CREATE DATABASE %s" % DB], capture_output=True)
    files = sorted(f for f in os.listdir(SQL_DIR)
                   if f.endswith(".sql") and f[:3].isdigit())

    def migrate():
        bad = 0
        for f in files:
            r = _run(DB, ["-f", os.path.join(SQL_DIR, f)])
            if "ERROR" in (r.stderr or ""):
                bad += 1
        return bad

    print("migrations pass 1: %d of %d had errors" % (migrate(), len(files)))

    import models
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.schema import CreateColumn

    async def orm():
        eng = create_async_engine(DSN)
        async with eng.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        added = []
        async with eng.begin() as conn:
            have = await conn.run_sync(
                lambda c: {t: {col["name"] for col in sa_inspect(c).get_columns(t)}
                           for t in sa_inspect(c).get_table_names()})
            for tname, table in models.Base.metadata.tables.items():
                for col in table.columns:
                    if tname in have and col.name not in have[tname]:
                        ddl = str(CreateColumn(col).compile(dialect=conn.dialect))
                        await conn.exec_driver_sql(
                            "ALTER TABLE %s ADD COLUMN %s" % (tname, ddl))
                        added.append("%s.%s" % (tname, col.name))
        await eng.dispose()
        return added

    added = asyncio.run(orm())
    print("create_all + %d columns reconciled from models.py: %s"
          % (len(added), ", ".join(a for a in added if a.startswith("matches."))))
    print("migrations pass 2: %d of %d had errors" % (migrate(), len(files)))

    # players through the ORM, so its python-side defaults land
    from datetime import datetime, timedelta, timezone
    import hashlib
    import uuid as _uuid
    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    def pid(n):
        return _uuid.UUID(hashlib.md5(("p%d" % n).encode()).hexdigest())

    async def seed():
        eng = create_async_engine(DSN)
        Session = async_sessionmaker(eng, expire_on_commit=False)
        now = datetime.now(timezone.utc)
        async with Session() as s:
            await s.execute(_text(
                "TRUNCATE matches, ranked_series, glicko_ratings, match_cards, "
                "pc_prints, pc_cards, players CASCADE"))
            await s.commit()
            s.add_all([models.Player(
                id=pid(n), steam_id=str(76561197960265728 + n),
                display_name="Player %d" % n,
                last_seen=(now - timedelta(days=(n % 80)) if n % 100 < 78
                           else now - timedelta(days=95 + (n % 300))),
                mod_seen_at=(now - timedelta(days=200) if n % 100 < 92 else None),
                deleted_at=(now - timedelta(days=30) if n % 50 == 7 else None),
            ) for n in range(1, N_PLAYERS + 1)])
            await s.commit()
        await eng.dispose()

    asyncio.run(seed())
    p = os.path.join(HERE, "_out", "item20_big.sql")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(BIG_SQL)
    r = _run(DB, ["-f", p])
    print(r.stdout.strip()[-400:] or r.stderr.strip()[-600:])


async def measure():
    import main
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    eng = create_async_engine(DSN)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    async with Session() as s:
        counts = (await s.execute(text("""
            SELECT (SELECT COUNT(*) FROM players) AS players,
                   (SELECT COUNT(*) FROM players WHERE deleted_at IS NULL) AS live,
                   (SELECT COUNT(*) FROM glicko_ratings) AS glicko,
                   (SELECT COUNT(*) FROM matches) AS matches,
                   (SELECT COUNT(*) FROM matches
                     WHERE is_ranked = true AND series_id IS NULL) AS legacy,
                   (SELECT COUNT(*) FROM ranked_series) AS series,
                   (SELECT COUNT(*) FROM ranked_series
                     WHERE status = 'completed') AS completed
        """))).mappings().first()
        print("population: %s" % dict(counts))

        ids = [str(r[0]) for r in (await s.execute(text(
            "SELECT id FROM players ORDER BY id LIMIT %d" % SUBJECT_IDS))).all()]

        async def timed(sql, binds, n=10):
            await s.execute(text(sql), binds)          # warm-up, discarded
            out = []
            for _ in range(n):
                t0 = time.perf_counter()
                rows = (await s.execute(text(sql), binds)).all()
                out.append((time.perf_counter() - t0) * 1000.0)
            return out, len(rows)

        a_binds = {"min_matches": main._PC_POOL_MIN_MATCHES,
                   "active_days": main.LEADERBOARD_ACTIVE_DAYS}
        ta, na = await timed(main._PC_BOARD_RANKS_SQL, a_binds)
        med_a = statistics.median(ta)
        print("\n(a) _PC_BOARD_RANKS_SQL      rows=%d  median %.1f ms "
              "(min %.1f max %.1f)" % (na, med_a, min(ta), max(ta)))

        b_binds = {"active_days": main.LEADERBOARD_ACTIVE_DAYS, "subject_ids": ids}
        tb, nb = await timed(main._PC_SUBJECT_STANDINGS_SQL, b_binds)
        print("(b) _PC_SUBJECT_STANDINGS_SQL  rows=%d  median %.3f ms "
              "(min %.3f max %.3f)" % (nb, statistics.median(tb), min(tb), max(tb)))

        for label, sql, binds in (("(a)", main._PC_BOARD_RANKS_SQL, a_binds),
                                  ("(b)", main._PC_SUBJECT_STANDINGS_SQL, b_binds)):
            plan = (await s.execute(
                text("EXPLAIN (ANALYZE, BUFFERS) " + sql), binds)).all()
            print("\n--- %s plan ---" % label)
            for row in plan:
                t = " ".join(row[0].split())
                if ("Scan" in t or "Join" in t or "Loop" in t or "shared hit" in t
                        or "Execution Time" in t):
                    print("   " + t[:118])

        # the bound the design states, computed here rather than by hand
        ttl = main._PC_STANDINGS_TTL_S
        print("\nTTL = %d s -> one refresh costs %.2f%% of a pool connection-minute "
              "(worst run %.2f%%); the bar is ~1%%."
              % (ttl, 100.0 * (med_a / 1000.0) / ttl, 100.0 * (max(ta) / 1000.0) / ttl))
    await eng.dispose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true",
                    help="drop and rebuild item20test before measuring")
    ap.add_argument("--players", type=int, default=N_PLAYERS,
                    help="players to seed (default %d, above production)" % N_PLAYERS)
    ap.add_argument("--rated", type=int, default=N_RATED,
                    help="glicko_ratings rows (default %d)" % N_RATED)
    a = ap.parse_args()
    # The sizes are overridable so both runs in the design -- the dominating one
    # and the smaller lower-reference one -- are re-derivable from this file
    # rather than being numbers only its author ever saw (#302). BIG_SQL is
    # rebuilt from the template rather than string-patched, so an override
    # cannot half-apply.
    N_PLAYERS, N_RATED = a.players, a.rated
    BIG_SQL = _big_sql(N_RATED, N_SERIES, N_COMPLETED, N_MATCHES)
    if a.build:
        build()
    asyncio.run(measure())
