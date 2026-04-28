-- v1.25.17: 2v2 betting on team_series.
--
-- The existing `bets` table is tightly coupled to `ranked_series` (NOT NULL FK
-- on series_id, NOT NULL bet_on_player_id). Rather than weakening those
-- constraints we add a parallel `team_bets` table that stores the same
-- shape but bets on a TEAM (1 or 2) of a `team_series`.
--
-- Settlement: when team_series.status flips to 'completed', any unsettled
-- team_bets rows for that series are paid out (winning team) or marked
-- settled with payout=0 (losing team). Mirrors the 1v1 bet settlement.

CREATE TABLE IF NOT EXISTS team_bets (
    id              BIGSERIAL PRIMARY KEY,
    player_id       UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_series_id  UUID NOT NULL REFERENCES team_series(id) ON DELETE CASCADE,
    bet_on_team     SMALLINT NOT NULL CHECK (bet_on_team IN (1, 2)),
    amount          INTEGER NOT NULL CHECK (amount > 0),
    odds_multiplier DOUBLE PRECISION NOT NULL CHECK (odds_multiplier >= 1.0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at      TIMESTAMPTZ,
    payout          INTEGER,
    UNIQUE(player_id, team_series_id)
);

CREATE INDEX IF NOT EXISTS idx_team_bets_pending
    ON team_bets(settled_at)
    WHERE settled_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_team_bets_series
    ON team_bets(team_series_id);
