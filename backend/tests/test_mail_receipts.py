"""Mail send receipts, reply all and the sender's own view (migration 404's
change), executed against the in-memory fake of test_mail.py.

What each endpoint answers after the change:

- POST /mail, POST /mail/{id}/reply and the admin broadcast answer a
  repeated idempotency_key from that key's send receipt alone: the first
  answer, whatever the message's delivery and whether the janitor has
  purged the message row since. A request that differs from the one the
  receipt was written for (its digest, main._mail_request_fp) is refused,
  409 idempotency_key_reused, and writes nothing. A receipt with no digest
  (written by migration 404's backfill or by its trigger) replays.
- Reply all addresses the original's sender and every addressee of the
  original, delivered or suppressed alike, so the replier's answer,
  recipient cap and Sent list are the same whatever the other players'
  delivery; an addressee whose copy of the original was suppressed gets a
  suppressed copy of the reply.
- Sent, and the sender's branch of the detail read and of the reply's
  original read, show a message until MAIL_RETENTION_DAYS after it was
  sent (or until its sender deletes it), whatever its delivery.
- DELETE /mail/{id} answers 200 {"status": "deleted", "id"} for every
  well-formed id.
- The janitor deletes a receipt MAIL_RETENTION_DAYS after its send,
  whatever the state of the message it names.

Every test runs a control (the code as written) and at least one mutant
(the code with one rule taken out: the production SQL rewritten on its way
to the fake, a statement not run, a function recompiled from its own source
with one line changed, or the receipt removed from the data) and asserts
that the mutant changes the answer the control pins. A mutant whose anchor
is not found fails the test instead of passing it.
"""

import inspect
import textwrap
import uuid
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

import main
import test_mail as tm
from test_mail import A_SID, ADMIN_SID, B_SID, C_SID, D_SID, NOW, _SENDER_CLOCK

REUSED = (409, "idempotency_key_reused")
NOT_FOUND = (404, "not_found")
OLD = NOW - timedelta(days=main.MAIL_RETENTION_DAYS + 1)
YOUNG = NOW - timedelta(days=main.MAIL_RETENTION_DAYS - 1)
_REPLY_ALL_READ = "SELECT recipient_id, kind, delivery FROM mail_recipients WHERE message_id = :mid"
_COMPARE = "if stored is not None and bytes(stored) != request_fp:"
_REPLY_FP = '_mail_request_fp("reply", body=body, all=bool(reply_all))'

# The functions the mutants are recompiled from, taken before any test can
# replace one on the module.
_REAL = {name: getattr(main, name) for name in (
    "_mail_prior_send", "_mail_reply_core", "mail_send", "admin_mail_broadcast", "mail_delete",
    "_mail_write_receipt", "_mail_request_fp")}


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch):
    monkeypatch.setattr(main, "_utc_now", lambda: NOW)


# ── helpers ───────────────────────────────────────────────────────────────

def _key():
    return str(uuid.uuid4())


def _outcome(fn, *a, **kw):
    """The call's answer, or (status, detail) for a refusal."""
    try:
        return fn(*a, **kw)
    except HTTPException as e:
        return (e.status_code, e.detail)


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
    ("subject", "subject=req.subject, body=req.body)", "body=req.body)"),
    ("body", "subject=req.subject, body=req.body)", "subject=req.subject)"),
])
def test_the_send_digest_covers_each_field(monkeypatch, field, old, new):
    _first, changed, _same, _sent = _send_reuse()
    assert changed == [REUSED] * 4
    # mutant: the field left out of the send's digest -> a change to that
    # field alone replays the first send, and every other change is refused
    monkeypatch.setattr(main, "mail_send", _recompiled("mail_send", old, new))
    first, changed, _same, _sent = _send_reuse()
    assert changed == [first if f == field else REUSED for f in _SEND_FIELDS]


def test_a_receipt_without_a_digest_replays_its_key(monkeypatch):
    """A receipt written by migration 404's backfill or by its trigger (a
    send the previous api build committed) has no digest: a retry of its
    key is answered from it, as before the change."""
    def run():
        db, ids = tm._world()
        key = uuid.uuid4()
        mid = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], key=key)
        assert db.receipts[(ids[A_SID], key)]["request_fp"] is None
        again = _outcome(tm._send, db, to=[B_SID], body="Some other body.", key=str(key))
        return mid, again, _directs(db, ids[A_SID])
    mid, again, sent = run()
    assert again == {"id": str(mid), "accepted": True} and len(sent) == 1
    # mutant: a missing digest compared as a mismatch -> the retry is refused
    monkeypatch.setattr(main, "_mail_prior_send", _recompiled(
        "_mail_prior_send", _COMPARE, "if bytes(stored or b'') != request_fp:"))
    _mid, again, sent = run()
    assert again == REUSED and len(sent) == 1


