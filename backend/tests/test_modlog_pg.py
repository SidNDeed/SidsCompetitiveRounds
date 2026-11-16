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

Migration 420 and its rollback run as files through psql on a second case
schema of their own (the section "migration 420 as a file" at the end): under
each session setting of SETTINGS, two first applies at once, two rollbacks
at once, a session whose bare name admin_actions names a temporary table,
the refusals, and one mutant per pinned line. The psql client:

    MODLOG_TEST_PSQL / CF_PSQL   the psql client (else PATH, else C:/pg16)
"""
import asyncio
import hashlib
import hmac
import io
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from urllib.parse import urlparse

import asyncpg

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


# -- migration 420 as a file ---------------------------------------------------
#
# A second case schema of its own (no row the tests above write, none of the
# 50,000 rows): 420's rollback, a seed written the old way, then 420 under the
# server's defaults is the state every test below starts from and ends in.

M420 = os.path.normpath(os.path.join(HERE, "..", "sql", "420_admin_actions_modlog.sql"))
R420 = os.path.normpath(os.path.join(HERE, "..", "sql", "rollback_420_admin_actions_modlog.sql"))

# Every session setting 420's result could follow. Each is set from OUTSIDE
# the file (PGOPTIONS) for a run of the REAL file, with its verdict and why:
#   "enters"     the setting would move the result; the line named pins it
#   "no effect"  nothing the file parses, prints or compares follows it
#   "refuses"    the file must end with an error, and nothing applied
# "{schema}" is the case schema: the table's own schema, as public is on the
# boxes.
SETTINGS = [
    ("defaults", (), "control",
     "the server's defaults: the run every other row is compared with"),
    ("quote_all_identifiers=on", (("quote_all_identifiers", "on"),), "enters",
     "the deparser would quote the CHECK's column names and the file would refuse its own CHECK;"
     " pinned off for the transaction in the head of 420's first block; types and the index are"
     " compared by"
     " identity, not text"),
    ("search_path=schema,pg_catalog", (("search_path", "{schema},pg_catalog"),), "enters",
     "every bare function, operator and table name would bind by this path, and the deparser"
     " prints by it; 420 resolves the table by it, then pins pg_catalog, the table's schema,"
     " pg_temp"),
    ("search_path=schema,pg_catalog+shadows", (("search_path", "{schema},pg_catalog"),), "enters",
     "as above, with a char_length(text) that answers 0 and an integer <= that answers true in"
     " the table's schema: bound by the session's path, the CHECK would admit any length, and a"
     " correct CHECK would deparse qualified and be refused"),
    ("default_transaction_isolation=repeatable read",
     (("default_transaction_isolation", "repeatable\\ read"),), "enters",
     "a read after the lock would not see a concurrent run's commit; pinned by BEGIN ISOLATION"
     " LEVEL READ COMMITTED (the two-run test runs under it too)"),
    ("default_transaction_isolation=serializable",
     (("default_transaction_isolation", "serializable"),), "enters", "as repeatable read"),
    ("default_transaction_read_only=on", (("default_transaction_read_only", "on"),), "refuses",
     "the transaction is read-only: 420's LOCK fails inside it and nothing is applied"),
    ("IntervalStyle=iso_8601", (("IntervalStyle", "iso_8601"),), "no effect",
     "no interval is printed or compared"),
    ("DateStyle=SQL,DMY", (("DateStyle", "SQL,DMY"),), "no effect",
     "no date or time is printed or compared"),
    ("TimeZone=Pacific/Chatham", (("TimeZone", "Pacific/Chatham"),), "no effect",
     "no time is printed, compared or computed"),
    ("standard_conforming_strings=off", (("standard_conforming_strings", "off"),), "no effect",
     "no literal holds a backslash (the tombstone test is starts_with(target, 'deleted_'))"),
    ("extra_float_digits=3", (("extra_float_digits", "3"),), "no effect",
     "no float is printed or compared"),
    ("default path+plants=true", (), "enters",
     "an `=` that answers true for each pair of PLANT_PAIRS in the table's schema: pg_catalog has no"
     " `=` for exactly oid with regclass, regclass with regclass, oid with regtype or regnamespace,"
     " varchar with varchar or text, text[] with text[], so such a plant is taken even with"
     " pg_catalog first; 420 compares oid with oid and casts varchar to text"),
    ("default path+plants=false", (), "enters", "as above, every plant answering false"),
    ("search_path=schema,pg_catalog+plants=true", (("search_path", "{schema},pg_catalog"),), "enters",
     "as above, with the table's schema searched first, so the plant on name with name is taken"
     " too wherever the path is not pinned"),
    ("search_path=schema,pg_catalog+plants=false", (("search_path", "{schema},pg_catalog"),), "enters",
     "as above, every plant answering false"),
    ("default path+format(text,text)", (), "enters",
     "a format(text, text) in the table's schema: a call format('...', nsp) has an untyped literal,"
     " so it is no exact match of pg_catalog's format(text, VARIADIC \"any\") and the path does not"
     " decide between the two; a bare call takes the plant. 420 writes pg_catalog.format"),
    ("default path+format(text,VARIADIC text[])", (), "enters",
     "as above, with a VARIADIC text[] plant: a bare call takes it on the first apply as on a rerun"),
    ("default path+jsonb arrows(jsonb,jsonb)", (), "enters",
     "a ->> and a -> for jsonb with jsonb in the table's schema: an untyped literal on the right is"
     " read as jsonb first, so a bare details->>'key' takes the plant (pg_catalog has no such pair)."
     " 420 writes OPERATOR(pg_catalog.->>) and OPERATOR(pg_catalog.->)"),
]
SETTING = {s[0]: s for s in SETTINGS}

# The test's own reads compare only pairs pg_catalog has an exact operator
# for (oid with oid, name with name, text with text), so the plants above
# never move them.
ROWS_SQL = ("SELECT coalesce(string_agg(format('%s/%s/%s', a.id, a.xmin, to_jsonb(a)), ' '"
            " ORDER BY a.id), '') FROM admin_actions a")
FILL_SQL = ("SELECT coalesce(string_agg(format('%s/%s/%s', a.id, a.affected_steam_ids,"
            " coalesce(a.reason, '-')), ' ' ORDER BY a.id), '') FROM admin_actions a")
CAT_SQL = (
    "SELECT coalesce(string_agg(x, ' ' ORDER BY x), '') FROM ("
    " SELECT 'class:' || c.relname::text || ':' || c.xmin::text AS x FROM pg_catalog.pg_class c"
    "  WHERE c.oid = to_regclass('admin_actions')::oid"
    "     OR c.oid = to_regclass('ix_admin_actions_affected')::oid"
    " UNION ALL SELECT 'att:' || a.attname::text || ':' || a.xmin::text FROM pg_catalog.pg_attribute a"
    "  WHERE a.attrelid = to_regclass('admin_actions')::oid AND a.attnum > 0"
    " UNION ALL SELECT 'con:' || k.conname::text || ':' || k.xmin::text FROM pg_catalog.pg_constraint k"
    "  WHERE k.conrelid = to_regclass('admin_actions')::oid"
    " UNION ALL SELECT 'idx:' || i.indexrelid::text || ':' || i.xmin::text FROM pg_catalog.pg_index i"
    "  WHERE i.indrelid = to_regclass('admin_actions')::oid"
    " UNION ALL SELECT 'desc:' || d.objsubid::text || ':' || d.xmin::text"
    "  FROM pg_catalog.pg_description d"
    "  WHERE d.objoid = to_regclass('admin_actions')::oid"
    "    AND d.classoid = 'pg_catalog.pg_class'::regclass::oid"
    ") s")
COLS_SQL = ("SELECT count(*) FROM pg_catalog.pg_attribute a"
            " WHERE a.attrelid = to_regclass('admin_actions')::oid"
            " AND a.attname IN ('affected_steam_ids', 'reason') AND NOT a.attisdropped")
OBJS_SQL = ("SELECT (SELECT count(*) FROM pg_catalog.pg_constraint k"
            "         WHERE k.conrelid = to_regclass('admin_actions')::oid"
            "           AND k.conname = 'ck_admin_actions_reason_len')"
            "     + (SELECT count(*) FROM pg_catalog.pg_class c"
            "         WHERE c.oid = to_regclass('ix_admin_actions_affected')::oid)")
# any relation of the index's name in the table's schema, whatever its shape
IDX_ANY_SQL = ("SELECT count(*) FROM pg_catalog.pg_class c WHERE c.relname = 'ix_admin_actions_affected'"
               " AND c.relnamespace = (SELECT t.relnamespace FROM pg_catalog.pg_class t"
               "                        WHERE t.oid = to_regclass('admin_actions')::oid)")
# the index by catalog identity: GIN, array_ops, one key column that is
# affected_steam_ids, valid, no expression, no predicate
IDX_SQL = (
    "SELECT count(*) FROM pg_catalog.pg_index i"
    "  JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid"
    "  JOIN pg_catalog.pg_am am ON am.oid = ic.relam"
    "  JOIN pg_catalog.pg_opclass oc ON oc.oid = i.indclass[0]"
    "  JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]"
    " WHERE i.indrelid = to_regclass('admin_actions')::oid AND ic.relname = 'ix_admin_actions_affected'"
    "   AND am.amname = 'gin' AND oc.opcname = 'array_ops' AND i.indnatts = 1"
    "   AND a.attname = 'affected_steam_ids' AND i.indisvalid"
    "   AND i.indexprs IS NULL AND i.indpred IS NULL")

_P = ["7656119000000000%d" % i for i in range(1, 7)]
_U = "00000000-0000-0000-0000-0000000001%02d"
# Rows written the old way (before 420's columns). Row 14 is the probe of the
# tombstone test: its target begins "deleted" but not "deleted_".
SEED_420 = """
INSERT INTO players (id, steam_id, display_name) VALUES
 ('00000000-0000-0000-0000-0000000000a1', '76561190000000001', 'Seed One'),
 ('00000000-0000-0000-0000-0000000000a2', '76561190000000002', 'Seed Two'),
 ('00000000-0000-0000-0000-0000000000a3', '76561190000000003', 'Seed Three'),
 ('00000000-0000-0000-0000-0000000000a4', '76561190000000004', 'Seed Four'),
 ('00000000-0000-0000-0000-0000000000a5', '76561190000000005', 'Seed Five'),
 ('00000000-0000-0000-0000-0000000000a6', '76561190000000006', 'Seed Six'),
 ('00000000-0000-0000-0000-0000000000a7', 'deleted_abc12345', '[Deleted User]');
