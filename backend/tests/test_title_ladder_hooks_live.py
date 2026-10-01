"""The ladder hook, DRIVEN: the three ranked game-reporting paths through their
real handlers, against a real PostgreSQL built from the migrations.

test_title_ladders.py proves from the parse tree that main.py calls the hook
once per ranked game-reporting path, awaited, with the right reference. This
file proves what those calls DO, per site. The unit is the GAME (board row
29, the title ladders build): every ranked game credits each player once,
keyed by that game's own row id, so a 1v1 or 2v2 series of two games credits
two. The bar, from LADDER-HOOK-DESIGN-LITE-V3 sections 3, 4 and 12.5 with the
unit moved from the series to the game:

  H3  one game delivered twice is credited once. 1v1's second delivery of a
      report dies at the match insert's flush on unique_match with nothing
      written; 2v2's is the duplicate echo; FFA's is refused by the room gate
      -- the replay echo -- with no second ffa_matches row. The after-the-fact
      2v2 settlement (admin completion, lead forfeit) plays no game and
      credits nothing, whichever path completed the series.
  H5  a DATABASE fault inside the hook's call -- the real hook runs, then a
      failing statement -- costs the completion nothing. The same completion
      runs twice, clean and faulted, each in a fresh schema: the result,
      ratings, XP, gold and items match, the faulted run holds no credit and
      no ladder change anywhere, and it printed exactly one
      `[LADDER-CREDIT] ... dropped` line. The control removes only the
      savepoint around the call -- the handler's own source, compiled without
      that one `async with` -- and the same fault then loses the whole
      completion (#235/#536).
  H6  what a game wrote reads back through main.app's own GET, on a session
      of its own: +1 on the worn line per game.
  H8  every must-not-count line leaves no credit and no progress change:
      1v1 casual after the downgrade, an anti-cheat-invalidated match, a
      closed bracket room and the abandoned idle series; 2v2 a roster, room
      or partition mismatch and a series that is not active; every 2v2
      settlement (admin completion, lead forfeit, the helper's missing-row,
      completed and unfilled-slot returns -- that slot's NOT NULL relaxed in
      the throwaway schema alone, 053_2v2_schema.sql makes all four NOT NULL
      -- an admin void and a disconnect that is not a clear forfeit); FFA a
      casual lobby, the refusals before the insert (lobby not active, score
      shape, game number), a failed insert and a failed strict skew refund.
      FFA's ghost and grace controls are read per game in the game-keyed test
      below.

Beside the three sites: the FFA game-keyed test (two games of one lobby
credit each rated player per game; a ghost or a graced leaver gets nothing
for the game it did not play), and three of Codex round 2's LOW residual
sentences (design 12.6) made tests, re-read for the game unit: R1 (a fault
in game 1 costs game 1's credit and nothing else; game 2 credits its own),
R3 (the 1v1 credit stands when the rating pass fails or skips, and causes
nothing else) and Q-G (the resent deciding 1v1 report answers 500 through
main.app and writes nothing -- behaviour documented as it stands, not
changed here).

Every H3 and H8 case also records each call main.py makes to the hook, the
real hook still doing the work (the hook_calls fixture), and asserts it: a
must-not-count line must never REACH the hook (design 4.1), a counted one
reaches it exactly once, with its mode, its reference and every participant,
and the one line that reaches it and is then rolled back -- the failed strict
skew refund -- is told apart from a line that never got there.

THE SCHEMA. Every case builds its own, in a throwaway schema through
ladder_pg_harness: every connection bound to it at connect, a census before
anything is created or dropped. The DDL of every numbered migration but the
ladder catalogue files (331, 365) and the refund (366, a production-census
data migration) is replayed -- statements that create or alter a table, index, function, trigger,
type or sequence, and DO blocks that do; no data statement, no extension, and
nothing that names a session's temporary schema (backfill helpers) -- then the
ORM's create_all makes the tables no migration creates, the mapped tables are
widened to every column the models map, and the DDL is replayed again now that
the tables it alters exist. That second pass may fail only with an
already-exists code or on one of REPLAY_KNOWN, statements on tables none of
the three paths touch; anything else fails the case. Migrations 331 and 365
then run whole, as written, in that order, and the tables and the five-tier
rungs are confirmed. A case that needs a
schema change of its own makes it next, and only then is the build sealed.

There is no defaults fill here, unlike test_title_ladders' ORM-only listing
schema: the replayed tables carry production's own defaults, and a default
given here to a NOT NULL column that production leaves without one would turn
a production NOT NULL failure into a pass. Rows a fixture writes into an
ORM-made table get explicit values for such columns instead (_insert).

The handlers run with MATCH_HMAC_SECRET cleared -- the module's own "no secret
configured" path -- and the Steam session check replaced, as
test_ffa_game_number_anchor.py drives submit_ffa_match; neither is what this
file is about. The one exception is the lead-forfeit test's two signed
live-points posts (the comment above _live_points_sig). Every observation is
made on a connection of its own, never on the session that ran the write.

Live PostgreSQL is REQUIRED, and a missing DSN FAILS, naming the variable --
the gate test_title_ladders.py's live half uses:
    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately
"""

import ast
import asyncio
import contextlib
import glob
import hashlib
import hmac
import io
import os
import re
import sys
import types
import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
import title_ladders as tl  # noqa: E402
from test_title_ladders import MAIN_PY, MIGRATION, MIGRATION_365  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402

try:
    import asyncpg as _asyncpg
except ImportError:                                    # pragma: no cover
    _asyncpg = None

DSN_VAR = "LADDER_TEST_PG_DSN"
OPTOUT_VAR = "LADDER_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

SQL_DIR = os.path.join(HERE, "..", "sql")
HOOK = "record_completed_games"
MODES = ("1v1", "2v2", "ffa")
# Games per completion _complete plays: a 1v1 or 2v2 series of two, one FFA game.
GAMES = {"1v1": 2, "2v2": 2, "ffa": 1}
# Run whole after the replay, never replayed: the ladder catalogue files. 366
# is not run at all -- it refunds a production census and refuses elsewhere.
NOT_REPLAYED = {os.path.basename(MIGRATION), os.path.basename(MIGRATION_365),
                "366_title_refunds_voidshot_kingslayer.sql"}

# Synthetic ids below 76561197960265728, the first individual-account id, so
# none of them can name a real account.
P1, P2, P3, P4 = ("76561190000000401", "76561190000000402",
                  "76561190000000403", "76561190000000404")
BYSTANDER = "76561190000000405"     # wears a rung, plays in nothing
OUTSIDER = "76561190000000406"      # wears nothing, for the roster control

LINES = [ld["line"] for ld in tl.LADDERS]


def _entry_sku(line):
    return tl.rungs_at_tier(line, 1)[0]["sku"]


def _tier2_threshold(line):
    return tl.next_rung(line, 1)["threshold"]


# P1 sits one game below its line's second rung, so a credit that lands
# moves a real rung -- a grant, an ownership row and an auto-equip --
# and not only a counter.
WEAR = {
    P1: (LINES[0], _tier2_threshold(LINES[0]) - 1),
    P2: (LINES[1], 3),
    P3: (LINES[2], 3),
    P4: (LINES[3], 3),
    BYSTANDER: (LINES[0], 5),
}


def _require_live_pg():
    """Fail, not skip: a skipped live case reports exit 0 for coverage that
    did not run."""
    if DSN and _asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: the driven-hook coverage is "
                    "deliberately waived." % (DSN_VAR, OPTOUT_VAR))
    if _asyncpg is None:
        pytest.fail("asyncpg is not installed, so no completion path was driven "
                    "against a real server. Install it, or set %s=1 to waive "
                    "deliberately." % OPTOUT_VAR)
    pytest.fail(
        "%s is unset, so none of the four completion paths was driven through "
        "its real handler against migration 331's tables. Point it at a "
        "throwaway database, or set %s=1 to waive the coverage deliberately."
        % (DSN_VAR, OPTOUT_VAR))


def _run(coro):
    return asyncio.run(coro)


# -- the schema ---------------------------------------------------------------

_TOKEN = re.compile(
    r"(?P<line>--[^\n]*)"
    r"|(?P<block>/\*.*?\*/)"
    r"|(?P<str>'(?:[^']|'')*')"
    r"|(?P<ident>\"(?:[^\"]|\"\")*\")"
    r"|(?P<dq0>\$\$.*?\$\$)"
    r"|(?P<dq>\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\$.*?\$(?P=tag)\$)"
    r"|(?P<semi>;)",
    re.S)


def _split_sql(sql):
    """Statements, split on the semicolons that end them: not inside a quoted
    string or identifier, a dollar-quoted body or a comment."""
    out, buf, pos = [], [], 0
    for m in _TOKEN.finditer(sql):
        buf.append(sql[pos:m.start()])
        if m.group("line") is not None or m.group("block") is not None:
            buf.append(" ")
        elif m.group("semi") is not None:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
        else:
            buf.append(m.group(0))
        pos = m.end()
    buf.append(sql[pos:])
    s = "".join(buf).strip()
    if s:
        out.append(s)
    return out


_DDL_HEAD = re.compile(
    r"^(CREATE\s+(?:UNIQUE\s+)?INDEX|DROP\s+INDEX|CREATE\s+TABLE|ALTER\s+TABLE"
    r"|CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION|CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER"
    r"|DROP\s+TRIGGER|CREATE\s+TYPE|CREATE\s+SEQUENCE)\b", re.I)
_DO_DDL = re.compile(r"\b(ALTER\s+TABLE|CREATE\s+(?:UNIQUE\s+)?INDEX|CREATE\s+TABLE"
                     r"|ADD\s+COLUMN)\b", re.I)

# Codes the second pass answers because the first one (or the ORM) already
# made the object: duplicate table/relation, object, column, schema, function.
_ALREADY = {"42P07", "42710", "42701", "42P06", "42723"}
# The second pass's other failures, each on a table none of the four paths
# touches: the card_stats unique indexes (card_stats is made by neither a
# migration's DDL nor the ORM), the bug_reports numbering sequence (made by a
# data statement), and a VALIDATE of a constraint whose ADD sits in a
# statement the replay does not select.
REPLAY_KNOWN = {
    ("001_schema.sql", "42P01"),
    ("013_dedup_poison_and_card_stats_index.sql", "42P01"),
    ("086_bug_report_number.sql", "42P01"),
    ("279_clavar_and_hardening.sql", "42704"),
}


def _ddl_statements():
    out = []
    for path in sorted(glob.glob(os.path.join(SQL_DIR, "*.sql"))):
        name = os.path.basename(path)
        if not re.match(r"^\d{3}_", name) or name in NOT_REPLAYED:
            continue
        for s in _split_sql(io.open(path, encoding="utf-8").read()):
            head = s.lstrip()
            if re.search(r"\bpg_temp\.", s):
                continue
            if _DDL_HEAD.match(head) or (re.match(r"^DO\b", head, re.I)
                                         and _DO_DDL.search(head)):
                s = re.sub(r"\buuid_generate_v4\(\)", "gen_random_uuid()", s)
                s = re.sub(r"\s+CONCURRENTLY\b", "", s, flags=re.I)
                out.append((name, s))
    return out


