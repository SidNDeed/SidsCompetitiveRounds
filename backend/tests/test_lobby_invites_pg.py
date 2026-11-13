"""Lobby invites on PostgreSQL (migration 405's change): the server half's
tests, design note section 11, against a local PostgreSQL through inv_pg
(one cf_pg case schema per case, the real handlers in main.py).

Every behaviour test here has its mutant, a statement rewrite that must turn
the named assertion red (each asserts that its rewrite reached a statement),
and its control, the same check on an ordinary mail or request that keeps
today's answer.
"""

import json
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import inv_pg as inv  # noqa: E402
from inv_pg import Answer, Req, case, key, placeholder_rx  # noqa: E402

import mail_discord  # noqa: E402
import main  # noqa: E402
from sqlalchemy import text  # noqa: E402


# -- the harness, end to end ---------------------------------------------------

@pytest.mark.parametrize("mode", inv.MODES)
def test_an_invite_is_listed_for_its_invitee_and_an_accept_seats_them(monkeypatch, mode):
    """The path every other test builds on, in each mode: the send writes a
    pending invite whose mail copy is delivered and bumps the invitee's
    revision; the invitee's pending list shows it; the accept seats them and
    marks it accepted; the accept's repeat answers the lobby as it is now and
    writes nothing; the pending list is then empty."""
    async def body(env):
        lid, (host,) = await env.lobby(mode, 1)
        guest = await env.player()
        rev0 = await env.rev(guest)
        iid = await env.invite(host, guest, mode, lid)
        row = await env.row(iid)
        assert (row["state"], row["kind"], row["mode"], row["lobby_id"]) == \
            ("pending", "invite", mode, lid), row
        assert await env.delivery(row["mail_message_id"], guest) == "delivered"
        assert await env.rev(guest) > rev0
        listed = await env.pending(guest)
        assert listed.status == 200 and [i["invite_id"] for i in listed["invites"]] == [str(iid)], listed
        k = key()
        first = await env.accept(guest, iid, k=k)
        assert first.status == 200 and first["lobby_id"] == str(lid), first
        assert guest.id in await env.members(mode, lid)
        assert (await env.row(iid))["state"] == "accepted"
        snap = await env.snapshot()
        again = await env.accept(guest, iid, k=k)
        assert again.status == 200 and again["lobby_id"] == str(lid), again
        assert await env.snapshot() == snap, "an accept's repeat wrote"
        assert (await env.pending(guest))["invites"] == []
    case(monkeypatch, body)


# -- the sender's handle, one test per mail route (section 11, first item) -----
#
# An invite's sender holds no handle on its mail row: for each mail route the
# sender gets exactly the answer of an absent id, byte for byte (the delete's
# 200 names the id it was asked about, so that id is masked), for a delivered,
# a suppressed and a purged invite, before and after the sweeps.

ROUTES = ("sent", "detail", "reply", "reply_all", "delete", "read", "report", "readback")

_KIND_FILTER = " AND m.kind <> 'invite'"
MUTANTS = {
    "sent": (_KIND_FILTER, ""),
    "detail": (_KIND_FILTER, ""),
    "reply": (_KIND_FILTER, ""),
    "reply_all": (_KIND_FILTER, ""),
    "delete": (" AND kind <> 'invite'", ""),
    # read and report: the delivered-recipient condition names the caller;
    # the mutant names every other recipient instead, keeping the bind.
    "read": (placeholder_rx("recipient_id"), r"recipient_id <> \1"),
    "report": (placeholder_rx("r.recipient_id"), r"r.recipient_id <> \1"),
    "readback": (_KIND_FILTER, ""),
}


