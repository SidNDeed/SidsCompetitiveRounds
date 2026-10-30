-- rollback_395_release_five_faces_v1410.sql
-- Reverses migration 395 for exactly its five faces (submissions 69-73,
-- shop items 359, 358, 569, 570, 571). Run ONLY to undo 395, for example when
-- the v1.41.0 release that carries their art is withdrawn, so the shop stops
-- offering art the latest client cannot render. Data only. NOT a
-- release-train migration.
--
-- What it restores is the measured pre-image of 2026-10-30: catalog_ready
-- FALSE, released_at NULL, stock_limit -1 (closed: learning #163's reset for
-- an opened-but-unbundled row), and published_placement_revision 0 on the
-- submission. The 148 trigger acts only on a false -> true flip, so the
-- unpublish writes all four itself. Owned copies are NOT touched: the count
-- is printed, and an owner keeps the item (it renders again once a release
-- carrying the art is latest and 395 is reapplied).
--
-- EVERY DECISION IS TOTAL. Per row the state must be 395's post-image
-- (catalog_ready TRUE: unpublish, exactly one row per UPDATE) or the
-- pre-image (catalog_ready FALSE, released_at NULL, published 0: no-op);
-- anything else RAISEs, so a rerun is a no-op.
--
-- `psql -f` does not wrap a file in a transaction, so this file does (#340).

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $$
DECLARE
    -- [submission_id, shop_item_id, sku]
    expected CONSTANT TEXT[][] := ARRAY[
        ['69', '359', 'face_detail_gold_headband'],
        ['70', '358', 'face_detail_orbit'],
        ['71', '569', 'face_detail_pumpking_hat'],
        ['72', '570', 'face_detail_leafy_mushroom'],
        ['73', '571', 'face_detail_red_scarf']
    ];
    v_sub    BIGINT;
    v_shop   BIGINT;
    v_sku    TEXT;
    si_rec   RECORD;
    cs_rec   RECORD;
    k        BIGINT;
    owners   BIGINT;
    undone   INT := 0;
    already  INT := 0;
    pre      INT;
BEGIN
    FOR i IN 1 .. array_length(expected, 1) LOOP
        v_sub  := CAST(expected[i][1] AS BIGINT);
        v_shop := CAST(expected[i][2] AS BIGINT);
        v_sku  := expected[i][3];

        SELECT si.sku, si.kind, si.catalog_ready, si.released_at, si.stock_limit
          INTO si_rec
          FROM shop_items si
         WHERE si.id = v_shop;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'rollback 395: no shop_items row id=% (%)', v_shop, v_sku;
        END IF;
        IF si_rec.sku IS DISTINCT FROM v_sku OR si_rec.kind IS DISTINCT FROM 'face' THEN
            RAISE EXCEPTION 'rollback 395: shop item % is (%, %) - expected (%, face)',
                            v_shop, si_rec.sku, si_rec.kind, v_sku;
        END IF;

        SELECT cs.shop_sku, cs.published_placement_revision
          INTO cs_rec
          FROM cosmetic_submissions cs
         WHERE cs.id = v_sub;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'rollback 395: no cosmetic_submissions row id=% (%)', v_sub, v_sku;
        END IF;
        IF cs_rec.shop_sku IS DISTINCT FROM v_sku THEN
            RAISE EXCEPTION 'rollback 395: submission % carries sku %, expected %',
                            v_sub, cs_rec.shop_sku, v_sku;
        END IF;

        IF si_rec.catalog_ready IS FALSE THEN
            IF si_rec.released_at IS NOT NULL
               OR cs_rec.published_placement_revision IS DISTINCT FROM 0 THEN
                RAISE EXCEPTION 'rollback 395: % is unpublished but not at the pre-image '
                                '(released_at %, published revision %) - refusing',
                                v_sku, si_rec.released_at, cs_rec.published_placement_revision;
            END IF;
            already := already + 1;            -- pre-image: rerun no-op
        ELSIF si_rec.catalog_ready IS TRUE THEN
            SELECT COUNT(*) INTO owners FROM player_items pi WHERE pi.item_id = v_shop;
            RAISE NOTICE 'rollback 395: % has % owned cop(ies), left untouched; stock_limit was %',
                         v_sku, owners, si_rec.stock_limit;

            UPDATE shop_items
               SET catalog_ready = FALSE,
                   released_at   = NULL,
                   stock_limit   = -1
             WHERE shop_items.id = v_shop
               AND shop_items.sku = v_sku
               AND shop_items.catalog_ready IS TRUE;
            GET DIAGNOSTICS k = ROW_COUNT;
            IF k IS DISTINCT FROM CAST(1 AS BIGINT) THEN
                RAISE EXCEPTION 'rollback 395: unpublishing % touched % rows, expected 1', v_sku, k;
            END IF;

            UPDATE cosmetic_submissions
               SET published_placement_revision = 0
             WHERE cosmetic_submissions.id = v_sub
               AND cosmetic_submissions.shop_sku = v_sku;
            GET DIAGNOSTICS k = ROW_COUNT;
            IF k IS DISTINCT FROM CAST(1 AS BIGINT) THEN
                RAISE EXCEPTION 'rollback 395: resetting % published revision touched % rows, '
                                'expected 1', v_sku, k;
            END IF;
            undone := undone + 1;
        ELSE
            RAISE EXCEPTION 'rollback 395: % catalog_ready is NULL - refusing', v_sku;
        END IF;
    END LOOP;

    SELECT COUNT(*) INTO pre
      FROM unnest(ARRAY[69, 70, 71, 72, 73], ARRAY[359, 358, 569, 570, 571]) AS e(sub_id, shop_id)
      JOIN shop_items si            ON si.id = e.shop_id
      JOIN cosmetic_submissions cs  ON cs.id = e.sub_id AND cs.shop_sku = si.sku
     WHERE si.catalog_ready IS FALSE
       AND si.released_at IS NULL
       AND cs.published_placement_revision IS NOT DISTINCT FROM 0;
    IF pre IS DISTINCT FROM 5 THEN
        RAISE EXCEPTION 'rollback 395: post-check FAILED: % of 5 faces back at the pre-image '
                        '(undone %, already %)', pre, undone, already;
    END IF;
    RAISE NOTICE 'rollback 395: post-check OK: 5 of 5 faces unpublished (undone %, already %)',
                 undone, already;
END $$;

COMMIT;
