"""The frozen DSN census (ro_census.forms over test_r7_ro_role_pg.CENSUS_FILES),
taken once at the round-7 tip 3130bb9d (rehearsal-four round 8, child ro).
Never regenerated from later code: a new form is refused until a reviewed
edit freezes it here by hand."""

FROZEN = {'api/admin_evidence.py': [('import', 'from sqlalchemy import text'),
                           ('import', 'from sqlalchemy import text'),
                           ('import', 'from sqlalchemy import text'),
                           ('import', 'from sqlalchemy import text'),
                           ('import', 'from sqlalchemy import text'),
                           ('import', 'from sqlalchemy import text'),
                           ('import', 'from sqlalchemy import text'),
                           ('import', 'from sqlalchemy import text'),
                           ('import', 'from sqlalchemy.ext.asyncio import AsyncSession')],
 'api/auto_logs.py': [('dsntext',
                       'Opt-in automatic log upload after a match — SERVER HALF (v1.41.0, Item '
                       '3).\n'
                       '\n'
                       'WHAT THIS IS. One authenticated write route, ``POST /api/v1/logs/auto``, '
                       'that\n'
                       'takes the same log bundle the F5 bug form already sends and stores it as '
                       'an\n'
                       "ordinary ``bug_reports`` row carrying ``kind = 'auto'``. Everything "
                       'downstream\n'
                       "— the admin list, the detail view, the download endpoint's read-time scrub "
                       'and\n'
                       'the ops ``bug-log:N`` verb — reads ``bug_reports`` and therefore works on '
                       'these\n'
                       'rows with no change at all. That reuse is the whole point of storing them '
                       'here\n'
                       'rather than in a table of their own.\n'
                       '\n'
                       'THE CLIENT HALF IS BUILT AND INSTALLED, so this route receives live '
                       'traffic.\n'
                       'The Data & Privacy setting, the ``OnLeftRoom`` trigger and the client-side '
                       'path\n'
                       'scrub are all in the v1.41.0 client lane build ``46f54d4``, which is on '
                       "Sid's\n"
                       'desktop. The feature is OPT-IN and defaults OFF, so a seat reaches this '
                       'route\n'
                       'only once the setting has been switched on -- and one has, which is why '
                       'this\n'
                       'module is being deployed ahead of the rest of its lane.\n'
                       '\n'
                       '  An earlier version of this paragraph named ``323cd9c`` as that build. '
                       'That\n'
                       '  commit is an unrelated vanilla fix and carries none of this; the number '
                       'was\n'
                       '  wrong rather than the conclusion. A still earlier version said the '
                       'opposite\n'
                       '  outright -- that the client half belonged to another session and that '
                       'this\n'
                       '  module was INERT on arrival -- and every conclusion drawn from that '
                       'premise\n'
                       '  was wrong in the unsafe direction: retention that "nothing exercises '
                       'yet",\n'
                       '  refusals that "no client can hit yet", a corpus that "cannot grow yet". '
                       'It\n'
                       '  can and it does. Treat every bound below as load-bearing from the first '
                       'boot.\n'
                       '\n'
                       '  Shipping inert is a known way to ship nothing while every log line '
                       'looks\n'
                       '  perfect (#438, #443), and the same signal that would have proved '
                       'inertness\n'
                       '  proves reachability now. This route emits a POSITIVE signal rather than\n'
                       '  relying on the absence of errors: every accepted upload prints exactly '
                       'one\n'
                       '  ``[AUTO-LOG] #`` LANDING line, naming the bug number, the raw and '
                       'stored\n'
                       "  sizes and the write-time scrub's own counters, and returns those same\n"
                       '  counters in the response body. Not one line in total -- an accepted '
                       'upload\n'
                       '  whose opportunistic prune fires also prints a prune line, so the '
                       'invariant\n'
                       '  is one landing record per acceptance, not one prefixed line per request. '
                       '``[AUTO-LOG]`` exists for no other purpose in this repo, so\n'
                       '  grepping the api log for it answers "has a client ever reached this '
                       'route"\n'
                       '  with a yes or a no and nothing in between (#306). Two greps, because '
                       'the\n'
                       '  prefix is also on the refusal lines and that distinction is the useful '
                       'one:\n'
                       '  ``[AUTO-LOG] #`` is an upload that LANDED, and a bare ``[AUTO-LOG]`` is '
                       'the\n'
                       '  route being reached at all. Neither line appearing means the shipped '
                       'client\n'
                       '  is not reaching this box — a deployment question, not a design one.\n'
                       '\n'
                       'WHAT LEAVES THE MACHINE, AND WHAT IS REMOVED BEFORE IT IS STORED. The '
                       'bundle\n'
                       "is the client's own log text, and it arrives ALREADY SCRUBBED: the "
                       'shipped\n'
                       'client replaces profile paths and local account names before it uploads. '
                       'So\n'
                       '``os_user == 0`` in the counters below is the EXPECTED reading for a '
                       'healthy\n'
                       'bundle and infers nothing about the header shape — an earlier version of '
                       'this\n'
                       'paragraph said every bundle carries a raw ``C:\\Users\\<person>\\...`` '
                       'and\n'
                       'that a zero count meant the header had changed. It does not; a nonzero '
                       'count\n'
                       "means the server pass found something the client's pass did not, which is "
                       'the\n'
                       'interesting direction.\n'
                       '\n'
                       'The server scrubs again at WRITE time anyway, and that is deliberate: the\n'
                       "bug-report pipeline's own scrub runs at READ time only, which is enough "
                       'for\n'
                       'the HTTP download endpoint and NOT enough for the ops ``bug-log:`` verb, '
                       'which\n'
                       'plain-``zcat``s the stored blob. A client-side pass is a claim by the '
                       'client;\n'
                       "the blob on disk is the server's own artifact, so it goes through\n"
                       '``main._scrub_pass_one`` (OS usernames in Windows and POSIX path shapes, '
                       'plus\n'
                       'Discord snowflakes) before it is gzipped, whatever the client already did. '
                       'The\n'
                       'read-time scrub still runs on top and is unaffected — the passes are\n'
                       "idempotent, and the second one is what redacts deleted accounts' "
                       'SteamID64s,\n'
                       'which is a database question this path deliberately does not ask.\n'
                       '\n'
                       '  The scrub is IMPORTED from main, never re-implemented here. Two copies '
                       'of a\n'
                       '  privacy rule are two readings of one question, and they diverge (#432).\n'
                       '\n'
                       'FAILURE DIRECTION. An auto upload exists only to carry its log, so a row\n'
                       'without one is noise an admin has to triage. The blob is therefore '
                       'written\n'
                       'BEFORE the row is inserted, under an id this module generates -- but only\n'
                       'AFTER the cap has admitted the upload. Admission (the per-account '
                       'advisory\n'
                       'lock and the count that decides) comes first precisely so that a failure\n'
                       "there, where the handler holds nothing but this request's own bytes, "
                       'cannot\n'
                       'leave a file behind. Every DETERMINATE failure after it -- the directory, '
                       'the\n'
                       'volume lock, the free-space reading, the stamp, the write, the re-check '
                       'under\n'
                       'the lock, the INSERT, and any of their waits passing its ceiling -- ends '
                       'the\n'
                       'same way: its cleanup TRIES to remove what this request wrote, the '
                       "refusal's\n"
                       'line says whether it did, and the client is told 503 -- never 500 -- and '
                       'can\n'
                       'try again after the next match. The one refusal after admission that is '
                       'not\n'
                       'a 503 is the cap itself, re-read under the lock immediately before the\n'
                       'INSERT: that is a 429, with the same cleanup. A commit whose outcome is\n'
                       'unknown is also a 503 (see below), and an upload whose row has committed '
                       'is\n'
                       'accepted whatever happens to its marker afterwards.\n'
                       '\n'
                       '  SINCE ROUND 8 NO CLEANUP CAN CHANGE THAT ANSWER (R7-L1). A cleanup ends '
                       'in\n'
                       '  one of four ways -- the blob removed, its unlink refused, the directory\n'
                       '  flush between its two unlinks refused, or its wait past the ceiling '
                       'every\n'
                       '  wait here has (R7-M4) -- and ``_discard_for_refusal`` turns each into '
                       'the\n'
                       "  words of the refusal's line instead of raising past it. Round 7 let the\n"
                       "  flush's raise out of the INSERT arm ahead of its rollback and its 503.\n"
                       '\n'
                       '  AND AN UNLINK THAT RAISES IS NOT A DISCARD. ``_release_marked_blob`` '
                       'answers\n'
                       '  whether the blob is GONE, and the INSERT arm says so either way: a file '
                       'that\n'
                       '  survived its own cleanup KEEPS its marker and is named for the sweep '
                       'rather\n'
                       '  than recorded as discarded. A cleanup record that cannot be wrong about '
                       'the\n'
                       '  file it describes is what makes the paragraph above a claim and not an\n'
                       '  intention.\n'
                       '\n'
                       '  EVERY BLOB CARRIES A DURABLE MARKER FROM BEFORE ITS FIRST BYTE. A '
                       'sidecar\n'
                       '  file, ``<blob>.orphan-candidate``, is created and fsynced -- with its\n'
                       '  directory entry, on a platform that has one to flush separately -- '
                       'before\n'
                       '  ``open()`` is called on the blob, and it is dropped only when the row '
                       'is\n'
                       '  committed, or together with the blob when one of the arms above discards '
                       'it.\n'
                       '  So there is no instant, and no crash between any two lines of this '
                       'handler,\n'
                       '  at which an unreferenced blob exists with nothing naming it. A stamp '
                       'that\n'
                       '  cannot be made durable REFUSES the upload rather than writing the blob\n'
                       '  anyway.\n'
                       '\n'
                       '  AND SO DOES THE PLAYER-FILED ATTACHMENT, SINCE ROUND 6. '
                       '``submit_bug_report``\n'
                       '  stamps the same marker before its own ``open()`` and clears it after the '
                       'row\n'
                       '  that names the file has committed. That path has no sweep of its own and '
                       'its\n'
                       '  row is written in the same transaction as the report, so before round 6 '
                       'a\n'
                       '  stop between its first byte and its cleanup arm left a prefix nothing in '
                       'this\n'
                       '  tree could name. The marker set is therefore no longer "the automatic\n'
                       '  uploads in flight" but "the blobs in flight", and the sweep\'s '
                       'protection of a\n'
                       '  referenced file has to carry the difference: it does, because the lookup '
                       'that\n'
                       '  decides is ``log_filename`` over the WHOLE ``bug_reports`` table with no '
                       'kind\n'
                       '  predicate, which is the property ``prune_orphan_blobs`` documents at '
                       'length.\n'
                       '\n'
                       '  AND EVERY ORDER THIS MODULE RELIES ON IS A PERSISTENCE ORDER, NOT A '
                       'CALL\n'
                       '  ORDER. An ordering that survives the PROCESS does not survive the HOST: '
                       'a\n'
                       '  power loss recovers whatever was flushed and discards the rest, in no\n'
                       '  guaranteed order between two un-synced changes to one directory. SIX\n'
                       '  flushes at FOUR sites make every unlink-then-drop-the-reference order '
                       'in\n'
                       '  this module true of the disk; the two on the write path are charged to '
                       'the\n'
                       "  marked span's own deadline rather than paid outside it:\n"
                       '\n'
                       "    * ``_stamp_marker`` fsyncs the marker's CONTENTS and then its "
                       'directory\n'
                       '      ENTRY, BEFORE ``open()`` is called on the blob;\n'
                       "    * ``_write_blob`` fsyncs the blob's CONTENTS and then its directory\n"
                       '      ENTRY before it returns -- so the row that names it is inserted and\n'
                       '      committed only over bytes the filesystem has promised;\n'
                       '    * ``_delete_blob_then_marker`` fsyncs the directory between the '
                       "blob's\n"
                       "      unlink and the marker's, so a crash cannot persist the marker's\n"
                       "      removal while recovering the blob's entry;\n"
                       "    * ``_unlink_due_blobs`` fsyncs the blob directory after RETENTION's "
                       'last\n'
                       '      unlink and before the rows that name those blobs are DELETEd, so a\n'
                       '      crash cannot recover a blob whose only reference is durably gone.\n'
                       '\n'
                       '  THE REFERENCE IS NOT ALWAYS A MARKER, WHICH IS WHY THE FOURTH SITE '
                       'EXISTS.\n'
                       '  On the write path the thing that offers an unreferenced blob to a '
                       'collector\n'
                       '  is its marker; on the retention path the blob has no marker and its ROW '
                       'is\n'
                       '  the only name it has, so the reference being dropped is a database '
                       'commit\n'
                       '  rather than a second unlink. The order is the same order and it needs '
                       'the\n'
                       '  same barrier.\n'
                       '\n'
                       '  THE ONE CASE THAT CANNOT BE MADE ATOMIC is a ``commit()`` that raises. '
                       'That\n'
                       '  is indeterminate, not failed -- PostgreSQL may have committed and the\n'
                       '  acknowledgement been lost on the way back -- so the blob is '
                       'deliberately\n'
                       '  KEPT. Deleting it is irreversible and, when the row did commit, destroys '
                       'the\n'
                       '  only copy of the log that row promises, which presents to the next admin '
                       'as\n'
                       '  corruption rather than as a failed upload. An orphan blob only costs '
                       'disk.\n'
                       '  Cheap reversible error over expensive irreversible one (#276).\n'
                       '\n'
                       '  THAT ARM NOW NAMES WHAT IT KEPT AND SOMETHING COLLECTS IT. The line '
                       'carries\n'
                       '  ``orphan-candidate=<file>`` and the marker beside the blob is left in '
                       'place,\n'
                       '  so ``prune_orphan_blobs`` -- run by the retention loop, not by a request '
                       '--\n'
                       '  finds it. If the commit did land, a ``bug_reports`` row of ANY kind '
                       'names\n'
                       '  the file and the sweep CLEARS the marker, keeping the blob for ever; if '
                       'it\n'
                       '  did not, the blob and then its marker are removed once past the age '
                       'gate.\n'
                       '  Nobody has to remember it either way. An earlier version of this '
                       'paragraph\n'
                       '  said "nothing collects such a blob ... a deliberate trade": the trade '
                       'was\n'
                       '  real, and it left a slow leak on a volume shared with player-filed\n'
                       '  attachments, which this route may not spend.\n'
                       '\n'
                       "  THE SWEEP'S POPULATION IS THE MARKER SET, NEVER THE ATTACHMENT HEAP. An\n"
                       '  earlier version walked the directory and bounded what one pass examined. '
                       'That\n'
                       '  directory holds every player-filed attachment permanently and nothing '
                       'here\n'
                       '  deletes a referenced one, so the budget was spent on files the sweep is\n'
                       '  required to KEEP and an orphan behind enough of them was never offered '
                       'to the\n'
                       '  database at all. A marker is created by one of TWO writers --\n'
                       '  ``upload_auto_log`` and ``submit_bug_report`` -- and lives from before '
                       'its\n'
                       "  blob's first byte until just after the row naming the blob commits, or "
                       'longer\n'
                       '  when that clear fails, which it is allowed to; so a referenced file '
                       'carries\n'
                       '  one only in that window, and the sweep clears such a marker over the '
                       'row\n'
                       "  that names it. The heap's floor is therefore gone, but the marker set "
                       'is\n'
                       '  still a population, and since round 6 one pass examines at most\n'
                       '  ``_ORPHAN_SCAN_BOUND`` of its names -- a window that a cursor moves on '
                       'across\n'
                       '  passes, so the bound is on cost and never on reach -- and removes at '
                       'most\n'
                       '  ``_ORPHAN_BATCH`` blobs.\n'
                       '\n'
                       '  An earlier version of this paragraph also claimed atomicity across both\n'
                       '  halves unconditionally. It was false of the write arm, which raised '
                       'without\n'
                       '  unlinking, and it was not achievable across the commit at all.\n'
                       '\n'
                       'RETENTION REQUIRES A SWEEP THAT RUNS WHETHER OR NOT ANYBODY UPLOADS. '
                       'Nothing\n'
                       'deletes a bug_reports row by age by itself: no reader filters on '
                       'created_at\n'
                       'for retention, and the only collector is ``prune_auto_logs``. An earlier\n'
                       'version of this module reached it two ways only -- opportunistically after '
                       'an\n'
                       'ACCEPTED upload, and from the internal route -- so the corpus was bounded '
                       'only\n'
                       'while uploads kept arriving, and the last cohort of rows and blobs '
                       'persisted\n'
                       'indefinitely the moment they stopped. #276 is about failure DIRECTION: an\n'
                       'expiring design lapses because nothing renews it, a blocking one needs a\n'
                       'positive cleanup that ALWAYS runs. A sweep reachable only from the thing '
                       'it\n'
                       "collects is the second kind wearing the first kind's clothes.\n"
                       '\n'
                       '  So the sweep is now a scheduled background task, '
                       '``auto_log_retention_loop``\n'
                       "  below, started from main's ``lifespan`` on the PRIMARY alone (it "
                       'deletes\n'
                       '  rows, and a DELETE raises in recovery on the standby). It prints\n'
                       '  ``[AUTO-LOG] retention sweep armed ...`` once at boot and one\n'
                       '  ``[AUTO-LOG] retention sweep:`` line per pass. That boot line is the\n'
                       '  positive signal (#438/#443): its ABSENCE on the primary means retention '
                       'is\n'
                       '  not running, which is a different fact from "nothing was old enough to\n'
                       '  delete" and is exactly what the old opportunistic-only design could not\n'
                       '  distinguish. The opportunistic call and the internal route both stay --\n'
                       '  they cost nothing and they are how an operator forces a pass -- but '
                       'neither\n'
                       '  is load-bearing any more.\n'
                       '\n'
                       'ORDER WITHIN A SWEEP: THE FILE GOES FIRST, AND THE ROW IS THE RETRY\n'
                       'REFERENCE. ``prune_auto_logs`` selects the due rows, unlinks each blob, '
                       'and\n'
                       'COMMITS the row deletion only for the rows whose blob is actually gone. A '
                       'row\n'
                       'whose unlink fails is KEPT -- deleting it first would have thrown away the '
                       'only\n'
                       'pointer to the file and left an orphan nothing can name.\n'
                       '\n'
                       '  KEPT IS NOT THE SAME AS RE-READ, and this paragraph used to say the '
                       'next\n'
                       '  pass simply finds such a row again. A pass reads the OLDEST\n'
                       '  ``_PRUNE_BATCH`` due rows, so a cohort that keeps failing is re-read in '
                       'full\n'
                       '  on every pass -- and once it is large enough to fill the batch, nothing\n'
                       "  younger than it is reached at all. The row's id is therefore parked in\n"
                       '  ``_PRUNE_HELD`` and the next selections look PAST it, for\n'
                       '  ``_PRUNE_HOLD_S``, after which it is due again. The retry is real and it '
                       'is\n'
                       '  DEFERRED; what the next pass reads instead is the rows behind the '
                       'failure.\n'
                       '\n'
                       '  The window this opens is the reverse one -- a blob unlinked and then a\n'
                       '  commit that does not land leaves a row advertising a log that is gone, '
                       'the\n'
                       '  state backend/sql/087_clear_orphaned_bug_logs.sql had to clean up once. '
                       'It\n'
                       '  is transient rather than permanent here, and that is the difference: no '
                       'hold\n'
                       '  is taken on that row, because its unlink did not fail. It is still due, '
                       'the\n'
                       '  next pass re-selects it, the unlink finds the file already absent '
                       '(counted\n'
                       '  as success, not an error), and the row is collected. That failure '
                       'repairs\n'
                       '  itself on the following tick instead of needing a migration.\n'
                       '\n'
                       '  A pass is bounded by ``_PRUNE_BATCH`` rows so one sweep cannot hold a\n'
                       '  volume worker across an unbounded unlink loop; a backlog drains over\n'
                       '  consecutive ticks. No transaction is open across the unlink loop at all\n'
                       '  since round 9: the due rows are read in one transaction, ended before '
                       'the\n'
                       '  loop, and deleted in a second (R8-M1).\n'
                       '\n'
                       "NOT A REPLICA-ROUTABLE PATH. The blob is written to the api container's "
                       'own\n'
                       "disk. If this path were ever added to the edge's read-routing list, "
                       'uploads\n'
                       'would land on whichever box answered and ``bug-log:`` on the primary would '
                       'not\n'
                       "find them. It is a POST, so today's routing (heavy READS to the standby) "
                       'does\n'
                       'not touch it; this note is here so that stays deliberate.\n'),
                      ('import', 'from sqlalchemy import text'),
                      ('import', 'from sqlalchemy.ext.asyncio import AsyncSession')],
 'api/card_evidence.py': [('import', 'from sqlalchemy import text'),
                          ('import', 'import asyncpg.exceptions as pg_exc'),
                          ('import', 'import sqlalchemy.exc as sa_exc')],
 'api/combat_evidence.py': [('import', 'from sqlalchemy import text'),
                            ('opener', 'str case'),
                            ('opener', 'str case'),
                            ('opener', 'str case')],
 'api/combat_measures.py': [('opener', 'Load case'),
                            ('opener', 'Load case'),
                            ('opener', 'Store case'),
                            ('opener', 'str case'),
                            ('opener', 'str case'),
                            ('opener', 'str case'),
                            ('opener', 'str case'),
                            ('opener', 'str case'),
                            ('opener', 'str case'),
                            ('opener', 'str case')],
 'api/database.py': [('dsntext',
                      '\n'
                      'Database connection management for Competitive ROUNDS API.\n'
                      'Uses SQLAlchemy async with asyncpg for PostgreSQL.\n'),
                     ('dsntext',
                      'postgresql+asyncpg://comp_rounds:changeme@localhost:5432/competitive_rounds'),
                     ('env', 'DATABASE_URL'),
                     ('import', 'from sqlalchemy import event'),
                     ('import',
                      'from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker'),
                     ('import',
                      'from sqlalchemy.ext.asyncio import create_async_engine as '
                      '_sqlalchemy_create_async_engine'),
                     ('kwarg', 'create_async_engine connect_args=args'),
                     ('opener', 'Load _sqlalchemy_create_async_engine'),
                     ('opener', 'Load create_async_engine'),
                     ('opener', 'Load create_async_engine'),
                     ('opener', 'Load create_async_engine'),
                     ('opener', 'Load make_asm_engine'),
                     ('opener', 'alias _sqlalchemy_create_async_engine'),
                     ('opener', 'def create_async_engine'),
                     ('opener', 'def make_asm_engine')],
 'api/flag_evidence.py': [('import', 'from sqlalchemy import text')],
 'api/glicko2.py': [('dsntext',
                     '\n'
                     'Glicko-2 Rating System Implementation\n'
                     "Based on Mark Glickman's paper: http://www.glicko.net/glicko/glicko2.pdf\n"
                     '\n'
                     'This module handles all rating calculations for Competitive ROUNDS.\n')],
 'api/identity_clock_evidence.py': [('import', 'from sqlalchemy import text')],
 'api/mail_discord.py': [('import', 'from sqlalchemy import text'),
                         ('import', 'from sqlalchemy.exc import IntegrityError'),
                         ('import', 'from sqlalchemy.ext.asyncio import AsyncSession')],
 'api/main.py': [('dsntext',
                  '\n'
                  '                    UPDATE ffa_lobbies l\n'
                  '                       SET departed_ids = (SELECT ARRAY(SELECT DISTINCT e\n'
                  '                                             FROM unnest(l.departed_ids || '
                  'p.id) e)),\n'
                  '                           departure_causes = CASE WHEN CAST(:cause AS text) = '
                  "''\n"
                  '                                                   THEN l.departure_causes\n'
                  '                                                   ELSE '
                  'jsonb_build_object(p.id::text,\n'
                  '                                                                           '
                  'CAST(:cause AS text))\n'
                  '                                                        || l.departure_causes '
                  'END\n'
                  '                      FROM players p\n'
                  '                     WHERE p.steam_id = :sid\n'
                  '                       AND l.id = CAST(:lid AS uuid)\n'
                  "                       AND l.status = 'active'\n"
                  '                       AND p.id = ANY(l.member_ids)\n'
                  '                       -- Bug #392 lens find 2: TWO ways in, not one. The\n'
                  '                       -- original predicate admitted only a departure that\n'
                  '                       -- was not yet marked, which made the cause reachable\n'
                  '                       -- ONLY on the request that first appended the player.\n'
                  "                       -- The client's durable-cause machinery exists to\n"
                  '                       -- re-send the attestation on a LATER request, after a\n'
                  "                       -- teardown's own untagged leave has already taken the\n"
                  '                       -- row path, appended the player and deleted the queue\n'
                  '                       -- row: by the time the tagged retry arrives there is\n'
                  '                       -- no row (so `me` is None, we are here) and the player\n'
                  '                       -- is already departed (so the old predicate was false\n'
                  '                       -- and zero rows were updated). Every attestation that\n'
                  '                       -- survived a teardown was dropped in silence.\n'
                  '                       --\n'
                  '                       -- "First attestation wins" still holds, and now means\n'
                  '                       -- what it says: the slot is the CAUSE key, not\n'
                  '                       -- membership of departed_ids. A tagged retry may fill\n'
                  '                       -- an empty slot; it can never overwrite a filled one.\n'
                  '                       -- An untagged retry ON AN ALREADY-MARKED departure\n'
                  '                       -- still matches nothing and stays the no-op it was;\n'
                  '                       -- an untagged FIRST leave is unaffected and marks the\n'
                  '                       -- departure through the original clause, as before.\n'
                  '                       AND (NOT (l.departed_ids @> ARRAY[p.id])\n'
                  "                            OR (CAST(:cause AS text) <> ''\n"
                  '                                AND NOT jsonb_exists(l.departure_causes,\n'
                  '                                                     p.id::text)))\n'
                  '                     RETURNING l.id\n'
                  '                '),
                 ('dsntext',
                  '\n'
                  '            UPDATE team_series\n'
                  '               SET spawn_confirmations = spawn_confirmations + 1,\n'
                  '                   spawn_confirmed_by = spawn_confirmed_by || '
                  'to_jsonb(CAST(:pid AS text))\n'
                  '             WHERE id = :sid\n'
                  "               AND status = 'active'\n"
                  '               AND NOT (spawn_confirmed_by @> to_jsonb(CAST(:pid AS text)))\n'
                  '            RETURNING spawn_confirmations\n'
                  '        '),
                 ('dsntext',
                  '\n'
                  '        -- r.card_rarity must stay in the GROUP BY: Postgres cannot infer the\n'
                  '        -- functional dependency through a CTE. Since `rarity` is\n'
                  '        -- DISTINCT ON (card_name) it adds no extra groups (same for the two\n'
                  '        -- Aug 31 aggregates — both are GROUP BY card_name CTEs).\n'
                  '        GROUP BY mc.card_name, r.card_rarity, o.times_offered, o.pass_rate,\n'
                  '                 sw.sweeps_with_card, st.stacked_builds\n'
                  '        HAVING COUNT(*) >= :min_picks\n'
                  '        ORDER BY '),
                 ('dsntext',
                  '\n'
                  '        SELECT id, solo_id FROM ovt_matches\n'
                  '         WHERE photon_room_id = :room\n'
                  '           AND ARRAY[solo_id, duo_a_id, duo_b_id] @> CAST(:trio AS uuid[])\n'
                  '           AND ARRAY[solo_id, duo_a_id, duo_b_id] <@ CAST(:trio AS uuid[])\n'
                  '         LIMIT 1\n'
                  '    '),
                 ('dsntext',
                  '\n'
                  '    Poll queue status. Handles searching, matching, mutual ready-up, and '
                  'timeouts.\n'
                  '    Uses SELECT FOR UPDATE SKIP LOCKED for race-safe matching.\n'
                  '    Elo range: ±100 / ±200@30s / ±400@60s / ±800@120s.\n'
                  "    Ready timeout: READY_TIMEOUT_SECONDS (90 s) — if both players don't ready\n"
                  '    up, the match is canceled.\n'
                  '\n'
                  "    v1.40.1: requires the caller's OWN valid Steam session (fail-closed —\n"
                  '    _strict_steam_session_ok, the same gate the link-code and artist\n'
                  '    endpoints use; _check_steam_session is a compatibility gate keyed on the\n'
                  '    client-supplied X-Mod-Version and is not a boundary). The poll answers '
                  'with\n'
                  "    this seat's own pairing and, at ready-up, the issued room name and region,\n"
                  '    so it is served only to the seat that owns the row. The 401 detail literal\n'
                  '    is LOAD-BEARING: ApiClient.HandleSessionReject matches "session_required"\n'
                  '    to re-mint; the client leaves the queue once its polls have been refused\n'
                  '    for 30 s straight (at least three, spanning a session re-mint cycle;\n'
                  '    refusals of a superseded credential do not count). Every live client\n'
                  '    (>= 1.40.0) stamps its token on every request WHILE IT HOLDS ONE — a seat\n'
                  '    before its first mint, or whose session was refused, is refused here until\n'
                  '    the heartbeat re-mints (impl note 65). Presence is touched only AFTER the\n'
                  '    gate — an unaccepted request must not count as an online seat.\n'
                  '    '),
                 ('dsntext', ' frames @ '),
                 ('dsntext', ' frames @ '),
                 ('dsntext', ' frames @ '),
                 ('dsntext', ' must be text PostgreSQL can store (no NUL character)'),
                 ('dsntext',
                  '(?i)\\b(?:https?://|www\\.|discord(?:app)?\\.(?:gg|com/invite)/)\\S+'),
                 ('dsntext',
                  "(class, keyword) of one harvested statement: 'explain', 'session' or\n"
                  "    'unclassified' (the table above), and its first keyword upper-cased, or\n"
                  "    '' when it has none. The keyword is read after leading whitespace, `--`\n"
                  '    line comments and `/* */` block comments, which nest as they do in\n'
                  '    PostgreSQL; an unterminated block comment leaves no keyword.'),
                 ('dsntext', '013457@$!'),
                 ('dsntext', '@-mentions are not allowed in translations'),
                 ('dsntext', '@\\w'),
                 ('dsntext', '@everyone'),
                 ('dsntext', '@everyone'),
                 ('dsntext', '@everyone'),
                 ('dsntext', '@everyone'),
                 ('dsntext', '@here'),
                 ('dsntext', '@here'),
                 ('dsntext', '@here'),
                 ('dsntext', '@here'),
                 ('dsntext',
                  "A moderation route's caller-sent FREE TEXT, before anything binds it.\n"
                  '\n'
                  '    The sibling of _mod_bindable_or_422, one field over (residual R8). A '
                  'reason\n'
                  '    is not a key, so no statement is keyed on it and no row could be found by\n'
                  '    it -- but the mute INSERT still binds it as text, and PostgreSQL text\n'
                  '    cannot hold a NUL character. Before this guard that INSERT failed, the\n'
                  "    route answered 500 and the mute rolled back, so a moderator's action was\n"
                  '    lost to a character they cannot type. The audit row is not what failed:\n'
                  '    it runs under a SAVEPOINT and only logs (#235/#187), which is exactly why\n'
                  '    the 500 came from the mute and not from the log.\n'
                  '\n'
                  '    REFUSED, not stripped. Storing something other than what was sent would\n'
                  '    leave the stored reason and the audit row describing different text, and a\n'
                  '    422 naming the field is a correction the caller can act on; a silent strip\n'
                  "    is not. The cost of this refusal is one retyped reason, against today's\n"
                  '    cost of a lost mute (#430).\n'
                  '\n'
                  '    Placed in the two WRITE cores rather than at each route, so every caller\n'
                  '    inherits it -- the in-game mute, the mute-by-message flow, the Discord\n'
                  '    context menu and the mail moderation act path -- and a future caller\n'
                  '    cannot forget it. None and "" are accepted: the column is nullable and\n'
                  '    both mean "no reason given".'),
                 ('dsntext',
                  "A restriction's target (review r13; the rationale corrected by v4.13):\n"
                  '    refused 422 unless _mod_target_ok. Exact form, no stripping: the\n'
                  '    signature covers the string as sent.\n'
                  '\n'
                  '    admin_ban calls it as its first statement, before the signature check,\n'
                  '    any read, the identity locks and the ban-rate gate, for two reasons. The\n'
                  '    target is the key the ban row is written with, and no ban may carry a key\n'
                  '    outside the domain (once migration 319 is applied the table refuses one\n'
                  "    on an active row). And the gate's refusal writes a best-effort audit row\n"
                  '    naming this target, then counts those rows to alert once per window\n'
                  '    (#656): the audit column is TEXT (028), so no LENGTH fails that insert,\n'
                  '    but a string PostgreSQL text cannot hold (a NUL character, for one) would\n'
                  '    fail it silently and every refusal would alert again -- the domain keeps\n'
                  '    every such string away from the gate.'),
                 ('dsntext',
                  'How many times a DC report may be re-run after PostgreSQL picks it as a\n'
                  'deadlock victim (SQLSTATE 40P01). Two, not more: a second abort means the\n'
                  'counterparty is still holding, and waiting inside the request is worse for the\n'
                  'caller than answering something its outbox will bring back.'),
                 ('dsntext',
                  'Names go into a Discord embed body — neutralize markdown metacharacters\n'
                  '    (embeds never ping, and the bot sends AllowedMentions.none(), so mention\n'
                  '    tokens are cosmetic-only here). Brackets/parens/angles included (review\n'
                  '    F10): AllowedMentions suppresses pings, NOT hyperlinks, and a name like\n'
                  '    "[watch](https://evil)" would otherwise render a clickable link in an\n'
                  '    official embed. Round-2 finding 5: whitespace/control chars collapse to\n'
                  '    single spaces (a newline in a name forges whole embed LINES) and bare\n'
                  "    URLs get a zero-width space after the scheme so Discord's auto-linker\n"
                  '    never fires on caller-authored text.'),
                 ('dsntext',
                  'On a read replica, refuse anything that is not a read.\n'
                  '\n'
                  '    DEFENCE IN DEPTH, not the primary control. The edge already gates by\n'
                  '    method: `map $request_method $scr_read_target` sends only GET and HEAD to\n'
                  '    the standby and everything else to the primary, verified empirically with\n'
                  '    the debug-upstream header. In normal operation this never fires.\n'
                  '\n'
                  '    It exists because that allowlist is config on another box, and nginx\n'
                  '    `location` matching is itself method-BLIND -- only the map makes it\n'
                  '    method-aware. An edit that dropped the map, or a request that reached this\n'
                  '    node without passing the edge, would put writes on a database in recovery.\n'
                  '    The honest answer then is a clean refusal naming the reason, rather than a\n'
                  '    500 surfacing from postgres several layers down, or a half-applied write.\n'
                  '\n'
                  '    Registered after every other gate but one, so it refuses before them. The\n'
                  '    one layer outside it is `evidence_key_gate` (admin_evidence.py), '
                  'registered\n'
                  '    right after this function: for the evidence report paths only it requires\n'
                  '    the internal key before anything else runs, in every server state, and\n'
                  '    passes every other path untouched. Inert on the primary: one boolean per\n'
                  '    request.\n'
                  '\n'
                  '    WHAT IT DOES NOT COVER, stated because a gate is easy to over-read:\n'
                  "      * WRITE-ON-GET. This codebase's dominant write shape is a GET that "
                  'writes\n'
                  '        through a shared helper, and no method test can see those. They are\n'
                  '        handled individually at their choke points (grep IS_REPLICA), and the\n'
                  "        real control for them is the edge's read allowlist, which is a regex "
                  'of\n'
                  '        analytics reads and routes nothing else here.\n'
                  "      * WEBSOCKETS. Starlette's http middleware never runs for a websocket\n"
                  '        scope, so the chat socket bypasses this entirely. It is not in the '
                  'edge\n'
                  '        allowlist either, so it cannot arrive here through the documented '
                  'path.\n'
                  '    This gate is a backstop for the one case a method test CAN catch: a\n'
                  '    non-GET arriving at a read replica.\n'
                  '    '),
                 ('dsntext',
                  'One pass of the deferred-fallback sweep. Returns the number settled.\n'
                  '\n'
                  '    Split out of the loop below so the acceptance harness can drive a pass\n'
                  '    against a real database at a chosen moment, which is the only way to test\n'
                  '    the orderings this sweep exists to make safe -- lock waits and\n'
                  '    clock_timestamp are PostgreSQL behaviours and a fake session cannot\n'
                  '    exhibit them.\n'
                  '    '),
                 ('dsntext',
                  "Opt-IN toggle (July 22, migration 144): show 'Discord: @displayname' on\n"
                  "    this player's leaderboard detail panel. Default OFF. Free setting — no\n"
                  "    ownership gate. HMAC signs 'show_discord:{steam_id}:{1|0}'."),
                 ('dsntext',
                  'Refund every UNSETTLED bet on a series. Stake was charged via gold_spent\n'
                  '    at place-time; back it out and add a gold_transactions entry per bet.\n'
                  '    Idempotent — already-settled bets (won/lost/refunded) are untouched.\n'
                  '\n'
                  '    Lifecycle r1 find 3: idempotence used to be SEQUENTIAL only — the old\n'
                  '    read-then-mark shape let two concurrent refunders (no-show sweep vs\n'
                  '    admin reversal vs the stale-series janitor) both read a bet as\n'
                  '    unsettled and both hand the stake back, minting gold. The claim is now\n'
                  '    ONE conditional UPDATE ... RETURNING: under READ COMMITTED the second\n'
                  '    claimant blocks on the bet row, re-evaluates settled_at on the\n'
                  '    committed version, matches zero rows, and pays nothing. Only claimed\n'
                  '    rows are paid, in the same transaction as the claim. No new lock-order\n'
                  "    edge: the only rows locked are this series' bet rows plus each claimed\n"
                  "    bettor's player row (below).\n"
                  '\n'
                  '    Lifecycle r1 find 10: bettor player rows are paid in sorted player_id\n'
                  '    order so two concurrent REFUNDS over overlapping bettor sets cannot\n'
                  '    ABBA each other. Cross-path cycles against writers with different\n'
                  '    deliberate orders (prize grants are podium-ordered by design, rounds\n'
                  '    26-27) remain possible and resolve as ordinary Postgres deadlock\n'
                  '    aborts — the losing sweep retries next tick, a losing admin request\n'
                  '    surfaces its error; money moves at most once either way because the\n'
                  '    claim above already settled the rows.'),
                 ('dsntext',
                  'Return players who joined the queue within the last N seconds. v1.34.1:\n'
                  "    also carries the searcher's Discord display name (opt-out honored) so the\n"
                  '    Search-Ranked beacon can name who to @ — plain text, never a real ping.'),
                 ('dsntext',
                  'SELECT id, series_id FROM ovt_matches WHERE photon_room_id = :room AND '
                  'ARRAY[solo_id, duo_a_id, duo_b_id] @> CAST(:trio AS uuid[]) AND ARRAY[solo_id, '
                  'duo_a_id, duo_b_id] <@ CAST(:trio AS uuid[]) LIMIT 1'),
                 ('dsntext',
                  'Take FOR UPDATE locks on the given queue rows in a deterministic GLOBAL\n'
                  '    order (ascending player_id), one statement per row.\n'
                  '\n'
                  "    `before_each`, when given, is awaited before each row's statement: a "
                  'caller\n'
                  '    under one deadline re-arms its lock_timeout and statement_timeout there\n'
                  '    from what is left of that deadline, so the row waits together spend one\n'
                  '    budget (merge pass 6, R2-C-L1; _asm_reform_formation). The order and the\n'
                  '    statements are the same with or without it.\n'
                  '\n'
                  "    Why this exists: queue_poll and queue_ready both used to lock the CALLER's\n"
                  "    row first and then the opponent's. Two players polling at the same instant\n"
                  '    therefore grabbed the same two rows in opposite orders — textbook ABBA.\n'
                  '    Postgres logged it twice on 2026-07-26 07:02 ("deadlock detected ... while\n'
                  '    locking tuple in relation ranked_queue"), and the loser\'s request 500s; '
                  'the\n'
                  '    client silently retries its poll 3s later, so it reads as a stutter in\n'
                  '    matchmaking rather than an error anyone reports.\n'
                  '\n'
                  '    Why one statement per row instead of a single\n'
                  '    `WHERE player_id = ANY(...) ORDER BY player_id FOR UPDATE`: that form '
                  'relies\n'
                  '    on the planner putting LockRows above the Sort so rows lock in sorted '
                  'order.\n'
                  '    It normally does, but it is a plan-shape assumption, and this is the one\n'
                  '    place where being wrong reintroduces exactly the bug we are fixing. '
                  'Separate\n'
                  '    ordered statements are unambiguous and each is a single indexed lookup.\n'
                  '\n'
                  '    CRITICAL: the caller must NOT already hold a lock on any of these rows.\n'
                  '    Discover the peer ids with an UNLOCKED read, call this, then re-read the\n'
                  '    authoritative state under the locks — a lock acquired before this runs '
                  'puts\n'
                  '    us right back into an inconsistent order.\n'
                  '\n'
                  '    Missing rows are simply not locked; callers revalidate after the re-read.\n'
                  '    '),
                 ('dsntext',
                  "Take the pair's current-series row lock at the top of a match report.\n"
                  '\n'
                  '    Lock-only: the authoritative load happens later in the report, and holding\n'
                  '    the row means it cannot change underneath that load. Taking it here, the\n'
                  '    moment both players are known, is what stops a concurrent /bets from\n'
                  '    taking the series lock first, reading the persisted pre-report score and\n'
                  '    accepting a wager on a game that has already been decided.\n'
                  '\n'
                  '    A fault FAILS THE REQUEST with a retryable 503. It used to be swallowed\n'
                  '    for ordinary (non-tournament) series, and the swallow is what made the\n'
                  '    wager window reachable by ordinary means: a lock wait that times out is\n'
                  '    the normal way this statement fails, the report then continued unlocked\n'
                  '    through every line the lock exists to cover, and the wager it admitted\n'
                  '    settled against the result the same request was recording. Re-raising as\n'
                  '    503 costs a redelivery — nothing in the handler has committed at this\n'
                  '    point — and that is the only outcome that keeps the window shut.\n'
                  '\n'
                  '    Tournament series already refused, on the separate ground that skipping\n'
                  '    the cross-path action gate reopens the report-vs-action state race. They\n'
                  '    refused by re-raising the original error, which surfaced as a 500; they\n'
                  '    now take the same 503 as every other series, so the distinction no longer\n'
                  '    has to be carried as a special case. Both are 5xx and both are redelivered\n'
                  "    by the report outbox, so nothing about the tournament path's outcome\n"
                  '    changes beyond the status code.\n'
                  '\n'
                  '    SAVEPOINT (#235): under asyncpg a failed statement leaves the TRANSACTION\n'
                  '    aborted, so without the savepoint the 503 below could not be raised\n'
                  "    cleanly — the caller's later statements would die first and the report\n"
                  '    would surface as whatever ran next. On SUCCESS the savepoint is RELEASED,\n'
                  '    and Postgres retains work released that way, so the FOR NO KEY UPDATE row\n'
                  '    lock is still held for the rest of the request, which is the entire point\n'
                  '    of taking it early.'),
                 ('dsntext',
                  'Take the portrait-blob locks P for this player, BEFORE the row lock R.\n'
                  '    Returns (game_hash, steam_hash) as the row currently holds them (None for\n'
                  '    an empty slot); both units share the lock discipline (Steam pictures v2 '
                  '§6).\n'
                  '\n'
                  "    The order is V → I → C → P → R, and P's key is a value that lives IN the\n"
                  '    row — which is why the row was being read first, with FOR NO KEY UPDATE,\n'
                  '    and P taken after. That is R → P, and it is a cycle as soon as two players\n'
                  '    share a portrait: one deletion holds R(A) and waits for P(H) while the\n'
                  "    other holds P(H) and waits for R(A) to refund A's lobby bet. PostgreSQL\n"
                  '    breaks the cycle by aborting one of them — in a transaction that is moving\n'
                  '    gold.\n'
                  '\n'
                  '    So the key is read WITHOUT a lock, P is taken on what that read saw, and\n'
                  '    the caller takes R afterwards and confirms the value did not move. Under\n'
                  '    the identity lock every caller of this already holds, no other writer for\n'
                  '    this player can move it, so the confirmation is a guard against a caller\n'
                  '    that forgot the identity lock rather than against a race.'),
                 ('dsntext',
                  'The PostgreSQL SQLSTATE behind `ex`, however the driver and\n'
                  '    SQLAlchemy wrapped it; None when there is none.'),
                 ('dsntext',
                  "The bot's /binder [@member]: one page of the owner's live prints, ten\n"
                  '    at a time in the binder order, each with its tile decision, and the\n'
                  '    collection-wide count, rarity totals and page count from the SAME\n'
                  "    statement. Consent as /internal/pc/collection: someone else's binder only\n"
                  '    while it is public (403 private), the shard balance to its owner only.\n'
                  "    `owner_ref` and `settings_rev` identify the answer for the bot's pre-send\n"
                  '    re-read.'),
                 ('dsntext',
                  "The bot's /card @user: the subject's card as the pool sees it now\n"
                  '    (latest snapshot: pool rank, band, rating, record, title) and how many\n'
                  '    prints of them are in circulation. A subject who is not in the pool\n'
                  '    answers 404 not_in_pool.'),
                 ('dsntext',
                  "The bot's /collection [@user]: the owner's binder summary (counts by\n"
                  "    rarity, the ten best prints with their face keys in the interaction's\n"
                  "    locale). Someone else's binder only while it is public (403 private);\n"
                  '    the owner always sees their own.'),
                 ('dsntext',
                  'The mode currently holding this player, or None. Expiry is evaluated\n'
                  '    HERE, at read time — Postgres cannot enforce it with a CHECK or a partial\n'
                  '    index (both require immutable expressions) and no trigger fires because\n'
                  '    time passed. Every admission decision must route through this helper; a\n'
                  '    new code path that tests queue-row existence instead reintroduces the\n'
                  '    unbounded-strand bug that migration 174 removes.'),
                 ('dsntext',
                  'The rating the leaderboard resolves titles and rank names against —\n'
                  '    ROUND(rating::numeric, 0), half away from zero as PostgreSQL rounds\n'
                  '    (c3 F); None stays None.'),
                 ('dsntext',
                  'True when a text bind can carry value to PostgreSQL: a str with no NUL\n'
                  '    character (PostgreSQL text cannot hold one) that has a UTF-8 encoding\n'
                  '    (asyncpg sends a str bind as UTF-8, and a lone surrogate has none). The\n'
                  '    database is UTF8, which holds every other str.'),
                 ('dsntext', '\\b[a-z][a-z0-9+.-]*://'),
                 ('dsntext', '^https://www\\.twitch\\.tv/videos/\\d{1,20}$'),
                 ('dsntext', '^https://www\\.youtube\\.com/watch\\?v=[A-Za-z0-9_-]{5,20}$'),
                 ('dsntext',
                  'https://api.steampowered.com/ISteamUserAuth/AuthenticateUserTicket/v1/?key='),
                 ('dsntext', 'https://twitch.tv/sidscompetitiverounds'),
                 ('dsntext', 'https://www.twitch.tv/sidscompetitiverounds/videos?filter=archives'),
                 ('dsntext', 'https://youtube.com/@SidsCompetitiveRounds/live'),
                 ('dsntext', 'https://youtube.com/@SidsCompetitiveRounds/streams'),
                 ('import', 'from sqlalchemy import and_, case, func, or_, select, text'),
                 ('import', 'from sqlalchemy import bindparam'),
                 ('import', 'from sqlalchemy import event as _sa_event'),
                 ('import', 'from sqlalchemy import exc as _sa_exc'),
                 ('import', 'from sqlalchemy.dialects.postgresql import UUID as PG_UUID'),
                 ('import', 'from sqlalchemy.dialects.postgresql import insert as pg_insert'),
                 ('import', 'from sqlalchemy.exc import DBAPIError, IntegrityError'),
                 ('import',
                  'from sqlalchemy.exc import PendingRollbackError as _triage_pending_rollback'),
                 ('import', 'from sqlalchemy.ext.asyncio import AsyncSession'),
                 ('import', 'from sqlalchemy.ext.asyncio import async_sessionmaker'),
                 ('import',
                  'from sqlalchemy.orm import configure_mappers as _triage_configure_mappers'),
                 ('import', 'import asyncpg.exceptions as _discord_fix_apg_exc'),
                 ('import', 'import asyncpg.exceptions as _ffa_fc_apg_exc'),
                 ('import', 'import asyncpg.exceptions as _team_dc_apg_exc'),
                 ('import', 'import asyncpg.exceptions as _triage_apg_exc'),
                 ('kwarg', "HealthResponse database='connected'"),
                 ('kwarg', "HealthResponse database='disconnected'"),
                 ('kwarg', "_apply_mute_for_row role='discord_mod'"),
                 ('kwarg', '_apply_mute_for_row role=role'),
                 ('opener', 'Load case'),
                 ('opener', 'Load case'),
                 ('opener', 'Load case'),
                 ('opener', 'Load case'),
                 ('opener', 'Load case'),
                 ('opener', 'Load case'),
                 ('opener', 'Load case'),
                 ('opener', 'Load case'),
                 ('opener', 'Load case'),
                 ('opener', 'Load case'),
                 ('opener', 'Load chat_manager.connect'),
                 ('opener', 'Store case'),
                 ('opener', 'alias case'),
                 ('opener', 'def connect'),
                 ('opener', 'str connect'),
                 ('opener', 'str connect'),
                 ('opener', 'str connect')],
 'api/match_hold.py': [('dsntext',
                        "Find an asyncpg/PostgreSQL SQLSTATE through SQLAlchemy's wrappers."),
                       ('dsntext',
                        'Force checkout, then arm both transaction-local PostgreSQL bounds.'),
                       ('dsntext',
                        'SELECT 1 FROM match_seat_presence WHERE room_name = CAST(:room AS '
                        'varchar)   AND beat_at > CAST(:now AS timestamptz) - make_interval(secs '
                        "=> CAST(:f AS integer))   AND (jsonb_path_exists(seen, '$[*] ? (@.u_id == "
                        "$u && @.actor != $x)',                          CAST(:vars AS "
                        'jsonb))        OR (player_id = CAST(:pid AS uuid) AND actor IS NOT '
                        'NULL            AND actor <> CAST(:x AS integer))) LIMIT 1'),
                       ('dsntext',
                        'SELECT 1 FROM match_seat_presence WHERE room_name = CAST(:room AS '
                        'varchar) AND player_id <> CAST(:pid AS uuid)   AND beat_at > CAST(:now AS '
                        'timestamptz) - make_interval(secs => CAST(:f AS integer))   AND seen @> '
                        'CAST(:probe AS jsonb) LIMIT 1'),
                       ('import', 'from sqlalchemy import text'),
                       ('import', 'from sqlalchemy.ext.asyncio import AsyncSession')],
 'api/match_report_window.py': [('dsntext',
                                 'PostgreSQL infinity is datetime.max, without a timezone in '
                                 'asyncpg.'),
                                ('import', 'from sqlalchemy import text')],
 'api/models.py': [('import',
                    'from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Date, '
                    'DateTime, Double, FetchedValue, Float, ForeignKey, Index, Integer, '
                    'SmallInteger, String, Text, UniqueConstraint, text'),
                   ('import', 'from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID'),
                   ('import',
                    'from sqlalchemy.orm import DeclarativeBase, deferred, relationship')],
 'api/pc_face.py': [('opener', 'Load case'),
                    ('opener', 'Load case'),
                    ('opener', 'Store case'),
                    ('opener', 'str case'),
                    ('opener', 'str case')],
 'api/pc_motion.py': [('dsntext', 'card=%d@%s'), ('dsntext', 'tile=%d@%s')],
 'api/pc_signature.py': [('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Store case'),
                         ('opener', 'str case'),
                         ('opener', 'str case')],
 'api/pc_steam.py': [('dsntext',
                      '^https://avatars\\.(?:akamai\\.)?steamstatic\\.com/([0-9a-f]{40})_full\\.jpg$'),
                     ('dsntext', 'https://'),
                     ('dsntext', 'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/'),
                     ('dsntext', 'https://steamcommunity.com/profiles/')],
 'api/read_gate.py': [('import', 'from sqlalchemy import text')],
 'api/review_measures.py': [('opener', 'Load case'),
                            ('opener', 'Load case'),
                            ('opener', 'Load case'),
                            ('opener', 'Store case')],
 'api/review_rules.py': [('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Load case'),
                         ('opener', 'Store case'),
                         ('opener', 'Store case'),
                         ('opener', 'Store case')],
 'api/seat_evidence.py': [('import', 'from sqlalchemy import text')],
 'api/steamid64.py': [('dsntext',
                       'The same rule as a PostgreSQL boolean expression over one column\n'
                       '    reference. The CASE is load-bearing: PostgreSQL does not promise to\n'
                       "    evaluate AND's operands in order, and the cast raises on text that is "
                       'not\n'
                       '    an integer, so the cast sits in the THEN branch and runs only for a '
                       'value\n'
                       '    of seventeen ASCII digits, which always fits bigint. The comparison '
                       'is\n'
                       '    numeric, so no collation is involved. `column` is spliced into the '
                       'SQL\n'
                       '    text as it is, so it must be a plain lower-case column reference\n'
                       '    (`name` or `alias.name`); anything else raises ValueError rather than\n'
                       '    reaching the statement. What PostgreSQL makes of this text is not\n'
                       '    something a Python test can see: backend/tests/steamid64_pg_parity.py\n'
                       '    builds a query from it over the shared vectors, the answer PostgreSQL '
                       'gave\n'
                       '    is committed in backend/tests/fixtures/steamid64_pg_answer.txt under '
                       'the\n'
                       '    sha256 of that query, and test_steamid64.py fails when this text, the\n'
                       '    vectors or the validator no longer match that answer.')],
 'api/title_ladders.py': [('import', 'from sqlalchemy import select, text'),
                          ('import', 'from sqlalchemy.ext.asyncio import AsyncSession')],
 'api/tournaments.py': [('dsntext',
                         "'<@id> <@id> ...' for every confirmed signup. discord_id is gated at\n"
                         "    signup time so it's effectively always present; missing ones are "
                         'skipped.'),
                        ('dsntext', '<@'),
                        ('import', 'from sqlalchemy import and_, func, or_, select, text, delete'),
                        ('import',
                         'from sqlalchemy.dialects.postgresql import insert as pg_insert'),
                        ('import', 'from sqlalchemy.ext.asyncio import AsyncSession')],
 'tests/cf_pg.py': [('dsntext',
                     'Live PostgreSQL for the connect-failure lane (DESIGN V11): one case schema\n'
                     'per case, built as the ladder suite builds its own.\n'
                     '\n'
                     'The build (test_title_ladder_hooks_live._build, reused step for step): the\n'
                     'DDL of every numbered migration is replayed, the ORM makes the tables no\n'
                     'migration makes, the mapped tables are widened, and the DDL is replayed '
                     'again;\n'
                     'then the held-out migrations run whole, in this order: 331, then\n'
                     "365_title_ladders_five_tiers.sql (it rewrites 331's tables, so a replay\n"
                     'cannot run it before 331 exists; the ladder suite runs it the same way),\n'
                     "then 355, then 378_ffa_readmission.sql (it alters 355's tables). Two\n"
                     'differences, both on purpose:\n'
                     '\n'
                     '  - 355_ffa_assembly.sql is held out of both replays and run WHOLE last,\n'
                     '    inside its own BEGIN/COMMIT, so every case runs the migration this lane\n'
                     '    ships as its FIRST apply. A case that builds with with_355=False '
                     'applies\n'
                     "    it itself (the migration's own dry run and re-run).\n"
                     "  - the case schema is sealed only after the case's own DDL, so the census\n"
                     '    proves that nothing the build or the case ran reached outside it.\n'
                     '\n'
                     'CF_TEST_PG_DSN names the lane database (postgresql+asyncpg://...);\n'
                     'CF_TEST_PG_OPTOUT=1 waives the live cases deliberately. Unset and not\n'
                     'waived, every live case FAILS, because a skipped live case reports exit 0\n'
                     'for coverage that did not run.\n'),
                    ('dsntext', 'postgresql+asyncpg://'),
                    ('dsntext', 'postgresql://'),
                    ('env', 'DSN_VAR'),
                    ('import', 'from sqlalchemy.ext.asyncio import async_sessionmaker'),
                    ('import', 'import asyncpg as _asyncpg'),
                    ('kwarg', 'build dsn=dsn'),
                    ('opener', 'Load _asyncpg.connect'),
                    ('opener', 'Load _asyncpg.connect'),
                    ('opener', 'Load case'),
                    ('opener', 'Load case'),
                    ('opener', 'Load cf_pool.checkout'),
                    ('opener', 'Load harness.CaseSchema'),
                    ('opener', 'Load harness.bound_engine'),
                    ('opener', 'Load harness.bound_engine'),
                    ('opener', 'def case'),
                    ('opener', 'def fresh_database')],
 'tests/cf_pool.py': [('dsntext', 'postgresql+asyncpg://'),
                      ('dsntext', 'postgresql://'),
                      ('import', 'from sqlalchemy.ext.asyncio import async_sessionmaker'),
                      ('kwarg', 'cf_pg.build dsn=dsn'),
                      ('opener', 'Load asyncpg.connect'),
                      ('opener', 'Load asyncpg.connect'),
                      ('opener', 'Load asyncpg.connect'),
                      ('opener', 'Load asyncpg.connect'),
                      ('opener', 'Load harness.bound_engine'),
                      ('opener', 'Load harness.connect_bound'),
                      ('opener', 'Load harness.connect_bound'),
                      ('opener', 'Load harness.connect_bound'),
                      ('opener', 'Load harness.connect_bound'),
                      ('opener', 'Load harness.connect_bound'),
                      ('opener', 'def checkout'),
                      ('opener', 'str case'),
                      ('opener', 'str case')],
 'tests/ladder_pg_harness.py': [('dsntext',
                                 'One throwaway schema per case: bound, and censused before '
                                 'anything is\n'
                                 'created or dropped.\n'
                                 '\n'
                                 "Used by the ladder's live-PostgreSQL tests. Each case builds a "
                                 'schema of its\n'
                                 'own in the database LADDER_TEST_PG_DSN names -- on an instance '
                                 "other lanes'\n"
                                 'sessions share -- runs DDL into it, and drops it afterwards. Two '
                                 'of those\n'
                                 'steps do damage if they reach the wrong place: DDL landing '
                                 'outside the case\n'
                                 'schema, and a DROP ... CASCADE reaching past it. This module is '
                                 'the ticket-\n'
                                 'redaction lane\'s discipline ("one schema, and a census before '
                                 'anything\n'
                                 'destructive") adapted to a schema per case:\n'
                                 '\n'
                                 '  BIND     every connection a case opens is bound at connect to '
                                 'the case\n'
                                 '           schema alone (search_path in the startup packet). '
                                 'Before the\n'
                                 '           schema is created, current_schemas(true) must be '
                                 'exactly\n'
                                 '           [pg_catalog]: the path reaches nothing a statement '
                                 'could land in\n'
                                 '           or resolve against, so an unqualified statement sent '
                                 'too early\n'
                                 '           fails instead of landing elsewhere. Right after, the '
                                 'path must be\n'
                                 '           exactly [pg_catalog, <case>] and the case schema must '
                                 'hold no\n'
                                 '           object. DDL a case composes names the schema (a '
                                 'widening ALTER, a\n'
                                 '           relaxed NOT NULL). DDL it executes as text -- the '
                                 'migration files,\n'
                                 '           and test_title_ladders.LADDER_PREREQ, which that '
                                 'suite shares --\n'
                                 '           runs as written, unqualified, and the binding is what '
                                 'makes it\n'
                                 '           single-schema; the build is then PROVED '
                                 'single-schema: seal()\n'
                                 '           requires every object outside the case schema, in '
                                 'every schema a\n'
                                 '           client can create, to be exactly what it was before '
                                 'the build.\n'
                                 '  CREATE   the name is fresh (a uuid suffix) and a schema that '
                                 'already\n'
                                 '           exists is refused, never reused.\n'
                                 '  DROP     the census runs first, on a bound connection: the '
                                 'path must still\n'
                                 '           be [pg_catalog, <case>] -- preceded, at most, by this '
                                 "session's\n"
                                 '           OWN temporary schema (pg_my_temp_schema()), which '
                                 "migration 331's\n"
                                 '           ON COMMIT DROP post-check table leaves on the '
                                 "building session's\n"
                                 '           path and which only that session can put objects in; '
                                 'every\n'
                                 '           object in the case schema must be\n'
                                 '           one the build left there (the set seal() recorded), '
                                 'so an object\n'
                                 '           the case did not create refuses the drop; and no '
                                 'object OUTSIDE\n'
                                 '           the schema may depend on one inside it (pg_depend '
                                 'normal\n'
                                 '           dependencies, each dependent homed through its own '
                                 'catalog,\n'
                                 '           because pg_identify_object reports no schema for a '
                                 'column default\n'
                                 "           or a view's rule; a dependent it cannot home counts "
                                 'as outside).\n'
                                 '           Only then DROP SCHEMA ... CASCADE, which can then '
                                 'remove only what\n'
                                 '           the case created. A refusal leaves the schema in '
                                 'place.\n'
                                 '  NEVER    no pg_terminate_backend, no DROP of anything but the '
                                 "case's own\n"
                                 '           schema, nothing created in or dropped from public.\n'),
                                ('dsntext', 'postgresql+asyncpg://'),
                                ('dsntext', 'postgresql+asyncpg://'),
                                ('dsntext', 'postgresql://'),
                                ('dsntext', 'postgresql://'),
                                ('import',
                                 'from sqlalchemy.ext.asyncio import create_async_engine'),
                                ('import', 'from sqlalchemy.pool import NullPool'),
                                ('import', 'import asyncpg as _asyncpg'),
                                ('kwarg',
                                 "_asyncpg.connect server_settings={'search_path': "
                                 'quoted(schema)}'),
                                ('kwarg',
                                 "create_async_engine connect_args={'server_settings': "
                                 "{'search_path': quoted(schema)}}"),
                                ('opener', 'Load _asyncpg.connect'),
                                ('opener', 'Load connect_bound'),
                                ('opener', 'Load create_async_engine'),
                                ('opener', 'alias create_async_engine'),
                                ('opener', 'def CaseSchema'),
                                ('opener', 'def bound_engine'),
                                ('opener', 'def connect_bound')],
 'tests/migration_table_ddl.py': [('dsntext',
                                   "A table's DDL, read from the migration that creates it.\n"
                                   '\n'
                                   'Users:\n'
                                   '  - test_a1_predicate_sql.py and '
                                   'test_a1_formation_concurrency.py, the\n'
                                   '    live-PostgreSQL fixtures that build a narrow schema of '
                                   'their own. They\n'
                                   '    cannot replay the migration folder -- the formation file '
                                   'DROPs and\n'
                                   '    recreates players in a two-column shape, the predicate '
                                   'file carries only\n'
                                   '    the queue columns its predicates touch -- so when main.py '
                                   'starts reading\n'
                                   '    another table on their path (the readmission landing '
                                   '1eb1aac6 added\n'
                                   '    match_seat_holds to the discovery predicates and the four '
                                   'queue tables\n'
                                   '    plus match_seat_holds to the shared admission gate), the '
                                   'fixture creates\n'
                                   "    that table from this module's output.\n"
                                   '  - closed_walk.py, which classifies SQL text from this '
                                   "module's lexer\n"
                                   '    (MigrationDdlError, _views, _tokens).\n'
                                   "  - test_migration_table_ddl.py, this module's own lexical and "
                                   'grammar cases.\n'
                                   '\n'
                                   'A hand-copied CREATE TABLE drifts from the migration it '
                                   'copied; this module\n'
                                   'reads the statement out of the migration file instead.\n'
                                   '\n'
                                   'table_ddl(migration, table) returns [the CREATE TABLE '
                                   'statement, then every\n'
                                   'top-level CREATE INDEX on that table in the same file], in '
                                   'file order, each\n'
                                   'cut from its CREATE keyword to (not including) its terminating '
                                   'semicolon,\n'
                                   'with SQL comments blanked.\n'
                                   '\n'
                                   'What DDL a migration PERFORMS is not read here. Ruling '
                                   'REHEARSAL-FOUR-R6\n'
                                   '(1)(a): it is an effect, measured at the database by\n'
                                   'test_r7_catalog_diff_pg.py (catalog_diff.py): every migration '
                                   'is applied and\n'
                                   'the catalog is diffed before and after. That file also shows '
                                   "that table_ddl's\n"
                                   'statements reproduce, column for column, the relation each '
                                   'migration the a1\n'
                                   'fixtures name produced. The text readers that tried to work '
                                   'out such effects\n'
                                   'from the source are deleted, with no replacement: the DO-body '
                                   'grammar, the\n'
                                   'executable-position walk, EXECUTE composition and its trigger '
                                   'exemption,\n'
                                   'ddl_naming_table and code_md5. That includes any DDL a body, '
                                   'an EXECUTE or\n'
                                   'another language runs.\n'
                                   '\n'
                                   'The rule for what remains is: a form is parsed, or '
                                   'MigrationDdlError is\n'
                                   'raised. Nothing is silently left out. Concretely:\n'
                                   '\n'
                                   "  * Lexing follows PostgreSQL 16's lexical structure: line "
                                   'comments (ended\n'
                                   "    by CR or LF), NESTED block comments, standard strings ('' "
                                   'doubles a\n'
                                   '    quote; a backslash is an ordinary character), escape '
                                   "strings E'...' (a\n"
                                   '    backslash escapes the next character), the continuation '
                                   'rule (two string\n'
                                   '    constants separated by whitespace holding a newline, line '
                                   'comments\n'
                                   "    allowed in that gap, are ONE constant of the first one's "
                                   'kind, as scan.l\n'
                                   '    continues it; the same two with no newline between them '
                                   'are a lexical\n'
                                   '    error and raise), dollar-quoted bodies (tags of '
                                   "PostgreSQL's identifier\n"
                                   '    alphabet: letters including every non-ASCII character, '
                                   'digits not first,\n'
                                   '    underscores), and quoted identifiers ("" doubles a quote). '
                                   'Text inside\n'
                                   '    any of them is never taken for a statement.\n'
                                   '  * Names are compared as PostgreSQL resolves them: an '
                                   'unquoted name folds to\n'
                                   '    lower case, a quoted one is taken exactly. A '
                                   'schema-qualified name, or a\n'
                                   '    Unicode-escaped one (U&"..."), naming the table raises: '
                                   'the fixtures\n'
                                   '    build into their own search_path and cannot honour '
                                   'either.\n'
                                   '  * A CREATE TABLE of the table must be `name ( ... )` up to '
                                   'its semicolon,\n'
                                   '    with balanced parentheses; AS, OF and PARTITION OF raise. '
                                   'Exactly one\n'
                                   '    such statement may exist at the top level.\n'
                                   '  * A CREATE INDEX on the table is parsed as\n'
                                   '    CREATE [UNIQUE] INDEX [CONCURRENTLY] [[IF NOT EXISTS] '
                                   'name] ON [ONLY]\n'
                                   '    table [USING method] ( ... ) [anything else] ; -- the '
                                   'index name and the\n'
                                   '    table name may be quoted, the name may be absent -- and is '
                                   'returned\n'
                                   '    whole. Parentheses that do not balance before the '
                                   'semicolon raise.\n'
                                   '  * Any CREATE ... TABLE or CREATE ... INDEX head this grammar '
                                   'cannot parse\n'
                                   '    raises, whatever table it names, because it might name '
                                   'this one.\n'
                                   '  * A missing file, an unterminated comment, string, '
                                   'identifier or dollar\n'
                                   '    body, and a statement with no terminating semicolon '
                                   'raise.\n'),
                                  ('dsntext',
                                   'Parse a possibly qualified name at toks[k]. Returns (schema, '
                                   "rel, k')\n"
                                   '    with names as PostgreSQL resolves them, or raises.')],
 'tests/resolution_sites.py': [('dsntext', '@')],
 'tests/test_a1_formation_concurrency.py': [('dsntext',
                                             'A1 acceptance item 5 — two REAL PostgreSQL '
                                             'transactions, with barriers.\n'
                                             '\n'
                                             'Everything else in the A1 suite runs against a fake '
                                             'session, which can prove\n'
                                             'what statements are issued and in what order but '
                                             'cannot prove that the identity\n'
                                             'lock actually BLOCKS a second formation. '
                                             'Advisory-lock blocking and FOR UPDATE\n'
                                             'waiting are Postgres behaviours; a fake cannot '
                                             'exhibit them, and a test that\n'
                                             'merely observes "no deadlock after enough '
                                             'repetitions" would pass with the\n'
                                             "serialization removed entirely (that was r1's "
                                             'version of this item, and it was\n'
                                             'wrong).\n'
                                             '\n'
                                             'So this file needs a live server. Point '
                                             'A1_TEST_PG_DSN at a throwaway cluster:\n'
                                             '\n'
                                             '    '
                                             'A1_TEST_PG_DSN=postgresql+asyncpg://postgres@127.0.0.1:55432/a1test\n'
                                             '\n'
                                             'and the file skips when it is unset, so the ordinary '
                                             'suite is unaffected. It\n'
                                             'NEVER runs against a real deployment: it creates and '
                                             'drops its own tables, and\n'
                                             'every steam id it uses is outside the real id '
                                             'space.\n'
                                             '\n'
                                             'No pytest-asyncio: the rest of this suite drives '
                                             'coroutines through a plain\n'
                                             'asyncio.run helper, and an opt-in acceptance test is '
                                             'not a good reason to add a\n'
                                             'test dependency the other 66 files do not have.\n'
                                             '\n'
                                             'What it asserts, in one scenario:\n'
                                             '\n'
                                             '  * both formations complete discovery before either '
                                             'locks anything (the\n'
                                             '    barrier is a real asyncio.Event, not a sleep);\n'
                                             '  * the second formation BLOCKS in the identity '
                                             'phase while holding no row;\n'
                                             '  * the winner commits;\n'
                                             '  * the loser then wakes and is refused by the '
                                             'STRICT lease gate;\n'
                                             '  * exactly one formation exists and the loser wrote '
                                             'nothing at all.\n'),
                                            ('dsntext',
                                             'A1_TEST_PG_DSN unset; live-Postgres acceptance item'),
                                            ('env', 'A1_TEST_PG_DSN'),
                                            ('import', 'from sqlalchemy import text'),
                                            ('import',
                                             'from sqlalchemy.ext.asyncio import '
                                             'async_sessionmaker, create_async_engine'),
                                            ('opener', 'Load create_async_engine'),
                                            ('opener', 'alias create_async_engine')],
 'tests/test_a1_identity_formation.py': [('dsntext', ', acquire@'),
                                         ('dsntext', ': gate@'),
                                         ('import',
                                          'from sqlalchemy.exc import DBAPIError as _DBAPIError')],
 'tests/test_a1_predicate_sql.py': [('dsntext',
                                     'A1 — the formation predicates, EXECUTED against a real '
                                     'PostgreSQL.\n'
                                     '\n'
                                     'Why this file exists. The rest of the A1 suite is '
                                     'fake-session and source-\n'
                                     'walking: it proves the phase order, the lease policies and '
                                     'the bind shapes, and\n'
                                     'it cannot prove that any of the SQL parses. A1 moved five '
                                     'predicates to module\n'
                                     'constants and gave each a typed `:only` bind -- `CAST(:only '
                                     'AS uuid[])` for the\n'
                                     'four group predicates, `CAST(:only AS uuid)` for the 1v1 one '
                                     '-- and a bind that\n'
                                     'Postgres cannot type is not a subtle bug: it is every gather '
                                     'poll answering\n'
                                     '500, on the hottest paths in the game, in a batch whose '
                                     'whole tests-pass story\n'
                                     'would otherwise be green (#438/#443 -- acceptance is a '
                                     'POSITIVE signal the\n'
                                     'change emits, and "the fakes accepted it" is not one).\n'
                                     '\n'
                                     'So each predicate is run BOTH ways here -- `only` NULL to '
                                     'discover, `only`\n'
                                     'carrying discovered ids to revalidate -- against a real '
                                     'server, on a schema\n'
                                     'carrying only the columns the predicates touch. The '
                                     'assertions are about what\n'
                                     'the predicate SELECTS, not about matchmaking policy; the '
                                     'policy is tested\n'
                                     'against the handlers elsewhere.\n'
                                     '\n'
                                     'Skips unless A1_TEST_PG_DSN is set, exactly like\n'
                                     'test_a1_formation_concurrency.py, so CI and the ordinary '
                                     'suite are unaffected:\n'
                                     '\n'
                                     '    '
                                     'A1_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/a1test" '
                                     '\\\n'
                                     '        python -m pytest tests/test_a1_predicate_sql.py '
                                     '-q\n'),
                                    ('dsntext',
                                     'A1_TEST_PG_DSN unset; live-Postgres predicate check'),
                                    ('env', 'A1_TEST_PG_DSN'),
                                    ('import', 'from sqlalchemy import text'),
                                    ('import',
                                     'from sqlalchemy.ext.asyncio import async_sessionmaker, '
                                     'create_async_engine'),
                                    ('opener', 'Load create_async_engine'),
                                    ('opener', 'alias create_async_engine')],
 'tests/test_match_hold_admission_gate_pg.py': [('dsntext',
                                                 'H3: one durable per-player gate across holds and '
                                                 'every formation writer.\n'
                                                 '\n'
                                                 'The source census is DSN-free and names every '
                                                 'authorized admission span.  The\n'
                                                 'live controls exercise open and claim refusals '
                                                 'plus the common gate in both\n'
                                                 'target orders for all four queue modes.  '
                                                 'CF_TEST_PG_DSN/CF_TEST_PG_OPTOUT have\n'
                                                 'the same meaning as in the other match-hold '
                                                 'PostgreSQL suites.\n'),
                                                ('opener', 'Load case'),
                                                ('opener', 'Load case'),
                                                ('opener', 'Load case'),
                                                ('opener', 'Load case'),
                                                ('opener', 'Load case'),
                                                ('opener', 'Load cf_pg.case'),
                                                ('opener', 'Store case')],
 'tests/test_match_hold_pg.py': [('dsntext', 'FIX3 M2 context clock follows PostgreSQL wait'),
                                 ('dsntext',
                                  'Nested operations reuse setup and the absolute deadline; only '
                                  'owned\n'
                                  '    expiry and PostgreSQL timeout states map to 503, while '
                                  'cancellation and\n'
                                  '    an unrelated inner TimeoutError retain their identity.'),
                                 ('dsntext',
                                  'The 2v2 and 1v2 readmission server half (Stage 2 design V3), '
                                  'against a\n'
                                  'local PostgreSQL through cf_pg (one case schema per case, 383 '
                                  'in the build).\n'
                                  '\n'
                                  'The router of backend/api/match_hold.py is mounted on a test '
                                  'app of its own\n'
                                  '(main.py does not include it until NX1 of the build brief) and '
                                  'every route\n'
                                  'is called through HTTP with a session bound to the case schema. '
                                  'The Steam\n'
                                  'session check of main is replaced by a fixture that accepts '
                                  'exactly the\n'
                                  'token "tok:<steam id>" for the claimed id and answers 401 '
                                  'otherwise, so a\n'
                                  'route that skips the check, or checks the wrong id, is '
                                  'visible.\n'
                                  '\n'
                                  'MATCH_HOLD_SRC, when set, names a directory holding a MUTANT '
                                  'copy of\n'
                                  'match_hold.py; it is put first on sys.path, and the module '
                                  'census below\n'
                                  'proves the copy is the module the routes run (#742, #838). The '
                                  'mutation\n'
                                  'runner (backend/tests/evidence/match-hold-mutation-runner.py) '
                                  'sets it.\n'),
                                 ('dsntext', 'http://t'),
                                 ('dsntext', 'http://t'),
                                 ('dsntext', 'http://t'),
                                 ('import', 'from asyncpg import UniqueViolationError'),
                                 ('import', 'from sqlalchemy import text'),
                                 ('import', 'from sqlalchemy.exc import IntegrityError'),
                                 ('opener', 'Load cf_pg.case'),
                                 ('opener', 'Load cf_pg.harness.connect_bound'),
                                 ('opener', 'Load cf_pg.harness.connect_bound'),
                                 ('opener', 'Load cf_pg.harness.connect_bound')],
 'tests/test_pc_routes.py': [('dsntext',
                              "r13 (2026-09-13), rationale corrected by v4.13 (r14): admin_ban's "
                              'target is the key the ban row is written\n'
                              "    with, and a target outside the moderation target's domain -- "
                              'one to twenty ASCII digits, the whole string, the\n'
                              '    pattern migration 319 puts on every ACTIVE player_bans row -- '
                              'is refused 422 before the signature check, any\n'
                              '    read, any lock and the ban-rate gate. Both ends of the length '
                              'are pinned (one and twenty digits pass, none and\n'
                              '    twenty-one are refused), digits are [0-9] (Arabic-Indic and '
                              'fullwidth digits refused), the match is the whole\n'
                              '    string (a trailing newline refused), and a NUL character -- '
                              "PostgreSQL text cannot hold one, so the gate's\n"
                              '    best-effort refusal audit would fail on it silently (#656) -- '
                              'is refused, as is every value no text bind can\n'
                              '    carry (UNBINDABLE below, a lone surrogate among them; review '
                              'r15). A target that passes reaches the\n'
                              '    signature check unchanged. The unban makes no domain check '
                              'before its UPDATE (the next test).'),
                             ('dsntext',
                              'v4.13 (r14 LOW): player_bans.steam_id is TEXT in the applied schema '
                              "(028), so the api's check was the only\n"
                              '    boundary and nothing tied it to the table. Migration 319 adds '
                              "the helper's pattern, anchored at both ends, as a\n"
                              '    CHECK on ACTIVE rows -- an unbanned row keeps whatever key it '
                              'was written with, and an unban (which sets\n'
                              '    unbanned_at) always leaves a row the CHECK admits. '
                              "(PostgreSQL's `$` is the end of the string, the boundary\n"
                              '    fullmatch has: measured on the primary 2026-09-14 for twenty '
                              'and twenty-one digits, a trailing newline,\n'
                              '    Arabic-Indic and fullwidth digits.) The file counts the active '
                              'rows outside the pattern and raises a named\n'
                              "    error with that count (ADD CONSTRAINT's own validation would "
                              'fail on them too, without the count), adds the\n'
                              '    constraint only when it is absent, validates it (no NOT VALID) '
                              'and is one explicit transaction. The domain is\n'
                              '    spelled once: no moderation route or core calls fullmatch '
                              'itself.'),
                             ('import', 'from sqlalchemy import select')],
 'tests/test_pc_sept12.py': [('dsntext',
                              "The text of a PostgreSQL E'...' literal as the generator writes "
                              'them.')],
 'tests/test_title_ladder_hooks_live.py': [('dsntext',
                                            'The ladder hook, DRIVEN: the three ranked '
                                            'game-reporting paths through their\n'
                                            'real handlers, against a real PostgreSQL built from '
                                            'the migrations.\n'
                                            '\n'
                                            'test_title_ladders.py proves from the parse tree that '
                                            'main.py calls the hook\n'
                                            'once per ranked game-reporting path, awaited, with '
                                            'the right reference. This\n'
                                            'file proves what those calls DO, per site. The unit '
                                            'is the GAME (board row\n'
                                            '29, the title ladders build): every ranked game '
                                            'credits each player once,\n'
                                            "keyed by that game's own row id, so a 1v1 or 2v2 "
                                            'series of two games credits\n'
                                            'two. The bar, from LADDER-HOOK-DESIGN-LITE-V3 '
                                            'sections 3, 4 and 12.5 with the\n'
                                            'unit moved from the series to the game:\n'
                                            '\n'
                                            '  H3  one game delivered twice is credited once. '
                                            "1v1's second delivery of a\n"
                                            "      report dies at the match insert's flush on "
                                            'unique_match with nothing\n'
                                            "      written; 2v2's is the duplicate echo; FFA's is "
                                            'refused by the room gate\n'
                                            '      -- the replay echo -- with no second '
                                            'ffa_matches row. The after-the-fact\n'
                                            '      2v2 settlement (admin completion, lead forfeit) '
                                            'plays no game and\n'
                                            '      credits nothing, whichever path completed the '
                                            'series.\n'
                                            "  H5  a DATABASE fault inside the hook's call -- the "
                                            'real hook runs, then a\n'
                                            '      failing statement -- costs the completion '
                                            'nothing. The same completion\n'
                                            '      runs twice, clean and faulted, each in a fresh '
                                            'schema: the result,\n'
                                            '      ratings, XP, gold and items match, the faulted '
                                            'run holds no credit and\n'
                                            '      no ladder change anywhere, and it printed '
                                            'exactly one\n'
                                            '      `[LADDER-CREDIT] ... dropped` line. The control '
                                            'removes only the\n'
                                            "      savepoint around the call -- the handler's own "
                                            'source, compiled without\n'
                                            '      that one `async with` -- and the same fault '
                                            'then loses the whole\n'
                                            '      completion (#235/#536).\n'
                                            "  H6  what a game wrote reads back through main.app's "
                                            'own GET, on a session\n'
                                            '      of its own: +1 on the worn line per game.\n'
                                            '  H8  every must-not-count line leaves no credit and '
                                            'no progress change:\n'
                                            '      1v1 casual after the downgrade, an '
                                            'anti-cheat-invalidated match, a\n'
                                            '      closed bracket room and the abandoned idle '
                                            'series; 2v2 a roster, room\n'
                                            '      or partition mismatch and a series that is not '
                                            'active; every 2v2\n'
                                            '      settlement (admin completion, lead forfeit, the '
                                            "helper's missing-row,\n"
                                            '      completed and unfilled-slot returns -- that '
                                            "slot's NOT NULL relaxed in\n"
                                            '      the throwaway schema alone, 053_2v2_schema.sql '
                                            'makes all four NOT NULL\n'
                                            '      -- an admin void and a disconnect that is not a '
                                            'clear forfeit); FFA a\n'
                                            '      casual lobby, the refusals before the insert '
                                            '(lobby not active, score\n'
                                            '      shape, game number), a failed insert and a '
                                            'failed strict skew refund.\n'
                                            "      FFA's ghost and grace controls are read per "
                                            'game in the game-keyed test\n'
                                            '      below.\n'
                                            '\n'
                                            'Beside the three sites: the FFA game-keyed test (two '
                                            'games of one lobby\n'
                                            'credit each rated player per game; a ghost or a '
                                            'graced leaver gets nothing\n'
                                            'for the game it did not play), and three of Codex '
                                            "round 2's LOW residual\n"
                                            'sentences (design 12.6) made tests, re-read for the '
                                            'game unit: R1 (a fault\n'
                                            "in game 1 costs game 1's credit and nothing else; "
                                            'game 2 credits its own),\n'
                                            'R3 (the 1v1 credit stands when the rating pass fails '
                                            'or skips, and causes\n'
                                            'nothing else) and Q-G (the resent deciding 1v1 report '
                                            'answers 500 through\n'
                                            'main.app and writes nothing -- behaviour documented '
                                            'as it stands, not\n'
                                            'changed here).\n'
                                            '\n'
                                            'Every H3 and H8 case also records each call main.py '
                                            'makes to the hook, the\n'
                                            'real hook still doing the work (the hook_calls '
                                            'fixture), and asserts it: a\n'
                                            'must-not-count line must never REACH the hook (design '
                                            '4.1), a counted one\n'
                                            'reaches it exactly once, with its mode, its reference '
                                            'and every participant,\n'
                                            'and the one line that reaches it and is then rolled '
                                            'back -- the failed strict\n'
                                            'skew refund -- is told apart from a line that never '
                                            'got there.\n'
                                            '\n'
                                            'THE SCHEMA. Every case builds its own, in a throwaway '
                                            'schema through\n'
                                            'ladder_pg_harness: every connection bound to it at '
                                            'connect, a census before\n'
                                            'anything is created or dropped. The DDL of every '
                                            'numbered migration but the\n'
                                            'ladder catalogue files (331, 365) and the refund '
                                            '(366, a production-census\n'
                                            'data migration) is replayed -- statements that create '
                                            'or alter a table, index, function, trigger,\n'
                                            'type or sequence, and DO blocks that do; no data '
                                            'statement, no extension, and\n'
                                            "nothing that names a session's temporary schema "
                                            '(backfill helpers) -- then the\n'
                                            "ORM's create_all makes the tables no migration "
                                            'creates, the mapped tables are\n'
                                            'widened to every column the models map, and the DDL '
                                            'is replayed again now that\n'
                                            'the tables it alters exist. That second pass may fail '
                                            'only with an\n'
                                            'already-exists code or on one of REPLAY_KNOWN, '
                                            'statements on tables none of\n'
                                            'the three paths touch; anything else fails the case. '
                                            'Migrations 331 and 365\n'
                                            'then run whole, as written, in that order, and the '
                                            'tables and the five-tier\n'
                                            'rungs are confirmed. A case that needs a\n'
                                            'schema change of its own makes it next, and only then '
                                            'is the build sealed.\n'
                                            '\n'
                                            'There is no defaults fill here, unlike '
                                            "test_title_ladders' ORM-only listing\n"
                                            "schema: the replayed tables carry production's own "
                                            'defaults, and a default\n'
                                            'given here to a NOT NULL column that production '
                                            'leaves without one would turn\n'
                                            'a production NOT NULL failure into a pass. Rows a '
                                            'fixture writes into an\n'
                                            'ORM-made table get explicit values for such columns '
                                            'instead (_insert).\n'
                                            '\n'
                                            'The handlers run with MATCH_HMAC_SECRET cleared -- '
                                            'the module\'s own "no secret\n'
                                            'configured" path -- and the Steam session check '
                                            'replaced, as\n'
                                            'test_ffa_game_number_anchor.py drives '
                                            'submit_ffa_match; neither is what this\n'
                                            'file is about. The one exception is the lead-forfeit '
                                            "test's two signed\n"
                                            'live-points posts (the comment above '
                                            '_live_points_sig). Every observation is\n'
                                            'made on a connection of its own, never on the session '
                                            'that ran the write.\n'
                                            '\n'
                                            'Live PostgreSQL is REQUIRED, and a missing DSN FAILS, '
                                            'naming the variable --\n'
                                            "the gate test_title_ladders.py's live half uses:\n"
                                            '    '
                                            'LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane '
                                            'database>\n'
                                            '    LADDER_TEST_PG_OPTOUT=1   waives the live cases '
                                            'deliberately\n'),
                                           ('dsntext', 'http://ladder.test'),
                                           ('dsntext', 'http://ladder.test'),
                                           ('dsntext', 'http://ladder.test/'),
                                           ('dsntext', 'postgresql+asyncpg://'),
                                           ('dsntext', 'postgresql://'),
                                           ('env', 'DSN_VAR'),
                                           ('import', 'from sqlalchemy import text'),
                                           ('import', 'from sqlalchemy.dialects import postgresql'),
                                           ('import', 'from sqlalchemy.exc import IntegrityError'),
                                           ('import',
                                            'from sqlalchemy.ext.asyncio import AsyncSession, '
                                            'async_sessionmaker'),
                                           ('import', 'import asyncpg as _asyncpg'),
                                           ('opener', 'Load case'),
                                           ('opener', 'Load case'),
                                           ('opener', 'Load case'),
                                           ('opener', 'Load case'),
                                           ('opener', 'Load case'),
                                           ('opener', 'Load case'),
                                           ('opener', 'Load harness.CaseSchema'),
                                           ('opener', 'Load harness.bound_engine'),
                                           ('opener', 'Load harness.bound_engine'),
                                           ('opener', 'Load harness.bound_engine'),
                                           ('opener', 'Load harness.bound_engine'),
                                           ('opener', 'Load harness.bound_engine'),
                                           ('opener', 'Load harness.connect_bound'),
                                           ('opener', 'Load harness.connect_bound'),
                                           ('opener', 'Load harness.connect_bound'),
                                           ('opener', 'Load harness.connect_bound'),
                                           ('opener', 'Load harness.connect_bound'),
                                           ('opener', 'Store case')],
 'tests/test_title_ladders.py': [('dsntext',
                                  '%s is unset and %s=1: live-Postgres ladder coverage '
                                  'deliberately waived.'),
                                 ('dsntext',
                                  '331, RUN. Not parsed, not regex-matched -- executed, '
                                  'post-checks and\n'
                                  '    all, on the version of PostgreSQL the primary runs.\n'
                                  '\n'
                                  '    This is the test a syntax-only mutation reddens. Every '
                                  'other assertion\n'
                                  '    about this file in this module is satisfied by SQL that '
                                  'would abort on its\n'
                                  '    first statement.\n'
                                  '    '),
                                 ('dsntext', '@'),
                                 ('dsntext',
                                  "SELECT 'relation' AS what, c.relname AS name, c.relkind::text "
                                  "|| ':' || c.oid::text AS ident   FROM pg_class c JOIN "
                                  'pg_namespace n ON n.oid = c.relnamespace  WHERE n.nspname = '
                                  "current_schema() UNION ALL SELECT 'constraint', co.conname || "
                                  "'@' || co.conrelid::text, co.oid::text   FROM pg_constraint co "
                                  'JOIN pg_namespace n ON n.oid = co.connamespace  WHERE n.nspname '
                                  "= current_schema() UNION ALL SELECT 'function', p.proname, "
                                  "p.oid::text || ':' || md5(p.prosrc)   FROM pg_proc p JOIN "
                                  'pg_namespace n ON n.oid = p.pronamespace  WHERE n.nspname = '
                                  "current_schema() UNION ALL SELECT 'trigger', tg.tgname || '@' "
                                  "|| tg.tgrelid::text, tg.oid::text || ':' || "
                                  'tg.tgenabled::text   FROM pg_trigger tg JOIN pg_class c ON '
                                  'c.oid = tg.tgrelid   JOIN pg_namespace n ON n.oid = '
                                  'c.relnamespace  WHERE n.nspname = current_schema() AND NOT '
                                  'tg.tgisinternal'),
                                 ('dsntext',
                                  'THE DEDUPE, DRIVEN THROUGH POSTGRESQL.\n'
                                  '\n'
                                  '    A report can be retried, so one game reaches this hook more '
                                  'than once by\n'
                                  '    construction. `title_ladder_credits` PRIMARY KEY '
                                  '(player_id, reference_id)\n'
                                  '    plus `ON CONFLICT DO NOTHING RETURNING 1` is the whole '
                                  'gate: the writer\n'
                                  '    that wins the insert is the one that increments.\n'
                                  '\n'
                                  '    Changing that `DO NOTHING` to a `DO UPDATE` makes the '
                                  'second arrival\n'
                                  '    return a row, credit again, and -- with the player seeded '
                                  'one game short\n'
                                  '    of the threshold -- hand out a rung for a game they played '
                                  'once. The\n'
                                  '    fake-session version of this test cannot see that mutation, '
                                  'because the\n'
                                  '    fake decides for itself what the second insert returns.\n'
                                  '    '),
                                 ('dsntext', 'postgresql+asyncpg://'),
                                 ('dsntext', 'postgresql+asyncpg://'),
                                 ('dsntext', 'postgresql+asyncpg://'),
                                 ('dsntext', 'postgresql://'),
                                 ('dsntext', 'postgresql://'),
                                 ('dsntext', 'postgresql://'),
                                 ('env', 'DSN_VAR'),
                                 ('env', 'LADDER_DSN_VAR'),
                                 ('import', 'from sqlalchemy import text as _text'),
                                 ('import', 'from sqlalchemy import text as _text'),
                                 ('import',
                                  'from sqlalchemy.ext.asyncio import async_sessionmaker, '
                                  'create_async_engine'),
                                 ('import', 'import asyncpg'),
                                 ('import', 'import asyncpg as _asyncpg'),
                                 ('kwarg',
                                  "create_async_engine connect_args={'server_settings': "
                                  "{'search_path': schema}}"),
                                 ('opener', 'Load _asyncpg.connect'),
                                 ('opener', 'Load _asyncpg.connect'),
                                 ('opener', 'Load _asyncpg.connect'),
                                 ('opener', 'Load _asyncpg.connect'),
                                 ('opener', 'Load _asyncpg.connect'),
                                 ('opener', 'Load _asyncpg.connect'),
                                 ('opener', 'Load asyncpg.connect'),
                                 ('opener', 'Load create_async_engine'),
                                 ('opener', 'alias create_async_engine')]}

