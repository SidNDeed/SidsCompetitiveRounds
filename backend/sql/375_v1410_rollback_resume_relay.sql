-- Resume only: landing plan D5e.
BEGIN;
SET LOCAL lock_timeout = '5s';
WITH r AS (
    UPDATE pending_dms d
       SET delivered_at = k.was_delivered_at,
           undeliverable = k.was_undeliverable
      FROM pending_dms_v1410_parked k
     WHERE k.id = d.id
       AND k.resumed_at IS NULL
       AND d.delivered_at = k.parked_at
       AND d.undeliverable
 RETURNING k.id, k.parked_at
)
UPDATE pending_dms_v1410_parked k
   SET resumed_at = NOW()
  FROM r
 WHERE k.id = r.id AND k.parked_at = r.parked_at;
COMMIT;
