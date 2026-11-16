"""QDIG-1 on live PostgreSQL: the janitor that files FOR THE RECORD rows, the
posted route, D1's added keys read by the new bot and by the bot before
QDIG-1, the Admin list's three strings, /health's two keys, and migration
419 with its rollback.

The harness is test_ffa_quarantine_triage.py's Env: database.py's own
engines redirected to the lane database (RJ_TRIAGE_TEST_PG_DSN), its schema
(which carries 419's two columns), and its admin and internal keys. A
missing DSN FAILS, as there. Rows are the six live rows of 16 Nov 2026 with
invented names and ids (qdig_fixtures).
"""

import asyncio
import json
import re
import types
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

import main
import qdig_fixtures as fx
import test_ffa_quarantine_triage as tq
import test_qdig_bot as tb
import test_quarantine_digest_bot as qb

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
M419 = SQL_DIR / "419_quarantine_digest_posted.sql"
R419 = SQL_DIR / "rollback_419_quarantine_digest_posted.sql"
POSTED = "/api/v1/internal/quarantine/digest/posted"
ADMIN_LIST = "/api/v1/admin/quarantine"
HEALTH = "/api/v1/health"


def run(coro):
    return asyncio.run(coro)


def pid(seat: int) -> uuid.UUID:
    return uuid.UUID(int=0x9000 + seat)


class QEnv(tq.Env):
    """The triage Env plus the QDIG-1 routes, a fresh janitor state, and the
    live seeding."""

    async def __aenter__(self):
        await super().__aenter__()
        self.mp.setattr(main, "_qdig_state", {"needs_decision": -1, "count_at": None, "after": None})
        self.app.add_api_route(POSTED, main.internal_quarantine_digest_posted, methods=["POST"])
        self.app.add_api_route(ADMIN_LIST, main.admin_list_quarantine, methods=["GET"])
        return self

    async def seed_players(self):
        for s, name in fx.NAMES.items():
            await self.ex("INSERT INTO players (id, steam_id, display_name) VALUES (:i, :s, :n)",
                          {"i": pid(s), "s": fx.steam(s), "n": name})

    async def seed_lobbies(self, kills_tiebreak=False):
        await self.ex("INSERT INTO ffa_lobbies (id, status, games_played, player_count, created_at, kills_tiebreak)"
                      " VALUES (:a, 'active', 2, 4, :ta, :kt), (:c, 'completed', 3, 6, :tc, false)",
                      {"a": fx.LOBBY_AB, "c": fx.LOBBY_C, "ta": fx.T_LIVE - timedelta(hours=1),
                       "tc": fx.T_OCT - timedelta(hours=1), "kt": kills_tiebreak})

    async def seed_game(self, game, *, room=None, mid=None, number=1, recorded=None, invalidated=False):
        g = fx.GAMES[game]
        nums = recorded or g["recorded"]
        mid = mid or g["match"]
        win = fx.winner_of(nums, g["seats"])
        await self.ex(
            "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, player_count, winner_id, reported_by,"
            " ended_at, created_at, invalidated_at, game_number) VALUES (:i, :l, :r, :pc, :w, :rb, :e, :e, :inv, :g)",
            {"i": mid, "l": g["lobby"], "r": room or g["room"], "pc": len(g["seats"]), "w": pid(win),
             "rb": pid(g["seats"][0]), "e": g["at"] + timedelta(minutes=10),
             "inv": (g["at"] + timedelta(hours=1)) if invalidated else None, "g": number})
        await self.exmany(
            "INSERT INTO ffa_match_players (match_id, player_id, slot, rounds_won, points_total, kills)"
            " VALUES (:m, :p, :sl, :rw, :pt, :k)",
            [{"m": mid, "p": pid(s), "sl": i, "rw": r, "pt": p, "k": k}
             for i, (s, (r, p, k)) in enumerate(zip(g["seats"], nums))])
        return mid

    async def seed_row(self, r, game, *, status="pending", note=None, reviewed=False, reporter=None):
        g = fx.GAMES[game]
        await self.ex(
            "INSERT INTO match_report_quarantine (id, mode, reason, http_status, group_id, photon_room_id,"
            " reporter_id, player_ids, payload, status, created_at, reviewed_at, review_note)"
            " VALUES (:i, 'ffa', :r, 409, :g, :room, :rep, :pids, CAST(:pl AS JSONB), :st, :c, :rv, :note)",
            {"i": r["id"], "r": r["reason"], "g": r["group_id"], "room": r["photon_room_id"],
             "rep": pid(reporter or g["reporters"][0]), "pids": [pid(s) for s in g["seats"]],
             "pl": json.dumps(r["payload"]), "st": status, "c": r["created_at"],
             "rv": r["created_at"] + timedelta(minutes=1) if reviewed else None, "note": note})
        return r["id"]

    async def seed_live(self):
        await self.seed_players()
        await self.seed_lobbies()
        await self.seed_game("A", number=1)
        await self.seed_game("B", number=2)
        rows = fx.live_rows()
        games = ["A", "A", "B", "B", "C2", "C3"]
        for r, game in zip(rows, games):
            await self.seed_row(r, game)
        return rows

    async def statuses(self):
        async with self.seed.connect() as conn:
            res = await conn.execute(text(
                "SELECT id, status, reviewed_by, reviewed_at IS NOT NULL AS rv, review_note"
                " FROM match_report_quarantine ORDER BY created_at, id"))
            return {str(r.id): (r.status, r.reviewed_by, r.rv, r.review_note) for r in res}

    async def post(self, body, key=tq.INTERNAL_KEY):
        return await self.client.post(POSTED, json=body, headers={"X-Internal-Key": key} if key else {})


