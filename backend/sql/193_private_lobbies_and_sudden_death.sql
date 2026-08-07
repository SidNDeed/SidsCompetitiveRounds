-- 193: Private lobbies for 2v2 + 1v2, passwords for all three modes
--      (Aug 6 item 9), and the FFA sudden-death config field (Aug 6 item 10).
--
-- MUST run BEFORE the code deploy: the new endpoints SELECT these columns,
-- and the FFA config reader does `SELECT * FROM ffa_lobbies` and then indexes
-- FFA_CONFIG_DEFAULTS keys, so a missing sudden_death column would be read as
-- absent on every lobby (learning #235's ordering rule — and the code half
-- degrades to the default rather than 500ing, but the column must exist for
-- the feature to do anything).
--
-- Idempotent statement-by-statement (#243).
--
-- NULLability follows the semantics exactly (#2):
--   password_hash IS NULL      -> the lobby has NO password (open to anyone)
--   sudden_death  NOT NULL     -> a gameplay rule is never "unknown"; it
--                                 defaults FALSE, which is today's behaviour,
--                                 so every existing row keeps playing exactly
--                                 as it does now.

-- ── Item 10: FFA sudden death ────────────────────────────────────────────
-- A gameplay-rule field, so it rides the FFA_CONFIG_MIN_VERSION capability
-- collapse: a lobby containing any client below the floor has its whole
-- config set (including this) reset to defaults at Start.
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS sudden_death BOOLEAN NOT NULL DEFAULT FALSE;

-- ── Item 9: passwords on all three lobby kinds ───────────────────────────
-- sha256(pepper + password), hex. NOT a credential store: the only thing it
-- protects is "can a stranger walk into my lobby", so the pepper + hash is
-- there to avoid keeping the plaintext, not to resist offline cracking.
-- VARCHAR(128) leaves room for a longer digest later without a migration.
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS password_hash VARCHAR(128) NULL;

-- ── Item 9: 2v2 + 1v2 lobby objects (mirroring ffa_lobbies) ──────────────
-- These are LOBBY rows, not series rows. A lobby is 'open' while the host is
-- gathering; at Start it becomes 'active' and a real team_series / ovt_series
-- row is created by the existing lock path. The lobby row then only carries
-- provenance (who hosted, which series it produced).
--
-- ⚠ created_at DOUBLES AS ACTIVATION TIME for every downstream consumer
-- (learning #252(b) — the FFA dispersed-close, bettable-window and dead-lock
-- sweeps all measure age from it). Start therefore RESETS created_at to NOW()
-- exactly as the FFA Start does; a lobby that sat open for an hour must not
-- be born already-expired.
CREATE TABLE IF NOT EXISTS team_lobbies (
    id                  UUID PRIMARY KEY,
    status              VARCHAR(16) NOT NULL DEFAULT 'open',  -- open|active|completed|canceled
    host_player_id      UUID REFERENCES players(id),
    -- The series this lobby produced at Start (NULL while open). This is the
    -- bridge back to the existing 2v2 machinery — everything downstream of
    -- Start keys on team_series, untouched.
    series_id           UUID REFERENCES team_series(id),
    photon_room_id      VARCHAR(64),
    region              VARCHAR(8),
    player_count        SMALLINT NOT NULL DEFAULT 0,
    member_ids          UUID[] NOT NULL DEFAULT '{}',
    password_hash       VARCHAR(128) NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    invalidated_at      TIMESTAMPTZ,
    invalidation_reason VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_team_lobbies_status
    ON team_lobbies (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_team_lobbies_open
    ON team_lobbies (created_at DESC) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS ovt_lobbies (
    id                  UUID PRIMARY KEY,
    status              VARCHAR(16) NOT NULL DEFAULT 'open',
    host_player_id      UUID REFERENCES players(id),
    series_id           UUID REFERENCES ovt_series(id),
    photon_room_id      VARCHAR(64),
    region              VARCHAR(8),
    player_count        SMALLINT NOT NULL DEFAULT 0,
    member_ids          UUID[] NOT NULL DEFAULT '{}',
    password_hash       VARCHAR(128) NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    invalidated_at      TIMESTAMPTZ,
    invalidation_reason VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_ovt_lobbies_status
    ON ovt_lobbies (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ovt_lobbies_open
    ON ovt_lobbies (created_at DESC) WHERE status = 'open';

-- The new 'lobby' status on team_queue / ovt_queue needs NO DDL: both status
-- columns are unconstrained VARCHAR(16), exactly as ffa_queue's was when the
-- FFA host-lobby redesign added the same value (migration 166).
--
-- While a member sits in an OPEN lobby, its queue row carries
--     status    = 'lobby'
--     series_id = <team_lobbies.id / ovt_lobbies.id>
-- mirroring the ffa_queue convention. The column NAME is the lock helper's
-- contract; the table it points at is decided per-STATUS in the API.

-- Membership lookups by lobby (the browser count + the live-member read run
-- on every poll of every open lobby).
CREATE INDEX IF NOT EXISTS ix_team_queue_lobby
    ON team_queue (series_id) WHERE status = 'lobby';
CREATE INDEX IF NOT EXISTS ix_ovt_queue_lobby
    ON ovt_queue (series_id) WHERE status = 'lobby';

-- Post-check: RAISE on failure so a partial apply is loud, never silent.
DO $$
DECLARE
    missing TEXT := '';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ffa_lobbies' AND column_name = 'sudden_death') THEN
        missing := missing || ' ffa_lobbies.sudden_death';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ffa_lobbies' AND column_name = 'password_hash') THEN
        missing := missing || ' ffa_lobbies.password_hash';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = 'team_lobbies') THEN
        missing := missing || ' table:team_lobbies';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = 'ovt_lobbies') THEN
        missing := missing || ' table:ovt_lobbies';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'team_lobbies' AND column_name = 'password_hash') THEN
        missing := missing || ' team_lobbies.password_hash';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ovt_lobbies' AND column_name = 'password_hash') THEN
        missing := missing || ' ovt_lobbies.password_hash';
    END IF;
    IF missing <> '' THEN
        RAISE EXCEPTION 'migration 193 post-check FAILED, missing:%', missing;
    END IF;
    RAISE NOTICE '193 private_lobbies_and_sudden_death: post-check OK';
END $$;
