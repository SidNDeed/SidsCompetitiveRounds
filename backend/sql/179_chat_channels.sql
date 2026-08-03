-- 179: chat channel split (localization-design §2.6, D5) + the two cheap
-- v2-moderation groundwork pieces that cannot be retrofitted later:
--   channel     — 'global' (mandatory floor) | 'ru' | 'es'; every existing
--                 row is global by definition.
--   deleted_at  — v1 ships NO removal mechanism (D16 accepted risk), but a
--                 message relayed without this column can never be redacted
--                 retroactively; costing the column now is free.
--
-- MUST run BEFORE the API deploy that writes channel (hot INSERT — #235).

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS channel VARCHAR(16) NOT NULL DEFAULT 'global';
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS ix_chat_messages_channel_created
    ON chat_messages (channel, created_at DESC);

DO $$ BEGIN RAISE NOTICE '179 chat_channels: post-check OK'; END $$;
