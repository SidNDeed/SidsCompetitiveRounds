-- 072_tournament_match_photon_room.sql
-- Per-match server-issued Photon room name. Replaces the previous
-- client-side derivation ("sct-" + match_id[:12]) which depended on both
-- clients computing the same string from the same UUID — fragile if the
-- string-split logic ever drifted between builds. Server now allocates
-- the room name at activation time (when status flips to 'ready') and
-- the client simply uses what the API returns.
--
-- Backfill existing 'ready'/'active' matches with the legacy derived
-- name so any tournament that's mid-flight when this migration lands
-- doesn't break.

ALTER TABLE tournament_matches
    ADD COLUMN IF NOT EXISTS photon_room_name VARCHAR(64);

UPDATE tournament_matches
   SET photon_room_name = 'sct-' || REPLACE(SUBSTRING(id::text, 1, 13), '-', '')
 WHERE photon_room_name IS NULL
   AND status IN ('ready', 'active');
