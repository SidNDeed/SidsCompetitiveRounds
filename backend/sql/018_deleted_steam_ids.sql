-- 018_deleted_steam_ids.sql
--
-- Blocklist of previously-purged Steam IDs. Stored as one-way hashes of
-- sha256(MATCH_HMAC_SECRET + ':' + steam_id) so the table can't be brute-
-- forced against a Steam ID list without the server secret.
--
-- Used to prevent "spoofing" — a player deleting their data and re-registering
-- with a fresh Elo. When the anonymize endpoint runs it inserts the hash;
-- subsequent get_or_create_player calls for that Steam ID produce a permanent
-- [Deleted User] tombstone row instead of a fresh player.

CREATE TABLE IF NOT EXISTS deleted_steam_ids (
    steam_id_hash CHAR(64) PRIMARY KEY,
    deleted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
