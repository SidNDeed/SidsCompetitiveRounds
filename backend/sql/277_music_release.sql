-- 277: flip the "Another Round" album live (music feature ship wave).
--
-- DO-NOT-APPLY-UNTIL ALL THREE HOLD (design v3 runbook steps 3-7):
--   1. The immutable `music-ar1` asset release EXISTS and
--      scripts/verify_music_release.py verify passes (both zips reachable at
--      the exact public client URLs, entry names + sizes + SHA-256 per
--      plugin/music/manifest.json).
--   2. The client version Sid NAMED for the music release has shipped (its
--      GitHub release exists; that DLL's MusicCatalog carries this sku).
--   3. The api on BOTH boxes (#422 — the standby serves the routed shop
--      reads) carries the MUSIC_SKU_MIN_VERSIONS entry for this sku = that
--      named version. After this flip the version gate owns exposure, exactly
--      like 273's dance ordering; before it, nothing gates old clients.
--
-- The UPDATE is guarded on the COMPLETE pre-state 276 pinned (minus the flag
-- being flipped): any drift = 0 rows updated = the post-check RAISES and the
-- whole transaction rolls back. The 148 trigger fires on the flip; this sku
-- has no cosmetic_submissions row (dry-run verified 2026-09-01), so the
-- trigger only stamps released_at = NOW() — no approval-revision interaction.
-- Rerun-safe: a second run updates 0 rows (catalog_ready already TRUE) and
-- the post-check passes on the already-live row. Explicit BEGIN/COMMIT (#340).

BEGIN;

UPDATE shop_items SET catalog_ready = TRUE
 WHERE shop_items.sku = 'music_album_another_round'
   AND shop_items.kind = 'music_album'
   AND shop_items.name = 'Another Round'
   AND shop_items.description = '7-track Metal / Phonk album'
   AND shop_items.price = 1
   AND shop_items.rarity = 'epic'
   AND shop_items.preview_color = '#FF5540'
   AND shop_items.rotation_pool IS NULL
   AND shop_items.artist_steam_id IS NULL
   AND shop_items.stock_limit IS NULL
   AND shop_items.released_at IS NULL
   AND shop_items.catalog_ready = FALSE;

-- Post-check: exactly one LIVE row carrying the full contract, catalog_ready
-- TRUE and released_at stamped by the 148 trigger. v_ prefixes (#442).
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
       OR v_row.catalog_ready IS DISTINCT FROM TRUE
       OR v_row.released_at  IS NULL THEN
        RAISE EXCEPTION 'post-check FAILED: music_album_another_round is not live with the pinned contract '
                        '(kind=%, name=%, desc=%, price=%, rarity=%, color=%, pool=%, artist=%, stock=%, ready=%, released=%) '
                        '- the guarded UPDATE matched 0 rows (pre-state drift?) or the 148 trigger did not stamp released_at',
                        v_row.kind, v_row.name, v_row.description, v_row.price,
                        v_row.rarity, v_row.preview_color, v_row.rotation_pool,
                        v_row.artist_steam_id, v_row.stock_limit,
                        v_row.catalog_ready, v_row.released_at;
    END IF;

    RAISE NOTICE 'post-check OK: music_album_another_round is LIVE (released_at = %)',
                 v_row.released_at;
END $$;

COMMIT;
