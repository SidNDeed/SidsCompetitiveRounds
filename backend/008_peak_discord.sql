-- ============================================================
-- Competitive ROUNDS — Peak Rating + Discord Linking Migration
-- ============================================================
-- Run manually:
--   docker compose exec db psql -U comp_rounds -d competitive_rounds -f /docker-entrypoint-initdb.d/008_peak_discord.sql
-- ============================================================

-- Peak rating tracking on glicko_ratings
ALTER TABLE glicko_ratings ADD COLUMN IF NOT EXISTS peak_rating DOUBLE PRECISION;

-- Backfill peak_rating from current rating for existing players
UPDATE glicko_ratings SET peak_rating = rating WHERE peak_rating IS NULL;

-- Discord account linking
ALTER TABLE players ADD COLUMN IF NOT EXISTS discord_id VARCHAR(20) UNIQUE;
CREATE INDEX IF NOT EXISTS idx_players_discord ON players (discord_id) WHERE discord_id IS NOT NULL;

-- Verification codes for Steam-Discord linking (10 min expiry)
CREATE TABLE IF NOT EXISTS link_codes (
    player_id   UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    code        VARCHAR(6) NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_link_codes_code ON link_codes (code);
