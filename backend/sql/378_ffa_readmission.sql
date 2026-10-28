-- 378: FFA mid-game readmission, the precursor (design V3, P4.8; P3 journal;
-- P5 rows). Files first, two-SHA order (learning 477): this file lands and is
-- run on the primary BEFORE the api that reads it, the standby takes it by
-- streaming replication, then the api goes to the primary, then the standby.
--
-- WHAT THE OLD API DOES AGAINST THIS SCHEMA DURING THE WINDOW. The api that
-- answers between this file and the new code never names a column added here:
--   * its lock UPDATE of ffa_lobbies and its REFORM insert leave readmit_v1 to
--     the default FALSE, the safe direction (no lobby of the old api is a
--     readmission lobby);
--   * its admission check inserts ffa_kept_epochs rows without kind, chain_v,
--     game or verifier: the defaults l and 1 describe that writer exactly
--     (every row it can insert is a late admission hashed by chain version 1),
--     and game stays NULL, which the kind r check below does not touch;
--   * its FFA report insert leaves ffa_matches.fallback_cls NULL (a report that
--     settled as the elected seat, which is every report the old api settles);
--   * it never reads or writes the four new tables.
-- The reverse order does not work: the new api writes every column below.
--
-- THE BACKFILL. Every existing ffa_kept_epochs row was written by the one
-- insert on main (_ffa_admission_check), so every existing row is a late
-- admission: it is labelled kind l, chain_v 1, and game = the late_game of the
-- seat row of that lobby and slot. Start seats were never epoch rows and are
-- not relabelled. Version 1 rows keep their chain bytes: no historical chain is
-- rewritten, and a lobby active across this file keeps verifying.
--
-- NO COLUMN OF 325 CHANGES (ffa_queue.held_until and held_lobby stay as they
-- are and nothing here writes them): the readmission hold lives on the seat row.
--
-- IDEMPOTENT. Every DDL step is IF NOT EXISTS or a guarded DO block, the
-- backfill updates only rows whose kind is still NULL, SET NOT NULL and SET
-- DEFAULT are no-ops on a re-run, and the post-check re-asserts what the first
-- run established. Explicit BEGIN and COMMIT because psql -f autocommits each
-- statement otherwise (learning 340); every value is a typed literal.

BEGIN;
SET LOCAL lock_timeout = '5s';

-- P4.6: the readmission flag, written once at lock beside assembly_v1 and
-- admission_v1. FALSE is the safe direction; the lock writer always names it.
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS readmit_v1 BOOLEAN NOT NULL DEFAULT FALSE;

-- P4.1: the hold on the seat row. present_at is the server receipt time of
-- the latest census of this seat listing its own slot with its own bound
-- actor; the three hold columns are written and cleared together.
ALTER TABLE ffa_assembly_seats ADD COLUMN IF NOT EXISTS present_at     TIMESTAMPTZ;
ALTER TABLE ffa_assembly_seats ADD COLUMN IF NOT EXISTS hold_n         SMALLINT;
ALTER TABLE ffa_assembly_seats ADD COLUMN IF NOT EXISTS hold_anchor_at TIMESTAMPTZ;
ALTER TABLE ffa_assembly_seats ADD COLUMN IF NOT EXISTS hold_until     TIMESTAMPTZ;

-- P4.8 (RJ2-H11): the kept-epoch kind, its game, the chain version and the
-- readmission token verifier (a SHA-256 hex digest, never the token).
ALTER TABLE ffa_kept_epochs ADD COLUMN IF NOT EXISTS kind     CHAR(1);
ALTER TABLE ffa_kept_epochs ADD COLUMN IF NOT EXISTS game     SMALLINT;
ALTER TABLE ffa_kept_epochs ADD COLUMN IF NOT EXISTS chain_v  SMALLINT;
ALTER TABLE ffa_kept_epochs ADD COLUMN IF NOT EXISTS verifier CHAR(64);

-- The backfill, before NOT NULL: kind l, chain_v 1, game = the seat's
-- late_game. A seat row of the same lobby and slot that was admitted late is
-- preferred; a row with no matching seat keeps game NULL and is still kind l.
WITH seat_game AS (
    SELECT DISTINCT ON (s.lobby_id, s.slot) s.lobby_id, s.slot, s.late_game
      FROM ffa_assembly_seats s
     ORDER BY s.lobby_id, s.slot, (s.late_admitted_at IS NULL), s.late_admitted_at,
              s.player_id
)
UPDATE ffa_kept_epochs e
   SET kind = CAST('l' AS CHAR(1)),
       chain_v = CAST(1 AS SMALLINT),
       game = sg.late_game
  FROM seat_game sg
 WHERE sg.lobby_id = e.lobby_id AND sg.slot = e.slot AND e.kind IS NULL;
UPDATE ffa_kept_epochs
   SET kind = CAST('l' AS CHAR(1)), chain_v = CAST(1 AS SMALLINT)
 WHERE kind IS NULL;
UPDATE ffa_kept_epochs SET chain_v = CAST(1 AS SMALLINT) WHERE chain_v IS NULL;

