"""Mail send receipts, reply all and the sender's own view (migration 404's
change), executed against the in-memory fake of test_mail.py.

What each endpoint answers after the change:

- POST /mail, POST /mail/{id}/reply and the admin broadcast answer a
  repeated idempotency_key from that key's send receipt alone: the first
  answer, whatever the message's delivery and whether the janitor has
  purged the message row since. A request that differs from the one the
  receipt was written for (its digest, main._mail_request_fp) is refused,
  409 idempotency_key_reused, and writes nothing. A receipt with no request
  digest (written by migration 404's backfill or by its trigger) is compared
  on the digest of the text its message stored (message_fp,
  main._mail_message_fp): the same text replays, another body (or another
  subject on a send or a broadcast) is refused the same way.
- The Discord reply route's target is resolved by the core after the
  repeated-key check, so a retry of a reply that was sent replays even when
  its relay code no longer resolves.
- Reply all addresses the original's sender and every addressee of the
  original, delivered or suppressed alike, so the replier's answer,
  recipient cap and Sent list are the same whatever the other players'
  delivery; an addressee whose copy of the original was suppressed gets a
  suppressed copy of the reply.
- Sent, and the sender's branch of the detail read and of the reply's
  original read, show a message until MAIL_RETENTION_DAYS after it was
  sent (or until its sender deletes it), whatever its delivery. Each reads
  the message and its envelopes (the reply-all list, the addressees) in ONE
  statement, with the clock read inside that statement (clock_timestamp()
  in a MATERIALIZED CTE), so its answer is the same whether or not the
  janitor's purge has taken the message.
- The spam check counts the sender's send receipts (same body by the
  receipt's body key, bulk by its envelope count), so a count is the same
  whatever the copies' delivery and whether the purge has run. The purge
  has no age floor.
- DELETE /mail/{id} answers 200 {"status": "deleted", "id"} for every
  well-formed id.
- The janitor deletes a receipt MAIL_RETENTION_DAYS after its send,
  whatever the state of the message it names, and moves a message still
  kept to a reserved key drawn at random, so the key can be sent again
  under 297's UNIQUE (sender_id, idempotency_key), which migration 404
  keeps.
- Every route that takes an idempotency key refuses a reserved one (version
  digit 0), 400 idempotency_key_invalid, before the sender lock and before
  any mail table is read (main._mail_parse_key).

Every test runs a control (the code as written) and at least one mutant
(the code with one rule taken out: the production SQL rewritten on its way
to the fake, a statement not run, a function recompiled from its own source
with one line changed, or the receipt removed from the data) and asserts
that the mutant changes the answer the control pins. A mutant whose anchor
is not found fails the test instead of passing it.
"""

import hashlib
import inspect
import re
import textwrap
import uuid
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

import mail_discord
import main
import test_mail as tm
from test_mail import A_SID, ADMIN_SID, B_SID, C_SID, D_SID, NOW, _CLOCK_CTE, _SENDER_CLOCK

REUSED = (409, "idempotency_key_reused")
NOT_FOUND = (404, "not_found")
OLD = NOW - timedelta(days=main.MAIL_RETENTION_DAYS + 1)
YOUNG = NOW - timedelta(days=main.MAIL_RETENTION_DAYS - 1)
# The reply core's join of the original's envelopes (migration 404's change)
_REPLY_ALL_JOIN = "ON e.message_id = o.id AND CAST(:reply_all AS boolean) AND o.kind <> 'system_broadcast'"
# Anchors of the three sender reads, present in the one-statement shape and
# in the previous build's first statement alike
_ORIG_READ = "SELECT m.id, m.sender_id, m.kind, m.thread_id, m.subject"
_SENT_READ = "WHERE m.sender_id = :me AND m.deleted_by_sender_at IS NULL"
_DETAIL_READ = "LEFT JOIN mail_recipients r ON r.message_id = m.id AND r.recipient_id = :me"
_COMPARE = "if stored is not None and bytes(stored) != request_fp:"
_LEGACY_COMPARE = ('if stored is None and (message_fp is None or bytes(prior["message_fp"])'
                   ' != message_fp):')
_REPLY_FP = '_mail_request_fp("reply", body=body, all=bool(reply_all))'
_REPLY_MFP = '_mail_request_message_fp("reply", subject="", body=body)'

# The functions the mutants are recompiled from, taken before any test can
# replace one on the module.
_REAL = {name: getattr(main, name) for name in (
    "_mail_prior_send", "_mail_reply_core", "mail_send", "admin_mail_broadcast", "mail_delete",
    "_mail_write_receipt", "_mail_request_fp", "_mail_request_message_fp",
    "_mail_spam_check", "_mail_finish_send", "mail_sent", "mail_detail")}
_REAL_SWEEP = main._MAIL_RECEIPT_SWEEP_SQL


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch):
    monkeypatch.setattr(main, "_utc_now", lambda: NOW)


# ── helpers ───────────────────────────────────────────────────────────────

def _key():
    return str(uuid.uuid4())


def _reserved(seed):
    """A key in the reserved space (version digit, the 13th hex digit, 0;
    main._mail_parse_key): the md5 of `seed` with that digit set to 0, the
    value the sweep and the trigger DERIVED before migration 404's change
    drew them at random."""
    h = hashlib.md5(seed.encode("ascii")).hexdigest()
    return UUID(h[:12] + "0" + h[13:])


def _drawn_reserved():
    """A reserved key as the sweep and the trigger now draw one."""
    h = uuid.uuid4().hex
    return UUID(h[:12] + "0" + h[13:])


def _outcome(fn, *a, **kw):
    """The call's answer, or (status, detail) for a refusal."""
    try:
        return fn(*a, **kw)
    except HTTPException as e:
        return (e.status_code, e.detail)


def _outcome_or_23505(fn, *a, **kw):
    """_outcome, and "23505" when the fake's unique constraint refuses the
    statement (test_mail.UniqueViolation, PostgreSQL's 23505)."""
    try:
        return _outcome(fn, *a, **kw)
    except tm.UniqueViolation:
        return "23505"


def _shape(ans):
    """An answer reduced to what may not differ between two worlds: the keys
    of a 200 body, or (status, detail) for a refusal."""
    return sorted(ans) if isinstance(ans, dict) else ans


def _reply(db, mid, body="Sounds good", all_=False, key=None, token="tokB"):
    req = main._MailReplyReq(body=body, all=all_, idempotency_key=key or _key())
    return tm._run(main.mail_reply(str(mid), req, tm._req(token), db))


def _sent(db, token):
    return tm._run(main.mail_sent(tm._req(token), "", 25, db))["messages"]


def _detail(db, mid, token):
    return tm._run(main.mail_detail(str(mid), tm._req(token), db))


def _directs(db, pid):
    return [m for m in db.messages.values() if m["sender_id"] == pid and m["kind"] == "direct"]


def _broadcasts(db):
    return [m for m in db.messages.values() if m["kind"] == "system_broadcast"]


def _purge(db, mid):
    """The janitor's purge of one message: the row and its envelopes go.
    mail_send_receipts has no foreign key, so the receipt stays."""
    mid = UUID(str(mid))
    db.messages.pop(mid)
    for k in [k for k in db.recipients if k[0] == mid]:
        db.recipients.pop(k)


def _rewrite_sql(db, old, new=""):
    """Mutant: every statement containing `old` reaches the fake with it
    replaced by `new`, as if the production text had been edited. Returns
    the statements it rewrote, so a test can prove the mutant applied."""
    real, hits = db.execute, []

    async def execute(statement, params=None):
        sql = str(statement)
        if isinstance(statement, TextClause) and old in sql:
            hits.append(sql)
            statement = text(sql.replace(old, new))
        return await real(statement, params)
    db.execute = execute
    return hits


def _skip_sql(db, anchor):
    """Mutant: statements containing `anchor` are not run at all."""
    real, hits = db.execute, []

    async def execute(statement, params=None):
        if anchor in str(statement):
            hits.append(str(statement))
            return tm._Res([])
        return await real(statement, params)
    db.execute = execute
    return hits


def _recompiled(name, old, new):
    """Mutant: main.<name> recompiled from its own source with `old`
    replaced by `new`, in a copy of main's namespace. Route decorators are
    dropped, so nothing is registered on the app."""
    src = textwrap.dedent(inspect.getsource(_REAL[name]))
    assert src.count(old) == 1, f"mutant anchor occurs {src.count(old)} times in {name}: {old!r}"
    lines = src.replace(old, new).splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if ln.startswith(("def ", "async def ")))
    ns = dict(vars(main))
    exec(compile("".join(lines[start:]), f"<mutant of {name}>", "exec"), ns)
    return ns[name]


