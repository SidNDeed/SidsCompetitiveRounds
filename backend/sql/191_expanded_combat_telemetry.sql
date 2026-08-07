-- 191: Expanded combat telemetry (Aug 6 items 1+4).
-- New per-match columns on matches (damage dealt + timelines, single-hit /
-- health / bounce records, classified deaths) and career record columns on
-- players. Everything advisory — nothing here touches any HMAC canonical.
--
-- All match columns are NULLable BY DESIGN (#257): matches played before this
-- deploy must read "not recorded", never zero, and every average must divide
-- by the rows that actually carry the column. casual_dc_count is NOT NULL
-- DEFAULT 0 to match the ORM default exactly (#2).
-- Idempotent statement-by-statement (#243: the wrapper's || fallback re-runs
-- the whole file on a first-arm failure).

ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_damage_dealt INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_damage_dealt INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_max_single_hit INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_max_single_hit INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_max_health INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_max_health INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_best_bounce_kill INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_best_bounce_kill INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_damage_timeline VARCHAR(1024);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_damage_timeline VARCHAR(1024);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_deaths SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_deaths SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_deaths_boundary SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_deaths_boundary SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_deaths_own_bullet SMALLINT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_deaths_own_bullet SMALLINT;

ALTER TABLE players ADD COLUMN IF NOT EXISTS record_max_single_hit INTEGER;
ALTER TABLE players ADD COLUMN IF NOT EXISTS record_max_health INTEGER;
ALTER TABLE players ADD COLUMN IF NOT EXISTS record_bounce_kill INTEGER;
ALTER TABLE players ADD COLUMN IF NOT EXISTS casual_dc_count INTEGER NOT NULL DEFAULT 0;

-- Casual rage-quit dedup ledger (Aug 6 item 1). The UNIQUE replay guard is
-- all-NOT-NULL by design (#147): a blank room_id is rejected server-side
-- before insert, so NULLS-distinct can never disable the dedup.
CREATE TABLE IF NOT EXISTS casual_dc_events (
    id BIGSERIAL PRIMARY KEY,
    room_id VARCHAR(64) NOT NULL,
    leaver_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    reporter_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (room_id, leaver_id)
);
CREATE INDEX IF NOT EXISTS ix_casual_dc_events_reporter_recent
    ON casual_dc_events (reporter_id, created_at DESC);

-- Post-check: every new column present.
DO $$
DECLARE
    missing TEXT := '';
    col TEXT;
BEGIN
    FOREACH col IN ARRAY ARRAY[
        'p1_damage_dealt','p2_damage_dealt','p1_max_single_hit','p2_max_single_hit',
        'p1_max_health','p2_max_health','p1_best_bounce_kill','p2_best_bounce_kill',
        'p1_damage_timeline','p2_damage_timeline','p1_deaths','p2_deaths',
        'p1_deaths_boundary','p2_deaths_boundary','p1_deaths_own_bullet','p2_deaths_own_bullet']
    LOOP
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'matches' AND column_name = col) THEN
            missing := missing || ' matches.' || col;
        END IF;
    END LOOP;
    FOREACH col IN ARRAY ARRAY[
        'record_max_single_hit','record_max_health','record_bounce_kill','casual_dc_count']
    LOOP
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'players' AND column_name = col) THEN
            missing := missing || ' players.' || col;
        END IF;
    END LOOP;
    IF missing <> '' THEN
        RAISE EXCEPTION 'migration 191 post-check FAILED, missing:%', missing;
    END IF;
    RAISE NOTICE 'migration 191 post-check OK (20 columns present)';
END $$;
