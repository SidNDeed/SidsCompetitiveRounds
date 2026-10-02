"""Seat evidence and the advisory review worker against a real PostgreSQL 16:
migration 368 applied twice, the route's session rule (M1), the first-record
rule and its conflict marker (M2), evidence before and after its match and
both seats racing (M3), the match path with the worker's statements failing
(M10), the absent state (A3), refused revisions leaving every count alone
(A4), shadow then posting under a SYNTHETIC revision (A8), re-evaluation on a
revision change, and the persisted dirty-sitting cursor (design report
finding 3).

One case schema per module run (the build replays every migration and takes
minutes), on one event loop. Each case uses its own stable keys and accounts.
Every rule value is synthetic (review_testkit). Live cases FAIL rather than
skip unless SEAT_EVIDENCE_TEST_PG_OPTOUT=1 (seat_evidence_pg)."""

import ast
import asyncio
import json
import os
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import main  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402
import seat_evidence as se  # noqa: E402
import seat_evidence_fixtures as fx  # noqa: E402
import seat_evidence_pg as sp  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

# Synthetic 16-digit seats per case (no Steam account has 16 digits).
M3_A, M3_B = fx.SEAT_A, fx.SEAT_B
M1_C = fx.SEAT_C
A8_A, A8_B = "1000000000000301", "1000000000000302"
A4_A, A4_B = "1000000000000401", "1000000000000402"
CU = ["1000000000000501", "1000000000000502", "1000000000000503",
      "1000000000000504", "1000000000000505", "1000000000000506",
      "1000000000000507", "1000000000000508"]


@pytest.fixture(scope="module")
def live():
    sp.require_live_pg()
    loop = asyncio.new_event_loop()
    cm = sp.case("sev")
    c, sm, snaps = loop.run_until_complete(cm.__aenter__())
    try:
        yield types.SimpleNamespace(run=loop.run_until_complete, case=c, sm=sm, snaps=snaps)
    finally:
        loop.run_until_complete(cm.__aexit__(None, None, None))
        loop.close()


def _armed_doc(post_since):
    doc = tk.synthetic_doc()
    for r in doc["rules"]:
        if r["id"] == tk.ID_GAP:
            r["post"] = True
            r["post_since"] = post_since
    return doc


@pytest.fixture(scope="module")
def revs(tmp_path_factory):
    """Two synthetic revisions in one store: everything in shadow, and the same
    rules with the two-seat gap rule armed from one day ago."""
    tmp = tmp_path_factory.mktemp("review")
    store, shadow = tk.build_revision(tmp, name="shadow")
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _store, armed = tk.build_revision(tmp, _armed_doc(since), name="armed")

    def state(rev):
        rs = rr.load_dir(os.path.join(store, "rules-" + rev))
        return rr.State(rs.rev, rs)
    return types.SimpleNamespace(store=store, shadow=state(shadow), armed=state(armed))