ALTER TABLE ffa_kept_epochs ALTER COLUMN kind SET DEFAULT 'l';
ALTER TABLE ffa_kept_epochs ALTER COLUMN kind SET NOT NULL;
ALTER TABLE ffa_kept_epochs ALTER COLUMN chain_v SET DEFAULT 1;
ALTER TABLE ffa_kept_epochs ALTER COLUMN chain_v SET NOT NULL;

-- P4.8: one row per hold, n immutable through claim, bind, entry and receipt.
-- The gone and leave columns of a bound seat move here at the bind.
CREATE TABLE IF NOT EXISTS ffa_seat_readmissions (
  lobby_id       UUID NOT NULL REFERENCES ffa_lobbies(id) ON DELETE CASCADE,
  player_id      UUID NOT NULL REFERENCES players(id),
  n              SMALLINT NOT NULL CHECK (n >= 1),
  anchor_at      TIMESTAMPTZ NOT NULL,
  held_at        TIMESTAMPTZ NOT NULL,
  hold_until     TIMESTAMPTZ NOT NULL,
  claimed_at     TIMESTAMPTZ,
  verifier       CHAR(64),
  bound_at       TIMESTAMPTZ,
  actor_nr       SMALLINT,
  game           SMALLINT,
  entered_at     TIMESTAMPTZ,
  refused_at     TIMESTAMPTZ,
  refused_reason VARCHAR(16),
  lapsed_at      TIMESTAMPTZ,
  gone_game      SMALLINT,
  gone_path      VARCHAR(8),
  left_at        TIMESTAMPTZ,
  left_cause     VARCHAR(16),
  left_label     VARCHAR(16),
  left_path      VARCHAR(12),
  PRIMARY KEY (lobby_id, player_id, n)
);

-- P5: every offered, claim, bind, entered and decline attempt is its own row.
CREATE TABLE IF NOT EXISTS ffa_readmit_attempts (
  lobby_id   UUID NOT NULL REFERENCES ffa_lobbies(id) ON DELETE CASCADE,
  player_id  UUID NOT NULL REFERENCES players(id),
  n          SMALLINT NOT NULL,
  attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
  kind       VARCHAR(8) NOT NULL,
  at         TIMESTAMPTZ NOT NULL,
  outcome    VARCHAR(8) NOT NULL,
  reason     VARCHAR(32),
  PRIMARY KEY (lobby_id, player_id, n, attempt_no)
);

-- P3 (RJ2-H6): the report window of one game of one lobby and the journal of
-- the reports it holds. settled_at is written once.
CREATE TABLE IF NOT EXISTS ffa_report_windows (
  lobby_id         UUID NOT NULL REFERENCES ffa_lobbies(id) ON DELETE CASCADE,
  game             SMALLINT NOT NULL,
  opened_at        TIMESTAMPTZ NOT NULL,
  settle_after     TIMESTAMPTZ NOT NULL,
  settled_at       TIMESTAMPTZ,
  settled_reporter UUID REFERENCES players(id),
  settled_cls      VARCHAR(2),
  PRIMARY KEY (lobby_id, game)
);

CREATE TABLE IF NOT EXISTS ffa_report_journal (
  lobby_id    UUID NOT NULL REFERENCES ffa_lobbies(id) ON DELETE CASCADE,
  game        SMALLINT NOT NULL,
  reporter_id UUID NOT NULL REFERENCES players(id),
  cls         VARCHAR(2),
  received_at TIMESTAMPTZ NOT NULL,
  payload     JSONB NOT NULL,
  state       VARCHAR(10) NOT NULL DEFAULT 'held',
  PRIMARY KEY (lobby_id, game, reporter_id)
);

-- P3: the class a settled FFA report came from when it was not the elected
-- seat's own report (NULL: settled as the elected seat, or before this file).
ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS fallback_cls VARCHAR(2);

