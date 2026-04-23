-- ============================================================
-- Competitive ROUNDS — Tournaments (Phase 1: sync single-elim BO3)
-- ============================================================
-- Adds: tournaments, tournament_signups, tournament_matches,
--       tournament_time_votes, tournament_force_votes,
--       player_tournament_penalty
-- Extends ranked_series with (tournament_id, is_tournament) so tournament
-- BO3s reuse the existing match-report pipeline. Glicko still applies —
-- tournament wins/losses move ladder Elo the same as regular ranked series.
-- Classification: additive-safe.
-- ============================================================

-- Tournament root row. One per scheduled event.
-- kind: 'sync' = all-at-once single-elim BO3. 'async' = Phase 2 (double-elim, 7d match deadlines).
-- status:
--   voting    — voting + signups open
--   locked    — bracket seeded, waiting for scheduled_start_ts
--   running   — first match has started
--   completed — winner decided, prizes paid
--   cancelled — <8 signups at lock time
-- prize_tier: 'full' (16+) | 'sixty' (12-15) | 'thirty' (8-11) | 'none' (<8, cancelled)
CREATE TABLE IF NOT EXISTS tournaments (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind                 VARCHAR(8)  NOT NULL DEFAULT 'sync',
    status               VARCHAR(16) NOT NULL DEFAULT 'voting',
    format               VARCHAR(24) NOT NULL DEFAULT 'single_elim_bo3',
    default_start_ts     TIMESTAMPTZ NOT NULL,
    scheduled_start_ts   TIMESTAMPTZ,
    voting_closes_at     TIMESTAMPTZ,
    lock_at              TIMESTAMPTZ NOT NULL,
    locked_at            TIMESTAMPTZ,
    started_at           TIMESTAMPTZ,
    ended_at             TIMESTAMPTZ,
    min_players          SMALLINT NOT NULL DEFAULT 8,
    max_players          SMALLINT NOT NULL DEFAULT 16,
    prize_tier           VARCHAR(8),
    winner_signup_id     UUID,
    runner_up_signup_id  UUID,
    third_place_signup_id UUID,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by           VARCHAR(16) NOT NULL DEFAULT 'cron'
);
CREATE INDEX IF NOT EXISTS idx_tournaments_status ON tournaments (status);
CREATE INDEX IF NOT EXISTS idx_tournaments_default_start ON tournaments (default_start_ts);