@pytest.fixture
def signing(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", fx.KEY)


class Req:
    """What the seat-evidence routes read off a request."""

    def __init__(self, body, token=None, version="1.41.0"):
        self._b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = {"X-Mod-Version": version}
        if token:
            self.headers["X-Session-Token"] = token
        self.client = None
        self.url = "http://seat-evidence.test/"
        self.state = types.SimpleNamespace()

    async def body(self):
        return self._b


async def _players(sm, *steams):
    ids = {}
    async with sm() as db:
        for s in steams:
            ids[s] = (await main.get_or_create_player(db, s, "Seat " + s[-3:])).id
        await db.commit()
    return ids


async def _session(sm, steam):
    token = "sev-" + uuid.uuid4().hex
    async with sm() as db:
        await db.execute(text(
            "INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at) "
            "VALUES (:s, encode(sha256(convert_to(:t, 'UTF8')), 'hex'), true, now(), "
            "        now() + interval '1 hour')"), {"s": steam, "t": token})
        await db.commit()
    return token


async def _post(sm, body, token, route=None):
    async with sm() as db:
        r = await (route or main.submit_seat_evidence)(Req(body, token), db)
    if isinstance(r, dict):
        return 200, r
    return r.status_code, json.loads(r.body)


async def _scalar(sm, sql, **p):
    async with sm() as db:
        return (await db.execute(text(sql), p)).scalar()


async def _rows(sm, sql, **p):
    async with sm() as db:
        return (await db.execute(text(sql), p)).mappings().all()


async def _set(sm, key, value):
    async with sm() as db:
        await db.execute(text(
            "INSERT INTO runtime_settings (key, value) VALUES (:k, :v) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"), {"k": key, "v": value})
        await db.commit()


async def _match(sm, ids, a, b, room, *, minutes_ago=10, a_rounds=5, b_rounds=3, **cols):
    vals = {"player1_id": ids[a], "player2_id": ids[b], "photon_room_id": room,
            "is_ranked": True, "p1_rounds_won": a_rounds, "p2_rounds_won": b_rounds,
            "winner_id": ids[a] if a_rounds > b_rounds else ids[b], "reported_by": ids[a]}
    vals.update(cols)
    async with sm() as db:
        row = await lh._insert(db, "matches", vals)
        await db.execute(text(
            "UPDATE matches SET ended_at = now() - make_interval(mins => CAST(:m AS int)), "
            "  created_at = now() - make_interval(mins => CAST(:m AS int)) "
            "WHERE id = :i"), {"m": minutes_ago, "i": row["id"]})
        await db.commit()
    return row["id"]


def _body(seat, other, stable, suffix=8, **over):
    """A signed envelope; `suffix` is the attach key's round count, `over`
    replaces record fields."""
    return fx.envelope(fx.base_record(**over), seat=seat, other=other, stable=stable,
                       rounds=suffix)


def _findings_sql(where):
    return ("SELECT rule_id, rules_rev, details, flag_id, dedup_key FROM seat_evidence_findings "
            "WHERE " + where + " ORDER BY rule_id")


async def _counts(sm):
    return (await _scalar(sm, "SELECT count(*) FROM flagged_matches"),
            await _scalar(sm, "SELECT count(*) FROM seat_evidence_findings"),
            await _scalar(sm, "SELECT count(*) FROM seat_evidence_findings WHERE flag_id IS NOT NULL"))


def _bot_line():
    """The bot's renderer for a review flag, taken from the bot's own source."""
    src = open(os.path.join(HERE, "..", "discord_bot.py"), encoding="utf-8").read()
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "_review_flag_line")
    ns = {"json": json}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "bot", "exec"), ns)
    return ns["_review_flag_line"]


# -- the migration ------------------------------------------------------------

def test_migration_368_applies_twice_with_an_identical_result(live):
    first, again = live.snaps
    assert first == again
    keys = {r[0]: r[1] for r in first["runtime_settings"] if r[0].startswith("seat")}
    assert keys == {k: "1" for k in se.SWITCHES}
    names = {r[0] for r in first["constraints"]}
    assert {"seat_evidence_one_per_seat"} <= names
    assert first["review_cursor"] == [] and first["review_sitting_dirty"] == []


def test_a_third_apply_keeps_a_switch_sid_set(live):
    async def go():
        await _set(live.sm, "seat_evidence_purge", "0")
        await live.case.conn.execute(sp.read_368())
        v = await _scalar(live.sm, "SELECT value FROM runtime_settings WHERE key = 'seat_evidence_purge'")
        await _set(live.sm, "seat_evidence_purge", "1")
        return v
    assert live.run(go()) == "0"


# -- M1 / B2: the session is the first decision --------------------------------

def test_m1_an_unauthenticated_first_arrival_is_refused_before_any_work(live, signing):
    async def go():
        sm = live.sm
        before = await _scalar(sm, "SELECT count(*) FROM players")
        body = _body(M1_C, M3_B, "ranked_sevm1_000001")
        out = [await _post(sm, body, None)]
        other_token = await _session(sm, M3_B)
        out.append(await _post(sm, body, other_token))          # a session for another seat
        await _set(sm, "seat_evidence_accept", "0")
        try:
            out.append(await _post(sm, body, None))              # the switch is read after
            own = await _session(sm, M1_C)
            out.append(await _post(sm, body, own))
        finally:
            await _set(sm, "seat_evidence_accept", "1")
        out.append(await _post(sm, body, own))                    # authenticated, no player row
        compat = {"seat_steam_id": M1_C, "outcome": "not_run", "plugins": [], "sig": "0" * 64}
        out.append(await _post(sm, compat, None, main.submit_compat_outcome))
        after = await _scalar(sm, "SELECT count(*) FROM players")
        rows = await _scalar(sm, "SELECT count(*) FROM seat_evidence WHERE stable_game_key = 'ranked_sevm1_000001'")
        made = await _scalar(sm, "SELECT count(*) FROM players WHERE steam_id = :s", s=M1_C)
        return out, before, after, rows, made
    out, before, after, rows, made = live.run(go())
    assert [o[0] for o in out] == [401, 401, 401, 503, 409, 401], out
    assert out[0][1] == {"detail": "seat_session"} and out[4][1] == {"status": "not_ready"}
    assert (before, rows, made) == (after, 0, 0)


# -- M2 / B3: one record per (stable key, seat); one conflict marker -----------

