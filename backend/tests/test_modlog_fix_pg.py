"""MODLOG-1, the fix sitting after review round modlog-r1 (Part A): each fix
read back against a real PostgreSQL, with its mutants.

    A1  the 2v2 rebuild records a START, committed before the first player's
        write; the read says when no finish followed it
    A2  a message stored with only a Discord author names the live account
        linked to that author, on every chat-moderation route
    A3  a set of players longer than one record holds is recorded whole, as
        parts of one action
    A4  an account deletion rewrites the id in the records' texts, by whole
        token
    A5  a supplied reason or note reaches the record
    A7  the read pages by key, and its total agrees with its rows
    A8  a mute's length is stored; a ban says permanent only when it is
    A6  the no-change branches that commit before any record change nothing

Same harness as test_modlog_pg.py (its case schema, built by the ladder
harness, sealed, dropped at the end):

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>

Every player is a synthetic id below the first individual-account SteamID64
and every name is invented.
"""
import asyncio
import hashlib
import hmac
import json
import os
import re
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

import main  # noqa: E402
import modlog  # noqa: E402
import test_modlog_pg as base  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402
from test_modlog_pg import case, admin_open  # noqa: E402,F401  (fixtures)

_sid, _player, _admin, _records, _with_sm, _commit, _qp = (
    base._sid, base._player, base._admin, base._records, base._with_sm, base._commit, base._qp)
INTERNAL_KEY = base.INTERNAL_KEY
_DIDS = iter(range(10**17 + 4200000, 10**17 + 4300000))


def _did():
    return str(next(_DIDS))


async def _all_records(db, action, **where):
    sql = ("SELECT id, action, admin_steam_id, affected_steam_ids, reason, details, target_steam_id,"
           "       created_at FROM admin_actions WHERE action = :a")
    params = {"a": action}
    for k, v in where.items():
        sql += f" AND details->>'{k}' = :{k}"
        params[k] = str(v)
    return (await db.execute(text(sql + " ORDER BY created_at, id"), params)).mappings().all()


async def _read(sm, **kw):
    f = main._modlog_parse(_qp(**kw))
    async with sm() as db:
        return await main._modlog_answer(db, f)


async def _chat_row(db, *, source="ingame", steam_id=None, discord_id=None, channel="global",
                    mirror=None):
    mid = (await db.execute(text(
        "INSERT INTO chat_messages (channel, steam_id, discord_id, display_name, message, source,"
        " author_verified) VALUES (:c, :s, :d, 'Author Example', 'a line', :src, true) RETURNING id"),
        {"c": channel, "s": steam_id, "d": discord_id, "src": source})).scalar()
    if mirror:
        platform, mirror_id = mirror
        await db.execute(text(
            "INSERT INTO chat_mirrors (chat_id, platform, mirror_id, channel_ref)"
            " VALUES (:i, :p, :m, '1')"), {"i": mid, "p": platform, "m": mirror_id})
    return int(mid)


# -- A1 --------------------------------------------------------------------------

async def _seed_team_series(db, n_players=4):
    p = [await _player(db) for _ in range(n_players)]
    await lh._insert(db, "team_series", {"id": uuid.uuid4(), "status": "completed", "winner_team": 1,
                                         "t1a_id": p[0][1], "t1b_id": p[1][1],
                                         "t2a_id": p[2][1], "t2b_id": p[3][1],
                                         "completed_at": main.datetime.now(main.timezone.utc)})
    return p


