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
    J3  the spam pattern add route's statement runs on PostgreSQL: a new
        pattern answers ok, a second add of it answers duplicate, and the
        route records the one addition that stored a row
    J4  each unmute route: an unmute that revokes nothing commits no record
        and changes nothing; one that revokes a mute commits its record with
        the revocation
    J7  the read says that a record carried in by migration 420 was not
        written at the time of the review
    K1  a moderator route that changed nothing writes no record and does not
        commit, and answers as before
    F1  a mute-by-message record names the player the mute changed, from the
        mute's own resolution, when the Discord link moves before the record
    F2  an account deletion rewrites a record whose id stands only in a JSON
        string details, and details keeps its JSON type; the read serves a
        record whose details is no object
    F3  a page key whose sort value cannot be bound as text is refused with
        422 after_invalid on the read and on its internal twin

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
    if route in ("mute_by_message", "discord_mute"):
        # A mute record names the account the mute itself resolved (fix F1):
        # the mutant takes that resolution away inside the mute helper.
        monkeypatch.setattr(main, "_apply_mute_for_row", _mutant_of(
            "_apply_mute_for_row", ("        if linked:\n", "        linked = None\n        if linked:\n")))
    else:
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
        async with sm() as db:
            pid = (await main.chat_moderate_spam_pattern_add(main._ChatSpamPatternReq(
                steam_id=a, pattern="buycheap%s" % uuid.uuid4().hex[:8], note="new spam wave"),
                db=db))["id"]
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
    assert [(r["details"]["op"], r["reason"]) for r in by["chat_spam_pattern"]] == \
        [("add", "new spam wave"), ("revoke", "too broad")], by["chat_spam_pattern"]
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


def _mutant_of(fname, *swaps):
    """main.<fname> rebuilt from its own source with each (old, new) text swap
    applied in order (each old text must stand exactly once at that point);
    its route decorator is dropped, so the mutant registers no route."""
    import inspect
    src = inspect.getsource(getattr(main, fname))
    for old, new in swaps:
        assert src.count(old) == 1, (fname, old, src.count(old))
        src = src.replace(old, new)
    lines = src.splitlines(True)
    while lines and lines[0].lstrip().startswith("@"):
        lines.pop(0)
    ns = {}
    exec(compile("".join(lines), "<mutant of %s>" % fname, "exec"), main.__dict__, ns)
    return ns[fname]


# -- J3: the spam pattern add route on PostgreSQL --------------------------------
#
# The route's INSERT ... SELECT names its pattern bind in the select list and
# again in the NOT EXISTS predicate. Each place types it by CAST to the
# column's own type (VARCHAR(128), migration 263), so PostgreSQL deduces one
# type for the parameter. The request goes through the route itself: its
# model, its handler and its dependency, on the case schema.

J3_PATH = "/api/v1/chat/moderate/spam-patterns/add"


async def _j3_post(sm, handler, body):
    import httpx
    from fastapi import FastAPI
    app = FastAPI()
    app.add_api_route(J3_PATH, handler, methods=["POST"])

    async def _db():
        async with sm() as db:
            yield db
    app.dependency_overrides[main.get_db] = _db
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post(J3_PATH, json=body)


def _j3_check(case, handler):
    async def body(sm):
        a, _ = await _commit(sm, _admin)
        raw = "Buy Cheap Gold %s" % uuid.uuid4().hex[:8]
        norm = main._squash_for_spam(raw)[:128]
        first = await _j3_post(sm, handler, {"steam_id": a, "pattern": raw, "note": "new wave"})
        second = await _j3_post(sm, handler, {"steam_id": a, "pattern": raw, "note": "again"})
        async with sm() as db:
            rows = (await db.execute(text(
                "SELECT id FROM bridge_spam_patterns WHERE pattern = :p ORDER BY id"),
                {"p": norm})).scalars().all()
            recs = await _all_records(db, "chat_spam_pattern", normalized=norm)
        return first, second, norm, rows, recs
    first, second, norm, rows, recs = _with_sm(case, body)
    assert first.status_code == 200, (first.status_code, first.text[:200])
    assert second.status_code == 200, (second.status_code, second.text[:200])
    one, two = first.json(), second.json()
    assert (one["status"], one["pattern"]) == ("ok", norm) and one["id"] is not None, one
    assert (two["status"], two["id"]) == ("duplicate", None), two
    assert rows == [one["id"]], rows
    assert len(recs) == 1, recs
    assert recs[0]["details"]["op"] == "add" and recs[0]["details"]["id"] == one["id"], recs[0]
    assert recs[0]["reason"] == "new wave", recs[0]


def test_j3_the_add_route_stores_a_new_pattern_once_and_answers_duplicate_after(case, admin_open):
    _j3_check(case, main.chat_moderate_spam_pattern_add)


J3_SELECT_CAST = ("SELECT CAST(:p AS VARCHAR(128)), :n", "SELECT :p, :n")
J3_PREDICATE_CAST = ("WHERE pattern = CAST(:p AS VARCHAR(128))", "WHERE pattern = :p")


def test_j3_mutant_with_both_casts_removed_is_red(case, admin_open):
    handler = _mutant_of("chat_moderate_spam_pattern_add", J3_SELECT_CAST, J3_PREDICATE_CAST)
    with pytest.raises(AssertionError) as e:
        _j3_check(case, handler)
    print("\nMUTANT-RED J3 both casts removed: %s" % str(e.value).splitlines()[0][:160])


