-- 105_rename_overlapping_titles.sql
--
-- Bug #49: the "Beginner" and "Grandmaster" SHOP titles collide with the elo
-- rank tier names ("Beginner" tier, "Grand Master" tier + the dynamic Current
-- Rank title). A player wearing the shop title looked identical to a player
-- at that rank. Renames per Sid: Beginner -> Noobie, Grandmaster -> Expert.
-- Skus stay stable (title_beginner / title_grandmaster) so player_items rows,
-- purchases, and equipped references are untouched — display name only.

BEGIN;

UPDATE shop_items SET name = 'Noobie',
                      description = 'Everyone starts somewhere.'
WHERE sku = 'title_beginner' AND name = 'Beginner';

UPDATE shop_items SET name = 'Expert',
                      description = 'Few reach it. Fewer afford the title.'
WHERE sku = 'title_grandmaster' AND name = 'Grandmaster';

COMMIT;
