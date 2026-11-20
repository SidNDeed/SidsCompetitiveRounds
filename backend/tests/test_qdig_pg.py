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
from asyncpg.exceptions import LockNotAvailableError
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
    candidates and before it locked that row: the janitor leaves it. The
    LOCK's own re-read is what leaves it: the row is never judged (its
    facts are never read), not merely refused by the filing UPDATE."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            real = main._qdig_load
            calls = []

            async def load(db, rows, deadline_check=None):
                if not calls:
                    await env.ex("UPDATE match_report_quarantine SET status='discarded', reviewed_at=NOW(),"
                                 " review_note='by an admin' WHERE id=CAST(:i AS uuid)", {"i": A2})
                calls.append([str(r["id"]) for r, _b in rows])
                return await real(db, rows, deadline_check=deadline_check)
            monkeypatch.setattr(main, "_qdig_load", load)
            filed = await main._qdig_janitor_pass()
            return filed, await env.statuses(), calls

    filed, st, calls = run(body())
    judged = [i for ids in calls for i in ids]
    assert A2 not in judged, "the janitor judged a row its lock should have re-read as reviewed"
    assert filed == 3
    assert st[A2] == ("discarded", None, True, "by an admin")
    assert st[A1][0] == st[B1][0] == st[B2][0] == "filed"


@pytest.mark.parametrize("held_lock", ["accept", "discard"])
def test_pg_qdig_a_row_an_admin_is_acting_on_is_skipped_not_waited_for(monkeypatch, held_lock, capsys):
    """The accept route's SELECT ... FOR UPDATE, and the discard route's
    UPDATE (FOR NO KEY UPDATE), each held open on row A1: the janitor's
    FOR UPDATE SKIP LOCKED passes over A1 and files the other three, at once;
    the next pass files A1. SKIPPED, not failed: no row is reported as not
    judged (a lock that waits until the statement timeout, or one that
    refuses with an error, ends in that line)."""
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
    out = capsys.readouterr().out
    assert "not judged" not in out, f"the held row was not skipped: {out}"
    assert (first, second) == (3, 1)
    assert took < 5.0
    assert st[A1][0] == "filed"


# The filing UPDATE's own re-check (_QDIG_SQL_JANITOR_FILE: status
# 'pending', reviewed_at and reviewed_by NULL) cannot be made to matter
# while the lock statement stands: _QDIG_SQL_JANITOR_LOCK takes FOR UPDATE,
# which conflicts with every writer of the row (the accept route's FOR
# UPDATE and the discard route's UPDATE, FOR NO KEY UPDATE), and the janitor
# holds it from the lock statement through the filing UPDATE in ONE
# transaction, so no review can land between the two. The mutant that drops
# the re-check alone (file_without_recheck) is therefore EQUIVALENT, and the
# re-check stays: it is the guard that remains if the lock statement is ever
# changed (lesson 1070). The test below shows the pair: a review that lands
# between the lock and the filing is held off by the lock, or refused by the
# re-check; only with BOTH gone does it get through and the reviewed row is
# filed over it.

def test_pg_qdig_the_lock_and_the_filing_recheck_each_guard_a_concurrent_review(monkeypatch):
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            real = main._qdig_load
            applied = []

            async def load(db, rows, deadline_check=None):
                ids = [str(r["id"]) for r, _b in rows]
                if not applied and ids == [A1]:
                    conn = await tq._pg(env.url)
                    try:
                        await conn.execute("SET lock_timeout = '500ms'")
                        try:
                            await conn.execute("UPDATE match_report_quarantine SET status='discarded',"
                                               " reviewed_at=NOW(), review_note='by an admin'"
                                               " WHERE id=$1 AND status='pending'", uuid.UUID(A1))
                            applied.append(True)
                        except LockNotAvailableError:
                            # the janitor's row lock held it off: lock_timeout
                            # (SQLSTATE 55P03); any other error fails the test
                            applied.append(False)
                    finally:
                        await conn.close()
                return await real(db, rows, deadline_check=deadline_check)
            monkeypatch.setattr(main, "_qdig_load", load)
            await main._qdig_janitor_pass()
            return applied, await env.statuses()

    applied, st = run(body())
    assert applied in ([True], [False])
    if applied == [True]:
        assert st[A1] == ("discarded", None, True, "by an admin"), (
            f"a review that landed between the lock and the filing was filed over: {st[A1]}")
    else:
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


