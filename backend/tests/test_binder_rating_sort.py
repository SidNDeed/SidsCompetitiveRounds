"""Item 20 server half -- the subject's standings TODAY on a collection read.

The binder's new "Rating position" sort orders cards by where each subject
stands on the leaderboard NOW. The print row carries only the MINT-TIME
snapshot (`pr.board_rank`, `pr.rating`), which pc_face draws on the card, so
the answer has to carry today's numbers beside it. Two statements do that:
`_PC_BOARD_RANKS_SQL`, the whole board over the shared `_PC_BOARD_CTE_SQL`,
cached per (min_matches, active_days) for `_PC_STANDINGS_TTL_S`; and
`_PC_SUBJECT_STANDINGS_SQL`, a per-request read over the subjects of the rows
just fetched.

Nothing here can be settled by reading. Whether the TTL actually collapses N
reads into one execution, whether the cache notices its binds changed, whether
`min_matches` really keeps a 4-game player off the board, and whether a deleted
subject's rating really comes back NULL are all properties of a running
PostgreSQL. So the statements are EXECUTED (#313/#340/#465) against this seat's
local server, and the module skips unless its DSN is set:

    BINDER_SORT_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/item20test" \\
        python -m pytest tests/test_binder_rating_sort.py -q

Build that database first -- it needs the real schema, both halves of it
(backend/sql for pc_*, models.py for matches/ranked_series). Set
BINDER_SORT_TESTS_REQUIRED=1 to turn "no DSN" into a hard failure rather than
a skip, so a verification run cannot pass by collecting nothing.

There is no pytest-asyncio here, as in test_pc_edition_rollover.py and
test_a1_predicate_sql.py: each test is a sync function that runs one
coroutine.
"""
import asyncio
import inspect
import os
import re
import sys
import urllib.parse as _urlparse
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import main  # noqa: E402

DSN_VAR = "BINDER_SORT_TEST_PG_DSN"
DSN = os.environ.get(DSN_VAR)
REQUIRED = os.environ.get("BINDER_SORT_TESTS_REQUIRED") == "1"

if REQUIRED and not DSN:
    raise RuntimeError(
        "BINDER_SORT_TESTS_REQUIRED=1 but %s is unset -- refusing to report a "
        "green run for a module that would collect nothing. Check the variable "
        "NAME: a near-miss spelling gives 'N skipped, exit 0', which reads as "
        "clean in any summary that reports pass/fail rather than collected "
        "count." % DSN_VAR)


def _refuse_unless_throwaway(dsn):
    """`_seed` DELETEs from players, glicko_ratings, ranked_series, matches,
    pc_prints and pc_cards. The only thing between this module and a real
    database is one environment variable, so the DSN has to name itself
    disposable before anything here runs -- loudly, at import, rather than
    after the first DELETE, by which point an assertion is only reporting the
    damage (#721).

    The host is an ALLOWLIST, not a denylist of known production names: "is
    not one of five names I thought of" is not "is a throwaway". Only loopback
    is.
    """
    parsed = _urlparse.urlsplit(dsn)
    try:
        host = (parsed.hostname or "").lower()
    except ValueError:                       # malformed authority
        host = "?"
    if host not in ("", "localhost", "127.0.0.1", "::1"):
        raise RuntimeError(
            "%s points at host %r. These tests empty core tables and run "
            "against a database on this machine only." % (DSN_VAR, host))
    tail = (parsed.path or "").lstrip("/").split("?")[0].strip().lower()
    if not tail:
        tail = dsn.rsplit("/", 1)[-1].split("?")[0].strip().lower()
    if not (tail.startswith("item20test") or tail.startswith("scratch")
            or tail.startswith("test")):
        raise RuntimeError(
            "%s names database %r. These tests empty core tables, so they run "
            "only against a database named item20test*/scratch*/test*."
            % (DSN_VAR, tail))
    low = dsn.lower()
    for marker in ("192.168.", "duckdns", "competitive-rounds", "scr-a", "scr-b"):
        if marker in low:
            raise RuntimeError(
                "%s contains %r, which names a real host. These tests empty "
                "core tables and run against a local throwaway only."
                % (DSN_VAR, marker))


if DSN:
    _refuse_unless_throwaway(DSN)

needs_pg = pytest.mark.skipif(
    not DSN, reason="%s unset; live-Postgres standings check" % DSN_VAR)

# Exactly this many tests in this module need the DSN. Pinned from OUTSIDE the
# gate (the test at the bottom of this file always runs) so that moving one
# behind the gate is a deliberate edit and not a silent extra "skipped" that
# still reads as a clean run.
LIVE_TESTS = 10


def run(coro):
    return asyncio.run(coro)


# ── the fixture ──────────────────────────────────────────────────────────────
#
# Four subjects whose standings must come out as four DISTINCT triples, plus
# 99 filler players that exist only to put B at a rank a constant could not
# guess. Everything is deterministic: ids are md5 of a name, ratings are
# literals, and `last_seen` is expressed as an offset from now, so the test
# says the same thing next month (#717 -- a date literal in a gated file is a
# bomb with a printed fuse).

SUBJ = {name: uuid.UUID(int=0x20A0_0000 + i)
        for i, name in enumerate(("top", "hundred_one", "four_games",
                                  "inactive_high", "owner"))}
