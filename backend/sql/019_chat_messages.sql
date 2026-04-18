-- 019_chat_messages.sql
--
-- Persistent chat history for the in-game ↔ Discord bridge. Every message
-- posted via /api/v1/ws/chat or /api/v1/chat/post is written here so new
-- clients can load scrollback on connect instead of seeing an empty log.
--
-- Bounded by a "keep last 24h" pattern — old rows are pruned on a cron or
-- lazily on read. Index on created_at DESC makes the "recent N" query cheap.

CREATE TABLE IF NOT EXISTS chat_messages (
    id           BIGSERIAL PRIMARY KEY,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source       VARCHAR(16) NOT NULL,   -- 'ingame' or 'discord'
    steam_id     VARCHAR(20),
    discord_id   VARCHAR(20),
    display_name VARCHAR(64) NOT NULL,
    message      VARCHAR(500) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages (created_at DESC);
