-- 247: Release the v1.39.2 community cosmetics (ship step 3b) and publish the
-- Seasonal Spring placement revision 3.
-- New (catalog_ready flips; all approved placement revision 1, offsets 0/0):
--   face_eyes_shock_shades 1.55, face_mouth_cat_mouth 1.55, face_eyes_cat_eyes
--   1.5, face_mouth_the_challenger 1.7, face_mouth_goober 1.8 - compiled
--   verbatim into CustomCosmetics.cs; PNGs pulled chunked and md5-verified.
-- Re-placement (already catalog_ready): face_detail_seasonal_spring approved
--   revision 3 (scale 1.4, art unchanged, md5 01e03dd773138ebd5c03ee6e3e8a18ba)
--   - published revision stamped by hand as in migration 172, because the
--   migration-148 trigger only stamps on the catalog_ready flip.
-- GUARDED per sku on the EXACT approved revision + scale the bundle was cut
-- from - abort if the artist moved a placement after the cut (#165). Float
-- columns are compared with a tolerance (migration 172's lesson).
-- Apply order: with the v1.39.2 ship deploy, AFTER the GitHub release that
-- carries the art (flip-early = green swatch on old clients, #163).

BEGIN;

DO $$
DECLARE
    r RECORD;
    expected_rev INTEGER;
    expected_scale NUMERIC;
BEGIN
    FOR r IN
        SELECT cs.shop_sku, cs.approved_placement_revision, cs.approved_render_scale
          FROM cosmetic_submissions cs
         WHERE cs.shop_sku IN ('face_eyes_shock_shades', 'face_mouth_cat_mouth',
                               'face_eyes_cat_eyes', 'face_mouth_the_challenger',
                               'face_mouth_goober', 'face_detail_seasonal_spring')
           AND cs.status = 'approved'
    LOOP
        expected_rev := CASE r.shop_sku
                          WHEN 'face_detail_seasonal_spring' THEN 3
                          ELSE 1
                        END;
        expected_scale := CASE r.shop_sku
                            WHEN 'face_eyes_shock_shades'      THEN 1.55
                            WHEN 'face_mouth_cat_mouth'        THEN 1.55
                            WHEN 'face_eyes_cat_eyes'          THEN 1.5
                            WHEN 'face_mouth_the_challenger'   THEN 1.7
                            WHEN 'face_mouth_goober'           THEN 1.8
                            WHEN 'face_detail_seasonal_spring' THEN 1.4
                          END;
        IF r.approved_placement_revision IS DISTINCT FROM expected_rev
           OR abs(r.approved_render_scale - expected_scale) >= 0.0001 THEN
            RAISE EXCEPTION 'sku % approved rev %/scale % differs from the bundle (rev %/scale %) - recut the bundle',
                r.shop_sku, r.approved_placement_revision, r.approved_render_scale, expected_rev, expected_scale;
        END IF;
    END LOOP;
    IF (SELECT COUNT(*) FROM cosmetic_submissions
         WHERE shop_sku IN ('face_eyes_shock_shades', 'face_mouth_cat_mouth',
                            'face_eyes_cat_eyes', 'face_mouth_the_challenger',
                            'face_mouth_goober', 'face_detail_seasonal_spring')
           AND status = 'approved') <> 6 THEN
        RAISE EXCEPTION 'expected 6 approved submissions for the v1.39.2 cosmetic release';
    END IF;
END $$;

UPDATE shop_items
   SET catalog_ready = TRUE
 WHERE sku IN ('face_eyes_shock_shades', 'face_mouth_cat_mouth',
               'face_eyes_cat_eyes', 'face_mouth_the_challenger',
               'face_mouth_goober')
   AND catalog_ready IS NOT TRUE;

UPDATE cosmetic_submissions
   SET published_placement_revision = 3
 WHERE shop_sku = 'face_detail_seasonal_spring'
   AND status = 'approved'
   AND approved_placement_revision = 3
   AND abs(approved_render_scale - 1.4) < 0.0001
   AND published_placement_revision < 3;

DO $$
DECLARE
    v_ready INTEGER;
    v_pub INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_ready FROM shop_items
     WHERE sku IN ('face_eyes_shock_shades', 'face_mouth_cat_mouth',
                   'face_eyes_cat_eyes', 'face_mouth_the_challenger',
                   'face_mouth_goober')
       AND catalog_ready AND released_at IS NOT NULL;
    IF v_ready <> 5 THEN
        RAISE EXCEPTION 'post-check FAILED: % of 5 new cosmetics ready+stamped', v_ready;
    END IF;
    SELECT published_placement_revision INTO v_pub FROM cosmetic_submissions
     WHERE shop_sku = 'face_detail_seasonal_spring' AND status = 'approved';
    IF v_pub IS DISTINCT FROM 3 THEN
        RAISE EXCEPTION 'post-check FAILED: Seasonal Spring published revision is %, expected 3', v_pub;
    END IF;
    RAISE NOTICE 'post-check OK: 5 cosmetics released, Seasonal Spring rev 3 published';
END $$;

COMMIT;