def _spliced(name, cuts, extra=None):
    """Mutant: main.<name> recompiled from its own source with each
    (start, end, new) cut applied in turn -- the text from `start` through
    `end` (each found exactly once) replaced by `new` -- in a copy of main's
    namespace updated with `extra`. Route decorators are dropped."""
    src = textwrap.dedent(inspect.getsource(_REAL[name]))
    for start, end, new in cuts:
        assert src.count(start) == 1, f"cut start occurs {src.count(start)} times in {name}: {start!r}"
        assert src.count(end) == 1, f"cut end occurs {src.count(end)} times in {name}: {end!r}"
        i = src.index(start)
        j = src.index(end, i) + len(end)
        src = src[:i] + new + src[j:]
    lines = src.splitlines(keepends=True)
    first = next(i for i, ln in enumerate(lines) if ln.startswith(("def ", "async def ")))
    ns = dict(vars(main))
    ns.update(extra or {})
    exec(compile("".join(lines[first:]), f"<mutant of {name}>", "exec"), ns)
    return ns[name]


def _after_sql(db, anchor, action):
    """Runs `action(db)` once, right after the first statement containing
    `anchor` has been answered: a commit (the janitor's purge) landing
    between that statement and the request's next one. Returns the
    statements it followed, so a test can prove it ran."""
    real, hits = db.execute, []

    async def execute(statement, params=None):
        res = await real(statement, params)
        if not hits and anchor in str(statement):
            hits.append(str(statement))
            action(db)
        return res
    db.execute = execute
    return hits


def _mail_reads(db):
    """The statements so far that read mail_messages or mail_recipients and
    write nothing."""
    return [s for s in db.statements if ("mail_messages" in s or "mail_recipients" in s)
            and not any(w in s for w in ("INSERT INTO", "UPDATE ", "DELETE FROM"))]


async def _no_receipt(db, **kw):
    return None


# ── the digest ────────────────────────────────────────────────────────────

def test_the_digest_is_sha256_of_sorted_ascii_json(monkeypatch):
    fp = main._mail_request_fp
    a = fp("send", to=[B_SID], cc=[], subject="Plan", body="Café \U0001F600")
    assert isinstance(a, bytes) and len(a) == 32
    assert a == fp("send", body="Café \U0001F600", subject="Plan", cc=[], to=[B_SID])   # field order
    assert a != fp("reply", to=[B_SID], cc=[], subject="Plan", body="Café \U0001F600")  # the route
    # mutant: keys not sorted -> the same request in another field order digests differently
    monkeypatch.setattr(main, "_mail_request_fp", _recompiled(
        "_mail_request_fp", "sort_keys=True, ", ""))
    fp = main._mail_request_fp
    assert fp("send", to=[B_SID], body="x") != fp("send", body="x", to=[B_SID])


_SEND_FIELDS = ("to", "cc", "subject", "body")
# The fields each route's digest covers, and the model fields no digest
# covers: the key itself, and the broadcast's admin fields (the admin is the
# sender the receipt is keyed by, the signature authenticates the request,
# and the actor must equal the admin). The per-field tests below show each
# listed field reaching its route's digest.
_DIGESTED = {"_MailSendReq": set(_SEND_FIELDS), "_MailReplyReq": {"body", "all"},
             "_AdminMailBroadcastReq": {"subject", "body"}}
_NOT_DIGESTED = {"idempotency_key", "admin_steam_id", "hmac_signature", "actor_steam_id"}


def test_every_request_field_is_in_its_routes_digest():
    """A field added to a mail request model later fails here until its
    route's digest takes it (or it joins _NOT_DIGESTED with a reason)."""
    for name, fields in _DIGESTED.items():
        assert set(getattr(main, name).model_fields) - _NOT_DIGESTED == fields, name
    # negative control: a model grown by one field no longer matches its set
    grown = type("_Grown", (main._MailSendReq,), {"__annotations__": {"via": str}, "via": ""})
    assert set(grown.model_fields) - _NOT_DIGESTED == _DIGESTED["_MailSendReq"] | {"via"}


# ── POST /mail ────────────────────────────────────────────────────────────

_SEND_FIRST = dict(to=[B_SID], cc=[C_SID], subject="Plan", body="Meet at eight.")
_SEND_CHANGED = (dict(_SEND_FIRST, to=[D_SID]), dict(_SEND_FIRST, cc=[D_SID]),
                 dict(_SEND_FIRST, subject="Plans"), dict(_SEND_FIRST, body="Meet at nine."))


def _send_reuse():
    """One send, then its key with each field changed in turn, then
    unchanged. Returns (first, the four changed answers, the unchanged
    answer, A's direct messages)."""
    db, ids = tm._world()
    key = _key()
    first = tm._send(db, key=key, **_SEND_FIRST)
    changed = [_outcome(tm._send, db, key=key, **kw) for kw in _SEND_CHANGED]
    same = tm._send(db, key=key, **_SEND_FIRST)
    return first, changed, same, _directs(db, ids[A_SID])


def test_a_send_key_answers_only_the_request_it_was_written_for(monkeypatch):
    first, changed, same, sent = _send_reuse()
    assert changed == [REUSED] * 4                          # to, cc, subject, body: each refused
    assert same == first and len(sent) == 1                 # the unchanged retry replays; nothing else written
    # mutant: the replay ignores the stored digest -> every changed request
    # is answered as the first one was
    monkeypatch.setattr(main, "_mail_prior_send", _recompiled("_mail_prior_send", _COMPARE, "if False:"))
    first, changed, same, sent = _send_reuse()
    assert changed == [first] * 4 and same == first and len(sent) == 1


@pytest.mark.parametrize("field, old, new", [
    ("to", "to=[str(x) for x in req.to], ", ""),
    ("cc", "cc=[str(x) for x in req.cc],", ""),
    # The digest's own continuation line: the message digest below it names
    # the same two fields.
    ("subject", "                          subject=req.subject, body=req.body)",
     "                          body=req.body)"),
    ("body", "                          subject=req.subject, body=req.body)",
     "                          subject=req.subject)"),
])
def test_the_send_digest_covers_each_field(monkeypatch, field, old, new):
    _first, changed, _same, _sent = _send_reuse()
    assert changed == [REUSED] * 4
    # mutant: the field left out of the send's digest -> a change to that
    # field alone replays the first send, and every other change is refused
    monkeypatch.setattr(main, "mail_send", _recompiled("mail_send", old, new))
    first, changed, _same, _sent = _send_reuse()
    assert changed == [first if f == field else REUSED for f in _SEND_FIELDS]


def test_a_receipt_without_a_request_digest_answers_on_the_stored_text(monkeypatch):
    """A receipt written by migration 404's backfill or by its trigger (a
    send or a reply the previous api build committed) has no request
    digest. A retry of its key is compared on the digest of the text the
    message stored: the same text replays, also when the request's body
    needs the send's canonicalising to equal it (a trailing CRLF); another
    body, or another subject on a send, is refused 409 and writes nothing.
    A reply's subject is derived, so a reply's retry is compared on its
    body."""
    def run():
        db, ids = tm._world()
        key = uuid.uuid4()
        mid = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], key=key,
                              subject="Plan", body="Meet at eight.")
        orig = db.seed_message(ids[B_SID], [(ids[A_SID], "to", "delivered")], subject="Day")
        rkey = uuid.uuid4()
        rmid = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], key=rkey,
                               subject="Re: Day", body="Sure.", thread_id=orig, in_reply_to=orig)
        assert {db.receipts[(ids[A_SID], k)]["request_fp"] for k in (key, rkey)} == {None}
        sends = [_outcome(tm._send, db, to=[B_SID], subject=s, body=b, key=str(key))
                 for s, b in (("Plan", "Meet at eight."), ("Plan", "Meet at eight.\r\n"),
                              ("Plan", "Meet at nine."), ("Plans", "Meet at eight."))]
        replies = [_outcome(_reply, db, orig, body=b, key=str(rkey), token="tokA")
                   for b in ("Sure.", "Sure!")]
        first = {"id": str(mid), "accepted": True}
        rfirst = {"id": str(rmid), "accepted": True}
        return sends, replies, first, rfirst, len(_directs(db, ids[A_SID]))
    sends, replies, first, rfirst, n = run()
    assert sends == [first, first, REUSED, REUSED] and replies == [rfirst, REUSED] and n == 2
    # mutant: no comparison where the receipt has no request digest -> the
    # changed body and the changed subject replay the first answer
    monkeypatch.setattr(main, "_mail_prior_send", _recompiled("_mail_prior_send", _LEGACY_COMPARE, "if False:"))
    sends, replies, first, rfirst, n = run()
    assert sends == [first] * 4 and replies == [rfirst, rfirst] and n == 2
    monkeypatch.setattr(main, "_mail_prior_send", _REAL["_mail_prior_send"])
    # mutant: the request's body digested as received, not canonicalised ->
    # the retry with a trailing CRLF is refused
    monkeypatch.setattr(main, "_mail_request_message_fp", _recompiled(
        "_mail_request_message_fp", 'b = _mail_text_or_raise(body, field="body", subject=False)',
        "b = body"))
    sends, _replies, first, _rfirst, _n = run()
    assert sends == [first, REUSED, REUSED, REUSED]
    monkeypatch.setattr(main, "_mail_request_message_fp", _REAL["_mail_request_message_fp"])
    # mutant: the reply's request digested as a send -> its own retry is refused
    monkeypatch.setattr(main, "_mail_reply_core", _recompiled(
        "_mail_reply_core", _REPLY_MFP, _REPLY_MFP.replace('"reply"', '"send"')))
    _sends, replies, _first, _rfirst, _n = run()
    assert replies == [REUSED, REUSED]


