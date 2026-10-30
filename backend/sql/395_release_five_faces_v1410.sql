-- 395: publish the five approved community faces bundled into the v1.41.0
-- client. (Numbered 395 because 391-394 are reserved by other lanes.)
--
-- DO NOT APPLY BEFORE THE RELEASE THAT SHIPS THE ART (learnings #163/#164):
-- catalog_ready=TRUE makes an item visible, giftable and purchasable, and a
-- client can only render it once CustomCosmetics.Catalog carries the
-- CosmeticDef and the LATEST GitHub release's cosmetics.zip carries the PNG.
-- Apply AFTER the v1.41.0 GitHub release (with cosmetics.zip) exists.
--
-- WHAT WAS COMPILED (read on the primary 2026-10-30 through the read-only
-- verb; each PNG extracted from cosmetic_submissions.png_data in 48-char
-- base64 chunks and written only after md5(png_data), png_bytes, the PNG
-- signature and a 512x512 IHDR matched):
--
--   sub  shop  sku                         bytes  md5                               scale  rev  frames
--   69   359   face_detail_gold_headband   24429  4242409ce643ec451420cf1976688506  1.45   1    1
--   70   358   face_detail_orbit           34839  412974a31b7569bd2a04275293b30787  1.60   1    1
--   71   569   face_detail_pumpking_hat    51759  06c4235ba87bf61cdb613169eee2c86c  1.40   1    1
--   72   570   face_detail_leafy_mushroom  23257  9e9b0421902c33077ca42c8bcea28882  1.30   1    1
--   73   571   face_detail_red_scarf       21241  6d43a388354876aabaf3808582832fbd  1.60   1    1
--
-- All five: slot detail, rarity rare, price 750, stock_limit -1, approved
-- offset (0,0), static (frame_count 1, anim_fps NULL). Scales and offsets come
-- from the approved_* snapshot only (#165).
--
-- Rows are keyed by BOTH ids (cosmetic_submissions.id and shop_items.id) and
-- the sku must agree with each. The guard RAISES (whole transaction) if any
-- approved value, or the stored art itself (md5 + byte count), moved between
-- bundle-cut and publish. released_at and published_placement_revision are
-- stamped by the migration-148 trigger (trg_shop_item_catalog_release, live
-- on the primary 2026-10-30) on the false -> true flip; stock stays closed
-- until the artist opens sales.
--
-- EVERY DECISION IS TOTAL (IS TRUE / IS FALSE / IS NOT DISTINCT FROM; a NULL
-- in any operand refuses). Per row the state must be EXACTLY the measured
-- pre-image (catalog_ready FALSE: flip it, exactly one row) or this file's
-- post-image (catalog_ready TRUE: no-op), so a rerun is a no-op. The
-- post-check at the end of the block requires all five live, stamped and
-- published at revision 1. Rollback: rollback_395_release_five_faces_v1410.sql.
--
-- `psql -f` does not wrap a file in a transaction, so this file does (#340).

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $$
DECLARE
    -- [submission_id, shop_item_id, sku, approved_scale, png_bytes, md5]
    expected CONSTANT TEXT[][] := ARRAY[
        ['69', '359', 'face_detail_gold_headband',  '1.45', '24429', '4242409ce643ec451420cf1976688506'],
        ['70', '358', 'face_detail_orbit',          '1.60', '34839', '412974a31b7569bd2a04275293b30787'],
        ['71', '569', 'face_detail_pumpking_hat',   '1.40', '51759', '06c4235ba87bf61cdb613169eee2c86c'],
        ['72', '570', 'face_detail_leafy_mushroom', '1.30', '23257', '9e9b0421902c33077ca42c8bcea28882'],
        ['73', '571', 'face_detail_red_scarf',      '1.60', '21241', '6d43a388354876aabaf3808582832fbd']
    ];
    want_rev  CONSTANT INT := 1;
    -- v_ prefixes, never bare column names (#442: a bare identifier resolves
    -- as the PL/pgSQL variable and makes a WHERE ambiguous).
    v_sub     BIGINT;
    v_shop    BIGINT;
    v_sku     TEXT;
    v_scale   NUMERIC;
    v_bytes   INT;
    v_md5     TEXT;
    cs_rec    RECORD;
    si_rec    RECORD;
    k         BIGINT;
    flipped   INT := 0;
    already   INT := 0;
    live      INT;
BEGIN
    FOR i IN 1 .. array_length(expected, 1) LOOP
        v_sub   := CAST(expected[i][1] AS BIGINT);
        v_shop  := CAST(expected[i][2] AS BIGINT);
        v_sku   := expected[i][3];
        v_scale := CAST(expected[i][4] AS NUMERIC);
        v_bytes := CAST(expected[i][5] AS INT);
        v_md5   := expected[i][6];

        SELECT cs.shop_sku, cs.status, cs.slot,
               cs.approved_render_scale, cs.approved_render_offset_x,
               cs.approved_render_offset_y, cs.approved_placement_revision,
               cs.published_placement_revision, cs.frame_count,
               cs.png_bytes, md5(cs.png_data) AS art_md5
          INTO cs_rec
          FROM cosmetic_submissions cs
         WHERE cs.id = v_sub;
        IF NOT FOUND THEN
            RAISE EXCEPTION '395: no cosmetic_submissions row id=% (%)', v_sub, v_sku;
        END IF;
        IF cs_rec.shop_sku IS DISTINCT FROM v_sku THEN
            RAISE EXCEPTION '395: submission % carries sku % but the client bundled %',
                            v_sub, cs_rec.shop_sku, v_sku;
        END IF;
        IF cs_rec.status IS DISTINCT FROM 'approved' THEN
            RAISE EXCEPTION '395: % is no longer approved (status=%)', v_sku, cs_rec.status;
        END IF;
        IF cs_rec.slot IS DISTINCT FROM 'detail' THEN
            RAISE EXCEPTION '395: % slot is % but the client bundled it as detail',
                            v_sku, cs_rec.slot;
        END IF;
        IF cs_rec.approved_placement_revision IS DISTINCT FROM want_rev THEN
            RAISE EXCEPTION '395: % approved revision moved to % (client built against %) - '
                            'recompile the catalog before publishing',
                            v_sku, cs_rec.approved_placement_revision, want_rev;
        END IF;
        IF (ROUND(CAST(cs_rec.approved_render_scale AS NUMERIC), 3)
                IS NOT DISTINCT FROM ROUND(v_scale, 3)) IS NOT TRUE THEN
            RAISE EXCEPTION '395: % approved scale is % but the client was built with % - '
                            'recompile the catalog before publishing',
                            v_sku, cs_rec.approved_render_scale, v_scale;
        END IF;
        IF COALESCE(cs_rec.approved_render_offset_x, 0) <> 0
           OR COALESCE(cs_rec.approved_render_offset_y, 0) <> 0 THEN
            RAISE EXCEPTION '395: % approved offset is now (%,%) but the client was built '
                            'with (0,0) - recompile the catalog before publishing',
                            v_sku, cs_rec.approved_render_offset_x, cs_rec.approved_render_offset_y;
        END IF;
        IF COALESCE(cs_rec.frame_count, 1) <> 1 THEN
            RAISE EXCEPTION '395: % frame_count is now % but the client bundled 1 frame - '
                            'ship every frame or none (#317)', v_sku, cs_rec.frame_count;
        END IF;
        IF cs_rec.png_bytes IS DISTINCT FROM v_bytes
           OR cs_rec.art_md5 IS DISTINCT FROM v_md5 THEN
            RAISE EXCEPTION '395: % stored art is now % bytes md5 % but the client bundled '
                            '% bytes md5 % - re-extract the PNG before publishing',
                            v_sku, cs_rec.png_bytes, cs_rec.art_md5, v_bytes, v_md5;
        END IF;

        SELECT si.sku, si.kind, si.catalog_ready
          INTO si_rec
          FROM shop_items si
         WHERE si.id = v_shop;
        IF NOT FOUND THEN
            RAISE EXCEPTION '395: no shop_items row id=% (%)', v_shop, v_sku;
        END IF;
        IF si_rec.sku IS DISTINCT FROM v_sku OR si_rec.kind IS DISTINCT FROM 'face' THEN
            RAISE EXCEPTION '395: shop item % is (%, %) - expected (%, face)',
                            v_shop, si_rec.sku, si_rec.kind, v_sku;
        END IF;

        IF si_rec.catalog_ready IS TRUE THEN
            already := already + 1;            -- post-image: rerun no-op
        ELSIF si_rec.catalog_ready IS FALSE THEN
            -- Pre-image. The flip fires the 148 trigger, which stamps
            -- released_at and published_placement_revision.
            UPDATE shop_items
               SET catalog_ready = TRUE
             WHERE shop_items.id = v_shop
               AND shop_items.sku = v_sku
               AND shop_items.kind = 'face'
               AND shop_items.catalog_ready IS FALSE;
            GET DIAGNOSTICS k = ROW_COUNT;
            IF k IS DISTINCT FROM CAST(1 AS BIGINT) THEN
                RAISE EXCEPTION '395: publishing % touched % rows, expected 1', v_sku, k;
            END IF;
            flipped := flipped + 1;
        ELSE
            RAISE EXCEPTION '395: % catalog_ready is NULL - refusing', v_sku;
        END IF;
    END LOOP;

    -- Post-check: all five EXIST, are live, carry a release stamp, and their
    -- submissions are published at the bundled revision. Counting by the
    -- expected ids (not by "unpublished rows") means an absent row cannot
    -- half-publish and still pass (the 264 finding).
    SELECT COUNT(*) INTO live
      FROM unnest(ARRAY[69, 70, 71, 72, 73], ARRAY[359, 358, 569, 570, 571]) AS e(sub_id, shop_id)
      JOIN shop_items si            ON si.id = e.shop_id
      JOIN cosmetic_submissions cs  ON cs.id = e.sub_id AND cs.shop_sku = si.sku
     WHERE si.kind = 'face'
       AND si.catalog_ready IS TRUE
       AND si.released_at IS NOT NULL
       AND cs.published_placement_revision IS NOT DISTINCT FROM want_rev;
    IF live IS DISTINCT FROM 5 THEN
        RAISE EXCEPTION '395: post-check FAILED: % of 5 faces live, stamped and published '
                        '(flipped %, already live %)', live, flipped, already;
    END IF;
    RAISE NOTICE '395: post-check OK: 5 of 5 v1.41.0 faces live (flipped %, already live %)',
                 flipped, already;
END $$;

COMMIT;