def _own_clock(monkeypatch):
    clock = types.SimpleNamespace(t=10_000.0)
    real_time = main.time

    class _Time:
        """main's time module, its monotonic clock the test's own (the
        event loop's clock is left alone)."""
        def __getattr__(self, name):
            return getattr(real_time, name)

        @staticmethod
        def monotonic():
            return clock.t
    monkeypatch.setattr(main, "time", _Time())
    return clock


def _count_censuses(monkeypatch):
    calls = []
    real = main._qdig_needs_games

    def counted(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(main, "_qdig_needs_games", counted)
    return calls


def test_pg_qdig_the_census_runs_at_most_every_five_minutes_filing_or_not(monkeypatch):
    """LOW 2: a pass that files a row runs no census before its interval; a
    pass runs its census after its filing step whenever the census is due."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            clock = _own_clock(monkeypatch)
            calls = _count_censuses(monkeypatch)
            f1 = await main._qdig_janitor_pass()                  # files 4, counts 2
            w1 = main._qdig_needs_decision_word()
            await env.ex("UPDATE match_report_quarantine SET status='discarded', reviewed_at=NOW()"
                         " WHERE id=CAST(:i AS uuid)", {"i": C2})
            # A third report of game A, from Juniper: FOR THE RECORD, filed at t+60.
            await env.seed_row(fx.row("A", keyed=False, body=fx.payload("A", reporter=4),
                                      qid="0a0a0a0a-0000-4000-8000-0000000000a9",
                                      created=fx.T_LIVE + timedelta(minutes=40)), "A", reporter=4)
            clock.t += 60
            f2 = await main._qdig_janitor_pass()                  # files 1, 60 s on: no census
            w2, c2 = main._qdig_needs_decision_word(), len(calls)
            clock.t += main.QDIG_COUNT_EVERY_S
            await main._qdig_janitor_pass()                       # 5 minutes on: the census again
            return f1, f2, w1, w2, c2, main._qdig_needs_decision_word(), len(calls)

    f1, f2, w1, w2, c2, w3, c3 = run(body())
    assert (f1, f2) == (4, 1)
    assert c2 == 1, "a pass that filed a row ran a census inside the five minutes"
    assert (w1, w2, w3, c3) == (2, 2, 1, 2)


def test_qdig_a_timed_out_pass_is_cancelled_its_session_closed_and_the_next_duty_runs(monkeypatch):
    """M5: the janitor loop's QDIG-1 duty with a pass that never ends (its
    session open on a statement that does not return): the duty returns
    within its time box, the pass is cancelled and its session closed, and
    the loop's next duty runs. A pass that raises is the same."""
    closed = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, et, ev, tb_):
            closed.append(et)
            return False

    async def hung():
        async with Session():
            await asyncio.sleep(3600)

    async def broken():
        async with Session():
            raise RuntimeError("the database went away")

    monkeypatch.setattr(main, "QDIG_PASS_TIMEOUT_S", 0.05)
    order = []

    async def loop_tick(pass_fn):
        monkeypatch.setattr(main, "_qdig_janitor_pass", pass_fn)
        await main._qdig_janitor_step()
        order.append("next duty")

    async def body():
        t0 = asyncio.get_running_loop().time()
        await loop_tick(hung)
        took = asyncio.get_running_loop().time() - t0
        await loop_tick(broken)
        return took

    took = run(body())
    assert order == ["next duty", "next duty"], "a timed-out or failing pass stopped the duty after it"
    assert took < 2.0
    assert closed == [asyncio.CancelledError, RuntimeError]
    # The loop calls the duty bare: nothing between it and the next duty
    # can be skipped by an exception it raised, because it raises none.
    import ast as _ast
    import inspect
    loop = _ast.parse(textwrap_dedent(inspect.getsource(main.queue_cleanup_loop)))
    calls = [n for n in _ast.walk(loop) if isinstance(n, _ast.Await) and isinstance(n.value, _ast.Call)
             and getattr(n.value.func, "id", None) == "_qdig_janitor_step"]
    assert len(calls) == 1
    # Read the CODE, never the text: a comment that names the pass is not a call.
    names = {n.id for n in _ast.walk(loop) if isinstance(n, _ast.Name)}
    names |= {n.attr for n in _ast.walk(loop) if isinstance(n, _ast.Attribute)}
    assert "_qdig_janitor_pass" not in names, "the loop reaches the pass without its step"