def test_a_send_replays_from_its_receipt_after_the_message_is_purged():
    """B's copy is suppressed, so no delivered copy keeps the row. The test
    removes the row directly (_purge): the state the janitor's purge reaches
    once the sender has deleted the message. The retry's answer is the first
    one."""
    def run(drop_receipt):
        db, ids = tm._world()
        db.players[ids[B_SID]]["mail_from"] = "nobody"
        key = _key()
        first = tm._send(db, [B_SID], key=key)
        _purge(db, first["id"])
        if drop_receipt:
            db.receipts.pop((ids[A_SID], UUID(key)))
        return first, tm._send(db, [B_SID], key=key), _directs(db, ids[A_SID])
    first, again, sent = run(False)
    assert again == first and sent == []                    # answered from the receipt; nothing sent again
    # data mutant: no receipt (the answer read off the message row, as before
    # migration 404) -> the retry after the purge is sent again under a new id
    first, again, sent = run(True)
    assert again != first and [str(m["id"]) for m in sent] == [again["id"]]


# ── POST /mail/{id}/reply ─────────────────────────────────────────────────

def _reply_reuse():
    """B replies once; then the key again with another body, with `all`
    flipped, unchanged, and unchanged on another thread (the Discord
    listing's second pick sends the key of its first). Returns (first,
    [other body, all flipped, unchanged, other thread], B's messages)."""
    db, ids = tm._world()
    orig = tm._send(db, [B_SID], subject="Plan")
    other = tm._send(db, [B_SID], subject="Another thread", body="Another ordinary body.")
    key = _key()
    first = _reply(db, orig["id"], body="Sounds good", key=key)
    after = [_outcome(_reply, db, orig["id"], body="Sounds bad", key=key),
             _outcome(_reply, db, orig["id"], body="Sounds good", all_=True, key=key),
             _outcome(_reply, db, orig["id"], body="Sounds good", key=key),
             _outcome(_reply, db, other["id"], body="Sounds good", key=key)]
    return first, after, _directs(db, ids[B_SID])


def test_a_reply_key_answers_its_body_and_flag_and_not_its_target(monkeypatch):
    first, after, mine = _reply_reuse()
    assert after == [REUSED, REUSED, first, first] and len(mine) == 1
    for new, want in (
            # the body out of the digest -> another body replays
            ('_mail_request_fp("reply", all=bool(reply_all))', ["first", REUSED, "first", "first"]),
            # `all` out of the digest -> the flipped flag replays
            ('_mail_request_fp("reply", body=body)', [REUSED, "first", "first", "first"]),
            # the target in the digest -> the Discord second pick is refused
            ('_mail_request_fp("reply", body=body, all=bool(reply_all), target=str(mid))',
             [REUSED, REUSED, "first", REUSED])):
        monkeypatch.setattr(main, "_mail_reply_core", _recompiled("_mail_reply_core", _REPLY_FP, new))
        first, after, _mine = _reply_reuse()
        assert after == [first if w == "first" else w for w in want], new


def _reply_all_world(suppress_d, mutate=None):
    """A writes to B and D, Cc C; D has blocked A in one world and not in
    the other. B replies to all. Returns what B can observe (the answer's
    keys, B's Sent entry for the reply), D's copy of the reply, D's inbox
    and the mutant's hits."""
    db, ids = tm._world()
    db.add_session("tokD", D_SID)
    if suppress_d:
        db.blocks.add((ids[D_SID], ids[A_SID]))
    orig = tm._send(db, [B_SID, D_SID], cc=[C_SID], subject="Plan")
    hits = mutate(db) if mutate else None
    ans = _reply(db, orig["id"], body="All of you?", all_=True)
    entry = next(m for m in _sent(db, "tokB") if m["id"] == ans["id"])
    seen = (_shape(ans), ans["accepted"], entry["addressees"], entry["subject"])
    d_inbox = [m["id"] for m in tm._inbox(db, token="tokD")["messages"]]
    return seen, db.recipients.get((UUID(ans["id"]), ids[D_SID])), d_inbox, hits


def _delivered_only(db):
    return _rewrite_sql(db, _REPLY_ALL_JOIN, _REPLY_ALL_JOIN + " AND e.delivery = 'delivered'")


def test_reply_all_answers_the_replier_the_same_whatever_the_delivery():
    seen_open, d_open, _inbox, _ = _reply_all_world(False)
    seen_hidden, d_hidden, _inbox, _ = _reply_all_world(True)
    assert seen_open == seen_hidden
    assert [(a["steam_id"], a["kind"]) for a in seen_open[2]] == [(A_SID, "to"), (D_SID, "to"), (C_SID, "cc")]
    assert d_open["delivery"] == "delivered" and d_hidden["delivery"] == "suppressed"
    # mutant: the reply-all read keeps delivered envelopes only (the rule
    # before migration 404) -> B's Sent entry differs between the worlds
    seen_open, _d, _inbox, hits_open = _reply_all_world(False, _delivered_only)
    seen_hidden, d_hidden, _inbox, hits = _reply_all_world(True, _delivered_only)
    assert hits and hits_open and seen_open != seen_hidden and d_hidden is None


def test_a_suppressed_addressee_gets_a_suppressed_copy_of_the_reply():
    _seen, d_copy, d_inbox, _ = _reply_all_world(True)
    assert (d_copy["kind"], d_copy["delivery"]) == ("to", "suppressed") and d_inbox == []
    # mutant: the fan-out's forced arm taken out -> D is delivered a reply in
    # a thread whose first message D was never delivered
    _seen, d_copy, d_inbox, hits = _reply_all_world(
        True, lambda db: _rewrite_sql(db, "WHEN a.forced THEN 'suppressed'", ""))
    assert hits and d_copy["delivery"] == "delivered" and len(d_inbox) == 1


def _wide_world(n_hidden, mutate=None):
    """A (a grant of 20) writes to B and 11 others; `n_hidden` of the others
    take mail from nobody, so their copies are suppressed. B (no grant: a
    cap of 8) replies to all: A plus the 11 others is 12 addressees."""
    db, ids = tm._world()
    db.bulk_grants[A_SID] = (20, NOW + timedelta(days=3))
    others = [f"765611980000001{i:02d}" for i in range(11)]
    for i, sid in enumerate(others):
        db.add_player(sid, mail_from="nobody" if i < n_hidden else "everyone")
    orig = tm._send(db, [B_SID] + others[:7], cc=others[7:])
    hits = mutate(db) if mutate else None
    return _shape(_outcome(_reply, db, orig["id"], body="Too many?", all_=True)), hits


def test_the_reply_all_cap_counts_every_addressee_whatever_the_delivery():
    assert _wide_world(0)[0] == _wide_world(5)[0] == (400, "too_many_recipients")
    # mutant: delivered envelopes only -> five suppressed copies bring the
    # reply under the cap, so the answer tells B how many were suppressed
    assert _wide_world(0, _delivered_only)[0] == (400, "too_many_recipients")
    shape, hits = _wide_world(5, _delivered_only)
    assert hits and shape == ["accepted", "id"]


def _own_reply_all(hidden, mutate=None):
    """A writes to B and D, then replies to all on A's own message; in one
    world both copies of the original were suppressed."""
    db, ids = tm._world()
    if hidden:
        db.players[ids[B_SID]]["mail_from"] = "nobody"
        db.blocks.add((ids[D_SID], ids[A_SID]))
    orig = tm._send(db, [B_SID, D_SID], subject="Plan")
    hits = mutate(db) if mutate else None
    ans = _outcome(_reply, db, orig["id"], body="Anyone?", all_=True, token="tokA")
    copies = sorted(e["delivery"] for (m, _r), e in db.recipients.items()
                    if isinstance(ans, dict) and m == UUID(ans["id"]))
    return _shape(ans), copies, hits


def test_reply_all_on_an_own_message_whose_copies_were_all_suppressed_is_accepted():
    assert _own_reply_all(False)[:2] == (["accepted", "id"], ["delivered", "delivered"])
    assert _own_reply_all(True)[:2] == (["accepted", "id"], ["suppressed", "suppressed"])
    # mutant: delivered envelopes only -> no addressee is left, and the
    # refusal tells A that every copy was suppressed
    assert _own_reply_all(False, _delivered_only)[0] == ["accepted", "id"]
    shape, _copies, hits = _own_reply_all(True, _delivered_only)
    assert hits and shape == (400, "recipients_empty")


# ── the sender's clock: Sent, detail, reply ───────────────────────────────

