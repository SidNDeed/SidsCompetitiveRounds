-- 391_dc_events_leave_anchor.sql
-- The leave time on the 1v1 disconnect record (small docket item a).
--
-- dc_events (migration 101) keeps one accepted disconnect report per
-- (series, leaver) and carries one time, created_at: when the server
-- ACCEPTED the report. That is not when the player left. The client keeps
-- the report in its durable outbox and retries it after a refusal, a 503 or
-- a restart, so the acceptance can trail the leave by the outbox's whole
-- retry budget.
--
-- leave_anchor_at is the leave's anchor by the rule the hold logic uses for
-- a dropped seat: the last server evidence of that seat's presence (the
-- 2v2 and 1v2 hold anchors at the held seat's last present_at, match_hold.py;
-- the FFA readmission hold at present_at, else verdict_at). 1v1 has no hold
-- and no presence beat, so its evidence is the leaver's own last verified
-- live-points stamp in the series (series_progress.last_seen_at, migration
-- 295), else the series' last recorded activity
-- (ranked_series.last_activity_at, migration 215). The api computes it in
-- the statement that inserts the row; that insert is first-write-wins
-- (uq_dc_event_series_player), so a replayed report never moves it.
--
-- NULL: every row written before the api that fills it, and a row whose
-- series carries neither stamp. No backfill: created_at is the acceptance
-- time, and copying it here would state a leave time nobody observed.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api, as two SHAs (learning #477):
-- the api's insert names this column. The column is nullable with no
-- default, so adding it rewrites no row.
--
-- RE-RUNS. The ADD is guarded on the catalog, so a second run issues no
-- ALTER and takes no lock: ADD COLUMN IF NOT EXISTS alone takes ACCESS
-- EXCLUSIVE on the table before it looks for the column
-- (test_a_second_run_takes_no_blocking_lock holds this file to that). The
-- post-check refuses a same-named column of another type, which the guard
-- alone would accept. Explicit transaction (learning #340).

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m391add$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_attribute a
                  WHERE a.attrelid = to_regclass(format('%I.dc_events', current_schema()))
                    AND a.attname = 'leave_anchor_at'
                    AND NOT a.attisdropped) THEN
    ALTER TABLE dc_events ADD COLUMN IF NOT EXISTS leave_anchor_at TIMESTAMPTZ;
    COMMENT ON COLUMN dc_events.leave_anchor_at IS
      'The last server evidence of the leaver''s presence in the series when '
      'the row was written: series_progress.last_seen_at of the leaver, else '
      'ranked_series.last_activity_at. The hold logic''s anchor rule. NULL on '
      'rows written before migration 391''s api and when neither stamp exists. '
      'created_at is when the report was accepted.';
  END IF;
END $m391add$;

DO $m391check$
DECLARE
  got text;
BEGIN
  SELECT format_type(a.atttypid, a.atttypmod) INTO got
    FROM pg_attribute a
   WHERE a.attrelid = to_regclass(format('%I.dc_events', current_schema()))
     AND a.attname = 'leave_anchor_at'
     AND NOT a.attisdropped;
  IF got IS DISTINCT FROM 'timestamp with time zone' THEN
    RAISE EXCEPTION '391: dc_events.leave_anchor_at is %, not timestamp with time zone',
      coalesce(got, 'missing');
  END IF;
END $m391check$;

COMMIT;
