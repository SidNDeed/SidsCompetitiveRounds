-- 122_cleanup_ovt_curltest2.sql — remove the decider-in-lobby curl-test series
-- (lopidav+Sid2+snail lock smoke test, 2026-07-13, no games reported). Idempotent.
DELETE FROM ovt_queue WHERE series_id IN (SELECT id FROM ovt_series WHERE solo_series_wins=0 AND duo_series_wins=0 AND created_at > NOW() - INTERVAL '30 minutes');
DELETE FROM ovt_series WHERE solo_series_wins=0 AND duo_series_wins=0 AND status='active' AND created_at > NOW() - INTERVAL '30 minutes';