# The complete layer (ruling REHEARSAL-R8-A1 G1; ro_census.complete_forms
# over the same files, census keys file + ro_census.COMPLETE), derived ONCE
# at the round-8 tip effc36c6 by RF/r9/ro/derive_complete.py: a judgement
# against the never-regenerated standard, recorded in the round-9 notes.
# The coarse FROZEN literal above is unchanged; like it, this layer is never
# regenerated: a new form is refused until a reviewed edit freezes it here.
COMPLETE_FROZEN = {'api/admin_evidence.py#complete': [],
 'api/auto_logs.py#complete': [],
 'api/build_manifest.py#complete': [],
 'api/card_evidence.py#complete': [],
 'api/card_measures.py#complete': [],
 'api/combat_evidence.py#complete': [],
 'api/combat_measures.py#complete': [('ref', 'case is None'),
                                     ('ref',
                                      "{'case': case, 'case_text': None, 'cycles': rows, "
                                      "'pairing': pairing, 'self_label': LABEL_SELF, 'meas_label': "
                                      "LABEL_MEAS, 'self_present': owner_rec is not None, "
                                      "'meas_present': meas_rec is not None}")],
 'api/conn_ranges.py#complete': [],
 'api/database.py#complete': [('call',
                               '_sqlalchemy_create_async_engine(url, hide_parameters=True, '
                               '**options)'),
                              ('call',
                               'create_async_engine(DATABASE_URL, echo=False, pool_size=20, '
                               'max_overflow=10, pool_timeout=30, pool_pre_ping=True, '
                               'pool_recycle=1800)'),
                              ('call',
                               'create_async_engine(DATABASE_URL, echo=False, '
                               'pool_size=RELEASE_POOL_SIZE, max_overflow=RELEASE_POOL_OVERFLOW, '
                               'pool_timeout=30, pool_pre_ping=True, pool_recycle=1800)'),
                              ('call',
                               'create_async_engine(url, echo=False, pool_size=ASM_POOL_SIZE, '
                               'max_overflow=ASM_POOL_OVERFLOW, pool_timeout=ASM_POOL_TIMEOUT_S, '
                               'pool_pre_ping=True, pool_recycle=1800, connect_args=args)'),
                              ('call', 'make_asm_engine()')],
 'api/flag_evidence.py#complete': [],
 'api/glicko2.py#complete': [],
 'api/identity_clock_evidence.py#complete': [],
 'api/identity_clock_measures.py#complete': [],
 'api/log_redaction.py#complete': [],
 'api/mail_discord.py#complete': [],
 'api/main.py#complete': [('call', 'chat_manager.connect(ws)'),
                          ('dynamic', 'getattr(e, attr, None)'),
                          ('dynamic', 'getattr(e, attr, None)'),
                          ('dynamic', 'getattr(e, attr, None)'),
                          ('dynamic', 'getattr(report, k)'),
                          ('dynamic', 'getattr(report, request_field)'),
                          ('dynamic',
                           "getattr(req, 'preferred_team' if mode == 'team' else 'preferred_side', "
                           'None)'),
                          ('dynamic',
                           "getattr(req, 'preferred_team' if mode == 'team' else 'preferred_side', "
                           'None)'),
                          ('dynamic', 'getattr(req, field)'),
                          ('dynamic', 'getattr(req, field)'),
                          ('dynamic', 'globals()'),
                          ('dynamic', 'globals()'),
                          ('dynamic', 'globals()'),
                          ('dynamic', 'setattr(player, attr, None)'),
                          ('dynamic', 'setattr(player, attr, item_id)'),
                          ('ref', 'case is None'),
                          ('ref', "case['kind']"),
                          ('ref', "case['kind']"),
                          ('ref', "case['kind']"),
                          ('ref', "case['resolution']"),
                          ('ref', "case['status']"),
                          ('ref', "case['status']"),
                          ('ref', "case['subject_name']"),
                          ('ref', "case['subject_name']"),
                          ('ref', "case['subject_steam_id']")],
 'api/match_hold.py#complete': [('dynamic', 'getattr(current, name, None)'),
                                ('dynamic', 'getattr(current, name, None)')],
 'api/match_report_window.py#complete': [],
 'api/models.py#complete': [],
 'api/pc_face.py#complete': [('ref', "case == 'smallcaps'"), ('ref', "case == 'spaced'")],
 'api/pc_motion.py#complete': [],
 'api/pc_portrait.py#complete': [],
 'api/pc_signature.py#complete': [('ref', 'case is None'),
                                  ('ref',
                                   "{'bold': flags['bold'], 'case': case, 'fill': fill, 'glow': "
                                   "glow, 'italic': flags['italic'], 'rgb': rgb, 'rgb2': rgb2, "
                                   "'size': float(size), 'strike': flags['strike'], 'underline': "
                                   "flags['underline']}")],
 'api/pc_steam.py#complete': [],
 'api/pc_strip.py#complete': [],
 'api/player_cards.py#complete': [],
 'api/read_gate.py#complete': [],
 'api/region_pick.py#complete': [],
 'api/review_boot.py#complete': [('dynamic',
                                  "exec(compile(raw, path, 'exec', dont_inherit=True), "
                                  'vars(module))'),
                                 ('dynamic', 'sys.modules'),
                                 ('dynamic', 'sys.modules'),
                                 ('dynamic', 'sys.modules'),
                                 ('dynamic', 'vars(module)')],
 'api/review_measures.py#complete': [('ref', "' '.join(case)"),
                                     ('ref', 'case.append'),
                                     ('ref', 'case.append')],
 'api/review_rules.py#complete': [('dynamic', 'mine.__dict__'),
                                  ('dynamic', 'sys.modules'),
                                  ('ref', "case['card']"),
                                  ('ref', "case['census']"),
                                  ('ref', "case['combat']"),
                                  ('ref', "case['combat']"),
                                  ('ref', "case['fire']"),
                                  ('ref', "case['fire']"),
                                  ('ref', "case['fire']"),
                                  ('ref', "case['fire']"),
                                  ('ref', "case['fire']"),
                                  ('ref', "case['identity']"),
                                  ('ref', "case['identity']"),
                                  ('ref', "case['match']"),
                                  ('ref', "case['records']"),
                                  ('ref', "case['records']"),
                                  ('ref', "case['registries']"),
                                  ('ref', "case['registry']"),
                                  ('ref', "case['sc']"),
                                  ('ref', "case['windows']"),
                                  ('ref', 'entry.impl[-1](self, case, budget)'),
                                  ('ref', 'isinstance(case, dict)'),
                                  ('ref', 'isinstance(case, dict)'),
                                  ('ref', 'isinstance(case, dict)'),
                                  ('ref', 'isinstance(case, dict)'),
                                  ('ref', 'isinstance(case, dict)'),
                                  ('ref', 'set(case)'),
                                  ('ref', 'set(case)'),
                                  ('ref', 'set(case)'),
                                  ('ref', 'set(case)'),
                                  ('ref', 'set(case)')],
 'api/schemas.py#complete': [],
 'api/seat_evidence.py#complete': [],
 'api/steamid64.py#complete': [],
 'api/title_ladders.py#complete': [('dynamic', "getattr(match, f'{me}_bullets_fired', None)"),
                                   ('dynamic', "getattr(match, f'{me}_bullets_hit', None)"),
                                   ('dynamic', "getattr(match, f'{me}_rounds_won', None)"),
                                   ('dynamic', "getattr(match, f'{opp}_rounds_won', None)")],
 'api/tournament_bracket.py#complete': [],
 'api/tournaments.py#complete': [],
 'tests/cf_pg.py#complete': [('call', '_asyncpg.connect(DSN)'),
                             ('call', '_asyncpg.connect(DSN)'),
                             ('call', 'cf_pool.checkout(faithful=faithful)'),
                             ('call', 'harness.CaseSchema(dsn or DSN, prefix)'),
                             ('call', 'harness.bound_engine(dsn or DSN, c.schema)'),
                             ('call', 'harness.bound_engine(dsn or DSN, schema)'),
                             ('ref', 'case.conn'),
                             ('ref', 'case.schema')],
 'tests/cf_pool.py#complete': [('call', 'asyncpg.connect(cf_pg.DSN)'),
                               ('call', 'asyncpg.connect(dsn)'),
                               ('call', 'asyncpg.connect(dsn, timeout=10, command_timeout=10)'),
                               ('call', 'asyncpg.connect(dsn, timeout=10, command_timeout=15)'),
                               ('call', 'harness.bound_engine(dsn, schema)'),
                               ('call', 'harness.connect_bound(dsn, schema)'),
                               ('call', 'harness.connect_bound(dsn, schema)'),
                               ('call', 'harness.connect_bound(dsn, schema)'),
                               ('call', 'harness.connect_bound(dsn, schema)'),
                               ('call', 'harness.connect_bound(self.dsn, self.schema)'),
                               ('dynamic', 'sys.modules')],
 'tests/closed_walk.py#complete': [('dynamic', 'getattr(p, f)'),
                                   ('dynamic', 'getattr(self.scope, name, _MISSING)'),
                                   ('dynamic', 'getattr(st, field, None)')],
 'tests/ladder_pg_harness.py#complete': [('call',
                                          "_asyncpg.connect(dsn.replace('postgresql+asyncpg://', "
                                          "'postgresql://'), server_settings={'search_path': "
                                          'quoted(schema)})'),
                                         ('call', 'connect_bound(self.dsn, self.schema)'),
                                         ('call',
                                          'create_async_engine(async_dsn(dsn), poolclass=NullPool, '
                                          "connect_args={'server_settings': {'search_path': "
                                          'quoted(schema)}})')],
 'tests/migration_table_ddl.py#complete': [],
 'tests/pc_themes_data.py#complete': [],
 'tests/resolution_sites.py#complete': [],
 'tests/test_a1_formation_concurrency.py#complete': [('call', 'create_async_engine(DSN)')],
 'tests/test_a1_identity_formation.py#complete': [('dynamic',
                                                   "eval(compile(_ast.Expression(test), '<test>', "
                                                   "'eval'), {'__builtins__': {}, 'len': len}, "
                                                   'dict(env))'),
                                                  ('dynamic',
                                                   'exec(compile(_R3_HELPER_SRC, mod.__file__, '
                                                   "'exec'), mod.__dict__)"),
                                                  ('dynamic',
                                                   'exec(compile(_R4_CW_SRC, mod.__file__, '
                                                   "'exec'), mod.__dict__)"),
                                                  ('dynamic',
                                                   'exec(compile(_R5_CW_SRC, mod.__file__, '
                                                   "'exec'), mod.__dict__)"),
                                                  ('dynamic',
                                                   "exec(compile(text, mod.__file__, 'exec'), "
                                                   'mod.__dict__)'),
                                                  ('dynamic',
                                                   "exec(compile(text, mod.__file__, 'exec'), "
                                                   'mod.__dict__)'),
                                                  ('dynamic', 'getattr(_SAMPLE, name)'),
                                                  ('dynamic', 'getattr(_cw, _ACC)'),
                                                  ('dynamic', 'getattr(main, const)'),
                                                  ('dynamic', 'getattr(main, const)'),
                                                  ('dynamic', 'getattr(main, function_name)'),
                                                  ('dynamic', 'getattr(main, n)'),
                                                  ('dynamic', 'getattr(main, n)'),
                                                  ('dynamic', 'getattr(main, name)'),
                                                  ('dynamic', 'getattr(main, name)'),
                                                  ('dynamic', 'getattr(main, name)'),
                                                  ('dynamic', 'getattr(main, name)'),
                                                  ('dynamic', 'getattr(main, name)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(main, site)'),
                                                  ('dynamic', 'getattr(mod, name)'),
                                                  ('dynamic', 'getattr(mod, span)'),
                                                  ('dynamic', 'getattr(parent, field, None)'),
                                                  ('dynamic',
                                                   "getattr(scope, getattr(d, 'name', ''), None)"),
                                                  ('dynamic', 'getattr(scope, helper)'),
                                                  ('dynamic', 'getattr(scope, helper)'),
                                                  ('dynamic', 'hasattr(_cw, n)'),
                                                  ('dynamic', 'hasattr(_cw.Bindings, n)'),
                                                  ('dynamic', 'hasattr(mod, name)'),
                                                  ('dynamic', 'mod.__dict__'),
                                                  ('dynamic', 'mod.__dict__'),
                                                  ('dynamic', 'mod.__dict__'),
                                                  ('dynamic', 'mod.__dict__'),
                                                  ('dynamic', 'mod.__dict__'),
                                                  ('dynamic', 'mod.__dict__'),
                                                  ('dynamic', 'vars(main)'),
                                                  ('dynamic', 'getattr(blk, field, None)')],
 'tests/test_a1_predicate_sql.py#complete': [('call', 'create_async_engine(DSN)')],
 'tests/test_match_hold_admission_gate_pg.py#complete': [('call', "cf_pg.case('h3gate')"),
                                                         ('dynamic',
                                                          'exec(compile(src, mod.__file__, '
                                                          "'exec'), mod.__dict__)"),
                                                         ('dynamic',
                                                          "exec(compile(text, filename, 'exec'), "
                                                          'mod.__dict__)'),
                                                         ('dynamic', 'getattr(main, name)'),
                                                         ('dynamic', 'getattr(main, name)'),
                                                         ('dynamic', 'getattr(main, name, None)'),
                                                         ('dynamic', 'getattr(match_hold, name)'),
                                                         ('dynamic', 'getattr(module, name)'),
                                                         ('dynamic',
                                                          'getattr(parent, field, None)'),
                                                         ('dynamic', 'mod.__dict__'),
                                                         ('dynamic', 'mod.__dict__'),
                                                         ('dynamic', 'mod.__dict__'),
                                                         ('dynamic', 'mod.__dict__'),
                                                         ('dynamic', 'module.__dict__'),
                                                         ('dynamic',
                                                          'monkeypatch.setattr(main, name, '
                                                          'step(name))'),
                                                         ('dynamic',
                                                          'setattr(scope, name, '
                                                          'getattr(match_hold, name))'),
                                                         ('dynamic', 'sys.modules'),
                                                         ('dynamic', 'sys.modules'),
                                                         ('dynamic', 'sys.modules'),
                                                         ('ref', 'case.conn'),
                                                         ('ref', 'case.conn'),
                                                         ('ref', 'case.conn'),
                                                         ('ref', 'case.conn'),
                                                         ('ref', 'case.conn')],
 'tests/test_match_hold_pg.py#complete': [('call', 'cf_pg.case(prefix)'),
                                          ('call',
                                           'cf_pg.harness.connect_bound(env.c.dsn, env.c.schema)'),
                                          ('call',
                                           'cf_pg.harness.connect_bound(env.c.dsn, env.c.schema)'),
                                          ('call',
                                           'cf_pg.harness.connect_bound(env.c.dsn, env.c.schema)'),
                                          ('dynamic', 'sys.modules'),
                                          ('dynamic', 'sys.modules'),
                                          ('dynamic', 'sys.modules')],
 'tests/test_pc_routes.py#complete': [],
 'tests/test_pc_sept12.py#complete': [],
 'tests/test_player_cards_server.py#complete': [('dynamic', 'getattr(main, name)'),
                                                ('dynamic', 'getattr(main, name)'),
                                                ('dynamic', 'getattr(main, name)')],
 'tests/test_title_ladder_hooks_live.py#complete': [('call',
                                                     "harness.CaseSchema(DSN, 'ladder_hooks')"),
                                                    ('call',
                                                     'harness.bound_engine(DSN, case.schema)'),
                                                    ('call', 'harness.bound_engine(DSN, schema)'),
                                                    ('call', 'harness.bound_engine(DSN, schema)'),
                                                    ('call', 'harness.bound_engine(DSN, schema)'),
                                                    ('call', 'harness.bound_engine(DSN, schema)'),
                                                    ('call', 'harness.connect_bound(DSN, schema)'),
                                                    ('call', 'harness.connect_bound(DSN, schema)'),
                                                    ('call', 'harness.connect_bound(DSN, schema)'),
                                                    ('call', 'harness.connect_bound(DSN, schema)'),
                                                    ('call', 'harness.connect_bound(DSN, schema)'),
                                                    ('dynamic',
                                                     "exec(compile(module, '%s [%s without its "
                                                     "hook savepoint]' % (MAIN_PY, name), 'exec'), "
                                                     'namespace)'),
                                                    ('dynamic',
                                                     'monkeypatch.setattr(tl, HOOK, _hook)'),
                                                    ('dynamic',
                                                     'monkeypatch.setattr(tl, HOOK, _no_hook)'),
                                                    ('dynamic',
                                                     'monkeypatch.setattr(tl, HOOK, _spy)'),
                                                    ('dynamic', 'vars(main)'),
                                                    ('ref', '_build(case, extra_ddl)'),
                                                    ('ref', 'case.conn'),
                                                    ('ref', 'case.schema'),
                                                    ('ref', 'case.schema'),
                                                    ('ref', 'case.schema'),
                                                    ('ref', 'case.seal')],
 'tests/test_title_ladders.py#complete': [('call', '_asyncpg.connect(LADDER_DSN)'),
                                          ('call', '_asyncpg.connect(LADDER_DSN)'),
                                          ('call', '_asyncpg.connect(LADDER_DSN)'),
                                          ('call', '_asyncpg.connect(LADDER_DSN)'),
                                          ('call', '_asyncpg.connect(LADDER_DSN)'),
                                          ('call', '_asyncpg.connect(LADDER_DSN)'),
                                          ('call',
                                           "asyncpg.connect(DSN.replace('postgresql+asyncpg://', "
                                           "'postgresql://'))"),
                                          ('call',
                                           "create_async_engine(LADDER_DSN.replace('postgresql://', "
                                           "'postgresql+asyncpg://'), "
                                           "connect_args={'server_settings': {'search_path': "
                                           'schema}}, poolclass=None)'),
                                          ('dynamic', 'self.__dict__')],
 'tests/title_ladders_lane_schema.py#complete': []}
