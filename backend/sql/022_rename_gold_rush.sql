-- 022_rename_gold_rush.sql
-- Renames the "Gold Rush" legendary title to "Royal" and raises price to 10000.
-- SKU stays the same so anyone who somehow owns it (no one yet) keeps their item.

UPDATE shop_items
SET name = 'Royal',
    description = 'Worn by those who climbed the mountain.',
    price = 10000
WHERE sku = 'title_gold_rush';
