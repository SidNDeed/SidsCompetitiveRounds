-- 209: FFA live points are a FIELD TOTAL, not one player's best.
--
-- Sid, Aug 9, correcting 208: "I did mean [2 points scored across the field].
-- For FFA or any mode that allows you to change the win condition to first to
-- 3, make it 1 point scored total if the win condition is 3 points."
--
-- 208 stored the HIGHEST total any single player held, on the reading that
-- "2 points scored" meant somebody reaching 2. It means two points having
-- been scored in the game, by anyone — the same shape 1v1 and 2v2 already
-- use (they sum both sides). This renames the column to say what it holds.
--
-- The cutoff itself now scales with the lobby's win condition, which only
-- FFA exposes (score_target, host-configurable 3-10, default 5):
--
--     score_target == 3  ->  betting closes at 1 point scored
--     otherwise          ->  betting closes at 2 points scored
--
-- That lives in the API (_ffa_bet_window_open), not here — a threshold is a
-- rule, and rules belong where they can be read next to the predicate they
-- gate. This migration only fixes the column's name and meaning.
--
-- SAFE TO RENAME: 208 shipped hours ago and the feature has never been live
-- for anyone — betting in FFA is refused outright for participants below
-- LIVE_POINTS_MIN_VERSION, which no released build satisfies, so every row
-- is still at its default 0. There is no stored value whose meaning changes
-- under players.
--
-- Re-runnable statement by statement (#243).

DO $$
BEGIN
    -- Rename only if 208's column is still the one present. Both guards
    -- matter: a re-run must not fail, and a fresh database that somehow got
    -- the new name first must not be clobbered.
    IF EXISTS (SELECT FROM information_schema.columns
                WHERE table_name = 'ffa_lobbies' AND column_name = 'live_top_points')
       AND NOT EXISTS (SELECT FROM information_schema.columns
                        WHERE table_name = 'ffa_lobbies' AND column_name = 'live_total_points') THEN
        ALTER TABLE ffa_lobbies RENAME COLUMN live_top_points TO live_total_points;
    END IF;
END $$;

-- Present on any database that never received 208.
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS live_total_points INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
    -- 208's CHECK names the old column; replace it rather than leave a
    -- constraint whose text no longer matches the schema.
    IF EXISTS (SELECT FROM pg_constraint
                WHERE conrelid = 'ffa_lobbies'::regclass
                  AND conname = 'ffa_lobbies_live_points_ck') THEN
        ALTER TABLE ffa_lobbies DROP CONSTRAINT ffa_lobbies_live_points_ck;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_constraint
                    WHERE conrelid = 'ffa_lobbies'::regclass
                      AND conname = 'ffa_lobbies_live_total_ck') THEN
        ALTER TABLE ffa_lobbies ADD CONSTRAINT ffa_lobbies_live_total_ck
            CHECK (live_total_points >= 0 AND live_points_game >= 0);
    END IF;
END $$;

DO $$
DECLARE
    _cols INT;
    _old  INT;
BEGIN
    SELECT COUNT(*) INTO _cols FROM information_schema.columns
     WHERE table_name = 'ffa_lobbies'
       AND column_name IN ('live_total_points', 'live_points_game');
    SELECT COUNT(*) INTO _old FROM information_schema.columns
     WHERE table_name = 'ffa_lobbies' AND column_name = 'live_top_points';
    RAISE NOTICE 'post-check: ffa_lobbies live-total columns=%, leftover live_top_points=%', _cols, _old;
    IF _cols <> 2 OR _old <> 0 THEN
        RAISE EXCEPTION 'migration 209 incomplete (new=% old=%)', _cols, _old;
    END IF;
    RAISE NOTICE 'post-check OK: FFA live points are a field total';
END $$;
