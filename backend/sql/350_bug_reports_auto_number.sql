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
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'bug_reports' AND column_name = 'kind'
    ) THEN
        RAISE EXCEPTION '350: bug_reports.kind is missing, so the shape 336 installs is not on this database. Apply 336_bug_reports_kind.sql first; this file constrains the automatic rows that column identifies';
    END IF;

    -- The CHECK. Without it `kind` is a free-text column: 'auto' would carry
    -- no meaning the schema enforces, and this file's own constraint --
    -- `kind <> 'auto' OR bug_number < 0` -- would be written against a value
    -- anything at all could hold.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'bug_reports_kind_known'
           AND conrelid = 'bug_reports'::regclass
    ) THEN
        RAISE EXCEPTION '350: bug_reports.kind exists but the bug_reports_kind_known CHECK does not, so the column admits any string and kind = ''auto'' is not a fact the schema enforces. Apply 336_bug_reports_kind.sql (either copy) before this file';
    END IF;

    -- The DEFAULT. Every row written by code that does not name the column --
    -- which is every row the bug form writes on the deploy's old-code half --
    -- relies on it to land as 'report'. Without it such a row takes NULL, and
    -- a NULL kind passes this file's CHECK for free: `NULL <> 'auto'` is NULL,
    -- `NULL OR false` is NULL, and a CHECK that evaluates to NULL ADMITS the
    -- row. So a missing default does not fail loudly here -- it makes the
    -- human/automatic split a thing the schema no longer enforces, quietly.
    SELECT column_default INTO v_default
      FROM information_schema.columns
     WHERE table_name = 'bug_reports' AND column_name = 'kind';
    IF v_default IS NULL OR v_default NOT LIKE '%report%' THEN
        RAISE EXCEPTION '350: bug_reports.kind has no ''report'' default (it reads %), so a writer that does not name the column leaves it NULL and the human/automatic split is not enforced. Apply 336_bug_reports_kind.sql (either copy) before this file', COALESCE(v_default, 'NULL');
    END IF;
END $m350g$;

-- ── 1. the descending sequence automatic rows draw from ──────────────────────
--
-- MINVALUE is the full bigint floor, so the range is not a limit anybody has
-- to think about: at the published cap of 12 uploads per account per day it
-- outlasts any plausible life of this table by a margin there is no point
-- writing down.
CREATE SEQUENCE IF NOT EXISTS bug_reports_auto_number_seq
    AS bigint
    INCREMENT BY -1
    START WITH -1
    MAXVALUE -1
    MINVALUE -9223372036854775807
    NO CYCLE;

-- Owned by the column, so DROP TABLE cleans it up -- the same relationship
-- 086 set up for the human sequence. A column may own more than one sequence;
-- this adds a second pg_depend edge and changes nothing about the first.
ALTER SEQUENCE bug_reports_auto_number_seq OWNED BY bug_reports.bug_number;

-- ── 2. the one-directional CHECK ─────────────────────────────────────────────
--
-- ADD CONSTRAINT has no IF NOT EXISTS, so re-runnability is a catalogue
-- lookup rather than a swallowed exception: swallowing duplicate_object here
-- would also swallow a constraint that exists under this name with a
-- DIFFERENT definition, which is the one case worth failing on.
DO $m350c$
DECLARE
    v_strays bigint;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'bug_reports_auto_number_negative'
           AND conrelid = 'bug_reports'::regclass
    ) THEN
        -- ADD CONSTRAINT validates the existing rows, so an automatic row
        -- already holding a human number would abort this migration with a
        -- bare check_violation naming a constraint nobody has heard of. Say
        -- it plainly instead, and say what to do. On production today the
        -- count is zero because production has no automatic upload path at
        -- all -- this arm is for a database where one already ran.
        SELECT COUNT(*) INTO v_strays
          FROM bug_reports WHERE kind = 'auto' AND bug_number >= 0;
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
BEGIN
    -- The human sequence's position, read BEFORE anything else in this block.
    -- The last assertion compares it with the position afterwards: the whole
    -- point of this migration is that automatic numbering stops moving this
    -- counter, and a post-check that advanced it itself would be a poor
    -- advertisement for that. 336 learned the same thing -- its probe supplies
    -- bug_number explicitly so a re-run cannot advance the human sequence.
    SELECT last_value INTO v_human_before FROM bug_reports_number_seq;

    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conname = 'bug_reports_auto_number_negative'
       AND conrelid = 'bug_reports'::regclass;
    IF v_def IS NULL THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_negative is missing; nothing would stop an automatic upload from taking a human bug number again';
    END IF;

    -- THE SEQUENCE'S SHAPE, asserted from the catalogue rather than assumed.
    -- CREATE SEQUENCE IF NOT EXISTS keeps a pre-existing sequence of the WRONG
    -- shape silently, so on a database where some earlier hand created an
    -- ascending sequence under this name every automatic row would take a
    -- POSITIVE number, collide with the human range, and be refused by the
    -- CHECK above -- 503s with no explanation. Checking the increment is what
    -- makes this file's re-run tell the difference (#342).
    IF (SELECT seqincrement FROM pg_sequence
         WHERE seqrelid = 'bug_reports_auto_number_seq'::regclass) >= 0 THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq exists but does not descend (increment %), so it would hand out positive numbers into the human range', (SELECT seqincrement FROM pg_sequence WHERE seqrelid = 'bug_reports_auto_number_seq'::regclass);
    END IF;

    -- And that it actually yields descending negatives. Two draws, because a
    -- single one cannot show a direction. These two numbers are spent by the
    -- check -- which is exactly the difference between this sequence and the
    -- human one: a gap here names nothing and nobody reads it, which is the
    -- property being installed.
    v_a := nextval('bug_reports_auto_number_seq');
    v_b := nextval('bug_reports_auto_number_seq');
    IF NOT (v_a < 0 AND v_b < v_a) THEN
        RAISE EXCEPTION '350: bug_reports_auto_number_seq yielded % then %, which is not a descending negative run', v_a, v_b;
    END IF;

    CREATE TEMP TABLE m350_number_probe
        (LIKE bug_reports INCLUDING DEFAULTS INCLUDING CONSTRAINTS) ON COMMIT DROP;

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

    SELECT last_value INTO v_human_after FROM bug_reports_number_seq;
    IF v_human_after <> v_human_before THEN
        RAISE EXCEPTION '350: this migration advanced the human bug-number sequence from % to %, which is the exact thing it exists to stop', v_human_before, v_human_after;
    END IF;

    RAISE NOTICE '350: bug_reports_auto_number_seq descends (% then %); the CHECK refuses a positive automatic number and accepts both controls; human sequence unmoved at %; % automatic row(s) present, all negative by construction',
        v_a, v_b, v_human_after,
        (SELECT COUNT(*) FROM bug_reports WHERE kind = 'auto');
END $m350p$;

COMMIT;
