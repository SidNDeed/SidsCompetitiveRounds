-- Rollback only: landing plan D5c.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE TABLE IF NOT EXISTS pending_dms_v1410_parked (
    id                BIGINT NOT NULL,
    was_delivered_at  TIMESTAMPTZ,
    was_undeliverable BOOLEAN NOT NULL,
    was_cancelled_at  TIMESTAMPTZ NOT NULL,
    acked             BOOLEAN NOT NULL,
    parked_at         TIMESTAMPTZ NOT NULL,
    resumed_at        TIMESTAMPTZ,
    PRIMARY KEY (id, parked_at)
);
WITH c AS (
    SELECT d.id, d.cancelled_at
      FROM pending_dms d
     WHERE d.delivered_at IS NULL
       AND NOT d.undeliverable
       AND d.cancelled_at IS NOT NULL
), p AS (
    UPDATE pending_dms u
       SET delivered_at = NOW(), undeliverable = false,
           cancelled_at = NULL
      FROM c
     WHERE u.id = c.id AND u.delivered_at IS NULL
 RETURNING u.id, c.cancelled_at, u.delivered_at
)
INSERT INTO pending_dms_v1410_parked (id, was_delivered_at,
       was_undeliverable, was_cancelled_at, acked, parked_at)
SELECT id, NULL, false, cancelled_at, true, delivered_at FROM p;
COMMIT;