async def _replay(conn, statements):
    """Run each statement on its own; return (file, sqlstate, message) for
    every one the server refused."""
    failed = []
    for name, s in statements:
        try:
            await conn.execute(s)
        except _asyncpg.PostgresError as e:
            failed.append((name, e.sqlstate, str(e).split("\n")[0][:200]))
    return failed


async def _widen(conn, schema):
    """Every column a model maps, on the table it maps it to: added nullable
    and default-free where the replayed DDL did not make it."""
    dialect = postgresql.dialect()
    for table in models.Base.metadata.sorted_tables:
        have = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            " WHERE table_schema = $1 AND table_name = $2", schema, table.name)}
        for col in table.columns:
            if col.name not in have:
                await conn.execute('ALTER TABLE %s."%s" ADD COLUMN "%s" %s' % (
                    harness.quoted(schema), table.name, col.name,
                    col.type.compile(dialect=dialect)))


async def _build(case, extra_ddl=None):
    """Into case.schema, on case.conn (bound to it): replay, ORM, widen,
    replay, 331 then 365 run and confirmed, the case's own change, sealed."""
    conn, schema = case.conn, case.schema
    statements = _ddl_statements()
    await _replay(conn, statements)      # the ORM's tables are not there yet
    engine = harness.bound_engine(DSN, schema)
    try:
        async with engine.begin() as c:
            await c.run_sync(models.Base.metadata.create_all)
    finally:
        await engine.dispose()
    await _widen(conn, schema)
    second = await _replay(conn, statements)
    unexpected = [f for f in second
                  if f[1] not in _ALREADY and (f[0], f[1]) not in REPLAY_KNOWN]
    assert not unexpected, (
        "the second DDL pass failed on statements outside REPLAY_KNOWN: %r"
        % unexpected[:5])
    await conn.execute(io.open(MIGRATION, encoding="utf-8").read())
    await conn.execute(io.open(MIGRATION_365, encoding="utf-8").read())
    rungs = await conn.fetchval("SELECT count(*) FROM title_ladders")
    items = await conn.fetchval(
        "SELECT count(*) FROM shop_items WHERE sku = ANY($1::text[])", list(tl.ALL_SKUS))
    tables = [await conn.fetchval("SELECT to_regclass($1)::text", t)
              for t in ("title_ladder_credits", "title_ladder_progress")]
    assert rungs == items == len(tl.ALL_SKUS) and None not in tables, (
        "331 and 365 did not land: %d rungs, %d shop rows, tables %r" % (rungs, items, tables))
    if extra_ddl is not None:
        await extra_ddl(conn, schema)
    await case.seal()


@contextlib.asynccontextmanager
async def _case(extra_ddl=None):
    """A built, sealed case schema and a session factory bound to it."""
    async with harness.CaseSchema(DSN, "ladder_hooks") as case:
        await _build(case, extra_ddl)
        engine = harness.bound_engine(DSN, case.schema)
        try:
            yield case.schema, async_sessionmaker(engine, expire_on_commit=False)
        finally:
            await engine.dispose()


# -- fixtures -----------------------------------------------------------------

async def _insert(db, table, values):
    """INSERT one row, giving every NOT NULL column that has no default and
    is not in `values` a plain value of its type. Test data for a table the
    ORM made, never a schema change."""
    missing = (await db.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        " WHERE table_schema = current_schema() AND table_name = :t "
        "   AND is_nullable = 'NO' AND column_default IS NULL"), {"t": table})).all()
    row = dict(values)
    for col, dtype in missing:
        if col in row:
            continue
        if dtype.startswith("timestamp") or dtype == "date":
            row[col] = None
        elif dtype == "boolean":
            row[col] = False
        elif dtype in ("integer", "bigint", "smallint", "numeric", "double precision", "real"):
            row[col] = 0
        elif dtype == "uuid":
            row[col] = uuid.uuid4()
        elif dtype in ("json", "jsonb"):
            row[col] = "{}"
        elif dtype == "ARRAY":
            row[col] = []
        else:
            row[col] = "lh"
    cols = sorted(row)
    exprs = []
    for c in cols:
        if row[c] is None:
            exprs.append("NOW()")
        else:
            exprs.append(":" + c)
    params = {c: row[c] for c in cols if row[c] is not None}
    return (await db.execute(text(
        'INSERT INTO "%s" (%s) VALUES (%s) RETURNING *' % (
            table, ", ".join('"%s"' % c for c in cols), ", ".join(exprs))),
        params)).mappings().one()


async def _seed(sm, wear=None, plain=(OUTSIDER,)):
    """The players, created through main.get_or_create_player as a first
    report or registration creates them -- the player row AND its initial
    1v1 rating row, without which submit_match's rating pass has nothing to
    update and skips -- each in `wear` wearing the first rung of a line it
    owns, at a recorded count. Returns {steam: player id}."""
    wear = WEAR if wear is None else wear
    ids = {}
    async with sm() as db:
        for steam in list(wear) + [s for s in plain if s not in wear]:
            ids[steam] = (await main.get_or_create_player(db, steam, "Ladder " + steam[-3:])).id
        for steam, (line, games) in wear.items():
            item = (await db.execute(text("SELECT id FROM shop_items WHERE sku = :s"),
                                     {"s": _entry_sku(line)})).scalar_one()
            await db.execute(text(
                "INSERT INTO player_items (player_id, item_id, purchase_price) "
                "VALUES (:p, :i, 0)"), {"p": ids[steam], "i": item})
            await db.execute(text("UPDATE players SET active_title_id = :i WHERE id = :p"),
                             {"i": item, "p": ids[steam]})
            await db.execute(text(
                "INSERT INTO title_ladder_progress (player_id, line, games, tier) "
                "VALUES (:p, :l, :g, 1)"), {"p": ids[steam], "l": line, "g": games})
        await db.commit()
    return ids


class _NoHeaders(dict):
    def get(self, k, d=None):
        return d


class _FakeRequest:
    """Only what the handlers read off a request once the session check is
    replaced."""
    headers = _NoHeaders()
    client = None
    url = "http://ladder.test/"

    def __init__(self):
        self.state = types.SimpleNamespace()


@pytest.fixture
def opened(monkeypatch):
    """The signature and session checks out of the way (module docstring),
    and an internal key for the admin route. Returns that key."""
    async def _no_session_check(request, steam_id, db):
        return None
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    monkeypatch.setattr(main, "_check_steam_session", _no_session_check)
    key = "ladder-hooks-" + uuid.uuid4().hex
    monkeypatch.setenv("API_SECRET_KEY", key)
    return key


@pytest.fixture
def hook_calls(monkeypatch):
    """Every call main.py makes to the hook, as (mode, reference id, number of
    players), the real hook still doing the work -- so a control can tell
    "never reached the hook" (design 4.1) from "reached it, and the claim
    was rolled back"."""
    real = tl.record_completed_games
    calls = []

    async def _spy(db, player_ids, *, mode, reference_id, rows=None):
        player_ids = list(player_ids)
        calls.append((mode, str(reference_id), len(player_ids)))
        return await real(db, player_ids, mode=mode, reference_id=reference_id, rows=rows)
    monkeypatch.setattr(tl, HOOK, _spy)
    return calls


async def _call(fn, *args, **kwargs):
    """Await one handler call; return (answer, exception, printed lines)."""
    buf = io.StringIO()
    answer = exc = None
    with contextlib.redirect_stdout(buf):
        try:
            answer = await fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 -- the caller asserts on it
            exc = e
    return answer, exc, buf.getvalue().splitlines()


def _dropped(lines, mode):
    return [ln for ln in lines if ln.startswith("[LADDER-CREDIT] %s credit dropped" % mode)]


# -- the four completion paths ------------------------------------------------

def _pd(steam):
    return schemas.PlayerMatchData(steam_id=steam, display_name="Ladder " + steam[-3:])


def _report_1v1(room, *, a=P1, b=P2, a_wins=True, ranked=True, duration=300):
    return schemas.MatchReport(
        player1=_pd(a), player2=_pd(b),
        p1_rounds_won=5 if a_wins else 2, p2_rounds_won=2 if a_wins else 5,
        photon_room_id=room, is_ranked=ranked, reported_by_steam_id=a,
        match_duration=duration)


def _report_2v2(sid, room, roster=(P1, P2, P3, P4), *, winner_team=1):
    t1a, t1b, t2a, t2b = roster
    return schemas.TeamMatchReport(
        series_id=str(sid), photon_room_id=room, is_ranked=True,
        t1_rounds_won=5 if winner_team == 1 else 1,
        t2_rounds_won=1 if winner_team == 1 else 5, winner_team=winner_team,
        reported_by_steam_id=t1a, t1a=_pd(t1a), t1b=_pd(t1b), t2a=_pd(t2a), t2b=_pd(t2b))


def _entry(steam, slot, rounds, points, *, left=False, absent=False, gp=None):
    return schemas.FfaPlayerEntry(
        steam_id=steam, slot=slot, rounds_won=rounds, points_total=points,
        left_early=left, absent=absent, game_points_at_leave=gp)


def _report_ffa(lobby, room, entries, winner):
    return schemas.FfaMatchReport(
        lobby_id=str(lobby), photon_room_id=room, winner_steam_id=winner,
        reported_by_steam_id=winner, is_ranked=True, players=entries)


def _ffa_game(members=(P1, P2, P3, P4)):
    """A complete four-seat game won by the first member at the default
    target, everyone present."""
    tallies = [(5, 10), (3, 6), (2, 4), (1, 2)]
    return [_entry(s, i, r, p) for i, (s, (r, p)) in enumerate(zip(members, tallies))]


async def _team_series(sm, ids, room, roster=(P1, P2, P3, P4), status="active"):
    sid = uuid.uuid4()
    async with sm() as db:
        await db.execute(text(
            "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, status, "
            "                         photon_room_id) "
            "VALUES (:i, :a, :b, :c, :d, :st, :r)"),
            {"i": sid, "a": ids[roster[0]], "b": ids[roster[1]], "c": ids[roster[2]],
             "d": ids[roster[3]], "st": status, "r": room})
        await db.commit()
    return sid


async def _ffa_lobby(sm, ids, members=(P1, P2, P3, P4), *, ranked=True,
                     status="active", score_target=None):
    lid = uuid.uuid4()
    async with sm() as db:
        await db.execute(text(
            "INSERT INTO ffa_lobbies (id, status, player_count, member_ids, games_played, "
            "                         created_at, is_ranked) "
            "VALUES (:i, :st, :n, CAST(:m AS uuid[]), 0, NOW() - interval '10 minutes', :rk)"),
            {"i": lid, "st": status, "n": len(members),
             "m": [str(ids[s]) for s in members], "rk": ranked})
        if score_target is not None:
            await db.execute(text("UPDATE ffa_lobbies SET score_target = :t WHERE id = :i"),
                             {"t": score_target, "i": lid})
        await db.commit()
    return lid


