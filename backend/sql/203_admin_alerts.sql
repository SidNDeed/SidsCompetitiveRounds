-- 203: Standing admin alert/broadcast system (Aug 7 batch item 1).
-- Admins post server notices (outage / issue / update / info) that every
-- player sees: a persistent banner while active, plus a one-time toast per
-- alert id (seen-set in PlayerPrefs covers the "coming online" population).
--
-- SERIAL int id on purpose: the client persists seen ids as a compact
-- PlayerPrefs CSV. VARCHAR + CHECK rather than a PG enum (project norm).
-- Deploy order: apply BEFORE the API deploy (new code reads the table).

CREATE TABLE IF NOT EXISTS admin_alerts (
    id              SERIAL PRIMARY KEY,
    admin_steam_id  VARCHAR(20) NOT NULL,
    admin_name      VARCHAR(64) NOT NULL DEFAULT 'Admin',
    category        VARCHAR(16) NOT NULL CHECK (category IN ('outage','issue','update','info')),
    message         VARCHAR(500) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,          -- NULL = until revoked
    revoked_at      TIMESTAMPTZ           -- NULL = live
);

CREATE INDEX IF NOT EXISTS ix_admin_alerts_live
    ON admin_alerts (created_at DESC)
    WHERE revoked_at IS NULL;

-- Post-check.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'admin_alerts' AND column_name = 'category'
    ) THEN
        RAISE EXCEPTION 'post-check FAILED: admin_alerts missing';
    END IF;
    RAISE NOTICE 'migration 203 post-check OK: admin_alerts present';
END $$;
