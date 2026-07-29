-- 163_ffa_game_code_index.sql
-- Bug #120: /matches/by-code gained an ffa_matches branch. Without this index
-- every /game lookup seq-scans a growing table (and FFA is the LAST branch, so
-- it is scanned on every miss from the other three modes too).
--
-- The expression must stay byte-identical to the WHERE clause in
-- get_match_by_code, exactly as migration 143 did for the other three tables.
-- Pure DDL, no state-mutating UPDATE -> rerun-safe by construction (#168).

CREATE INDEX IF NOT EXISTS idx_ffa_matches_shortcode
    ON ffa_matches (LEFT(REPLACE(id::text, '-', ''), 12));