def _aged_world():
    """A's messages to B: two sent MAIL_RETENTION_DAYS+1 days ago and two
    MAIL_RETENTION_DAYS-1 days ago, of each pair one delivered (unread, so
    the janitor keeps it) and one suppressed."""
    db, ids = tm._world()
    made = {}
    for age, at in (("old", OLD), ("young", YOUNG)):
        for delivery in ("delivered", "suppressed"):
            made[f"{age}_{delivery}"] = str(db.seed_message(
                ids[A_SID], [(ids[B_SID], "to", delivery)], created_at=at, body=f"{age} {delivery}"))
    return db, ids, made


def test_sent_lists_a_message_until_retention_whatever_its_delivery():
    def listed(mutate):
        db, _ids, made = _aged_world()
        hits = _rewrite_sql(db, _SENDER_CLOCK) if mutate else None
        shown = {m["id"] for m in _sent(db, "tokA")}
        return {k for k, v in made.items() if v in shown}, hits
    got, _ = listed(False)
    assert got == {"young_delivered", "young_suppressed"}
    # mutant: the clock taken out of Sent -> old messages are listed for as
    # long as their rows exist, which depends on the recipients' delivery
    got, hits = listed(True)
    assert hits and got == {"old_delivered", "old_suppressed", "young_delivered", "young_suppressed"}


def test_the_senders_detail_and_reply_follow_the_same_clock():
    def run(mutate):
        db, _ids, made = _aged_world()
        hits = _rewrite_sql(db, _SENDER_CLOCK) if mutate else None
        out = {}
        for k in ("old_delivered", "young_delivered"):
            out["detail", k] = _shape(_outcome(_detail, db, made[k], "tokA"))
            out["reply_all", k] = _shape(_outcome(_reply, db, made[k], body=f"Still there? {k}",
                                                  all_=True, token="tokA"))
        out["recipient_detail"] = _shape(_outcome(_detail, db, made["old_delivered"], "tokB"))
        return out, hits
    out, _ = run(False)
    assert out["detail", "old_delivered"] == out["reply_all", "old_delivered"] == NOT_FOUND
    assert isinstance(out["detail", "young_delivered"], list)
    assert out["reply_all", "young_delivered"] == ["accepted", "id"]
    assert isinstance(out["recipient_detail"], list)        # a delivered copy keeps its own clock
    # mutant: the clock taken out of both reads -> the sender still reaches
    # the old message for as long as its row exists
    out, hits = run(True)
    assert hits and isinstance(out["detail", "old_delivered"], list)
    assert out["reply_all", "old_delivered"] == ["accepted", "id"]


# ── DELETE /mail/{id} ─────────────────────────────────────────────────────

_DELETE_404 = ("    if as_recipient is not None:\n",
               "    if as_recipient is None and as_sender is None:\n"
               "        raise HTTPException(status_code=404, detail=\"not_found\")\n"
               "    if as_recipient is not None:\n")


def _deletes(route):
    """A deletes a live message of A's, a message of A's the janitor has
    purged (B's copy was suppressed) and an id nobody holds; B deletes a
    delivered copy and a suppressed one."""
    db, ids = tm._world()
    live = tm._send(db, [C_SID], subject="Live", body="Body one.")["id"]
    db.players[ids[B_SID]]["mail_from"] = "nobody"
    purged = tm._send(db, [B_SID], subject="Purged", body="Body two.")["id"]
    hidden = tm._send(db, [B_SID], subject="Hidden", body="Body three.")["id"]
    db.players[ids[B_SID]]["mail_from"] = "everyone"
    shown = tm._send(db, [B_SID], subject="Shown", body="Body four.")["id"]
    _purge(db, purged)
    calls = (("tokA", live), ("tokA", purged), ("tokA", str(uuid.uuid4())), ("tokB", shown), ("tokB", hidden))
    out = [_outcome(lambda m, t: tm._run(route(m, tm._req(t), db)), mid, tok) for tok, mid in calls]
    return db, ids, [mid for _t, mid in calls], out


def test_delete_answers_the_same_for_every_well_formed_id():
    db, ids, mids, out = _deletes(main.mail_delete)
    assert out == [{"status": "deleted", "id": m} for m in mids]
    live, _purged, _nobody, shown, hidden = mids
    assert db.messages[UUID(live)]["deleted_by_sender_at"] is not None
    assert tm._env(db, shown, ids[B_SID])["deleted_at"] is not None
    assert tm._env(db, hidden, ids[B_SID])["deleted_at"] is None          # a suppressed copy is left as it is
    assert _outcome(lambda: tm._run(main.mail_delete("not-a-uuid", tm._req("tokA"), db)))[0] == 400
    # mutant: the earlier 404 for an id the caller holds no live copy of ->
    # A's answer for its own message changes once the janitor has purged it
    _db, _ids, mids, out = _deletes(_recompiled("mail_delete", *_DELETE_404))
    assert out == [{"status": "deleted", "id": mids[0]}, NOT_FOUND, NOT_FOUND,
                   {"status": "deleted", "id": mids[3]}, NOT_FOUND]


# ── the send rate window ──────────────────────────────────────────────────

_RATE_FROM = "  FROM mail_send_receipts WHERE sender_id = :sid AND kind = 'direct'"


def _rate_after_a_purge(delete, mutant=False):
    """Nine sends from A to B 30 s ago, the first one's copy suppressed.
    With `delete` A deletes that first send, and the janitor's sweep purges
    its row (no delivered copy keeps it; the purge has no age floor); then A
    sends twice. The tenth send fits the minute's window of 10 and the
    eleventh does not, either way: the window counts the send's receipt,
    which the purge leaves."""
    db, ids = tm._world()
    mids = [db.seed_message(ids[A_SID], [(ids[B_SID], "to", "suppressed" if i == 0 else "delivered")],
                            created_at=NOW - timedelta(seconds=30)) for i in range(9)]
    hits = _rewrite_sql(db, _RATE_FROM, _RATE_FROM.replace("mail_send_receipts", "mail_messages")) \
        if mutant else None
    if delete:
        assert tm._run(main.mail_delete(str(mids[0]), tm._req("tokA"), db))["status"] == "deleted"
    tm._run(main._mail_retention_sweep(db))
    kept = mids[0] in db.messages
    out = [_outcome(tm._send, db, [B_SID]), _outcome(tm._send, db, [B_SID])]
    assert hits is None or hits, "the mutant did not reach the rate query"
    return kept, [o if isinstance(o, tuple) else "accepted" for o in out]


def test_the_rate_window_counts_a_send_whose_row_is_gone():
    limited = (429, {"error": "rate_limited", "retry_after": 30})
    assert _rate_after_a_purge(False) == (True, ["accepted", limited])
    assert _rate_after_a_purge(True) == (False, ["accepted", limited])
    # mutant: the window counted on message rows -> the purged row frees a
    # place, so A's eleventh send in the minute is accepted
    assert _rate_after_a_purge(True, mutant=True) == (False, ["accepted", "accepted"])
    assert _rate_after_a_purge(False, mutant=True) == (True, ["accepted", limited])


# ── the spam check counts receipts ────────────────────────────────────────

# The previous build's spam reads, as a cut of main._mail_spam_check: the
# sender's day of bodies from mail_messages, compared in Python, and bulk
# from the envelopes in mail_recipients.
_OLD_SPAM_READ = '''
    key = _mail_norm_body(body)
    bodies = (await db.execute(text(
        "SELECT body FROM mail_messages"
        " WHERE sender_id = :sid AND kind = 'direct'"
        "   AND created_at > NOW() - make_interval(days => 1)"
    ), {"sid": sender["id"]})).scalars().all()
    same_body = sum(1 for b in bodies if _mail_norm_body(b) == key)
    row = (await db.execute(text(
        "SELECT"
        "  (SELECT COUNT(*) FROM ("
        "     SELECT m.id FROM mail_messages m"
        "       JOIN mail_recipients r ON r.message_id = m.id"
        "      WHERE m.sender_id = :sid AND m.kind = 'direct'"
        "        AND m.created_at > NOW() - make_interval(hours => 1)"
        "      GROUP BY m.id"
        "     HAVING COUNT(DISTINCT r.recipient_id) > CAST(:bulk_n AS integer)) x) AS bulk_hour,"
        "  (SELECT COUNT(*) FROM mail_censor_hits"
        "    WHERE sender_id = :sid AND created_at > NOW() - make_interval(days => 1)) AS censor_hits"
    ), {"sid": sender["id"], "bulk_n": MAIL_SPAM_BULK_RECIPIENTS})).mappings().first()
'''[1:]
_OLD_SPAM_CUT = ('    row = (await db.execute(text(\n',
                 '    same_body = int((row or {}).get("same_body") or 0)\n', _OLD_SPAM_READ)


