-- 361: pc_shard_batches -- the idempotency record of the batch shard route
-- (board row 25, whole-pack quick shard): POST /api/v1/pc/prints/discard-batch.
--
-- The route discards up to player_cards.PC_DISCARD_BATCH_CAP prints of the
-- caller's in ONE transaction and credits their shards as ONE delta. Its
-- body carries an idempotency key: the pack id when the player shards a
-- pack from its result, a client nonce when they shard a selection from the
-- binder. One row per (player, key) the route has COMMITTED, written in the
-- same transaction as the discards and the credit, so a row exists exactly
-- when that transaction committed:
--   player_id      the caller.
--   batch_key      the key as the body sent it. The CHECK refuses an empty
--                  or oddly shaped key, so a key can never become NULL and
--                  silently stop deduplicating (#147).
--   print_ids      the discarded print ids, lowercased, sorted and joined
--                  with commas: a replay of the same key must name the same
--                  SET of prints, whatever order it lists them in.
--   prints         how many prints the batch discarded (1..40).
--   shards_gained  the shards the batch credited, which a replay answers
--                  again without crediting anything.
--   created_at     when the batch committed. Nothing prunes by it: the rows
--                  are kept (below). Its index lost its only reader (the
--                  retention that pruned by age) and stays unused.
-- A replay of the same key with the same set answers the stored row and
-- credits nothing; the same key with a different set is refused (409
-- key_reused), however old the key is.
--
-- THE ROWS ARE KEPT. No retention deletes them (asks-b round 2): a key
-- whose row was pruned would read as never used, and the same key with
-- another list of prints would then discard and credit that list instead
-- of answering 409 key_reused. Every row names at least one discarded
-- print and a print is discarded once, so the table never holds more rows
-- than the discarded prints. Per print, the money guard is the conditional
-- UPDATE (discarded_at IS NULL): a print pays at most once whatever this
-- table holds.
--
-- Written and read by the batch route only; deleted only by
-- delete_player_data (by name: a players row is anonymised, never deleted,
-- so the ON DELETE CASCADE below never fires on that path, #437). Not
-- mapped in models.py: only raw SQL names it.
--
-- DEPLOY ORDER (#477): THIS FILE FIRST, as its own commit and its own deploy,
-- then the API that reads and writes it. A wrong order fails safe: the batch
-- route answers 503 shard_batch_unavailable before it takes a lock or writes
-- anything, the deletion statement is skipped while the table does not
-- exist, and the single-print route does not depend on this table at all.
--
-- LOCKS: CREATE TABLE with a foreign key takes SHARE ROW EXCLUSIVE on
-- players for the length of this short transaction, which waits for writers
-- already in flight and holds new ones. lock_timeout bounds that wait: if the
-- lock is not granted within 5 s the transaction fails and nothing is
-- applied (re-run it).
--
-- Idempotent: IF NOT EXISTS (a re-run skips the table and the index, their
-- CHECKs included), no data change, one explicit transaction (#340).

BEGIN;

SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS pc_shard_batches (
    player_id     UUID        NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    batch_key     TEXT        NOT NULL CHECK (batch_key ~ '^[A-Za-z0-9-]{8,64}$'),
    print_ids     TEXT        NOT NULL CHECK (length(print_ids) BETWEEN 36 AND 1600),
    prints        INTEGER     NOT NULL CHECK (prints BETWEEN 1 AND 40),
    shards_gained INTEGER     NOT NULL CHECK (shards_gained >= 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, batch_key)
);

CREATE INDEX IF NOT EXISTS ix_pc_shard_batches_created ON pc_shard_batches (created_at);

-- A positive signal before commit (#438): the table and both indexes exist.
DO $$
BEGIN
    IF to_regclass('pc_shard_batches') IS NULL THEN
        RAISE EXCEPTION '361: pc_shard_batches was not created';
    END IF;
    IF to_regclass('pc_shard_batches_pkey') IS NULL OR to_regclass('ix_pc_shard_batches_created') IS NULL THEN
        RAISE EXCEPTION '361: an index of pc_shard_batches is missing';
    END IF;
END $$;

COMMIT;