FILLERS = 99


def _pid(n):
    return uuid.UUID(int=0x20B0_0000 + n)


# One statement per execute: asyncpg prepares every statement, and a prepared
# statement may not carry multiple commands. Ordered so no foreign key is ever
# left dangling.
SEED_WIPE = ("DELETE FROM pc_prints", "DELETE FROM pc_cards",
             "DELETE FROM matches", "DELETE FROM ranked_series",
             "DELETE FROM glicko_ratings", "DELETE FROM players")


async def _seed(s, *, inactive_high_days=120, four_games_deleted=False,
                top_deleted=False):
    """Build the population. Ratings are chosen so the board comes out

        top           3000.0   active,  6 completed series  -> rank 1
        filler 1..99  2000..1902                            -> ranks 2..100
        hundred_one   1900.0   active,  6 completed series  -> rank 101
        four_games    2500.0   active,  FOUR completed      -> no rank
        inactive_high 3500.0   inactive (120 days), 6       -> no rank

    `four_games` is the whole point of the 5-match minimum: it has the second
    highest rating of the four and must still be off the board.
    `inactive_high` has the highest of all and must also be off it, which is
    why the design's FRONT predicate can afford to say "top 100 AND not
    inactive" -- an inactive subject holds no position on this board at all.
    """
    for stmt in SEED_WIPE:
        await s.execute(text(stmt))
    now = datetime.now(timezone.utc)
    rows = [
        (SUBJ["top"], "Subject Top", 3000.0, 2, 6, top_deleted),
        (SUBJ["hundred_one"], "Subject 101", 1900.0, 2, 6, False),
        (SUBJ["four_games"], "Subject Four", 2500.0, 2, 4, four_games_deleted),
        (SUBJ["inactive_high"], "Subject Quiet", 3500.0, inactive_high_days, 6, False),
    ]
    for n in range(1, FILLERS + 1):
        rows.append((_pid(n), "Filler %d" % n, 2000.0 - (n - 1), 3, 6, False))
    # the binder's owner: not a card subject, so no rating and no series
    rows.append((SUBJ["owner"], "Binder Owner", None, 1, 0, False))

    # Three bulk statements, in dependency order: every player row exists
    # before any rating or series can reference it. Written per-row first, and
    # that version failed on the OWNER -- appended last, but named as player2
    # by the very first series insert. Bulk executes fix the ordering and take
    # the seed from ~620 round trips to three.
    await s.execute(text("""
        INSERT INTO players (id, steam_id, display_name, last_seen, mod_seen_at,
                             deleted_at, pc_collection_public, total_xp,
                             pref_same_cards, nametag_style_ids)
        VALUES (CAST(:id AS uuid), CAST(:sid AS text), CAST(:nm AS text),
                :seen, :seen, :del, true, 0, false, ARRAY[]::bigint[])
    """), [{"id": str(pid), "sid": str(76561197960265728 + i),
            "nm": name, "seen": now - timedelta(days=seen_days),
            "del": (now - timedelta(days=1)) if deleted else None}
           # the Steam id is the row's ORDINAL, not a hash of the uuid: the
           # first version masked the low 20 bits of two id families that
           # overlap there, and `players_steam_id_key` caught it
           for i, (pid, name, _r, seen_days, _n, deleted) in enumerate(rows)])

    rated = [{"id": str(pid), "r": rating}
             for pid, _nm, rating, _s, _n, _d in rows if rating is not None]
    await s.execute(text("""
        INSERT INTO glicko_ratings (player_id, rating, rating_deviation,
                                    volatility, games_in_period,
                                    last_calculated, updated_at)
        VALUES (CAST(:id AS uuid), :r, 60.0, 0.06, 0, NOW(), NOW())
    """), rated)

    series_rows = [{"a": str(pid), "b": str(SUBJ["owner"])}
                   for pid, _nm, _r, _s, n, _d in rows for _k in range(n)]
    await s.execute(text("""
        INSERT INTO ranked_series (id, player1_id, player2_id, winner_id,
                                   status, p1_series_wins, p2_series_wins,
                                   created_at, completed_at, live_p1_points,
                                   live_p2_points, is_tournament, is_private)
        VALUES (gen_random_uuid(), CAST(:a AS uuid), CAST(:b AS uuid),
                CAST(:a AS uuid), 'completed', 2, 1, NOW(), NOW(),
                0, 0, false, false)
    """), series_rows)
    await s.commit()


async def _standings(s, names=("top", "hundred_one", "four_games", "inactive_high")):
    """The shipped helper, run for real, keyed back by fixture name."""
    got = await main._pc_subject_standings(s, [str(SUBJ[n]) for n in names])
    return {n: got.get(str(SUBJ[n])) for n in names}


class _CountingSession:
    """An AsyncSession proxy that counts executions of one statement.

    S6 and S7 both turn on "how many times did the BOARD statement run", and
    counting it anywhere else -- a call counter on the helper, a log line --
    would count the cache hits too, which is precisely the difference being
    measured.
    """

    def __init__(self, inner, sql):
        self._inner, self._sql, self.n = inner, sql, 0

    async def execute(self, clause, params=None):
        try:
            same = str(clause) == self._sql
        except Exception:
            same = False
        if same:
            self.n += 1
        return await self._inner.execute(clause, params)

    def __getattr__(self, item):
        return getattr(self._inner, item)


