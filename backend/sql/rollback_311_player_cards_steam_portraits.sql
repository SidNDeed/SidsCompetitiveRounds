-- rollback_311_player_cards_steam_portraits.sql
-- The pre-rollback clear for the Steam pictures unit (Steam pictures v4 §8,
-- v4.1 §1). NOT a migration: the release train never lists it under
-- schema_sql and it is idempotent (a second run changes nothing). Apply it
-- with the migrate: verb BEFORE deploying any api SHA older than the Sept 12
-- batch's code SHA once a Steam picture has been stored, because the older
-- code neither clears the Steam unit when a player opts out, chooses None or
-- deletes their data, nor ages the derived-face cache, so a picture stored
-- by the newer code would stay referenced (and keep rendering into faces)
-- for as long as the older code ran.
--   1. every player's Steam unit is withdrawn: hash, reference and failure
--      run; the attempt id advances so a fetch still in flight binds to
--      nothing; and the row is PARKED: pc_steam_portrait_next_at moves a
--      century out, which the claim's due predicate (next_at IS NULL OR
--      next_at <= now()) can never match. So no claim can start in ANY
--      process — the newer code still running between this file and the
--      old SHA included — and the transition needs no sweep quiescence to
--      arrange or verify. Older code ignores the column. After a forward
--      redeploy of the Sept 12 code, resume_311_player_cards_steam_portraits.sql
--      unparks the rows (the sweep then re-fetches everyone).
--   2. every blob no row references any more is marked released, so the
--      newer code's janitor deletes it ten minutes after its next deploy
--      (older code ignores the mark; the blobs simply wait);
--   3. the derived-face cache is NOT touched here: faces that composited a
--      withdrawn picture are keyed by revisions the older code never asks
--      for again, and its cache evicts by capacity only. If they must go at
--      once, clear the PC_FACE_CACHE_DIR mount (docker-compose.yml) on BOTH
--      boxes before the older code starts.
-- Explicit transaction: psql -f autocommits statement by statement (#340).
BEGIN;

UPDATE players
   SET pc_steam_portrait_hash = NULL, pc_steam_avatar_ref = NULL, pc_steam_portrait_fail = 0,
       pc_steam_portrait_next_at = now() + make_interval(years => 100),
       pc_steam_attempt = pc_steam_attempt + 1
 WHERE pc_steam_portrait_next_at IS NULL
    OR pc_steam_portrait_next_at < now() + make_interval(years => 50);

UPDATE pc_portraits p SET unreferenced_since = now()
 WHERE p.unreferenced_since IS NULL
   AND NOT EXISTS (SELECT 1 FROM players q
                    WHERE q.pc_game_portrait_hash = p.hash OR q.pc_steam_portrait_hash = p.hash);

COMMIT;
