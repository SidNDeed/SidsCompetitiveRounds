-- 316: the pool rule a snapshot was taken under (Sept 14 Player Cards batch, S1).
--
-- Rule 1 (Sept 10-13): every registered, non-banned player is in the card pool.
-- Rule 2 (this batch): only players who have run the mod (players.mod_seen_at set)
-- and are not banned. The api carries the current rule as _PC_POOL_RULE and takes a
-- new snapshot as soon as the latest one predates it, so the pool changes at the
-- deploy and not at the next 00:05 UTC daily; the daily rule is unchanged. Additive
-- and idempotent (ADD COLUMN IF NOT EXISTS); the default is the OLD rule so every
-- snapshot the pre-316 code writes between this file and the code deploy (#477
-- two-SHA order) is correctly marked as rule 1 and re-taken under rule 2 by the
-- new code. Explicit transaction (#340). No data change, no index.
BEGIN;

ALTER TABLE pc_pool_snapshots ADD COLUMN IF NOT EXISTS rule INTEGER NOT NULL DEFAULT 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'pc_pool_snapshots' AND column_name = 'rule'
    ) THEN
        RAISE EXCEPTION 'migration 316: pc_pool_snapshots.rule is missing after ADD COLUMN';
    END IF;
    RAISE NOTICE 'migration 316: pc_pool_snapshots.rule present (default 1 = every registered player)';
END $$;

COMMIT;