async def _session():
    eng = create_async_engine(DSN)
    return eng, async_sessionmaker(eng, expire_on_commit=False)


# ── S2: the board is ONE text, and both statements stand on it ───────────────
#
# Outside the DSN gate on purpose. A machine with no Postgres skips everything
# below, and a shared fragment that silently stops being shared is exactly the
# thing that would then rot unobserved.

EXPECTED_BOARD_CTE = """
    legacy AS (
        SELECT p.id AS player_id, COUNT(m.id) AS total
          FROM players p
          JOIN matches m ON (m.player1_id = p.id OR m.player2_id = p.id)
                        AND m.is_ranked = true AND m.series_id IS NULL
         GROUP BY p.id
    ),
    board_series AS (
        SELECT s.player_id, COUNT(*) AS total
          FROM (SELECT rs.player1_id AS player_id FROM ranked_series rs WHERE rs.status = 'completed'
                UNION ALL
                SELECT rs.player2_id FROM ranked_series rs WHERE rs.status = 'completed') s
         GROUP BY s.player_id
    ),
    board AS (
        SELECT gr.player_id, ROW_NUMBER() OVER (ORDER BY gr.rating DESC, p.id) AS board_rank
          FROM glicko_ratings gr
          JOIN players p ON p.id = gr.player_id
          LEFT JOIN board_series se ON se.player_id = p.id
          LEFT JOIN legacy lg ON lg.player_id = p.id
         WHERE p.deleted_at IS NULL
           AND COALESCE(se.total, 0) + COALESCE(lg.total, 0) >= CAST(:min_matches AS integer)
           AND p.last_seen > NOW() - make_interval(days => CAST(:active_days AS integer))
    )
"""


def test_s2_the_board_is_one_text_that_both_statements_interpolate():
    """A card PRINTS a board position and the binder ORDERS by one. If the two
    came from two texts, a drift in the match minimum, the activity clause or
    the ROW_NUMBER ordering would put a card in a group its own printed rank
    contradicts, and nothing would say so. Pinned character for character, the
    way test_pc_no_steam_no_card.py:319 pins the pool's id clause.
    """
    assert main._PC_BOARD_CTE_SQL == EXPECTED_BOARD_CTE
    # both consumers interpolate the SAME object, not a copy that matches today
    assert main._PC_BOARD_CTE_SQL in main._PC_SNAPSHOT_SELECT_SQL
    assert main._PC_BOARD_CTE_SQL in main._PC_BOARD_RANKS_SQL
    # ...and `board` is the last CTE of the fragment, which is what lets the
    # ranks statement append its own SELECT to it
    assert main._PC_BOARD_RANKS_SQL == ("WITH" + main._PC_BOARD_CTE_SQL
                                        + "\n    SELECT player_id, board_rank FROM board\n")
    src = inspect.getsource(main)
    # the definition plus exactly two readers: no third statement grows its own
    # copy of the board by any other spelling
    assert src.count("_PC_BOARD_CTE_SQL") == 3, "a reader of the board CTE appeared or vanished"
    assert src.count("_PC_BOARD_CTE_SQL = ") == 1


def test_s2b_the_activity_clause_is_the_select_list_form_not_the_where_form():
    """The leaderboard spells "inactive" twice: a bare SELECT-list expression,
    and a WHERE clause carrying `OR CAST(:include_inactive AS boolean)`. That
    disjunct belongs to a display toggle, and inheriting it here would make the
    binder's order change when a player flips a checkbox on another screen.
    """
    assert ("NOT (p.last_seen > NOW() - make_interval(days => CAST(:active_days AS integer)))"
            in main._PC_SUBJECT_STANDINGS_SQL)
    assert "include_inactive" not in main._PC_SUBJECT_STANDINGS_SQL
    assert "include_inactive" not in main._PC_BOARD_RANKS_SQL
    # every bind typed, none string-built (#448)
    assert "CAST(:subject_ids AS uuid[])" in main._PC_SUBJECT_STANDINGS_SQL
    # the request-path statement touches neither aggregate table: that is what
    # makes it cheap, and it is a property of the text, not of a measurement
    for table in ("matches", "ranked_series"):
        assert table not in main._PC_SUBJECT_STANDINGS_SQL


