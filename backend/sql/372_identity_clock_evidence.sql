-- 372_identity_clock_evidence.sql
--
-- IDENTITY, CLOCK AND CONNECTION EVIDENCE, server half. Additive only: four
-- new tables and three seeded runtime switches. No existing table, column,
-- constraint or row is changed; the match table and the 7-field match HMAC
-- are untouched. Requires 368_seat_evidence.sql (players, the findings table
-- and the release registry this lane reads).
--
--   identity_clock_evidence        one signed record per (stable game key,
--                                  seat), the first one kept; a later
--                                  different record sets one idempotent
--                                  conflict marker on that row. Beside the
--                                  record: what the api saw at that post --
--                                  the clock header's state and (only when its
--                                  process is the record's own) its three
--                                  readings, and the connection CLASS word of
--                                  the api path with the range-list revision
--                                  that produced it. No address column exists.
--   identity_clock_games           the worker's per-game state: the match the
--                                  records attached to, the record set last
--                                  evaluated, the rules revision, the counts
--   game_file_digests              registered public game-file facts; STARTS
--                                  EMPTY
--   identity_clock_seeded_keys     the switch keys THIS file inserted, so the
--                                  rollback removes only those
--
-- What is evaluated, and whether a finding is posted, is decided by the
-- loaded review rules revision, not by any row here. With no revision loaded
-- the worker attaches and pairs records and opens nothing. Findings live in
-- seat_evidence_findings under dedup keys that begin with "identity ".
--
-- The switches say whether a part of the lane runs at all. Seeds use
-- ON CONFLICT DO NOTHING, so a re-run never moves a switch already set.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api. An api deployed first reads
-- the absent switch rows as off: the identity-clock route answers 503
-- identity_clock_evidence_off and the worker pass idles, while the admin
-- identity-clock view and the game-file registration answer 500 until this
-- file lands (no other route is affected).
-- Re-runnable: IF NOT EXISTS throughout; a second run writes no row.

BEGIN;

CREATE TABLE IF NOT EXISTS identity_clock_evidence (
    id                 BIGSERIAL    PRIMARY KEY,
    stable_game_key    VARCHAR(60)  NOT NULL,
    attach_key         VARCHAR(64)  NOT NULL,
    seat_player_id     UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    other_player_id    UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    header_mod_version VARCHAR(16)  NULL,
    consts_version     INTEGER      NOT NULL DEFAULT 0,
    payload            JSONB        NOT NULL,
    payload_sha256     VARCHAR(64)  NOT NULL,
    payload_bytes      INTEGER      NOT NULL DEFAULT 0,
    post_clock         VARCHAR(12)  NOT NULL DEFAULT 'absent',
    post_proc          VARCHAR(12)  NULL,
    post_sw_ms         BIGINT       NULL,
    post_unity_ms      BIGINT       NULL,
    post_photon_ts     INTEGER      NULL,
    conn_class         VARCHAR(8)   NOT NULL DEFAULT 'unknown',
    conn_ranges        VARCHAR(12)  NOT NULL DEFAULT 'absent',
    conflict_at        TIMESTAMPTZ  NULL,
    conflict_kind      VARCHAR(16)  NULL,
    lists_purged_at    TIMESTAMPTZ  NULL,
    received_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT identity_clock_evidence_one_per_seat UNIQUE (stable_game_key, seat_player_id),
    CONSTRAINT identity_clock_evidence_two_seats CHECK (seat_player_id <> other_player_id),
    CONSTRAINT identity_clock_evidence_post_clock
        CHECK (post_clock IN ('ok', 'absent', 'malformed', 'other_proc')),
    -- the three readings exist exactly when the header named the record's process
    CONSTRAINT identity_clock_evidence_clock_cols CHECK (
        (post_clock = 'ok' AND post_proc IS NOT NULL AND post_sw_ms IS NOT NULL
             AND post_unity_ms IS NOT NULL AND post_photon_ts IS NOT NULL)
        OR (post_clock <> 'ok' AND post_proc IS NULL AND post_sw_ms IS NULL
             AND post_unity_ms IS NULL AND post_photon_ts IS NULL)),
    CONSTRAINT identity_clock_evidence_conn_class
        CHECK (conn_class IN ('none', 'lan', 'hosting', 'vpn', 'relay', 'tor', 'unknown'))
);
CREATE INDEX IF NOT EXISTS ix_identity_clock_evidence_attach
    ON identity_clock_evidence (attach_key);
CREATE INDEX IF NOT EXISTS ix_identity_clock_evidence_seat_time
    ON identity_clock_evidence (seat_player_id, received_at);
CREATE INDEX IF NOT EXISTS ix_identity_clock_evidence_proc
    ON identity_clock_evidence (seat_player_id, post_proc, received_at)
    WHERE post_clock = 'ok';

CREATE TABLE IF NOT EXISTS identity_clock_games (
    stable_game_key  VARCHAR(60)  NOT NULL,
    pair_lo          UUID         NOT NULL,
    pair_hi          UUID         NOT NULL,
    match_id         UUID         NULL,
    signature        VARCHAR(400) NULL,
    records_n        SMALLINT     NOT NULL DEFAULT 0,
    paired_points    INTEGER      NOT NULL DEFAULT 0,
    first_seen_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    processed_at     TIMESTAMPTZ  NULL,
    finalized_at     TIMESTAMPTZ  NULL,
    evaluated_rev    VARCHAR(16)  NULL,
    CONSTRAINT identity_clock_games_pk PRIMARY KEY (stable_game_key, pair_lo, pair_hi),
    CONSTRAINT identity_clock_games_order CHECK (pair_lo < pair_hi)
);

CREATE TABLE IF NOT EXISTS game_file_digests (
    file_id        SMALLINT    NOT NULL,
    game_version   VARCHAR(16) NOT NULL,
    sha256         VARCHAR(64) NOT NULL,
    registered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT game_file_digests_pk PRIMARY KEY (file_id, game_version, sha256),
    CONSTRAINT game_file_digests_id CHECK (file_id BETWEEN 0 AND 255)
);

CREATE TABLE IF NOT EXISTS identity_clock_seeded_keys (
    key        VARCHAR(64) PRIMARY KEY,
    seeded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

WITH seeded AS (
    INSERT INTO runtime_settings (key, value) VALUES
        ('identity_clock_evidence_accept', '1'),
        ('identity_clock_evidence_worker', '1'),
        ('identity_clock_evidence_purge', '1')
    ON CONFLICT (key) DO NOTHING
    RETURNING key
)
INSERT INTO identity_clock_seeded_keys (key)
SELECT key FROM seeded
ON CONFLICT (key) DO NOTHING;

COMMIT;
