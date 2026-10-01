-- 355: the FFA ready-up connect-failure record and grant columns
-- (connect-failure design V11, instruments I2 and I3, the verdict's grant
-- and short-start columns, the wager flag, and the G3 enrolment table).
--
-- ffa_assembly_seats   one row per locked seat of a lobby (I2): what the
--                      server offered, what the client said, what other
--                      seats observed, and the verdict the server reached.
--                      Written only by the eight I2 writers in main.py.
-- ffa_g3_seats         the G3 enrolment (admission before production);
--                      the production-enabling release drops it.
-- ffa_kept_epochs      the kept epoch, one immutable row per late
--                      admission, insert-only.
-- ffa_lobbies          18 columns: the re-form links, the two capability
--                      flags taken at the lock, the wager flag, the grant
--                      and short-start stamps, the deciding rule, the
--                      closers' record (I3) and the region projection (I5).
-- ffa_queue.caps       the capability tokens a client advertised at enrol.
--
-- Additive only: every statement is IF NOT EXISTS or a constraint added
-- inside a block that catches duplicate_object, so the file re-runs clean.
-- The three flags are BOOLEAN NOT NULL DEFAULT FALSE explicitly: a schema
-- default overrides the ORM's, and every lobby locked before this file (or
-- by old code) must read ungated and bettable exactly as before.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api, as two SHAs (learning #477).
-- The api built from the NEXT commit writes ffa_assembly_seats on every FFA
-- Start, poll and leave, and the new ffa_lobbies columns in every FFA
-- closer, so an api that goes first fails every FFA Start. This file ships
-- as a migration-only precursor commit: deploy that SHA, run migrate:355,
-- verify the tables on the primary and the standby's replication, and only
-- then deploy the code SHA.

BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS ffa_assembly_seats (
  lobby_id         UUID NOT NULL REFERENCES ffa_lobbies(id) ON DELETE CASCADE,
  player_id        UUID NOT NULL REFERENCES players(id),
  slot             SMALLINT NOT NULL,
  locked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  lock_offered_at  TIMESTAMPTZ,
  lock_seen_at     TIMESTAMPTZ,
  countdown_at     TIMESTAMPTZ,
  countdown_abort  VARCHAR(16),
  attempt          SMALLINT NOT NULL DEFAULT 0,
  attempt_phase    VARCHAR(8),
  first_attempt_at TIMESTAMPTZ,
  attempt_at       TIMESTAMPTZ,
  admitted_at      TIMESTAMPTZ,
  arrived_at       TIMESTAMPTZ,
  arrived_region   VARCHAR(8),
  wrong_region     VARCHAR(8),
  wrong_region_n   SMALLINT NOT NULL DEFAULT 0,
  arrived_count    SMALLINT,
  actor_claim      SMALLINT,
  claim_region     VARCHAR(8),
  actor_nr         SMALLINT,
  actor_region     VARCHAR(8),
  uid_missing      BOOLEAN NOT NULL DEFAULT FALSE,
  failed_at        TIMESTAMPTZ,
  failed_step      VARCHAR(16),
  failed_code      INTEGER,
  failed_state     VARCHAR(24),
  fail_count       SMALLINT NOT NULL DEFAULT 0,
  spawn_failed_at  TIMESTAMPTZ,
  spawn_ok_at      TIMESTAMPTZ,
  body_seen_at     TIMESTAMPTZ,
  bodiless_at      TIMESTAMPTZ,
  left_at          TIMESTAMPTZ,
  left_cause       VARCHAR(16),
  left_label       VARCHAR(16),
  left_path        VARCHAR(12),
  start_req_at     TIMESTAMPTZ,
  start_ok_at      TIMESTAMPTZ,
  started_at       TIMESTAMPTZ,
  start_roster     BOOLEAN NOT NULL DEFAULT FALSE,
  late_admitted_at TIMESTAMPTZ,
  late_game        SMALLINT,
  late_entered_at  TIMESTAMPTZ,
  late_game_claim  SMALLINT,
  entered_game     SMALLINT,
  late_body_game   SMALLINT,
  late_body_at     TIMESTAMPTZ,
  census_slots     SMALLINT[],
  census_actors    SMALLINT[],
  census_nobody    SMALLINT[],
  census_unkept    SMALLINT[],
  census_game      SMALLINT,
  census_anon      SMALLINT NOT NULL DEFAULT 0,
  census_region    VARCHAR(8),
  census_at        TIMESTAMPTZ,
  census_seen_at   TIMESTAMPTZ,
  epoch_seen       SMALLINT,
  client_ms        INTEGER,
  writes           SMALLINT NOT NULL DEFAULT 0,
  verdict          VARCHAR(16),
  verdict_at       TIMESTAMPTZ,
  dec_at           TIMESTAMPTZ,
  dec_census       SMALLINT[],
  dec_census_at    TIMESTAMPTZ,
  notice_seen_at   TIMESTAMPTZ,
  gone_game        SMALLINT,
  gone_path        VARCHAR(8),
  lag_games        SMALLINT[] NOT NULL DEFAULT '{}',
  released_at      TIMESTAMPTZ,
  release_why      VARCHAR(16),
  PRIMARY KEY (lobby_id, player_id),
  CONSTRAINT ck_ffa_seat_late_body CHECK (late_body_game IS NULL OR (late_game IS NOT NULL AND late_body_game >= late_game)),
  CONSTRAINT ck_ffa_seat_gone CHECK ((gone_game IS NULL) = (gone_path IS NULL) AND (gone_path IS NULL OR gone_path IN ('leave', 'witness'))),
  CONSTRAINT ck_ffa_seat_release CHECK ((released_at IS NULL) = (release_why IS NULL) AND (release_why IS NULL OR release_why IN ('fence_expired', 'join_timeout')))
);
CREATE INDEX IF NOT EXISTS ffa_assembly_seats_player_verdict
  ON ffa_assembly_seats (player_id, verdict_at) WHERE verdict IS NOT NULL;

CREATE TABLE IF NOT EXISTS ffa_g3_seats (
  player_id  UUID PRIMARY KEY REFERENCES players(id),
  added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS ffa_kept_epochs (
  lobby_id   UUID NOT NULL REFERENCES ffa_lobbies(id) ON DELETE CASCADE,
  epoch_no   SMALLINT NOT NULL CHECK (epoch_no >= 1),
  slot       SMALLINT NOT NULL,
  actor_nr   SMALLINT NOT NULL,
  chain      CHAR(16) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (lobby_id, epoch_no)
);

ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS reformed_from       UUID;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS reformed_to         UUID;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS assembly_v1         BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS admission_v1        BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS bets_disabled       BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS start_granted_at    TIMESTAMPTZ;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS short_started_at    TIMESTAMPTZ;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS asm_rule            VARCHAR(4);
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS dissolve_path       VARCHAR(32);
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS dissolve_trigger    VARCHAR(16);
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS first_leaver        UUID;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS first_leave_label   VARCHAR(16);
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS dissolve_after_ms   INTEGER;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS present_at_dissolve SMALLINT[];
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS absent_at_dissolve  SMALLINT[];
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS arrived_at_dissolve SMALLINT[];
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS region_why          VARCHAR(16);
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS region_detail       JSONB;
ALTER TABLE ffa_queue   ADD COLUMN IF NOT EXISTS caps                VARCHAR(64) NOT NULL DEFAULT '';

-- ADD CONSTRAINT has no IF NOT EXISTS: each is added inside its own block
-- that catches duplicate_object (the pattern of 176_ffa_lobby_config.sql).
DO $$
BEGIN
    BEGIN
        ALTER TABLE ffa_lobbies ADD CONSTRAINT ck_ffa_lobby_reform_no_bets
            CHECK (reformed_from IS NULL OR bets_disabled);
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_lobbies ADD CONSTRAINT ck_ffa_lobby_short_no_bets
            CHECK (short_started_at IS NULL OR bets_disabled);
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_lobbies ADD CONSTRAINT ck_ffa_lobby_region_why
            CHECK (region_why IS NULL OR region_why IN
                   ('baseline', 'majority', 'bounded', 'quorum', 'error', 'other'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_assembly_seats ADD CONSTRAINT ck_ffa_seat_verdict
            CHECK (verdict IS NULL OR verdict IN
                   ('granted', 'admissible', 'admitted_late', 'carried',
                    'excluded', 'dissolved', 'left'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
END $$;

-- Proof: every CHECK, the index, both new tables and every new column are
-- present, and the three flags are NOT NULL with a FALSE default. Any gap
-- raises and rolls the whole file back.
DO $$
DECLARE
    missing text[] := ARRAY[]::text[];
    r record;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('ffa_assembly_seats', 'ck_ffa_seat_late_body'),
            ('ffa_assembly_seats', 'ck_ffa_seat_gone'),
            ('ffa_assembly_seats', 'ck_ffa_seat_release'),
            ('ffa_assembly_seats', 'ck_ffa_seat_verdict'),
            ('ffa_lobbies', 'ck_ffa_lobby_reform_no_bets'),
            ('ffa_lobbies', 'ck_ffa_lobby_short_no_bets'),
            ('ffa_lobbies', 'ck_ffa_lobby_region_why')
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
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
         WHERE c.contype = 'c' AND c.conrelid = to_regclass('ffa_kept_epochs')
           AND pg_get_constraintdef(c.oid) LIKE '%epoch_no >= 1%'
    ) THEN
        missing := missing || 'check ffa_kept_epochs.epoch_no'::text;
    END IF;
    IF to_regclass('ffa_assembly_seats_player_verdict') IS NULL THEN
        missing := missing || 'index ffa_assembly_seats_player_verdict'::text;
    END IF;
    IF to_regclass('ffa_g3_seats') IS NULL THEN
        missing := missing || 'table ffa_g3_seats'::text;
    END IF;
    IF to_regclass('ffa_kept_epochs') IS NULL THEN
        missing := missing || 'table ffa_kept_epochs'::text;
    END IF;
    FOR r IN
        SELECT * FROM (VALUES
            ('ffa_lobbies', 'reformed_from'), ('ffa_lobbies', 'reformed_to'),
            ('ffa_lobbies', 'assembly_v1'), ('ffa_lobbies', 'admission_v1'),
            ('ffa_lobbies', 'bets_disabled'), ('ffa_lobbies', 'start_granted_at'),
            ('ffa_lobbies', 'short_started_at'), ('ffa_lobbies', 'asm_rule'),
            ('ffa_lobbies', 'dissolve_path'), ('ffa_lobbies', 'dissolve_trigger'),
            ('ffa_lobbies', 'first_leaver'), ('ffa_lobbies', 'first_leave_label'),
            ('ffa_lobbies', 'dissolve_after_ms'), ('ffa_lobbies', 'present_at_dissolve'),
            ('ffa_lobbies', 'absent_at_dissolve'), ('ffa_lobbies', 'arrived_at_dissolve'),
            ('ffa_lobbies', 'region_why'), ('ffa_lobbies', 'region_detail'),
            ('ffa_queue', 'caps')
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
    FOR r IN
        SELECT * FROM (VALUES ('assembly_v1'), ('admission_v1'), ('bets_disabled')) AS v(col)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns c
             WHERE c.table_schema = current_schema()
               AND c.table_name = 'ffa_lobbies' AND c.column_name = r.col
               AND c.is_nullable = 'NO' AND c.column_default = 'false'
        ) THEN
            missing := missing || ('default ffa_lobbies.' || r.col);
        END IF;
    END LOOP;
    IF cardinality(missing) > 0 THEN
        RAISE EXCEPTION '355_ffa_assembly: missing after apply: %', missing;
    END IF;
END $$;

COMMIT;
