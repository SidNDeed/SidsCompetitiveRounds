-- 157: FFA betting (Sid round-2 item 6). One bet per bettor per lobby GAME;
-- odds snapshot stored at placement (immune to later rating movement);
-- settled when that game's report lands, refunded if the lobby dies first.
CREATE TABLE IF NOT EXISTS ffa_bets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lobby_id UUID NOT NULL REFERENCES ffa_lobbies(id),
    game_number INTEGER NOT NULL,
    player_id UUID NOT NULL REFERENCES players(id),
    bet_on_player_id UUID NOT NULL REFERENCES players(id),
    amount INTEGER NOT NULL CHECK (amount > 0),
    odds_multiplier NUMERIC(6,2) NOT NULL,
    payout INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at TIMESTAMPTZ,
    UNIQUE (lobby_id, game_number, player_id)
);
CREATE INDEX IF NOT EXISTS idx_ffa_bets_open ON ffa_bets (lobby_id) WHERE settled_at IS NULL;