def test_s4c_the_deleted_subject_is_guarded_in_all_three_places():
    """The three guards are MUTUALLY MASKING, so no behavioural test can see
    any one of them go missing. This one reads the text instead.

    `_PC_SUBJECT_STANDINGS_SQL` refuses a deleted subject's numbers three
    separate ways: the LEFT JOIN carries `AND p.deleted_at IS NULL`, `rating`
    is a CASE on the same predicate, and `rated` repeats it. Any ONE of them
    nulls both columns on its own -- so deleting exactly one changes no output,
    and S4 and S4b both stay GREEN. Measured, not assumed: dropping the CASE
    guard, and separately dropping it from `rated`, each left the whole live
    suite passing (2026-09-20 mutation run, cases M12 and M12b).

    That makes the pair of live tests above a check that cannot fail for this
    particular defect (#342), and the defect is a CLASS -- every one of the
    three -- rather than the line a flag would name (#432). The redundancy is
    deliberate and stays: a subject who asked for their data to be deleted
    should be refused by more than one clause. What must not stay is the
    redundancy being INVISIBLE, so the presence of all three is asserted here.
    Remove any one and this reds, which is the only way the suite can tell.
    """
    sql = main._PC_SUBJECT_STANDINGS_SQL
    assert ("LEFT JOIN glicko_ratings gr ON gr.player_id = p.id "
            "AND p.deleted_at IS NULL") in " ".join(sql.split()), \
        "the join's own deleted_at guard is gone"
    assert "CASE WHEN p.deleted_at IS NULL THEN gr.rating END" in " ".join(sql.split()), \
        "the rating column's deleted_at guard is gone"
    assert "(gr.player_id IS NOT NULL AND p.deleted_at IS NULL)" in " ".join(sql.split()), \
        "the rated column's deleted_at guard is gone"
    # exactly three, so a fourth spelling appearing somewhere else in this
    # statement is a deliberate edit rather than a silent drift
    assert " ".join(sql.split()).count("p.deleted_at IS NULL") == 3


# ── S5: scope -- the collection route only ───────────────────────────────────

def test_s5_only_the_collection_route_attaches_standings():
    """`/pc/card` and a pack-open answer go through the same `_pc_print_dict`.
    If the attach had drifted into that helper, every one of them would grow
    four keys and the payload would claim standings on routes that never
    computed any.

    Counted within the FUNCTION span, never file-wide (#432/#279): a file-wide
    count of 1 would be satisfied by the call moving into `_pc_prints_of_pack`.
    """
    src = inspect.getsource(main)
    # the definition, the docstring reference in pc_collection's comment block,
    # and exactly one call
    assert src.count("_pc_attach_subject_standings") == 2
    coll = inspect.getsource(main.pc_collection)
    assert coll.count("await _pc_attach_subject_standings(db, prints)") == 1
    for fn in (main._pc_print_dict, main._pc_prints_of_pack, main.pc_card_face):
        s = inspect.getsource(fn)
        assert "_pc_attach_subject_standings" not in s, fn.__name__
        for key in ("subject_board_rank", "subject_rating", "subject_inactive"):
            assert key not in s, (fn.__name__, key)


def test_s5b_the_standings_flag_is_computed_never_a_literal():
    """`subject_standings: true` may only be said by the path that holds a
    board map and a completed per-subject read. A literal on a return path
    would let a half-deployed box, an early return or a refresh that raised
    claim standings it does not have -- and the client answers a missing or
    false flag by not offering the sort, which is the whole safety of it.
    """
    coll = inspect.getsource(main.pc_collection)
    assert '"subject_standings": standings' in coll
    assert '"subject_standings": True' not in coll and '"subject_standings": true' not in coll
    # the flag's value is the helper's return, and the helper returns False on
    # any failure rather than raising through the route (#276: expiring by
    # default, never blocking by default)
    att = inspect.getsource(main._pc_attach_subject_standings)
    assert "return False" in att and att.count("return True") == 1
    assert "except Exception" in att


def test_s5c_the_cache_is_keyed_on_its_binds_and_rechecks_after_the_lock():
    """Two source properties that the live tests below then demonstrate.

    The key is `(min_matches, active_days)`, so a request whose binds differ
    misses rather than being served someone else's board (#744). And the
    expiry is re-checked AFTER the lock is acquired: without the second check,
    twenty tabs that all miss the first check would queue up and run the
    statement twenty times in a row -- the lock would serialise the cost
    instead of collapsing it.
    """
    fn = inspect.getsource(main._pc_board_ranks)
    assert "key = (int(min_matches), int(active_days))" in fn
    assert fn.count("_PC_BOARD_RANKS_CACHE.get(key)") == 2, \
        "the expiry is checked once, so the lock serialises instead of collapsing"
    body = fn[fn.index("async with _PC_BOARD_RANKS_LOCK:"):]
    assert "_PC_BOARD_RANKS_CACHE.get(key)" in body, "the re-check is outside the lock"
    assert "functools" not in fn and "lru_cache" not in fn
    # monotonic on both sides of every comparison: a wall-clock step must not
    # be able to make an entry immortal. Four since the failure stamp (round 1
    # LOW 2): two comparisons, the success expiry and the failure expiry.
    assert fn.count("time.monotonic()") == 4
    assert "time.time()" not in fn
    assert fn.count("_PC_STANDINGS_FAIL_TTL_S") >= 2 and "_PC_STANDINGS_TTL_S)" in fn
    # the binds are read at the CALLER, so a redirected global changes the key
    caller = inspect.getsource(main._pc_subject_standings)
    assert "min_matches, active_days = _PC_POOL_MIN_MATCHES, LEADERBOARD_ACTIVE_DAYS" in caller


# ── the live half ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_cache():
    """Empty the module cache around every test.

    This is test ISOLATION, not a substitute for keying: the cache is keyed on
    its binds and S7 proves it. What a fixture cannot key away is TIME -- an
    entry written by the previous test is still inside its TTL when the next
    one starts, and every test here would then read a board built from another
    test's fixture.
    """
    main._PC_BOARD_RANKS_CACHE.clear()
    yield
    main._PC_BOARD_RANKS_CACHE.clear()


