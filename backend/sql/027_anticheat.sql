-- Anti-cheat infrastructure (v1.21.0).
--
-- Adds:
--   matches.duration_seconds         — client-reported match length, used by sub-60s pattern detection
--   matches.local_bullets_fired      — local player's shot count (Harmony-instrumented Bullet awake)
--   matches.local_blocks_raised      — local player's block count
--   matches.invalidated_at           — non-NULL = match's gold/xp/glicko effects were reversed
--   matches.invalidation_reason      — short tag like 'short_duration_pattern' / 'too_many_cards' / 'admin_reverse'
--   ranked_series.invalidated_at     — series-level invalidation (cascade from a flagged constituent match)
--   ranked_series.invalidation_reason
--
--   flagged_matches table            — append-only audit log; one row per detection event. Multiple flags
--                                       can attach to one match (e.g. both >5 cards AND inactive).
--
-- Idempotent — safe to re-run.

ALTER TABLE matches ADD COLUMN IF NOT EXISTS duration_seconds INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS local_bullets_fired INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS local_blocks_raised INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS invalidated_at TIMESTAMPTZ;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS invalidation_reason TEXT;

ALTER TABLE ranked_series ADD COLUMN IF NOT EXISTS invalidated_at TIMESTAMPTZ;
ALTER TABLE ranked_series ADD COLUMN IF NOT EXISTS invalidation_reason TEXT;

CREATE TABLE IF NOT EXISTS flagged_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    series_id UUID REFERENCES ranked_series(id) ON DELETE SET NULL,
    player_steam_ids TEXT[] NOT NULL,
    flag_reason TEXT NOT NULL,           -- 'short_duration_pattern' | 'too_many_cards' | 'inactive_player'
    flag_details JSONB,                   -- per-reason context (durations, card counts, bullet/block counts)
    auto_invalidated BOOLEAN NOT NULL DEFAULT false,
    reviewed_at TIMESTAMPTZ,
    reviewed_by_steam_id TEXT,
    review_action TEXT,                   -- 'confirmed_cheat' | 'false_positive' | 'reversed'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_flagged_matches_match ON flagged_matches(match_id);
CREATE INDEX IF NOT EXISTS idx_flagged_matches_unreviewed ON flagged_matches(created_at DESC) WHERE reviewed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_flagged_matches_steam_ids ON flagged_matches USING GIN(player_steam_ids);

-- Used by the leaderboard / stats queries to ignore invalidated rows without per-call WHERE noise.
-- Add WHEN reading code calls this view; existing direct selects on matches keep counting them
-- so we can still surface them in admin views.
CREATE OR REPLACE VIEW valid_matches AS
    SELECT * FROM matches WHERE invalidated_at IS NULL;
