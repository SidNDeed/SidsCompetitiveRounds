"""Opt-in automatic log upload after a match — SERVER HALF (v1.41.0, Item 3).

WHAT THIS IS. One authenticated write route, ``POST /api/v1/logs/auto``, that
takes the same log bundle the F5 bug form already sends and stores it as an
ordinary ``bug_reports`` row carrying ``kind = 'auto'``. Everything downstream
— the admin list, the detail view, the download endpoint's read-time scrub and
the ops ``bug-log:N`` verb — reads ``bug_reports`` and therefore works on these
rows with no change at all. That reuse is the whole point of storing them here
rather than in a table of their own.

NO CLIENT CALLS IT IN THIS RELEASE. The client half (the Data & Privacy
setting, the ``OnLeftRoom`` trigger, the client-side path scrub) is owned by
another session's lifecycle work and is not in this batch. This module is
therefore INERT on arrival: deployable, authenticated, rate-limited, tested,
and with no caller.

  Inert is a known way to ship nothing while every log line looks perfect
  (#438, #443). So this route emits a POSITIVE signal rather than relying on
  the absence of errors: every accepted upload prints exactly one
  ``[AUTO-LOG] #`` LANDING line, naming the bug number, the raw and stored
  sizes and the write-time scrub's own counters, and returns those same
  counters in the response body. Not one line in total -- an accepted upload
  whose opportunistic prune fires also prints a prune line, so the invariant
  is one landing record per acceptance, not one prefixed line per request. ``[AUTO-LOG]`` exists for no other purpose in this repo, so
  grepping the api log for it answers "has a client ever reached this route"
  with a yes or a no and nothing in between (#306). Two greps, because the
  prefix is also on the refusal lines and that distinction is the useful one:
  ``[AUTO-LOG] #`` is an upload that LANDED, and a bare ``[AUTO-LOG]`` is the
  route being reached at all. Until the second one appears in production, the
  correct reading is that the feature has never run — not that it is working
  quietly.

WHAT LEAVES THE MACHINE, AND WHAT IS REMOVED BEFORE IT IS STORED. The bundle
is the client's own log text. The client interpolates ABSOLUTE log paths into
its bundle header, so every bundle carries ``C:\\Users\\<person>\\...``. The
bug-report pipeline scrubs that at READ time only, which is enough for the
HTTP download endpoint and NOT enough for the ops ``bug-log:`` verb, which
plain-``zcat``s the stored blob. An auto upload is not something a player
chose to send one at a time, so it is scrubbed at WRITE time as well: the blob
on disk has already been through ``main._scrub_pass_one`` (OS usernames in
Windows and POSIX path shapes, plus Discord snowflakes) before it is gzipped.
The read-time scrub still runs on top and is unaffected — the passes are
idempotent, and the second one is what redacts deleted accounts' SteamID64s,
which is a database question this path deliberately does not ask.

  The scrub is IMPORTED from main, never re-implemented here. Two copies of a
  privacy rule are two readings of one question, and they diverge (#432).

FAILURE DIRECTION. An auto upload exists only to carry its log, so a row
without one is noise an admin has to triage. The blob is therefore written
BEFORE the row is inserted, under an id this module generates, and every
DETERMINATE failure leaves neither artifact: a failed write unlinks its own
partial file, a failed INSERT unlinks the blob it just wrote. The client is
told 503 in both cases and can try again after the next match.

  THE ONE CASE THAT CANNOT BE MADE ATOMIC is a ``commit()`` that raises. That
  is indeterminate, not failed -- PostgreSQL may have committed and the
  acknowledgement been lost on the way back -- so the blob is deliberately
  KEPT and its id printed. Deleting it is irreversible and, when the row did
  commit, destroys the only copy of the log that row promises, which presents
  to the next admin as corruption rather than as a failed upload. An orphan
  blob only costs disk. Cheap reversible error over expensive irreversible
  one (#276). Nothing collects such a blob -- ``prune_auto_logs`` unlinks only
  files named by rows it is deleting -- so the printed id is the whole of the
  recovery story, and that is a deliberate trade rather than an oversight.

  An earlier version of this paragraph claimed atomicity across both halves
  unconditionally. It was false of the write arm, which raised without
  unlinking, and it was not achievable across the commit at all.

RETENTION REQUIRES A SWEEP TO RUN -- it does not expire on its own, and an
earlier version of this paragraph claimed the opposite. Nothing deletes a
bug_reports row by age by itself: no reader filters on created_at for
retention, and the only collector is ``prune_auto_logs``, reached either
opportunistically after an ACCEPTED upload (at most hourly) or from the
internal route. So the corpus is bounded only while uploads keep arriving,
and if every client vanishes the last cohort of rows and blobs persists
indefinitely -- the exact case the old wording called safe. The #276 citation
was pointed backwards: #276 is about failure DIRECTION, where an expiring
design lapses because nothing renews it and a blocking one needs a positive
cleanup that always runs. A sweep that must be invoked is the second kind, so
#276 is the reason to be uneasy about this design rather than the reason it is
fine. Wiring the sweep into the janitor is the fix and is not done here (see
below). ``prune_auto_logs`` deletes the ROW first and the file second. The reverse order would leave, for the width of the window, a row
advertising a log that is already gone — and that exact state has needed a
migration here before: backend/sql/087_clear_orphaned_bug_logs.sql exists
because rows pointed at blobs the container had discarded and the admin
viewer kept showing a [log] tag over empty content. An orphan FILE is the
cheaper failure: nothing reads it and nothing claims it exists.

NOT WIRED INTO THE JANITOR. The plan asks for the retention sweep to run from
main.py's janitor; that is a main.py body edit this batch's ownership table
does not grant Item 3, so it is not done here. Instead the prune runs
opportunistically after an accepted upload (at most hourly) and is exposed as
``POST /api/v1/internal/logs/auto/prune`` for an operator or the bot. The gap
this leaves is bounded and stated plainly: if uploads stop entirely, the last
cohort of rows is never collected until something calls the internal route.

NOT A REPLICA-ROUTABLE PATH. The blob is written to the api container's own
disk. If this path were ever added to the edge's read-routing list, uploads
would land on whichever box answered and ``bug-log:`` on the primary would not
find them. It is a POST, so today's routing (heavy READS to the standby) does
not touch it; this note is here so that stays deliberate.
"""

