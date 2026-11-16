"""MODLOG-1 against a real PostgreSQL: the record of every action family read
back, the read (each filter, the search, each sort both ways, the paging, the
refusals, the internal twin), the plan of the per-player read on 50,000 rows,
the writer's own input, and the deletion path.

One case schema for the module, built by the ladder harness's procedure
(test_title_ladder_hooks_live._build: every migration's DDL replayed, 420
included, the ORM, the widening pass), sealed, and dropped at the end:

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately (else they FAIL)

Every player is a synthetic id below the first individual-account SteamID64
and every name is invented. The admin routes' signature checks are replaced
(they are tested on their own elsewhere); every route runs its own handler.

The mutants (search, one sort, the per-player filter) run each read check
against a mutated read and require it to fail: each prints its red line.
"""
import asyncio
import hashlib
import hmac
import itertools
import json
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402
from starlette.datastructures import QueryParams  # noqa: E402

import main  # noqa: E402
import modlog  # noqa: E402
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402

INTERNAL_KEY = "modlog-internal-key"
DELETE_SECRET = "modlog-delete-secret"
_IDS = itertools.count(1)


def _sid():
    """A fresh synthetic 17-digit id below 76561197960265728."""
    return "76561190420%06d" % next(_IDS)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def case():
    lh._require_live_pg()
    built = {}

    async def build():
        c = harness.CaseSchema(lh.DSN, "modlog")
        await c.__aenter__()
        try:
            await lh._build(c)
        except BaseException:
            await c.__aexit__(None, None, None)
            raise
        built.update(schema=c.schema, own=c.own)
        await c.conn.close()
    _run(build())
    try:
        yield built["schema"]
    finally:
        async def drop():
            conn = await harness.connect_bound(lh.DSN, built["schema"])
            try:
                await harness.drop_case_schema(conn, built["schema"], built["own"])
            finally:
                await conn.close()
        _run(drop())


def _with_sm(schema, body):
    async def go():
        engine = harness.bound_engine(lh.DSN, schema)
        try:
            return await body(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()
    return _run(go())


@pytest.fixture
def admin_open(monkeypatch):
    async def _ok(*a, **k):
        return None
    monkeypatch.setattr(main, "_require_admin", _ok)
    monkeypatch.setattr(main, "_verify_admin_hmac", lambda *a, **k: True)
    monkeypatch.setenv("API_SECRET_KEY", INTERNAL_KEY)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)


# -- seeding ----------------------------------------------------------------

async def _player(db, sid=None, name=None, **extra):
    sid = sid or _sid()
    pid = uuid.uuid4()
    values = {"id": pid, "steam_id": sid, "display_name": name or ("Tester " + sid[-4:])}
    values.update(extra)
    await lh._insert(db, "players", values)
    return sid, pid


async def _admin(db, name=None, discord_id=None):
    # lh._insert writes NOW() for a None value: pass discord_id only when set
    extra = {"discord_id": discord_id} if discord_id is not None else {}
    sid, pid = await _player(db, name=name or "Mod Example", **extra)
    await lh._insert(db, "admin_users", {"steam_id": sid})
    return sid, pid


async def _records(db, actor):
    return (await db.execute(text(
        "SELECT action, admin_steam_id, affected_steam_ids, reason, details,"
        "       target_steam_id, target_match_id, target_series_id"
        "  FROM admin_actions WHERE admin_steam_id = :a ORDER BY created_at, id"
    ), {"a": actor})).mappings().all()


def _one(rows, action):
    got = [r for r in rows if r["action"] == action]
    assert len(got) == 1, (action, [r["action"] for r in rows])
    return got[0]


def _commit(sm, fn):
    async def go():
        async with sm() as db:
            out = await fn(db)
            await db.commit()
            return out
    return go()


# -- the families -------------------------------------------------------------

