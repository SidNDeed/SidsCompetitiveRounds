-- 226: Living stream posts for #scr-ranked-streaming (Aug 17).
--
-- One row per broadcast STREAM SESSION. Unlike pending_channel_posts (an
-- append-only fire-once bus), a stream post is EDITED across its life —
-- match switches, score changes, final "stream ended" state — so delivery
-- is revision-acked (#175: the ack binds to the exact revision rendered)
-- and the Discord message id is stored DURABLY here (#129: a bot restart
-- must not orphan the living message).
--
-- Deliberately a separate table from pending_channel_posts: that bus is
-- strictly ordered and a stuck stream post would stall admin alerts behind
-- it (failure-domain coupling; #187 family).
--
-- Idempotent statement-by-statement (#243 - the deploy wrapper's || retry
-- reruns the whole file).

BEGIN;

CREATE TABLE IF NOT EXISTS stream_channel_posts (
    post_key        TEXT PRIMARY KEY,          -- stream session id from the VM bot
    channel_id      TEXT NOT NULL,
    content         TEXT NOT NULL,             -- body WITHOUT the live timestamp (bot stamps it)
    revision        INTEGER NOT NULL DEFAULT 1,
    finalized       BOOLEAN NOT NULL DEFAULT FALSE,
    message_id      TEXT,                      -- Discord message id, written back by the bot's ack
    posted_revision INTEGER,                   -- last revision the bot confirmed rendered
    last_live_at    TIMESTAMPTZ NOT NULL DEFAULT now(),  -- last stream_live poll carrying this session
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The bot polls for rows whose rendered state lags the desired state.
CREATE INDEX IF NOT EXISTS idx_stream_posts_pending
    ON stream_channel_posts (updated_at)
    WHERE posted_revision IS DISTINCT FROM revision;

COMMIT;
