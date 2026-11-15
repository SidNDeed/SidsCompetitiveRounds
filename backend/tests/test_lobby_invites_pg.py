"""Lobby invites on PostgreSQL (migration 416's change): the server half's
tests, design note section 11, against a local PostgreSQL through inv_pg
(one cf_pg case schema per case, the real handlers in main.py).

Every behaviour test here has its mutant, a statement rewrite that must turn
the named assertion red (each asserts that its rewrite reached a statement),
and its control, the same check on an ordinary mail or request that keeps
today's answer.
"""

import ast
import asyncio
import json
import os
import re
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
        # A plain reply goes to its parent's sender, so on the sender's own
        # mail it has no addressee (today's 400 recipients_empty); the reply's
        # control is a mail the sender received.
        ctrl_in = None
        if route == "reply":
            got_in = await env.mail(d, [s])
            assert got_in.status == 200, got_in
            ctrl_in = uuid.UUID(got_in["id"])
        mids = {}
        for name, p in (("delivered", d), ("suppressed", u), ("purged", g)):
            iid = await env.invite(s, p, "team", lid)
            mids[name] = (iid, await env.mail_of(iid))
        assert await env.delivery(mids["delivered"][1], d) == "delivered"
        assert await env.delivery(mids["suppressed"][1], u) == "suppressed"
        await env.age(mids["purged"][0], kept_days=main.INVITE_KEEP_DAYS + 1,
                      mail_days=main.MAIL_RETENTION_DAYS + 1)
        # read, so the mail retention sweep expires the copy and purges the row
        await env.conn.execute("UPDATE mail_recipients SET read_at = NOW() WHERE message_id = $1",
                               mids["purged"][1])
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
        assert not await env.conn.fetchval("SELECT EXISTS (SELECT 1 FROM mail_messages WHERE id = $1)",
                                           mids["purged"][1]), "the purged invite's mail row was kept"
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
            got = await _ask(env, route, s, ctrl_in if route == "reply" else ctrl_mid)
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


# -- reserved keys, no mail receipt, and 415's trigger (section 11) ------------

def test_an_invites_mail_rows_hold_reserved_keys_and_no_mail_receipt(monkeypatch):
    """Every invite's mail row has a key in the reserved space (version
    digit 0), and no mail_send_receipts row names it, for a delivered and a
    suppressed copy and for a challenge. The mutant widens 415's trigger to
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

        # the mutant: 415's trigger with its WHEN widened to every kind
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


# -- no path takes the per-sender mail lock after a lobby lock (section 11) ----

MAIN_PY = os.path.join(HERE, "..", "api", "main.py")
# The functions that take the per-sender mail lock themselves. A new taker
# fails the test, so its place in the lock order is looked at before it lands.
MAIL_LOCK_TAKERS = {"mail_send", "_mail_reply_core", "admin_mail_broadcast", "invite_send"}
_ROW_LOCK = re.compile(r"FOR (NO KEY )?UPDATE")
_LOBBY_ROW = re.compile(r"\b(team|ovt|ffa)_lobbies\b|_INVITE_LOBBY_TABLES|\[.lobbies.\]")


def _lock_order(src):
    """(problems, facts) for main.py's source: every function's calls in
    line order; a lobby lock is a statement naming a lobby table with FOR
    UPDATE or FOR NO KEY UPDATE (a literal, an f-string, or a module string
    a function names), or a call to a function that takes one; a mail-lock
    holder is _mail_lock_sender or a function that reaches it. A problem is
    a call that reaches the mail lock below the function's first lobby lock."""
    tree = ast.parse(src)
    fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    const_locks = set()
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            seg = ast.get_source_segment(src, n.value) or ""
            if _ROW_LOCK.search(seg) and _LOBBY_ROW.search(seg):
                const_locks.add(n.targets[0].id)

    def callee(c):
        f = c.func
        return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None

    # a call with no plain name (a call's result called, a subscript) sorts
    # as "" so two calls on one line always compare
    calls = {name: sorted((c.lineno, callee(c) or "") for c in ast.walk(fn) if isinstance(c, ast.Call))
             for name, fn in fns.items()}
    direct = {}
    for name, fn in fns.items():
        lines = []
        for node in ast.walk(fn):
            if isinstance(node, (ast.Constant, ast.JoinedStr)) and not (
                    isinstance(node, ast.Constant) and not isinstance(node.value, str)):
                seg = ast.get_source_segment(src, node) or ""
                if _ROW_LOCK.search(seg) and _LOBBY_ROW.search(seg):
                    lines.append(node.lineno)
            elif isinstance(node, ast.Name) and node.id in const_locks:
                lines.append(node.lineno)
        if lines:
            direct[name] = min(lines)
    takers = {n for n, cs in calls.items() if any(c == "_mail_lock_sender" for _l, c in cs)}
    reach = set(takers) | {"_mail_lock_sender"}
    lobby = set(direct)
    for _ in range(len(fns)):
        grew = False
        for n, cs in calls.items():
            if n not in reach and any(c in reach for _l, c in cs):
                reach.add(n)
                grew = True
            if n not in lobby and any(c in lobby for _l, c in cs):
                lobby.add(n)
                grew = True
        if not grew:
            break
    problems = []
    first = {}
    for n in fns:
        marks = [direct[n]] if n in direct else []
        marks += [ln for ln, c in calls[n] if c in lobby and c != n]
        if marks:
            first[n] = min(marks)
            late = [(ln, c) for ln, c in calls[n] if c in reach and c != n and ln > first[n]]
            if late:
                problems.append((n, first[n], late))
    return problems, {"takers": takers, "first": first, "calls": calls}