INSERT INTO ranked_series (id, player1_id, player2_id, p1_series_wins, p2_series_wins, status, created_at,
                           live_p1_points, live_p2_points, is_tournament, is_private)
VALUES ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000a2',
        '00000000-0000-0000-0000-0000000000a3', 2, 0, 'completed', NOW(), 0, 0, false, false),
       ('00000000-0000-0000-0000-0000000000b2', '00000000-0000-0000-0000-0000000000a7',
        '00000000-0000-0000-0000-0000000000a4', 2, 0, 'completed', NOW(), 0, 0, false, false);
INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id)
VALUES ('00000000-0000-0000-0000-0000000000c1', '00000000-0000-0000-0000-0000000000a1',
        '00000000-0000-0000-0000-0000000000a2', '00000000-0000-0000-0000-0000000000a3',
        '00000000-0000-0000-0000-0000000000a4');
INSERT INTO matches (id, player1_id, player2_id, p1_rounds_won, p2_rounds_won)
VALUES ('00000000-0000-0000-0000-0000000000d1', '00000000-0000-0000-0000-0000000000a5',
        '00000000-0000-0000-0000-0000000000a6', 3, 1);
INSERT INTO chat_messages (id, source, display_name, message, steam_id)
VALUES (900001, 'game', 'Seed Six', 'hello', '76561190000000006'),
       (900002, 'game', 'gone', 'bye', 'deleted_abc12345');
INSERT INTO admin_actions (id, admin_steam_id, action, target_steam_id, target_series_id, details) VALUES
 ('00000000-0000-0000-0000-000000000101', '76561190000000099', 'ban', '76561190000000001', NULL, '{"reason": "cheating"}'),
 ('00000000-0000-0000-0000-000000000102', '76561190000000099', 'unban', '76561190000000001', NULL, '{"rows": 1}'),
 ('00000000-0000-0000-0000-000000000103', '76561190000000099', 'ban', 'deleted_abc12345', NULL, '{"reason": "old"}'),
 ('00000000-0000-0000-0000-000000000104', '76561190000000099', 'reverse_series', NULL,
  '00000000-0000-0000-0000-0000000000b1', '{"matches_reversed": 2}'),
 ('00000000-0000-0000-0000-000000000105', '76561190000000099', 'reverse_series', NULL,
  '00000000-0000-0000-0000-0000000000b2', '{}'),
 ('00000000-0000-0000-0000-000000000106', 'internal-key', 'resolve_team_series', NULL,
  '00000000-0000-0000-0000-0000000000c1', '{"action": "void"}'),
 ('00000000-0000-0000-0000-000000000107', '76561190000000099', 'record_exclude', NULL, NULL,
  '{"match_id": "00000000-0000-0000-0000-0000000000d1", "board": "*", "reason": "lag abuse"}'),
 ('00000000-0000-0000-0000-000000000108', '76561190000000099', 'chat_delete', NULL, NULL, '{"message_id": 900001}'),
 ('00000000-0000-0000-0000-000000000109', '76561190000000099', 'chat_delete', NULL, NULL, '{"message_ids": [900002]}'),
 ('00000000-0000-0000-0000-000000000110', '76561190000000099', 'ban_rate_blocked', '76561190000000001', NULL,
  '{"recent_bans": 5}'),
 ('00000000-0000-0000-0000-000000000111', 'discord:1', 'chat_mute', '123', NULL, '{"reason": "spam"}'),
 ('00000000-0000-0000-0000-000000000112', '76561190000000099', 'chat_mute', '76561190000000005', NULL,
  jsonb_build_object('reason', repeat('x', 300))),
 ('00000000-0000-0000-0000-000000000113', '76561190000000099', 'chat_lockdown', NULL, NULL, '{"locked": true}'),
 ('00000000-0000-0000-0000-000000000114', '76561190000000099', 'reverse_series', 'deletedXnote',
  '00000000-0000-0000-0000-0000000000b1', '{}');
