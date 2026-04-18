-- 009_achievements.sql  —  Achievement tracking

CREATE TABLE IF NOT EXISTS player_achievements (
    id              SERIAL PRIMARY KEY,
    player_id       UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    achievement_key VARCHAR(64) NOT NULL,
    unlocked_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    match_id        UUID REFERENCES matches(id) ON DELETE SET NULL,
    UNIQUE (player_id, achievement_key)
);

CREATE INDEX IF NOT EXISTS idx_pa_player ON player_achievements(player_id);
CREATE INDEX IF NOT EXISTS idx_pa_key    ON player_achievements(achievement_key);