import asyncio
import gzip
import hashlib
import json
import os
import pathlib
import time
import uuid
from datetime import datetime, timedelta, timezone

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import BUG_REPORT_LOG_MAX_CHARS

router = APIRouter(prefix="/api/v1/logs", tags=["Auto Logs"])

# Its own 24 h bucket, counted over kind='auto' rows only, so an auto upload
# can never spend a player's 10-reports-a-day budget and a player at their
# report cap can still have logs arrive. The separation only holds because
# submit_bug_report's own count is scoped to kind='report' — the two halves
# are one change and neither works alone.
AUTO_LOG_PER_STEAM_PER_DAY = 12

# Sid's answer (a) in the plan: 14 days. Bug reports keep their no-retention
# posture; this applies to kind='auto' rows and nothing else.
AUTO_LOG_RETENTION_DAYS = 14

# Read ceiling for the raw request body, ahead of any parsing. It is tighter
# than the 16 MB header gate in main's rate_limit_gate and it is NOT strictly
# looser than the 12 M CHARACTER clamp, which an earlier version of this
# comment claimed. The two measure different things and neither dominates: a
# 12 M character log of single-byte text is ~12 MB and passes here, while 12 M
# two-byte characters is ~24 MB and is refused by THIS gate before the
# character clamp is ever consulted. So for non-Latin logs the byte ceiling is
# the binding one. That is acceptable -- both are refusals, and a client
# sending 12 M characters of CJK is not a case this route needs to serve --
# but it should not be described as the looser of the two.
AUTO_LOG_MAX_BODY_BYTES = 14 * 1024 * 1024

# At most one opportunistic prune an hour per process, on a monotonic clock so
# a wall-clock correction cannot stall or stampede it.
_PRUNE_MIN_INTERVAL_S = 3600.0
_LAST_PRUNE = [0.0]