LIVE_IDS = [str(r["id"]) for r in fx.live_rows()]
A1, A2, B1, B2, C2, C3 = LIVE_IDS


# ── the janitor ────────────────────────────────────────────────────────────

NOTE_A = ("auto-filed: same result as the recorded game b8ffc875f9d8; kills differ for 2 players "
          "(Heron 19 against 18, Iris 23 against 24) (held report against recorded game)")
NOTE_B = ("auto-filed: same result as the recorded game 5e1f00d277aa; kills differ for 1 player "
          "(Heron 33 against 34) (held report against recorded game)")


def test_pg_qdig_the_janitor_files_the_four_live_contradiction_rows(monkeypatch):
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            before = await env.checksums(("ffa_matches", "ffa_match_players", "ffa_lobbies", "players"))
            first = await main._qdig_janitor_pass()
            after_first = await env.statuses()
            word = main._qdig_needs_decision_word()
            second = await main._qdig_janitor_pass()
            after = await env.checksums(("ffa_matches", "ffa_match_players", "ffa_lobbies", "players"))
            return first, second, after_first, await env.statuses(), word, before, after

    first, second, st1, st2, word, before, after = run(body())
    assert (first, second) == (4, 0)
    assert st1 == st2
    for qid, note in ((A1, NOTE_A), (A2, NOTE_A), (B1, NOTE_B), (B2, NOTE_B)):
        assert st1[qid] == ("filed", None, True, note), st1[qid]
    for qid in (C2, C3):
        assert st1[qid] == ("pending", None, False, None)
    assert word == 2
    assert before == after          # the janitor writes the held table only


def test_pg_qdig_the_janitor_leaves_reviewed_rows_and_needs_decision_rows(monkeypatch):
    """A discarded row of the same numbers, an accepted one, and a pending
    row an admin already reviewed are all left alone; a pending row whose
    kills cross 50 stays pending."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_players()
            await env.seed_lobbies()
            await env.seed_game("A")
            await env.seed_game("B", number=2, recorded=[(4, 16, 51), (4, 14, 34), (5, 11, 19), (3, 11, 13)])
            ids = {}
            for st in ("discarded", "accepted"):
                ids[st] = await env.seed_row(fx.row("A", keyed=False), "A", status=st, reviewed=True,
                                             note="admin note")
            r = fx.row("A", keyed=False)
            ids["reviewed_pending"] = await env.seed_row(r, "A", reviewed=True, note="looked at it")
            ids["crosses"] = await env.seed_row(fx.row("B", body=fx.payload(
                "B", [(4, 16, 49), (4, 14, 34), (5, 11, 19), (3, 11, 13)])), "B")
            filed = await main._qdig_janitor_pass()
            return filed, ids, await env.statuses()

    filed, ids, st = run(body())
    assert filed == 0
    assert st[str(ids["discarded"])] == ("discarded", None, True, "admin note")
    assert st[str(ids["accepted"])] == ("accepted", None, True, "admin note")
    assert st[str(ids["reviewed_pending"])] == ("pending", None, True, "looked at it")
    assert st[str(ids["crosses"])] == ("pending", None, False, None)


def test_pg_qdig_the_predicate_is_re_read_under_the_lock(monkeypatch):
    """An admin discards the second candidate after the janitor read its
    candidates and before it locked that row: the janitor leaves it."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            real = main._qdig_load
            calls = []

            async def load(db, rows, admit=None):
                if not calls:
                    await env.ex("UPDATE match_report_quarantine SET status='discarded', reviewed_at=NOW(),"
                                 " review_note='by an admin' WHERE id=CAST(:i AS uuid)", {"i": A2})
                calls.append(1)
                return await real(db, rows, admit=admit)
            monkeypatch.setattr(main, "_qdig_load", load)
            filed = await main._qdig_janitor_pass()
            return filed, await env.statuses()

    filed, st = run(body())
    assert filed == 3
    assert st[A2] == ("discarded", None, True, "by an admin")
    assert st[A1][0] == st[B1][0] == st[B2][0] == "filed"


