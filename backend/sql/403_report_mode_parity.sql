-- 403_report_mode_parity.sql
-- Session report, one data model for every mode (ask 9 of the 2026-11-04
-- batch). The number is provisional: the integrator assigns the final one at
-- landing, and nothing in this file depends on it.
--
-- The report envelope (main.get_set_report) emits one slot shape, but 2v2,
-- 1v2 and FFA could only part-fill it because their uploads never stored the
-- facts 1v1 stores: a 2v2 or 1v2 game had no point events (so no score race
-- and no death marks), no per-player damage total, kills or deaths; a 1v2
-- game had no telemetry beyond an fps average and three damage CSVs; an FFA
-- player had kills but no deaths. This file adds the storage; the api's
-- submit routes write it from the fields the client sends (schemas
-- TeamPlayerTelemetry, TeamMatchReport, OvtMatchReport), and the report
-- loaders read it. Every column is NULLable with no default: NULL is "not
-- recorded" (an old client, or a game before this file), never zero (#257).
--
--   team_match_telemetry  + damage_dealt INTEGER, kills SMALLINT, deaths SMALLINT,
--                           kill_timeline VARCHAR(512), death_times VARCHAR(512)
--   team_matches          + point_timeline VARCHAR(512), point_times VARCHAR(512)
--                           (the pair matches.point_timeline / point_times has
--                           carried for 1v1 since 111/136; team 1 is the left side)
--   ovt_matches           + point_timeline VARCHAR(512), point_times VARCHAR(512)
--                           (solo is the left side)
--   ffa_match_players     + deaths SMALLINT, death_times VARCHAR(512)
--   ovt_match_telemetry   NEW: the team_match_telemetry shape (142 + 201) plus
--                           the five combat columns above, one row per seat
--                           whose blob reached the reporter; PRIMARY KEY
--                           (match_id, player_id), ON DELETE CASCADE from the
--                           match, index on match_id (idx_omt_match)
--
-- death_times is the seconds since match start of each death, comma
-- separated ("12.4,47.0"), the grammar point_times uses; kill_timeline is
-- cumulative on the fps grid like damage_dealt_timeline (201).
--
-- NO BACKFILL. Nothing stored before this file can say who killed whom or
-- when a 2v2 point fell; those games keep reading as they do today (no score
-- race, no marks, counters only).
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api. The api's report statements
-- SELECT these columns and its submit routes INSERT into them, so an api
-- built from this lane fails every 2v2, 1v2 and FFA report and submit until
-- the columns exist; an api without the lane ignores them. Apply on the
-- primary; the standby receives it by streaming replication; read the
-- post-check's NOTICE on both before the code deploys (the two-SHA order,
-- #477).
--
-- LOCKS. ADD COLUMN of a nullable column with no default changes the catalog
-- only (no table rewrite), but each ALTER takes ACCESS EXCLUSIVE on its table
-- and holds it until COMMIT, so the four tables' writers (the submit routes)
-- and readers (the report, the profile aggregates) wait through the rest of
-- the file. The DDL itself is milliseconds; lock_timeout bounds only how long
-- the file waits to START each statement behind a report in flight, and on
-- expiry the whole file rolls back with nothing changed and is re-applied.
-- idle_in_transaction_session_timeout bounds a runner that stops before
-- COMMIT; statement_timeout bounds each statement; synchronous_commit = local
-- keeps the COMMIT from waiting on a standby (as 391 and 401 explain).
--
-- RE-RUNS. Every ADD COLUMN and the CREATE TABLE are GUARDED ON THE CATALOG
-- and issued only when the object is absent, so a second run issues none of
-- them and takes no lock on any of the tables (an IF NOT EXISTS spelling
-- alone takes the table lock before it checks). The statements inside the
-- guards keep IF NOT EXISTS.
--
-- POST-CHECK. After the guards, one pass compares every column with the type
-- this file states and aborts the file naming the first difference, because a
-- guard alone would accept a same-named column of another type.
--
-- Rollback: rollback_403_report_mode_parity.sql (drops the table and the
-- columns; discards what they recorded).

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $m403$
DECLARE
  spec text[];
  got  text;
  specs text[][] := ARRAY[
    ARRAY['team_match_telemetry', 'damage_dealt',   'INTEGER',      'integer'],
    ARRAY['team_match_telemetry', 'kills',          'SMALLINT',     'smallint'],
    ARRAY['team_match_telemetry', 'deaths',         'SMALLINT',     'smallint'],
    ARRAY['team_match_telemetry', 'kill_timeline',  'VARCHAR(512)', 'character varying(512)'],
    ARRAY['team_match_telemetry', 'death_times',    'VARCHAR(512)', 'character varying(512)'],
    ARRAY['team_matches',         'point_timeline', 'VARCHAR(512)', 'character varying(512)'],
    ARRAY['team_matches',         'point_times',    'VARCHAR(512)', 'character varying(512)'],
    ARRAY['ovt_matches',          'point_timeline', 'VARCHAR(512)', 'character varying(512)'],
    ARRAY['ovt_matches',          'point_times',    'VARCHAR(512)', 'character varying(512)'],
    ARRAY['ffa_match_players',    'deaths',         'SMALLINT',     'smallint'],
    ARRAY['ffa_match_players',    'death_times',    'VARCHAR(512)', 'character varying(512)']
  ];
