"""Mail <-> Discord relay (v1.41.0 item 5): outbound DM + reply from Discord.

Mounted from main.py. Two entry points and nothing else:

  queue_mail_relay(...)   called by _mail_finish_send INSIDE the send
                          transaction, once the fan-out has decided who
                          actually receives the mail.
  POST /api/v1/internal/mail/reply-from-discord
                          the bot's reply route.

THE QUEUE IS `pending_dms`, NOT A NEW OUTBOX. PLAN.md specified a fresh
`mail_discord_outbox` with state/lease_until/attempts plus a second bot poll
loop, citing learning #167. But #167 is the learning `pending_dms`
(migration 129) already implements, in production: durable unacknowledged
rows, deterministic created_at order, an internal-key ack, and an in-memory
sent-but-unacked set so an ack retry does not repost. #167 calls the one
remaining gap -- a crash between send and ack -- "the correct at-least-once
tradeoff". Migration 330 adds what that queue genuinely lacked and reuses
everything else. This docstring is the record of that deviation: the
schema half is backend/sql/330_mail_discord_relay.sql, and
backend/tests/test_mail_discord_relay.py runs the fan-out over pending_dms.

HOW A REPLY FINDS ITS THREAD, AND WHY IT IS NOT INFERRED. Every DM carries a
`relay_code` on its own final line. The code is minted and stored in the SAME
transaction that composes the text, so it is durable strictly BEFORE the
Discord message exists -- which is the property no Discord message id can
have, because a snowflake only exists after the message does. A reply names
its thread by carrying that code back, and a reply that names none is
REFUSED with a list to pick from.

Four review rounds were spent patching the alternative. Process-local maps,
a content-substring identity test, an exact-then-recent ladder and a 24-hour
window each answered "which thread did they mean?" with a guess, and the
server-side envelope check can only answer "may they write here" -- so a
guess that lands on another authorized thread is accepted and the player's
words are committed to it. Learning #174 states the general form: request
arrival time is not identity. #177 adds the disposition: retaining
unattached evidence is safer than accusing the wrong match.

WHY THE FAN-OUT READS `mail_recipients` AND NOT THE ADDRESSEE LIST. The
relay must never deliver a copy the in-game path suppressed. Rather than
re-derive the block / mail_from / played rules here -- where they would
drift -- the relay selects from the rows `_MAIL_FANOUT_SQL` has just
written, filtered to `delivery = 'delivered'`. A recipient who blocked the
sender, or who has mail_from = 'nobody', produces a 'suppressed' row and so
produces no DM, by construction rather than by a second copy of the rule.

WHY THERE IS A bind(). The reply route must run the SAME core the in-game
route runs -- every gate, both callers, no rule reachable from one and not
the other. That core lives in main.py, which imports this module, so a
top-level import here would be circular. main.py calls bind() immediately
after defining the core, and asserts at import that the bind happened; an
unbound handler raises rather than quietly doing something less careful.
"""
import re
import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

router = APIRouter()

# main.py binds the real implementations here at import time.
_BOUND: dict = {}
_REQUIRED = ("reply_core", "discord_safe", "internal_key")


def bind(**fns) -> None:
    """Called once from main.py, after the bound functions exist."""
    unknown = set(fns) - set(_REQUIRED)
    if unknown:
        raise RuntimeError("mail_discord.bind: unknown %s" % sorted(unknown))
    _BOUND.update(fns)


def bound_ok() -> bool:
    """True once every required implementation is present. main.py asserts
    this at import so an incomplete wiring fails at startup, not at the
    first player reply."""
    return all(_BOUND.get(k) is not None for k in _REQUIRED)


def _need(name):
    fn = _BOUND.get(name)
    if fn is None:
        raise HTTPException(
            status_code=500,
            detail="mail_relay_unbound")
    return fn


# ── Outbound ──────────────────────────────────────────────────────────────

# Typed binds throughout (#275/#448): asyncpg will not infer a parameter's
# type from an INSERT ... SELECT's target column.
_RELAY_FANOUT_SQL = (
    "INSERT INTO pending_dms (steam_id, content, mail_id, relay_code)"
    " SELECT p.steam_id, CAST(:content AS text), CAST(:mid AS uuid),"
    "        CAST(:code AS text)"
    "   FROM mail_recipients r"
    "   JOIN players p ON p.id = r.recipient_id"
    "  WHERE r.message_id = CAST(:mid AS uuid)"
    "    AND r.delivery = 'delivered'"
    # Defensive: inside the sending transaction an envelope written moments
    # ago cannot be soft-deleted yet. Carried anyway because every other
    # reader of this table carries it, and a relay that is the one reader
    # without it is a trap for whoever reuses the statement.
    "    AND r.deleted_at IS NULL"
    "    AND p.discord_id IS NOT NULL"
    "    AND p.mail_discord_relay"
)