@pytest.mark.parametrize("held_lock", ["accept", "discard"])
def test_pg_qdig_a_row_an_admin_is_acting_on_is_skipped_not_waited_for(monkeypatch, held_lock):
    """The accept route's SELECT ... FOR UPDATE, and the discard route's
    UPDATE (FOR NO KEY UPDATE), each held open on row A1: the janitor's
    FOR UPDATE SKIP LOCKED passes over A1 and files the other three, at once;
    the next pass files A1."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            conn = await tq._pg(env.url)
            try:
                tr = conn.transaction()
                await tr.start()
                if held_lock == "accept":
                    await conn.execute("SELECT * FROM match_report_quarantine WHERE id=$1 AND status='pending'"
                                       " FOR UPDATE", uuid.UUID(A1))
                else:
                    await conn.execute("UPDATE match_report_quarantine SET review_note='x' WHERE id=$1"
                                       " AND status='pending'", uuid.UUID(A1))
                t0 = asyncio.get_running_loop().time()
                first = await asyncio.wait_for(main._qdig_janitor_pass(), timeout=10)
                took = asyncio.get_running_loop().time() - t0
                await tr.rollback()
            finally:
                await conn.close()
            second = await main._qdig_janitor_pass()
            return first, second, took, await env.statuses()

    first, second, took, st = run(body())
    assert (first, second) == (3, 1)
    assert took < 5.0
    assert st[A1][0] == "filed"


def test_pg_qdig_the_pass_is_bounded_and_its_cursor_reaches_every_row(monkeypatch):
    """25 FOR THE RECORD rows: the first pass judges 20, the second the
    other 5; a NEEDS A DECISION row at the head never hides the rows behind."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_players()
            await env.seed_lobbies()
            head = await env.seed_row(fx.row("A", reason="ffa_game_contradiction", keyed=False,
                                             body=fx.payload("A", [(5, 14, 31), (4, 10, 30), (4, 11, 24),
                                                                   (3, 8, 13)]),
                                             created=fx.T_LIVE - timedelta(days=1)), "A")
            await env.seed_game("A")
            for n in range(25):
                room = f"QDIGBOUND_{n:06d}_r1"
                await env.seed_game("A", room=room, mid=uuid.uuid4(), number=n + 2)
                body_ = dict(fx.payload("A"), photon_room_id=room)
                await env.seed_row(dict(fx.row("A", body=body_, created=fx.T_LIVE + timedelta(minutes=n)),
                                        photon_room_id=room), "A")
            counts = [await main._qdig_janitor_pass() for _ in range(3)]
            return head, counts, await env.statuses()

    head, counts, st = run(body())
    assert counts == [19, 6, 0]          # the head row is a candidate (kills 30 against 18) and stays
    assert st[str(head)][0] == "pending"
    assert sum(1 for v in st.values() if v[0] == "filed") == 25


def test_pg_qdig_the_census_runs_at_most_every_five_minutes_or_after_a_filing(monkeypatch):
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            clock = types.SimpleNamespace(t=10_000.0)
            real_time = main.time

            class _Time:
                """main's time module, its monotonic clock the test's own
                (the event loop's clock is left alone)."""
                def __getattr__(self, name):
                    return getattr(real_time, name)

                @staticmethod
                def monotonic():
                    return clock.t
            monkeypatch.setattr(main, "time", _Time())
            await main._qdig_janitor_pass()                       # files 4, counts 2
            w1 = main._qdig_needs_decision_word()
            await env.ex("UPDATE match_report_quarantine SET status='discarded', reviewed_at=NOW()"
                         " WHERE id=CAST(:i AS uuid)", {"i": C2})
            clock.t += 60
            await main._qdig_janitor_pass()                       # files nothing, 60 s: no census
            w2 = main._qdig_needs_decision_word()
            clock.t += main.QDIG_COUNT_EVERY_S
            await main._qdig_janitor_pass()                       # 5 minutes on: the census again
            return w1, w2, main._qdig_needs_decision_word()

    assert run(body()) == (2, 2, 1)


