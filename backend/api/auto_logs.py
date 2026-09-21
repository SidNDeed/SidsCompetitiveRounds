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

  AND AN UNLINK THAT RAISES IS NOT A DISCARD. ``_release_marked_blob`` answers
  whether the blob is GONE, and the INSERT arm says so either way: a file that
  survived its own cleanup KEEPS its marker and is named for the sweep rather
  than recorded as discarded. A cleanup record that cannot be wrong about the
  file it describes is what makes the paragraph above a claim and not an
  intention.

  EVERY BLOB CARRIES A DURABLE MARKER FROM BEFORE ITS FIRST BYTE. A sidecar
  file, ``<blob>.orphan-candidate``, is created and fsynced -- with its
  directory entry, on a platform that has one to flush separately -- before
  ``open()`` is called on the blob, and it is dropped only when the row is
  committed, or together with the blob when one of the arms above discards it.
  So there is no instant, and no crash between any two lines of this handler,
  at which an unreferenced blob exists with nothing naming it. A stamp that
  cannot be made durable REFUSES the upload rather than writing the blob
  anyway.

  AND EVERY ORDER THIS MODULE RELIES ON IS A PERSISTENCE ORDER, NOT A CALL
  ORDER. An ordering that survives the PROCESS does not survive the HOST: a
  power loss recovers whatever was flushed and discards the rest, in no
  guaranteed order between two un-synced changes to one directory. Three
  barriers make the two orders above true of the disk, and each one is
  charged to the marked span's own deadline rather than paid outside it:

    * ``_stamp_marker`` fsyncs the marker and then its directory entry
      BEFORE ``open()`` is called on the blob;
    * ``_write_blob`` fsyncs the blob's CONTENTS and then its directory
      ENTRY before it returns -- so the row that names it is inserted and
      committed only over bytes the filesystem has promised;
    * ``_delete_blob_then_marker`` fsyncs the directory between the blob's
      unlink and the marker's, so a crash cannot persist the marker's
      removal while recovering the blob's entry.

  THE ONE CASE THAT CANNOT BE MADE ATOMIC is a ``commit()`` that raises. That
  is indeterminate, not failed -- PostgreSQL may have committed and the
  acknowledgement been lost on the way back -- so the blob is deliberately
  KEPT. Deleting it is irreversible and, when the row did commit, destroys the
  only copy of the log that row promises, which presents to the next admin as
  corruption rather than as a failed upload. An orphan blob only costs disk.
  Cheap reversible error over expensive irreversible one (#276).

  THAT ARM NOW NAMES WHAT IT KEPT AND SOMETHING COLLECTS IT. The line carries
  ``orphan-candidate=<file>`` and the marker beside the blob is left in place,
  so ``prune_orphan_blobs`` -- run by the retention loop, not by a request --
  finds it. If the commit did land, a ``bug_reports`` row of ANY kind names
  the file and the sweep CLEARS the marker, keeping the blob for ever; if it
  did not, the blob and then its marker are removed once past the age gate.
  Nobody has to remember it either way. An earlier version of this paragraph
  said "nothing collects such a blob ... a deliberate trade": the trade was
  real, and it left a slow leak on a volume shared with player-filed
  attachments, which this route may not spend.

  THE SWEEP'S POPULATION IS THE MARKER SET, NEVER THE ATTACHMENT HEAP. An
  earlier version walked the directory and bounded what one pass examined. That
  directory holds every player-filed attachment permanently and nothing here
  deletes a referenced one, so the budget was spent on files the sweep is
  required to KEEP and an orphan behind enough of them was never offered to the
  database at all. A referenced file does not carry a marker, so the marker set
  has no such floor, no cap over it and no starvation class; the bound that
  remains is on how many blobs one pass may REMOVE.

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
import threading
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

# WHAT THE BOUNDED WAIT IS PAID WITH, AND WHY IT IS NOT PAID TWICE.
#
# The wait above is served inside this request's DATABASE TRANSACTION: the
# per-account advisory lock is taken before it (that ordering is what keeps a
# blob from existing before the cap admitted it) and the transaction is not
# committed until after the INSERT.
#
# The CONNECTION is not what this span introduced -- this handler has had one
# checked out since its first statement, the session-token lookup, and held it
# across the scrub and the gzip before that was ever true here. What this span
# adds is time in which that connection is idle IN A TRANSACTION and the
# per-account advisory lock is held with it, and the length of it is decided
# by a volume rather than by this process. The pool is 20 + 10 with a 30 s
# checkout timeout (`database.py`), so one request paying the full wait is the
# design; EVERY arriving request paying it, because the holder is stuck on a
# volume that is not answering, is a queue that consumes connections other
# endpoints need -- and each of them ends in the same 503 it could have been
# given immediately.
#
# So a pass records when it started its measure-and-write, and an arriving
# request that finds one in flight PAST this ceiling refuses at once instead
# of joining the queue. It is a refusal either way; the difference is whether
# it costs a connection for twenty seconds first. The ceiling is generous
# against an ordinary slow write -- an 8 MiB write that takes this long is not
# a volume this route should be adding to.
_BLOB_WRITE_STARTED = [0.0]
_BLOB_WRITE_STALL_S = 5.0

# Above this, the hold is REPORTED. An unmeasured hold is the one nobody can
# argue about afterwards: without this line "the volume was slow" and "the
# route was slow" are the same log (#438/#443). Under it, nothing is printed
# -- the accepted path already prints its landing line and a second line per
# upload would bury it.
_BLOB_HOLD_REPORT_S = 5.0

# THE HARD DEADLINE ON THE MARKED SPAN, AND IT IS THE `T` THE AGE GATE IS
# DERIVED FROM.
#
# WHAT IT BOUNDS, stated so the derivation below rests on something true: the
# interval between the marker's creation and the last instant at which a row
# naming that blob could still be INSERTED. Past T the request has decided --
# the row is committed, or the request answered 503 and will never attempt an
# INSERT for this blob, or the commit outcome is unknown and the marker is
# left deliberately for the sweep to resolve by asking the database.
#
# It is NOT "no marker outlives T", and an earlier version of this comment
# said so: the indeterminate-commit arm's marker outlives it on purpose, and
# so does a shielded section still writing after its handler refused. Neither
# extends the span above, because neither can still insert a row.
#
# WHERE IT IS ENFORCED: `_span_budget`, at EVERY await inside the span -- the
# shielded section, the INSERT and the commit -- each given what is LEFT of
# the one deadline taken in `upload_auto_log`, so the three cannot sum past
# it. The previous version wrapped the section alone and claimed the whole
# span; the INSERT and the commit ran under no ceiling at all.
#
# WHAT IT BUYS. `_ORPHAN_MIN_AGE_S` below is `AUTO_LOG_SWEEP_EVERY_S + 2 * T`,
# which is strictly greater than T plus one retention tick, so a marker past
# the gate belongs to a request that can no longer insert a row for it. That
# is a BOUND rather than a hope, and the suite reds both when the gate is
# lowered below T and when an await inside the span loses its budget.
#
# It is generous on purpose: an upload that has held the volume lock, written
# its blob and committed inside a minute is every healthy upload, and the
# refusal a slow one gets is the same "try after the next match" every other
# refusal on this path gives (#276/#430).
AUTO_LOG_MARKED_SPAN_DEADLINE_S = 60.0

# The token the indeterminate-commit arm prints and the orphan sweep matches,
# and -- since the method change -- the SUFFIX of the marker FILE that makes a
# blob collectable at all. ONE literal for all three: the handler writes a blob
# it cannot prove has a row, the marker beside it is the only thing that ever
# offers that blob to the sweep, and the sweep is the only thing that removes
# it. Two spellings would be two chances for the recovery line to name
# something nothing collects (#432).
_ORPHAN_MARKER = "orphan-candidate"
_ORPHAN_MARKER_SUFFIX = "." + _ORPHAN_MARKER

# THE MARKERS A LIVE UPLOAD OWNS, and the reason cancellation cannot produce a
# deleted-from-under-you blob in this process.
#
# The retention loop runs in the SAME process as the handler -- it is started
# from main's `lifespan` -- so "is a request still working on this blob" is a
# question this process can answer exactly rather than infer from an mtime. A
# name is added before the marker file is created and removed only once the
# request has decided (row committed, blob discarded, or marker deliberately
# left behind), and the sweep skips every name in it WHATEVER ITS AGE.
#
# The age gate above is the second line, not the first: it covers the case this
# set cannot see, which is a marker left by a PREVIOUS process life. In that
# case the writer is gone by definition, because the process it ran in is.
_MARKERS_IN_FLIGHT: set[str] = set()

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

# ORPHAN SWEEP: how old a MARKER has to be before "no row names its blob" is
# read as "no row ever will".
#
# DERIVED FROM THE TICK AND FROM THE HANDLER'S OWN DEADLINE, so the three
# cannot be tuned apart: `AUTO_LOG_SWEEP_EVERY_S + 2 * T`. What T bounds is
# the interval between a marker's creation and the last instant at which a row
# naming its blob could still be inserted (`AUTO_LOG_MARKED_SPAN_DEADLINE_S`),
# and this gate is strictly greater than T plus one retention tick. So a
# marker past this gate belongs to a request that has already decided, and
# "no row names it" cannot turn into "a row names it" underneath the pass.
#
# It is a second line rather than the first: the in-process
# `_MARKERS_IN_FLIGHT` set already excludes every marker a live request owns,
# and what remains for the gate is a marker left behind by a process life that
# has ended -- or one this process's own request left deliberately.
#
# The sweep exists because ONE arm of the upload deliberately keeps a blob it
# cannot prove has a row -- the indeterminate commit. Without a collector that
# arm is a slow leak on a volume shared with player-filed attachments, which
# is the one thing this route is not allowed to spend.
_ORPHAN_MIN_AGE_S = AUTO_LOG_SWEEP_EVERY_S + 2.0 * AUTO_LOG_MARKED_SPAN_DEADLINE_S

# Blobs UNLINKED per pass.
#
# THERE IS NO EXAMINATION CEILING ANY MORE, AND ITS ABSENCE IS THE METHOD
# CHANGE. An earlier version of this sweep took the ATTACHMENT HEAP as its
# population and bounded the examination at `50 * _ORPHAN_BATCH` files. That
# directory holds every player-filed attachment permanently and nothing in
# this tree deletes a referenced one, so the budget was spent on files the
# pass is REQUIRED to keep: past that many older referenced attachments, a
# newer orphan was never offered to the database at all. A cap over the heap
# is a starvation class, so the heap stopped being the population and the cap
# was deleted rather than raised (#310).
#
# The population is now the MARKER SET, which every pass CONSUMES -- each
# marker is cleared over a committed row, or taken with its blob, or skipped
# because a live request owns it. A set that shrinks by being worked cannot
# starve, so enumerating all of it is what keeps the pass honest; the only
# bound worth having is on the irreversible half, which is how many blobs one
# pass may REMOVE. Candidates are ordered OLDEST FIRST, so a backlog larger
# than one batch drains across ticks.
_ORPHAN_BATCH = _PRUNE_BATCH

# Names per `log_filename = ANY(...)` lookup. The marker set is small by
# construction, but a single bound array parameter of unknown size is still a
# statement nobody wants to see in a log; the predicate is unchanged and the
# chunks are unioned.
_ORPHAN_NAME_CHUNK = 500


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


def _unlink_if_present(path) -> bool:
    """Remove `path`; answer whether it is GONE.

    An absent file answers True -- the caller wanted it gone and it is. An
    unlink that RAISES answers False, and that distinction is the whole
    difference between "discarded" and "still on the volume": a caller that
    cannot tell the two apart writes a record saying a blob was cleaned up
    while the blob is still there, which is a false cleanup nobody can find
    again. This function never prints; the caller owns the wording, because
    only the caller knows what the file's survival means.
    """
    if path is None:
        return True
    try:
        os.unlink(str(path))
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def _unlink_existing(path) -> str:
    """Remove `path` and say WHICH of the three things happened.

    `removed` -- the file was there and is not now.
    `absent`  -- there was nothing to remove.
    `failed`  -- the unlink raised and the file is still on the volume.

    `_unlink_if_present` above collapses the first two on purpose: most
    callers only want to know whether the file is gone. The orphan sweep is
    the caller that does not. Counting an absent file as a removal makes the
    pass report bytes it never reclaimed, and the operator reading that line
    decides the leak is draining at N an hour while nothing has drained
    (#304). One function per question, rather than one boolean that has to
    mean two things (#430).
    """
    if path is None:
        return "absent"
    try:
        os.unlink(str(path))
        return "removed"
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "failed"


def _marker_path(blob_path):
    """The marker that sits BESIDE a blob and is the only thing that offers it
    to the orphan sweep."""
    return blob_path.with_name(blob_path.name + _ORPHAN_MARKER_SUFFIX)


def _fsync_dir(directory) -> None:
    """Commit the DIRECTORY ENTRY a marker was just created in.

    On Linux -- which is what the api container runs -- `fsync` on the file's
    own descriptor commits the file's bytes and says nothing about the entry
    naming it, so a crash can leave the marker's data durable and its name
    absent. The entry needs its own `fsync` on a descriptor opened with
    `O_DIRECTORY`.

    On a platform with no directory handle to open (`os.O_DIRECTORY` absent --
    Windows, where this suite runs), `FlushFileBuffers` behind `os.fsync`
    already commits the entry with the file, so there is nothing to do here.
    The test is for the CAPABILITY, not for a platform name, so a platform
    that gains one is covered without an edit.

    IT DOES NOT SWALLOW. A directory that will not flush is a volume on which
    this marker cannot be made durable, and the caller's answer to that is to
    refuse the upload -- never to write a blob and hope, and never to fall
    back to walking the heap.
    """
    flag = getattr(os, "O_DIRECTORY", None)
    if flag is None:
        return
    fd = os.open(str(directory), os.O_RDONLY | flag)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _stamp_marker(blob_path) -> None:
    """Create this blob's marker, DURABLY, before the blob has any bytes.

    Off the event loop, like every other filesystem call on this path: two
    fsyncs on a contended volume are not something to do on the loop.

    The content is the blob's own name plus a newline. It is not what the
    sweep reads -- the sweep reads the marker's NAME -- but a zero-byte file
    is indistinguishable from a failed create when an operator looks at the
    directory, and one line costs nothing.
    """
    marker = _marker_path(blob_path)
    # O_BINARY for the same reason `_write_blob` takes it: `os.open` is TEXT
    # mode on this development seat, which would make the content the blob's
    # name plus CR LF rather than the name plus a newline this docstring and
    # the notes' disk bound both claim. Absent on Linux, where it reads 0.
    fd = os.open(str(marker),
                 os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0),
                 0o600)
    try:
        os.write(fd, blob_path.name.encode("utf-8") + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(blob_path.parent)


def _delete_blob_then_marker(blob_path) -> tuple[str, bool]:
    """Remove a blob and then its marker, with the FIRST removal made durable
    before the second is issued. Answers (the blob's state, marker gone).

    THE ORDER IS ONE WAY ROUND, AND SINCE THIS FUNCTION EXISTS IT IS A
    PERSISTENCE ORDER RATHER THAN A CALL ORDER. The blob goes first, so the
    only state an interruption can leave is a marker whose blob is absent --
    disposition 5, cleared by the next pass at no cost. The other way round
    leaves an unreferenced blob with nothing naming it, which is the one
    state this whole mechanism exists to make unreachable.

    ISSUING THE TWO UNLINKS IN THAT ORDER DOES NOT SURVIVE A HOST CRASH ON
    ITS OWN. Neither removal is durable until the directory entry is
    flushed, and a filesystem promises no order between two un-synced entry
    changes: a power loss can persist the marker's removal while recovering
    the blob's entry, which is exactly the forbidden state. `_fsync_dir`
    between the two is what makes the order a property of the disk instead
    of a property of these lines (#507 -- a crash window that is MOVED is
    not a crash window that is CLOSED).

    ONE FUNCTION, SO THERE IS ONE SITE. The determinate cleanup
    (`_release_marked_blob`) and the orphan sweep both delete a blob and
    then its marker; a barrier added to one and not the other is the class
    defect rather than the line defect (#432). Both call this.

    A FAILED BLOB UNLINK KEEPS THE MARKER and takes no barrier: the blob
    survived, so the marker is what offers it to the next pass, and there is
    no removal to persist. The caller owns the wording, because only the
    caller knows what the file's survival means.
    """
    state = _unlink_existing(blob_path)
    if state == "failed":
        return state, False
    _fsync_dir(blob_path.parent)
    return state, _unlink_if_present(_marker_path(blob_path))


class _MarkedBlob:
    """One request's claim on one blob file and the marker beside it.

    WHY AN OBJECT AND NOT FOUR LOCALS. The reserve section runs as its own
    task so that cancelling the handler cannot separate measure from write
    (see `_reserve_stamp_and_write`), and the handler and that task have to
    agree afterwards about who cleans up. `abandoned` is the handler saying "I
    stopped waiting"; the section reads it in its own `finally` with no await
    between the read and its return, so exactly one of the two performs the
    cleanup and never both:

    * the handler sets `abandoned` and then asks whether the section is done.
      Not done means the section has not yet reached its check and will see
      the flag. Done means the section already returned, so the handler does
      it.

    `marked` and `written` are what is on disk, so a cleanup knows whether
    there is anything to remove.

    WHY THERE IS A LOCK ON IT AND NOT ONLY A FLAG. `asyncio.to_thread` does
    not stop a worker thread. Cancelling the section's await raises in the
    COROUTINE while the thread is still on its way to `open()`, so a cleanup
    that ran in that window unlinked a file that did not exist yet, removed
    the marker, and the thread created the blob afterwards -- an unreferenced
    file with nothing naming it, which is the one state this mechanism exists
    to make unreachable. It is a race of microseconds and it is still a state,
    and "the cleanup usually gets there second" is ordering luck rather than a
    construction.

    So `lock` covers BOTH sides of the question: every creation of this blob
    or its marker happens under it and checks `discarded` inside it, and every
    removal of either happens under it and sets `discarded` first. Only two
    interleavings remain and both are safe -- the worker creates the file and
    the cleanup then removes something that exists, or the cleanup goes first
    and the worker creates nothing.

    THE CLEANUP MAY THEREFORE WAIT ON A WRITE IN PROGRESS. It is reached on
    the event loop and the wait is as long as the write it is waiting for.
    That wait happens only on a cancelled section -- every other caller runs
    after the write has returned, where the lock is free -- and it fails in
    the right direction: nothing has been removed while it waits, so a process
    killed in that window leaves the marker beside the blob, which is the pair
    the sweep collects.
    """

    __slots__ = ("path", "marked", "written", "failed", "abandoned",
                 "lock", "discarded")

    def __init__(self, path):
        self.path = path
        self.marked = False
        self.written = False
        self.failed = False
        self.abandoned = False
        self.lock = threading.Lock()
        self.discarded = False


def _clear_marker(own: "_MarkedBlob") -> bool:
    """Drop the marker and KEEP the blob -- the row is committed.

    A marker that will not unlink is not an error worth failing an accepted
    upload over: the next sweep finds it, asks the database, is told a row
    names the blob, and clears it then. That is disposition 2 of the sweep and
    it exists precisely so this call is allowed to fail.

    UNDER THE BLOB'S OWN LOCK, like every other removal on this path, so it
    cannot interleave with a worker still creating the marker. It does NOT set
    `discarded`: that flag means "no file for this blob may exist", and the
    blob is exactly what this call keeps.
    """
    with own.lock:
        gone = True if not own.marked else _unlink_if_present(_marker_path(own.path))
        own.marked = not gone
    _MARKERS_IN_FLIGHT.discard(own.path.name)
    return gone


def _release_marked_blob(own: "_MarkedBlob") -> bool:
    """Remove the blob and then its marker, for a failure KNOWN to have left
    no row naming it. Answers whether the BLOB is gone.

    THE ORDER IS LOAD-BEARING AND IT IS ONE WAY ROUND. The blob goes first, so
    the only state a crash between the two unlinks can leave is a marker whose
    blob is absent -- which the next sweep clears at no cost. The other order
    would leave an unreferenced blob with nothing naming it, which is the one
    state this whole mechanism exists to make unreachable.

    AND THE ORDER IS MADE PERSISTENT, not merely issued: the two unlinks go
    through `_delete_blob_then_marker`, which flushes the directory entry
    between them so a host crash cannot recover the blob while the marker's
    removal has already persisted. The sweep's own deletion arm calls the
    same function, because the barrier belongs to the OPERATION and not to
    one of its two callers (#432).

    An unlink that RAISES therefore keeps the marker: the blob survived, and
    the marker is what will offer it to the sweep. The caller says so in its
    line rather than reporting a discard that did not happen.

    `discarded` IS SET FIRST AND UNDER THE LOCK. A worker thread that has not
    yet reached its `open()` then creates nothing, so this call cannot leave
    behind a file it has already decided must not exist. That is what makes "a
    blob with no marker" unreachable by construction instead of by which of
    the two got there first; it is also why this call can block while a write
    finishes, which is the price and is named in `_MarkedBlob`.
    """
    with own.lock:
        own.discarded = True
        state, marker_gone = _delete_blob_then_marker(own.path)
        blob_gone = state != "failed"
        if blob_gone:
            own.written = False
            if own.marked and marker_gone:
                own.marked = False
    _MARKERS_IN_FLIGHT.discard(own.path.name)
    return blob_gone


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
    """Write the blob and make it DURABLE before this call returns.

    THIS IS A PERSISTENCE CALL, NOT A WRITE, and the difference is what the
    row that follows it is allowed to claim. `write()` puts the bytes in the
    page cache and `close()` promises nothing about them, so a host power
    loss after the INSERT has committed could recover a row naming a blob
    that is empty, truncated, or absent from the directory altogether -- a
    detail view reporting a read error over a file the database says exists.
    An ordering that survives the PROCESS is not an ordering that survives
    the HOST (#507).

    TWO BARRIERS, IN THIS ORDER, AND BOTH BEFORE THE INSERT:

      * `os.fsync(fd)` commits the CONTENTS of the file;
      * `_fsync_dir(path.parent)` commits the directory ENTRY that names
        them. On Linux -- which is what the api container runs -- `fsync` on
        the file's own descriptor says nothing about the entry, so without
        this a crash can recover fully written bytes under no name at all.

    WHERE THE COST IS CHARGED, because a barrier outside the budget is a
    barrier that lengthens the span the sweep's age gate is derived from.
    Both run inside `_guarded_write`, on the worker thread, inside the
    reserve section -- and the handler awaits that section under
    `_span_budget`, as it does the INSERT and the commit. So the flush is
    spent out of the SAME `T`: a volume whose flush does not return ENDS the
    span and refuses 503 rather than extending it.

    IT DOES NOT SWALLOW. A blob that cannot be made durable raises; the
    section's cleanup removes what it wrote and the upload is refused, which
    is the direction `_stamp_marker` fails in for the same reason (#276).

    The mode is the one the builtin `open(path, "wb")` this replaced used --
    0o666 less the process umask -- so nothing about who can read a stored
    blob changed with the barriers.
    """
    # O_BINARY IS NOT COSMETIC ON THIS DEVELOPMENT SEAT. `os.open` defaults to
    # TEXT mode on Windows, where every 0x0A in a gzip stream would be written
    # as 0x0D 0x0A -- a stored blob one byte longer than the row says and not
    # a gzip file any more. The builtin `open(path, "wb")` this replaced set
    # the flag itself; doing it by hand means saying so. The constant does not
    # exist on Linux, where the api runs, so it reads 0 there.
    fd = os.open(str(path),
                 os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0),
                 0o666)
    try:
        # os.write may write fewer bytes than it was given; one call is a
        # partial file waiting for a large enough blob.
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(path.parent)


