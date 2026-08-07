-- 201: Damage-dealt timelines for 2v2 and 1v2 (Aug-7b item 3, "DPS over the
--      course of a game").
--
-- MUST run BEFORE the code deploy: the 2v2/1v2 submit paths INSERT these
-- columns and the history responses SELECT them, so the column has to exist
-- first (#235's ordering rule). There is no backfill and no idempotency key
-- written by the new code, so #236's opposite rule does not apply here.
--
-- Idempotent statement-by-statement. A normal run executes the file ONCE: the
-- wrapper's preferred `-f /migrations/<file>` arm fails on the missing path
-- BEFORE any SQL is executed, and the `||` stdin fallback then runs it (#243).
-- Idempotency is still required — a hand re-run is always possible, and a
-- failure partway through re-executes the whole file from the top.
--
-- WHY NULLABLE, no default, no backfill (#257):
--   NULL  = this game predates the telemetry, or the client never sent it.
--   '0,0' = the player was recorded and genuinely dealt nothing.
-- A NOT NULL DEFAULT '' (or a zero-filled backfill) would make every historical
-- 2v2/1v2 game claim "dealt no damage" instead of "not recorded", and the DPS
-- graph would draw a flat zero line over history that looks like a gameplay
-- fact rather than an absence. The consumer must skip a NULL row entirely — a
-- row with no timeline registers no hover graph at all.
--
-- Consequence, stated so nobody reports it as a bug: the DPS graph is
-- FORWARD-ONLY for these two modes. No historical game carries the data and
-- none can be reconstructed (damage attribution only ever existed client-side,
-- in the live match), so the chart starts empty and fills from the first game
-- played on the release that ships the client half. The affected history is
-- small — measured 2026-08-07: 63 team_matches / 40 team_match_telemetry rows
-- / 11 ovt_matches — so there is little to miss and nothing worth faking.
--
-- Format matches the sibling timelines in the same row: cumulative damage
-- dealt, comma-separated ints, one sample per 3s, cap 128 samples
-- (GameStateWatcher's localFps3sTimeline grid, which is what fps_timeline in
-- this same row already rides — so the DPS derivative shares its x-axis).
-- NOTE the 1v1 pair (matches.p1_damage_timeline) is a DIFFERENT grid: 5s, cap
-- 90. Do not assume one cadence across modes; read the row's own fps_timeline.
--
-- VARCHAR(1024), matching EVERY sibling timeline column. The frozen contract
-- said TEXT; that was an error in the contract, not a deliberate choice, and it
-- was correctly flagged rather than silently followed. Verified against
-- production: all 20 existing *_timeline columns are VARCHAR, and every DAMAGE
-- timeline specifically is VARCHAR(1024) — matches.p1/p2_damage_timeline and
-- ffa_match_players.damage_dealt_timeline alike.
--
-- The bound is not cosmetic. These strings are client-supplied, so the column
-- width is a real backstop underneath the schemas.py max_length; TEXT would
-- have left the Pydantic check as the only thing between a modified client and
-- an unbounded write.

-- 2v2: per-player telemetry row already exists (migration 142), so this is one
-- more column beside fps/ping/hit/block.
ALTER TABLE team_match_telemetry ADD COLUMN IF NOT EXISTS damage_dealt_timeline VARCHAR(1024);

-- 1v2 has no telemetry table at all, so the columns hang off the match row.
-- Naming follows the existing ovt_matches convention exactly
-- (solo_fps_avg / duo_a_fps_avg / duo_b_fps_avg).
ALTER TABLE ovt_matches ADD COLUMN IF NOT EXISTS solo_damage_timeline VARCHAR(1024);
ALTER TABLE ovt_matches ADD COLUMN IF NOT EXISTS duo_a_damage_timeline VARCHAR(1024);
ALTER TABLE ovt_matches ADD COLUMN IF NOT EXISTS duo_b_damage_timeline VARCHAR(1024);

COMMENT ON COLUMN team_match_telemetry.damage_dealt_timeline IS
    'Cumulative damage this player dealt, comma-separated ints, one sample per 3s (cap 128). NULL = not recorded (pre-Aug-7b game or old client); never zero-filled.';
COMMENT ON COLUMN ovt_matches.solo_damage_timeline IS
    'Cumulative damage the solo dealt, comma-separated ints, one sample per 3s (cap 128). NULL = not recorded.';
COMMENT ON COLUMN ovt_matches.duo_a_damage_timeline IS
    'Cumulative damage duo slot A dealt, comma-separated ints, one sample per 3s (cap 128). NULL = not recorded.';
COMMENT ON COLUMN ovt_matches.duo_b_damage_timeline IS
    'Cumulative damage duo slot B dealt, comma-separated ints, one sample per 3s (cap 128). NULL = not recorded.';

-- Post-check: RAISE if any column is missing. Both tables exist only in the
-- public schema (verified against prod), so the schema-less information_schema
-- filter used by the surrounding migrations is unambiguous here.
DO $$
DECLARE
    missing TEXT := '';
    col TEXT;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'team_match_telemetry'
                     AND column_name = 'damage_dealt_timeline') THEN
        missing := missing || ' team_match_telemetry.damage_dealt_timeline';
    END IF;
    FOREACH col IN ARRAY ARRAY[
        'solo_damage_timeline', 'duo_a_damage_timeline', 'duo_b_damage_timeline']
    LOOP
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'ovt_matches' AND column_name = col) THEN
            missing := missing || ' ovt_matches.' || col;
        END IF;
    END LOOP;
    IF missing <> '' THEN
        RAISE EXCEPTION 'migration 201 post-check FAILED, missing:%', missing;
    END IF;
    RAISE NOTICE 'migration 201 post-check OK (4 damage-timeline columns present)';
END $$;
