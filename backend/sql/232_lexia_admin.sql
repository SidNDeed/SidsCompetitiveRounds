-- 232_lexia_admin.sql
--
-- Renumbered 231 -> 232 at integration: another session applied its own
-- migration 231 (the NotNic grant) a day earlier, so 231 was already
-- taken. This file was APPLIED to production on 2026-08-20 under the
-- old number; it is idempotent (ON CONFLICT DO NOTHING), so re-running
-- it as 232 is a no-op.
--
-- Grant Lexia (76561199012602040) admin, per request. Same shape as the
-- existing Stan grant (117). Idempotent.
--
-- The DB row is only half the grant: /admin/* also requires an HMAC signed
-- with ADMIN_HMAC_SECRET, so Lexia's client cfg needs AdminSecret set to the
-- server's value before any admin action will pass (_verify_admin_hmac fails
-- closed). Sid hands that over out-of-band.

INSERT INTO admin_users (steam_id, granted_by_steam_id, notes)
VALUES ('76561199012602040', '76561198040410653', 'Trusted moderator — Lexia')
ON CONFLICT (steam_id) DO NOTHING;