# Coarse layer re-frozen ONCE at the round-11 merge (FOUR-R11-A16 (5)) from the
# seat derivation test_zz_r11_rec_derive (never-merged branch
# claude/rehearsal-four-r11-rec-derive) at 21aaf7f2: 2 coarse forms the round-10
# grammar finds beyond FROZEN, each text (listed with file and line in the
# round-11 notes); they join FROZEN's coarse keys.
R11_COARSE_FROZEN = {'tests/test_match_hold_admission_gate_pg.py': [('dsntext',
                                                 'FOUR-R11-A9 (1)(c): the operations the '
                                                 'S2 and S3 conditions use on a\n'
                                                 '    UUID value of a seat row (NOTES r11 '
                                                 'rules, "K table amendment"): str()\n'
                                                 "    (_asm_deferred_departure's pidt) and "
                                                 'binding as a statement parameter\n'
                                                 "    through main's session (every "
                                                 'seat["player_id"] bind). Each is '
                                                 'executed\n'
                                                 "    on a value read through main's own "
                                                 'session from PostgreSQL (the\n'
                                                 "    driver's class) and on a uuid.UUID "
                                                 'of the same value, and must agree;\n'
                                                 "    str() is the driver's own "
                                                 'implementation (read from the class).'),
                                                ('dsntext',
                                                 'Rules W, P and K (ruling FOUR-R11-A4 '
                                                 '(2)(a) to (2)(g)): every bound\n'
                                                 '    discharge the real gate walks of S1 '
                                                 "(_asm_readmit_work's\n"
                                                 "    _asm_readmit_on), S2 (_rdm_claim's "
                                                 '_rdm_live_or_lapse) and S3\n'
                                                 "    (_rdm_claim's gate refusal) make is "
                                                 'marked by the walk (site, rule);\n'
                                                 '    each marked site is observed on the '
                                                 "measured flows (main's own\n"
                                                 '    construction path, PostgreSQL rows), '
                                                 'its value of the named type and\n'
                                                 '    its root an instance of K by type '
                                                 "identity; every call at rule W's site\n"
                                                 '    calls a function of the census, the '
                                                 'named one with a K first argument.\n'
                                                 '    An unreached marked site fails, '
                                                 'listed. The interpreter must provide\n'
                                                 '    sys.monitoring (CPython 3.12+): '
                                                 'without it the test fails, it never\n'
                                                 '    skips or passes (ruling FOUR-R11-A5 '
                                                 '(4)).')]}
