"""Migration 421 (OCT3-B) and its rollback on a real PostgreSQL.

421 credits the gold and XP of games 2 and 3 of one FFA lobby whose reports
were held in match_report_quarantine, and applies no rating. These tests run
the REAL files (backend/sql/421_... and rollback_421_...) against a schema
seeded like the primary: the six players, the lobby, a glicko row each and the
two held rows, whose bodies carry the live tallies (rounds, points, kills per
slot) under invented Steam ids and display names.

The file pins each held body by md5(payload::text), read on the primary. An
invented body has another md5, so every apply here substitutes the fixture's
two md5 values for the file's two (each must stand in the file exactly once);
nothing else in the file is changed, except by a named mutant.

  T1 apply: the exact XP and placement gold, drip and level gold from the rows
     as found, ledger rows naming the held rows, 12 audit rows, both credited.
  T2 a second run writes nothing (values and row versions).
  T3 each state but both-pending and both-credited raises, nothing applied.
  T4 no held rows: nothing applied (the migration and the rollback).
  T5 the literal amounts equal what main's own helpers compute from the bodies.
  T6 the rollback restores every player and both rows; 421 then applies again
     identically.
  T7 the SQL level expression equals level_from_xp / level_reward_for.
  T8 a lock held on a player: the run fails inside its lock timeout, nothing
     applied.
  T9 where migration 420's two admin_actions columns stand, each audit row
     names its player in affected_steam_ids and carries the note as reason.
  T10 one of those columns alone, or affected_steam_ids of another type:
     the run raises, nothing applied.

RUNNING IT: OCT3B_TEST_PG_DSN names a database (postgresql://...); each case
makes its own schema there and leaves it. Without the DSN the live cases FAIL;
OCT3B_TEST_PG_OPTOUT=1 waives them deliberately. OCT3B_MUTANT=<name> applies
one named mutant from MUTANTS to the file text before every run: each mutant
must turn the test it names red while the unmutated run stays green.
"""

import asyncio
import json
import math
import os
import re
import time
import uuid
from pathlib import Path

import pytest

import main

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
M421 = SQL_DIR / "421_oct3b_credit_held_ffa_games.sql"
R421 = SQL_DIR / "rollback_421_oct3b_credit_held_ffa_games.sql"

