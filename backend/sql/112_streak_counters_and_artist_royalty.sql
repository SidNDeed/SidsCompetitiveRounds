-- 112_streak_counters_and_artist_royalty.sql  (v1.30, Sid July 12 batch)
--
-- 1) Win-streak achievement counters (item 2):
--      consecutive_sweeps — consecutive 5-0 WINS (any non-sweep game or any
--                           loss resets). Flawless fires at 5.
--      casual_win_streak  — consecutive CASUAL wins (a casual loss resets;
--                           ranked games don't touch it). Century Club /
--                           Casual Conqueror / Touch Grass at 100/200/500.
--    Both start at 0 from this deploy — the achievements are forward-looking.
--
-- 2) No schema needed for the 30% artist royalty (rides gold_transactions
--    with reason='artist_royalty'), included here as documentation.

ALTER TABLE players ADD COLUMN IF NOT EXISTS consecutive_sweeps INTEGER NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS casual_win_streak INTEGER NOT NULL DEFAULT 0;
