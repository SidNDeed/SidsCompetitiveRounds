-- 015_dedup_cardnames_v2.sql
--
-- Follow-up to 013. A handful of cards still leaked non-canonical names after
-- 013 because the client's Harmony EndPick hook wasn't canonicalizing opponent
-- card names (only the local log-capture path was). Client is now fixed to
-- canonicalize both paths; this migration cleans the rows reported in between.
--
-- Affects both match_cards and the new card_offers table.

BEGIN;

-- Poison → Poison Bullets (12 stray rows post-013)
UPDATE match_cards
SET card_name = 'Poison Bullets', card_rarity = 'Common'
WHERE card_name = 'Poison';

UPDATE card_offers SET card_name = 'Poison Bullets' WHERE card_name = 'Poison';

-- Prisitne → Pristine Perseverence (18 stray rows vs 1 canonical)
UPDATE match_cards
SET card_name = 'Pristine Perseverence'
WHERE card_name = 'Prisitne Perseverence';

UPDATE card_offers SET card_name = 'Pristine Perseverence' WHERE card_name = 'Prisitne Perseverence';

COMMIT;

REFRESH MATERIALIZED VIEW CONCURRENTLY card_stats;