def _guarded_stamp(own: "_MarkedBlob") -> None:
    """Create this blob's marker on a worker thread, unless a cleanup has
    already decided the blob must not exist.

    The check and the create are ONE critical section with every removal on
    this path (`_MarkedBlob.lock`), so a cancellation cannot land between
    them and leave a marker behind that its own cleanup has already tried to
    remove.
    """
    with own.lock:
        if own.discarded:
            return
        _stamp_marker(own.path)


def _guarded_write(own: "_MarkedBlob", data: bytes) -> None:
    """Write the blob on a worker thread under the same lock and the same
    condition.

    A cleanup that ran while this call was still queued on the executor has
    set `discarded`, and then this creates NOTHING -- so there is no file left
    on the volume that the cleanup could have missed. `written` is set inside
    the lock, so the state the cleanup reads is the state the thread left.
    """
    with own.lock:
        if own.discarded:
            return
        _write_blob(own.path, data)
        own.written = True


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


class _SpanExpired(TimeoutError):
    """The marked span's deadline had already passed when the next await
    inside it was about to start.

    A `TimeoutError` subclass on purpose. Every arm inside the span already
    has to handle the deadline firing DURING an await; this is the same event
    one moment earlier, and one exception type means one disposition per arm
    rather than two that can drift apart.
    """


