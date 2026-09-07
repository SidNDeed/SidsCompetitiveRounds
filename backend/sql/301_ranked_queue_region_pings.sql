-- 301_ranked_queue_region_pings.sql
-- Sept 7 item 3: the ranked best-region finder. A client carrying the sweep measures
-- Photon's region list with its own UDP pinger and sends the result with its
-- 1v1 queue join (body fields region_pings / region_pings_age_s) and, while it
-- keeps polling, as the X-Region-Pings request header for the three polls
-- after each new sweep. The room-region pick reads both seats' maps at
-- issuance and may move the pair to a region that costs NEITHER seat more
-- than 20 ms over its own measured baseline; anything missing, stale or
-- malformed leaves the existing ladder's answer exactly as it was.
--
-- region_pings     {"us": 42, "eu": 31, ...}  <= 24 entries, ms in 1..5000
-- region_pings_at  when the client completed that sweep (now() - age at write)
--
-- Deliberately NOT declared on the RankedQueue ORM model: raw SQL on both
-- ends (the 296 pattern). Writers: queue_join's INSERT ... ON CONFLICT (NULL
-- when the validator refused the body) and queue_poll's heartbeat UPDATE
-- (only with a valid header; a poll never clears the columns). Readers: the
-- four authoritative re-reads under the ordered locks in queue_poll and
-- queue_ready. Rows leave ranked_queue with the pair, so nothing here
-- outlives a queue session.
--
-- Deploy order (#477): this file rides the migrations-only precursor SHA.
-- Apply it on the primary, confirm the columns there AND on the standby
-- (streaming replication), THEN deploy the api SHA whose raw SELECTs name
-- the columns — an api ahead of the schema 500s every poll on
-- undefined_column.
BEGIN;
ALTER TABLE ranked_queue ADD COLUMN IF NOT EXISTS region_pings JSONB;
ALTER TABLE ranked_queue ADD COLUMN IF NOT EXISTS region_pings_at TIMESTAMPTZ;
COMMIT;
