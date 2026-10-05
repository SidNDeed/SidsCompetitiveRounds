-- 370_card_evidence.sql
--
-- CARD DRAW EVIDENCE, server half. Additive: eight new tables, three seeded
-- runtime switches, and ONE change to an existing table: the findings table
-- 368 created (shared with the seat evidence lane) gains an evidence domain.
-- The match table, match_cards and the 7-field match HMAC are untouched.
-- Requires 368 (findings are stored in seat_evidence_findings).
--
--   seat_evidence_findings.domain
--                           'seat' (every existing row, and every row the
--                           seat lane writes, by the column default) or
--                           'card'; a CHECK keeps it to those two, and a
--                           unique index over (domain, scope, dedup_key,
--                           rule_id) is the card upsert's conflict target.
--                           The seat lane's own unique constraint and
--                           statements are unchanged. A card finding's key
--                           holds a space ('card <game>' / 'card win
--                           <window>'), which no seat finding key can: a
--                           stable game key is printable ASCII without the
--                           space, and the other parts are ids and dates. So
--                           no card key equals a seat key, and the one
--                           UPDATE below can mark only card rows.
--
--   card_evidence           one signed card record per (stable game key, seat),
--                           the first one kept; a later different record sets
--                           one idempotent conflict marker on that row
--   card_pool_registry      registered card-pool censuses, keyed by the full
--                           64-hex digest of the census text; STARTS EMPTY
--   card_games              the worker's per-game state: the attached match,
--                           the series' frozen Same Cards rule, the record set
--                           last evaluated and the rules revision it was
--                           evaluated under
--   card_hand_outside       per hand, the hand and pick measures that read
--                           other than zero, stamped with the revision
--   card_phase_outside      the same per phase
--   card_contrib            per game, recorder, dealer, source and deal
--                           profile: the hands and slots that entered the
--                           rarity expectation and its sums; replaced on every
--                           evaluation of the game
--   card_player_daily       the same summed per dealer, UTC day, source,
--                           coverage, deal profile and revision; recomputed
--                           from card_contrib in the transaction that changes it
--   card_evidence_seeded_keys
--                           the runtime switch keys THIS file inserted (a key
--                           that already existed is not recorded), so the
--                           rollback removes only those
--
-- With no rules revision loaded the worker attaches records and purges, and
-- writes no derived row (card_hand_outside, card_phase_outside, card_contrib,
-- card_player_daily) and no finding.
--
-- DEPLOY ORDER: 368 FIRST, THEN THIS FILE, then the api. An api deployed
-- before this file reads the absent switch rows as off: the card route answers
-- 503 card_evidence_off and the card pass idles, while the admin card read and
-- the census registration answer 500 until this file lands.
-- Re-runnable: IF NOT EXISTS throughout; a second run in a row writes no row
-- (after the rollback it re-marks the posted card findings that one kept).

BEGIN;

CREATE TABLE IF NOT EXISTS card_evidence (
    id                 BIGSERIAL    PRIMARY KEY,
    stable_game_key    VARCHAR(60)  NOT NULL,
    attach_key         VARCHAR(64)  NOT NULL,
    seat_player_id     UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    other_player_id    UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    header_mod_version VARCHAR(16)  NULL,
    pool_digest        VARCHAR(64)  NULL,
    pool_state         VARCHAR(12)  NOT NULL DEFAULT 'not_run',
    deal_profile       VARCHAR(64)  NOT NULL,
    payload            JSONB        NOT NULL,
    payload_sha256     VARCHAR(64)  NOT NULL,
    payload_bytes      INTEGER      NOT NULL DEFAULT 0,
    conflict_at        TIMESTAMPTZ  NULL,
    conflict_kind      VARCHAR(16)  NULL,
    lists_purged_at    TIMESTAMPTZ  NULL,
    received_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT card_evidence_one_per_seat UNIQUE (stable_game_key, seat_player_id),
    CONSTRAINT card_evidence_two_seats CHECK (seat_player_id <> other_player_id)
);
CREATE INDEX IF NOT EXISTS ix_card_evidence_attach ON card_evidence (attach_key);
CREATE INDEX IF NOT EXISTS ix_card_evidence_seat_time ON card_evidence (seat_player_id, received_at);
CREATE INDEX IF NOT EXISTS ix_card_evidence_digest ON card_evidence (pool_digest);

CREATE TABLE IF NOT EXISTS card_pool_registry (
    digest           VARCHAR(64)  PRIMARY KEY,
    census           JSONB        NOT NULL,
    card_count       INTEGER      NOT NULL DEFAULT 0,
    slot_count       SMALLINT     NOT NULL DEFAULT 0,
    game_dll_sha256  VARCHAR(64)  NOT NULL,
    source           VARCHAR(16)  NOT NULL DEFAULT 'admin',
    registered_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS card_games (
    stable_game_key  VARCHAR(60)  NOT NULL,
    pair_lo          UUID         NOT NULL,
    pair_hi          UUID         NOT NULL,
    match_id         UUID         NULL,
    series_sc        VARCHAR(4)   NULL,
    signature        VARCHAR(400) NULL,
    first_seen_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    processed_at     TIMESTAMPTZ  NULL,
    finalized_at     TIMESTAMPTZ  NULL,
    evaluated_rev    VARCHAR(16)  NULL,
    derive_fault     VARCHAR(40)  NULL,
    CONSTRAINT card_games_pk PRIMARY KEY (stable_game_key, pair_lo, pair_hi),
    CONSTRAINT card_games_order CHECK (pair_lo < pair_hi)
);
CREATE INDEX IF NOT EXISTS ix_card_games_match ON card_games (match_id);

CREATE TABLE IF NOT EXISTS card_hand_outside (
    stable_game_key     VARCHAR(60)  NOT NULL,
    pair_lo             UUID         NOT NULL,
    pair_hi             UUID         NOT NULL,
    recorder_player_id  UUID         NOT NULL,
    dealer_player_id    UUID         NULL,
    phase               SMALLINT     NOT NULL,
    deal                SMALLINT     NOT NULL,
    rules_rev           VARCHAR(16)  NOT NULL,
    measures            JSONB        NOT NULL DEFAULT '{}'::jsonb,
    computed_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT card_hand_outside_pk PRIMARY KEY (stable_game_key, pair_lo, pair_hi,
                                                 recorder_player_id, phase, deal)
);

CREATE TABLE IF NOT EXISTS card_phase_outside (
    stable_game_key     VARCHAR(60)  NOT NULL,
    pair_lo             UUID         NOT NULL,
    pair_hi             UUID         NOT NULL,
    recorder_player_id  UUID         NOT NULL,
    phase               SMALLINT     NOT NULL,
    rules_rev           VARCHAR(16)  NOT NULL,
    measures            JSONB        NOT NULL DEFAULT '{}'::jsonb,
    computed_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT card_phase_outside_pk PRIMARY KEY (stable_game_key, pair_lo, pair_hi,
                                                  recorder_player_id, phase)
);

CREATE TABLE IF NOT EXISTS card_contrib (
    stable_game_key     VARCHAR(60)  NOT NULL,
    pair_lo             UUID         NOT NULL,
    pair_hi             UUID         NOT NULL,
    recorder_player_id  UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    subject_player_id   UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    source              VARCHAR(4)   NOT NULL,
    coverage            VARCHAR(8)   NOT NULL,
    deal_profile        VARCHAR(64)  NOT NULL,
    rules_rev           VARCHAR(16)  NOT NULL,
    utc_day             DATE         NOT NULL,
    match_id            UUID         NULL,
    hands               INTEGER      NOT NULL DEFAULT 0,
    slots               INTEGER      NOT NULL DEFAULT 0,
    notrun_hands        INTEGER      NOT NULL DEFAULT 0,
    obs_common          INTEGER      NOT NULL DEFAULT 0,
    obs_uncommon        INTEGER      NOT NULL DEFAULT 0,
    obs_rare            INTEGER      NOT NULL DEFAULT 0,
    exp_common          BIGINT       NOT NULL DEFAULT 0,
    exp_uncommon        BIGINT       NOT NULL DEFAULT 0,
    exp_rare            BIGINT       NOT NULL DEFAULT 0,
    var_common          BIGINT       NOT NULL DEFAULT 0,
    var_uncommon        BIGINT       NOT NULL DEFAULT 0,
    var_rare            BIGINT       NOT NULL DEFAULT 0,
    computed_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT card_contrib_pk PRIMARY KEY (stable_game_key, pair_lo, pair_hi, recorder_player_id,
                                            subject_player_id, source, deal_profile, rules_rev),
    CONSTRAINT card_contrib_source CHECK (source IN ('self', 'meas')),
    CONSTRAINT card_contrib_coverage CHECK (coverage IN ('one', 'paired'))
);
CREATE INDEX IF NOT EXISTS ix_card_contrib_daily
    ON card_contrib (subject_player_id, utc_day, source, coverage, deal_profile, rules_rev);

CREATE TABLE IF NOT EXISTS card_player_daily (
    subject_player_id   UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    day                 DATE         NOT NULL,
    source              VARCHAR(4)   NOT NULL,
    coverage            VARCHAR(8)   NOT NULL,
    deal_profile        VARCHAR(64)  NOT NULL,
    rules_rev           VARCHAR(16)  NOT NULL,
    games               INTEGER      NOT NULL DEFAULT 0,
    hands               INTEGER      NOT NULL DEFAULT 0,
    slots               INTEGER      NOT NULL DEFAULT 0,
    notrun_hands        INTEGER      NOT NULL DEFAULT 0,
    obs_common          INTEGER      NOT NULL DEFAULT 0,
    obs_uncommon        INTEGER      NOT NULL DEFAULT 0,
    obs_rare            INTEGER      NOT NULL DEFAULT 0,
    exp_common          BIGINT       NOT NULL DEFAULT 0,
    exp_uncommon        BIGINT       NOT NULL DEFAULT 0,
    exp_rare            BIGINT       NOT NULL DEFAULT 0,
    var_common          BIGINT       NOT NULL DEFAULT 0,
    var_uncommon        BIGINT       NOT NULL DEFAULT 0,
    var_rare            BIGINT       NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT card_player_daily_pk PRIMARY KEY (subject_player_id, day, source, coverage,
                                                 deal_profile, rules_rev),
    CONSTRAINT card_player_daily_source CHECK (source IN ('self', 'meas')),
    CONSTRAINT card_player_daily_coverage CHECK (coverage IN ('one', 'paired'))
);

CREATE TABLE IF NOT EXISTS card_evidence_seeded_keys (
    key        VARCHAR(64) PRIMARY KEY,
    seeded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE seat_evidence_findings
    ADD COLUMN IF NOT EXISTS domain VARCHAR(8) NOT NULL DEFAULT 'seat';
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'seat_evidence_findings'::regclass
                      AND conname = 'seat_evidence_findings_domain') THEN
        ALTER TABLE seat_evidence_findings
            ADD CONSTRAINT seat_evidence_findings_domain CHECK (domain IN ('seat', 'card'));
    END IF;
END
$$;
CREATE UNIQUE INDEX IF NOT EXISTS ux_seat_evidence_findings_domain
    ON seat_evidence_findings (domain, scope, dedup_key, rule_id);
-- A posted card finding the rollback kept (it keeps its flag) comes back
-- marked 'seat' by the default when this file runs again; it is put back in
-- its own domain. Only keys holding a space: card keys (see above).
UPDATE seat_evidence_findings SET domain = 'card'
 WHERE domain = 'seat' AND dedup_key LIKE 'card %';

WITH seeded AS (
    INSERT INTO runtime_settings (key, value) VALUES
        ('card_evidence_accept', '1'),
        ('card_evidence_worker', '1'),
        ('card_evidence_purge', '1')
    ON CONFLICT (key) DO NOTHING
    RETURNING key
)
INSERT INTO card_evidence_seeded_keys (key)
SELECT key FROM seeded
ON CONFLICT (key) DO NOTHING;

COMMIT;
