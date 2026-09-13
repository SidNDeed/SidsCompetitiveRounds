-- resume_311_player_cards_steam_portraits.sql
-- The companion of rollback_311_player_cards_steam_portraits.sql (Steam
-- pictures v4.1 §1). NOT a migration and idempotent. That file PARKS every
-- player (pc_steam_portrait_next_at a century out) so no claim can start
-- while an older api SHA is being deployed; once the Sept 12 batch's code
-- (or newer) is live on both boxes again, apply this file with the migrate:
-- verb to unpark the rows — the sweep then claims and re-fetches everyone in
-- its usual order. Rows never parked (next_at within the next fifty years)
-- are untouched. Explicit transaction (#340).
BEGIN;

UPDATE players
   SET pc_steam_portrait_next_at = NULL
 WHERE pc_steam_portrait_next_at > now() + make_interval(years => 50);

COMMIT;