# Measured at the join: with ONE of the two CASTs removed the route still
# passes, since the typed place fixes the parameter's type and the other place
# takes it. A mutant of one CAST cannot turn the test red; the route keeps a
# CAST at each place, and these two runs show that either one alone holds.
@pytest.mark.parametrize("swap", [J3_SELECT_CAST, J3_PREDICATE_CAST], ids=["select_list", "predicate"])
def test_j3_one_cast_alone_still_types_the_parameter(case, admin_open, swap):
    _j3_check(case, _mutant_of("chat_moderate_spam_pattern_add", swap))


# -- J4: the two unmute exemptions of the census, checked by behaviour ------------
#
# test_modlog_census.NO_CHANGE_COMMITS exempts the one commit of each unmute
# route from the rule that a record precedes every commit, because the writer
# runs whenever the UPDATE revoked a row. Here each route runs twice on one
# mute: the first call revokes it and commits its record with the revocation;
# the second revokes nothing, and its commit writes no record and changes no
# row of the mute, the records or the outbox.

_J4_WRITER = "    if cleared:\n        await _modlog_write("
_J4_COMMIT = "    await db.commit()\n"
J4_MUTANTS = {
    # the guard dropped: a call that revokes nothing writes a record
    "guard_removed": ((_J4_WRITER, "    if True:\n        await _modlog_write("),),
    # the commit moved before the writer: the record is never committed
    "record_after_commit": ((_J4_COMMIT, ""), (_J4_WRITER, _J4_COMMIT + _J4_WRITER)),
}


async def _j4_chat_seed(sm):
    async def seed(db):
        a, _ = await _admin(db)
        t, _ = await _player(db)
        return a, t
    a, t = await _commit(sm, seed)
    async with sm() as db:
        await main.chat_moderate_mute(main._ChatModMuteReq(
            steam_id=a, target_steam_id=t, duration_minutes=60, reason="insults"), None, db=db)
    return a, t


async def _j4_chat_call(sm, fn, a, t):
    async with sm() as db:
        return (await fn(main._ChatModMuteReq(steam_id=a, target_steam_id=t, reason="appeal"),
                         None, db=db))["cleared"]


async def _j4_chat_state(sm, a, t):
    async with sm() as db:
        mutes = (await db.execute(text(
            "SELECT id, revoked_at FROM chat_mutes WHERE steam_id = :t ORDER BY id"), {"t": t})).all()
        recs = (await db.execute(text(
            "SELECT count(*) FROM admin_actions WHERE action = 'chat_unmute' AND target_steam_id = :t"),
            {"t": t})).scalar()
        total = (await db.execute(text("SELECT count(*) FROM admin_actions"))).scalar()
    return [tuple(m) for m in mutes], recs, total


async def _j4_bridge_seed(sm):
    async def seed(db):
        a, _ = await _admin(db)
        uid = "tw-%s" % uuid.uuid4().hex[:10]
        mid = (await db.execute(text(
            "INSERT INTO bridge_mutes (platform, platform_user_id, platform_login, channel, muted_by)"
            " VALUES ('twitch', :u, :l, NULL, 'system') RETURNING id"),
            {"u": uid, "l": "login" + uid[-6:]})).scalar()
        return a, mid
    return await _commit(sm, seed)


async def _j4_bridge_call(sm, fn, a, mid):
    async with sm() as db:
        return (await fn(main._ChatModBridgeUnmuteReq(steam_id=a, mute_id=mid), None, db=db))["cleared"]


async def _j4_bridge_state(sm, a, mid):
    async with sm() as db:
        mutes = (await db.execute(text(
            "SELECT id, revoked_at FROM bridge_mutes WHERE id = :i"), {"i": mid})).all()
        recs = (await db.execute(text(
            "SELECT count(*) FROM admin_actions WHERE action = 'chat_unmute_bridge'"
            "   AND details->>'mute_id' = :i"), {"i": str(mid)})).scalar()
        total = (await db.execute(text("SELECT count(*) FROM admin_actions"))).scalar()
        outbox = (await db.execute(text("SELECT count(*) FROM chat_mod_actions"))).scalar()
    return [tuple(m) for m in mutes], recs, (total, outbox)


J4_ROUTES = {
    "chat_moderate_unmute": (_j4_chat_seed, _j4_chat_call, _j4_chat_state),
    "chat_moderate_bridge_unmute": (_j4_bridge_seed, _j4_bridge_call, _j4_bridge_state),
}


def _j4_check(case, route, fn):
    seed, call, state = J4_ROUTES[route]

    async def body(sm):
        a, key = await seed(sm)
        before = await state(sm, a, key)
        n1 = await call(sm, fn, a, key)
        s1 = await state(sm, a, key)
        n2 = await call(sm, fn, a, key)
        s2 = await state(sm, a, key)
        return before, n1, s1, n2, s2
    before, n1, s1, n2, s2 = _with_sm(case, body)
    assert before[1] == 0 and all(m[1] is None for m in before[0]) and before[0], (route, before)
    assert n1 >= 1 and all(m[1] is not None for m in s1[0]), (route, n1, s1)
    assert s1[1] == 1, (route, "the revoking call's record", s1)
    assert n2 == 0, (route, n2)
    assert s2 == s1, (route, "the call that revoked nothing changed state", s1, s2)