def _spam_after_a_purge(purged, before_fifth=None):
    """A sends one body to B four times (this build: each receipt carries
    the body key) and deletes the four; three more sends of that body two
    hours ago were made by the previous build (migration 404's backfill
    wrote their receipts, with no body key), A deleted those too. B's copies
    are suppressed (`purged`: no delivered copy keeps the rows and the
    janitor's sweep purges them) or delivered and unread (the sweep keeps
    them). Then A sends the body to C. Returns the rows the sweep left, the
    receipts with no body key, and each case's same-body count."""
    db, ids = tm._world()
    if purged:
        db.players[ids[B_SID]]["mail_from"] = "nobody"
    delivery = "suppressed" if purged else "delivered"
    for _ in range(3):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", delivery)], body="Buy gold now",
                        created_at=NOW - timedelta(hours=2), deleted_by_sender_at=NOW - timedelta(hours=1))
    for _ in range(4):
        sent = tm._send(db, [B_SID], body="Buy  GOLD now")
        assert tm._run(main.mail_delete(sent["id"], tm._req("tokA"), db))["status"] == "deleted"
    assert not db.cases
    tm._run(main._mail_retention_sweep(db))
    left = len(_directs(db, ids[A_SID]))
    keyless = sum(1 for r in db.receipts.values() if r["kind"] == "direct" and r["body_key"] is None)
    if before_fifth is not None:
        before_fifth()
    tm._send(db, [C_SID], body="buy gold now")
    return left, keyless, [c["evidence"]["same_body_day"] for c in db.cases.values()]


def test_the_same_body_count_is_the_same_whether_the_purge_ran(monkeypatch):
    # the fifth send of the body by this build opens the case in both
    # states; the previous build's three sends count in neither
    assert _spam_after_a_purge(True) == (0, 3, [5])
    assert _spam_after_a_purge(False) == (7, 3, [5])
    # mutant: the count read off mail_messages bodies (the shape before
    # migration 404's change) -> the purge decides the count: one body left
    # and no case, or every kept body and a case of 8
    old = _spliced("_mail_spam_check", [_OLD_SPAM_CUT])
    install = lambda: monkeypatch.setattr(main, "_mail_spam_check", old)  # noqa: E731
    assert _spam_after_a_purge(True, install) == (0, 3, [])
    monkeypatch.setattr(main, "_mail_spam_check", _REAL["_mail_spam_check"])
    assert _spam_after_a_purge(False, install) == (7, 3, [8])


def _bulk_sends(delivery, before=None):
    """A (an admin: no recipient cap) sends three messages within the hour,
    each to MAIL_SPAM_BULK_RECIPIENTS + 1 players whose copies are all
    `delivery`. Returns the copies' deliveries and each case's bulk count."""
    db, ids = tm._world()
    db.admins.add(A_SID)
    many = [db.add_player(f"765611980000003{i:02d}",
                          mail_from="everyone" if delivery == "delivered" else "nobody")
            for i in range(main.MAIL_SPAM_BULK_RECIPIENTS + 1)]
    if before is not None:
        before()
    for i in range(3):
        tm._send(db, [db.players[r]["steam_id"] for r in many], body=f"Notice number {i}.")
    copies = {e["delivery"] for (_m, r), e in db.recipients.items() if r in set(many)}
    return copies, [c["evidence"]["bulk_hour"] for c in db.cases.values()]


def test_bulk_counts_each_sends_envelope_count_whatever_the_delivery(monkeypatch):
    assert _bulk_sends("delivered") == ({"delivered"}, [3])
    assert _bulk_sends("suppressed") == ({"suppressed"}, [3])
    # the receipt records the fan-out's own count
    assert "recipients=int(fanned.rowcount)" in inspect.getsource(main._mail_finish_send)
    # mutant: the receipt written with no envelope count -> no send is bulk
    old = _recompiled("_mail_finish_send", "recipients=int(fanned.rowcount)", "recipients=None")
    install = lambda: monkeypatch.setattr(main, "_mail_finish_send", old)  # noqa: E731
    assert _bulk_sends("delivered", install) == ({"delivered"}, [])
    assert _bulk_sends("suppressed", install) == ({"suppressed"}, [])


# ── the admin broadcast ───────────────────────────────────────────────────

def _bcast_db():
    db, ids = tm._world()
    db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    return db, ids, db.player_by_sid(ADMIN_SID)["id"]


def test_a_broadcast_replays_its_receipt_after_the_message_is_purged():
    def run(drop_receipt):
        db, _ids, admin = _bcast_db()
        key = _key()
        with tm._admin_secret():
            first = tm._broadcast(db, key=key)
            db.add_player("76561198000000077")               # one more player who ran the mod: a recount says 5
            _purge(db, first["id"])
            if drop_receipt:
                db.receipts.pop((admin, UUID(key)))
            again = tm._broadcast(db, key=key)
        return first, again, _broadcasts(db)
    first, again, live = run(False)
    assert first["recipients"] == 4 and again == first and live == []
    # data mutant: no receipt -> the retry broadcasts again, to 5
    first, again, live = run(True)
    assert again["id"] != first["id"] and again["recipients"] == 5 and len(live) == 1


_BCAST_FIRST = dict(subject="Notice", body="Servers restart at 04:00 UTC.")


def _bcast_reuse():
    db, _ids, _admin = _bcast_db()
    key = _key()
    with tm._admin_secret():
        first = tm._broadcast(db, key=key, **_BCAST_FIRST)
        changed = [_outcome(tm._broadcast, db, key=key, **dict(_BCAST_FIRST, subject="Notices")),
                   _outcome(tm._broadcast, db, key=key, **dict(_BCAST_FIRST, body="Servers restart at 05:00 UTC."))]
        same = tm._broadcast(db, key=key, **_BCAST_FIRST)
    return first, changed, same, _broadcasts(db)


def test_a_broadcast_key_answers_only_its_subject_and_body(monkeypatch):
    first, changed, same, live = _bcast_reuse()
    assert changed == [REUSED, REUSED] and same == first and len(live) == 1
    old = '_mail_request_fp("broadcast", subject=req.subject, body=req.body)'
    for name, mutant, want in (
            ("_mail_prior_send", (_COMPARE, "if False:"), ["first", "first"]),
            ("admin_mail_broadcast", (old, '_mail_request_fp("broadcast", body=req.body)'), ["first", REUSED]),
            ("admin_mail_broadcast", (old, '_mail_request_fp("broadcast", subject=req.subject)'),
             [REUSED, "first"])):
        monkeypatch.setattr(main, name, _recompiled(name, *mutant))
        first, changed, _same, live = _bcast_reuse()
        assert changed == [first if w == "first" else w for w in want] and len(live) == 1, mutant
        monkeypatch.setattr(main, name, _REAL[name])


# ── the receipt's writers and its sweep ───────────────────────────────────

def test_the_receipt_write_completes_only_its_own_messages_receipt(monkeypatch):
    def run():
        db, ids = tm._world()
        key = uuid.uuid4()
        other = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], key=key)
        fp = main._mail_request_fp("send", to=[B_SID], cc=[], subject="s", body="b")
        res = _outcome(lambda: tm._run(main._mail_write_receipt(
            db, sender_id=ids[A_SID], key=key, kind="direct", request_fp=fp,
            message_fp=main._mail_message_fp("send", "s", "b"), message_id=uuid.uuid4())))
        return db, ids, key, other, fp, res
    db, ids, key, other, fp, res = run()
    r = db.receipts[(ids[A_SID], key)]
    assert res == (500, "mail_receipt_conflict") and r["message_id"] == other and r["request_fp"] is None
    tm._run(main._mail_write_receipt(db, sender_id=ids[A_SID], key=key, kind="direct", request_fp=fp,
                                     message_fp=main._mail_message_fp("send", "s", "b"),
                                     message_id=other))
    assert r["message_id"] == other and r["request_fp"] == fp           # its own message's receipt is completed
    # mutant: the upsert's WHERE taken out -> the receipt of another message
    # takes this request's digest
    where = "   WHERE mail_send_receipts.message_id = EXCLUDED.message_id"
    assert main._MAIL_RECEIPT_SQL.count(where) == 1
    monkeypatch.setattr(main, "_MAIL_RECEIPT_SQL", main._MAIL_RECEIPT_SQL.replace(where, ""))
    db, ids, key, other, fp, res = run()
    r = db.receipts[(ids[A_SID], key)]
    assert res is None and r["message_id"] == other and r["request_fp"] == fp


def test_without_the_trigger_the_api_writes_the_whole_receipt(monkeypatch):
    """The api's own receipt carries the request's digest, which covers what
    the message row does not store: the same key with the same text and
    another recipient is refused. The retry after the purge replays."""
    def run(trigger):
        db, ids = tm._world()
        db.receipt_trigger = trigger                         # False: a schema without migration 404's trigger
        key = _key()
        first = tm._send(db, [B_SID], body="Meet at eight.", key=key)
        changed = _outcome_or_23505(tm._send, db, to=[C_SID], body="Meet at eight.", key=key)
        _purge(db, first["id"])
        again = tm._send(db, [B_SID], body="Meet at eight.", key=key)
        return first, changed, again, _directs(db, ids[A_SID])
    for trigger in (False, True):
        first, changed, again, sent = run(trigger)
        assert changed == REUSED and again == first and sent == [], trigger
    monkeypatch.setattr(main, "_mail_write_receipt", _no_receipt)
    # mutant, no trigger: nothing records the key -> the changed request
    # reaches the insert, which 297's unique key refuses while the first row
    # holds the key, and the retry after the purge is sent again
    first, changed, again, sent = run(False)
    assert changed == "23505" and again != first and len(sent) == 1
    # mutant, with the trigger: its receipt has the message's text digest
    # only -> the same text to another recipient replays the first send
    first, changed, again, sent = run(True)
    assert changed == first and again == first and sent == []