# The widths are the DATABASE's, per column, not one number for all of them:
# bug_reports.steam_id is VARCHAR(32), display_name VARCHAR(64), mod_version
# and game_version VARCHAR(32) (backend/sql/083_bug_reports.sql). Clamping
# every short field to a single 64 -- which is what BugReportRequest does --
# leaves a value that passes validation and then fails the INSERT with "value
# too long", i.e. a 500 on a request the model said was fine. Module level
# rather than a class attribute because a leading-underscore name inside a
# pydantic BaseModel is a private attribute, not a plain dict.
_FIELD_WIDTHS = {"steam_id": 32, "display_name": 64, "mod_version": 32,
                 "game_version": 32, "mode": 64, "room_name": 64,
                 "opponent_steam_id": 32, "series_id": 64}


class AutoLogRequest(BaseModel):
    """The auto-upload body.

    Deliberately NOT ``BugReportRequest``: that model requires a non-empty
    ``description``, and an auto upload's description is written by the server
    from the match context rather than supplied by the client. What the two
    share is the log CEILING, which is imported from schemas rather than
    restated here. The plan pointed at the wrong validator for it — a line
    range spanning ``_clamp_short`` (64 characters, the identity fields) and
    the head of ``_clamp_text`` (8000, the free-text fields) — and either of
    those applied to ``log_text`` would have been a working, authenticated,
    rate-limited endpoint that stored nothing a person could debug from.
    """

    steam_id: str = Field(..., max_length=32)
    display_name: str | None = Field(None, max_length=64)
    mod_version: str | None = Field(None, max_length=32)
    game_version: str | None = Field(None, max_length=32)
    # Match context. None of these has a column on bug_reports — and the bug
    # form does not fill any either, contrary to the plan's "the room/opponent/
    # series fields the bug form already fills"; that table has exactly the
    # columns in backend/sql/083_bug_reports.sql and no more. They are rendered
    # into description and repro_steps below, which is where the bug form puts
    # its own context too.
    mode: str | None = Field(None, max_length=64)
    room_name: str | None = Field(None, max_length=64)
    opponent_steam_id: str | None = Field(None, max_length=32)
    series_id: str | None = Field(None, max_length=64)
    log_text: str | None = None      # no Pydantic cap — clamped to the tail below

    @field_validator("steam_id", "display_name", "mod_version", "game_version",
                     "mode", "room_name", "opponent_steam_id", "series_id",
                     mode="before")
    @classmethod
    def _clamp_short(cls, v, info):
        # Truncate rather than 422, for the same reason BugReportRequest does:
        # a hard max_length makes FastAPI reject the whole upload before the
        # handler runs, and an automatic upload has no user to retry it.
        width = _FIELD_WIDTHS.get(info.field_name, 32)
        if isinstance(v, str) and len(v) > width:
            return v[:width]
        return v

    @field_validator("log_text", mode="before")
    @classmethod
    def _clamp_log(cls, v):
        # Keep the TAIL: the events nearest the end of the match are the ones
        # worth having. Same ceiling as the bug-report bundle, imported from
        # schemas so the two cannot drift apart.
        if isinstance(v, str) and len(v) > BUG_REPORT_LOG_MAX_CHARS:
            return v[-BUG_REPORT_LOG_MAX_CHARS:]
        return v


def _context_block(req: "AutoLogRequest") -> str | None:
    """The match context, as the labelled text block that goes in repro_steps."""
    parts = []
    for label, value in (("mode", req.mode), ("room", req.room_name),
                         ("opponent", req.opponent_steam_id), ("series", req.series_id),
                         ("game_version", req.game_version)):
        if value:
            parts.append(f"{label}: {value}")
    if not parts:
        return None
    return "automatic upload context\n" + "\n".join(parts)