def test_no_path_takes_the_per_sender_mail_lock_after_a_lobby_lock():
    """The lock order every invite path keeps (main.py's invite section):
    the per-sender mail lock comes before any lobby row lock. Its positive
    controls: the checker finds invite_send's lobby lock and its mail lock
    above it. Its mutant: invite_send's mail lock moved below the lobby
    gates, which the checker refuses."""
    src = open(MAIN_PY, encoding="utf-8").read()
    problems, facts = _lock_order(src)
    assert facts["takers"] == MAIL_LOCK_TAKERS, sorted(facts["takers"])
    assert problems == [], problems
    lock_at = [ln for ln, c in facts["calls"]["invite_send"] if c == "_mail_lock_sender"]
    assert len(lock_at) == 1 and "invite_send" in facts["first"] and lock_at[0] < facts["first"]["invite_send"]
    assert "_invite_lobby_gates" in facts["first"] and "_invite_lock_lobby" in facts["first"]
    mutant = src
    for old, new in (
            ('    await _mail_lock_sender(db, me["id"])\n    prior = await _invite_prior(db, me["id"], key, fp)\n',
             '    prior = await _invite_prior(db, me["id"], key, fp)\n'),
            ('        ended = await _invite_lobby_gates(db, mode, lobby_id, me, invitee)\n',
             '        ended = await _invite_lobby_gates(db, mode, lobby_id, me, invitee)\n'
             '        await _mail_lock_sender(db, me["id"])\n')):
        assert mutant.count(old) == 1, old
        mutant = mutant.replace(old, new)
    bad, _facts = _lock_order(mutant)
    assert [p[0] for p in bad] == ["invite_send"], bad


# -- no answer carries a room name or a password (section 11) ------------------

def test_no_invite_answer_carries_a_room_name_or_a_password(monkeypatch):
    """A probe planted in every room and password column of the lobby row
    appears in no answer of the feature: the sends and their repeats, the
    pending list, the inbox and the reader, the lobby state's invite list,
    the accept and its repeat, a decline, a cancel and the refusals. The
    negative control plants the same probe in an answer (the pending list's
    invite object) and the check sees it."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        probe = "PRB" + uuid.uuid4().hex
        cols = [r["column_name"] for r in await env.conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'team_lobbies'"
            "   AND data_type IN ('text', 'character varying') AND column_name ~ '(room|password|pw)'")]
        assert cols, "the lobby row has no room or password column to plant the probe in"
        for col in cols:
            await env.conn.execute("UPDATE team_lobbies SET %s = $2 WHERE id = $1" % col, lid, probe)
        g1, g2, g3 = await env.players(3)
        answers = []
        k1 = key()
        answers.append(await env.send(h, g1, "team", lid, k=k1))
        answers.append(await env.send(h, g1, "team", lid, k=k1))               # its repeat
        answers.append(await env.send(h, g1, "team", lid))                     # already_invited
        iid1 = uuid.UUID(answers[0]["invite_id"])
        answers.append(await env.pending(g1))
        answers.append(await env.call(lambda db: main.mail_inbox(Req(g1.sid), cursor="",
                                                                 limit=main.MAIL_PAGE_MAX, db=db)))
        mid1 = await env.mail_of(iid1)
        answers.append(await env.call(lambda db: main.mail_detail(str(mid1), Req(g1.sid), db)))
        state = await env.call(lambda db: main._lobby_state_impl("team", h.sid, Req(h.sid), db))
        assert state.status == 200 and [i["invite_id"] for i in state["invites"]] == [str(iid1)], state
        answers.append(Answer(state.status, state["invites"]))     # the lobby state's invite list
        ka = key()
        answers.append(await env.accept(g1, iid1, k=ka))
        answers.append(await env.accept(g1, iid1, k=ka))                        # its repeat
        iid2 = await env.invite(h, g2, "team", lid)
        answers.append(await env.decline(g2, iid2))
        iid3 = await env.invite(h, g3, "team", lid)
        answers.append(await env.cancel(h, iid3))
        answers.append(await env.accept(g3, iid3))                              # a refusal
        c, t = await env.players(2)
        answers.append(await env.send(c, t, "team"))                            # a challenge
        statuses = [a.status for a in answers]
        assert statuses.count(200) >= 10, statuses
        for a in answers:
            assert probe not in a.wire, a
        # the negative control: a probe in an answer is seen
        real = main._invite_object

        async def leaky(db, row):
            out = await real(db, row)
            out["room"] = probe
            return out
        monkeypatch.setattr(main, "_invite_object", leaky)
        g4 = await env.player()
        await env.invite(h, g4, "team", lid)
        assert probe in (await env.pending(g4)).wire
    case(monkeypatch, body)


# -- the send rate counts invites; the same-body rule does not (section 11) ----

def test_the_send_rate_counts_a_senders_invites_from_their_rows(monkeypatch):
    """Eight invites and two direct mails fill the minute's window of ten,
    so the next send is refused 429. The mutant counts no invite row and the
    same send passes. The control: ten direct mails alone fill it too."""
    async def body(env):
        lid, (s,) = await env.lobby("team", 1)
        d = await env.player()
        invitees = await env.players(8)
        for p in invitees:
            await env.invite(s, p, "team", lid)
        for i in range(2):
            assert (await env.mail(s, [d], body="Message %d of the minute." % i)).status == 200
        assert (await env.mail(s, [d], body="One send too many.")).status == 429
        with env.rewriting(" WHERE sender_player_id = ", " WHERE FALSE AND sender_player_id = ") as hits:
            assert (await env.mail(s, [d], body="One send too many.")).status == 200
        assert hits, "the rate mutant reached no statement"
        t = await env.player()
        for i in range(10):
            assert (await env.mail(t, [d], body="Control message %d." % i)).status == 200
        assert (await env.mail(t, [d], body="Control message 10.")).status == 429
    case(monkeypatch, body)


def test_the_days_invite_count_is_the_same_for_a_delivered_and_a_suppressed_invite(monkeypatch):
    """The rate's invite statement counts rows, never deliveries: three
    delivered invites and three suppressed ones count three each. The mutant
    counts only delivered copies, and the two senders' counts part."""
    async def body(env):
        la, (a,) = await env.lobby("team", 1)
        lb, (b,) = await env.lobby("team", 1)
        for p in await env.players(3):
            await env.invite(a, p, "team", la)
        for p in await env.players(3, mail_from="nobody"):
            await env.invite(b, p, "team", lb)

        async def day(p):
            async with env.sm() as db:
                row = (await db.execute(text(main._INVITE_RATE_SQL), {"sid": p.id})).mappings().first()
            return int(row["invites_day"]), int(row["invites_minute"])
        assert await day(a) == await day(b) == (3, 3)
        with env.rewriting(" WHERE sender_player_id = ",
                           " WHERE EXISTS (SELECT 1 FROM mail_recipients mr"
                           " WHERE mr.message_id = mail_message_id AND mr.delivery = 'delivered')"
                           " AND sender_player_id = ") as hits:
            assert await day(a) != await day(b)
        assert hits
    case(monkeypatch, body)


