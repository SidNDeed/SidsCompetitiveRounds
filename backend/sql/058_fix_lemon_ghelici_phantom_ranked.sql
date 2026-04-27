-- 058_fix_lemon_ghelici_phantom_ranked.sql
-- Lemon32p (76561199106086874) and Ghelici (76561198093336650) played 3 casual
-- private-room matches on 2026-04-26 that the mod incorrectly reported as
-- ranked because both had ranked_enabled=true. The room wasn't a queue room.
-- Mod-side fix in v1.25.1+ requires the room name to start with ranked_/team_/
-- sct- before the match counts as ranked; this migration cleans up the data
-- those 3 matches already left behind.
--
-- Series eebe9860-70eb-44fc-b6ed-863c5259d9c1 → completed, Lemon +24.5,
-- Ghelici -448.4. Invalidating the series and reversing both rating deltas.

-- 1. Mark the 3 matches as casual + invalidated.
UPDATE matches
SET is_ranked = false,
    invalidated_at = NOW(),
    invalidation_reason = 'phantom_ranked_private_room'
WHERE id IN (
    'a3c62914-5321-4a2c-8feb-b5e2192bc263',
    'd8194b43-a1fa-41cb-8fce-09ca3dbb3e91',
    'd0cecbde-1584-4e71-9c39-57225661d499'
);

-- 2. Mark the series invalidated so it stops counting in any leaderboard /
--    series-W/L aggregations.
UPDATE ranked_series
SET status = 'invalidated',
    invalidated_at = NOW(),
    invalidation_reason = 'phantom_ranked_private_room'
WHERE id = 'eebe9860-70eb-44fc-b6ed-863c5259d9c1';

-- 3. Reverse the Glicko deltas. Lemon (player1) +24.5 → subtract; Ghelici
--    (player2) -448.4 → add back. Peak rating stays where it is — the series
--    didn't push either above their existing peak, so no correction needed.
UPDATE glicko_ratings
SET rating = rating - 24.5,
    updated_at = NOW()
WHERE player_id = '9c587ddf-556c-428b-bcb1-503029dc729a';  -- Lemon32p

UPDATE glicko_ratings
SET rating = rating + 448.4,
    updated_at = NOW()
WHERE player_id = '4e252a43-65df-43a7-abde-046f35c9c160';  -- Ghelici
