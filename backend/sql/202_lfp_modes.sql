-- 202: LFP ping mode multi-select (Aug 7 batch item 11).
-- The client's RLFP prompt gains 1v1 / 2v2 / FFA toggles; the selection is
-- stored canonically ("1v1,ffa" — lowercase, fixed order, comma-joined) and
-- rendered into the Discord beacon ("LFP: 1v1+FFA for 30min").
--
-- Deploy order (#236 direction): this migration must be applied BEFORE the
-- API deploy — the new INSERT writes the column unconditionally.

ALTER TABLE lfp_pings ADD COLUMN IF NOT EXISTS modes VARCHAR(20) NOT NULL DEFAULT '1v1';

-- Post-check.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'lfp_pings' AND column_name = 'modes'
    ) THEN
        RAISE EXCEPTION 'post-check FAILED: lfp_pings.modes missing';
    END IF;
    RAISE NOTICE 'migration 202 post-check OK: lfp_pings.modes present';
END $$;