def test_without_the_trigger_a_broadcast_receipt_carries_its_count(monkeypatch):
    def run():
        db, _ids, admin = _bcast_db()
        db.receipt_trigger = False
        key = _key()
        with tm._admin_secret():
            first = tm._broadcast(db, key=key)
            r = dict(db.receipts.get((admin, UUID(key))) or {})
            db.add_player("76561198000000077")
            _purge(db, first["id"])
            again = tm._broadcast(db, key=key)
        return first, r, again
    first, r, again = run()
    assert (r["kind"], r["recipients"]) == ("system_broadcast", 4) and r["request_fp"] is not None
    assert again == first
    # mutant: the api writes no receipt -> nothing answers the retry after the purge
    monkeypatch.setattr(main, "_mail_write_receipt", _no_receipt)
    first, r, again = run()
    assert r == {} and again["id"] != first["id"] and again["recipients"] == 5


def test_a_receipt_goes_after_retention_whatever_its_message():
    def run(mutate):
        db, _ids, made = _aged_world()
        _purge(db, made["old_suppressed"])
        _purge(db, made["young_suppressed"])
        hits = _skip_sql(db, "DELETE FROM mail_send_receipts") if mutate else None
        n = tm._run(main._mail_retention_sweep(db))[3]
        left = {k for k, v in made.items() if any(str(r["message_id"]) == v for r in db.receipts.values())}
        return n, left, UUID(made["old_delivered"]) in db.messages, hits
    n, left, row_kept, _ = run(False)
    # the old receipts go, one of them while its message is still kept (unread)
    assert n == 2 and left == {"young_delivered", "young_suppressed"} and row_kept
    # mutant: the receipt arm not run -> every receipt stays
    n, left, _row_kept, hits = run(True)
    assert hits and n == 0 and left == {"old_delivered", "old_suppressed", "young_delivered", "young_suppressed"}


_DRAWN = re.compile(r"CAST\(overlay\(replace\(CAST\(gen_random_uuid\(\) AS text\), '-', ''\)"
                    r"\s+PLACING '0' FROM 13 FOR 1\) AS uuid\)")
_DRAW_EXPR = "replace(CAST(gen_random_uuid() AS text), '-', '')"
_DERIVE_EXPR = "md5('mail-key-retired:' || CAST(m.id AS text))"


def _sweep_with(monkeypatch, new):
    """Mutant: the sweep's new key for a kept message is `new`."""
    assert len(_DRAWN.findall(_REAL_SWEEP)) == 1
    monkeypatch.setattr(main, "_MAIL_RECEIPT_SWEEP_SQL", _DRAWN.sub(lambda _m: new, _REAL_SWEEP))


def test_a_swept_receipt_moves_a_kept_message_to_a_reserved_key(monkeypatch):
    """The janitor deletes an old receipt while an unread delivered copy
    still keeps its message. The same statement moves that message to a
    reserved key drawn at random, so the old key, which has no receipt now,
    is sent as a new message instead of being refused by 297's UNIQUE
    (sender_id, idempotency_key). The moved row's own key is refused on
    every route (_mail_parse_key), so no answer depends on whether that row
    is still kept."""
    def run():
        db, _ids, made = _aged_world()
        row = db.messages[UUID(made["old_delivered"])]
        key = row["idempotency_key"]
        tm._run(main._mail_retention_sweep(db))
        kept = UUID(made["old_delivered"]) in db.messages
        again = _outcome_or_23505(tm._send, db, to=[B_SID], key=str(key))
        named = _outcome_or_23505(tm._send, db, to=[B_SID], key=str(row["idempotency_key"]))
        return kept, row["idempotency_key"], key, again, named, made
    kept, now_key, key, again, named, made = run()
    assert kept and now_key.hex[12] == "0" and now_key != key
    assert now_key != _reserved("mail-key-retired:" + made["old_delivered"])
    assert isinstance(again, dict) and again["accepted"] and again["id"] != made["old_delivered"]
    assert named == (400, "idempotency_key_invalid")
    # mutant (a): the sweep leaves the key as it was -> the kept row still
    # holds it, and the new send under it is refused by the unique key
    _sweep_with(monkeypatch, "m.idempotency_key")
    kept, now_key, key, again, named, _made = run()
    assert kept and now_key == key and again == "23505"
    # mutant (b): a random key with its version digit as drawn (4) -> a
    # request can name the moved row's key, and the send under it reaches
    # the insert, which the kept row refuses (a purged row would let it
    # through)
    _sweep_with(monkeypatch, "gen_random_uuid()")
    kept, now_key, key, again, named, made = run()
    assert kept and now_key.hex[12] == "4" and now_key != key
    assert isinstance(again, dict) and again["accepted"] and named == "23505"


def _sweep_beside_a_held_derived_key(collide=False):
    """_aged_world, plus a message of A's sent now under the value the sweep
    DERIVED before migration 404's change for the kept message M
    (old_delivered): md5('mail-key-retired:' || M) with version digit 0. The
    previous build refuses no key, so a request it served could have stored
    that value. The janitor then sweeps M's receipt (older than retention)
    while B's unread copy keeps M. `collide` forces the sweep's draw to that
    same value. Returns (the sweep's outcome, M's key after, M's key before,
    the derived value, whether M's receipt is left, the holder's key)."""
    db, ids, made = _aged_world()
    m = UUID(made["old_delivered"])
    key = db.messages[m]["idempotency_key"]
    derived = _reserved("mail-key-retired:" + made["old_delivered"])
    holder = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], key=derived)
    if collide:
        db.draw = lambda: derived
    res = _outcome_or_23505(lambda: tm._run(main._mail_retention_sweep(db)))
    return (res, db.messages[m]["idempotency_key"], key, derived, (ids[A_SID], key) in db.receipts,
            db.messages[holder]["idempotency_key"])


def test_the_sweep_draws_a_kept_messages_key_at_random(monkeypatch):
    """A key another message of the sender already holds does not stop the
    sweep: M's receipt goes and M moves to a reserved key drawn for it."""
    res, now_key, key, derived, receipt_left, held = _sweep_beside_a_held_derived_key()
    assert isinstance(res, tuple) and res[3] == 2 and not receipt_left
    assert now_key.hex[12] == "0" and now_key not in (key, derived) and held == derived
    assert _outcome(main._mail_parse_key, str(now_key)) == (400, "idempotency_key_invalid")
    # drawn per run: a second world moves its M to another key
    assert _sweep_beside_a_held_derived_key()[1] != now_key
    # the fake's own control: a draw that meets a key the sender's messages
    # hold fails the statement (297's unique key), and nothing it did stays
    res, now_key, key, _derived, receipt_left, _held = _sweep_beside_a_held_derived_key(collide=True)
    assert res == "23505" and now_key == key and receipt_left
    # mutant: the key derived from M's id (the expression before migration
    # 404's change) -> the derived value is held already, the statement
    # fails, and M's receipt is never deleted
    assert _REAL_SWEEP.count(_DRAW_EXPR) == 1
    monkeypatch.setattr(main, "_MAIL_RECEIPT_SWEEP_SQL", _REAL_SWEEP.replace(_DRAW_EXPR, _DERIVE_EXPR))
    res, now_key, key, _derived, receipt_left, held = _sweep_beside_a_held_derived_key()
    assert res == "23505" and now_key == key and receipt_left


_MAIL_READS = ("mail_send_receipts", "mail_messages", "mail_recipients", "pg_advisory")


def _every_key_route(key):
    """Every route that takes an idempotency key, each in a world of its
    own, called with `key`: [(route, answer, the statements that read a
    mail table or took a lock, plus "resolved" for each call of the Discord
    route's relay-code resolver)]."""
    def touched(db):
        return [s for s in db.statements if any(t in s for t in _MAIL_READS)]
    out = []
    db, _ids = tm._world()
    out.append(("send", _outcome(tm._send, db, [B_SID], key=key), touched(db)))
    db, ids = tm._world()
    mid = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")])
    out.append(("reply", _outcome(_reply, db, mid, key=key), touched(db)))
    db, ids = tm._world()
    orig = db.seed_message(ids[B_SID], [(ids[A_SID], "to", "delivered")], subject="Day")
    me = tm._run(main._mail_caller(tm._req("tokA"), db))
    resolved = []

    async def target():
        resolved.append("resolved")
        return str(orig)
    ans = _outcome(lambda: tm._run(main._mail_reply_core(
        db, me, resolve_target=target, body="Yes.", reply_all=False, idempotency_key=key,
        via="discord")))
    out.append(("discord reply", ans, touched(db) + resolved))
    db, _ids, _admin = _bcast_db()
    with tm._admin_secret():
        out.append(("broadcast", _outcome(tm._broadcast, db, key=key), touched(db)))
    return out


