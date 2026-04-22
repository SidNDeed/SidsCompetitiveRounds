-- v1.23.x — Purge phantom "offline room" matches from the DB.
--
-- Context: ROUNDS' offline / practice mode uses a photon room name like "offline room"
-- with an AI opponent. The mod's cached opponent_steam_id from the most recent online
-- match would leak into those offline reports, so the server recorded phantom matches
-- attributing a 5-0 loss to the real player from the previous session. Confirmed in
-- production: two phantom matches reported by "Nix ツ" against "Sid" with
-- photon_room_id starting with 'offline room'.
--
-- This migration hard-deletes every such row. Child tables (match_cards, card_offers,
-- flagged_matches, gold_transactions keyed on match.id) cascade via their FKs.
-- Client-side block AND server-side rejection were both added in the same pass so new
-- offline matches can't reach the DB going forward.
--
-- Idempotent.

-- Pre-flight: log how many we're about to delete so the migration output is informative.
DO $$
DECLARE n integer;
BEGIN
    SELECT COUNT(*) INTO n FROM matches
     WHERE photon_room_id IS NOT NULL AND LOWER(photon_room_id) LIKE '%offline%';
    RAISE NOTICE 'Purging % offline phantom matches', n;
END $$;

DELETE FROM matches
 WHERE photon_room_id IS NOT NULL
   AND LOWER(photon_room_id) LIKE '%offline%';
