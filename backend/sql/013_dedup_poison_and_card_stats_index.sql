-- 013_dedup_poison_and_card_stats_index.sql
--
-- Two related fixes:
--   1. Merge "Poison" → "Poison Bullets" in match_cards. The mod historically
--      reported the GameObject name ("Poison") in some code paths and the
--      CardInfo.cardName ("Poison Bullets") in others, splitting the same card
--      across two rows in the leaderboard "Top Cards" and Card Stats panel.
--   2. Fix card_stats unique index. The materialized view groups by
--      (card_name, card_rarity) but the unique index was on (card_name) alone,
--      causing REFRESH CONCURRENTLY to fail with "duplicate key" whenever the
--      same card name appeared with multiple rarities (e.g., Poison Bullets had
--      Common/Uncommon/Unknown rows). The index is now keyed to match the GROUP BY.

BEGIN;

-- Merge Poison into Poison Bullets, normalize rarity to Common.
UPDATE match_cards
SET card_name = 'Poison Bullets', card_rarity = 'Common'
WHERE card_name = 'Poison';

-- Standardize stray Poison Bullets rarities (Uncommon/Unknown were incorrect captures).
UPDATE match_cards
SET card_rarity = 'Common'
WHERE card_name = 'Poison Bullets' AND card_rarity <> 'Common';

-- Replace the broken unique index on the materialized view.
DROP INDEX IF EXISTS idx_card_stats_name;
CREATE UNIQUE INDEX idx_card_stats_name ON card_stats (card_name, card_rarity);

COMMIT;

-- Refresh outside the transaction (CONCURRENTLY can't run inside one).
REFRESH MATERIALIZED VIEW CONCURRENTLY card_stats;
