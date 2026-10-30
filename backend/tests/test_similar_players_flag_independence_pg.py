"""GET /api/v1/players/{steam_id}/similar answers the same with or without
review flags (small docket item c).

Required behaviour: the public answer must not depend on whether any player
carries a review flag. A flagged player is pooled, scored and listed exactly
as an unflagged player with the same record, and a flag on the requested
player changes nothing either. The pool used to leave out every player with
an undismissed suspected_macro flag (pending or confirmed), so the list
changed when such a flag was filed.

Live PostgreSQL. players, matches, match_cards and flagged_matches are built
from the models (columns and types, no foreign keys) in one throwaway schema
for the module, seeded once; every test starts with no flag row. The route
function itself, main.get_similar_players, runs on a session whose
search_path is that schema.

Seed: the requested player TARGET; twins ALPHA and BRAVO with the same record
(the same players-row counters, twelve ranked games each against TARGET with
the same damage, duration and card); CHARLIE with a different record. Every
case reads the whole answer (ids, names, scores) at limits 10 and 2 before any
flag exists, files the case's flag rows, and reads it again:

  pending      an unreviewed suspected_macro flag naming ALPHA
  confirmed    the same flag reviewed as confirmed_cheat
  legacy key   a pending flag naming BRAVO under the legacy reporter_steam key
  dismissed    a flag naming ALPHA reviewed as false_positive
  everyone     a pending flag naming each of the four, TARGET included

Mutation controls (#391): the shipped function with the old exclusion put
back at its old site (compiled from the shipped source, only that clause
added) must turn every case the old rule acted on red, dropping exactly the
players it named, and an inert twin of the clause at the same site must keep
every case green.

SIMILAR_TEST_PG_DSN names a throwaway database (postgresql:// or the
postgresql+asyncpg:// form); unset, every executed case FAILS rather than
skips (#342), and SIMILAR_TEST_PG_OPTOUT=1 makes that a named skip.
"""

import ast
import asyncio
import datetime as dt
import inspect
import json
import os
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "api"))
sys.path.insert(0, str(HERE))

import main  # noqa: E402
import models  # noqa: E402
from test_admin_evidence_cells_pg import _required_defaults  # noqa: E402

try:
    import asyncpg  # noqa: F401
except ImportError:                                    # pragma: no cover
    asyncpg = None

DSN_VAR = "SIMILAR_TEST_PG_DSN"
OPTOUT_VAR = "SIMILAR_TEST_PG_OPTOUT"
_RAW = os.environ.get(DSN_VAR) or ""
PLAIN_DSN = _RAW.replace("postgresql+asyncpg://", "postgresql://")
ASYNC_DSN = PLAIN_DSN.replace("postgresql://", "postgresql+asyncpg://", 1)
OPTOUT = str(os.environ.get(OPTOUT_VAR) or "").strip().lower() in {"1", "true", "yes", "on"}

TABLES = (models.Player.__table__, models.Match.__table__,
          models.MatchCard.__table__, models.FlaggedMatch.__table__)
PLAYER_REQUIRED = _required_defaults(models.Player.__table__)
MATCH_REQUIRED = _required_defaults(models.Match.__table__)
CARD_REQUIRED = _required_defaults(models.MatchCard.__table__)
FLAG_REQUIRED = _required_defaults(models.FlaggedMatch.__table__)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
GAMES = 12                    # each candidate's ranked games; the pool floor is 10
LIMITS = (10, 2)

# Test-only steam ids and names.
TARGET, ALPHA, BRAVO, CHARLIE = "sim-target", "sim-alpha", "sim-bravo", "sim-charlie"
NAMES = {TARGET: "Target", ALPHA: "Alpha", BRAVO: "Bravo", CHARLIE: "Charlie"}

# Per player: the players-row counters (hit %, block %, keys/sec), the damage
# dealt in each 100 s ranked game, and the one card picked in each game
# ("Tank" is a Health build, "Spray" an Other one).
TWIN = dict(bullets_fired=1000, bullets_hit=400, blocks_activated=200,
            blocks_successful=100, keys_pressed_total=6000, active_seconds_total=1200.0)
RECORDS = {
    TARGET: (dict(TWIN, bullets_hit=420, blocks_successful=110, keys_pressed_total=5400),
             480, "Tank"),
    ALPHA: (dict(TWIN), 500, "Tank"),
    BRAVO: (dict(TWIN), 500, "Tank"),
    CHARLIE: (dict(TWIN, bullets_hit=150, blocks_successful=30, keys_pressed_total=12000),
              900, "Spray"),
}

