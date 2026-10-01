-- 367_api_operator_keys.sql -- verified reads (board row 33, item b).
--
-- Registered operator keys: the third read credential beside a player's
-- Steam-verified session and the bot's internal key. One operator holds at
-- most two LIVE keys (slots 1 and 2) so a key can be rotated without a gap:
-- issue the second, the operator deploys it, the census shows the old one
-- at zero, revoke the old one.
--
-- A key is shown once at issue and stored only as its sha256 (the storage
-- rule steam_sessions follows). key_hint is the first characters after the
-- prefix, for listing; it never identifies the key on its own.
--
-- operator_name is a canonical lowercase ASCII slug, enforced here so the
-- live-slot index below holds per LOGICAL operator: "scrmod" and "SCRMOD"
-- cannot both be stored, so neither can hold two live keys of its own. The
-- api canonicalises the name (strip, lowercase, slug check) before its
-- advisory lock, its insert, the admin signature's target and every lookup.
--
-- An ordinary logged table, so streaming replication carries it to the
-- standby exactly as it carries steam_sessions.
--
-- Idempotent: every statement is IF NOT EXISTS or guarded, so a second apply
-- changes nothing.

BEGIN;

CREATE TABLE IF NOT EXISTS api_operator_keys (
    id            BIGSERIAL    PRIMARY KEY,
    operator_name VARCHAR(64)  NOT NULL,
    contact       VARCHAR(200) NOT NULL,
    slot          SMALLINT     NOT NULL,
    key_hash      CHAR(64)     NOT NULL,
    key_hint      VARCHAR(16)  NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    created_by    VARCHAR(20)  NOT NULL,
    revoked_at    TIMESTAMPTZ  NULL,
    revoked_by    VARCHAR(20)  NULL,
    CONSTRAINT api_operator_keys_slot_check CHECK (slot IN (1, 2)),
    CONSTRAINT api_operator_keys_name_slug CHECK (operator_name ~ '^[a-z0-9][a-z0-9-]{1,31}$'),
    CONSTRAINT api_operator_keys_key_hash_key UNIQUE (key_hash)
);

-- At most two LIVE keys per operator, as a database guarantee rather than a
-- handler check: a racing third insert is refused here even if two issue
-- requests passed the handler's slot pick at once.
CREATE UNIQUE INDEX IF NOT EXISTS ux_api_operator_keys_live_slot
    ON api_operator_keys (operator_name, slot) WHERE revoked_at IS NULL;

COMMIT;
