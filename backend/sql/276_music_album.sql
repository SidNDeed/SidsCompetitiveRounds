-- 276: seed the "Another Round" music album shop row (music feature wave 1).
--
-- kind='music_album' is a NEW behavior-gated kind on the dance precedent
-- (272/273): the row is born catalog_ready = FALSE EXPLICITLY — the 148
-- BEFORE INSERT trigger forces FALSE only for kind='face'; any other kind
-- inherits the column DEFAULT TRUE and would be instantly visible and
-- purchasable to every client. Migration 277 flips it live at the ship wave.
--
-- artist_steam_id stays NULL DELIBERATELY (house-owned): _artist_own_item
-- matches on artist_steam_id, so a NULL row has NO artist mutation surface —
-- no set-price/set-stock/gift/block endpoint can touch it and no royalty is
-- claimable. Price then changes only by migration, so the displayed price can
-- never drift under a buyer mid-click (design v2 F1/F2/F10). "By Sid"
-- attribution renders from the client MusicCatalog, not this row.
--
-- Idempotent: ON CONFLICT (sku) DO NOTHING + a full-contract post-check that
-- RAISES on any mismatch — a pre-existing conflicting sku aborts the whole
-- transaction loudly instead of being silently adopted (design v3 G6).
-- Rerun-safe only UNTIL 277 flips the row: a rerun after the flip RAISES on
-- catalog_ready/released_at by design (do not re-apply this file then; a loud
-- abort beats tolerating drift). Explicit BEGIN/COMMIT (#340).
-- Dry-run 2026-09-01 against prod (#313): sku count 0, kind count 0, no
-- cosmetic_submissions row, post-check SELECT shape verified column-by-column.

BEGIN;

INSERT INTO shop_items (sku, kind, name, description, price, rarity,
                        preview_color, rotation_pool, artist_steam_id,
                        stock_limit, catalog_ready)
VALUES ('music_album_another_round', 'music_album', 'Another Round',
        '7-track Metal / Phonk album', 1, 'epic', '#FF5540',
        NULL, NULL, NULL, FALSE)
ON CONFLICT (sku) DO NOTHING;

-- Full-contract post-check (the 264 pattern widened to EVERY pinned column).
-- v_ prefixes, never bare column names (#442).
DO $$
DECLARE
    v_count INT;
    v_row   RECORD;
BEGIN
    SELECT COUNT(*) INTO v_count
      FROM shop_items si
     WHERE si.sku = 'music_album_another_round';
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'post-check FAILED: % rows for music_album_another_round (want exactly 1)',
                        v_count;
    END IF;

    SELECT si.kind, si.name, si.description, si.price, si.rarity,
           si.preview_color, si.rotation_pool, si.artist_steam_id,
           si.stock_limit, si.catalog_ready, si.released_at
      INTO v_row
      FROM shop_items si
     WHERE si.sku = 'music_album_another_round';

    IF v_row.kind            IS DISTINCT FROM 'music_album'
       OR v_row.name         IS DISTINCT FROM 'Another Round'
       OR v_row.description  IS DISTINCT FROM '7-track Metal / Phonk album'
       OR v_row.price        IS DISTINCT FROM 1
       OR v_row.rarity       IS DISTINCT FROM 'epic'
       OR v_row.preview_color IS DISTINCT FROM '#FF5540'
       OR v_row.rotation_pool IS NOT NULL
       OR v_row.artist_steam_id IS NOT NULL
       OR v_row.stock_limit  IS NOT NULL
       OR v_row.catalog_ready IS DISTINCT FROM FALSE
       OR v_row.released_at  IS NOT NULL THEN
        RAISE EXCEPTION 'post-check FAILED: music_album_another_round does not match the pinned contract '
                        '(kind=%, name=%, desc=%, price=%, rarity=%, color=%, pool=%, artist=%, stock=%, ready=%, released=%)',
                        v_row.kind, v_row.name, v_row.description, v_row.price,
                        v_row.rarity, v_row.preview_color, v_row.rotation_pool,
                        v_row.artist_steam_id, v_row.stock_limit,
                        v_row.catalog_ready, v_row.released_at;
    END IF;

    RAISE NOTICE 'post-check OK: music_album_another_round seeded, born gated (catalog_ready = FALSE)';
END $$;

COMMIT;
