-- 139_lfp_pings.sql — July 21
--
-- 'Looking For Player' Discord role pings: queued by POST /api/v1/lfp-ping
-- (the in-game LFP button) and drained by the bot's poll_lfp_pings loop into
-- the queue-beacon channel with a ping to the LFP role (durable ack pattern,
-- learning #105 family — posted_at NULL and not undeliverable = pending; the
-- pending poll also filters expires_at > now() so stale rows self-heal).
--
-- The table doubles as the 1-hour cooldown store: MAX(created_at) per
-- steam_id — survives restarts, multi-worker-safe (learning #125).

CREATE TABLE IF NOT EXISTS lfp_pings (
    id            BIGSERIAL PRIMARY KEY,
    steam_id      VARCHAR(20) NOT NULL,
    message       TEXT NOT NULL DEFAULT '',
    expires_minutes INT NOT NULL DEFAULT 60,
    expires_at    TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_at     TIMESTAMPTZ,
    undeliverable BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_lfp_pings_pending ON lfp_pings(created_at) WHERE posted_at IS NULL AND NOT undeliverable;
CREATE INDEX IF NOT EXISTS idx_lfp_pings_by_steam ON lfp_pings(steam_id, created_at DESC);
