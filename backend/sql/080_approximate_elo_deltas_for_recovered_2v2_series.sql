-- 080_approximate_elo_deltas_for_recovered_2v2_series.sql
-- Populates the per-slot rating_change columns on the two recovered
-- Sid+feauxen series so the F5 history view actually renders an elo
-- chip. We can't reconstruct the ACTUAL Glicko inputs from 2026-05-04
-- (no rating-history snapshot for 2v2 ratings), so these deltas are
-- computed as if the matches were played against the snapshot of
-- pre-series Glicko inputs we could best reconstruct:
--   T2A (Sid):     r=1820, RD=215, vol=0.06   (real, current 2v2 row)
--   T2B (feauxen): r=1500, RD=350, vol=0.06   (defaults, no 2v2 row)
--   T1A (MAX1T0P): r=1500, RD=350, vol=0.06   (defaults)
--   T1B (NotHoly): r=1500, RD=350, vol=0.06   (defaults)
-- Then chained: series B uses post-series-A outputs as its inputs.
-- Calculation done with backend/api/glicko2.py:calculate_new_rating
-- using tau=0.5. Three of the four players had massive RD (350), so
-- feauxen's series-A delta of +247 reflects big upset swing under
-- high-uncertainty defaults — accurate Glicko output, just visibly
-- larger than a typical match.
--
-- This ONLY backfills team_series.t*_rating_change for UI display.
-- We do NOT touch the live glicko_ratings_2v2 rows — the players'
-- current ratings already reflect every match they played AFTER
-- these recovered series, and applying these deltas now would
-- double-count or invent rating history.

UPDATE team_series
   SET t1a_rating_change = -182.9,
       t1b_rating_change = -182.9,
       t2a_rating_change =  +65.0,
       t2b_rating_change = +247.3
 WHERE id = '4ea30d95-9612-4f71-a4f0-47dd4a064da3';

UPDATE team_series
   SET t1a_rating_change = -45.6,
       t1b_rating_change = -45.6,
       t2a_rating_change = +22.3,
       t2b_rating_change = +57.1
 WHERE id = 'cdd8d17a-64b4-488c-9e73-90b66299cd77';