def textwrap_dedent(s):
    import textwrap
    return textwrap.dedent(s)


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
              "can_accept", "accept_blocked_reason", "can_credit"}


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
            first = tq.ok(resp)
            # Lobby C as the live rows left it carries no frozen roster
            # (member_ids is the column's empty default); with its six seats
            # as its roster, the verdict reaches the gate.
            await env.ex("UPDATE ffa_lobbies SET member_ids = CAST(:m AS uuid[]) WHERE id = :l",
                         {"m": [pid(s) for s in fx.GAMES["C2"]["seats"]], "l": fx.LOBBY_C})
            resp = await env.client.get(ADMIN_LIST, params={"admin_steam_id": tq.ADMIN,
                                                            "hmac_signature": tq.sig("list")})
            return first, tq.ok(resp)

    listed, rostered = run(body())
    rep = listed["reports"]
    assert [r["id"] for r in rep] == [C3, C2]
    for r in rep:
        assert set(r) == ADMIN_KEYS
        assert len(r["reason"]) <= 140 and len(r["score"]) <= 64
        assert r["can_accept"] is False
    c2 = rep[1]
    assert c2["reason"] == ("The lobby had already been closed when this report arrived, so the game was "
                            "never recorded. [lobby_completed]")
    assert c2["score"] == "Dune 5r 11p | Elm 2r 5p | Ash 0r 2p | Birch 0r 2p | +2"
    # QAPPLY-1: the verdict is _qapply_verdict's, from the verifications
    # Accept's body and Credit make, in the body's order. With no frozen
    # roster, the report's players are not the lobby's roster.
    assert c2["accept_blocked_reason"] == main._QAPPLY_TEXTS["roster"]
    # With the roster, the gate decides: the later game is game 9 of C2's own
    # lobby, so its end is the lobby's previous game for C2, and C2 was
    # received before it (R5).
    c2 = {r["id"]: r for r in rostered["reports"]}[C2]
    assert (c2["can_accept"], c2["accept_blocked_reason"]) == (False, main._QAPPLY_TEXTS["clock"])


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


# ── review qdig-r1 ─────────────────────────────────────────────────────────

BAD = "0bad0bad-0000-4000-8000-000000000bad"


async def _seed_body(env, body, *, qid=BAD, game="C2", keyed=False, status="pending", created=None):
    r = fx.row(game, keyed=keyed, body=body, qid=qid, created=created)
    return await env.seed_row(r, game, status=status)


def test_pg_qdig_an_oversize_body_never_reaches_python(monkeypatch):
    """HIGH 4: a body whose text is over QDIG_BODY_MAX_BYTES comes back from
    every statement of the lane as NULL with its over-size mark; the row
    reads MALFORMED (oversize), NEEDS A DECISION, and is never filed."""
    big = dict(fx.payload("A"), padding="x" * 300000)

    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            await _seed_body(env, big, game="A")
            async with env.seed.connect() as conn:
                d = (await conn.execute(text(main._QDIG_SQL_D1_DETAIL), {
                    "ids": [BAD], "body_max": main.QDIG_BODY_MAX_BYTES,
                    "budget": main.QDIG_DECODE_BUDGET_BYTES})).mappings().all()
                lk = (await conn.execute(text(main._QDIG_SQL_JANITOR_LOCK), {
                    "id": BAD, "body_max": main.QDIG_BODY_MAX_BYTES})).mappings().all()
            await main._qdig_janitor_pass()
            feed = tq.ok(await env.d1())
            admin = tq.ok(await env.client.get(ADMIN_LIST, params={"admin_steam_id": tq.ADMIN,
                                                                   "hmac_signature": tq.sig("list")}))
            return d, lk, await env.statuses(), feed, admin

    d, lk, st, feed, admin = run(body())
    assert d[0]["payload"] is None, "the D1 detail statement handed an over-size body to Python"
    assert d[0]["payload_oversize"] is True
    assert lk[0]["payload"] is None and lk[0]["payload_oversize"] is True
    assert st[BAD][0] == "pending"
    (row,) = [r for r in feed["rows"] if r["id"] == BAD]
    assert row["class"] == "needs_decision" and row["malformed"] == "oversize" and row["players"] == []
    (adm,) = [r for r in admin["reports"] if r["id"] == BAD]
    assert adm["reason"].startswith("The stored report cannot be read (oversize)") and adm["score"] == ""