@needs_pg
def test_s1_four_subjects_get_four_distinct_triples():
    """The load-bearing case. A server emitting a constant gives four equal
    triples; one that dropped the `min_matches` clause hands `four_games` a
    position; one that ignored the activity clause hands `inactive_high` the
    top of the board, since its rating is the highest of all.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s)
                got = await _standings(s)
                assert got["top"] == {"board_rank": 1, "rating": 3000.0,
                                      "inactive": False}
                assert got["hundred_one"] == {"board_rank": 101, "rating": 1900.0,
                                              "inactive": False}
                # 4 completed series, one short of the minimum: no position,
                # and a rating that is nonetheless the second highest here
                assert got["four_games"] == {"board_rank": None, "rating": 2500.0,
                                             "inactive": False}
                # the highest rating of the four, and off the board entirely
                assert got["inactive_high"] == {"board_rank": None, "rating": 3500.0,
                                                "inactive": True}
                assert len({tuple(sorted(v.items())) for v in got.values()}) == 4
        finally:
            await eng.dispose()
    run(go())


@needs_pg
def test_s3_the_inactive_subject_gains_a_position_when_it_comes_back():
    """Mutation and control on one fixture: the same player, at 120 days and
    at 3 days. A statement that ignored `last_seen` would give the same answer
    twice; one that hard-coded "no rank for this player" would give the same
    answer twice as well, in the other direction.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s, inactive_high_days=120)
                quiet = (await _standings(s))["inactive_high"]
                assert quiet["board_rank"] is None and quiet["inactive"] is True

                # the same subject, seen yesterday. The TTL is the reason the
                # cache is emptied here rather than waiting: the board map is
                # what carries the rank, and it is good for 60 s.
                main._PC_BOARD_RANKS_CACHE.clear()
                await _seed(s, inactive_high_days=3)
                back = (await _standings(s))["inactive_high"]
                # rating 3500 is the highest in the fixture, so it comes back
                # at the very top of the board
                assert back["board_rank"] == 1 and back["inactive"] is False
        finally:
            await eng.dispose()
    run(go())


@needs_pg
def test_s4_a_deleted_subject_has_no_rating_and_no_position():
    """Delete-my-data leaves the print rows standing -- the card is still in
    someone's binder -- so the answer has to stop carrying the subject's
    numbers rather than stop carrying the card. Control: the same fixture
    undeleted, where both come back.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s, top_deleted=True)
                gone = (await _standings(s))["top"]
                assert gone["rating"] is None, "a deleted subject's rating is still on the wire"
                assert gone["board_rank"] is None

                main._PC_BOARD_RANKS_CACHE.clear()
                await _seed(s, top_deleted=False)
                live = (await _standings(s))["top"]
                assert live["rating"] == 3000.0 and live["board_rank"] == 1
        finally:
            await eng.dispose()
    run(go())


@needs_pg
def test_s4b_the_statement_nulls_both_halves_for_a_deleted_subject():
    """The statement's OWN two columns, read directly, because the test above
    cannot see one of them.

    `_PC_SUBJECT_STANDINGS_SQL` guards a deleted subject three times over: the
    LEFT JOIN, the `rating` CASE, and `rated`. `_pc_subject_standings` puts the
    rating on the wire only when `rated` says so, so the rating COLUMN is
    invisible from the helper -- which is why this test reads the statement's
    own columns instead of the helper's output.

    What this test does NOT do, stated plainly because the reverse was once
    written here: it cannot catch the loss of any SINGLE one of the three
    guards. They mask each other -- each nulls both columns unaided -- so
    dropping one changes no output and this test stays green. That was measured
    (2026-09-20 mutation run, M12 and M12b), and it is why
    `test_s4c_the_deleted_subject_is_guarded_in_all_three_places` exists: the
    single-guard case is a TEXT property and is pinned there. What this test
    does catch is the real behavioural failure -- the deleted subject's numbers
    reaching the statement's output at all, which needs two of the three gone.

    Control: the same subject undeleted, where both columns carry a value.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s, top_deleted=True)

                async def row_for(pid):
                    got = (await s.execute(
                        text(main._PC_SUBJECT_STANDINGS_SQL),
                        {"active_days": main.LEADERBOARD_ACTIVE_DAYS,
                         "subject_ids": [str(pid)]})).mappings().all()
                    assert len(got) == 1
                    return got[0]

                gone = await row_for(SUBJ["top"])
                assert gone["rating"] is None, \
                    "the rating column's own deleted_at guard does not bite"
                assert gone["rated"] is False, \
                    "the rated column's deleted_at guard does not bite"

                await _seed(s, top_deleted=False)
                live = await row_for(SUBJ["top"])
                assert live["rating"] == 3000.0 and live["rated"] is True
        finally:
            await eng.dispose()
    run(go())


