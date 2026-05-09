-- 075_player_mod_version.sql
-- Track the most recently observed mod version per player so the
-- leaderboard player-detail view can show "running v1.26.5" / "running
-- v1.26.3" — makes it obvious whether a tester is on a build that has
-- a given fix or not. Stamped by _mark_mod_seen on every mod-only
-- request, sourced from the X-Mod-Version request header that the
-- version-gate middleware already inspects.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS mod_version VARCHAR(16);

CREATE INDEX IF NOT EXISTS idx_players_mod_version
    ON players (mod_version)
    WHERE mod_version IS NOT NULL;
