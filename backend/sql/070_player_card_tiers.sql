-- v1.25.24: per-player card tier assignments (S/A/B/C/D/E/F).
--
-- Each player gets THREE independent tier lists (Casual / Ranked / All) so
-- they can express different opinions per match-mode. Filter is one of
-- 'casual', 'ranked', 'all' (lowercase, mirrors the existing card-stats
-- filter). Tier is a single character S/A/B/C/D/E/F. Absence of a row
-- means the player hasn't ranked that card in that filter.

CREATE TABLE IF NOT EXISTS player_card_tiers (
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    card_name VARCHAR(64) NOT NULL,
    filter    VARCHAR(8)  NOT NULL,
    tier      CHAR(1)     NOT NULL,
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (player_id, card_name, filter)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'player_card_tiers_filter_chk'
    ) THEN
        ALTER TABLE player_card_tiers
            ADD CONSTRAINT player_card_tiers_filter_chk
            CHECK (filter IN ('casual','ranked','all'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'player_card_tiers_tier_chk'
    ) THEN
        ALTER TABLE player_card_tiers
            ADD CONSTRAINT player_card_tiers_tier_chk
            CHECK (tier IN ('S','A','B','C','D','E','F'));
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_player_card_tiers_lookup
    ON player_card_tiers (player_id, filter);
