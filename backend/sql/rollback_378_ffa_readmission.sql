-- rollback_378_ffa_readmission.sql
-- The inverse of migration 378 (FFA mid-game readmission). NOT a release-train
-- migration and never applied by the train: a hand-run file for the case the
-- 378 schema has to come back out. It drops exactly what 378 added and nothing
-- else. 378 is additive (every step IF NOT EXISTS or a guarded DO block), so no
-- table or column of 325 or earlier is touched here.
--
-- DEPLOY ORDER: THE API FIRST. Roll the api back to a build that names none of
-- these objects before running this file; the new api reads and writes every
-- object below on the FFA paths. The rollback order of the RJ server landing is
-- rollback_384 (i18n keys), then rollback_383 (the Stage 2 hold), then this
-- file (ruling R3 of the landing).
--
-- WHAT IS LOST. The readmit flag of every lobby, the readmission hold of every
-- seat row, the fallback class of every FFA report, the four readmission tables
-- with their rows, and the kind, game, chain_v and verifier labels of
-- ffa_kept_epochs. The 378 backfill labelled every pre-378 epoch row as a
-- version 1 late admission, which is the one reading the old api makes without
-- the columns; rows the new api wrote as kind r (chain version 2) lose that
-- label, and the old api reads them as version 1 rows, which they are not.
--
-- Explicit transaction (learning 340): all or nothing. Every DROP is IF EXISTS,
-- so a second run changes nothing. The post-check raises if any 378 object is
-- still present, which rolls the whole file back.

BEGIN;

-- The constraints 378 added to pre-existing tables. The constraints of the
-- four new tables go with the tables.
ALTER TABLE ffa_matches        DROP CONSTRAINT IF EXISTS ck_ffa_match_fallback_cls;
ALTER TABLE ffa_kept_epochs    DROP CONSTRAINT IF EXISTS ck_ffa_epoch_kind_r;
ALTER TABLE ffa_kept_epochs    DROP CONSTRAINT IF EXISTS ck_ffa_epoch_chain_v;
ALTER TABLE ffa_kept_epochs    DROP CONSTRAINT IF EXISTS ck_ffa_epoch_kind;
ALTER TABLE ffa_assembly_seats DROP CONSTRAINT IF EXISTS ck_ffa_seat_hold;

-- The four tables, in the reverse of their creation order. None references
-- another of the four; each references ffa_lobbies and players only.
DROP TABLE IF EXISTS ffa_report_journal;
DROP TABLE IF EXISTS ffa_report_windows;
DROP TABLE IF EXISTS ffa_readmit_attempts;
DROP TABLE IF EXISTS ffa_seat_readmissions;

-- The columns, in the reverse of their addition order. Dropping kind and
-- chain_v takes the SET DEFAULT and SET NOT NULL of 378 with them.
ALTER TABLE ffa_matches        DROP COLUMN IF EXISTS fallback_cls;
ALTER TABLE ffa_kept_epochs    DROP COLUMN IF EXISTS verifier;
ALTER TABLE ffa_kept_epochs    DROP COLUMN IF EXISTS chain_v;
ALTER TABLE ffa_kept_epochs    DROP COLUMN IF EXISTS game;
ALTER TABLE ffa_kept_epochs    DROP COLUMN IF EXISTS kind;
ALTER TABLE ffa_assembly_seats DROP COLUMN IF EXISTS hold_until;
ALTER TABLE ffa_assembly_seats DROP COLUMN IF EXISTS hold_anchor_at;
ALTER TABLE ffa_assembly_seats DROP COLUMN IF EXISTS hold_n;
ALTER TABLE ffa_assembly_seats DROP COLUMN IF EXISTS present_at;
ALTER TABLE ffa_lobbies        DROP COLUMN IF EXISTS readmit_v1;

-- The post-check: nothing of 378 remains. It raises on any leftover, so a
-- partial run rolls back whole.
DO $chk$
DECLARE
    left_over text[] := ARRAY[]::text[];
    t text;
    c record;
BEGIN
    FOREACH t IN ARRAY ARRAY['ffa_seat_readmissions', 'ffa_readmit_attempts',
                             'ffa_report_windows', 'ffa_report_journal'] LOOP
        IF to_regclass(t) IS NOT NULL THEN
            left_over := left_over || ('table ' || t);
        END IF;
    END LOOP;
    FOREACH t IN ARRAY ARRAY['ck_ffa_match_fallback_cls', 'ck_ffa_epoch_kind_r',
                             'ck_ffa_epoch_chain_v', 'ck_ffa_epoch_kind',
                             'ck_ffa_seat_hold'] LOOP
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = t) THEN
            left_over := left_over || ('constraint ' || t);
        END IF;
    END LOOP;
    FOR c IN
        SELECT * FROM (VALUES
            ('ffa_lobbies', 'readmit_v1'),
            ('ffa_assembly_seats', 'present_at'),
            ('ffa_assembly_seats', 'hold_n'),
            ('ffa_assembly_seats', 'hold_anchor_at'),
            ('ffa_assembly_seats', 'hold_until'),
            ('ffa_kept_epochs', 'kind'),
            ('ffa_kept_epochs', 'game'),
            ('ffa_kept_epochs', 'chain_v'),
            ('ffa_kept_epochs', 'verifier'),
            ('ffa_matches', 'fallback_cls')) AS v(tbl, col)
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = c.tbl AND column_name = c.col) THEN
            left_over := left_over || ('column ' || c.tbl || '.' || c.col);
        END IF;
    END LOOP;
    IF array_length(left_over, 1) IS NOT NULL THEN
        RAISE EXCEPTION 'rollback_378 post-check FAILED: % still present',
            array_to_string(left_over, ', ');
    END IF;
    RAISE NOTICE 'rollback_378 post-check OK';
END $chk$;

COMMIT;
