-- rollback_383_match_hold_stage2.sql
-- The inverse of migration 383 (the 2v2 and 1v2 Stage 2 match hold). NOT a
-- release-train migration and never applied by the train: a hand-run file for
-- the case the 383 schema has to come back out. It drops exactly what 383 added
-- and nothing else. 383 is additive (every statement IF NOT EXISTS), so no
-- pre-383 table or column is touched here.
--
-- DEPLOY ORDER: THE API FIRST. Roll the api back to a build that names none of
-- these objects before running this file; the new api reads and writes every
-- object below on the team and 1v2 paths. The rollback order of the RJ server
-- landing is rollback_384 (i18n keys), then this file, then rollback_378 (the
-- FFA readmission schema) (ruling R3 of the landing).
--
-- WHAT IS LOST. Every game id, presence beat, seat hold, hold attempt, report
-- window and journaled report of a flagged room (the seven tables with their
-- rows), the hold flag and hold room of every series, the capability tokens of
-- every queue row, and the fallback class of every team and 1v2 report. The old
-- api never reads any of them; a series issued under 383 reads as unflagged
-- once hold_v2 is gone, which is how the old api treated every series.
--
-- Explicit transaction (learning 340): all or nothing. Every DROP is IF EXISTS,
-- so a second run changes nothing. The post-check raises if any 383 object is
-- still present, which rolls the whole file back.

BEGIN;

-- The columns 383 added to pre-existing tables, in the reverse of their
-- addition order. The inline check constraints of fallback_cls are dropped by
-- name first so the intent is explicit; the column drop would take them.
ALTER TABLE ovt_matches  DROP CONSTRAINT IF EXISTS ck_ovt_matches_fallback_cls;
ALTER TABLE ovt_matches  DROP COLUMN IF EXISTS fallback_cls;
ALTER TABLE team_matches DROP CONSTRAINT IF EXISTS ck_team_matches_fallback_cls;
ALTER TABLE team_matches DROP COLUMN IF EXISTS fallback_cls;
ALTER TABLE ovt_series   DROP COLUMN IF EXISTS hold_room;
ALTER TABLE ovt_series   DROP COLUMN IF EXISTS hold_v2;
ALTER TABLE team_series  DROP COLUMN IF EXISTS hold_room;
ALTER TABLE team_series  DROP COLUMN IF EXISTS hold_v2;
ALTER TABLE ovt_queue    DROP COLUMN IF EXISTS caps;
ALTER TABLE team_queue   DROP COLUMN IF EXISTS caps;

-- The three explicit indexes, then the seven tables in the reverse of their
-- creation order: match_report_journal, match_report_windows and
-- match_seat_holds reference match_games; match_hold_attempts and
-- match_hold_open_attempts reference match_seat_holds.
DROP INDEX IF EXISTS idx_msh_player_open;
DROP INDEX IF EXISTS uq_msh_one_open_per_room;
DROP INDEX IF EXISTS uq_match_games_first;
DROP TABLE IF EXISTS match_report_journal;
DROP TABLE IF EXISTS match_report_windows;
DROP TABLE IF EXISTS match_hold_attempts;
DROP TABLE IF EXISTS match_hold_open_attempts;
DROP TABLE IF EXISTS match_seat_holds;
DROP TABLE IF EXISTS match_seat_presence;
DROP TABLE IF EXISTS match_games;

-- The post-check: nothing of 383 remains. It raises on any leftover, so a
-- partial run rolls back whole.
DO $chk$
DECLARE
    left_over text[] := ARRAY[]::text[];
    t text;
    c record;
BEGIN
    FOREACH t IN ARRAY ARRAY['match_games', 'match_seat_presence',
                             'match_seat_holds', 'match_hold_open_attempts',
                             'match_hold_attempts', 'match_report_windows',
                             'match_report_journal', 'uq_match_games_first',
                             'uq_msh_one_open_per_room', 'idx_msh_player_open'] LOOP
        IF to_regclass(t) IS NOT NULL THEN
            left_over := left_over || ('relation ' || t);
        END IF;
    END LOOP;
    FOREACH t IN ARRAY ARRAY['ck_team_matches_fallback_cls',
                             'ck_ovt_matches_fallback_cls'] LOOP
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = t) THEN
            left_over := left_over || ('constraint ' || t);
        END IF;
    END LOOP;
    FOR c IN
        SELECT * FROM (VALUES
            ('team_queue', 'caps'),
            ('ovt_queue', 'caps'),
            ('team_series', 'hold_v2'),
            ('team_series', 'hold_room'),
            ('ovt_series', 'hold_v2'),
            ('ovt_series', 'hold_room'),
            ('team_matches', 'fallback_cls'),
            ('ovt_matches', 'fallback_cls')) AS v(tbl, col)
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = c.tbl AND column_name = c.col) THEN
            left_over := left_over || ('column ' || c.tbl || '.' || c.col);
        END IF;
    END LOOP;
    IF array_length(left_over, 1) IS NOT NULL THEN
        RAISE EXCEPTION 'rollback_383 post-check FAILED: % still present',
            array_to_string(left_over, ', ');
    END IF;
    RAISE NOTICE 'rollback_383 post-check OK';
END $chk$;

COMMIT;
