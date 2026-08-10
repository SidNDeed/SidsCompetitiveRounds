-- 208: live game-1 points for 2v2 and FFA, so betting closes on the SAME
-- rule 1v1 has always used — 2 points scored in game 1 — instead of a clock.
--
-- WHY THIS EXISTS
--
-- 1v1 has had live-point reporting since v1.22: the reporter POSTs the
-- current game-1 score, ranked_series.live_p*_points carry it, and betting
-- locks once the two sides' points sum to 2. 2v2 and FFA never had that
-- channel, so their bet windows were guessed at instead:
--
--   * 2v2 had NO mid-game close at all — game 1 stayed bettable for its full
--     ~9 minutes, so a live viewer could back a side that had already won the
--     opening exchanges.
--   * FFA used _ffa_bet_window_open, a 90-second clock whose own docstring
--     calls itself an INTERIM exploit gate "replaced by the exact 2-point
--     lock as soon as the client can push live scores".
--
-- This migration is the missing channel. The client reports game-1 points for
-- both modes exactly as it does for 1v1; these columns hold them; the listing
-- and the placement endpoint both lock at a summed 2. One rule, four modes.
--
-- MONOTONIC BY CONSTRUCTION
--
-- Writes are GREATEST(stored, incoming) in a single UPDATE (never a
-- read-then-write), so an out-of-order or duplicated report from either
-- client can only ever raise the stored score. Betting cannot re-open once
-- the cutoff is crossed.
--
-- NO DATA BACKFILL: pure DDL. Existing rows default to 0, which reads as
-- "game 1 has not been scored in yet" — correct for anything already live,
-- and any series/lobby old enough to matter is closed by its own rules.
--
-- Re-runnable statement by statement (#243: the deploy wrapper may execute
-- the whole file twice).

-- ── 2v2 ────────────────────────────────────────────────────────────────
-- Team 1 / team 2 in the SAME slot order team_series already uses
-- (t1a/t1b vs t2a/t2b), so the reporter's mapping needs no extra lookup.
ALTER TABLE team_series ADD COLUMN IF NOT EXISTS live_t1_points INTEGER NOT NULL DEFAULT 0;
ALTER TABLE team_series ADD COLUMN IF NOT EXISTS live_t2_points INTEGER NOT NULL DEFAULT 0;

-- ── FFA ────────────────────────────────────────────────────────────────
-- FFA is a free-for-all: there is no "two sides" to sum, so what matters for
-- the cutoff is the HIGHEST point total anyone in the current game holds and
-- which game it belongs to (a lobby plays many games; a stale score from
-- game 2 must not lock game 3's window).
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS live_top_points INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS live_points_game INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_constraint
                    WHERE conrelid = 'team_series'::regclass
                      AND conname = 'team_series_live_points_ck') THEN
        ALTER TABLE team_series ADD CONSTRAINT team_series_live_points_ck
            CHECK (live_t1_points >= 0 AND live_t2_points >= 0);
    END IF;
    IF NOT EXISTS (SELECT FROM pg_constraint
                    WHERE conrelid = 'ffa_lobbies'::regclass
                      AND conname = 'ffa_lobbies_live_points_ck') THEN
        ALTER TABLE ffa_lobbies ADD CONSTRAINT ffa_lobbies_live_points_ck
            CHECK (live_top_points >= 0 AND live_points_game >= 0);
    END IF;
END $$;

DO $$
DECLARE
    _team_cols INT;
    _ffa_cols  INT;
BEGIN
    SELECT COUNT(*) INTO _team_cols FROM information_schema.columns
     WHERE table_name = 'team_series'
       AND column_name IN ('live_t1_points', 'live_t2_points');
    SELECT COUNT(*) INTO _ffa_cols FROM information_schema.columns
     WHERE table_name = 'ffa_lobbies'
       AND column_name IN ('live_top_points', 'live_points_game');
    RAISE NOTICE 'post-check: team_series live-point columns=%, ffa_lobbies live-point columns=%',
                 _team_cols, _ffa_cols;
    IF _team_cols <> 2 OR _ffa_cols <> 2 THEN
        RAISE EXCEPTION 'migration 208 incomplete (team=% ffa=%)', _team_cols, _ffa_cols;
    END IF;
    RAISE NOTICE 'post-check OK: live-point channels ready for 2v2 + FFA';
END $$;
