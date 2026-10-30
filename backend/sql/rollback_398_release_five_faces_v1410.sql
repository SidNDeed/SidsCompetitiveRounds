-- rollback_398_release_five_faces_v1410.sql
-- Reverses migration 398 for exactly its five faces (submissions 69-73,
-- shop items 359, 358, 569, 570, 571), and ONLY where 398's publication is
-- still the one in place. Run it to undo 398, for example when the v1.41.0
-- release that carries their art is withdrawn, so the shop stops offering
-- art the latest client cannot render. Data only. NOT a release-train
-- migration.
--
-- PROVENANCE. 398 recorded, per row, what it wrote
-- (shop_item_release_provenance, migration '398'): the release timestamp
-- the trigger stamped, the published placement revision, the minimum client
-- version, and the description before and after. A row is reverted only
-- while it is live and still carries that release timestamp, that published
-- revision and that minimum. A row whose values differ was published again
-- by a person (a revision 2, a re-publish after an earlier rollback): it is
-- LEFT ALONE and named in a NOTICE, with its provenance row kept. A row with
-- no 398 provenance row is not 398's to undo: left alone, named in a NOTICE
-- unless it is already at the pre-image (the rerun case).
--
-- WHAT A REVERT WRITES: catalog_ready FALSE, released_at NULL,
-- min_client_version NULL, published_placement_revision 0 on the
-- submission, and the description back to the placeholder only when it is
-- still the text 398 wrote (an artist's later description stays). One write
-- is not 398's own: stock_limit -1 (closed). Unpublished art must not stay
-- on sale (learning #163's reset for an opened-but-unbundled row); the old
-- stock is printed. Owned copies are NOT touched: the count is printed, and
-- an owner keeps the item (it renders again once a release carrying the art
-- is latest and 398 is reapplied). The provenance row is deleted, so a
-- rerun is a no-op and 398 can be applied again.
--
-- LOCK FIRST, THEN COMPARE. The DO's first statements lock every row it
-- may restore or delete -- the five shop_items rows, the five submissions
-- and their 398 provenance rows -- FOR NO KEY UPDATE, in id order,
-- shop_items first (398's order), and holds them to COMMIT. Every
-- comparison against the provenance row therefore reads committed values
-- that cannot change before the revert that acts on them: a publication
-- by a person that commits while this file waits is seen and LEFT ALONE,
-- never reverted or aborted on an earlier reading. A writer that holds one
-- of the rows longer than lock_timeout (5 s) aborts this file whole,
-- changing nothing; rerun it.
--
-- `psql -f` does not wrap a file in a transaction, so this file does (#340).
-- Lock bound (learning #1072): wait 5 s; hold 25 s + 5 s plus the COMMIT's
-- local completion.

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
    pv_rec   RECORD;
    k        BIGINT;
    owners   BIGINT;
    undone   INT := 0;
    already  INT := 0;
    kept     INT := 0;
    undone_ids BIGINT[] := ARRAY[]::BIGINT[];
    pre      INT;
BEGIN
    -- Lock first, then compare (see the header).
    PERFORM 1 FROM shop_items si
     WHERE si.id IN (SELECT CAST(expected[j][2] AS BIGINT)
                       FROM generate_subscripts(expected, 1) AS j)
     ORDER BY si.id
       FOR NO KEY UPDATE;
    PERFORM 1 FROM cosmetic_submissions cs
     WHERE cs.id IN (SELECT CAST(expected[j][1] AS BIGINT)
                       FROM generate_subscripts(expected, 1) AS j)
     ORDER BY cs.id
       FOR NO KEY UPDATE;
    PERFORM 1 FROM shop_item_release_provenance p
     WHERE p.migration = '398'
       AND p.shop_item_id IN (SELECT CAST(expected[j][2] AS BIGINT)
                                FROM generate_subscripts(expected, 1) AS j)
     ORDER BY p.shop_item_id
       FOR NO KEY UPDATE;

    FOR i IN 1 .. array_length(expected, 1) LOOP
        v_sub  := CAST(expected[i][1] AS BIGINT);
        v_shop := CAST(expected[i][2] AS BIGINT);
        v_sku  := expected[i][3];

        SELECT si.sku, si.kind, si.catalog_ready, si.released_at, si.stock_limit,
               si.min_client_version, si.description
          INTO si_rec
          FROM shop_items si
         WHERE si.id = v_shop;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'rollback 398: no shop_items row id=% (%)', v_shop, v_sku;
        END IF;
        IF si_rec.sku IS DISTINCT FROM v_sku OR si_rec.kind IS DISTINCT FROM 'face' THEN
            RAISE EXCEPTION 'rollback 398: shop item % is (%, %) - expected (%, face)',
                            v_shop, si_rec.sku, si_rec.kind, v_sku;
        END IF;

        SELECT cs.shop_sku, cs.published_placement_revision
          INTO cs_rec
          FROM cosmetic_submissions cs
         WHERE cs.id = v_sub;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'rollback 398: no cosmetic_submissions row id=% (%)', v_sub, v_sku;
        END IF;
        IF cs_rec.shop_sku IS DISTINCT FROM v_sku THEN
            RAISE EXCEPTION 'rollback 398: submission % carries sku %, expected %',
                            v_sub, cs_rec.shop_sku, v_sku;
        END IF;

        SELECT p.submission_id, p.released_at, p.published_revision, p.min_client_version,
               p.description_before, p.description_written
          INTO pv_rec
          FROM shop_item_release_provenance p
         WHERE p.migration = '398' AND p.shop_item_id = v_shop;

        IF NOT FOUND THEN
            IF si_rec.catalog_ready IS FALSE AND si_rec.released_at IS NULL
               AND si_rec.min_client_version IS NULL
               AND cs_rec.published_placement_revision IS NOT DISTINCT FROM 0 THEN
                already := already + 1;        -- pre-image: rerun no-op
            ELSE
                kept := kept + 1;
                RAISE NOTICE 'rollback 398: % LEFT ALONE - no 398 provenance row, so its '
                             'current state (catalog_ready %, released_at %, published revision '
                             '%, minimum %) is not 398''s to undo', v_sku, si_rec.catalog_ready,
                             si_rec.released_at, cs_rec.published_placement_revision,
                             si_rec.min_client_version;
            END IF;
            CONTINUE;
        END IF;

        IF pv_rec.submission_id IS DISTINCT FROM v_sub
           OR si_rec.catalog_ready IS NOT TRUE
           OR si_rec.released_at IS DISTINCT FROM pv_rec.released_at
           OR cs_rec.published_placement_revision IS DISTINCT FROM pv_rec.published_revision
           OR si_rec.min_client_version IS DISTINCT FROM pv_rec.min_client_version THEN
            kept := kept + 1;
            RAISE NOTICE 'rollback 398: % LEFT ALONE - it no longer carries what 398 wrote: '
                         'catalog_ready % (398: true), released_at % (398: %), published '
                         'revision % (398: %), minimum % (398: %)', v_sku,
                         si_rec.catalog_ready, si_rec.released_at, pv_rec.released_at,
                         cs_rec.published_placement_revision, pv_rec.published_revision,
                         si_rec.min_client_version, pv_rec.min_client_version;
            CONTINUE;
        END IF;

        SELECT COUNT(*) INTO owners FROM player_items pi WHERE pi.item_id = v_shop;
        RAISE NOTICE 'rollback 398: % has % owned cop(ies), left untouched; stock_limit was %',
                     v_sku, owners, si_rec.stock_limit;
        IF pv_rec.description_written IS NOT NULL
           AND si_rec.description IS DISTINCT FROM pv_rec.description_written THEN
            RAISE NOTICE 'rollback 398: % description was changed after 398; kept as is', v_sku;
        END IF;

        UPDATE shop_items
           SET catalog_ready      = FALSE,
               released_at        = NULL,
               stock_limit        = -1,
               min_client_version = NULL,
               description        = CASE
                   WHEN pv_rec.description_written IS NOT NULL
                        AND shop_items.description IS NOT DISTINCT FROM pv_rec.description_written
                   THEN pv_rec.description_before
                   ELSE shop_items.description END
         WHERE shop_items.id = v_shop
           AND shop_items.sku = v_sku
           AND shop_items.catalog_ready IS TRUE
           AND shop_items.released_at IS NOT DISTINCT FROM pv_rec.released_at
           AND shop_items.min_client_version IS NOT DISTINCT FROM pv_rec.min_client_version;
        GET DIAGNOSTICS k = ROW_COUNT;
        IF k IS DISTINCT FROM CAST(1 AS BIGINT) THEN
            RAISE EXCEPTION 'rollback 398: unpublishing % touched % rows, expected 1', v_sku, k;
        END IF;

        UPDATE cosmetic_submissions
           SET published_placement_revision = 0
         WHERE cosmetic_submissions.id = v_sub
           AND cosmetic_submissions.shop_sku = v_sku
           AND cosmetic_submissions.published_placement_revision
               IS NOT DISTINCT FROM pv_rec.published_revision;
        GET DIAGNOSTICS k = ROW_COUNT;
        IF k IS DISTINCT FROM CAST(1 AS BIGINT) THEN
            RAISE EXCEPTION 'rollback 398: resetting % published revision touched % rows, '
                            'expected 1', v_sku, k;
        END IF;

        DELETE FROM shop_item_release_provenance p
         WHERE p.migration = '398' AND p.shop_item_id = v_shop;
        GET DIAGNOSTICS k = ROW_COUNT;
        IF k IS DISTINCT FROM CAST(1 AS BIGINT) THEN
            RAISE EXCEPTION 'rollback 398: clearing % provenance removed % rows, expected 1',
                            v_sku, k;
        END IF;
        undone := undone + 1;
        undone_ids := undone_ids || v_shop;
    END LOOP;

    -- Post-check over the rows THIS run reverted: each is back at the
    -- pre-image with no 398 provenance row.
    SELECT COUNT(*) INTO pre
      FROM unnest(ARRAY[69, 70, 71, 72, 73], ARRAY[359, 358, 569, 570, 571]) AS e(sub_id, shop_id)
      JOIN shop_items si            ON si.id = e.shop_id
      JOIN cosmetic_submissions cs  ON cs.id = e.sub_id AND cs.shop_sku = si.sku
     WHERE si.id = ANY(undone_ids)
       AND si.catalog_ready IS FALSE
       AND si.released_at IS NULL
       AND si.min_client_version IS NULL
       AND cs.published_placement_revision IS NOT DISTINCT FROM 0
       AND NOT EXISTS (SELECT 1 FROM shop_item_release_provenance p
                        WHERE p.migration = '398' AND p.shop_item_id = si.id);
    IF pre IS DISTINCT FROM undone THEN
        RAISE EXCEPTION 'rollback 398: post-check FAILED: % of % reverted faces back at the '
                        'pre-image', pre, undone;
    END IF;
    RAISE NOTICE 'rollback 398: post-check OK: undone %, already at the pre-image %, left alone %',
                 undone, already, kept;
END $$;

COMMIT;