def _span_budget(deadline: float) -> float:
    """What is left of `T` for the next await inside the marked span, and the
    place the bound is actually enforced.

    IT IS ENFORCED AT EVERY AWAIT IN THE SPAN, not around one of them. The
    span is measure -> stamp -> write -> INSERT -> commit, and a `wait_for`
    around the first three bounds only the first three: the INSERT and the
    commit then run under no ceiling at all, which is what made the derivation
    of `_ORPHAN_MIN_AGE_S` a claim rather than a bound. Each await is given
    what is LEFT of the one deadline, so the parts cannot sum past it however
    the time is distributed between them.
    """
    left = deadline - time.monotonic()
    if left <= 0.0:
        raise _SpanExpired()
    return left


async def _release_marked_blob_off_loop(own: "_MarkedBlob") -> bool:
    """`_release_marked_blob`, performed on a worker thread.

    IT TAKES THE BLOB'S LOCK, AND A WORKER MAY BE HOLDING THAT LOCK THROUGH
    AN 8 MiB WRITE AND TWO FSYNCS. Called on the event loop, this cleanup
    therefore stops every other request on this worker for as long as that
    write takes -- and the one caller that can reach it while a write is
    still in flight is a CANCELLED section: loop close, or the container's
    SIGTERM during a rebuild. That is the moment the loop has least business
    being frozen, because what is queued behind it is every other seat's
    queue join, match report and chat poll.

    So the WAIT happens in a thread and the loop stays free. Every other
    caller of `_release_marked_blob` runs after the write has returned, where
    the lock is uncontended and a direct call blocks nobody; those are left
    as they are rather than routed through an executor hop they do not need.

    IT IS NOT MADE OPTIONAL OR GIVEN UP ON. What the lock buys is that a
    cleanup cannot leave behind a file a worker creates after it, and a
    cleanup that abandoned the wait would put that state back (LENS-2). The
    wait is bounded by the write it is waiting for, which is bounded by the
    volume's own stall ceiling and by `T`.
    """
    return await asyncio.to_thread(_release_marked_blob, own)