@pytest.mark.parametrize("route", sorted(J4_ROUTES))
def test_j4_an_unmute_records_what_it_revokes_and_a_no_change_unmute_records_nothing(
        case, admin_open, route):
    _j4_check(case, route, getattr(main, route))


@pytest.mark.parametrize("mutant", sorted(J4_MUTANTS))
@pytest.mark.parametrize("route", sorted(J4_ROUTES))
def test_j4_mutant_is_red(case, admin_open, route, mutant):
    fn = _mutant_of(route, *J4_MUTANTS[mutant])
    with pytest.raises(AssertionError) as e:
        _j4_check(case, route, fn)
    print("\nMUTANT-RED J4 %s %s: %s" % (route, mutant, str(e.value).splitlines()[0][:160]))


# -- J7: a carried-in record says so in the read ----------------------------------
#
# Migration 420 carries in a flag_review record for each reviewed flag that no
# record named, with details carried_from = 'flagged_matches'. The read's
# sentence for such a record says in plain words that it was carried in and
# was not written at the time of the review; a record written by the review
# route says nothing of the kind.

def _j7_check(case):
    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            t, _ = await _player(db)
            ids = {}
            for carried in (False, True):
                d = {"flag_id": str(uuid.uuid4()), "review_action": "false_positive"}
                if carried:
                    d["carried_from"] = "flagged_matches"
                ids[carried] = d["flag_id"]
                await db.execute(text(
                    "INSERT INTO admin_actions (admin_steam_id, action, details, affected_steam_ids,"
                    "                           created_at)"
                    " VALUES (:a, 'flag_review', CAST(:d AS jsonb), CAST(:p AS text[]), clock_timestamp())"),
                    {"a": a, "d": json.dumps(d), "p": [t]})
            return t, ids
        t, ids = await _commit(sm, seed)
        rows = (await _read(sm, player=t))["rows"]
        return {c: [r for r in rows if r["details"].get("flag_id") == f] for c, f in ids.items()}
    by = _with_sm(case, body)
    (written,), (carried,) = by[False], by[True]
    assert written["sentence"] == "Reviewed a flagged match: false positive.", written
    assert carried["sentence"] == (
        "Reviewed a flagged match: false positive. This record was carried in from the flagged "
        "match's own review data; it was not written at the time of the review."), carried
    assert modlog.carried_text({"carried_from": "another_table"}) == modlog.CARRIED_OTHER


def test_j7_the_read_says_a_carried_in_record_was_not_written_at_the_review(case):
    _j7_check(case)


def test_j7_mutant_without_the_carried_in_words_is_red(case, monkeypatch):
    monkeypatch.setattr(modlog, "carried_text", lambda details: "")
    with pytest.raises(AssertionError) as e:
        _j7_check(case)
    print("\nMUTANT-RED J7 read without the carried-in words: %s" % str(e.value).splitlines()[0][:160])


# -- K1: a moderator route that changed nothing records nothing and commits nothing
#
# A moderator route writes its admin_actions record only on a path that changed
# state; a path that changed nothing writes no record and does not commit, and
# its answer keeps its status code and its shape. Each site below is called
# twice through the route itself (its handler on an ASGI app with the get_db
# override, as J3), with one request: the first call changes state and commits
# exactly one record; the second changes nothing, and must leave the records,
# the route's own table and the commit count as they were, answering as the
# route answered before the fix. The override counts the session's commits.

async def _k1_call(sm, method, path, handler, **req):
    import httpx
    from fastapi import FastAPI
    app = FastAPI()
    app.add_api_route(path, handler, methods=[method])
    commits = []

    async def _db():
        async with sm() as db:
            real = db.commit

            async def counted():
                commits.append(1)
                await real()
            db.commit = counted
            yield db
    app.dependency_overrides[main.get_db] = _db
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.request(method, path, **req)
    return r, len(commits)


async def _k1_rows(sm, sql, **params):
    async with sm() as db:
        return [tuple(r) for r in (await db.execute(text(sql), params)).all()]


async def _k1_records(sm):
    async with sm() as db:
        return (await db.execute(text("SELECT count(*) FROM admin_actions"))).scalar()


async def _k1_spam_seed(db):
    a, _ = await _admin(db)
    pid = (await db.execute(text(
        "INSERT INTO bridge_spam_patterns (pattern, note, added_by) VALUES (:p, NULL, 'k1 seed')"
        " RETURNING id"), {"p": "kone%s" % uuid.uuid4().hex[:10]})).scalar()
    return {"a": a, "id": int(pid)}


async def _k1_exclude_seed(db):
    a, _ = await _admin(db)
    p = [await _player(db) for _ in range(2)]
    match = uuid.uuid4()
    await lh._insert(db, "matches", {"id": match, "player1_id": p[0][1], "player2_id": p[1][1],
                                     "photon_room_id": "modlog-k1-%s" % match})
    return {"a": a, "m": str(match), "t": p[0][0]}


async def _k1_twitch_rows(db, uid, n):
    for _ in range(n):
        await lh._insert(db, "chat_messages", {"channel": "global", "display_name": "Author Example",
                                               "message": "a line", "source": "twitch",
                                               "origin_user_id": uid})


async def _k1_purge_user_seed(db):
    uid = "tw-k1-%s" % uuid.uuid4().hex[:8]
    await _k1_twitch_rows(db, uid, 2)
    return {"u": uid}


