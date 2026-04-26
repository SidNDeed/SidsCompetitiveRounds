-- 052_fps_avg.sql
-- Per-match average FPS for each player. SMALLINT (NULL = not reported / opponent
-- didn't have the mod). Display-only; never feeds Glicko or anti-cheat.

ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS p1_fps_avg SMALLINT NULL,
    ADD COLUMN IF NOT EXISTS p2_fps_avg SMALLINT NULL;