def test_the_same_body_rule_does_not_count_invites(monkeypatch):
    """Invites carry the same server text; a direct mail with that text
    afterwards opens no spam case, because the rule counts direct send
    receipts and an invite writes none. The sender sends one invite fewer
    than the rule's count, so the mail reaches the count only if the invites
    are in it. The mutant gives each invite a direct send receipt carrying
    its body's key (what an invite sent through the direct send path would
    write), and the same mail opens a case. Writing the invites' rows as
    direct mail is no mutant here: 415's trigger would give each a receipt,
    but that receipt carries no body key, so the rule counts none of them.
    The minute's rate counts invites and direct receipts together, so the
    mutant's sender stays under it only with fewer than half its ten.
    The control: the rule's count of direct mails with one body opens one."""
    async def body(env):
        async def cases(p):
            return await env.conn.fetchval(
                "SELECT COUNT(*) FROM moderation_cases WHERE kind = 'mail_spam' AND subject_player_id = $1",
                p.id)
        text_body = main._invite_mail_text("team", "invite")[1]
        n = main.MAIL_SPAM_SAME_BODY - 1
        assert 2 * n < main.MAIL_RATE_PER_MINUTE, (n, main.MAIL_RATE_PER_MINUTE)

        async def invites_then_mail(s, lid):
            for p in await env.players(n):
                await env.invite(s, p, "team", lid)
            d = await env.player()
            assert (await env.mail(s, [d], subject="Hi", body=text_body)).status == 200
        lid, (s,) = await env.lobby("team", 1)
        await invites_then_mail(s, lid)
        assert await cases(s) == 0
        real = main._mail_write_message

        async def with_direct_receipt(db, sender_id, *, kind, **kw):
            mid, fanned = await real(db, sender_id, kind=kind, **kw)
            if kind == "invite":
                await main._mail_write_receipt(
                    db, sender_id=sender_id, key=uuid.uuid4(), kind="direct", request_fp=bytes(32),
                    message_fp=main._mail_message_fp("send", kw["subject"], kw["body"]),
                    message_id=mid, recipients=int(fanned.rowcount),
                    body_key=main._mail_body_key(kw["body"]))
            return mid, fanned
        monkeypatch.setattr(main, "_mail_write_message", with_direct_receipt)
        lid2, (s2,) = await env.lobby("team", 1)
        await invites_then_mail(s2, lid2)
        assert await cases(s2) == 1, "the mutant's invites did not count"
        monkeypatch.setattr(main, "_mail_write_message", real)
        c = await env.player()
        for _ in range(main.MAIL_SPAM_SAME_BODY):
            d = await env.player()
            assert (await env.mail(c, [d], subject="Hi", body="The same body five times.")).status == 200
        assert await cases(c) == 1
    case(monkeypatch, body)


# -- a challenge commits all of its rows or none (section 11) ------------------

def test_a_challenge_commits_its_lobby_seat_invite_receipt_and_mail_together_or_none(monkeypatch):
    async def body(env):
        s, t = await env.players(2)
        k = key()
        ans = await env.send(s, t, "team", k=k)
        assert ans.status == 200 and "lobby_id" in ans.body, ans
        iid, lid = uuid.UUID(ans["invite_id"]), uuid.UUID(ans["lobby_id"])
        got = await env.conn.fetchrow(
            "SELECT (SELECT status FROM team_lobbies WHERE id = $1) AS lobby,"
            "       (SELECT host_player_id FROM team_lobbies WHERE id = $1) AS host,"
            "       (SELECT status FROM team_queue WHERE player_id = $2 AND series_id = $1) AS seat,"
            "       (SELECT kind FROM lobby_invites WHERE id = $3) AS invite,"
            "       (SELECT route FROM invite_receipts WHERE caller_player_id = $2"
            "          AND idempotency_key = CAST($4 AS uuid)) AS receipt,"
            "       (SELECT r.delivery FROM mail_recipients r JOIN lobby_invites i"
            "          ON i.mail_message_id = r.message_id WHERE i.id = $3) AS copy",
            lid, s.id, iid, k)
        assert dict(got) == {"lobby": "open", "host": s.id, "seat": "lobby", "invite": "challenge",
                             "receipt": "send", "copy": "delivered"}, dict(got)
        u, v = await env.players(2)
        snap = await env.snapshot()

        async def down(*_a, **_k):
            raise RuntimeError("relay down")
        monkeypatch.setattr(mail_discord, "queue_mail_relay", down)
        with pytest.raises(RuntimeError):
            await env.send(u, v, "team")
        assert await env.snapshot() == snap, "a failed challenge left rows"
        # the mutant: the challenge's lobby committed on its own
        real = main._invite_challenge_core

        async def split(mode, req, me, request, db):
            entry = await real(mode, req, me, request, db)
            await db.commit()
            return entry
        monkeypatch.setattr(main, "_invite_challenge_core", split)
        with pytest.raises(RuntimeError):
            await env.send(u, v, "team")
        assert await env.snapshot() != snap, "the split mutant left nothing behind"
    case(monkeypatch, body)


