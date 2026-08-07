-- 192: T-chat moderation + admin panel groundwork (Aug 6 item 5).
--
-- Adds the chat_mutes table (the enforcement store for the new
-- /chat/moderate/* endpoints) and the deleted_by audit column on
-- chat_messages. chat_messages.deleted_at already exists (migration 179) and
-- /chat/recent already filters on it — this migration only adds the "who did
-- it" half so a soft-delete is attributable.
--
-- No new status values need DDL: language_grants.scope already accepts
-- 'chat_moderate' (nothing consumed it until now).
--
-- Idempotent statement-by-statement (#243: the deploy wrapper's `||` fallback
-- re-runs the whole file whenever the first `psql -f` arm fails, which it
-- always does).
--
-- Column defaults match the server's semantics exactly (#2): created_at is
-- NOT NULL DEFAULT NOW() because a mute always has a creation instant, while
-- channel / expires_at / revoked_at are NULLABLE BY DESIGN and each NULL
-- carries meaning:
--     channel    IS NULL  ->  the mute applies to EVERY channel
--     expires_at IS NULL  ->  permanent (no automatic expiry)
--     revoked_at IS NULL  ->  still in force
-- Anything that reads them must treat NULL as those semantics, never as zero.

CREATE TABLE IF NOT EXISTS chat_mutes (
    id                BIGSERIAL PRIMARY KEY,
    steam_id          VARCHAR(32)  NOT NULL,
    -- NULL = all channels. A per-channel mute is what a scoped language
    -- moderator is allowed to issue; only an admin can issue a NULL (global)
    -- mute, because a NULL row silences the player in 'global' too.
    channel           VARCHAR(16)  NULL,
    muted_by_steam_id VARCHAR(32)  NULL,
    reason            VARCHAR(256) NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at        TIMESTAMPTZ  NULL,
    revoked_at        TIMESTAMPTZ  NULL
);

-- The enforcement lookup runs on EVERY chat send (WS + bot relay), so it gets
-- a partial index over live rows only. Partial on revoked_at (not on
-- expires_at) deliberately: expiry is a moving target that would invalidate
-- the index predicate, whereas revocation is a durable fact.
CREATE INDEX IF NOT EXISTS ix_chat_mutes_active
    ON chat_mutes (steam_id) WHERE revoked_at IS NULL;

-- Audit half of a soft-delete. deleted_at ships from 179; this records WHO.
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS deleted_by_steam_id VARCHAR(32);

-- The admin-actions log endpoint pages newest-first and filters by action /
-- target. admin_actions has carried rows since migration 028 with no index
-- beyond its PK, so the first paged read would seq-scan the whole table.
CREATE INDEX IF NOT EXISTS ix_admin_actions_created
    ON admin_actions (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_admin_actions_target
    ON admin_actions (target_steam_id, created_at DESC)
    WHERE target_steam_id IS NOT NULL;

-- Drop the FK admin_actions.admin_steam_id -> admin_users.steam_id.
--
-- REQUIRED by item 5, and correct on its own merits:
--   1. Scoped chat moderators (language_grants scope='chat_moderate') are
--      deliberately NOT in admin_users, but their chat_delete / chat_mute /
--      chat_unmute actions must be auditable in the same log. With the FK in
--      place every one of those inserts violates it — and because the insert
--      runs inside a SAVEPOINT so an audit failure cannot take down the
--      moderation action itself, the row would be dropped SILENTLY. A log
--      that quietly discards exactly the actors it was extended to cover is
--      worse than no log.
--   2. An audit log must not be constrained by the CURRENT roster. With the
--      FK, removing a retired admin from admin_users is blocked by their own
--      history (or would have to cascade it away — destroying the audit
--      trail). History is a record of what happened, not of who is currently
--      privileged.
-- Dropped BY DISCOVERED NAME rather than by the assumed default
-- (`admin_actions_admin_steam_id_fkey`) so a differently-named constraint on
-- some environment is still removed. Idempotent: a second run finds nothing.
DO $$
DECLARE
    c RECORD;
BEGIN
    FOR c IN
        SELECT con.conname
          FROM pg_constraint con
          JOIN pg_class      rel  ON rel.oid = con.conrelid
          JOIN pg_class      frel ON frel.oid = con.confrelid
         WHERE con.contype = 'f'
           AND rel.relname  = 'admin_actions'
           AND frel.relname = 'admin_users'
    LOOP
        EXECUTE format('ALTER TABLE admin_actions DROP CONSTRAINT %I', c.conname);
        RAISE NOTICE '192: dropped FK admin_actions.%', c.conname;
    END LOOP;
END $$;

-- Post-check: RAISE (not NOTICE) on failure so a partial apply is loud.
DO $$
DECLARE
    missing TEXT := '';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = 'chat_mutes') THEN
        missing := missing || ' table:chat_mutes';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'chat_messages'
                     AND column_name = 'deleted_by_steam_id') THEN
        missing := missing || ' chat_messages.deleted_by_steam_id';
    END IF;
    -- deleted_at is a PRECONDITION, not something this migration adds: the
    -- delete endpoint writes both columns together, so a database missing it
    -- would fail at runtime rather than here. Check it explicitly.
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'chat_messages'
                     AND column_name = 'deleted_at') THEN
        missing := missing || ' chat_messages.deleted_at(from-179)';
    END IF;
    -- The FK must be GONE, or every scoped-moderator audit row silently
    -- vanishes into its savepoint (see the drop block above).
    IF EXISTS (SELECT 1 FROM pg_constraint con
                 JOIN pg_class rel  ON rel.oid  = con.conrelid
                 JOIN pg_class frel ON frel.oid = con.confrelid
                WHERE con.contype = 'f' AND rel.relname = 'admin_actions'
                  AND frel.relname = 'admin_users') THEN
        missing := missing || ' admin_actions->admin_users FK still present';
    END IF;
    IF missing <> '' THEN
        RAISE EXCEPTION 'migration 192 post-check FAILED, missing:%', missing;
    END IF;
    RAISE NOTICE '192 chat_moderation: post-check OK';
END $$;