def test_a_reserved_key_is_refused_on_every_route_before_any_read(monkeypatch):
    """A key with version digit 0 is the janitor's and the trigger's, never
    a request's: each route refuses it 400 before the sender lock and before
    any mail table is read, so its answer cannot depend on a row that holds
    it. The keys the shipped callers mint, uuid4 and uuid5, are sent."""
    bad = (400, "idempotency_key_invalid")
    reserved = [str(_drawn_reserved()), str(_reserved("mail-key-retired:%s" % uuid.uuid4()))]
    for key in reserved:
        got = _every_key_route(key)
        assert [(r, a, t) for r, a, t in got] == [(r, bad, []) for r, _a, _t in got], key
    for key in (str(uuid.uuid4()), str(uuid.uuid5(uuid.NAMESPACE_URL, "reply:%s" % uuid.uuid4()))):
        for route, ans, seen in _every_key_route(key):
            assert isinstance(ans, dict) and seen, (route, key)    # sent, and the probe sees its reads
    # mutant: the parse refuses no version digit -> every route sends under
    # a reserved key, after reading the mail tables
    monkeypatch.setattr(main, "_mail_parse_key", lambda v: main._mail_parse_uuid(v, "idempotency_key"))
    for route, ans, seen in _every_key_route(reserved[0]):
        assert isinstance(ans, dict) and seen, route


def test_a_reply_target_is_resolved_only_after_the_receipt_check(monkeypatch):
    """The Discord route hands the core a resolver for its relay code, not a
    message id; the core calls it under the locks after the repeated-key
    check. A retry of a reply that was sent replays even when the code no
    longer resolves (the replier deleted their copy of the thread since);
    a new key still resolves it first, and its refusal refuses the reply."""
    def run():
        db, ids = tm._world()
        orig = db.seed_message(ids[B_SID], [(ids[A_SID], "to", "delivered")], subject="Day")
        me = tm._run(main._mail_caller(tm._req("tokA"), db))
        calls = []

        async def live():
            calls.append("resolved")
            return str(orig)

        async def gone():
            calls.append("resolved")
            raise HTTPException(status_code=404, detail="not_found")

        def reply(target, key):
            return _outcome(lambda: tm._run(main._mail_reply_core(
                db, me, resolve_target=target, body="Yes.", reply_all=False,
                idempotency_key=key, via="discord")))
        key = _key()
        first = reply(live, key)
        return first, reply(gone, key), reply(gone, _key()), calls
    first, again, fresh, calls = run()
    assert first["accepted"] and again == first and fresh == NOT_FOUND
    assert calls == ["resolved", "resolved"]                   # the retry never asked
    # mutant: the target resolved before the repeated-key check -> the retry
    # of the reply that was sent is refused 404
    check = ('    prior = await _mail_prior_send(db, me["id"], key, fp, mfp)\n'
             '    if prior is not None:\n'
             '        return prior\n')
    resolve = ('    if mid is None:\n'
               '        mid = _mail_parse_uuid(await resolve_target(), "message_id")\n')
    monkeypatch.setattr(main, "_mail_reply_core", _recompiled(
        "_mail_reply_core", check + resolve, resolve + check))
    first, again, fresh, calls = run()
    assert first["accepted"] and again == NOT_FOUND and fresh == NOT_FOUND and len(calls) == 3


# ── one statement per sender read ─────────────────────────────────────────
#
# The janitor's purge removes a message and its envelopes together. The
# reply core, Sent and the detail read take the message and its envelopes
# (the reply-all list, the addressees) from ONE statement, so from one
# snapshot. Each test below purges the message right after the statement
# that read it (_after_sql) -- the state the purge reaches when it commits
# between two statements of the request -- and compares the answer with the
# kept state. The mutant is the previous build's two-statement shape (a cut
# of the route's own source), whose second statement finds the envelopes
# gone.

_OLD_REPLY_CUTS = (
    ('    rows = (await db.execute(text(\n        _MAIL_CLOCK_CTE +\n',
     '    orig = rows[0]\n', '''
    orig = (await db.execute(text(
        "SELECT m.id, m.sender_id, m.kind, m.thread_id, m.subject"
        "  FROM mail_messages m"
        " WHERE m.id = :mid"
        "   AND ((m.sender_id = :me AND m.deleted_by_sender_at IS NULL"
        "         AND m.created_at > NOW() - make_interval(days => CAST(:ret_days AS integer)))"
        "        OR EXISTS (SELECT 1 FROM mail_recipients r"
        "                    WHERE r.message_id = m.id AND r.recipient_id = :me"
        "                      AND r.delivery = 'delivered' AND r.deleted_at IS NULL))"
    ), {"mid": mid, "me": me["id"], "ret_days": MAIL_RETENTION_DAYS})).mappings().first()
    if orig is None:
        raise HTTPException(status_code=404, detail="not_found")
'''[1:]),
    ('        pairs.extend((r["env_recipient_id"]',
     '                     for r in rows if r["env_recipient_id"] is not None)\n', '''
        rows = (await db.execute(text(
            "SELECT recipient_id, kind, delivery FROM mail_recipients"
            " WHERE message_id = :mid"
        ), {"mid": mid})).mappings().all()
        pairs.extend((r["recipient_id"], r["kind"], r["delivery"] != "delivered") for r in rows)
'''[1:]))

# The previous build's addressee read (main._MAIL_ADDRESSEES_SQL and
# main._mail_addressees before migration 404's change), for the mutants.
_OLD_ADDRESSEES_SQL = (
    "WITH a AS ("
    "  SELECT r.message_id, r.kind, p.steam_id, p.display_name,"
    "         ROW_NUMBER() OVER (PARTITION BY r.message_id"
    "                            ORDER BY r.kind DESC, p.display_name, p.steam_id) AS rn"
    "    FROM mail_recipients r JOIN players p ON p.id = r.recipient_id"
    "   WHERE r.message_id = ANY(CAST(:mids AS uuid[])))"
    " SELECT message_id, kind, steam_id, display_name FROM a"
    "  WHERE rn <= CAST(:cap AS integer) ORDER BY message_id, rn"
)


async def _old_addressees(db, message_ids):
    if not message_ids:
        return {}
    rows = (await db.execute(text(_OLD_ADDRESSEES_SQL),
                             {"mids": list(message_ids), "cap": main.MAIL_ADDRESSEES_MAX})).mappings().all()
    out = {}
    for r in rows:
        out.setdefault(r["message_id"], []).append(
            {"steam_id": r["steam_id"], "name": r["display_name"], "kind": r["kind"]})
    return out


_OLD_SENT_CUTS = (
    ('    rows = (await db.execute(text(\n',
     '    page, next_cursor = _mail_page(_mail_group_addressees(rows), limit)\n', '''
    rows = (await db.execute(text(
        "SELECT m.id, m.thread_id, m.subject, m.created_at, m.kind"
        "  FROM mail_messages m"
        " WHERE m.sender_id = :me AND m.deleted_by_sender_at IS NULL"
        "   AND m.created_at > NOW() - make_interval(days => CAST(:ret_days AS integer))"
        "   AND (CAST(:c_at AS timestamptz) IS NULL"
        "        OR (m.created_at, m.id) < (CAST(:c_at AS timestamptz), CAST(:c_id AS uuid)))"
        " ORDER BY m.created_at DESC, m.id DESC"
        " LIMIT CAST(:lim AS integer)"
    ), {"me": me["id"], "c_at": c_at, "c_id": c_id, "lim": limit + 1,
        "ret_days": MAIL_RETENTION_DAYS})).mappings().all()
    page, next_cursor = _mail_page(rows, limit)
    addr = await _mail_addressees(db, [r["id"] for r in page if r["kind"] != "system_broadcast"])
'''[1:]),
    ('"addressees": r["addressees"],', '"addressees": r["addressees"],', '"addressees": addr.get(r["id"], []),'))

