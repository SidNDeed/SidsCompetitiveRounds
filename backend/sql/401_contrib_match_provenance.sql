-- 401_contrib_match_provenance.sql
--
-- Admin evidence report, phase 2 (ship-gate row B10, review round B10-R3):
-- the match a per-game contribution was derived for, stored and indexed on
-- both evidence sources that keep per-game contributions.
--
--   combat_contrib.match_id   NEW column, UUID NULL. The ranked match the
--                             combat worker derived the row for, written by
--                             combat_evidence._write_contributions in the
--                             INSERT that creates the row (the match it
--                             attached in the same transaction). No other
--                             statement writes it and no statement updates a
--                             stored contribution: the worker's re-attachment
--                             UPDATE writes combat_games only, a pass that
--                             does not derive leaves the stored rows as they
--                             are, and the purge only deletes rows past the
--                             retention.
--   ix_combat_contrib_match   btree (match_id) on combat_contrib.
--   ix_card_contrib_match     btree (match_id) on card_contrib. The column
--                             exists since 370 and card_evidence._write_contrib
--                             already writes it; the index is new.
--
-- The admin evidence report reads both columns: a contribution is shown and
-- totalled for a match only when its stored match_id is that match's id, and
-- both indexes serve the report's lookup of the contributions stored for the
-- page's matches (admin_evidence.section_sql, statement `contrib_keys`).
--
-- NO BACKFILL. Combat rows written before this file carry NULL, and the
-- report shows a NULL row under the word `unattributed`, in no total. A
-- backfill would have to guess the match from the games row, which is the
-- very association this column replaces; the worker writes the column on
-- the next derivation of each game. Like card_contrib.match_id, the column
-- has no foreign key (matches rows are the report's subject, not owned by
-- the evidence lanes).
--
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND.
-- -----------------------------------------------
-- The api build carrying this lane names combat_contrib.match_id in the
-- worker's INSERT and in the report's combat select. Against a schema
-- without the column, every combat derivation fails (the game keeps its
-- records and is retried) and the report's combat section reads
-- `unavailable`. So the file lands first, as a migration-only precursor
-- commit (the two-SHA order, #477): the migrate verb applies it on the
-- primary, the standby receives it by streaming replication, the column and
-- both indexes are read back on both boxes, and only then does the code
-- deploy. An api build without this lane ignores the column and the indexes.
--
-- LOCKS. On a first run, ADD COLUMN of a nullable column with no default
-- changes the catalog only (no table rewrite), but its ACCESS EXCLUSIVE lock
-- on combat_contrib is held from that statement until COMMIT: combat_contrib
-- readers and writers wait through BOTH index builds (the combat index and
-- then the card index) until the file commits. Each CREATE INDEX holds SHARE
-- on its own table while it builds, so the worker's writes to card_contrib
-- wait during the card index build while card_contrib readers continue.
-- `lock_timeout` bounds only how long the file waits to START each step
-- behind a transaction already in flight, not the build durations; if it
-- expires the whole file rolls back with nothing changed and is re-applied.
--
-- RE-RUNS. Each step is guarded on the catalog and issued only when its
-- object is absent from the current schema, so a second run issues none of
-- them and takes no lock on either table (an `IF NOT EXISTS` spelling alone
-- takes the table lock before it checks; test_migration_reruns holds this
-- file to that). The statements inside the guards keep `IF NOT EXISTS`.
--
-- POST-CHECK. After the guards, one read compares the column and both
-- indexes with the definitions this file states (uuid, nullable, no default;
-- btree (match_id), valid, not unique, on the named table). Any other
-- same-named object aborts the file with the names that differ, because a
-- guard alone would accept it.

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m401col$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_attribute a
                   JOIN pg_class c ON c.oid = a.attrelid
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'combat_contrib'
                    AND a.attname = 'match_id'
                    AND NOT a.attisdropped) THEN
    ALTER TABLE combat_contrib ADD COLUMN IF NOT EXISTS match_id UUID NULL;
  END IF;
END $m401col$;

DO $m401combat$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'ix_combat_contrib_match') THEN
    CREATE INDEX IF NOT EXISTS ix_combat_contrib_match ON combat_contrib (match_id);
  END IF;
END $m401combat$;

DO $m401card$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'ix_card_contrib_match') THEN
    CREATE INDEX IF NOT EXISTS ix_card_contrib_match ON card_contrib (match_id);
  END IF;
END $m401card$;

DO $m401check$
DECLARE
  differing text;
  columns_matching integer;
BEGIN
  SELECT count(*) INTO columns_matching
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = current_schema()
     AND c.relname = 'combat_contrib'
     AND a.attname = 'match_id'
     AND NOT a.attisdropped
     AND a.atttypid = 'uuid'::regtype
     AND NOT a.attnotnull
     AND NOT a.atthasdef;
  IF columns_matching <> 1 THEN
    RAISE EXCEPTION '401: combat_contrib.match_id differs from this file (uuid, nullable, no default)';
  END IF;
  SELECT string_agg(w.name, ', ' ORDER BY w.name) INTO differing
    FROM (VALUES ('ix_combat_contrib_match', 'combat_contrib'),
                 ('ix_card_contrib_match', 'card_contrib')) AS w(name, tbl)
   WHERE NOT EXISTS (
         SELECT 1
           FROM pg_index i
           JOIN pg_class ci ON ci.oid = i.indexrelid
           JOIN pg_class t ON t.oid = i.indrelid
           JOIN pg_namespace n ON n.oid = ci.relnamespace
          WHERE n.nspname = current_schema()
            AND ci.relname = w.name
            AND t.relname = w.tbl
            AND NOT i.indisunique
            AND i.indisvalid
            AND substr(pg_get_indexdef(i.indexrelid),
                       strpos(pg_get_indexdef(i.indexrelid), ' USING ') + 7) = 'btree (match_id)');
  IF differing IS NOT NULL THEN
    RAISE EXCEPTION '401: index definition differs from this file: %', differing;
  END IF;
END $m401check$;

COMMIT;