async def _k1_purge_channel_seed(db):
    await _k1_twitch_rows(db, "tw-k1-%s" % uuid.uuid4().hex[:8], 1)
    return {}


async def _k1_artist_seed(db, holds):
    a, _ = await _admin(db)
    t, _ = await _player(db)
    if holds:
        await lh._insert(db, "artist_users", {"steam_id": t, "granted_by_steam_id": a})
    return {"a": a, "t": t}


async def _k1_item_seed(db):
    a, _ = await _admin(db)
    t, _ = await _player(db)
    await lh._insert(db, "artist_users", {"steam_id": t, "granted_by_steam_id": a})
    sku = "k1_item_%s" % uuid.uuid4().hex[:10]
    await lh._insert(db, "shop_items", {"sku": sku, "kind": "face", "name": "Item Example", "price": 1})
    return {"a": a, "t": t, "sku": sku}


K1_TITLE_KEY = "rosetta"


async def _k1_repair_seed(db):
    a, _ = await _admin(db)
    t, pid = await _player(db)
    sku = main.ACHIEVEMENT_TITLE_SKUS[K1_TITLE_KEY]
    if (await db.execute(text("SELECT id FROM shop_items WHERE sku = :s"), {"s": sku})).scalar() is None:
        await lh._insert(db, "shop_items", {"sku": sku, "kind": "title", "name": "Title Example", "price": 0})
    await lh._insert(db, "player_achievements", {"player_id": pid, "achievement_key": K1_TITLE_KEY})
    return {"a": a, "t": t, "pid": pid, "sku": sku}


_K1_KEY = {"X-Internal-Key": INTERNAL_KEY}

# site: (handler name, method, path, seed, request(ctx), state(sm, ctx),
#        the changing call's answer(ctx, body) -> bool, the no-change answer(ctx))
K1_SITES = {
    "spam_pattern_revoke": (
        "chat_moderate_spam_pattern_revoke", "POST", "/api/v1/chat/moderate/spam-patterns/revoke",
        _k1_spam_seed,
        lambda c: {"json": {"steam_id": c["a"], "pattern_id": c["id"], "note": "too broad"}},
        lambda sm, c: _k1_rows(sm, "SELECT id, revoked_at FROM bridge_spam_patterns WHERE id = :i", i=c["id"]),
        lambda c, b: b == {"status": "ok", "cleared": 1},
        lambda c: {"status": "ok", "cleared": 0}),
    "record_exclude": (
        "admin_record_exclude", "POST", "/api/v1/admin/records/exclude",
        _k1_exclude_seed,
        lambda c: {"json": {"admin_steam_id": c["a"], "board": "*", "match_id": c["m"],
                            "steam_id": c["t"], "reason": "lag abuse", "signature": "x"}},
        lambda sm, c: _k1_rows(sm, "SELECT id FROM record_exclusions WHERE match_id = CAST(:m AS uuid)"
                                   " ORDER BY id", m=c["m"]),
        lambda c, b: b == {"status": "ok"},
        lambda c: {"status": "ok"}),
    "purge_user": (
        "internal_chat_bridge_moderation", "POST", "/api/v1/internal/chat/bridge-moderation",
        _k1_purge_user_seed,
        lambda c: {"json": {"source": "twitch", "kind": "purge_user", "platform_user_id": c["u"]},
                   "headers": _K1_KEY},
        lambda sm, c: _k1_rows(
            sm, "SELECT id, deleted_at IS NULL, (SELECT count(*) FROM bridge_mutes"
                "        WHERE platform_user_id = :u) FROM chat_messages WHERE origin_user_id = :u"
                " ORDER BY id", u=c["u"]),
        lambda c, b: b == {"status": "ok", "purged": 2, "truncated": False},
        lambda c: {"status": "ok", "purged": 0, "truncated": False}),
    "purge_channel": (
        "internal_chat_bridge_moderation", "POST", "/api/v1/internal/chat/bridge-moderation",
        _k1_purge_channel_seed,
        lambda c: {"json": {"source": "twitch", "kind": "purge_channel"}, "headers": _K1_KEY},
        lambda sm, c: _k1_rows(sm, "SELECT id FROM chat_messages WHERE source = 'twitch'"
                                   " AND deleted_at IS NULL ORDER BY id"),
        lambda c, b: b["status"] == "ok" and b["purged"] >= 1 and b["truncated"] is False,
        lambda c: {"status": "ok", "purged": 0, "truncated": False}),
    "artist_grant": (
        "admin_set_artist", "POST", "/api/v1/admin/artists/set",
        lambda db: _k1_artist_seed(db, False),
        lambda c: {"params": {"admin_steam_id": c["a"], "target_steam_id": c["t"], "grant": "true",
                              "sig": "x"}},
        lambda sm, c: _k1_rows(sm, "SELECT steam_id FROM artist_users WHERE steam_id = :t", t=c["t"]),
        lambda c, b: b == {"status": "ok", "target": c["t"], "artist": True},
        lambda c: {"status": "ok", "target": c["t"], "artist": True}),
    "artist_revoke": (
        "admin_set_artist", "POST", "/api/v1/admin/artists/set",
        lambda db: _k1_artist_seed(db, True),
        lambda c: {"params": {"admin_steam_id": c["a"], "target_steam_id": c["t"], "grant": "false",
                              "sig": "x"}},
        lambda sm, c: _k1_rows(sm, "SELECT steam_id FROM artist_users WHERE steam_id = :t", t=c["t"]),
        lambda c, b: b == {"status": "ok", "target": c["t"], "artist": False},
        lambda c: {"status": "ok", "target": c["t"], "artist": False}),
    "item_artist": (
        "admin_set_item_artist", "POST", "/api/v1/admin/shop/set-artist",
        _k1_item_seed,
        lambda c: {"params": {"admin_steam_id": c["a"], "sku": c["sku"], "artist_steam_id": c["t"],
                              "sig": "x"}},
        lambda sm, c: _k1_rows(sm, "SELECT artist_steam_id FROM shop_items WHERE sku = :s", s=c["sku"]),
        lambda c, b: b == {"status": "ok", "sku": c["sku"], "artist_steam_id": c["t"]},
        lambda c: {"status": "ok", "sku": c["sku"], "artist_steam_id": c["t"]}),
    "achievement_title_repair": (
        "admin_grant_achievement", "POST", "/api/v1/admin/grant-achievement",
        _k1_repair_seed,
        lambda c: {"json": {"admin_steam_id": c["a"], "target_steam_id": c["t"],
                            "achievement_key": K1_TITLE_KEY}},
        lambda sm, c: _k1_rows(sm, "SELECT pi.item_id FROM player_items pi JOIN shop_items si"
                                   "    ON si.id = pi.item_id WHERE pi.player_id = :p AND si.sku = :s",
                               p=c["pid"], s=c["sku"]),
        lambda c, b: b == {"status": "already_unlocked"},
        lambda c: {"status": "already_unlocked"}),
}

