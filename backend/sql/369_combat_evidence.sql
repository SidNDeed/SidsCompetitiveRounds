-- 369_combat_evidence.sql
--
-- COMBAT EVIDENCE, server half (combat contract one). Additive only: four new
-- tables and three seeded runtime switches. No existing table, column,
-- constraint or row is changed; the match table, ratings, rewards and the
-- 7-field match HMAC are untouched.
--
--   combat_evidence      one signed combat record per (stable game key, seat),
--                        stored before anything is derived: its JSON value and
--                        the SHA-256 and length of the exact signed bytes;
--                        the first one is kept and a later different record
--                        sets one idempotent conflict marker on that row
--   combat_games         the worker's per-game state, keyed by stable game key
--                        AND canonical unordered seat pair: the attached match
--                        and the exact attach key it attached by, the
--                        readiness signature last derived, the coverage, the
--                        rebuild faults, the revision last evaluated under
--   combat_contrib       per-game contributions, one row per (game, pair,
--                        subject, source), carrying the contributing record's
--                        measurement version
--   combat_player_daily  daily rows rolled from the contributions, one per
--                        (subject, UTC day, source, coverage, measurement
--                        version): versions are never added together
--
-- Findings reuse seat_evidence_findings (scope 'game', dedup key prefixed
-- 'combat|'), so its CHECK constraint is unchanged.
--
-- What is evaluated, and whether a finding is posted, is decided by the
-- loaded review rules revision, not by any row here. With no revision loaded
-- the worker attaches records and purges, and derives nothing.
--
-- The switches say whether a part of the lane runs at all. Seeds use
-- ON CONFLICT DO NOTHING, so a re-run never moves a switch already set.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api. An api deployed first reads the
-- absent switch rows as off: the combat evidence route answers 503
-- combat_evidence_off and the combat pass idles, while the admin combat
-- evidence read answers 500 until this file lands (no other route is affected).
-- Re-runnable: IF NOT EXISTS throughout; a second run writes no row.

BEGIN;

CREATE TABLE IF NOT EXISTS combat_evidence (
    id                 BIGSERIAL    PRIMARY KEY,
    stable_game_key    VARCHAR(60)  NOT NULL,
    attach_key         VARCHAR(64)  NOT NULL,
    seat_player_id     UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    other_player_id    UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    header_mod_version VARCHAR(16)  NULL,
    consts_version     SMALLINT     NOT NULL DEFAULT 0,
    payload            JSONB        NOT NULL,
    payload_sha256     VARCHAR(64)  NOT NULL,
    payload_bytes      INTEGER      NOT NULL DEFAULT 0,
    conflict_at        TIMESTAMPTZ  NULL,
    conflict_kind      VARCHAR(16)  NULL,
    lists_purged_at    TIMESTAMPTZ  NULL,
    received_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT combat_evidence_one_per_seat UNIQUE (stable_game_key, seat_player_id),
    CONSTRAINT combat_evidence_two_seats CHECK (seat_player_id <> other_player_id)
);
CREATE INDEX IF NOT EXISTS ix_combat_evidence_attach ON combat_evidence (attach_key);
CREATE INDEX IF NOT EXISTS ix_combat_evidence_seat_time ON combat_evidence (seat_player_id, received_at);

CREATE TABLE IF NOT EXISTS combat_games (
    stable_game_key  VARCHAR(60)  NOT NULL,
    pair_lo          UUID         NOT NULL,
    pair_hi          UUID         NOT NULL,
    match_id         UUID         NULL,
    attach_key       VARCHAR(64)  NULL,
    readiness_sig    TEXT         NULL,
    coverage         VARCHAR(8)   NOT NULL DEFAULT 'one',
    record_faults    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    processed_at     TIMESTAMPTZ  NULL,
    finalized_at     TIMESTAMPTZ  NULL,
    evaluated_rev    VARCHAR(16)  NULL,
    CONSTRAINT combat_games_pk PRIMARY KEY (stable_game_key, pair_lo, pair_hi),
    CONSTRAINT combat_games_order CHECK (pair_lo < pair_hi),
    CONSTRAINT combat_games_coverage CHECK (coverage IN ('one', 'paired'))
);
CREATE INDEX IF NOT EXISTS ix_combat_games_match ON combat_games (match_id);

CREATE TABLE IF NOT EXISTS combat_contrib (
    stable_game_key    VARCHAR(60)  NOT NULL,
    pair_lo            UUID         NOT NULL,
    pair_hi            UUID         NOT NULL,
    subject_player_id  UUID         NOT NULL,
    source             VARCHAR(8)   NOT NULL DEFAULT 'self',
    coverage           VARCHAR(8)   NOT NULL DEFAULT 'one',
    consts_version     SMALLINT     NOT NULL DEFAULT 0,
    utc_day            DATE         NOT NULL,
    sums               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    computed_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT combat_contrib_pk PRIMARY KEY (stable_game_key, pair_lo, pair_hi,
                                              subject_player_id, source),
    CONSTRAINT combat_contrib_source CHECK (source IN ('self', 'meas')),
    CONSTRAINT combat_contrib_coverage CHECK (coverage IN ('one', 'paired'))
);
CREATE INDEX IF NOT EXISTS ix_combat_contrib_subject_day ON combat_contrib (subject_player_id, utc_day);

CREATE TABLE IF NOT EXISTS combat_player_daily (
    subject_player_id  UUID         NOT NULL,
    utc_day            DATE         NOT NULL,
    source             VARCHAR(8)   NOT NULL DEFAULT 'self',
    coverage           VARCHAR(8)   NOT NULL DEFAULT 'one',
    consts_version     SMALLINT     NOT NULL DEFAULT 0,
    games              INTEGER      NOT NULL DEFAULT 0,
    sums               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    rolled_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT combat_player_daily_pk PRIMARY KEY (subject_player_id, utc_day, source,
                                                   coverage, consts_version)
);

INSERT INTO runtime_settings (key, value) VALUES
    ('combat_evidence_accept', '1'),
    ('combat_evidence_worker', '1'),
    ('combat_evidence_purge', '1')
ON CONFLICT (key) DO NOTHING;

COMMIT;
