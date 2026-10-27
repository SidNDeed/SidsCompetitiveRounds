-- rollback_338_faq_channel_post_revisions.sql
-- Roll back migration 338 only after the API and the bot that read or write
-- the revision columns have been rolled back. NOT a release-train migration.
-- Explicit transaction (learning #340).
-- DEPLOY ORDER: THE API AND THE BOT FIRST (roll back readers and writers:
-- the api's pending SELECT and its hand-out UPDATE name these columns), then
-- this file.
--
-- What this reverses: the nine revision-acked columns and the partial index
-- that 338 section 1 added. What it leaves in place: the corrected #scr-faq
-- bodies that 338 section 2 wrote into pending_channel_posts.content. Those
-- six rows already carry posted_at, and posted_at IS NULL is what the pre-338
-- pending SELECT filters on, so the pre-338 bot re-sends nothing; the
-- corrected text simply stays the stored text, and the message on Discord
-- keeps whatever the upgraded bot last rendered.

BEGIN;

DROP INDEX IF EXISTS idx_pending_channel_posts_unrendered;

ALTER TABLE pending_channel_posts
    DROP COLUMN IF EXISTS message_id,
    DROP COLUMN IF EXISTS revision,
    DROP COLUMN IF EXISTS posted_revision,
    DROP COLUMN IF EXISTS adopt_fingerprint,
    DROP COLUMN IF EXISTS claimed_at,
    DROP COLUMN IF EXISTS claimed_token,
    DROP COLUMN IF EXISTS handed_revision,
    DROP COLUMN IF EXISTS handed_fingerprint,
    DROP COLUMN IF EXISTS handed_revisionless;

COMMIT;
