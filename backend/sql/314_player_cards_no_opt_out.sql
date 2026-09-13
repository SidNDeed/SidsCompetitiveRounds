-- 314: Player Cards — no opt-out, no picture choice (2026-09-13).
--
-- Every registered player is a card and every card carries a picture: the
-- uploaded character face once the game has sent one, else the Steam
-- profile picture, else the emblem. Deleting all data is the one way a
-- card leaves every binder (the api's deletion endpoint now removes the
-- prints of the deleted player's card from every holder).
--
-- The two columns that carried the choices — pc_opted_out_at (308) and
-- pc_portrait_source (310) — are no longer read or written by the api.
-- They are RETAINED, not dropped: the previous api selects them, so a
-- rollback past this batch must still find them. They are reset here so
-- that such a rollback sees the same world the new code does. A later
-- release drops them once this one is out of its rollback window.
--
-- Rows a choice had excluded re-enter the Steam sweep at once: their
-- schedule is cleared (the claim orders NULLS FIRST), exactly as the old
-- "back to the character" write did. Deleted rows are left alone here —
-- their deleted_at keeps them out of every predicate; the prints and cards
-- of a subject deleted before this batch are removed by 315, which runs
-- AFTER the api that deletes them itself is live (the deploy interval).
--
-- The index rebuild takes the table's lock queue for the duration of a
-- CREATE INDEX on players (4,925 rows, 1.4 MB on 2026-09-13: milliseconds).
-- What could hurt is WAITING for that lock behind a long transaction, with
-- every later query queued behind this one: the timeout turns that into a
-- clean failure, and the file is re-runnable as written (IF EXISTS, IF NOT
-- EXISTS, idempotent UPDATEs).
BEGIN;
SET LOCAL lock_timeout = '5s';

UPDATE players
   SET pc_steam_portrait_next_at = NULL
 WHERE deleted_at IS NULL
   AND (pc_opted_out_at IS NOT NULL OR pc_portrait_source IS DISTINCT FROM 'game');

UPDATE players
   SET pc_opted_out_at = NULL,
       pc_portrait_source = 'game'
 WHERE pc_opted_out_at IS NOT NULL OR pc_portrait_source IS DISTINCT FROM 'game';

-- The sweep's claim no longer names the two columns, and a partial index
-- whose predicate the query does not imply is never used: rebuild it on
-- the predicate the claim still has (311 created the original).
DROP INDEX IF EXISTS players_pc_steam_portrait_next_at_idx;
CREATE INDEX IF NOT EXISTS players_pc_steam_portrait_next_at_idx
    ON players (pc_steam_portrait_next_at ASC NULLS FIRST)
    WHERE deleted_at IS NULL;

COMMIT;