# case -> the flag rows it files: (subject, attribution key, review_action)
CASES = {
    "pending": [(ALPHA, "suspect_steam", None)],
    "confirmed": [(ALPHA, "suspect_steam", "confirmed_cheat")],
    "legacy key": [(BRAVO, "reporter_steam", None)],
    "dismissed": [(ALPHA, "suspect_steam", "false_positive")],
    "everyone": [(s, "suspect_steam", None) for s in (TARGET, ALPHA, BRAVO, CHARLIE)],
}
# who the old exclusion left out in each case (it skipped dismissed flags,
# and the requested player was never in the pool)
OLD_RULE_DROPS = {
    "pending": {ALPHA},
    "confirmed": {ALPHA},
    "legacy key": {BRAVO},
    "dismissed": set(),
    "everyone": {ALPHA, BRAVO, CHARLIE},
}

# The exclusion the pool carried before this item, verbatim, and the one line
# of the pool it followed.
SITE = "AND c.ranked_matches >= 10"
OLD_EXCLUSION = """
           AND NOT EXISTS (
               SELECT 1 FROM flagged_matches fm
                WHERE fm.flag_reason = 'suspected_macro'
                  AND COALESCE(fm.flag_details->>'suspect_steam',
                               fm.flag_details->>'reporter_steam') = p.steam_id
                  AND fm.review_action IS DISTINCT FROM 'false_positive'%s)"""


def _route_def():
    src = textwrap.dedent(inspect.getsource(main.get_similar_players))
    fn = ast.parse(src).body[0]
    assert isinstance(fn, ast.AsyncFunctionDef) and fn.name == "get_similar_players"
    return fn


def variant(tail):
    """The shipped route function with the old exclusion (ending in `tail`)
    added after SITE; nothing else differs."""
    fn = _route_def()
    fn.decorator_list = []
    sites = [n for n in ast.walk(fn) if isinstance(n, ast.Constant)
             and isinstance(n.value, str) and SITE in n.value]
    assert len(sites) == 1 and sites[0].value.count(SITE) == 1, len(sites)
    sites[0].value = sites[0].value.replace(SITE, SITE + OLD_EXCLUSION % tail)
    ns = dict(vars(main))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<similar variant>", "exec"), ns)
    return ns["get_similar_players"]


def _require_live_pg():
    if PLAIN_DSN and asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the similar-players answer was deliberately "
                    "not read from PostgreSQL" % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s is unset (or asyncpg is missing), so the similar-players route was "
                "never executed; point it at a throwaway database, or set %s=1 to "
                "waive the coverage deliberately" % (DSN_VAR, OPTOUT_VAR))


class Rig:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.schema = "sim_flags_%s" % uuid.uuid4().hex[:10]
        self.ids = {}
        self.first_game = {}
        self.engine = self.conn = self.reader = None

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    async def up(self):
        from sqlalchemy import text
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.schema import CreateTable
        self.engine = create_async_engine(ASYNC_DSN)
        self.conn = await self.engine.connect()
        await self.conn.execute(text('CREATE SCHEMA "%s"' % self.schema))
        await self.conn.execute(text('SET search_path TO "%s"' % self.schema))
        dialect = postgresql.dialect()
        for table in TABLES:
            await self.conn.execute(text(str(
                CreateTable(table, include_foreign_key_constraints=[]).compile(dialect=dialect))))
        await self._seed()
        await self.conn.commit()
        # The route's sessions: their own engine, every connection on the schema.
        self.reader = create_async_engine(
            ASYNC_DSN, connect_args={"server_settings": {"search_path": self.schema}})

    async def down(self):
        from sqlalchemy import text
        try:
            if self.reader is not None:
                await self.reader.dispose()
            if self.conn is not None:
                await self.conn.rollback()
                await self.conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % self.schema))
                await self.conn.commit()
        finally:
            if self.conn is not None:
                await self.conn.close()
            if self.engine is not None:
                await self.engine.dispose()

    async def _insert(self, table, rows):
        """One INSERT for every row (rows of one table share their columns)."""
        from sqlalchemy import text
        names = sorted(rows[0])
        assert all(sorted(r) == names for r in rows), table
        vals = ", ".join("CAST(:%s AS jsonb)" % n if n == "flag_details" else ":%s" % n
                         for n in names)
        await self.conn.execute(text("INSERT INTO %s (%s) VALUES (%s)"
                                     % (table, ", ".join(names), vals)), rows)

    async def _seed(self):
        players, games, cards = [], [], []
        for steam, (counters, _dmg, _card) in RECORDS.items():
            self.ids[steam] = uuid.uuid4()
            players.append(dict(PLAYER_REQUIRED, id=self.ids[steam], steam_id=steam,
                                display_name=NAMES[steam], **counters))
        _c, t_dmg, t_card = RECORDS[TARGET]
        for steam in (ALPHA, BRAVO, CHARLIE):
            _c, dmg, card = RECORDS[steam]
            for i in range(GAMES):
                mid = uuid.uuid4()
                self.first_game.setdefault(steam, (mid, [steam, TARGET]))
                ended = T0 + dt.timedelta(minutes=10 * i)
                games.append(dict(
                    MATCH_REQUIRED, id=mid, player1_id=self.ids[steam],
                    player2_id=self.ids[TARGET], photon_room_id="sim-%s-%d" % (steam, i),
                    is_ranked=True, ended_at=ended, created_at=ended, duration_seconds=100,
                    p1_damage_dealt=dmg, p2_damage_dealt=t_dmg))
                for who, name in ((steam, card), (TARGET, t_card)):
                    cards.append(dict(
                        CARD_REQUIRED, id=uuid.uuid4(), match_id=mid, player_id=self.ids[who],
                        card_name=name, pick_order=1, round_number=1))
        self.first_game[TARGET] = self.first_game[ALPHA]
        await self._insert("players", players)
        await self._insert("matches", games)
        await self._insert("match_cards", cards)

    async def flag(self, subject, key, action):
        mid, pair = self.first_game[subject]
        await self._insert("flagged_matches", [dict(
            FLAG_REQUIRED, id=uuid.uuid4(), match_id=mid, player_steam_ids=pair,
            flag_reason="suspected_macro", flag_details=json.dumps({key: subject}),
            created_at=T0 + dt.timedelta(days=1),
            reviewed_at=(T0 + dt.timedelta(days=2)) if action else None,
            review_action=action)])
        await self.conn.commit()

    async def clear_flags(self):
        from sqlalchemy import text
        await self.conn.rollback()          # whatever an earlier failed case left open
        await self.conn.execute(text("DELETE FROM flagged_matches"))
        await self.conn.commit()

    async def answer(self, fn, limit):
        """The route's whole answer as (steam id, name, score) rows."""
        from sqlalchemy.ext.asyncio import AsyncSession
        async with AsyncSession(self.reader) as db:
            got = await fn(TARGET, limit=limit, db=db)
        return tuple(zip(got.steam_ids, got.display_names, got.similarity_scores))