# Discord's own hard limit is 2000 characters for a message. The mail body
# alone may be 2000, so it is clipped well short of it and the rest of the
# budget goes to the header, the footer and the marker line; a reader who
# wants the whole thing has it in-game, which the footer says.

# ── The marker: the one thing that says which thread a DM is ────────────────
#
# `SCR-` + 12 Crockford base32 characters (I, L, O and U are not in the
# alphabet, so the shapes a player can mis-read or mis-type are not in it
# either). 60 bits: a collision inside one player's threads is unreachable,
# and the unique index means one would be refused rather than mis-resolve.
#
# It appears in a DM as its own FINAL line and is recognised only by an
# anchored pattern on that line. `discord_safe` rewrites a line-leading "-#"
# and collapses intra-line whitespace, so no player-authored field can render
# as this line -- the marker is a thing whose only purpose is to be probed
# (#306), never product copy and never translated. Contrast what the previous
# revision tested, the sentence "Reply to this message to answer in-game",
# which is product copy and was the identity check.
RELAY_DM_MAX = 2000
RELAY_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RELAY_CODE_LEN = 12
_CODE_BODY = "[0-9A-HJKMNP-TV-Z]{%d}" % RELAY_CODE_LEN
# The ONE definition of "this message names a thread".
RELAY_CODE_RE = re.compile(r"(?m)^-# \u21a9 (SCR-" + _CODE_BODY + r")[ \t]*$")
# "this message is one of ours and MENTIONS a thread without naming one" --
# the pick-a-thread listing, whose text contains several codes and must never
# be read as naming any of them.
RELAY_CODE_ANY_RE = re.compile(r"SCR-" + _CODE_BODY)


def mint_relay_code() -> str:
    return "SCR-" + "".join(secrets.choice(RELAY_CODE_ALPHABET)
                            for _ in range(RELAY_CODE_LEN))


def relay_code_line(code: str) -> str:
    return "\n-# \u21a9 %s" % code


def normalize_relay_code(s: str) -> str:
    """A code the PLAYER typed -> the stored form, or "" if it is not one.

    Crockford decoding: case-insensitive, and I/L read as 1 while O reads as
    0, because those are the substitutions a person makes when copying a code
    by eye. U is not in the alphabet and is deliberately NOT remapped -- it is
    simply not a code."""
    t = re.sub(r"[^0-9A-Z]", "", (s or "").strip().upper())
    if not t.startswith("SCR"):
        return ""
    t = t[3:].replace("I", "1").replace("L", "1").replace("O", "0")
    if len(t) != RELAY_CODE_LEN or any(c not in RELAY_CODE_ALPHABET for c in t):
        return ""
    return "SCR-" + t


# ── Resolution: one path, shared by the resolver and the listing ────────────
#
# One fragment so the two can never disagree about what is answerable (#412).
# A thread the listing offers is by construction one the resolver accepts.
_RELAY_ROW_FROM = (
    "  FROM pending_dms d"
    "  JOIN mail_messages m ON m.id = d.mail_id"
    "  JOIN players sp ON sp.id = m.sender_id"
    "  JOIN mail_recipients r ON r.message_id = d.mail_id"
    "                       AND r.recipient_id = CAST(:pid AS uuid)"
    " WHERE d.steam_id = :s AND d.mail_id IS NOT NULL"
    "   AND d.relay_code IS NOT NULL AND NOT d.undeliverable"
    "   AND d.cancelled_at IS NULL"
    "   AND r.delivery = 'delivered' AND r.deleted_at IS NULL")
# NO `d.delivered_at IS NOT NULL`. That predicate would re-create the
# send-to-ack window this design exists to remove: a reply sent two seconds
# after the DM lands must resolve, and the row is not acked yet. NOT
# undeliverable is kept -- a refused DM is one the player never saw, so its
# code is not one they can be quoting.
#
# NO time bound. The 24-hour window was a property of the GUESS, not of the
# authorization: the envelope check in main.py's _mail_reply_core (the read
# that loads `orig`) has no time bound either, and a year-old thread is
# still the player's thread.
# Once the player names the thread there is nothing for a window to protect.
#
# `d.cancelled_at IS NULL` is carried explicitly rather than left to
# `r.deleted_at IS NULL`, which already excludes the same rows today. Two
# reasons: the partial index idx_pending_dms_relay_recent is predicated on it
# and a query that does not state it cannot use the index, and the two
# columns are written by different paths, so relying on their agreement is
# relying on something no statement here enforces.

