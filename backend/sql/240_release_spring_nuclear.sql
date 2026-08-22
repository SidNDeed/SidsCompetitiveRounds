-- 240: Release "Seasonal Spring" + "Nuclear glasses" (v1.39.1 ship step 3b).
-- Flips catalog_ready for the two skus whose art this release compiles into
-- CustomCosmetics. Guarded per sku on the EXACT approved placement revision
-- the bundle was cut from (seasonal_spring rev 2, nuclear_glasses rev 1) —
-- abort if the artist submitted a newer placement after the cut (#165's
-- three-state rule). The migration-148 trigger stamps released_at +
-- published_placement_revision when catalog_ready flips; never by hand.
-- Apply order: with the v1.39.1 ship deploy, AFTER the GitHub release that
-- carries the art (flip-early = green swatch on old clients, #163).

BEGIN;

DO $$
DECLARE
    r RECORD;
    expected_rev INTEGER;
BEGIN
    FOR r IN
        SELECT cs.shop_sku, cs.approved_placement_revision, cs.placement_revision
          FROM cosmetic_submissions cs
         WHERE cs.shop_sku IN ('face_detail_seasonal_spring',
                               'face_eyes_nuclear_glasses')
           AND cs.status = 'approved'
    LOOP
        expected_rev := CASE r.shop_sku
                          WHEN 'face_detail_seasonal_spring' THEN 2
                          WHEN 'face_eyes_nuclear_glasses'   THEN 1
                        END;
        IF r.approved_placement_revision IS DISTINCT FROM expected_rev THEN
            RAISE EXCEPTION 'sku % approved revision moved to % (bundle compiled rev %) — recut the bundle',
                r.shop_sku, r.approved_placement_revision, expected_rev;
        END IF;
    END LOOP;
    IF (SELECT COUNT(*) FROM cosmetic_submissions
         WHERE shop_sku IN ('face_detail_seasonal_spring',
                            'face_eyes_nuclear_glasses')
           AND status = 'approved') <> 2 THEN
        RAISE EXCEPTION 'expected 2 approved submissions for the v1.39.1 cosmetic release';
    END IF;
END $$;

UPDATE shop_items
   SET catalog_ready = TRUE
 WHERE sku IN ('face_detail_seasonal_spring',
               'face_eyes_nuclear_glasses')
   AND catalog_ready IS NOT TRUE;

-- Verification: both rows ready, released_at stamped by the trigger.
SELECT sku, catalog_ready, released_at IS NOT NULL AS released_stamped
  FROM shop_items
 WHERE sku IN ('face_detail_seasonal_spring', 'face_eyes_nuclear_glasses')
 ORDER BY sku;

COMMIT;