# Each site's mutant restores the unconditional write: its guard never returns
# early, so the path that changed nothing goes on to the record and the commit.
K1_MUTANTS = {
    "spam_pattern_revoke": (('        return {"status": "ok", "cleared": 0}\n', "        pass\n"),),
    "record_exclude": (("    if stored is None:\n", "    if False:\n"),),
    "purge_user": (("        if not purged and not muted:\n", "        if False:\n"),),
    "purge_channel": (("        if not purged:\n", "        if False:\n"),),
    "artist_grant": (("    if changed is None:\n", "    if False:\n"),),
    "artist_revoke": (("    if changed is None:\n", "    if False:\n"),),
    "item_artist": (("    if item.artist_steam_id == (artist_steam_id or None):\n", "    if False:\n"),),
    "achievement_title_repair": (("            if restored is not None:\n", "            if True:\n"),),
}


def _k1_check(case, site, handler):
    _, method, path, seed, req, state, changed_answer, same_answer = K1_SITES[site]

    async def body(sm):
        ctx = await _commit(sm, seed)
        before = (await _k1_records(sm), await state(sm, ctx))
        r1, c1 = await _k1_call(sm, method, path, handler, **req(ctx))
        after1 = (await _k1_records(sm), await state(sm, ctx))
        r2, c2 = await _k1_call(sm, method, path, handler, **req(ctx))
        after2 = (await _k1_records(sm), await state(sm, ctx))
        return ctx, before, (r1.status_code, r1.text, c1), after1, (r2.status_code, r2.text, c2), after2
    ctx, before, one, after1, two, after2 = _with_sm(case, body)
    # the control: the changing call
    assert one[0] == 200 and changed_answer(ctx, json.loads(one[1])), (site, one)
    assert one[2] == 1, (site, "the changing call's commits", one)
    assert after1[0] == before[0] + 1, (site, "the changing call's record", before[0], after1[0])
    assert after1[1] != before[1], (site, "the changing call changed nothing", before[1])
    # the call that changed nothing
    assert two[0] == 200 and json.loads(two[1]) == same_answer(ctx), (site, "the answer", two)
    assert after2[0] == after1[0], (site, "a record for a call that changed nothing", after1[0], after2[0])
    assert two[2] == 0, (site, "a commit for a call that changed nothing", two[2])
    assert after2[1] == after1[1], (site, "the route's table changed", after1[1], after2[1])


@pytest.mark.parametrize("site", sorted(K1_SITES))
def test_k1_a_call_that_changes_nothing_records_nothing_and_commits_nothing(case, admin_open, site):
    _k1_check(case, site, getattr(main, K1_SITES[site][0]))


@pytest.mark.parametrize("site", sorted(K1_MUTANTS))
def test_k1_mutant_with_the_unconditional_write_restored_is_red(case, admin_open, site):
    fn = _mutant_of(K1_SITES[site][0], *K1_MUTANTS[site])
    with pytest.raises(AssertionError) as e:
        _k1_check(case, site, fn)
    print("\nMUTANT-RED K1 %s: %s" % (site, str(e.value).splitlines()[0][:160]))


# -- K3: the item artist route's row lock ----------------------------------------
#
# The route reads the shop item under the weakest lock that still conflicts
# with its own later write, which changes artist_steam_id alone (a column no
# key uses): FOR NO KEY UPDATE. An insert or key change that references the
# item takes FOR KEY SHARE on its row; FOR NO KEY UPDATE does not block it,
# FOR UPDATE does. The test calls the route through its own handler (the K1
# ASGI app with the get_db override) and reads every statement the route
# sends to the test's engine, by a cursor-execute event, not a copy.

_K3_FOR_UPDATE_ALONE = re.compile(r"(?<!NO KEY )\bFOR\s+UPDATE\b", re.I)


