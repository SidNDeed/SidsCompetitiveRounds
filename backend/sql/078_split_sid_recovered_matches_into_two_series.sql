-- 078_split_sid_recovered_matches_into_two_series.sql
-- Migration 077 dumped all 4 recovered matches under one series_id, but
-- Sid+feauxen actually played TWO BO3 series back-to-back that day:
--   Series A: matches 1 (3-5) + 2 (4-5)  -> T2 wins 2-0 at 11:25
--   Series B: matches 3 (4-5) + 4 (3-5)  -> T2 wins 2-0 at 11:40
-- Series A is correct as-is on series_id 4ea30d95... Just need to spin
-- a second team_series row, re-point matches 3+4 to it, and complete it.

-- 1. Create the second series (covers matches 3 + 4).
INSERT INTO team_series (
    id,
    t1a_id, t1b_id, t2a_id, t2b_id,
    t1_series_wins, t2_series_wins,
    status, winner_team,
    photon_room_id, region,
    created_at, completed_at,
    spawn_confirmations, was_auto_balanced
)
SELECT
    gen_random_uuid(),
    s.t1a_id, s.t1b_id, s.t2a_id, s.t2b_id,
    0, 2,
    'completed', 2,
    'team_56346ed7bd62_seriesB', s.region,
    '2026-05-09 11:30:00+00'::timestamptz,
    '2026-05-09 11:40:00+00'::timestamptz,
    4, s.was_auto_balanced
FROM team_series s
WHERE s.id = '4ea30d95-9612-4f71-a4f0-47dd4a064da3'
RETURNING id;

-- 2. Re-point matches 3 and 4 to the new series. The new series id was
--    just generated, so look it up by photon_room_id sentinel.
UPDATE team_matches
   SET series_id = (SELECT id FROM team_series WHERE photon_room_id = 'team_56346ed7bd62_seriesB')
 WHERE id IN (
     '03d857bf-b169-4fb9-8603-bc968355c3e9',  -- match 3
     'eb24c7d0-a995-4272-bc71-87366c9006b9'   -- match 4
 );

-- 3. Series A keeps matches 1+2 only -- it's already completed 0-2 at
--    11:25 from migration 077. Nothing to update.