def test_m2_two_suffixes_on_one_stable_key_keep_the_first_and_mark_once(live, signing):
    async def go():
        sm = live.sm
        await _players(sm, M3_A, M3_B)
        tok = await _session(sm, M3_A)
        key = "ranked_sevm2_000001"
        first = _body(M3_A, M3_B, key, suffix=5)
        second = _body(M3_A, M3_B, key, suffix=6)
        out = [await _post(sm, first, tok), await _post(sm, second, tok)]
        mark1 = await _rows(sm, "SELECT conflict_at, conflict_kind FROM seat_evidence WHERE stable_game_key = :k", k=key)
        await asyncio.sleep(0.05)
        out.append(await _post(sm, second, tok))                 # the same conflicting retry
        out.append(await _post(sm, _body(M3_A, M3_B, key, suffix=6, fire_floor=7), tok))
        out.append(await _post(sm, first, tok))                  # the identical retry
        rows = await _rows(sm, "SELECT attach_key, conflict_at, conflict_kind, payload_sha256 "
                               "FROM seat_evidence WHERE stable_game_key = :k", k=key)
        return out, mark1, rows
    out, mark1, rows = live.run(go())
    assert [o[0] for o in out] == [200, 409, 409, 409, 200], out
    assert out[0][1] == {"status": "recorded"} and out[1][1] == {"status": "conflict"}
    assert out[4][1] == {"status": "already_recorded"}
    assert len(rows) == 1 and rows[0]["attach_key"] == "ranked_sevm2_000001_r5"
    assert rows[0]["conflict_kind"] == "attach_key"
    assert mark1[0]["conflict_at"] is not None
    assert rows[0]["conflict_at"] == mark1[0]["conflict_at"]     # counted once


# -- M3 / B4: evidence before its match, both orders, both seats racing --------

def _errors(stats):
    return {k for k in stats if k.startswith("error")} | (
        {"rule_errors"} if stats.get("rule_errors") else set())


GAME_SQL = "SELECT match_id, finalized_at, evaluated_rev FROM seat_evidence_games WHERE stable_game_key = :k"


def test_m3_evidence_before_the_match_waits_then_attaches_and_absent_evaluates_nothing(live, signing, revs):
    async def go():
        sm = live.sm
        ids = await _players(sm, M3_A, M3_B)
        ta, tb = await _session(sm, M3_A), await _session(sm, M3_B)
        key = "ranked_sevm3a_000001"
        await _post(sm, _body(M3_A, M3_B, key), ta)
        await _post(sm, _body(M3_B, M3_A, key, rounds=[3, 5]), tb)
        s1 = await se.games_pass(sm)
        g1 = await _rows(sm, GAME_SQL, k=key)
        mid = await _match(sm, ids, M3_A, M3_B, key + "_r8", minutes_ago=0)
        s2 = await se.games_pass(sm)                              # ended under READY_LAG_S ago
        g2 = await _rows(sm, GAME_SQL, k=key)
        async with sm() as db:
            await db.execute(text("UPDATE matches SET ended_at = now() - interval '10 minutes' WHERE id = :i"), {"i": mid})
            await db.commit()
        s3 = await se.games_pass(sm, rr.State("absent"))
        g3 = await _rows(sm, GAME_SQL, k=key)
        f3 = await _rows(sm, _findings_sql("dedup_key LIKE :k"), k=key + "|%")
        s4 = await se.games_pass(sm, revs.shadow)
        g4 = await _rows(sm, GAME_SQL, k=key)
        f4 = await _rows(sm, _findings_sql("dedup_key LIKE :k"), k=key + "|%")
        return (s1, s2, s3, s4), (g1, g2, g3, g4), mid, f3, f4
    stats, games, mid, f3, f4 = live.run(go())
    assert not any(_errors(s) for s in stats), stats
    assert [s["evaluated"] for s in stats[:3]] == [0, 0, 0]
    assert games[0][0]["match_id"] is None and games[1][0]["match_id"] is None
    assert games[2][0]["match_id"] == mid and games[2][0]["finalized_at"] is None
    assert f3 == []                                               # absent: attach only
    assert games[3][0]["finalized_at"] is not None
    assert games[3][0]["evaluated_rev"] == revs.shadow.ruleset.rev
    assert [r["rule_id"] for r in f4] == [tk.ID_NOT_GAP]          # the synthetic quiet game
    assert all(r["rules_rev"] == revs.shadow.ruleset.rev and r["flag_id"] is None for r in f4)


