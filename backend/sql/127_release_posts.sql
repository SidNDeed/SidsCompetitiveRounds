-- 127_release_posts.sql
--
-- Mirror of the #scr-releases Discord channel (v1.33 Home tab). The bot
-- pushes every message posted (or edited) in the releases channel via
-- POST /internal/release-posts; the Home tab reads GET /releases/recent so
-- players see update notes as they're posted, not just when they update.
--
-- discord_message_id is the replay/dedup guard — NOT NULL UNIQUE per
-- learning #147 (edits upsert content by the same id).
-- Idempotent (IF NOT EXISTS guards).

CREATE TABLE IF NOT EXISTS release_posts (
    id                 BIGSERIAL PRIMARY KEY,
    discord_message_id VARCHAR(24) NOT NULL UNIQUE,
    author             VARCHAR(64) NOT NULL DEFAULT '',
    content            TEXT NOT NULL,
    posted_at          TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_release_posts_posted ON release_posts (posted_at DESC);

SELECT COUNT(*) AS release_posts_rows FROM release_posts;