async def _reserve_stamp_and_write(own: "_MarkedBlob", data: bytes,
                                   steam_id: str, span_deadline: float) -> None:
    """MEASURE, STAMP, WRITE -- one section, and cancellation cannot separate
    it into parts.

    WHY IT IS A FUNCTION AND A TASK. This used to be an inline block awaited by
    the handler, with the lock released in the handler's own `finally`.
    Cancelling that await -- a client disconnect, a server shutdown, the
    deadline below -- ran the `finally` and released the lock while
    `asyncio.to_thread` went on writing in its worker, because nothing cancels
    a thread. The next upload could then measure a volume the previous one had
    not finished writing to, which is exactly the bound
    `_BLOB_RESERVE_LOCK` exists to hold, and the cancelled request could leave
    bytes on the volume with nobody left to account for them.

    So the section is its own task and the handler awaits it through
    `asyncio.shield`. A cancelled handler does not cancel this; the lock is
    released HERE, in this coroutine's `finally`, after the write has actually
    returned. If the handler stopped waiting it says so with `own.abandoned`,
    and this coroutine performs the cleanup on its way out.

    THE MARKER IS STAMPED BEFORE THE BYTES EXIST. `_stamp_marker` fsyncs the
    marker and its directory entry, and RAISES if it cannot -- a volume that
    cannot record the marker is a volume this route refuses rather than one it
    writes an uncollectable blob onto. From the instant `open()` is called on
    the blob there is a durable marker naming it, so no arm of this handler,
    and no crash between any two lines of it, can produce a blob that the
    sweep has no way of finding.

    AND THAT COVERS THIS TASK BEING CANCELLED, not only the handler being
    cancelled -- which is a different event and for a while was the only one
    this docstring reasoned about. Loop shutdown cancels the bare task; the
    `except BaseException` below then runs the cleanup while a worker thread
    may still be on its way to `open()`, and nothing cancels a thread. The
    ORDERING is not what makes that safe: `_MarkedBlob.lock` is, because every
    creation of the blob or its marker and every removal of either happen
    under it, and a creation checks `discarded` inside it (see `_MarkedBlob`,
    `_guarded_stamp`, `_guarded_write`). So the cleanup either removes a file
    that exists or stops one from being made, and "a blob with no marker"
    is unreachable rather than unlikely.

    THAT CLEANUP RUNS IN A THREAD, NOT ON THE LOOP. It has to take the blob's
    lock, and the worker may hold that lock through the write and its two
    fsyncs; taking it on the event loop stopped every other request on this
    worker for that whole time, in the one window -- loop close, container
    SIGTERM -- where that is least affordable. The ordering is unchanged and
    so is the guarantee; only the thread that waits moved
    (`_release_marked_blob_off_loop`).

    AND EVERY HOP INSIDE THIS SECTION SPENDS `span_deadline`. The stamp and
    the write are each awaited for what is LEFT of the one deadline the
    handler took, so the durability barriers they perform are charged to `T`
    exactly as the INSERT and the commit are: a volume whose flush does not
    return ENDS the span rather than extending the interval the sweep's age
    gate is derived from.
    """
    hold_started = time.monotonic()

    # BEFORE THE WAIT: IS THERE ANYTHING TO WAIT FOR? The wait is served
    # inside this request's open transaction, so it is paid in pooled
    # connections (see `_BLOB_WRITE_STALL_S`). A measure-and-write that has
    # already been in flight past the stall ceiling is a volume that is not
    # answering, and every request that queues behind it spends a connection
    # for the full ceiling to be told the same 503 it could have had at once.
    in_flight = _BLOB_WRITE_STARTED[0]
    stalled_for = (time.monotonic() - in_flight) if in_flight else 0.0
    if stalled_for >= _BLOB_WRITE_STALL_S:
        print(f"[AUTO-LOG] refused 503: the blob volume has had a write in "
              f"flight for {stalled_for:.1f}s (ceiling {_BLOB_WRITE_STALL_S}s), "
              f"so this upload refuses now rather than holding a database "
              f"connection for {_BLOB_RESERVE_LOCK_WAIT_S}s to be refused then")
        raise HTTPException(status_code=503, detail="log storage unavailable")
    try:
        await asyncio.wait_for(_BLOB_RESERVE_LOCK.acquire(),
                               _BLOB_RESERVE_LOCK_WAIT_S)
    except (asyncio.TimeoutError, TimeoutError):
        print(f"[AUTO-LOG] refused 503: waited {_BLOB_RESERVE_LOCK_WAIT_S}s "
              f"for the blob-volume lock and did not get it -- refusing "
              f"rather than measuring the reserve against a reading this "
              f"request never took")
        raise HTTPException(status_code=503, detail="log storage unavailable")

    _BLOB_WRITE_STARTED[0] = time.monotonic()
    try:
        # LEAVE THE LAST OF THE VOLUME TO THE PATH THAT HAS A PERSON WAITING.
        #
        # This corpus and the bug form's attachments share one directory, and
        # this is the half that grows by itself: up to twelve blobs per
        # opted-in account per day, held fourteen days. When the volume fills,
        # THIS route handles it correctly -- it unlinks, answers 503, and the
        # client tries after the next match. `submit_bug_report` does not: its
        # write failure is caught, logged and fallen through, so the report
        # commits with no attachment and the player is answered 200 by a
        # server that just lost their log.
        #
        # So the automatic path stops first, while there is still room for the
        # one that cannot retry. Refusing here rather than at ENOSPC also
        # means no partial file is written on a volume that is already out of
        # space.
        free = _free_bytes(own.path.parent)
        if free < 0:
            # UNKNOWN IS A REFUSAL. This arm used to be the admitting one --
            # `free >= 0 and ...` skipped the whole guard when the volume
            # would not answer -- so the reserve stopped existing in exactly
            # the conditions that produce an unreadable volume. Which
            # direction the unhandled case fails in is the question (#276),
            # and the answer here is: toward the path that has a person
            # waiting on it.
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

        # THE REGISTRY ENTRY GOES IN BEFORE THE MARKER FILE, and the marker
        # file before the bytes. Each step is only ever ADDING something that
        # protects the blob, so there is no instant at which a blob exists
        # with nothing naming it -- not between two lines here, and not across
        # a crash between them.
        _MARKERS_IN_FLIGHT.add(own.path.name)
        own.marked = True
        # EACH HOP CARRIES WHAT IS LEFT OF THE ONE DEADLINE. The stamp is two
        # fsyncs and the write below is up to 8 MiB plus two more, and both
        # are inside the marked span -- so both spend `T` rather than sitting
        # outside it. `asyncio.to_thread` cannot stop the worker, so what the
        # ceiling ends is this coroutine's WAIT: the section stops waiting,
        # runs its cleanup, and the cleanup's `discarded` flag is what stops
        # the thread from creating anything afterwards.
        await asyncio.wait_for(asyncio.to_thread(_guarded_stamp, own),
                               _span_budget(span_deadline))

        # Off the event loop, like the compression in the handler: this is a
        # write of up to 8 MiB, and on a slow or contended volume it blocks
        # every other request on this worker for as long as it takes.
        #
        # INSIDE the reserve lock, not after it. The measurement above is only
        # a decision about this write if this write is the one that follows
        # it; releasing between the two is the gap the lock exists to close --
        # and NOT releasing it on a cancellation is what makes that true when
        # the request goes away mid-write.
        await asyncio.wait_for(asyncio.to_thread(_guarded_write, own, data),
                               _span_budget(span_deadline))
    except BaseException:
        own.failed = True
        raise
    finally:
        # ONE OF US CLEANS UP, AND THIS IS THE HALF THAT KNOWS IT IS STILL
        # RUNNING. Read `abandoned` here, with no await between the read and
        # the return, so that a handler which sets it after this point
        # observes `done()` and cleans up itself.
        #
        # AND IT RUNS BEFORE THE VOLUME IS HANDED ON, not after.
        # `_release_marked_blob` takes the blob's own lock, so once it returns
        # no worker thread of this section can still create a file: either it
        # had already written and the unlink took what it wrote, or it is
        # queued and `discarded` stops it. Releasing the reserve lock first
        # would hand the next upload a volume this section may still be
        # writing to, which is the bound the lock exists to hold and the same
        # class of mistake the cancelled `await` used to make (R2-M1).
        #
        # AND IT WAITS IN A THREAD, NEVER ON THE EVENT LOOP. This is the one
        # call site that can reach the cleanup while a worker still holds the
        # blob's lock -- a cancelled section, i.e. loop close or the
        # container's SIGTERM -- and taking that lock on the loop froze every
        # other request on this worker for the length of the write. The
        # ordering above is unchanged; only the thread that waits is.
        try:
            if own.failed or own.abandoned:
                if not await _release_marked_blob_off_loop(own):
                    print(f"[AUTO-LOG] the blob for {own.path.name} could not "
                          f"be removed after a failed or abandoned write; it "
                          f"SURVIVES and its {_ORPHAN_MARKER} marker is kept "
                          f"so the orphan sweep collects it")
        finally:
            # THE LOCK IS RELEASED WHATEVER HAPPENED TO THE CLEANUP ABOVE. A
            # second cancellation delivered while this coroutine waits in its
            # own `finally` must not leave the volume lock held for the life
            # of the process: the cleanup goes on in its thread, and the only
            # thing lost is the ordering guarantee, in a window where the
            # process is already being torn down.
            #
            # The in-flight stamp is cleared BEFORE the release, so the next
            # waiter can never read a stamp belonging to a pass that has
            # already handed the lock on.
            _BLOB_WRITE_STARTED[0] = 0.0
            _BLOB_RESERVE_LOCK.release()

        # MEASURED, whichever way this went. This span -- the wait for the
        # volume lock plus the measure-and-write under it -- is the part of
        # the open transaction that this route added when admission moved
        # ahead of the write, and it is the part a contended volume extends.
        # Reported only past the ceiling, so an ordinary upload still prints
        # exactly one landing line.
        held = time.monotonic() - hold_started
        if held >= _BLOB_HOLD_REPORT_S:
            print(f"[AUTO-LOG] slow blob volume: {held:.1f}s holding an open "
                  f"transaction and the per-account lock for {steam_id} "
                  f"across the volume lock and a {len(data)}-byte write "
                  f"(report ceiling {_BLOB_HOLD_REPORT_S}s)")


