-- Admin tools (v1.21.0).
--
-- admin_users — whitelist of Steam IDs allowed to call /admin/* endpoints.
--               Seed Sid + Lopi at install. Add more via direct SQL or admin UI.
-- player_bans — append-only log; player is "currently banned" if the latest
--               row has unbanned_at IS NULL.
-- admin_actions — audit log for everything admins do (bans, achievement grants,
--               series reversals). Used by the admin tab and #scr-admin channel.
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS admin_users (
    steam_id TEXT PRIMARY KEY,
    granted_by_steam_id TEXT,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);

-- Seed: Sid (mod owner) + Lopi (trusted moderator). Re-running this is a no-op.
INSERT INTO admin_users (steam_id, granted_by_steam_id, notes) VALUES
    ('76561198040410653', NULL, 'Mod owner — Sid'),
    ('76561198041616199', '76561198040410653', 'Trusted moderator — lopidav')
ON CONFLICT (steam_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS player_bans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    steam_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    banned_by_steam_id TEXT NOT NULL REFERENCES admin_users(steam_id),
    banned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    unbanned_at TIMESTAMPTZ,
    unbanned_by_steam_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_player_bans_active ON player_bans(steam_id) WHERE unbanned_at IS NULL;

CREATE TABLE IF NOT EXISTS admin_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_steam_id TEXT NOT NULL REFERENCES admin_users(steam_id),
    action TEXT NOT NULL,                  -- 'ban' | 'unban' | 'grant_achievement' | 'reverse_series' | 'reverse_match' | 'flag_review'
    target_steam_id TEXT,                  -- the affected player, if any
    target_match_id UUID,                  -- the affected match, if any
    target_series_id UUID,                 -- the affected series, if any
    details JSONB,                         -- arbitrary action context (achievement_id, reason, before/after rating, etc.)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_actions_admin ON admin_actions(admin_steam_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_actions_target ON admin_actions(target_steam_id, created_at DESC);