# -- revisions: every change bumps the invitee's; suppressed bumps none --------

def test_every_invite_change_bumps_its_invitees_revision_and_a_suppressed_one_none(monkeypatch):
    """A send, a decline, a cancel, the sweep's expiry, an accept and a
    departure's void each bump a delivered invitee's revision; a suppressed
    invitee's revision moves for none of them; deleting an invite's copy
    bumps the deleter's. Mutants: the bump's delivered condition widened to
    suppressed copies; the bump reaching no row, on a cancel."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        x = await env.player()
        y = await env.player(mail_from="nobody")
        moves = []

        async def step(label, fn):
            bx, by = await env.rev(x), await env.rev(y)
            out = await fn()
            moves.append((label, await env.rev(x) > bx, await env.rev(y) - by))
            return out
        ix = await step("send", lambda: env.invite(h, x, "team", lid))
        iy = await step("send suppressed", lambda: env.invite(h, y, "team", lid))
        await step("decline", lambda: env.decline(x, ix))
        await step("cancel suppressed", lambda: env.cancel(h, iy))
        ix = await step("send", lambda: env.invite(h, x, "team", lid))
        await step("cancel", lambda: env.cancel(h, ix))
        ix = await step("send", lambda: env.invite(h, x, "team", lid))
        await env.age(ix, expired_s=5)
        await step("sweep", env.sweep)
        ix = await step("send", lambda: env.invite(h, x, "team", lid))
        await step("accept", lambda: env.accept(x, ix))
        l2, (h2,) = await env.lobby("team", 1)
        iz = await step("send", lambda: env.invite(h2, x, "team", l2))
        iy2 = await step("send suppressed", lambda: env.invite(h2, y, "team", l2))
        await step("departure", lambda: env.leave("team", h2, l2))
        assert (await env.row(iz))["state"] == "void" and (await env.row(iy2))["state"] == "void"
        assert all(bumped for label, bumped, _dy in moves if "suppressed" not in label), moves
        assert all(dy == 0 for _l, _b, dy in moves), moves
        mid = await env.mail_of(iz)
        before = await env.rev(x)
        assert (await env.call(lambda db: main.mail_delete(str(mid), Req(x.sid), db))).status == 200
        assert await env.rev(x) > before, "deleting an invite's copy did not bump the deleter's revision"
        # mutants
        l3, (h3,) = await env.lobby("team", 1)
        with env.rewriting("r.delivery = 'delivered'", "r.delivery IN ('delivered', 'suppressed')") as hits:
            by = await env.rev(y)
            await env.invite(h3, y, "team", l3)
            assert await env.rev(y) > by, "the widened bump left the suppressed revision alone"
        assert hits
        # A send's envelope also bumps, through migration 300's trigger on
        # mail_recipients (the api keeps its own bump as well, as 300 says),
        # so the mutant of the api's bump is judged on a change that writes
        # no envelope: the sender's cancel.
        z = await env.player()
        iz3 = await env.invite(h3, z, "team", l3)
        with env.rewriting("WHERE r.message_id = ANY(", "WHERE FALSE AND r.message_id = ANY(") as hits:
            bz = await env.rev(z)
            assert (await env.cancel(h3, iz3)).status == 200
            assert await env.rev(z) == bz, "the bump mutant still bumped"
        assert hits
    case(monkeypatch, body)


def test_two_transactions_bumping_two_invitees_in_opposite_orders_do_not_deadlock(monkeypatch):
    """The bump takes its revision rows in ascending recipient order in one
    statement, so two transactions over the same two invitees wait, never
    deadlock. A third session holds the lower row; both transactions queue
    behind it; on release both finish. The mutant runs one transaction's
    bump in descending order: it takes the upper row first, and the release
    ends in a deadlock."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        a, b = await env.players(2)
        mids = [await env.mail_of(await env.invite(h, p, "team", lid)) for p in (a, b)]
        lo, hi = sorted([a.id, b.id], key=str)
        stmt = main._INVITE_REV_BUMP_SQL.replace(":mids", "$1")
        assert stmt.count("ORDER BY v.recipient_id FOR NO KEY UPDATE") == 1

        async def blocked(pid):
            for _ in range(100):
                if await env.conn.fetchval("SELECT cardinality(pg_blocking_pids($1)) > 0", pid):
                    return True
                await asyncio.sleep(0.05)
            return False

        async def race(second):
            """Both bumps queued behind `hold`'s lock on the lower row, the
            hold released; each transaction ends as soon as its bump does
            (a bump that waits on the other's row waits on its commit).
            Returns the errors' names."""
            hold, t1, t2 = await env.side(), await env.side(), await env.side()
            await hold.execute("BEGIN")
            await hold.execute("SELECT 1 FROM mail_inbox_rev WHERE recipient_id = $1 FOR UPDATE", lo)
            pending = {}
            for t, sql in ((t1, stmt), (t2, second)):
                await t.execute("BEGIN")
                pending[asyncio.ensure_future(t.execute(sql, mids))] = t
                assert await blocked(t.get_server_pid()), "a bump did not queue"
            await hold.execute("ROLLBACK")
            errs = []
            while pending:
                done, _rest = await asyncio.wait(list(pending), timeout=20,
                                                 return_when=asyncio.FIRST_COMPLETED)
                assert done, "a bump never finished"
                for fut in done:
                    t = pending.pop(fut)
                    if fut.exception() is not None:
                        errs.append(type(fut.exception()).__name__)
                    await t.execute("ROLLBACK")
            return errs
        assert await race(stmt) == []
        mutant = stmt.replace("ORDER BY v.recipient_id", "ORDER BY v.recipient_id DESC")
        assert "DeadlockDetectedError" in await race(mutant)
    case(monkeypatch, body)


