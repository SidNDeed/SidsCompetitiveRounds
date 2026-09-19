-- 332_pc_edition_schedule.sql
--
-- Player Cards editions become seasonal (v1.41.0, item 7): four months
-- each, ending on the 21st of December, April and August at 00:00 UTC.
-- Edition 1 ends when winter starts -- 2026-12-21 00:00 UTC, the solstice
-- (Sid's call, 2026-09-18).
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
-- SAFE TO RUN BEFORE THE API, AND IT MUST BE. The column is nullable with
-- no default, so every current reader and writer of pc_editions is
-- untouched -- the one application reference today is the mint path's
-- `SELECT id FROM pc_editions WHERE ended_at IS NULL ... FOR SHARE`. Apply
-- this file first and deploy the api second: the api's boot-time janitor
-- EXPLAIN sweep parses the rollover statement against the live schema and
-- reports it as a failure if the column is missing.
--
-- NOTHING ROLLS TODAY, and that is the negative control for this file:
-- 2026-12-21 is three months out, so pc_editions must still show exactly
-- one open row, with a schedule, still in the future -- which is precisely
-- what the DO block at the bottom asserts, and all it asserts.
--
-- It deliberately does NOT assert "and that row is Edition 1". The UPDATE
-- below is guarded on ended_at IS NULL exactly so it does not assume id 1,
-- and a post-check that did assume it would contradict the statement it is
-- checking. started_at is untouched because the UPDATE's SET list contains
-- one column -- a property you can read off this file, not a runtime claim.
-- An earlier version of this comment said the block asserted both.

BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE pc_editions ADD COLUMN IF NOT EXISTS ends_at_planned TIMESTAMPTZ;

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

-- The open edition gets winter. Guarded on IS NULL so a re-run is a no-op
-- and so this can never overwrite a schedule the rollover has since
-- written; guarded on ended_at IS NULL so it addresses whichever edition is
-- current rather than assuming that is still id 1.
UPDATE pc_editions
   SET ends_at_planned = TIMESTAMPTZ '2026-12-21 00:00:00+00'
 WHERE ended_at IS NULL AND ends_at_planned IS NULL;

DO $$
DECLARE
  v_open  integer;
  v_id    integer;
  v_ends  timestamptz;
BEGIN
  SELECT COUNT(*) INTO v_open FROM pc_editions WHERE ended_at IS NULL;
  IF v_open <> 1 THEN
    RAISE EXCEPTION '332: expected exactly one open edition, found % -- the partial unique index pc_editions_one_active should make this impossible, so the table is not in the state 308 built.', v_open;
  END IF;

  SELECT id, ends_at_planned INTO v_id, v_ends
    FROM pc_editions WHERE ended_at IS NULL;

  IF v_ends IS NULL THEN
    RAISE EXCEPTION '332: the open edition (id %) still has no ends_at_planned -- the UPDATE above matched nothing.', v_id;
  END IF;

  -- An end already in the past would make the api roll the edition over on
  -- its very next janitor pass, which is not what applying a schedule is
  -- supposed to do. Refuse instead: whoever runs this after the date has
  -- passed needs to choose the next anchor deliberately.
  IF v_ends <= now() THEN
    RAISE EXCEPTION '332: the open edition (id %) is now scheduled to end at %, which is not in the future -- the api would roll it over on its next janitor pass. Pick the next anchor (21 Dec / 21 Apr / 21 Aug) and edit this file before applying it.', v_id, v_ends;
  END IF;

  RAISE NOTICE '332: edition % is scheduled to end %', v_id, v_ends;
END $$;

COMMIT;
