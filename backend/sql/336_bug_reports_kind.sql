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

-- UNCONDITIONAL WORK, NAMED: FOUR statements in this file touch a relation
-- from outside every guard block, and each of them runs unconditionally on
-- every re-application. They are named here because a reader who has seen
-- the guards otherwise concludes a re-run issues nothing at all:
--
--   * `COMMENT ON COLUMN` on bug_reports.kind -- re-sets the comment to the
--     same text. A re-run writes what the first run wrote: the text is a
--     literal in this file.
--   * `DROP TABLE IF EXISTS` on pg_temp.m336_expected_probe -- the
--     post-check's cleanup of its own probe, below. It is qualified to THIS
--     session's temporary schema, so it can reach no relation other than the
--     one the next statement creates; on a session that has never made a
--     temporary table it reports that the schema does not exist and carries
--     on.
--   * `CREATE TEMP TABLE` pg_temp.m336_expected_probe -- the post-check
--     writes this file's own CHECK predicate over a throwaway column of the
--     live column's type and reads back what the catalog makes of it, rather
--     than comparing against a rendering typed out here. The table is
--     session-local and `ON COMMIT DROP`, takes no lock on bug_reports, and
--     does not outlive the transaction.
--   * `ALTER TABLE` pg_temp.m336_expected_probe -- the predicate itself, put
--     on that temporary table. Safe on a re-run for the same reason: the
--     only relation it can name is the one created immediately above, which
--     each run makes fresh.
--
-- Every schema statement that touches bug_reports itself -- the ADD COLUMN,
-- the SET DEFAULT, the CHECK constraint and both indexes -- is guarded on the
-- catalog. (The file's `BEGIN`, `SET LOCAL lock_timeout` and `COMMIT` are
-- outside the guards too and are not what this is about -- none of them
-- touches a relation.)
--
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
-- the constraint's own definition and requires it to BE the definition this
-- statement produces -- not to contain the right literals, which a predicate
-- admitting every value on earth can also do. A same-named constraint whose
-- body is anything else is a failure rather than something this file silently
-- keeps.
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
    v_values TEXT[];
    v_coltype TEXT;
    -- The rendering this file's own `CHECK (kind IN ('report', 'auto'))`
    -- produces, DERIVED below by writing that exact predicate in a throwaway
    -- scope and reading `pg_get_constraintdef` back off it.
    --
    -- Derived rather than written out, because the rendering is not a
    -- property of the predicate alone: it is a property of the predicate AND
    -- the column's type. Over `character varying` PostgreSQL renders `IN` as
    -- `((kind)::text = ANY ((ARRAY[...])::text[]))` with a per-element
    -- `::character varying` cast; over `text` it renders
    -- `(kind = ANY (ARRAY[...::text]))` with no outer cast at all.
    --
    -- The literal below was measured over the VARCHAR(16) column this file
    -- ADDS -- and the `ADD COLUMN` above is guarded on EXISTENCE, so the
    -- column measured against is not always the column this file adds. The
    -- default guard thirty lines up says so in as many words: "a hand-added
    -- or partially-applied column". Over a pre-existing `text` kind, a
    -- hardcoded varchar rendering refuses the constraint this file's own
    -- ADD CONSTRAINT wrote seconds earlier, reports that the name was adopted
    -- from a constraint this file did not write -- which is false in that
    -- state -- and prints a remedy, DROP CONSTRAINT and re-run, that cannot
    -- converge, because the re-run writes the same body again. Measured on
    -- PostgreSQL 16.9.
    v_expected TEXT;
    -- KEPT, and it is now the cross-check rather than the answer. A
    -- derivation compared against nothing is a check that cannot fail: if it
    -- ever stopped writing this file's own predicate, it and the catalog
    -- would agree with each other and with nothing else (#342). So over a
    -- `character varying` column -- the type this file itself adds, and the
    -- one every ordinary deployment of it has -- the derived string must
    -- equal this independently measured one, or the file refuses.
    v_expected_varchar CONSTANT TEXT :=
        'CHECK (((kind)::text = ANY ((ARRAY[''report''::character varying, ''auto''::character varying])::text[])))';
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

    -- The column's own type, read from the catalog rather than assumed. It is
    -- an INPUT to the constraint comparison at the bottom of this block
    -- rather than a requirement of its own. Both consumers spell their
    -- predicate `kind = 'report'` / `kind = 'auto'`, which a `text` column
    -- serves exactly as a `character varying` one does, so a difference
    -- between those two is not on its own a reason to refuse. Stated as
    -- narrowly as it is implemented: the only type this file rejects is one
    -- its own `CHECK (kind IN ('report', 'auto'))` cannot be written over at
    -- all, and that rejection is raised where it happens, below. What this
    -- block refuses is a constraint BODY that is not the one this file
    -- writes, and that comparison has to be made in the rendering this
    -- column produces.
    SELECT format_type(a.atttypid, a.atttypmod) INTO v_coltype
      FROM pg_attribute a
     WHERE a.attrelid = 'bug_reports'::regclass
       AND a.attname = 'kind' AND a.attnum > 0 AND NOT a.attisdropped;

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

    -- The CHECK constraint, read the same way and read WHOLE. Guarded
    -- creation adopts a same-named constraint it did not write, so this is
    -- the only reader of its BODY.
    --
    -- WHAT IS ASSERTED: the definition the catalog renders for the surviving
    -- constraint is, after whitespace collapsing, the definition the catalog
    -- renders for the constraint this file writes. Two weaker readings were
    -- tried here first, and each one is a check that cannot fail for the case
    -- its own message names (#342/#441):
    --
    --   * asking whether 'report' and 'auto' APPEAR in the definition admits
    --     `CHECK (kind IN ('report','auto','legacy'))`;
    --   * asking whether the quoted values are EXACTLY {auto, report} admits
    --     `CHECK (kind <> 'report' OR kind <> 'auto')`, which carries those
    --     two literals and no others. No value equals both at once, so one
    --     disjunct always holds and the predicate is TRUE for every non-null
    --     value -- and this column is NOT NULL, so that is every value it can
    --     hold. A constraint that enforces nothing, adopted by name, and then
    --     announced as the one this column has.
    --
    -- The set of literals is a property of how a predicate is SPELLED; what
    -- this column needs is a property of what the predicate ADMITS, and the
    -- only predicate whose admitted set is known here is the one this file's
    -- own ADD CONSTRAINT writes. So the whole definition is compared, and the
    -- expected string is a measurement of that statement rather than a
    -- restatement of the rule (see v_expected, and the derivation below it).
    --
    -- The cost of exactness is that a logically equivalent constraint spelled
    -- differently -- `CHECK (kind = 'report' OR kind = 'auto')` -- is refused
    -- as well. That is the deliberate direction and not an oversight: there
    -- is no equivalence oracle for an arbitrary predicate, the refusal prints
    -- both definitions so the difference is visible, and the remedy is one
    -- DROP CONSTRAINT and a re-run. A file that adopts a body it cannot
    -- reason about is the failure this is written against.
    --
    -- THAT REMEDY CONVERGES, and the claim is scoped to the refusal that
    -- prints it -- the body comparison below, which is the only place that
    -- says DROP CONSTRAINT. It holds because the string compared against is
    -- derived from this file's own predicate over THIS column, so the body a
    -- re-run writes is the body the re-run then expects. A hardcoded
    -- rendering is what broke it: over a pre-existing `text` kind the file
    -- refused the constraint it had just written, and DROP-and-re-run
    -- reproduced the refusal for ever. The two other exceptions raised near
    -- here print their own remedies and neither is a DROP: an unwritable
    -- column type, and a derivation that has drifted from the measurement it
    -- is cross-checked against.
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conname = 'bug_reports_kind_known' AND conrelid = 'bug_reports'::regclass;
    IF v_def IS NULL THEN
        RAISE EXCEPTION '336: bug_reports_kind_known is missing; a typo''d kind would be announced by nothing and collected by nothing';
    END IF;
    -- Diagnostic only, for the message below: the quoted literals are what a
    -- reader looks at first, and on the tautology named above they are
    -- exactly the two expected ones, which is the confusing part worth
    -- printing beside the definition itself.
    SELECT COALESCE(array_agg(DISTINCT m[1] ORDER BY m[1]), ARRAY[]::TEXT[])
      INTO v_values
      FROM regexp_matches(v_def, '''([^'']*)''', 'g') AS m;
    -- DERIVE the expected rendering: write this file's own predicate over a
    -- throwaway column of the SAME type and read back what the catalog makes
    -- of it. The temp table is dropped at COMMIT, is visible to this session
    -- only, and takes no lock on bug_reports -- the lock discipline the rest
    -- of this file is written to is untouched by it.
    --
    -- The predicate below is a COPY of the one the ADD CONSTRAINT above
    -- writes, and the two have to be edited together; the whole point of the
    -- comparison is lost if they drift. `test_336_accepts_the_constraint_it_
    -- writes_itself` and its `text` sibling are what catch that drift, in
    -- both directions and against a live cluster.
    -- Dropped first rather than assumed absent: the name is fixed, so a
    -- session that already carries one would otherwise fail the CREATE and be
    -- reported below as a column-type problem, which it would not be.
    --
    -- AND EVERY NAME BELOW IS QUALIFIED `pg_temp.`, WHICH IS WHAT MAKES THAT
    -- DROP SAFE TO ISSUE. Unqualified, the name resolves against the search
    -- path the deploy happens to be running under; a database holding an
    -- ordinary table called `m336_expected_probe` would have that one
    -- resolved here, and this DROP would delete it and COMMIT the deletion
    -- with the rest of the file. `pg_temp` names THIS session's temporary
    -- schema and nothing else, so the only relation these statements can
    -- reach is the one this block creates itself. A session that has not yet
    -- made a temporary table has no such schema, and the DROP answers
    -- `schema "pg_temp" does not exist, skipping` and carries on -- measured
    -- on 16.9, because the alternative would be an exception caught by the
    -- handler below and reported as a column-type problem.
    BEGIN
        EXECUTE 'DROP TABLE IF EXISTS pg_temp.m336_expected_probe';
        EXECUTE format(
            'CREATE TEMP TABLE pg_temp.m336_expected_probe (kind %s) ON COMMIT DROP',
            v_coltype);
        EXECUTE 'ALTER TABLE pg_temp.m336_expected_probe
                     ADD CONSTRAINT m336_expected_probe_body
                     CHECK (kind IN (''report'', ''auto''))';
    EXCEPTION WHEN others THEN
        -- The type is CONTEXT here, not a diagnosis. This handler catches
        -- whatever any of the statements above raises, and the commonest
        -- cause -- a `kind` of some type this file's predicate cannot be
        -- written over -- is a guess about the error, not a reading of it. So
        -- the error itself is printed and named as the authority.
        RAISE EXCEPTION '336: could not derive the expected constraint rendering for a bug_reports.kind of type %. PostgreSQL said: %. That derivation writes this file''s own CHECK (kind IN (''report'', ''auto'')) on a temporary table of the same type, so the likeliest cause is a column whose type that predicate cannot be written over -- this file adds it as VARCHAR(16). Read the message above before assuming so.', v_coltype, SQLERRM;
    END;
    SELECT btrim(regexp_replace(pg_get_constraintdef(oid), '\s+', ' ', 'g'))
      INTO v_expected
      FROM pg_constraint
     WHERE conname = 'm336_expected_probe_body'
       AND conrelid = 'pg_temp.m336_expected_probe'::regclass;

    -- The derivation, held to the independently measured literal on the type
    -- this file itself adds. Without this the derivation would be its own
    -- authority and could not disagree with anything (#342).
    IF v_coltype LIKE 'character varying%' AND v_expected <> v_expected_varchar THEN
        RAISE EXCEPTION '336: over a % column this file''s own CHECK (kind IN (''report'', ''auto'')) now renders as %, and the rendering measured when this file was written is %. The two disagree, so the comparison below is no longer measuring what it says it measures -- re-measure it on this cluster before trusting either.', v_coltype, v_expected, v_expected_varchar;
    END IF;

    IF btrim(regexp_replace(v_def, '\s+', ' ', 'g')) <> v_expected THEN
        RAISE EXCEPTION '336: bug_reports_kind_known is defined as % (quoted values %), and the constraint this file writes over a % column renders as % -- so the surviving constraint is not the one this file writes, and what it ADMITS is unknown here. This column has exactly two consumers: the report feed selects kind = ''report'' and the retention sweep selects kind = ''auto'', so any value outside those two is a row announced by nothing and collected by nothing. DROP CONSTRAINT bug_reports_kind_known and re-run this file.', v_def, v_values, v_coltype, v_expected;
    END IF;

    RAISE NOTICE '336: bug_reports.kind present as %, NOT NULL, default ''report''; % row(s) report, % auto; both indexes present',
        v_coltype,
        (SELECT COUNT(*) FROM bug_reports WHERE kind = 'report'),
        (SELECT COUNT(*) FROM bug_reports WHERE kind = 'auto');
END $m336$;

COMMIT;