@pytest.fixture(scope="module")
def seeded():
    """The schema and its seed, built once: the DDL is the slow part."""
    _require_live_pg()
    r = Rig()
    try:
        r.run(r.up())
        yield r
    finally:
        try:
            r.run(r.down())
        finally:
            r.loop.close()


@pytest.fixture()
def rig(seeded):
    """The seeded schema with no flag row (a case only ever adds flags)."""
    seeded.run(seeded.clear_flags())
    return seeded


async def _before_and_after(rig, case, fns):
    """Each function's answer at every limit, before and after the case's flags."""
    async def read():
        return {name: {lim: await rig.answer(fn, lim) for lim in LIMITS}
                for name, fn in fns.items()}
    before = await read()
    for subject, key, action in CASES[case]:
        await rig.flag(subject, key, action)
    return before, await read()


def _differences(before, after):
    return ["limit %d: %r became %r" % (lim, before[lim], after[lim])
            for lim in LIMITS if after[lim] != before[lim]]


def _as_designed(answer):
    """The seed reads as designed: the twins listed alike, ahead of CHARLIE."""
    full, top2 = answer[10], answer[2]
    assert [row[0] for row in full] == [ALPHA, BRAVO, CHARLIE], full
    assert [row[1] for row in full] == ["Alpha", "Bravo", "Charlie"], full
    assert full[0][2] == full[1][2] > full[2][2], full
    assert top2 == full[:2], (top2, full)


def test_the_route_reads_no_flag_table():
    fn = _route_def()
    sql = [n.args[0].value for n in ast.walk(fn)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "text"
           and n.args and isinstance(n.args[0], ast.Constant)
           and isinstance(n.args[0].value, str)]
    # the pool, the DPS aggregate and the card aggregate (the docstring's
    # three-query design); a fourth read is a new place a flag could enter
    assert len(sql) == 3, len(sql)
    assert [s for s in sql if "flagged_matches" in s.lower()] == []
    assert "FlaggedMatch" not in {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}


@pytest.mark.parametrize("case", list(CASES))
def test_a_flag_changes_nothing_in_the_answer(rig, case):
    before, after = rig.run(_before_and_after(rig, case, {"shipped": main.get_similar_players}))
    _as_designed(before["shipped"])
    assert _differences(before["shipped"], after["shipped"]) == []
    # so a flagged twin is still listed exactly as the unflagged one
    _as_designed(after["shipped"])


@pytest.mark.parametrize("case", list(CASES))
def test_the_old_exclusion_turns_the_check_red_and_its_inert_twin_does_not(rig, case):
    fns = {"shipped": main.get_similar_players,
           "old exclusion": variant(""),
           "inert twin": variant(" AND false")}
    before, after = rig.run(_before_and_after(rig, case, fns))
    # with no flag filed, both variants answer exactly as the shipped function
    assert before["old exclusion"] == before["shipped"]
    assert before["inert twin"] == before["shipped"]
    red = _differences(before["shipped"], after["old exclusion"])
    assert bool(red) == bool(OLD_RULE_DROPS[case]), (case, red)
    listed = {row[0] for row in after["old exclusion"][10]}
    assert listed == {ALPHA, BRAVO, CHARLIE} - OLD_RULE_DROPS[case], (case, listed)
    assert _differences(before["shipped"], after["inert twin"]) == []
