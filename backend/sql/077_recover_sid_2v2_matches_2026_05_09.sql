-- 077_recover_sid_2v2_matches_2026_05_09.sql
-- Reconstruct Sid+feauxen's four unreported 2v2 wins from 2026-05-09.
-- The series 4ea30d95-9612-4f71-a4f0-47dd4a064da3 was cancelled by the
-- team_queue_cleanup_loop at 11:12:40 (stale_queue_rows) about 3 min
-- after creation, before any matches were reported. Players started
-- match reporting at 11:18+ but every POST /api/v1/team/matches
-- bounced with HTTP 400 because the series was no longer 'active'.
--
-- The client log captured the exact rounds + winner for each of the
-- four matches:
--   match 1: 3-5 winner=T2 (Sid+feauxen on T2)
--   match 2: 4-5 winner=T2
--   match 3: 4-5 winner=T2
--   match 4: 3-5 winner=T2
-- All four have winner_team=2. T2 = (76561198040410653 Sid + 76561198081664646 feauxen).
-- T1 = (76561199057431340 + 76561199261741278).
--
-- Underlying bug fixed in the same deploy (cleanup loop now gates on
-- spawn_confirmations < 4 so post-assembly series aren't swept).
-- This migration only repairs the data Sid lost.

-- 1. Reactivate the series so the inserts pass FK + status checks.
UPDATE team_series
   SET status = 'active',
       invalidated_at = NULL,
       invalidation_reason = NULL,
       spawn_confirmations = 4   -- four matches were played, so spawn-confirms had clearly happened
 WHERE id = '4ea30d95-9612-4f71-a4f0-47dd4a064da3'
   AND status = 'cancelled'
   AND invalidation_reason = 'stale_queue_rows';

-- 2. Insert the four match rows with reconstructed scores. created_at /
--    ended_at use real timestamps from the client log (UTC).
WITH series AS (
    SELECT id, t1a_id, t1b_id, t2a_id, t2b_id FROM team_series
    WHERE id = '4ea30d95-9612-4f71-a4f0-47dd4a064da3'
)
INSERT INTO team_matches (
    series_id, t1a_id, t1b_id, t2a_id, t2b_id,
    t1_rounds_won, t2_rounds_won, t1_points_total, t2_points_total,
    winner_team, ended_at, photon_room_id
)
SELECT s.id, s.t1a_id, s.t1b_id, s.t2a_id, s.t2b_id,
       m.t1r, m.t2r, m.t1r, m.t2r,
       2, m.ended, m.room
  FROM series s, (VALUES
      (3, 5, '2026-05-09 11:18:00+00'::timestamptz, 'team_56346ed7bd62_111800_r1'),
      (4, 5, '2026-05-09 11:25:00+00'::timestamptz, 'team_56346ed7bd62_112500_r2'),
      (4, 5, '2026-05-09 11:32:00+00'::timestamptz, 'team_56346ed7bd62_113200_r3'),
      (3, 5, '2026-05-09 11:40:00+00'::timestamptz, 'team_56346ed7bd62_114000_r4')
  ) AS m(t1r, t2r, ended, room);

-- 3. Update series totals: T2 won all 4 matches. Series is BO3, so the
--    first 2 wins decide. Mark completed with winner_team=2 once the
--    second match was won.
UPDATE team_series
   SET t1_series_wins = 0,
       t2_series_wins = 2,
       status = 'completed',
       winner_team = 2,
       completed_at = '2026-05-09 11:25:00+00'::timestamptz
 WHERE id = '4ea30d95-9612-4f71-a4f0-47dd4a064da3';
