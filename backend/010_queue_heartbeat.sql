-- 010_queue_heartbeat.sql
ALTER TABLE ranked_queue ADD COLUMN IF NOT EXISTS last_polled TIMESTAMPTZ DEFAULT NOW();
