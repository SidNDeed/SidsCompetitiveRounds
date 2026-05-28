-- 082_invalidate_misrouted_2v2_matches.sql
--
-- Backfill for the phantom 2v2-routed-into-1v1 contamination described in
-- learning #65 / migrations 060 and 065. The earlier passes only cancelled
-- ranked_series rows with no matches reported. This pass covers the matches
-- that DID get reported through /api/v1/matches with a "team_" photon_room_id
-- (2v2 client routing fall-through) — those rows polluted 1v1 history and
-- created phantom ranked_series even after gate fixes shipped.
--
-- Going forward: the server-side guard in submit_match rejects such reports
-- with HTTP 400, and the client now hard-blocks the 1v1 fallback whenever
-- cr_ff or a team series ID is present. This migration cleans up the 5
-- historical rows so they stop showing in /matches and /series/active.

BEGIN;

-- 1. Downgrade phantom 1v1 matches: drop is_ranked + stamp invalidation reason.
--    XP / gold already in player totals stays put — too long since the matches
--    happened to safely retro-reverse, and the amounts are negligible.
UPDATE matches
SET is_ranked = FALSE,
    invalidated_at = COALESCE(invalidated_at, NOW()),
    invalidation_reason = COALESCE(invalidation_reason, '2v2_misrouted_to_1v1')
WHERE photon_room_id LIKE 'team\_%' ESCAPE '\';

-- 2. Cancel any ranked_series whose only/all matches were 2v2 misroutes.
UPDATE ranked_series rs
SET status = 'cancelled',
    invalidated_at = COALESCE(rs.invalidated_at, NOW()),
    invalidation_reason = COALESCE(rs.invalidation_reason, '2v2_misrouted_to_1v1')
WHERE rs.status != 'cancelled'
  AND EXISTS (SELECT 1 FROM matches m WHERE m.series_id = rs.id AND m.photon_room_id LIKE 'team\_%' ESCAPE '\')
  AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.series_id = rs.id AND (m.photon_room_id IS NULL OR m.photon_room_id NOT LIKE 'team\_%' ESCAPE '\'));

-- 3. Refund any bets attached to those cancelled series (defensive — should be none
--    in practice since these phantom series had no real game-1 odds locked).
--    bets schema: payout NULL + settled_at NULL = pending. Refund = settled with
--    payout = amount, credit player gold accordingly.
WITH unsettled AS (
    SELECT b.id, b.player_id, b.amount
      FROM bets b
      JOIN ranked_series rs ON rs.id = b.series_id
     WHERE rs.invalidation_reason = '2v2_misrouted_to_1v1'
       AND b.settled_at IS NULL
)
UPDATE bets
   SET settled_at = NOW(),
       payout = amount
 WHERE id IN (SELECT id FROM unsettled);

UPDATE players p
   SET gold_earned = COALESCE(gold_earned, 0) + r.amount
  FROM (
    SELECT b.player_id, SUM(b.amount) AS amount
      FROM bets b
      JOIN ranked_series rs ON rs.id = b.series_id
     WHERE rs.invalidation_reason = '2v2_misrouted_to_1v1'
       AND b.payout = b.amount
       AND b.settled_at >= NOW() - INTERVAL '1 minute'
     GROUP BY b.player_id
  ) r
 WHERE p.id = r.player_id;

COMMIT;
