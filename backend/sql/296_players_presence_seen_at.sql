-- 296_players_presence_seen_at.sql
-- The leaderboards' online marker (bug 342) needs a liveness stamp that ONLY
-- the presence heartbeat writes. players.last_seen is also stamped by
-- get_or_create_player, i.e. for every participant a match or disconnect
-- report names, so a queued report filed after an opponent had quit kept
-- their dot lit for up to three minutes.
--
-- Written by /api/v1/presence/ping only (the mod's ~60 s heartbeat); NULL until
-- a client's first ping after this deploy, and NULL compares as "not online".
-- Deliberately not declared on the ORM Player model: raw SQL on both ends.
--
-- Deploy order: apply this on the primary BEFORE the api build that selects
-- the column; the standby receives it by streaming replication and serves the
-- boards from it.
BEGIN;
ALTER TABLE players ADD COLUMN IF NOT EXISTS presence_seen_at TIMESTAMPTZ;
COMMIT;