def test_bans_family_records_actor_word_players_and_reason(case, admin_open):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            t, _ = await _player(db)
            n, _ = await _player(db)
            return a, t, n
        a, t, n = await _commit(sm, seed)

        async def call(req, fn):
            async with sm() as db:
                return await fn(req, _slot=None, db=db)
        r = await call(main._AdminBanReq(admin_steam_id=a, target_steam_id=t, reason="cheating, first",
                                         duration_minutes=10080), main.admin_ban)
        assert r["status"] == "banned"
        await call(main._AdminBanReq(admin_steam_id=a, target_steam_id=t, reason="appeal granted",
                                     duration_minutes=60), main.admin_ban)
        await call(main._AdminBanReq(admin_steam_id=a, target_steam_id=t, duration_minutes=120),
                   main.admin_ban)
        await call(main._AdminBanReq(admin_steam_id=a, target_steam_id=t), main.admin_ban)
        await call(main._AdminUnbanReq(admin_steam_id=a, target_steam_id=t, reason="served"),
                   main.admin_unban)
        await call(main._AdminUnbanReq(admin_steam_id=a, target_steam_id=n), main.admin_unban)
        async with sm() as db:
            rows = await _records(db, a)
        assert [r["action"] for r in rows] == ["ban", "ban_length", "ban_length", "ban_repeat",
                                               "unban", "unban"]
        ban = rows[0]
        assert ban["affected_steam_ids"] == [t] and ban["reason"] == "cheating, first"
        assert modlog.sentence("ban", ban["details"]).startswith("Banned for 7 days, until ")
        assert rows[1]["reason"] == "appeal granted" and rows[1]["affected_steam_ids"] == [t]
        assert rows[1]["details"]["old_expires_at"] and rows[1]["details"]["new_expires_at"]
        assert rows[2]["reason"] is None        # no reason sent: as today
        assert rows[3]["affected_steam_ids"] == [t]
        assert rows[4]["reason"] == "served" and rows[4]["details"]["rows"] == 1
        assert rows[5]["affected_steam_ids"] == [n] and rows[5]["details"]["rows"] == 0
        assert modlog.sentence("unban", rows[5]["details"]) == \
            "Unban requested; there was no active ban to lift."
        assert {r["admin_steam_id"] for r in rows} == {a}
    _with_sm(case, body)


def test_bans_rate_block_records_one_refusal(case, admin_open):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            ts = [(await _player(db))[0] for _ in range(6)]
            return a, ts
        a, ts = await _commit(sm, seed)
        for t in ts[:5]:
            async with sm() as db:
                await main.admin_ban(main._AdminBanReq(admin_steam_id=a, target_steam_id=t),
                                     _slot=None, db=db)
        async with sm() as db:
            with pytest.raises(HTTPException) as e:
                await main.admin_ban(main._AdminBanReq(admin_steam_id=a, target_steam_id=ts[5]),
                                     _slot=None, db=db)
        assert e.value.status_code == 429
        async with sm() as db:
            rows = await _records(db, a)
        assert [r["action"] for r in rows] == ["ban"] * 5 + ["ban_rate_blocked"]
        blocked = rows[-1]
        assert blocked["target_steam_id"] == ts[5] and blocked["affected_steam_ids"] == []
    _with_sm(case, body)


def test_chat_family_records(case, admin_open):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            t, _ = await _player(db)
            au, _ = await _player(db)
            mid = (await db.execute(text(
                "INSERT INTO chat_messages (channel, steam_id, display_name, message, source,"
                " author_verified) VALUES ('global', :s, 'Author Example', 'hello there', 'ingame', true)"
                " RETURNING id"), {"s": au})).scalar()
            mid2 = (await db.execute(text(
                "INSERT INTO chat_messages (channel, steam_id, display_name, message, source,"
                " author_verified) VALUES ('global', :s, 'Author Example', 'bad words', 'ingame', true)"
                " RETURNING id"), {"s": au})).scalar()
            return a, t, au, int(mid), int(mid2)
        a, t, au, mid, mid2 = await _commit(sm, seed)
        async with sm() as db:
            await main.chat_moderate_mute(main._ChatModMuteReq(
                steam_id=a, target_steam_id=t, duration_minutes=60, reason="insults"), None, db=db)
        async with sm() as db:
            await main.chat_moderate_unmute(main._ChatModMuteReq(
                steam_id=a, target_steam_id=t), None, db=db)
        async with sm() as db:
            await main.chat_moderate_unmute(main._ChatModMuteReq(
                steam_id=a, target_steam_id=t), None, db=db)      # clears nothing: no record
        async with sm() as db:
            await main.chat_moderate_delete(main._ChatModDeleteReq(steam_id=a, message_id=mid), None, db=db)
        async with sm() as db:
            await main.chat_moderate_mute_by_message(main._ChatModMuteMsgReq(
                steam_id=a, message_id=mid2, duration_minutes=30, reason="spam lines"), None, db=db)
        async with sm() as db:
            rows = await _records(db, a)
        assert [r["action"] for r in rows] == ["chat_mute", "chat_unmute", "chat_delete", "chat_mute_msg"]
        assert rows[0]["affected_steam_ids"] == [t] and rows[0]["reason"] == "insults"
        assert rows[1]["affected_steam_ids"] == [t]
        assert rows[2]["affected_steam_ids"] == [au]
        assert rows[3]["affected_steam_ids"] == [au] and rows[3]["reason"] == "spam lines"
    _with_sm(case, body)