def _k3_check(case, handler):
    from sqlalchemy import event
    _, method, path, seed, req, _, changed_answer, _ = K1_SITES["item_artist"]

    async def body(sm):
        ctx = await _commit(sm, seed)
        sent = []

        def collect(conn, cursor, statement, parameters, context, executemany):
            sent.append(statement)
        engine = sm.kw["bind"].sync_engine
        event.listen(engine, "before_cursor_execute", collect)
        try:
            r, commits = await _k1_call(sm, method, path, handler, **req(ctx))
        finally:
            event.remove(engine, "before_cursor_execute", collect)
        return ctx, r, commits, sent
    ctx, r, commits, sent = _with_sm(case, body)
    # the control: the call reached the route's write
    assert r.status_code == 200 and changed_answer(ctx, r.json()), (r.status_code, r.text[:200])
    assert commits == 1, commits
    flat = [" ".join(s.split()) for s in sent]
    reads = [s for s in flat if re.match(r"SELECT\b", s, re.I)
             and re.search(r"\bFROM\s+shop_items\b", s, re.I)]
    assert len(reads) == 1, ("the route's SELECTs of shop_items", reads)
    assert re.search(r"\bFOR\s+NO\s+KEY\s+UPDATE$", reads[0], re.I), reads[0]
    alone = [s for s in flat if _K3_FOR_UPDATE_ALONE.search(s)]
    assert alone == [], ("a statement holds FOR UPDATE alone", alone)


def test_k3_the_item_artist_route_reads_its_item_for_no_key_update(case, admin_open):
    _k3_check(case, main.admin_set_item_artist)


def test_k3_mutant_without_key_share_is_red(case, admin_open):
    fn = _mutant_of("admin_set_item_artist", ("with_for_update(key_share=True)", "with_for_update()"))
    with pytest.raises(AssertionError) as e:
        _k3_check(case, fn)
    print("\nMUTANT-RED K3 item_artist: %s" % str(e.value).splitlines()[0][:160])


# -- F1: a mute record names the player the mute changed ---------------------------
#
# Each mute-by-message route resolves a Discord author to the live account
# linked to it and mutes that account. The test wraps the mute helper: after
# it returns, and before the route writes its record, a second session moves
# that account's Discord link to another id and commits. The record must name
# the account the mute changed, and the mute must stand.

async def _f1_mute_by_message(sm, handler, a, did):
    async with sm() as db:
        mid = await _chat_row(db, source="discord", discord_id=did)
        await db.commit()
    async with sm() as db:
        await handler(main._ChatModMuteMsgReq(
            steam_id=a, message_id=mid, duration_minutes=30, reason="spam lines"), None, db=db)
    return mid


async def _f1_discord_mute(sm, handler, a, did):
    dm = "dc-%s" % uuid.uuid4().hex[:12]
    async with sm() as db:
        mid = await _chat_row(db, source="discord", discord_id=did, mirror=("discord", dm))
        await db.commit()
    async with sm() as db:
        await handler(
            {"message_id": dm, "actor_discord_id": "420000000000000078", "actor_name": "Mod Example",
             "actor_channel_lang": "global", "duration_minutes": 60},
            x_internal_key=INTERNAL_KEY, db=db)
    return mid


F1_ROUTES = {"mute_by_message": ("chat_moderate_mute_by_message", _f1_mute_by_message),
             "discord_mute": ("internal_chat_discord_mute", _f1_discord_mute)}
F1_SWAP = ("authors, unlinked = _modlog_mute_named(result)",
           "authors, unlinked = await _modlog_chat_authors(db, [row])")


def _f1_check(case, monkeypatch, route, handler, relink):
    real = main._apply_mute_for_row

    async def body(sm):
        async def seed(db):
            a, _ = await _admin(db)
            did = _did()
            linked, _ = await _player(db, discord_id=did)
            return a, linked, did
        a, linked, did = await _commit(sm, seed)
        moved = []

        async def mute_then_relink(db, row, **kw):
            result = await real(db, row, **kw)
            if relink:
                async with sm() as other:
                    await other.execute(text("SET LOCAL lock_timeout = '5s'"))
                    await other.execute(text("UPDATE players SET discord_id = :d WHERE steam_id = :s"),
                                        {"d": _did(), "s": linked})
                    await other.commit()
                moved.append(linked)
            return result
        monkeypatch.setattr(main, "_apply_mute_for_row", mute_then_relink)
        try:
            mid = await F1_ROUTES[route][1](sm, handler, a, did)
        finally:
            monkeypatch.setattr(main, "_apply_mute_for_row", real)
        async with sm() as db:
            recs = await _record_of_message(db, mid)
            mutes = (await db.execute(text(
                "SELECT count(*) FROM chat_mutes WHERE steam_id = :s AND revoked_at IS NULL"),
                {"s": linked})).scalar()
            now_did = (await db.execute(text("SELECT discord_id FROM players WHERE steam_id = :s"),
                                        {"s": linked})).scalar()
        return linked, did, moved, recs, mutes, now_did
    linked, did, moved, recs, mutes, now_did = _with_sm(case, body)
    # the setting: the link moved between the mute and its record (or, for
    # the control, did not)
    assert moved == ([linked] if relink else []), moved
    assert (now_did != did) is relink, (route, now_did, did)
    assert mutes == 1, (route, relink, "the linked account's mute", mutes)
    assert len(recs) == 1, (route, relink, recs)
    assert recs[0]["affected_steam_ids"] == [linked], (route, relink, recs[0]["affected_steam_ids"],
                                                       recs[0]["details"])
    assert "unlinked_discord_authors" not in recs[0]["details"], (route, relink, recs[0]["details"])