def test_m3_the_match_before_the_evidence_waits_for_the_second_seat(live, signing, revs):
    async def go():
        sm = live.sm
        ids = await _players(sm, M3_A, M3_B)
        ta, tb = await _session(sm, M3_A), await _session(sm, M3_B)
        key = "ranked_sevm3b_000001"
        mid = await _match(sm, ids, M3_A, M3_B, key + "_r8")
        await _post(sm, _body(M3_A, M3_B, key), ta)
        s1 = await se.games_pass(sm, revs.shadow)
        g1 = await _rows(sm, GAME_SQL, k=key)
        await _post(sm, _body(M3_B, M3_A, key, rounds=[3, 5]), tb)
        s2 = await se.games_pass(sm, revs.shadow)
        g2 = await _rows(sm, GAME_SQL, k=key)
        return (s1, s2), (g1, g2), mid
    stats, games, mid = live.run(go())
    assert stats[0]["evaluated"] >= 1 and not _errors(stats[0]), stats
    assert games[0][0]["match_id"] == mid and games[0][0]["finalized_at"] is None
    assert games[1][0]["finalized_at"] is not None


def test_m3_both_seats_and_two_passes_racing_on_separate_connections(live, signing, revs):
    async def go():
        sm = live.sm
        ids = await _players(sm, M3_A, M3_B)
        ta, tb = await _session(sm, M3_A), await _session(sm, M3_B)
        out = []
        for i in range(3):
            key = "ranked_sevm3r_00000%d" % i
            mid = await _match(sm, ids, M3_A, M3_B, key + "_r8")
            res = await asyncio.gather(
                _post(sm, _body(M3_A, M3_B, key), ta),
                _post(sm, _body(M3_B, M3_A, key, rounds=[3, 5]), tb),
                se.games_pass(sm, revs.shadow), se.games_pass(sm, revs.shadow),
                return_exceptions=True)
            settle = await se.games_pass(sm, revs.shadow)
            g = await _rows(sm, GAME_SQL, k=key)
            n = await _scalar(sm, "SELECT count(*) FROM seat_evidence WHERE stable_game_key = :k", k=key)
            f = await _rows(sm, "SELECT rule_id, count(*) n FROM seat_evidence_findings "
                                "WHERE dedup_key LIKE :k GROUP BY rule_id", k=key + "|%")
            out.append((res, settle, g, n, f, mid))
        return out
    for res, settle, g, n, f, mid in live.run(go()):
        assert not any(isinstance(r, BaseException) for r in res), res
        assert res[0] == (200, {"status": "recorded"}) and res[1] == (200, {"status": "recorded"})
        assert not _errors(res[2]) and not _errors(res[3]) and not _errors(settle)
        assert n == 2 and len(g) == 1 and g[0]["match_id"] == mid and g[0]["finalized_at"] is not None
        assert f and all(r["n"] == 1 for r in f), f


# -- M10 / B11: the match path never waits on, or fails with, this lane ---------

def test_m10_the_match_commits_while_every_worker_statement_fails(live, monkeypatch, revs):
    async def no_session_check(request, steam_id, db):
        return None

    async def broken_mark(db, rs, limit):
        await db.execute(text("SELECT * FROM sev_no_such_table"))
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    monkeypatch.setattr(main, "_check_steam_session", no_session_check)
    monkeypatch.setattr(se, "_mark_dirty", broken_mark)
    monkeypatch.setattr(se, "_CANDIDATES", text(
        "SELECT * FROM sev_no_such_table WHERE 1 = CAST(:lim AS int) AND CAST(:rev AS varchar) IS NULL"))
    room = "ranked_sevm10_000001_r1"

    async def go():
        sm = live.sm
        await _players(sm, lh.P1, lh.P2)

        async def report():
            async with sm() as db:
                return await main.submit_match(lh._report_1v1(room), lh._FakeRequest(), db)
        res = await asyncio.gather(report(), se.games_pass(sm, revs.shadow),
                                   se.sitting_pass(sm, revs.shadow), return_exceptions=True)
        n = await _scalar(sm, "SELECT count(*) FROM matches WHERE photon_room_id = :r", r=room)
        return res, n
    res, n = live.run(go())
    assert not isinstance(res[0], BaseException), res[0]
    assert n == 1
    assert isinstance(res[1], Exception) and isinstance(res[2], Exception)   # the worker's own failures


# -- A3: the absent state ------------------------------------------------------