DSN = (os.environ.get("OCT3B_TEST_PG_DSN") or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get("OCT3B_TEST_PG_OPTOUT") == "1"
MUTANT = os.environ.get("OCT3B_MUTANT") or ""

Q2 = "cb241216-41f9-49cc-aab5-3f0984c2c051"
Q3 = "1e419790-b377-402a-8455-20f4e39ebdc8"
LOBBY = "a18d56f5-382f-4fd0-8312-d873412a5ace"
ROOMS = {Q2: "ffa_58e81a62609a_040746_r2", Q3: "ffa_58e81a62609a_042203_r3"}
LIVE_MD5 = {Q2: "5b3a330d97fd669722eb23954ccc3dbc", Q3: "761bb451e3f395c6ad26cd69aa5b60a0"}
ACTOR = "system:migration_421"

# The live tallies per slot: (rounds_won, points_total, kills).
TALLIES = {
    Q2: {0: (0, 2, 8), 1: (0, 2, 7), 2: (0, 2, 13), 3: (5, 11, 31), 4: (2, 5, 20), 5: (0, 0, 10)},
    Q3: {0: (1, 2, 12), 1: (0, 3, 20), 2: (1, 4, 10), 3: (5, 11, 34), 4: (0, 4, 10), 5: (0, 0, 3)},
}
DURATION = {Q2: 855, Q3: 819}
# The design's Table 3: per (held row, slot), the XP and the placement gold.
DESIGN = {
    Q2: {0: (2330, 28), 1: (1614, 20), 2: (3046, 37), 3: (2986, 36), 4: (3763, 46), 5: (898, 11)},
    Q3: {0: (3323, 41), 1: (1761, 22), 2: (4105, 50), 3: (3257, 40), 4: (2542, 31), 5: (980, 12)},
}
# Each slot's FFA rating after game 1 (rating_before + change of game 1's rows,
# read on the primary): the tier inputs of games 2 and 3 (ruling 2).
RATING_AFTER_G1 = {0: 1492.2581799811808, 1: 1255.0, 2: 1504.4418200188193,
                   3: 2052.765250588468, 4: 1776.8290842227273, 5: 1428.0709157772726}
# Game 1 (recorded) per slot: placement, rating_before, and what the live rows
# hold for XP and placement gold; battles 25 over 745 s. T5's control.
G1 = {0: (5, 1835.0581799811807, 1834, 22), 1: (6, 1500.0, 1020, 12),
      2: (3, 1164.9418200188193, 4616, 56), 3: (1, 2045.265250588468, 5090, 62),
      4: (2, 1667.5290842227273, 4276, 52), 5: (4, 1332.4709157772727, 2648, 32)}
# T7's range: every XP value from 0 to beyond the six players' totals plus
# their credit (the largest read 1,376,379 on the primary on 17 Nov 2026).
T7_MAX_XP = 1_400_000

# name -> (file, old text, new text, the test it must turn red)
MUTANTS = {
    "xp-literal": (M421, '"slot": 0, "xp": 2330,', '"slot": 0, "xp": 2331,', "T1, T5"),
    "place-literal": (M421, '"xp": 2330, "place_gold": 28}', '"xp": 2330, "place_gold": 29}', "T5"),
    "drip-round": (M421, "pg_catalog.floor(new_xp::pg_catalog.numeric / 100)",
                   "pg_catalog.round(new_xp::pg_catalog.numeric / 100)", "T1"),
    "no-second-run": (M421, "IF n_credited = 2 THEN", "IF false THEN", "T2"),
    "no-md5-guard": (M421, "     AND pg_catalog.md5(q.payload::pg_catalog.text) = (p->>'md5')\n", "", "T3"),
    "no-deleted-guard": (M421, "   WHERE pl.deleted_at IS NULL\n     AND pl.steam_id IN",
                         "   WHERE pl.steam_id IN", "T3"),
    "no-ledger-guard": (M421, "IF EXISTS (SELECT 1 FROM gold_transactions g WHERE g.reference_id = ANY "
                        "(qids::pg_catalog.text[]))\n     OR", "IF false\n     OR", "T3"),
    "no-roster-guard": (M421, "RAISE EXCEPTION '421: the held bodies'' players",
                        "RAISE NOTICE '421: the held bodies'' players", "T3"),
    "no-empty-return": (M421, "IF n_rows = 0 THEN", "IF n_rows = -1 THEN", "T4"),
    "rollback-keeps-ffa-gold": (R421, "ffa_gold_earned = COALESCE(pl.ffa_gold_earned, 0) - r.gold",
                                "ffa_gold_earned = COALESCE(pl.ffa_gold_earned, 0)", "T6"),
    "reward-400": (M421, "ELSE 500 END", "ELSE 400 END", "T7"),
    "threshold": (M421, "10000::pg_catalog.numeric", "10001::pg_catalog.numeric", "T7"),
    "lock-timeout": (M421, "SET LOCAL lock_timeout = '5s';", "SET LOCAL lock_timeout = '60s';", "T8"),
    "modlog-writes-old-insert": (M421, "    IF modlog THEN\n", "    IF false THEN\n", "T9"),
    "one-column-as-absent": (M421, "IF aa_rel IS NULL OR (aff_t IS NULL) <> (reason_t IS NULL) THEN",
                             "IF aa_rel IS NULL THEN", "T10"),
}

NOTE = "Migration 421, option B: gold and XP credited, ratings not applied."

# Migration 420's two admin_actions columns and its CHECK, as its file adds
# them (backend/sql/420_admin_actions_modlog.sql on the moderator log
# branch, claude/modlog-1116, the ADD COLUMN and ADD CONSTRAINT statements).
M420_AFFECTED = "ALTER TABLE admin_actions ADD COLUMN affected_steam_ids TEXT[] NOT NULL DEFAULT '{}';"
M420_REASON = ("ALTER TABLE admin_actions ADD COLUMN reason TEXT NULL;\n"
               "ALTER TABLE admin_actions ADD CONSTRAINT ck_admin_actions_reason_len\n"
               "  CHECK (reason IS NULL OR pg_catalog.char_length(reason) <= 256);")


def _text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if MUTANT:
        f, old, new, _ = MUTANTS[MUTANT]
        if f == path:
            assert text.count(old) == 1, ("mutant site not found once", MUTANT)
            text = text.replace(old, new)
    return text


def migration_text(md5s: dict) -> str:
    text = _text(M421)
    for q, live in LIVE_MD5.items():
        assert text.count(live) == 1, (q, "the file must pin this body exactly once")
        text = text.replace(live, md5s[q])
    return text


def steam(slot: int) -> str:
    return "7656119900000%04d" % (slot + 10)


def body(q: str) -> dict:
    return {
        "lobby_id": LOBBY, "photon_room_id": ROOMS[q], "is_ranked": True,
        "winner_steam_id": steam(3), "reported_by_steam_id": steam(0),
        "match_duration": DURATION[q], "game_version": "1.41.0",
        "players": [{"slot": s, "steam_id": steam(s), "display_name": "Seat %d" % s,
                     "rounds_won": r, "points_total": p, "kills": k,
                     "left_early": False, "absent": False}
                    for s, (r, p, k) in sorted(TALLIES[q].items())],
    }


# ── harness ────────────────────────────────────────────────────────────────

def require_pg():
    if DSN and asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip("OCT3B_TEST_PG_OPTOUT=1: the live cases are waived")
    pytest.fail("OCT3B_TEST_PG_DSN is not set (or asyncpg is missing): migration 421's live cases "
                "did not run. Set it, or OCT3B_TEST_PG_OPTOUT=1 to waive them.")


SCHEMA_DDL = """
CREATE TABLE players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    steam_id VARCHAR NOT NULL UNIQUE,
    display_name VARCHAR NOT NULL,
    deleted_at TIMESTAMPTZ,
    total_xp INTEGER NOT NULL DEFAULT 0,
    ffa_xp_earned INTEGER NOT NULL DEFAULT 0,
    gold_earned INTEGER NOT NULL DEFAULT 0,
    ffa_gold_earned INTEGER NOT NULL DEFAULT 0);
CREATE TABLE gold_transactions (
    id BIGSERIAL PRIMARY KEY,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    reason VARCHAR(64) NOT NULL,
    reference_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE admin_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_steam_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_steam_id TEXT,
    target_match_id UUID,
    target_series_id UUID,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE ffa_lobbies (
    id UUID PRIMARY KEY,
    status VARCHAR(16) NOT NULL,
    member_ids UUID[] NOT NULL,
    games_played INTEGER NOT NULL,
    is_ranked BOOLEAN NOT NULL,
    kills_tiebreak BOOLEAN NOT NULL);
CREATE TABLE glicko_ratings_ffa (
    player_id UUID PRIMARY KEY REFERENCES players(id),
    rating DOUBLE PRECISION NOT NULL,
    rating_deviation DOUBLE PRECISION NOT NULL,
    volatility DOUBLE PRECISION NOT NULL);
"""

TABLES = ("players", "gold_transactions", "admin_actions", "match_report_quarantine",
          "ffa_lobbies", "glicko_ratings_ffa")


def run(coro):
    return asyncio.run(coro)


class Case:
    """One fresh schema in the test database, built and seeded like the
    primary; the schema is left in place afterwards."""

    def __init__(self, seed=True, extra_ddl=""):
        self.seed_rows = seed
        self.extra_ddl = extra_ddl
        self.schema = "o3_" + uuid.uuid4().hex[:12]
        self.notices = []

    async def __aenter__(self):
        boot = await asyncpg.connect(DSN, timeout=10)
        try:
            await boot.execute('CREATE SCHEMA "%s"' % self.schema)
        finally:
            await boot.close()
        self.conn = await self.connect()
        self.conn.add_log_listener(lambda c, m: self.notices.append(m.message))
        await self.conn.execute(SCHEMA_DDL)
        q169 = (SQL_DIR / "169_match_report_quarantine.sql").read_text(encoding="utf-8")
        # 169's own post-check counts the table across every schema of the
        # database, so it is left out; its DDL runs as written.
        await self.conn.execute(q169.split("\nDO $$")[0])
        await self.conn.execute((SQL_DIR / "419_quarantine_digest_posted.sql").read_text(encoding="utf-8"))
        if self.extra_ddl:
            await self.conn.execute(self.extra_ddl)
        await self.seed()
        return self

    async def __aexit__(self, *exc):
        await self.conn.close()
        return False

    async def connect(self):
        return await asyncpg.connect(DSN, timeout=10, server_settings={"search_path": self.schema})

    async def seed(self):
        # total_xp as found: slot 4 stands 50 below level 15, so its first
        # credit pays a level_reward; the others sit at drip boundaries.
        lvl15 = main.total_xp_for_level(15)
        self.xp0 = {0: 18511, 1: 17390, 2: 5899, 3: 1370136, 4: lvl15 - 50, 5: 14967}
        self.pid = {}
        for s in range(6):
            pid = uuid.uuid4()
            self.pid[s] = pid
            await self.conn.execute(
                "INSERT INTO players (id, steam_id, display_name, total_xp, ffa_xp_earned,"
                " gold_earned, ffa_gold_earned) VALUES ($1, $2, $3, $4, $4, $5, $6)",
                pid, steam(s), "Seat %d" % s, self.xp0[s], 600 + s, 300 + s)
            await self.conn.execute(
                "INSERT INTO gold_transactions (player_id, amount, reason, reference_id)"
                " VALUES ($1, 100, 'xp', 'earlier')", pid)
            await self.conn.execute(
                "INSERT INTO glicko_ratings_ffa VALUES ($1, $2, 120.5, 0.06)", pid, RATING_AFTER_G1[s])
        await self.conn.execute(
            "INSERT INTO ffa_lobbies VALUES ($1, 'completed', $2, 1, true, true)",
            uuid.UUID(LOBBY), [self.pid[s] for s in (4, 0, 1, 2, 5, 3)])
        self.md5 = {}
        if self.seed_rows:
            for q in (Q2, Q3):
                await self.conn.execute(
                    "INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id,"
                    " photon_room_id, reporter_id, player_ids, payload, status, created_at)"
                    " VALUES ($1, 'ffa', 'lobby_completed', 409, $2, $3, $4, $5, $6::jsonb, 'pending',"
                    " '2026-10-04 04:30:00+00')",
                    uuid.UUID(q), uuid.UUID(LOBBY), ROOMS[q], self.pid[0],
                    [self.pid[s] for s in range(6)], json.dumps(body(q)))
                self.md5[q] = await self.conn.fetchval(
                    "SELECT md5(payload::text) FROM match_report_quarantine WHERE id = $1", uuid.UUID(q))
        else:
            self.md5 = {Q2: "0" * 32, Q3: "1" * 32}

    async def apply(self, text=None):
        """Run a file as the migrate verb does: the whole text, stopping at
        the first error (the file's own BEGIN/COMMIT is the transaction)."""
        self.notices.clear()
        try:
            await self.conn.execute(text if text is not None else migration_text(self.md5))
        except Exception:
            await self.conn.execute("ROLLBACK")
            raise
        finally:
            await self.conn.execute("RESET search_path")

    async def rollback_file(self):
        await self.apply(_text(R421))

    async def fingerprint(self, versions=True):
        out = {}
        for t in TABLES:
            expr = "t::text || '|' || t.xmin::text" if versions else "t::text"
            out[t] = await self.conn.fetchval(
                "SELECT count(*)::text || ':' || coalesce(md5(string_agg(%s, ',' ORDER BY %s)), '')"
                " FROM %s t" % (expr, expr, t))
        return out

    async def players(self):
        rows = await self.conn.fetch(
            "SELECT id, total_xp, ffa_xp_earned, gold_earned, ffa_gold_earned FROM players")
        return {r["id"]: tuple(r)[1:] for r in rows}

    async def ledger(self):
        rows = await self.conn.fetch(
            "SELECT player_id, reason, amount, reference_id FROM gold_transactions"
            " WHERE reference_id IN ($1, $2)", Q2, Q3)
        return sorted((str(r["player_id"]), r["reason"], r["amount"], r["reference_id"]) for r in rows)

    async def audit(self):
        rows = await self.conn.fetch(
            "SELECT admin_steam_id, action, target_steam_id, target_match_id, details FROM admin_actions")
        return sorted((r["admin_steam_id"], r["action"], r["target_steam_id"], r["target_match_id"],
                       json.dumps(json.loads(r["details"]), sort_keys=True)) for r in rows)

    async def held(self):
        rows = await self.conn.fetch(
            "SELECT id::text, status, reviewed_by, reviewed_at, review_note, payload::text"
            " FROM match_report_quarantine ORDER BY id")
        return [tuple(r) for r in rows]


def expected(case):
    """What the credit must do, computed here from the rows as found with
    main's own level helpers and settlement's floor-division drip."""
    xp = dict(case.xp0)
    per_player = {s: [0, 0] for s in range(6)}       # [xp, gold]
    ledger, audit = [], []
    order = sorted(range(6), key=lambda s: str(case.pid[s]))
    for q, game in ((Q2, 2), (Q3, 3)):
        for s in order:
            add, place = DESIGN[q][s]
            old, new = xp[s], xp[s] + add
            xp[s] = new
            drip = max(0, new // 100 - old // 100)
            ol, nl = main.level_from_xp(old)[0], main.level_from_xp(new)[0]
            lvl = sum(main.level_reward_for(v) for v in range(ol + 1, nl + 1)) if nl > ol else 0
            per_player[s][0] += add
            per_player[s][1] += drip + place + lvl
            for reason, amt in (("ffa_xp", drip), ("ffa_placement", place), ("level_reward", lvl)):
                if amt > 0:
                    ledger.append((str(case.pid[s]), reason, amt, q))
            audit.append((ACTOR, "quarantine_credit", steam(s), None, json.dumps({
                "qid": q, "game": game, "room": ROOMS[q], "slot": s, "xp": add,
                "gold_ffa_xp": drip, "gold_ffa_placement": place, "gold_level_reward": lvl,
                "ratings": "not applied", "migration": 421}, sort_keys=True)))
    return per_player, sorted(ledger), sorted(audit)


# ── T1 ──────────────────────────────────────────────────────────────────────

def test_t1_apply_credits_the_exact_amounts():
    require_pg()

    async def body_():
        async with Case() as c:
            before = await c.players()
            glicko = await c.fingerprint()
            await c.apply()
            per_player, ledger, audit = expected(c)
            after = await c.players()
            for s in range(6):
                b, a = before[c.pid[s]], after[c.pid[s]]
                x, g = per_player[s]
                assert a == (b[0] + x, b[1] + x, b[2] + g, b[3] + g), (s, b, a, x, g)
            assert await c.ledger() == ledger
            assert await c.audit() == audit
            assert len(audit) == 12
            held = await c.held()
            assert [h[1] for h in held] == ["credited", "credited"]
            assert all(h[2] is None and h[3] is not None for h in held)
            assert all(h[4] == "Migration 421, option B: gold and XP credited, ratings not applied."
                       for h in held)
            after_fp = await c.fingerprint()
            for t in ("ffa_lobbies", "glicko_ratings_ffa"):
                assert after_fp[t] == glicko[t], t
            # the fixture reaches the level branch (slot 4 crosses level 15)
            assert any(r[1] == "level_reward" for r in ledger)
            assert sum(x for x, _ in per_player.values()) == 30605
            assert sum(v[1] for v in DESIGN[Q2].values()) + sum(v[1] for v in DESIGN[Q3].values()) == 374
            assert any(m.startswith("421: credited games 2 and 3") for m in c.notices), c.notices

    run(body_())


# ── T2 ──────────────────────────────────────────────────────────────────────

def test_t2_a_second_run_changes_nothing():
    require_pg()

    async def body_():
        async with Case() as c:
            await c.apply()
            first = await c.fingerprint()
            await c.apply()
            assert await c.fingerprint() == first
            assert any("already applied" in m for m in c.notices), c.notices

    run(body_())


# ── T3 ──────────────────────────────────────────────────────────────────────

async def _mixed(c, how):
    ex = c.conn.execute
    q2, q3 = uuid.UUID(Q2), uuid.UUID(Q3)
    if how == "one-absent":
        await ex("DELETE FROM match_report_quarantine WHERE id = $1", q3)
    elif how == "one-credited":
        await ex("UPDATE match_report_quarantine SET status = 'credited' WHERE id = $1", q2)
    elif how == "both-accepted":
        await ex("UPDATE match_report_quarantine SET status = 'accepted'")
    elif how == "both-filed":
        await ex("UPDATE match_report_quarantine SET status = 'filed'")
    elif how == "credited-without-ledger":
        await ex("UPDATE match_report_quarantine SET status = 'credited', review_note ="
                 " 'Migration 421, option B: gold and XP credited, ratings not applied.'")
    elif how == "a-kill-changed":
        await ex("UPDATE match_report_quarantine SET payload = jsonb_set(payload, '{players,0,kills}', '9')"
                 " WHERE id = $1", q2)
    elif how == "a-deleted-player":
        await ex("UPDATE players SET deleted_at = NOW() WHERE id = $1", c.pid[2])
    elif how == "an-existing-ledger-row":
        await ex("INSERT INTO gold_transactions (player_id, amount, reason, reference_id)"
                 " VALUES ($1, 5, 'admin_grant', $2)", c.pid[1], Q3)
    elif how == "a-player-off-the-roster":
        await ex("UPDATE ffa_lobbies SET member_ids = array_replace(member_ids, $1, $2)",
                 c.pid[5], uuid.uuid4())
    else:
        raise AssertionError(how)


MIXED = ("one-absent", "one-credited", "both-accepted", "both-filed", "credited-without-ledger",
         "a-kill-changed", "a-deleted-player", "an-existing-ledger-row", "a-player-off-the-roster")


@pytest.mark.parametrize("how", MIXED)
def test_t3_every_other_state_raises_with_nothing_applied(how):
    require_pg()

    async def body_():
        async with Case() as c:
            await _mixed(c, how)
            before = await c.fingerprint()
            with pytest.raises(asyncpg.exceptions.RaiseError) as ei:
                await c.apply()
            assert str(ei.value).startswith("421: "), str(ei.value)
            assert await c.fingerprint() == before

    run(body_())


# ── T4 ──────────────────────────────────────────────────────────────────────

def test_t4_no_held_rows_nothing_applied():
    require_pg()

    async def body_():
        async with Case(seed=False) as c:
            before = await c.fingerprint()
            await c.apply()
            assert await c.fingerprint() == before
            assert any("nothing written" in m for m in c.notices), c.notices
            await c.rollback_file()
            assert await c.fingerprint() == before
            assert any("nothing written" in m for m in c.notices), c.notices

    run(body_())


# ── T5 ──────────────────────────────────────────────────────────────────────

def _file_amounts():
    text = _text(M421)
    m = re.search(r"amounts CONSTANT pg_catalog\.jsonb := '(\[.*?\])';", text, re.S)
    assert m, "the amounts literal is not where T5 reads it"
    return {(a["q"], a["slot"]): (a["xp"], a["place_gold"]) for a in json.loads(m.group(1))}


def _places(tallies, kills_break_ties):
    """Settlement's placement rule (submit_ffa_match, the _place_key block):
    rounds, points, then kills when they break ties; COMPETITION ties."""
    key = {s: (r, p, k if kills_break_ties else 0) for s, (r, p, k) in tallies.items()}
    order = sorted(key, key=lambda s: tuple(-v for v in key[s]))
    places, prev_k, prev_p = {}, None, 0
    for i, s in enumerate(order):
        places[s] = prev_p if key[s] == prev_k else i + 1
        prev_k, prev_p = key[s], places[s]
    return places


def _amounts(places, ratings, battles, elapsed):
    """The XP and placement gold of each slot, by main's own helpers, in the
    arithmetic of submit_ffa_match's XP + gold block."""
    n_live = len(places)
    paid = main._ffa_paid_battles(battles, elapsed, n_live)
    out = {}
    for s, place in places.items():
        beaten = sum(1 for o in places if places[o] > place)
        opp = [ratings[o] for o in places if o != s]
        tier = main._tier_mult_for(sum(opp) / len(opp))[0]
        pool = (main._ffa_battle_rate(n_live) * paid * main._ffa_pool_shape(place, beaten, n_live)
                * (tier / 1.5))
        xp = max(main.FFA_MIN_XP, int(round(pool * main.FFA_XP_SHARE * 100)))
        gold = max(1, int(round(pool * (1.0 - main.FFA_XP_SHARE))))
        out[s] = (xp, gold, tier, paid)
    return out


def test_t5_the_literals_are_what_mains_helpers_compute():
    # Control: the same arithmetic reproduces recorded game 1 exactly.
    g1 = _amounts({s: v[0] for s, v in G1.items()}, {s: v[1] for s, v in G1.items()}, 25, 745)
    assert {s: v[:2] for s, v in g1.items()} == {s: (v[2], v[3]) for s, v in G1.items()}

    lit = _file_amounts()
    assert len(lit) == 12
    for q in (Q2, Q3):
        tallies = TALLIES[q]
        battles = sum(p for _, p, _ in tallies.values())
        for elapsed in (DURATION[q], 7 * 24 * 3600.0):       # the client's, and weeks
            got = _amounts(_places(tallies, True), RATING_AFTER_G1, battles, elapsed)
            assert all(v[3] == battles for v in got.values()), "the pace cap binds"
            assert {s: v[:2] for s, v in got.items()} == {s: lit[(q, s)] for s in range(6)}, q
            assert {s: v[2] for s, v in got.items()} == {0: 1.5, 1: 1.5, 2: 1.5, 3: 1.0, 4: 1.5, 5: 1.5}
        assert {s: lit[(q, s)] for s in range(6)} == DESIGN[q]
    assert sum(v[0] for v in lit.values()) == 30605
    assert sum(v[1] for v in lit.values()) == 374


# ── T6 ──────────────────────────────────────────────────────────────────────

def test_t6_rollback_restores_and_421_applies_again_identically():
    require_pg()

    async def body_():
        async with Case() as c:
            pre_players, pre_held = await c.players(), await c.held()
            pre_fp = await c.fingerprint(versions=False)
            await c.apply()
            first = (await c.players(), await c.ledger(), await c.audit(),
                     [h[1] for h in await c.held()])
            await c.rollback_file()
            assert await c.players() == pre_players
            assert await c.held() == pre_held
            assert await c.fingerprint(versions=False) == pre_fp
            await c.apply()
            again = (await c.players(), await c.ledger(), await c.audit(),
                     [h[1] for h in await c.held()])
            assert again == first

    run(body_())


# ── T7 ──────────────────────────────────────────────────────────────────────

def _marked(name):
    text = _text(M421)
    m = re.search(r"-- oct3b:%s-begin\n(.*?)\n\s*-- oct3b:%s-end" % (name, name), text, re.S)
    assert m, name
    return m.group(1)


def test_t7_the_sql_level_expression_is_level_from_xp_and_level_reward_for():
    require_pg()
    # the integer form the SQL uses is the float form main computes
    for n in range(1, 101):
        assert main.xp_for_level(n) == int(100 * math.pow(n, 1.5)) == math.isqrt(10000 * n ** 3), n
    thresholds, level = _marked("thresholds"), _marked("level")
    lv_sql = ("SELECT pg_catalog.array_agg(b.old_lvl ORDER BY v.old_xp)"
              " FROM (SELECT x::int8 AS old_xp, x::int8 AS new_xp, $3::numeric[] AS cum"
              "        FROM pg_catalog.generate_series($1::int8, $2::int8) AS x) AS v,"
              " LATERAL (%s) AS b" % level)

    async def body_():
        async with Case(seed=False) as c:
            cum = await c.conn.fetchval("SELECT (%s)" % thresholds)
            assert [int(v) for v in cum] == [main.total_xp_for_level(n) for n in range(1, 101)]
            # the level gold of every crossing a -> b, 0 <= a <= b <= 100
            pairs = [(a, b) for a in range(101) for b in range(a, 101)]
            at = [0] + [int(v) for v in cum]
            rows = await c.conn.fetch(
                "SELECT v.a, v.b, r.old_lvl, r.new_lvl, r.level_gold"
                " FROM (SELECT a, b, old_xp, new_xp, $5::numeric[] AS cum"
                "        FROM unnest($1::int[], $2::int[], $3::int8[], $4::int8[]) AS u(a, b, old_xp, new_xp)) AS v,"
                " LATERAL (%s) AS r" % level,
                [a for a, _ in pairs], [b for _, b in pairs],
                [at[a] for a, _ in pairs], [at[b] for _, b in pairs], cum)
            assert len(rows) == len(pairs)
            for r in rows:
                a, b = r["a"], r["b"]
                assert (r["old_lvl"], r["new_lvl"]) == (a, b)
                assert r["level_gold"] == sum(main.level_reward_for(v) for v in range(a + 1, b + 1)), (a, b)
            # the level at EVERY XP value from 0 to beyond the six totals plus credit
            step = 200_000
            for lo in range(0, T7_MAX_XP + 1, step):
                hi = min(lo + step - 1, T7_MAX_XP)
                got = await c.conn.fetchval(lv_sql, lo, hi, cum)
                want = [main.level_from_xp(x)[0] for x in range(lo, hi + 1)]
                assert got == want, (lo, hi, next(i for i, (a, b) in enumerate(zip(got, want)) if a != b))

    run(body_())


# ── T8 ──────────────────────────────────────────────────────────────────────

def test_t8_a_held_player_lock_fails_the_run_inside_its_lock_timeout():
    require_pg()

    async def body_():
        async with Case() as c:
            before = await c.fingerprint()
            other = await c.connect()
            try:
                await other.execute("BEGIN")
                await other.execute("SELECT 1 FROM players WHERE id = $1 FOR NO KEY UPDATE", c.pid[3])
                t0 = time.monotonic()
                with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
                    await c.apply()
                took = time.monotonic() - t0
                assert 4.0 <= took < 15.0, took
            finally:
                await other.execute("ROLLBACK")
                await other.close()
            assert await c.fingerprint() == before

    run(body_())


# ── T9 / T10 ────────────────────────────────────────────────────────────────

def test_t9_after_420_each_audit_row_names_its_player_and_the_note():
    require_pg()

    async def body_():
        async with Case(extra_ddl=M420_AFFECTED + "\n" + M420_REASON) as c:
            await c.apply()
            _, ledger, audit = expected(c)
            assert await c.ledger() == ledger
            assert await c.audit() == audit
            rows = await c.conn.fetch(
                "SELECT target_steam_id, affected_steam_ids, reason FROM admin_actions")
            assert len(rows) == 12
            for r in rows:
                assert r["affected_steam_ids"] == [r["target_steam_id"]], r
                assert r["reason"] == NOTE, r
            assert sorted(r["target_steam_id"] for r in rows) == sorted([steam(s) for s in range(6)] * 2)

    run(body_())


T10_FORMS = {
    "reason-alone": M420_REASON,
    "affected-alone": M420_AFFECTED,
    "affected-not-text-array": ("ALTER TABLE admin_actions ADD COLUMN affected_steam_ids TEXT NOT NULL DEFAULT '';\n"
                                + M420_REASON),
}


@pytest.mark.parametrize("form", sorted(T10_FORMS))
def test_t10_a_partial_or_other_audit_form_raises_with_nothing_applied(form):
    require_pg()

    async def body_():
        async with Case(extra_ddl=T10_FORMS[form]) as c:
            before = await c.fingerprint()
            with pytest.raises(asyncpg.exceptions.RaiseError) as ei:
                await c.apply()
            assert str(ei.value).startswith("421: admin_actions"), str(ei.value)
            assert await c.fingerprint() == before

    run(body_())


# ── the mutant table itself ────────────────────────────────────────────────

def test_every_mutant_site_stands_once():
    """A mutant whose site has moved would mutate nothing and pass as a
    kill; each names text that stands exactly once in its file."""
    for name, (f, old, new, _) in MUTANTS.items():
        assert f.read_text(encoding="utf-8").count(old) == 1, name
        assert old != new, name
