-- 181: L10n server infrastructure (localization-design §2.3/§2.5).
--
-- Key registry + live catalogue + append-only proposals + grants + audit.
-- Live states are 'machine' and 'approved' ONLY; proposals are the history.
-- Staleness (approved_source_hash != current source_hash) is DERIVED at read
-- time, never stored (#205/#208 — a stored staleness bit aliases).
--
-- Additive-safe: CREATE TABLE IF NOT EXISTS only. Apply before deploying the
-- v1.36 API (the i18n endpoints read these tables).

-- Key registry, synced from tools/i18n_extract.py output via the admin sync
-- endpoint at release time. msgctxt is the ENGLISH SOURCE STRING — it is the
-- runtime catalogue key on the client (whole-string chokepoint), so the
-- portal shows it verbatim.
--
-- KEY-MODEL DECISION (wave-2 review blocker 1, settled deliberately): the
-- design doc's §2.3 sketch wanted key_id stable across English edits, but
-- the IMPLEMENTED runtime is whole-string keyed (design §2.3's own note:
-- "the DLL embeds a flat source→target table ... which is what a
-- whole-string chokepoint can actually consume"). Under that runtime an
-- English edit ALWAYS orphans the translation at lookup time regardless of
-- any server-side identity — the client looks up by the NEW string. So
-- key_id = sha1(namespace||\0||source) is the honest identity: an edited
-- string mints a new key (retiring, never deleting, the old one — its
-- proposals/history survive for reference), and `approved_source_hash !=
-- source_hash` staleness covers server-side source updates on a STABLE key
-- (metadata edits via sync that keep the string identical are the no-op
-- case). This is NOT the design's rejected "fuzzy re-linking" — nothing is
-- ever silently re-linked; an edit visibly produces an untranslated key.
CREATE TABLE IF NOT EXISTS i18n_keys (
    key_id       VARCHAR(16) PRIMARY KEY,       -- sha1(namespace||\0||msgctxt)[:16]
    namespace    VARCHAR(32) NOT NULL,
    msgctxt      TEXT        NOT NULL,          -- English source
    source_hash  VARCHAR(40) NOT NULL,          -- sha1(source_text)
    sensitive    BOOLEAN     NOT NULL DEFAULT FALSE,  -- §2.5: admin-only approval
    max_px       INTEGER,                       -- optional per-key width budget
    retired_at   TIMESTAMPTZ,                   -- key no longer in the extraction
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Live catalogue entries (the pack the client fetches).
CREATE TABLE IF NOT EXISTS i18n_entries (
    key_id               VARCHAR(16) NOT NULL REFERENCES i18n_keys(key_id) ON DELETE CASCADE,
    language_code        VARCHAR(8)  NOT NULL,
    target               TEXT        NOT NULL,
    state                VARCHAR(10) NOT NULL DEFAULT 'machine',  -- machine | approved
    approved_source_hash VARCHAR(40),           -- source hash the approval saw
    approved_by_steam_id VARCHAR(20),
    self_approved        BOOLEAN     NOT NULL DEFAULT FALSE,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (key_id, language_code)
);

-- Append-only proposal history. status: pending | approved | rejected |
-- superseded (a newer proposal for the same key+lang was decided instead).
CREATE TABLE IF NOT EXISTS i18n_proposals (
    id                 BIGSERIAL PRIMARY KEY,
    key_id             VARCHAR(16) NOT NULL REFERENCES i18n_keys(key_id) ON DELETE CASCADE,
    language_code      VARCHAR(8)  NOT NULL,
    source_hash        VARCHAR(40) NOT NULL,    -- source as the proposer saw it
    proposed_target    TEXT        NOT NULL,
    proposer_steam_id  VARCHAR(20) NOT NULL,
    -- D15 contribution licence (wave-2 find 5): every proposal records the
    -- contributor's explicit assent + the terms revision they saw. The API
    -- rejects submissions without assent; approval therefore always has a
    -- recorded redistribution grant behind it.
    license_assent     BOOLEAN     NOT NULL DEFAULT FALSE,
    license_terms_rev  VARCHAR(16),
    assented_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status             VARCHAR(12) NOT NULL DEFAULT 'pending',
    reviewed_by_steam_id VARCHAR(20),
    reviewed_at        TIMESTAMPTZ,
    review_note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_i18n_proposals_queue
    ON i18n_proposals (language_code, status, created_at);

-- Translate / chat-moderate grants (§2.5). Two independent scopes; a revoked
-- grant keeps its row (revoked_at set) for the audit trail.
CREATE TABLE IF NOT EXISTS language_grants (
    id                  BIGSERIAL PRIMARY KEY,
    steam_id            VARCHAR(20) NOT NULL,
    language_code       VARCHAR(8)  NOT NULL,
    scope               VARCHAR(16) NOT NULL,   -- 'translate' | 'chat_moderate'
    granted_by_steam_id VARCHAR(20) NOT NULL,
    granted_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at          TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_language_grants_lookup
    ON language_grants (steam_id, language_code, scope)
    WHERE revoked_at IS NULL;

-- Moderator-capable audit (§2.5: admin_actions.admin_steam_id is FK
-- admin_users NOT NULL, so it structurally cannot record a moderator —
-- separate table, modeled on bug_report_events).
CREATE TABLE IF NOT EXISTS i18n_review_events (
    id             BIGSERIAL PRIMARY KEY,
    actor_steam_id VARCHAR(20) NOT NULL,
    actor_role     VARCHAR(12) NOT NULL,        -- 'admin' | 'moderator'
    language_code  VARCHAR(8)  NOT NULL,
    key_id         VARCHAR(16),
    action         VARCHAR(24) NOT NULL,        -- propose|approve|reject|revert|grant|revoke|sync_keys
    detail         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_i18n_review_events_lang
    ON i18n_review_events (language_code, created_at);

-- Short-TTL portal sessions (§2.5 portal security): token handed to the
-- in-game client over HTTPS only, bound to the requesting IP, sent back as a
-- non-cookie bearer header (X-Portal-Token) — no cookies anywhere in the
-- portal, so there is no ambient credential for same-origin fetch to ride.
CREATE TABLE IF NOT EXISTS i18n_portal_sessions (
    token       VARCHAR(64) PRIMARY KEY,
    steam_id    VARCHAR(20) NOT NULL,
    bound_ip    VARCHAR(64) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_i18n_portal_sessions_expiry
    ON i18n_portal_sessions (expires_at);

DO $$ BEGIN RAISE NOTICE 'migration 181 OK: i18n infrastructure created'; END $$;