def _drain_section_error(task) -> None:
    """Consume the exception of a section the handler stopped waiting for, so
    an abandoned task does not surface as a "never retrieved" warning on a
    path whose whole job is to be quiet."""
    if not task.cancelled():
        task.exception()


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

    # The path resolution has its own arm: _bug_report_log_path creates the
    # directory, so an unusable BUG_REPORT_LOG_DIR fails here and not at
    # open(). Uncaught that becomes a 500, and 500 vs 503 is not cosmetic here
    # -- the client half is a background retry loop, and 503 is the code that
    # says the same request will work later. Nothing exists yet for it to
    # clean up.
    try:
        path = _bug_report_log_path(str(report_id))
    except Exception as ex:
        print(f"[AUTO-LOG] refused 503: the blob directory could not be "
              f"resolved for {report_id} ({type(ex).__name__})")
        raise HTTPException(status_code=503, detail="log storage unavailable")

    # THE MARKED SPAN: measure, stamp, write, INSERT, commit.
    #
    # The measure-stamp-write third of it is a SEPARATE TASK awaited through
    # `asyncio.shield`, so that cancelling this handler cannot separate the
    # measurement from the write it decides (see `_reserve_stamp_and_write`).
    #
    # ONE DEADLINE GOVERNS THE WHOLE OF IT, taken here and spent by every await
    # inside the span. `_span_budget(span_deadline)` is what each of the three
    # -- the section, the INSERT, the commit -- is given, so they cannot sum
    # past T however the time is distributed between them. The previous
    # version put `AUTO_LOG_MARKED_SPAN_DEADLINE_S` around the section alone
    # and said in a comment that the whole span was bounded; the INSERT and
    # the commit ran under no ceiling, so the sentence the sweep's age gate is
    # derived from was not true of the code beneath it.
    #
    # ON TIMEOUT OR CANCELLATION the section is NOT cancelled -- it holds the
    # volume lock and a worker thread, and neither stops on request. It is
    # told it has been abandoned and cleans up its own blob and marker on its
    # way out; if it has already finished by then, this half does it instead.
    # A section still writing after T does not extend the bound: this half has
    # already refused, so no INSERT for that blob will follow it.
    span_started = time.monotonic()
    span_deadline = span_started + AUTO_LOG_MARKED_SPAN_DEADLINE_S
    own = _MarkedBlob(path)
    section = asyncio.ensure_future(
        _reserve_stamp_and_write(own, data, req.steam_id, span_deadline))
    section.add_done_callback(_drain_section_error)
    try:
        await asyncio.wait_for(asyncio.shield(section),
                               _span_budget(span_deadline))
    except HTTPException:
        # The reserve refusals inside the section are already the answer they
        # want to give, and the section has cleaned up after itself. Re-raised
        # as-is so it does not get rewritten into the generic storage failure
        # below and lose the one line that says WHY.
        raise
    except (asyncio.TimeoutError, TimeoutError):
        own.abandoned = True
        if section.done():
            _release_marked_blob(own)
        print(f"[AUTO-LOG] refused 503: the measure-and-write for {report_id} "
              f"passed its {AUTO_LOG_MARKED_SPAN_DEADLINE_S}s deadline; the "
              f"write is left to finish and discard itself, and the client is "
              f"told to try after the next match")
        raise HTTPException(status_code=503, detail="log storage unavailable")
    except asyncio.CancelledError:
        # The request went away. Same disposition as the deadline: the section
        # keeps the lock until its write returns and then removes what it
        # wrote. Re-raised, because a cancelled request has no answer to give.
        own.abandoned = True
        if section.done():
            _release_marked_blob(own)
        raise
    except Exception as ex:
        print(f"[AUTO-LOG] blob write failed for {report_id}: {type(ex).__name__}")
        raise HTTPException(status_code=503, detail="log storage unavailable")

    # THE REGISTRY ENTRY IS RELEASED ON EVERY EXIT PATH, cancellation
    # included. `_clear_marker` and `_release_marked_blob` each drop it on
    # the arms they own, but a request cancelled between the write and the
    # commit reaches neither -- and a name left in `_MARKERS_IN_FLIGHT`
    # after its request is gone would make the sweep skip that marker for
    # the life of the process, which is the one way this design could keep
    # a blob nothing collects. Dropping the name is always safe: the marker
    # FILE is what protects the blob, and it is still on disk.
    try:
        room = req.room_name or "an unnamed room"
        description = f"auto-upload after {req.mode or 'a match'} in {room}"
        try:
            left = _span_budget(span_deadline)
            row = (await asyncio.wait_for(db.execute(
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
            ), left)).mappings().first()
        except Exception as ex:
            # The INSERT raised, so there is DEFINITIVELY no row and the only thing
            # that could ever find this blob again does not exist. Remove it, blob
            # first and marker second. The rollback is explicit because under
            # asyncpg a caught statement error leaves the whole transaction
            # ABORTED, and the next statement on this session -- the opportunistic
            # prune, or anything a later dependency runs -- would raise on that and
            # not on its own fault.
            #
            # AND THE RECORD SAYS WHICH OF THE TWO OUTCOMES HAPPENED. An unlink
            # that raises leaves an unreferenced blob on the volume; a line saying
            # "blob discarded" over that state is a false cleanup record, and the
            # file it describes is one nobody goes looking for. So the marker is
            # KEPT in that case and the line says the blob SURVIVES and names it
            # for the sweep, which is the mechanism that collects it.
            discarded = _release_marked_blob(own)
            try:
                await db.rollback()
            except Exception:
                pass
            # ONE print statement, two outcomes. The branch is on the MESSAGE
            # and not on the printing, because this module's own suite reads
            # refusal paths structurally and a refusal whose only print sits
            # inside a conditional reads as a silent one (#438/#443).
            #
            # THE DEADLINE LANDS IN THIS ARM TOO. `_span_budget` gives the
            # statement only what is left of T, so a database that will not
            # answer ENDS the span instead of extending it -- and the
            # disposition is unchanged, because no COMMIT was issued for this
            # row and an uncommitted INSERT cannot become visible. The line
            # says which of the two happened rather than leaving it to be
            # inferred from an exception name.
            via = (f" (the {AUTO_LOG_MARKED_SPAN_DEADLINE_S}s marked-span "
                   f"deadline)" if isinstance(ex, TimeoutError) else "")
            outcome = ("blob discarded" if discarded else
                       f"the blob could NOT be removed and SURVIVES as "
                       f"{path.name} -- {_ORPHAN_MARKER}={path.name}, kept for "
                       f"the retention loop's orphan sweep")
            print(f"[AUTO-LOG] insert failed for {report_id}: "
                  f"{type(ex).__name__}{via}; {outcome}")
            raise HTTPException(status_code=503, detail="log storage unavailable")

        try:
            left = _span_budget(span_deadline)
            await asyncio.wait_for(db.commit(), left)
        except Exception as ex:
            # INDETERMINATE -- see FAILURE DIRECTION at the top. The blob STAYS,
            # AND SO DOES ITS MARKER. This is the one arm that deliberately leaves
            # an artifact behind: the row may have committed and the
            # acknowledgement been lost, and deleting the file then destroys the
            # only copy of a log a live row promises.
            #
            # The marker is what makes that safe rather than merely cheap. It was
            # stamped before the bytes existed and it is left in place here, so the
            # sweep has the file in its population either way: if the commit did
            # land a row names the blob and the sweep CLEARS the marker, keeping
            # the file for ever; if it did not, the file and its marker are
            # collected once past the age gate. Nothing has to be remembered by
            # anybody.
            #
            # THE MUTATION THIS ARM IS HELD BY -- and it is a mutation of code
            # that EXISTS, not an instruction to add a cleanup this arm must
            # never have -- is deleting the `_MARKERS_IN_FLIGHT.discard` below.
            # That set means "a live request owns this marker" and the sweep
            # skips every name in it, so a name held after its request has
            # finished makes the marker permanent and the blob uncollectable for
            # the life of the process. The suite's control removes that line and
            # watches the sweep pass over a blob it should have taken.
            #
            # THE NAME IS DROPPED BEFORE THE ROLLBACK, not after. This request
            # has decided -- blob and marker stay, the sweep resolves them by
            # asking the database -- so nothing waits on the rollback to make
            # that true. A rollback that never returns, on the database that
            # has just stopped answering, would otherwise hold the name for
            # the life of the process, and a held name is precisely what makes
            # a marker permanent and its blob uncollectable.
            _MARKERS_IN_FLIGHT.discard(path.name)
            try:
                await db.rollback()
            except Exception:
                pass
            via = (f" (the {AUTO_LOG_MARKED_SPAN_DEADLINE_S}s marked-span "
                   f"deadline)" if isinstance(ex, TimeoutError) else "")
            print(f"[AUTO-LOG] commit INDETERMINATE for {report_id}: "
                  f"{type(ex).__name__}{via}; blob KEPT as {path.name} -- a row may or "
                  f"may not exist for it; {_ORPHAN_MARKER}={path.name}, collected "
                  f"by the retention loop's orphan sweep if no row names it")
            raise HTTPException(status_code=503, detail="log storage unavailable")

        # THE ROW IS COMMITTED, so the blob is referenced and the marker has done
        # its job. Clearing it is the ONLY way a marker is dropped while its blob
        # stays, and it is allowed to fail: the sweep's second disposition asks the
        # database, is told a row names the blob, and clears it then.
        _clear_marker(own)

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
    finally:
        _MARKERS_IN_FLIGHT.discard(path.name)

        # THE SPAN, MEASURED -- and this line is the bound's falsifier.
        #
        # The hold timer inside the section stops when the write returns, so
        # it cannot see the INSERT or the commit; a residual whose falsifier
        # reads only that line could not observe the half of the span that was
        # unbounded (#342/#431). This one runs from before the marker existed
        # to after the request has decided, so a span that outlived T on a
        # path that did NOT refuse is a line in the log rather than a
        # deduction from the code (#438/#443). Reported past the same ceiling
        # as the volume hold, so an ordinary upload still prints one line.
        span = time.monotonic() - span_started
        if span >= _BLOB_HOLD_REPORT_S:
            print(f"[AUTO-LOG] marked span for {report_id}: {span:.1f}s from "
                  f"before the marker existed to this request's decision "
                  f"(deadline {AUTO_LOG_MARKED_SPAN_DEADLINE_S}s, report "
                  f"ceiling {_BLOB_HOLD_REPORT_S}s)")


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


