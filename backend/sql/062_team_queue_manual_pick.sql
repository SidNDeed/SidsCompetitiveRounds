-- v1.25.17: manual team picking in 2v2 queue.
--
-- UX flow:
--   - Each queuer can toggle a "Allow team picking" checkbox (manual_pick_enabled).
--   - When 3+ queuers have manual_pick_enabled = true, all 4 can claim a side
--     via "Team 1" / "Team 2" buttons (preferred_team).
--   - Matchmaker: if quorum >= 3, respect preferred_team assignments. Else
--     auto-balance by elo (existing behavior).
--   - team_series.was_auto_balanced records which path was used so the
--     post-series auto-balance reshuffle (item #12) only fires for
--     auto-balanced series, not manually-picked ones.

ALTER TABLE team_queue
    ADD COLUMN IF NOT EXISTS manual_pick_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS preferred_team SMALLINT;

ALTER TABLE team_series
    ADD COLUMN IF NOT EXISTS was_auto_balanced BOOLEAN NOT NULL DEFAULT TRUE;