@pytest.mark.parametrize("relink", [True, False], ids=["link_moved", "control_link_kept"])
@pytest.mark.parametrize("route", sorted(F1_ROUTES))
def test_f1_the_mute_record_names_the_account_the_mute_changed(case, admin_open, monkeypatch, route, relink):
    _f1_check(case, monkeypatch, route, getattr(main, F1_ROUTES[route][0]), relink)


@pytest.mark.parametrize("route", sorted(F1_ROUTES))
def test_f1_mutant_with_the_second_lookup_is_red(case, admin_open, monkeypatch, route):
    fn = _mutant_of(F1_ROUTES[route][0], F1_SWAP)
    with pytest.raises(AssertionError) as e:
        _f1_check(case, monkeypatch, route, fn, True)
    print("\nMUTANT-RED F1 %s second lookup: %s" % (route, str(e.value).splitlines()[0][:160]))


def test_f1_the_names_come_from_the_mute_answer_alone():
    sid = "76561190420999901"
    assert main._modlog_mute_named({"muted": "steam:" + sid}) == ([sid], 0)
    assert main._modlog_mute_named({"muted": "discord:1", "linked_steam": sid}) == ([sid], 0)
    assert main._modlog_mute_named({"muted": "discord:1", "linked_steam": None}) == ([], 1)
    assert main._modlog_mute_named({"muted": "twitch:abc"}) == ([], 0)


# -- F2: the deletion rewrites a record whose id stands only in details -------------
#
# Records whose deleted id stands only in details, stored as a JSON string, an
# array, an object, and a JSON string that holds JSON text. After the deletion
# no stored text of any of them holds the id, each keeps its JSON type, and the
# read finds no record by the id.

F2_KINDS = {"string": "string", "array": "array", "object": "object", "json_text": "string"}


def _f2_details(kind, sid):
    if kind == "string":
        return "muted %s for spam lines" % sid
    if kind == "array":
        return ["x", "from %s." % sid]
    if kind == "object":
        return {"note": "from %s." % sid}
    return json.dumps({"note": "from %s." % sid})


def _f2_delete(case, monkeypatch, kind, scrub=None):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", base.DELETE_SECRET)
    if scrub is not None:
        monkeypatch.setattr(main, "_modlog_scrub_records", scrub)
    import cf_asm

    async def body(sm):
        async with sm() as db:
            a, _ = await _admin(db)
            gone, gpid = await _player(db, name="Leaving Player")
            rid = (await db.execute(text(
                "INSERT INTO admin_actions (admin_steam_id, action, details)"
                " VALUES (:a, 'chat_mute', CAST(:d AS jsonb)) RETURNING id"),
                {"a": a, "d": json.dumps(_f2_details(kind, gone))})).scalar()
            await db.commit()
        sig = hmac.new(base.DELETE_SECRET.encode(), ("delete:%s" % gone).encode(),
                       hashlib.sha256).hexdigest()
        async with sm() as db:
            await main.delete_player_data(gone, cf_asm.FakeRequest(), sig=sig, _slot=None, db=db)
        async with sm() as db:
            row = (await db.execute(text(
                "SELECT COALESCE(reason, '') || ' ' || CAST(details AS text) || ' '"
                "       || COALESCE(target_steam_id, '') || ' ' || admin_steam_id || ' '"
                "       || array_to_string(affected_steam_ids, ' ') AS texts,"
                "       jsonb_typeof(details) AS t, CAST(details AS text) AS details_text"
                "  FROM admin_actions WHERE id = :i"), {"i": rid})).mappings().first()
            tomb = (await db.execute(text("SELECT steam_id FROM players WHERE id = :i"),
                                     {"i": gpid})).scalar()
        found = await _read(sm, q=gone, include_reads=1, limit=100)
        return gone, tomb, row, found
    return _with_sm(case, body)


def _f2_check(case, monkeypatch, kind, scrub=None):
    gone, tomb, row, found = _f2_delete(case, monkeypatch, kind, scrub)
    assert tomb.startswith("deleted_"), tomb
    assert gone not in row["texts"], (kind, "the id still stored", row["texts"])
    assert row["t"] == F2_KINDS[kind], (kind, "the JSON type", row["t"])
    assert json.loads(row["details_text"]) == _f2_details(kind, tomb), (kind, row["details_text"])
    assert found["total"] == len(found["rows"]) == 0, (kind, "the read finds the id", found["total"])


@pytest.mark.parametrize("kind", sorted(F2_KINDS))
def test_f2_the_deletion_rewrites_details_of_each_json_type(case, admin_open, monkeypatch, kind):
    _f2_check(case, monkeypatch, kind)


F2_MUTANT = ("if all(new[k] == old[k] for k in old):",
             "if all(new[k] == (new[k] if k == 'details' else old[k]) for k in old):")


@pytest.mark.parametrize("kind", sorted(F2_KINDS))
def test_f2_mutant_comparing_against_the_scrubbed_details_is_red(case, admin_open, monkeypatch, kind):
    fn = _mutant_of("_modlog_scrub_records", F2_MUTANT)
    with pytest.raises(AssertionError) as e:
        _f2_check(case, monkeypatch, kind, scrub=fn)
    print("\nMUTANT-RED F2 %s compared against the scrubbed value: %s"
          % (kind, str(e.value).splitlines()[0][:160]))


