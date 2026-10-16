-- 377_admin_evidence_indexes.sql
--
-- Admin evidence report, phase 1a: four order indexes on `matches`, each
-- ending in the `id` its ordering breaks ties on, so every report read is an
-- index-ordered scan under a LIMIT with no sort in between (design 2.9 and
-- 7.1). The existing player indexes stop at `ended_at`
-- (001_schema.sql:91-93) and stay as they are.
--
--   idx_matches_pair      pair reads and pair-global baselines, both
--                         orientation branches
--   idx_matches_p1_order  player reads and seat baselines, seat 1
--   idx_matches_p2_order  player reads and seat baselines, seat 2
--   idx_matches_series    series reads, oldest first, bounded by a sentinel
--                         row
--
-- Additive only: no column, row or existing index is changed, and nothing
-- reads these indexes by name. The `Match` model declares all four beside
-- the existing three (backend/api/models.py, `Match.__table_args__`), so a
-- schema built from the model carries them too.
--
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND.
-- -----------------------------------------------
-- The report routes are correct without these indexes but are only bounded
-- in time with them, so the file lands ahead of the code that reads through
-- them, as a migration-only precursor commit (the two-SHA order, #477): the
-- precursor deploys, the migrate verb applies this file on the primary, the
-- standby receives it by streaming replication, the four indexes are read
-- back on both boxes, and only then does the code commit deploy.
--
-- WRITE BLOCK ON matches (notes). Each first-run build is a plain
-- `CREATE INDEX`, which holds SHARE on `matches` for as long as it builds:
-- readers continue, and every writer to `matches` (a game report) waits
-- until the build ends. At the measured table size (design 2.8) each build
-- is short. `lock_timeout` below bounds how long the file waits to START a
-- build behind a writer already in flight; if it expires the file aborts as
-- a whole, nothing is left half-built, and the file is re-applied.
--
-- RE-RUNS. Each index is guarded on the catalog: the `CREATE INDEX` runs
-- only when no relation of that name exists in the current schema. Spelling
-- it `IF NOT EXISTS` alone would decide the same question too late, because
-- `CREATE INDEX` takes its SHARE lock on the table before it looks for the
-- name, so a second run would queue behind every writer to `matches`
-- (`test_a_second_run_takes_no_blocking_lock` holds this file to that). The
-- statement inside each guard is the design's text exactly, `IF NOT EXISTS`
-- included.
--
-- POST-CHECK. After the guards, one read compares all four indexes with the
-- definition this file states: on `matches`, not unique, valid, and the same
-- columns, directions and predicate. A same-named index with any other
-- definition aborts the file with the names that differ, because the guard
-- alone would accept it and every report read would then lose its bound
-- without any error.

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m377pair$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'idx_matches_pair') THEN
    CREATE INDEX IF NOT EXISTS idx_matches_pair ON matches (player1_id, player2_id, ended_at DESC, id DESC);
  END IF;
END $m377pair$;

DO $m377p1$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'idx_matches_p1_order') THEN
    CREATE INDEX IF NOT EXISTS idx_matches_p1_order ON matches (player1_id, ended_at DESC, id DESC);
  END IF;
END $m377p1$;

DO $m377p2$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'idx_matches_p2_order') THEN
    CREATE INDEX IF NOT EXISTS idx_matches_p2_order ON matches (player2_id, ended_at DESC, id DESC);
  END IF;
END $m377p2$;

DO $m377series$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'idx_matches_series') THEN
    CREATE INDEX IF NOT EXISTS idx_matches_series ON matches (series_id, ended_at, id) WHERE series_id IS NOT NULL;
  END IF;
END $m377series$;

DO $m377check$
DECLARE
  differing text;
BEGIN
  SELECT string_agg(w.name, ', ' ORDER BY w.name) INTO differing
    FROM (VALUES
            ('idx_matches_pair',
             'btree (player1_id, player2_id, ended_at DESC, id DESC)'),
            ('idx_matches_p1_order', 'btree (player1_id, ended_at DESC, id DESC)'),
            ('idx_matches_p2_order', 'btree (player2_id, ended_at DESC, id DESC)'),
            ('idx_matches_series',
             'btree (series_id, ended_at, id) WHERE (series_id IS NOT NULL)')
         ) AS w(name, def)
   WHERE NOT EXISTS (
         SELECT 1
           FROM pg_index i
           JOIN pg_class ci ON ci.oid = i.indexrelid
           JOIN pg_class t ON t.oid = i.indrelid
           JOIN pg_namespace n ON n.oid = ci.relnamespace
          WHERE n.nspname = current_schema()
            AND ci.relname = w.name
            AND t.relname = 'matches'
            AND NOT i.indisunique
            AND i.indisvalid
            AND substr(pg_get_indexdef(i.indexrelid),
                       strpos(pg_get_indexdef(i.indexrelid), ' USING ') + 7) = w.def);
  IF differing IS NOT NULL THEN
    RAISE EXCEPTION '377: index definition differs from this file: %', differing;
  END IF;
END $m377check$;

COMMIT;