for _k, _v in R11_COARSE_FROZEN.items():
    FROZEN[_k] = list(FROZEN.get(_k, [])) + list(_v)
COARSE_COUNT = 365
COMPLETE_COUNT = 218
# Hand edit at the round-9 merge (W30b; the ro child's question 1; reviewed
# in the round-9 notes): two dynamic forms the gr child's G2/G3 code adds,
# each reading an AST node's own field named by the field the walk stands in
# (closed_walk._index_path: `getattr(p, f)`, f from shape_grammar.visit) or
# by a literal tuple (test_a1_identity_formation, the queue_poll ends test:
# `getattr(blk, field, None)` over ("body", "orelse")). Neither reaches a
# module or an opener. 216 forms were derived at effc36c6; these two are
# frozen by hand, not by a re-derivation.
FROZEN.update(COMPLETE_FROZEN)

# Round 10 (ruling REHEARSAL-R9-A1 (C), refuse by default): the four round-10
# kinds of the complete layer (constructed, alias, wrapper, argdef; see
# ro_census), derived ONCE at the round-9 tip 0b317394 by
# RF/r10/ro/derive_r10.py from the census files of that tree: a judgement
# against the never-regenerated standard, recorded in the round-10 notes
# (child ro). COMPLETE_FROZEN and FROZEN above are unchanged; each key's
# round-10 forms join its complete layer. Never regenerated: a form the
# freeze lacks is refused until a reviewed edit freezes it here by hand.
R10_FROZEN = {'api/admin_evidence.py#complete': [],
 'api/auto_logs.py#complete': [],
 'api/build_manifest.py#complete': [],
 'api/card_evidence.py#complete': [],
 'api/card_measures.py#complete': [('constructed', '_FIELD[key](rec[key])')],
 'api/combat_evidence.py#complete': [],
 'api/combat_measures.py#complete': [('constructed',
                                      'cmeasure(name, subject, consts=consts, field=[sub, key, '
                                      'clock])(fn)')],
 'api/conn_ranges.py#complete': [],
 'api/database.py#complete': [('alias',
                               'from sqlalchemy.ext.asyncio import create_async_engine as '
                               '_sqlalchemy_create_async_engine'),
                              ('argdef', 'ASM_POOL_OVERFLOW <- ASM_POOL_OVERFLOW = 4'),
                              ('argdef', 'ASM_POOL_SIZE <- ASM_POOL_SIZE = 4'),
                              ('argdef', 'ASM_POOL_TIMEOUT_S <- ASM_POOL_TIMEOUT_S = 3'),
                              ('argdef',
                               "DATABASE_URL <- DATABASE_URL = os.getenv('DATABASE_URL', "
                               "'postgresql+asyncpg://comp_rounds:changeme@localhost:5432/competitive_rounds')"),
                              ('argdef', 'RELEASE_POOL_OVERFLOW <- RELEASE_POOL_OVERFLOW = 2'),
                              ('argdef', 'RELEASE_POOL_SIZE <- RELEASE_POOL_SIZE = 3'),
                              ('wrapper',
                               'def create_async_engine(url, **options):\n'
                               '    return _sqlalchemy_create_async_engine(url, '
                               'hide_parameters=True, **options)'),
                              ('wrapper',
                               'def make_asm_engine(url=DATABASE_URL, **connect_args):\n'
                               '    """An engine with the assembly pool\'s arguments. The api '
                               'builds exactly\n'
                               '    one (asm_engine); a test builds its own with the same '
                               'arguments against\n'
                               '    its database (extra connect_args, such as server_settings, '
                               'merge in)."""\n'
                               "    args = {'timeout': ASM_CONNECT_TIMEOUT_S}\n"
                               '    args.update(connect_args)\n'
                               '    return create_async_engine(url, echo=False, '
                               'pool_size=ASM_POOL_SIZE, max_overflow=ASM_POOL_OVERFLOW, '
                               'pool_timeout=ASM_POOL_TIMEOUT_S, pool_pre_ping=True, '
                               'pool_recycle=1800, connect_args=args)')],
 'api/flag_evidence.py#complete': [],
 'api/glicko2.py#complete': [],
 'api/identity_clock_evidence.py#complete': [],
 'api/identity_clock_measures.py#complete': [],
 'api/log_redaction.py#complete': [],
 'api/mail_discord.py#complete': [],
 'api/main.py#complete': [('alias', 'from sqlalchemy import and_, case, func, or_, select, text'),
                          ('alias', 'str __builtins__'),
                          ('alias', 'str __builtins__'),
                          ('alias', 'str __import__'),
                          ('alias', 'str eval'),
                          ('alias', 'str exec'),
                          ('alias', 'str globals'),
                          ('alias', 'str import_module'),
                          ('alias', 'str locals'),
                          ('alias', 'str setattr'),
                          ('alias', 'str setattr'),
                          ('alias', 'str vars'),
                          ('constructed', '_pc_motion_sessions()()'),
                          ('constructed', '_pc_motion_sessions()()'),
                          ('constructed',
                           "app.middleware('http')(_admin_evidence.evidence_key_gate)"),
                          ('wrapper',
                           "@app.websocket('/api/v1/ws/chat')\n"
                           'async def ws_chat(ws: WebSocket):\n'
                           '    """Mod <-> server chat channel. Messages are broadcast fan-out '
                           'style."""\n'
                           "    expected_internal_key = os.getenv('API_SECRET_KEY', '')\n"
                           '    is_internal = bool(expected_internal_key and '
                           "ws.headers.get('x-internal-key') == expected_internal_key)\n"
                           '    if not is_internal:\n'
                           "        sent = ws.headers.get('x-mod-version')\n"
                           '        if not sent and REQUIRE_MOD_VERSION:\n'
                           "            await ws.close(code=1008, reason='outdated')\n"
                           '            return\n'
                           '        if sent and _parse_version(sent) < '
                           '_parse_version(MIN_MOD_VERSION_EFFECTIVE):\n'
                           "            await ws.close(code=1008, reason='outdated')\n"
                           '            return\n'
                           '    if not _ws_chat_charge(ws):\n'
                           '        await ws.accept()\n'
                           "        await ws.close(code=1013, reason='rate_limited')\n"
                           '        return\n'
                           '    await chat_manager.connect(ws)\n'
                           "    print(f'[CHAT] subscriber connected "
                           "(total={chat_manager.count})')\n"
                           '    await read_gate.count_socket(ws)\n'
                           '    try:\n'
                           '        _locked_now = await _chat_lockdown_active()\n'
                           '        await ws.send_text(\'{"type":"lock","locked":\' + (\'1\' if '
                           "_locked_now else '0') + '}')\n"
                           '    except Exception:\n'
                           '        pass\n'
                           '    verified_sid: str | None = None\n'
                           '    try:\n'
                           '        while True:\n'
                           '            raw = await ws.receive_text()\n'
                           '            try:\n'
                           '                data = _json.loads(raw)\n'
                           '            except Exception:\n'
                           '                continue\n'
                           '            if not isinstance(data, dict):\n'
                           '                continue\n'
                           "            if data.get('type') == 'ping':\n"
                           '                continue\n'
                           "            if data.get('type') == 'auth':\n"
                           "                claim = str(data.get('steam_id', ''))[:20]\n"
                           "                token = str(data.get('token', ''))[:128]\n"
                           '                if claim and token and _ws_chat_charge(ws):\n'
                           '                    try:\n'
                           '                        from database import async_session\n'
                           '                        async with async_session() as _adb:\n'
                           "                            row = (await _adb.execute(text('SELECT "
                           'steam_id, verified, expires_at FROM steam_sessions WHERE token_hash = '
                           ":th'), {'th': "
                           'hashlib.sha256(token.encode()).hexdigest()})).mappings().first()\n'
                           "                        if row is not None and row['steam_id'] == "
                           "claim and bool(row['verified']) and (row['expires_at'] is None or "
                           "row['expires_at'] > datetime.now(timezone.utc)):\n"
                           '                            verified_sid = claim\n'
                           "                            print(f'[CHAT] socket authenticated as "
                           "{claim}')\n"
                           '                    except Exception as _aex:\n'
                           "                        print(f'[CHAT] ws auth check failed: {_aex}')\n"
                           '                continue\n'
                           "            if data.get('type') == 'subscribe':\n"
                           '                got = chat_manager.subscribe(ws, '
                           "data.get('channels'))\n"
                           "                print(f'[CHAT] subscriber channels -> {sorted(got)}')\n"
                           '                continue\n'
                           "            message = str(data.get('message', ''))[:500].strip()\n"
                           "            steam_id = str(data.get('steam_id', ''))[:20]\n"
                           "            display_name = str(data.get('display_name', ''))[:64]\n"
                           '            if not message or not steam_id:\n'
                           '                continue\n'
                           "            if _is_broadcast_account(verified_sid or '') or "
                           '_is_broadcast_account(steam_id):\n'
                           '                continue\n'
                           '            if await _chat_lockdown_active():\n'
                           '                try:\n'
                           '                    await '
                           'ws.send_text(\'{"type":"lock","locked":1}\')\n'
                           '                except Exception:\n'
                           '                    pass\n'
                           '                continue\n'
                           '            _presence_touch(steam_id)\n'
                           "            client_msg_id = str(data.get('client_msg_id', ''))[:64]\n"
                           '            if client_msg_id and (not _claim_chat_nonce(steam_id, '
                           'client_msg_id)):\n'
                           "                print(f'[CHAT] dropped resend (nonce "
                           "{client_msg_id[:12]}) from {display_name}')\n"
                           '                continue\n'
                           "            channel = str(data.get('channel', 'global')).lower()\n"
                           '            if channel not in CHAT_CHANNELS_ALLOWED:\n'
                           "                channel = 'global'\n"
                           '            if not _chat_spam_ok(id(ws), message):\n'
                           "                print(f'[CHAT] rate-limited {display_name} "
                           "({steam_id})')\n"
                           '                continue\n'
                           '            if not _ws_chat_charge(ws):\n'
                           "                print(f'[CHAT] address rate-limited {display_name} "
                           "({steam_id})')\n"
                           '                continue\n'
                           '            if await _is_banned_via_session(steam_id):\n'
                           '                continue\n'
                           '            if await _is_chat_muted(steam_id, channel):\n'
                           "                print(f'[CHAT-MOD] dropped muted {display_name} "
                           "({steam_id}) in [{channel}]')\n"
                           '                continue\n'
                           '            _hit = _chat_censor_hit(message)\n'
                           '            if _hit is not None:\n'
                           '                if verified_sid is not None and verified_sid == '
                           'steam_id:\n'
                           '                    minutes = await _chat_censor_strike(steam_id, '
                           "display_name, channel, message, _hit, 'ingame')\n"
                           '                    try:\n'
                           "                        await ws.send_text(_json.dumps({'type': "
                           "'muted', 'minutes': int(minutes or _CHAT_MUTE_BASE_MINUTES)}))\n"
                           '                    except Exception:\n'
                           '                        pass\n'
                           '                else:\n'
                           "                    print(f'[CHAT-MOD] censored UNVERIFIED socket "
                           "(claim={steam_id}) — dropped, no strike')\n"
                           '                continue\n'
                           '            meta = await _lookup_chat_meta(steam_id=steam_id)\n'
                           "            out = {'source': 'ingame', 'steam_id': steam_id, "
                           "'display_name': display_name, 'rating': meta['rating'], 'title': "
                           "meta['title'], 'title_color': meta['title_color'], 'message': message, "
                           "'channel': channel}\n"
                           '            mid, created_iso = await _persist_chat(out, '
                           'author_verified=verified_sid is not None and verified_sid == '
                           'steam_id)\n'
                           "            out['timestamp'] = created_iso or "
                           'datetime.now(timezone.utc).isoformat()\n'
                           '            if mid is not None:\n'
                           "                out['id'] = mid\n"
                           '            print(f"[CHAT] <- ingame '
                           '{display_name}({meta[\'rating\']}) [{channel}]: {message[:80]}")\n'
                           '            await chat_manager.broadcast(out, exclude=ws, '
                           'channel=channel)\n'
                           '    except WebSocketDisconnect:\n'
                           "        print(f'[CHAT] subscriber disconnected')\n"
                           '        chat_manager.disconnect(ws)\n'
                           '    except Exception as e:\n'
                           "        print(f'[CHAT] WS error: {e}')\n"
                           '        chat_manager.disconnect(ws)')],
 'api/match_hold.py#complete': [('alias', 'str vars')],
 'api/match_report_window.py#complete': [],
 'api/models.py#complete': [],
 'api/pc_face.py#complete': [],
 'api/pc_motion.py#complete': [],
 'api/pc_portrait.py#complete': [],
 'api/pc_signature.py#complete': [],
 'api/pc_steam.py#complete': [],
 'api/pc_strip.py#complete': [],
 'api/player_cards.py#complete': [],
 'api/read_gate.py#complete': [],
 'api/region_pick.py#complete': [],
 'api/review_boot.py#complete': [('alias', 'str exec')],
 'api/review_measures.py#complete': [],
 'api/review_rules.py#complete': [('constructed', 'core.impl[0](self, records, budget)'),
                                  ('constructed', 'core.impl[0](self, records, regs, budget)'),
                                  ('constructed', 'entry.impl[-1](self, case, budget)'),
                                  ('constructed', 'entry.impl[0](*vals)'),
                                  ('constructed', 'entry.impl[0](args, _bound_lookup(refs), mode)'),
                                  ('constructed', 'entry.impl[0](out, _bound_lookup(refs), mode)'),
                                  ('constructed', 'entry.impl[0](self, subjects, budget)'),
                                  ('constructed', 'm.impl[0](ctx, fam)'),
                                  ('constructed',
                                   "self.core['core.game'].impl[-1](self, cases, deadline)"),
                                  ('constructed',
                                   "self.core['core.game'].impl[0](self, records, match, registry, "
                                   'budget)'),
                                  ('constructed', "self.core['core.render'].impl[0](rule, items)"),
                                  ('constructed', "self.core['core.sitting'].impl[-1](self)"),
                                  ('constructed', "self.core['core.sitting'].impl[0](rule, rows)"),
                                  ('constructed', "self.core['core.sitting'].impl[1](rule, mode)"),
                                  ('constructed',
                                   'self.core[COMBAT_CORE].impl[-1](self, cases, deadline)'),
                                  ('constructed',
                                   'self.core[IDENTITY_CORE].impl[-1](self, cases, deadline)')],
 'api/schemas.py#complete': [],
 'api/seat_evidence.py#complete': [],
 'api/steamid64.py#complete': [],
 'api/title_ladders.py#complete': [('constructed', '_CONDITIONS[kind](row)')],
 'api/tournament_bracket.py#complete': [],
 'api/tournaments.py#complete': [],
 'tests/cf_pg.py#complete': [('argdef',
                              'DSN <- DSN = (os.environ.get(DSN_VAR) or '
                              "'').replace('postgresql+asyncpg://', 'postgresql://')"),
                             ('wrapper',
                              '@contextlib.asynccontextmanager\n'
                              "async def case(prefix='cf', *, with_355=True, dsn=None, "
                              'faithful=False):\n'
                              '    """A built case schema; yields (case, sessionmaker). The case '
                              'seals its\n'
                              '    schema through `await c.seal()` before the first handler call '
                              'when it\n'
                              '    runs DDL of its own; otherwise the context seals it on entry. '
                              '`dsn`\n'
                              '    names another database on the same server (fresh_database). A '
                              'case\n'
                              '    with 355 applied and no dsn of its own comes from cf_pool when '
                              'POOL is\n'
                              '    on; a case that applies 355 itself always builds its own '
                              'schema."""\n'
                              '    if POOL and with_355 and (dsn is None):\n'
                              '        import cf_pool\n'
                              '        async with cf_pool.checkout(faithful=faithful) as got:\n'
                              '            yield got\n'
                              '        return\n'
                              '    async with harness.CaseSchema(dsn or DSN, prefix) as c:\n'
                              '        await build(c, with_355=with_355, dsn=dsn, '
                              'faithful=faithful)\n'
                              '        if with_355:\n'
                              '            await c.seal()\n'
                              '        engine = harness.bound_engine(dsn or DSN, c.schema)\n'
                              '        try:\n'
                              '            yield (c, async_sessionmaker(engine, '
                              'expire_on_commit=False))\n'
                              '        finally:\n'
                              '            await engine.dispose()'),
                             ('wrapper',
                              'async def build(case, *, with_355=True, dsn=None, faithful=False):\n'
                              '    """Into case.schema, on case.conn: replay, ORM, widen, replay, '
                              '331, 365,\n'
                              '    and 355 when asked. Not sealed: the caller seals after its own '
                              'DDL.\n'
                              '\n'
                              '    faithful=True replays every statement ONCE where it can run: '
                              'the second\n'
                              '    pass re-runs only the statements the first pass refused (the '
                              'ones that\n'
                              '    alter tables only the ORM makes). The default second pass '
                              're-runs them\n'
                              '    all, which re-adds a column a later migration renamed away '
                              "(208's\n"
                              "    live_top_points after 209's rename) -- harmless to a handler, "
                              'wrong for\n'
                              '    a check that reads the table\'s column list."""\n'
                              '    conn, schema = (case.conn, case.schema)\n'
                              '    statements = ddl_statements()\n'
                              '    refused = await _replay_refused(conn, statements) if faithful '
                              'else await lh._replay(conn, statements)\n'
                              '    engine = harness.bound_engine(dsn or DSN, schema)\n'
                              '    try:\n'
                              '        async with engine.begin() as c:\n'
                              '            await c.run_sync(models.Base.metadata.create_all)\n'
                              '    finally:\n'
                              '        await engine.dispose()\n'
                              '    await lh._widen(conn, schema)\n'
                              '    if faithful:\n'
                              '        for _ in range(3):\n'
                              '            if not refused:\n'
                              '                break\n'
                              '            refused = await _replay_refused(conn, refused)\n'
                              '    else:\n'
                              '        second = await lh._replay(conn, statements)\n'
                              '        unexpected = [f for f in second if f[1] not in lh._ALREADY '
                              'and (f[0], f[1]) not in lh.REPLAY_KNOWN]\n'
                              "        assert not unexpected, 'the second DDL pass failed on "
                              "statements outside REPLAY_KNOWN: %r' % unexpected[:5]\n"
                              "    await conn.execute(io.open(M331, encoding='utf-8').read())\n"
                              "    await conn.execute(io.open(M365, encoding='utf-8').read())\n"
                              '    if with_355:\n'
                              '        await apply_355(conn)\n'
                              '        await apply_378(conn)')],
 'tests/cf_pool.py#complete': [('argdef',
                                'cf_pg <- await cf_pg.build(types.SimpleNamespace(conn=conn, '
                                'schema=schema), with_355=True, dsn=dsn, faithful=faithful)'),
                               ('argdef', 'cf_pg <- import cf_pg'),
                               ('wrapper',
                                '@contextlib.asynccontextmanager\n'
                                'async def checkout(faithful=False):\n'
                                '    """A pristine, positively registered schema for one case."""\n'
                                '    dsn = await _faithful_dsn() if faithful else cf_pg.DSN\n'
                                '    key = build_key(faithful)\n'
                                '    meta = await asyncpg.connect(dsn)\n'
                                '    try:\n'
                                "        _phase('pool_lock', 'start')\n"
                                "        await meta.execute('SELECT pg_advisory_lock($1)', "
                                'LOCK_KEY)\n'
                                "        _phase('pool_lock', 'end')\n"
                                '        await _ensure_meta(meta)\n'
                                '        state = await _owner(meta)\n'
                                "        owner = state['owner']\n"
                                "        if state['unverified'] and "
                                "os.environ.get('CF_POOL_ACTIVE_TOKEN') != state['active_token']:\n"
                                "            raise harness.CensusRefusal('registry database is "
                                "unverified')\n"
                                "        row = await meta.fetchrow('SELECT key, schema_name, "
                                "pristine, owner FROM %s.entries WHERE key=$1' % META, key)\n"
                                '        schema = pristine = None\n'
                                '        if row is not None:\n'
                                "            if row['owner'] != owner:\n"
                                "                raise harness.CensusRefusal('pool schema belongs "
                                "to another run')\n"
                                "            schema, pristine = (row['schema_name'], "
                                "json.loads(row['pristine']))\n"
                                '            if pristine is None:\n'
                                '                await _drop_registered(meta, dsn, row, owner)\n'
                                '                schema = None\n'
                                '            else:\n'
                                '                conn = await harness.connect_bound(dsn, schema)\n'
                                '                try:\n'
                                "                    _phase('reset', 'start', schema=schema)\n"
                                '                    why = await reset(conn, schema, pristine)\n'
                                "                    _phase('reset', 'end', schema=schema, "
                                'pristine=why is None)\n'
                                '                except Exception as exc:\n'
                                "                    why = 'reset raised %s' % type(exc).__name__\n"
                                '                finally:\n'
                                '                    await conn.close()\n'
                                '                if why is not None:\n'
                                "                    _log('retire %s key=%s: %s' % (schema, key, "
                                'why))\n'
                                '                    await _drop_registered(meta, dsn, row, '
                                'owner)\n'
                                '                    schema = pristine = None\n'
                                '        if schema is None:\n'
                                "            for old in await meta.fetch('SELECT key, schema_name, "
                                "pristine, owner FROM %s.entries WHERE key<>$1' % META, key):\n"
                                '                await _drop_registered(meta, dsn, old, owner)\n'
                                '            schema, pristine = await _build(dsn, faithful, key, '
                                'owner)\n'
                                "            _log('built %s key=%s' % (schema, key))\n"
                                "            _phase('registration_complete', 'start', "
                                'schema=schema)\n'
                                "            await meta.execute('UPDATE %s.entries SET pristine=$1 "
                                "WHERE key=$2 AND schema_name=$3 AND owner=$4' % META, "
                                'json.dumps(pristine, sort_keys=True), key, schema, owner)\n'
                                "            _phase('registration_complete', 'end', "
                                'schema=schema)\n'
                                "        await meta.execute('UPDATE %s.entries SET used_at=now(), "
                                "uses=uses+1 WHERE key=$1' % META, key)\n"
                                "        c = PoolCase(dsn, schema, pristine['own'])\n"
                                '        await c.open()\n'
                                '        engine = harness.bound_engine(dsn, schema)\n'
                                '        try:\n'
                                "            _phase('case', 'start', schema=schema)\n"
                                '            yield (c, async_sessionmaker(engine, '
                                'expire_on_commit=False))\n'
                                '        finally:\n'
                                "            _phase('case', 'end', schema=schema)\n"
                                "            _phase('case_cleanup', 'start', schema=schema)\n"
                                '            await engine.dispose()\n'
                                '            await c.close()\n'
                                '            if c.declared:\n'
                                '                why = await _drop_declared(dsn, schema, '
                                'c.declared)\n'
                                '                if why is None:\n'
                                "                    _log('dropped declared %s' % schema)\n"
                                '                else:\n'
                                "                    row = await meta.fetchrow('SELECT key, "
                                "schema_name, pristine, owner FROM %s.entries WHERE key=$1' % "
                                'META, key)\n'
                                '                    await _drop_registered(meta, dsn, row, owner, '
                                'sorted(c.own | c.declared))\n'
                                "            _phase('case_cleanup', 'end', schema=schema)\n"
                                '    finally:\n'
                                '        await meta.close()'),
                               ('wrapper',
                                'async def _build(dsn, faithful, key, owner):\n'
                                '    """A new pool schema: the harness\'s create-under-census, the '
                                'build, the\n'
                                '    outside census, the pristine record."""\n'
                                '    import types\n'
                                "    schema = harness.case_schema('cfpool')\n"
                                '    conn = await harness.connect_bound(dsn, schema)\n'
                                '    created = False\n'
                                '    try:\n'
                                '        others = [r[0] for r in await conn.fetch("SELECT '
                                'n.nspname::text FROM pg_catalog.pg_class c JOIN '
                                'pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE '
                                'c.relname = \'ffa_lobbies\' AND c.relkind = \'r\'")]\n'
                                '        if others:\n'
                                "            raise harness.CensusRefusal('refusing to build %s: "
                                "schema(s) %r already hold ffa_lobbies in this database' % "
                                '(schema, others))\n'
                                "        _phase('reserve', 'start', schema=schema)\n"
                                '        async with conn.transaction():\n'
                                '            await conn.execute("INSERT INTO %s.entries (key, '
                                'schema_name, pristine, owner) VALUES ($1, $2, \'null\', $3)" % '
                                'META, key, schema, owner)\n'
                                '            await harness.create_case_schema(conn, schema)\n'
                                '        created = True\n'
                                "        _phase('reserve', 'end', schema=schema)\n"
                                "        _phase('build', 'start', schema=schema)\n"
                                '        outside = await harness.outside_objects(conn, schema)\n'
                                '        await cf_pg.build(types.SimpleNamespace(conn=conn, '
                                'schema=schema), with_355=True, dsn=dsn, faithful=faithful)\n'
                                '        after = await harness.outside_objects(conn, schema)\n'
                                '        if after != outside:\n'
                                '            changed = sorted(set(after) ^ set(outside))\n'
                                "            raise harness.CensusRefusal('the build of %s changed "
                                "%d object(s) outside it: %r' % (schema, len(changed), "
                                'changed[:5]))\n'
                                "        _phase('capture', 'start', schema=schema)\n"
                                '        pristine = await capture(conn, schema)\n'
                                "        _phase('capture', 'end', schema=schema)\n"
                                "        _phase('build', 'end', schema=schema)\n"
                                '    except BaseException:\n'
                                '        if created:\n'
                                '            try:\n'
                                '                await harness.drop_case_schema(conn, schema, '
                                'None)\n'
                                '                assert not await conn.fetchval(_NSP, schema), '
                                "'owned failed build remains'\n"
                                "                await conn.execute('DELETE FROM %s.entries WHERE "
                                "key=$1 AND schema_name=$2 AND owner=$3' % META, key, schema, "
                                'owner)\n'
                                '            finally:\n'
                                '                await conn.close()\n'
                                '        else:\n'
                                '            await conn.close()\n'
                                '        raise\n'
                                '    await conn.close()\n'
                                '    return (schema, pristine)'),
                               ('wrapper',
                                'async def _drop(dsn, schema, own):\n'
                                '    conn = await harness.connect_bound(dsn, schema)\n'
                                '    try:\n'
                                '        await harness.drop_case_schema(conn, schema, None if own '
                                'is None else {tuple(x) for x in own})\n'
                                '    finally:\n'
                                '        await conn.close()'),
                               ('wrapper',
                                'async def _drop_declared(dsn, schema, declared):\n'
                                '    """Drop the objects a case declared through seal(), relations '
                                'first\n'
                                '    (their row types go with them), then routines (CASCADE takes '
                                'a trigger\n'
                                '    that calls one). Returns None when none of them is left, else '
                                'why."""\n'
                                '    conn = await harness.connect_bound(dsn, schema)\n'
                                '    try:\n'
                                '        await conn.execute("SET lock_timeout = \'10s\'")\n'
                                '        order = sorted(declared, key=lambda kn: (kn[0] == '
                                "'routine', kn[0] == 'type', kn))\n"
                                '        for kind, name in order:\n'
                                '            what = _DECLARED_DROP.get(kind)\n'
                                '            if what is None:\n'
                                '                continue\n'
                                "            if kind == 'routine':\n"
                                "                fname, _, args = name.partition('(')\n"
                                "                target = '%s(%s' % (_q(fname), args)\n"
                                '            else:\n'
                                '                target = _q(name)\n'
                                "            await conn.execute('DROP %s IF EXISTS %s.%s CASCADE' "
                                '% (what, _q(schema), target))\n'
                                '        left = {tuple(x) for x in await '
                                'harness.schema_objects(conn, schema)} & set(declared)\n'
                                "        return None if not left else 'declared object(s) left: "
                                "%r' % sorted(left)[:5]\n"
                                '    except Exception as exc:\n'
                                "        return 'dropping the declared objects raised %r' % "
                                '(exc,)\n'
                                '    finally:\n'
                                '        await conn.close()'),
                               ('wrapper',
                                'async def open(self):\n'
                                '    self.conn = await harness.connect_bound(self.dsn, '
                                'self.schema)\n'
                                '    self._outside = await harness.outside_objects(self.conn, '
                                'self.schema)'),
                               ('wrapper',
                                'async def registry_database(dsn, *, action, pooled=True, '
                                "reason='', active_token=None):\n"
                                '    """Persist in-flight ownership; recover only this run\'s '
                                'exact registrations.\n'
                                '\n'
                                '    A timed-out triage child needs explicit database recreation: '
                                'public triage\n'
                                '    tables are outside the positively registered pool resources.\n'
                                '    """\n'
                                "    dsn = dsn.replace('postgresql+asyncpg://', 'postgresql://')\n"
                                '    meta = await asyncpg.connect(dsn, timeout=10, '
                                'command_timeout=15)\n'
                                '    try:\n'
                                '        await _ensure_meta(meta)\n'
                                '        state = await _owner(meta)\n'
                                "        owner = state['owner']\n"
                                "        if not await meta.fetchval('SELECT "
                                "pg_try_advisory_lock($1)', LOCK_KEY):\n"
                                "            raise harness.CensusRefusal('pool is still owned by a "
                                "live connection')\n"
                                '        gone_deadline = time.monotonic() + 5\n'
                                '        while True:\n'
                                '            sessions = await meta.fetchval("SELECT count(*) FROM '
                                'pg_catalog.pg_stat_activity WHERE datname=current_database() AND '
                                'pid<>pg_backend_pid() AND backend_type=\'client backend\'")\n'
                                '            if not sessions:\n'
                                '                break\n'
                                '            if time.monotonic() >= gone_deadline:\n'
                                "                raise harness.CensusRefusal('lane database still "
                                "has client connections')\n"
                                '            await asyncio.sleep(0.05)\n'
                                "        rows = await meta.fetch('SELECT key, schema_name, "
                                "pristine, owner FROM %s.entries ORDER BY key' % META)\n"
                                "        if any((r['owner'] != owner or not "
                                "re.fullmatch('cfpool_[0-9a-f]{10}', r['schema_name']) for r in "
                                'rows)):\n'
                                "            raise harness.CensusRefusal('lane has pool "
                                "registrations not owned by this run')\n"
                                '        recovered = []\n'
                                "        if action == 'begin' and state['unverified']:\n"
                                '            if not pooled:\n'
                                "                raise harness.CensusRefusal('triage timeout "
                                "requires verified database recreation')\n"
                                '            for row in rows:\n'
                                '                await _drop_registered(meta, dsn, row, owner)\n'
                                "                recovered.append(row['schema_name'])\n"
                                '            rows = []\n'
                                '        if pooled:\n'
                                '            app_schemas = await meta.fetch("SELECT DISTINCT '
                                'n.nspname::text FROM pg_catalog.pg_class c JOIN '
                                'pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE '
                                'c.relname=\'ffa_lobbies\' AND c.relkind=\'r\'")\n'
                                '            app_schemas = {r[0] for r in app_schemas}\n'
                                "            registered = {r['schema_name'] for r in rows}\n"
                                '            if app_schemas - registered:\n'
                                "                raise harness.CensusRefusal('unregistered "
                                "application schema prevents reuse')\n"
                                "            if any((json.loads(r['pristine']) is None for r in "
                                'rows)):\n'
                                "                raise harness.CensusRefusal('incomplete pool "
                                "build prevents reuse')\n"
                                "        if action == 'begin':\n"
                                '            token = uuid.uuid4().hex\n'
                                "            await meta.execute('UPDATE %s.registry_state SET "
                                "unverified=true, active_token=$1, reason=$2 WHERE singleton' % "
                                'META, token, reason)\n'
                                "            return {'owner': owner, 'active_token': token, "
                                "'recovered': recovered, 'verified': True, 'client_connections': "
                                '0}\n'
                                "        if action != 'finish' or state['active_token'] != "
                                'active_token:\n'
                                "            raise harness.CensusRefusal('registry completion "
                                "token does not own this child')\n"
                                '        await meta.execute("UPDATE %s.registry_state SET '
                                'unverified=false, active_token=NULL, reason=\'\' WHERE singleton" '
                                '% META)\n'
                                "        return {'owner': owner, 'verified': True, "
                                "'client_connections': 0}\n"
                                '    finally:\n'
                                '        await meta.close()'),
                               ('wrapper',
                                'async def require_registry_verified(dsn):\n'
                                '    """Read-only refusal control: no child may bypass persisted '
                                'quarantine."""\n'
                                '    meta = await asyncpg.connect(dsn, timeout=10, '
                                'command_timeout=10)\n'
                                '    try:\n'
                                "        row = await meta.fetchrow('SELECT unverified FROM "
                                "%s.registry_state WHERE singleton' % META)\n"
                                "        if row is None or row['unverified']:\n"
                                "            raise harness.CensusRefusal('registry database is "
                                "unverified')\n"
                                '    finally:\n'
                                '        await meta.close()')],
 'tests/closed_walk.py#complete': [('alias', 'str getattr'), ('alias', 'str hasattr')],
 'tests/ladder_pg_harness.py#complete': [('alias',
                                          'from sqlalchemy.ext.asyncio import create_async_engine'),
                                         ('argdef',
                                          'NullPool <- from sqlalchemy.pool import NullPool'),
                                         ('argdef',
                                          'async_dsn <- def async_dsn(dsn):\n'
                                          "    return dsn.replace('postgresql://', "
                                          "'postgresql+asyncpg://')"),
                                         ('argdef',
                                          'quoted <- def quoted(schema):\n'
                                          "    if not (schema.replace('_', '').isalnum() and "
                                          'schema == schema.lower()):\n'
                                          "        raise CensusRefusal('not a harness schema name: "
                                          "%r' % schema)\n"
                                          '    return \'"%s"\' % schema'),
                                         ('wrapper',
                                          'async def __aenter__(self):\n'
                                          '    self.conn = await connect_bound(self.dsn, '
                                          'self.schema)\n'
                                          '    try:\n'
                                          '        await create_case_schema(self.conn, '
                                          'self.schema)\n'
                                          '        self._created = True\n'
                                          '        self._outside = await '
                                          'outside_objects(self.conn, self.schema)\n'
                                          '    except BaseException:\n'
                                          '        try:\n'
                                          '            if self._created:\n'
                                          '                await drop_case_schema(self.conn, '
                                          'self.schema, None)\n'
                                          '        finally:\n'
                                          '            await self.conn.close()\n'
                                          '        raise\n'
                                          '    return self'),
                                         ('wrapper',
                                          'async def connect_bound(dsn, schema):\n'
                                          '    """An asyncpg connection whose search_path is '
                                          '`schema` alone."""\n'
                                          '    return await '
                                          "_asyncpg.connect(dsn.replace('postgresql+asyncpg://', "
                                          "'postgresql://'), server_settings={'search_path': "
                                          'quoted(schema)})'),
                                         ('wrapper',
                                          'def bound_engine(dsn, schema):\n'
                                          '    """A SQLAlchemy async engine whose every connection '
                                          'has search_path\n'
                                          '    `schema` alone; NullPool, so no connection outlives '
                                          'its use."""\n'
                                          '    return create_async_engine(async_dsn(dsn), '
                                          "poolclass=NullPool, connect_args={'server_settings': "
                                          "{'search_path': quoted(schema)}})")],
 'tests/migration_table_ddl.py#complete': [],
 'tests/pc_themes_data.py#complete': [],
 'tests/resolution_sites.py#complete': [('alias', 'str __import__'),
                                        ('alias', 'str __import__'),
                                        ('alias', 'str getattr'),
                                        ('alias', 'str getattr'),
                                        ('alias', 'str getattr'),
                                        ('alias', 'str getattr'),
                                        ('alias', 'str hasattr'),
                                        ('alias', 'str hasattr'),
                                        ('alias', 'str import_module'),
                                        ('alias', 'str import_module')],
 'tests/test_a1_formation_concurrency.py#complete': [('alias',
                                                      'from sqlalchemy.ext.asyncio import '
                                                      'async_sessionmaker, create_async_engine'),
                                                     ('argdef',
                                                      'DSN <- DSN = '
                                                      "os.environ.get('A1_TEST_PG_DSN')")],
 'tests/test_a1_identity_formation.py#complete': [('alias', 'str __builtins__'),
                                                  ('alias', 'str eval'),
                                                  ('alias', 'str exec'),
                                                  ('alias', 'str exec'),
                                                  ('alias', 'str exec'),
                                                  ('alias', 'str exec'),
                                                  ('alias', 'str exec'),
                                                  ('alias', 'str setattr'),
                                                  ('constructed',
                                                   'getattr(_cw, _ACC)(object(), _ast.Constant(1), '
                                                   '())'),
                                                  ('constructed',
                                                   "type('_orig', (Exception,), {'sqlstate': "
                                                   'self.sqlstate})()')],
 'tests/test_a1_predicate_sql.py#complete': [('alias',
                                              'from sqlalchemy.ext.asyncio import '
                                              'async_sessionmaker, create_async_engine'),
                                             ('argdef',
                                              "DSN <- DSN = os.environ.get('A1_TEST_PG_DSN')")],
 'tests/test_match_hold_admission_gate_pg.py#complete': [('alias', 'str exec'),
                                                         ('alias', 'str exec')],
 'tests/test_match_hold_pg.py#complete': [('wrapper',
                                           'async def _concurrent_opens(env, series_rows, calls):\n'
                                           '    """Hold the series rows until both request '
                                           'backends join the blocking chain.\n'
                                           '\n'
                                           '    Observe both contenders, including a contender '
                                           'queued on the earlier\n'
                                           '    identity advisory guard. Release the series locks '
                                           'before collecting\n'
                                           '    responses, and close every task on a failed '
                                           'observation or request.\n'
                                           '    """\n'
                                           '    blocker = await '
                                           'cf_pg.harness.connect_bound(env.c.dsn, env.c.schema)\n'
                                           '    transaction = blocker.transaction()\n'
                                           '    tasks = []\n'
                                           '    try:\n'
                                           '        await transaction.start()\n'
                                           '        try:\n'
                                           '            for sid in series_rows:\n'
                                           "                await blocker.execute('SELECT 1 FROM "
                                           "team_series WHERE id = $1 FOR NO KEY UPDATE', sid)\n"
                                           '            tasks = [asyncio.ensure_future(c) for c in '
                                           'calls]\n'
                                           '            observed = await _lock_waiters(env, '
                                           'blocker.get_server_pid(), len(tasks))\n'
                                           '            assert len(observed) == len(set(observed)) '
                                           "== len(tasks) == 2, ('FIX2 M2 both contenders', "
                                           'observed, len(tasks))\n'
                                           '        finally:\n'
                                           '            await transaction.rollback()\n'
                                           '        return await asyncio.gather(*tasks)\n'
                                           '    finally:\n'
                                           '        try:\n'
                                           '            await blocker.close()\n'
                                           '        finally:\n'
                                           '            for task in tasks:\n'
                                           '                if not task.done():\n'
                                           '                    task.cancel()\n'
                                           '            if tasks:\n'
                                           '                await asyncio.gather(*tasks, '
                                           'return_exceptions=True)'),
                                          ('wrapper',
                                           'async def body(env):\n'
                                           '    from sqlalchemy import text\n'
                                           '    async with env.sm() as clock_db:\n'
                                           '        transaction_at = (await '
                                           "clock_db.execute(text('SELECT now()'))).scalar()\n"
                                           "        await clock_db.execute(text('SELECT "
                                           "pg_sleep(0.05)'))\n"
                                           '        lower = await dbclock(env)\n'
                                           '        observed = await '
                                           'match_hold._ctx_now(clock_db)\n'
                                           '        upper = await dbclock(env)\n'
                                           '        assert transaction_at < lower <= observed <= '
                                           "upper, ('FIX3 M2 context clock follows PostgreSQL "
                                           "wait', transaction_at, lower, observed, upper)\n"
                                           '        await clock_db.rollback()\n'
                                           '    s, g, pres = await opened_series(env)\n'
                                           '    await env.conn.execute("INSERT INTO queue_leases '
                                           '(player_id, mode, group_id, generation, acquired_at,  '
                                           "renewed_at, expires_at) VALUES ($1, 'team', $2, "
                                           'gen_random_uuid(),  clock_timestamp(), '
                                           "clock_timestamp(), clock_timestamp() + interval '10 "
                                           'minutes\')", s.pid(1), s.sid)\n'
                                           '    blk = await cf_pg.harness.connect_bound(env.c.dsn, '
                                           'env.c.schema)\n'
                                           '    tr = blk.transaction()\n'
                                           '    await tr.start()\n'
                                           "    await blk.execute('SELECT 1 FROM team_series WHERE "
                                           "id = $1 FOR NO KEY UPDATE', s.sid)\n"
                                           '    t0 = await dbclock(env)\n'
                                           '    task = asyncio.ensure_future(open_hold(env, s, 1, '
                                           "0, g, rid='req-first-open'))\n"
                                           '    await asyncio.sleep(2.0)\n'
                                           "    released = await blk.fetchval('SELECT "
                                           "clock_timestamp()')\n"
                                           '    await tr.rollback()\n'
                                           '    await blk.close()\n'
                                           '    r = await task\n'
                                           '    t1 = await dbclock(env)\n'
                                           '    out = r.json()\n'
                                           "    assert (r.status_code, out['status'], "
                                           "out['repeat']) == (200, 'opened', False), out\n"
                                           "    h = await hold_db(env, out['hold_id'])\n"
                                           "    assert h['held_anchor_at'] == pres, "
                                           "(h['held_anchor_at'], pres)\n"
                                           "    assert h['held_until'] == pres + "
                                           'timedelta(seconds=120)\n'
                                           "    assert released <= h['held_at'] <= t1 and t0 <= "
                                           "h['held_at'], (released, h['held_at'])\n"
                                           "    assert (h['n'], h['slot'], h['team'], h['seq'], "
                                           "h['closed_at']) == (1, 1, 0, 0, None)\n"
                                           "    assert h['opener_player_id'] == s.pid(0) and "
                                           "h['game_id'] == uuid.UUID(g)\n"
                                           "    assert 85 <= out['deadline_s'] <= 90, out\n"
                                           "    assert await env.conn.fetchval('SELECT count(*) "
                                           "FROM queue_leases WHERE player_id = $1', s.pid(1)) == "
                                           '0\n'
                                           '    rep = (await open_hold(env, s, 1, 2, g)).json()\n'
                                           "    assert (rep['status'], rep['repeat'], "
                                           "rep['hold_id']) == ('opened', True, out['hold_id'])\n"
                                           "    assert await env.conn.fetchval('SELECT count(*) "
                                           "FROM match_seat_holds WHERE room_name = $1', s.room) "
                                           '== 1\n'
                                           '    assert await sweep(env) == {}\n'
                                           '    assert (await hold_db(env, '
                                           "out['hold_id']))['held_until'] == h['held_until']\n"
                                           "    await shift_hold(env, out['hold_id'], 200)\n"
                                           '    lapsed_until = (await hold_db(env, '
                                           "out['hold_id']))['held_until']\n"
                                           '    late = (await open_hold(env, s, 1, 2, g)).json()\n'
                                           "    assert (late['status'], late['reason']) == "
                                           "('refused', 'duplicate_game'), late\n"
                                           "    hh = await hold_db(env, out['hold_id'])\n"
                                           "    assert (hh['held_until'], hh['closed_at'], "
                                           "hh['closed_reason']) == (lapsed_until, lapsed_until, "
                                           "'lapsed')\n"
                                           '    assert await sweep(env) == {}\n'
                                           '\n'
                                           '    async def refusal(r):\n'
                                           '        assert r.status_code == 200, r.text\n'
                                           '        j = r.json()\n'
                                           "        assert 'status' in j and j['status'] == "
                                           "'refused', ('FIX3 M2.6 open must refuse', j)\n"
                                           "        assert 'reason' in j, ('FIX3 M2.6 refusal "
                                           "names reason', j)\n"
                                           "        return j['reason']\n"
                                           '    assert await refusal(await open_hold(env, s, 1, 0, '
                                           "g)) == 'duplicate_game'\n"
                                           '    busy, gb, _ = await opened_series(env)\n'
                                           '    assert (await open_hold(env, busy, 1, 0, '
                                           "gb)).json()['status'] == 'opened'\n"
                                           '    await beat(env, busy, 2)\n'
                                           '    assert await refusal(await open_hold(env, busy, 2, '
                                           "0, gb)) == 'room_busy'\n"
                                           '    nm, gn, _ = await opened_series(env)\n'
                                           '    stranger = (await seed_players(env.conn, 1))[0]\n'
                                           '    assert await refusal(await open_hold(env, nm, 1, '
                                           "0, gn, held_steam_id=stranger[1])) == 'not_member'\n"
                                           '    assert await refusal(await open_hold(env, nm, 1, '
                                           "1, gn)) == 'not_member'\n"
                                           '    assert await refusal(await open_hold(env, nm, 1, '
                                           "0, gn, team=1)) == 'not_member'\n"
                                           '    assert await refusal(await open_hold(env, nm, 1, '
                                           "0, gn, slot=3)) == 'not_member'\n"
                                           "    cl, gc, _ = await opened_series(env, 'ovt')\n"
                                           '    await env.conn.execute("UPDATE ovt_series SET '
                                           'status = \'completed\' WHERE id = $1", cl.sid)\n'
                                           '    assert await refusal(await open_hold(env, cl, 1, '
                                           "0, gc)) == 'series_closed'\n"
                                           '    nf, gf, _ = await opened_series(env)\n'
                                           '    await env.conn.execute("UPDATE team_series SET '
                                           'hold_room = \'elsewhere\' WHERE id = $1", nf.sid)\n'
                                           '    assert await refusal(await open_hold(env, nf, 1, '
                                           "0, gf)) == 'not_flagged'\n"
                                           '    nc, g1, _ = await opened_series(env)\n'
                                           '    await game_start(env, nc, 0, prev=g1)\n'
                                           '    assert await refusal(await open_hold(env, nc, 1, '
                                           "0, g1)) == 'not_current_game'\n"
                                           '    assert await refusal(await open_hold(env, nc, 1, '
                                           "0, uuid.uuid4())) == 'not_current_game'\n"
                                           "    npz = await seed_series(env.conn, 'ovt')\n"
                                           "    gp = (await game_start(env, npz, 0))['game_id']\n"
                                           '    assert await refusal(await open_hold(env, npz, 2, '
                                           "0, gp)) == 'no_presence'\n"
                                           '    ws, gw, _ = await opened_series(env, back=110)\n'
                                           '    assert await refusal(await open_hold(env, ws, 1, '
                                           "0, gw)) == 'window_spent'\n"
                                           '    bad = await open_hold(env, ws, 1, 0, gw, '
                                           'sign=False)\n'
                                           '    assert bad.status_code == 403\n'
                                           "    assert await env.conn.fetchval('SELECT count(*) "
                                           'FROM match_seat_holds WHERE room_name = '
                                           "ANY($1::text[])', [nm.room, cl.room, nf.room, nc.room, "
                                           'npz.room, ws.room]) == 0'),
                                          ('wrapper',
                                           'async def body(env):\n'
                                           '    s, g, _ = await opened_series(env)\n'
                                           '    await env.conn.execute("INSERT INTO queue_leases '
                                           '(player_id, mode, group_id, generation, acquired_at, '
                                           "renewed_at, expires_at) VALUES ($1, 'team', $2, "
                                           'gen_random_uuid(), clock_timestamp(), '
                                           "clock_timestamp(), clock_timestamp() + interval '10 "
                                           'minutes\')", s.pid(1), s.sid)\n'
                                           '    blocker = await '
                                           'cf_pg.harness.connect_bound(env.c.dsn, env.c.schema)\n'
                                           '    transaction = blocker.transaction()\n'
                                           '    await transaction.start()\n'
                                           "    await blocker.execute('SELECT 1 FROM team_series "
                                           "WHERE id = $1 FOR NO KEY UPDATE', s.sid)\n"
                                           '    started = asyncio.get_running_loop().time()\n'
                                           '    try:\n'
                                           '        response = await open_hold(env, s, 1, 0, g, '
                                           "rid='req-m2-lock-timeout')\n"
                                           '        elapsed = asyncio.get_running_loop().time() - '
                                           'started\n'
                                           '        assert response.status_code == 503, '
                                           'response.text\n'
                                           "        assert response.json() == {'detail': "
                                           "'database_deadline'}\n"
                                           '        assert 4.0 <= elapsed < 7.0, elapsed\n'
                                           "        assert await env.conn.fetchval('SELECT "
                                           "count(*) FROM match_seat_holds WHERE room_name = $1', "
                                           's.room) == 0\n'
                                           "        assert await env.conn.fetchval('SELECT "
                                           'count(*) FROM match_hold_open_attempts WHERE '
                                           "request_id = $1', 'req-m2-lock-timeout') == 0\n"
                                           "        assert await env.conn.fetchval('SELECT "
                                           "count(*) FROM queue_leases WHERE player_id = $1', "
                                           's.pid(1)) == 1\n'
                                           '    finally:\n'
                                           '        await transaction.rollback()\n'
                                           '        await blocker.close()\n'
                                           '    await asyncio.sleep(0.1)\n'
                                           "    assert await env.conn.fetchval('SELECT count(*) "
                                           "FROM match_seat_holds WHERE room_name = $1', s.room) "
                                           '== 0\n'
                                           "    assert await env.conn.fetchval('SELECT count(*) "
                                           "FROM queue_leases WHERE player_id = $1', s.pid(1)) == "
                                           '1'),
                                          ('wrapper',
                                           'async def inside():\n'
                                           '    async with cf_pg.case(prefix) as (c, sm):\n'
                                           '        await body(Env(c, sm, monkeypatch))'),
                                          ('wrapper',
                                           "def run_env(monkeypatch, body, prefix='rjs2'):\n"
                                           '    cf_pg.require_live_pg()\n'
                                           '\n'
                                           '    async def inside():\n'
                                           '        async with cf_pg.case(prefix) as (c, sm):\n'
                                           '            await body(Env(c, sm, monkeypatch))\n'
                                           '    _run(inside())')],
 'tests/test_pc_routes.py#complete': [],
 'tests/test_pc_sept12.py#complete': [],
 'tests/test_player_cards_server.py#complete': [],
 'tests/test_title_ladder_hooks_live.py#complete': [('alias', 'str exec'),
                                                    ('argdef',
                                                     'DSN <- DSN = (os.environ.get(DSN_VAR) or '
                                                     "'').replace('postgresql+asyncpg://', "
                                                     "'postgresql://')"),
                                                    ('wrapper',
                                                     '@contextlib.asynccontextmanager\n'
                                                     'async def _app(schema):\n'
                                                     '    """An httpx client on main.app, every '
                                                     'request on a session of its own\n'
                                                     '    bound to `schema`; an exception the app '
                                                     'does not handle comes back as\n'
                                                     "    the 500 a player's client would get, not "
                                                     'raised into the test."""\n'
                                                     '    engine = harness.bound_engine(DSN, '
                                                     'schema)\n'
                                                     '    session = async_sessionmaker(engine, '
                                                     'expire_on_commit=False)\n'
                                                     '\n'
                                                     '    async def _db():\n'
                                                     '        async with session() as db:\n'
                                                     '            yield db\n'
                                                     '    '
                                                     'main.app.dependency_overrides[database.get_db] '
                                                     '= _db\n'
                                                     '    try:\n'
                                                     '        transport = '
                                                     'httpx.ASGITransport(app=main.app, '
                                                     'raise_app_exceptions=False)\n'
                                                     '        async with '
                                                     'httpx.AsyncClient(transport=transport, '
                                                     "base_url='http://ladder.test', "
                                                     "headers={'X-Mod-Version': "
                                                     'main.MIN_MOD_VERSION_EFFECTIVE}) as client:\n'
                                                     '            yield client\n'
                                                     '    finally:\n'
                                                     '        '
                                                     'main.app.dependency_overrides.pop(database.get_db, '
                                                     'None)\n'
                                                     '        await engine.dispose()'),
                                                    ('wrapper',
                                                     '@contextlib.asynccontextmanager\n'
                                                     'async def _case(extra_ddl=None):\n'
                                                     '    """A built, sealed case schema and a '
                                                     'session factory bound to it.\n'
                                                     '\n'
                                                     '    The 1v1 podium cache '
                                                     '(main._podium_cache, a 60 s process-wide '
                                                     'copy) is\n'
                                                     '    emptied for the case and put back after '
                                                     'it: a podium read from another\n'
                                                     "    case's players answers about a different "
                                                     'database, and the series-gold\n'
                                                     '    "Podium beaten x2" of two runs compared '
                                                     'here then depended on which ran\n'
                                                     "    first (the v1.41.0 beta's refresh reads "
                                                     'the case\'s own podium)."""\n'
                                                     '    saved = dict(main._podium_cache)\n'
                                                     "    main._podium_cache.update({'at': 0.0, "
                                                     "'ok': False, 'ids': [], 'map': {}})\n"
                                                     '    try:\n'
                                                     '        async with harness.CaseSchema(DSN, '
                                                     "'ladder_hooks') as case:\n"
                                                     '            await _build(case, extra_ddl)\n'
                                                     '            engine = '
                                                     'harness.bound_engine(DSN, case.schema)\n'
                                                     '            try:\n'
                                                     '                yield (case.schema, '
                                                     'async_sessionmaker(engine, '
                                                     'expire_on_commit=False))\n'
                                                     '            finally:\n'
                                                     '                await engine.dispose()\n'
                                                     '    finally:\n'
                                                     '        main._podium_cache.clear()\n'
                                                     '        main._podium_cache.update(saved)'),
                                                    ('wrapper',
                                                     'async def _build(case, extra_ddl=None):\n'
                                                     '    """Into case.schema, on case.conn (bound '
                                                     'to it): replay, ORM, widen,\n'
                                                     '    replay, 331 then 365 run and confirmed, '
                                                     'the case\'s own change, sealed."""\n'
                                                     '    conn, schema = (case.conn, case.schema)\n'
                                                     '    statements = _ddl_statements()\n'
                                                     '    await _replay(conn, statements)\n'
                                                     '    engine = harness.bound_engine(DSN, '
                                                     'schema)\n'
                                                     '    try:\n'
                                                     '        async with engine.begin() as c:\n'
                                                     '            await '
                                                     'c.run_sync(models.Base.metadata.create_all)\n'
                                                     '    finally:\n'
                                                     '        await engine.dispose()\n'
                                                     '    await _widen(conn, schema)\n'
                                                     '    second = await _replay(conn, '
                                                     'statements)\n'
                                                     '    unexpected = [f for f in second if f[1] '
                                                     'not in _ALREADY and (f[0], f[1]) not in '
                                                     'REPLAY_KNOWN]\n'
                                                     "    assert not unexpected, 'the second DDL "
                                                     'pass failed on statements outside '
                                                     "REPLAY_KNOWN: %r' % unexpected[:5]\n"
                                                     '    await conn.execute(io.open(MIGRATION, '
                                                     "encoding='utf-8').read())\n"
                                                     '    await '
                                                     'conn.execute(io.open(MIGRATION_365, '
                                                     "encoding='utf-8').read())\n"
                                                     "    rungs = await conn.fetchval('SELECT "
                                                     "count(*) FROM title_ladders')\n"
                                                     "    items = await conn.fetchval('SELECT "
                                                     'count(*) FROM shop_items WHERE sku = '
                                                     "ANY($1::text[])', list(tl.ALL_SKUS))\n"
                                                     "    tables = [await conn.fetchval('SELECT "
                                                     "to_regclass($1)::text', t) for t in "
                                                     "('title_ladder_credits', "
                                                     "'title_ladder_progress')]\n"
                                                     '    assert rungs == items == '
                                                     'len(tl.ALL_SKUS) and None not in tables, '
                                                     "'331 and 365 did not land: %d rungs, %d shop "
                                                     "rows, tables %r' % (rungs, items, tables)\n"
                                                     '    if extra_ddl is not None:\n'
                                                     '        await extra_ddl(conn, schema)\n'
                                                     '    await case.seal()'),
                                                    ('wrapper',
                                                     'async def _get_ladders(schema, steams):\n'
                                                     '    """GET each player\'s ladders from '
                                                     'main.app, each request on a session of\n'
                                                     '    its own bound to `schema`. Returns '
                                                     '{steam: (status, body)}."""\n'
                                                     '    engine = harness.bound_engine(DSN, '
                                                     'schema)\n'
                                                     '    session = async_sessionmaker(engine, '
                                                     'expire_on_commit=False)\n'
                                                     '\n'
                                                     '    async def _db():\n'
                                                     '        async with session() as db:\n'
                                                     '            yield db\n'
                                                     '    out = {}\n'
                                                     '    '
                                                     'main.app.dependency_overrides[database.get_db] '
                                                     '= _db\n'
                                                     '    try:\n'
                                                     '        transport = '
                                                     'httpx.ASGITransport(app=main.app)\n'
                                                     '        async with '
                                                     'httpx.AsyncClient(transport=transport, '
                                                     "base_url='http://ladder.test') as c:\n"
                                                     '            for steam in steams:\n'
                                                     '                r = await '
                                                     "c.get('/api/v1/players/%s/title-ladders' % "
                                                     "steam, headers={'X-Mod-Version': "
                                                     'main.MIN_MOD_VERSION_EFFECTIVE})\n'
                                                     '                out[steam] = (r.status_code, '
                                                     'r.json())\n'
                                                     '    finally:\n'
                                                     '        '
                                                     'main.app.dependency_overrides.pop(database.get_db, '
                                                     'None)\n'
                                                     '        await engine.dispose()\n'
                                                     '    return out'),
                                                    ('wrapper',
                                                     'async def _look(schema):\n'
                                                     '    conn = await harness.connect_bound(DSN, '
                                                     'schema)\n'
                                                     '    try:\n'
                                                     '        return (await _ladder(conn), await '
                                                     '_economy(conn))\n'
                                                     '    finally:\n'
                                                     '        await conn.close()'),
                                                    ('wrapper',
                                                     'async def _on_disk(schema):\n'
                                                     '    """What another connection sees at this '
                                                     'moment: the match rows, the\n'
                                                     '    completed series and the rating_history '
                                                     'rows."""\n'
                                                     '    conn = await harness.connect_bound(DSN, '
                                                     'schema)\n'
                                                     '    try:\n'
                                                     "        return (await conn.fetchval('SELECT "
                                                     "COUNT(*) FROM matches'), await "
                                                     'conn.fetchval("SELECT COUNT(*) FROM '
                                                     'ranked_series WHERE status = '
                                                     '\'completed\'"), await '
                                                     "conn.fetchval('SELECT COUNT(*) FROM "
                                                     "rating_history'))\n"
                                                     '    finally:\n'
                                                     '        await conn.close()'),
                                                    ('wrapper',
                                                     'async def _per_game(schema, lobbies):\n'
                                                     '    """What stays per game: each lobby\'s '
                                                     'ffa_matches ids in game order, the\n'
                                                     '    FFA games each player has been rated in, '
                                                     'and the ffa_placement gold rows\n'
                                                     '    as {reference id: sorted steam ids}."""\n'
                                                     '    conn = await harness.connect_bound(DSN, '
                                                     'schema)\n'
                                                     '    try:\n'
                                                     '        matches = {}\n'
                                                     '        for lobby in lobbies:\n'
                                                     '            matches[str(lobby)] = '
                                                     "[str(r['id']) for r in await "
                                                     "conn.fetch('SELECT id FROM ffa_matches WHERE "
                                                     "lobby_id = $1 ORDER BY game_number', "
                                                     'lobby)]\n'
                                                     "        played = {r['steam_id']: "
                                                     "r['games_played'] for r in await "
                                                     "conn.fetch('SELECT p.steam_id, "
                                                     'g.games_played FROM glicko_ratings_ffa g   '
                                                     'JOIN players p ON p.id = g.player_id WHERE '
                                                     "g.games_played > 0')}\n"
                                                     '        placed = {}\n'
                                                     '        for r in await conn.fetch("SELECT '
                                                     'g.reference_id, p.steam_id FROM '
                                                     'gold_transactions g   JOIN players p ON p.id '
                                                     '= g.player_id WHERE g.reason = '
                                                     '\'ffa_placement\'"):\n'
                                                     '            '
                                                     "placed.setdefault(r['reference_id'], "
                                                     "[]).append(r['steam_id'])\n"
                                                     '        return (matches, played, {k: '
                                                     'sorted(v) for k, v in placed.items()})\n'
                                                     '    finally:\n'
                                                     '        await conn.close()'),
                                                    ('wrapper',
                                                     'async def _play_ledger(schema):\n'
                                                     '    conn = await harness.connect_bound(DSN, '
                                                     'schema)\n'
                                                     '    try:\n'
                                                     "        rows = await conn.fetch('SELECT "
                                                     'p.steam_id, g.reason, g.amount FROM '
                                                     'gold_transactions g   JOIN players p ON p.id '
                                                     "= g.player_id WHERE g.amount > 0')\n"
                                                     '    finally:\n'
                                                     '        await conn.close()\n'
                                                     '    play, ach = ({}, {})\n'
                                                     '    for r in rows:\n'
                                                     "        if r['reason'] in PLAY_REASONS:\n"
                                                     "            play[r['steam_id']] = "
                                                     "play.get(r['steam_id'], 0) + r['amount']\n"
                                                     "        if r['reason'] == 'achievement':\n"
                                                     "            ach[r['steam_id']] = "
                                                     "ach.get(r['steam_id'], 0) + r['amount']\n"
                                                     '    return (play, ach)'),
                                                    ('wrapper',
                                                     'async def _r3_run(how, tag, armed=None):\n'
                                                     '    """A 1v1 series to completion with the '
                                                     'deciding report forced one way;\n'
                                                     "    game 1 runs on the case's own sessions. "
                                                     'For `how` == "fail", `armed`\n'
                                                     "    holds the switch of the test's "
                                                     'rating-calculation fault: the deciding\n'
                                                     '    report is sent once with the fault armed '
                                                     'and, after the state is read,\n'
                                                     '    once more with it lifted. For `how` == '
                                                     '"one_commit", the deciding report\n'
                                                     '    runs on a session that counts its '
                                                     'commits and, before each, reads from\n'
                                                     '    another connection what the database '
                                                     'holds at that moment.\n'
                                                     '\n'
                                                     '    Either way the one write submit_match '
                                                     'makes in a session of its own --\n'
                                                     "    the podium holders' sync (bug 325), "
                                                     'which fires from a cold podium copy,\n'
                                                     '    and _case leaves the copy cold -- is '
                                                     'routed to the case schema and\n'
                                                     '    counted: the copy is warmed on the '
                                                     "case's own players before the state\n"
                                                     '    is read and held past the reports '
                                                     "whatever the seat's load (_case puts\n"
                                                     '    the cache back), so a commit on that '
                                                     'session during the reports is a\n'
                                                     '    finding, and one commit of this '
                                                     'function\'s own proves the count live."""\n'
                                                     '    async with _case() as (schema, sm):\n'
                                                     '        ids = await _seed(sm)\n'
                                                     '        seeded, _ = await _look(schema)\n'
                                                     '        g1 = await _submit(sm, '
                                                     'main.submit_match, '
                                                     "_report_1v1('ranked_lh%s_000001_r1' % tag))\n"
                                                     '        assert g1[1] is None and '
                                                     "g1[0].series_status == 'active', g1\n"
                                                     '        seen, other = ([], [])\n'
                                                     '\n'
                                                     '        class _Counting(AsyncSession):\n'
                                                     '\n'
                                                     '            async def commit(self):\n'
                                                     '                seen.append(await '
                                                     '_on_disk(schema))\n'
                                                     '                await super().commit()\n'
                                                     '\n'
                                                     '        class _Elsewhere(AsyncSession):\n'
                                                     '\n'
                                                     '            async def commit(self):\n'
                                                     '                other.append(await '
                                                     '_on_disk(schema))\n'
                                                     '                await super().commit()\n'
                                                     '        engine = harness.bound_engine(DSN, '
                                                     'schema)\n'
                                                     "        deciding = sm if how != 'one_commit' "
                                                     'else async_sessionmaker(engine, '
                                                     'expire_on_commit=False, class_=_Counting)\n'
                                                     '        saved = database.async_session\n'
                                                     '        database.async_session = '
                                                     'async_sessionmaker(engine, '
                                                     'expire_on_commit=False, class_=_Elsewhere)\n'
                                                     '        try:\n'
                                                     '            async with sm() as db:\n'
                                                     '                await '
                                                     'main._podium_player_ids(db)\n'
                                                     "            main._podium_cache['at'] = "
                                                     'time.monotonic() + 3600\n'
                                                     '            del other[:]\n'
                                                     '            mid, mid_econ = await '
                                                     '_look(schema)\n'
                                                     "            room = 'ranked_lh%s_000002_r2' % "
                                                     'tag\n'
                                                     '            g2 = await _submit(deciding, '
                                                     'main.submit_match, _report_1v1(room))\n'
                                                     '            refused, refused_econ = await '
                                                     '_look(schema)\n'
                                                     '            g3 = None\n'
                                                     "            if how == 'fail':\n"
                                                     '                armed[0] = False\n'
                                                     '                g3 = await _submit(deciding, '
                                                     'main.submit_match, _report_1v1(room))\n'
                                                     '            other_during = len(other)\n'
                                                     '            async with '
                                                     'database.async_session() as probe:\n'
                                                     '                await '
                                                     "probe.execute(text('SELECT 1'))\n"
                                                     '                await probe.commit()\n'
                                                     '            other_probe = len(other)\n'
                                                     '            conn = await '
                                                     'harness.connect_bound(DSN, schema)\n'
                                                     '            try:\n'
                                                     "                disk = [str(r['id']) for r "
                                                     "in await conn.fetch('SELECT id FROM matches "
                                                     "WHERE photon_room_id = $1', room)]\n"
                                                     '            finally:\n'
                                                     '                await conn.close()\n'
                                                     '        finally:\n'
                                                     '            database.async_session = saved\n'
                                                     '            await engine.dispose()\n'
                                                     '        after, econ = await _look(schema)\n'
                                                     '        refs = [str(g[0].match_id) for g in '
                                                     '(g1, g2, g3) if g is not None and g[1] is '
                                                     'None]\n'
                                                     '        return dict(seeded=seeded, mid=mid, '
                                                     'mid_econ=mid_econ, g2=g2, g3=g3, '
                                                     'refused=refused, refused_econ=refused_econ, '
                                                     'after=after, econ=econ, seen=seen, '
                                                     'other=other, other_during=other_during, '
                                                     'other_probe=other_probe, disk=disk, '
                                                     'refs=refs)')],
 'tests/test_title_ladders.py#complete': [('alias',
                                           'from sqlalchemy.ext.asyncio import async_sessionmaker, '
                                           'create_async_engine'),
                                          ('alias', 'str getattr'),
                                          ('argdef', 'DSN <- DSN = os.environ.get(DSN_VAR)'),
                                          ('argdef',
                                           'LADDER_DSN <- LADDER_DSN = '
                                           '(os.environ.get(LADDER_DSN_VAR) or '
                                           "'').replace('postgresql+asyncpg://', 'postgresql://')"),
                                          ('wrapper',
                                           'def _ladder_engine(schema):\n'
                                           '    from sqlalchemy.ext.asyncio import '
                                           'async_sessionmaker, create_async_engine\n'
                                           '    engine = '
                                           "create_async_engine(LADDER_DSN.replace('postgresql://', "
                                           "'postgresql+asyncpg://'), "
                                           "connect_args={'server_settings': {'search_path': "
                                           'schema}}, poolclass=None)\n'
                                           '    return (engine, async_sessionmaker(engine, '
                                           'expire_on_commit=False))')],
 'tests/title_ladders_lane_schema.py#complete': []}
