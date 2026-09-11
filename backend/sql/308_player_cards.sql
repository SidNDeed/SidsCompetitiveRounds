-- 308: Player Cards (phase 1) — the collectible cards of ranked players.
--
-- Pool = every non-deleted, non-opted-out, non-banned players row (opt-OUT
-- model). A daily snapshot ranks the pool (pool_rank) and fixes each member's
-- rarity band (Legendary = rank 1, Epic 2-10, Rare 11-20, Uncommon 21-40,
-- Common 41+) plus the stats a print freezes. Packs are five prints rolled
-- from the latest snapshot; every print is its own row and is immutable
-- after insert except its owner (trade, phase 2) and the two discard
-- columns — a trigger enforces that where it cannot be forgotten.
--
-- Deploy order: this file BEFORE the api. The api's janitor takes the first
-- snapshot within a minute of boot when none exists, and every day at 00:05
-- UTC after that; nothing here seeds a snapshot.

BEGIN;

ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_opted_out_at TIMESTAMPTZ NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_collection_public BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_announce BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_settings_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_shards INTEGER NOT NULL DEFAULT 0;

-- Editions: exactly one active row (ended_at IS NULL) at any time.
CREATE TABLE IF NOT EXISTS pc_editions (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS pc_editions_one_active ON pc_editions ((1)) WHERE ended_at IS NULL;
INSERT INTO pc_editions (name) SELECT 'Edition 1' WHERE NOT EXISTS (SELECT 1 FROM pc_editions);

-- Pool snapshots: rolls read MAX(id); the janitor keeps the last 14.
CREATE TABLE IF NOT EXISTS pc_pool_snapshots (
    id            SERIAL PRIMARY KEY,
    taken_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    member_count  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pc_pool_members (
    snapshot_id    INTEGER NOT NULL REFERENCES pc_pool_snapshots(id) ON DELETE CASCADE,
    player_id      UUID NOT NULL,
    pool_rank      INTEGER NOT NULL,
    rarity         TEXT NOT NULL,
    rating         DOUBLE PRECISION NULL,
    peak_rating    DOUBLE PRECISION NULL,
    board_rank     INTEGER NULL,
    series_wins    INTEGER NOT NULL DEFAULT 0,
    series_losses  INTEGER NOT NULL DEFAULT 0,
    top_card       TEXT NULL,
    title          TEXT NULL,
    PRIMARY KEY (snapshot_id, player_id)
);
CREATE INDEX IF NOT EXISTS pc_pool_members_rarity ON pc_pool_members (snapshot_id, rarity, pool_rank);

-- One card per (subject, edition, variant); created lazily on the first print.
CREATE TABLE IF NOT EXISTS pc_cards (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_player_id   UUID NOT NULL REFERENCES players(id),
    edition_id          INTEGER NOT NULL REFERENCES pc_editions(id),
    variant             TEXT NOT NULL DEFAULT 'base',
    first_minted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (subject_player_id, edition_id, variant)
);

-- Packs: the idempotency claim for every open (purchase nonce, or the
-- unopened pack row itself) and the durable result.
CREATE TABLE IF NOT EXISTS pc_packs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id      UUID NOT NULL REFERENCES players(id),
    source         TEXT NOT NULL,                 -- bought | daily | earned
    mode           TEXT NULL,                     -- earned: 1v1 | team | ovt | ffa
    kind           TEXT NULL,                     -- earned: win | sweep
    nonce          TEXT NULL,                     -- bought: the client's purchase nonce
    reference_id   TEXT NULL,                     -- daily: claimed_on; earned: series / match id
    status         TEXT NOT NULL,                 -- pending | done | rejected | unopened | opening | voided
    pay            TEXT NULL,                     -- bought: gold | shards
    price          INTEGER NULL,
    snapshot_id    INTEGER NULL,
    result         JSONB NULL,
    reject_reason  TEXT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    opened_at      TIMESTAMPTZ NULL,
    voided_at      TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS pc_packs_player_nonce ON pc_packs (player_id, nonce) WHERE nonce IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS pc_packs_player_source_ref ON pc_packs (player_id, source, reference_id) WHERE reference_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS pc_packs_player_status ON pc_packs (player_id, status);
CREATE INDEX IF NOT EXISTS pc_packs_paid_day ON pc_packs (player_id, opened_at) WHERE source = 'bought' AND status = 'done';
-- The earned-pack void predicates (a reversal, a retro-invalidation, the
-- reconciler's sweep) probe by reference: a partial index on exactly the
-- rows they can touch.
CREATE INDEX IF NOT EXISTS pc_packs_earned_unopened_ref ON pc_packs (reference_id) WHERE source = 'earned' AND status = 'unopened';

-- The last open attempt of an unopened pack (a pre-debit rejection returns
-- the pack to 'unopened' and records why here).
CREATE TABLE IF NOT EXISTS pc_open_attempts (
    pack_id        UUID PRIMARY KEY REFERENCES pc_packs(id) ON DELETE CASCADE,
    attempted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    reject_reason  TEXT NULL
);

-- Prints: the binder. Immutable after insert except owner_player_id and the
-- two discard columns (trigger below).
CREATE TABLE IF NOT EXISTS pc_prints (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    card_id          UUID NOT NULL REFERENCES pc_cards(id),
    owner_player_id  UUID NOT NULL REFERENCES players(id),
    minted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    snapshot_id      INTEGER NOT NULL,
    rarity           TEXT NOT NULL,
    foil             BOOLEAN NOT NULL DEFAULT false,
    signed           BOOLEAN NOT NULL DEFAULT false,
    pool_rank        INTEGER NOT NULL,
    rating           DOUBLE PRECISION NULL,
    peak_rating      DOUBLE PRECISION NULL,
    board_rank       INTEGER NULL,
    series_wins      INTEGER NULL,
    series_losses    INTEGER NULL,
    top_card         TEXT NULL,
    title            TEXT NULL,
    source           TEXT NOT NULL,
    pack_id          UUID NULL REFERENCES pc_packs(id),
    slot             SMALLINT NULL,
    discarded_at     TIMESTAMPTZ NULL,
    discard_shards   INTEGER NULL
);
CREATE INDEX IF NOT EXISTS pc_prints_owner_live ON pc_prints (owner_player_id) WHERE discarded_at IS NULL;
CREATE INDEX IF NOT EXISTS pc_prints_card ON pc_prints (card_id);
CREATE INDEX IF NOT EXISTS pc_prints_pack ON pc_prints (pack_id);

CREATE OR REPLACE FUNCTION pc_prints_immutable() RETURNS trigger AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.card_id IS DISTINCT FROM OLD.card_id
       OR NEW.minted_at IS DISTINCT FROM OLD.minted_at
       OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
       OR NEW.rarity IS DISTINCT FROM OLD.rarity
       OR NEW.foil IS DISTINCT FROM OLD.foil
       OR NEW.signed IS DISTINCT FROM OLD.signed
       OR NEW.pool_rank IS DISTINCT FROM OLD.pool_rank
       OR NEW.rating IS DISTINCT FROM OLD.rating
       OR NEW.peak_rating IS DISTINCT FROM OLD.peak_rating
       OR NEW.board_rank IS DISTINCT FROM OLD.board_rank
       OR NEW.series_wins IS DISTINCT FROM OLD.series_wins
       OR NEW.series_losses IS DISTINCT FROM OLD.series_losses
       OR NEW.top_card IS DISTINCT FROM OLD.top_card
       OR NEW.title IS DISTINCT FROM OLD.title
       OR NEW.source IS DISTINCT FROM OLD.source
       OR NEW.pack_id IS DISTINCT FROM OLD.pack_id
       OR NEW.slot IS DISTINCT FROM OLD.slot THEN
        RAISE EXCEPTION 'pc_prints is immutable except owner_player_id, discarded_at and discard_shards';
    END IF;
    IF OLD.discarded_at IS NOT NULL
       AND (NEW.discarded_at IS DISTINCT FROM OLD.discarded_at
            OR NEW.discard_shards IS DISTINCT FROM OLD.discard_shards
            OR NEW.owner_player_id IS DISTINCT FROM OLD.owner_player_id) THEN
        RAISE EXCEPTION 'a discarded print cannot change';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS pc_prints_immutable ON pc_prints;
CREATE TRIGGER pc_prints_immutable BEFORE UPDATE ON pc_prints
    FOR EACH ROW EXECUTE FUNCTION pc_prints_immutable();

-- Daily pack: one claim per player per UTC day; the day comes from the DB clock.
CREATE TABLE IF NOT EXISTS pc_daily_claims (
    player_id   UUID NOT NULL REFERENCES players(id),
    claimed_on  DATE NOT NULL,
    pack_id     UUID NULL REFERENCES pc_packs(id),
    PRIMARY KEY (player_id, claimed_on)
);

-- Notable pulls for the Discord drain (which re-checks consent, pc_announce
-- and deleted_at for BOTH the puller and the subject before posting).
CREATE TABLE IF NOT EXISTS pc_events (
    id                  BIGSERIAL PRIMARY KEY,
    kind                TEXT NOT NULL,             -- legendary | epic | signed | foil | self
    player_id           UUID NOT NULL REFERENCES players(id),
    subject_player_id   UUID NOT NULL REFERENCES players(id),
    print_id            UUID NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_at           TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS pc_events_unposted ON pc_events (created_at) WHERE posted_at IS NULL;

-- Earned-pack reconciler: a high-water mark per source, and the instant the
-- feature started (nothing completed before it is ever back-filled).
CREATE TABLE IF NOT EXISTS pc_reconcile_cursors (
    source      TEXT PRIMARY KEY,
    cursor_at   TIMESTAMPTZ NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
