"""Opt-in automatic log upload after a match — SERVER HALF (v1.41.0, Item 3).

WHAT THIS IS. One authenticated write route, ``POST /api/v1/logs/auto``, that
takes the same log bundle the F5 bug form already sends and stores it as an
ordinary ``bug_reports`` row carrying ``kind = 'auto'``. Everything downstream
— the admin list, the detail view, the download endpoint's read-time scrub and
the ops ``bug-log:N`` verb — reads ``bug_reports`` and therefore works on these
rows with no change at all. That reuse is the whole point of storing them here
rather than in a table of their own.

THE CLIENT HALF IS BUILT AND INSTALLED, so this route receives live traffic.
The Data & Privacy setting, the ``OnLeftRoom`` trigger and the client-side path
scrub are all in the v1.41.0 client lane build ``46f54d4``, which is on Sid's
desktop. The feature is OPT-IN and defaults OFF, so a seat reaches this route
only once the setting has been switched on -- and one has, which is why this
module is being deployed ahead of the rest of its lane.

  An earlier version of this paragraph named ``323cd9c`` as that build. That
  commit is an unrelated vanilla fix and carries none of this; the number was
  wrong rather than the conclusion. A still earlier version said the opposite
  outright -- that the client half belonged to another session and that this
  module was INERT on arrival -- and every conclusion drawn from that premise
  was wrong in the unsafe direction: retention that "nothing exercises yet",
  refusals that "no client can hit yet", a corpus that "cannot grow yet". It
  can and it does. Treat every bound below as load-bearing from the first boot.

  Shipping inert is a known way to ship nothing while every log line looks
  perfect (#438, #443), and the same signal that would have proved inertness
  proves reachability now. This route emits a POSITIVE signal rather than
  relying on the absence of errors: every accepted upload prints exactly one
  ``[AUTO-LOG] #`` LANDING line, naming the bug number, the raw and stored
  sizes and the write-time scrub's own counters, and returns those same
  counters in the response body. Not one line in total -- an accepted upload
  whose opportunistic prune fires also prints a prune line, so the invariant
  is one landing record per acceptance, not one prefixed line per request. ``[AUTO-LOG]`` exists for no other purpose in this repo, so
  grepping the api log for it answers "has a client ever reached this route"
  with a yes or a no and nothing in between (#306). Two greps, because the
  prefix is also on the refusal lines and that distinction is the useful one:
  ``[AUTO-LOG] #`` is an upload that LANDED, and a bare ``[AUTO-LOG]`` is the
  route being reached at all. Neither line appearing means the shipped client
  is not reaching this box — a deployment question, not a design one.

WHAT LEAVES THE MACHINE, AND WHAT IS REMOVED BEFORE IT IS STORED. The bundle
is the client's own log text, and it arrives ALREADY SCRUBBED: the shipped
client replaces profile paths and local account names before it uploads. So
``os_user == 0`` in the counters below is the EXPECTED reading for a healthy
bundle and infers nothing about the header shape — an earlier version of this
paragraph said every bundle carries a raw ``C:\\Users\\<person>\\...`` and
that a zero count meant the header had changed. It does not; a nonzero count
means the server pass found something the client's pass did not, which is the
interesting direction.

The server scrubs again at WRITE time anyway, and that is deliberate: the
bug-report pipeline's own scrub runs at READ time only, which is enough for
the HTTP download endpoint and NOT enough for the ops ``bug-log:`` verb, which
plain-``zcat``s the stored blob. A client-side pass is a claim by the client;
the blob on disk is the server's own artifact, so it goes through
``main._scrub_pass_one`` (OS usernames in Windows and POSIX path shapes, plus
Discord snowflakes) before it is gzipped, whatever the client already did. The
read-time scrub still runs on top and is unaffected — the passes are
idempotent, and the second one is what redacts deleted accounts' SteamID64s,
which is a database question this path deliberately does not ask.

  The scrub is IMPORTED from main, never re-implemented here. Two copies of a
  privacy rule are two readings of one question, and they diverge (#432).

FAILURE DIRECTION. An auto upload exists only to carry its log, so a row
without one is noise an admin has to triage. The blob is therefore written
BEFORE the row is inserted, under an id this module generates -- but only
AFTER the cap has admitted the upload. Admission (the per-account advisory
lock and the count that decides) comes first precisely so that a failure
there, where the handler holds nothing but this request's own bytes, cannot
leave a file behind. Every DETERMINATE failure after it leaves neither
artifact: a failed write unlinks its own partial file, a failed INSERT
unlinks the blob it just wrote. The client is told 503 in every one of these
cases -- never 500 -- and can try again after the next match.

  THE ONE CASE THAT CANNOT BE MADE ATOMIC is a ``commit()`` that raises. That
  is indeterminate, not failed -- PostgreSQL may have committed and the
  acknowledgement been lost on the way back -- so the blob is deliberately
  KEPT. Deleting it is irreversible and, when the row did commit, destroys the
  only copy of the log that row promises, which presents to the next admin as
  corruption rather than as a failed upload. An orphan blob only costs disk.
  Cheap reversible error over expensive irreversible one (#276).

  THAT ARM NOW NAMES WHAT IT KEPT AND SOMETHING COLLECTS IT. The line carries
  ``orphan-candidate=<file>``, and ``prune_orphan_blobs`` -- run by the
  retention loop, not by a request -- removes a file that no ``bug_reports``
  row of ANY kind names once it is a full retention tick old. If the commit
  did land, a row names the file and the sweep passes over it for ever; if it
  did not, the file is collected without anybody having to remember it. An
  earlier version of this paragraph said "nothing collects such a blob ... a
  deliberate trade": the trade was real, and it left a slow leak on a volume
  shared with player-filed attachments, which this route may not spend.

  An earlier version of this paragraph also claimed atomicity across both
  halves unconditionally. It was false of the write arm, which raised without
  unlinking, and it was not achievable across the commit at all.

RETENTION REQUIRES A SWEEP THAT RUNS WHETHER OR NOT ANYBODY UPLOADS. Nothing
deletes a bug_reports row by age by itself: no reader filters on created_at
for retention, and the only collector is ``prune_auto_logs``. An earlier
version of this module reached it two ways only -- opportunistically after an
ACCEPTED upload, and from the internal route -- so the corpus was bounded only
while uploads kept arriving, and the last cohort of rows and blobs persisted
indefinitely the moment they stopped. #276 is about failure DIRECTION: an
expiring design lapses because nothing renews it, a blocking one needs a
positive cleanup that ALWAYS runs. A sweep reachable only from the thing it
collects is the second kind wearing the first kind's clothes.

  So the sweep is now a scheduled background task, ``auto_log_retention_loop``
  below, started from main's ``lifespan`` on the PRIMARY alone (it deletes
  rows, and a DELETE raises in recovery on the standby). It prints
  ``[AUTO-LOG] retention sweep armed ...`` once at boot and one
  ``[AUTO-LOG] retention sweep:`` line per pass. That boot line is the
  positive signal (#438/#443): its ABSENCE on the primary means retention is
  not running, which is a different fact from "nothing was old enough to
  delete" and is exactly what the old opportunistic-only design could not
  distinguish. The opportunistic call and the internal route both stay --
  they cost nothing and they are how an operator forces a pass -- but neither
  is load-bearing any more.

ORDER WITHIN A SWEEP: THE FILE GOES FIRST, AND THE ROW IS THE RETRY
REFERENCE. ``prune_auto_logs`` selects the due rows, unlinks each blob, and
COMMITS the row deletion only for the rows whose blob is actually gone. A row
whose unlink fails is KEPT -- deleting it first would have thrown away the only
pointer to the file and left an orphan nothing can name.

  KEPT IS NOT THE SAME AS RE-READ, and this paragraph used to say the next
  pass simply finds such a row again. A pass reads the OLDEST
  ``_PRUNE_BATCH`` due rows, so a cohort that keeps failing is re-read in full
  on every pass -- and once it is large enough to fill the batch, nothing
  younger than it is reached at all. The row's id is therefore parked in
  ``_PRUNE_HELD`` and the next selections look PAST it, for
  ``_PRUNE_HOLD_S``, after which it is due again. The retry is real and it is
  DEFERRED; what the next pass reads instead is the rows behind the failure.

  The window this opens is the reverse one -- a blob unlinked and then a
  commit that does not land leaves a row advertising a log that is gone, the
  state backend/sql/087_clear_orphaned_bug_logs.sql had to clean up once. It
  is transient rather than permanent here, and that is the difference: no hold
  is taken on that row, because its unlink did not fail. It is still due, the
  next pass re-selects it, the unlink finds the file already absent (counted
  as success, not an error), and the row is collected. That failure repairs
  itself on the following tick instead of needing a migration.

  A pass is bounded by ``_PRUNE_BATCH`` rows so one sweep cannot hold a
  transaction open across an unbounded unlink loop; a backlog drains over
  consecutive ticks.

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
import shutil
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

# THE 401 DETAIL LITERAL, AND IT IS LOAD-BEARING ACROSS THE WIRE.
#
# `ApiClient.HandleSessionReject` (plugin/ApiClient.cs:20916) tests the
# response body with `body.Contains("session_required")` and, only on a match,
# calls `SteamAuth.InvalidateSessionIf` to drop the stale token so the next
# heartbeat mints a fresh one. Production spells it with an UNDERSCORE at
# every strict-session refusal it has, and three of those sites carry a
# comment saying the literal is load-bearing for exactly this reason
# (main.py:15572, :16175, :17388).
#
# THIS MODULE SPELLED IT "session required", WITH A SPACE, AT ALL THREE OF ITS
# REFUSALS. The client's test would have been false, the token would have been
# kept, and the ONE repair path the client has for a stale or unverified
# session would never have run for this route. `AutoLogUpload.OnRoomLeft`'s
# only session gate is that a token is non-empty, which stays true, so the
# seat would have rebuilt and re-uploaded a multi-megabyte bundle at every
# qualifying room exit for the rest of the game session and been refused 401
# every time. Nothing else would have looked wrong: the player's other traffic
# keeps working, because a session minted unverified is refused only by the
# STRICT check and this route is the only place the client meets it.
#
# It is a module constant rather than three string literals because the three
# sites are one contract with another process, and three copies of a contract
# are three chances to drift (#432). The suite asserts the value, the count of
# refusal sites that use it, and that no 401 on this route spells it any other
# way.
_SESSION_REJECT = "session_required"

# Reserved for the blob volume, which this corpus SHARES with player-filed bug
# report attachments (both land under BUG_REPORT_LOG_DIR). The automatic path
# refuses once a write would eat into this margin; the player-filed path never
# consults it.
#
# That asymmetry is the whole point, and it is a failure-direction choice
# (#276/#430). This path can back off at no cost to anybody -- the client
# treats 503 as "try after the next match" -- while a player filing a report
# cannot: they are in front of the form, and on a full volume their log is
# lost with the row still answering 200. So the automatic corpus, which is the
# one that grows on its own, is the one that stops first and leaves the last
# of the volume to the path that has a person waiting on it.
AUTO_LOG_FREE_SPACE_RESERVE_BYTES = 64 * 1024 * 1024

# THE RESERVE IS A DECISION, SO IT HAS TO BE SERIALISED LIKE ONE.
#
# `disk_usage(...).free` is a reading of the past. Measured by two coroutines
# before either has written, it admits both, and the reserve is then short by
# whatever the second one stores. The per-account advisory lock below cannot
# close that: it is keyed on the steam id and two SEATS have different keys,
# which is exactly the shape of the gap.
#
# So the measure-and-write pair is taken under ONE process-wide asyncio lock.
# The api runs a single uvicorn worker BY DESIGN and the flag is pinned on the
# compose command (#125/#651), so process-wide is box-wide here; that pin is
# the premise this bound rests on, and if the api ever runs N workers this
# reserve is short by (N-1) blobs and the bound below has to be restated.
#
# THE BOUND, STATED SO IT CAN BE TESTED (#651). At most ONE automatic blob of
# at most `_BUG_LOG_MAX_GZ` bytes may be written against any one free-space
# reading: the lock is taken before the measurement and released after the
# write returns, so the next measurement sees the previous write. N = 1, and
# `test_two_concurrent_uploads_cannot_both_spend_the_same_reserve` is what
# holds it. The writers this bound does NOT cover are named rather than
# waved at: `submit_bug_report`, which never consults the reserve on purpose
# (see above), and anything outside this process.
#
# BOUNDED WAIT, because an unbounded one is a different failure. A wedged
# volume makes `_write_blob` block inside its worker thread with the lock
# held; without a ceiling every later upload would await it forever and the
# route would stop answering at all. With one, a seat that cannot take the
# lock in time refuses 503 and retries after its next match -- the same
# direction every other refusal on this path takes (#276/#430).
_BLOB_RESERVE_LOCK = asyncio.Lock()
_BLOB_RESERVE_LOCK_WAIT_S = 20.0

# The token the indeterminate-commit arm prints and the orphan sweep matches.
# ONE literal for both halves: the handler writes a blob it cannot prove has a
# row, and the sweep is the only thing that ever removes it, so two spellings
# of the marker would be two chances for the recovery line to name something
# nothing collects (#432).
_ORPHAN_MARKER = "orphan-candidate"

# The advisory-lock CLASS for this route's per-account serialisation. See the
# lock site in upload_auto_log for why the route does not use the bare
# `hashtext(steam_id)` idiom the rest of main.py uses. The value is arbitrary
# and its only requirement is to differ from every other *_LOCK_CLASS in the
# tree, which the suite asserts; it is written as 1.41.0's Item 3 so the
# number has a provenance rather than being a magic six digits.
AUTO_LOG_LOCK_CLASS = 141003

# At most one opportunistic prune an hour per process, on a monotonic clock so
# a wall-clock correction cannot stall or stampede it. The opportunistic call
# is a convenience now, not the mechanism -- auto_log_retention_loop is.
_PRUNE_MIN_INTERVAL_S = 3600.0
_LAST_PRUNE = [0.0]

# Rows handled per pass. One pass holds a transaction open across its unlink
# loop, so the loop is bounded and a backlog drains over consecutive ticks
# instead of in one unbounded pass.
_PRUNE_BATCH = 200

# Rows whose blob could not be unlinked, held out of the next few selections.
#
# WHY THIS EXISTS. The pass takes the OLDEST `_PRUNE_BATCH` due rows and keeps
# any row whose unlink raised, so that the row -- the only thing that names its
# blob -- survives as the retry. Without a hold, a cohort of rows that CANNOT
# be unlinked is re-selected in full on every pass: the directory's volume
# comes back read-only after a host incident, or the container loses write
# permission on a subtree, and from then on every pass reads that same batch,
# keeps all of it, deletes nothing, and never reaches a row newer than them.
# The fourteen-day rule would then be unenforced for the whole corpus while
# each pass still printed a line that reads like a working sweep.
#
# So a failed unlink parks the row's id until a deadline and the next pass
# looks PAST it. The hold is a cooldown, not a blacklist: it expires, so a
# transient fault is retried rather than written off, and the id is dropped the
# moment a pass succeeds on it. The dict is per-process and bounded; losing it
# on restart costs one pass, which re-parks the same rows.
_PRUNE_HOLD_S = 6 * 3600.0
_PRUNE_HELD_MAX = 5 * _PRUNE_BATCH
_PRUNE_HELD: dict[str, float] = {}

# The scheduled sweep's period, and how long after boot the first pass waits.
# The delay keeps retention off the boot path, where the janitor self-test,
# the snapshot retake and the theme load are already competing for the first
# connections.
AUTO_LOG_SWEEP_EVERY_S = 3600.0
AUTO_LOG_SWEEP_BOOT_DELAY_S = 120.0

# ORPHAN SWEEP: how old a blob has to be before "no row names it" is read as
# "no row will ever name it".
#
# ONE RETENTION TICK, and the number is DERIVED from the tick rather than
# written down beside it, so the two cannot be tuned apart. A file is a
# candidate only once it has survived a whole period in which any request that
# was going to commit a row for it has long since finished or died; the write
# -to-commit span on both the automatic and the player-filed path is seconds.
#
# The sweep exists because ONE arm of the upload deliberately keeps a blob it
# cannot prove has a row -- the indeterminate commit. Without a collector that
# arm is a slow leak on a volume shared with player-filed attachments, which
# is the one thing this route is not allowed to spend.
_ORPHAN_MIN_AGE_S = AUTO_LOG_SWEEP_EVERY_S

# Files examined per pass. Same bound and the same reason as `_PRUNE_BATCH`: a
# backlog drains over consecutive ticks instead of one pass holding a
# directory listing and a transaction open over an unbounded loop.
_ORPHAN_BATCH = _PRUNE_BATCH


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


async def _auto_bucket(db: AsyncSession, steam_id: str):
    """This account's automatic uploads inside the rolling 24 h window: how
    many, and the oldest one's timestamp.

    ONE statement and ONE predicate, read by both the cheap pre-check and the
    authoritative check under the lock, because two copies of a bucket's
    definition are two buckets (#432). `kind = 'auto'` is what makes this a
    separate budget rather than a second reader of the report budget.

    The oldest timestamp is what turns the refusal into a number a client can
    act on: the window is a rolling one, so the moment the bucket reopens is
    that row's 24th hour and not some fixed interval from now.
    """
    row = (await db.execute(
        text("SELECT COUNT(*) AS n, MIN(created_at) AS oldest FROM bug_reports "
             "WHERE steam_id = :sid AND kind = 'auto' AND created_at >= :cutoff"),
        {"sid": steam_id,
         "cutoff": datetime.now(timezone.utc) - timedelta(hours=24)},
    )).mappings().first()
    if row is None:
        return 0, None
    return int(row["n"] or 0), row["oldest"]


def _bucket_full(steam_id: str, oldest, when: str) -> HTTPException:
    """The 429, carrying Retry-After.

    WHY THE HEADER MATTERS MORE THAN THE SENTENCE. The bucket is twelve per 24
    HOURS. The client's entire memory of a refusal is a 300-second debounce,
    and its own comment calls a 429 "terminal, never retried" -- which is true
    of that one bundle and not of the bucket. Nothing on the wire said the
    refusal lasts the better part of a day, so the next qualifying room exit
    built and uploaded a full bundle again: over a long sitting, twenty-odd
    further uploads of several megabytes each, every one of them read from
    disk, scrubbed, escaped, sent and discarded.

    The limiter's own 429 in main.rate_limit_gate already sets this header, and
    the client already knows how to read it -- `ApiClient.FormatRequestError`
    appends the value as a trailing line and `MailClient.RetryAfterSeconds`
    parses it. So this is the server half of a mechanism that exists on both
    ends; the client half is a separate, small change in its own lane.

    The value is the rolling window's true reopening: the oldest row in the
    bucket plus 24 hours. Floored at 60 s so a boundary case cannot advertise
    an immediate retry, and capped at the window so a clock skew on either side
    cannot produce a number longer than the limit it describes.
    """
    now = datetime.now(timezone.utc)
    window = int(timedelta(hours=24).total_seconds())
    if oldest is None:
        retry_after = window
    else:
        # created_at is TIMESTAMPTZ, so asyncpg hands back an aware datetime.
        # Normalised anyway: the scripted sessions the suite runs against are
        # free to hand back whatever they like, and a naive/aware subtraction
        # would raise TypeError -- turning a refusal into a 500 on the one
        # path whose whole job is to refuse cheaply.
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        retry_after = int((oldest + timedelta(hours=24) - now).total_seconds())
    retry_after = max(60, min(window, retry_after))
    print(f"[AUTO-LOG] refused 429: {steam_id} at the "
          f"{AUTO_LOG_PER_STEAM_PER_DAY}/24h cap, {when}; "
          f"Retry-After {retry_after}s")
    return HTTPException(
        status_code=429,
        detail=f"Limit is {AUTO_LOG_PER_STEAM_PER_DAY} automatic uploads per 24h",
        headers={"Retry-After": str(retry_after)},
    )


def _compress_blob(scrubbed: str) -> bytes:
    """Encode and gzip, off the event loop -- see the call site."""
    return gzip.compress(scrubbed.encode("utf-8", errors="replace"))


def _write_blob(path, data: bytes) -> None:
    """Write the blob, off the event loop -- see the call site."""
    with open(path, "wb") as f:
        f.write(data)


def _free_bytes(directory) -> int:
    """Free space on the blob volume, or -1 if it cannot be determined.

    -1 rather than an exception so the CALLER owns the direction -- and the
    caller REFUSES. An earlier version of this docstring said the opposite
    ("an unknown figure is no reason to refuse") and the caller agreed with
    it, which made a reserve whose whole job is to hold the last of a shared
    volume for player-filed reports evaporate in precisely the conditions
    that stop a volume answering. A guard that admits on measurement failure
    is weakest exactly when it matters most (#276).

    The cost of refusing is one 503 and one retry after the next match. The
    cost of admitting is a player's attachment lost on a full volume with the
    form answering 200. So unknown means no.
    """
    try:
        return shutil.disk_usage(str(directory)).free
    except Exception:
        return -1


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
        raise HTTPException(status_code=401, detail=_SESSION_REJECT)
    _bound = (await db.execute(text(
        "SELECT steam_id FROM steam_sessions WHERE token_hash = :th"
    ), {"th": hashlib.sha256(_token.encode()).hexdigest()})).mappings().first()
    if _bound is None or not await _strict_steam_session_ok(
            request, _bound["steam_id"], db):
        print("[AUTO-LOG] refused 401: token is not a known, unexpired, "
              "verified session -- body not read")
        raise HTTPException(status_code=401, detail=_SESSION_REJECT)

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
        raise HTTPException(status_code=401, detail=_SESSION_REJECT)

    log_blob = (req.log_text or "").strip()
    if not log_blob:
        # A log upload with no log is not a degenerate success. Refusing it
        # keeps the corpus free of rows whose only content is their own
        # existence, and tells a miswired client something is wrong.
        print(f"[AUTO-LOG] refused 400: empty log_text from {req.steam_id}")
        raise HTTPException(status_code=400, detail="log_text required")

    # THE CHEAP REFUSAL, UNLOCKED AND REFUSE-ONLY.
    #
    # This read decides one thing: whether to spend the next second of CPU on a
    # bundle the authoritative check below is going to refuse anyway. It is NOT
    # the guard. Under READ COMMITTED an unlocked count proves nothing about
    # the moment of the INSERT -- #207 refuted exactly that shape -- so this
    # arm is allowed to REFUSE and never to ADMIT. Passing it means only "not
    # obviously over the cap"; the count under the lock further down is what
    # decides.
    #
    # Without it the 429 is the most expensive answer this route gives: a seat
    # that reached its cap two hours into a long sitting would still read three
    # log files, scrub up to 3.5 M characters, gzip them and write megabytes to
    # disk before being told no, at every qualifying room exit for the rest of
    # the sitting.
    count, oldest = await _auto_bucket(db, req.steam_id)
    if count >= AUTO_LOG_PER_STEAM_PER_DAY:
        raise _bucket_full(req.steam_id, oldest, "before the bundle was processed")

    player_row = (await db.execute(
        text("SELECT id FROM players WHERE steam_id = :sid"), {"sid": req.steam_id},
    )).mappings().first()

    # Write-time scrub, in a worker thread. The counters it returns are the
    # positive signal that the scrub RAN, as opposed to matched nothing.
    #
    # os_user == 0 IS THE EXPECTED READING for a healthy bundle: the shipped
    # client scrubs profile paths and local account names before it uploads,
    # so there is normally nothing here for the server pass to find. It infers
    # nothing about the header shape. A NONZERO count is the interesting
    # direction -- it means this pass found something the client's pass did
    # not. (An earlier version of this comment said a zero meant the header
    # had changed, which contradicted the module contract at the top of this
    # file and would have had an operator chasing a client defect every time
    # the client did its job.)
    scrubbed, counts, _ids = await asyncio.to_thread(_scrub_pass_one, log_blob)

    report_id = uuid.uuid4()
    # In a worker thread for the same reason the scrub above is, and the two
    # cost the same order of magnitude. gzip at its default level over a
    # multi-megabyte bundle is hundreds of milliseconds of uninterruptible
    # CPU, and the api runs ONE uvicorn worker by design: on the event loop
    # that is time in which no queue join, match report, bet or chat poll on
    # this box makes any progress at all. Sixteen seats leaving a tournament
    # round inside the same second serialise into several seconds of it.
    #
    # The encode is inside the same hop deliberately -- it is a pass over up
    # to twelve million characters in its own right, and moving only the gzip
    # would have left half the cost where it was.
    data = await asyncio.to_thread(_compress_blob, scrubbed)

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
    # ── ADMISSION: the lock and the count that decides, BEFORE anything lands ──
    #
    # ONE INVARIANT NEEDS THIS LOCK -- count-then-INSERT of kind='auto' rows
    # for one account -- and it holds for exactly that. There is no row to take
    # FOR UPDATE, because the row being counted is the one about to be written,
    # which is the case the repo keys an advisory lock on a VALUE for
    # (#202/#203/#207).
    #
    # IT SITS BEFORE THE BLOB WRITE, AND THAT POSITION IS THE FIX.
    # It used to sit after it. A lock wait that lost its connection, or a count
    # that raised, then left a blob on disk that no row would ever name: no
    # prune could find it (the prune walks ROWS), no operator could tell it
    # from a live artifact, and the caller got a 500 -- a code the client half
    # retries, so the next match wrote another one. Nothing before this line
    # touches shared state, and nothing after it writes to disk until the count
    # has admitted the upload, so the only blob that exists is one the cap
    # already said yes to.
    #
    # WHAT MOVED INSIDE THE LOCK, AND WHAT DID NOT. The scrub (up to ~2.4 s by
    # main's own measurement) and the gzip stay OUTSIDE it -- they were the
    # expensive tenants the earlier round evicted and they are not coming back.
    # What is inside now is the blob write, the INSERT and the commit. The
    # exclusion is per ACCOUNT, so the seat that waits is the same seat that is
    # uploading twice, and the client's own 300 s debounce makes that rare;
    # nobody else's upload waits on it.
    #
    # AND IT IS CLASS-DISCRIMINATED, not the bare `hashtext(steam_id)` idiom.
    # That one-argument expression is this application's IDENTITY lock: match
    # reporting, queue join, session refresh and account deletion all take it
    # on the same key, and their own comments fix the order "identity ->
    # lobby/series -> queue -> lease". An automatic log upload is not an
    # identity operation and has no business in that namespace -- a seat
    # leaving a match would have had its match report wait behind its own log
    # upload. The two-argument overload is a SEPARATE lock space (the same form
    # and the same reasoning as `_pc_lock_blob` in main.py), and moving to it
    # is only safe because of what must exclude this route: the
    # count-then-INSERT is over kind='auto' rows, this handler is their only
    # writer, and nothing else in the tree counts them (#707 -- the question to
    # ask is never "which keyspace" but "which other sites must exclude this
    # one").
    try:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(CAST(:cls AS integer), hashtext(CAST(:h AS text)))"),
            {"cls": AUTO_LOG_LOCK_CLASS, "h": req.steam_id})

        # The authoritative count. Re-read under the lock and re-checked,
        # because the number the cheap arm saw was read without it and a
        # concurrent upload may have landed since (#208). This is the read the
        # cap is made of; the earlier one only saved work.
        count, oldest = await _auto_bucket(db, req.steam_id)
    except HTTPException:
        # Nothing in this span raises one today. The arm is here so that if
        # anything ever does, its own status code survives instead of being
        # rewritten into the generic 503 below -- the same discipline the blob
        # block uses, and the reason the reserve refusal still says WHY.
        raise
    except Exception as ex:
        # 503 AND NOT 500. A lost connection, a lock wait killed by
        # `idle_in_transaction_session_timeout`, a deadlock detector -- every
        # one of them is "this exact request would work later", which is what
        # 503 means to the client half and what 500 does not. Nothing has been
        # written, so there is nothing to clean up; the rollback is explicit
        # because under asyncpg a caught statement error leaves the whole
        # transaction ABORTED and the next statement on this session would
        # raise on that and not on its own fault.
        try:
            await db.rollback()
        except Exception:
            pass
        print(f"[AUTO-LOG] refused 503: admission failed for {req.steam_id} "
              f"before anything was written ({type(ex).__name__})")
        raise HTTPException(status_code=503, detail="log storage unavailable")

    if count >= AUTO_LOG_PER_STEAM_PER_DAY:
        # Nothing to discard: this refusal now happens before the write, which
        # is the whole point of moving the lock up.
        raise _bucket_full(req.steam_id, oldest, "on the locked re-check")

    # The path resolution is INSIDE the try, not before it: _bug_report_log_path
    # creates the directory, so an unusable BUG_REPORT_LOG_DIR fails there and
    # not at open(). Outside the try that becomes a 500, and 500 vs 503 is not
    # cosmetic here -- the client half is a background retry loop, and 503 is
    # the code that says the same request will work later.
    path = None
    try:
        # THE MEASURE-AND-WRITE PAIR, UNDER ONE PROCESS-WIDE LOCK.
        # See `_BLOB_RESERVE_LOCK` for the bound this holds (N = 1 blob per
        # reading) and for why the per-account advisory lock above cannot hold
        # it: two seats have two keys, and the reserve is one volume.
        try:
            await asyncio.wait_for(_BLOB_RESERVE_LOCK.acquire(),
                                   _BLOB_RESERVE_LOCK_WAIT_S)
        except (asyncio.TimeoutError, TimeoutError):
            print(f"[AUTO-LOG] refused 503: waited {_BLOB_RESERVE_LOCK_WAIT_S}s "
                  f"for the blob-volume lock and did not get it -- refusing "
                  f"rather than measuring the reserve against a reading this "
                  f"request never took")
            raise HTTPException(status_code=503, detail="log storage unavailable")
        try:
            path = _bug_report_log_path(str(report_id))

            # LEAVE THE LAST OF THE VOLUME TO THE PATH THAT HAS A PERSON WAITING.
            #
            # This corpus and the bug form's attachments share one directory,
            # and this is the half that grows by itself: up to twelve blobs per
            # opted-in account per day, held fourteen days. When the volume
            # fills, THIS route handles it correctly -- it unlinks, answers
            # 503, and the client tries after the next match.
            # `submit_bug_report` does not: its write failure is caught,
            # logged and fallen through, so the report commits with no
            # attachment and the player is answered 200 by a server that just
            # lost their log.
            #
            # So the automatic path stops first, while there is still room for
            # the one that cannot retry. Refusing here rather than at ENOSPC
            # also means no partial file is written on a volume that is
            # already out of space.
            free = _free_bytes(path.parent)
            if free < 0:
                # UNKNOWN IS A REFUSAL. This arm used to be the admitting one
                # -- `free >= 0 and ...` skipped the whole guard when the
                # volume would not answer -- so the reserve stopped existing
                # in exactly the conditions that produce an unreadable volume.
                # Which direction the unhandled case fails in is the question
                # (#276), and the answer here is: toward the path that has a
                # person waiting on it.
                print("[AUTO-LOG] refused 503: free space on the blob volume "
                      "could not be measured, so the reserve held for "
                      "player-filed reports cannot be shown to survive this "
                      "write")
                raise HTTPException(status_code=503,
                                    detail="log storage unavailable")
            if free - len(data) < AUTO_LOG_FREE_SPACE_RESERVE_BYTES:
                print(f"[AUTO-LOG] refused 503: {free} bytes free on the blob "
                      f"volume, and storing {len(data)} would leave less than "
                      f"the {AUTO_LOG_FREE_SPACE_RESERVE_BYTES}-byte reserve "
                      f"held for player-filed reports")
                raise HTTPException(status_code=503,
                                    detail="log storage unavailable")

            # Off the event loop, like the compression above: this is a write
            # of up to 8 MiB, and on a slow or contended volume it blocks
            # every other request on this worker for as long as it takes. The
            # path resolution stays on the loop -- it is a mkdir, and keeping
            # it here is what binds `path` for the unlink below.
            #
            # INSIDE the reserve lock, not after it. The measurement above is
            # only a decision about this write if this write is the one that
            # follows it; releasing between the two is the gap the lock exists
            # to close.
            await asyncio.to_thread(_write_blob, path, data)
        finally:
            _BLOB_RESERVE_LOCK.release()
    except HTTPException:
        # The reserve refusal above is already the answer it wants to give,
        # and nothing has been written for it to clean up. Re-raised as-is so
        # it does not get rewritten into the generic storage failure below and
        # lose the one line that says WHY.
        raise
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
            # bug_number IS SUPPLIED, from a sequence of this route's own
            # (migration 350). The column's DEFAULT is nextval() on
            # `bug_reports_number_seq` -- the counter that names a player's
            # ticket in #bug-reports, in admin triage and in the ops
            # `bug-log:N` verb. Left to the default, every automatic upload
            # would spend one of those numbers and retention would then delete
            # the row that held it, so a player filing a report a month later
            # is told they are #1,247 with ~900 numbers behind them naming
            # nothing. A sequence never rewinds; that gap is permanent and
            # reads as data loss to whoever hits it.
            #
            # `bug_reports_auto_number_seq` descends from -1, so an automatic
            # row's number cannot collide with a human one (the unique index
            # is satisfied) and cannot consume one. The CHECK added by 350
            # makes it a property of the schema rather than of this statement.
            text("""INSERT INTO bug_reports
                        (id, player_id, steam_id, display_name, mod_version, game_version,
                         severity, category, kind, description, repro_steps,
                         log_filename, log_bytes, status, bug_number)
                    VALUES
                        (CAST(:id AS uuid), CAST(:pid AS uuid), :sid, :name, :mv, :gv,
                         'low', 'other', 'auto', :descr, :repro,
                         :fname, :fbytes, 'open',
                         nextval('bug_reports_auto_number_seq'))
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
        #
        # AND IT IS THE ONE ARM THAT CAN STILL PRODUCE AN UNREFERENCED BLOB, so
        # it names it. `_ORPHAN_MARKER` is the token `prune_orphan_blobs` uses
        # for the same file, so the line an operator greps for and the line the
        # sweep prints when it removes it are the same word. If the commit did
        # land, a row names the file and the sweep leaves it alone for ever; if
        # it did not, the file is collected one retention tick later and
        # nothing has to be remembered by anybody. A kept artifact with no
        # collector is how a shared volume fills, which is why the recovery
        # identifier and the sweep are one change and neither works alone.
        try:
            await db.rollback()
        except Exception:
            pass
        print(f"[AUTO-LOG] commit INDETERMINATE for {report_id}: "
              f"{type(ex).__name__}; blob KEPT as {path.name} -- a row may or "
              f"may not exist for it; {_ORPHAN_MARKER}={path.name}, collected "
              f"by the retention loop's orphan sweep if no row names it")
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


def _hold(row_id: str, clock: float) -> None:
    """Park one row id until `clock + _PRUNE_HOLD_S`, keeping the dict bounded.

    At the ceiling the entry closest to expiring is evicted rather than the
    new one being dropped. That choice is what keeps the sweep MOVING: the
    evicted id is the one whose fault is oldest and therefore the one most
    worth trying again, and refusing to record the new failure instead would
    put its row straight back at the head of the next selection -- which is
    the state this whole mechanism exists to leave.
    """
    if row_id not in _PRUNE_HELD and len(_PRUNE_HELD) >= _PRUNE_HELD_MAX:
        _PRUNE_HELD.pop(min(_PRUNE_HELD, key=_PRUNE_HELD.get), None)
    _PRUNE_HELD[row_id] = clock + _PRUNE_HOLD_S


async def prune_auto_logs(db: AsyncSession, *, days: int = AUTO_LOG_RETENTION_DAYS) -> dict:
    """Unlink the blobs of kind='auto' rows older than `days`, then delete the
    rows whose blob is gone.

    ONLY kind='auto'. The predicate is the whole safety property here: bug
    reports have no retention and this function must never be the thing that
    gives them one.

    THE FILE IS REMOVED BEFORE THE ROW DELETION COMMITS, and a row whose
    unlink raised is left in place. The row is the only thing that names its
    blob, so deleting it first turns a transient filesystem error into an
    orphan nothing can ever find again; leaving it makes the next pass the
    retry. `retained` in the returned dict counts exactly those.

    An `unlink` that reports the file already absent is SUCCESS, not an error:
    that is the expected state after a pass that unlinked and then failed to
    commit, and treating it as a failure would pin such a row for ever.

    A row kept this way is also HELD OUT of the next few selections
    (`_PRUNE_HELD`). Keeping it and re-selecting it are two different
    decisions, and only the first one is wanted: this pass reads the oldest
    `_PRUNE_BATCH` due rows, so an un-unlinkable cohort that fills the batch
    is otherwise re-read whole on every pass, deletes nothing, and hides every
    newer row behind it for as long as the fault lasts. The hold expires, so
    it is a cooldown and not a verdict.

    Bounded to `_PRUNE_BATCH` rows per call. A backlog drains across ticks
    rather than holding one transaction open over an unbounded loop of
    filesystem calls.

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

    # Expire the holds first, so the ids handed to the query are only the ones
    # still cooling down and a fault that has been repaired is retried.
    clock = time.monotonic()
    for rid in [k for k, until in _PRUNE_HELD.items() if until <= clock]:
        _PRUNE_HELD.pop(rid, None)
    held = [uuid.UUID(rid) for rid in _PRUNE_HELD]

    due = (await db.execute(
        text("""SELECT id::text AS id, log_filename
                  FROM bug_reports
                 WHERE kind = 'auto'
                   AND created_at < NOW() - make_interval(days => CAST(:days AS integer))
                   AND NOT (id = ANY(CAST(:held AS uuid[])))
                 ORDER BY created_at
                 LIMIT :lim"""),
        {"days": int(days), "lim": _PRUNE_BATCH, "held": held},
    )).mappings().all()
    if not due:
        if held:
            # Not "nothing to collect": there are rows this pass deliberately
            # did not look at. Said out loud, because a quiet pass and a pass
            # that skipped its entire backlog print the same thing otherwise.
            print(f"[AUTO-LOG] retention sweep: nothing due outside the "
                  f"{len(held)} row(s) held back after a failed unlink")
        # The SELECT above opened a transaction on this session and this path
        # writes nothing, so it has to be ENDED rather than abandoned. On the
        # loop's own session that would resolve itself when the context manager
        # exits; on the opportunistic call it does not, because the session is
        # the REQUEST's and it stays checked out until the request finishes --
        # an idle-in-transaction connection holding back the vacuum horizon for
        # that long, for a pass that decided to do nothing.
        await db.rollback()
        return {"rows": 0, "blobs": 0, "retained": 0, "due": 0,
                "held": len(held)}

    base = pathlib.Path(BUG_REPORT_LOG_DIR)
    collectable: list[str] = []
    retained: list[str] = []
    unlinked = 0
    for r in due:
        name = r["log_filename"]
        if not name:
            collectable.append(r["id"])
            continue
        try:
            (base / name).unlink()
            unlinked += 1
        except FileNotFoundError:
            # Already gone -- a previous pass unlinked it and did not get to
            # commit, or an operator cleared the directory. The row is now
            # collectable for the same reason it would have been anyway.
            _PRUNE_HELD.pop(r["id"], None)
            collectable.append(r["id"])
            continue
        except OSError as ex:
            # KEPT. The row is the only name this blob has; dropping it would
            # strand the file permanently. A later pass retries it -- later,
            # and not standing in front of everything younger than it, which
            # is what _PRUNE_HELD is for.
            retained.append(r["id"])
            _hold(r["id"], clock)
            print(f"[AUTO-LOG] retention: keeping row {r['id']} -- its blob "
                  f"{name} could not be removed ({type(ex).__name__}); held "
                  f"out of the next {int(_PRUNE_HOLD_S)}s of sweeps")
            continue
        _PRUNE_HELD.pop(r["id"], None)
        collectable.append(r["id"])

    deleted = 0
    if collectable:
        # `CAST(:ids AS uuid[])` types the bound parameter explicitly, and the
        # values handed over are real UUID objects rather than strings --
        # #275/#448: under asyncpg the surrounding expression types the param,
        # and a bare `= ANY(:ids)` would leave the driver to guess. The age
        # predicate is REPEATED rather than replaced by the id list: the second
        # statement re-reads and re-checks the predicate the first one selected
        # on (#208), and it is what keeps idx_bug_reports_kind_created usable.
        deleted = (await db.execute(
            text("""DELETE FROM bug_reports
                     WHERE kind = 'auto'
                       AND created_at < NOW() - make_interval(days => CAST(:days AS integer))
                       AND id = ANY(CAST(:ids AS uuid[]))"""),
            {"days": int(days), "ids": [uuid.UUID(i) for i in collectable]},
        )).rowcount or 0
        await db.commit()
    else:
        # Every due row was retained, so there is nothing to commit -- and the
        # SELECT's transaction is still open. Same reason as the early return
        # above: the loop's own session would be ended by its context manager,
        # the request's session would not be, and this is the shape of pass a
        # stuck blob volume produces for as long as the fault lasts.
        await db.rollback()

    print(f"[AUTO-LOG] retention sweep: {len(due)} row(s) past {days}d, "
          f"{unlinked} blob(s) unlinked, {deleted} row(s) deleted, "
          f"{len(retained)} kept for retry, {len(_PRUNE_HELD)} held")
    return {"rows": deleted, "blobs": unlinked, "retained": len(retained),
            "due": len(due), "held": len(_PRUNE_HELD)}


def _stale_blob_names(base, cutoff: float, limit: int) -> list[str]:
    """Up to `limit` file names under `base` last modified before `cutoff`.

    On the worker thread, because it is a directory walk plus one `stat` per
    entry and the corpus is thousands of files on a contended volume.

    A name whose `stat` raises is SKIPPED rather than reported: the only thing
    this pass does with a name is delete the file, and a file that will not
    answer about its own age is not one to act on. Nothing is lost -- the next
    tick asks again.
    """
    out: list[str] = []
    try:
        entries = os.scandir(str(base))
    except OSError:
        return out
    with entries:
        for e in entries:
            if len(out) >= limit:
                break
            try:
                if not e.is_file():
                    continue
                if e.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            out.append(e.name)
    return out


async def prune_orphan_blobs(db: AsyncSession, *, min_age_s: float | None = None,
                             limit: int = _ORPHAN_BATCH) -> dict:
    """Remove blobs that no `bug_reports` row names, once they are old enough
    that no row ever will.

    WHY THIS EXISTS. `upload_auto_log` has exactly one arm that leaves a file
    behind it cannot account for: a commit whose outcome is UNKNOWN. That arm
    keeps the blob on purpose -- destroying a log because an acknowledgement
    was lost is the worse error -- and it prints `<marker>=<name>`. This is the
    other half of that decision. Without it the kept file is permanent, and the
    volume it is permanent on is shared with player-filed attachments.

    NOT SCOPED TO kind='auto', AND THAT IS THE SAFETY PROPERTY, NOT AN
    OVERSIGHT. `prune_auto_logs` above walks ROWS and must never touch a bug
    report; this walks FILES, where the only thing that protects a file is a
    row naming it -- and a player-filed report's row names its attachment
    exactly as an automatic row does. Scoping this query to kind='auto' would
    make every player-filed attachment look unreferenced and delete the lot. So
    the predicate is `log_filename = ANY(...)` over the WHOLE table, and the
    test that reds when someone adds `kind = 'auto'` to it is named after this
    paragraph.

    THREE GUARDS, each with its own failure direction (#276):

    * AGE. A file is a candidate only after `_ORPHAN_MIN_AGE_S`, one whole
      retention tick. The window between writing a blob and committing its row
      is seconds on both paths, so this is four orders of magnitude of margin
      against deleting a file whose row is still in flight.
    * THE TABLE MUST KNOW ABOUT THIS CORPUS AT ALL. If `bug_reports` names no
      blob whatsoever while the directory holds candidates, this pass REFUSES
      and says so. That reading is not "everything here is an orphan"; it is
      "this process is talking to a database that does not own this
      directory" -- a restored volume, a mis-set BUG_REPORT_LOG_DIR, a
      pointed-at scratch database -- and the honest answer to it is to delete
      nothing.
    * BOUNDED. `limit` files per pass, so a mistake is bounded by the batch and
      a backlog drains over ticks.

    Read-only on the database: the transaction the SELECT opens is ENDED with a
    rollback, for the same reason the early returns above are (an
    idle-in-transaction connection holds back the vacuum horizon).
    """
    from main import BUG_REPORT_LOG_DIR

    base = pathlib.Path(BUG_REPORT_LOG_DIR)
    cutoff = time.time() - float(_ORPHAN_MIN_AGE_S if min_age_s is None else min_age_s)
    names = await asyncio.to_thread(_stale_blob_names, base, cutoff, int(limit))
    if not names:
        return {"candidates": 0, "orphans": 0, "unlinked": 0, "refused": False}

    named_total = (await db.execute(
        text("SELECT COUNT(*) AS n FROM bug_reports WHERE log_filename IS NOT NULL")
    )).mappings().first()
    if not (named_total or {}).get("n"):
        await db.rollback()
        print(f"[AUTO-LOG] orphan sweep REFUSED: {len(names)} aged file(s) under "
              f"{base}, and bug_reports names no blob at all. That reads as a "
              f"database which does not own this directory, not as a directory "
              f"full of orphans -- nothing removed")
        return {"candidates": len(names), "orphans": 0, "unlinked": 0,
                "refused": True}

    known = {r["log_filename"] for r in (await db.execute(
        text("""SELECT log_filename FROM bug_reports
                 WHERE log_filename = ANY(CAST(:names AS text[]))"""),
        {"names": list(names)},
    )).mappings().all()}
    await db.rollback()

    orphans = [n for n in names if n not in known]
    unlinked = 0
    for name in orphans:
        try:
            (base / name).unlink()
        except FileNotFoundError:
            # Someone else got there first. Not an error -- the file is gone,
            # which is the outcome this pass wanted.
            unlinked += 1
            continue
        except OSError as ex:
            print(f"[AUTO-LOG] orphan sweep: {_ORPHAN_MARKER}={name} could not "
                  f"be removed ({type(ex).__name__}); the next tick retries it")
            continue
        unlinked += 1
        print(f"[AUTO-LOG] orphan sweep: removed {_ORPHAN_MARKER}={name} -- "
              f"older than {int(_ORPHAN_MIN_AGE_S)}s and no bug_reports row "
              f"names it")

    print(f"[AUTO-LOG] orphan sweep: {len(names)} aged file(s) examined, "
          f"{len(orphans)} unreferenced, {unlinked} removed")
    return {"candidates": len(names), "orphans": len(orphans),
            "unlinked": unlinked, "refused": False}


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


async def auto_log_retention_loop() -> None:
    """THE thing that enforces the fourteen-day rule. Started from main's
    ``lifespan`` on the PRIMARY only, because every pass DELETEs and a delete
    raises in recovery on the standby.

    It runs whether or not anybody uploads, which is the whole point: the
    opportunistic prune inside ``upload_auto_log`` collects nothing once
    uploads stop, and "the corpus stopped growing" and "the corpus stopped
    being collected" look identical from outside.

    POSITIVE SIGNAL (#438/#443). One ``[AUTO-LOG] retention sweep armed`` line
    at boot, then one ``[AUTO-LOG] retention sweep:`` line per pass -- printed
    on EVERY pass, including the passes that delete nothing, because "zero
    rows were due" is the answer this loop exists to be able to give. A
    primary whose log has no armed line is a primary where retention is not
    running, and that is now a one-grep question.

    Its own session per pass: the loop must not hold a pooled connection
    between ticks, and an error in one pass must not leave a poisoned session
    behind for the next.

    A FAILING PASS IS CAUGHT HERE, on purpose, and the line an operator looks
    for is ``[AUTO-LOG] retention sweep FAILED`` carrying the number of
    consecutive failures -- that string, and not a background-task restart
    line. A blip on one tick must not take retention down until the next boot,
    so the loop reports and ticks again, and says
    ``[AUTO-LOG] retention sweep recovered`` when a pass finally gets through.
    ``_supervised`` wraps this loop as the backstop for what it does NOT catch
    -- a BaseException, or a failure of the sleep between ticks -- and for
    nothing that happens inside a pass. "Is retention running" is the armed
    line; "is it working" is a FAILED count that is not climbing.
    """
    from database import async_session

    print(f"[AUTO-LOG] retention sweep armed: every "
          f"{int(AUTO_LOG_SWEEP_EVERY_S)}s, deleting kind='auto' rows older "
          f"than {AUTO_LOG_RETENTION_DAYS}d, first pass in "
          f"{int(AUTO_LOG_SWEEP_BOOT_DELAY_S)}s")
    await asyncio.sleep(AUTO_LOG_SWEEP_BOOT_DELAY_S)
    failures = 0
    while True:
        try:
            async with async_session() as db:
                result = await prune_auto_logs(db)
                # The row-walking sweep above cannot see a file no row names,
                # and the upload's indeterminate-commit arm deliberately leaves
                # one. This is the only thing in the tree that collects it, and
                # it runs HERE and not from `_maybe_prune`: a directory listing
                # does not belong on a request.
                await prune_orphan_blobs(db)
            if failures:
                print(f"[AUTO-LOG] retention sweep recovered after "
                      f"{failures} failed pass(es)")
                failures = 0
            if result["due"] == 0 and not result.get("held"):
                # prune_auto_logs prints when it had rows in hand or rows held
                # back, so the genuinely quiet pass says so here. A loop that
                # prints nothing when there is nothing to do is a loop you
                # cannot tell from a dead one.
                print("[AUTO-LOG] retention sweep: 0 row(s) past "
                      f"{AUTO_LOG_RETENTION_DAYS}d, nothing to collect")
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            # COUNTED, because one line an hour reads the same whether it is
            # the first failure or the hundred-and-sixty-eighth. The count is
            # what turns "it failed" into "it has not run for a week".
            failures += 1
            print(f"[AUTO-LOG] retention sweep FAILED ({failures} consecutive): "
                  f"{type(ex).__name__}: {ex}")
        await asyncio.sleep(AUTO_LOG_SWEEP_EVERY_S)


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