def test_mail_case_family_one_record_per_action(case, admin_open):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            out = []
            for i in range(3):
                s, pid = await _player(db)
                cid = uuid.uuid4()
                await lh._insert(db, "moderation_cases", {
                    "id": cid, "kind": "report", "bucket_key": "modlog-%s" % cid,
                    "subject_player_id": pid, "status": "open", "evidence": "{}"})
                out.append((s, cid))
            return a, out
        a, cases = await _commit(sm, seed)
        for (s, cid), (act, hours) in zip(cases, (("dismiss", None), ("mute", 2), ("ban", None))):
            async with sm() as db:
                await main.admin_moderation_case_act(str(cid), main._AdminModCaseActReq(
                    admin_steam_id=a, action=act, hours=hours, reason="case %s" % act),
                    _slot=None, db=db)
        async with sm() as db:
            rows = await _records(db, a)
        assert [r["action"] for r in rows] == ["modcase_act", "chat_mute", "ban"]
        for r, (s, cid) in zip(rows, cases):
            assert r["affected_steam_ids"] == [s]
            assert r["details"]["case_id"] == str(cid)
            assert r["reason"].startswith("case ")
        assert rows[0]["details"]["action"] == "dismiss"
    _with_sm(case, body)


def test_results_family_names_every_player(case, admin_open):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            p = [await _player(db) for _ in range(4)]
            series = uuid.uuid4()
            await lh._insert(db, "ranked_series", {"id": series, "player1_id": p[0][1],
                                                   "player2_id": p[1][1], "status": "completed"})
            match = uuid.uuid4()
            await lh._insert(db, "matches", {"id": match, "player1_id": p[0][1], "player2_id": p[1][1],
                                             "photon_room_id": "modlog-%s" % match})
            flag = uuid.uuid4()
            await lh._insert(db, "flagged_matches", {"id": flag, "match_id": match,
                                                     "player_steam_ids": [p[0][0], p[1][0]],
                                                     "flag_reason": "modlog_test",
                                                     "discord_evidence_revision": 1})
            team = uuid.uuid4()
            await lh._insert(db, "team_series", {"id": team, "status": "active",
                                                 "t1a_id": p[0][1], "t1b_id": p[1][1],
                                                 "t2a_id": p[2][1], "t2b_id": p[3][1]})
            q = uuid.uuid4()
            await lh._insert(db, "match_report_quarantine", {
                "id": q, "mode": "1v1", "reason": "modlog test", "http_status": 409,
                "player_ids": [p[2][1], p[3][1]], "payload": "{}", "status": "pending"})
            return a, p, series, match, flag, team, q
        a, p, series, match, flag, team, q = await _commit(sm, seed)
        async with sm() as db:
            await main.admin_reverse_series(main._AdminReverseSeriesReq(
                admin_steam_id=a, series_id=str(series), reason="collusion"), db=db)
        async with sm() as db:
            await main.admin_review_flag(main._AdminReviewFlagReq(
                admin_steam_id=a, flag_id=str(flag), review_action="false_positive",
                evidence_revision=1, signature_version=3), db=db)
        async with sm() as db:
            await main.admin_record_exclude({"admin_steam_id": a, "board": "*", "match_id": str(match),
                                             "steam_id": p[0][0], "reason": "lag abuse",
                                             "signature": "x"}, db=db)
        async with sm() as db:
            await main.admin_discard_quarantine(str(q), main._AdminQuarantineReq(
                admin_steam_id=a, note="duplicate report"), db=db)
        async with sm() as db:
            await main.admin_resolve_team_series(str(team), action="void", winner_team=None,
                                                 x_internal_key=INTERNAL_KEY, admin_steam_id=None,
                                                 hmac_signature=None, db=db)
        async with sm() as db:
            rows = await _records(db, a)
            key_rows = (await db.execute(text(
                "SELECT action, affected_steam_ids FROM admin_actions"
                " WHERE admin_steam_id = :k AND target_series_id = :s"),
                {"k": modlog.ACTOR_INTERNAL_KEY, "s": team})).mappings().all()
        assert [r["action"] for r in rows] == ["reverse_series", "flag_review", "record_exclude",
                                               "quarantine_discard"]
        pair = sorted([p[0][0], p[1][0]])
        assert rows[0]["affected_steam_ids"] == pair and rows[0]["reason"] == "collusion"
        assert rows[1]["affected_steam_ids"] == pair
        assert rows[2]["affected_steam_ids"] == [p[0][0]] and rows[2]["reason"] == "lag abuse"
        assert rows[3]["affected_steam_ids"] == sorted([p[2][0], p[3][0]])
        assert rows[3]["reason"] == "duplicate report"
        assert [dict(r) for r in key_rows] == [{"action": "resolve_team_series",
                                                "affected_steam_ids": sorted(x[0] for x in p)}]
    _with_sm(case, body)