async def _submit(sm, fn, *args):
    async with sm() as db:
        return await _call(fn, *args, _FakeRequest(), db)


async def _admin(sm, key, sid, action, winner_team=None):
    async with sm() as db:
        return await _call(main.admin_resolve_team_series, series_id=str(sid),
                           action=action, winner_team=winner_team, x_internal_key=key,
                           admin_steam_id=None, hmac_signature=None, db=db)


async def _team_dc(sm, sid, reporter, dc_player, t1_points, t2_points, room):
    async with sm() as db:
        # A direct call gets no FastAPI resolution: an omitted is_fallback would be
        # its Query(False) default object, which is truthy, and the handler would
        # take the 2v2 fallback deferral. This report is a real one (886bed8 LAND).
        return await _call(main.team_series_report_dc, series_id=str(sid),
                           reporter_steam_id=reporter, dc_player_steam_id=dc_player,
                           t1_points_total=t1_points, t2_points_total=t2_points,
                           photon_room_id=room, is_fallback=False,
                           hmac_sig="unsigned", db=db)


async def _ranked_series_id(sm, ids, a=P1, b=P2):
    async with sm() as db:
        return (await db.execute(text(
            "SELECT id FROM ranked_series WHERE (player1_id = :a AND player2_id = :b) "
            "   OR (player1_id = :b AND player2_id = :a) ORDER BY created_at DESC LIMIT 1"),
            {"a": ids[a], "b": ids[b]})).scalar_one()


async def _complete(mode, sm, ids, key, tag, submit=None):
    """One rated completion of `mode`, through its real handler(s): a 1v1 or
    2v2 series of GAMES[mode] games, or one FFA game. `submit` replaces the
    handler (the no-savepoint control). Returns (the game ids a credit is
    keyed by, one per game that answered one, participants, answers, printed
    lines)."""
    answers, lines = [], []

    def keep(res):
        answers.append(res)
        lines.extend(res[2])
        return res
    if mode == "1v1":
        fn = submit or main.submit_match
        for g in (1, 2):
            keep(await _submit(sm, fn, _report_1v1("ranked_lh%s_00000%d_r%d" % (tag, g, g))))
        return _game_refs(answers), [P1, P2], answers, lines
    if mode == "2v2":
        fn = submit or main.submit_team_match
        sid = await _team_series(sm, ids, "team_lh%s" % tag)
        for g in (1, 2):
            keep(await _submit(sm, fn, _report_2v2(sid, "team_lh%s_00000%d_r%d" % (tag, g, g))))
        return _game_refs(answers), [P1, P2, P3, P4], answers, lines
    fn = submit or main.submit_ffa_match
    lid = await _ffa_lobby(sm, ids)
    keep(await _submit(sm, fn, _report_ffa(lid, "ffa_lh%s_r1" % tag, _ffa_game(), P1)))
    return _game_refs(answers), [P1, P2, P3, P4], answers, lines


def _game_refs(answers):
    """The game id each answered report recorded -- the credit key."""
    return [str(a.match_id) for a, exc, _l in answers if exc is None and a is not None]


# -- observation, on connections of their own ---------------------------------

async def _ladder(conn):
    progress = {(r["steam_id"], r["line"]): (r["games"], r["tier"]) for r in await conn.fetch(
        "SELECT p.steam_id, t.line, t.games, t.tier FROM title_ladder_progress t "
        "  JOIN players p ON p.id = t.player_id")}
    credits = sorted((r["steam_id"], r["reference_id"], r["line"], r["mode"])
                     for r in await conn.fetch(
        "SELECT p.steam_id, c.reference_id, c.line, c.mode FROM title_ladder_credits c "
        "  JOIN players p ON p.id = c.player_id"))
    worn = {r["steam_id"]: r["sku"] for r in await conn.fetch(
        "SELECT p.steam_id, si.sku FROM players p "
        "  LEFT JOIN shop_items si ON si.id = p.active_title_id")}
    rungs = sorted((r["steam_id"], r["sku"]) for r in await conn.fetch(
        "SELECT p.steam_id, si.sku FROM player_items pi "
        "  JOIN players p ON p.id = pi.player_id JOIN shop_items si ON si.id = pi.item_id "
        " WHERE si.sku = ANY($1::text[])", list(tl.ALL_SKUS)))
    return {"progress": progress, "credits": credits, "worn": worn, "rungs": rungs}


def _rounded(rows, places):
    """Rows as tuples, floats rounded to `places`, sorted on a key that puts
    NULL apart from every value -- an unrated player's rating_change is NULL
    beside a rated one's float."""
    out = [tuple(round(v, places) if isinstance(v, float) else v for v in r) for r in rows]
    return sorted(out, key=lambda t: tuple((v is None, 0 if v is None else v) for v in t))


async def _economy(conn):
    """Everything a completion writes that is not ladder state, keyed by
    steam id so two schemas' runs compare."""
    out = {
        "gold": sorted(tuple(r) for r in await conn.fetch(
            "SELECT p.steam_id, g.reason, g.amount FROM gold_transactions g "
            "  JOIN players p ON p.id = g.player_id")),
        "xp": sorted(tuple(r) for r in await conn.fetch(
            "SELECT steam_id, total_xp FROM players")),
        "items": sorted(tuple(r) for r in await conn.fetch(
            "SELECT p.steam_id, si.sku FROM player_items pi "
            "  JOIN players p ON p.id = pi.player_id JOIN shop_items si ON si.id = pi.item_id "
            " WHERE NOT (si.sku = ANY($1::text[]))", list(tl.ALL_SKUS))),
        "achievements": await conn.fetchval("SELECT count(*) FROM player_achievements"),
        "rating_history": await conn.fetchval("SELECT count(*) FROM rating_history"),
        "matches": sorted(tuple(r) for r in await conn.fetch(
            "SELECT a.steam_id, b.steam_id, m.p1_rounds_won, m.p2_rounds_won, m.is_ranked, "
            "       m.invalidated_at IS NOT NULL "
            "  FROM matches m JOIN players a ON a.id = m.player1_id "
            "  JOIN players b ON b.id = m.player2_id")),
        "ranked_series": sorted(tuple(r) for r in await conn.fetch(
            "SELECT rs.status, rs.p1_series_wins, rs.p2_series_wins, w.steam_id "
            "  FROM ranked_series rs LEFT JOIN players w ON w.id = rs.winner_id")),
        "team_matches": await conn.fetchval("SELECT count(*) FROM team_matches"),
        "team_series": sorted(tuple(r) for r in await conn.fetch(
            "SELECT status, t1_series_wins, t2_series_wins, winner_team FROM team_series")),
        "ffa_matches": await conn.fetchval("SELECT count(*) FROM ffa_matches"),
        "ffa_match_players": _rounded(await conn.fetch(
            "SELECT p.steam_id, f.placement, f.rating_change, f.xp_gained, f.gold_gained, "
            "       f.absent FROM ffa_match_players f JOIN players p ON p.id = f.player_id"), 6),
        "ffa_lobbies": sorted(tuple(r) for r in await conn.fetch(
            "SELECT status, games_played FROM ffa_lobbies")),
    }
    for table in ("glicko_ratings", "glicko_ratings_2v2", "glicko_ratings_ffa"):
        out[table] = _rounded(await conn.fetch(
            "SELECT p.steam_id, g.rating, g.rating_deviation, g.volatility "
            "  FROM %s g JOIN players p ON p.id = g.player_id" % table), 6)
    return out


async def _look(schema):
    conn = await harness.connect_bound(DSN, schema)
    try:
        return await _ladder(conn), await _economy(conn)
    finally:
        await conn.close()


async def _get_ladders(schema, steams):
    """GET each player's ladders from main.app, each request on a session of
    its own bound to `schema`. Returns {steam: (status, body)}."""
    engine = harness.bound_engine(DSN, schema)
    session = async_sessionmaker(engine, expire_on_commit=False)

    async def _db():
        async with session() as db:
            yield db
    out = {}
    main.app.dependency_overrides[database.get_db] = _db
    try:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://ladder.test") as c:
            for steam in steams:
                r = await c.get("/api/v1/players/%s/title-ladders" % steam,
                                headers={"X-Mod-Version": main.MIN_MOD_VERSION_EFFECTIVE})
                out[steam] = (r.status_code, r.json())
    finally:
        main.app.dependency_overrides.pop(database.get_db, None)
        await engine.dispose()
    return out


def _worn_games(body):
    """(active line, games on it) from a GET answer."""
    line = body["active_line"]
    return line, next(ld["games"] for ld in body["ladders"] if ld["line"] == line)


def _plus_n(before, after, steams, n):
    """The progress rows `after` holds, for `steams`, when each moved by
    exactly `n` on its worn line and nothing else moved anywhere."""
    want = dict(before["progress"])
    for s in steams:
        line = WEAR[s][0]
        games, tier = want[(s, line)]
        want[(s, line)] = (games + n, tl.tier_for_games(line, games + n))
    return after["progress"] == want, want


def _plus_one(before, after, steams):
    return _plus_n(before, after, steams, 1)


def _credited(after, ref, mode, steams):
    return [c for c in after["credits"] if c[1] == ref] == sorted(
        (s, ref, WEAR[s][0], mode) for s in steams)


# -- H3 / H6 / H8 per site ----------------------------------------------------

