-- 350_bug_reports_auto_number.sql
--
-- Automatic uploads stop spending human bug numbers (v1.41.0 Item 3 hotfix,
-- 2026-09-20).
--
-- THE DEFECT THIS CLOSES. `bug_reports.bug_number` is
-- `NOT NULL DEFAULT nextval('bug_reports_number_seq')` with a unique index
-- (086_bug_report_number.sql:33). The automatic post-match upload added by
-- 336 writes an ordinary `bug_reports` row and did NOT supply that column, so
-- every automatic upload drew the next number from the same counter that
-- names a player's ticket in #bug-reports, in the admin list and in the ops
-- `bug-log:N` verb. Retention (14 days, auto rows only) then deleted the rows
-- and a sequence never rewinds.
--
-- One opted-in seat at the 12-per-24h cap takes ~168 numbers a fortnight.
-- The visible result is a player being told their report is #1,247 while the
-- last number anybody recognises is #310, with ~900 numbers in between that
-- name nothing and `bug-log:N` answering "not found" for every one of them.
-- To the person reading it that is indistinguishable from data loss, and it
-- cannot be undone.
--
-- THE FIX, IN TWO PARTS.
--
--   1. A SECOND SEQUENCE, DESCENDING. `bug_reports_auto_number_seq` starts at
--      -1 and steps by -1. Automatic rows draw from it; the unique index is
--      satisfied because the two ranges cannot meet; and the human counter is
--      never touched. A negative number is also self-describing at a glance --
--      336's own post-check already uses negative bug_numbers for exactly
--      that reason, so the convention is not new here.
--
--   2. A ONE-DIRECTIONAL CHECK. `kind <> 'auto' OR bug_number < 0` constrains
--      automatic rows ONLY. It says nothing about a report row, so it cannot
--      refuse any row that exists today and cannot refuse anything the bug
--      form writes tomorrow. That direction is deliberate: the constraint's
--      job is to make "an automatic upload never took a human number" a
--      property of the schema rather than a claim in a comment (#302), and a
--      constraint that also policed the human side would be a second, weaker
--      copy of what 086's sequence already guarantees.
--
-- WHY A NEW FILE AND NOT AN EDIT TO 336. The deploy wrapper applies a
-- migration once BY FILE NAME, so whichever copy of a file reaches a database
-- first is the only one that will ever run there; editing 336 in place would
-- have left the wave B/C lane's own copy permanently unapplied. So this is a
-- separate file, and it rides the same sql-only precursor commit.
--
-- AND THE TWO COPIES OF 336 ARE NOT BYTE-IDENTICAL, WHICH THIS FILE USED TO
-- GUARANTEE THEY WERE. The hotfix copy is 22,384 bytes; the lane's is 19,445;
-- they agree up to line 216 and diverge at 217, where the post-check was
-- rebuilt to OFFER rows to the CHECK rather than read the constraint's
-- rendered text. The hotfix copy is a strict SUPERSET: both create the same
-- three objects -- the `kind` column, its `bug_reports_kind_known` CHECK and
-- its `'report'` default -- and only the self-verification differs. Lane
-- adoption of this copy is filed in the notes (section 9).
--
-- SO THIS FILE DOES NOT DEPEND ON WHICH COPY RAN. Its precondition below asks
-- for the three OBJECTS by name and refuses by name when one is missing,
-- rather than assuming a file. A guarantee about bytes was the wrong shape:
-- it could not be checked from inside a migration, it was false, and the
-- thing that actually matters to this file is the schema it inherits (#302,
-- #351).
--
-- NUMBERING (#553). The v1.41.0 lane has reserved 330-344 across its item
-- briefs -- 336 and 337 in the tree, 338/339/340/341/342/343/344 in the
-- briefs, several of them twice over. 350 is clear of all of it with room to
-- spare. If the lane later wants 350, THIS file is the one that renumbers:
-- it is unshipped until the hotfix deploys, and the lane's briefs are older.
--
-- EVERY GUARD IN THIS FILE IS SCOPED TO current_schema(). The preconditions
-- used to read `information_schema.columns` with no schema predicate, so on a
-- database carrying a second accessible schema that also holds
-- `bug_reports.kind` they could read one relation while the ALTER statements
-- changed another -- admitting a drifted target because the other schema was
-- correct, and refusing a correct target because the other had drifted. The
-- unqualified name every statement here uses is now resolved once, required
-- to be the relation in `current_schema()`, and every lookup -- the object
-- guard, the default guard and the executable post-check -- is bound to that
-- one relation. If the two disagree the file REFUSES and names the remedy.
--
-- ORDER: 336 FIRST, THEN THIS FILE, THEN THE API. This file names `kind`, so
-- it cannot be applied before 336; sorted order gives that for free, and the
-- guard below says so out loud rather than failing as a bare UndefinedColumn.
--
-- WRITERS AND READERS (#346):
--   WRITER  auto_logs.upload_auto_log   supplies bug_number from
--                                       bug_reports_auto_number_seq
--   READER  main.list_bug_reports       shows bug_number in admin triage
--   READER  main.get_bug_report         shows it in the detail pane
--   READER  main.submit_bug_report      returns the HUMAN number it was given
--                                       by the default -- unchanged, and the
--                                       whole point of this file
--   READER  the ops `bug-log:N` verb    looks a ticket up by that number
--
-- BOTH MIXED WINDOWS (#477):
--   * THIS FILE APPLIED, OLD CODE STILL RUNNING -- entirely safe, and it is
--     the state the two-SHA order passes through on purpose. The old code has
--     no automatic upload path at all, so it writes no kind='auto' row and
--     the CHECK is never consulted. The bug form is untouched.
--   * NEW CODE AGAINST A DATABASE WITHOUT THIS FILE -- the automatic INSERT
--     names a sequence that does not exist, raises UndefinedObject, and the
--     handler's existing arm discards the blob and answers 503. The client
--     half treats 503 as retried-next-match. Player-filed reports are
--     unaffected because they never touch this sequence. Degraded in the
--     conservative direction, not broken -- but still the wrong order, and
--     the release train applies migrations before code for this reason.

BEGIN;

-- ── guard: the SHAPE 336 leaves must already be here, object by object ───────
--
-- ASKED FOR BY OBJECT, NOT BY FILE. Two copies of 336 exist (see the header)
-- and they differ in their self-verification only, so "did 336 run" is not a
-- question this file can answer and not the question it needs answered. What
-- it needs is the three objects its own CHECK and its own handler are written
-- against, and each one is named separately so a partial shape says WHICH
-- part is missing instead of failing later as a bare UndefinedColumn or, in
-- the default's case, not failing at all until a row arrives.
DO $m350g$
DECLARE
    v_default text;
    v_target  oid;
    v_schema  text;
    -- EXACTLY what 336 leaves, and nothing else. 336 declares
    -- `kind VARCHAR(16) NOT NULL DEFAULT 'report'`, which PostgreSQL renders
    -- in information_schema.columns.column_default as this string. It is
    -- written out here so the comparison below is an equality against a value
    -- this file names, rather than a pattern that a drifted default can
    -- satisfy by accident.
    c_336_default CONSTANT text := '''report''::character varying';
BEGIN
    -- ── THE RELATION THIS FILE WILL ACTUALLY ALTER ───────────────────────
    --
    -- RESOLVED ONCE, AND EVERY GUARD BELOW IS SCOPED TO IT. These checks
    -- used to read `information_schema.columns` with no schema predicate at
    -- all, so on a database carrying a SECOND accessible schema that also
    -- holds a `bug_reports.kind` the row they read was whichever one the
    -- catalogue happened to return. That is a guard inspecting one relation
    -- while the DDL below alters another: a drifted default on the target
    -- passes because the other schema's is correct, and a correct target is
    -- refused because the other schema's has drifted. Both directions are
    -- rehearsed against a database carrying two such schemas.
    --
    -- The unqualified name is what every statement in this file uses, so it
    -- is what is resolved here -- and it is then REQUIRED to be the relation
    -- in `current_schema()`, which is what the scoped lookups below read.
    -- If the two disagree this file refuses rather than altering a table its
    -- guards never looked at; the remedy is one line and the message says it
    -- (#276 -- the unhandled case refuses).
    v_target := to_regclass('bug_reports');
    IF v_target IS NULL THEN
        RAISE EXCEPTION '350: no relation named bug_reports is visible on the search_path (current_schema() is %), so neither the guards below nor the DDL in this file has a target. Apply 336_bug_reports_kind.sql to this database first', current_schema();
    END IF;
    SELECT n.nspname INTO v_schema
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.oid = v_target;
    IF v_schema IS DISTINCT FROM current_schema() THEN
        RAISE EXCEPTION '350: the unqualified name bug_reports resolves to %.bug_reports while current_schema() is %, so the guards in this file and its ALTER statements would not be looking at the same relation. Put the schema that owns bug_reports first on the path (SET search_path TO %) and apply this file again', v_schema, current_schema(), v_schema;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'bug_reports' AND column_name = 'kind'
    ) THEN
        RAISE EXCEPTION '350: bug_reports.kind is missing from schema %, so the shape 336 installs is not on this database. Apply 336_bug_reports_kind.sql first; this file constrains the automatic rows that column identifies', current_schema();
    END IF;

    -- The CHECK. Without it `kind` is a free-text column: 'auto' would carry
    -- no meaning the schema enforces, and this file's own constraint --
    -- `kind <> 'auto' OR bug_number < 0` -- would be written against a value
    -- anything at all could hold.
    -- ON THE RESOLVED OID, not on a second resolution of the name: the
    -- object guard and the default guard have to be about the one relation
    -- established above.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'bug_reports_kind_known'
           AND conrelid = v_target
    ) THEN
        RAISE EXCEPTION '350: %.bug_reports.kind exists but the bug_reports_kind_known CHECK does not, so the column admits any string and kind = ''auto'' is not a fact the schema enforces. Apply 336_bug_reports_kind.sql (either copy) before this file', current_schema();
    END IF;

    -- The DEFAULT. Every row written by code that does not name the column --
    -- which is every row the bug form writes on the deploy's old-code half --
    -- relies on it to land as 'report'. Without it such a row takes NULL, and
    -- a NULL kind passes this file's CHECK for free: `NULL <> 'auto'` is NULL,
    -- `NULL OR false` is NULL, and a CHECK that evaluates to NULL ADMITS the
    -- row. So a missing default does not fail loudly here -- it makes the
    -- human/automatic split a thing the schema no longer enforces, quietly.
    --
    -- EQUALITY AGAINST 336's EXACT RENDERING, NEVER A SUBSTRING. This test
    -- used to be `NOT LIKE '%report%'`, which is satisfied by any default
    -- merely CONTAINING that word -- `'auto_report'::character varying`,
    -- `'reported'::character varying`, a function call whose text mentions it.
    -- A drifted default of that shape passed this guard, and then every
    -- old-code bug-form INSERT during the migration-before-code window landed
    -- a `kind` this file's CHECK does not recognise. What this file needs is
    -- not "something reportish"; it is the one value 336 installs, because
    -- that is the value the CHECK below and the handler are written against.
    -- So the comparison is `IS DISTINCT FROM` -- which is also how a NULL
    -- default (no default at all) is refused by the same line.
    --
    -- AND ON THE TARGET SCHEMA'S ROW. Without `table_schema` this SELECT
    -- INTO takes whichever `bug_reports.kind` the catalogue returns first,
    -- which on a database with a second accessible schema is not necessarily
    -- the column the ALTER statements below will constrain (R3-M1).
    SELECT column_default INTO v_default
      FROM information_schema.columns
     WHERE table_schema = current_schema()
       AND table_name = 'bug_reports' AND column_name = 'kind';
    IF v_default IS DISTINCT FROM c_336_default THEN
        RAISE EXCEPTION '350: bug_reports.kind must carry exactly the default 336 installs, %, and it reads % instead. A default that merely mentions ''report'' is not the same fact: rows written by code that does not name the column would take a value this file''s CHECK was not written against. Apply 336_bug_reports_kind.sql (either copy), or repair the default with ALTER TABLE bug_reports ALTER COLUMN kind SET DEFAULT ''report'', before this file', c_336_default, COALESCE(v_default, 'NULL');
    END IF;
END $m350g$;

-- ── 1. the descending sequence automatic rows draw from ──────────────────────
--
-- EVERY UNQUALIFIED NAME FROM HERE ON IS THE CURRENT SCHEMA'S, and that is a
-- fact the guard above established rather than an assumption: it refused
-- unless the unqualified `bug_reports` resolves inside `current_schema()`.
-- So this sequence is created beside the table it is owned by, and the ALTER
-- statements below constrain the column the guard inspected.
--
-- MINVALUE is -9223372036854775807, which is the configured floor and is what
-- the shape block below asserts. It is ONE ABOVE the bigint floor
-- (-9223372036854775808) and is written here as the value it is rather than
-- as "the full bigint floor", because a comment that is one off from the DDL
-- under it is the kind of claim a check then gets written against (#302).
-- Nothing turns on the difference: at the published cap of 12 uploads per
-- account per day this range outlasts any plausible life of this table by a
-- margin there is no point writing down.
CREATE SEQUENCE IF NOT EXISTS bug_reports_auto_number_seq
    AS bigint
    INCREMENT BY -1
    START WITH -1
    MAXVALUE -1
    MINVALUE -9223372036854775807
    NO CYCLE;

-- ── 1b. the shape this file is willing to adopt ──────────────────────────────
--
-- BEFORE ANYTHING ELSE TOUCHES THE SEQUENCE, and that placement is the point.
-- CREATE SEQUENCE IF NOT EXISTS keeps a pre-existing sequence of the WRONG
-- shape silently, so on a database where an earlier hand created something
-- else under this name, the statement above did nothing and every line below
-- runs against that other sequence.
--
-- Checking only the increment, and then spending two draws, admits a sequence
-- that descends and is unusable for every other reason: `START -1 INCREMENT -1
-- MINVALUE -2 MAXVALUE -1 NO CYCLE` passes both -- the two draws spend -1 and
-- -2 -- and then EVERY real upload fails at `nextval` and answers 503 with
-- nothing in the log naming this file. A range of two, a cycling sequence that
-- would hand -1 out twice into a UNIQUE index, an `integer` sequence that
-- stops four billion rows early, and a start outside its own range all behave
-- the same way: the migration reports success and the feature cannot write.
-- (Every attribute here is CONFIGURATION. Where the sequence currently IS --
-- a RESTART or a setval moves that without touching any of them -- is block
-- 1c's question, asked under the lock the ALTER SEQUENCE below takes.)
--
-- AND A START INSIDE THE RANGE IS NOT THE SAME FACT AS THE CONFIGURED START.
-- `IN RANGE` was the whole of the start question here until round 6, and it
-- admits `START WITH -9223372036854775806` -- one above MINVALUE, inside the
-- range, internally consistent, and every other attribute exact. That
-- sequence survives `OWNED BY`, and the two draws the post-check spends are
-- the last two values it holds: the first real upload after this file reports
-- success answers 503 and stays that way. The range test
-- and the identity test are two different questions, so this block asks
-- both, in that order -- the range one first, because it is the one whose
-- message can name the range, and the identity one after it, so that an
-- out-of-range start still gets the refusal written for it rather than the
-- generic one.
--
-- WHY HERE AND NOT IN THE POST-CHECK, where these six lines were first
-- written: `ALTER SEQUENCE ... OWNED BY` below re-validates the whole
-- sequence, so a catalogue row whose START sits outside its own range is
-- refused THERE, by PostgreSQL, with `START value (5) cannot be greater than
-- MAXVALUE (-1)` -- a message that names neither this file nor the repair,
-- and one that made that arm of the post-check unreachable. The other five
-- shapes survive that line, because their rows are internally consistent, and
-- were then refused only after this file had added a CHECK constraint over a
-- sequence it was about to refuse. Asserting the shape first makes all six
-- refusals this file's own, and each one NAMES the attribute it is about --
-- a single "the sequence is wrong" refusal is one an operator cannot act on.
-- The literals restate the DDL above: that is the specification.
DO $m350s$
DECLARE
    v_typid     oid;
    v_start     bigint;
    v_increment bigint;
    v_max       bigint;
    v_min       bigint;
    v_cycle     boolean;
    -- THE CONFIGURED SHAPE, restating the CREATE SEQUENCE above. These are
    -- the values this file installs, so they are also the values it must
    -- refuse to adopt a different sequence over.
    c_auto_increment CONSTANT bigint := -1;
    c_auto_max       CONSTANT bigint := -1;
    c_auto_min       CONSTANT bigint := -9223372036854775807;
    c_auto_start     CONSTANT bigint := -1;
    -- SCOPED LIKE THE GUARD ABOVE, for the same reason (R3-M1).
    v_autoseq CONSTANT regclass :=
        to_regclass(quote_ident(current_schema()) || '.bug_reports_auto_number_seq');
BEGIN
    IF v_autoseq IS NULL THEN
        RAISE EXCEPTION '350: schema % does not carry bug_reports_auto_number_seq after the CREATE above, so there is no shape to inspect', current_schema();
    END IF;

    SELECT seqtypid, seqstart, seqincrement, seqmax, seqmin, seqcycle
      INTO v_typid, v_start, v_increment, v_max, v_min, v_cycle
      FROM pg_sequence
     WHERE seqrelid = v_autoseq;

    IF v_typid IS DISTINCT FROM 'bigint'::regtype::oid THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq exists in schema % with data type %, not bigint; its range would run out while bug_reports.bug_number can still hold the number, and every upload past that point would 503', current_schema(), format_type(v_typid, NULL);
    END IF;
    IF v_increment IS DISTINCT FROM c_auto_increment THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq exists in schema % with increment %, not %; a sequence that does not descend by one hands out numbers into the human range, which the CHECK this file adds below then refuses -- 503s with no explanation', current_schema(), v_increment, c_auto_increment;
    END IF;
    IF v_max IS DISTINCT FROM c_auto_max THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq exists in schema % with MAXVALUE %, not %; the ceiling is what keeps every automatic number negative and out of the human range', current_schema(), v_max, c_auto_max;
    END IF;
    IF v_min IS DISTINCT FROM c_auto_min THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq exists in schema % with MINVALUE %, not %; the range this file configures is what makes exhaustion something nobody has to think about, and a shorter one exhausts into a 503 on every upload', current_schema(), v_min, c_auto_min;
    END IF;
    IF v_cycle THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq exists in schema % and CYCLES; on exhaustion it would hand out a number it has already given away, and bug_reports.bug_number is UNIQUE, so the upload would fail on the index instead of on the counter', current_schema();
    END IF;
    IF v_start < v_min OR v_start > v_max THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq exists in schema % starting at %, which is outside its own range % .. %; a restart would put it there and the next draw would fail', current_schema(), v_start, v_min, v_max;
    END IF;
    -- THE START, BY IDENTITY AND NOT BY RANGE. The test above answers "could
    -- this sequence be restarted at all"; this one answers "is this the
    -- sequence this file configures". They differ over every value strictly
    -- inside the range, and the ones near MINVALUE are the expensive half:
    -- exact in type, increment, ceiling, floor and cycle, in range, and two
    -- draws from the end of a counter this file exists to make nobody think
    -- about. Kept BELOW the range test so that test keeps the case it was
    -- written for and this one is reached only by a start that is usable and
    -- still not ours (#342).
    --
    -- SINCE ROUND 7 THE EXPENSIVE HALF HAS A SECOND GATE: a fresh sequence's
    -- next value IS its start, so block 1c refuses a start near MINVALUE again
    -- by POSITION. This line still decides the rest -- a start of -2, say,
    -- which 1c's floor admits -- because a sequence configured to begin
    -- anywhere but -1 is not the one this file configures, and a RESTART with
    -- no value returns it to that start rather than to -1.
    IF v_start IS DISTINCT FROM c_auto_start THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq exists in schema % starting at %, not %; it is inside its own range, so it draws, but a sequence configured to begin somewhere else was set up by something other than this file, and a RESTART with no value returns it to %, not to %. Near MINVALUE that start is also a short distance from exhaustion; anywhere else it is still not the sequence this file configures', current_schema(), v_start, c_auto_start, v_start, c_auto_start;
    END IF;

    -- WHAT THIS BLOCK JUDGED, handed to block 1c. Everything above is about
    -- how the sequence is CONFIGURED; where it currently IS is 1c's question,
    -- asked under the lock the ALTER SEQUENCE below takes. 1c re-reads this
    -- catalogue row under that lock and refuses unless it is this reading, so
    -- the shape adopted and the position adopted are one reading of one
    -- sequence. Transaction-local: nothing of it outlives COMMIT.
    PERFORM set_config('m350.shape_1b',
                       format('%s/%s/%s/%s/%s/%s', v_typid, v_start,
                              v_increment, v_max, v_min, v_cycle),
                       true);
END $m350s$;

-- Owned by the column, so DROP TABLE cleans it up -- the same relationship
-- 086 set up for the human sequence. A column may own more than one sequence;
-- this adds a second pg_depend edge and changes nothing about the first.
--
-- AND IT TAKES THE LOCK THE ADOPTION IS DECIDED UNDER. ALTER SEQUENCE locks
-- the sequence in ShareRowExclusiveLock and holds it to COMMIT; `nextval`
-- takes RowExclusiveLock, which conflicts with it. So from this statement to
-- the end of the file no other session can draw from the sequence, and its
-- position moves only by the post-check's own two draws. Block 1c reads the
-- position under this lock and refuses unless it holds it.
ALTER SEQUENCE bug_reports_auto_number_seq OWNED BY bug_reports.bug_number;

-- ── 1c. the position this file is willing to adopt ──────────────────────────
--
-- 1b judges what the sequence is CONFIGURED to do and nothing in it reads
-- where the sequence currently IS. `ALTER SEQUENCE ... RESTART` and `setval()`
-- move the position without touching one attribute 1b asserts, so an exact
-- `START -1` sequence restarted at MINVALUE + 1 passes every line of 1b, the
-- post-check spends its last two values, the file commits, and the first real
-- upload answers 503. So the position is read here -- `last_value` and
-- `is_called`, from the sequence relation itself -- and judged BEFORE anything
-- draws from it.
--
-- UNDER THE LOCK, AND PROVEN TO BE: the block refuses unless pg_locks shows
-- this backend holding a granted mode on the sequence that blocks nextval.
-- The shape is re-read under the same lock and must equal 1b's reading.
--
-- THE BOUND: the next value must be at or above -4611686018427387904 (-2^62),
-- so that at least 2^62 values -- half the configured range -- remain.
--   * Function: 2^62 values is the same order of guarantee a fresh sequence
--     gives, which is the property that makes exhaustion something nobody has
--     to think about (the MINVALUE assertion in 1b). A smaller floor is a
--     number somebody would have to watch.
--   * Provenance: at the published cap of 12 uploads per account per day, a
--     million accounts all at the cap spend about 4.4e9 numbers a year, so
--     reaching the midpoint BY USE takes about a billion years. A position
--     past it was put there by a restart or a setval -- the same question
--     1b's identity test asks of START, and refused for the same reason.
--
-- AND A POSITION THE WRITER CAN CONTINUE FROM. bug_number is UNIQUE (086), so
-- a position whose next values are already held by rows -- a restart back to
-- -1 over rows already numbered -1, -2, ... -- hands the writer a unique
-- violation for each of them. That is refused by name as well.
DO $m350n$
DECLARE
    v_typid     oid;
    v_start     bigint;
    v_increment bigint;
    v_max       bigint;
    v_min       bigint;
    v_cycle     boolean;
    v_shape     text;
    v_last      bigint;
    v_called    boolean;
    v_next      bigint;
    v_held      bigint;
    -- THE ADOPTION FLOOR, -2^62. The block comment above says why this value.
    c_floor CONSTANT bigint := -4611686018427387904;
    -- SCOPED LIKE THE GUARDS, for the same reason (R3-M1).
    v_autoseq CONSTANT regclass :=
        to_regclass(quote_ident(current_schema()) || '.bug_reports_auto_number_seq');
BEGIN
    IF v_autoseq IS NULL THEN
        RAISE EXCEPTION '350: schema % does not carry bug_reports_auto_number_seq, so there is no position to read', current_schema();
    END IF;

    -- A mode that conflicts with nextval's RowExclusiveLock, held by THIS
    -- backend and granted. If an edit ever moves this block above the ALTER
    -- SEQUENCE that takes it, this is what refuses.
    IF NOT EXISTS (
        SELECT 1 FROM pg_locks
         WHERE locktype = 'relation'
           AND relation = v_autoseq::oid
           AND pid = pg_backend_pid()
           AND granted
           AND mode IN ('ShareLock', 'ShareRowExclusiveLock',
                        'ExclusiveLock', 'AccessExclusiveLock')
    ) THEN
        RAISE EXCEPTION '350: this transaction holds no lock on bug_reports_auto_number_seq in schema % that blocks nextval, so the position read below could move before COMMIT; ALTER SEQUENCE ... OWNED BY takes that lock and must run before this block', current_schema();
    END IF;

    SELECT seqtypid, seqstart, seqincrement, seqmax, seqmin, seqcycle
      INTO v_typid, v_start, v_increment, v_max, v_min, v_cycle
      FROM pg_sequence
     WHERE seqrelid = v_autoseq;
    v_shape := format('%s/%s/%s/%s/%s/%s', v_typid, v_start, v_increment,
                      v_max, v_min, v_cycle);
    IF v_shape IS DISTINCT FROM current_setting('m350.shape_1b', true) THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq in schema % reads as % under the lock, but block 1b judged %; the sequence this file would adopt is not the one it checked', current_schema(), v_shape, coalesce(current_setting('m350.shape_1b', true), '(no reading)');
    END IF;

    -- `is_called` false: the next draw returns `last_value` itself (a fresh
    -- sequence, or one just restarted). True: it returns `last_value` plus
    -- the increment. At MINVALUE with is_called true that is one below the
    -- range -- still a bigint, because MINVALUE is one above the type floor.
    EXECUTE format('SELECT last_value, is_called FROM %I.bug_reports_auto_number_seq',
                   current_schema())
       INTO v_last, v_called;
    v_next := CASE WHEN v_called THEN v_last + v_increment ELSE v_last END;

    IF v_next < c_floor THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq in schema % would hand out % next (last_value %, is_called %), below the adoption floor %: fewer than 2^62 of its % .. % range remain, and uploads cannot have spent that many, so a restart or a setval put it there and every upload past its end answers 503. Move it with ALTER SEQUENCE bug_reports_auto_number_seq RESTART WITH a value at or above the floor and below every negative bug_number in use, then apply this file again', current_schema(), v_next, v_last, v_called, c_floor, v_min, v_max;
    END IF;

    EXECUTE format('SELECT max(bug_number) FROM %I.bug_reports WHERE bug_number <= $1',
                   current_schema())
       INTO v_held
      USING v_next;
    IF v_held IS NOT NULL THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq in schema % would hand out % next, but bug_reports already holds bug number % at or below it; bug_number is UNIQUE, so the writer would draw into a number that is taken and that upload would fail. Move it with ALTER SEQUENCE bug_reports_auto_number_seq RESTART WITH a value below every negative bug_number in use, then apply this file again', current_schema(), v_next, v_held;
    END IF;

    -- Handed to the post-check, whose FIRST DRAW must return exactly this:
    -- the reading is bound to the thing it describes (#732).
    PERFORM set_config('m350.next_1c', v_next::text, true);
END $m350n$;

-- ── 2. the one-directional CHECK ─────────────────────────────────────────────
--
-- ADD CONSTRAINT has no IF NOT EXISTS, so re-runnability is a catalogue
-- lookup rather than a swallowed exception: swallowing duplicate_object here
-- would also swallow a constraint that exists under this name with a
-- DIFFERENT definition, which is the one case worth failing on.
DO $m350c$
DECLARE
    v_strays bigint;
    -- THE SAME RELATION THE GUARD BLOCK INSPECTED, named the same way. A
    -- second resolution of a bare name is a second chance to reach a
    -- different schema's table, so it is qualified here (R3-M1).
    v_target CONSTANT oid := to_regclass(quote_ident(current_schema()) || '.bug_reports');
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'bug_reports_auto_number_negative'
           AND conrelid = v_target
    ) THEN
        -- ADD CONSTRAINT validates the existing rows, so an automatic row
        -- already holding a human number would abort this migration with a
        -- bare check_violation naming a constraint nobody has heard of. Say
        -- it plainly instead, and say what to do. On production today the
        -- count is zero because production has no automatic upload path at
        -- all -- this arm is for a database where one already ran.
        EXECUTE format('SELECT COUNT(*) FROM %I.bug_reports '
                       'WHERE kind = ''auto'' AND bug_number >= 0',
                       current_schema())
           INTO v_strays;
        IF v_strays > 0 THEN
            RAISE EXCEPTION '350: % automatic row(s) already hold a non-negative bug number. Renumber them onto bug_reports_auto_number_seq (UPDATE bug_reports SET bug_number = nextval(''bug_reports_auto_number_seq'') WHERE kind = ''auto'' AND bug_number >= 0) before applying this file; adding the constraint over them would abort with an unexplained check violation', v_strays;
        END IF;

        ALTER TABLE bug_reports
            ADD CONSTRAINT bug_reports_auto_number_negative
            CHECK (kind <> 'auto' OR bug_number < 0);
    END IF;
END $m350c$;

-- ── 3. post-check, exercised rather than read ────────────────────────────────
--
-- The same discipline 336 arrived at after two false starts: reading a
-- constraint's rendered text tells you which literals it quotes, not what it
-- admits. So the predicate is OFFERED rows, and every refusal it must make is
-- paired with an acceptance it must not refuse (#391).
DO $m350p$
DECLARE
    v_def       text;
    v_admitted  boolean;
    v_human_before bigint;
    v_human_after  bigint;
    v_a         bigint;
    v_b         bigint;
    v_autos     bigint;
    -- The sequence's catalogue row, re-read here FOR THE CLOSING NOTICE.
    -- Block 1b is where it is asserted attribute by attribute; this block
    -- reads the same row so the line an operator sees states the shape this
    -- file ran against.
    v_typid     oid;
    v_start     bigint;
    v_increment bigint;
    v_max       bigint;
    v_min       bigint;
    v_cycle     boolean;
    -- NO c_auto_* CONSTANTS HERE. They were declared in this block when the
    -- shape assertions lived in it, and round 5 moved those assertions to
    -- block 1b without taking the declarations with them. What was left was
    -- three named values carrying a comment that said this block refuses a
    -- sequence over them, which it does not do and must not start doing: 1b
    -- runs before anything touches the sequence, and a second copy of the
    -- same literals here would be a specification in two places (#351).
    -- SCOPED LIKE THE GUARDS, for the same reason: a post-check that offers
    -- rows to one schema's constraint while the ALTER above installed it on
    -- another proves nothing about the database this file just changed
    -- (R3-M1). Each name is resolved inside `current_schema()` once.
    v_target CONSTANT oid := to_regclass(quote_ident(current_schema()) || '.bug_reports');
    v_autoseq CONSTANT regclass :=
        to_regclass(quote_ident(current_schema()) || '.bug_reports_auto_number_seq');
    v_humanseq CONSTANT regclass :=
        to_regclass(quote_ident(current_schema()) || '.bug_reports_number_seq');
BEGIN
    IF v_target IS NULL OR v_autoseq IS NULL OR v_humanseq IS NULL THEN
        RAISE EXCEPTION '350: schema % does not carry all three of bug_reports, bug_reports_auto_number_seq and bug_reports_number_seq after this file ran, so its post-check has nothing to exercise', current_schema();
    END IF;
    -- The human sequence's position, read BEFORE anything else in this block.
    -- The last assertion compares it with the position afterwards: the whole
    -- point of this migration is that automatic numbering stops moving this
    -- counter, and a post-check that advanced it itself would be a poor
    -- advertisement for that. 336 learned the same thing -- its probe supplies
    -- bug_number explicitly so a re-run cannot advance the human sequence.
    EXECUTE format('SELECT last_value FROM %s', v_humanseq::text)
       INTO v_human_before;

    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conname = 'bug_reports_auto_number_negative'
       AND conrelid = v_target;
    IF v_def IS NULL THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_negative is missing; nothing would stop an automatic upload from taking a human bug number again';
    END IF;

    -- The shape was asserted attribute by attribute in its own block above,
    -- before anything in this file touched the sequence. What is read here
    -- is the same catalogue row, for the closing NOTICE only -- so that the
    -- line an operator sees states the shape this file ran against rather
    -- than the shape it configured and hoped for.
    SELECT seqtypid, seqstart, seqincrement, seqmax, seqmin, seqcycle
      INTO v_typid, v_start, v_increment, v_max, v_min, v_cycle
      FROM pg_sequence
     WHERE seqrelid = v_autoseq;


    -- And that it actually yields descending negatives. Two draws, because a
    -- single one cannot show a direction. They are what proves the shape
    -- above is a working sequence and not only a well-formed catalogue row.
    -- These two numbers are spent by the check -- which is exactly the
    -- difference between this sequence and the human one: a gap here names
    -- nothing and nobody reads it, which is the property being installed.
    v_a := nextval(v_autoseq);
    v_b := nextval(v_autoseq);
    IF NOT (v_a < 0 AND v_b < v_a) THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq yielded % then %, which is not a descending negative run', v_a, v_b;
    END IF;
    -- AND THE FIRST DRAW IS THE POSITION 1c ADOPTED. 1c read it under the
    -- lock this transaction still holds; any other first value means the
    -- reading judged something other than what the sequence continues from.
    IF v_a IS DISTINCT FROM current_setting('m350.next_1c', true)::bigint THEN
        RAISE EXCEPTION '350: the first draw from bug_reports_auto_number_seq returned % but block 1c read the next value as %; the position this file judged is not the one the sequence continues from', v_a, coalesce(current_setting('m350.next_1c', true), '(no reading)');
    END IF;

    -- FROM THE TARGET RELATION, named explicitly. `LIKE bug_reports` takes
    -- whichever one the search_path resolves, and the probe below would then
    -- be offering rows to a constraint this file never installed.
    EXECUTE format('CREATE TEMP TABLE m350_number_probe (LIKE %s INCLUDING '
                   'DEFAULTS INCLUDING CONSTRAINTS) ON COMMIT DROP',
                   v_target::regclass::text);

    -- 1. An automatic row carrying a HUMAN-RANGE number must be refused. This
    --    is the defect itself, offered to the constraint.
    v_admitted := TRUE;
    BEGIN
        INSERT INTO m350_number_probe (steam_id, description, kind, bug_number)
             VALUES ('0', '350 post-check probe', 'auto', 999000001);
    EXCEPTION
        WHEN check_violation THEN
            v_admitted := FALSE;
    END;
    IF v_admitted THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_negative is defined as % and ADMITS an automatic row holding a positive bug number -- the counter players read by number is still being spent by machine uploads', v_def;
    END IF;

    -- 2. CONTROL A: an automatic row with a negative number must be ACCEPTED,
    --    or the refusal above passed because the constraint refuses every
    --    automatic row and the feature cannot write at all.
    BEGIN
        INSERT INTO m350_number_probe (steam_id, description, kind, bug_number)
             VALUES ('0', '350 post-check control', 'auto', -999000001);
    EXCEPTION WHEN check_violation THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_negative is defined as % and REFUSES a correctly numbered automatic row; every automatic upload would 503', v_def;
    END;

    -- 3. CONTROL B: the human side is untouched. A report row with an ordinary
    --    positive number must be accepted -- if this ever fails, the bug form
    --    is down and this file did it.
    BEGIN
        INSERT INTO m350_number_probe (steam_id, description, kind, bug_number)
             VALUES ('0', '350 post-check control', 'report', 999000002);
    EXCEPTION WHEN check_violation THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_negative is defined as % and REFUSES an ordinary player-filed report; no player could file a bug report', v_def;
    END;

    DROP TABLE m350_number_probe;

    EXECUTE format('SELECT last_value FROM %s', v_humanseq::text)
       INTO v_human_after;
    IF v_human_after <> v_human_before THEN
        RAISE EXCEPTION '350: this migration advanced the human bug-number sequence from % to %, which is the exact thing it exists to stop', v_human_before, v_human_after;
    END IF;

    EXECUTE format('SELECT COUNT(*) FROM %s WHERE kind = ''auto''',
                   v_target::regclass::text)
       INTO v_autos;
    -- EVERY ATTRIBUTE IN THIS LINE IS THE ONE THAT WAS READ, not a literal
    -- beside a variable. The type and the cycle flag used to be spelled out
    -- as `bigint` and `NO CYCLE` while `v_typid` and `v_cycle` were selected
    -- and never used; block 1b does refuse anything else, so the sentence was
    -- true -- but a line an operator reads as a measurement has to be one
    -- (#732), and a variable read into and never used is where the next
    -- untrue one starts.
    RAISE NOTICE '350: in schema %, bug_reports_auto_number_seq is %, increment %, range % .. %, cycle %, starting at %, adopted at next value % (read under the lock by block 1c), and descends (% then %); the CHECK refuses a positive automatic number and accepts both controls; human sequence unmoved at %; % automatic row(s) present, all negative by construction',
        current_schema(), format_type(v_typid, NULL), v_increment, v_min, v_max, v_cycle, v_start, current_setting('m350.next_1c', true), v_a, v_b, v_human_after, v_autos;
END $m350p$;

COMMIT;
