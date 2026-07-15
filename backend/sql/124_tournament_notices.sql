-- 124_tournament_notices.sql
--
-- v1.31: durable tournament DM queue (learning #105 — acked server-side
-- notices instead of bot in-memory state, so bot restarts can't drop DMs).
-- First notice type: 'availability_check' — queued by tournament_tick for
-- every confirmed signup when a voting tournament with quorum is 24-96h
-- from its start (sync) / signup close (async). The bot polls
-- GET /api/v1/internal/tournament-notices?unnotified=true and acks
-- notified_at via POST /api/v1/internal/tournament-notices/ack after the
-- DM lands.
--
-- UNIQUE(tournament_id, player_id, notice_type) doubles as the replay guard
-- for the tick's ON CONFLICT DO NOTHING insert — all three columns are
-- NOT NULL (learning #147: a UNIQUE used as a replay guard must have
-- all-NOT-NULL columns).
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS tournament_notices (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    player_id     UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    notice_type   VARCHAR(32) NOT NULL,
    payload       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notified_at   TIMESTAMPTZ,
    UNIQUE (tournament_id, player_id, notice_type)
);

-- Partial index for the bot's unnotified poll (mirrors
-- idx_pending_channel_posts_unposted from migration 109).
CREATE INDEX IF NOT EXISTS idx_tournament_notices_unnotified
    ON tournament_notices (created_at)
    WHERE notified_at IS NULL;
