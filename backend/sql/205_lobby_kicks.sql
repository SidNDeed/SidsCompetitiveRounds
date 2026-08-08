-- 205: Host kick for hosted lobbies (Sid, Aug 8 follow-up).
-- One comma-joined VARCHAR per lobby (NOT a TEXT[] — learning #275: an
-- `array_col || :param` types the param as the ARRAY and asyncpg rejects the
-- scalar, which silently broke every FFA leave for three releases; the
-- membership test lives in Python, so a flat string removes the class).
-- A kicked player may not rejoin THAT lobby; admins are unkickable
-- (checked against admin_users at kick time, server-side).

ALTER TABLE ffa_lobbies  ADD COLUMN IF NOT EXISTS kicked_steam_ids VARCHAR(700) NOT NULL DEFAULT '';
ALTER TABLE team_lobbies ADD COLUMN IF NOT EXISTS kicked_steam_ids VARCHAR(700) NOT NULL DEFAULT '';
ALTER TABLE ovt_lobbies  ADD COLUMN IF NOT EXISTS kicked_steam_ids VARCHAR(700) NOT NULL DEFAULT '';

-- Post-check.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ffa_lobbies' AND column_name = 'kicked_steam_ids')
    OR NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'team_lobbies' AND column_name = 'kicked_steam_ids')
    OR NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ovt_lobbies' AND column_name = 'kicked_steam_ids')
    THEN
        RAISE EXCEPTION 'post-check FAILED: kicked_steam_ids missing';
    END IF;
    RAISE NOTICE 'migration 205 post-check OK: kicked_steam_ids on all three lobby tables';
END $$;