def test_pg_1v1_a_series_of_two_games_credits_two(opened, hook_calls):
    """1v1, H3 + H6, and the brief's series-to-games test: ONE series of TWO
    games credits each player TWO, not one. Game 1 (mid-series) reaches the
    hook for both players keyed by its own match id and credits each +1 --
    P1 across its second rung (granted, owned, worn); game 2 completes the
    series and credits each +1 again under ITS id; both GETs read +2; the
    deciding report sent again dies at the flush on unique_match, before the
    hook, with nothing written; the bystander never moves.

    Negative control (recorded in the build notes): main.py's 1v1 call keyed
    by str(series.id) again turns this red -- the second game's claim
    collides with the first and each player reads +1."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            g1 = await _submit(sm, main.submit_match, _report_1v1("ranked_lhA_000001_r1"))
            assert g1[1] is None and g1[0].series_status == "active", g1
            m1 = str(g1[0].match_id)
            assert hook_calls == [("1v1", m1, 2)], ("game 1 did not reach the hook once",
                                                    hook_calls)
            mid, _ = await _look(schema)
            ok, want = _plus_one(seeded, mid, [P1, P2])
            assert ok, ("H3: after game 1, mid-series", mid["progress"], want)
            p1_line = WEAR[P1][0]
            top = tl.rungs_at_tier(p1_line, 2)[0]["sku"]
            assert mid["worn"][P1] == top and (P1, top) in mid["rungs"], (
                "the crossing credit did not grant and equip the second rung",
                mid["worn"][P1], mid["rungs"])
            deciding = _report_1v1("ranked_lhA_000002_r2")
            g2 = await _submit(sm, main.submit_match, deciding)
            assert g2[1] is None and g2[0].series_status == "completed", g2
            m2 = str(g2[0].match_id)
            assert m2 != m1 and hook_calls == [("1v1", m1, 2), ("1v1", m2, 2)], hook_calls
            done, econ = await _look(schema)
            ok, want = _plus_n(seeded, done, [P1, P2], 2)
            assert ok, ("series-to-games: one series of two games must credit two",
                        done["progress"], want)
            assert _credited(done, m1, "1v1", [P1, P2]), done["credits"]
            assert _credited(done, m2, "1v1", [P1, P2]), done["credits"]
            assert len(done["credits"]) == 4, done["credits"]
            rated = {r[0]: r[1] for r in econ["glicko_ratings"]}
            assert econ["rating_history"] == 2 and rated[P1] > rated[P2], (
                "the series' rating pass did not run", econ["rating_history"], rated)
            read = await _get_ladders(schema, [P1, P2])
            for s in (P1, P2):
                status, body = read[s]
                assert status == 200, (s, status)
                assert _worn_games(body) == (WEAR[s][0], WEAR[s][1] + 2), (
                    "H6: the GET after the series", s, _worn_games(body))
            again = await _submit(sm, main.submit_match, deciding)
            assert isinstance(again[1], IntegrityError) and "unique_match" in str(again[1]), (
                "H3: the resent deciding report did not die on unique_match", again[1])
            after, econ2 = await _look(schema)
            assert after == done and econ2 == econ, (
                "H3: the resent deciding report wrote something")
            assert len(hook_calls) == 2, (
                "H3: the resent deciding report reached the hook", hook_calls)
            assert not _dropped(g1[2] + g2[2], "1v1")
    _run(_go())


def test_pg_1v1_casual_after_the_downgrade_credits_nothing(opened, hook_calls):
    """1v1, H8: a report claiming ranked, from a room that is not the mod's,
    between players one of whom has ranked disabled, is downgraded to casual
    before the series logic -- two such wins complete nothing and credit
    nothing."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            async with sm() as db:
                await db.execute(text("UPDATE players SET ranked_enabled = FALSE WHERE id = :p"),
                                 {"p": ids[P2]})
                await db.commit()
            seeded, _ = await _look(schema)
            for g in (1, 2):
                res = await _submit(sm, main.submit_match,
                                    _report_1v1("quick_lhB_00000%d_r%d" % (g, g)))
                assert res[1] is None, res
                assert any("downgraded to casual" in ln for ln in res[2]), res[2]
            after, econ = await _look(schema)
            assert after == seeded, "H8: a downgraded casual 1v1 moved the ladder"
            assert hook_calls == [], hook_calls
            assert econ["ranked_series"] == [] and len(econ["matches"]) == 2, econ["matches"]
            assert not any(m[4] for m in econ["matches"]), econ["matches"]
    _run(_go())


def test_pg_1v1_anticheat_invalidated_match_credits_nothing(opened, hook_calls):
    """1v1, H8: a second sub-minute ranked game of the pair is invalidated by
    the anti-cheat and returns before the hook; the series never completes.
    The FIRST game was a valid ranked game and credits +1; the invalidated
    one credits nothing and never reaches the hook."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            await _seed(sm)
            seeded, _ = await _look(schema)
            first = await _submit(sm, main.submit_match,
                                  _report_1v1("ranked_lhC_000001_r1", duration=20))
            assert first[1] is None and first[0].series_status == "active", first
            m1 = str(first[0].match_id)
            after1, _ = await _look(schema)
            second = await _submit(sm, main.submit_match,
                                   _report_1v1("ranked_lhC_000002_r2", duration=20))
            assert second[1] is None and second[0].series_status == "invalidated", second
            after, econ = await _look(schema)
            ok, want = _plus_one(seeded, after1, [P1, P2])
            assert ok, ("the valid first game did not credit", after1["progress"], want)
            assert after == after1, "H8: an invalidated 1v1 match moved the ladder"
            assert hook_calls == [("1v1", m1, 2)], hook_calls
            assert not any(s[0] == "completed" for s in econ["ranked_series"]), econ
    _run(_go())


def test_pg_1v1_closed_bracket_room_credits_nothing(opened, hook_calls):
    """1v1, H8: a report from the room of a bracket match that is already
    completed is refused 409 before anything records."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            await _seed(sm)
            async with sm() as db:
                tour = await _insert(db, "tournaments", {})
                await _insert(db, "tournament_matches", {
                    "tournament_id": tour["id"], "round": 1, "slot_idx": 0,
                    "status": "completed", "photon_room_name": "sct-lhclosed"})
                await db.commit()
            seeded, econ0 = await _look(schema)
            for g in (1, 2):
                res = await _submit(sm, main.submit_match,
                                    _report_1v1("sct-lhclosed_00000%d_r%d" % (g, g)))
                assert getattr(res[1], "status_code", None) == 409, res
            after, econ = await _look(schema)
            assert after == seeded and econ == econ0, (
                "H8: a report from a closed bracket room wrote something")
            assert hook_calls == [], hook_calls
    _run(_go())


def test_pg_1v1_abandoned_idle_series_credits_nothing(opened, hook_calls):
    """1v1, H8: the prune's abandon of a ranked series that never recorded a
    match writes 'abandoned' and applies nothing."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            async with sm() as db:
                row = await _insert(db, "ranked_series", {
                    "player1_id": ids[P1], "player2_id": ids[P2], "status": "active"})
                await db.execute(text(
                    "UPDATE ranked_series SET created_at = NOW() - interval '40 minutes' "
                    " WHERE id = :i"), {"i": row["id"]})
                await db.commit()
            seeded, _ = await _look(schema)
            async with sm() as db:
                changed, exc, _lines = await _call(main._prune_stale_series, db)
            assert exc is None and changed == 1, (changed, exc)
            after, econ = await _look(schema)
            assert econ["ranked_series"] == [("abandoned", 0, 0, None)], econ["ranked_series"]
            assert after == seeded, "H8: the abandon of an idle series moved the ladder"
            assert hook_calls == [], hook_calls
    _run(_go())


def test_pg_2v2_credits_every_game_once_and_reads_back(opened, hook_calls):
    """2v2, H3 + H6 + H8. Game 1 credits all four once, keyed by its own
    team_matches id; a report naming an outsider, one from another room and
    one with the teams split differently are each refused and credit
    nothing; game 2 completes the series and credits all four again under
    its id; the GETs read +2; the deciding report sent again is the
    duplicate echo; a report on the completed series is refused."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            sid = await _team_series(sm, ids, "team_lhD")
            g1 = await _submit(sm, main.submit_team_match,
                               _report_2v2(sid, "team_lhD_000001_r1"))
            assert g1[1] is None and g1[0].series_status == "active", g1
            m1 = str(g1[0].match_id)
            assert hook_calls == [("2v2", m1, 4)], hook_calls
            after1, _ = await _look(schema)
            refused = [
                ("roster", _report_2v2(sid, "team_lhD_000002_r2", (P1, P2, P3, OUTSIDER))),
                ("room", _report_2v2(sid, "team_elsewhere_000002_r2")),
                ("partition", _report_2v2(sid, "team_lhD_000002_r2", (P1, P3, P2, P4))),
            ]
            for label, rep in refused:
                res = await _submit(sm, main.submit_team_match, rep)
                assert getattr(res[1], "status_code", None) in (400, 403), (label, res)
            mid, _ = await _look(schema)
            ok, want = _plus_one(seeded, mid, [P1, P2, P3, P4])
            assert ok, ("H3: after game 1", mid["progress"], want)
            assert mid == after1, "H8: a refused 2v2 report moved the ladder"
            assert hook_calls == [("2v2", m1, 4)], (
                "H8: a refused 2v2 report reached the hook", hook_calls)
            deciding = _report_2v2(sid, "team_lhD_000002_r2")
            g2 = await _submit(sm, main.submit_team_match, deciding)
            assert g2[1] is None and g2[0].series_status == "completed", g2
            m2 = str(g2[0].match_id)
            assert hook_calls == [("2v2", m1, 4), ("2v2", m2, 4)], hook_calls
            done, econ = await _look(schema)
            ok, want = _plus_n(seeded, done, [P1, P2, P3, P4], 2)
            assert ok, ("H3/H6: after the series of two games", done["progress"], want)
            assert _credited(done, m1, "2v2", [P1, P2, P3, P4]), done["credits"]
            assert _credited(done, m2, "2v2", [P1, P2, P3, P4]), done["credits"]
            read = await _get_ladders(schema, [P1, P2, P3, P4])
            for s in (P1, P2, P3, P4):
                assert read[s][0] == 200, (s, read[s][0])
                assert _worn_games(read[s][1]) == (WEAR[s][0], WEAR[s][1] + 2), (
                    "H6", s, _worn_games(read[s][1]))
            again = await _submit(sm, main.submit_team_match, deciding)
            assert again[1] is None and "duplicate" in again[0].message, again
            late = await _submit(sm, main.submit_team_match,
                                 _report_2v2(sid, "team_lhD_000003_r3"))
            assert getattr(late[1], "status_code", None) == 400, late
            after, econ2 = await _look(schema)
            assert after == done and econ2 == econ, (
                "H3/H8: the duplicate or the late report wrote something")
            assert len(hook_calls) == 2, (
                "H3/H8: the duplicate or the late report reached the hook", hook_calls)
    _run(_go())