def test_a3_absent_reads_absent_passes_evaluate_nothing_and_the_match_body_is_unchanged(
        live, monkeypatch, revs):
    async def no_session_check(request, steam_id, db):
        return None
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    monkeypatch.setattr(main, "_check_steam_session", no_session_check)
    pairs = [("76561190000000611", "76561190000000612"), ("76561190000000613", "76561190000000614")]

    async def submit(a, b, room):
        async with live.sm() as db:
            r = await main.submit_match(lh._report_1v1(room, a=a, b=b), lh._FakeRequest(), db)
        return json.loads(r.model_dump_json())

    async def go():
        monkeypatch.setattr(rr, "_STATE", rr.State("absent"))
        word = rr.health_word()
        g = await se.games_pass(live.sm, rr.current_rules())
        s = await se.sitting_pass(live.sm, rr.current_rules())
        line = main._review_pass_line(rr.health_word(), g, s)
        absent = await submit(*pairs[0], "ranked_seva3_000001_r1")
        monkeypatch.setattr(rr, "_STATE", revs.shadow)
        loaded = await submit(*pairs[1], "ranked_seva3_000002_r1")
        return word, line, absent, loaded
    word, line, absent, loaded = live.run(go())
    assert word == "absent"
    assert line.startswith("[REVIEW] pass rev=absent evaluated=0 fired=0 errors=0"), line
    # Two fresh pairs in the same state: the bodies differ only in the row
    # identity (the new match id and the winner's own steam id).
    for body, (a, _b) in ((absent, pairs[0]), (loaded, pairs[1])):
        assert body.pop("winner_steam_id") == a
        body.pop("match_id")
    assert json.dumps(absent, sort_keys=True) == json.dumps(loaded, sort_keys=True)


# -- A8: shadow, then one posted flag; re-evaluation on a revision change -------

def test_a8_shadow_then_posting_from_post_since_and_the_bot_prints_the_line(live, signing, revs):
    new, old = "ranked_seva8_000001", "ranked_seva8_000002"

    async def go():
        sm = live.sm
        ids = await _players(sm, A8_A, A8_B)
        ta, tb = await _session(sm, A8_A), await _session(sm, A8_B)
        mid_new = await _match(sm, ids, A8_A, A8_B, new + "_r8")
        mid_old = await _match(sm, ids, A8_A, A8_B, old + "_r8", minutes_ago=3 * 24 * 60)
        for key in (new, old):
            await _post(sm, _body(A8_A, A8_B, key, dec=[40, 2]), ta)
            await _post(sm, _body(A8_B, A8_A, key, rounds=[3, 5]), tb)
        before = await _counts(sm)
        s1 = await se.games_pass(sm, revs.shadow)
        f1 = await _rows(sm, _findings_sql("dedup_key LIKE :k AND rule_id = :r"), k=new + "|%", r=tk.ID_GAP)
        mid1 = await _counts(sm)
        s2 = await se.games_pass(sm, revs.armed)
        f2 = {k: await _rows(sm, _findings_sql("dedup_key LIKE :k AND rule_id = :r"), k=k + "|%", r=tk.ID_GAP)
              for k in (new, old)}
        g2 = {k: await _rows(sm, GAME_SQL, k=k) for k in (new, old)}
        flags = await _rows(sm, "SELECT match_id, flag_reason, auto_invalidated, flag_details "
                                "FROM flagged_matches WHERE flag_reason = 'review'")
        s3 = await se.games_pass(sm, revs.armed)
        after = await _counts(sm)
        return (s1, s2, s3), before, mid1, after, f1, f2, g2, flags, (mid_new, mid_old)
    stats, before, mid1, after, f1, f2, g2, flags, (mid_new, mid_old) = live.run(go())
    assert not any(_errors(s) for s in stats), stats
    # shadow: one row carrying the rule id and revision, no flag
    assert len(f1) == 1 and f1[0]["rules_rev"] == revs.shadow.ruleset.rev and f1[0]["flag_id"] is None
    assert mid1[0] == before[0] and mid1[2] == before[2]
    # the next revision re-evaluates both games (evaluated_rev moves) ...
    for k in g2:
        assert g2[k][0]["evaluated_rev"] == revs.armed.ruleset.rev
        assert f2[k][0]["rules_rev"] == revs.armed.ruleset.rev
    # ... and posts exactly one flag: the game that ended after post_since
    assert len(flags) == 1 and flags[0]["match_id"] == mid_new
    assert f2[old][0]["flag_id"] is None and f2[new][0]["flag_id"] is not None
    assert flags[0]["flag_reason"] == "review" and flags[0]["auto_invalidated"] is False
    det = se._jsonv(flags[0]["flag_details"])
    rule = revs.armed.ruleset.rule(tk.ID_GAP)
    want = revs.armed.ruleset.render_line(rule, se._jsonv(f2[new][0]["details"])["items"])
    assert det["line"] == want and det["rule_id"] == tk.ID_GAP
    assert det["rules_rev"] == revs.armed.ruleset.rev
    assert want.startswith("synthetic gap ")
    assert _bot_line()(flags[0]["flag_details"]) == want
    assert after[0] == before[0] + 1                              # a repeat pass adds nothing
    assert stats[2]["evaluated"] == 0