@needs_pg
def test_s6_the_ttl_collapses_repeated_reads_into_one_board_execution():
    """Both halves, because neither proves anything alone: a route that
    re-runs the board per request reds the first, and a cache that never
    expires reds the second.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s)
                c = _CountingSession(s, main._PC_BOARD_RANKS_SQL)
                for _ in range(5):
                    await main._pc_subject_standings(c, [str(SUBJ["top"])])
                assert c.n == 1, "five reads inside the TTL ran the board %d times" % c.n

                # the mutation: no TTL at all
                main._PC_BOARD_RANKS_CACHE.clear()
                old = main._PC_STANDINGS_TTL_S
                main._PC_STANDINGS_TTL_S = 0
                try:
                    c2 = _CountingSession(s, main._PC_BOARD_RANKS_SQL)
                    for _ in range(5):
                        await main._pc_subject_standings(c2, [str(SUBJ["top"])])
                    assert c2.n == 5, "with the TTL at 0 the board still ran %d times" % c2.n
                finally:
                    main._PC_STANDINGS_TTL_S = old
        finally:
            await eng.dispose()
    run(go())


@needs_pg
def test_s6b_twenty_concurrent_opens_execute_the_board_once():
    """Twenty binder tabs opening together all miss the first expiry check and
    queue on the lock. If the winner's entry were not re-checked after the
    lock, the other nineteen would each run the statement in turn -- the lock
    would serialise 20 executions rather than collapse them, which is worse
    than no lock at all. Control: the same twenty with the TTL at 0, where
    every one of them must execute.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s)
                c = _CountingSession(s, main._PC_BOARD_RANKS_SQL)
                await asyncio.gather(*[
                    main._pc_board_ranks(c, min_matches=5, active_days=90)
                    for _ in range(20)])
                assert c.n == 1, "twenty concurrent opens ran the board %d times" % c.n

                main._PC_BOARD_RANKS_CACHE.clear()
                old = main._PC_STANDINGS_TTL_S
                main._PC_STANDINGS_TTL_S = 0
                try:
                    c2 = _CountingSession(s, main._PC_BOARD_RANKS_SQL)
                    await asyncio.gather(*[
                        main._pc_board_ranks(c2, min_matches=5, active_days=90)
                        for _ in range(20)])
                    assert c2.n == 20, "with the TTL at 0 only %d of twenty ran" % c2.n
                finally:
                    main._PC_STANDINGS_TTL_S = old
        finally:
            await eng.dispose()
    run(go())


@needs_pg
def test_s7_the_cache_notices_its_binds_changed(monkeypatch):
    """#744, as a mutation with its control on the same fixture.

    MUTATION: read once, redirect `LEADERBOARD_ACTIVE_DAYS` to a window that
    admits the quiet subject, read again INSIDE the TTL. The second read must
    see a different board. CONTROL: read twice with the global untouched and
    the board must be identical, and the statement must have run once.

    A path-blind cache passes the control and fails the mutation, which is the
    only way to tell the two apart: with only the control, a cache keyed on
    nothing looks exactly like a cache keyed correctly.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s, inactive_high_days=120)
                c = _CountingSession(s, main._PC_BOARD_RANKS_SQL)

                first = await _standings(c)
                assert first["inactive_high"]["board_rank"] is None
                assert c.n == 1

                # control: nothing changed, so nothing is recomputed
                again = await _standings(c)
                assert again == first and c.n == 1

                # mutation: a 365-day window admits a subject seen 120 days ago
                monkeypatch.setattr(main, "LEADERBOARD_ACTIVE_DAYS", 365)
                wider = await _standings(c)
                assert c.n == 2, "the redirected bind was served from the old key"
                assert wider["inactive_high"]["board_rank"] == 1, \
                    "the board was not recomputed under the new window"
                # ...and `inactive` follows the same global, so the two halves
                # of the answer cannot disagree about what the window is
                assert wider["inactive_high"]["inactive"] is False

                # the original key is still there and still good: a redirect
                # ADDS an entry beside the real one, it does not evict it
                monkeypatch.setattr(main, "LEADERBOARD_ACTIVE_DAYS", 90)
                back = await _standings(c)
                assert back == first and c.n == 2
        finally:
            await eng.dispose()
    run(go())


@needs_pg
def test_s8_a_failing_standings_read_costs_the_sort_and_nothing_else():
    """Which direction the unhandled case fails (#276/#430). A refresh that
    raises must not 500 the binder: the answer comes back with
    `subject_standings` false and no per-print keys, the client keeps its five
    existing sorts, and the refusal costs one ordering.

    Control: the same prints with a working read, where the flag is true and
    the keys are there. Without it this test would pass against a route that
    never attaches anything at all.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s)
                prints = [{"subject_player_id": str(SUBJ["top"]), "rarity": "rare"}]

                ok = await main._pc_attach_subject_standings(s, prints)
                assert ok is True
                assert prints[0]["subject_board_rank"] == 1
                assert prints[0]["subject_rating"] == 3000.0
                assert prints[0]["subject_inactive"] is False

                broken = [{"subject_player_id": str(SUBJ["top"]), "rarity": "rare"}]

                class _Boom:
                    async def execute(self, *a, **k):
                        raise RuntimeError("board unavailable")

                main._PC_BOARD_RANKS_CACHE.clear()
                flag = await main._pc_attach_subject_standings(_Boom(), broken)
                assert flag is False
                for key in ("subject_board_rank", "subject_rating", "subject_inactive"):
                    assert key not in broken[0]
        finally:
            await eng.dispose()
    run(go())


