-- 079_backfill_economy_for_recovered_2v2_series.sql
-- Migrations 077 + 078 stitched the data rows back together but did NOT
-- credit the players the gold/XP they earned, nor populate the per-slot
-- accumulator columns the F5 history view reads. This migration closes
-- that gap for the four recovered matches across two series.
--
-- Economy constants (mirrors backend/api/main.py L5101+):
--   TEAM_MATCH_XP_BASE       = 600
--   TEAM_MATCH_WIN_MULT      = 1.5    -> 900 xp per match-win
--   100 xp = 1 gold (auto-conversion at submit)
--   TEAM_SERIES_WIN_GOLD     = 50     (one-shot, on series completion)
--   TEAM_SERIES_LOSS_GOLD    = 25
--
-- Both series went 2-0 to T2 (Sid + feauxen). Per-slot deltas:
--   T1 (loser, 2 matches): +1200 xp, +12 gold xp-conv, +25 gold series-loss
--   T2 (winner, 2 matches): +1800 xp, +18 gold xp-conv, +50 gold series-win
-- Across BOTH series, per slot:
--   t1a / t1b: +2400 xp, +74 gold total
--   t2a / t2b: +3600 xp, +136 gold total
--
-- Glicko rating_change (t1a_rating_change etc.) is intentionally left
-- NULL on the recovered series. The 2v2 rating period closed
-- without these matches; a backdated Glicko recompute would need
-- snapshot ratings we no longer have. The F5 UI omits the elo delta
-- chip when rating_change is NULL/0, which reads correctly for these.

-- Populate per-slot accumulators on the two recovered series rows.
UPDATE team_series
   SET t1a_xp_earned   = 1200, t1b_xp_earned   = 1200,
       t2a_xp_earned   = 1800, t2b_xp_earned   = 1800,
       t1a_gold_earned = 37,   t1b_gold_earned = 37,
       t2a_gold_earned = 68,   t2b_gold_earned = 68
 WHERE id IN (
     '4ea30d95-9612-4f71-a4f0-47dd4a064da3',
     'cdd8d17a-64b4-488c-9e73-90b66299cd77'
 );

-- Credit each player. T1A + T1B got +2400 xp + 74 gold total across both
-- series; T2A + T2B got +3600 xp + 136 gold.
WITH t1_players AS (
    SELECT id FROM players WHERE steam_id IN ('76561199057431340','76561199261741278')
),
t2_players AS (
    SELECT id FROM players WHERE steam_id IN ('76561198040410653','76561198081664646')
)
UPDATE players p
   SET total_xp = COALESCE(total_xp,0) + CASE WHEN p.id IN (SELECT id FROM t1_players) THEN 2400 ELSE 3600 END,
       team_xp_earned   = COALESCE(team_xp_earned,0) + CASE WHEN p.id IN (SELECT id FROM t1_players) THEN 2400 ELSE 3600 END,
       gold_earned      = COALESCE(gold_earned,0) + CASE WHEN p.id IN (SELECT id FROM t1_players) THEN 74 ELSE 136 END,
       team_gold_earned = COALESCE(team_gold_earned,0) + CASE WHEN p.id IN (SELECT id FROM t1_players) THEN 74 ELSE 136 END
 WHERE p.id IN (SELECT id FROM t1_players UNION SELECT id FROM t2_players);

-- Audit-trail gold_transactions rows. One row per series for xp-conv +
-- series-bonus, keyed to the recovered series_ids.
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT p.id, 12, 'team_xp', '4ea30d95-9612-4f71-a4f0-47dd4a064da3'
  FROM players p WHERE p.steam_id IN ('76561199057431340','76561199261741278')
UNION ALL
SELECT p.id, 25, 'team_series_loss', '4ea30d95-9612-4f71-a4f0-47dd4a064da3'
  FROM players p WHERE p.steam_id IN ('76561199057431340','76561199261741278')
UNION ALL
SELECT p.id, 18, 'team_xp', '4ea30d95-9612-4f71-a4f0-47dd4a064da3'
  FROM players p WHERE p.steam_id IN ('76561198040410653','76561198081664646')
UNION ALL
SELECT p.id, 50, 'team_series_win', '4ea30d95-9612-4f71-a4f0-47dd4a064da3'
  FROM players p WHERE p.steam_id IN ('76561198040410653','76561198081664646')
UNION ALL
SELECT p.id, 12, 'team_xp', 'cdd8d17a-64b4-488c-9e73-90b66299cd77'
  FROM players p WHERE p.steam_id IN ('76561199057431340','76561199261741278')
UNION ALL
SELECT p.id, 25, 'team_series_loss', 'cdd8d17a-64b4-488c-9e73-90b66299cd77'
  FROM players p WHERE p.steam_id IN ('76561199057431340','76561199261741278')
UNION ALL
SELECT p.id, 18, 'team_xp', 'cdd8d17a-64b4-488c-9e73-90b66299cd77'
  FROM players p WHERE p.steam_id IN ('76561198040410653','76561198081664646')
UNION ALL
SELECT p.id, 50, 'team_series_win', 'cdd8d17a-64b4-488c-9e73-90b66299cd77'
  FROM players p WHERE p.steam_id IN ('76561198040410653','76561198081664646');