def test_pg_qdig_a_malformed_body_does_not_stop_the_feed_or_the_list(monkeypatch):
    """HIGH 5: a pending row whose body is {"players": 1}: D1, the Admin list
    and the census answer, and the row NEEDS A DECISION."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            await _seed_body(env, {"players": 1})
            await main._qdig_janitor_pass()
            feed = await env.d1()
            admin = await env.client.get(ADMIN_LIST, params={"admin_steam_id": tq.ADMIN,
                                                            "hmac_signature": tq.sig("list")})
            return feed, admin, main._qdig_needs_decision_word()

    feed, admin, word = run(body())
    d = tq.ok(feed)
    (row,) = [r for r in d["rows"] if r["id"] == BAD]
    assert row["class"] == "needs_decision" and row["malformed"] == "players"
    assert BAD in [r["id"] for r in tq.ok(admin)["reports"]]
    assert word == 3


def test_pg_qdig_the_janitor_never_files_a_malformed_report(monkeypatch):
    """HIGH 1: game A's held numbers with two players on slot 0 (a capture
    that runs before the settlement's slot check keeps such a body)."""
    dup = fx.payload("A")
    dup["players"][1]["slot"] = 0

    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            await _seed_body(env, dup, game="A")
            filed = await main._qdig_janitor_pass()
            return filed, await env.statuses()

    filed, st = run(body())
    assert st[BAD][0] == "pending", "a report with two players on one slot was filed"
    assert filed == 4


def test_pg_qdig_the_decode_budget_leaves_later_rows_unread_and_the_census_says_so(monkeypatch):
    """A statement hands Python at most QDIG_DECODE_BUDGET_BYTES of body
    text: with the budget below two bodies, D1 describes the first rows (the
    unposted first) and leaves the rest with class None; the census reads
    -1."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            await main._qdig_janitor_pass()
            n_full = main._qdig_needs_decision_word()
            async with env.seed.connect() as conn:
                one = (await conn.execute(text(
                    "SELECT max(octet_length(payload::text)) FROM match_report_quarantine"))).scalar()
            monkeypatch.setattr(main, "QDIG_DECODE_BUDGET_BYTES", one + 10)
            monkeypatch.setattr(main, "_qdig_state", {"needs_decision": -1, "count_at": None, "after": None})
            await main._qdig_janitor_pass()
            return n_full, tq.ok(await env.d1()), main._qdig_needs_decision_word()

    n_full, d, word = run(body())
    assert n_full == 2
    assert [r["class"] for r in d["rows"]] == ["needs_decision", None]
    assert d["totals"]["needs_decision_complete"] is False
    assert word == -1


def test_pg_qdig_the_census_reads_minus_one_past_its_row_bound(monkeypatch):
    """LOW 1: more pending rows than QDIG_CENSUS_MAX_ROWS: -1, never a
    truncated count."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_players()
            await env.seed_lobbies()
            await env.ex(
                "INSERT INTO match_report_quarantine (mode, reason, http_status, group_id, photon_room_id, payload,"
                " status, created_at)"
                " SELECT 'ffa', 'lobby_completed', 409, NULL, 'QDIGMANY_' || n, CAST(:pl AS JSONB), 'pending',"
                "        now() - make_interval(secs => n)"
                "   FROM generate_series(1, 201) n",
                {"pl": json.dumps(fx.payload("C2"))})
            await main._qdig_janitor_pass()
            return main._qdig_needs_decision_word()

    assert run(body()) == -1


