-- 012_leave_tracking.sql
-- Adds ranked disconnect count to players table for leave % tracking

ALTER TABLE players ADD COLUMN IF NOT EXISTS ranked_dc_count INTEGER NOT NULL DEFAULT 0;

-- Verify
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'players' AND column_name = 'ranked_dc_count';