# LIMIT 2, and the caller requires exactly one. The unique index
# idx_pending_dms_relay_code makes two rows unreachable; this is what keeps
# it unreachable, rather than trusting that it is.
_REPLY_BY_CODE_SQL = ("SELECT d.mail_id" + _RELAY_ROW_FROM +
                      "   AND d.relay_code = :c LIMIT 2")

# The listing the refusal offers. This is PRESENTATION order, not identity:
# the player names the thread by tapping it, so ordering decides only what is
# shown first and can never decide what is answered.
_RELAY_THREADS_SQL = (
    "SELECT d.relay_code, m.subject, sp.display_name AS sender_name,"
    "       d.created_at"
    + _RELAY_ROW_FROM +
    " ORDER BY d.created_at DESC, d.id DESC LIMIT 5")

# What the reply ACTUALLY answered, read back from the committed reply's
# own in_reply_to rather than from the id this request resolved. An
# idempotent replay returns the ORIGINAL reply, which may answer a
# different mail than the one the recent-window branch would pick today --
# naming the latter told the player they had answered a mail they had not.
_REPLIED_TO_SQL = (
    "SELECT m.id, m.subject, p.display_name AS sender_name,"
    # The code of the thread that was ACTUALLY answered, so the bot's
    # confirmation carries a marker line of its own. Replying to the last
    # message in a DM conversation is what people do, and without this every
    # such reply would name no thread and be refused.
    "       (SELECT d.relay_code FROM pending_dms d"
    "         WHERE d.mail_id = m.id AND d.steam_id = :sid"
    "           AND d.relay_code IS NOT NULL AND NOT d.undeliverable"
    "         ORDER BY d.id DESC LIMIT 1) AS relay_code"
    "  FROM mail_messages rep"
    "  JOIN mail_messages m ON m.id = rep.in_reply_to"
    "  JOIN players p ON p.id = m.sender_id"
    " WHERE rep.id = CAST(:rid AS uuid)")

# The idempotency namespace, and the derivation as a function rather than
# an expression buried in the route: a structural pin could see a uuid5
# call and a namespace without either one reaching the key (Codex r2).
_REPLY_KEY_NS = "scr:mail-reply-from-discord:"


def reply_idempotency_key(source_message_id: str) -> str:
    """The key a Discord-originated reply is sent under.

    Discord may redeliver a message, and a reply can commit while its
    confirmation never reaches the player. Both are a repeat of the SAME
    message, so the key has to be a function OF that message: uuid5 over
    the message id collapses the repeat onto the original reply, where a
    fresh uuid4 per request made every retry a second in-game mail.

    Without a source there is nothing to be idempotent about, so the caller
    gets a unique key rather than a shared constant -- a constant would
    collapse UNRELATED replies onto the first one ever sent."""
    src = (source_message_id or "").strip()
    if not src:
        return str(uuid.uuid4())
    return str(uuid.uuid5(uuid.NAMESPACE_URL, _REPLY_KEY_NS + src))

RELAY_NAME_MAX = 64
RELAY_SUBJECT_MAX = 120
RELAY_BODY_MAX = 1500

RELAY_FOOTER = (
    "\n\n-# Reply to this message to answer in-game "
    "\u00b7 `/mail relay off` to stop these DMs")