def test_grants_family_records(case, admin_open):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            t, _ = await _player(db)
            return a, t
        a, t = await _commit(sm, seed)
        async with sm() as db:
            await main.admin_grant_achievement(main._AdminGrantAchReq(
                admin_steam_id=a, target_steam_id=t, achievement_key="untouchable"), db=db)
        async with sm() as db:
            await main.admin_set_artist(admin_steam_id=a, target_steam_id=t, grant=True, sig="x", db=db)
        async with sm() as db:
            await main.admin_ffa_g3_seat({"admin_steam_id": a, "target_steam_id": t, "hours": 3,
                                          "signature": "x"}, db=db)
        async with sm() as db:
            await main.admin_mail_bulk_grant(main._AdminMailBulkGrantReq(
                admin_steam_id=a, steam_id=t, max_recipients=main.MAIL_RECIPIENT_CAP + 1, days=3), db=db)
        async with sm() as db:
            rows = await _records(db, a)
        assert [r["action"] for r in rows] == ["grant_achievement", "artist-set", "ffa_g3_seat",
                                               "mail_bulk_grant"]
        assert all(r["affected_steam_ids"] == [t] for r in rows), rows
    _with_sm(case, body)


def test_cards_and_quarantine_accept_records(case, admin_open):
    """The cards family's portrait clear, and the quarantine accept (results
    family): each one record naming its players, read back."""
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            t, _ = await _player(db)
            p = [await _player(db) for _ in range(2)]
            q = uuid.uuid4()
            await lh._insert(db, "match_report_quarantine", {
                "id": q, "mode": "1v1", "reason": "modlog test", "http_status": 409,
                "player_ids": [p[0][1], p[1][1]], "payload": "{}", "status": "pending"})
            return a, t, p, q
        a, t, p, q = await _commit(sm, seed)
        async with sm() as db:
            await main.admin_pc_portrait_clear({"admin_steam_id": a, "steam_id": t, "lock_days": 7,
                                                "signature": "x"}, db=db)
        async with sm() as db:
            await main.admin_accept_quarantine(str(q), main._AdminQuarantineReq(
                admin_steam_id=a, note="checked by hand"), db=db)
        async with sm() as db:
            again = None
            try:
                await main.admin_accept_quarantine(str(q), main._AdminQuarantineReq(admin_steam_id=a), db=db)
            except HTTPException as exc:
                again = exc.status_code
        async with sm() as db:
            rows = await _records(db, a)
        assert again == 409
        assert [r["action"] for r in rows] == ["pc_portrait_clear", "quarantine_accept"], rows
        assert rows[0]["affected_steam_ids"] == [t] and rows[0]["details"]["lock_days"] == 7
        assert rows[1]["affected_steam_ids"] == sorted([p[0][0], p[1][0]])
        assert rows[1]["reason"] == "checked by hand" and rows[1]["details"]["quarantine_id"] == str(q)
    _with_sm(case, body)


# -- the writer's own input ---------------------------------------------------