def _marker_candidates(base, cutoff: float, live: set) -> tuple[list[str], int, int, int]:
    """The blobs this pass may act on, OLDEST MARKER FIRST.

    Returns `(blob_names_oldest_first, markers_total, owned_by_a_live_upload,
    younger_than_the_gate)`.

    THE POPULATION IS THE MARKER SET AND NEVER THE DIRECTORY. This used to
    enumerate every file under `base`, keep the oldest `_ORPHAN_SCAN_MAX` aged
    ones in a heap and offer those to the database. That directory is the
    attachment heap: it holds every player-filed bug-report attachment
    permanently, and nothing in this tree deletes a referenced one. So the
    examination budget was spent on files the pass is REQUIRED to keep, and
    past that many older referenced attachments a newer orphan was never
    offered to the database at all -- a starvation class rather than a corner
    case. A cap over the heap cannot be fixed by raising it, so the heap
    stopped being the population (#310).

    A blob carries a marker only between the instant before its bytes exist
    and the instant its row commits, so a referenced file does not appear here
    at all and there is nothing to cap. Every marker this returns is one the
    pass then CONSUMES -- cleared over a committed row, or taken with its
    blob -- which is what makes a full enumeration finite in the way a heap
    walk never was.

    TWO EXCLUSIONS, and they are different questions:

    * `live` is the set of markers a request in THIS process still owns. Those
      are skipped whatever their age, because the answer to "is somebody still
      writing this" is one this process knows exactly rather than infers.
    * `cutoff` excludes a marker younger than the age gate. That covers the
      case the set cannot see -- a marker left by a process life that has
      ended -- and it is derived from the handler's own deadline, so a stalled
      write cannot outlive it.

    On the worker thread: a directory scan plus one `stat` per marker, on a
    volume that may be contended.

    A marker whose `stat` raises is SKIPPED rather than reported: the only
    thing this pass does with it is act on its blob, and a name that will not
    answer about its own age is not one to act on. Nothing is lost -- the next
    tick asks again.
    """
    aged: list[tuple[float, str]] = []
    markers_total = 0
    owned = 0
    young = 0
    try:
        entries = os.scandir(str(base))
    except OSError:
        return [], 0, 0, 0
    with entries:
        for e in entries:
            if not e.name.endswith(_ORPHAN_MARKER_SUFFIX):
                continue
            try:
                if not e.is_file():
                    continue
                mtime = e.stat().st_mtime
            except OSError:
                continue
            markers_total += 1
            blob = e.name[:-len(_ORPHAN_MARKER_SUFFIX)]
            if blob in live:
                owned += 1
                continue
            if mtime >= cutoff:
                young += 1
                continue
            aged.append((mtime, blob))
    aged.sort()
    return [name for _, name in aged], markers_total, owned, young


