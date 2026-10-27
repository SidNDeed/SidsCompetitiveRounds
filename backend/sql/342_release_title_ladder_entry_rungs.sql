-- 342_release_title_ladder_entry_rungs.sql
--
-- SUPERSEDED BY 365 AND 366. This file changes nothing on any database.
--
-- Migration 365 (title_ladders_five_tiers) publishes the five-tier catalogue:
-- 32 ladders of five rungs each, every tier-1 rung on sale. Migration 366
-- (title_refunds_voidshot_kingslayer) retires two titles. Together they are
-- the catalogue that is approved and live. This file used to put the eight
-- entry rungs of the earlier eight-ladder catalogue (331) on sale; 365 does
-- that for every entry rung, so nothing is left for this file to do.
--
-- Required behaviour, on every database and on every application:
--   * it writes no row, takes no row lock and raises nothing;
--   * it reads no table, so it applies the same way whatever catalogue the
--     database holds, before or after 365 and 366;
--   * applying it once, twice or never leaves the same database.
--
-- It is kept, and keeps its number and name, so the number stays taken and
-- no later file reuses it. A release train may list it or leave it out;
-- neither choice changes anything.
--
-- DEPLOY ORDER: either side first; it changes nothing.
--
-- psql -f does not wrap a file in a transaction (#340); the statement below
-- sits in an explicit transaction like every other migration here.

BEGIN;

SELECT 1;

COMMIT;