def relay_dm_text(safe, *, sender_name: str, sender_steam_id: str,
                  subject: str, body: str, code: str) -> str:
    """The DM a relayed mail becomes. Every field is player-authored and is
    therefore hostile text (#253): `safe` neutralises mention syntax, code
    fences and angle brackets. The body keeps its line breaks -- a relayed
    mail collapsed onto one line is unreadable -- and the same neutralisation
    is applied either way, so nothing is escaped in one field and not
    another.

    The marker line is LAST and the bot sends `content[:2000]`, so the body
    budget is computed from the assembled head, footer and marker rather than
    asserted afterwards. A raised RELAY_BODY_MAX, a longer footer or a new
    locale then shortens the BODY -- which the player still has in full in
    game -- instead of truncating the marker, which is not recoverable at all
    and would leave the DM promising a reply route it cannot honour."""
    line = relay_code_line(code)
    head = ("\U0001f4ec **New in-game mail** from "
            "**%s** (`%s`)\n"
            "**%s**\n\n" % (
                safe(sender_name or "?", RELAY_NAME_MAX),
                sender_steam_id or "?",
                safe(subject or "(no subject)", RELAY_SUBJECT_MAX)))
    budget = RELAY_DM_MAX - len(head) - len(RELAY_FOOTER) - len(line)
    return (head
            + safe(body or "", max(0, min(RELAY_BODY_MAX, budget)), keep_lines=True)
            + RELAY_FOOTER + line)


async def queue_mail_relay(db: AsyncSession, *, mail_id, sender_name: str,
                           sender_steam_id: str, subject: str,
                           body: str) -> int:
    """Queue a Discord DM for every recipient who actually received this
    mail and has the relay on. Runs INSIDE the send transaction and does not
    commit: a mail that rolls back queues nothing, and a mail that commits
    always has its DMs queued. Returns the number of rows queued.

    Never raises into the send path. A relay is an extra; a failure here
    must not fail the mail itself, which is already durable in the same
    transaction -- so the caller keeps its mail and this returns -1."""
    try:
        safe = _BOUND.get("discord_safe")
        if safe is None:
            return -1
        # Mint, THEN compose. One local feeds both the DM text and the bind,
        # so the code stored on the row and the code the player can see are
        # the same object rather than two derivations that agree today.
        for attempt in (1, 2):
            code = mint_relay_code()
            content = relay_dm_text(
                safe, sender_name=sender_name, sender_steam_id=sender_steam_id,
                subject=subject, body=body, code=code)
            # SAVEPOINT, not a bare try/except. PostgreSQL aborts the WHOLE
            # transaction on a failed statement, so catching the exception
            # without one leaves a dead transaction and the caller's COMMIT
            # of the mail itself then fails -- i.e. the handler written to
            # protect the mail would be the thing that lost it.
            # begin_nested() rolls back to the savepoint and leaves the outer
            # transaction usable, so the docstring above states a property
            # rather than an intention. It is also what makes the retry below
            # possible: a unique violation aborts the savepoint, not the mail.
            try:
                async with db.begin_nested():
                    res = await db.execute(
                        text(_RELAY_FANOUT_SQL),
                        {"content": content, "mid": str(mail_id), "code": code})
                return res.rowcount or 0
            except IntegrityError:
                # Named rather than folded into the handler below, because
                # that one returns -1, which is indistinguishable from "no
                # recipient has the relay on" -- this case would otherwise
                # ship a mail with no DM and no signal anywhere.
                print("[MAIL-RELAY] CODE COLLISION mail=%s attempt=%d"
                      % (mail_id, attempt))
                if attempt == 2:
                    raise
    except Exception as ex:
        # A silently unqueued DM is otherwise indistinguishable from a
        # recipient with no linked Discord, so the mail id goes in the line.
        print("[MAIL-RELAY] QUEUE FAILED mail=%s: %s" % (mail_id, ex))
        return -1


# ── Inbound ───────────────────────────────────────────────────────────────

class _ReplyFromDiscord(BaseModel):
    discord_id: str = Field("", max_length=32)
    # The thread the player named. This is the ONLY way a target is chosen.
    # `dm_message_id`, `mail_id` and `use_recent` are gone with the ladder
    # they fed: a Discord message id could only be recorded after the message
    # existed, and `use_recent` answered "which thread?" with "the newest
    # one", which is arrival time used as identity (#174).
    relay_code: str = Field("", max_length=24)
    # The Discord message that TRIGGERED this reply (H5). Discord can
    # redeliver a message, and a reply can commit while its confirmation
    # never reaches the player -- both are a repeat of the SAME message and
    # must collapse onto one in-game reply.
    source_message_id: str = Field("", max_length=32)
    body: str = ""
    idempotency_key: str = Field("", max_length=64)


