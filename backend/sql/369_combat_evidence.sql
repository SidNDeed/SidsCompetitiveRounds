-- 369_combat_evidence.sql
--
-- COMBAT EVIDENCE, server half (combat contract one). Additive but for one
-- CHECK: five new tables (the lane's four and the switch-seed ledger), three
-- seeded runtime switches, and the seat_evidence_findings domain CHECK that
-- migration 370 added gains the value 'combat'. No other existing table,
-- column, constraint or row is changed; the match table, ratings, rewards
-- and the 7-field match HMAC are untouched.
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
--                        rebuild faults, the revision last evaluated under,
--                        and how many records that evaluation saw (a later
--                        record makes a finalized game a candidate again)
--   combat_contrib       per-game contributions, one row per (game, pair,
--                        subject, source), carrying the contributing record's
--                        measurement version; the subject is a player row and
--                        its contributions go with it
--   combat_player_daily  daily rows rolled from the contributions, one per
--                        (subject, UTC day, source, coverage, measurement
--                        version): versions are never added together; the
--                        subject is a player row and its rows go with it
--   combat_evidence_seeded_keys
--                        the runtime switch keys THIS file inserted (a key
--                        that already existed is not recorded), so the
--                        rollback removes only those
--
-- Findings reuse seat_evidence_findings (scope 'game') under the combat
-- namespace: every combat dedup key starts with 'combat ' (with a space). A
-- seat evidence dedup key is its stable key (printable ASCII without the
-- space, the only writer's check) and two pair ids, so no seat key can equal
-- or start with it. Since 370 the table also carries a domain column ('seat' |
-- 'card'); this file admits 'combat' in that CHECK and every combat row names
-- the combat domain. Every seat and card row is unchanged.
--
-- What is evaluated, and whether a finding is posted, is decided by the
-- loaded review rules revision, not by any row here. With no revision loaded
-- the worker attaches records and purges, and derives nothing.
--
-- The switches say whether a part of the lane runs at all. Seeds use
-- ON CONFLICT DO NOTHING, so a re-run never moves a switch already set; the
-- keys this file's own insert created are recorded in
-- combat_evidence_seeded_keys, so the rollback removes only those.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api. An api deployed first reads the
-- absent switch rows as off: the combat evidence route answers 503
-- combat_evidence_off and the combat pass idles, while the admin combat
-- evidence read answers 500 until this file lands (no other route is affected).
-- Re-runnable: IF NOT EXISTS throughout; a second run writes no row.

BEGIN;
-- Every lock this file takes is waited for at most 5 s, as 370 and 372 do.
SET LOCAL lock_timeout = '5s';

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
    records_n        INTEGER      NOT NULL DEFAULT 0,
    CONSTRAINT combat_games_pk PRIMARY KEY (stable_game_key, pair_lo, pair_hi),
    CONSTRAINT combat_games_order CHECK (pair_lo < pair_hi),
    CONSTRAINT combat_games_coverage CHECK (coverage IN ('one', 'paired'))
);
CREATE INDEX IF NOT EXISTS ix_combat_games_match ON combat_games (match_id);

CREATE TABLE IF NOT EXISTS combat_contrib (
    stable_game_key    VARCHAR(60)  NOT NULL,
    pair_lo            UUID         NOT NULL,
    pair_hi            UUID         NOT NULL,
    subject_player_id  UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
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
    subject_player_id  UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS combat_evidence_seeded_keys (
    key        VARCHAR(64) PRIMARY KEY,
    seeded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The findings domain (migration 370: 'seat' | 'card') gains 'combat'. The
-- constraint is replaced by name; the unique index over the domain column is
-- untouched. Re-runnable: a second run drops and adds the same constraint.
ALTER TABLE seat_evidence_findings DROP CONSTRAINT IF EXISTS seat_evidence_findings_domain;
ALTER TABLE seat_evidence_findings
    ADD CONSTRAINT seat_evidence_findings_domain CHECK (domain IN ('seat', 'card', 'combat'));

WITH seeded AS (
    INSERT INTO runtime_settings (key, value) VALUES
        ('combat_evidence_accept', '1'),
        ('combat_evidence_worker', '1'),
        ('combat_evidence_purge', '1')
    ON CONFLICT (key) DO NOTHING
    RETURNING key
)
INSERT INTO combat_evidence_seeded_keys (key)
SELECT key FROM seeded
ON CONFLICT (key) DO NOTHING;

COMMIT;
