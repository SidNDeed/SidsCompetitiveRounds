-- 238_tournament_checkins.sql
-- Durable async-tournament deadline responses and one-per-opponent deadline
-- extensions. Every replay-key column is NOT NULL so each UNIQUE constraint
-- remains an effective idempotency guard.
-- The legacy self_forfeit CHECK value remains permitted but is no longer written; retaining it avoids migration churn.
--
-- The migration wrapper may execute the whole file again after a fallback,
-- so every statement is independently safe to repeat. psql -f does not wrap
-- files in a transaction; keep the explicit boundary.

BEGIN;

CREATE TABLE IF NOT EXISTS tournament_match_checkins (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id    UUID NOT NULL REFERENCES tournament_matches(id) ON DELETE CASCADE,
    player_id   UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    answer      VARCHAR(32) NOT NULL,
    answered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tournament_match_checkins_match_player
        UNIQUE (match_id, player_id),
    CONSTRAINT ck_tournament_match_checkins_answer
        CHECK (answer IN (
            'yes_playing',
            'contacted_no_response',
            'not_yet',
            'self_forfeit'
        ))
);

CREATE TABLE IF NOT EXISTS tournament_deadline_extensions (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id      UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    player_id          UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    opponent_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    extended_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tournament_deadline_extensions_pair
        UNIQUE (tournament_id, player_id, opponent_player_id),
    CONSTRAINT ck_tournament_deadline_extensions_distinct_players
        CHECK (player_id <> opponent_player_id)
);

COMMIT;
