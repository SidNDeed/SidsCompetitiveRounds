-- 137_steam_sessions.sql — July 21 (Steam ticket auth)
--
-- Opaque session tokens issued by POST /api/v1/auth/steam after Steam
-- Web-API ticket verification. DB-backed (not in-memory) so sessions survive
-- `docker compose up -d --build` redeploys — an in-memory store would
-- 401-storm every client after each deploy once enforcement is on. Only
-- sha256(token) is stored, never the raw token. Expired rows are pruned
-- opportunistically by the auth endpoint (expires_at index below).

CREATE TABLE IF NOT EXISTS steam_sessions (
    id BIGSERIAL PRIMARY KEY,
    steam_id VARCHAR(20) NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    verified BOOLEAN NOT NULL DEFAULT false,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_steam_sessions_token ON steam_sessions (token_hash);
CREATE INDEX IF NOT EXISTS ix_steam_sessions_expiry ON steam_sessions (expires_at);
-- Per-account arming lookup in _check_steam_session (any recent verified
-- session for a claimed steam_id → enforce regardless of claimed version).
CREATE INDEX IF NOT EXISTS ix_steam_sessions_steam_id ON steam_sessions (steam_id);