# -- A4: a refused revision changes no count -------------------------------------

def _broken(store, rev, how):
    """A copy of a built revision, broken one way, under a fresh directory."""
    import shutil
    src = os.path.join(store, "rules-" + rev)
    dst = os.path.join(os.path.dirname(store), "broken-" + how, "rules-" + rev)
    shutil.copytree(src, dst)
    if how == "digest":
        with open(os.path.join(dst, "rules.json"), "a", encoding="utf-8") as f:
            f.write(" ")
        return dst
    if how == "malformed":
        with open(os.path.join(dst, "rules.json"), "w", encoding="utf-8") as f:
            f.write("{")
    if how == "selftest":
        p = os.path.join(dst, "selftest.json")
        doc = json.load(open(p, encoding="utf-8"))
        doc["cases"][0]["fire"] = [tk.ID_PUB]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f)
    if how == "stale":
        p = os.path.join(dst, "rules.json")
        doc = json.load(open(p, encoding="utf-8"))
        first = sorted(doc["vocabulary"])[0]
        doc["vocabulary"][first] = "0" * 64
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f)
    return tk.reseal(dst)[0]


def test_a4_each_refused_revision_changes_no_count_and_a_loaded_one_does(live, signing, revs, monkeypatch):
    shadow = revs.shadow.ruleset.rev
    monkeypatch.setattr(rr, "_STATE", rr.current_rules())

    async def go():
        sm = live.sm
        ids = await _players(sm, A4_A, A4_B)
        ta, tb = await _session(sm, A4_A), await _session(sm, A4_B)
        key = "ranked_seva4_000001"
        await _match(sm, ids, A4_A, A4_B, key + "_r8")
        await _post(sm, _body(A4_A, A4_B, key, dec=[40, 2]), ta)
        await _post(sm, _body(A4_B, A4_A, key, rounds=[3, 5]), tb)
        out = {}
        for how in ("digest", "malformed", "selftest", "stale"):
            rdir = _broken(revs.store, shadow, how)
            root = os.path.dirname(rdir)
            tk.point(root, os.path.basename(rdir))
            monkeypatch.setenv(rr.ROOT_ENV, root)
            monkeypatch.setattr(rr, "_KEY", None)
            st = rr.refresh_rules()
            before = await _counts(sm)
            g = await se.games_pass(sm, st)
            s = await se.sitting_pass(sm, st)
            out[how] = (st.word, st.reason, before, await _counts(sm), g["evaluated"], s["evaluated"])
        before = await _counts(sm)
        await se.games_pass(sm, revs.shadow)
        control = (before, await _counts(sm))
        return out, control
    out, control = live.run(go())
    assert {k: v[1] for k, v in out.items()} == {
        "digest": "digest", "malformed": "malformed", "selftest": "selftest", "stale": "stale"}
    for how, (word, _reason, before, after, ge, sv) in out.items():
        assert word == "refused" and before == after and (ge, sv) == (0, 0), how
    assert control[1][1] > control[0][1]                          # the negative control


# -- design report finding 3: the persisted dirty-sitting cursor -----------------

async def _step_sitting(sm, ids, a, b, days_ago, tag, *, created_seconds_ago=None):
    """Four ranked games on one UTC day, reported by `a`, whose observed batch
    rate steps up by a factor the synthetic step rule reads as a step."""
    for g, obs in enumerate((40, 40, 120, 120)):
        mid = await _match(sm, ids, a, b, "ranked_sevcu%s_00000%d_r%d" % (tag, g, g),
                           duration_seconds=40, p1_obs_batches=obs)
        async with sm() as db:
            await db.execute(text(
                "UPDATE matches SET ended_at = date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' "
                "  - make_interval(days => CAST(:d AS int)) + make_interval(hours => 12, mins => CAST(:g AS int)), "
                "  created_at = CASE WHEN CAST(:c AS int) IS NULL "
                "    THEN date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' "
                "      - make_interval(days => CAST(:d AS int)) + make_interval(hours => 12, mins => CAST(:g AS int)) "
                "    ELSE now() - make_interval(secs => CAST(:c AS int)) END "
                "WHERE id = :i"), {"d": days_ago, "g": g, "c": created_seconds_ago, "i": mid})
            await db.commit()


async def _drain(sm, state, cap=150):
    """Bounded passes (one sitting and three match rows per pass) until the
    cursor has nothing left to read and the dirty set is empty."""
    passes = []
    for _ in range(cap):
        s = await se.sitting_pass(sm, state, limit=1, mark_limit=3)
        passes.append(s)
        left = await _scalar(sm, "SELECT count(*) FROM review_sitting_dirty")
        if not s.get("marked_rows") and not left:
            return passes
    raise AssertionError("the dirty set did not drain: %r" % passes[-3:])


