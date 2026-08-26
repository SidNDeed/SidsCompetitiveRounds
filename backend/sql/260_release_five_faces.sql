-- 260: publish five approved community faces bundled into the client catalog.
--
-- DO NOT APPLY BEFORE THE RELEASE THAT SHIPS THE ART. catalog_ready=TRUE is what
-- makes an item visible and purchasable, and the client can only RENDER it once
-- CustomCosmetics.Catalog carries a CosmeticDef and cosmetics.zip carries the
-- PNG. Flip it early and Home renders the green fallback swatch for a sku no
-- client can draw (learning #163); flip it late and the art ships invisible
-- (#164). It belongs in the same release as the catalog entries, applied as a
-- step-9 seed migration AFTER the GitHub release exists.
--
-- WHAT WAS COMPILED, and where it came from. Each PNG was pulled from
-- cosmetic_submissions.png_data in short base64 chunks with the newlines
-- stripped server-side, and REQUIRED to match md5(png_data) plus the stored
-- byte count plus the PNG magic before it was written to disk. That check
-- earned its place on the first run: a naive filter also matched psql's
-- one-character column header, which is itself valid base64, and produced a
-- 10727-byte file where the row said 10726. Nothing was written.
--
--   sku                        slot    bytes   md5                               scale
--   face_detail_lucky_coin     detail  12521   5feec29e5f87744510f11daf2535f5f4  1.65
--   face_detail_lucky_ears     detail  14979   c0f55eca24e6163eada9bb3c049999fb  1.40
--   face_detail_militia_man    detail  37031   f35c66be40fb9cbbb92e22fd63201d93  1.45
--   face_eyes_sadness          eyes    28789   81e6cf5919903d482b4a1536a10191d1  1.55
--   face_mouth_sinister_smile  mouth   10726   5618a223572d5389c8b8b77a621fb7b7  1.55
--
-- All five are frame_count=1 (static), all approved offsets are (0,0), and all
-- are at approved_placement_revision=1. Scale/offset were copied from the
-- approved_* snapshot, never the mutable proposal columns (#165).
--
-- THE GUARD BELOW IS THE POINT. An artist can submit a newer revision between
-- the moment the bundle is cut and the moment this runs. If that happens, the
-- values compiled into the client no longer match what the database calls
-- approved, and publishing would render every player's copy at a placement the
-- artist has already superseded. So this ABORTS rather than publishing a stale
-- bundle -- a loud failure at deploy time beats a wrong placement in the wild.
--
-- released_at and published_placement_revision are deliberately NOT set here:
-- the migration-148 trigger stamps both when catalog_ready flips. stock_limit is
-- left alone -- the artist opens sales from the Artist tab.
--
-- BEGIN/COMMIT are explicit: psql -f does NOT wrap a file in a transaction
-- (learning #340), so without them a failed guard would leave a partial flip.

BEGIN;

DO $$
DECLARE
    expected CONSTANT TEXT[][] := ARRAY[
        ['face_detail_lucky_coin',     '1.65'],
        ['face_detail_lucky_ears',     '1.40'],
        ['face_detail_militia_man',    '1.45'],
        ['face_eyes_sadness',          '1.55'],
        ['face_mouth_sinister_smile',  '1.55']
    ];
    -- v_sku, not sku: inside a DO block PL/pgSQL resolves a bare identifier as
    -- the VARIABLE, so `WHERE shop_items.sku = sku` is ambiguous and raises.
    -- It raised on the first real run and rolled back -- loud, which is what
    -- the explicit BEGIN/COMMIT is for. Dry-running the SELECT half against
    -- production had not exercised this UPDATE (#313).
    v_sku    TEXT;
    want     NUMERIC;
    rec      RECORD;
    flipped  INT := 0;
BEGIN
    FOR i IN 1 .. array_length(expected, 1) LOOP
        v_sku  := expected[i][1];
        want := expected[i][2]::numeric;

        SELECT cs.approved_render_scale, cs.approved_render_offset_x,
               cs.approved_render_offset_y, cs.approved_placement_revision,
               cs.status, cs.frame_count
          INTO rec
          FROM cosmetic_submissions cs
         WHERE cs.shop_sku = v_sku;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'no cosmetic_submissions row for %', v_sku;
        END IF;
        IF rec.status <> 'approved' THEN
            RAISE EXCEPTION '% is no longer approved (status=%)', v_sku, rec.status;
        END IF;
        IF rec.approved_placement_revision IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION '% approved revision moved to % since the bundle was cut - '
                            'recompile the catalog before publishing',
                            v_sku, rec.approved_placement_revision;
        END IF;
        IF ROUND(rec.approved_render_scale::numeric, 3) <> ROUND(want, 3) THEN
            RAISE EXCEPTION '% approved scale is % but the client was built with % - '
                            'recompile the catalog before publishing',
                            v_sku, rec.approved_render_scale, want;
        END IF;
        IF COALESCE(rec.approved_render_offset_x, 0) <> 0
           OR COALESCE(rec.approved_render_offset_y, 0) <> 0 THEN
            RAISE EXCEPTION '% approved offset is now (%,%) but the client was built '
                            'with (0,0) - recompile the catalog before publishing',
                            v_sku, rec.approved_render_offset_x, rec.approved_render_offset_y;
        END IF;
        IF COALESCE(rec.frame_count, 1) <> 1 THEN
            RAISE EXCEPTION '% is now animated (frame_count=%) but only a single frame '
                            'was bundled - ship every frame or none (#317)',
                            v_sku, rec.frame_count;
        END IF;

        UPDATE shop_items SET catalog_ready = TRUE
         WHERE shop_items.sku = v_sku AND catalog_ready IS DISTINCT FROM TRUE;
        flipped := flipped + 1;
    END LOOP;

    RAISE NOTICE 'post-check OK: verified and published % face sku(s)', flipped;
END $$;

-- Fails loudly if any of the five is still unpublished after the loop.
DO $$
DECLARE missing INT;
BEGIN
    SELECT COUNT(*) INTO missing
      FROM shop_items
     WHERE kind = 'face'
       AND sku IN ('face_detail_lucky_coin', 'face_detail_lucky_ears',
                   'face_detail_militia_man', 'face_eyes_sadness',
                   'face_mouth_sinister_smile')
       AND catalog_ready IS DISTINCT FROM TRUE;
    IF missing <> 0 THEN
        RAISE EXCEPTION '% of the five faces are still not catalog_ready', missing;
    END IF;
    RAISE NOTICE 'post-check OK: all five faces are catalog_ready';
END $$;

COMMIT;
