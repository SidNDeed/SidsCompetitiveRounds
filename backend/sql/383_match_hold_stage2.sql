-- 383: the 2v2 and 1v2 mid-game readmission precursor (Stage 2 design V3,
-- S1, S2, S5 and S6 tables and columns).
--
-- match_games               one row per physical game of a flagged room: the
--                           game id G, minted by the server under the series
--                           lock and chained by the previous G (S1 step 3).
-- match_seat_holds          one row per held seat (S2): the anchor, the
--                           write-once deadline, the claim, bind and entry
--                           stamps and the one terminal closed_at.
-- match_seat_presence       the presence beat of every fighter of a flagged
--                           room (S2): the anchor every hold opens from.
-- match_hold_open_attempts  every hold-open request, refused or not (S2, S6).
-- match_hold_attempts       every offered, claim, bind and entered attempt
--                           of a hold (S6).
-- match_report_windows      the 30 s settle window of one game (S5).
-- match_report_journal      every HMAC-verified game report of a flagged
--                           room, journaled with its server class (S5).
-- team_queue.caps,
-- ovt_queue.caps            the capability tokens a client advertised.
-- team_series, ovt_series   hold_v2 and hold_room: the hold flag, latched
--                           once per room issue (S1 step 2).
-- team_matches.fallback_cls,
-- ovt_matches.fallback_cls  the server class a settled report came from (S5);
--                           the tables submit_team_match and the 1v2 match
--                           route insert into.
--
-- Additive only: every statement is IF NOT EXISTS, so the file re-runs
-- clean. hold_v2 and crossed_at_hold are BOOLEAN NOT NULL DEFAULT FALSE
-- explicitly: a schema default overrides the ORM default, and every series
-- issued before this file (or by old code) must read unflagged.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api, as two SHAs (learning #477).
-- This file ships as a migration-only precursor commit: deploy that SHA, run
-- migrate:383, verify the tables on the primary and the replication of the
-- standby, and only then deploy the code SHA.

BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS match_games (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mode        VARCHAR(8)  NOT NULL,
  series_id   UUID        NOT NULL,
  room_name   VARCHAR(64) NOT NULL,
  seq         INTEGER     NOT NULL,
  prev_game   UUID        REFERENCES match_games(id),
  started_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ck_match_games_mode CHECK (mode IN ('team', 'ovt')),
  CONSTRAINT ck_match_games_seq CHECK (seq >= 1),
  CONSTRAINT uq_match_games_seq UNIQUE (series_id, room_name, seq),
  CONSTRAINT uq_match_games_prev UNIQUE (series_id, room_name, prev_game)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_match_games_first
  ON match_games (series_id, room_name) WHERE prev_game IS NULL;

CREATE TABLE IF NOT EXISTS match_seat_presence (
  room_name        VARCHAR(64) NOT NULL,
  player_id        UUID        NOT NULL REFERENCES players(id),
  mode             VARCHAR(8)  NOT NULL,
  series_id        UUID        NOT NULL,
  actor            INTEGER,
  present_at       TIMESTAMPTZ,
  beat_at          TIMESTAMPTZ NOT NULL,
  seen             JSONB       NOT NULL DEFAULT '[]'::jsonb,
  boundary_digest  VARCHAR(64),
  PRIMARY KEY (room_name, player_id),
  CONSTRAINT ck_match_seat_presence_mode CHECK (mode IN ('team', 'ovt'))
);

CREATE TABLE IF NOT EXISTS match_seat_holds (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mode              VARCHAR(8)  NOT NULL,
  room_name         VARCHAR(64) NOT NULL,
  series_id         UUID        NOT NULL,
  game_id           UUID        NOT NULL REFERENCES match_games(id),
  player_id         UUID        NOT NULL REFERENCES players(id),
  n                 SMALLINT    NOT NULL,
  slot              SMALLINT    NOT NULL,
  team              SMALLINT    NOT NULL,
  opener_player_id  UUID        NOT NULL REFERENCES players(id),
  held_anchor_at    TIMESTAMPTZ NOT NULL,
  held_at           TIMESTAMPTZ NOT NULL,
  held_until        TIMESTAMPTZ NOT NULL,
  seq               INTEGER     NOT NULL DEFAULT 0,
  offered_at        TIMESTAMPTZ,
  claimed_at        TIMESTAMPTZ,
  verifier          CHAR(64),
  bound_at          TIMESTAMPTZ,
  bound_actor       INTEGER,
  bound_region      VARCHAR(8),
  entered_at        TIMESTAMPTZ,
  closed_at         TIMESTAMPTZ,
  closed_reason     VARCHAR(48),
  crossed_at_hold   BOOLEAN     NOT NULL DEFAULT FALSE,
  drop_t1_points    SMALLINT,
  drop_t2_points    SMALLINT,
  CONSTRAINT ck_msh_mode CHECK (mode IN ('team', 'ovt')),
  CONSTRAINT ck_msh_n CHECK (n >= 1),
  CONSTRAINT ck_msh_seat CHECK (team IN (0, 1) AND slot BETWEEN 0 AND 3),
  CONSTRAINT ck_msh_closed CHECK ((closed_at IS NULL) = (closed_reason IS NULL)),
  CONSTRAINT ck_msh_until CHECK (held_until > held_anchor_at),
  CONSTRAINT uq_msh_room_game_player UNIQUE (room_name, game_id, player_id),
  CONSTRAINT uq_msh_room_player_n UNIQUE (room_name, player_id, n)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_msh_one_open_per_room
  ON match_seat_holds (room_name) WHERE closed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_msh_player_open
  ON match_seat_holds (player_id) WHERE closed_at IS NULL;

CREATE TABLE IF NOT EXISTS match_hold_open_attempts (
  request_id        VARCHAR(64) PRIMARY KEY,
  room_name         VARCHAR(64) NOT NULL,
  game_id           UUID,
  held_player_id    UUID REFERENCES players(id),
  opener_player_id  UUID REFERENCES players(id),
  at                TIMESTAMPTZ NOT NULL,
  outcome           VARCHAR(12) NOT NULL,
  reason            VARCHAR(32),
  hold_id           UUID REFERENCES match_seat_holds(id),
  CONSTRAINT ck_mhoa_outcome CHECK (outcome IN ('opened', 'repeat', 'refused')),
  CONSTRAINT ck_mhoa_hold CHECK ((outcome = 'refused') = (hold_id IS NULL))
);

CREATE TABLE IF NOT EXISTS match_hold_attempts (
  hold_id     UUID        NOT NULL REFERENCES match_seat_holds(id),
  attempt_no  INTEGER     NOT NULL,
  kind        VARCHAR(12) NOT NULL,
  at          TIMESTAMPTZ NOT NULL,
  outcome     VARCHAR(12) NOT NULL,
  reason      VARCHAR(48),
  PRIMARY KEY (hold_id, attempt_no),
  CONSTRAINT ck_mha_kind CHECK (kind IN ('offered', 'claim', 'bind', 'entered')),
  CONSTRAINT ck_mha_outcome CHECK (outcome IN ('ok', 'refused')),
  CONSTRAINT ck_mha_reason CHECK ((outcome = 'refused') = (reason IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS match_report_windows (
  room_name            VARCHAR(64) NOT NULL,
  game_id              UUID        NOT NULL REFERENCES match_games(id),
  mode                 VARCHAR(8)  NOT NULL,
  opened_at            TIMESTAMPTZ NOT NULL,
  settle_after         TIMESTAMPTZ NOT NULL,
  settled_at           TIMESTAMPTZ,
  settled_reporter_id  UUID REFERENCES players(id),
  settled_cls          VARCHAR(1),
  superseded_at        TIMESTAMPTZ,
  PRIMARY KEY (room_name, game_id),
  CONSTRAINT ck_mrw_mode CHECK (mode IN ('team', 'ovt')),
  CONSTRAINT ck_mrw_cls CHECK (settled_cls IS NULL OR settled_cls IN ('c', 'r', 'u')),
  CONSTRAINT ck_mrw_settled CHECK ((settled_at IS NULL) = (settled_cls IS NULL))
);

CREATE TABLE IF NOT EXISTS match_report_journal (
  room_name       VARCHAR(64) NOT NULL,
  game_id         UUID        NOT NULL REFERENCES match_games(id),
  reporter_id     UUID        NOT NULL REFERENCES players(id),
  mode            VARCHAR(8)  NOT NULL,
  reporter_steam  VARCHAR(20) NOT NULL,
  cls             VARCHAR(1)  NOT NULL,
  state           VARCHAR(12) NOT NULL DEFAULT 'journaled',
  payload         JSONB       NOT NULL,
  received_at     TIMESTAMPTZ NOT NULL,
  decided_at      TIMESTAMPTZ,
  PRIMARY KEY (room_name, game_id, reporter_id),
  CONSTRAINT ck_mrj_mode CHECK (mode IN ('team', 'ovt')),
  CONSTRAINT ck_mrj_cls CHECK (cls IN ('c', 'r', 'u')),
  CONSTRAINT ck_mrj_state CHECK (state IN ('journaled', 'held', 'settled', 'kept', 'superseded'))
);

ALTER TABLE team_queue   ADD COLUMN IF NOT EXISTS caps      VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE ovt_queue    ADD COLUMN IF NOT EXISTS caps      VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE team_series  ADD COLUMN IF NOT EXISTS hold_v2   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE team_series  ADD COLUMN IF NOT EXISTS hold_room VARCHAR(64);
ALTER TABLE ovt_series   ADD COLUMN IF NOT EXISTS hold_v2   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ovt_series   ADD COLUMN IF NOT EXISTS hold_room VARCHAR(64);
ALTER TABLE team_matches ADD COLUMN IF NOT EXISTS fallback_cls VARCHAR(1)
  CONSTRAINT ck_team_matches_fallback_cls CHECK (fallback_cls IS NULL OR fallback_cls IN ('c', 'r', 'u'));
ALTER TABLE ovt_matches  ADD COLUMN IF NOT EXISTS fallback_cls VARCHAR(1)
  CONSTRAINT ck_ovt_matches_fallback_cls CHECK (fallback_cls IS NULL OR fallback_cls IN ('c', 'r', 'u'));

-- Proof: every new table, unique key, partial index and column is present,
-- and the two flags are NOT NULL with a FALSE default. Any gap raises and
-- rolls the whole file back.
DO $$
DECLARE
    missing text[] := ARRAY[]::text[];
    r record;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('match_games'), ('match_seat_holds'), ('match_seat_presence'),
            ('match_hold_open_attempts'), ('match_hold_attempts'),
            ('match_report_windows'), ('match_report_journal'),
            ('uq_match_games_first'), ('uq_msh_one_open_per_room'),
            ('idx_msh_player_open')
        ) AS v(rel)
    LOOP
        IF to_regclass(r.rel) IS NULL THEN
            missing := missing || ('relation ' || r.rel);
        END IF;
    END LOOP;
    FOR r IN
        SELECT * FROM (VALUES
            ('match_games', 'uq_match_games_seq'), ('match_games', 'uq_match_games_prev'),
            ('match_seat_holds', 'uq_msh_room_game_player'),
            ('match_seat_holds', 'uq_msh_room_player_n'),
            ('match_seat_holds', 'ck_msh_closed'),
            ('team_matches', 'ck_team_matches_fallback_cls'),
            ('ovt_matches', 'ck_ovt_matches_fallback_cls')
        ) AS v(tbl, con)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
             WHERE c.conname = r.con AND c.conrelid = to_regclass(r.tbl)
        ) THEN
            missing := missing || ('constraint ' || r.con);
        END IF;
    END LOOP;
    FOR r IN
        SELECT * FROM (VALUES
            ('team_queue', 'caps'), ('ovt_queue', 'caps'),
            ('team_series', 'hold_v2'), ('team_series', 'hold_room'),
            ('ovt_series', 'hold_v2'), ('ovt_series', 'hold_room'),
            ('team_matches', 'fallback_cls'), ('ovt_matches', 'fallback_cls'),
            ('match_report_windows', 'superseded_at')
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
        SELECT * FROM (VALUES
            ('team_series', 'hold_v2'), ('ovt_series', 'hold_v2'),
            ('match_seat_holds', 'crossed_at_hold')
        ) AS v(tbl, col)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns c
             WHERE c.table_schema = current_schema()
               AND c.table_name = r.tbl AND c.column_name = r.col
               AND c.is_nullable = 'NO' AND c.column_default = 'false'
        ) THEN
            missing := missing || ('default ' || r.tbl || '.' || r.col);
        END IF;
    END LOOP;
    IF cardinality(missing) > 0 THEN
        RAISE EXCEPTION '383_match_hold_stage2: missing after apply: %', missing;
    END IF;
END $$;

COMMIT;