def test_pg_2v2_settled_admin_completion_credits_nothing(opened, hook_calls):
    """2v2 settlement, H8. The admin completion completes the series and
    rates it, but plays no game: it never reaches the hook and nothing is
    credited; the GETs read the seeded counts; the same completion asked
    again is the route's noop, the helper called again on the completed
    series returns before anything, and a report on the series the helper
    completed is refused -- none of them credits."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            sid = await _team_series(sm, ids, "team_lhE")
            res = await _admin(sm, opened, sid, "complete", 1)
            assert res[1] is None and res[0]["status"] == "completed", res
            assert hook_calls == [], hook_calls
            done, econ = await _look(schema)
            assert done == seeded, ("H8: the admin completion moved the ladder",
                                    done["progress"])
            assert econ["glicko_ratings_2v2"], "the admin completion rated nobody"
            read = await _get_ladders(schema, [P1, P2, P3, P4])
            for s in (P1, P2, P3, P4):
                assert _worn_games(read[s][1]) == (WEAR[s][0], WEAR[s][1]), (
                    "H6", s, read[s])
            noop = await _admin(sm, opened, sid, "complete", 1)
            assert noop[1] is None and noop[0]["status"] == "noop", noop
            async with sm() as db:
                direct = await _call(main._complete_team_series_with_ratings, db, sid, 1,
                                     "ladder-hooks-probe")
                await db.commit()
            assert direct[1] is None and direct[0] == {}, direct
            late = await _submit(sm, main.submit_team_match,
                                 _report_2v2(sid, "team_lhE_000001_r1"))
            assert getattr(late[1], "status_code", None) == 400, late
            after, econ2 = await _look(schema)
            assert after == done and econ2 == econ, (
                "H3/H8: a repeat of the settled completion wrote something")
            assert hook_calls == [], (
                "H3/H8: a repeat of the settled completion reached the hook", hook_calls)
    _run(_go())


# The per-game record a 2v2 lead forfeit is settled from. Since the lead-forfeit
# hotfix (migrations 348, 351 and 352), team_series_report_dc settles a lead
# forfeit from team_series_games -- the record update_team_live_points writes
# during play -- and never from the DC report's own point snapshot: the
# abandoned game counts as played only when the posts that count for it show a
# pair of two points or more from a seat of EACH team, and in any game but the
# first of the original sitting only the posts that named exactly that game and
# sitting count (_team_game_crossed_two). A report on a series with no such
# record parks the series as dc_incomplete for an admin, by design.
# The lead-forfeit test therefore writes that record the way a client does: one
# attested post naming game 2 of the stored sitting from a seat of each team.
# Those two posts are signed, so for them alone the secret is set and the seat
# gate answers unbound, as the hotfix's own tests post; every other handler
# call in this file runs with MATCH_HMAC_SECRET cleared (module docstring).
_LIVE_POINTS_SECRET = "ladder-hooks-live-points"


def _live_points_sig(sid, reporter, t1, t2, game, room):
    msg = "team-live-points-game:%s:%s:%s:%s:%s:%s" % (sid, reporter, t1, t2, game, room)
    return hmac.new(_LIVE_POINTS_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


async def _unbound_seat(request, steam_id, db):
    return main.SEAT_UNBOUND


async def _lead_forfeit_series(monkeypatch, sm, ids, posters):
    """Team 1 wins game 1 of a team_lhF series through submit_team_match; then
    each seat in `posters` posts the pair 1-1 for game 2 of the stored sitting,
    naming it (attested). Returns the series id."""
    sid = await _team_series(sm, ids, "team_lhF")
    g1 = await _submit(sm, main.submit_team_match,
                       _report_2v2(sid, "team_lhF_000001_r1"))
    assert g1[1] is None and g1[0].series_status == "active", g1
    if posters:
        monkeypatch.setattr(main, "MATCH_HMAC_SECRET", _LIVE_POINTS_SECRET)
        monkeypatch.setattr(main, "_seat_gate_for_live_points", _unbound_seat)
        for reporter in posters:
            async with sm() as db:
                post = await _call(main.update_team_live_points, series_id=str(sid),
                                   request=None, t1_points=1, t2_points=1,
                                   reporter_steam_id=reporter,
                                   sig=_live_points_sig(str(sid), reporter, 1, 1, 2,
                                                        "team_lhF"),
                                   game_number=2, photon_room_id="team_lhF", db=db)
            assert post[1] is None and post[0]["status"] == "ok", post
        monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    return sid


def test_pg_2v2_settled_lead_forfeit_credits_only_the_game_played(opened, hook_calls,
                                                                  monkeypatch):
    """2v2 settlement through the helper's other caller: team 1 wins game 1
    through submit_team_match -- one credit per player, keyed by that game --
    then a team-2 disconnect in game 2 whose per-game record shows the pair
    from a seat of each team is a lead forfeit and completes the series
    through the helper, which plays no game and credits nothing more; the
    same report again is ignored. Two controls come first, the same steps
    each on a schema of its own: with no per-game record, and with team 1's
    post alone, the same report parks the series as dc_incomplete and the
    ladder holds game 1's credit alone (the comment above
    _live_points_sig)."""
    _require_live_pg()

    async def _control(posters):
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            sid = await _lead_forfeit_series(monkeypatch, sm, ids, posters)
            game1, _ = await _look(schema)
            calls = list(hook_calls)
            dc = await _team_dc(sm, sid, P1, P3, 2, 1, "team_lhF_000002_r2")
            assert dc[1] is None and dc[0]["status"] == "dc_incomplete", (posters, dc)
            assert hook_calls == calls and [c[0] for c in calls] == ["2v2"], (
                posters, hook_calls)
            after, _ = await _look(schema)
            ok, want = _plus_one(seeded, after, [P1, P2, P3, P4])
            assert ok and after == game1, ("the parked DC moved the ladder", posters,
                                           after["progress"], want)
            del hook_calls[:]

    async def _go():
        await _control(())
        await _control((P1,))
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            sid = await _lead_forfeit_series(monkeypatch, sm, ids, (P1, P3))
            assert [(c[0], c[2]) for c in hook_calls] == [("2v2", 4)], hook_calls
            m1 = hook_calls[0][1]
            dc = await _team_dc(sm, sid, P1, P3, 2, 1, "team_lhF_000002_r2")
            assert dc[1] is None and dc[0].get("reason") == "dc_leadforfeit", dc
            assert len(hook_calls) == 1, ("the lead forfeit reached the hook", hook_calls)
            done, econ = await _look(schema)
            ok, want = _plus_one(seeded, done, [P1, P2, P3, P4])
            assert ok, ("H8: the lead forfeit credited more than game 1",
                        done["progress"], want)
            assert _credited(done, m1, "2v2", [P1, P2, P3, P4]), done["credits"]
            assert len(done["credits"]) == 4, done["credits"]
            assert [s[0] for s in econ["team_series"]] == ["completed"], econ["team_series"]
            again = await _team_dc(sm, sid, P1, P3, 2, 1, "team_lhF_000002_r2")
            assert again[1] is None and again[0].get("ignored") is True, again
            after, econ2 = await _look(schema)
            assert after == done and econ2 == econ, "H3: the repeated DC report wrote something"
            assert len(hook_calls) == 1, hook_calls
    _run(_go())


def test_pg_2v2_settled_returns_void_and_unclear_forfeit_credit_nothing(opened, hook_calls):
    """2v2-settled, H8: the helper on a series id with no row returns before
    anything; an admin void cancels with no result; a disconnect in a level
    series with no points is not a clear forfeit and parks the series for an
    admin. None of them credits."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            async with sm() as db:
                missing = await _call(main._complete_team_series_with_ratings, db,
                                      uuid.uuid4(), 1, "ladder-hooks-probe")
                await db.commit()
            assert missing[1] is None and missing[0] == {}, missing
            void_sid = await _team_series(sm, ids, "team_lhG")
            void = await _admin(sm, opened, void_sid, "void")
            assert void[1] is None and void[0]["status"] == "voided", void
            dc_sid = await _team_series(sm, ids, "team_lhH")
            dc = await _team_dc(sm, dc_sid, P1, P3, 0, 0, "team_lhH_000001_r1")
            assert dc[1] is None and dc[0]["status"] == "dc_incomplete", dc
            after, econ = await _look(schema)
            assert after == seeded, "H8: a settlement return, void or unclear DC moved the ladder"
            assert hook_calls == [], hook_calls
            assert sorted(s[0] for s in econ["team_series"]) == ["cancelled", "dc_incomplete"], (
                econ["team_series"])
    _run(_go())


async def _relax_t2b(conn, schema):
    await conn.execute("ALTER TABLE %s.team_series ALTER COLUMN t2b_id DROP NOT NULL"
                       % harness.quoted(schema))


def test_pg_2v2_settled_unfilled_slot_credits_nothing(opened, hook_calls):
    """2v2-settled, H8: the helper's unfilled-slot return. Unreachable on the
    real schema -- all four slot columns are NOT NULL (053_2v2_schema.sql) --
    so this case's schema, and only this case's, relaxes one of them: the
    series completes with no ratings and nothing is credited."""
    _require_live_pg()

    async def _go():
        async with _case(extra_ddl=_relax_t2b) as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            sid = uuid.uuid4()
            async with sm() as db:
                await db.execute(text(
                    "INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, status, "
                    "                         photon_room_id) "
                    "VALUES (:i, :a, :b, :c, NULL, 'active', 'team_lhI')"),
                    {"i": sid, "a": ids[P1], "b": ids[P2], "c": ids[P3]})
                await db.commit()
            async with sm() as db:
                res = await _call(main._complete_team_series_with_ratings, db, sid, 1,
                                  "ladder-hooks-probe")
                await db.commit()
            assert res[1] is None and res[0] == {}, res
            after, econ = await _look(schema)
            assert econ["team_series"] == [("completed", 0, 0, 1)], econ["team_series"]
            assert econ["glicko_ratings_2v2"] == [], econ["glicko_ratings_2v2"]
            assert after == seeded, "H8: the unfilled-slot return moved the ladder"
            assert hook_calls == [], hook_calls
    _run(_go())


def test_pg_either_2v2_path_after_the_other_adds_nothing(opened, hook_calls):
    """2v2, H3 across the two paths: a series completed by its two reported
    games credits each player once per game and is then the admin route's
    noop; a series completed by the admin route credits nothing and refuses
    the report. Two series, two games played, eight credits."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            by_reports = await _team_series(sm, ids, "team_lhJ")
            games = []
            for g in (1, 2):
                res = await _submit(sm, main.submit_team_match,
                                    _report_2v2(by_reports, "team_lhJ_00000%d_r%d" % (g, g)))
                assert res[1] is None, res
                games.append(str(res[0].match_id))
            noop = await _admin(sm, opened, by_reports, "complete", 1)
            assert noop[0]["status"] == "noop", noop
            by_admin = await _team_series(sm, ids, "team_lhK")
            res = await _admin(sm, opened, by_admin, "complete", 1)
            assert res[0]["status"] == "completed", res
            late = await _submit(sm, main.submit_team_match,
                                 _report_2v2(by_admin, "team_lhK_000001_r1"))
            assert getattr(late[1], "status_code", None) == 400, late
            after, _ = await _look(schema)
            four = [P1, P2, P3, P4]
            for m in games:
                assert _credited(after, m, "2v2", four), after["credits"]
            assert len(after["credits"]) == 8, after["credits"]
            assert hook_calls == [("2v2", m, 4) for m in games], hook_calls
            for s in four:
                line, games = WEAR[s]
                assert after["progress"][(s, line)][0] == games + 2, (s, after["progress"])
    _run(_go())


def test_pg_ffa_credits_once_per_game_and_reads_back(opened, hook_calls):
    """FFA, H3 + H6. The game credits every rated member once, keyed by the
    GAME's ffa_matches id; the GETs read +1; the same report again is
    refused by the room gate -- the replay echo -- with no second
    ffa_matches row and nothing else written."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            lid = await _ffa_lobby(sm, ids)
            report = _report_ffa(lid, "ffa_lhL_r1", _ffa_game(), P1)
            res = await _submit(sm, main.submit_ffa_match, report)
            assert res[1] is None, res
            m1 = str(res[0].match_id)
            assert hook_calls == [("ffa", m1, 4)], hook_calls
            done, econ = await _look(schema)
            ok, want = _plus_one(seeded, done, [P1, P2, P3, P4])
            assert ok, ("H3/H6: after the game", done["progress"], want)
            assert _credited(done, m1, "ffa", [P1, P2, P3, P4]), done["credits"]
            read = await _get_ladders(schema, [P1, P2, P3, P4])
            for s in (P1, P2, P3, P4):
                assert _worn_games(read[s][1]) == (WEAR[s][0], WEAR[s][1] + 1), (
                    "H6", s, read[s])
            again = await _submit(sm, main.submit_ffa_match, report)
            assert again[1] is None and again[0].match_id == res[0].match_id, (
                "H3: the resend was not the replay echo of the recorded game", again)
            after, econ2 = await _look(schema)
            assert econ2["ffa_matches"] == 1 and after == done and econ2 == econ, (
                "H3: the resend wrote something")
            assert hook_calls == [("ffa", m1, 4)], (
                "H3: the replay echo reached the hook", hook_calls)
    _run(_go())