@router.post("/api/v1/internal/mail/reply-from-discord", tags=["Internal"])
async def mail_reply_from_discord(
    req: _ReplyFromDiscord,
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Bot-only. The bot forwards the Discord actor id; the actor is resolved
    HERE from `players.discord_id` and never trusted from the request body
    (#545). `discord_id` is UNIQUE (sql/008:16), which is what makes that
    resolution single-valued.

    The reply then runs `_mail_reply_core` -- the identical function the
    in-game route runs -- so blocks, the sender gates, the censor, the
    length rules, the recipient cap, the rate window and the idempotency
    key all apply exactly as they do in game. The only thing this route
    does differently is how it learns who is speaking, and that `via` is
    recorded as 'discord'."""
    expected = _BOUND.get("internal_key")
    expected = expected() if callable(expected) else expected
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")

    did = (req.discord_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="discord_id_required")

    me = (await db.execute(text(
        "SELECT id, steam_id, display_name, mod_seen_at, mail_from"
        "  FROM players WHERE discord_id = :d"
    ), {"d": did})).mappings().first()
    if me is None:
        raise HTTPException(status_code=404, detail="not_linked")
    me = dict(me)

    # ONE path. The player named a thread or they did not; there is no
    # ladder, no fallback and no third branch, because every additional way
    # of arriving at a target was another way of arriving at the WRONG one.
    # `_mail_reply_core` is deliberately NOT modified: its envelope check
    # still answers "may this player write here", which is the only question
    # it was ever able to answer. Which thread is answered is settled here,
    # before it is called.
    code = normalize_relay_code(req.relay_code)
    if not code:
        raise HTTPException(status_code=400, detail="target_required")
    rows = (await db.execute(text(_REPLY_BY_CODE_SQL),
                             {"c": code, "s": me["steam_id"],
                              "pid": str(me["id"])})).mappings().all()
    if len(rows) != 1:
        # Zero is a code that names no thread of this player's. Two is
        # unreachable while idx_pending_dms_relay_code exists, and is
        # refused rather than resolved so that it stays unreachable instead
        # of silently becoming "pick one".
        raise HTTPException(status_code=404, detail="unknown_code")
    mail_id = str(rows[0]["mail_id"])

    key = (req.idempotency_key or "").strip()
    src = (req.source_message_id or "").strip()
    if not key and not src:
        # Neither a key nor anything to derive one from. Minting a uuid4
        # here would make a retry of this very request a second in-game
        # reply, which is the defect the derivation exists to prevent --
        # so the request is refused rather than quietly made unsafe.
        raise HTTPException(status_code=400, detail="idempotency_source_required")
    key = key or reply_idempotency_key(src)
    reply_core = _need("reply_core")
    out = await reply_core(
        db, me, message_id=mail_id, body=req.body, reply_all=False,
        idempotency_key=key, via="discord")
    out = dict(out or {})
    # Read the thread AFTER the send, from the reply's own in_reply_to. The
    # core may have returned an EARLIER reply under the same key, and that
    # reply's parent -- not the id resolved above -- is what the player
    # actually answered. Naming the resolved id told a player who retried a
    # lost confirmation that they had answered a mail they had not.
    #
    # Wrapped, because it runs after the reply has COMMITTED: letting a
    # transient failure here become a 500 tells the player their reply did
    # not send when it did, and their retry arrives with a new Discord
    # message id and therefore a new key -- a duplicate mail caused
    # entirely by the cosmetic half of the response.
    ctx = None
    rid = str((out or {}).get("id") or "")
    if rid:
        try:
            ctx = (await db.execute(
                text(_REPLIED_TO_SQL),
                {"rid": rid, "sid": me["steam_id"]})).mappings().first()
        except Exception as ex:
            print("[MAIL-RELAY] replied_to lookup failed for %s: %s" % (rid, ex))
    safe = _need("discord_safe")
    out["replied_to"] = {
        # Escaped here, not in the bot: these are player-authored and the
        # bot interpolates them into markdown. Same helper as the DM text,
        # so no caller of this surface is more permissive than another.
        "subject": safe((ctx["subject"] if ctx else "") or "", RELAY_SUBJECT_MAX),
        "sender_name": safe((ctx["sender_name"] if ctx else "") or "", RELAY_NAME_MAX),
        # False when the thread could not be read back at all -- the bot
        # must not print "replied to them - (no subject)" as if it knew.
        "known": ctx is not None,
        # The thread this reply actually answered, so the bot's confirmation
        # carries a marker line and can itself be replied to. Read from the
        # COMMITTED reply's own in_reply_to, so an idempotent replay names
        # the thread that was answered rather than the one this request
        # asked about. Empty when the thread was never relayed to this
        # player -- a reply sent in game, for instance.
        "relay_code": (ctx["relay_code"] if ctx else "") or "",
    }
    # `inferred` is gone from this response with the branch that set it. It
    # reported whether the route had chosen the target on the player's
    # behalf; nothing does that any more, so a flag answering the question
    # would be describing a state that cannot occur.
    return out


# ── The pick-a-thread listing a refusal offers ────────────────────────────

class _RelayThreadsReq(BaseModel):
    discord_id: str = Field("", max_length=32)


@router.post("/api/v1/internal/mail/relay-threads", tags=["Internal"])
async def mail_relay_threads(
    req: _RelayThreadsReq,
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Bot-only: the threads a reply could be naming, newest first.

    This is what makes the refusal affordable. A reply that names no thread
    is refused rather than guessed, and the cost of that refusal is one tap
    -- but only because this exists to tap (#430: a guard is judged by what
    its refusal costs).

    POST rather than GET: the Discord id is personal data and does not belong
    in a query string or an access log, and this matches the internal-key,
    server-side-actor-resolution shape of the two routes beside it (#545).
    The caller forwards only the Discord id; the player is resolved here from
    `players.discord_id`, which is UNIQUE (sql/008:16).

    Ordering here is PRESENTATION only. The player names the thread by
    tapping it, so nothing in this list can decide what gets answered --
    which is exactly the property the deleted recency branch did not have."""
    expected = _BOUND.get("internal_key")
    expected = expected() if callable(expected) else expected
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
    did = (req.discord_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="discord_id_required")

    me = (await db.execute(text(
        "SELECT id, steam_id FROM players WHERE discord_id = :d"
    ), {"d": did})).mappings().first()
    if me is None:
        raise HTTPException(status_code=404, detail="not_linked")

    rows = (await db.execute(text(_RELAY_THREADS_SQL),
                             {"s": me["steam_id"],
                              "pid": str(me["id"])})).mappings().all()
    safe = _need("discord_safe")
    return {"threads": [{
        "relay_code": r["relay_code"],
        # The SAME neutralisation the DM text uses. These are player-authored
        # and the bot interpolates them into markdown and into button labels,
        # so a surface that escaped them differently would be the permissive
        # one (#412).
        "subject": safe(r["subject"] or "", RELAY_SUBJECT_MAX),
        "sender_name": safe(r["sender_name"] or "", RELAY_NAME_MAX),
        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
    } for r in rows]}


# ── Relay preference, read and written by the bot's /mail relay command ───

# Turning the relay OFF withdraws what is still queued. Defined here and used
# from BOTH toggle sites -- this route and the client's mail-settings PUT in
# main.py -- because the same statement written out twice in two files is the
# drift this project has already paid for (#329/#341).
#
# Undelivered only: a DM already sent is out, and the row has to survive so
# the code in that DM still resolves. Cancelling rather than deleting is the
# same reasoning as the mail-delete path.
RELAY_OFF_CANCEL_SQL = (
    "UPDATE pending_dms SET cancelled_at = NOW(),"
    "       claim_id = NULL, claim_until = NULL"
    " WHERE steam_id = :sid AND mail_id IS NOT NULL"
    "   AND delivered_at IS NULL AND cancelled_at IS NULL")


class _RelayPrefReq(BaseModel):
    discord_id: str = Field("", max_length=32)
    enabled: bool = True


@router.post("/api/v1/internal/mail/relay-pref", tags=["Internal"])
async def mail_relay_pref(
    req: _RelayPrefReq,
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Bot-only: `/mail relay on|off`. Same server-side actor resolution as
    the reply route. This exists so a 1.40.3 player can turn the relay off
    today, without waiting for the 1.41.0 client's Mail settings row."""
    expected = _BOUND.get("internal_key")
    expected = expected() if callable(expected) else expected
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
    did = (req.discord_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="discord_id_required")
    row = (await db.execute(text(
        "UPDATE players SET mail_discord_relay = :v WHERE discord_id = :d"
        " RETURNING steam_id"
    ), {"v": bool(req.enabled), "d": did})).first()
    if row is None:
        raise HTTPException(status_code=404, detail="not_linked")
    withdrawn = 0
    if not req.enabled:
        # The preference alone only ever governed rows the fan-out had yet
        # to create. Anything already queued was still DMed.
        withdrawn = (await db.execute(
            text(RELAY_OFF_CANCEL_SQL), {"sid": row[0]})).rowcount or 0
    await db.commit()
    return {"discord_relay": bool(req.enabled), "withdrawn": withdrawn}