def test_a_send_replays_from_its_receipt_after_the_message_is_purged():
    """B's copy is suppressed, so no delivered copy keeps the row and the
    janitor may purge it at once; the retry's answer is the first one."""
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
    return _rewrite_sql(db, _REPLY_ALL_READ, _REPLY_ALL_READ + " AND delivery = 'delivered'")


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


def _rate_after_a_delete(delivery, mutant=False):
    """Nine sends from A to B 30 s ago; A deletes the first, whose copy to B
    was `delivery`, and the janitor sweeps; then A sends twice. The tenth
    send fits the minute's window of 10 and the eleventh does not, in both
    worlds: the deleted send still counts after its row is purged."""
    db, ids = tm._world()
    mids = [db.seed_message(ids[A_SID], [(ids[B_SID], "to", delivery if i == 0 else "delivered")],
                            created_at=NOW - timedelta(seconds=30)) for i in range(9)]
    hits = _rewrite_sql(db, _RATE_FROM, _RATE_FROM.replace("mail_send_receipts", "mail_messages")) \
        if mutant else None
    assert tm._run(main.mail_delete(str(mids[0]), tm._req("tokA"), db))["status"] == "deleted"
    tm._run(main._mail_retention_sweep(db))
    purged = mids[0] not in db.messages
    out = [_outcome(tm._send, db, [B_SID]), _outcome(tm._send, db, [B_SID])]
    assert hits is None or hits, "the mutant did not reach the rate query"
    return purged, [o if isinstance(o, tuple) else "accepted" for o in out]


def test_the_rate_window_counts_a_deleted_send_whatever_its_delivery():
    limited = (429, {"error": "rate_limited", "retry_after": 30})
    assert _rate_after_a_delete("suppressed") == (True, ["accepted", limited])    # the row was purged
    assert _rate_after_a_delete("delivered") == (False, ["accepted", limited])    # B's unread copy keeps it
    # mutant: the window counted on message rows -> the purged send frees a
    # place, so A's eleventh send in the minute is accepted only when the
    # deleted message's copy was suppressed
    assert _rate_after_a_delete("suppressed", mutant=True) == (True, ["accepted", "accepted"])
    assert _rate_after_a_delete("delivered", mutant=True) == (False, ["accepted", limited])


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
    old = '"broadcast", subject=req.subject, body=req.body)'
    for name, mutant, want in (
            ("_mail_prior_send", (_COMPARE, "if False:"), ["first", "first"]),
            ("admin_mail_broadcast", (old, '"broadcast", body=req.body)'), ["first", REUSED]),
            ("admin_mail_broadcast", (old, '"broadcast", subject=req.subject)'), [REUSED, "first"])):
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
            db, sender_id=ids[A_SID], key=key, kind="direct", request_fp=fp, message_id=uuid.uuid4())))
        return db, ids, key, other, fp, res
    db, ids, key, other, fp, res = run()
    r = db.receipts[(ids[A_SID], key)]
    assert res == (500, "mail_receipt_conflict") and r["message_id"] == other and r["request_fp"] is None
    tm._run(main._mail_write_receipt(db, sender_id=ids[A_SID], key=key, kind="direct", request_fp=fp,
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
    def run(trigger):
        db, ids = tm._world()
        db.receipt_trigger = trigger                         # False: a schema without migration 404's trigger
        key = _key()
        first = tm._send(db, [B_SID], body="Meet at eight.", key=key)
        changed = _outcome(tm._send, db, to=[B_SID], body="Meet at nine.", key=key)
        _purge(db, first["id"])
        again = tm._send(db, [B_SID], body="Meet at eight.", key=key)
        return first, changed, again, _directs(db, ids[A_SID])
    for trigger in (False, True):
        first, changed, again, sent = run(trigger)
        assert changed == REUSED and again == first and sent == [], trigger
    monkeypatch.setattr(main, "_mail_write_receipt", _no_receipt)
    # mutant, no trigger: nothing records the key -> the changed body is
    # sent, and the retry after the purge is sent again
    first, changed, again, sent = run(False)
    assert changed != REUSED and again != first and len(sent) == 2
    # mutant, with the trigger: its receipt has no digest -> the changed body replays
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