def test_pg_qdig_filed_rows_count_against_the_quota_and_are_still_recognised(monkeypatch):
    """M1: the capture's held-row quota and its variant search count FILED
    rows as they count pending ones."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_players()
            await env.seed_lobbies()
            g = fx.LOBBY_AB
            pl = json.dumps(fx.payload("A"))
            await env.ex(
                "INSERT INTO match_report_quarantine (mode, reason, http_status, group_id, photon_room_id, payload,"
                " status, created_at, reviewed_at)"
                " SELECT 'ffa', 'ffa_game_contradiction', 409, :g, 'QDIGQUOTA_' || n, CAST(:pl AS JSONB),"
                "        CASE WHEN n <= 4 THEN 'filed' ELSE 'pending' END, now(),"
                "        CASE WHEN n <= 4 THEN now() END"
                "   FROM generate_series(1, 50) n", {"g": g, "pl": pl})
            quota = await env.real_capture(mode="ffa", reason="ffa_game_contradiction", status_code=409,
                                           payload=fx.payload("B"), group_id=g, photon_room_id="QDIGQUOTA_new",
                                           reporter_id=None, player_ids=[])
            await env.ex("DELETE FROM match_report_quarantine")
            # A keyed row of room R, and a FILED variant of R with another body.
            room = fx.GAMES["A"]["room"]
            await env.ex(
                "INSERT INTO match_report_quarantine (mode, reason, http_status, group_id, photon_room_id, payload,"
                " status) VALUES ('ffa', 'ffa_game_contradiction', 409, :g, :r, CAST(:k AS JSONB), 'pending'),"
                " ('ffa', 'ffa_game_contradiction', 409, :g, NULL, CAST(:v AS JSONB), 'filed')",
                {"g": g, "r": room, "k": json.dumps(fx.payload("A", reporter=2)),
                 "v": json.dumps(fx.payload("A", reporter=3))})
            again = await env.real_capture(mode="ffa", reason="ffa_game_contradiction", status_code=409,
                                           payload=fx.payload("A", reporter=3), group_id=g, photon_room_id=room,
                                           reporter_id=None, player_ids=[])
            async with env.seed.connect() as conn:
                n = (await conn.execute(text(
                    "SELECT count(*) FROM match_report_quarantine WHERE photon_room_id IS NULL"))).scalar()
            return quota, again, n

    quota, again, n = run(body())
    assert quota == "quota", "four filed rows of fifty did not count against the quota"
    assert n == 1, "a redelivery of a filed variant was captured again"
    assert again == "variant"


def test_pg_qdig_a_repeated_reminder_inside_its_interval_keeps_its_stamp(monkeypatch):
    """M2: the same reminder acknowledged twice: the second marks nothing and
    the stamp stays."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()
            await main._qdig_janitor_pass()
            first = (await env.post({"kind": "reminder", "ids": [C2, C3]})).json()

            async def stamps():
                async with env.seed.connect() as conn:
                    res = await conn.execute(text(
                        "SELECT id, digest_reminded_at FROM match_report_quarantine WHERE digest_reminded_at"
                        " IS NOT NULL"))
                    return {str(r.id): r.digest_reminded_at for r in res}
            s1 = await stamps()
            await asyncio.sleep(0.05)
            second = (await env.post({"kind": "reminder", "ids": [C2, C3]})).json()
            await env.ex("UPDATE match_report_quarantine SET digest_reminded_at = NOW() - INTERVAL '25 hours'"
                         " WHERE id = CAST(:i AS uuid)", {"i": C2})
            third = (await env.post({"kind": "reminder", "ids": [C2, C3]})).json()
            return first, second, third, s1, await stamps()

    first, second, third, s1, s3 = run(body())
    assert first["marked"] == 2
    assert second["marked"] == 0, "a reminder acknowledged again inside 24 hours moved its stamp"
    assert third["marked"] == 1 and s3[C3] == s1[C3] and s3[C2] > s1[C2]


def test_pg_qdig_a_failed_eligibility_check_answers_one_fixed_sentence(monkeypatch):
    """M4: the later-rated lookup raises an error whose text carries a
    statement: accept_blocked_reason is one fixed sentence within 140."""
    async def body():
        async with QEnv(monkeypatch) as env:
            await env.seed_live()

            async def fails(*a, **k):
                raise RuntimeError("SELECT count(*) FROM ffa_match_players WHERE " + "x = 1 AND " * 40)
            # QAPPLY-1: the list's eligibility is _qapply_verdict's.
            monkeypatch.setattr(main, "_qapply_verdict", fails)
            return tq.ok(await env.client.get(ADMIN_LIST, params={"admin_steam_id": tq.ADMIN,
                                                                 "hmac_signature": tq.sig("list")}))

    rep = run(body())["reports"]
    assert rep
    for r in rep:
        assert len(r["accept_blocked_reason"]) <= 140, (
            "the blocked reason carries the exception's text: " + r["accept_blocked_reason"][:80])
        assert r["accept_blocked_reason"] == ("The server could not check whether these players have played "
                                              "since; try again later.")
        assert r["can_accept"] is False
