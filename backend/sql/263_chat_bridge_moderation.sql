-- 263: cross-platform chat moderation (design: ai-collab/chat-moderation-design.md v3,
-- Codex design round D1 dispositions F1-F18).
--
-- Adds: origin identity + author verification on chat_messages; platform-identity
-- mutes (bridge_mutes); normalized spam patterns (bridge_spam_patterns); the
-- one-to-many external-copy map (chat_mirrors); the durable moderation-action
-- outbox (chat_mod_actions). Explicit BEGIN/COMMIT — psql -f autocommits per
-- statement otherwise (#340), and the deploy wrapper's || retry re-runs the whole
-- file, so every statement here is idempotent.

BEGIN;

-- D1 F1: an in-game row's steam_id is CLIENT-CLAIMED on the WS path. It may only
-- ever become a MUTE target when the socket that sent it was session-verified as
-- that id — recorded here at persist time. Deletes stay allowed either way (they
-- target the row, not the identity).
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS author_verified BOOLEAN NOT NULL DEFAULT FALSE;
-- Stable platform identity of bridged rows (Twitch user-id tag / YouTube channel
-- id, plus the Twitch login from the IRC prefix). NULL on every pre-263 row —
-- and the identity-matching rule (D1 F4) says a NULL stable id is matched by
-- nothing except explicit legacy login fallbacks.
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS origin_user_id VARCHAR(64);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS origin_login VARCHAR(64);

-- Platform-identity mutes: twitch/youtube/discord chatters have no steam_id, so
-- chat_mutes cannot hold them. Same lifecycle shape as chat_mutes (supersede-
-- then-insert, revoked_at = audit trail, expires_at NULL = permanent).
CREATE TABLE IF NOT EXISTS bridge_mutes (
    id               BIGSERIAL PRIMARY KEY,
    platform         VARCHAR(16) NOT NULL CHECK (platform IN ('twitch','youtube','discord')),
    -- Stable id (Twitch user-id / YouTube channel id / Discord user id).
    platform_user_id VARCHAR(64) NULL,
    -- Lowercase login. D1 F4 identity rule: a row with a NON-NULL user id is
    -- matched ONLY by that id; login comparison applies ONLY to rows whose
    -- stored user id IS NULL (hand-seeded name mutes) — a login is a mutable
    -- alias and must never override a stable id.
    platform_login   VARCHAR(64) NULL,
    -- NULL = every channel, ADMIN-ONLY to issue (mirrors chat_mutes; D1 F5 —
    -- a language moderator's mute is scoped to the row's channel).
    channel          VARCHAR(16) NULL,
    display_name     VARCHAR(64) NULL,
    -- Free-form actor label: a steam_id, 'discord:<id>', 'twitch_mod',
    -- 'youtube_mod', 'system'. Not an FK on purpose (actors span platforms).
    muted_by         VARCHAR(64) NOT NULL,
    reason           VARCHAR(256) NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ NULL,
    revoked_at       TIMESTAMPTZ NULL,
    CHECK (platform_user_id IS NOT NULL OR platform_login IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_bridge_mutes_active
    ON bridge_mutes (platform) WHERE revoked_at IS NULL;

-- Content-pattern drop list for BRIDGED sources only (the observed Twitch ad
-- spam is one-shot throwaway accounts — identity mutes cannot stop it, D1 §1).
-- `pattern` is stored ALREADY NORMALIZED (lowercase → confusable-fold → strip
-- non-alphanumerics); the length CHECK is load-bearing (D1 F16): an empty or
-- near-empty squash would substring-match every message.
CREATE TABLE IF NOT EXISTS bridge_spam_patterns (
    id         BIGSERIAL PRIMARY KEY,
    pattern    VARCHAR(128) NOT NULL CHECK (char_length(pattern) >= 4),
    note       VARCHAR(256) NULL,
    added_by   VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_bridge_spam_patterns_active
    ON bridge_spam_patterns (pattern) WHERE revoked_at IS NULL;

-- One row per EXTERNAL COPY of a chat message (D1 F2: one-to-many — an
-- ambiguous Discord send timeout legitimately produces two copies, and deletion
-- must fan out to every copy). The ORIGIN of a bridged/discord message is
-- registered as its own platform's row too (that is how a Twitch CLEARMSG's
-- target-msg-id resolves back to the chat row). mirror ids are globally unique
-- per platform (Discord snowflakes, Twitch/YouTube message uuids), so
-- (platform, mirror_id) is the natural identity; registration is idempotent
-- via ON CONFLICT DO NOTHING. Deliberately NO foreign key to chat_messages:
-- the delete fan-out holds FOR UPDATE on the chat row, and an FK's KEY SHARE
-- from concurrent mirror INSERTs would join that lock graph (#202) — the
-- registration endpoint takes the same FOR UPDATE instead, which serializes
-- the deleted_at check it needs anyway.
CREATE TABLE IF NOT EXISTS chat_mirrors (
    id          BIGSERIAL PRIMARY KEY,
    chat_id     BIGINT NOT NULL,
    platform    VARCHAR(16) NOT NULL CHECK (platform IN ('twitch','youtube','discord')),
    mirror_id   VARCHAR(128) NOT NULL,
    -- Discord: channel id (needed to delete). Twitch: broadcaster id (optional).
    channel_ref VARCHAR(32) NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (platform, mirror_id)
);
CREATE INDEX IF NOT EXISTS ix_chat_mirrors_chat ON chat_mirrors (chat_id);

-- Durable moderation-action outbox, consumed by the Discord bot's poll
-- (at-least-once + per-kind idempotency; `twitch_say` alone is acked before
-- send = at-most-once, D1 F13). The unacked feed carries NO age predicate
-- (D1 F8 — a bot outage must never orphan moderation); acked rows are pruned
-- after 7 days by the ack endpoint's time-gated sweep.
CREATE TABLE IF NOT EXISTS chat_mod_actions (
    id            BIGSERIAL PRIMARY KEY,
    kind          VARCHAR(32) NOT NULL,
    payload       TEXT NOT NULL,           -- JSON, kind-specific
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acked_at      TIMESTAMPTZ NULL,
    undeliverable BOOLEAN NOT NULL DEFAULT FALSE,
    attempts      INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_chat_mod_actions_unacked
    ON chat_mod_actions (id) WHERE acked_at IS NULL;

-- Seed the observed ad-spam shapes (prod chat_messages sample, 2026-08-29:
-- "Ai viewers twitchmax .com" / "streamboo . Com" / "twitchstar .com" /
-- "Best promotion on streamboo. org" from one-shot accounts). Values are the
-- NORMALIZED form. Guarded per-row so the || re-run stays a no-op (#243).
INSERT INTO bridge_spam_patterns (pattern, note, added_by)
SELECT v.p, v.n, 'migration_263'
  FROM (VALUES
        ('aiviewers',     'observed Twitch ad-bot phrasing, Aug 2026'),
        ('streamboo',     'observed ad-bot domain'),
        ('twitchmax',     'observed ad-bot domain'),
        ('twitchstar',    'observed ad-bot domain'),
        ('bestpromotion', 'observed ad-bot phrasing')
       ) AS v(p, n)
 WHERE NOT EXISTS (SELECT 1 FROM bridge_spam_patterns bp
                    WHERE bp.pattern = v.p AND bp.revoked_at IS NULL);

COMMIT;
