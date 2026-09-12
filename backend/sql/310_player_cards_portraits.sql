-- 310: Player Cards portraits, delivery leases and the pull-time dup count.
-- (309 is claim-window's ranked_queue_wait_since on claude/queue-window-sept12;
--  this file was renumbered so the two never collide on the server.)
-- Additive only. Old api code neither reads nor writes any of this, so the
-- file rides a migrations-only precursor SHA and is applied before the code
-- that needs it (learning #477). Explicit transaction: psql -f autocommits
-- statement by statement otherwise (learning #340).
BEGIN;

ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_portrait_source TEXT NOT NULL DEFAULT 'game';
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_game_portrait_hash TEXT NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_game_portrait_descriptor TEXT NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_game_portrait_at TIMESTAMPTZ NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_game_portrait_locked_until TIMESTAMPTZ NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'players_pc_portrait_source_check'
    ) THEN
        ALTER TABLE players
            ADD CONSTRAINT players_pc_portrait_source_check
            CHECK (pc_portrait_source IN ('none', 'game'));
    END IF;
END $$;

-- Canonical portrait bytes, keyed by the SHA-256 of the canonical PNG.
-- A blob is live exactly while some players row references it: the writer,
-- deletion, the admin clear and the 310 repair are the only deleters.
CREATE TABLE IF NOT EXISTS pc_portraits (
    hash          TEXT PRIMARY KEY,
    bytes         BYTEA NOT NULL,
    content_type  TEXT NOT NULL,
    width         INTEGER NOT NULL,
    height        INTEGER NOT NULL,
    stored_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'players_pc_game_portrait_hash_fkey'
    ) THEN
        ALTER TABLE players
            ADD CONSTRAINT players_pc_game_portrait_hash_fkey
            FOREIGN KEY (pc_game_portrait_hash) REFERENCES pc_portraits(hash);
    END IF;
END $$;

-- One delivery lease per portrait-bearing bot send: the picture named by
-- portrait_hash stays authoritative for the subject until `until`, or until
-- a writer that cannot wait (deletion, ban, print discard) deletes the row.
-- event_ids is BIGINT[]: pc_events.id is BIGSERIAL (308).
CREATE TABLE IF NOT EXISTS pc_delivery_leases (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id     UUID NOT NULL REFERENCES players(id),
    print_id       UUID NULL,
    event_ids      BIGINT[] NOT NULL DEFAULT '{}',
    portrait_hash  TEXT NULL,
    until          TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pc_delivery_leases_subject_until_idx
    ON pc_delivery_leases (subject_id, until);
CREATE INDEX IF NOT EXISTS pc_delivery_leases_print_idx
    ON pc_delivery_leases (print_id) WHERE print_id IS NOT NULL;

-- Single-use nonces for the signed portrait writer (replay guard, r18 M1).
CREATE TABLE IF NOT EXISTS pc_portrait_nonces (
    player_id   UUID NOT NULL REFERENCES players(id),
    nonce       TEXT NOT NULL,
    used_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, nonce)
);
CREATE INDEX IF NOT EXISTS pc_portrait_nonces_used_at_idx ON pc_portrait_nonces (used_at);

-- How many copies of the card the puller already held when this event's
-- print was pulled (NULL for events recorded before 310).
ALTER TABLE pc_events ADD COLUMN IF NOT EXISTS dup_at_pull INTEGER NULL;

COMMIT;
