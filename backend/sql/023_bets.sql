-- 023_bets.sql
--
-- Per-player bets on live ranked series. One bet per (player, series). Odds
-- are snapshotted at bet time from the players' Glicko ratings at that moment.
--
-- Settlement runs when the series transitions to status='completed':
--   winner bet → payout = amount * odds_multiplier  (stake returned + winnings)
--   loser bet  → payout = 0, stake forfeited
--
-- House model: pooled losses pay the winners. For now the "pool" is an
-- implicit liquidity source (server just credits the computed payout regardless
-- of what was staked against it). Revisit if unbalanced pools become a problem.

CREATE TABLE IF NOT EXISTS bets (
    id                BIGSERIAL PRIMARY KEY,
    player_id         UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    series_id         UUID NOT NULL REFERENCES ranked_series(id) ON DELETE CASCADE,
    bet_on_player_id  UUID NOT NULL REFERENCES players(id),
    amount            INTEGER NOT NULL CHECK (amount > 0),
    odds_multiplier   DOUBLE PRECISION NOT NULL CHECK (odds_multiplier >= 1.0),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at        TIMESTAMPTZ,
    payout            INTEGER,                                 -- NULL until settled
    UNIQUE (player_id, series_id)
);

CREATE INDEX IF NOT EXISTS idx_bets_series   ON bets (series_id);
CREATE INDEX IF NOT EXISTS idx_bets_pending  ON bets (settled_at) WHERE settled_at IS NULL;
