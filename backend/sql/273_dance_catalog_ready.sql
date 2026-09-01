-- Flip the dance rows live (see 272's header for the ordering design).
--
-- APPLY ONLY AFTER the new api (the build carrying DANCES_MIN_VERSION) is
-- deployed on BOTH boxes (#422 — the standby serves the routed shop reads).
-- Before that, the old api has no version gate, so flipping early would
-- surface Buy-able dance rows to clients that cannot use them (round-2
-- review blocker 2's exact scenario). After the new api is live the version
-- gate owns the exposure decision and this flip is safe regardless of the
-- client release timing.
-- Idempotent: the UPDATE is a no-op once the rows are TRUE.

BEGIN;

UPDATE shop_items SET catalog_ready = TRUE
 WHERE kind = 'dance' AND sku IN ('dance_bounce', 'dance_wave');

COMMIT;
