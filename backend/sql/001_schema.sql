-- ============================================================
-- Competitive ROUNDS — Database Schema
-- ============================================================
-- This file runs automatically on first PostgreSQL startup.
-- To re-run manually:
--   docker compose exec db psql -U comp_rounds -d competitive_rounds -f /docker-entrypoint-initdb.d/001_schema.sql
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Players ───────────────────────────────────────────────────
-- One row per unique Steam account that has the mod installed.
-- Auto-created on first match report.
CREATE TABLE players (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    steam_id        VARCHAR(20) NOT NULL UNIQUE,   -- Steam64 ID string
    display_name    VARCHAR(64) NOT NULL,
    ranked_enabled  BOOLEAN NOT NULL DEFAULT true,  -- player's ranked toggle state
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_players_steam ON players (steam_id);

-- ── Glicko-2 Ratings ─────────────────────────────────────────
-- Current rating state per player. One row per player.
-- Updated at the end of each rating period.
CREATE TABLE glicko_ratings (
    player_id       UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    rating          DOUBLE PRECISION NOT NULL DEFAULT 1500.0,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350.0,  -- RD
    volatility      DOUBLE PRECISION NOT NULL DEFAULT 0.06,
    games_in_period INTEGER NOT NULL DEFAULT 0,     -- matches since last calc
    last_calculated TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Rating History ────────────────────────────────────────────
-- Snapshot after each rating period recalculation.
-- Powers rating-over-time graphs in the leaderboard UI.
CREATE TABLE rating_history (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    player_id       UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    rating          DOUBLE PRECISION NOT NULL,
    rating_deviation DOUBLE PRECISION NOT NULL,
    volatility      DOUBLE PRECISION NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rating_history_player ON rating_history (player_id, period_end DESC);

-- ── Matches ───────────────────────────────────────────────────
-- One row per completed ranked match between two mod users.
CREATE TABLE matches (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Players (player 1 = host/reporter, player 2 = opponent)
    player1_id      UUID NOT NULL REFERENCES players(id),
    player2_id      UUID NOT NULL REFERENCES players(id),

    -- Final score
    p1_rounds_won   SMALLINT NOT NULL,  -- rounds won by player 1
    p2_rounds_won   SMALLINT NOT NULL,  -- rounds won by player 2
    p1_points_total SMALLINT NOT NULL DEFAULT 0,  -- total points scored across all rounds
    p2_points_total SMALLINT NOT NULL DEFAULT 0,

    -- Who won (redundant but fast for queries)
    winner_id       UUID REFERENCES players(id),  -- NULL = draw (shouldn't happen in ROUNDS)

    -- Match metadata
    match_duration  INTEGER,            -- seconds, if we can track it
    photon_room_id  VARCHAR(64),        -- Photon room name for deduplication
    game_version    VARCHAR(32),        -- e.g. "v1.1.2.a75ee335a"
    region          VARCHAR(8),         -- Photon region code

    -- Integrity
    hmac_signature  VARCHAR(128),       -- HMAC-SHA256 of match payload (Phase 4)
    reported_by     UUID REFERENCES players(id),  -- which player's mod sent this

    -- Timestamps
    started_at      TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Prevent duplicate reports of the same match
    CONSTRAINT unique_match UNIQUE (photon_room_id, player1_id, player2_id)
);

CREATE INDEX idx_matches_player1 ON matches (player1_id, ended_at DESC);
CREATE INDEX idx_matches_player2 ON matches (player2_id, ended_at DESC);
CREATE INDEX idx_matches_ended ON matches (ended_at DESC);

-- ── Match Cards ───────────────────────────────────────────────
-- Every card picked by every player in every match.
-- One row per card pick event.
CREATE TABLE match_cards (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    match_id        UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id       UUID NOT NULL REFERENCES players(id),
    card_name       VARCHAR(64) NOT NULL,  -- exact CardInfo.cardName
    card_rarity     VARCHAR(16),           -- Common, Uncommon, Rare, etc.
    pick_order      SMALLINT NOT NULL,      -- 1st pick, 2nd pick, etc.
    round_number    SMALLINT NOT NULL       -- which round the pick happened in
);

CREATE INDEX idx_match_cards_match ON match_cards (match_id);
CREATE INDEX idx_match_cards_player ON match_cards (player_id);
CREATE INDEX idx_match_cards_card ON match_cards (card_name);

-- ── Card Stats (Materialized View) ───────────────────────────
-- Aggregated win/loss/pick rates per card. Refreshed periodically.
-- Much faster than computing on every leaderboard request.
CREATE MATERIALIZED VIEW card_stats AS
SELECT
    mc.card_name,
    mc.card_rarity,
    COUNT(*)                                          AS times_picked,
    COUNT(DISTINCT mc.match_id)                       AS matches_appeared,
    COUNT(DISTINCT mc.player_id)                      AS unique_players,
    SUM(CASE WHEN m.winner_id = mc.player_id THEN 1 ELSE 0 END) AS wins_with_card,
    ROUND(
        SUM(CASE WHEN m.winner_id = mc.player_id THEN 1 ELSE 0 END)::NUMERIC
        / NULLIF(COUNT(*), 0), 4
    )                                                 AS win_rate
FROM match_cards mc
JOIN matches m ON m.id = mc.match_id
GROUP BY mc.card_name, mc.card_rarity;

-- Unique index required for REFRESH CONCURRENTLY
CREATE UNIQUE INDEX idx_card_stats_name ON card_stats (card_name);

-- ── Player Stats (View) ──────────────────────────────────────
-- Live W/L stats per player. This is a regular view (always fresh).
CREATE VIEW player_stats AS
SELECT
    p.id AS player_id,
    p.steam_id,
    p.display_name,
    gr.rating,
    gr.rating_deviation,
    COUNT(m.id)                                       AS total_matches,
    SUM(CASE WHEN m.winner_id = p.id THEN 1 ELSE 0 END)  AS wins,
    SUM(CASE WHEN m.winner_id IS NOT NULL
              AND m.winner_id != p.id THEN 1 ELSE 0 END)  AS losses,
    ROUND(
        SUM(CASE WHEN m.winner_id = p.id THEN 1 ELSE 0 END)::NUMERIC
        / NULLIF(COUNT(m.id), 0), 4
    )                                                 AS win_rate,
    MAX(m.ended_at)                                   AS last_match
FROM players p
LEFT JOIN glicko_ratings gr ON gr.player_id = p.id
LEFT JOIN matches m ON m.player1_id = p.id OR m.player2_id = p.id
GROUP BY p.id, p.steam_id, p.display_name, gr.rating, gr.rating_deviation;

-- ── Leaderboard (View) ───────────────────────────────────────
-- Top players ranked by Glicko-2 rating, filtered to active players
-- with enough games for a reliable rating.
CREATE VIEW leaderboard AS
SELECT
    ROW_NUMBER() OVER (ORDER BY gr.rating DESC) AS rank,
    p.display_name,
    p.steam_id,
    ROUND(gr.rating::NUMERIC, 0)        AS rating,
    ROUND(gr.rating_deviation::NUMERIC, 0) AS rd,
    ps.total_matches,
    ps.wins,
    ps.losses,
    ps.win_rate,
    ps.last_match
FROM glicko_ratings gr
JOIN players p ON p.id = gr.player_id
JOIN player_stats ps ON ps.player_id = p.id
WHERE ps.total_matches >= 5             -- minimum games to appear on leaderboard
  AND gr.rating_deviation < 200          -- rating must be reasonably settled
ORDER BY gr.rating DESC;

-- ── Refresh function for card stats ──────────────────────────
-- Call this periodically (e.g. every hour via pg_cron or the API)
-- CONCURRENTLY allows reads during refresh.
-- Note: requires at least one row in the materialized view to use CONCURRENTLY.

-- ── Helpful comments ─────────────────────────────────────────
COMMENT ON TABLE players IS 'Registered competitive ROUNDS players, keyed by Steam ID';
COMMENT ON TABLE matches IS 'Completed ranked match results reported by the BepInEx mod';
COMMENT ON TABLE match_cards IS 'Individual card picks per player per match';
COMMENT ON TABLE glicko_ratings IS 'Current Glicko-2 rating state per player';
COMMENT ON TABLE rating_history IS 'Historical snapshots for rating-over-time graphs';
COMMENT ON MATERIALIZED VIEW card_stats IS 'Aggregated card win/pick rates — refresh with: REFRESH MATERIALIZED VIEW CONCURRENTLY card_stats;';
