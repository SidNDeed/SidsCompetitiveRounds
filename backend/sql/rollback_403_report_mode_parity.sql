-- rollback_403_report_mode_parity.sql
-- Roll back the report-mode-parity migration (403 when written; the
-- integrator assigns the final number, and nothing below depends on it) only
-- after the api that reads and writes these columns has been rolled back.
-- NOT a release-train migration. Explicit transaction (learning #340).
-- DEPLOY ORDER: THE API FIRST (roll back the readers and writers), then this
-- file. An api from the lane fails every 2v2, 1v2 and FFA report and submit
-- once the columns are gone.
--
-- DATA. Dropping the table and the columns DISCARDS, with no copy: every
-- point event, damage total, kill, death and death time recorded since the
-- migration in every mode, AND the whole 1v2 telemetry table, whose fps,
-- ping, hit, block and damage streams and bullets/blocks/keys/active-seconds
-- counters only exist since this migration. What stays: the match rows, the
-- 2v2 telemetry rows' pre-existing columns and the FFA player rows'
-- pre-existing columns. A deliberate, documented loss.
--
-- Guarded on the catalog like the forward file, so a rerun after success
-- issues nothing and takes no lock. The lock bounds are the forward file's:
-- lock_timeout for the wait, statement_timeout per statement,
-- idle_in_transaction_session_timeout for a stopped runner,
-- synchronous_commit = local for the COMMIT (391 explains each).

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r403$
DECLARE
  spec text[];
  specs text[][] := ARRAY[
    ARRAY['team_match_telemetry', 'damage_dealt'],
    ARRAY['team_match_telemetry', 'kills'],
    ARRAY['team_match_telemetry', 'deaths'],
    ARRAY['team_match_telemetry', 'kill_timeline'],
    ARRAY['team_match_telemetry', 'death_times'],
    ARRAY['team_matches',         'point_timeline'],
    ARRAY['team_matches',         'point_times'],
    ARRAY['ovt_matches',          'point_timeline'],
    ARRAY['ovt_matches',          'point_times'],
    ARRAY['ffa_match_players',    'deaths'],
    ARRAY['ffa_match_players',    'death_times']
  ];
BEGIN
  IF to_regclass(format('%I.ovt_match_telemetry', current_schema())) IS NOT NULL THEN
    DROP TABLE ovt_match_telemetry;
  END IF;
  FOREACH spec SLICE 1 IN ARRAY specs LOOP
    IF EXISTS (SELECT 1 FROM pg_attribute a
                WHERE a.attrelid = to_regclass(format('%I.%I', current_schema(), spec[1]))
                  AND a.attname = spec[2]
                  AND NOT a.attisdropped) THEN
      EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS %I', spec[1], spec[2]);
    END IF;
  END LOOP;
  RAISE NOTICE 'report mode parity rollback: ovt_match_telemetry and the 11 column(s) absent';
END $r403$;

COMMIT;
