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
 'tests/closed_walk.py#complete': [('dynamic', 'getattr(self.scope, name, _MISSING)'),
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
                                                  ('dynamic', 'vars(main)')],
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
COARSE_COUNT = 363
COMPLETE_COUNT = 216
FROZEN.update(COMPLETE_FROZEN)
FROZEN_COUNT = COARSE_COUNT + COMPLETE_COUNT