"""
EXPECT_420 = [
    (_U % 1, [_P[0]], "cheating"),
    (_U % 2, [_P[0]], None),
    (_U % 3, [], "old"),                       # a tombstone target keeps '{}'
    (_U % 4, [_P[1], _P[2]], None),
    (_U % 5, [_P[3]], None),                   # the deleted player is not named
    (_U % 6, _P[:4], None),
    (_U % 7, [_P[4], _P[5]], "lag abuse"),
    (_U % 8, [_P[5]], None),
    (_U % 9, [], None),                        # the author's account was deleted
    (_U % 10, [], None),                       # a word that names no player
    (_U % 11, [], "spam"),                     # not a 17-digit id
    (_U % 12, [_P[4]], "x" * 256),             # the reason cut to 256
    (_U % 13, [], None),
    (_U % 14, [_P[1], _P[2]], None),           # "deletedX..." is no tombstone
]


def _psql_client():
    for var in ("MODLOG_TEST_PSQL", "CF_PSQL"):
        named = os.environ.get(var)
        if named and (os.path.isfile(named) or shutil.which(named)):
            return named
    found = shutil.which("psql")
    if found:
        return found
    fallback = "C:/pg16/pgsql/bin/psql.exe"
    return fallback if os.path.isfile(fallback) else None


def _psql_args(schema, settings=(), appname=None, tuples=False):
    """psql with ON_ERROR_STOP, bound to the case schema by the startup
    packet's search path; `settings` are further session settings given the
    same way, from OUTSIDE the file (name, value; a later one wins)."""
    psql = _psql_client()
    assert psql is not None, "no psql client found (set MODLOG_TEST_PSQL or put psql on PATH)"
    u = urlparse(lh.DSN)
    opts = ["-c search_path=%s" % schema] + ["-c %s=%s" % (k, v.format(schema=schema))
                                              for k, v in settings]
    env = dict(os.environ, PGOPTIONS=" ".join(opts))
    env.pop("PGAPPNAME", None)
    if appname:
        env["PGAPPNAME"] = appname
    if u.password:
        env["PGPASSWORD"] = u.password
    args = [psql, "-X", "-q", "-w", "-v", "ON_ERROR_STOP=1", "-h", u.hostname or "localhost",
            "-p", str(u.port or 5432), "-d", u.path.lstrip("/")]
    if u.username:
        args += ["-U", u.username]
    if tuples:
        args += ["-A", "-t"]
    return args, env


def _psql_apply(schema, path, settings=(), prefix=""):
    """The file on psql's stdin (after `prefix`): (exit code, stderr)."""
    args, env = _psql_args(schema, settings)
    with open(path, "rb") as fh:
        data = prefix.encode("utf-8") + fh.read()
    p = subprocess.run(args, input=data, env=env, capture_output=True, timeout=180)
    return p.returncode, p.stderr.decode("utf-8", "replace")