async def _read_capped_body(request: Request, cap: int) -> bytes:
    """Read the body with a hard ceiling, streaming.

    The Content-Length header is checked first because it is free, and the
    stream is capped anyway because a chunked request does not send one. This
    runs AFTER the session-token presence check in the handler, which is the
    part that matters: FastAPI resolves a declared body parameter by buffering
    and JSON-parsing it before the handler's first line, so a handler-level
    auth check cannot stop an unauthenticated client from making the process
    materialize megabytes (#388). This route declares no body parameter for
    exactly that reason.
    """
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > cap:
                print(f"[AUTO-LOG] refused 413: declared content-length {declared} over the {cap}-byte cap")
                raise HTTPException(status_code=413, detail="payload_too_large")
        except ValueError:
            pass
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > cap:
            print(f"[AUTO-LOG] refused 413: streamed body passed the {cap}-byte cap")
            raise HTTPException(status_code=413, detail="payload_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def _discard_blob(path):
    """Remove a blob this request wrote, for a failure that is KNOWN to have
    left no row pointing at it.

    Deliberately not used on the commit arm: see FAILURE DIRECTION. An absent
    file is the expected outcome when the write itself failed, so a missing
    file is not an error.
    """
    if path is None:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


@router.post("/auto")
async def upload_auto_log(request: Request, db: AsyncSession = Depends(get_db)):
    """Store one post-match log bundle as a kind='auto' bug_reports row.

    Authentication is the STRICT session check, not the soft write-path gate:
    this route creates a disk artifact attributed to a Steam ID, so a claimed
    id that cannot be proven must not be able to write one. ``_strict_steam_session_ok``
    fails closed on every path — missing token, unknown/expired/unverified
    session, id mismatch, database error — and has no soft carve-out.
    """
    from main import (            # late import: main imports this module
        _strict_steam_session_ok,
        _bug_report_log_path,
        _scrub_pass_one,
    )

    # Before a byte of the body is read -- and the check is the REAL one, not
    # a presence test. A non-empty header satisfied the old gate, so a request
    # carrying any string at all was streamed, joined, decoded and JSON-parsed
    # up to AUTO_LOG_MAX_BODY_BYTES (14 MiB) before the session was looked up
    # at all: the full cost paid on behalf of a caller the handler was always
    # going to refuse. token_hash is UNIQUE on steam_sessions, so resolving the
    # token first costs one indexed row.
    #
    # This does NOT move the authorization decision, and must not be read as
    # doing so. `_strict_steam_session_ok` below still runs against the
    # steam_id the BODY claims, still owns the verdict (#432), and still
    # decides the one case this cannot see: a valid token naming a DIFFERENT
    # account than the body does. All that moves earlier is the refusal of a
    # request that could never have been accepted either way. Same shape as
    # `_mail_canonical_ids` in main.py, which resolves the token and then
    # defers to the same helper rather than re-deciding the question.
    _token = request.headers.get("X-Session-Token")
    if not _token:
        print("[AUTO-LOG] refused 401: no X-Session-Token header")
        raise HTTPException(status_code=401, detail="session required")
    _bound = (await db.execute(text(
        "SELECT steam_id FROM steam_sessions WHERE token_hash = :th"
    ), {"th": hashlib.sha256(_token.encode()).hexdigest()})).mappings().first()
    if _bound is None or not await _strict_steam_session_ok(
            request, _bound["steam_id"], db):
        print("[AUTO-LOG] refused 401: token is not a known, unexpired, "
              "verified session -- body not read")
        raise HTTPException(status_code=401, detail="session required")

    raw = await _read_capped_body(request, AUTO_LOG_MAX_BODY_BYTES)
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as ex:
        # LOUD, because this is the refusal the client half is most likely to
        # hit first. Python's decoder is strict about raw control characters
        # inside a string, and the client builds this JSON by hand: bug #31
        # was exactly this on the bug-report path -- a raw TAB/NUL/ESC
        # anywhere in an attached log made the whole submit 422 before any
        # validator ran, and the fix was ApiClient.JsonEscapeFull escaping
        # every char below 0x20 (#100). The ceiling is NOT relaxed here to
        # compensate: the two paths must accept the same bundle, and a server
        # that quietly tolerated unescaped logs would hide the client defect
        # on one of them.
        print(f"[AUTO-LOG] malformed body ({len(raw)} bytes) from a caller with a session token: {ex}")
        raise HTTPException(status_code=400, detail="malformed body")
    if not isinstance(payload, dict):
        print(f"[AUTO-LOG] refused 400: body parsed as {type(payload).__name__}, not an object")
        raise HTTPException(status_code=400, detail="malformed body")
    try:
        req = AutoLogRequest.model_validate(payload)
    except ValidationError as ex:
        # A ValidationError raised INSIDE a handler is not the one FastAPI's
        # dependency system turns into a 422 -- uncaught it is a 500, which
        # tells a client to retry a body that will never be accepted. The only
        # way to reach this is a missing or non-string steam_id, since every
        # other field is optional and every over-long one is truncated.
        print(f"[AUTO-LOG] refused 422: {ex.error_count()} invalid field(s), most likely a missing steam_id")
        raise HTTPException(status_code=422, detail=f"invalid body: {ex.error_count()} field(s)")

    if not await _strict_steam_session_ok(request, req.steam_id, db):
        # The loudest of the refusals, because it is the one a healthy
        # deployment is most likely to sit on: sessions are minted with
        # verified=False whenever the Steam ticket cannot be validated, and
        # the attestation verdict fails closed on unverified/expired/unknown.
        # A client half with a slightly wrong token lifetime produces zero
        # rows forever, and without this line the api log is indistinguishable
        # from one where no client has ever called the route (#438/#443).
        print(f"[AUTO-LOG] refused 401: session check failed for {req.steam_id}")
        raise HTTPException(status_code=401, detail="session required")

    log_blob = (req.log_text or "").strip()
    if not log_blob:
        # A log upload with no log is not a degenerate success. Refusing it
        # keeps the corpus free of rows whose only content is their own
        # existence, and tells a miswired client something is wrong.
        print(f"[AUTO-LOG] refused 400: empty log_text from {req.steam_id}")
        raise HTTPException(status_code=400, detail="log_text required")

    # Serialise count-then-insert FOR THIS ACCOUNT. What follows is an
    # unlocked COUNT and, a good way further down, an INSERT; two uploads from
    # one steam_id that both observe 11 rows both commit and the cap lands at
    # 13. There is no row to take FOR UPDATE here -- the row being counted is
    # the one about to be written -- which is exactly the case the repo keys an
    # advisory lock on a VALUE for (#202/#203/#207; main.py takes the same lock
    # in steam_auth and _enrollment_identity_gate). Held to commit, keyed per
    # account, so it serialises one player's concurrent uploads and touches
    # nobody else's.
    #
    # It is taken BEFORE the count deliberately: after it, the second caller
    # would already have read a stale number and the lock would protect
    # nothing.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:sid))"),
                     {"sid": req.steam_id})

    # Own bucket, own predicate. `kind = 'auto'` is what makes this a separate
    # budget rather than a second reader of the report budget.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = await db.execute(
        text("SELECT COUNT(*) FROM bug_reports "
             "WHERE steam_id = :sid AND kind = 'auto' AND created_at >= :cutoff"),
        {"sid": req.steam_id, "cutoff": cutoff},
    )
    if (recent.scalar() or 0) >= AUTO_LOG_PER_STEAM_PER_DAY:
        print(f"[AUTO-LOG] refused 429: {req.steam_id} at the {AUTO_LOG_PER_STEAM_PER_DAY}/24h cap")
        raise HTTPException(
            status_code=429,
            detail=f"Limit is {AUTO_LOG_PER_STEAM_PER_DAY} automatic uploads per 24h",
        )

    player_row = (await db.execute(
        text("SELECT id FROM players WHERE steam_id = :sid"), {"sid": req.steam_id},
    )).mappings().first()

    # Write-time scrub, in a worker thread. The counters it returns are the
    # positive signal that the scrub RAN, as opposed to matched nothing:
    # os_user == 0 on a Windows bundle means the header shape changed, not
    # that the bundle was clean.
    scrubbed, counts, _ids = await asyncio.to_thread(_scrub_pass_one, log_blob)

    report_id = uuid.uuid4()
    data = gzip.compress(scrubbed.encode("utf-8", errors="replace"))

    # Do not accept what the reader cannot serve. The body cap above is 14 MiB
    # of REQUEST; this is the ceiling the STORED blob has to satisfy, and a
    # high-entropy log that fits the first can gzip past the second. Accepting
    # one produces a row whose detail view reports a read error and whose
    # download answers 413 -- an upload that reported success and landed as an
    # unreadable artifact. IMPORTED from main rather than restated, for the
    # same reason the scrub is: two copies of one limit are two readings of one
    # question and they drift (#432). The late import also means a test can
    # move the reader's ceiling and see this follow it.
    from main import _BUG_LOG_MAX_GZ
    if len(data) > _BUG_LOG_MAX_GZ:
        print(f"[AUTO-LOG] refused 413: {req.steam_id} compressed to "
              f"{len(data)} bytes, over the reader's {_BUG_LOG_MAX_GZ}-byte "
              f"ceiling -- stored, it would be undownloadable")
        raise HTTPException(status_code=413,
                            detail="log too large once compressed")
    # The path resolution is INSIDE the try, not before it: _bug_report_log_path
    # creates the directory, so an unusable BUG_REPORT_LOG_DIR fails there and
    # not at open(). Outside the try that becomes a 500, and 500 vs 503 is not
    # cosmetic here -- the client half is a background retry loop, and 503 is
    # the code that says the same request will work later.
    path = None
    try:
        path = _bug_report_log_path(str(report_id))
        with open(path, "wb") as f:
            f.write(data)
    except Exception as ex:
        # Unlink whatever landed. `open()` succeeding and `write()` failing --
        # a full disk, a dying volume -- leaves a partial or empty file under
        # an id that no row will ever name, and nothing in this module or the
        # prune can find it again. `path` is None only if the directory
        # resolution itself raised, in which case there is nothing to remove.
        _discard_blob(path)
        print(f"[AUTO-LOG] blob write failed for {report_id}: {type(ex).__name__}")
        raise HTTPException(status_code=503, detail="log storage unavailable")

    room = req.room_name or "an unnamed room"
    description = f"auto-upload after {req.mode or 'a match'} in {room}"
    try:
        row = (await db.execute(
            text("""INSERT INTO bug_reports
                        (id, player_id, steam_id, display_name, mod_version, game_version,
                         severity, category, kind, description, repro_steps,
                         log_filename, log_bytes, status)
                    VALUES
                        (CAST(:id AS uuid), CAST(:pid AS uuid), :sid, :name, :mv, :gv,
                         'low', 'other', 'auto', :descr, :repro,
                         :fname, :fbytes, 'open')
                 RETURNING bug_number"""),
            {
                "id": str(report_id),
                "pid": str(player_row["id"]) if player_row else None,
                "sid": req.steam_id,
                "name": req.display_name,
                "mv": req.mod_version,
                "gv": req.game_version,
                "descr": description,
                "repro": _context_block(req),
                "fname": path.name,
                "fbytes": len(data),
            },
        )).mappings().first()
    except Exception as ex:
        # The INSERT raised, so there is DEFINITIVELY no row and the only thing
        # that could ever find this blob again does not exist. Remove it. The
        # rollback is explicit because under asyncpg a caught statement error
        # leaves the whole transaction ABORTED, and the next statement on this
        # session -- the opportunistic prune, or anything a later dependency
        # runs -- would raise on that and not on its own fault.
        _discard_blob(path)
        try:
            await db.rollback()
        except Exception:
            pass
        print(f"[AUTO-LOG] insert failed for {report_id}: "
              f"{type(ex).__name__}; blob discarded")
        raise HTTPException(status_code=503, detail="log storage unavailable")

    try:
        await db.commit()
    except Exception as ex:
        # INDETERMINATE -- see FAILURE DIRECTION at the top. The blob STAYS.
        # This is the one arm that deliberately leaves an artifact behind, and
        # removing the `_discard_blob` call from it is the mutation that turns
        # a lost acknowledgement into a destroyed log.
        try:
            await db.rollback()
        except Exception:
            pass
        print(f"[AUTO-LOG] commit INDETERMINATE for {report_id}: "
              f"{type(ex).__name__}; blob KEPT as {path.name} -- a row may or "
              f"may not exist for it")
        raise HTTPException(status_code=503, detail="log storage unavailable")

    bug_number = (row or {}).get("bug_number") or 0
    print(f"[AUTO-LOG] #{bug_number} ({report_id}) steam={req.steam_id} "
          f"mode={req.mode or '-'} raw_chars={len(log_blob)} stored_bytes={len(data)} "
          f"scrub os_user={counts.get('os_user', 0)} discord_id={counts.get('discord_id', 0)}")

    await _maybe_prune(db)

    return {
        "status": "received",
        "id": str(report_id),
        "bug_number": bug_number,
        "log_persisted": True,
        "log_bytes": len(data),
        "scrubbed": {"os_user": counts.get("os_user", 0),
                     "discord_id": counts.get("discord_id", 0)},
    }


