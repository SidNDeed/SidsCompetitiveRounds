-- 348: team_series_games -- the per-game record the 2v2 lead-forfeit rule
-- reads (v1.41.0 beta review, round 2, finding 1).
--
-- team_series_report_dc completes a series to the team that stayed, with
-- ratings and gold, only when that team was already a game up AND the
-- abandoned game saw real play: two points between the teams. The second half
-- used to come from the DC report's own query string, one survivor's snapshot
-- outside the DC signature, so two honest survivors holding different
-- snapshots of the same game got different settlements depending on which
-- report took the series lock first.
--
-- This table is the server's own record of that half, one row per game:
--   series_id, game_ordinal  the game, numbered by the server: the games
--                            recorded on the series (t1_series_wins +
--                            t2_series_wins) plus one, read under the series
--                            row lock when the post is written.
--   crossed_at               the transaction start of the LATEST live-points
--                            post for this game whose own pair summed to two
--                            or more. NULL = no post has carried two points.
--   max_points_sum           the largest pair sum any post for this game
--                            carried. For people reading the table; the
--                            settlement never reads it.
--   first_posted_at,
--   last_posted_at           when posts for this game began and last arrived.
-- Written only by POST /api/v1/team/series/{series_id}/live-points, read only
-- by the DC report. main.py's _record_team_game_points and
-- _team_game_crossed_two carry the rules, including why a crossing counts
-- only when it was posted after the game's settle window.
--
-- Not a column on team_series: live_t1_points / live_t2_points there are the
-- bet cutoff's series-wide latch (GREATEST across every game, kept across a
-- relock), which is exactly why they cannot answer a question about one game.
--
-- ON DELETE CASCADE: a row is a fact about one series' games and means
-- nothing without the series.
--
-- DEPLOY ORDER: apply BEFORE the API deploy that writes and reads it. Both the
-- writer and the reader are savepointed, so the reversed order fails no
-- request: the live-points POST still answers, and every DC report settles as
-- dc_incomplete (no automatic forfeit) until the table exists. Migration first
-- is still the correct order.
--
-- Idempotent: IF NOT EXISTS, one explicit transaction (#340).

BEGIN;

CREATE TABLE IF NOT EXISTS team_series_games (
    series_id       UUID        NOT NULL REFERENCES team_series(id) ON DELETE CASCADE,
    game_ordinal    SMALLINT    NOT NULL CHECK (game_ordinal >= 1),
    max_points_sum  INTEGER     NOT NULL DEFAULT 0 CHECK (max_points_sum >= 0),
    crossed_at      TIMESTAMPTZ NULL,
    first_posted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_posted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (series_id, game_ordinal)
);

COMMIT;
