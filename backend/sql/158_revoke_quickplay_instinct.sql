-- 158: revoke one wrongly-granted Instinct (bug #101). The reporter earned it
-- from public quickplay while scrolling/picking non-leftmost cards — the
-- violation detectors only run in competitive rooms, so quickplay wins could
-- only ever look clean. Achievements now evaluate only in competitive rooms
-- (client fix); this removes the one unlock its owner reported as false.
-- Other recent unlocks are left untouched pending owner confirmation.
DELETE FROM player_achievements
 WHERE achievement_key = 'instinct'
   AND player_id = (SELECT id FROM players WHERE steam_id = '76561199121899818')
   AND unlocked_at >= '2026-07-28 00:00:00+00';
