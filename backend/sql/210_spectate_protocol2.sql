-- 210: Spectate protocol 2 rollout (Aug 10 design-review blocker 3, r2 blocker 1).
--
-- The spectator desync/safety client batch is protocol 2; protocol-1 clients
-- carry hazards that must not share a room with fixed clients (suppressed-
-- lifecycle clock ratchet, master-window RPC hazard, unregistered husk
-- views). Deploy order: THIS MIGRATION FIRST, then the API (the API's
-- heartbeat/validate now read spectate_leases.protocol, added here), then
-- the client release. Grants refused in the gap = spectate deliberately dark.
--
--   1. Leases carry the protocol they were minted under; the API writes
--      SPECTATE_PROTOCOL at grant and heartbeat/validate refuse a lease
--      below its game's floor — so a lease minted in any mixed-deploy
--      window self-revokes within one heartbeat (15s) instead of renewing
--      forever (r2 blocker 1).
--   2. Advance every LIVE game row's protocol floor (the attest refresh
--      UPDATE now GREATESTs it too, but rows whose fighters stop attesting
--      before the next refresh would otherwise keep the old floor).
--   3. Revoke open PROTOCOL-1 leases only (r2 find 11: an unconditional
--      revoke made a rerun after the release kill every legitimate
--      protocol-2 lease). Rerun-safe by construction.

ALTER TABLE spectate_leases
    ADD COLUMN IF NOT EXISTS protocol INTEGER NOT NULL DEFAULT 1;

UPDATE spectate_games
   SET protocol_min = GREATEST(protocol_min, 2)
 WHERE ended_at IS NULL;

UPDATE spectate_leases
   SET revoked_at = COALESCE(revoked_at, NOW())
 WHERE revoked_at IS NULL
   AND protocol < 2;

DO $$
BEGIN
    RAISE NOTICE 'migration 210: lease protocol column added, live game floors -> 2, protocol-1 leases revoked (post-check OK)';
END $$;
