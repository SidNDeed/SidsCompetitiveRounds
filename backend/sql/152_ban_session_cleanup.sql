-- 152: One-time revocation of Steam sessions held by already-banned accounts.
--
-- The July 26 batch makes /admin/ban revoke the target's steam_sessions and
-- makes /auth/steam refuse to mint for banned accounts — but bans issued
-- BEFORE that deploy left their sessions alive until natural TTL (~24h).
-- Close the gap for every currently-active ban. Idempotent: re-running
-- deletes nothing new.

DELETE FROM steam_sessions
 WHERE steam_id IN (SELECT steam_id FROM player_bans WHERE unbanned_at IS NULL);