def test_the_writer_stores_what_callers_pass_and_refuses_only_its_bounds(case):
    async def body(sm):
        actor = _sid()
        async with sm() as db:
            await main._modlog_write(
                db, actor=actor, action="ban", affected=[_sid(), None, ""],
                reason="x\x00y\ud800z" + "r" * 400,
                details={"nan": float("nan"), "s": {"a", "b"}, "nul": "a\x00b", "when": main.datetime.now(main.timezone.utc),
                         "u": uuid.uuid4(), "deep": [[[[[[[[[[[[[[["x"]]]]]]]]]]]]]]]})
            await db.commit()
        async with sm() as db:
            row = (await _records(db, actor))[0]
        assert len(row["reason"]) == 256 and "\x00" not in row["reason"]
        assert row["details"]["nul"] == "a�b" and row["details"]["nan"] == "nan"
        assert len(row["affected_steam_ids"]) == 1
        async with sm() as db:
            with pytest.raises(ValueError):
                await main._modlog_write(db, actor=actor, action="ban",
                                         affected=[_sid() for _ in range(17)])
            with pytest.raises(ValueError):
                await main._modlog_write(db, actor=actor, action="not_a_word")
    _with_sm(case, body)


# -- the read ------------------------------------------------------------------

async def _seed_read(sm):
    """A fixture player with twelve records of five kinds by two moderators
    and the automatic filter, one hour apart from 1 Nov 2026 00:00 UTC; a
    second player's record; one evidence report read of the fixture player."""
    async with sm() as db:
        p, _ = await _player(db, name="Fixture Player")
        o, _ = await _player(db, name="Other Player")
        m1, _ = await _admin(db, name="Mod Alpha", discord_id="420000000000000001")
        m2, _ = await _admin(db, name="Mod Beta")
        plan = [("ban", m1, "griefing 50% of games", {"duration_minutes": 1440}),
                ("chat_mute", m2, "insults", {"channel": "ALL", "duration_minutes": 60}),
                ("chat_automute", "system", "auto: slur filter (offense 1)", {"offense": 1, "duration_minutes": 30}),
                ("record_exclude", m1, "lag abuse", {"board": "fastest_win"}),
                ("flag_review", m2, None, {"review_action": "confirmed_cheat"}),
                ("chat_mute", m1, "spam", {"channel": "global", "duration_minutes": 10}),
                ("ban", m2, "alt account", {}),
                ("chat_automute", "system", "auto: slur filter (offense 2)", {"offense": 2, "duration_minutes": 60}),
                ("record_exclude", m2, "boosting", {"board": "longest_streak"}),
                ("flag_review", m1, None, {"review_action": "false_positive"}),
                ("chat_mute", m2, "threats", {"channel": "ALL", "duration_minutes": 1440}),
                ("ban", m1, "evasion", {"duration_minutes": 10080, "expires_at": "2026-11-23T09:12:00+00:00"})]
        for i, (word, actor, why, details) in enumerate(plan):
            await main._modlog_write(db, actor=actor, action=word, affected=[p], reason=why, details=details)
            # Within one transaction NOW() is fixed, so the row just written is
            # the one fixture row still stamped NOW().
            await db.execute(text(
                "UPDATE admin_actions SET created_at = TIMESTAMPTZ '2026-11-01 00:00:00+00'"
                "       + make_interval(hours => CAST(:h AS integer))"
                " WHERE created_at = NOW() AND affected_steam_ids = ARRAY[CAST(:p AS text)]"),
                {"h": i, "p": p})
        await main._modlog_write(db, actor=m1, action="chat_mute", affected=[o], reason="insults")
        await main._modlog_write(db, actor=m1, action="evidence_report", affected=[p],
                                 details={"shape": "player"})
        await db.commit()
    return {"p": p, "o": o, "m1": m1, "m2": m2, "plan": plan}


def _qp(**kw):
    items = []
    for k, v in kw.items():
        for x in (v if isinstance(v, list) else [v]):
            items.append((k, str(x)))
    return QueryParams(items)


async def _read(sm, **kw):
    f = main._modlog_parse(_qp(**kw))
    async with sm() as db:
        return await main._modlog_answer(db, f)


@pytest.fixture(scope="module")
def world(case):
    return _with_sm(case, _seed_read)


# Each check is a coroutine over (sm, world); the mutants run the same check
# against a mutated read and require it to fail.