def test_finding3_the_cursor_reaches_every_sitting_in_the_window_including_after_downtime(live, revs):
    rule = revs.shadow.ruleset.rule(tk.ID_STEP)
    window = rule.sitting[1]["window_days"]

    async def go():
        sm = live.sm
        ids = await _players(sm, *CU)
        await _step_sitting(sm, ids, CU[0], CU[1], 1, "a")
        await _step_sitting(sm, ids, CU[2], CU[3], window - 2, "b")   # older than any short cutoff
        await _step_sitting(sm, ids, CU[4], CU[5], window + 2, "c")   # outside the rule's window
        p1 = await _drain(sm, revs.shadow)
        keys1 = await _rows(sm, "SELECT dedup_key, rules_rev FROM seat_evidence_findings "
                                "WHERE scope = 'sitting' AND rule_id = :r ORDER BY dedup_key", r=tk.ID_STEP)
        # downtime: a sitting played days ago whose rows were written after the
        # cursor moved on (late reports, a stopped worker)
        await _step_sitting(sm, ids, CU[6], CU[7], window - 3, "d", created_seconds_ago=150)
        p2 = await _drain(sm, revs.shadow)
        keys2 = await _rows(sm, "SELECT dedup_key FROM seat_evidence_findings "
                                "WHERE scope = 'sitting' AND rule_id = :r ORDER BY dedup_key", r=tk.ID_STEP)
        # the literal form over the same days, for the same rule
        lit = rr.literal(os.path.join(revs.store, "rules-" + revs.shadow.ruleset.rev), tk.ID_STEP, 400)
        lit_rows = await live.case.conn.fetch(lit)
        # a new revision restarts the cursor at its own horizon
        p3 = await _drain(sm, revs.armed)
        keys3 = await _rows(sm, "SELECT dedup_key, rules_rev FROM seat_evidence_findings "
                                "WHERE scope = 'sitting' AND rule_id = :r ORDER BY dedup_key", r=tk.ID_STEP)
        cur = await _rows(sm, "SELECT rules_rev FROM review_cursor WHERE name = :n", n=se.CURSOR)
        return ids, (p1, p2, p3), keys1, keys2, lit_rows, keys3, cur
    ids, passes, keys1, keys2, lit_rows, keys3, cur = live.run(go())
    for ps in passes:
        assert all(not p.get("rule_errors") for p in ps), ps
        assert len(ps) > 2                                       # bounded: it took several passes

    def pair(a, b):
        lo, hi = sorted([str(ids[a]), str(ids[b])])
        return "%s|%s|" % (lo, hi)
    got1 = {k["dedup_key"].rsplit("|", 1)[0] + "|" for k in keys1}
    assert got1 == {pair(CU[0], CU[1]), pair(CU[2], CU[3])}
    got2 = {k["dedup_key"].rsplit("|", 1)[0] + "|" for k in keys2}
    assert got2 == got1 | {pair(CU[6], CU[7])}
    lit_keys = {"%s|%s|%s" % (*sorted([str(r["subject"]), str(r["opponent"])]), r["d"]) for r in lit_rows}
    assert {k["dedup_key"] for k in keys2} <= lit_keys
    assert {k for k in lit_keys if k.split("|")[0] in {str(i) for i in ids.values()}} == \
        {k["dedup_key"] for k in keys2}
    assert {k["rules_rev"] for k in keys3} == {revs.armed.ruleset.rev}
    assert cur[0]["rules_rev"] == revs.armed.ruleset.rev


def test_finding3_a_failing_sitting_rule_keeps_the_dirty_rows_for_the_next_pass(live, revs, monkeypatch):
    a, b = "1000000000000601", "1000000000000602"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        await _step_sitting(sm, ids, a, b, 2, "e", created_seconds_ago=150)
        rs = revs.shadow.ruleset
        monkeypatch.setattr(rs, "sitting_statement",
                            lambda rule, mode="dirty": ("SELECT * FROM sev_no_such_table", {}),
                            raising=False)
        failed = await se.sitting_pass(sm, revs.shadow, mark_limit=1000)
        kept = await _scalar(sm, "SELECT count(*) FROM review_sitting_dirty")
        monkeypatch.undo()
        await _drain(sm, revs.shadow)
        lo, hi = sorted([str(ids[a]), str(ids[b])])
        found = await _scalar(sm, "SELECT count(*) FROM seat_evidence_findings WHERE scope = 'sitting' "
                                  "AND rule_id = :r AND dedup_key LIKE :k", r=tk.ID_STEP, k="%s|%s|%%" % (lo, hi))
        return failed, kept, found
    failed, kept, found = live.run(go())
    assert failed["rule_errors"] >= 1 and kept > 0, (failed, kept)
    assert found == 1


