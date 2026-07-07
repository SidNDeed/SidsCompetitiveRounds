-- 104_backfill_unranked_first_games.sql
--
-- Bug #47 backfill: "first game(s) of a code-room session recorded casual".
-- Root cause: the client's matchIsRanked races (opponent props / mod-check /
-- late startup ranked-sync) resolve mid-session, so the first game(s) of a
-- sitting report is_ranked=false even though both players are consenting mod
-- users and later games of the same sitting record ranked. Code fix lands in
-- v1.29.1 (server-side re-evaluation at report time); this migration repairs
-- the four affected games from 2026-07-07 (all reported by Sid, all Sid wins):
--
--   CYDCTL_082909_r6  Sid 5-1 A_pancake  08:32:49  -> attach to its sitting's
--                     series 88e91fb1 (created 08:29:24 by preflight, completed
--                     2-0; score fields untouched)
--   CLFPEN_104142_r8  Sid 5-3 Catus      10:47:44  -> NEW completed series (game 1)
--   CLFPEN_104758_r6  Sid 5-1 Catus      10:51:51  -> NEW completed series (game 2)
--   CLFPEN_105207_r9  Sid 5-4 Catus      10:59:02  -> attach to series 8dbcf532
--                     (created 11:00:02, the sitting's next series; score untouched)
--
-- The new Sid-vs-Catus series gets the full inline-completion treatment the
-- server would have applied: winner/completed stamps, p1/p2_rating_change,
-- one Glicko-2 rating period for both players (values computed offline with
-- backend/api/glicko2.py from live ratings — see session log), rating_history
-- snapshots, and the 10+2 sweep series-win gold with its ledger row.
-- XP corrections: casual->ranked multiplier is x1.5 (win 375->562, loss 250->375).
--
-- NOT included (deliberate):
--   - MAX/Snail 6/26 casual games (MAX currently has ranked disabled -- possible
--     deliberate opt-out; needs Sid's call)
--   - Nyxx/GGG quickplay games (GGG has ranked disabled -- deliberate opt-out)
--   - Sid/no1 7/3 games (no1's mod first seen AFTER that session ended)
--   - gold-from-XP deltas (<= ~3g per game; not worth ledger noise)
--
-- Idempotent: every statement guards on the pre-migration state.

BEGIN;

-- ── 1. New completed series for Catus games 1+2 ─────────────────────────────
-- Fixed UUID so re-runs are no-ops.
INSERT INTO ranked_series (id, player1_id, player2_id, p1_series_wins, p2_series_wins,
                           status, winner_id, created_at, completed_at,
                           p1_rating_change, p2_rating_change, is_private)
SELECT '7a1c9f04-2026-0707-b0f1-000000000104'::uuid,
       sid.id, cat.id, 2, 0, 'completed', sid.id,
       '2026-07-07 10:41:42+00'::timestamptz, '2026-07-07 10:51:51+00'::timestamptz,
       1.1, -3.4, true
FROM players sid, players cat
WHERE sid.steam_id = '76561198040410653' AND cat.steam_id = '76561198853378225'
  AND NOT EXISTS (SELECT 1 FROM ranked_series WHERE id = '7a1c9f04-2026-0707-b0f1-000000000104'::uuid);

-- ── 2. Flip the four matches to ranked + attach to series + XP correction ──
-- A_pancake game 1 -> existing series 88e91fb1 (its sitting's series).
UPDATE matches SET is_ranked = true,
                   series_id = '88e91fb1-c2de-4328-bc36-8485e8b07982'::uuid,
                   p1_xp_gained = 562, p2_xp_gained = 375
WHERE photon_room_id = 'CYDCTL_082909_r6' AND is_ranked = false;

-- Catus games 1+2 -> the new series.
UPDATE matches SET is_ranked = true,
                   series_id = '7a1c9f04-2026-0707-b0f1-000000000104'::uuid,
                   p1_xp_gained = 562, p2_xp_gained = 375
WHERE photon_room_id IN ('CLFPEN_104142_r8', 'CLFPEN_104758_r6') AND is_ranked = false;

-- Catus game 3 -> existing series 8dbcf532 (note: that series row is p1=Catus,
-- p2=Sid; the match row is p1=Sid — series score fields are NOT touched, they
-- already read 0-2 with winner Sid).
UPDATE matches SET is_ranked = true,
                   series_id = '8dbcf532-7e45-4843-ba2d-a8d9a9efb028'::uuid,
                   p1_xp_gained = 562, p2_xp_gained = 375
WHERE photon_room_id = 'CLFPEN_105207_r9' AND is_ranked = false;

-- ── 3. Player XP totals (winner +187/game, loser +125/game) ────────────────
-- Guard: only apply once, keyed on the gold ledger row below not existing yet.
UPDATE players SET total_xp = total_xp + 748
WHERE steam_id = '76561198040410653'
  AND NOT EXISTS (SELECT 1 FROM gold_transactions
                  WHERE reference_id = '7a1c9f04-2026-0707-b0f1-000000000104' AND reason = 'series_win');
UPDATE players SET total_xp = total_xp + 125
WHERE steam_id = '76561198993605415'
  AND NOT EXISTS (SELECT 1 FROM gold_transactions
                  WHERE reference_id = '7a1c9f04-2026-0707-b0f1-000000000104' AND reason = 'series_win');
UPDATE players SET total_xp = total_xp + 375
WHERE steam_id = '76561198853378225'
  AND NOT EXISTS (SELECT 1 FROM gold_transactions
                  WHERE reference_id = '7a1c9f04-2026-0707-b0f1-000000000104' AND reason = 'series_win');

-- ── 4. Glicko-2 rating period for the new completed series ─────────────────
-- Computed offline with backend/api/glicko2.py (tau=0.5) from live values:
--   Sid   2324.650858525516/109.23534286005643/0.05993492595602146 -> beat Catus
--   Catus 1428.944660664006/290.05407092197174/0.05999849771099005 -> lost to Sid
UPDATE glicko_ratings g SET
    rating = 2325.768612706973,
    rating_deviation = 109.47611409957004,
    volatility = 0.05993477331947928,
    peak_rating = GREATEST(COALESCE(peak_rating, 0), 2325.768612706973),
    updated_at = NOW()
FROM players p
WHERE p.id = g.player_id AND p.steam_id = '76561198040410653'
  AND NOT EXISTS (SELECT 1 FROM gold_transactions
                  WHERE reference_id = '7a1c9f04-2026-0707-b0f1-000000000104' AND reason = 'series_win');

UPDATE glicko_ratings g SET
    rating = 1425.5256918693242,
    rating_deviation = 287.5507460037329,
    volatility = 0.05999840914167679,
    updated_at = NOW()
FROM players p
WHERE p.id = g.player_id AND p.steam_id = '76561198853378225'
  AND NOT EXISTS (SELECT 1 FROM gold_transactions
                  WHERE reference_id = '7a1c9f04-2026-0707-b0f1-000000000104' AND reason = 'series_win');

INSERT INTO rating_history (player_id, rating, rating_deviation, volatility, period_end)
SELECT p.id, 2325.768612706973, 109.47611409957004, 0.05993477331947928, NOW()
FROM players p WHERE p.steam_id = '76561198040410653'
  AND NOT EXISTS (SELECT 1 FROM gold_transactions
                  WHERE reference_id = '7a1c9f04-2026-0707-b0f1-000000000104' AND reason = 'series_win');
INSERT INTO rating_history (player_id, rating, rating_deviation, volatility, period_end)
SELECT p.id, 1425.5256918693242, 287.5507460037329, 0.05999840914167679, NOW()
FROM players p WHERE p.steam_id = '76561198853378225'
  AND NOT EXISTS (SELECT 1 FROM gold_transactions
                  WHERE reference_id = '7a1c9f04-2026-0707-b0f1-000000000104' AND reason = 'series_win');

-- ── 5. Series-win gold (10 + 2 sweep) + ledger row ──────────────────────────
-- The ledger row doubles as the idempotency marker for steps 3-5, so it is
-- inserted LAST inside the transaction.
UPDATE players SET gold_earned = gold_earned + 12
WHERE steam_id = '76561198040410653'
  AND NOT EXISTS (SELECT 1 FROM gold_transactions
                  WHERE reference_id = '7a1c9f04-2026-0707-b0f1-000000000104' AND reason = 'series_win');

INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT p.id, 12, 'series_win', '7a1c9f04-2026-0707-b0f1-000000000104'
FROM players p WHERE p.steam_id = '76561198040410653'
  AND NOT EXISTS (SELECT 1 FROM gold_transactions
                  WHERE reference_id = '7a1c9f04-2026-0707-b0f1-000000000104' AND reason = 'series_win');

COMMIT;

-- Verification (run via sql-readonly after applying):
--   SELECT photon_room_id, is_ranked, series_id FROM matches WHERE photon_room_id IN
--     ('CYDCTL_082909_r6','CLFPEN_104142_r8','CLFPEN_104758_r6','CLFPEN_105207_r9');
--   SELECT * FROM ranked_series WHERE id = '7a1c9f04-2026-0707-b0f1-000000000104';
