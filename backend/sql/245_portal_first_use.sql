-- 245: first-use address binding for translation-portal sessions.
-- The mint binds a token to the GAME's source address; for players whose game
-- and browser egress differently (Cloudflare WARP, privacy relays,
-- split-tunnel VPNs) every portal call then 401'd as "Session expired". The
-- first portal request inside a short window may now re-bind the token to the
-- browser's address; first_use_at records that the window has closed.
-- Nullable, no default: NULL = never used. Pure idempotent DDL; explicit
-- transaction because psql -f does not add one (learning #340).
-- DEPLOY ORDER: apply BEFORE the API that reads the column (learning #235 -
-- the portal auth SELECT names it on every portal request).

BEGIN;

ALTER TABLE i18n_portal_sessions
    ADD COLUMN IF NOT EXISTS first_use_at TIMESTAMPTZ;

COMMIT;