def _variant(path, old, new):
    """A copy of the file at `path` with the one occurrence of `old` replaced."""
    src = io.open(path, encoding="utf-8").read()
    assert src.count(old) == 1, ("the mutant's text is not in the file exactly once", old)
    fd, out = tempfile.mkstemp(prefix="modlog420_", suffix=".sql")
    with io.open(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(src.replace(old, new))
    return out


def _fetch(schema, sql):
    async def go():
        c = await harness.connect_bound(lh.DSN, schema)
        try:
            return await c.fetchval(sql)
        finally:
            await c.close()
    return _run(go())


def _exec(schema, sql):
    async def go():
        c = await harness.connect_bound(lh.DSN, schema)
        try:
            await c.execute(sql)
        finally:
            await c.close()
    _run(go())


def _snap(schema):
    """(every admin_actions row with its xmin, the table's catalog rows with
    theirs): equal before and after a run = the run wrote no row."""
    async def go():
        c = await harness.connect_bound(lh.DSN, schema)
        try:
            return (await c.fetchval(ROWS_SQL), await c.fetchval(CAT_SQL))
        finally:
            await c.close()
    return _run(go())


def _seed_rows(schema):
    async def go():
        c = await harness.connect_bound(lh.DSN, schema)
        try:
            return [(r["id"], list(r["affected_steam_ids"]), r["reason"]) for r in await c.fetch(
                "SELECT id::text AS id, affected_steam_ids, reason FROM admin_actions ORDER BY id")]
        finally:
            await c.close()
    return _run(go())


def _reason_verdicts(schema):
    """What the table does with a reason of 257 and 256 characters and none."""
    async def go():
        c = await harness.connect_bound(lh.DSN, schema)
        out = {}
        try:
            for label, value in (("257", "r" * 257), ("256", "r" * 256), ("null", None)):
                tr = c.transaction()
                await tr.start()
                try:
                    await c.execute(
                        "INSERT INTO admin_actions (admin_steam_id, action, details, reason)"
                        " VALUES ('76561190000000099', 'chat_mute', '{}'::jsonb, $1::text)", value)
                    out[label] = "admitted"
                except asyncpg.exceptions.CheckViolationError:
                    out[label] = "refused"
                finally:
                    await tr.rollback()
        finally:
            await c.close()
        return out
    return _run(go())


def _plant_of(name):
    """The objects an entry of SETTINGS plants in the table's own schema."""
    for kind in ("shadows", "plants=true", "plants=false") + tuple(CALL_PLANTS):
        if name.endswith("+" + kind):
            return kind
    return None


# Same-named objects in the table's schema whose argument types are NOT those
# of pg_catalog's own (S1 of the fix order): the path decides only between
# identical argument types, so each is taken by a bare call or operator whose
# arguments are no exact match of pg_catalog's; only the schema written at the
# call keeps pg_catalog's. (create, drop) per kind.
CALL_PLANTS = {
    "format(text,text)": (
        "CREATE FUNCTION {s}.format(text, text) RETURNS text LANGUAGE sql IMMUTABLE"
        " AS 'SELECT ''modlog_plant''';",
        "DROP FUNCTION IF EXISTS {s}.format(text, text);"),
    "format(text,VARIADIC text[])": (
        "CREATE FUNCTION {s}.format(text, VARIADIC text[]) RETURNS text LANGUAGE sql IMMUTABLE"
        " AS 'SELECT ''modlog_plant''';",
        "DROP FUNCTION IF EXISTS {s}.format(text, VARIADIC text[]);"),
    "jsonb arrows(jsonb,jsonb)": (
        "CREATE FUNCTION {s}.modlog_arrow_text(jsonb, jsonb) RETURNS text LANGUAGE sql IMMUTABLE"
        " AS 'SELECT ''modlog_plant''';"
        " CREATE OPERATOR {s}.->> (LEFTARG = jsonb, RIGHTARG = jsonb, FUNCTION = {s}.modlog_arrow_text);"
        " CREATE FUNCTION {s}.modlog_arrow_json(jsonb, jsonb) RETURNS jsonb LANGUAGE sql IMMUTABLE"
        " AS 'SELECT ''\"modlog_plant\"''::jsonb';"
        " CREATE OPERATOR {s}.-> (LEFTARG = jsonb, RIGHTARG = jsonb, FUNCTION = {s}.modlog_arrow_json);",
        "DROP OPERATOR IF EXISTS {s}.->> (jsonb, jsonb); DROP FUNCTION IF EXISTS {s}.modlog_arrow_text(jsonb, jsonb);"
        " DROP OPERATOR IF EXISTS {s}.-> (jsonb, jsonb); DROP FUNCTION IF EXISTS {s}.modlog_arrow_json(jsonb, jsonb);"),
    "format_type(oid,text)": (
        "CREATE FUNCTION {s}.format_type(oid, text) RETURNS text LANGUAGE sql IMMUTABLE"
        " AS 'SELECT ''modlog_plant''';",
        "DROP FUNCTION IF EXISTS {s}.format_type(oid, text);"),
}


# The pairs of argument types that pg_catalog has no `=` for exactly (it
# compares them through a cast), so an exact `=` in a schema on the path is
# taken for them; and name with name, which pg_catalog has, so a plant is
# taken only when the path searches the table's schema before pg_catalog.
PLANT_PAIRS = [("oid", "regclass"), ("regclass", "oid"), ("regclass", "regclass"),
               ("oid", "regtype"), ("oid", "regnamespace"), ("name", "name"),
               ("varchar", "varchar"), ("text", "varchar"), ("varchar", "text"),
               ("text[]", "text[]")]


def _plant(schema, kind, on):
    """kind "shadows": a char_length(text) that answers 0 and an integer <=
    that answers true. kind "plants=true" / "plants=false": an `=` for each
    pair of PLANT_PAIRS that always answers true / false. All in the table's
    own schema."""
    s = harness.quoted(schema)
    if kind in CALL_PLANTS:
        _exec(schema, CALL_PLANTS[kind][0 if on else 1].format(s=s))
        return
    if kind == "shadows":
        if on:
            _exec(schema, (
                "CREATE FUNCTION {s}.char_length(text) RETURNS integer LANGUAGE sql IMMUTABLE"
                " AS 'SELECT 0';"
                " CREATE FUNCTION {s}.modlog_le_true(integer, integer) RETURNS boolean LANGUAGE sql"
                " IMMUTABLE AS 'SELECT true';"
                " CREATE OPERATOR {s}.<= (LEFTARG = integer, RIGHTARG = integer,"
                " FUNCTION = {s}.modlog_le_true)").format(s=s))
        else:
            _exec(schema, (
                "DROP OPERATOR IF EXISTS {s}.<= (integer, integer);"
                " DROP FUNCTION IF EXISTS {s}.modlog_le_true(integer, integer);"
                " DROP FUNCTION IF EXISTS {s}.char_length(text)").format(s=s))
        return
    answer = kind.split("=")[1]
    sql = []
    for i, (left, right) in enumerate(PLANT_PAIRS):
        if on:
            sql.append("CREATE FUNCTION {s}.modlog_eq_{i}({l}, {r}) RETURNS boolean LANGUAGE sql"
                       " IMMUTABLE AS 'SELECT {a}'; CREATE OPERATOR {s}.= (LEFTARG = {l},"
                       " RIGHTARG = {r}, FUNCTION = {s}.modlog_eq_{i});"
                       .format(s=s, i=i, l=left, r=right, a=answer))
        else:
            sql.append("DROP OPERATOR IF EXISTS {s}.= ({l}, {r});"
                       " DROP FUNCTION IF EXISTS {s}.modlog_eq_{i}({l}, {r});"
                       .format(s=s, i=i, l=left, r=right))
    _exec(schema, " ".join(sql))


def _restore(schema, plant=None):
    """Back to the state every test starts from: 420 applied under the
    server's defaults. Planted operators go first; shadows go after the
    rollback (a CHECK a mutant bound to a shadow depends on it)."""
    if plant in ("plants=true", "plants=false") or plant in CALL_PLANTS:
        _plant(schema, plant, False)
    rc, err = _psql_apply(schema, R420)
    assert rc == 0, err
    if plant == "shadows":
        _plant(schema, plant, False)
    rc, err = _psql_apply(schema, M420)
    assert rc == 0, err



def _tail(err):
    return " ".join(err.split())[-400:]


@pytest.fixture(scope="module")
def mcase():
    lh._require_live_pg()
    built = {}

    async def build():
        c = harness.CaseSchema(lh.DSN, "modlogm")
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


@pytest.fixture(scope="module")
def m420(mcase):
    """The rollback, the seed written the old way, 420 under the defaults;
    the fills read back against what each row names. Answers the fills'
    text, which every run under a setting must give again."""
    rc, err = _psql_apply(mcase, R420)
    assert rc == 0, err
    _exec(mcase, SEED_420)
    rc, err = _psql_apply(mcase, M420)
    assert rc == 0, err
    assert _seed_rows(mcase) == EXPECT_420
    return _fetch(mcase, FILL_SQL)


def _rolled_back_failures(schema, label):
    """After a rollback: the two columns, the check and the index are gone
    (by catalog identity), and a row in the shape the api before 420 writes
    is admitted."""
    fails = []
    if _fetch(schema, COLS_SQL) != 0:
        fails.append(label + "-LEFT-COLUMNS")
    if _fetch(schema, OBJS_SQL) != 0 or _fetch(schema, IDX_ANY_SQL) != 0:
        fails.append(label + "-LEFT-INDEX-OR-CHECK")
    try:
        _exec(schema, "BEGIN; INSERT INTO admin_actions (admin_steam_id, action, details)"
                      " VALUES ('76561190000000099', 'chat_mute', '{}'::jsonb); ROLLBACK")
    except Exception as e:   # noqa: BLE001 - the label carries it
        fails.append(label + "-OLD-SHAPE-INSERT-REFUSED %s" % e)
    return fails


def _settings_failures(schema, s0, settings, verdict, plant=None, path=M420, rpath=R420):
    """The REAL files (or those at `path` / `rpath`) under `settings`, from
    the state "420 applied under the defaults": an apply over that result;
    then the rollback, a first apply and an apply again; then the rollback
    and a rollback again. Answers the labelled failures (empty = as the
    verdict says)."""
    fails = []
    try:
        if plant:
            _plant(schema, plant, True)
        before = _snap(schema)
        rc, err = _psql_apply(schema, path, settings)
        if verdict == "refuses":
            if rc == 0 or "read-only transaction" not in err:
                fails.append("SECOND-APPLY-NOT-REFUSED rc=%s %s" % (rc, _tail(err)))
            if _snap(schema) != before:
                fails.append("SECOND-APPLY-CHANGED")
            rc, err = _psql_apply(schema, rpath, settings)
            if rc == 0 or "read-only transaction" not in err:
                fails.append("ROLLBACK-NOT-REFUSED rc=%s %s" % (rc, _tail(err)))
            if _snap(schema) != before or _fetch(schema, IDX_SQL) != 1:
                fails.append("ROLLBACK-CHANGED")
            rc, err = _psql_apply(schema, R420)
            assert rc == 0, err
            before = _snap(schema)
            rc, err = _psql_apply(schema, path, settings)
            if rc == 0 or "read-only transaction" not in err:
                fails.append("FIRST-APPLY-NOT-REFUSED rc=%s %s" % (rc, _tail(err)))
            if _snap(schema) != before:
                fails.append("FIRST-APPLY-CHANGED")
            if _fetch(schema, COLS_SQL) != 0 or _fetch(schema, OBJS_SQL) != 0:
                fails.append("FIRST-APPLY-LEFT-OBJECTS")
            return fails
        if rc != 0:
            fails.append("SECOND-APPLY-RC rc=%s %s" % (rc, _tail(err)))
        elif _snap(schema) != before:
            fails.append("SECOND-APPLY-CHANGED")
        rc, err = _psql_apply(schema, rpath, settings)
        if rc != 0:
            fails.append("ROLLBACK-RC rc=%s %s" % (rc, _tail(err)))
        fails += _rolled_back_failures(schema, "ROLLBACK")
        if fails and any(f.startswith("ROLLBACK") for f in fails):
            return fails
        rc, err = _psql_apply(schema, path, settings)
        if rc != 0:
            fails.append("FIRST-APPLY-RC rc=%s %s" % (rc, _tail(err)))
            return fails
        if _fetch(schema, FILL_SQL) != s0:
            fails.append("FILL-DIFFERS")
        verdicts = _reason_verdicts(schema)
        if verdicts != {"257": "refused", "256": "admitted", "null": "admitted"}:
            fails.append("CHECK-BEHAVIOUR %r" % (verdicts,))
        if _fetch(schema, IDX_SQL) != 1:
            fails.append("INDEX-IDENTITY")
        before = _snap(schema)
        rc, err = _psql_apply(schema, path, settings)
        if rc != 0:
            fails.append("RERUN-RC rc=%s %s" % (rc, _tail(err)))
        elif _snap(schema) != before:
            fails.append("RERUN-CHANGED")
        rc, err = _psql_apply(schema, rpath, settings)
        if rc != 0:
            fails.append("LAST-ROLLBACK-RC rc=%s %s" % (rc, _tail(err)))
        fails += _rolled_back_failures(schema, "LAST-ROLLBACK")
        before = _snap(schema)
        rc, err = _psql_apply(schema, rpath, settings)
        if rc != 0:
            fails.append("ROLLBACK-RERUN-RC rc=%s %s" % (rc, _tail(err)))
        elif _snap(schema) != before:
            fails.append("ROLLBACK-RERUN-CHANGED")
        return fails
    finally:
        _restore(schema, plant=plant)


@pytest.mark.parametrize("name,settings,verdict,why", SETTINGS, ids=[s[0] for s in SETTINGS])
def test_420_gives_one_result_under_each_session_setting(mcase, m420, name, settings, verdict, why,
                                                        capsys):
    """The ONE generated test: the real file and the real rollback under each
    setting of SETTINGS. An apply over the defaults' result, a first apply
    and an apply again all end rc 0; neither later apply changes an
    admin_actions row or a catalog row of the table; the fills are the
    defaults' fills; a reason of 257 characters is refused, 256 and NULL
    admitted; the index is GIN on the column by catalog identity. The
    rollback ends rc 0 with both columns, the check and the index gone (by
    catalog identity) and a row of the old shape admitted, and a rollback
    again changes nothing. Under a read-only default each file ends with an
    error and nothing is applied or dropped."""
    fails = _settings_failures(mcase, m420, settings, verdict, plant=_plant_of(name))
    with capsys.disabled():
        print("\nMODLOG-SETTING %s [%s] %s" % (name, verdict, fails or "as the verdict says"))
    assert not fails, "%s (%s): %s" % (name, why, fails)


_QAI_PIN = ("  PERFORM pg_catalog.set_config('quote_all_identifiers', 'off', true);"
            "   -- the CHECK's deparsed text is compared below\n")
_PATH_PIN = ("  PERFORM pg_catalog.set_config('search_path',\n"
             "    pg_catalog.format('pg_catalog, %I, pg_temp', nsp), true);   -- names bind as written\n")
_TOMB = "NOT pg_catalog.starts_with(a.target_steam_id::text, 'deleted_')"
_OID_IDENTITY = ("  IF pg_catalog.to_regclass('admin_actions')::oid IS DISTINCT FROM tbl THEN"
                 "   -- the bare name names the same table\n")
_TBL_OID = ("  tbl pg_catalog.oid := pg_catalog.to_regclass(\n"
            "    pg_catalog.format('%I.admin_actions', pg_catalog.current_schema()))::pg_catalog.oid;\n")
_CHAT_JOIN = "JOIN players p ON p.steam_id::text = cm.steam_id::text"
# S1: the sites a same-named function or operator of other argument types
# takes when written without pg_catalog (each mutant below drops the schema).
_S1_IDX_FORMAT = "  idx := pg_catalog.to_regclass(pg_catalog.format('%I.ix_admin_actions_affected', nsp))::oid;\n"
_S1_POST_FORMAT = ("       WHERE i.indexrelid = pg_catalog.to_regclass(pg_catalog.format("
                   "'%I.ix_admin_actions_affected', nsp))::oid\n")
_S1_REASON_OP = "   SET reason = pg_catalog.left(details OPERATOR(pg_catalog.->>) 'reason', 256)\n"


@pytest.mark.parametrize("pin,old,new,setting,expect", [
    ("quote_all_identifiers off", _QAI_PIN, "", "quote_all_identifiers=on",
     ("SECOND-APPLY-RC", "FIRST-APPLY-RC")),
    ("the search path pinned", _PATH_PIN, "", "search_path=schema,pg_catalog+shadows",
     ("SECOND-APPLY-RC", "CHECK-BEHAVIOUR")),
    ("the tombstone test without a backslash", _TOMB, "a.target_steam_id::text NOT LIKE 'deleted\\_%'",
     "standard_conforming_strings=off", ("FILL-DIFFERS",)),
    ("the table's identity held as an oid", _TBL_OID,
     "  tbl pg_catalog.regclass := pg_catalog.to_regclass(\n"
     "    pg_catalog.format('%I.admin_actions', pg_catalog.current_schema()));\n",
     "default path+plants=false", ("SECOND-APPLY-RC",)),
    ("varchar ids compared as text", _CHAT_JOIN, "JOIN players p ON p.steam_id = cm.steam_id",
     "default path+plants=false", ("FILL-DIFFERS",)),
    ("the index lookup's format names pg_catalog", _S1_IDX_FORMAT, _S1_IDX_FORMAT.replace("(pg_catalog.format(", "(format("),
     "default path+format(text,text)", ("SECOND-APPLY-RC",)),
    ("the post-check's format names pg_catalog", _S1_POST_FORMAT,
     _S1_POST_FORMAT.replace("(pg_catalog.format(", "(format("),
     "default path+format(text,VARIADIC text[])", ("SECOND-APPLY-RC", "FIRST-APPLY-RC")),
    ("the reason copy's ->> names pg_catalog", _S1_REASON_OP,
     _S1_REASON_OP.replace(" OPERATOR(pg_catalog.->>) ", "->>"),
     "default path+jsonb arrows(jsonb,jsonb)", ("SECOND-APPLY-RC",)),
], ids=["quote_all_identifiers", "search_path", "tombstone_literal", "oid_identity", "varchar_as_text",
        "s1_idx_lookup", "s1_post_check", "s1_reason_op"])
def test_mutant_420_without_its_pin_is_red_under_its_setting(mcase, m420, pin, old, new, setting,
                                                            expect, capsys):
    """One mutant per pinned line of the settings list: the file without that
    line, run under the setting the line pins, fails the generated test for
    the line's stated reason (the control is the generated test itself)."""
    path = _variant(M420, old, new)
    try:
        s = SETTING[setting]
        fails = _settings_failures(mcase, m420, s[1], s[2], plant=_plant_of(setting), path=path)
    finally:
        os.unlink(path)
    with capsys.disabled():
        print("\nMODLOG-MUTANT %s under %s: %s" % (pin, setting, fails))
    for label in expect:
        assert any(f.startswith(label) for f in fails), (label, fails)


_R_DROP_REASON = "ALTER TABLE admin_actions DROP COLUMN IF EXISTS reason;\n"
_R_POST = "-- Its own result: each of the four is gone"


def test_the_rollback_refuses_to_end_with_an_object_standing(mcase, m420, capsys):
    """The rollback's own check of its result: a rollback whose drop of the
    reason column is cut ends in an error with nothing dropped (the control);
    the same file without the check ends rc 0 with the column standing (the
    mutant, red)."""
    cut = _variant(R420, _R_DROP_REASON, "")
    src = io.open(cut, encoding="utf-8").read()
    start, end = src.index(_R_POST), src.index("END $post420r$;") + len("END $post420r$;")
    fd, nocheck = tempfile.mkstemp(prefix="modlog420_", suffix=".sql")
    with io.open(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(src[:start] + src[end:])
    try:
        before = _snap(mcase)
        rc, err = _psql_apply(mcase, cut)
        control = (rc, "still standing after the drops: column reason" in err, _snap(mcase) == before)
        rc2, err2 = _psql_apply(mcase, nocheck)
        mutant = (rc2, _fetch(mcase, COLS_SQL))
    finally:
        os.unlink(cut)
        os.unlink(nocheck)
        _restore(mcase)
    with capsys.disabled():
        print("\nMODLOG-ROLLBACK-SELF-CHECK control (rc, named, nothing dropped)=%r;"
              " MODLOG-MUTANT without the check (rc, columns standing)=%r" % (control, mutant))
    assert control[0] != 0 and control[1] and control[2], (control, _tail(err))
    assert mutant == (0, 1), "the mutant without the check must end rc 0 with reason standing"


# -- two runs at once ------------------------------------------------------------

def _without_commit(path):
    src = io.open(path, encoding="utf-8").read()
    body, tail = src.rstrip().rsplit("\n", 1)
    assert tail.strip() == "COMMIT;", tail
    return body + "\n"


async def _wait_for_lock_wait(obs, appname, limit_s=10.0):
    """True once the session named `appname` waits on a lock."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_s
    while loop.time() < deadline:
        if await obs.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name = $1"
                " AND wait_event_type = 'Lock'", appname):
            return True
        await asyncio.sleep(0.05)
    return False


async def _two_runs(schema, path, settings=()):
    """Run A (psql) runs the file at `path` up to its last line, COMMIT, then
    reads the rows and the catalog on its OWN connection into a file; run B
    (psql, the whole file) starts and is observed waiting on a lock; then A
    commits and B ends."""
    loop = asyncio.get_running_loop()
    tmp = tempfile.mkdtemp(prefix="modlog420_")
    snap = os.path.join(tmp, "a_snap.txt").replace("\\", "/")
    a_out_path, a_err_path = os.path.join(tmp, "a_out.txt"), os.path.join(tmp, "a_err.txt")
    out = {}
    obs = await harness.connect_bound(lh.DSN, schema)
    a = b = None
    a_out, a_err = open(a_out_path, "wb"), open(a_err_path, "wb")
    try:
        out["pre"] = (await obs.fetchval(ROWS_SQL), await obs.fetchval(CAT_SQL))
        args, env = _psql_args(schema, settings, appname="modlog_a_" + uuid.uuid4().hex[:8], tuples=True)
        a = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=a_out, stderr=a_err, env=env)
        a.stdin.write((_without_commit(path) + "\\o '%s'\n" % snap + ROWS_SQL + ";\n" + CAT_SQL
                       + ";\n\\qecho A-SNAP-END\n\\o\n").encode("utf-8"))
        a.stdin.flush()
        deadline, text_ = loop.time() + 60, ""
        while loop.time() < deadline:
            if os.path.exists(snap):
                text_ = io.open(snap, encoding="utf-8").read()
                if "A-SNAP-END" in text_:
                    break
            if a.poll() is not None:
                break
            await asyncio.sleep(0.05)
        lines = text_.splitlines()
        out["a_ready"] = len(lines) >= 3 and lines[2] == "A-SNAP-END"
        if out["a_ready"]:
            out["a_own"] = (lines[0], lines[1])
            appname = "modlog_b_" + uuid.uuid4().hex[:8]
            bargs, benv = _psql_args(schema, settings, appname=appname)
            with open(path, "rb") as fh:
                b = subprocess.Popen(bargs, stdin=fh, env=benv, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
            out["b_waited"] = await _wait_for_lock_wait(obs, appname)
        if a.poll() is None:
            a.stdin.write(b"COMMIT;\n")
            a.stdin.close()
        out["a_rc"] = await loop.run_in_executor(None, lambda: a.wait(timeout=60))
        if b is not None:
            _o, e = await loop.run_in_executor(None, lambda: b.communicate(timeout=60))
            out["b"] = (b.returncode, e.decode("utf-8", "replace"))
        out["after"] = (await obs.fetchval(ROWS_SQL), await obs.fetchval(CAT_SQL))
    except BaseException:
        for p in (a, b):
            if p is not None and p.poll() is None:
                p.kill()
        raise
    finally:
        await obs.close()
        a_out.close()
        a_err.close()
    out["a_err"] = io.open(a_err_path, encoding="utf-8", errors="replace").read()
    for f in (snap, a_out_path, a_err_path):
        if os.path.exists(f):
            os.unlink(f)
    os.rmdir(tmp)
    return out


def _two_run_failures(out):
    fails = []
    if not out.get("a_ready"):
        fails.append("A-NOT-READY %s" % _tail(out.get("a_err", "")))
        return fails
    if not out.get("b_waited"):
        fails.append("B-NOT-WAITED")
    if out.get("a_rc") != 0:
        fails.append("A-RC rc=%s %s" % (out.get("a_rc"), _tail(out.get("a_err", ""))))
    b_rc, b_err = out.get("b", (None, ""))
    if b_rc != 0:
        fails.append("B-RC rc=%s %s" % (b_rc, _tail(b_err)))
    if out["after"][0] != out["a_own"][0]:
        fails.append("B-CHANGED-ROWS")
    if out["after"][1] != out["a_own"][1]:
        fails.append("B-CHANGED-CATALOG")
    if out["a_own"] == out["pre"]:
        fails.append("A-CHANGED-NOTHING")
    return fails


def _first_applies_failures(schema, s0, path, settings=()):
    """Two first applies of the file at `path` at once (after the rollback);
    the rows and the catalog as A leaves them, read on A's own connection
    before its COMMIT, against the same after B."""
    rc, err = _psql_apply(schema, R420)
    assert rc == 0, err
    try:
        fails = _two_run_failures(_run(_two_runs(schema, path, settings)))
        if _fetch(schema, COLS_SQL) != 2:
            fails.append("COLUMNS-MISSING")
        elif _fetch(schema, FILL_SQL) != s0:
            fails.append("FILL-DIFFERS")
        return fails
    finally:
        _restore(schema)


ISOLATIONS = [
    ("default", ()),
    ("repeatable read", (("default_transaction_isolation", "repeatable\\ read"),)),
    ("serializable", (("default_transaction_isolation", "serializable"),)),
]


@pytest.mark.parametrize("label,settings", ISOLATIONS, ids=[i[0] for i in ISOLATIONS])
def test_two_first_applies_of_420_at_once_end_as_two_in_sequence(mcase, m420, label, settings, capsys):
    """Class 1: the lock first and every precondition read under it, at READ
    COMMITTED whatever the session's default. B waits on the lock A holds;
    both end rc 0; B changes no row and no catalog row of the table (the
    rows and the catalog as A left them, read on A's own connection before
    its COMMIT)."""
    fails = _first_applies_failures(mcase, m420, M420, settings)
    with capsys.disabled():
        print("\nMODLOG-TWO-APPLIES %s: %s" % (label, fails or "both rc 0, B changed nothing"))
    assert not fails, fails


_LOCK_FIRST = "  LOCK TABLE admin_actions IN ACCESS EXCLUSIVE MODE;   -- every read below runs under it\n"
_BEGIN_RC = "BEGIN ISOLATION LEVEL READ COMMITTED;   -- reads after the lock see a concurrent run's commit\n"


@pytest.mark.parametrize("pin,old,new,isolation", [
    ("the lock first", _LOCK_FIRST, "", "default"),
    ("BEGIN ISOLATION LEVEL READ COMMITTED", _BEGIN_RC, "BEGIN;\n", "repeatable read"),
], ids=["lock_first", "read_committed"])
def test_mutant_420_without_its_pin_fails_the_second_of_two_applies(mcase, m420, pin, old, new,
                                                                   isolation, capsys):
    """Without the lock first, B reads before A commits; without READ
    COMMITTED, under a repeatable read default, B's reads after the lock keep
    the snapshot taken before it. Either way B does not see A's columns and
    ends in an error: it adds a column A added ("already exists"), or, at
    repeatable read, it sees A's index (a catalog lookup, which reads the
    latest commit) but not A's column, and refuses the index as not the one
    420 creates."""
    path = _variant(M420, old, new)
    try:
        fails = _first_applies_failures(mcase, m420, path, dict(ISOLATIONS)[isolation])
    finally:
        os.unlink(path)
    with capsys.disabled():
        print("\nMODLOG-MUTANT %s under %s: %s" % (pin, isolation, fails))
    assert any(f.startswith("B-RC") and ("already exists" in f or "is not the GIN index" in f)
               for f in fails), fails


def _rollbacks_failures(schema, path):
    """Two rollbacks (the file at `path`) at once, from 420 applied."""
    try:
        fails = _two_run_failures(_run(_two_runs(schema, path)))
        if _fetch(schema, COLS_SQL) != 0 or _fetch(schema, OBJS_SQL) != 0:
            fails.append("LEFT-OBJECTS")
        return fails
    finally:
        _restore(schema)


def test_two_rollbacks_of_420_at_once_both_end_rc_0(mcase, m420, capsys):
    fails = _rollbacks_failures(mcase, R420)
    with capsys.disabled():
        print("\nMODLOG-TWO-ROLLBACKS: %s" % (fails or "both rc 0, B changed nothing"))
    assert not fails, fails


@pytest.mark.parametrize("old,new", [
    ("DROP INDEX IF EXISTS ix_admin_actions_affected;", "DROP INDEX ix_admin_actions_affected;"),
    ("DROP CONSTRAINT IF EXISTS ck_admin_actions_reason_len;", "DROP CONSTRAINT ck_admin_actions_reason_len;"),
    ("DROP COLUMN IF EXISTS affected_steam_ids;", "DROP COLUMN affected_steam_ids;"),
    ("DROP COLUMN IF EXISTS reason;", "DROP COLUMN reason;"),
], ids=["index", "constraint", "affected_steam_ids", "reason"])
def test_mutant_the_rollback_without_an_if_exists_fails_the_second_run(mcase, m420, old, new, capsys):
    path = _variant(R420, old, new)
    try:
        fails = _rollbacks_failures(mcase, path)
    finally:
        os.unlink(path)
    with capsys.disabled():
        print("\nMODLOG-MUTANT rollback %r: %s" % (new, fails))
    assert any(f.startswith("B-RC") and "does not exist" in f for f in fails), fails


# -- the bare name, a temporary table of the name, the refusals ---------------------

_TEMP = "CREATE TEMP TABLE admin_actions (id integer);\n"
_PG_TEMP_LAST = "pg_catalog.format('pg_catalog, %I, pg_temp', nsp), true);   -- names bind as written"
_SAME_TABLE = ("  IF pg_catalog.to_regclass('admin_actions')::oid IS DISTINCT FROM tbl THEN"
               "   -- the bare name names the same table\n"
               "    RAISE EXCEPTION '420: the name admin_actions resolves to %, not %; nothing changed',\n"
               "      coalesce(pg_catalog.to_regclass('admin_actions')::text, 'nothing'), tbl::regclass;\n"
               "  END IF;\n")


def _temp_failures(schema, s0, path):
    """A first apply and an apply again in sessions that hold a temporary
    table named admin_actions (which a path without pg_temp searches first)."""
    rc, err = _psql_apply(schema, R420)
    assert rc == 0, err
    fails = []
    try:
        before = _snap(schema)
        rc, err = _psql_apply(schema, path, prefix=_TEMP)
        if rc != 0:
            fails.append("FIRST-APPLY-RC rc=%s %s" % (rc, _tail(err)))
            if _snap(schema) != before:
                fails.append("REFUSAL-CHANGED")
            return fails
        if _fetch(schema, FILL_SQL) != s0:
            fails.append("FILL-DIFFERS")
        before = _snap(schema)
        rc, err = _psql_apply(schema, path, prefix=_TEMP)
        if rc != 0:
            fails.append("RERUN-RC rc=%s %s" % (rc, _tail(err)))
        elif _snap(schema) != before:
            fails.append("RERUN-CHANGED")
        return fails
    finally:
        _restore(schema)


def test_420_applies_to_its_own_table_beside_a_temporary_table_of_the_name(mcase, m420, capsys):
    """Class 3: pg_temp searched last, and the bare name checked to be the
    table resolved first."""
    fails = _temp_failures(mcase, m420, M420)
    with capsys.disabled():
        print("\nMODLOG-TEMP-TABLE: %s" % (fails or "rc 0 twice, the fills as the defaults'"))
    assert not fails, fails


def test_mutant_the_path_without_pg_temp_is_refused_by_the_same_table_check(mcase, m420, capsys):
    path = _variant(M420, _PG_TEMP_LAST, _PG_TEMP_LAST.replace(", pg_temp'", "'"))
    try:
        fails = _temp_failures(mcase, m420, path)
    finally:
        os.unlink(path)
    with capsys.disabled():
        print("\nMODLOG-MUTANT path without pg_temp: %s" % fails)
    assert any(f.startswith("FIRST-APPLY-RC") and "the name admin_actions resolves to" in f
               for f in fails), fails
    assert "REFUSAL-CHANGED" not in fails


def test_mutant_without_the_same_table_check_the_cause_goes_unnamed(mcase, m420, capsys):
    """The same-table line removed as well: the run still fails, but later
    (the post-check, after a lock of the temporary table and writes to it),
    and no line names the cause."""
    p1 = _variant(M420, _PG_TEMP_LAST, _PG_TEMP_LAST.replace(", pg_temp'", "'"))
    try:
        p2 = _variant(p1, _SAME_TABLE, "")
    finally:
        os.unlink(p1)
    try:
        fails = _temp_failures(mcase, m420, p2)
    finally:
        os.unlink(p2)
    with capsys.disabled():
        print("\nMODLOG-MUTANT without the same-table check: %s" % fails)
    assert any(f.startswith("FIRST-APPLY-RC") for f in fails), fails
    assert not any("the name admin_actions resolves to" in f for f in fails), fails


_COL_AFF = "ALTER TABLE admin_actions ADD COLUMN affected_steam_ids text[] NOT NULL DEFAULT '{}'; "
WRONG_SHAPES = [
    ("btree_index", _COL_AFF + "CREATE INDEX ix_admin_actions_affected ON admin_actions"
     " USING btree (affected_steam_ids)", "is not the GIN index 420 creates"),
    ("gin_with_predicate", _COL_AFF + "CREATE INDEX ix_admin_actions_affected ON admin_actions"
     " USING gin (affected_steam_ids) WHERE cardinality(affected_steam_ids) > 0",
     "is not the GIN index 420 creates"),
    ("gin_on_expression", _COL_AFF + "CREATE INDEX ix_admin_actions_affected ON admin_actions"
     " USING gin ((affected_steam_ids || ARRAY['x']::text[]))", "is not the GIN index 420 creates"),
    ("affected_varchar_array", "ALTER TABLE admin_actions ADD COLUMN affected_steam_ids varchar(17)[]",
     "affected_steam_ids is character varying"),
    ("reason_varchar", "ALTER TABLE admin_actions ADD COLUMN reason varchar(256)",
     "admin_actions.reason is character varying"),
    ("another_check", "ALTER TABLE admin_actions ADD COLUMN reason text; ALTER TABLE admin_actions"
     " ADD CONSTRAINT ck_admin_actions_reason_len CHECK (reason IS NULL OR char_length(reason) <= 300)",
     "ck_admin_actions_reason_len is"),
    ("check_not_validated", "ALTER TABLE admin_actions ADD COLUMN reason text; ALTER TABLE admin_actions"
     " ADD CONSTRAINT ck_admin_actions_reason_len CHECK (reason IS NULL OR char_length(reason) <= 256)"
     " NOT VALID", "ck_admin_actions_reason_len is"),
]


@pytest.mark.parametrize("label,ddl,message", WRONG_SHAPES, ids=[w[0] for w in WRONG_SHAPES])
def test_420_refuses_a_name_that_exists_with_another_shape(mcase, m420, label, ddl, message):
    """Class 2: types by oid, the index by catalog identity, the CHECK
    validated and as 420 writes it; a refusal changes nothing."""
    rc, err = _psql_apply(mcase, R420)
    assert rc == 0, err
    try:
        _exec(mcase, ddl)
        before = _snap(mcase)
        rc, err = _psql_apply(mcase, M420)
        assert rc != 0 and message in err and "nothing changed" in err, (rc, err)
        assert _snap(mcase) == before
    finally:
        _restore(mcase)


def _refusal_beside_format_type_plant(schema, path):
    """The refusal of a varchar[] affected_steam_ids with a format_type(oid,
    text) in the table's schema: (rc, stderr). The refusal's message passes
    an untyped NULL, so a bare format_type takes the plant."""
    rc, err = _psql_apply(schema, R420)
    assert rc == 0, err
    try:
        _exec(schema, "ALTER TABLE admin_actions ADD COLUMN affected_steam_ids varchar(17)[]")
        _plant(schema, "format_type(oid,text)", True)
        return _psql_apply(schema, path)
    finally:
        _plant(schema, "format_type(oid,text)", False)
        _restore(schema)


def test_420_refusal_names_the_type_beside_a_format_type_plant(mcase, m420, capsys):
    rc, err = _refusal_beside_format_type_plant(mcase, M420)
    with capsys.disabled():
        print("\nMODLOG-FORMAT-TYPE-PLANT rc=%s %s" % (rc, _tail(err)))
    assert rc != 0 and "affected_steam_ids is character varying" in err, (rc, _tail(err))