async def _ask(env, route, who, mid):
    """`who`'s answer from `route` about mail row `mid`, as a wire string
    with the asked id masked (the delete's answer names it). For Sent: the
    ids it lists."""
    s = str(mid)
    if route == "sent":
        ans = await env.call(lambda db: main.mail_sent(Req(who.sid), cursor="",
                                                        limit=main.MAIL_PAGE_MAX, db=db))
        assert ans.status == 200, ans
        return sorted(m["id"] for m in ans["messages"])
    if route == "detail":
        ans = await env.call(lambda db: main.mail_detail(s, Req(who.sid), db))
    elif route in ("reply", "reply_all"):
        req = main._MailReplyReq(body="A short reply.", all=(route == "reply_all"),
                                 idempotency_key=key())
        ans = await env.call(lambda db: main.mail_reply(s, req, Req(who.sid), db))
    elif route == "delete":
        ans = await env.call(lambda db: main.mail_delete(s, Req(who.sid), db))
    elif route == "read":
        ans = await env.call(lambda db: main.mail_read(s, Req(who.sid), db))
    elif route == "report":
        ans = await env.call(lambda db: main.mail_report(s, main._MailReportReq(reason=""),
                                                         Req(who.sid), db))
    elif route == "readback":
        ans = await _readback(env, who, mid)
    else:                                                  # pragma: no cover
        raise AssertionError(route)
    return ans.wire.replace(s, "<id>")


async def _readback(env, who, mid):
    """The Discord reply's read-back (mail_discord._REPLIED_TO_SQL) for a
    reply by `who` whose parent is `mid`; an absent `mid` has no such reply.
    Its answer: {known} as the route builds it."""
    rid = uuid.uuid4()
    exists = await env.conn.fetchval("SELECT EXISTS (SELECT 1 FROM mail_messages WHERE id = $1)", mid)
    if exists:
        await env.conn.execute(
            "INSERT INTO mail_messages (id, sender_id, kind, thread_id, in_reply_to, subject, body,"
            "                           idempotency_key, via)"
            " VALUES ($1, $2, 'direct', $3, $3, 'Re: x', 'A reply.', $4, 'discord')",
            rid, who.id, mid, uuid.uuid4())
    async with env.sm() as db:
        ctx = (await db.execute(text(mail_discord._REPLIED_TO_SQL), {
            "rid": str(rid), "sid": who.sid, "pid": str(who.id),
            "ret_days": main.MAIL_RETENTION_DAYS})).mappings().first()
    return Answer(200, {"known": ctx is not None})


@pytest.mark.parametrize("route", ROUTES)
def test_an_invites_sender_gets_the_answer_of_an_absent_id(monkeypatch, route):
    async def body(env):
        lid, (s,) = await env.lobby("team", 1)
        d = await env.player()
        u = await env.player(mail_from="nobody")
        g = await env.player()
        ctrl = await env.mail(s, [d])
        assert ctrl.status == 200, ctrl
        ctrl_mid = uuid.UUID(ctrl["id"])
        mids = {}
        for name, p in (("delivered", d), ("suppressed", u), ("purged", g)):
            iid = await env.invite(s, p, "team", lid)
            mids[name] = (iid, await env.mail_of(iid))
        assert await env.delivery(mids["delivered"][1], d) == "delivered"
        assert await env.delivery(mids["suppressed"][1], u) == "suppressed"
        await env.age(mids["purged"][0], kept_days=main.INVITE_KEEP_DAYS + 1,
                      mail_days=main.MAIL_RETENTION_DAYS + 1)
        absent = uuid.uuid4()

        async def holds(phase):
            if route == "sent":
                assert await _ask(env, route, s, None) == [str(ctrl_mid)], (phase, "Sent lists an invite")
                return
            want = await _ask(env, route, s, absent)
            for name, (_iid, mid) in mids.items():
                assert await _ask(env, route, s, mid) == want, (phase, route, name)
            if route == "delete":
                # the 200 changed nothing: the invite's mail rows are as sent
                n = await env.conn.fetchval(
                    "SELECT COUNT(*) FROM mail_messages WHERE id = ANY($1::uuid[])"
                    "   AND deleted_by_sender_at IS NOT NULL", [m for _i, m in mids.values()])
                assert n == 0, (phase, "the sender's delete reached an invite's mail row")

        await holds("before")
        await env.sweep()
        await env.retention()
        await holds("after")

        # the mutant: this route's own condition taken out
        old, new = MUTANTS[route]
        live = mids["delivered"][1]
        with env.rewriting(old, new) as hits:
            if route == "sent":
                got = await _ask(env, route, s, None)
                assert got != [str(ctrl_mid)], "the Sent mutant did not list the invite"
            elif route == "delete":
                # the delete answers 200 either way; its mutant shows in the row
                await _ask(env, route, s, live)
                assert await env.conn.fetchval(
                    "SELECT deleted_by_sender_at IS NOT NULL FROM mail_messages WHERE id = $1", live), \
                    "the delete mutant left the invite's mail row as sent"
            else:
                assert await _ask(env, route, s, live) != await _ask(env, route, s, absent), \
                    "the %s mutant left the sender's answer unchanged" % route
        assert hits, "the %s mutant reached no statement" % route

        # the control: an ordinary mail keeps today's answer
        if route in ("read", "report"):
            got = await _ask(env, route, d, ctrl_mid)
            assert json.loads(got)[0] == 200, got
        elif route == "sent":
            pass                                  # the before/after checks list the ordinary mail
        else:
            got = await _ask(env, route, s, ctrl_mid)
            if route == "readback":
                assert json.loads(got) == [200, {"known": True}], got
            elif route == "delete":
                assert json.loads(got)[0] == 200, got
                assert await env.conn.fetchval(
                    "SELECT deleted_by_sender_at IS NOT NULL FROM mail_messages WHERE id = $1",
                    ctrl_mid), "the sender's delete of an ordinary mail did not take it out of Sent"
            else:
                assert json.loads(got)[0] == 200, got
    case(monkeypatch, body)