R10_COUNT = 114
for _k, _v in R10_FROZEN.items():
    FROZEN[_k] = list(FROZEN[_k]) + list(_v)
FROZEN_COUNT = COARSE_COUNT + COMPLETE_COUNT + R10_COUNT

# Hand edit at the round-10 merge (W30b; the ro child's question 4; reviewed in
# the round-10 notes): fifteen forms the gr child's round-10 code adds (ruling
# REHEARSAL-R9-A1 (D), every pure callee bound to its frozen provider). Each
# is a reference to the builtins module or a module's __builtins__ entry: the
# provider tables bind a pure name to the builtins object itself
# (closed_walk._builtins, test_a1_identity_formation._a1_builtins,
# test_match_hold_admission_gate_pg._gate_builtins), Bindings.listed reads a
# module's '__builtins__' to compare identity, and the a1 and gate controls
# rebind main.__builtins__ or a module name (monkeypatch, restored) to prove
# the identity check refuses; the a1 predicate evaluator passes an empty
# '__builtins__' mapping to eval. None reaches an opener, a DSN, a role or an
# identity statement. Frozen by hand at the merge, not by a re-derivation.
R10_MERGE_FROZEN = {
    'tests/closed_walk.py#complete': [
        ('alias', '(_builtins.getattr,)'), ('alias', '(_builtins.hasattr,)'),
        ('alias', 'import builtins as _builtins'), ('alias', 'str __builtins__')],
    'tests/test_a1_identity_formation.py#complete': [
        ('alias', 'builtins.int'), ('alias', 'import builtins'), ('alias', 'import builtins'),
        ('alias', 'import builtins as _a1_builtins'),
        ('alias', "m.setattr(main, '__builtins__', builtins)"),
        ('alias', 'str __builtins__'), ('alias', 'str __builtins__'), ('alias', 'str eval')],
    'tests/test_match_hold_admission_gate_pg.py#complete': [
        ('alias', 'import builtins as _gate_builtins'), ('alias', 'str eval'),
        ('dynamic', 'm.setattr(main, name, writer, raising=False)')],
}
R10_MERGE_COUNT = 15
for _k, _v in R10_MERGE_FROZEN.items():
    FROZEN[_k] = list(FROZEN[_k]) + list(_v)