def test_qdig_the_loop_runs_the_pass_isolated_and_time_boxed():
    import inspect
    src = inspect.getsource(main.queue_cleanup_loop)
    i = src.index("_qdig_janitor_pass()")
    block = src[src.rindex("try:", 0, i):src.index("[QDIG] janitor pass error", i)]
    assert "asyncio.wait_for(_qdig_janitor_pass(), timeout=QDIG_PASS_TIMEOUT_S)" in block
    assert src.count("_qdig_janitor_pass()") == 1
    assert main.QDIG_PASS_TIMEOUT_S <= 30


# ── the posted route ───────────────────────────────────────────────────────

def test_pg_qdig_the_posted_route_stamps_once_and_only_pending_rows(monkeypatch):
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            await main._qdig_janitor_pass()
            out = {"new": (await env.post({"kind": "new", "ids": [C2, A1]})).json(),
                   "again": (await env.post({"kind": "new", "ids": [C2, C3]})).json(),
                   "rem": (await env.post({"kind": "reminder", "ids": [C2, C3, B1]})).json()}
            async with env.seed.connect() as conn:
                res = await conn.execute(text("SELECT id, digest_posted_at IS NOT NULL AS p,"
                                              " digest_reminded_at IS NOT NULL AS r FROM match_report_quarantine"))
                out["cols"] = {str(r.id): (r.p, r.r) for r in res}
            out["bad"] = [(await env.post(b)).status_code for b in (
                {"kind": "other", "ids": [C2]}, {"kind": "new", "ids": []}, {"kind": "new", "ids": ["nope"]},
                {"kind": "new", "ids": [str(uuid.uuid4()) for _ in range(201)]}, {"kind": "new", "ids": C2})]
            out["key"] = [(await env.post({"kind": "new", "ids": [C2]}, key=k)).status_code for k in (None, "wrong")]
            return out

    out = run(body())
    assert out["new"] == {"kind": "new", "marked": 1, "ignored": 1}           # A1 is filed
    assert out["again"] == {"kind": "new", "marked": 1, "ignored": 1}         # C2 already posted
    assert out["rem"] == {"kind": "reminder", "marked": 2, "ignored": 1}
    assert out["cols"][C2] == (True, True) and out["cols"][C3] == (True, True)
    assert out["cols"][A1] == (False, False) and out["cols"][B1] == (False, False)
    assert out["bad"] == [422] * 5
    assert out["key"] == [403, 403]


# ── D1, read by both bots ──────────────────────────────────────────────────

class RealFeed:
    """The bot's http session over a D1 answer the real route gave, and the
    real posted route."""

    def __init__(self, env, body):
        self.env, self.body, self.posts = env, body, []

    def get(self, url, params=None, headers=None, timeout=None):
        return tb._Resp(200, self.body)

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append(json)
        return tb._Resp(200, {})


def test_pg_qdig_d1_adds_keys_that_carry_names_and_no_ids(monkeypatch):
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            return tq.ok(await env.d1())

    d = run(body())
    assert d["qdig"] == 1
    assert [r["id"] for r in d["rows"]] == [C2, C3, A1, A2, B1, B2]      # D1's order: created_at, id
    assert [r["class"] for r in d["rows"]] == ["needs_decision"] * 2 + ["for_the_record"] * 4
    assert d["totals"]["needs_decision_games"] == 2 and d["totals"]["reminder_due"] is False
    base_keys = {"id", "mode", "group", "family", "created_at"}
    for r in d["rows"]:
        added = json.dumps({k: v for k, v in r.items() if k not in base_keys})
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-", added), added
        assert not re.search(r"\d{17}", added), added
        assert "QDIGROOM" not in added
    c2 = d["rows"][0]
    assert c2["reason_text"].startswith("The lobby had already been closed")
    assert [p["name"] for p in c2["players"]] == ["Ash", "Birch", "Cedar", "Dune", "Elm", "Fern"]
    assert c2["winner_name"] == "Dune" and c2["reporter_name"] == "Ash" and c2["game_number"] == 2
    assert d["rows"][2]["game_key"] == d["rows"][3]["game_key"] != d["rows"][4]["game_key"]