# -- deviation (a): a send ends only its own invitee's stale invite; the cap
#    counts unexpired rows ------------------------------------------------------

def test_a_send_ends_only_its_invitees_stale_invite_and_the_cap_counts_unexpired_rows(monkeypatch):
    """A send to x ends x's pending invite that is past its expiry (so the
    unique pending index admits the new one) and leaves another invitee's
    stale row to the sweep; eight stale rows, the 2v2 cap, refuse no send.
    Mutants: the expiry step reaching every stale row of the lobby; the cap
    counting stale rows."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        x, y = await env.players(2)
        ix, iy = await env.invite(h, x, "team", lid), await env.invite(h, y, "team", lid)
        for i in (ix, iy):
            await env.age(i, expired_s=5)
        ix2 = await env.invite(h, x, "team", lid)
        assert ((await env.row(ix))["state"], (await env.row(iy))["state"]) == ("expired", "pending")
        for p in await env.players(7):
            await env.age(await env.invite(h, p, "team", lid), expired_s=5)
        stale = await env.conn.fetchval(
            "SELECT COUNT(*) FROM lobby_invites WHERE lobby_id = $1 AND state = 'pending'"
            "   AND expires_at <= NOW()", lid)
        assert stale == 2 * main._invite_capacity("team") == 8, stale
        assert (await env.send(h, await env.player(), "team", lid)).status == 200
        # mutant 1: the cap counts stale rows (eight of them are pending)
        # (the reading stays bound, so the statement keeps its parameter)
        with env.rewriting(re.compile(r"AND expires_at > CAST\((\$\d+|%s|%\(\w+\)s|:\w+) AS timestamptz\)"),
                           r"AND CAST(\1 AS timestamptz) IS NOT NULL",
                           where="SELECT id, invitee_player_id FROM lobby_invites") as hits:
            ans = await env.send(h, await env.player(), "team", lid)
        assert hits
        assert ans.status == 409 and ans.body == "invites_full", ans
        # mutant 2: the send's expiry step reaches every stale row of the lobby
        q = await env.player()
        iq = await env.invite(h, q, "team", lid)
        await env.age(iq, expired_s=5)
        assert (await env.row(iy))["state"] == "pending"
        with env.rewriting(inv.placeholder_rx("invitee_player_id"), r"(invitee_player_id = \1 OR TRUE)",
                           where="SET state = 'expired', ended_at = CAST(") as hits:
            assert (await env.send(h, q, "team", lid)).status == 200
        assert hits
        assert (await env.row(iy))["state"] == "expired", "the expiry mutant left another invitee's row"
        assert ix2
    case(monkeypatch, body)


# -- deviation (e): invite rows only for clients at or above the floor ---------

def test_invite_rows_reach_only_clients_at_or_above_the_floor(monkeypatch):
    """A lobby member's state carries the lobby's invites, and an invitee's
    inbox, unread count and pending list carry the invite row, only for a
    client at or above INVITE_FLOOR_VERSION; an older client sees none of
    them (its pending list is an empty page). The mutant calls every client
    current."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        g = await env.player()
        iid = await env.invite(h, g, "team", lid)
        mid = await env.mail_of(iid)

        async def views(version):
            st = await env.call(lambda db: main._lobby_state_impl("team", h.sid, Req(h.sid, version), db))
            ib = await env.call(lambda db: main.mail_inbox(Req(g.sid, version), cursor="",
                                                           limit=main.MAIL_PAGE_MAX, db=db))
            ms = await env.call(lambda db: main.mail_status(Req(g.sid, version), db))
            pd = await env.pending(g, version)
            assert st.status == ib.status == ms.status == pd.status == 200, (st, ib, ms, pd)
            listed = [m["id"] for m in ib["messages"]]
            pending = [i["invite_id"] for i in pd["invites"]]
            assert pd["next_cursor"] is None, pd
            return ("invites" in st.body and bool(st["invites"]), str(mid) in listed, ms["unread"],
                    pending == [str(iid)])
        assert await views(inv.FLOOR) == (True, True, 1, True)
        assert await views(inv.BELOW) == (False, False, 0, False)
        monkeypatch.setattr(main, "_invite_ok_for", lambda request: True)
        assert await views(inv.BELOW) == (True, True, 1, True), "the floor mutant changed nothing"
    case(monkeypatch, body)


# -- FFA's lobby list rides the poll answer, read after the inner poll -----------

