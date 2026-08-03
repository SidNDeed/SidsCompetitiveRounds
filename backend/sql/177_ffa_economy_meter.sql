-- 177: FFA battles-x-players economy meter — audit columns.
--
-- The v1.36.0 payout is metered on WORK (decisive half-points, which are
-- inside the signed HMAC canonical) instead of per-game constants. These
-- columns store what the meter saw so the seconds-per-battle fit s(P) can be
-- re-fitted from server-side receipt deltas later (the shipped fit rests on
-- 38 games and is clamped at the P=6 value above 6 players).
--
-- *** MUST run BEFORE the API deploy that writes them (learning #235/#5c.9:
-- the INSERT in the hot submit path gains these columns; begin_nested cannot
-- rescue a missing column in a main-path INSERT). ***
--
-- NULLable, no backfill: pre-meter games genuinely did not record them, and
-- NULL is the honest value (#257 — a metric that starts mid-history must be
-- NULLable so averages divide by the rows that carry it).

ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS battles_total   INTEGER NULL;
ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS paid_battles    REAL    NULL;
ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS elapsed_seconds INTEGER NULL;

DO $$ BEGIN RAISE NOTICE '177 ffa_economy_meter: post-check OK'; END $$;