# -- retention and the compat outcome ------------------------------------------

def test_purge_drops_old_lists_and_old_unattached_records_only(live, signing):
    async def go():
        sm = live.sm
        ids = await _players(sm, M3_A, M3_B)
        tok = await _session(sm, M3_A)
        kept, gone = "ranked_sevpurge_000001", "ranked_sevpurge_000002"
        await _match(sm, ids, M3_A, M3_B, kept + "_r8")
        await _post(sm, _body(M3_A, M3_B, kept, blk_sent=[[1, 0, 0, 0]]), tok)
        await _post(sm, _body(M3_A, M3_B, gone), tok)
        await se.games_pass(sm)                                   # attaches `kept` only
        async with sm() as db:
            await db.execute(text("UPDATE seat_evidence SET received_at = now() - interval '121 days' "
                                  "WHERE stable_game_key = ANY(CAST(:k AS varchar[]))"),
                             {"k": [kept, gone]})
            await db.commit()
        out = await se.purge_pass(sm)
        rows = await _rows(sm, "SELECT stable_game_key k, (payload ? 'blk_sent') has_list, "
                               "(payload ? 'rtt') has_rtt, lists_purged_at FROM seat_evidence "
                               "WHERE stable_game_key = ANY(CAST(:k AS varchar[]))", k=[kept, gone])
        return out, rows
    out, rows = live.run(go())
    assert out["lists"] >= 2 and out["unattached"] >= 1, out
    assert [r["k"] for r in rows] == ["ranked_sevpurge_000001"]
    assert rows[0]["has_list"] is False and rows[0]["has_rtt"] is True
    assert rows[0]["lists_purged_at"] is not None


def test_the_compat_outcome_is_one_row_per_account_per_hour(live, signing):
    async def go():
        sm = live.sm
        await _players(sm, M3_A)
        tok = await _session(sm, M3_A)

        def body(outcome, plugins):
            want = se.compat_canonical(M3_A, outcome, plugins)
            import hashlib as _h
            import hmac as _m
            sig = _m.new(fx.KEY.encode(), want.encode(), _h.sha256).hexdigest()
            return {"seat_steam_id": M3_A, "outcome": outcome, "plugins": plugins, "sig": sig}
        route = main.submit_compat_outcome
        out = [await _post(sm, body("finding", ["a.plugin", "b"]), tok, route),
               await _post(sm, body("not_run", []), tok, route),
               await _post(sm, dict(body("not_run", []), sig="f" * 64), tok, route)]
        rows = await _rows(sm, "SELECT c.outcome, c.other_plugin_count, c.other_plugins FROM "
                               "client_compat_events c JOIN players p ON p.id = c.player_id "
                               "WHERE p.steam_id = :s", s=M3_A)
        return out, rows
    out, rows = live.run(go())
    assert out == [(200, {"status": "recorded"}), (200, {"status": "already_recorded"}),
                   (403, {"detail": "signature"})]
    assert [tuple(r.values()) for r in rows] == [("finding", 2, "a.plugin,b")]


# -- last in this module: it drops the lane's tables and puts them back ---------

def test_the_rollback_removes_exactly_what_368_added_and_368_reapplies(live):
    rollback = os.path.join(os.path.dirname(sp.M368), "rollback_368_seat_evidence.sql")

    async def tables(conn):
        return await conn.fetchval(
            "SELECT count(*) FROM pg_tables WHERE schemaname = current_schema() "
            "AND tablename = ANY($1::text[])", sorted(sp.SEV_TABLES))

    async def go():
        conn = live.case.conn
        others = await conn.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname = current_schema()")
        flags = await conn.fetchval("SELECT count(*) FROM flagged_matches")
        await conn.execute(open(rollback, encoding="utf-8").read())
        gone = (await tables(conn),
                await conn.fetchval("SELECT count(*) FROM runtime_settings WHERE key LIKE 'seat%'"),
                await conn.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname = current_schema()"),
                await conn.fetchval("SELECT count(*) FROM flagged_matches"))
        await conn.execute(sp.read_368())
        back = await sp.snapshot(conn)
        return others, flags, gone, back
    others, flags, gone, back = live.run(go())
    assert gone == (0, 0, others - len(sp.SEV_TABLES), flags)
    first = live.snaps[0]

    def seat_keys(snap):
        return [r[:2] for r in snap["runtime_settings"] if r[0].startswith("seat")]
    assert len(seat_keys(back)) == len(se.SWITCHES) == 3
    assert seat_keys(back) == seat_keys(first)
    assert back["constraints"] == first["constraints"] and back["indexes"] == first["indexes"]