BEGIN
  -- The per-seat 1v2 telemetry table, guarded on the catalog.
  IF to_regclass(format('%I.ovt_match_telemetry', current_schema())) IS NULL THEN
    CREATE TABLE IF NOT EXISTS ovt_match_telemetry (
        match_id  UUID NOT NULL REFERENCES ovt_matches(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id),
        fps_timeline           VARCHAR(512),
        ping_timeline          VARCHAR(512),
        ping_avg               SMALLINT,
        hit_timeline           VARCHAR(1024),
        block_timeline         VARCHAR(1024),
        damage_dealt_timeline  VARCHAR(1024),
        bullets_fired          INTEGER,
        bullets_hit            INTEGER,
        blocks_activated       INTEGER,
        blocks_successful      INTEGER,
        keys_pressed           INTEGER,
        active_seconds         DOUBLE PRECISION,
        damage_dealt           INTEGER,
        kills                  SMALLINT,
        deaths                 SMALLINT,
        kill_timeline          VARCHAR(512),
        death_times            VARCHAR(512),
        PRIMARY KEY (match_id, player_id)
    );
    COMMENT ON TABLE ovt_match_telemetry IS
      'Per-seat 1v2 telemetry (migration 403), the team_match_telemetry shape plus '
      'damage_dealt, kills, deaths, kill_timeline and death_times. Rows exist only '
      'for seats whose blob reached the reporter; NULL = not recorded (#257).';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema() AND c.relname = 'idx_omt_match') THEN
    CREATE INDEX IF NOT EXISTS idx_omt_match ON ovt_match_telemetry (match_id);
  END IF;

  -- The columns, each guarded on the catalog.
  FOREACH spec SLICE 1 IN ARRAY specs LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_attribute a
                    WHERE a.attrelid = to_regclass(format('%I.%I', current_schema(), spec[1]))
                      AND a.attname = spec[2]
                      AND NOT a.attisdropped) THEN
      EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS %I %s', spec[1], spec[2], spec[3]);
    END IF;
  END LOOP;

  -- The post-check: the guards only asked whether the names exist.
  FOREACH spec SLICE 1 IN ARRAY specs LOOP
    SELECT format_type(a.atttypid, a.atttypmod) INTO got
      FROM pg_attribute a
     WHERE a.attrelid = to_regclass(format('%I.%I', current_schema(), spec[1]))
       AND a.attname = spec[2]
       AND NOT a.attisdropped;
    IF got IS DISTINCT FROM spec[4] THEN
      RAISE EXCEPTION 'report mode parity: %.% is %, not %',
        spec[1], spec[2], coalesce(got, 'missing'), spec[4];
    END IF;
  END LOOP;
  IF to_regclass(format('%I.ovt_match_telemetry', current_schema())) IS NULL THEN
    RAISE EXCEPTION 'report mode parity: ovt_match_telemetry is missing after its guard';
  END IF;
  RAISE NOTICE 'report mode parity: 11 column(s) and ovt_match_telemetry present';
END $m403$;

COMMIT;