@needs_pg
def test_s9_an_empty_binder_still_reports_that_standings_were_computed():
    """A binder with no prints has no subjects, and the statement is never
    run -- but the api DOES carry the feature, so the flag is true and the
    client offers the sort. Reading it the other way would hide the sort from
    every player until their first card, off a code path that has nothing to
    do with whether the server can compute standings.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s)
                c = _CountingSession(s, main._PC_BOARD_RANKS_SQL)
                assert await main._pc_attach_subject_standings(c, []) is True
                assert c.n == 0, "an empty binder ran the board statement"
        finally:
            await eng.dispose()
    run(go())


@needs_pg
def test_s10_a_cached_rank_never_outlives_the_subjects_rating():
    """The cached board map is a hint and the live row is the authority (Codex
    item 20 round 1, LOW 1). Seed the map with both subjects rated, then take
    one subject's rating row away and mark the other deleted WITHOUT expiring
    the map: inside the TTL the map still holds both old ranks, and the answer
    must still carry no rank for either.

    Control on the same read: `four_games` and the fillers are untouched, and
    the board statement does not run again, so the answer really was built
    from the stale map rather than from a recomputed board.
    """
    async def go():
        eng, Session = await _session()
        try:
            async with Session() as s:
                await _seed(s)
                first = await _standings(s, names=("top", "hundred_one"))
                assert first["top"] == {"board_rank": 1, "rating": 3000.0, "inactive": False}
                assert first["hundred_one"]["board_rank"] == 101
                key = (main._PC_POOL_MIN_MATCHES, main.LEADERBOARD_ACTIVE_DAYS)
                cached = main._PC_BOARD_RANKS_CACHE[key][1]
                assert cached[str(SUBJ["top"])] == 1 and cached[str(SUBJ["hundred_one"])] == 101

                # unrated: the rating row goes; deleted: the data-deletion mark
                await s.execute(text("DELETE FROM glicko_ratings WHERE player_id = CAST(:p AS uuid)"),
                                {"p": str(SUBJ["top"])})
                await s.execute(text("UPDATE players SET deleted_at = NOW() WHERE id = CAST(:p AS uuid)"),
                                {"p": str(SUBJ["hundred_one"])})
                await s.commit()

                c = _CountingSession(s, main._PC_BOARD_RANKS_SQL)
                got = await _standings(c, names=("top", "hundred_one", "four_games"))
                assert c.n == 0, "the map was recomputed, so this read proves nothing about it"
                assert main._PC_BOARD_RANKS_CACHE[key][1][str(SUBJ["top"])] == 1, \
                    "the stale rank is no longer in the map"
                assert got["top"]["rating"] is None
                assert got["top"]["board_rank"] is None, \
                    "a cached rank %r stands beside rating None" % (got["top"]["board_rank"],)
                assert got["hundred_one"]["rating"] is None
                assert got["hundred_one"]["board_rank"] is None, \
                    "a deleted subject keeps cached rank %r" % (got["hundred_one"]["board_rank"],)
                # control: a subject still rated keeps the rank the same map
                # holds, so the mask removes only what the live row disowns
                filler = (await main._pc_subject_standings(c, [str(_pid(1))]))[str(_pid(1))]
                assert filler == {"board_rank": 2, "rating": 2000.0, "inactive": False}
                assert c.n == 0
                assert got["four_games"] == {"board_rank": None, "rating": 2500.0,
                                             "inactive": False}
                assert set(got) == {"top", "hundred_one", "four_games"}
        finally:
            await eng.dispose()
    run(go())


class _FailingBoard:
    """A session whose board statement raises after yielding once, so every
    concurrent caller really is queued on the lock while the first one runs.
    Counts executions of the board statement; any other statement is a defect
    in the test (the board is the first thing the attach path runs)."""

    def __init__(self):
        self.n = 0

    async def execute(self, clause, params=None):
        assert str(clause) == main._PC_BOARD_RANKS_SQL, "unexpected statement"
        self.n += 1
        await asyncio.sleep(0)
        raise RuntimeError("board unavailable")


class _WorkingBoard(_FailingBoard):
    async def execute(self, clause, params=None):
        assert str(clause) == main._PC_BOARD_RANKS_SQL, "unexpected statement"
        self.n += 1

        class _R:
            def mappings(self):
                return self

            def all(self):
                return [{"player_id": "p1", "board_rank": 1}]
        return _R()


def test_s11_a_failed_refresh_is_stamped_so_cold_callers_do_not_queue_on_it(monkeypatch):
    """Codex item 20 round 1, LOW 2. Twelve cold callers arrive together and
    the board statement raises. Without a failure stamp each caller wakes
    behind the lock, finds nothing, and runs the failing statement again --
    twelve executions in series, each on a pool connection. With it: one.

    The clock is the test's own (`main.time` replaced for this test only, the
    asyncio loop keeps the real one), so the window is crossed by setting a
    number, never by sleeping. Recovery half: inside the window a caller and
    the attach helper both answer without the statement (the helper with
    False, the existing degraded answer); after it the next caller runs the
    statement exactly once more, and a working statement then caches the
    board for the full TTL.
    """
    import time as _real_time
    now = [10_000.0]

    class _Clock:
        def __getattr__(self, name):
            return getattr(_real_time, name)

        def monotonic(self):
            return now[0]

    monkeypatch.setattr(main, "time", _Clock())
    # a fresh lock: asyncio.Lock binds to the first loop it is contended on,
    # and each test here runs its own loop
    monkeypatch.setattr(main, "_PC_BOARD_RANKS_LOCK", asyncio.Lock())
    fail_ttl = getattr(main, "_PC_STANDINGS_FAIL_TTL_S", 5)
    # the binds the attach path itself uses, so its read hits the same key
    binds = {"min_matches": main._PC_POOL_MIN_MATCHES,
             "active_days": main.LEADERBOARD_ACTIVE_DAYS}
    db = _FailingBoard()

    async def cold_burst(n):
        return await asyncio.gather(*[
            main._pc_board_ranks(db, **binds) for _ in range(n)],
            return_exceptions=True)

    async def go():
        got = await cold_burst(12)
        assert all(isinstance(g, Exception) for g in got), got
        assert db.n == 1, "twelve cold callers ran the failing board %d times" % db.n

        # inside the window: no statement, and the binder's degraded answer
        now[0] += fail_ttl - 0.5
        prints = [{"subject_player_id": "p1"}]
        assert await main._pc_attach_subject_standings(db, prints) is False
        assert "subject_board_rank" not in prints[0]
        assert db.n == 1, "a caller inside the failure window ran the board"

        # after the window: exactly one retry
        now[0] += 1.0
        await cold_burst(8)
        assert db.n == 2, "after the window the board ran %d times, not once more" % (db.n - 1)

        # recovery: a working statement after the next window caches for the TTL
        now[0] += fail_ttl + 0.5
        ok = _WorkingBoard()
        assert await main._pc_board_ranks(ok, **binds) == {"p1": 1}
        now[0] += main._PC_STANDINGS_TTL_S - 1
        assert await main._pc_board_ranks(ok, **binds) == {"p1": 1}
        assert ok.n == 1
    run(go())


# ── the build discriminator: /health's binder_standings ──────────────────────

def test_s12_health_answers_binder_standings_1_on_both_arms(monkeypatch):
    """The release train's discriminator for this build: the collection route
    needs a signed request on every build, so an unsigned probe answers alike
    old and new, and only this word tells them apart. Required in the schema,
    passed once in each arm of health_check, a code constant so the degraded
    arm answers it with no database, and on the wire of a sessionless,
    versionless GET, as the train reads it.
    """
    import ast
    import pathlib
    import pydantic
    from fastapi.testclient import TestClient
    sys.path.insert(0, HERE)
    import read_gate_testkit as K
    import schemas
    import test_health_read_gate_marker as H

    field = schemas.HealthResponse.model_fields.get("binder_standings")
    assert field is not None and field.annotation is int and field.is_required(), field

    tree = ast.parse(pathlib.Path(main.__file__).read_text(encoding="utf-8"))
    health = [n for n in tree.body
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    assert len(health) == 1
    tries = [n for n in ast.walk(health[0]) if isinstance(n, ast.Try)]
    ok_arm = {id(n) for s in tries[0].body for n in ast.walk(s)}
    degraded = {id(n) for h in tries[0].handlers for n in ast.walk(h)}
    kws = [k for k in ast.walk(health[0])
           if isinstance(k, ast.keyword) and k.arg == "binder_standings"]
    assert len(kws) == 2 and sum(id(k) in ok_arm for k in kws) == 1 \
        and sum(id(k) in degraded for k in kws) == 1, len(kws)

    K.reset_gate()
    try:
        up, down = H._health("off")
        assert up["binder_standings"] == 1, up
        assert down["binder_standings"] == 1, down
        # required: an answer without it does not validate
        down.pop("binder_standings")
        with pytest.raises(pydantic.ValidationError):
            schemas.HealthResponse(**down)
    finally:
        K.reset_gate()

    with K.gate_env(monkeypatch, mode=None) as (stub, _clock):
        stub.fail.add("mode")

        async def _db():
            yield H._Down()
        monkeypatch.setitem(main.app.dependency_overrides, main.get_db, _db)
        r = TestClient(main.app, raise_server_exceptions=False).get("/api/v1/health")
        assert r.status_code == 200, r.text
        assert r.json().get("binder_standings") == 1, r.json()


# ── the gate's own guard, always outside it ──────────────────────────────────

def test_the_live_test_count_is_what_this_module_claims():
    """A module gated on an environment variable reports "N skipped, exit 0"
    when the variable is missing or misspelled, and that reads as a clean run
    in any summary that counts pass/fail rather than collected tests. This
    counts the gated tests from outside the gate, so moving one behind it (or
    forgetting to gate a new one) is a deliberate edit rather than a silent
    change in what a green run means (#720).
    """
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    marked = len(re.findall(r"^@needs_pg$", src, re.M))
    assert marked == LIVE_TESTS, (
        "%d tests carry @needs_pg but LIVE_TESTS says %d" % (marked, LIVE_TESTS))
    # ...and the gate is a skipif on the DSN, never on a truthiness that a
    # missing variable satisfies
    assert 'DSN = os.environ.get(DSN_VAR)' in src
    assert 'DSN_VAR = "BINDER_SORT_TEST_PG_DSN"' in src
