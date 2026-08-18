-- 229: Stream-ended posts keep their links + direct VOD urls (Aug 18).
--
-- Per request: the finalize edit stripped the twitch/youtube links. It now
-- links the session's own VODs — resolved by the VM bot with its platform
-- creds WHILE LIVE (Twitch mints the archive at broadcast start; the
-- YouTube broadcast id IS the video id), carried on the mod's authenticated
-- /broadcast/target poll, stored here, rendered only by the finalize edit.
-- Channel archive pages are the fallback when a session never resolved them.
--
-- Idempotent statement-by-statement (#243 — the deploy wrapper's || retry
-- reruns the whole file). Explicit BEGIN/COMMIT (#340 — psql -f autocommits
-- per statement otherwise).

BEGIN;

ALTER TABLE stream_channel_posts ADD COLUMN IF NOT EXISTS twitch_vod_url  TEXT;
ALTER TABLE stream_channel_posts ADD COLUMN IF NOT EXISTS youtube_vod_url TEXT;

-- Retro-fix already-finalized posts (the visible "links removed" message):
-- re-compose their ended body with the channel fallbacks and bump revision
-- so the Discord bot re-edits the live message. The NOT LIKE guard makes
-- reruns a no-op (#168: the DDL above being idempotent does not make this
-- UPDATE rerun-safe — the predicate does). Body matches the API's
-- _stream_ended_content default-fallback output byte-for-byte.
UPDATE stream_channel_posts
   SET content = E'The stream has ended - thanks for watching!\n' ||
                 E'🎬 Twitch VOD: https://www.twitch.tv/sidscompetitiverounds/videos?filter=archives\n' ||
                 E'▶️ YouTube VOD: https://youtube.com/@SidsCompetitiveRounds/streams',
       revision = revision + 1,
       updated_at = NOW()
 WHERE finalized
   AND content NOT LIKE '%VOD:%';

COMMIT;
