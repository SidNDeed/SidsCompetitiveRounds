-- 311: Player Cards — Steam profile pictures as the default portrait
-- (Steam pictures design v2 §2). Additive only. Old api code neither reads
-- nor writes any of this, so the file rides a migrations-only precursor SHA
-- and is applied before the code that needs it (learning #477). Explicit
-- transaction: psql -f autocommits statement by statement otherwise (#340).
BEGIN;

-- The fetched picture (a pc_portraits blob, same shape as the rig's), the
-- Steam avatar reference the last COMPLETED attempt answered with (withdrawn
-- while an attempt is in flight; every reference is downloaded, none is
-- skipped as "unchanged"), when the last attempt began (logs and the admin
-- view only), the run of consecutive failures, the attempt id every write
-- binds on (advanced by each claim and by each clear, None, opt-out and
-- deletion), and the ONE scheduling column: NULL = never attempted (highest
-- priority), else when the sweep may next touch this player (success
-- now()+7d, failure now()+least(2^fail,720)h, admin clear the lock's end).
-- Nothing else decides.
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_steam_portrait_hash TEXT NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_steam_avatar_ref TEXT NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_steam_portrait_at TIMESTAMPTZ NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_steam_portrait_fail SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_steam_portrait_next_at TIMESTAMPTZ NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_steam_attempt BIGINT NOT NULL DEFAULT 0;

-- The FK in the game hash's shape (310): a blob a row names cannot be deleted.
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'players_pc_steam_portrait_hash_fkey'
    ) THEN
        ALTER TABLE players
            ADD CONSTRAINT players_pc_steam_portrait_hash_fkey
            FOREIGN KEY (pc_steam_portrait_hash) REFERENCES pc_portraits(hash);
    END IF;
END $$;

-- A blob is released by MARKING it (the writer that drops the last reference
-- sets this; any writer that adds a reference clears it) and deleted by the
-- janitor once it has stayed unreferenced for ten minutes — never in the
-- same statement that swapped it out, so a render that read the row before
-- the swap still finds its bytes (design v2 §6).
ALTER TABLE pc_portraits ADD COLUMN IF NOT EXISTS unreferenced_since TIMESTAMPTZ NULL;

-- 310 indexed neither hash column; the "does anything still reference this
-- blob" check was a seq scan, and Steam's default silhouette will be one blob
-- named by thousands of rows.
CREATE INDEX IF NOT EXISTS players_pc_game_portrait_hash_idx
    ON players (pc_game_portrait_hash) WHERE pc_game_portrait_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS players_pc_steam_portrait_hash_idx
    ON players (pc_steam_portrait_hash) WHERE pc_steam_portrait_hash IS NOT NULL;
-- The sweep's claim: eligible rows ordered NULLS FIRST on the one scheduling column.
CREATE INDEX IF NOT EXISTS players_pc_steam_portrait_next_at_idx
    ON players (pc_steam_portrait_next_at ASC NULLS FIRST)
    WHERE deleted_at IS NULL AND pc_opted_out_at IS NULL AND pc_portrait_source = 'game';
CREATE INDEX IF NOT EXISTS pc_portraits_unreferenced_since_idx
    ON pc_portraits (unreferenced_since) WHERE unreferenced_since IS NOT NULL;

COMMIT;
