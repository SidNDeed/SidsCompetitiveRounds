-- 017_anonymize_not_delete.sql
--
-- Soft-delete column so the "Delete my data" endpoint can ANONYMIZE instead of
-- destructively DELETE.
--
-- Motivation: match records are shared between two players. Fully deleting one
-- player cascades their matches, which would:
--   - rewrite the opponent's W/L history
--   - invalidate the next Glicko recalculation (the matches it iterates vanish)
--   - erase entries from rating_history used to plot Elo curves
--
-- Anonymization keeps every cross-player record intact. The player row is kept
-- with identifying columns scrubbed and deleted_at stamped; the leaderboard and
-- any player-lookup paths filter on deleted_at IS NULL so they simply disappear.

ALTER TABLE players ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- A partial index keeps the live leaderboard lookups cheap.
CREATE INDEX IF NOT EXISTS idx_players_active ON players (id) WHERE deleted_at IS NULL;
