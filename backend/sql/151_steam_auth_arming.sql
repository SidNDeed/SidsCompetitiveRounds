-- 151: Monotonic steam-auth arming (security item A4).
--
-- The per-account arming check used to read steam_sessions for a verified
-- session issued in the last 7 days. Two problems:
--   1. steam_sessions rows expire after 24h and are pruned ~1 day later, so
--      the table never holds more than ~2 days of history — the 7-day window
--      only worked because active players re-mint every launch.
--   2. An account whose player skipped a week was silently DE-armed: their
--      next request could claim an old X-Mod-Version and ride the version
--      carve-out around session enforcement entirely.
-- Arming must be monotonic: once an account has EVER minted a verified
-- session, it stays armed. players.steam_auth_seen_at is stamped at the first
-- verified mint (main.py steam_auth) and never cleared.

ALTER TABLE players ADD COLUMN IF NOT EXISTS steam_auth_seen_at TIMESTAMPTZ;

-- Backfill from whatever verified sessions still exist (<= ~2 days of
-- history, but it arms every currently-active ticket-auth account without
-- waiting for their next launch). Idempotent: only fills NULLs.
UPDATE players p
   SET steam_auth_seen_at = s.first_verified
  FROM (SELECT steam_id, MIN(issued_at) AS first_verified
          FROM steam_sessions
         WHERE verified
         GROUP BY steam_id) s
 WHERE p.steam_id = s.steam_id
   AND p.steam_auth_seen_at IS NULL;