async def prune_auto_logs(db: AsyncSession, *, days: int = AUTO_LOG_RETENTION_DAYS) -> dict:
    """Delete kind='auto' rows older than `days`, then their blobs.

    ONLY kind='auto'. The predicate is the whole safety property here: bug
    reports have no retention and this function must never be the thing that
    gives them one.

    `make_interval(days => CAST(:days AS integer))` rather than composing an
    interval from a string. The precise history, because the two learnings
    say different things: #275 is the trap itself — under asyncpg the
    surrounding expression types the bound parameter, and an array
    concatenation typed one as uuid[] and broke the FFA leave path in 100% of
    its invocations. It also records that `(:w || ' minutes')::interval`
    happens to be safe, because the text literal types the param. #448 is the
    RULING that followed: the one statement still using that form passed
    :mins to a string concatenation and to a numeric comparison in the same
    statement, and all new interval arithmetic uses the make_interval form
    regardless. This is new interval arithmetic, so it uses make_interval.
    """
    from main import BUG_REPORT_LOG_DIR

    rows = (await db.execute(
        text("""DELETE FROM bug_reports
                 WHERE kind = 'auto'
                   AND created_at < NOW() - make_interval(days => CAST(:days AS integer))
             RETURNING id::text AS id, log_filename"""),
        {"days": int(days)},
    )).mappings().all()
    await db.commit()

    unlinked = 0
    base = pathlib.Path(BUG_REPORT_LOG_DIR)
    for r in rows:
        name = r["log_filename"]
        if not name:
            continue
        try:
            (base / name).unlink()
            unlinked += 1
        except OSError:
            # An already-absent file is the expected outcome of a previous
            # half-finished sweep, not an error worth failing the pass for.
            pass
    if rows:
        print(f"[AUTO-LOG] prune removed {len(rows)} row(s) older than {days}d, "
              f"{unlinked} blob(s) unlinked")
    return {"rows": len(rows), "blobs": unlinked}