def test_an_ffa_lobby_poll_carries_its_invites_read_after_the_inner_polls_commit(monkeypatch):
    """An open FFA lobby's members get the lobby's invites on their poll
    answer, as the 2v2 and 1v2 lobby state carries them: ffa_queue_poll
    attaches them (_ffa_attach_invites) after _ffa_queue_poll_inner has
    answered and committed, so the inner poll's own answer has none.
    can_cancel is true for the invite's sender and for the lobby's host, false
    for another member; a client below the floor gets no list; a failed list
    read loses only the list (the poll still answers its lobby). Mutants: the
    wrapper skips the attach (no member gets a list); the attach passes no
    host (the host loses its cancel); every client called current (a client
    below the floor gets the list)."""
    async def body(env):
        lid, (h, m, k) = await env.lobby("ffa", 3)
        x = await env.player()
        iid = await env.invite(m, x, "ffa", lid)
        await env.fresh("ffa", lid)
        none = {"h": None, "m": None, "k": None}

        async def views(version=inv.FLOOR):
            got = {}
            for tag, p in (("h", h), ("m", m), ("k", k)):
                ans = await env.call(lambda db: main.ffa_queue_poll(p.sid, Req(p.sid, version), db=db))
                assert ans.status == 200 and ans["status"] == "lobby" and ans["lobby_id"] == str(lid), ans
                got[tag] = ([(i["invite_id"], i["state"], i["can_cancel"]) for i in ans["invites"]]
                            if "invites" in ans.body else None)
            return got

        want = {"h": [(str(iid), "pending", True)], "m": [(str(iid), "pending", True)],
                "k": [(str(iid), "pending", False)]}
        assert await views() == want
        assert await views(inv.BELOW) == none
        # the inner poll alone (the a1 site, as main has it) carries no list
        inner = await env.call(lambda db: main._ffa_queue_poll_inner(h.sid, Req(h.sid), db))
        assert inner.status == 200 and inner["status"] == "lobby" and "invites" not in inner.body, inner

        # a failed list read: the poll still answers its lobby, without the list
        with env.rewriting("FROM lobby_invites i JOIN players p",
                           "FROM lobby_invites_absent i JOIN players p") as hits:
            assert await views() == none
        assert hits, "the planted failure reached no statement"
        assert await views() == want

        with monkeypatch.context() as mp:
            async def _skip(db, request, steam_id, out):
                return out
            mp.setattr(main, "_ffa_attach_invites", _skip)
            assert await views() == none, "the skip mutant changed nothing"
        with monkeypatch.context() as mp:
            real = main._invite_lobby_list

            async def _no_host(db, mode, lobby_id, me_id, host_id):
                return await real(db, mode, lobby_id, me_id, None)
            mp.setattr(main, "_invite_lobby_list", _no_host)
            got = await views()
        assert got == dict(want, h=[(str(iid), "pending", False)]), ("the no-host mutant", got)
        with monkeypatch.context() as mp:
            mp.setattr(main, "_invite_ok_for", lambda request: True)
            assert await views(inv.BELOW) == want, "the floor mutant changed nothing"
    case(monkeypatch, body)


# -- retention: a row and its receipts go seven days after expiry ---------------

def test_an_invite_and_its_receipts_go_seven_days_after_its_expiry_whatever_its_end(monkeypatch):
    """Delivered, suppressed, declined and expired invites alike: kept six
    days after expires_at, gone with their receipts at eight. A suppressed
    invite is never listed for its invitee and never answerable by them: its
    accept and decline answer as for an unknown id. The mutant keeps a
    declined row."""
    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        d, c, e = await env.players(3)
        u = await env.player(mail_from="nobody")
        ids = {"delivered": await env.invite(h, d, "team", lid),
               "suppressed": await env.invite(h, u, "team", lid),
               "declined": await env.invite(h, c, "team", lid),
               "expired": await env.invite(h, e, "team", lid)}
        assert (await env.decline(c, ids["declined"])).status == 200
        await env.age(ids["expired"], expired_s=5)
        await env.sweep()
        assert (await env.row(ids["expired"]))["state"] == "expired"
        # the suppressed invite, from its invitee's side
        assert (await env.pending(u))["invites"] == []
        unknown = uuid.uuid4()
        for verb in ("accept", "decline"):
            got = await getattr(env, verb)(u, ids["suppressed"])
            want = await getattr(env, verb)(u, unknown)
            assert got == want and got.status == 404, (verb, got, want)

        async def receipts():
            return await env.conn.fetchval(
                "SELECT COUNT(*) FROM invite_receipts WHERE invite_id = ANY($1::uuid[])", list(ids.values()))
        assert await receipts() == 5                       # four sends and the decline
        for i in ids.values():
            await env.age(i, kept_days=main.INVITE_KEEP_DAYS - 1)
        await env.retention()
        assert all([await env.row(i) is not None for i in ids.values()])
        for i in ids.values():
            await env.age(i, kept_days=main.INVITE_KEEP_DAYS + 1)
        with env.rewriting("WHERE expires_at < (SELECT clock_timestamp())",
                           "WHERE state <> 'declined' AND expires_at < (SELECT clock_timestamp())",
                           where="DELETE FROM lobby_invites") as hits:
            await env.retention()
        assert hits
        assert await env.row(ids["declined"]) is not None, "the retention mutant deleted the declined row"
        await env.retention()
        assert [await env.row(i) for i in ids.values()] == [None] * 4
        assert await receipts() == 0
    case(monkeypatch, body)


# -- a mail, a reply and a broadcast keyed with an invite's id (section 11) ----

