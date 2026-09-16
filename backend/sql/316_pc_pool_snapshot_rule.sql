-- 316: the pool rule a snapshot was taken under (Sept 14 Player Cards batch, S1).
--
-- Rule 1 (Sept 10-13): every registered, non-banned player is in the card pool.
-- Rule 2 (Sept 14 batch): only players who have run the mod (players.mod_seen_at
-- set) and are not banned.
-- Rule 3 (the 2026-09-15 merge): rule 2 AND the id is a public individual
-- SteamID64 -- the INTERSECTION of the mod-runner decision (2026-09-13) and "no
-- Steam ID, no card" (2026-09-15), both of them restrictions on who may be a
-- subject. Rule 3 is what the api deployed alongside this file STAMPS; the column
-- holds a number and nothing else, so this list is the stamp's only decoder and a
-- rule added to main.py's enumeration (_PC_POOL_RULE) belongs here in the same
-- change.
--
-- The api carries the current rule as _PC_POOL_RULE and takes a new snapshot as
-- soon as the latest one predates it, so the pool changes at the deploy and not at
-- the next 00:05 UTC daily; the daily rule is unchanged. Additive and idempotent
-- (ADD COLUMN IF NOT EXISTS); the default is the OLD rule so every snapshot the
-- pre-316 code writes between this file and the code deploy (#477 two-SHA order)
-- is correctly marked as rule 1 and re-taken under the deployed rule by the new
-- code. Explicit transaction (#340). No data change, no index.
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
