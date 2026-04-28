-- v1.25.17: 2v2 disconnect tracking + sticky-team requeue grace window.
--
-- New columns:
--   team_match.dc_player_id  → who DC'd (null = clean match)
--   team_match.dc_at         → when the DC was registered
--   team_series.dc_grace_until      → 5-min sticky-team requeue deadline
--   team_series.dc_team_remaining   → 1 or 2: which team is "still here" after the DC
--   team_series.dc_player_id        → the leaver, captured for requeue identity check
--
-- DC rule for 2v2 (different from 1v1): any match abandoned with the
-- combined point total >= 2 awards the match to the non-DC team. The
-- match still flows through the regular team_match write path with
-- dc_player_id set so post-mortem analysis can filter these.
--
-- 5-min grace: when a series has dc_grace_until > NOW() and the same 4
-- players from the original lineup all re-queue, server resumes the
-- existing series (same series_id, same teams). If only one team's
-- 2 members re-queue by the deadline, that team takes the series win
-- by forfeit.

ALTER TABLE team_matches
    ADD COLUMN IF NOT EXISTS dc_player_id UUID REFERENCES players(id),
    ADD COLUMN IF NOT EXISTS dc_at        TIMESTAMPTZ;

ALTER TABLE team_series
    ADD COLUMN IF NOT EXISTS dc_grace_until    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS dc_team_remaining SMALLINT,
    ADD COLUMN IF NOT EXISTS dc_player_id      UUID REFERENCES players(id);

CREATE INDEX IF NOT EXISTS idx_team_series_dc_grace
    ON team_series(dc_grace_until)
    WHERE dc_grace_until IS NOT NULL;