def test_mail_keyed_with_an_invites_id_is_a_new_message_whatever_the_invite(monkeypatch):
    """The invite's sender sends a direct mail, a reply or a broadcast, each
    with an invite's id as its key, for a delivered, a suppressed and a
    suppressed-then-purged invite: each is a new message, and the answers are
    byte for byte the same across the three but for the new message's id.
    One sender per verb: a direct mail and a reply share their sender's key
    space, so a reply keyed like that sender's earlier mail is refused as a
    reused key (409 idempotency_key_reused), whatever any invite does.
    The mutant keys each invite's mail row with the invite's id."""
    async def scenario(env, h, verb):
        lid = await env.create("team", h)
        d = await env.player()
        u1, u2 = await env.players(2, mail_from="nobody")
        r = await env.player()
        await env.conn.execute("INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, NOW())"
                               " ON CONFLICT DO NOTHING", h.sid)
        ids = [await env.invite(h, d, "team", lid), await env.invite(h, u1, "team", lid),
               await env.invite(h, u2, "team", lid)]
        await env.age(ids[2], kept_days=main.INVITE_KEEP_DAYS + 1, mail_days=main.MAIL_RETENTION_DAYS + 1)
        await env.retention()
        first = await env.mail(r, [h], body="A thread to answer.")
        assert first.status == 200, first
        out = []
        for i in ids:
            k = str(i)
            if verb == "mail":
                coro = lambda db, k=k: main.mail_send(main._MailSendReq(
                    to=[r.sid], subject="Hi", body="Keyed with an id.", idempotency_key=k), Req(h.sid), db)
            elif verb == "reply":
                coro = lambda db, k=k: main.mail_reply(first["id"], main._MailReplyReq(
                    body="A keyed reply.", idempotency_key=k), Req(h.sid), db)
            else:
                coro = lambda db, k=k: main.admin_mail_broadcast(main._AdminMailBroadcastReq(
                    admin_steam_id=h.sid, subject="News", body="A keyed notice.", idempotency_key=k), db)
            try:
                ans = await env.call(coro)
            except Exception as exc:                       # the mutant's collision
                ans = Answer(500, type(exc).__name__)
            new = ans.get("id") if ans.status == 200 else None
            if new is not None:
                row = await env.conn.fetchrow(
                    "SELECT kind, CAST(idempotency_key AS text) AS k FROM mail_messages WHERE id = $1",
                    uuid.UUID(new))
                assert row is not None and row["k"] == k, (verb, row)
            out.append(ans.wire.replace(new, "<id>") if new else ans.wire)
        return out
    monkeypatch.setattr(main, "_verify_admin_hmac", lambda *a, **k: True)
    verbs = ("mail", "reply", "broadcast")

    async def body(env):
        for verb in verbs:
            answers = await scenario(env, await env.player(), verb)
            assert len(set(answers)) == 1 and json.loads(answers[0])[0] == 200, (verb, answers)
        real = main._mail_write_message

        async def keyed_by_invite(db, sender_id, *, kind, idempotency_key, **kw):
            if kind == "invite":
                idempotency_key = (await db.execute(text(
                    "SELECT id FROM lobby_invites WHERE sender_player_id = :sid AND mail_message_id IS NULL"
                    " ORDER BY created_at DESC LIMIT 1"), {"sid": sender_id})).scalar()
            return await real(db, sender_id, kind=kind, idempotency_key=idempotency_key, **kw)
        monkeypatch.setattr(main, "_mail_write_message", keyed_by_invite)
        bad = {}
        for verb in verbs:
            bad[verb] = await scenario(env, await env.player(), verb)
        assert any(len(set(a)) > 1 for a in bad.values()), ("the key mutant changed no answer", bad)
    case(monkeypatch, body)


# -- section 11: two accepts for the last seat; the join's own identity and
#    service gates ---------------------------------------------------------------

def _answers(got):
    """gather(..., return_exceptions=True) as Answers: an exception that is not
    an HTTP answer becomes a 500 named by its type."""
    return [g if isinstance(g, Answer) else Answer(500, type(g).__name__) for g in got]