def test_pg_ffa_casual_and_refused_reports_credit_nothing(opened, hook_calls):
    """FFA, H8: a casual lobby's game records and credits nothing; a report
    to a lobby that is not active, one whose winner does not hold a complete
    game's rounds, and one naming the wrong game number are each refused
    before the insert and credit nothing."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            casual = await _ffa_lobby(sm, ids, ranked=False)
            res = await _submit(sm, main.submit_ffa_match,
                                _report_ffa(casual, "ffa_lhM_r1", _ffa_game(), P1))
            assert res[1] is None, res
            closed = await _ffa_lobby(sm, ids, status="completed")
            short = await _ffa_lobby(sm, ids)
            short_game = _ffa_game()
            short_game[0] = _entry(P1, 0, 4, 8)
            numbered = await _ffa_lobby(sm, ids)
            for label, rep in (
                    ("not active", _report_ffa(closed, "ffa_lhN_r1", _ffa_game(), P1)),
                    ("score shape", _report_ffa(short, "ffa_lhO_r1", short_game, P1)),
                    ("game number", _report_ffa(numbered, "ffa_lhP_r3", _ffa_game(), P1))):
                refused = await _submit(sm, main.submit_ffa_match, rep)
                assert refused[1] is not None and refused[1].status_code >= 400, (label, refused)
            after, econ = await _look(schema)
            assert after == seeded, "H8: a casual or refused FFA report moved the ladder"
            assert hook_calls == [], hook_calls
            assert econ["ffa_matches"] == 1, econ["ffa_matches"]
    _run(_go())


_FAILING_INSERT = """
CREATE FUNCTION {schema}.ladder_hooks_refuse_ffa_insert() RETURNS trigger
LANGUAGE plpgsql AS $f$
BEGIN
    RAISE EXCEPTION 'ladder hooks: ffa_matches insert refused' USING ERRCODE = '{code}';
END $f$;
CREATE TRIGGER ladder_hooks_refuse_ffa_insert BEFORE INSERT ON {schema}.ffa_matches
    FOR EACH ROW EXECUTE FUNCTION {schema}.ladder_hooks_refuse_ffa_insert();
"""


@pytest.mark.parametrize("code,status", [("23505", 500), ("P0001", 503)])
def test_pg_ffa_failed_insert_credits_nothing(opened, hook_calls, code, status):
    """FFA, H8: the ffa_matches insert failing -- as a constraint violation
    (the IntegrityError branch) or as any other database error -- rolls the
    report back and answers the refusal; nothing is credited. The failure
    is a trigger this case's schema alone carries."""
    _require_live_pg()

    async def _refuse(conn, schema):
        await conn.execute(_FAILING_INSERT.format(schema=harness.quoted(schema), code=code))

    async def _go():
        async with _case(extra_ddl=_refuse) as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            lid = await _ffa_lobby(sm, ids)
            res = await _submit(sm, main.submit_ffa_match,
                                _report_ffa(lid, "ffa_lhQ_r1", _ffa_game(), P1))
            assert getattr(res[1], "status_code", None) == status, res
            after, econ = await _look(schema)
            assert after == seeded and econ["ffa_matches"] == 0, (
                "H8: a failed FFA insert moved the ladder")
            assert hook_calls == [], hook_calls
    _run(_go())


def test_pg_ffa_failed_skew_refund_takes_the_credit_back(opened, monkeypatch, hook_calls):
    """FFA, H8: a game played to the module default in a lobby that froze
    another target settles with a strict refund of that game's wagers, AFTER
    the hook has run; when the refund fails the refusal propagates, nothing
    commits, and the credit the hook claimed goes with it. The hook WAS
    reached -- once, for the four -- so the empty ladder is the rollback's
    doing, not a path that never got there."""
    _require_live_pg()
    calls = []

    async def _refund_fails(db, lobby_id, game_number, *a, **k):
        calls.append(game_number)
        raise RuntimeError("ladder hooks: strict refund refused")
    monkeypatch.setattr(main, "_refund_ffa_game_bets_strict", _refund_fails)

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            lid = await _ffa_lobby(sm, ids, score_target=7)
            res = await _submit(sm, main.submit_ffa_match,
                                _report_ffa(lid, "ffa_lhR_r1", _ffa_game(), P1))
            assert getattr(res[1], "status_code", None) == 503, res
            assert calls == [1], calls
            assert [(m, n) for m, _r, n in hook_calls] == [("ffa", 4)], hook_calls
            after, econ = await _look(schema)
            assert after == seeded and econ["ffa_matches"] == 0, (
                "H8: a rolled-back FFA settlement kept its credit")
    _run(_go())


# -- FFA: one credit per GAME (board row 29) ----------------------------------

# W, R and G each wear the first rung of a line at a recorded count; V and X
# wear nothing. X is the second lobby's third seat: a lobby forms at
# FFA_MIN_PLAYERS (three), so the new rated lobby with W and V is played
# three-handed.
W, V, R, G, X = ("76561190000000411", "76561190000000412", "76561190000000413",
                 "76561190000000414", "76561190000000415")
SITTING_WEAR = {W: (LINES[0], 3), R: (LINES[1], 3), G: (LINES[2], 3)}
NAME = {W: "W", V: "V", R: "R", G: "G", X: "X"}


def _sitting_game_1(lobby):
    """Game 1 of the lobby: W wins and V plays it out; R leaves with six
    field points on the board, late enough to be rated; G leaves at one,
    inside the grace (FFA_LEAVE_GRACE_POINTS), and is unrated."""
    return _report_ffa(lobby, "ffa_lhS_r1", [
        _entry(W, 0, 5, 10), _entry(V, 1, 3, 6),
        _entry(R, 2, 2, 4, left=True, gp=6),
        _entry(G, 3, 0, 0, left=True, gp=1)], W)


def _sitting_game_2(lobby):
    """Game 2, in a new room: W and V play; R and G ride the frozen roster
    as ghosts (left early, absent, nothing on the board)."""
    return _report_ffa(lobby, "ffa_lhT_r2", [
        _entry(W, 0, 5, 10), _entry(V, 1, 3, 6),
        _entry(R, 2, 0, 0, left=True, absent=True),
        _entry(G, 3, 0, 0, left=True, absent=True)], W)


async def _per_game(schema, lobbies):
    """What stays per game: each lobby's ffa_matches ids in game order, the
    FFA games each player has been rated in, and the ffa_placement gold rows
    as {reference id: sorted steam ids}."""
    conn = await harness.connect_bound(DSN, schema)
    try:
        matches = {}
        for lobby in lobbies:
            matches[str(lobby)] = [str(r["id"]) for r in await conn.fetch(
                "SELECT id FROM ffa_matches WHERE lobby_id = $1 ORDER BY game_number", lobby)]
        played = {r["steam_id"]: r["games_played"] for r in await conn.fetch(
            "SELECT p.steam_id, g.games_played FROM glicko_ratings_ffa g "
            "  JOIN players p ON p.id = g.player_id WHERE g.games_played > 0")}
        placed = {}
        for r in await conn.fetch(
                "SELECT g.reference_id, p.steam_id FROM gold_transactions g "
                "  JOIN players p ON p.id = g.player_id WHERE g.reason = 'ffa_placement'"):
            placed.setdefault(r["reference_id"], []).append(r["steam_id"])
        return matches, played, {k: sorted(v) for k, v in placed.items()}
    finally:
        await conn.close()


def _sitting_problems(when, look, got, games, refs):
    """Every way the ladder disagrees with `games` (worn-line count per
    wearer) and `refs` (credit references per player), as sentences."""
    out = []
    for s, (line, _start) in sorted(SITTING_WEAR.items()):
        have = look["progress"].get((s, line), (None, None))[0]
        if have != games[s]:
            out.append("%s: %s's worn line holds %s games, want %s"
                       % (when, NAME[s], have, games[s]))
        status, body = got[s]
        read = _worn_games(body) if status == 200 else ("HTTP", status)
        if read != (line, games[s]):
            out.append("%s: the GET reads %s's worn line as %r, want %r"
                       % (when, NAME[s], read, (line, games[s])))
    for s in sorted(refs):
        have = sorted(c[1] for c in look["credits"] if c[0] == s)
        if have != sorted(refs[s]):
            out.append("%s: %s holds %d credit(s) %r, want %r"
                       % (when, NAME[s], len(have), have, sorted(refs[s])))
    return out