def test_pg_qdig_both_bots_read_the_real_answer(monkeypatch):
    """The bot after QDIG-1 posts the two NEEDS games and records them
    through the real posted route; the bot before QDIG-1 posts today's form
    for every pending row without an error."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            await main._qdig_janitor_pass()
            d = tq.ok(await env.d1())
            nf = RealFeed(env, d)
            ns, ch_new, _ = tb.new_bot(nf)
            await ns["poll_quarantine_digest"]()
            for p in nf.posts:
                assert (await env.post(p)).status_code == 200
            d2 = tq.ok(await env.d1())
            ns2, ch_again, _ = tb.new_bot(RealFeed(env, d2))           # a restart
            await ns2["poll_quarantine_digest"]()
            of = RealFeed(env, d)
            ons, ch_old, clock = tb.old_bot(of)
            qb.settle_state(ons, clock)
            await ons["poll_quarantine_digest"]()
            return d, nf.posts, tb.texts(ch_new), tb.texts(ch_again), tb.texts(ch_old), ons["_out"]

    d, posts, new, again, old, old_out = run(body())
    assert [r["id"] for r in d["rows"]] == [C2, C3]
    assert len(new) == 1 and new[0].count("**FFA, 6 players, ranked**") == 2
    assert "[c2c2c2c2]" in new[0] and "[c3c3c3c3]" in new[0]
    assert posts == [{"kind": "new", "ids": [C2, C3]}]
    assert again == []
    assert len(old) == 1 and qb.ids_in(old[0]) == [C2, C3]
    assert not [line for line in old_out if "error" in line]


# ── the Admin list ─────────────────────────────────────────────────────────

ADMIN_KEYS = {"id", "mode", "reason", "score", "http_status", "created_at", "player_names", "room", "status",
              "can_accept", "accept_blocked_reason"}


def test_pg_qdig_the_admin_lists_strings(monkeypatch):
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            await main._qdig_janitor_pass()
            # A later rated game for the six October players blocks Accept.
            mid = uuid.uuid4()
            await env.ex("INSERT INTO ffa_matches (id, lobby_id, photon_room_id, player_count, winner_id,"
                         " ended_at, created_at, game_number) VALUES (:i, :l, 'QDIGLATER_r1', 6, :w, :e, :e, 9)",
                         {"i": mid, "l": fx.LOBBY_C, "w": pid(14), "e": fx.T_OCT + timedelta(days=2)})
            await env.exmany("INSERT INTO ffa_match_players (match_id, player_id) VALUES (:m, :p)",
                             [{"m": mid, "p": pid(s)} for s in fx.GAMES["C2"]["seats"]])
            resp = await env.client.get(ADMIN_LIST, params={"admin_steam_id": tq.ADMIN,
                                                            "hmac_signature": tq.sig("list")})
            return tq.ok(resp)

    rep = run(body())["reports"]
    assert [r["id"] for r in rep] == [C3, C2]
    for r in rep:
        assert set(r) == ADMIN_KEYS
        assert len(r["reason"]) <= 140 and len(r["score"]) <= 64
        assert r["can_accept"] is False
    c2 = rep[1]
    assert c2["reason"] == ("The lobby had already been closed when this report arrived, so the game was "
                            "never recorded. [lobby_completed]")
    assert c2["score"] == "Dune 5r 11p | Elm 2r 5p | Ash 0r 2p | Birch 0r 2p | +2"
    assert c2["accept_blocked_reason"] == ("6 players have played rated games since; adding this game now "
                                           "would need a full replay")


# ── /health ────────────────────────────────────────────────────────────────

def test_pg_qdig_health_carries_the_build_and_the_census(monkeypatch):
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            api = [r for r in main.app.routes if getattr(r, "path", None) == HEALTH]
            env.app.add_api_route(HEALTH, api[0].endpoint, methods=["GET"], response_model=api[0].response_model)
            before = tq.ok(await env.client.get(HEALTH))
            await main._qdig_janitor_pass()
            after = tq.ok(await env.client.get(HEALTH))
            env.app.dependency_overrides[main.get_db] = lambda: tq._RjTriageUnreachable()
            down = (await env.client.get(HEALTH)).json()
            return before, after, down

    before, after, down = run(body())
    assert (before["qdig_build"], before["quarantine_needs_decision"]) == (1, -1)
    assert (after["qdig_build"], after["quarantine_needs_decision"]) == (1, 2)
    assert (down["qdig_build"], down["quarantine_needs_decision"]) == (1, 2)


# ── migration 419 ──────────────────────────────────────────────────────────

BASE_169 = (SQL_DIR / "169_match_report_quarantine.sql").read_text(encoding="utf-8")


async def _fresh(conn):
    await conn.execute("DROP TABLE IF EXISTS match_report_quarantine CASCADE; DROP TABLE IF EXISTS players CASCADE;"
                       " CREATE TABLE players (id UUID PRIMARY KEY);")
    await conn.execute(BASE_169)
    await conn.execute("INSERT INTO match_report_quarantine (mode, reason, http_status, payload, status)"
                       " VALUES ('ffa', 'lobby_completed', 409, '{}'::jsonb, 'pending')")


async def _cols(conn):
    return {r["column_name"]: r["data_type"] for r in await conn.fetch(
        "SELECT column_name, data_type FROM information_schema.columns"
        " WHERE table_name='match_report_quarantine' AND column_name LIKE 'digest_%'")}


async def _status_comment(conn):
    return await conn.fetchval("SELECT col_description('match_report_quarantine'::regclass,"
                               " (SELECT attnum FROM pg_attribute WHERE attrelid='match_report_quarantine'::regclass"
                               " AND attname='status'))")


def test_pg_qdig_migration_419_applies_twice_refuses_and_rolls_back():
    url = tq.make_url(tq.require_pg())
    m419, r419 = M419.read_text(encoding="utf-8"), R419.read_text(encoding="utf-8")

    async def body():
        conn = await tq._pg(url)
        out = {}
        try:
            await _fresh(conn)
            await conn.execute(m419)
            await conn.execute(m419)
            out["cols"] = await _cols(conn)
            out["comment"] = await _status_comment(conn)
            out["rows"] = await conn.fetchval("SELECT COUNT(*) FROM match_report_quarantine")
            await conn.execute(r419)
            await conn.execute(r419)
            out["cols_after_rollback"] = await _cols(conn)
            out["comment_after_rollback"] = await _status_comment(conn)
            refusals = {}
            for name, prep in (
                ("check", "ALTER TABLE match_report_quarantine ADD CONSTRAINT q_st CHECK"
                          " (status IN ('pending','accepted','discarded'))"),
                ("type", "ALTER TABLE match_report_quarantine ADD COLUMN digest_posted_at TEXT"),
                ("status_type", "ALTER TABLE match_report_quarantine ALTER COLUMN status TYPE VARCHAR(8)"),
            ):
                await _fresh(conn)
                await conn.execute(prep)
                try:
                    await conn.execute(m419)
                    refusals[name] = None
                except Exception as ex:
                    refusals[name] = type(ex).__name__
                    await conn.execute("ROLLBACK")      # what psql's exit does to the open block
                    refusals[name + "_cols"] = await _cols(conn)
                    refusals[name + "_comment"] = await _status_comment(conn)
            out["refusals"] = refusals
            await conn.execute("DROP TABLE IF EXISTS match_report_quarantine CASCADE")
            try:
                await conn.execute(m419)
                out["missing"] = None
            except Exception as ex:
                out["missing"] = type(ex).__name__
        finally:
            await conn.close()
        return out

    out = run(body())
    assert out["cols"] == {"digest_posted_at": "timestamp with time zone",
                           "digest_reminded_at": "timestamp with time zone"}
    assert "filed" in out["comment"] and out["rows"] == 1
    assert out["cols_after_rollback"] == {} and out["comment_after_rollback"] is None
    r = out["refusals"]
    assert r["check"] == r["status_type"] == r["type"] == "RaiseError"
    assert r["check_cols"] == {} and r["status_type_cols"] == {}
    assert r["type_cols"] == {"digest_posted_at": "text"}
    assert r["check_comment"] is None and r["type_comment"] is None and r["status_type_comment"] is None
    assert out["missing"] == "RaiseError"


def test_qdig_migration_419_shape():
    sql = M419.read_text(encoding="utf-8")
    assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1
    assert "SET LOCAL lock_timeout" in sql
    assert "ADD COLUMN IF NOT EXISTS digest_posted_at TIMESTAMPTZ" in sql
    assert "ADD COLUMN IF NOT EXISTS digest_reminded_at TIMESTAMPTZ" in sql
    assert "ADD CONSTRAINT" not in sql.upper()
    rb = R419.read_text(encoding="utf-8")
    assert rb.count("BEGIN;") == 1 and rb.count("COMMIT;") == 1