_OLD_DETAIL_CUTS = (
    ('    rows = (await db.execute(text(\n', '    addr = row["addressees"]\n', '''
    row = (await db.execute(text(
        "SELECT m.id, m.thread_id, m.in_reply_to, m.kind, m.subject, m.body, m.created_at, m.via,"
        "       m.sender_id, s.steam_id AS sender_steam_id, s.display_name AS sender_name,"
        "       CAST(s.id AS text) AS sender_pid, COALESCE(gr.rating, 1500) AS rating,"
        "       si.name AS title, si.preview_color AS title_color, si.sku AS title_sku,"
        "       r.read_at"
        "  FROM mail_messages m"
        "  JOIN players s ON s.id = m.sender_id"
        "  LEFT JOIN glicko_ratings gr ON gr.player_id = s.id"
        "  LEFT JOIN shop_items si ON si.id = s.active_title_id"
        "  LEFT JOIN mail_recipients r ON r.message_id = m.id AND r.recipient_id = :me"
        "                             AND r.delivery = 'delivered' AND r.deleted_at IS NULL"
        " WHERE m.id = :mid"
        "   AND (r.recipient_id IS NOT NULL"
        "        OR (m.sender_id = :me AND m.deleted_by_sender_at IS NULL"
        "            AND m.created_at > NOW() - make_interval(days => CAST(:ret_days AS integer))))"
    ), {"mid": mid, "me": me["id"], "ret_days": MAIL_RETENTION_DAYS})).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    colors = await _mail_sender_colors(db, [row])
    addr = [] if row["kind"] == "system_broadcast" else (await _mail_addressees(db, [row["id"]])).get(row["id"], [])
'''[1:]),)


def _one_statement(reads):
    """The route read the message and its envelopes in exactly one statement."""
    return len(reads) == 1 and "FROM mail_messages m" in reads[0] and "mail_recipients" in reads[0]


def _reply_all_across_a_purge(purge):
    """A writes to B and D, both copies suppressed (so no delivered copy
    keeps the message), and replies to all on A's own message; with `purge`
    the message is purged right after the statement that admitted it.
    Returns the answer's shape, the reply's copies and the reply's reads."""
    db, ids = tm._world()
    db.players[ids[B_SID]]["mail_from"] = "nobody"
    db.blocks.add((ids[D_SID], ids[A_SID]))
    orig = tm._send(db, [B_SID, D_SID], subject="Plan")
    hits = _after_sql(db, _ORIG_READ, lambda d: _purge(d, orig["id"])) if purge else None
    db.statements.clear()
    ans = _outcome(_reply, db, orig["id"], body="Anyone?", all_=True, token="tokA")
    reads = _mail_reads(db)
    assert hits is None or hits, "the purge did not run"
    copies = sorted(e["delivery"] for (m, _r), e in db.recipients.items()
                    if isinstance(ans, dict) and m == UUID(ans["id"]))
    return _shape(ans), copies, reads


def test_reply_all_reads_the_original_and_its_envelopes_in_one_statement(monkeypatch):
    for purge in (False, True):
        shape, copies, reads = _reply_all_across_a_purge(purge)
        assert shape == ["accepted", "id"] and copies == ["suppressed", "suppressed"], purge
        assert _one_statement(reads), reads
    # mutant: the original and its envelopes read by two statements -> a
    # purge between them leaves the reply with no addressee, and the
    # refusal depends on whether the purge ran
    monkeypatch.setattr(main, "_mail_reply_core", _spliced("_mail_reply_core", _OLD_REPLY_CUTS))
    shape, copies, reads = _reply_all_across_a_purge(False)
    assert shape == ["accepted", "id"] and copies == ["suppressed", "suppressed"]
    assert len(reads) == 2 and not _one_statement(reads)
    shape, _copies, _reads = _reply_all_across_a_purge(True)
    assert shape == (400, "recipients_empty")


def _sent_and_detail_across_a_purge(route, purge):
    """A writes to B, Cc C, then opens Sent (`route` "sent") or the
    message's detail ("detail"); with `purge` the message is purged right
    after the statement that read it. Returns the addressees shown and the
    route's reads."""
    db, ids = tm._world()
    orig = tm._send(db, [B_SID], cc=[C_SID], subject="Plan")
    anchor = _SENT_READ if route == "sent" else _DETAIL_READ
    hits = _after_sql(db, anchor, lambda d: _purge(d, orig["id"])) if purge else None
    db.statements.clear()
    if route == "sent":
        entry = next(m for m in _sent(db, "tokA") if m["id"] == orig["id"])
        shown = [(a["steam_id"], a["kind"]) for a in entry["addressees"]]
    else:
        ans = _detail(db, orig["id"], "tokA")
        shown = [(a["steam_id"], k) for k in ("to", "cc") for a in ans[k]]
    reads = _mail_reads(db)
    assert hits is None or hits, "the purge did not run"
    return shown, reads


@pytest.mark.parametrize("route, cuts", [("sent", _OLD_SENT_CUTS), ("detail", _OLD_DETAIL_CUTS)])
def test_sent_and_detail_read_the_message_and_its_addressees_in_one_statement(monkeypatch, route, cuts):
    want = [(B_SID, "to"), (C_SID, "cc")]
    for purge in (False, True):
        shown, reads = _sent_and_detail_across_a_purge(route, purge)
        assert shown == want and _one_statement(reads), (purge, reads)
    for gone in ("_MAIL_ADDRESSEES_SQL", "_mail_addressees"):
        assert not hasattr(main, gone), gone
    # mutant: the message and its addressees read by two statements -> a
    # purge between them empties the list the sender is shown
    name = "mail_sent" if route == "sent" else "mail_detail"
    monkeypatch.setattr(main, name, _spliced(name, cuts, {"_mail_addressees": _old_addressees}))
    shown, reads = _sent_and_detail_across_a_purge(route, False)
    assert shown == want and len(reads) == 2 and not _one_statement(reads)
    shown, _reads = _sent_and_detail_across_a_purge(route, True)
    assert shown == []


# ── the clock is read inside each statement ───────────────────────────────

_CLOCK_APPLIED = "t.now_ - make_interval(days => CAST(:ret_days AS integer))"


def _clock_faults(sql):
    """What keeps `sql` from reading its retention clock inside itself: the
    MATERIALIZED clock_timestamp() CTE first, joined and applied, and no
    NOW() anywhere."""
    faults = []
    if not sql.lstrip().startswith(_CLOCK_CTE):
        faults.append("no clock CTE")
    if "NOW()" in sql.upper():
        faults.append("NOW()")
    if "CROSS JOIN t" not in sql:
        faults.append("t not joined")
    if _CLOCK_APPLIED not in sql:
        faults.append("clock not applied")
    return faults


def _clock_statements():
    """The reply core's read (reply all), Sent's and the detail read, as the
    routes issue them against the fake, and mail_discord._REPLIED_TO_SQL."""
    db, _ids = tm._world()
    orig = tm._send(db, [B_SID], cc=[C_SID])
    db.statements.clear()
    _reply(db, orig["id"], body="All of you?", all_=True, token="tokA")
    _sent(db, "tokA")
    _detail(db, orig["id"], "tokA")
    out = {}
    for name, anchor in (("reply", _ORIG_READ), ("sent", _SENT_READ), ("detail", _DETAIL_READ)):
        found = [s for s in db.statements if anchor in s]
        assert len(found) == 1, (name, found)
        out[name] = found[0]
    out["replied_to"] = mail_discord._REPLIED_TO_SQL
    return out


def test_each_sender_read_takes_its_clock_inside_the_statement():
    assert main._MAIL_CLOCK_CTE == _CLOCK_CTE + ","
    assert mail_discord._REPLIED_TO_SQL.startswith(_CLOCK_CTE)
    for name, sql in _clock_statements().items():
        assert _clock_faults(sql) == [], name
        # mutant: NOW() (the transaction's start) in place of t.now_
        assert sql.count("t.now_ -") >= 1, name
        assert "NOW()" in _clock_faults(sql.replace("t.now_ -", "NOW() -")), name


def _past_retention_across_the_purge(mutate):
    """A's message to B (suppressed), sent MAIL_RETENTION_DAYS and 5 s ago.
    A's transaction began 10 s before the statement ran (it waited for its
    locks), so NOW() is 10 s behind the statement's clock. A opens Sent and
    the detail, the janitor's sweep purges the message, A opens both again.
    Returns (before, purged, after), each view as (listed, detail shape)."""
    db, ids = tm._world()
    db.txn_start = NOW - timedelta(seconds=10)
    mid = str(db.seed_message(ids[A_SID], [(ids[B_SID], "to", "suppressed")],
                              created_at=NOW - timedelta(days=main.MAIL_RETENTION_DAYS, seconds=5)))
    hits = _rewrite_sql(db, "t.now_ -", "NOW() -") if mutate else None

    def seen():
        return mid in {m["id"] for m in _sent(db, "tokA")}, _shape(_outcome(_detail, db, mid, "tokA"))
    before = seen()
    tm._run(main._mail_retention_sweep(db))
    purged = UUID(mid) not in db.messages
    after = seen()
    assert hits is None or hits, "the mutant did not reach the reads"
    return before, purged, after


def test_the_senders_view_is_the_same_whether_the_purge_ran():
    assert _past_retention_across_the_purge(False) == ((False, NOT_FOUND), True, (False, NOT_FOUND))
    # mutant: the clock taken from NOW() -> the transaction's earlier start
    # still admits the message, so the answer turns on whether the purge ran
    before, purged, after = _past_retention_across_the_purge(True)
    assert purged and before[0] is True and isinstance(before[1], list) and after == (False, NOT_FOUND)