def test_pg_ffa_credit_is_keyed_by_the_game(opened, hook_calls):
    """FFA per game (board row 29; the steps of design V3 section 12.3 with
    the unit moved from the lobby to the game).

    One rated lobby L, two games. Game 1 rates W, V and R -- R left late --
    and not G, who left inside the grace; game 2, in a new room, rates W and
    V while R and G ride as ghosts. Every write is per game: two ffa_matches
    rows, one FFA game per rated player per game (W and V twice, R once, G
    never), one ffa_placement gold row per rated player per game referencing
    THAT game's match id -- and now the ladder too: after game 1, W and R
    each hold one credit keyed by game 1's id and read +1 through the GET;
    after game 2, W holds a second keyed by game 2's id and reads +2, R --
    a ghost in game 2 -- still one, G none. Game 2 sent again is the replay
    echo and moves nothing. A new lobby gives W the next +1.

    The hook is reached by both games of L -- three players, then two. The
    mutation control, main.py's FFA call keyed by str(lobby_uuid) again (the
    series-unit build), must turn this red: the checks are collected and
    reported together, so the red run names W's single credit and the GET's
    +1 rather than stopping at the first difference."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm, SITTING_WEAR, plain=(V, X))
            seeded, _ = await _look(schema)
            start = {s: seeded["progress"][(s, line)][0]
                     for s, (line, _g) in SITTING_WEAR.items()}
            lobby = await _ffa_lobby(sm, ids, members=(W, V, R, G))
            L = str(lobby)
            problems = []

            # Game 1.
            g1 = await _submit(sm, main.submit_ffa_match, _sitting_game_1(lobby))
            assert g1[1] is None, g1
            assert any(ln.startswith("[FFA] early-leave grace for %s" % G) for ln in g1[2]), (
                "G's leave did not take the grace", g1[2])
            m1 = str(g1[0].match_id)
            matches, played, placed = await _per_game(schema, [lobby])
            assert matches == {L: [m1]}, ("game 1", matches)
            assert played == {W: 1, V: 1, R: 1}, ("game 1: FFA games", played)
            assert placed == {m1: sorted([W, V, R])}, ("game 1: placement gold", placed)
            assert hook_calls == [("ffa", m1, 3)], hook_calls
            after1, _ = await _look(schema)
            got1 = await _get_ladders(schema, [W, R, G])
            once = {W: start[W] + 1, R: start[R] + 1, G: start[G]}
            problems += _sitting_problems("after game 1", after1, got1, once,
                                          {W: [m1], V: [], R: [m1], G: []})

            # Game 2.
            game_2 = _sitting_game_2(lobby)
            g2 = await _submit(sm, main.submit_ffa_match, game_2)
            assert g2[1] is None, g2
            m2 = str(g2[0].match_id)
            assert m2 != m1, (m1, m2)
            matches, played, placed = await _per_game(schema, [lobby])
            assert matches == {L: [m1, m2]}, ("game 2", matches)
            assert played == {W: 2, V: 2, R: 1}, ("game 2: FFA games", played)
            assert placed == {m1: sorted([W, V, R]), m2: sorted([W, V])}, (
                "game 2: placement gold", placed)
            assert [(m, n) for m, _r, n in hook_calls] == [("ffa", 3), ("ffa", 2)], hook_calls
            after2, econ2 = await _look(schema)
            got2 = await _get_ladders(schema, [W, R, G])
            twice = {W: start[W] + 2, R: start[R] + 1, G: start[G]}
            problems += _sitting_problems("after game 2", after2, got2, twice,
                                          {W: [m1, m2], V: [], R: [m1], G: []})
            by_lobby = sorted(NAME[c[0]] for c in after2["credits"] if c[1] == L)
            if by_lobby:
                problems.append("after game 2: %d credit(s) keyed by the lobby, not a "
                                "game: %r" % (len(by_lobby), by_lobby))
            keys = [r for _m, r, _n in hook_calls]
            if keys != [m1, m2]:
                problems.append("the hook was called with %r, not the games %r"
                                % (keys, [m1, m2]))

            # Game 2 sent again is the replay echo.
            again = await _submit(sm, main.submit_ffa_match, game_2)
            assert again[1] is None and str(again[0].match_id) == m2, (
                "the resend was not the replay echo of game 2", again)
            after3, econ3 = await _look(schema)
            matches3, _played, _placed = await _per_game(schema, [lobby])
            assert matches3 == {L: [m1, m2]}, ("a third ffa_matches row", matches3)
            assert after3 == after2 and econ3 == econ2, "the replay echo moved something"
            assert len(hook_calls) == 2, ("the replay echo reached the hook", hook_calls)

            assert not problems, ("the games did not count once each:\n  "
                                  + "\n  ".join(problems))

            # The lobby ends; a new lobby's game is one more game.
            async with sm() as db:
                await db.execute(text(
                    "UPDATE ffa_lobbies SET status = 'completed', completed_at = NOW() "
                    " WHERE id = :i"), {"i": lobby})
                await db.commit()
            lobby2 = await _ffa_lobby(sm, ids, members=(W, V, X))
            g3 = await _submit(sm, main.submit_ffa_match,
                               _report_ffa(lobby2, "ffa_lhU_r1", _ffa_game((W, V, X)), W))
            assert g3[1] is None, g3
            m3 = str(g3[0].match_id)
            assert hook_calls[2:] == [("ffa", m3, 3)], hook_calls
            after4, _ = await _look(schema)
            got4 = await _get_ladders(schema, [W, R, G])
            thrice = {W: start[W] + 3, R: start[R] + 1, G: start[G]}
            late = _sitting_problems("after the second lobby", after4, got4, thrice,
                                     {W: [m1, m2, m3], V: [], R: [m1], G: [], X: []})
            assert not late, late
    _run(_go())


# -- H5: a database fault inside the hook call ------------------------------

def _faulting_hook(monkeypatch, *, only_first=False):
    """Replace the hook main.py calls with one that runs the REAL hook, counts
    the credit rows it wrote for this reference inside the transaction, then
    sends a statement the server refuses (division by zero). Returns the list
    those counts are appended to."""
    real = tl.record_completed_games
    wrote = []

    async def _hook(db, player_ids, *, mode, reference_id, rows=None):
        events = await real(db, player_ids, mode=mode, reference_id=reference_id, rows=rows)
        if only_first and wrote:
            return events
        wrote.append((await db.execute(text(
            "SELECT count(*) FROM title_ladder_credits WHERE reference_id = :r"),
            {"r": str(reference_id)})).scalar_one())
        await db.execute(text("SELECT 1 / 0"))
        return events
    monkeypatch.setattr(tl, HOOK, _hook)
    return wrote


async def _run_completion(mode, key, tag, submit=None):
    async with _case() as (schema, sm):
        ids = await _seed(sm)
        seeded, econ0 = await _look(schema)
        ref, who, answers, lines = await _complete(mode, sm, ids, key, tag, submit=submit)
        after, econ = await _look(schema)
        return dict(ref=ref, who=who, answers=answers, lines=lines, seeded=seeded,
                    econ0=econ0, after=after, econ=econ)


def _answer_digest(answers):
    """The handler answers with the per-run ids taken out."""
    out = []
    for answer, exc, _lines in answers:
        if hasattr(answer, "model_dump"):
            d = answer.model_dump()
        else:
            d = dict(answer or {})
        d = {k: v for k, v in d.items()
             if k not in ("match_id", "series_id", "lobby_id", "new_ratings")}
        out.append((d, type(exc).__name__ if exc else None))
    return out


@pytest.mark.parametrize("mode", MODES)
def test_pg_a_database_fault_in_the_hook_costs_the_completion_nothing(opened, monkeypatch, mode):
    """H5, per site: the same completion, clean and with the hook's call
    faulted in the database after the real hook wrote its credits -- in
    every game. The faulted run answers the same, commits the same results,
    ratings, XP, gold and items, holds no credit and no ladder change for
    anyone, and printed exactly one dropped line per game, naming it."""
    _require_live_pg()
    n = GAMES[mode]
    clean = _run(_run_completion(mode, opened, "S"))
    wrote = _faulting_hook(monkeypatch)
    faulted = _run(_run_completion(mode, opened, "S"))
    assert wrote == [len(clean["who"])] * n, (
        "the fault did not land after the real hook wrote its credits", wrote)
    assert all(exc is None for _a, exc, _l in faulted["answers"]), faulted["answers"]
    assert _answer_digest(faulted["answers"]) == _answer_digest(clean["answers"])
    assert faulted["econ"] == clean["econ"], (
        "H5: the fault changed the completion's result, rating, XP, gold or items")
    ok, _want = _plus_n(clean["seeded"], clean["after"], clean["who"], n)
    assert ok and len(clean["after"]["credits"]) == len(clean["who"]) * n, clean["after"]
    table = RATING_TABLE[mode]
    assert clean["econ"][table] != clean["econ0"][table], (
        "the clean completion rated nobody, so the comparison could not see a "
        "rating the fault lost", mode, table)
    assert faulted["after"] == faulted["seeded"], (
        "H5: the faulted completion left ladder state behind", faulted["after"])
    dropped = _dropped(faulted["lines"], mode)
    assert len(dropped) == n and len(faulted["ref"]) == n, (faulted["lines"], faulted["ref"])
    assert all(r in d for r, d in zip(faulted["ref"], dropped)), (dropped, faulted["ref"])
    assert not _dropped(clean["lines"], mode), clean["lines"]


RATING_TABLE = {
    "1v1": "glicko_ratings",
    "2v2": "glicko_ratings_2v2",
    "ffa": "glicko_ratings_ffa",
}


_SITE_FUNCTION = {
    "1v1": "submit_match",
    "2v2": "submit_team_match",
    "ffa": "submit_ffa_match",
}


def _without_hook_savepoint(name):
    """main.<name>, compiled from main.py's own source with the one
    `async with db.begin_nested():` that holds the hook's call replaced by
    its body -- nothing else changed -- and with main's globals as they are
    at the call."""
    tree = ast.parse(io.open(MAIN_PY, encoding="utf-8").read())
    fn = next(n for n in tree.body
              if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)
    removed = []

    class _Strip(ast.NodeTransformer):
        def visit_AsyncWith(self, node):
            self.generic_visit(node)
            ctx = node.items[0].context_expr if len(node.items) == 1 else None
            savepoint = (isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Attribute)
                         and ctx.func.attr == "begin_nested")
            if savepoint and any(isinstance(n, ast.Attribute) and n.attr == HOOK
                                 for n in ast.walk(node)):
                removed.append(node.lineno)
                return node.body
            return node
    _Strip().visit(fn)
    assert len(removed) == 1, ("expected one hook savepoint in %s" % name, removed)
    fn.decorator_list = []
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(vars(main))
    exec(compile(module, "%s [%s without its hook savepoint]" % (MAIN_PY, name), "exec"),
         namespace)
    return namespace[name]


@pytest.mark.parametrize("mode", MODES)
def test_pg_without_the_savepoint_the_same_fault_costs_the_completion(opened, monkeypatch, mode):
    """H5's control (#235/#536): the handler with only the hook's savepoint
    taken out, and the same fault. The handler's own except still catches it
    and prints the dropped line -- and the game is lost with the credit: the
    transaction the fault aborted is the game's own. Every game reaches the
    hook now, so no game of the completion survives."""
    _require_live_pg()
    variant = _without_hook_savepoint(_SITE_FUNCTION[mode])
    _faulting_hook(monkeypatch)
    run = _run(_run_completion(mode, opened, "V", submit=variant))
    assert _dropped(run["lines"], mode), run["lines"]
    econ = run["econ"]
    lost = {
        "1v1": econ["matches"] == [] and not any(s[0] == "completed"
                                                 for s in econ["ranked_series"]),
        "2v2": econ["team_matches"] == 0 and [s[0] for s in econ["team_series"]] == ["active"],
        "ffa": econ["ffa_matches"] == 0,
    }[mode]
    assert lost, ("without the savepoint the completion survived the fault -- then the "
                  "savepoint would not be what protects it", mode, econ)
    assert run["after"] == run["seeded"], run["after"]


# -- LOW residual sentences made tests (design V3 section 12.6) ---------------

def test_pg_r1_a_fault_in_game_one_costs_only_game_ones_credit(opened, monkeypatch):
    """LOW-R1 (design V3 section 12.6), re-read for the game unit: "Injecting
    a SQL failure inside each hook savepoint must leave the normal
    completion, rating and gold committed while writing no credit and
    logging `[LADDER-CREDIT]`; any effect on those states or a
    nonparticipant ladder falsifies containment." A failing SQL statement is
    injected into the hook's call in game 1 of a two-game FFA lobby, and only
    there. After game 1 the game is committed exactly as a clean twin's game
    1 is -- the same answer, match row, ratings, XP, gold and items -- no
    credit exists, no ladder moved (the bystander's included) and one
    dropped line names game 1. Game 2, unfaulted, rates the same four and
    writes each one's credit under GAME 2's id: +1 each, once, and the GET
    reads it. Game 1's credit is not recovered -- under the game unit it
    belongs to game 1 alone; the residual is in the build notes."""
    _require_live_pg()
    four = [P1, P2, P3, P4]

    async def _lobby(two_games):
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            seeded, _ = await _look(schema)
            lobby = await _ffa_lobby(sm, ids)
            g1 = await _submit(sm, main.submit_ffa_match,
                               _report_ffa(lobby, "ffa_lhX_r1", _ffa_game(), P1))
            after1, econ1 = await _look(schema)
            out = dict(lobby=str(lobby), seeded=seeded, g1=g1, after1=after1, econ1=econ1)
            if two_games:
                g2 = await _submit(sm, main.submit_ffa_match,
                                   _report_ffa(lobby, "ffa_lhY_r2", _ffa_game(), P1))
                after2, _ = await _look(schema)
                out.update(g2=g2, after2=after2, got2=await _get_ladders(schema, four))
            return out

    clean = _run(_lobby(False))
    wrote = _faulting_hook(monkeypatch, only_first=True)
    run = _run(_lobby(True))
    assert wrote == [4], ("the fault did not land after the real hook wrote four credits",
                          wrote)
    assert run["g1"][1] is None, run["g1"]
    assert _answer_digest([run["g1"]]) == _answer_digest([clean["g1"]])
    assert run["econ1"] == clean["econ1"], (
        "R1: the fault changed game 1's result, rating, XP, gold or items")
    assert run["after1"] == run["seeded"], (
        "R1: game 1's fault left ladder state behind", run["after1"])
    m1 = str(run["g1"][0].match_id)
    dropped = _dropped(run["g1"][2], "ffa")
    assert len(dropped) == 1 and m1 in dropped[0], run["g1"][2]
    assert run["g2"][1] is None and not _dropped(run["g2"][2], "ffa"), run["g2"]
    m2 = str(run["g2"][0].match_id)
    ok, want = _plus_one(run["seeded"], run["after2"], four)
    assert ok, ("R1: game 2 did not write its own credit", run["after2"]["progress"], want)
    assert _credited(run["after2"], m2, "ffa", four), run["after2"]["credits"]
    assert len(run["after2"]["credits"]) == 4, run["after2"]["credits"]
    for s in four:
        status, body = run["got2"][s]
        assert status == 200 and _worn_games(body) == (WEAR[s][0], WEAR[s][1] + 1), (
            s, run["got2"][s])


async def _r3_run(how, tag):
    """A 1v1 series to completion with the rating pass forced one way: game
    1 on the case's own sessions, the deciding report on a session whose
    commit, for `how` == "skip", invalidates the series from another
    connection as soon as the completion is on disk -- a reversal landing in
    the one gap between the completion's commit and the rating pass."""
    async with _case() as (schema, sm):
        ids = await _seed(sm)
        seeded, _ = await _look(schema)
        g1 = await _submit(sm, main.submit_match, _report_1v1("ranked_lh%s_000001_r1" % tag))
        assert g1[1] is None and g1[0].series_status == "active", g1
        _mid, mid_econ = await _look(schema)
        reversed_ = []

        class _ReverseBetween(AsyncSession):
            async def commit(self):
                await super().commit()
                if reversed_:
                    return
                conn = await harness.connect_bound(DSN, schema)
                try:
                    done = await conn.execute(
                        "UPDATE ranked_series SET invalidated_at = NOW() "
                        " WHERE status = 'completed' AND invalidated_at IS NULL")
                finally:
                    await conn.close()
                if done == "UPDATE 1":
                    reversed_.append(True)
        engine = harness.bound_engine(DSN, schema) if how == "skip" else None
        deciding = sm if engine is None else async_sessionmaker(
            engine, expire_on_commit=False, class_=_ReverseBetween)
        try:
            g2 = await _submit(deciding, main.submit_match,
                               _report_1v1("ranked_lh%s_000002_r2" % tag))
        finally:
            if engine is not None:
                await engine.dispose()
        after, econ = await _look(schema)
        refs = [str(g[0].match_id) for g in (g1, g2) if g[1] is None]
        return dict(seeded=seeded, mid_econ=mid_econ, g2=g2, after=after, econ=econ,
                    reversed=bool(reversed_), refs=refs)


@pytest.mark.parametrize("how", ["fail", "skip"])
def test_pg_r3_the_1v1_credit_stands_when_the_rating_pass_does_not_run(opened, monkeypatch,
                                                                       how):
    """LOW-R3 (design V3 section 12.6): "Forcing the 1v1 T2 pass to fail or
    take the skip at `backend/api/main.py:8338-8350` leaves the T1 credit
    committed without a rating update; the credit must not cause a match,
    gold or unrelated-ladder mutation." (The line numbers are the base
    tree's.) The 1v1 rating pass is the second transaction,
    after the completion's commit. Forced to FAIL (the rating calculation
    raises) or to take its SKIP (the series is invalidated between the two
    transactions -- what the pass's authoritative re-read exists to catch),
    the credits committed with the two games stand: both players +2, one
    keyed by each game, and nobody else's ladder moves -- while the ratings stay
    where game 1 left them and no rating history is written. And the credit
    causes nothing else: the same run with the hook made a no-op answers the
    same and commits the same matches, series, XP, gold, items and ratings."""
    _require_live_pg()
    if how == "fail":
        def _refuse(*a, **k):
            raise RuntimeError("ladder hooks: rating pass refused")
        monkeypatch.setattr(main, "calculate_new_rating", _refuse)
    live = _run(_r3_run(how, "R"))

    async def _no_hook(db, player_ids, *, mode, reference_id, rows=None):
        return []
    monkeypatch.setattr(tl, HOOK, _no_hook)
    inert = _run(_r3_run(how, "R"))

    forced = {"fail": "Series Glicko update error",
              "skip": "was invalidated/changed between the match commit and the rating pass"}
    for label, run in (("hook live", live), ("hook no-op", inert)):
        assert run["g2"][1] is None and run["g2"][0].series_status == "completed", (
            label, run["g2"])
        assert any(forced[how] in ln for ln in run["g2"][2]), (
            "the rating pass did not take the forced path", label, how, run["g2"][2])
        assert run["reversed"] == (how == "skip"), (label, run["reversed"])
    ok, want = _plus_n(live["seeded"], live["after"], [P1, P2], 2)
    assert ok, ("R3: the committed credit did not stand", live["after"]["progress"], want)
    assert len(live["refs"]) == 2, live["refs"]
    for ref in live["refs"]:
        assert _credited(live["after"], ref, "1v1", [P1, P2]), live["after"]["credits"]
    assert len(live["after"]["credits"]) == 4, live["after"]["credits"]
    for table in ("glicko_ratings", "glicko_ratings_2v2", "glicko_ratings_ffa"):
        assert live["econ"][table] == live["mid_econ"][table], ("R3: a rating moved", table)
    assert live["econ"]["rating_history"] == 0, live["econ"]["rating_history"]
    assert inert["after"] == inert["seeded"], inert["after"]
    assert live["econ"] == inert["econ"], (
        "R3: the credit changed a match, series, XP, gold, item or rating")
    assert _answer_digest([live["g2"]]) == _answer_digest([inert["g2"]])


@contextlib.asynccontextmanager
async def _app(schema):
    """An httpx client on main.app, every request on a session of its own
    bound to `schema`; an exception the app does not handle comes back as
    the 500 a player's client would get, not raised into the test."""
    engine = harness.bound_engine(DSN, schema)
    session = async_sessionmaker(engine, expire_on_commit=False)

    async def _db():
        async with session() as db:
            yield db
    main.app.dependency_overrides[database.get_db] = _db
    try:
        transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
                transport=transport, base_url="http://ladder.test",
                headers={"X-Mod-Version": main.MIN_MOD_VERSION_EFFECTIVE}) as client:
            yield client
    finally:
        main.app.dependency_overrides.pop(database.get_db, None)
        await engine.dispose()


