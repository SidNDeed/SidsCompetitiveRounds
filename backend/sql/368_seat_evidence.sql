-- 368_seat_evidence.sql
--
-- SEAT EVIDENCE, server half (contract V2), and the state of the review
-- rules worker. Additive only: seven new tables and three seeded runtime
-- switches. No existing table, column, constraint or row is changed; the
-- match table and the 7-field match HMAC are untouched.
--
--   seat_evidence           one signed record per (stable game key, seat), the
--                           first one kept; a later different record sets one
--                           idempotent conflict marker on that row
--   seat_evidence_games     the worker's per-game state: which match the records
--                           attached to, the record set last evaluated, and the
--                           rules revision it was last evaluated under
--   seat_evidence_findings  review findings, one row per normalized
--                           (scope, key, rule id), stamped with the revision
--                           that produced them
--   mod_release_digests     the registered release tuples; STARTS EMPTY
--   client_compat_events    a seat's other-plug-in check outcome, one row per
--                           account per UTC hour
--   review_sitting_dirty    (pair, UTC day) sittings waiting for evaluation
--   review_cursor           the worker's position in the match rows it folds
--                           into review_sitting_dirty
--
-- What is evaluated, and whether a finding is posted, is decided by the
-- loaded review rules revision, not by any row here. With no revision loaded
-- the worker attaches records and purges, and opens nothing.
--
-- The switches say whether a part of the lane runs at all. Seeds use
-- ON CONFLICT DO NOTHING, so a re-run never moves a switch already set.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api. An api deployed first reads the
-- absent switch rows as off: the seat-evidence route answers 503
-- seat_evidence_off and the worker idles, while the admin seat-evidence view,
-- the digest registration and the compat-outcome route answer 500 until this
-- file lands (no other route is affected).
-- Re-runnable: IF NOT EXISTS throughout; a second run writes no row.

BEGIN;

CREATE TABLE IF NOT EXISTS seat_evidence (
    id                 BIGSERIAL    PRIMARY KEY,
    stable_game_key    VARCHAR(60)  NOT NULL,
    attach_key         VARCHAR(64)  NOT NULL,
    seat_player_id     UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    other_player_id    UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    header_mod_version VARCHAR(16)  NULL,
    build_version      VARCHAR(16)  NULL,
    build_variant      VARCHAR(16)  NULL,
    build_commit       VARCHAR(12)  NULL,
    dll_sha256         VARCHAR(64)  NULL,
    dll_hash_state     VARCHAR(12)  NOT NULL DEFAULT 'absent',
    compat_outcome     VARCHAR(8)   NOT NULL DEFAULT 'absent',
    payload            JSONB        NOT NULL,
    payload_sha256     VARCHAR(64)  NOT NULL,
    payload_bytes      INTEGER      NOT NULL DEFAULT 0,
    conflict_at        TIMESTAMPTZ  NULL,
    conflict_kind      VARCHAR(16)  NULL,
    lists_purged_at    TIMESTAMPTZ  NULL,
    received_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT seat_evidence_one_per_seat UNIQUE (stable_game_key, seat_player_id),
    CONSTRAINT seat_evidence_two_seats CHECK (seat_player_id <> other_player_id)
);
CREATE INDEX IF NOT EXISTS ix_seat_evidence_attach ON seat_evidence (attach_key);
CREATE INDEX IF NOT EXISTS ix_seat_evidence_seat_time ON seat_evidence (seat_player_id, received_at);

CREATE TABLE IF NOT EXISTS seat_evidence_games (
    stable_game_key  VARCHAR(60)  NOT NULL,
    pair_lo          UUID         NOT NULL,
    pair_hi          UUID         NOT NULL,
    match_id         UUID         NULL,
    signature        VARCHAR(200) NULL,
    first_seen_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    processed_at     TIMESTAMPTZ  NULL,
    finalized_at     TIMESTAMPTZ  NULL,
    evaluated_rev    VARCHAR(16)  NULL,
    CONSTRAINT seat_evidence_games_pk PRIMARY KEY (stable_game_key, pair_lo, pair_hi),
    CONSTRAINT seat_evidence_games_order CHECK (pair_lo < pair_hi)
);

CREATE TABLE IF NOT EXISTS seat_evidence_findings (
    id           BIGSERIAL    PRIMARY KEY,
    scope        VARCHAR(8)   NOT NULL DEFAULT 'game',
    dedup_key    VARCHAR(160) NOT NULL,
    rule_id      VARCHAR(16)  NOT NULL,
    rules_rev    VARCHAR(16)  NOT NULL,
    match_id     UUID         NULL,
    details      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    computed_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    changed_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    flag_id      UUID         NULL,
    CONSTRAINT seat_evidence_findings_once UNIQUE (scope, dedup_key, rule_id),
    CONSTRAINT seat_evidence_findings_scope CHECK (scope IN ('game', 'sitting'))
);

CREATE TABLE IF NOT EXISTS mod_release_digests (
    version        VARCHAR(16) NOT NULL,
    variant        VARCHAR(16) NOT NULL DEFAULT 'STANDALONE',
    commit_sha     VARCHAR(12) NOT NULL DEFAULT '',
    dll_sha256     VARCHAR(64) NOT NULL,
    source         VARCHAR(16) NOT NULL DEFAULT 'release',
    registered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mod_release_digests_pk PRIMARY KEY (version, variant, commit_sha, dll_sha256)
);

CREATE TABLE IF NOT EXISTS client_compat_events (
    id                 BIGSERIAL    PRIMARY KEY,
    player_id          UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    outcome            VARCHAR(8)   NOT NULL DEFAULT 'not_run',
    other_plugin_count SMALLINT     NOT NULL DEFAULT 0,
    other_plugins      TEXT         NULL,
    mod_version        VARCHAR(16)  NULL,
    hour_bucket        TIMESTAMPTZ  NOT NULL,
    received_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT client_compat_events_hourly UNIQUE (player_id, hour_bucket),
    CONSTRAINT client_compat_events_outcome CHECK (outcome IN ('finding', 'not_run'))
);

CREATE TABLE IF NOT EXISTS review_sitting_dirty (
    pair_lo    UUID        NOT NULL,
    pair_hi    UUID        NOT NULL,
    day        DATE        NOT NULL,
    marked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT review_sitting_dirty_pk PRIMARY KEY (pair_lo, pair_hi, day)
);
CREATE INDEX IF NOT EXISTS ix_review_sitting_dirty_marked ON review_sitting_dirty (marked_at);

CREATE TABLE IF NOT EXISTS review_cursor (
    name         VARCHAR(16) PRIMARY KEY,
    position_at  TIMESTAMPTZ NULL,
    position_id  UUID        NULL,
    rules_rev    VARCHAR(16) NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO runtime_settings (key, value) VALUES
    ('seat_evidence_accept', '1'),
    ('seat_evidence_worker', '1'),
    ('seat_evidence_purge', '1')
ON CONFLICT (key) DO NOTHING;

COMMIT;
