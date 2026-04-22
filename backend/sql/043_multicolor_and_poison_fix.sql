-- v1.23.x — Two unrelated-but-small changes packaged together.
--
-- 1. Map colors become multi-equip. Add active_color_ids BIGINT[] column; backfill from
--    the existing single active_color_id. Clients now cycle between equipped colors with
--    Left Shift in-game (ArtHandler.NextArtPatch indexes through the list). The legacy
--    active_color_id column stays for backward compat with any older-client code paths;
--    the server keeps it in sync with active_color_ids[0].
--
-- 2. Poison / Poison Bullets pass-rate dedup. ROUNDS' in-game display is just "Poison"
--    for what historically had the codename "Poison Bullets". The mod's hardAliases map
--    used to canonicalize Poison → Poison Bullets (now reversed to → Poison). Backfill
--    every historical "Poison Bullets" row in card_offers and match_cards so the pass-
--    rate stats stop being split across two names.
--
-- Idempotent.

-- Part 1: multi-equip map colors.
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS active_color_ids BIGINT[] NOT NULL DEFAULT '{}'::BIGINT[];

-- Backfill: put each player's current single-value active_color_id into the new array,
-- but only if the array doesn't already contain it (idempotent re-runs).
UPDATE players
   SET active_color_ids = ARRAY[active_color_id]::BIGINT[]
 WHERE active_color_id IS NOT NULL
   AND (active_color_ids IS NULL OR NOT (active_color_ids @> ARRAY[active_color_id]::BIGINT[]));

-- Part 2: Poison Bullets → Poison consolidation.
UPDATE card_offers SET card_name = 'Poison' WHERE card_name = 'Poison Bullets';
UPDATE match_cards SET card_name = 'Poison' WHERE card_name = 'Poison Bullets';
