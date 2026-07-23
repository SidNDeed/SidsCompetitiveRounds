-- 145_ovt_status_spelling.sql — July 22 (1v2 forensics data fix)
--
-- The queue-cleanup janitor wrote status='cancelled' (two Ls) while every
-- other ovt path — and the continuation prior-series consent lookup — uses
-- 'canceled'. Janitor-cancelled series were therefore invisible to the
-- continuation lookup (409 "No prior series" → unrecorded games, bug #70
-- family). The janitor now writes 'canceled'; this normalizes the legacy rows.
-- Scoped to ovt_series ONLY — team_series legitimately uses 'cancelled'.

UPDATE ovt_series
   SET status = 'canceled',
       invalidated_at = COALESCE(invalidated_at, NOW()),
       invalidation_reason = COALESCE(invalidation_reason, 'janitor_dead_lock')
 WHERE status = 'cancelled';
