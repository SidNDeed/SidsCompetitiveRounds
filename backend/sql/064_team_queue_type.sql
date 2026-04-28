-- v1.25.18: decouple Random matchmaking from Pick-Teams matchmaking.
--
-- Two parallel 2v2 queues:
--   queue_type = 'auto'   — random matchmaking, balancer chooses teams
--   queue_type = 'manual' — players chose a "pick teams" lobby; matchmaker
--                           always honors preferred_team within these 4
--
-- The matchmaker filters candidates by queue_type so the two queues never
-- cross-match. manual_pick_enabled (from migration 062) is now redundant —
-- queue membership IS the toggle — but the column stays for compatibility
-- with prior DLLs still in the wild during the rollout window.

ALTER TABLE team_queue
    ADD COLUMN IF NOT EXISTS queue_type VARCHAR(8) NOT NULL DEFAULT 'auto';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'team_queue_queue_type_chk'
    ) THEN
        ALTER TABLE team_queue
            ADD CONSTRAINT team_queue_queue_type_chk
            CHECK (queue_type IN ('auto','manual'));
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS team_queue_queue_type_status_idx
    ON team_queue (queue_type, status);
