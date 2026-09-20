-- 336_bug_reports_kind.sql
--
-- bug_reports.kind — what put this row here (v1.41.0 Item 3, 2026-09-18).
--
--   'report'  a player filed it from the F5 bug form. Every row that exists
--             today is one of these, and nothing about them changes.
--   'auto'    the opt-in automatic post-match log upload wrote it
--             (POST /api/v1/logs/auto, backend/api/auto_logs.py).
--
-- WHY ONE TABLE AND NOT TWO. An auto upload is the same artifact as a bug
-- report's attachment: the same bundle, the same gzipped blob under
-- BUG_REPORT_LOG_DIR, the same admin detail view, the same read-time scrub,
-- the same ops `bug-log:N` verb. A separate table would have needed a second
-- copy of every one of those readers. One column and one discriminator
-- instead.
--
-- NUMBERING. 336 is inside the 330-339 block the v1.41.0 batch reserved.
-- 331, 332, 337 and 338 belong to other items in the same batch; the highest
-- number merged in main is 325.
--
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND, AND THAT IS MANDATORY --
-- not a preference, and not merely "the ordinary two-SHA order". Deploying
-- the code against a database without this column takes DOWN paths that work
-- today, because the new code NAMES `kind` in statements that run on ordinary
-- requests rather than only on the new feature's own path.
--
-- Enumerated as WRITERS and READERS, because a deploy-order note that lists
-- only readers has already been wrong here once (#346):
--
--   WRITER  auto_logs.upload_auto_log          INSERT ... kind = 'auto'
--   WRITER  auto_logs.prune_auto_logs          DELETE ... WHERE kind = 'auto'
--   READER  main.submit_bug_report             the 10/24h count, now scoped to
--                                              kind = 'report' so automatic
--                                              uploads cannot spend a
--                                              player's report budget
--   READER  main.recent_bug_reports            the Discord #bug-reports feed,
--                                              now scoped to kind = 'report'
--   READER  main.recent_bug_report_events      the bot-poll feed. BOTH of its
--                                              branches carry br.kind =
--                                              'report', and it is polled
--                                              continuously, so without the
--                                              column this endpoint fails on
--                                              every call
--   READER  main.list_bug_reports              SELECTs kind for admin triage
--   READER  main.get_bug_report                SELECTs kind for the detail
--                                              pane
--   READER  main.user_comment_on_bug_report    reads kind to refuse an
--                                              automatic row before the
--                                              Discord reply path
--   READER  auto_logs.auto_log_retention_loop  the scheduled sweep's own
--                                              predicate, via prune_auto_logs
--
-- So code-before-migration is a BROKEN deployment, not a degraded one. The
-- REVERSE -- this file applied while the OLD code is still running -- is
-- entirely safe, and is the state the two-SHA order deliberately passes
-- through: the column has a default, every existing row gets 'report', and no
-- statement in the old code names it.
--
-- The ORM does NOT map this column, and that is a narrower guarantee than it
-- looks. models.BugReport is deliberately left without it so submit_bug_report's
-- ORM INSERT keeps working unchanged against either schema -- the
-- conservative direction is that a player can always file a bug. It does NOT
-- make the api as a whole tolerant of a missing column: every READER above is
-- raw SQL naming `kind` directly, which is why the order above is mandatory
-- and why an earlier version of this header -- which said the file was
-- "otherwise safe to apply at any time" and left the ORM note to imply the
-- reverse order was survivable -- was wrong. Because an ORM assignment to an
-- undeclared column is a silent no-op rather than an error (#346), the reason
-- is recorded in models.py at the class as well as here, and auto_logs.py
-- writes kind with raw SQL.

BEGIN;
SET LOCAL lock_timeout = '5s';

-- GUARDED ON THE CATALOG, not spelled `IF NOT EXISTS`, and the difference is
-- the whole re-run story of this file. ALTER TABLE takes its ACCESS EXCLUSIVE
-- lock on the relation BEFORE it evaluates `IF NOT EXISTS`, so the no-op
-- spelling still queues behind every reader that is already open and puts
-- every NEW reader behind itself while it waits -- and with the lock_timeout
-- above, a re-run on a live primary aborts instead. Measured on PostgreSQL
-- 16.9 rather than reasoned: with one ordinary `SELECT count(*) FROM
-- bug_reports` open in another session, a second application of this file in
-- its previous spelling died with "canceling statement due to lock timeout".
-- Asking the catalog first issues no statement at all when the column is
-- already there. The property that buys, stated as narrowly as it was
-- measured: a re-run of this file takes no lock on bug_reports that an
-- ordinary reader or an ordinary writer conflicts with. NOT "no lock" --
-- the COMMENT below is heavier than the reads are.
-- `test_a_second_run_takes_no_blocking_lock` holds a reader's AccessShare in
-- one case and a writer's RowExclusive in the other, re-applies the file
-- under each, and carries a control statement proving such a holder can stop
-- a re-run at all -- without which "it completed" is also what a holder that
-- took nothing would produce.
DO $m336col$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_attribute
                    WHERE attrelid = 'bug_reports'::regclass
                      AND attname = 'kind'
                      AND NOT attisdropped) THEN
        ALTER TABLE bug_reports
            ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'report';
    END IF;
END $m336col$;

-- Left unguarded deliberately, and it is the reason the sentence above is
-- about which locks CONFLICT rather than about taking none: COMMENT's lock is
-- stronger than a read's and still conflicts with neither an ordinary reader
-- nor an ordinary writer. Measured the same way as the rest -- the re-run
-- completes with either of those held, and this statement is in it.
COMMENT ON COLUMN bug_reports.kind IS
    'What created this row: ''report'' = player-filed via the F5 bug form; ''auto'' = opt-in automatic post-match log upload. Retention applies to ''auto'' only.';

-- Redundant on a first run -- the ADD COLUMN above already set it -- and NOT
-- redundant on any other: the block above adds nothing to a column that is
-- already there, so a re-run over a hand-added or partially-applied column
-- would otherwise leave it with no default at all. The schema default is the
-- ONLY default this column has: models.py deliberately does not map it, so
-- there is no ORM default to disagree with it (which is the direction that
-- once made every auto-created opponent come out ranked).
--
-- Guarded on the exact condition the post-check at the bottom requires, so
-- the two cannot disagree: a column that already renders that default is left
-- alone and costs the re-run no lock, and anything else -- absent, or some
-- other default -- takes the ALTER, which is real work for a real reason.
DO $m336def$
BEGIN
    IF COALESCE((SELECT column_default
                   FROM information_schema.columns
                  WHERE table_schema = current_schema()
                    AND table_name = 'bug_reports'
                    AND column_name = 'kind'), '') NOT LIKE '''report''%' THEN
        ALTER TABLE bug_reports ALTER COLUMN kind SET DEFAULT 'report';
    END IF;
END $m336def$;

-- Only two values are meant to exist. A third arriving from a typo would be
-- invisible: it would simply fall out of both the report feed and the auto
-- retention sweep, i.e. a row nobody announces and nobody ever deletes.
--
-- GUARDED ON EXISTENCE rather than DROP-then-ADD. PostgreSQL has no
-- `ADD CONSTRAINT IF NOT EXISTS`, and the drop/recreate spelling makes every
-- re-run do real work: an ACCESS EXCLUSIVE lock on bug_reports plus a full
-- validating scan of the table, for a constraint that is already exactly
-- right. Re-running a migration must be a no-op, and "it ends in the same
-- state" is not the same claim as "it did nothing" when the difference is a
-- table lock on a live system. That is the rule the whole file is written to
-- and not a remark about this one statement: every other statement here that
-- would take a lock a reader or a writer can be stopped by is guarded on the
-- catalog for the same reason. An earlier version of this file kept the
-- sentence above and still took ACCESS EXCLUSIVE twice and SHARE twice on a
-- re-run, which is what "it did nothing" had quietly come to mean.
--
-- The name is the identity here, so this guard adopts whatever already
-- carries it. The post-check below is what stops that being a hole: it reads
-- the constraint's own definition and requires the only values named in it to
-- be 'report' and 'auto', so a same-named constraint that admits a third is a
-- failure rather than something this file silently keeps.
DO $m336c$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'bug_reports_kind_known'
                      AND conrelid = 'bug_reports'::regclass) THEN
        ALTER TABLE bug_reports ADD CONSTRAINT bug_reports_kind_known
            CHECK (kind IN ('report', 'auto'));
    END IF;
END $m336c$;

-- Two questions are asked of this column, both with a time bound: "which auto
-- rows are older than the retention window" (the sweep) and "which report rows
-- are new" (the feed and the admin list). One composite index serves both. The
-- second index is the per-steam bucket the auto route counts against:
-- (steam_id, kind) with the timestamp, so the 24 h count is an index-only
-- range and does not walk a player's whole report history.
--
-- Built in-transaction and therefore NOT CONCURRENTLY, which holds SHARE on
-- bug_reports for the build -- writers wait, readers do not. The table is a
-- few thousand player-filed rows, so that is milliseconds, and CONCURRENTLY is
-- not available inside the BEGIN/COMMIT this file needs (#340).
--
-- Guarded on the catalog for the same reason as the column above, and not
-- because the guard and `IF NOT EXISTS` decide differently: they decide
-- identically, on the name alone. `CREATE INDEX IF NOT EXISTS` also takes its
-- SHARE lock before it looks, so a re-run used to stop every WRITER to
-- bug_reports for as long as it queued. Which columns the surviving index is
-- actually over is not this guard's question and never was -- the post-check
-- below reads pg_get_indexdef and the catalog beside it, which is what
-- catches a same-named index over the wrong columns, or a UNIQUE or partial
-- one over the right ones.
DO $m336idx$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                     JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = current_schema()
                      AND c.relname = 'idx_bug_reports_kind_created') THEN
        CREATE INDEX idx_bug_reports_kind_created
            ON bug_reports (kind, created_at DESC);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_class c
                     JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = current_schema()
                      AND c.relname = 'idx_bug_reports_steam_kind_created') THEN
        CREATE INDEX idx_bug_reports_steam_kind_created
            ON bug_reports (steam_id, kind, created_at DESC);
    END IF;
END $m336idx$;

-- Post-check: assert the END STATE, not that the statements above parsed.
DO $m336$
DECLARE
    v_default TEXT;
    v_notnull BOOLEAN;
    v_unlabelled BIGINT;
    v_def TEXT;
    v_unique BOOLEAN;
    v_partial BOOLEAN;
    v_admitted BOOLEAN;
BEGIN
    SELECT column_default, (is_nullable = 'NO')
      INTO v_default, v_notnull
      FROM information_schema.columns
     WHERE table_schema = current_schema()
       AND table_name = 'bug_reports' AND column_name = 'kind';

    IF v_default IS NULL THEN
        RAISE EXCEPTION '336: bug_reports.kind is absent or has no default; the auto-upload route would insert rows the report feed cannot distinguish';
    END IF;
    -- column_default renders as 'report'::character varying, so the test is
    -- on the literal at the head and not a substring anywhere in it.
    IF v_default NOT LIKE '''report''%' THEN
        RAISE EXCEPTION '336: bug_reports.kind defaults to % and not to ''report''; every new player-filed report would be mislabelled', v_default;
    END IF;
    IF NOT v_notnull THEN
        RAISE EXCEPTION '336: bug_reports.kind is nullable; a NULL row matches neither the report feed nor the auto retention sweep';
    END IF;

    -- Every row carries a value the two consumers recognise. Stated as a
    -- membership test and NOT as "every row is 'report'": on the first run
    -- that is the same assertion, but this file could be re-applied after the
    -- auto route has landed rows, and a post-check that fails on a legitimate
    -- re-run is a trap rather than a guarantee.
    SELECT COUNT(*) INTO v_unlabelled FROM bug_reports WHERE kind IS NULL OR kind NOT IN ('report', 'auto');
    IF v_unlabelled > 0 THEN
        RAISE EXCEPTION '336: % bug_reports row(s) carry a kind that is neither ''report'' nor ''auto''; such a row is announced by nothing and collected by nothing', v_unlabelled;
    END IF;

    -- THE DEFINITION, NOT THE NAME. `CREATE INDEX IF NOT EXISTS` keeps
    -- whatever index already carries the name, whatever columns it is over,
    -- so a name-only check passes for ever over an index on the wrong
    -- columns or in the wrong order -- a check that cannot fail (#342/#441).
    -- pg_get_indexdef is compared on its column list, and UNIQUENESS and the
    -- presence of a WHERE clause are read from the catalog beside it. The
    -- column list alone is not the whole identity of an index: `CREATE UNIQUE
    -- INDEX ... (kind, created_at DESC)` and `CREATE INDEX ... (kind,
    -- created_at DESC) WHERE kind = 'report'` both match the pattern and
    -- neither is what this file creates. The unique one makes two auto
    -- uploads that land on the same created_at an INSERT failure on a live
    -- route; the partial one indexes a subset, and the subset that would
    -- still serve the sweep is not a thing this check can tell apart from the
    -- subset that would not -- so ANY predicate is refused, because this file
    -- writes none.
    SELECT pg_get_indexdef(i.indexrelid), i.indisunique, (i.indpred IS NOT NULL)
      INTO v_def, v_unique, v_partial
      FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = current_schema() AND c.relname = 'idx_bug_reports_kind_created';
    IF v_def IS NULL THEN
        RAISE EXCEPTION '336: idx_bug_reports_kind_created is missing; the retention sweep would seq-scan bug_reports';
    END IF;
    IF v_def NOT LIKE '%(kind, created_at DESC)%' THEN
        RAISE EXCEPTION '336: idx_bug_reports_kind_created exists but is defined as %, not over (kind, created_at DESC); the retention sweep would not use it', v_def;
    END IF;
    IF v_unique THEN
        RAISE EXCEPTION '336: idx_bug_reports_kind_created is UNIQUE (%); two auto uploads sharing a created_at would fail to insert', v_def;
    END IF;
    IF v_partial THEN
        RAISE EXCEPTION '336: idx_bug_reports_kind_created carries a WHERE clause (%); it covers only part of the table, so the retention sweep''s range scan is not served for the rows outside it', v_def;
    END IF;

    SELECT pg_get_indexdef(i.indexrelid), i.indisunique, (i.indpred IS NOT NULL)
      INTO v_def, v_unique, v_partial
      FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = current_schema() AND c.relname = 'idx_bug_reports_steam_kind_created';
    IF v_def IS NULL THEN
        RAISE EXCEPTION '336: idx_bug_reports_steam_kind_created is missing; the per-steam auto bucket would seq-scan bug_reports';
    END IF;
    IF v_def NOT LIKE '%(steam_id, kind, created_at DESC)%' THEN
        RAISE EXCEPTION '336: idx_bug_reports_steam_kind_created exists but is defined as %, not over (steam_id, kind, created_at DESC); the per-steam auto bucket would not use it', v_def;
    END IF;
    IF v_unique THEN
        RAISE EXCEPTION '336: idx_bug_reports_steam_kind_created is UNIQUE (%); a player''s second upload in the same instant would fail to insert', v_def;
    END IF;
    IF v_partial THEN
        RAISE EXCEPTION '336: idx_bug_reports_steam_kind_created carries a WHERE clause (%); the 24 h count would not be served for the rows outside it', v_def;
    END IF;

    -- The CHECK constraint: guarded creation keeps a same-named constraint it
    -- did not write, so what that constraint DOES is asserted here.
    --
    -- ASSERTED BY BEHAVIOUR, NOT BY READING THE DEFINITION. Two earlier forms
    -- of this check both read the text and both had the same hole in
    -- different sizes. The first asked whether 'report' and 'auto' were
    -- PRESENT, which `CHECK (kind IN ('report','auto','legacy'))` satisfies.
    -- The second -- this one's immediate predecessor -- asked that the only
    -- quoted values ANYWHERE in the definition were exactly those two, which
    -- is narrower and still not the question: `CHECK (kind <> 'report' OR
    -- kind <> 'auto')` quotes exactly those two literals, is a tautology, and
    -- admits every third value there is (Codex wave B/C r2, MEDIUM). A
    -- predicate's literals are not its logic, and no amount of parsing the
    -- rendered text gets from one to the other.
    --
    -- So the constraint is EXERCISED instead. A temp table is created LIKE
    -- bug_reports INCLUDING CONSTRAINTS -- PostgreSQL copies the CHECK
    -- expression itself, so this is the real predicate and not a restatement
    -- of it -- and three rows are offered to it: a third kind, which it must
    -- REFUSE, and both real kinds, which it must ACCEPT. The second half is
    -- the control: without it a constraint that refused everything would pass
    -- the first half and look correct (#391).
    --
    -- Nothing touches bug_reports. The probe table is ON COMMIT DROP, and
    -- bug_number is supplied explicitly so the real bug-number sequence is
    -- never advanced by a migration re-run.
    --
    -- THE PROBE VALUE MUST FIT THE COLUMN, and this is not a detail: kind is
    -- VARCHAR(16) and the value first written here was nineteen characters.
    -- PostgreSQL refused it as string_data_right_truncation, which is not
    -- check_violation, so the handler below did not catch it and the whole
    -- migration aborted -- found by running it, not by reading it. The
    -- general form is worth more than the fix: a probe the column TYPE
    -- refuses never reaches the predicate it claims to test, and had that
    -- error been caught as a refusal it would have "passed" this check for a
    -- reason having nothing to do with the constraint (#342). The value is
    -- now thirteen characters, and a truncation is caught and re-raised
    -- saying precisely that, so narrowing the column or lengthening the probe
    -- reports a probe that proves nothing rather than a constraint that looks
    -- checked.
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conname = 'bug_reports_kind_known' AND conrelid = 'bug_reports'::regclass;
    IF v_def IS NULL THEN
        RAISE EXCEPTION '336: bug_reports_kind_known is missing; a typo''d kind would be announced by nothing and collected by nothing';
    END IF;

    CREATE TEMP TABLE m336_kind_probe
        (LIKE bug_reports INCLUDING DEFAULTS INCLUDING CONSTRAINTS) ON COMMIT DROP;

    -- 1. A third kind must be refused.
    v_admitted := TRUE;
    BEGIN
        INSERT INTO m336_kind_probe (steam_id, description, kind, bug_number)
             VALUES ('0', '336 post-check probe', '__m336_nope__', -1);
    EXCEPTION
        WHEN check_violation THEN
            v_admitted := FALSE;
        WHEN string_data_right_truncation THEN
            RAISE EXCEPTION '336: the post-check probe value does not fit bug_reports.kind, so the column type refused it before bug_reports_kind_known was ever consulted -- this probe proves nothing until the value is shortened or the column widened';
    END;
    IF v_admitted THEN
        RAISE EXCEPTION '336: bug_reports_kind_known is defined as % and ADMITS a third kind -- its literals look right and its logic is not. This column has exactly two consumers, the report feed and the retention sweep, and a value neither of them knows is a row announced by nothing and collected by nothing', v_def;
    END IF;

    -- 2. THE CONTROL: both real kinds must still be accepted, or the check
    --    above passed because the constraint refuses everything.
    BEGIN
        INSERT INTO m336_kind_probe (steam_id, description, kind, bug_number)
             VALUES ('0', '336 post-check control', 'report', -2),
                    ('0', '336 post-check control', 'auto', -3);
    EXCEPTION WHEN check_violation THEN
        RAISE EXCEPTION '336: bug_reports_kind_known is defined as % and REFUSES its own two values; every insert on this table would fail', v_def;
    END;

    DROP TABLE m336_kind_probe;

    RAISE NOTICE '336: bug_reports.kind present, NOT NULL, default ''report''; % row(s) report, % auto; both indexes present',
        (SELECT COUNT(*) FROM bug_reports WHERE kind = 'report'),
        (SELECT COUNT(*) FROM bug_reports WHERE kind = 'auto');
END $m336$;

COMMIT;
