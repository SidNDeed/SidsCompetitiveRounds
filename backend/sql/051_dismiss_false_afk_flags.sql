-- ============================================================
-- Dismiss the 4 unreviewed inactive_player flags identified as false positives
-- ============================================================
-- Context: audit of flagged_matches showed every "inactive_player" flag has
-- 1-5 cards picked by the reporter, meaning they were at the keyboard during
-- pick phases but just didn't shoot/block (Pacifist, Melee, Trap builds).
-- Backend check tightened to also require cards_picked=0 (see main.py
-- _check_anticheat). These historical flags are not real — dismiss them so
-- the admin feed stays clean.
-- Classification: additive (UPDATE with restrictive WHERE).
-- ============================================================

UPDATE flagged_matches
   SET reviewed_at = NOW(),
       reviewed_by_steam_id = '76561198040410653',
       review_action = 'false_positive'
 WHERE flag_reason = 'inactive_player'
   AND reviewed_at IS NULL;

-- Verify afterward:
--   SELECT COUNT(*) FROM flagged_matches WHERE flag_reason='inactive_player' AND reviewed_at IS NULL;
--   -- expect 0
