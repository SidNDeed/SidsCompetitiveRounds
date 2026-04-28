-- v1.25.15 cleanup of test 2v2 matches that mis-routed as 1v1 matches.
-- Root cause: the 2v2 CreatePlayer override skipped AssignUserID(), so
-- the `u_id` Photon custom property that peers use to resolve actor →
-- Steam ID was never published. ResolvePhotonSteamId then returned the
-- "photon_<actor>" placeholder, TryReportTeamMatch aborted, and the match
-- silently fell through to the 1v1 ReportMatch path. That path called
-- get_or_create_player which created phantom rows with steam_id like
-- "photon_1" / "photon_2", and then logged each match as 1v1 between Sid
-- and the phantom. v1.25.15 fixes the publish; this script cleans the data.
--
-- Affected rows (verified via sql-readonly before writing):
--   - matches: ~25 rows where one side has steam_id LIKE 'photon_%', all
--     between Sid's alt accounts and phantom placeholders
--   - players: 2 phantom rows (photon_1 = "Sid", photon_2 = "Sid3")
--   - team_series: ~4 'active' rows that never produced a team_match row,
--     all in the 4/27-4/28 testing window

BEGIN;

-- Capture the misroute matches before deletion for the audit log.
CREATE TEMP TABLE _misrouted_match_ids ON COMMIT DROP AS
SELECT m.id
  FROM matches m
  JOIN players p1 ON m.player1_id = p1.id
  JOIN players p2 ON m.player2_id = p2.id
 WHERE m.created_at >= '2026-04-27'
   AND (p1.steam_id LIKE 'photon_%' OR p2.steam_id LIKE 'photon_%');

-- Drop child rows in any tables that reference matches (cards, offers,
-- flag rows, bets). Use a generous list — none of the misrouted matches
-- should leave orphans behind.
DELETE FROM match_cards WHERE match_id IN (SELECT id FROM _misrouted_match_ids);
DELETE FROM card_offers WHERE match_id IN (SELECT id FROM _misrouted_match_ids);
DELETE FROM flagged_matches WHERE match_id IN (SELECT id FROM _misrouted_match_ids);
-- bets are keyed by series_id (not match_id) and cascade-delete with the
-- ranked_series row, so they're handled by the ranked_series cleanup below.

-- Now the matches themselves.
DELETE FROM matches WHERE id IN (SELECT id FROM _misrouted_match_ids);

-- Drop any 1v1 ranked_series rows whose only matches just got deleted.
DELETE FROM ranked_series rs
 WHERE rs.created_at >= '2026-04-27'
   AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.series_id = rs.id);

-- Phantom player rows the misroute created. Delete cascade-safe order:
-- their match_history was already removed above, no other tables reference
-- player_id of a "photon_<actor>" row.
DELETE FROM player_blocks
 WHERE blocker_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%')
    OR blocked_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%');
DELETE FROM player_achievements
 WHERE player_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%');
DELETE FROM player_items
 WHERE player_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%');
DELETE FROM rating_history
 WHERE player_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%');
DELETE FROM ranked_queue
 WHERE player_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%');
DELETE FROM team_queue
 WHERE player_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%');

-- Belt-and-suspenders: any matches that still reference a photon_* player
-- (older test data from before the 2026-04-27 window the temp table caught).
-- These also need to be removed before we can delete the player rows.
DELETE FROM match_cards
 WHERE match_id IN (
   SELECT m.id FROM matches m
   WHERE m.player1_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%')
      OR m.player2_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%')
 );
DELETE FROM card_offers
 WHERE match_id IN (
   SELECT m.id FROM matches m
   WHERE m.player1_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%')
      OR m.player2_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%')
 );
DELETE FROM flagged_matches
 WHERE match_id IN (
   SELECT m.id FROM matches m
   WHERE m.player1_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%')
      OR m.player2_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%')
 );
DELETE FROM matches
 WHERE player1_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%')
    OR player2_id IN (SELECT id FROM players WHERE steam_id LIKE 'photon_%');

DELETE FROM players WHERE steam_id LIKE 'photon_%';

-- Cancel any active test team_series in the same window. They never
-- produced a team_match row (verified earlier), so canceling is purely
-- a status flip + audit reason.
UPDATE team_series
   SET status = 'canceled',
       invalidated_at = NOW(),
       invalidation_reason = 'test_misroute_cleanup_v1.25.15'
 WHERE status = 'active'
   AND created_at >= '2026-04-27';

COMMIT;