async def check_player_filter(sm, w):
    ans = await _read(sm, player=w["p"], limit=100)
    assert ans["total"] == 12, ans["total"]
    assert len(ans["rows"]) == 12
    assert all(w["p"] in [x["steam_id"] for x in r["players"]] for r in ans["rows"])
    assert {c["action"]: c["count"] for c in ans["counts_by_action"]} == {
        "ban": 3, "chat_mute": 3, "chat_automute": 2, "record_exclude": 2, "flag_review": 2}
    assert ans["player"] == {"steam_id": w["p"], "name": "Fixture Player"}
    other = await _read(sm, player=w["o"])
    assert other["total"] == 1 and other["rows"][0]["reason"] == "insults"


async def check_search(sm, w):
    p = w["p"]
    assert [r["reason"] for r in (await _read(sm, player=p, q="INSULT"))["rows"]] == ["insults"]
    assert (await _read(sm, player=p, q="50%"))["total"] == 1             # % is a literal
    assert (await _read(sm, player=p, q="0%"))["total"] == 1
    assert (await _read(sm, player=p, q="automatic"))["total"] == 2       # the label arm
    assert (await _read(sm, player=p, q="longest_streak"))["total"] == 1  # the details arm
    assert (await _read(sm, player=p, q="nothing-like-this"))["total"] == 0


async def check_sort_time(sm, w):
    p = w["p"]
    desc = [r["at"] for r in (await _read(sm, player=p, limit=100))["rows"]]
    asc = [r["at"] for r in (await _read(sm, player=p, limit=100, sort="time", dir="asc"))["rows"]]
    assert desc == sorted(desc, reverse=True), desc
    assert asc == sorted(asc) and asc == desc[::-1], asc
    assert desc[0] == "2026-11-01T11:00:00Z" and asc[0] == "2026-11-01T00:00:00Z"


async def check_sort_action_and_actor(sm, w):
    p = w["p"]
    for key, field in (("action", "action"), ("actor", "actor")):
        a = [r[field] for r in (await _read(sm, player=p, limit=100, sort=key, dir="asc"))["rows"]]
        d = [r[field] for r in (await _read(sm, player=p, limit=100, sort=key, dir="desc"))["rows"]]
        assert a == sorted(a) and d == sorted(d, reverse=True), (key, a, d)


async def check_paging(sm, w):
    p = w["p"]
    pages = [(await _read(sm, player=p, limit=5, offset=o))["rows"] for o in (0, 5, 10)]
    assert [len(x) for x in pages] == [5, 5, 2]
    ids = [r["id"] for pg in pages for r in pg]
    assert len(set(ids)) == 12
    assert (await _read(sm, player=p, limit=5, offset=10000))["rows"] == []


async def check_filters(sm, w):
    p = w["p"]
    assert (await _read(sm, player=p, action=["ban", "flag_review"]))["total"] == 5
    assert (await _read(sm, player=p, actor="system"))["total"] == 2
    assert (await _read(sm, player=p, actor=w["m1"]))["total"] == 5
    assert (await _read(sm, player=p, since="2026-11-01T06:00:00Z"))["total"] == 6
    assert (await _read(sm, player=p, until="2026-11-01T06:00:00Z"))["total"] == 6
    reads = await _read(sm, player=p, include_reads=1)
    assert reads["total"] == 13 and "evidence_report" in [c["action"] for c in reads["counts_by_action"]]
    assert (await _read(sm, player=p, action="evidence_report"))["total"] == 1


async def check_answer_shape(sm, w):
    ans = await _read(sm, player=w["p"], limit=1)
    row = ans["rows"][0]
    assert set(ans) == {"total", "counts_by_action", "limit", "offset", "sort", "dir", "rows", "player"}
    assert set(row) == {"id", "at", "action", "action_label", "actor", "actor_name", "players",
                        "reason", "sentence", "target_steam_id", "target_match_id",
                        "target_series_id", "details"}
    assert row["action"] == "ban" and row["actor_name"] == "Mod Alpha"
    assert row["action_label"] == modlog.label("ban")
    assert row["sentence"].startswith("Banned for 7 days, until 23 Nov 2026 09:12 UTC")
    automute = (await _read(sm, player=w["p"], actor="system", limit=1))["rows"][0]
    assert automute["actor_name"] == "System"


def _go(case, check, w):
    return _with_sm(case, lambda sm: check(sm, w))


@pytest.mark.parametrize("check", [check_player_filter, check_search, check_sort_time,
                                   check_sort_action_and_actor, check_paging, check_filters,
                                   check_answer_shape], ids=lambda c: c.__name__)
