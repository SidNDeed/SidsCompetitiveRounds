-- 332_pc_edition_schedule.sql
--
-- Player Cards editions become seasonal (v1.41.0, item 7): four months
-- each, ending on the 21st of December, April and August at 00:00 UTC.
-- Edition 1 ends when winter starts -- 2026-12-21 00:00 UTC, the solstice
-- (Sid's call, 2026-09-18). That date is the SERIES SEED rather than a
-- literal the file writes: a first application before it lands assigns it
-- exactly, and one after it lands assigns the next boundary on the same
-- four-month cadence instead of refusing. See the UPDATE below.
--
-- NUMBERING. The highest file in main is 325; 322/323 exist only on
-- claude/wave2-level-rewards and 330-339 are reserved for this batch, of
-- which this file takes 332 (learning #553: a number is taken from a
-- census of backend/sql, never from the branch's own base).
--
-- WHAT THIS ADDS. One nullable column on pc_editions:
--
--   ends_at_planned -- when this edition is SCHEDULED to end. NULL means
--                      no schedule, and the api's rollover leaves such a
--                      row alone forever. That is the safe direction: a
--                      missing schedule stops the clock rather than
--                      rolling the edition early (learning #276).
--
-- The schedule lives here, in data, and not in the api: moving a boundary
-- is one UPDATE on one row and needs no deploy.
--
-- WHO WRITES IT. `_pc_edition_rollover`, inside the Player Cards janitor
-- step in backend/api/main.py. On the first pass at or after
-- ends_at_planned it closes the open row (ended_at = now()) and inserts the
-- successor carrying the next anchor -- the incumbent's planned end plus
-- four months, repeated until that lands in the future, so a rollover that
-- runs late still lands on the 21st. The same statement queues the Discord
-- notice in pending_channel_posts. Nothing else in the backend has ever
-- written pc_editions: before this, its only writer anywhere was the seed
-- INSERT in 308_player_cards.sql:36.
--
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND, AND THAT IS MANDATORY.
-- -----------------------------------------------------------------------
-- In the batch's standard form, so the order can be read off every file in
-- the same place instead of inferred from prose. Mandatory here because the
-- new api's boot-time janitor EXPLAIN sweep parses the rollover statement
-- against the live schema and REPORTS A FAILURE when `ends_at_planned` is
-- absent -- a boot-path signal, not a first-request one. The reverse state
-- (this file applied while the old api still runs) is entirely safe and is
-- what the two-SHA order passes through: the column is nullable with no
-- default and the old code never names it.
--
-- SAFE TO RUN BEFORE THE API, AND IT MUST BE. The column is nullable with
-- no default, so every current reader and writer of pc_editions is
-- untouched -- the one application reference today is the mint path's
-- `SELECT id FROM pc_editions WHERE ended_at IS NULL ... FOR SHARE`. Apply
-- this file first and deploy the api second: the api's boot-time janitor
-- EXPLAIN sweep parses the rollover statement against the live schema and
-- reports it as a failure if the column is missing.
--
-- NOTHING ROLLS TODAY, and that is the negative control for this file:
-- 2026-12-21 is three months out, so on a FIRST application pc_editions must
-- still show exactly one open row, with a schedule, still in the future --
-- which is precisely what the DO block at the bottom asserts on that path.
--
-- ON A RE-RUN it asserts only the one-open-edition invariant and REPORTS the
-- rest, because this file writes nothing on a re-run and every state it could
-- then find is lawful: an unscheduled (NULL) edition is an operator who
-- stopped the clock, and a past boundary is a rollover that has not ticked
-- yet. A post-check that failed on either would be a trap rather than a
-- guarantee. An earlier version asserted the first-run conditions on every
-- path, which is why re-applying this file after the boundary passed would
-- have aborted for a reason unconnected to the database it was running
-- against.
--
-- It deliberately does NOT assert "and that row is Edition 1". The UPDATE
-- below is guarded on ended_at IS NULL exactly so it does not assume id 1,
-- and a post-check that did assume it would contradict the statement it is
-- checking. started_at is untouched because the UPDATE's SET list contains
-- one column -- a property you can read off this file, not a runtime claim.
-- An earlier version of this comment said the block asserted both.
--
-- UNCONDITIONAL WORK, NAMED: outside every guard block this file issues a
-- `CREATE TEMP TABLE`, a `COMMENT ON COLUMN` and an `UPDATE`, and all three
-- STATEMENTS are issued unconditionally on each re-application rather than
-- guarded away. A header that lists what it guards and then stops invites the
-- opposite reading, which is the whole reason this paragraph is here.
--
-- THE LIST IS DERIVED, NOT REMEMBERED. An earlier version of this sentence
-- named two of the three and read as exhaustive. The one it left out is the
-- `CREATE TEMP TABLE _m332_state` below -- which runs outside every guard,
-- creates a relation and queries `information_schema` -- and the check that
-- was meant to cover this paragraph matched a fixed list of keywords that did
-- not include that verb, so the sentence and the check agreed with each other
-- and neither agreed with the file. The disclosure check in
-- `test_migration_headers` parses this file now and reds if it issues a kind
-- this paragraph does not name.
--
-- What each of them WRITES on a re-run is a second question, and the three
-- answers differ. The `CREATE TEMP TABLE` really does run every time: it
-- creates a session-local relation, fills it from `information_schema` and
-- drops it at COMMIT, so nothing in the schema or the data this database
-- serves is touched and nothing outside this transaction can see it. The
-- `COMMENT ON COLUMN` really does re-set the comment, to the same text, every
-- time. The `UPDATE` is gated in SQL rather than by a catalog guard --
-- `WHERE ended_at IS NULL AND ends_at_planned IS NULL AND NOT
-- already_applied` -- so on any re-run it matches no row and writes nothing.
--
-- IT STILL TAKES A LOCK, AND THIS PARAGRAPH USED TO SAY IT DID NOT. "Locks
-- nothing" attributed to the WHERE clause a property the WHERE clause does
-- not have: the lock is requested on the relation before the predicate is
-- evaluated, so a predicate that matches no row does not stop it being
-- acquired. Measured on PostgreSQL 16.9 rather than reasoned, and kept in
-- `ai-collab/lock-probe-zero-row-update.log`: an `UPDATE` with this file's
-- own WHERE plus `AND NOT true` reports `UPDATE 0` and leaves
-- `RowExclusiveLock granted=True` on the relation. What makes that harmless
-- is which locks CONFLICT, which is the framing 336's header uses for the
-- same question: ROW EXCLUSIVE conflicts with neither an ordinary reader nor
-- an ordinary writer, and in this file the `COMMENT ON COLUMN` above has
-- already taken the stronger SHARE UPDATE EXCLUSIVE on the same relation
-- (measured in the same run), so the UPDATE's request is covered by a lock
-- this transaction already holds and can queue behind nothing the COMMENT did
-- not already queue behind. A reader carrying "a no-match UPDATE locks
-- nothing" to a file without that preceding COMMENT would conclude it cannot
-- be stopped by a concurrent holder; under the `SET LOCAL lock_timeout` above
-- that is a re-run that aborts.
--
-- Both are therefore no-ops by VALUE and by row version, which is what the
-- fingerprint checks in `test_migration_reruns` measure; neither statement is
-- SKIPPED, which is what this paragraph is disclosing.

BEGIN;
SET LOCAL lock_timeout = '5s';

-- HAS THIS FILE RUN BEFORE? Captured BEFORE the ADD COLUMN below, because the
-- column's absence is the only first-run marker available -- this repo keeps
-- no migrations ledger. Everything that SEEDS DATA is gated on it, because
-- re-seeding data is destructive in the way the next paragraph describes.
--
-- The ADD COLUMN below is gated too -- separately, on the catalog, and for a
-- different reason: not what it writes but what it LOCKS. (The COMMENT is
-- not: its lock is stronger than a read's and conflicts with neither an
-- ordinary reader nor an ordinary writer, which is what re-running this file
-- under each of those, separately, measures. The constraint below was already
-- guarded before any of this, for the plainer reason it states itself:
-- PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS, so an unguarded re-run
-- would ERROR rather than merely lock. Issuing nothing takes no lock either,
-- which is why the ADD COLUMN was the only statement in this file that needed
-- changing.) `ALTER TABLE ...
-- ADD COLUMN IF NOT EXISTS` takes its ACCESS EXCLUSIVE lock on the relation
-- BEFORE it evaluates the IF NOT EXISTS, so that spelling is a no-op only in
-- what it writes -- it still queues behind every reader already open and
-- holds every new one behind it while it waits, and with the lock_timeout
-- above a re-run on a live primary aborts rather than waits. Measured on
-- PostgreSQL 16.9 rather than reasoned: with one ordinary
-- `SELECT count(*) FROM pc_editions` open in another session, a second
-- application of this file in its previous spelling died with "canceling
-- statement due to lock timeout". `test_a_second_run_takes_no_blocking_lock`
-- holds that lock and re-applies this file.
--
-- The seed has to be one-shot for a reason that is not tidiness. NULL is a
-- SUPPORTED, MEANINGFUL value here: it says "this edition is unscheduled",
-- the rollover never touches such a row, and clearing the schedule is exactly
-- how an operator stops the clock. A re-run that writes the anchor wherever
-- it finds NULL cannot tell that state from a fresh install, so it silently
-- RE-ARMS an edition somebody deliberately stopped -- the one failure this
-- column's own NULL semantics exist to make possible.
CREATE TEMP TABLE _m332_state ON COMMIT DROP AS
SELECT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'pc_editions'
                  AND column_name = 'ends_at_planned') AS already_applied;

DO $m332col$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_attribute
                  WHERE attrelid = 'pc_editions'::regclass
                    AND attname = 'ends_at_planned'
                    AND NOT attisdropped) THEN
    ALTER TABLE pc_editions ADD COLUMN ends_at_planned TIMESTAMPTZ;
  END IF;
END $m332col$;

-- The rollover walks the anchor forward in four-month steps with
-- generate_series(1, 1000) -- 333 years 4 months. Past that the scalar
-- subquery returns NULL and the successor is minted PERMANENTLY UNSCHEDULED,
-- because the rollover never touches a row with no schedule: the edition
-- chain stops, silently, and no statement errors. Bounding the column below
-- makes the step limit unreachable instead of widening it, and rejects the
-- nonsense value at the write that introduces it rather than at a rollover
-- months later. A static floor, because a CHECK cannot call now().
-- Guarded rather than plain ADD CONSTRAINT: PostgreSQL has no
-- IF NOT EXISTS there, and this file must stay re-runnable.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'pc_editions_planned_sane'
                    AND conrelid = 'pc_editions'::regclass) THEN
    ALTER TABLE pc_editions ADD CONSTRAINT pc_editions_planned_sane CHECK (ends_at_planned IS NULL OR ends_at_planned > TIMESTAMPTZ '2000-01-01');
  END IF;
