-- 377_admin_evidence_indexes.sql
--
-- Admin evidence report, phase 1a: four order indexes on `matches`, each
-- ending in the `id` its ordering breaks ties on, so every report read is an
-- index-ordered scan under a LIMIT with no sort in between (design 2.9 and
-- 7.1). The existing player indexes stop at `ended_at`
-- (001_schema.sql:91-93) and stay as they are. A statistics object on the
-- seat pair lets the planner see that LIMIT bind (below).
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
-- STATISTICS ON THE SEAT PAIR. A fifth guarded block creates the extended
-- statistics object `stx_matches_pair`, kind `mcv` only, on
-- (player1_id, player2_id), then runs `ANALYZE matches`, both inside the
-- same BEGIN and COMMIT. The planner must estimate the correlated seat pair
-- from measured frequencies so that a pair read's branch LIMIT binds: with
-- the two seat selectivities multiplied as independent, a pair-global
-- baseline over a frequent pair was estimated at 308 rows where 4,999 were
-- read, and the planner chose a bitmap read and a sort over the whole pair
-- instead of an ordered index read under the LIMIT. The object corrects the
-- estimate and forces no plan. `CREATE STATISTICS` and `ANALYZE` each take
-- SHARE UPDATE EXCLUSIVE on `matches`, which readers and writers do not
-- wait for; on a first run the index builds already hold SHARE until
-- COMMIT, so the sampling time of the `ANALYZE` (about 30,000 rows at the
-- default statistics target) adds to the write block stated above. The
-- guard probes `pg_statistic_ext` by name, so a re-run issues neither
-- statement; later automatic analyses keep the object current.
--
-- POST-CHECK. After the guards, one read compares all four indexes with the
-- definition this file states: on `matches`, not unique, valid, and the same
-- columns, directions and predicate. A same-named index with any other
-- definition aborts the file with the names that differ, because the guard
-- alone would accept it and every report read would then lose its bound
-- without any error. The statistics object is held to its definition the
-- same way: on `matches`, kind `mcv` only, over exactly the two seat
-- columns in that order.

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

DO $m377stats$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_statistic_ext s
                   JOIN pg_namespace n ON n.oid = s.stxnamespace
                  WHERE n.nspname = current_schema()
                    AND s.stxname = 'stx_matches_pair') THEN
    CREATE STATISTICS IF NOT EXISTS stx_matches_pair (mcv) ON player1_id, player2_id FROM matches;
    ANALYZE matches;
  END IF;
END $m377stats$;

DO $m377check$
DECLARE
  differing text;
  stats_matching integer;
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
  SELECT count(*) INTO stats_matching
    FROM pg_statistic_ext s
    JOIN pg_namespace n ON n.oid = s.stxnamespace
    JOIN pg_class t ON t.oid = s.stxrelid
   WHERE n.nspname = current_schema()
     AND s.stxname = 'stx_matches_pair'
     AND t.relname = 'matches'
     AND s.stxkind::text = '{m}'
     AND (SELECT array_agg(a.attname::text ORDER BY k.ord)
            FROM unnest(s.stxkeys::int2[]) WITH ORDINALITY AS k(attnum, ord)
            JOIN pg_attribute a ON a.attrelid = s.stxrelid AND a.attnum = k.attnum)
         = ARRAY['player1_id', 'player2_id'];
  IF stats_matching <> 1 THEN
    RAISE EXCEPTION '377: statistics object differs from this file: stx_matches_pair';
  END IF;
END $m377check$;

COMMIT;
