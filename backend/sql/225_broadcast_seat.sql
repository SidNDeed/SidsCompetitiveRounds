-- 225: Reserved broadcast spectator seat and durable drain occupancy.
--
-- Known pre-policy service-account history is intentionally left untouched:
-- Steam account 76561198709950406 has two terminal 0-0 ranked series from
-- 2026-04-28, three XP/gold ledger rows totalling 7g from casual testing, and
-- one default 1500 rating row with zero matches.  These rows predate the
-- SERVICE_POLICY_WATERMARK and are harmless historical records; the runtime
-- audit only pages on references created or updated after that watermark.
--
-- Idempotent statement-by-statement (#243).  Explicit transaction (#340).

BEGIN;

ALTER TABLE spectate_games
    ALTER COLUMN spectator_cap SET DEFAULT 5;

UPDATE spectate_games
   SET spectator_cap = 5
 WHERE ended_at IS NULL AND spectator_cap < 5;

CREATE TABLE IF NOT EXISTS spectate_drain_tombstones (
    room_name VARCHAR(64) NOT NULL,
    region VARCHAR(16) NOT NULL DEFAULT '',
    ghost_steam_id VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_spectate_drain_tombstone
        UNIQUE (room_name, region, ghost_steam_id)
);

CREATE INDEX IF NOT EXISTS idx_spectate_drain_tombstones_age
    ON spectate_drain_tombstones (created_at);

COMMIT;
