-- 237_async_lb_unforfeit_repair.sql
-- Per request (2026-08-21): in the running async tournament
-- (a2d3c090-54c9-46ae-a4e2-fa1b85f0f10c), LB R1 slot 1 hit the 7-day
-- deadline with one player who WANTED to play (contacted the opponent,
-- got no response) and one who had quit. The overdue sweep's mutual
-- no-show branch double-forfeited BOTH signups, and the same tick's
-- activation cascade consumed the survivor's forfeited flag to award
-- LB R2 slot 1 to the third player without a game.
--
-- Repair: the willing player advances by a normal single forfeit; the
-- LB R2 match returns to 'pending' so the next tournament tick's
-- _activate_ready_matches re-resolves it through the REAL code path
-- (same seats from prereq roles {W,L}, fresh series + room + 7-day
-- deadline_at, match_ready notices to both players). Deliberately NO
-- hand-built series here — the tick owns activation.
--
-- Downstream safety, verified 2026-08-22: LB R3 slot 0
-- (5b697fe0-d26e-4eae-8eca-08a6f08bd47e) is still 'pending' with NULL
-- seats — the wrong LB R2 result was never consumed further, so these
-- three writes unwind everything. The declined player's signup keeps
-- forfeited=true (they chose not to play); the old match's 0-0 series
-- (038524e6-...) stays as the normal forfeit path leaves it — its
-- terminal match status excludes it from listings/bets either way.
--
-- Idempotent: every UPDATE is predicated on the exact broken state; a
-- second run matches nothing.

BEGIN;

-- 1. Un-eliminate the willing player (LB R1 survivor).
UPDATE tournament_signups
   SET forfeited = FALSE
 WHERE id = 'c2ca0c61-f254-43ea-accd-3f4cffc9853b'
   AND forfeited;

-- 2. LB R1 slot 1: mutual double_forfeit -> normal single forfeit with
--    the willing player as winner (the opponent had quit). Winner is
--    already this signup (the tiebreak carrier), so only status moves.
UPDATE tournament_matches
   SET status = 'forfeit'
 WHERE id = 'f5dadeed-4400-4ed0-b561-123dee887862'
   AND status = 'double_forfeit'
   AND winner_signup_id = 'c2ca0c61-f254-43ea-accd-3f4cffc9853b';

-- 3. LB R2 slot 1: undo the cascade award and hand the match back to
--    the activation tick (prereqs both carry winners, both resolved
--    signups now unforfeited -> it goes 'ready' with a fresh 7-day
--    deadline within ~30s).
UPDATE tournament_matches
   SET status = 'pending',
       winner_signup_id = NULL,
       ended_at = NULL
 WHERE id = 'd9de58c4-8d88-450c-a1d3-8b095cca7c4d'
   AND status = 'forfeit'
   AND winner_signup_id = 'ad735b10-38a1-498c-8385-a5fe41db3fa1'
   AND series_id IS NULL;

-- Verification: expect (f | forfeit | pending) on one row each.
SELECT s.forfeited AS lopidav_forfeited,
       m1.status   AS lb_r1_status,
       m2.status   AS lb_r2_status,
       m2.winner_signup_id AS lb_r2_winner_should_be_null
  FROM tournament_signups s,
       tournament_matches m1,
       tournament_matches m2
 WHERE s.id  = 'c2ca0c61-f254-43ea-accd-3f4cffc9853b'
   AND m1.id = 'f5dadeed-4400-4ed0-b561-123dee887862'
   AND m2.id = 'd9de58c4-8d88-450c-a1d3-8b095cca7c4d';

COMMIT;