async def _maybe_prune(db: AsyncSession) -> None:
    """Opportunistic retention, throttled per process. Never fails an upload."""
    now = time.monotonic()
    if now - _LAST_PRUNE[0] < _PRUNE_MIN_INTERVAL_S:
        return
    _LAST_PRUNE[0] = now
    try:
        await prune_auto_logs(db)
    except Exception as ex:
        print(f"[AUTO-LOG] prune failed: {type(ex).__name__}")
        try:
            await db.rollback()
        except Exception:
            pass


# The operator entry point lives under /api/v1/internal/, NOT under this
# module's public prefix: that prefix is where main's rate_limit_gate checks
# X-Internal-Key in middleware, before any body is read (#388). A prune route
# at /api/v1/logs/auto/prune would be authenticated only inside its handler.
internal_router = APIRouter(prefix="/api/v1/internal/logs", tags=["Auto Logs"])


@internal_router.post("/auto/prune")
async def run_auto_log_prune(
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    db: AsyncSession = Depends(get_db),
):
    """Operator/bot entry point for the retention sweep.

    The /api/v1/internal/ prefix is gated on X-Internal-Key in main's
    rate_limit_gate middleware before any body is read; the check is repeated
    here because every other internal route repeats it and a route that
    depended only on the middleware would be one refactor away from open.
    """
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
    # ge/le above bound the HTTP path; this bounds a direct in-process call,
    # which is the one a test or a future janitor hook would make.
    #
    # `Annotated[..., Query(...)] = None`, not `= Query(None, ...)`. Outside
    # FastAPI nothing resolves a Query default, so with the older spelling the
    # parameter arrives as the descriptor OBJECT and `int(days)` raises
    # TypeError -- the in-process caller this clamp was written for was the one
    # caller it could not serve. Moving the marker into Annotated leaves a real
    # None as the Python default, so both entry points land on the same number.
    # (A first attempt at this fix used `Query(None, ...)`, which is still a
    # Query instance and changed nothing; the test below caught it.)
    requested = AUTO_LOG_RETENTION_DAYS if days is None else days
    return await prune_auto_logs(db, days=max(1, min(int(requested), 365)))