FROZEN_COUNT = COARSE_COUNT + COMPLETE_COUNT + R10_COUNT + R10_MERGE_COUNT


# Round 11 (ruling FOUR-R10-A2 (3) FIX-R11-OPEN; child OPEN of W30e). Two
# blocks, each derived ONCE at the round-11 base 5b18949a by
# RF11/open/freeze_r11.py (it refuses unless the census files equal
# 5b18949a and this file equals its pre-image md5 77b307f3), never
# regenerated:
#
# R11_ID_FROZEN: the 33 forms the ROUND-10 grammar already finds at
# 5b18949a beyond FROZEN, all from FIX-R11-ID's code (closed_walk.py, the
# identity binder's reads of module and builtins namespaces, and
# test_a1_identity_formation.py, its controls). Not this child's forms:
# frozen here so the census is green at 5b18949a; the integrator reviews or
# replaces this block at the merge (the round-10 precedent: R10_MERGE_FROZEN).
#
# R11_OPEN_FROZEN: the 33 forms the ROUND-11 grammar adds at 5b18949a, every
# one a reflective literal (a string constant spelled __x__, finding F5).
# The round-11 binding forms (finding F6) add no form at 5b18949a.
R11_ID_FROZEN = {'tests/closed_walk.py#complete': [('alias', 'str __builtins__'),
                                   ('alias', 'str delattr'),
                                   ('alias', 'str eval'),
                                   ('alias', 'str exec'),
                                   ('alias', 'str globals'),
                                   ('alias', 'str hasattr'),
                                   ('alias', 'str locals'),
                                   ('alias', 'str setattr'),
                                   ('alias', 'str vars'),
                                   ('alias', 'str vars'),
                                   ('alias', 'str vars'),
                                   ('dynamic', 'b.__dict__'),
                                   ('dynamic', 'b.__dict__'),
                                   ('dynamic', 'b.__dict__'),
                                   ('dynamic', 'b.__dict__'),
                                   ('dynamic', 'b.__dict__'),
                                   ('dynamic', 'b.__dict__'),
                                   ('dynamic', 'getattr(bi, name, _MISSING)'),
                                   ('dynamic', 'getattr(self.scope, name, _MISSING)'),
                                   ('dynamic', 'hasattr(_builtins, d.name)'),
                                   ('dynamic', 'pol.__dict__'),
                                   ('dynamic', 'pol.__dict__'),
                                   ('dynamic', 'policy.__dict__'),
                                   ('dynamic', 'policy.__dict__'),
                                   ('dynamic', 'policy.__dict__'),
                                   ('dynamic', 'self.p.__dict__'),
                                   ('dynamic', 'vars(K)'),
                                   ('dynamic', 'vars(c)'),
                                   ('dynamic', 'vars(c)'),
                                   ('dynamic', 'vars(c)'),
                                   ('dynamic', 'vars(c)'),
                                   ('dynamic', 'vars(cls)'),
                                   ('dynamic', 'vars(mod)'),
                                   ('dynamic', 'vars(mod)'),
                                   ('dynamic', 'vars(mod)'),
                                   ('dynamic', 'vars(mod)'),
                                   ('dynamic', 'vars(mod)'),
                                   ('dynamic', 'vars(mod)'),
                                   ('dynamic', 'vars(scope)'),
                                   ('dynamic', 'vars(type(self.scope))')],
 'tests/test_a1_identity_formation.py#complete': [('alias', 'builtins.int'),
                                                  ('alias', 'import builtins'),
                                                  ('alias', 'str builtins'),
                                                  ('alias', 'str builtins'),
                                                  ('alias', 'str exec'),
                                                  ('alias', 'str exec'),
                                                  ('alias', 'str exec'),
                                                  ('dynamic',
                                                   "exec(compile('def f(x):\\n    return "
                                                   "x\\n', other.__file__, 'exec'), "
                                                   'other.__dict__)'),
                                                  ('dynamic',
                                                   "exec(compile('def g():\\n    return 2\\n', "
                                                   "late.__file__, 'exec'), late.__dict__)"),
                                                  ('dynamic',
                                                   "exec(compile(text, mod.__file__, 'exec'), "
                                                   'mod.__dict__)'),
                                                  ('dynamic',
                                                   'getattr(_a1_real_inspect, name)'),
                                                  ('dynamic', 'hasattr(mod, name)'),
                                                  ('dynamic', 'late.__dict__'),
                                                  ('dynamic', 'mod.__dict__'),
                                                  ('dynamic', 'mod.__dict__'),
                                                  ('dynamic', 'other.__dict__'),
                                                  ('dynamic', 'pol.__dict__'),
                                                  ('dynamic', 'vars(main)')],
 'tests/test_match_hold_admission_gate_pg.py#complete': [('alias', 'str exec'),
                                                         ('alias', 'str exec'),
                                                         ('alias', 'str exec'),
                                                         ('alias', 'str getattr'),
                                                         ('alias', 'str hasattr'),
                                                         ('alias', 'str setattr'),
                                                         ('dynamic',
                                                          "exec(compile('def f():' + chr(10) + "
                                                          "'    return 2' + chr(10), '<r11 "
                                                          "order>', 'exec'), early)"),
                                                         ('dynamic',
                                                          "exec(compile(chr(10) * 2 + 'def "
                                                          "f():' + chr(10) + '    return 1' + "
                                                          "chr(10), '<r11 order>', 'exec'), "
                                                          'late)'),
                                                         ('dynamic',
                                                          "exec(compile(src, f'<unregistered "
                                                          "{name}>', 'exec'), scope.__dict__)"),
                                                         ('dynamic', 'getattr(R, n)'),
                                                         ('dynamic', 'getattr(_cw, n)'),
                                                         ('dynamic', 'getattr(mod, name)'),
                                                         ('dynamic', 'getattr(module, name)'),
                                                         ('dynamic', 'module.__dict__'),
                                                         ('dynamic', 'scope.__dict__'),
                                                         ('dynamic', 'scope.__dict__'),
                                                         ('dynamic', 'sys.modules'),
                                                         ('dynamic', 'sys.modules'),
                                                         ('dynamic', 'sys.modules'),
                                                         ('dynamic', 'vars(cls)'),
                                                         ('dynamic', 'vars(cls)'),
                                                         ('dynamic', 'vars(mod)'),
                                                         ('dynamic', 'vars(scope)'),
                                                         ('dynamic', 'vars(scope)'),
                                                         ('dynamic', 'vars(scope)'),
                                                         ('dynamic', 'vars(scope)'),
                                                         ('dynamic', 'vars(v)'),
                                                         ('dynamic', 'vars(v)')]}
