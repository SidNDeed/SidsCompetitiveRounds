-- v1.25.21: 2v2 economy.
--
-- Per-match XP awards mirror the 1v1 path (calculate_xp_earned) but with a
-- higher base so 2v2 wins land in the user's target band of ~800-900 XP and
-- losses land near ~600 XP. Per-series gold: +50g winner, +25g loser. The
-- existing 100xp=1g conversion still applies on top so a high-XP match also
-- yields a few gold beyond the series bonus.
--
-- New columns track the 2v2-source slice of each player's gold / XP so the
-- 2v2 leaderboard can surface "Total 2v2 Gold" + "Total 2v2 XP" without
-- having to sum gold_transactions every render.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS team_gold_earned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS team_xp_earned   INTEGER NOT NULL DEFAULT 0;

-- Per-series economy snapshot. Drives the F5 Recent 2v2 Series UI showing
-- "+50g, +900xp" beside each player's row in their own series. Filled at
-- series-complete time so we don't have to sum gold_transactions live.
ALTER TABLE team_series
    ADD COLUMN IF NOT EXISTS t1a_gold_earned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS t1b_gold_earned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS t2a_gold_earned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS t2b_gold_earned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS t1a_xp_earned   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS t1b_xp_earned   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS t2a_xp_earned   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS t2b_xp_earned   INTEGER NOT NULL DEFAULT 0;