def test_pg_qg_the_resent_1v1_report_answers_500_and_writes_nothing(opened):
    """LOW-Q-G (design V3 section 12.6): "Resending the same 1v1 report
    currently returns HTTP 500 at `backend/api/main.py:7669`; it must write
    no second result, rating, gold or ladder credit." (The line number is
    the base tree's.) Documented as it stands and NOT changed in this
    lane: through main.app, the series' two reports answer 200 and complete
    it, crediting both players once per game; the deciding report sent again
    answers
    HTTP 500 -- its match insert's flush meets unique_match before any
    series logic -- and writes no second result, rating, gold or ladder
    credit."""
    _require_live_pg()

    async def _go():
        async with _case() as (schema, sm):
            ids = await _seed(sm)
            async with _app(schema) as client:
                first = await client.post(
                    "/api/v1/matches",
                    json=_report_1v1("ranked_lhZ_000001_r1").model_dump(mode="json"))
                assert first.status_code == 200, (first.status_code, first.text)
                assert first.json()["series_status"] == "active", first.text
                deciding = _report_1v1("ranked_lhZ_000002_r2").model_dump(mode="json")
                second = await client.post("/api/v1/matches", json=deciding)
                assert second.status_code == 200, (second.status_code, second.text)
                assert second.json()["series_status"] == "completed", second.text
                done, econ = await _look(schema)
                for ref in (first.json()["match_id"], second.json()["match_id"]):
                    assert _credited(done, str(ref), "1v1", [P1, P2]), done["credits"]
                assert len(done["credits"]) == 4, done["credits"]
                again = await client.post("/api/v1/matches", json=deciding)
                assert again.status_code == 500, (again.status_code, again.text)
            after, econ2 = await _look(schema)
            assert len(econ2["matches"]) == 2, econ2["matches"]
            assert after == done and econ2 == econ, (
                "Q-G: the resent deciding report wrote something")
    _run(_go())