def test_read(case, world, check):
    _go(case, check, world)


def test_read_whole_answer_for_the_fixture_player(case, world, capsys):
    """Prints the whole answer for the fixture player (report item 4)."""
    ans = _go(case, lambda sm, w: _read(sm, player=w["p"], limit=100), world)
    with capsys.disabled():
        print("\nMODLOG-ANSWER " + json.dumps(ans, sort_keys=True))
    assert ans["total"] == 12


# The mutants: each read check above must fail when the part it tests is broken.

def _mutant_red(case, world, check, monkeypatch, target, value):
    monkeypatch.setattr(main, target, value)
    with pytest.raises(AssertionError) as e:
        _go(case, check, world)
    line = str(e.value).splitlines()[0][:160] if str(e.value) else repr(e.value)
    print("\nMUTANT-RED %s %s: %s" % (check.__name__, target, line))


def test_mutant_search_without_the_escape_is_red(case, world, monkeypatch):
    _mutant_red(case, world, check_search, monkeypatch, "_modlog_like", lambda q: "%" + q + "%")


def test_mutant_search_without_the_label_arm_is_red(case, world, monkeypatch):
    real = main._modlog_where

    def where(f):
        sql, params = real(f)
        if "mql" in params:
            params["mql"] = []
        return sql, params
    _mutant_red(case, world, check_search, monkeypatch, "_modlog_where", where)


def test_mutant_time_sort_ignoring_dir_is_red(case, world, monkeypatch):
    order = dict(main._MODLOG_ORDER)
    order[("time", "asc")] = order[("time", "desc")]
    _mutant_red(case, world, check_sort_time, monkeypatch, "_MODLOG_ORDER", order)


def test_mutant_player_filter_dropped_is_red(case, world, monkeypatch):
    real = main._modlog_where
    _mutant_red(case, world, check_player_filter, monkeypatch, "_modlog_where",
                lambda f: real({**f, "player": None}))


def test_refusals():
    for kw, word in ((dict(nope=1), "unknown_parameter"),
                     (dict(player="1234"), "player_invalid"),
                     (dict(player=["76561190420000001", "76561190420000002"]), "player_repeated"),
                     (dict(action="dance"), "action_unknown"),
                     (dict(q="x" * 65), "q_too_long"),
                     (dict(sort="name"), "sort_invalid"),
                     (dict(dir="up"), "dir_invalid"),
                     (dict(limit=0), "limit_out_of_range"),
                     (dict(limit=101), "limit_out_of_range"),
                     (dict(limit="ten"), "limit_invalid"),
                     (dict(offset=10001), "offset_out_of_range"),
                     (dict(since="yesterday"), "since_invalid"),
                     (dict(include_reads="maybe"), "include_reads_invalid"),
                     (dict(q="a\x00b"), "q_invalid")):
        with pytest.raises(HTTPException) as e:
            main._modlog_parse(_qp(**kw))
        assert (e.value.status_code, e.value.detail) == (400, word), (kw, e.value.detail)
    # the admin route's own two parameters are refused on the internal twin
    with pytest.raises(HTTPException):
        main._modlog_parse(_qp(admin_steam_id="76561190420000001"), player_may_be_name=True)


class _Req:
    def __init__(self, **kw):
        self.query_params = _qp(**kw)


def test_internal_twin_gate_and_name_lookup(case, world, admin_open):
    w = world

    async def body(sm):
        async def call(discord_id, **kw):
            async with sm() as db:
                return await main.internal_modlog(_Req(**kw), x_internal_key=INTERNAL_KEY,
                                                  x_actor_discord_id=discord_id, db=db)
        ans = await call("420000000000000001", player="fixture player", limit=3)
        assert ans["total"] == 12 and ans["player"]["steam_id"] == w["p"]
        for bad in (None, "", "abc", "420000000000000999"):
            with pytest.raises(HTTPException) as e:
                await call(bad, player=w["p"])
            assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            async with sm() as db:
                await main.internal_modlog(_Req(player=w["p"]), x_internal_key="wrong",
                                           x_actor_discord_id="420000000000000001", db=db)
        assert e.value.status_code in (401, 403)
        with pytest.raises(HTTPException) as e:
            await call("420000000000000001", player="Nobody Has This Name")
        assert (e.value.status_code, e.value.detail) == (404, "player_not_found")
        async with sm() as db:
            await _player(db, name="Twin Name")
            await _player(db, name="twin name")
            await db.commit()
        with pytest.raises(HTTPException) as e:
            await call("420000000000000001", player="Twin Name")
        assert (e.value.status_code, e.value.detail) == (409, "player_ambiguous")
    _with_sm(case, body)


