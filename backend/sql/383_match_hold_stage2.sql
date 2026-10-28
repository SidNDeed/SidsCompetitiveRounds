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
ALTER TABLE team_matches ADD COLUMN IF NOT EXISTS fallback_cls VARCHAR(1);
ALTER TABLE ovt_matches  ADD COLUMN IF NOT EXISTS fallback_cls VARCHAR(1);
-- The CHECKs ride guarded statements of their own (378's form): an inline
-- column constraint is skipped together with its column when the column
-- already exists (a re-run, or a schema whose ORM step added the column
-- first, as backend/tests/test_pc_trades.py's harness does), and the proof
-- below then finds the constraint missing.
DO $$
BEGIN
    BEGIN
        ALTER TABLE team_matches ADD CONSTRAINT ck_team_matches_fallback_cls
            CHECK (fallback_cls IS NULL OR fallback_cls IN ('c', 'r', 'u'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ovt_matches ADD CONSTRAINT ck_ovt_matches_fallback_cls
            CHECK (fallback_cls IS NULL OR fallback_cls IN ('c', 'r', 'u'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
END $$;

-- Proof: every relation this file creates has its intended kind, and every
-- column, constraint and explicit index this file owns has its complete
-- catalog shape. Guarded DDL never repairs a same-named malformed object, so
-- any mismatch raises and rolls the whole file back.
DO $proof$
DECLARE
    missing text[] := ARRAY[]::text[];
    r record;
BEGIN
    FOR r IN
        WITH expected(rel, kind, persistence) AS (VALUES
            ('match_games', 'r', 'p'),
            ('match_seat_presence', 'r', 'p'),
            ('match_seat_holds', 'r', 'p'),
            ('match_hold_open_attempts', 'r', 'p'),
            ('match_hold_attempts', 'r', 'p'),
            ('match_report_windows', 'r', 'p'),
            ('match_report_journal', 'r', 'p'),
            ('uq_match_games_first', 'i', 'p'),
            ('uq_msh_one_open_per_room', 'i', 'p'),
            ('idx_msh_player_open', 'i', 'p')
        ),
        actual AS (
            SELECT c.relname::text AS rel, c.relkind::text AS kind,
                   c.relpersistence::text AS persistence
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = current_schema()
               AND EXISTS (SELECT 1 FROM expected e WHERE e.rel = c.relname)
        )
        SELECT e.rel
          FROM expected e LEFT JOIN actual a USING (rel)
         WHERE a.rel IS NULL OR a.kind IS DISTINCT FROM e.kind
            OR a.persistence IS DISTINCT FROM e.persistence
    LOOP
        missing := missing || ('relation ' || r.rel);
    END LOOP;

    FOR r IN
        WITH expected(tbl, ord, col, typ, not_null, def) AS (VALUES
            ('match_games', 1, 'id', 'uuid', true, 'gen_random_uuid()'),
            ('match_games', 2, 'mode', 'character varying(8)', true, ''),
            ('match_games', 3, 'series_id', 'uuid', true, ''),
            ('match_games', 4, 'room_name', 'character varying(64)', true, ''),
            ('match_games', 5, 'seq', 'integer', true, ''),
            ('match_games', 6, 'prev_game', 'uuid', false, ''),
            ('match_games', 7, 'started_at', 'timestamp with time zone', true,
             'clock_timestamp()'),
            ('match_seat_presence', 1, 'room_name', 'character varying(64)', true, ''),
            ('match_seat_presence', 2, 'player_id', 'uuid', true, ''),
            ('match_seat_presence', 3, 'mode', 'character varying(8)', true, ''),
            ('match_seat_presence', 4, 'series_id', 'uuid', true, ''),
            ('match_seat_presence', 5, 'actor', 'integer', false, ''),
            ('match_seat_presence', 6, 'present_at', 'timestamp with time zone', false, ''),
            ('match_seat_presence', 7, 'beat_at', 'timestamp with time zone', true, ''),
            ('match_seat_presence', 8, 'seen', 'jsonb', true, $d$'[]'::jsonb$d$),
            ('match_seat_presence', 9, 'boundary_digest', 'character varying(64)', false, ''),
            ('match_seat_holds', 1, 'id', 'uuid', true, 'gen_random_uuid()'),
            ('match_seat_holds', 2, 'mode', 'character varying(8)', true, ''),
            ('match_seat_holds', 3, 'room_name', 'character varying(64)', true, ''),
            ('match_seat_holds', 4, 'series_id', 'uuid', true, ''),
            ('match_seat_holds', 5, 'game_id', 'uuid', true, ''),
            ('match_seat_holds', 6, 'player_id', 'uuid', true, ''),
            ('match_seat_holds', 7, 'n', 'smallint', true, ''),
            ('match_seat_holds', 8, 'slot', 'smallint', true, ''),
            ('match_seat_holds', 9, 'team', 'smallint', true, ''),
            ('match_seat_holds', 10, 'opener_player_id', 'uuid', true, ''),
            ('match_seat_holds', 11, 'held_anchor_at', 'timestamp with time zone', true, ''),
            ('match_seat_holds', 12, 'held_at', 'timestamp with time zone', true, ''),
            ('match_seat_holds', 13, 'held_until', 'timestamp with time zone', true, ''),
            ('match_seat_holds', 14, 'seq', 'integer', true, '0'),
            ('match_seat_holds', 15, 'offered_at', 'timestamp with time zone', false, ''),
            ('match_seat_holds', 16, 'claimed_at', 'timestamp with time zone', false, ''),
            ('match_seat_holds', 17, 'verifier', 'character(64)', false, ''),
            ('match_seat_holds', 18, 'bound_at', 'timestamp with time zone', false, ''),
            ('match_seat_holds', 19, 'bound_actor', 'integer', false, ''),
            ('match_seat_holds', 20, 'bound_region', 'character varying(8)', false, ''),
            ('match_seat_holds', 21, 'entered_at', 'timestamp with time zone', false, ''),
            ('match_seat_holds', 22, 'closed_at', 'timestamp with time zone', false, ''),
            ('match_seat_holds', 23, 'closed_reason', 'character varying(48)', false, ''),
            ('match_seat_holds', 24, 'crossed_at_hold', 'boolean', true, 'false'),
            ('match_seat_holds', 25, 'drop_t1_points', 'smallint', false, ''),
            ('match_seat_holds', 26, 'drop_t2_points', 'smallint', false, ''),
            ('match_hold_open_attempts', 1, 'request_id', 'character varying(64)', true, ''),
            ('match_hold_open_attempts', 2, 'room_name', 'character varying(64)', true, ''),
            ('match_hold_open_attempts', 3, 'game_id', 'uuid', false, ''),
            ('match_hold_open_attempts', 4, 'held_player_id', 'uuid', false, ''),
            ('match_hold_open_attempts', 5, 'opener_player_id', 'uuid', false, ''),
            ('match_hold_open_attempts', 6, 'at', 'timestamp with time zone', true, ''),
            ('match_hold_open_attempts', 7, 'outcome', 'character varying(12)', true, ''),
            ('match_hold_open_attempts', 8, 'reason', 'character varying(32)', false, ''),
            ('match_hold_open_attempts', 9, 'hold_id', 'uuid', false, ''),
            ('match_hold_attempts', 1, 'hold_id', 'uuid', true, ''),
            ('match_hold_attempts', 2, 'attempt_no', 'integer', true, ''),
            ('match_hold_attempts', 3, 'kind', 'character varying(12)', true, ''),
            ('match_hold_attempts', 4, 'at', 'timestamp with time zone', true, ''),
            ('match_hold_attempts', 5, 'outcome', 'character varying(12)', true, ''),
            ('match_hold_attempts', 6, 'reason', 'character varying(48)', false, ''),
            ('match_report_windows', 1, 'room_name', 'character varying(64)', true, ''),
            ('match_report_windows', 2, 'game_id', 'uuid', true, ''),
            ('match_report_windows', 3, 'mode', 'character varying(8)', true, ''),
            ('match_report_windows', 4, 'opened_at', 'timestamp with time zone', true, ''),
            ('match_report_windows', 5, 'settle_after', 'timestamp with time zone', true, ''),
            ('match_report_windows', 6, 'settled_at', 'timestamp with time zone', false, ''),
            ('match_report_windows', 7, 'settled_reporter_id', 'uuid', false, ''),
            ('match_report_windows', 8, 'settled_cls', 'character varying(1)', false, ''),
            ('match_report_windows', 9, 'superseded_at', 'timestamp with time zone', false, ''),
            ('match_report_journal', 1, 'room_name', 'character varying(64)', true, ''),
            ('match_report_journal', 2, 'game_id', 'uuid', true, ''),
            ('match_report_journal', 3, 'reporter_id', 'uuid', true, ''),
            ('match_report_journal', 4, 'mode', 'character varying(8)', true, ''),
            ('match_report_journal', 5, 'reporter_steam', 'character varying(20)', true, ''),
            ('match_report_journal', 6, 'cls', 'character varying(1)', true, ''),
            ('match_report_journal', 7, 'state', 'character varying(12)', true,
             $d$'journaled'::charactervarying$d$),
            ('match_report_journal', 8, 'payload', 'jsonb', true, ''),
            ('match_report_journal', 9, 'received_at', 'timestamp with time zone', true, ''),
            ('match_report_journal', 10, 'decided_at', 'timestamp with time zone', false, ''),
            ('team_queue', NULL, 'caps', 'character varying(64)', true,
             $d$''::charactervarying$d$),
            ('ovt_queue', NULL, 'caps', 'character varying(64)', true,
             $d$''::charactervarying$d$),
            ('team_series', NULL, 'hold_v2', 'boolean', true, 'false'),
            ('team_series', NULL, 'hold_room', 'character varying(64)', false, ''),
            ('ovt_series', NULL, 'hold_v2', 'boolean', true, 'false'),
            ('ovt_series', NULL, 'hold_room', 'character varying(64)', false, ''),
            ('team_matches', NULL, 'fallback_cls', 'character varying(1)', false, ''),
            ('ovt_matches', NULL, 'fallback_cls', 'character varying(1)', false, '')
        ),
        actual AS (
            SELECT c.relname::text AS tbl, a.attnum::integer AS ord,
                   a.attname::text AS col, format_type(a.atttypid, a.atttypmod) AS typ,
                   a.attnotnull AS not_null,
                   /* M3 normalize def */
                   (SELECT coalesce(string_agg(
                       CASE WHEN token[1] ~ '^[[:space:]]$' THEN ''
                            ELSE token[1] END, '' ORDER BY ord), '')
                      FROM regexp_matches(coalesce(pg_get_expr(d.adbin, d.adrelid, false), ''),
                           $norm$([eE]'(?:[^'\\]|\\.|'')*'|'(?:[^']|'')*'|"(?:[^"]|"")*"|.)$norm$, 'gs')
                           WITH ORDINALITY AS part(token, ord)) AS def
              FROM pg_attribute a
              JOIN pg_class c ON c.oid = a.attrelid
              JOIN pg_namespace n ON n.oid = c.relnamespace
              LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
             WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p')
               AND a.attnum > 0 AND NOT a.attisdropped
               AND EXISTS (SELECT 1 FROM expected e
                            WHERE e.tbl = c.relname AND e.col = a.attname)
        )
        SELECT e.tbl, e.col
          FROM expected e LEFT JOIN actual a USING (tbl, col)
         WHERE a.col IS NULL
            OR (e.ord IS NOT NULL AND a.ord IS DISTINCT FROM e.ord)
            OR a.typ IS DISTINCT FROM e.typ
            OR a.not_null IS DISTINCT FROM e.not_null
            OR a.def IS DISTINCT FROM e.def
    LOOP
        missing := missing || ('column ' || r.tbl || '.' || r.col);
    END LOOP;

    FOR r IN
        WITH expected(tbl, con, kind, keys, ref_tbl, ref_keys, definition, validated) AS (VALUES
            ('match_games', 'match_games_pkey', 'p', ARRAY['id'], NULL, NULL,
             $c$PRIMARYKEY(id)$c$, true),
            ('match_games', 'match_games_prev_game_fkey', 'f', ARRAY['prev_game'],
             'match_games', ARRAY['id'],
             $c$FOREIGNKEY(prev_game)REFERENCESmatch_games(id)$c$, true),
            ('match_games', 'ck_match_games_mode', 'c', NULL, NULL, NULL,
             $c$CHECK(((mode)::text=ANY((ARRAY['team'::charactervarying,'ovt'::charactervarying])::text[])))$c$, true),
            ('match_games', 'ck_match_games_seq', 'c', NULL, NULL, NULL,
             $c$CHECK((seq>=1))$c$, true),
            ('match_games', 'uq_match_games_seq', 'u',
             ARRAY['series_id', 'room_name', 'seq'], NULL, NULL,
             $c$UNIQUE(series_id,room_name,seq)$c$, true),
            ('match_games', 'uq_match_games_prev', 'u',
             ARRAY['series_id', 'room_name', 'prev_game'], NULL, NULL,
             $c$UNIQUE(series_id,room_name,prev_game)$c$, true),
            ('match_seat_presence', 'match_seat_presence_pkey', 'p',
             ARRAY['room_name', 'player_id'], NULL, NULL,
             $c$PRIMARYKEY(room_name,player_id)$c$, true),
            ('match_seat_presence', 'match_seat_presence_player_id_fkey', 'f',
             ARRAY['player_id'], 'players', ARRAY['id'],
             $c$FOREIGNKEY(player_id)REFERENCESplayers(id)$c$, true),
            ('match_seat_presence', 'ck_match_seat_presence_mode', 'c', NULL, NULL, NULL,
             $c$CHECK(((mode)::text=ANY((ARRAY['team'::charactervarying,'ovt'::charactervarying])::text[])))$c$, true),
            ('match_seat_holds', 'match_seat_holds_pkey', 'p', ARRAY['id'], NULL, NULL,
             $c$PRIMARYKEY(id)$c$, true),
            ('match_seat_holds', 'match_seat_holds_game_id_fkey', 'f', ARRAY['game_id'],
             'match_games', ARRAY['id'],
             $c$FOREIGNKEY(game_id)REFERENCESmatch_games(id)$c$, true),
            ('match_seat_holds', 'match_seat_holds_player_id_fkey', 'f',
             ARRAY['player_id'], 'players', ARRAY['id'],
             $c$FOREIGNKEY(player_id)REFERENCESplayers(id)$c$, true),
            ('match_seat_holds', 'match_seat_holds_opener_player_id_fkey', 'f',
             ARRAY['opener_player_id'], 'players', ARRAY['id'],
             $c$FOREIGNKEY(opener_player_id)REFERENCESplayers(id)$c$, true),
            ('match_seat_holds', 'ck_msh_mode', 'c', NULL, NULL, NULL,
             $c$CHECK(((mode)::text=ANY((ARRAY['team'::charactervarying,'ovt'::charactervarying])::text[])))$c$, true),
            ('match_seat_holds', 'ck_msh_n', 'c', NULL, NULL, NULL,
             $c$CHECK((n>=1))$c$, true),
            ('match_seat_holds', 'ck_msh_seat', 'c', NULL, NULL, NULL,
             $c$CHECK(((team=ANY(ARRAY[0,1]))AND((slot>=0)AND(slot<=3))))$c$, true),
            ('match_seat_holds', 'ck_msh_closed', 'c', NULL, NULL, NULL,
             $c$CHECK(((closed_atISNULL)=(closed_reasonISNULL)))$c$, true),
            ('match_seat_holds', 'ck_msh_until', 'c', NULL, NULL, NULL,
             $c$CHECK((held_until>held_anchor_at))$c$, true),
            ('match_seat_holds', 'uq_msh_room_game_player', 'u',
             ARRAY['room_name', 'game_id', 'player_id'], NULL, NULL,
             $c$UNIQUE(room_name,game_id,player_id)$c$, true),
            ('match_seat_holds', 'uq_msh_room_player_n', 'u',
             ARRAY['room_name', 'player_id', 'n'], NULL, NULL,
             $c$UNIQUE(room_name,player_id,n)$c$, true),
            ('match_hold_open_attempts', 'match_hold_open_attempts_pkey', 'p',
             ARRAY['request_id'], NULL, NULL, $c$PRIMARYKEY(request_id)$c$, true),
            ('match_hold_open_attempts', 'match_hold_open_attempts_held_player_id_fkey', 'f',
             ARRAY['held_player_id'], 'players', ARRAY['id'],
             $c$FOREIGNKEY(held_player_id)REFERENCESplayers(id)$c$, true),
            ('match_hold_open_attempts', 'match_hold_open_attempts_opener_player_id_fkey', 'f',
             ARRAY['opener_player_id'], 'players', ARRAY['id'],
             $c$FOREIGNKEY(opener_player_id)REFERENCESplayers(id)$c$, true),
            ('match_hold_open_attempts', 'match_hold_open_attempts_hold_id_fkey', 'f',
             ARRAY['hold_id'], 'match_seat_holds', ARRAY['id'],
             $c$FOREIGNKEY(hold_id)REFERENCESmatch_seat_holds(id)$c$, true),
            ('match_hold_open_attempts', 'ck_mhoa_outcome', 'c', NULL, NULL, NULL,
             $c$CHECK(((outcome)::text=ANY((ARRAY['opened'::charactervarying,'repeat'::charactervarying,'refused'::charactervarying])::text[])))$c$, true),
            ('match_hold_open_attempts', 'ck_mhoa_hold', 'c', NULL, NULL, NULL,
             $c$CHECK((((outcome)::text='refused'::text)=(hold_idISNULL)))$c$, true),
            ('match_hold_attempts', 'match_hold_attempts_pkey', 'p',
             ARRAY['hold_id', 'attempt_no'], NULL, NULL,
             $c$PRIMARYKEY(hold_id,attempt_no)$c$, true),
            ('match_hold_attempts', 'match_hold_attempts_hold_id_fkey', 'f',
             ARRAY['hold_id'], 'match_seat_holds', ARRAY['id'],
             $c$FOREIGNKEY(hold_id)REFERENCESmatch_seat_holds(id)$c$, true),
            ('match_hold_attempts', 'ck_mha_kind', 'c', NULL, NULL, NULL,
             $c$CHECK(((kind)::text=ANY((ARRAY['offered'::charactervarying,'claim'::charactervarying,'bind'::charactervarying,'entered'::charactervarying])::text[])))$c$, true),
            ('match_hold_attempts', 'ck_mha_outcome', 'c', NULL, NULL, NULL,
             $c$CHECK(((outcome)::text=ANY((ARRAY['ok'::charactervarying,'refused'::charactervarying])::text[])))$c$, true),
            ('match_hold_attempts', 'ck_mha_reason', 'c', NULL, NULL, NULL,
             $c$CHECK((((outcome)::text='refused'::text)=(reasonISNOTNULL)))$c$, true),
            ('match_report_windows', 'match_report_windows_pkey', 'p',
             ARRAY['room_name', 'game_id'], NULL, NULL,
             $c$PRIMARYKEY(room_name,game_id)$c$, true),
            ('match_report_windows', 'match_report_windows_game_id_fkey', 'f',
             ARRAY['game_id'], 'match_games', ARRAY['id'],
             $c$FOREIGNKEY(game_id)REFERENCESmatch_games(id)$c$, true),
            ('match_report_windows', 'match_report_windows_settled_reporter_id_fkey', 'f',
             ARRAY['settled_reporter_id'], 'players', ARRAY['id'],
             $c$FOREIGNKEY(settled_reporter_id)REFERENCESplayers(id)$c$, true),
            ('match_report_windows', 'ck_mrw_mode', 'c', NULL, NULL, NULL,
             $c$CHECK(((mode)::text=ANY((ARRAY['team'::charactervarying,'ovt'::charactervarying])::text[])))$c$, true),
            ('match_report_windows', 'ck_mrw_cls', 'c', NULL, NULL, NULL,
             $c$CHECK(((settled_clsISNULL)OR((settled_cls)::text=ANY((ARRAY['c'::charactervarying,'r'::charactervarying,'u'::charactervarying])::text[]))))$c$, true),
            ('match_report_windows', 'ck_mrw_settled', 'c', NULL, NULL, NULL,
             $c$CHECK(((settled_atISNULL)=(settled_clsISNULL)))$c$, true),
            ('match_report_journal', 'match_report_journal_pkey', 'p',
             ARRAY['room_name', 'game_id', 'reporter_id'], NULL, NULL,
             $c$PRIMARYKEY(room_name,game_id,reporter_id)$c$, true),
            ('match_report_journal', 'match_report_journal_game_id_fkey', 'f',
             ARRAY['game_id'], 'match_games', ARRAY['id'],
             $c$FOREIGNKEY(game_id)REFERENCESmatch_games(id)$c$, true),
            ('match_report_journal', 'match_report_journal_reporter_id_fkey', 'f',
             ARRAY['reporter_id'], 'players', ARRAY['id'],
             $c$FOREIGNKEY(reporter_id)REFERENCESplayers(id)$c$, true),
            ('match_report_journal', 'ck_mrj_mode', 'c', NULL, NULL, NULL,
             $c$CHECK(((mode)::text=ANY((ARRAY['team'::charactervarying,'ovt'::charactervarying])::text[])))$c$, true),
            ('match_report_journal', 'ck_mrj_cls', 'c', NULL, NULL, NULL,
             $c$CHECK(((cls)::text=ANY((ARRAY['c'::charactervarying,'r'::charactervarying,'u'::charactervarying])::text[])))$c$, true),
            ('match_report_journal', 'ck_mrj_state', 'c', NULL, NULL, NULL,
             $c$CHECK(((state)::text=ANY((ARRAY['journaled'::charactervarying,'held'::charactervarying,'settled'::charactervarying,'kept'::charactervarying,'superseded'::charactervarying])::text[])))$c$, true),
            ('team_matches', 'ck_team_matches_fallback_cls', 'c', NULL, NULL, NULL,
             $c$CHECK(((fallback_clsISNULL)OR((fallback_cls)::text=ANY((ARRAY['c'::charactervarying,'r'::charactervarying,'u'::charactervarying])::text[]))))$c$, true),
            ('ovt_matches', 'ck_ovt_matches_fallback_cls', 'c', NULL, NULL, NULL,
             $c$CHECK(((fallback_clsISNULL)OR((fallback_cls)::text=ANY((ARRAY['c'::charactervarying,'r'::charactervarying,'u'::charactervarying])::text[]))))$c$, true)
        ),
        actual AS (
            SELECT tc.relname::text AS tbl, c.conname::text AS con,
                   c.contype::text AS kind,
                   CASE WHEN c.contype IN ('p', 'u', 'f') THEN
                       ARRAY(SELECT a.attname::text
                               FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
                               JOIN pg_attribute a
                                 ON a.attrelid = c.conrelid AND a.attnum = k.attnum
                              ORDER BY k.ord)
                   END AS keys,
                   CASE WHEN c.contype = 'f' THEN rc.relname::text END AS ref_tbl,
                   CASE WHEN c.contype = 'f' THEN
                       ARRAY(SELECT a.attname::text
                               FROM unnest(c.confkey) WITH ORDINALITY k(attnum, ord)
                               JOIN pg_attribute a
                                 ON a.attrelid = c.confrelid AND a.attnum = k.attnum
                              ORDER BY k.ord)
                   END AS ref_keys,
                   /* M3 normalize definition */
                   (SELECT coalesce(string_agg(
                       CASE WHEN token[1] ~ '^[[:space:]]$' THEN ''
                            ELSE token[1] END, '' ORDER BY ord), '')
                      FROM regexp_matches(pg_get_constraintdef(c.oid, false),
                           $norm$([eE]'(?:[^'\\]|\\.|'')*'|'(?:[^']|'')*'|"(?:[^"]|"")*"|.)$norm$, 'gs')
                           WITH ORDINALITY AS part(token, ord)) AS definition,
                   c.convalidated AS validated, c.condeferrable, c.condeferred
              FROM pg_constraint c
              JOIN pg_class tc ON tc.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = tc.relnamespace
              LEFT JOIN pg_class rc ON rc.oid = c.confrelid
             WHERE n.nspname = current_schema()
               AND EXISTS (SELECT 1 FROM expected e
                            WHERE e.tbl = tc.relname AND e.con = c.conname)
        )
        SELECT e.tbl, e.con
          FROM expected e LEFT JOIN actual a USING (tbl, con)
         WHERE a.con IS NULL
            OR a.kind IS DISTINCT FROM e.kind
            OR a.keys IS DISTINCT FROM e.keys
            OR a.ref_tbl IS DISTINCT FROM e.ref_tbl
            OR a.ref_keys IS DISTINCT FROM e.ref_keys
            OR a.definition IS DISTINCT FROM e.definition
            OR a.validated IS DISTINCT FROM e.validated
            OR a.condeferrable IS DISTINCT FROM false
            OR a.condeferred IS DISTINCT FROM false
    LOOP
        missing := missing || ('constraint ' || r.tbl || '.' || r.con);
    END LOOP;

    FOR r IN
        WITH expected(idx, tbl, method, keys, key_defs, is_unique, predicate) AS (VALUES
            ('uq_match_games_first', 'match_games', 'btree',
             ARRAY['series_id', 'room_name'], ARRAY['series_id', 'room_name'], true,
             '(prev_gameISNULL)'),
            ('uq_msh_one_open_per_room', 'match_seat_holds', 'btree',
             ARRAY['room_name'], ARRAY['room_name'], true, '(closed_atISNULL)'),
            ('idx_msh_player_open', 'match_seat_holds', 'btree',
             ARRAY['player_id'], ARRAY['player_id'], false, '(closed_atISNULL)')
        ),
        actual AS (
            SELECT ic.relname::text AS idx, tc.relname::text AS tbl,
                   am.amname::text AS method,
                   ARRAY(SELECT a.attname::text
                           FROM unnest(i.indkey) WITH ORDINALITY k(attnum, ord)
                           JOIN pg_attribute a
                             ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                          WHERE k.ord <= i.indnkeyatts ORDER BY k.ord) AS keys,
                   ARRAY(SELECT pg_get_indexdef(i.indexrelid, k, false)
                           FROM generate_series(1, i.indnkeyatts::integer) k
                          ORDER BY k) AS key_defs,
                   i.indisunique AS is_unique,
                   /* M3 normalize predicate */
                   (SELECT coalesce(string_agg(
                       CASE WHEN token[1] ~ '^[[:space:]]$' THEN ''
                            ELSE token[1] END, '' ORDER BY ord), '')
                      FROM regexp_matches(coalesce(pg_get_expr(i.indpred, i.indrelid, false), ''),
                           $norm$([eE]'(?:[^'\\]|\\.|'')*'|'(?:[^']|'')*'|"(?:[^"]|"")*"|.)$norm$, 'gs')
                           WITH ORDINALITY AS part(token, ord)) AS predicate,
                   (i.indnatts = i.indnkeyatts) AS no_includes,
                   (i.indexprs IS NULL) AS no_expressions,
                   i.indisprimary, i.indisexclusion, i.indnullsnotdistinct,
                   i.indisvalid, i.indisready, i.indislive
              FROM pg_index i
              JOIN pg_class ic ON ic.oid = i.indexrelid
              JOIN pg_namespace n ON n.oid = ic.relnamespace
              JOIN pg_class tc ON tc.oid = i.indrelid
              JOIN pg_am am ON am.oid = ic.relam
             WHERE n.nspname = current_schema()
               AND EXISTS (SELECT 1 FROM expected e WHERE e.idx = ic.relname)
        )
        SELECT e.idx
          FROM expected e LEFT JOIN actual a USING (idx)
         WHERE a.idx IS NULL
            OR a.tbl IS DISTINCT FROM e.tbl
            OR a.method IS DISTINCT FROM e.method
            OR a.keys IS DISTINCT FROM e.keys
            OR a.key_defs IS DISTINCT FROM e.key_defs
            OR a.is_unique IS DISTINCT FROM e.is_unique
            OR a.predicate IS DISTINCT FROM e.predicate
            OR a.no_includes IS DISTINCT FROM true
            OR a.no_expressions IS DISTINCT FROM true
            OR a.indisprimary IS DISTINCT FROM false
            OR a.indisexclusion IS DISTINCT FROM false
            OR a.indnullsnotdistinct IS DISTINCT FROM false
            OR a.indisvalid IS DISTINCT FROM true
            OR a.indisready IS DISTINCT FROM true
            OR a.indislive IS DISTINCT FROM true
    LOOP
        missing := missing || ('index ' || r.idx);
    END LOOP;

    IF cardinality(missing) > 0 THEN
        RAISE EXCEPTION '383_match_hold_stage2: shape mismatch after apply: %', missing;
    END IF;
END $proof$;

COMMIT;
