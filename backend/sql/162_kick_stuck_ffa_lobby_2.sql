-- 162: second one-off (July 28 ~23:48 UTC) — same shape as 161 for the
-- re-formed wedge: lobby c0e4c893 (1 recorded game) ended its sitting but
-- held all four members ready_join. Close (game kept) + free the rows.
BEGIN;
UPDATE ffa_lobbies
   SET status = 'completed', completed_at = NOW()
 WHERE id = 'c0e4c893-8e3d-4373-a748-1549140f7eb1'
   AND status = 'active';
DELETE FROM ffa_queue
 WHERE series_id = 'c0e4c893-8e3d-4373-a748-1549140f7eb1';
COMMIT;