R11_ID_COUNT = 86
R11_OPEN_FROZEN = {'api/build_manifest.py#complete': [('alias', 'str __main__')],
 'api/conn_ranges.py#complete': [('alias', 'str __main__')],
 'api/log_redaction.py#complete': [('alias', 'str __main__')],
 'api/main.py#complete': [('alias', 'str __cause__'),
                          ('alias', 'str __dict__'),
                          ('alias', 'str __globals__'),
                          ('alias', 'str __module__'),
                          ('alias', 'str __qualname__')],
 'api/match_hold.py#complete': [('alias', 'str __cause__'), ('alias', 'str __context__')],
 'api/pc_face.py#complete': [('alias', 'str __pycache__')],
 'api/review_boot.py#complete': [('alias', 'str __file__'),
                                 ('alias', 'str __main__'),
                                 ('alias', 'str __main__')],
 'api/review_rules.py#complete': [('alias', 'str __main__'), ('alias', 'str __main__')],
 'api/tournament_bracket.py#complete': [('alias', 'str __main__')],
 'tests/closed_walk.py#complete': [('alias', 'str __binder_address__'),
                                   ('alias', 'str __class__'),
                                   ('alias', 'str __delattr__'),
                                   ('alias', 'str __delattr__'),
                                   ('alias', 'str __dict__'),
                                   ('alias', 'str __dict__'),
                                   ('alias', 'str __dict__'),
                                   ('alias', 'str __file__'),
                                   ('alias', 'str __file__'),
                                   ('alias', 'str __getattr__'),
                                   ('alias', 'str __getattribute__'),
                                   ('alias', 'str __name__'),
                                   ('alias', 'str __name__'),
                                   ('alias', 'str __name__'),
                                   ('alias', 'str __name__'),
                                   ('alias', 'str __name__'),
                                   ('alias', 'str __name__'),
                                   ('alias', 'str __name__'),
                                   ('alias', 'str __qualname__'),
                                   ('alias', 'str __self__'),
                                   ('alias', 'str __self__'),
                                   ('alias', 'str __setattr__'),
                                   ('alias', 'str __setattr__'),
                                   ('alias', 'str __slots__')],
 'tests/resolution_sites.py#complete': [('alias', 'str __init__'),
                                        ('alias', 'str __init__'),
                                        ('alias', 'str __main__')],
 'tests/test_a1_identity_formation.py#complete': [('alias', 'str __file__')],
 'tests/test_match_hold_admission_gate_pg.py#complete': [('alias', 'str __code__'),
                                                         ('alias', 'str __file__'),
                                                         ('alias', 'str __module__'),
                                                         ('alias', 'str __name__'),
                                                         ('alias', 'str __name__'),
                                                         ('alias', 'str __name__'),
                                                         ('alias', 'str __name__'),
                                                         ('alias', 'str __name__'),
                                                         ('alias', 'str __qualname__'),
                                                         ('alias', 'str __self__'),
                                                         ('alias', 'str __str__')]}
R11_OPEN_COUNT = 56
for _k, _v in list(R11_ID_FROZEN.items()) + list(R11_OPEN_FROZEN.items()):
    FROZEN[_k] = list(FROZEN[_k]) + list(_v)
FROZEN_COUNT = (COARSE_COUNT + COMPLETE_COUNT + R10_COUNT + R10_MERGE_COUNT
                + R11_ID_COUNT + R11_OPEN_COUNT)