DO $$
BEGIN
    BEGIN
        ALTER TABLE ffa_assembly_seats ADD CONSTRAINT ck_ffa_seat_hold
            CHECK ((hold_n IS NULL) = (hold_until IS NULL)
                   AND (hold_anchor_at IS NULL) = (hold_until IS NULL));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_kept_epochs ADD CONSTRAINT ck_ffa_epoch_kind
            CHECK (kind IN ('l', 'r'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_kept_epochs ADD CONSTRAINT ck_ffa_epoch_chain_v
            CHECK (chain_v IN (1, 2));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_kept_epochs ADD CONSTRAINT ck_ffa_epoch_kind_r
            CHECK (kind <> 'r' OR (game IS NOT NULL AND verifier IS NOT NULL AND chain_v = 2));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_seat_readmissions ADD CONSTRAINT ck_ffa_readmit_refused
            CHECK ((refused_at IS NULL) = (refused_reason IS NULL)
                   AND (refused_reason IS NULL OR refused_reason IN
                        ('declined', 'entry_failed', 'lobby_closed')));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_seat_readmissions ADD CONSTRAINT ck_ffa_readmit_gone
            CHECK ((gone_game IS NULL) = (gone_path IS NULL)
                   AND (gone_path IS NULL OR gone_path IN ('leave', 'witness')));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_readmit_attempts ADD CONSTRAINT ck_ffa_readmit_attempt
            CHECK (kind IN ('offered', 'claim', 'bind', 'entered', 'decline')
                   AND outcome IN ('ok', 'refused'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_report_windows ADD CONSTRAINT ck_ffa_report_window
            CHECK ((settled_at IS NULL) = (settled_cls IS NULL)
                   AND (settled_cls IS NULL OR settled_cls IN ('c', 'r', 'l', 'g', 'g1')));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_report_journal ADD CONSTRAINT ck_ffa_report_journal
            CHECK ((cls IS NULL OR cls IN ('c', 'r', 'l', 'g', 'u'))
                   AND state IN ('held', 'settled', 'superseded'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_matches ADD CONSTRAINT ck_ffa_match_fallback_cls
            CHECK (fallback_cls IS NULL OR fallback_cls IN ('r', 'l', 'g', 'g1'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
END $$;

-- The post-check: every object above exists, the defaults are the ones the old
-- writer relies on, and no epoch row is left unlabelled. It raises on any gap,
-- so a partial apply rolls back whole.
DO $$
DECLARE
    missing text[] := ARRAY[]::text[];
    r record;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('ffa_assembly_seats', 'ck_ffa_seat_hold'),
            ('ffa_kept_epochs', 'ck_ffa_epoch_kind'),
            ('ffa_kept_epochs', 'ck_ffa_epoch_chain_v'),
            ('ffa_kept_epochs', 'ck_ffa_epoch_kind_r'),
            ('ffa_seat_readmissions', 'ck_ffa_readmit_refused'),
            ('ffa_seat_readmissions', 'ck_ffa_readmit_gone'),
            ('ffa_readmit_attempts', 'ck_ffa_readmit_attempt'),
            ('ffa_report_windows', 'ck_ffa_report_window'),
            ('ffa_report_journal', 'ck_ffa_report_journal'),
            ('ffa_matches', 'ck_ffa_match_fallback_cls')
        ) AS v(tbl, con)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
             WHERE c.conname = r.con AND c.contype = 'c'
               AND c.conrelid = to_regclass(r.tbl)
        ) THEN
            missing := missing || ('check ' || r.con);
        END IF;
    END LOOP;
    FOR r IN
        SELECT * FROM (VALUES ('ffa_seat_readmissions'), ('ffa_readmit_attempts'),
                              ('ffa_report_windows'), ('ffa_report_journal')) AS v(tbl)
    LOOP
        IF to_regclass(r.tbl) IS NULL THEN
            missing := missing || ('table ' || r.tbl);
        END IF;
    END LOOP;
    FOR r IN
        SELECT * FROM (VALUES
            ('ffa_lobbies', 'readmit_v1'),
            ('ffa_assembly_seats', 'present_at'), ('ffa_assembly_seats', 'hold_n'),
            ('ffa_assembly_seats', 'hold_anchor_at'), ('ffa_assembly_seats', 'hold_until'),
            ('ffa_kept_epochs', 'kind'), ('ffa_kept_epochs', 'game'),
            ('ffa_kept_epochs', 'chain_v'), ('ffa_kept_epochs', 'verifier'),
            ('ffa_matches', 'fallback_cls')
        ) AS v(tbl, col)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns c
             WHERE c.table_schema = current_schema()
               AND c.table_name = r.tbl AND c.column_name = r.col
        ) THEN
            missing := missing || ('column ' || r.tbl || '.' || r.col);
        END IF;
    END LOOP;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns c
         WHERE c.table_schema = current_schema()
           AND c.table_name = 'ffa_lobbies' AND c.column_name = 'readmit_v1'
           AND c.is_nullable = 'NO' AND c.column_default = 'false'
    ) THEN
        missing := missing || 'default ffa_lobbies.readmit_v1'::text;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns c
         WHERE c.table_schema = current_schema()
           AND c.table_name = 'ffa_kept_epochs' AND c.column_name = 'kind'
           AND c.is_nullable = 'NO' AND c.column_default LIKE '''l''%'
    ) THEN
        missing := missing || 'default ffa_kept_epochs.kind'::text;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns c
         WHERE c.table_schema = current_schema()
           AND c.table_name = 'ffa_kept_epochs' AND c.column_name = 'chain_v'
           AND c.is_nullable = 'NO' AND c.column_default = '1'
    ) THEN
        missing := missing || 'default ffa_kept_epochs.chain_v'::text;
    END IF;
    IF EXISTS (SELECT 1 FROM ffa_kept_epochs WHERE kind IS NULL OR chain_v IS NULL) THEN
        missing := missing || 'backfill ffa_kept_epochs'::text;
    END IF;
    IF cardinality(missing) > 0 THEN
        RAISE EXCEPTION '378_ffa_readmission: missing after apply: %', missing;
    END IF;
END $$;

COMMIT;