END $$;

COMMENT ON COLUMN pc_editions.ends_at_planned IS
    'When this edition is scheduled to end. NULL = unscheduled, and the janitor''s rollover never touches such a row. A successor gets the incumbent''s value advanced in four-month STEPS until it lands in the future -- one step normally, more when the rollover runs late (a 2025-12-21 anchor rolled in 2026 lands on 2026-12-21, not 2026-04-21). Four months is the step, not the offset. The anchor keeps its day of the month either way.';

-- The open edition gets the next seasonal boundary.
--
-- THE BOUNDARY IS DERIVED, NOT WRITTEN DOWN. An earlier version of this file
-- assigned the literal 2026-12-21 and then ABORTED if that date was not in
-- the future -- which made the file expire: a cold replay of the schema in
-- 2027, onto a rebuilt box or a fresh test cluster, would have failed on a
-- date that had simply passed, for a reason that has nothing to do with the
-- database it is running against. A migration that stops working because
-- time moved is a migration that will be hit at the worst moment.
--
-- So the anchor is the FIRST member of the season series strictly after
-- now(): 2026-12-21 stepped forward in four-month increments, which is the
-- same 21 Dec / 21 Apr / 21 Aug cadence the rollover itself walks and the
-- same arithmetic (month addition preserves the day of the month). Today
-- that resolves to 2026-12-21 exactly, so applying this file now does what
-- it always did; applied in 2027 it lands on the next real boundary instead
-- of refusing. The series is bounded, so the subquery is cheap and cannot run
-- away: generate_series is inclusive at BOTH ends, so `generate_series(0,
-- 120)` yields 121 candidates, the last of them 480 months past the seed.
-- This sentence used to say "40 years -- 120 candidates", which is one
-- candidate out; it is now read back out of the file and checked against the
-- expression by `test_332_states_its_own_bound_correctly`, because a bound
-- quoted in prose is the number a later reader reasons with when the seed
-- moves.
--
-- Guarded on `ended_at IS NULL` so it addresses whichever edition is current
-- rather than assuming that is still id 1; guarded on `ends_at_planned IS
-- NULL` so it cannot overwrite a schedule the rollover has since written; and
-- guarded on NOT already_applied so a re-run cannot re-arm an edition an
-- operator deliberately unscheduled.
-- THE MONTH ARITHMETIC IS DONE IN UTC, not in the session's timezone, and
-- that is not decoration. `timestamptz + interval '4 months'` is evaluated in
-- the SESSION's TimeZone, so on a box set to a DST zone the step lands an
-- hour off and the calendar day rolls back: seeded from a Pacific session,
-- the boundary after 2026-12-21 comes out 2027-04-20 23:00 UTC rather than
-- 2027-04-21 00:00 UTC. Converting to a naive timestamp, stepping, and
-- reinterpreting as UTC is the form the rollover in main.py already uses for
-- exactly this reason, so the two now derive the same series by the same
-- arithmetic. Measured, not reasoned: a test of this expression against five
-- as-of dates is what produced the number above.
--
-- The `-- @m332-anchor-*` markers exist for ONE purpose: to let
-- test_migration_reruns.py lift this expression out and execute it against
-- chosen dates instead of retyping it. A test that retypes an expression
-- keeps passing after the file changes (#342), and a marker that means
-- nothing else cannot be matched by accident (#306).
UPDATE pc_editions
   SET ends_at_planned = (
-- @m332-anchor-begin
         SELECT ((TIMESTAMPTZ '2026-12-21 00:00:00+00' AT TIME ZONE 'UTC')
                 + make_interval(months => 4 * n)) AT TIME ZONE 'UTC'
           FROM generate_series(0, 120) AS n
          WHERE ((TIMESTAMPTZ '2026-12-21 00:00:00+00' AT TIME ZONE 'UTC')
                 + make_interval(months => 4 * n)) AT TIME ZONE 'UTC' > now()
          ORDER BY n
          LIMIT 1
-- @m332-anchor-end
       )
 WHERE ended_at IS NULL
   AND ends_at_planned IS NULL
   AND NOT (SELECT already_applied FROM _m332_state);

DO $$
DECLARE
  v_open    integer;
  v_id      integer;
  v_ends    timestamptz;
  v_applied boolean;
BEGIN
  SELECT already_applied INTO v_applied FROM _m332_state;

  SELECT COUNT(*) INTO v_open FROM pc_editions WHERE ended_at IS NULL;
  IF v_open <> 1 THEN
    RAISE EXCEPTION '332: expected exactly one open edition, found % -- the partial unique index pc_editions_one_active should make this impossible, so the table is not in the state 308 built.', v_open;
  END IF;

  SELECT id, ends_at_planned INTO v_id, v_ends
    FROM pc_editions WHERE ended_at IS NULL;

  -- FIRST RUN: the seed above must have landed, and by construction it must
  -- have landed in the future. Both are assertions about the statement
  -- immediately above, so both can genuinely fail.
  IF NOT v_applied THEN
    IF v_ends IS NULL THEN
      RAISE EXCEPTION '332: the open edition (id %) still has no ends_at_planned -- the seeding UPDATE matched nothing on a first run.', v_id;
    END IF;
    IF v_ends <= now() THEN
      RAISE EXCEPTION '332: the open edition (id %) was seeded with %, which is not in the future -- the derivation of the next seasonal boundary is wrong.', v_id, v_ends;
    END IF;
    RAISE NOTICE '332: edition % is scheduled to end % (first application)', v_id, v_ends;
    RETURN;
  END IF;

  -- RE-RUN: this file wrote nothing, and every state it could find is
  -- legitimate. NULL is an operator who stopped the clock; a past date is a
  -- rollover that has not ticked yet. Neither is this file''s to correct, so
  -- it reports rather than refuses -- a post-check that fails on a lawful
  -- re-run is a trap rather than a guarantee.
  IF v_ends IS NULL THEN
    RAISE NOTICE '332: already applied; edition % is UNSCHEDULED (ends_at_planned IS NULL) and this re-run left it alone -- the rollover never touches such a row.', v_id;
  ELSIF v_ends <= now() THEN
    RAISE NOTICE '332: already applied; edition % is scheduled to end %, which is in the PAST -- the next janitor pass will roll it over. Unchanged by this re-run.', v_id, v_ends;
  ELSE
    RAISE NOTICE '332: already applied; edition % is scheduled to end %. Unchanged by this re-run.', v_id, v_ends;
  END IF;
END $$;

COMMIT;
