-- 143_game_code_indexes.sql — July 22 (per-game ID lookup for the Discord bot)
--
-- Expression indexes for the 12-hex short-code lookup (first 12 chars of the
-- match UUID, dashes stripped). The /matches/by-code/{code} predicate must be
-- the byte-identical expression: LEFT(REPLACE(id::text,'-',''),12).
-- Safe to apply any time (indexes only).

CREATE INDEX IF NOT EXISTS idx_matches_shortcode
    ON matches (LEFT(REPLACE(id::text, '-', ''), 12));
CREATE INDEX IF NOT EXISTS idx_team_matches_shortcode
    ON team_matches (LEFT(REPLACE(id::text, '-', ''), 12));
CREATE INDEX IF NOT EXISTS idx_ovt_matches_shortcode
    ON ovt_matches (LEFT(REPLACE(id::text, '-', ''), 12));