-- Per-player signup row.
-- is_speculative: TRUE when >16 signed up and this row is a ~-prefixed tentative slot.
--                 Promoted to FALSE once lock + 24h passes OR a penalty-free late signup
--                 can't bump them.
-- penalty_at_signup: snapshot of that player's penalty % when they signed up
--                    (used for >16 tiebreak / ~ promotion ordering).
-- cached_elo_at_lock: snapshot for bracket seeding, set at lock time.
-- ready_at: most recent ready-up heartbeat. Cleared server-side when >60s stale.
-- forfeited: TRUE if no-show at match start (past 5min grace).
CREATE TABLE IF NOT EXISTS tournament_signups (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id        UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    player_id            UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    signed_up_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_speculative       BOOLEAN NOT NULL DEFAULT false,
    penalty_at_signup    DOUBLE PRECISION NOT NULL DEFAULT 0,
    seed                 SMALLINT,
    cached_elo_at_lock   DOUBLE PRECISION,
    ready_at             TIMESTAMPTZ,
    forfeited            BOOLEAN NOT NULL DEFAULT false,
    placed_rank          SMALLINT,
    UNIQUE (tournament_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_tournament_signups_tournament
    ON tournament_signups (tournament_id);
CREATE INDEX IF NOT EXISTS idx_tournament_signups_player
    ON tournament_signups (player_id);

-- Back-references from tournaments to winning signups (added after the table exists).
ALTER TABLE tournaments
    ADD CONSTRAINT fk_tournaments_winner_signup
    FOREIGN KEY (winner_signup_id) REFERENCES tournament_signups(id) ON DELETE SET NULL;
ALTER TABLE tournaments
    ADD CONSTRAINT fk_tournaments_runner_up_signup
    FOREIGN KEY (runner_up_signup_id) REFERENCES tournament_signups(id) ON DELETE SET NULL;
ALTER TABLE tournaments
    ADD CONSTRAINT fk_tournaments_third_place_signup
    FOREIGN KEY (third_place_signup_id) REFERENCES tournament_signups(id) ON DELETE SET NULL;

-- Bracket match rows. One row per BO3 slot, including byes.
-- bracket_side: 'W' (winners — only path for sync single-elim) | 'TP' (3rd-place match)
--               (future 'L', 'GF', 'GF_RESET' for async double-elim, Phase 2.)
-- prereq_match_ids: upstream matches whose winners feed this match's p1/p2. NULL-empty for
--                   round 1. Partial-advance is implemented by checking this list rather
--                   than the round number — a match becomes playable the moment both
--                   prereq matches have winners (or is_bye upstream).
-- is_bye: TRUE when p2_signup_id IS NULL (top seed auto-advances).
-- series_id: FK into ranked_series once the match is actually started. Reuses the BO3
--            reporting pipeline. ranked_series.is_tournament is set for UI/history
--            filtering; Glicko still runs so tournament results move ladder Elo.
CREATE TABLE IF NOT EXISTS tournament_matches (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id        UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    round                SMALLINT NOT NULL,
    bracket_side         VARCHAR(4) NOT NULL DEFAULT 'W',
    slot_idx             SMALLINT NOT NULL,
    p1_signup_id         UUID REFERENCES tournament_signups(id) ON DELETE SET NULL,
    p2_signup_id         UUID REFERENCES tournament_signups(id) ON DELETE SET NULL,
    prereq_match_ids     UUID[] NOT NULL DEFAULT '{}',
    is_bye               BOOLEAN NOT NULL DEFAULT false,
    status               VARCHAR(16) NOT NULL DEFAULT 'pending',
    series_id            UUID REFERENCES ranked_series(id) ON DELETE SET NULL,
    winner_signup_id     UUID REFERENCES tournament_signups(id) ON DELETE SET NULL,
    ready_deadline_at    TIMESTAMPTZ,
    started_at           TIMESTAMPTZ,
    ended_at             TIMESTAMPTZ,
    UNIQUE (tournament_id, round, bracket_side, slot_idx)
);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_tournament_status
    ON tournament_matches (tournament_id, status);
CREATE INDEX IF NOT EXISTS idx_tournament_matches_series
    ON tournament_matches (series_id) WHERE series_id IS NOT NULL;

-- Time voting. One row per (player, slot_ts) — players can vote for multiple slots,
-- unweighted. Slots are discrete TIMESTAMPTZ values generated by the API at the 8
-- offered slots within ±24h of default_start_ts.
CREATE TABLE IF NOT EXISTS tournament_time_votes (
    tournament_id        UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    player_id            UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    slot_ts              TIMESTAMPTZ NOT NULL,
    voted_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tournament_id, player_id, slot_ts)
);
CREATE INDEX IF NOT EXISTS idx_tournament_time_votes_tournament_slot
    ON tournament_time_votes (tournament_id, slot_ts);

-- Force-start voting. Tournament unlocks and starts immediately when every current
-- signup has voted AND (latest_vote_ts - earliest_vote_ts) <= 30 minutes AND >= 8
-- signups present. Votes older than 30min from the newest one are considered stale
-- and ignored by the force-start check.
CREATE TABLE IF NOT EXISTS tournament_force_votes (
    tournament_id        UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    player_id            UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    voted_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tournament_id, player_id)
);

-- Per-player penalty cache. Rolling 90-day show rate with linear decay.
--   raw_penalty = sum(decay(age_days) for each miss) / sum(decay(age_days) for each signup)
--   decay(d)    = max(0, 1 - d/90)
-- Cached for display speed; refreshed inline on each signup + nightly cron.
-- no_show_last_at / latest_signup_at are useful for the player-profile view ("last
-- no-show 12 days ago").
CREATE TABLE IF NOT EXISTS player_tournament_penalty (
    player_id            UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    cached_penalty_pct   DOUBLE PRECISION NOT NULL DEFAULT 0,
    signups_90d          SMALLINT NOT NULL DEFAULT 0,
    missed_90d           SMALLINT NOT NULL DEFAULT 0,
    no_show_last_at      TIMESTAMPTZ,
    latest_signup_at     TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Extend ranked_series so a series created for a tournament match is distinguishable
-- and can be skipped by Glicko. Tournament seeding is snapshot at lock; individual
-- series outcomes do not move ladder Elo.
ALTER TABLE ranked_series
    ADD COLUMN IF NOT EXISTS tournament_id UUID REFERENCES tournaments(id) ON DELETE SET NULL;
ALTER TABLE ranked_series
    ADD COLUMN IF NOT EXISTS is_tournament BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_ranked_series_tournament
    ON ranked_series (tournament_id) WHERE tournament_id IS NOT NULL;

-- ============================================================
-- Verification
-- ============================================================
-- After running:
--   \d+ tournaments
--   \d+ tournament_signups
--   \d+ tournament_matches
--   \d+ ranked_series          -- confirm is_tournament + tournament_id columns present
