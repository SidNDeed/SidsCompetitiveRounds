-- 175: publish the v1.35.5 community cosmetics batch.
--
-- These five were approved during the v1.35.5 ship. Their PNGs and their
-- APPROVED placement values are compiled into CustomCosmetics.Catalog in the
-- same release, so flipping catalog_ready here is what makes them visible and
-- purchasable (learning #163/#164: metadata approval is not publication, and
-- the Shop list, the Home "newest" panel and the purchase/stock/gift endpoints
-- all gate on catalog_ready).
--
-- GUARDED against the artist revising a placement after the bundle was cut.
-- The client now contains scale 1.3 / offset (0,0) for every one of these; if
-- approved_placement_revision has moved past what we published, the shipped art
-- would render at a size the artist never approved, so this ABORTS rather than
-- publishing a mismatch. Same reasoning as migration 147's allowlist RAISE
-- (#183): a gate that silently does the wrong thing is worse than a loud stop.
--
-- released_at and published_placement_revision are NOT set by hand — the
-- migration-148 trigger stamps both when catalog_ready flips.
--
-- stock_limit is deliberately left alone; the artist opens sales themselves
-- from the Artist tab, and a shipped-but-unopened item is the intended
-- "coming soon" state (#164).
--
-- Idempotent: the UPDATE is a no-op once catalog_ready is TRUE, and the guard
-- re-passes because the revisions still match.

DO $$
DECLARE
    v_bad int;
    v_missing int;
BEGIN
    -- Every sku in this batch must still be at approved revision 1, which is
    -- what CustomCosmetics.cs was built against.
    SELECT COUNT(*) INTO v_bad
      FROM cosmetic_submissions cs
     WHERE cs.shop_sku IN ('face_detail_brain_cane','face_mouth_casi_s_mouth',
                           'face_eyes_casicorn_s_eyes','face_detail_little_pink_buddy',
                           'face_detail_sniper_medal')
       AND (cs.status <> 'approved' OR cs.approved_placement_revision <> 1);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'ABORT: % of the v1.35.5 cosmetics changed approval state or placement '
                        'since the client bundle was built - rebuild the client before publishing',
                        v_bad;
    END IF;

    SELECT 5 - COUNT(*) INTO v_missing
      FROM shop_items
     WHERE sku IN ('face_detail_brain_cane','face_mouth_casi_s_mouth',
                   'face_eyes_casicorn_s_eyes','face_detail_little_pink_buddy',
                   'face_detail_sniper_medal');
    IF v_missing <> 0 THEN
        RAISE EXCEPTION 'ABORT: % of the 5 shop_items rows are missing', v_missing;
    END IF;
END $$;

UPDATE shop_items
   SET catalog_ready = TRUE
 WHERE sku IN ('face_detail_brain_cane','face_mouth_casi_s_mouth',
               'face_eyes_casicorn_s_eyes','face_detail_little_pink_buddy',
               'face_detail_sniper_medal')
   AND catalog_ready IS NOT TRUE;

DO $$
DECLARE
    v_ready int;
    v_total int;
BEGIN
    SELECT COUNT(*) FILTER (WHERE catalog_ready), COUNT(*) INTO v_ready, v_total
      FROM shop_items WHERE kind = 'face';
    RAISE NOTICE 'post-check: % of % face items catalog_ready', v_ready, v_total;
    IF (SELECT COUNT(*) FROM shop_items
         WHERE sku IN ('face_detail_brain_cane','face_mouth_casi_s_mouth',
                       'face_eyes_casicorn_s_eyes','face_detail_little_pink_buddy',
                       'face_detail_sniper_medal')
           AND catalog_ready) = 5 THEN
        RAISE NOTICE 'post-check OK: all 5 v1.35.5 cosmetics published';
    ELSE
        RAISE WARNING 'post-check FAILED: not all 5 flipped - inspect before announcing';
    END IF;
END $$;