# -- reserved keys, no mail receipt, and 404's trigger (section 11) ------------

def test_an_invites_mail_rows_hold_reserved_keys_and_no_mail_receipt(monkeypatch):
    """Every invite's mail row has a key in the reserved space (version
    digit 0), and no mail_send_receipts row names it, for a delivered and a
    suppressed copy and for a challenge. The mutant widens 404's trigger to
    every kind inside a transaction that is rolled back: the invite's mail
    row then fails the receipts' kind check. The control: a direct send
    writes its receipt."""
    async def body(env):
        lid, (s,) = await env.lobby("team", 1)
        d = await env.player()
        u = await env.player(mail_from="nobody")
        c = await env.player()
        iids = [await env.invite(s, d, "team", lid), await env.invite(s, u, "team", lid)]
        t = await env.player()
        iids.append(await env.invite(t, c, "ovt"))                  # a challenge
        for iid in iids:
            mid = await env.mail_of(iid)
            k = await env.conn.fetchval("SELECT idempotency_key FROM mail_messages WHERE id = $1", mid)
            assert str(k)[14] == "0", ("an invite's mail key outside the reserved space", k)
            assert await env.conn.fetchval(
                "SELECT COUNT(*) FROM mail_send_receipts WHERE message_id = $1", mid) == 0
        ctrl = await env.mail(s, [d])
        assert ctrl.status == 200, ctrl
        assert await env.conn.fetchval(
            "SELECT COUNT(*) FROM mail_send_receipts WHERE message_id = $1", uuid.UUID(ctrl["id"])) == 1

        # the mutant: 404's trigger with its WHEN widened to every kind
        side = await env.side()
        tdef = await side.fetchval(
            "SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
            " WHERE c.relname = 'mail_messages' AND NOT t.tgisinternal"
            "   AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())")
        assert tdef and " WHEN (" in tdef, tdef
        head, rest = tdef.split(" WHEN (", 1)
        widened = head + " EXECUTE " + rest.split(") EXECUTE ", 1)[1]
        name = tdef.split("CREATE TRIGGER ", 1)[1].split(" ", 1)[0]

        async def invite_row_in(conn):
            mid = uuid.uuid4()
            await conn.execute(
                "INSERT INTO mail_messages (id, sender_id, kind, thread_id, subject, body,"
                "                           idempotency_key, via)"
                " VALUES ($1, $2, 'invite', $1, 'Lobby invite: 2v2', 'x', $3, 'game')",
                mid, s.id, main._invite_mail_key())
            await conn.execute(
                "UPDATE mail_messages SET recipient_count = 1 WHERE id = $1", mid)
            return mid
        tr = side.transaction()
        await tr.start()
        try:
            mid = await invite_row_in(side)                           # as written: no error, no receipt
            assert await side.fetchval(
                "SELECT COUNT(*) FROM mail_send_receipts WHERE message_id = $1", mid) == 0
            await side.execute("DROP TRIGGER %s ON mail_messages" % name)
            await side.execute(widened)
            with pytest.raises(Exception) as info:
                await invite_row_in(side)
            assert "mail_send_receipts" in str(info.value) or "check" in str(info.value).lower(), info.value
        finally:
            await tr.rollback()
    case(monkeypatch, body)