# The read serves a record whose details is no object (the deletion keeps a
# record's JSON type, so such a record stays one): it answers with every row,
# the details as stored and a sentence, never an error. The object is the
# control.
F2_READ_DETAILS = {"array": ["x", "y"], "number": 7, "json_array_text": "[1, 2]", "object": {"note": "n"}}


def _f2_read_check(case, answer=None):
    async def body(sm):
        async with sm() as db:
            a, _ = await _admin(db)
            for d in F2_READ_DETAILS.values():
                await db.execute(text(
                    "INSERT INTO admin_actions (admin_steam_id, action, details)"
                    " VALUES (:a, 'chat_mute', CAST(:d AS jsonb))"), {"a": a, "d": json.dumps(d)})
            await db.commit()
        f = main._modlog_parse(_qp(actor=a, limit=100))
        async with sm() as db:
            try:
                return await (answer or main._modlog_answer)(db, f)
            except Exception as e:  # what reaches the client as a 500
                return ("error", type(e).__name__, str(e)[:120])
    ans = _with_sm(case, body)
    assert isinstance(ans, dict), ans
    assert ans["total"] == len(ans["rows"]) == len(F2_READ_DETAILS), ans["total"]
    assert all(isinstance(r["sentence"], str) and r["sentence"] for r in ans["rows"]), ans["rows"]
    served = [json.dumps(r["details"], sort_keys=True) for r in ans["rows"]]
    for d in (["x", "y"], 7, {"note": "n"}):
        assert served.count(json.dumps(d, sort_keys=True)) == 1, (d, served)


def test_f2_the_read_serves_a_record_whose_details_is_no_object(case):
    _f2_read_check(case)


def test_f2_mutant_read_without_the_object_guard_is_red(case):
    fn = _mutant_of("_modlog_answer", ("facts = details if isinstance(details, dict) else {}",
                                       "facts = details"))
    with pytest.raises(AssertionError) as e:
        _f2_read_check(case, fn)
    print("\nMUTANT-RED F2 read without the object guard: %s" % str(e.value).splitlines()[0][:160])


# -- F3: a page key whose sort value is not storable text is refused --------------
#
# A key valid in every other way whose sort value holds a NUL (or a lone
# surrogate, which has no UTF-8 encoding) answers 422 after_invalid on the read
# and on its internal twin, for each sort that binds a text value, both
# directions; a valid key's page answers.

F3_SORTS = sorted(k for k in main._MODLOG_ORDER if k[0] != "time")
F3_BAD = ("ban\x00x", "\x00", "ban\ud800")


def _f3_key(sort, direction, value):
    raw = json.dumps([sort, direction, value, "2026-11-16T12:00:00+00:00", str(uuid.uuid4())],
                     separators=(",", ":"), ensure_ascii=True)
    return main.base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii").rstrip("=")


def _f3_answers(case, keys):
    async def body(sm):
        async def seed(db):
            did = _did()
            a, _ = await _admin(db, discord_id=did)
            await main._modlog_write(db, actor=a, action="chat_mute", details={"note": "f3"})
            return a, did
        a, did = await _commit(sm, seed)
        out = []
        for route in ("admin", "internal"):
            for sort, direction, value in keys:
                # the actor filter keeps the page to this test's own record
                kw = {"after": _f3_key(sort, direction, value), "sort": sort, "dir": direction, "actor": a}
                try:
                    async with sm() as db:
                        if route == "admin":
                            ans = await main.admin_modlog(
                                base._Req(admin_steam_id=a, hmac_signature="x", **kw), db=db)
                        else:
                            ans = await main.internal_modlog(
                                base._Req(**kw), x_internal_key=INTERNAL_KEY, x_actor_discord_id=did,
                                db=db)
                    got = ("answered", isinstance(ans, dict) and "rows" in ans)
                except HTTPException as e:
                    got = (e.status_code, e.detail)
                except Exception as e:  # what reaches the client as a 500
                    got = ("error", type(e).__name__)
                out.append((route, sort, direction, repr(value), got))
        return out
    return _with_sm(case, body)


def _f3_check(case):
    keys = [(s, d, v) for s, d in F3_SORTS for v in F3_BAD]
    for route, sort, direction, value, got in _f3_answers(case, keys):
        assert got == (422, "after_invalid"), (route, sort, direction, value, got)


def test_f3_a_key_whose_sort_value_is_not_storable_text_is_422(case, admin_open):
    _f3_check(case)


def test_f3_control_a_valid_key_answers_its_page(case, admin_open):
    keys = [(s, d, "chat_mute" if s == "action" else "76561190420999902") for s, d in F3_SORTS]
    for route, sort, direction, value, got in _f3_answers(case, keys):
        assert got == ("answered", True), (route, sort, direction, value, got)


F3_CHECK = ("    if value is not None and not _pg_text_ok(value):\n"
            "        raise HTTPException(status_code=422, detail=\"after_invalid\")\n")


def test_f3_mutant_without_the_check_is_red(case, admin_open, monkeypatch):
    monkeypatch.setattr(main, "_modlog_unkey", _mutant_of("_modlog_unkey", (F3_CHECK, "")))
    with pytest.raises(AssertionError) as e:
        _f3_check(case)
    print("\nMUTANT-RED F3 check removed: %s" % str(e.value).splitlines()[0][:160])
