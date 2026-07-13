-- 117_stan_admin.sql
--
-- Grant Stan (76561198983423367) admin, per request. Same shape as the
-- existing lopidav grant. Idempotent.

INSERT INTO admin_users (steam_id, granted_by_steam_id, notes)
VALUES ('76561198983423367', '76561198040410653', 'Trusted moderator — Stan')
ON CONFLICT (steam_id) DO NOTHING;