def test_admin_route_refuses_an_unknown_parameter_before_the_signature(case, monkeypatch):
    seen = []

    async def _never(*a, **k):
        seen.append(a)
    monkeypatch.setattr(main, "_require_admin", _never)

    async def body(sm):
        async with sm() as db:
            with pytest.raises(HTTPException) as e:
                await main.admin_modlog(_Req(admin_steam_id="76561190420000001",
                                             hmac_signature="x", nope=1), db=db)
        assert (e.value.status_code, e.value.detail) == (400, "unknown_parameter")
    _with_sm(case, body)
    assert seen == []


def test_the_per_player_read_uses_the_gin_index_on_50000_rows(case, world, capsys):
    """Ruling 6: the plan on 50,000 local rows."""
    async def body(sm):
        async with sm() as db:
            await db.execute(text(
                "INSERT INTO admin_actions (admin_steam_id, action, details, affected_steam_ids)"
                " SELECT 'system', 'chat_automute', '{}'::jsonb,"
                "        ARRAY['7656119042' || lpad(CAST(g AS text), 7, '0')]"
                "   FROM generate_series(1, 50000) g"))
            await db.commit()
        async with sm() as db:
            await db.execute(text("ANALYZE admin_actions"))
            f = main._modlog_parse(_qp(player=world["p"]))
            where, params = main._modlog_where(f)
            plan = (await db.execute(text(
                "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT aa.id FROM admin_actions aa"
                f" WHERE {where} ORDER BY {main._MODLOG_ORDER[('time', 'desc')]}"
                " LIMIT 50"), params)).scalars().all()
            n = (await db.execute(text("SELECT count(*) FROM admin_actions"))).scalar()
        return n, plan
    n, plan = _with_sm(case, body)
    with capsys.disabled():
        print("\nMODLOG-PLAN rows=%d\n%s" % (n, "\n".join(plan)))
    assert n >= 50000
    assert any("ix_admin_actions_affected" in line for line in plan), plan


# -- the deletion path ---------------------------------------------------------

def test_deletion_replaces_the_id_in_every_record_and_keeps_the_reason(case, admin_open, monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", DELETE_SECRET)
    import cf_asm

    async def body(sm):
        async with sm() as db:
            a, _ = await _admin(db)
            gone, gpid = await _player(db, name="Leaving Player")
            stay, _ = await _player(db, name="Staying Player")
            await main._modlog_write(db, actor=a, action="chat_mute", affected=[gone],
                                     target_steam_id=gone, reason="said %s things" % gone)
            await main._modlog_write(db, actor=a, action="reverse_series", affected=[stay, gone])
            await main._modlog_write(db, actor=a, action="ban", affected=[stay])
            await db.commit()
        sig = hmac.new(DELETE_SECRET.encode(), ("delete:%s" % gone).encode(),
                       hashlib.sha256).hexdigest()
        async with sm() as db:
            await main.delete_player_data(gone, cf_asm.FakeRequest(), sig=sig, _slot=None, db=db)
        async with sm() as db:
            rows = await _records(db, a)
            tomb = (await db.execute(text("SELECT steam_id FROM players WHERE id = :i"),
                                     {"i": gpid})).scalar()
        assert tomb.startswith("deleted_")
        # one transaction wrote all three, so created_at ties: compare by word
        by = {r["action"]: r for r in rows}
        assert len(rows) == 3 and set(by) == {"chat_mute", "reverse_series", "ban"}
        assert by["chat_mute"]["affected_steam_ids"] == [tomb]
        assert by["reverse_series"]["affected_steam_ids"] == [stay, tomb]   # in place
        assert by["ban"]["affected_steam_ids"] == [stay]
        assert all(gone not in (r["affected_steam_ids"] or []) for r in rows)
        assert by["chat_mute"]["target_steam_id"] == tomb
        assert by["chat_mute"]["reason"] == "said %s things" % gone     # free text is not rewritten
        assert (await _read(sm, player=gone))["total"] == 0
    _with_sm(case, body)
