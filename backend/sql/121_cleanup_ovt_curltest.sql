-- 121_cleanup_ovt_curltest.sql
-- Remove the 1v2 curl-test artifacts (queue lock smoke test on 2026-07-13,
-- test accounts Sid/Sid2/lopidav). No real games were reported, so only the
-- test queue rows + the empty test series exist. Idempotent.
DELETE FROM ovt_queue WHERE series_id IN (
    SELECT id FROM ovt_series WHERE photon_room_id = 'ovt_85136abe8545');
DELETE FROM ovt_series WHERE photon_room_id = 'ovt_85136abe8545'
    AND solo_series_wins = 0 AND duo_series_wins = 0;