@pytest.mark.parametrize("mode", inv.MODES)
def test_two_accepts_for_the_last_seat_seat_one_and_the_other_gets_the_joins_full_answer(monkeypatch, mode):
    """A lobby one seat short of full and two invitees accepting at once: the
    join's lobby row lock orders them, so one is seated, the other is answered
    byte for byte as the mode's join answers a full lobby, and its invite stays
    pending. The accepts are made to meet inside the join: each waits up to
    1.5 s for the other right after the lobby row lock, so with the lock the
    second arrives only after the first committed. The mutant drops the join's
    FOR UPDATE for the two accepts alone: both meet, both count the same
    members, and both are seated."""
    cap = main._invite_capacity(mode)
    real_lock = main._InviteJoinHook.lock

    async def race(env, mutant):
        lid, ps = await env.lobby(mode, cap - 1)
        x, y = await env.players(2)
        ix, iy = await env.invite(ps[0], x, mode, lid), await env.invite(ps[0], y, mode, lid)
        await env.fresh(mode, lid)
        arrived, met = [], asyncio.Event()

        async def meeting(self, db):
            arrived.append(self.invite_id)
            if len(arrived) >= 2:
                met.set()
            try:
                await asyncio.wait_for(met.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
            return await real_lock(self, db)

        async def both():
            return await asyncio.wait_for(asyncio.gather(env.accept(x, ix), env.accept(y, iy),
                                                         return_exceptions=True), timeout=60)
        hits = []
        monkeypatch.setattr(main._InviteJoinHook, "lock", meeting)
        try:
            if mutant:
                with env.rewriting(" FOR UPDATE", "", where="password_hash, kicked_steam_ids") as hits:
                    got = await both()
            else:
                got = await both()
        finally:
            monkeypatch.setattr(main._InviteJoinHook, "lock", real_lock)
        assert len(arrived) == 2, ("an accept never reached the join's invite step", arrived)
        return lid, [ix, iy], _answers(got), list(hits)

    async def body(env):
        lid, invs, got, _hits = await race(env, False)
        assert sorted(a.status for a in got) == [200, 409], got
        win, lose = (0, 1) if got[0].status == 200 else (1, 0)
        assert len(await env.members(mode, lid)) == cap
        assert (await env.row(invs[win]))["state"] == "accepted"
        assert (await env.row(invs[lose]))["state"] == "pending"
        z = await env.player()
        full = await env.join(mode, z, lid)
        assert full.status == 409 and got[lose].wire == full.wire, ("not the join's own full answer",
                                                                    got[lose], full)
        # the mutant: the join's lobby row lock dropped for the two accepts
        lid2, _invs, bad, hits = await race(env, True)
        assert len(hits) >= 2, hits
        n = len(await env.members(mode, lid2))
        assert n > cap or [a.status for a in bad] == [200, 200], ("the lock mutant changed nothing", bad, n)
    case(monkeypatch, body)


@pytest.mark.parametrize("why", ["banned", "deleted", "service"])
def test_a_banned_deleted_or_service_invitee_gets_the_joins_own_refusal(monkeypatch, why):
    """An invitee banned, carrying a deleted account's tombstone, or made a
    service account after the send is refused by the join's own identity or
    service gate: the accept's answer is byte for byte the mode's join answer
    for the same account, the invite stays pending and nothing is written. The
    invite path keeps no list of its own: with that gate taken out (the
    mutant), the same accept seats the invitee."""
    gate = {"banned": "_enrollment_identity_gate", "deleted": "_enrollment_identity_gate",
            "service": "_assert_no_service_subject"}[why]

    async def body(env):
        lid, (h,) = await env.lobby("team", 1)
        x = await env.player()
        iid = await env.invite(h, x, "team", lid)
        if why == "banned":
            await env.conn.execute("INSERT INTO admin_users (steam_id, granted_at) VALUES ($1, NOW())"
                                   " ON CONFLICT DO NOTHING", h.sid)
            await env.conn.execute("INSERT INTO player_bans (steam_id, reason, banned_by_steam_id)"
                                   " VALUES ($1, 'test', $2)", x.sid, h.sid)
        elif why == "deleted":
            monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "inv-case-secret")
            await env.conn.execute("INSERT INTO deleted_steam_ids (steam_id_hash) VALUES ($1)",
                                   main._hash_steam_id(x.sid))
        else:
            monkeypatch.setattr(main, "SPECTATE_BROADCAST_STEAM_IDS",
                                set(main.SPECTATE_BROADCAST_STEAM_IDS) | {x.sid})
        want = await env.join("team", x, lid)
        assert want.status in (403, 409, 410), want
        before = await env.snapshot()
        got = await env.accept(x, iid)
        assert got.wire == want.wire, (why, got, want)
        assert await env.snapshot() == before, "a refused accept wrote rows"
        assert (await env.row(iid))["state"] == "pending"

        # the mutant: the join's gate taken out
        async def no_gate(*a, **k):
            return None
        monkeypatch.setattr(main, gate, no_gate)
        bad = await env.accept(x, iid)
        assert bad.status == 200 and x.id in await env.members("team", lid), (
            "the gate mutant left a refusal: the invite path checks the account itself", why, bad)
        assert (await env.row(iid))["state"] == "accepted"
    case(monkeypatch, body)


# -- design change (k): lobby_closed before not_in_lobby ----------------------------

def test_a_send_to_a_lobby_no_longer_open_answers_lobby_closed_whoever_sends(monkeypatch):
    """The send's lobby gate checks that the lobby is open, under its row lock,
    before it checks that the caller is a live member: a member of a lobby
    that is no longer open and a caller who never was one are both answered
    409 lobby_closed and nothing is written, while a caller who is not a
    member of an open lobby is answered 403 not_in_lobby. The mutant makes
    the gate read the lobby as open: the outsider's answer becomes
    not_in_lobby."""
    async def body(env):
        for mode in inv.MODES:
            lid, (h,) = await env.lobby(mode, 1)
            outsider, x = await env.players(2)
            ans = await env.send(outsider, x, mode, lid)
            assert ans.status == 403 and ans.body == "not_in_lobby", (mode, ans)
            await env.conn.execute("UPDATE %s SET status = 'canceled' WHERE id = $1"
                                   % inv.LOBBY_TABLE[mode], lid)
            for who in (h, outsider):
                before = await env.snapshot()
                ans = await env.send(who, x, mode, lid)
                assert ans.status == 409 and ans.body == "lobby_closed", (mode, who, ans)
                assert await env.snapshot() == before, (mode, "a refused send wrote rows")
            # the mutant: the gate's lobby read answers 'open'
            with env.rewriting("SELECT id, status, kicked_steam_ids FROM",
                               "SELECT id, CAST('open' AS text) AS status, kicked_steam_ids FROM",
                               where=" FOR UPDATE") as hits:
                bad = await env.send(outsider, x, mode, lid)
            assert hits, mode
            assert bad.status == 403 and bad.body == "not_in_lobby", (mode, "the mutant changed nothing", bad)
    case(monkeypatch, body)
