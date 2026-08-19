-- 230: session matchup list on the living stream post (Sid, Aug 18: the
-- ended/VOD message must say WHICH matches the stream covered, so players
-- can find the VOD holding their games).
--
-- The upkeep path appends each DISTINCT rendered matchup line (names + elo +
-- mode, no score) while the session is live, capped at 25 entries; the
-- finalize edit renders them under the VOD links. TEXT[] because entries are
-- pre-composed display lines, not structured data — the composer owns the
-- format and older rows simply render no list.
BEGIN;

ALTER TABLE stream_channel_posts
    ADD COLUMN IF NOT EXISTS matchups TEXT[] NOT NULL DEFAULT '{}';

COMMIT;
