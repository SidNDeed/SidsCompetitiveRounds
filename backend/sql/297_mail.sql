-- 297_mail.sql — in-game mail (Sept 6 batch, Group 4 item b, server half).
--
-- Sept 6 batch Group 4 item b, items B-1 .. B-14. The
-- shape decisions that cost a review round, so they are not re-litigated here:
--
--   * mail_recipients is the immutable ADDRESS ENVELOPE: who was addressed, as
--     To or Cc, and whether the copy was delivered or SUPPRESSED (recipient
--     blocks the sender, mail_from = 'nobody', or 'played' with no shared
--     participant set). Suppression is silent (B-7): the sender's response is
--     identical either way and every read path filters delivery = 'delivered'.
--   * mail_blocks is its own table (B-1). player_blocks is MATCHMAKING state
--     and team formation deletes its rows; mail never reads or writes it.
--   * Threads are provenance, not a mutable object (B-9): thread_id is the
--     root message's own id, in_reply_to is a self-FK. Replies derive their
--     recipients server-side from the envelope, so the envelope must never be
--     edited after the send.
--   * UNIQUE (sender_id, idempotency_key): a retried send finds its original
--     row (B-11). Both columns are NOT NULL — a nullable dedup key is no dedup
--     key at all (learning #147).
--   * moderation_cases is the one lifecycle for mail reports and automatic spam
--     buckets (B-10): UNIQUE (kind, bucket_key) makes a repeat report a no-op
--     and a spam burst ONE row per sender per day. evidence is a JSONB snapshot
--     so a later delete cannot empty the report. FlaggedMatch is untouched.
--   * mail_bulk_grants raises the per-message recipient cap for organisers
--     without admin status (B-14). steam_id is VARCHAR(20) like players.steam_id
--     and admin_users.steam_id — steam ids are strings throughout this schema.
--   * mail_censor_hits counts censor refusals per sender (B-14's third spam
--     trigger); rows are pruned after two days by the janitor.
--
-- Retention (janitor): a message is purged once no delivered copy is still
-- unread-and-kept and it is older than 180 days, or once the sender AND every
-- delivered recipient have deleted it. mail_recipients cascades with its
-- message; in_reply_to and moderation_cases.message_id SET NULL (the case keeps
-- its snapshot).
--
-- Deploy order: apply on the primary BEFORE the api build that references these
-- tables (the api boots its janitor self-test against them); the standby
-- receives the schema by streaming replication. Rebuild the bot container after
-- the api for the moderation buttons.

BEGIN;

ALTER TABLE players ADD COLUMN IF NOT EXISTS mail_from TEXT NOT NULL DEFAULT 'everyone';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_players_mail_from') THEN
        ALTER TABLE players ADD CONSTRAINT ck_players_mail_from
            CHECK (mail_from IN ('everyone', 'played', 'nobody'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS mail_messages (
    id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_id            UUID         NOT NULL REFERENCES players(id),
    kind                 TEXT         NOT NULL CHECK (kind IN ('direct', 'system_broadcast')),
    thread_id            UUID         NOT NULL,
    in_reply_to          UUID         NULL REFERENCES mail_messages(id) ON DELETE SET NULL,
    subject              VARCHAR(120) NOT NULL,
    body                 VARCHAR(2000) NOT NULL,
    idempotency_key      UUID         NOT NULL,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_by_sender_at TIMESTAMPTZ  NULL,
    CONSTRAINT uq_mail_messages_sender_idem UNIQUE (sender_id, idempotency_key)
);

-- Rate counts (10/min, 100/day per sender) and the Sent view.
CREATE INDEX IF NOT EXISTS ix_mail_messages_sender_created
    ON mail_messages (sender_id, created_at);
-- Thread reads.
CREATE INDEX IF NOT EXISTS ix_mail_messages_thread_created
    ON mail_messages (thread_id, created_at);

CREATE TABLE IF NOT EXISTS mail_recipients (
    message_id   UUID        NOT NULL REFERENCES mail_messages(id) ON DELETE CASCADE,
    recipient_id UUID        NOT NULL REFERENCES players(id),
    kind         TEXT        NOT NULL CHECK (kind IN ('to', 'cc')),
    delivery     TEXT        NOT NULL CHECK (delivery IN ('delivered', 'suppressed')),
    read_at      TIMESTAMPTZ NULL,
    deleted_at   TIMESTAMPTZ NULL,
    PRIMARY KEY (message_id, recipient_id)
);

-- The unread COUNT and /mail/status: exactly the rows those queries touch.
CREATE INDEX IF NOT EXISTS ix_mail_recipients_unread
    ON mail_recipients (recipient_id)
    WHERE delivery = 'delivered' AND read_at IS NULL AND deleted_at IS NULL;
-- The inbox page and /mail/status's revision: the envelope has no created_at,
-- so the page is one recipient's delivered envelopes joined to mail_messages
-- and sorted by the message's created_at. This partial index hands the join
-- exactly that envelope set (message_id is the join key); the sort is over
-- one player's mail, which is small by the rate limits. Deliberately NOT
-- filtered on deleted_at: the revision is the newest DELIVERED message id
-- whether or not the recipient has since deleted it, so that deleting the
-- newest message can never move the revision backwards (B-6 monotonic
-- cursor); the inbox applies deleted_at IS NULL on the heap rows.
CREATE INDEX IF NOT EXISTS ix_mail_recipients_inbox
    ON mail_recipients (recipient_id, message_id)
    WHERE delivery = 'delivered';

CREATE TABLE IF NOT EXISTS mail_blocks (
    blocker_id UUID        NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    blocked_id UUID        NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (blocker_id, blocked_id)
);

CREATE TABLE IF NOT EXISTS moderation_cases (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kind              TEXT        NOT NULL,
    subject_player_id UUID        NOT NULL REFERENCES players(id),
    reporter_id       UUID        NULL REFERENCES players(id),
    message_id        UUID        NULL REFERENCES mail_messages(id) ON DELETE SET NULL,
    evidence          JSONB       NOT NULL,
    bucket_key        TEXT        NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'dismissed')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at       TIMESTAMPTZ NULL,
    -- The acting moderator's steam id (admin_actions.admin_steam_id convention;
    -- no FK, for the same reason migration 192 dropped admin_actions' one).
    resolved_by       VARCHAR(32) NULL,
    resolution        TEXT        NULL,
    notified_at       TIMESTAMPTZ NULL,
    CONSTRAINT uq_moderation_cases_kind_bucket UNIQUE (kind, bucket_key)
);

CREATE INDEX IF NOT EXISTS ix_moderation_cases_status_created
    ON moderation_cases (status, created_at);

CREATE TABLE IF NOT EXISTS mail_bulk_grants (
    steam_id       VARCHAR(20) PRIMARY KEY,
    max_recipients INTEGER     NOT NULL,
    expires_at     TIMESTAMPTZ NOT NULL,
    granted_by     VARCHAR(20) NULL,
    granted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mail_censor_hits (
    id         BIGSERIAL   PRIMARY KEY,
    sender_id  UUID        NOT NULL REFERENCES players(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_mail_censor_hits_sender_created
    ON mail_censor_hits (sender_id, created_at);

COMMIT;