async def prune_orphan_blobs(db: AsyncSession, *, min_age_s: float | None = None,
                             limit: int = _ORPHAN_BATCH) -> dict:
    """Resolve every orphan-candidate MARKER: clear it over a committed row,
    or take its blob once the database refuses to name it.

    WHY THIS EXISTS. `upload_auto_log` has one arm that leaves a file behind
    it cannot account for: a commit whose outcome is UNKNOWN. That arm keeps
    the blob on purpose -- destroying a log because an acknowledgement was
    lost is the worse error -- and it leaves the marker in place. This is the
    other half of that decision. Without it the kept file is permanent, and
    the volume it is permanent on is shared with player-filed attachments.

    NOT SCOPED TO kind='auto', AND THAT IS THE SAFETY PROPERTY, NOT AN
    OVERSIGHT. `prune_auto_logs` above walks ROWS and must never touch a bug
    report; this decides the fate of FILES, where the only thing that protects
    a file is a row naming it -- and a player-filed report's row names its
    attachment exactly as an automatic row does. Scoping this lookup to
    kind='auto' would read a marked blob that a player-filed row names as
    unreferenced and delete it. So the predicate is `log_filename = ANY(...)`
    over the WHOLE table, and the control that reds when someone adds
    `kind = 'auto'` to it executes this function against a database holding
    rows of every kind rather than asserting on the statement's text.

    FIVE DISPOSITIONS, one per state a marker can be in:

    1. A marker a LIVE upload owns is skipped, whatever its age. The registry
       is in-process and the retention loop runs in that same process.
    2. A marker whose blob the table NAMES is CLEARED and the file is left
       alone. That is the commit that landed and whose marker clear did not --
       a crash between the two, or an unlink that raised -- and it is the
       reason `_clear_marker` is allowed to fail.
    3. A marker whose blob the table refuses to name, once past the age gate,
       has its BLOB removed and then its marker, with the blob's removal made
       DURABLE in between (`_delete_blob_then_marker`). That is what keeps a
       host crash between the two unlinks harmless: issuing them in order is
       not enough, because a filesystem persists two un-synced entry changes
       in whichever order it likes.
    4. `bug_reports` naming NO blob whatsoever, while markers exist, REFUSES
       the whole pass. That reading is not "everything here is an orphan"; it
       is "this process is talking to a database that does not own this
       directory" -- a restored volume, a mis-set BUG_REPORT_LOG_DIR, a
       pointed-at scratch database -- and the honest answer is to delete
       nothing (#276).
    5. A marker past the gate whose BLOB IS NOT ON THE VOLUME is a leftover
       and is counted as one. The design produces that state deliberately --
       a crash between the stamp and `open()`, or a cleanup interrupted
       between its two unlinks -- and clearing the marker is the whole of the
       work. It is reported as `marker-only` and NOT as a removal, because
       nothing was reclaimed; see the budget below.

    BOUNDED ON THE REMOVALS, and nowhere else. `limit` counts blobs actually
    taken off the volume, so a mistake is bounded by the batch; candidates are
    oldest first, so a backlog drains across ticks. There is no examination
    ceiling, because the population is consumed by being worked rather than
    re-read -- and disposition 5 costs no budget for the same reason
    disposition 2 does not: neither reclaims a byte, so neither can spend a
    slot this pass owes a real orphan and then report the leak as draining
    (#304).

    AND THE CLOSING LINE'S ARITHMETIC CLOSES. Every unreferenced candidate is
    removed, marker-only, unremovable, or deferred, and the line prints all
    four, so the number an operator reads as the drain rate can be checked
    against the population it came out of rather than taken on trust.

    A DISPOSITION IS REPORTED ONLY WHEN THE UNLINK THAT PERFORMS IT
    SUCCEEDED. Every arm that removes a marker reads the result: a marker a
    permission or I/O fault leaves on the volume is reported as NOT cleared
    and named for the next tick, never as `cleared` under a line an operator
    reads as work that was done. `unremovable` is the one term for "this
    candidate is unchanged on the volume and the next tick retries it",
    whichever of the two unlinks could not be taken -- one term, one meaning
    (#430). A removed blob whose marker survived is still `removed`, because
    the byte reclaim is what that term counts; the surviving marker is
    reported beside it and comes back next tick as disposition 5.

    THE TWO UNLINKS GO THROUGH `_delete_blob_then_marker`, which is also
    what the determinate cleanup calls: the blob-before-marker order, and
    the directory flush that makes that order survive a host crash, belong
    to the OPERATION and not to one of its two callers (#432).

    Read-only on the database: the transaction the SELECT opens is ENDED with
    a rollback, for the same reason the early returns above are (an
    idle-in-transaction connection holds back the vacuum horizon).
    """
    from main import BUG_REPORT_LOG_DIR

    base = pathlib.Path(BUG_REPORT_LOG_DIR)
    cutoff = time.time() - float(_ORPHAN_MIN_AGE_S if min_age_s is None else min_age_s)
    # A COPY, taken before the scan. The set is mutated by handlers between
    # awaits, and a membership test against a moving set is a different
    # question at the top of the loop than at the bottom.
    live = set(_MARKERS_IN_FLIGHT)
    names, markers_total, owned, young = await asyncio.to_thread(
        _marker_candidates, base, cutoff, live)
    if not names:
        return {"candidates": 0, "markers": markers_total, "in_flight": owned,
                "young": young, "orphans": 0, "unlinked": 0, "cleared": 0,
                "uncleared": 0, "markers_kept": 0,
                "marker_only": 0, "unremovable": 0, "deferred": 0,
                "refused": False}

    named_total = (await db.execute(
        text("SELECT COUNT(*) AS n FROM bug_reports WHERE log_filename IS NOT NULL")
    )).mappings().first()
    if not (named_total or {}).get("n"):
        await db.rollback()
        print(f"[AUTO-LOG] orphan sweep REFUSED: {len(names)} marked file(s) under "
              f"{base}, and bug_reports names no blob at all. That reads as a "
              f"database which does not own this directory, not as a directory "
              f"full of orphans -- nothing removed")
        return {"candidates": len(names), "markers": markers_total,
                "in_flight": owned, "young": young, "orphans": 0,
                "unlinked": 0, "cleared": 0, "uncleared": 0,
                "markers_kept": 0, "marker_only": 0,
                "unremovable": 0, "deferred": 0, "refused": True}

    # CHUNKED, and the predicate is the same one in every chunk. A name absent
    # from its own chunk's answer is unreferenced -- union, never intersect.
    known: set[str] = set()
    for start in range(0, len(names), _ORPHAN_NAME_CHUNK):
        chunk = names[start:start + _ORPHAN_NAME_CHUNK]
        known |= {r["log_filename"] for r in (await db.execute(
            text("""SELECT log_filename FROM bug_reports
                     WHERE log_filename = ANY(CAST(:names AS text[]))"""),
            {"names": chunk},
        )).mappings().all()}
    await db.rollback()

    # DISPOSITION 2 FIRST, because it is the one that removes nothing. A
    # marker over a blob the table names is a commit that landed; the file is
    # referenced and must never be touched.
    cleared = 0
    uncleared = 0
    for name in (n for n in names if n in known):
        if _unlink_if_present(base / (name + _ORPHAN_MARKER_SUFFIX)):
            cleared += 1
            print(f"[AUTO-LOG] orphan sweep: cleared {_ORPHAN_MARKER}={name} -- "
                  f"a bug_reports row names it, so the commit landed and the "
                  f"blob stays")
        else:
            # NOT cleared, and the line says so. The blob is referenced and
            # safe either way; what a `cleared` here would cost is an
            # operator's reading of a marker that keeps coming back.
            uncleared += 1
            print(f"[AUTO-LOG] orphan sweep: {_ORPHAN_MARKER}={name} is over a "
                  f"blob a bug_reports row names, and the marker could NOT be "
                  f"removed; the blob stays and the next tick retries the "
                  f"marker")

    # `names` is oldest-first, so `all_orphans` is too and the loop below
    # reaches the oldest unreferenced blobs first rather than whichever the
    # filesystem listed first. That ordering is what makes the deferred
    # remainder a BACKLOG -- the files taken here are gone by the next tick --
    # instead of a set that keeps being skipped. There is no slice: the budget
    # is spent INSIDE the loop and on removals only, which is what stops a
    # cohort that reclaims nothing from consuming it.
    all_orphans = [n for n in names if n not in known]
    unlinked = 0
    marker_only = 0
    unremovable = 0
    markers_kept = 0
    deferred = 0
    for name in all_orphans:
        # THE BUDGET IS SPENT ON REMOVALS AND ON NOTHING ELSE. `limit` counts
        # blobs actually taken off the volume, so a cohort of marker-only
        # leftovers -- which reclaim nothing -- cannot consume the slots this
        # pass owes to real orphans while the line still reads "200 removed,
        # 200 left for the next tick" (#304). The names are oldest-first, so
        # what is deferred here is a backlog the next tick takes.
        if unlinked >= int(limit):
            deferred += 1
            continue

        # THE BLOB FIRST, THEN ITS MARKER, AND THE FIRST REMOVAL MADE DURABLE
        # BEFORE THE SECOND IS ISSUED. A crash between the two then leaves a
        # marker whose blob is absent, which this pass reads as disposition 5;
        # the other order -- or this order with no barrier between, which a
        # filesystem may persist either way round -- leaves an unreferenced
        # blob with nothing naming it, the state this mechanism exists to make
        # unreachable. `_delete_blob_then_marker` is the one site that
        # performs it, and the determinate cleanup calls the same function.
        state, marker_gone = _delete_blob_then_marker(base / name)
        stuck = (state == "failed") or (state == "absent" and not marker_gone)
        if stuck:
            # COUNTED, for the same reason disposition 5 is counted separately.
            # A candidate that is neither removed, nor marker-only, nor
            # deferred, and appears in none of the three, is a hole in this
            # line's arithmetic -- and how much of the leak drained is exactly
            # the reading an operator takes from it (#304). ONE term for one
            # state: nothing on the volume changed for this candidate and the
            # next tick retries it, whichever of the two unlinks refused.
            unremovable += 1
            why = ("its blob is still on the volume and its marker is kept"
                   if state == "failed" else
                   "it has no blob on the volume and the marker itself would "
                   "not unlink")
            print(f"[AUTO-LOG] orphan sweep: {_ORPHAN_MARKER}={name} could not "
                  f"be removed -- {why}; nothing was reclaimed or cleared and "
                  f"the next tick retries it")
            continue
        if state == "absent":
            # DISPOSITION 5. Nothing was reclaimed, so nothing is counted as
            # removed: the marker was the only leftover, and it is reported
            # cleared only because the unlink above actually took it.
            # `_unlink_if_present` cannot tell this from a real removal by
            # design, which is why this arm asks `_unlink_existing` instead.
            marker_only += 1
            print(f"[AUTO-LOG] orphan sweep: cleared {_ORPHAN_MARKER}={name} -- "
                  f"marked, past the gate and NO BLOB on the volume; the marker "
                  f"was the only leftover and nothing was reclaimed")
            continue
        unlinked += 1
        if not marker_gone:
            markers_kept += 1
        after = ("its marker is cleared" if marker_gone else
                 "its marker could NOT be removed and SURVIVES, so the next "
                 "tick reads it as a marker with no blob")
        print(f"[AUTO-LOG] orphan sweep: removed {_ORPHAN_MARKER}={name} -- "
              f"marked, older than {int(_ORPHAN_MIN_AGE_S)}s and no "
              f"bug_reports row names it; {after}")

    # THE LINE ACCOUNTS FOR EVERY CANDIDATE, and the four terms after
    # "unreferenced" SUM to it: removed + marker-only + unremovable +
    # deferred. "0 unreferenced" over a population nobody can size is exactly
    # the reading that let the old heap-bounded pass report an hour of nothing
    # while the leak grew, and a term missing from the sum is the same mistake
    # one level down -- it lets an operator read a drain rate off a line whose
    # own arithmetic does not close (#304).
    print(f"[AUTO-LOG] orphan sweep: {markers_total} marker(s) on the volume, "
          f"{owned} owned by a live upload, {young} younger than the "
          f"{int(_ORPHAN_MIN_AGE_S if min_age_s is None else min_age_s)}s gate, "
          f"{len(names)} offered to the database, {cleared} cleared over a "
          f"committed row ({uncleared} over a committed row that would not "
          f"clear), {len(all_orphans)} unreferenced, {unlinked} removed "
          f"({markers_kept} of them leaving a marker behind), "
          f"{marker_only} marker-only with no blob to reclaim, "
          f"{unremovable} that could not be removed, "
          f"{deferred} left for the next tick")
    return {"candidates": len(names), "markers": markers_total,
            "in_flight": owned, "young": young, "orphans": len(all_orphans),
            "unlinked": unlinked, "cleared": cleared, "uncleared": uncleared,
            "markers_kept": markers_kept,
            "marker_only": marker_only, "unremovable": unremovable,
            "deferred": deferred, "refused": False}



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
