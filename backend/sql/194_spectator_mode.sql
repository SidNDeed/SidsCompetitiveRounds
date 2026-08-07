-- 194: Spectator mode registry (Aug 6 item 13, phase 6).
--
-- MUST run BEFORE the code deploy: the spectate endpoints SELECT these
-- tables/columns directly (#235-236 ordering rule; the endpoints are new
-- routes, so pre-deploy there is no caller and the window is harmless).
--
-- Idempotent statement-by-statement (#243).
--
-- Design (docs/spectator-design.md §6):
--   * players.allow_spectators — per-player opt-out. DEFAULT TRUE matches
--     the intended semantics (#2): spectating is on unless a player turns
--     it off. Flagged to Sid as an explicit product default.
--   * spectate_games — one live row per attested room. room_name/room_region
--     are JOIN CREDENTIALS: they must never appear in list endpoints, logs,
--     Discord messages, or query strings (only the grant response carries
--     them, to the granted spectator alone).
--   * spectate_attestations — one row per (game, fighter). A game is
--     spectatable only while EVERY roster member holds a fresh attestation
--     whose tuple matches byte-for-byte (§6.3).
--   * spectate_leases — issued seats. token_hash only (sha256), never the
--     raw token. One ACTIVE lease per spectator account (partial unique);
--     grant revokes any expired-but-unrevoked lease first, so the partial
--     unique cannot deadlock a returning spectator.

ALTER TABLE players ADD COLUMN IF NOT EXISTS allow_spectators BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS spectate_games (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode VARCHAR(8) NOT NULL,
    source_ref VARCHAR(64) NOT NULL DEFAULT '',
    room_name VARCHAR(64) NOT NULL,
    room_region VARCHAR(16) NOT NULL DEFAULT '',
    -- Latest attested roster: sorted comma-joined steam ids. The
    -- completeness check compares each attestation against THIS string.
    roster TEXT NOT NULL DEFAULT '',
    fighter_target INTEGER NOT NULL,
    room_capacity INTEGER NOT NULL DEFAULT 0,
    spectator_cap INTEGER NOT NULL DEFAULT 4,
    protocol_min INTEGER NOT NULL DEFAULT 1,
    phase VARCHAR(16) NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_attest_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Stamped only by attests reporting phase='battle'. Grants and listing
    -- require THIS to be fresh, so a room that never reaches (or has left)
    -- live combat can be listed but never granted (Codex r1 find 15).
    last_battle_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);

-- One LIVE row per room; ended rows keep history without blocking a new
-- sitting in a reused room name.
CREATE UNIQUE INDEX IF NOT EXISTS idx_spectate_games_room_live
    ON spectate_games (room_name) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_spectate_games_live
    ON spectate_games (last_attest_at) WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS spectate_attestations (
    game_id UUID NOT NULL REFERENCES spectate_games(id) ON DELETE CASCADE,
    steam_id VARCHAR(32) NOT NULL,
    actor_number INTEGER NOT NULL DEFAULT -1,
    region VARCHAR(16) NOT NULL DEFAULT '',
    fighter_target INTEGER NOT NULL,
    room_capacity INTEGER NOT NULL DEFAULT 0,
    protocol INTEGER NOT NULL DEFAULT 1,
    roster TEXT NOT NULL DEFAULT '',
    phase VARCHAR(16) NOT NULL DEFAULT '',
    attested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (game_id, steam_id)
);

CREATE TABLE IF NOT EXISTS spectate_leases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash VARCHAR(64) NOT NULL,
    game_id UUID NOT NULL REFERENCES spectate_games(id) ON DELETE CASCADE,
    spectator_steam_id VARCHAR(32) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    join_expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_expires_at TIMESTAMPTZ NOT NULL,
    -- Photon ActorNumber this lease was first validated as. One lease = one
    -- actor: a second actor claiming the same identity fails validation and
    -- is kicked (Codex r1 find 3 — lease/actor binding).
    bound_actor INTEGER,
    revoked_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_spectate_leases_one_active
    ON spectate_leases (spectator_steam_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_spectate_leases_game
    ON spectate_leases (game_id) WHERE revoked_at IS NULL;

DO $$
BEGIN
    RAISE NOTICE 'migration 194 post-check: spectate_games=%, attestations=%, leases=%',
        (SELECT COUNT(*) FROM spectate_games),
        (SELECT COUNT(*) FROM spectate_attestations),
        (SELECT COUNT(*) FROM spectate_leases);
END $$;