def _rebuild_fails_at_the_second_player(case, monkeypatch):
    real = main._assert_no_service_subject
    calls = []

    async def flaky(db, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("injected: the second player's write fails")
        return await real(db, **kw)
    monkeypatch.setattr(main, "_assert_no_service_subject", flaky)

    async def body(sm):
        async def seed(db):
            return [x[1] for x in await _seed_team_series(db)]
        pids = await _commit(sm, seed)
        async with sm() as db:
            before = len(await _all_records(db, "team_glicko_rebuild"))
        async with sm() as db:
            with pytest.raises(RuntimeError):
                await main.admin_rebuild_team_glicko(x_internal_key=INTERNAL_KEY, db=db)
        async with sm() as db:
            written = (await db.execute(text(
                "SELECT count(*) FROM glicko_ratings_2v2 WHERE player_id = ANY(CAST(:p AS uuid[]))"),
                {"p": [str(x) for x in pids]})).scalar()
            recs = (await _all_records(db, "team_glicko_rebuild"))[before:]
        return written, recs
    return _with_sm(case, body)


def test_a1_a_failure_after_the_first_players_commit_leaves_the_start_record(case, admin_open, monkeypatch):
    written, recs = _rebuild_fails_at_the_second_player(case, monkeypatch)
    assert written >= 1, "the injection must fall after a player's commit"
    assert [r["details"].get("stage") for r in recs] == ["started"], recs
    start = recs[0]["details"]
    assert start["players_planned"] >= 4 and len(start["run_id"]) == 32
    assert recs[0]["affected_steam_ids"] == []

    async def body(sm):
        ans = await _read(sm, action="team_glicko_rebuild", limit=100)
        return [r for r in ans["rows"] if r["details"].get("run_id") == start["run_id"]]
    rows = _with_sm(case, body)
    assert len(rows) == 1 and rows[0]["sentence"].endswith("no finish was recorded."), rows


def test_a1_a_whole_run_records_a_start_and_an_end_with_one_run_id(case, admin_open):
    async def body(sm):
        await _commit(sm, _seed_team_series)
        async with sm() as db:
            before = len(await _all_records(db, "team_glicko_rebuild"))
        async with sm() as db:
            out = await main.admin_rebuild_team_glicko(x_internal_key=INTERNAL_KEY, db=db)
        async with sm() as db:
            recs = (await _all_records(db, "team_glicko_rebuild"))[before:]
        ans = await _read(sm, action="team_glicko_rebuild", limit=100)
        return out, recs, ans
    out, recs, ans = _with_sm(case, body)
    assert [r["details"]["stage"] for r in recs] == ["started", "finished"]
    assert recs[0]["details"]["run_id"] == recs[1]["details"]["run_id"]
    assert recs[1]["details"]["players_written"] == out["players_written"]
    start = [r for r in ans["rows"] if r["details"].get("run_id") == recs[0]["details"]["run_id"]
             and r["details"].get("stage") == "started"]
    assert start and start[0]["sentence"].endswith("its finish is recorded."), start


def test_a1_mutant_without_the_start_record_is_red(case, admin_open, monkeypatch):
    async def none(db, **kw):
        return "0" * 32
    monkeypatch.setattr(main, "_modlog_rebuild_start", none)
    with pytest.raises(AssertionError) as e:
        test_a1_a_failure_after_the_first_players_commit_leaves_the_start_record(case, None, monkeypatch)
    print("\nMUTANT-RED A1 start record removed: %s" % str(e.value).splitlines()[0][:160])


# -- A2 --------------------------------------------------------------------------

async def _record_of_message(db, mid):
    return (await db.execute(text(
        "SELECT action, affected_steam_ids, details FROM admin_actions"
        " WHERE action IN ('chat_delete', 'chat_mute_msg')"
        "   AND (details->>'message_id' = :m OR details->'message_ids' @> CAST(:arr AS jsonb))"),
        {"m": str(mid), "arr": "[%d]" % mid})).mappings().all()


async def _a2_delete(sm, a, did):
    async with sm() as db:
        mid = await _chat_row(db, source="discord", discord_id=did)
        await db.commit()
    async with sm() as db:
        await main.chat_moderate_delete(main._ChatModDeleteReq(steam_id=a, message_id=mid), None, db=db)
    return mid


async def _a2_bridge(sm, a, did):
    nid = "tw-%s" % uuid.uuid4().hex[:12]
    async with sm() as db:
        mid = await _chat_row(db, source="discord", discord_id=did, mirror=("twitch", nid))
        await db.commit()
    async with sm() as db:
        await main.internal_chat_bridge_moderation(
            {"source": "twitch", "kind": "delete_message", "native_id": nid},
            x_internal_key=INTERNAL_KEY, db=db)
    return mid


async def _a2_discord_deleted(sm, a, did):
    dm = "dc-%s" % uuid.uuid4().hex[:12]
    async with sm() as db:
        mid = await _chat_row(db, source="discord", discord_id=did, mirror=("discord", dm))
        await db.commit()
    async with sm() as db:
        await main.internal_chat_discord_deleted({"message_ids": [dm]}, x_internal_key=INTERNAL_KEY, db=db)
    return mid


async def _a2_mute_by_message(sm, a, did):
    async with sm() as db:
        mid = await _chat_row(db, source="discord", discord_id=did)
        await db.commit()
    async with sm() as db:
        await main.chat_moderate_mute_by_message(main._ChatModMuteMsgReq(
            steam_id=a, message_id=mid, duration_minutes=30, reason="spam lines"), None, db=db)
    return mid


async def _a2_discord_mute(sm, a, did):
    dm = "dc-%s" % uuid.uuid4().hex[:12]
    async with sm() as db:
        mid = await _chat_row(db, source="discord", discord_id=did, mirror=("discord", dm))
        await db.commit()
    async with sm() as db:
        await main.internal_chat_discord_mute(
            {"message_id": dm, "actor_discord_id": "420000000000000077", "actor_name": "Mod Example",
             "actor_channel_lang": "global", "duration_minutes": 60},
            x_internal_key=INTERNAL_KEY, db=db)
    return mid


A2_ROUTES = {"delete": _a2_delete, "bridge": _a2_bridge, "discord_deleted": _a2_discord_deleted,
             "mute_by_message": _a2_mute_by_message, "discord_mute": _a2_discord_mute}


def _a2_check(case, route):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            linked_did, unlinked_did, gone_did = _did(), _did(), _did()
            linked, _ = await _player(db, discord_id=linked_did)
            await _player(db, discord_id=gone_did, deleted_at=main.datetime.now(main.timezone.utc))
            return a, linked, linked_did, unlinked_did, gone_did
        a, linked, linked_did, unlinked_did, gone_did = await _commit(sm, seed)
        out = {}
        for who, did in (("linked", linked_did), ("unlinked", unlinked_did), ("gone", gone_did)):
            mid = await A2_ROUTES[route](sm, a, did)
            async with sm() as db:
                out[who] = await _record_of_message(db, mid)
        found = (await _read(sm, player=linked))["rows"]
        return linked, out, found
    linked, out, found = _with_sm(case, body)
    for who in out:
        assert len(out[who]) == 1, (route, who, out[who])
    assert out["linked"][0]["affected_steam_ids"] == [linked], (route, out["linked"][0])
    assert "unlinked_discord_authors" not in out["linked"][0]["details"]
    for who in ("unlinked", "gone"):
        rec = out[who][0]
        assert rec["affected_steam_ids"] == [], (route, who, rec)
        assert rec["details"].get("unlinked_discord_authors") == 1, (route, who, rec["details"])
    assert any(r["action"] == out["linked"][0]["action"] for r in found), (route, found)


@pytest.mark.parametrize("route", sorted(A2_ROUTES))
def test_a2_a_discord_author_is_named_through_the_live_linked_account(case, admin_open, route):
    _a2_check(case, route)


@pytest.mark.parametrize("route", sorted(A2_ROUTES))
def test_a2_mutant_without_the_resolution_is_red(case, admin_open, monkeypatch, route):
    async def nobody(db, discord_ids):
        return {}
    monkeypatch.setattr(main, "_modlog_linked_steam", nobody)
    with pytest.raises(AssertionError) as e:
        _a2_check(case, route)
    print("\nMUTANT-RED A2 %s resolution removed: %s" % (route, str(e.value).splitlines()[0][:160]))


# -- A3 --------------------------------------------------------------------------

def _a3_bulk_delete(case):
    async def body(sm):
        async def seed(db):
            sids, mirrors = [], []
            for _ in range(17):
                s, _ = await _player(db)
                dm = "dc-%s" % uuid.uuid4().hex[:12]
                await _chat_row(db, source="ingame", steam_id=s, mirror=("discord", dm))
                sids.append(s)
                mirrors.append(dm)
            return sids, mirrors
        sids, mirrors = await _commit(sm, seed)
        async with sm() as db:
            await main.internal_chat_discord_deleted({"message_ids": mirrors},
                                                     x_internal_key=INTERNAL_KEY, db=db)
        async with sm() as db:
            recs = (await db.execute(text(
                "SELECT affected_steam_ids, details FROM admin_actions WHERE action = 'chat_delete'"
                "   AND details->'discord_message_ids' @> CAST(:m AS jsonb)"
                " ORDER BY details->>'batch_part'"),
                {"m": '["%s"]' % mirrors[0]})).mappings().all()
        per_player = []
        for s in sids:
            per_player.append([r["sentence"] for r in
                               (await _read(sm, player=s, action="chat_delete"))["rows"]])
        return sids, recs, per_player
    return _with_sm(case, body)


def test_a3_seventeen_authors_are_recorded_whole_in_two_parts(case, admin_open):
    sids, recs, per_player = _a3_bulk_delete(case)
    assert [len(r["affected_steam_ids"]) for r in recs] == [16, 1], recs
    assert sorted(s for r in recs for s in r["affected_steam_ids"]) == sorted(sids)
    assert len({r["details"]["batch"] for r in recs}) == 1
    assert [r["details"]["batch_part"] for r in recs] == [1, 2]
    assert all(r["details"]["batch_parts"] == 2 and r["details"]["affected_total"] == 17 for r in recs)
    assert all(len(x) == 1 and "of 2 of one action on 17 players." in x[0] for x in per_player), per_player


def test_a3_mutant_without_the_split_is_red(case, admin_open, monkeypatch):
    monkeypatch.setattr(main, "_modlog_parts", lambda named: [named])
    with pytest.raises((AssertionError, ValueError)) as e:
        test_a3_seventeen_authors_are_recorded_whole_in_two_parts(case, None)
    print("\nMUTANT-RED A3 split removed: %s" % str(e.value).splitlines()[0][:160])


def test_a3_mutant_without_the_batch_value_is_red(case, admin_open, monkeypatch):
    monkeypatch.setattr(main, "_modlog_batch", lambda details, batch, part, parts, total: dict(details))
    with pytest.raises((AssertionError, KeyError)) as e:
        test_a3_seventeen_authors_are_recorded_whole_in_two_parts(case, None)
    print("\nMUTANT-RED A3 batch value dropped: %r" % (str(e.value).splitlines() or [""])[0][:160])


# -- A4 --------------------------------------------------------------------------

def _a4_delete(case, monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", base.DELETE_SECRET)
    import cf_asm

    async def body(sm):
        async with sm() as db:
            a, _ = await _admin(db)
            gone, gpid = await _player(db, name="Leaving Player")
            other, _ = await _player(db, name="Staying Player")
            long_run = "12" + gone            # 19 digits holding the id
            await main._modlog_write(
                db, actor=a, action="chat_mute", affected=[gone], target_steam_id=gone,
                reason="said %s things; see %s and %s" % (gone, other, long_run),
                details={"note": {"deep": ["x", "from %s." % gone]}, "other": other,
                         "run": long_run, "num": int(gone), gone: "keyed"})
            await db.commit()
        sig = hmac.new(base.DELETE_SECRET.encode(), ("delete:%s" % gone).encode(),
                       hashlib.sha256).hexdigest()
        async with sm() as db:
            await main.delete_player_data(gone, cf_asm.FakeRequest(), sig=sig, _slot=None, db=db)
        async with sm() as db:
            rec = (await _records(db, a))[0]
            tomb = (await db.execute(text("SELECT steam_id FROM players WHERE id = :i"),
                                     {"i": gpid})).scalar()
        found = await _read(sm, q=gone, include_reads=1, limit=100)
        return gone, other, long_run, tomb, rec, found
    return _with_sm(case, body)


def test_a4_the_deleted_id_leaves_the_reason_and_the_details(case, admin_open, monkeypatch):
    gone, other, long_run, tomb, rec, found = _a4_delete(case, monkeypatch)
    assert tomb.startswith("deleted_")
    assert rec["reason"] == "said %s things; see %s and %s" % (tomb, other, long_run), rec["reason"]
    d = rec["details"]
    assert d["note"]["deep"] == ["x", "from %s." % tomb], d
    assert d["other"] == other and d["run"] == long_run       # another id, a longer run: untouched
    assert d["num"] == tomb and d.get(tomb) == "keyed" and gone not in d, d
    # The read's search is by substring, so it still finds the record that
    # holds the longer run; no record found holds the id as a whole token.
    token = re.compile(r"(?<![0-9])%s(?![0-9])" % gone)
    assert found["total"] == len(found["rows"]) == 1, found
    for r in found["rows"]:
        assert not token.search(json.dumps([r["reason"], r["details"]])), r


@pytest.mark.parametrize("kind", ["reason", "details"])
def test_a4_mutant_per_kind_of_text_is_red(case, admin_open, monkeypatch, kind):
    monkeypatch.setattr(main, "_MODLOG_SCRUB_FIELDS",
                        tuple(f for f in main._MODLOG_SCRUB_FIELDS if f != kind))
    with pytest.raises(AssertionError) as e:
        test_a4_the_deleted_id_leaves_the_reason_and_the_details(case, None, monkeypatch)
    print("\nMUTANT-RED A4 %s not rewritten: %s" % (kind, str(e.value).splitlines()[0][:160]))


def test_a4_the_token_rule_on_its_own():
    rx = main._modlog_token_re(["76561190420999999"])
    assert rx.sub("T", "a 76561190420999999, b") == "a T, b"
    assert rx.sub("T", "x1276561190420999999y") == "x1276561190420999999y"
    assert rx.sub("T", "765611904209999990") == "765611904209999990"
    assert main._modlog_token_re([None, "", "deleted_x"]) is None


def test_a4_cost_of_the_statement_at_127_and_12700_rows(case, capsys):
    """The deletion's text statement over the whole table: its plan and time
    at 127 records and at a hundred times that (the pre-filter reads every
    row; the rewrite touches only rows holding the id)."""
    async def body(sm):
        out = []
        for n in (127, 12700):
            async with sm() as db:
                await db.execute(text("DELETE FROM admin_actions WHERE admin_steam_id = 'cost-probe'"))
                await db.execute(text(
                    "INSERT INTO admin_actions (admin_steam_id, action, details, affected_steam_ids, reason)"
                    " SELECT 'cost-probe', 'chat_mute',"
                    "        jsonb_build_object('channel', 'global', 'note', 'n' || g),"
                    "        ARRAY['7656119043' || lpad(CAST(g AS text), 7, '0')], 'reason ' || g"
                    "   FROM generate_series(1, :n) g"), {"n": n})
                await db.commit()
            async with sm() as db:
                await db.execute(text("ANALYZE admin_actions"))
                total = (await db.execute(text("SELECT count(*) FROM admin_actions"))).scalar()
                t0 = asyncio.get_event_loop().time()
                await main._modlog_scrub_records(db, ["76561190439999999"], "deleted_probe0")
                ms = (asyncio.get_event_loop().time() - t0) * 1000
                await db.rollback()
            out.append((n, total, ms))
        async with sm() as db:
            await db.execute(text("DELETE FROM admin_actions WHERE admin_steam_id = 'cost-probe'"))
            await db.commit()
        return out
    out = _with_sm(case, body)
    with capsys.disabled():
        for n, total, ms in out:
            print("\nMODLOG-A4-COST probe rows=%d table rows=%d statement ms=%.1f" % (n, total, ms))
    assert len(out) == 2


# -- A5 --------------------------------------------------------------------------

def test_a5_a_supplied_reason_or_note_reaches_the_record(case, admin_open):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            t, _ = await _player(db)
            ts = [(await _player(db))[0] for _ in range(6)]
            return a, t, ts
        a, t, ts = await _commit(sm, seed)
        async with sm() as db:
            await main.chat_moderate_mute(main._ChatModMuteReq(
                steam_id=a, target_steam_id=t, duration_minutes=60, reason="insults"), None, db=db)
        async with sm() as db:
            await main.chat_moderate_unmute(main._ChatModMuteReq(
                steam_id=a, target_steam_id=t, reason="appeal accepted"), None, db=db)
        # The add route's own statement fails on PostgreSQL at the lane's base
        # (reported, not fixed in this sitting): the pattern is seeded, and
        # the add route's reason is proved by the census check alone.
        async with sm() as db:
            pid = (await db.execute(text(
                "INSERT INTO bridge_spam_patterns (pattern, note, added_by)"
                " VALUES (:p, 'seeded', :a) RETURNING id"),
                {"p": "buycheap%s" % uuid.uuid4().hex[:8], "a": a})).scalar()
            await db.commit()
        async with sm() as db:
            await main.chat_moderate_spam_pattern_revoke(main._ChatSpamPatternReq(
                steam_id=a, pattern_id=pid, note="too broad"), db=db)
        for x in ts[:5]:
            async with sm() as db:
                await main.admin_ban(main._AdminBanReq(admin_steam_id=a, target_steam_id=x),
                                     _slot=None, db=db)
        async with sm() as db:
            with pytest.raises(HTTPException):
                await main.admin_ban(main._AdminBanReq(admin_steam_id=a, target_steam_id=ts[5],
                                                       reason="repeat cheating"), _slot=None, db=db)
        async with sm() as db:
            return await _records(db, a)
    rows = _with_sm(case, body)
    by = {}
    for r in rows:
        by.setdefault(r["action"], []).append(r)
    assert by["chat_unmute"][0]["reason"] == "appeal accepted", by["chat_unmute"]
    assert [r["reason"] for r in by["chat_spam_pattern"]] == ["too broad"]
    assert by["ban_rate_blocked"][0]["reason"] == "repeat cheating", by["ban_rate_blocked"]


# -- A6: the branches that commit before any record change nothing ---------------

def test_a6_a_repeated_deletion_changes_nothing_and_records_nothing(case, admin_open):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            s, _ = await _player(db)
            nid, dm = "tw-%s" % uuid.uuid4().hex[:12], "dc-%s" % uuid.uuid4().hex[:12]
            m1 = await _chat_row(db, steam_id=s)
            m2 = await _chat_row(db, steam_id=s, mirror=("twitch", nid))
            m3 = await _chat_row(db, steam_id=s, mirror=("discord", dm))
            return a, (m1, m2, m3), nid, dm

        a, mids, nid, dm = await _commit(sm, seed)

        async def calls():
            async with sm() as db:
                await main.chat_moderate_delete(main._ChatModDeleteReq(steam_id=a, message_id=mids[0]),
                                                None, db=db)
            async with sm() as db:
                await main.internal_chat_bridge_moderation(
                    {"source": "twitch", "kind": "delete_message", "native_id": nid},
                    x_internal_key=INTERNAL_KEY, db=db)
            async with sm() as db:
                await main.internal_chat_discord_deleted({"message_ids": [dm]},
                                                         x_internal_key=INTERNAL_KEY, db=db)

        async def state():
            async with sm() as db:
                rows = (await db.execute(text(
                    "SELECT id, deleted_at, deleted_by_steam_id FROM chat_messages"
                    " WHERE id = ANY(:i) ORDER BY id"), {"i": list(mids)})).all()
                recs = [len(await _record_of_message(db, m)) for m in mids]
                outbox = (await db.execute(text("SELECT count(*) FROM chat_mod_actions"))).scalar()
            return [tuple(r) for r in rows], recs, outbox
        await calls()
        first = await state()
        await calls()
        second = await state()
        return first, second
    first, second = _with_sm(case, body)
    assert first[1] == [1, 1, 1] and all(r[1] is not None for r in first[0]), first
    assert second == first, (first, second)


# -- A7 --------------------------------------------------------------------------

# For each order the read offers: the values of a record inserted between two
# page reads that sorts BEFORE every seeded record, so that position paging
# shows one record twice.
A7_FIRST = {
    ("time", "desc"): {"created_at": main.datetime(2030, 1, 1, tzinfo=main.timezone.utc)},
    ("time", "asc"): {"created_at": main.datetime(2000, 1, 1, tzinfo=main.timezone.utc)},
    ("action", "asc"): {"action": "alert_create"},
    ("action", "desc"): {"action": "unban"},
    ("actor", "asc"): {"admin_steam_id": "00000000000000001"},
    ("actor", "desc"): {"admin_steam_id": "zzzz-actor"},
}
A7_WORDS = ["ban", "chat_mute", "flag_review", "record_exclude", "chat_automute", "pc_portrait_clear",
            "grant_achievement"]


async def _a7_seed(sm):
    async with sm() as db:
        p, _ = await _player(db)
        ids = []
        for i, word in enumerate(A7_WORDS):
            ids.append(str((await db.execute(text(
                "INSERT INTO admin_actions (admin_steam_id, action, details, affected_steam_ids, created_at)"
                " VALUES (:a, :w, '{}'::jsonb, ARRAY[CAST(:p AS text)],"
                "         TIMESTAMPTZ '2026-11-02 00:00:00+00' + make_interval(hours => :h))"
                " RETURNING id"), {"a": "7656119042%07d" % (9000000 + i % 3), "w": word, "p": p,
                                   "h": i})).scalar()))
        await db.commit()
    return p, ids


async def _a7_insert(sm, p, values):
    v = {"admin_steam_id": "76561190429000001", "action": "ban", "created_at": None}
    v.update(values)
    async with sm() as db:
        await db.execute(text(
            "INSERT INTO admin_actions (admin_steam_id, action, details, affected_steam_ids, created_at)"
            " VALUES (:a, :w, '{}'::jsonb, ARRAY[CAST(:p AS text)],"
            "         COALESCE(CAST(:t AS timestamptz), NOW()))"),
            {"a": v["admin_steam_id"], "w": v["action"], "p": p, "t": v["created_at"]})
        await db.commit()


async def _a7_walk(sm, sort, direction, insert=None):
    """Every page of the per-player read, 3 rows a page, with `insert` run
    once between the first and the second page read: the ids in page order.
    Pages by the answer's key when it has one, else by position."""
    p, seeded = await _a7_seed(sm)
    out, after, offset = [], None, 0
    for _ in range(20):
        kw = dict(player=p, sort=sort, dir=direction, limit=3)
        if after:
            kw["after"] = after
        elif offset:
            kw["offset"] = offset
        ans = await _read(sm, **kw)
        out.extend(r["id"] for r in ans["rows"])
        if insert and len(out) == len(ans["rows"]):
            await _a7_insert(sm, p, insert)
        if "next" in ans:
            after = ans["next"]
            if not after:
                break
        else:
            offset += 3
            if not ans["rows"]:
                break
    return seeded, out


@pytest.mark.parametrize("order", sorted(A7_FIRST), ids=lambda o: "%s-%s" % o)
def test_a7_a_record_inserted_between_pages_neither_repeats_nor_hides_one(case, order):
    seeded, seen = _with_sm(case, lambda sm: _a7_walk(sm, order[0], order[1], A7_FIRST[order]))
    assert len(seen) == len(set(seen)), ("a row repeats", order, seen)
    assert set(seeded) <= set(seen), ("a row is missing", order)


def test_a7_mutant_with_the_key_ignored_is_red(case, monkeypatch):
    monkeypatch.setattr(main, "_modlog_after_sql", lambda f: ("TRUE", {}))
    with pytest.raises(AssertionError) as e:
        test_a7_a_record_inserted_between_pages_neither_repeats_nor_hides_one(case, ("time", "desc"))
    print("\nMUTANT-RED A7 key ignored: %s" % str(e.value).splitlines()[0][:160])


def test_a7_total_and_rows_come_from_one_statement(case):
    """A second session inserts a matching record right after the read's
    first statement on admin_actions: the total still counts exactly the
    rows the answer holds."""
    async def body(sm):
        async with sm() as db:
            q, _ = await _player(db)
            for word in ("ban", "chat_mute"):
                await main._modlog_write(db, actor="76561190429000002", action=word, affected=[q])
            await db.commit()
        fired = []
        async with sm() as db:
            real = db.execute

            async def execute(stmt, *a, **k):
                res = await real(stmt, *a, **k)
                if not fired and "admin_actions" in str(stmt):
                    fired.append(str(stmt)[:60])
                    async with sm() as other:
                        await main._modlog_write(other, actor="76561190429000003", action="unban",
                                                 affected=[q])
                        await other.commit()
                return res
            db.execute = execute
            ans = await main._modlog_answer(db, main._modlog_parse(_qp(player=q, limit=100)))
        return fired, ans
    fired, ans = _with_sm(case, body)
    assert fired, "the second session never ran"
    assert ans["total"] == len(ans["rows"]), (ans["total"], [r["action"] for r in ans["rows"]])
    assert sum(c["count"] for c in ans["counts_by_action"]) == len(ans["rows"])


def test_a7_a_malformed_or_foreign_key_is_422():
    for bad in ("", "!!!", "e30", "a" * 600):
        if not bad:
            continue
        with pytest.raises(HTTPException) as e:
            main._modlog_parse(_qp(after=bad))
        assert e.value.status_code == 422, bad
    key = main._modlog_key({"sort": "time", "dir": "desc"},
                           {"action": "ban", "admin_steam_id": "x", "id": uuid.uuid4(),
                            "created_at": main.datetime.now(main.timezone.utc)})
    assert main._modlog_parse(_qp(after=key))["after"]
    with pytest.raises(HTTPException) as e:
        main._modlog_parse(_qp(after=key, sort="action", dir="asc"))
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        main._modlog_parse(_qp(offset=10))
    assert e.value.status_code == 400


# -- A8 --------------------------------------------------------------------------

def test_a8_every_mute_stores_its_length_and_a_ban_says_permanent_only_when_it_is(case, admin_open):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            t, _ = await _player(db)
            linked_did = _did()
            linked, _ = await _player(db, discord_id=linked_did)
            return a, t, linked, linked_did
        a, t, linked, linked_did = await _commit(sm, seed)
        mid_timed = await _a2_discord_mute(sm, a, linked_did)
        async with sm() as db:
            mid_perm = await _chat_row(db, steam_id=t)
            await db.commit()
        async with sm() as db:
            await main.chat_moderate_mute_by_message(main._ChatModMuteMsgReq(
                steam_id=a, message_id=mid_perm, duration_minutes=0, reason="slurs"), None, db=db)
        uid = "tw-user-%s" % uuid.uuid4().hex[:8]
        async with sm() as db:
            await main.internal_chat_bridge_moderation(
                {"source": "twitch", "kind": "purge_user", "platform_user_id": uid,
                 "ban_duration_s": 600}, x_internal_key=INTERNAL_KEY, db=db)
        async with sm() as db:
            await main.admin_ban(main._AdminBanReq(admin_steam_id=a, target_steam_id=t), _slot=None, db=db)
        async with sm() as db:
            timed = (await _record_of_message(db, mid_timed))[0]["details"]
            perm = (await _record_of_message(db, mid_perm))[0]["details"]
            purge = (await db.execute(text(
                "SELECT details FROM admin_actions WHERE action = 'chat_purge_user'"
                "   AND details->>'platform_user_id' = :u"), {"u": uid})).scalar()
            ban = [r for r in await _records(db, a) if r["action"] == "ban"][0]["details"]
        return timed, perm, purge, ban
    timed, perm, purge, ban = _with_sm(case, body)
    assert (timed.get("duration_minutes"), timed.get("permanent")) == (60, False), timed
    assert (perm.get("duration_minutes"), perm.get("permanent")) == (None, True), perm
    assert (purge.get("duration_minutes"), purge.get("permanent")) == (10, False), purge
    assert ban.get("permanent") is True and "duration_minutes" not in ban, ban
    assert modlog.sentence("chat_mute_msg", timed).startswith("Muted from a message for 1 hour")
    assert "permanently" in modlog.sentence("chat_mute_msg", perm)
    assert modlog.sentence("ban", ban) == "Banned permanently."


def test_a8_a_length_not_stored_is_never_read_as_permanent():
    for word in ("chat_mute", "chat_automute", "chat_mute_msg"):
        s = modlog.sentence(word, {})
        assert "length not recorded" in s and "permanent" not in s, (word, s)
        assert "permanently" in modlog.sentence(word, {"permanent": True}), word
        assert "for 2 hours" in modlog.sentence(word, {"duration_minutes": 120}), word
    assert modlog.sentence("ban", {}) == "Banned (length not recorded)."
    assert modlog.sentence("ban", {"permanent": True}) == "Banned permanently."
    assert "not recorded" in modlog.sentence("ban_length", {})
    assert modlog.sentence("ban_length", {"old_expires_at": None, "new_expires_at": None}) == \
        "Ban length changed from permanent to permanent."
    assert "length not recorded" in modlog.sentence("chat_purge_user", {"purged": 2, "platform": "twitch"})
