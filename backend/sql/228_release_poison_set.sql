-- 228: Release the Poison face set (v1.39.0 ship step 3b).
-- Flips catalog_ready for the three skus whose art this release compiles
-- into CustomCosmetics. Guarded per sku: abort if the artist submitted a
-- NEWER placement revision after the bundle was cut (the compiled Scale/
-- Offset would no longer match what was approved — #165's three-state
-- rule). The migration-148 trigger stamps released_at +
-- published_placement_revision when catalog_ready flips; never by hand.

BEGIN;

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT cs.shop_sku, cs.approved_placement_revision, cs.placement_revision
          FROM cosmetic_submissions cs
         WHERE cs.shop_sku IN ('face_eyes_poison_s_eyes',
                               'face_mouth_poison_s_mouth',
                               'face_detail_poison_s_weeping')
           AND cs.status = 'approved'
    LOOP
        IF r.approved_placement_revision IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION 'sku % approved revision moved to % (bundle compiled rev 1) — recut the bundle',
                r.shop_sku, r.approved_placement_revision;
        END IF;
    END LOOP;
    IF (SELECT COUNT(*) FROM cosmetic_submissions
         WHERE shop_sku IN ('face_eyes_poison_s_eyes',
                            'face_mouth_poison_s_mouth',
                            'face_detail_poison_s_weeping')
           AND status = 'approved') <> 3 THEN
        RAISE EXCEPTION 'expected 3 approved Poison-set submissions';
    END IF;
END $$;

UPDATE shop_items
   SET catalog_ready = TRUE
 WHERE sku IN ('face_eyes_poison_s_eyes',
               'face_mouth_poison_s_mouth',
               'face_detail_poison_s_weeping')
   AND catalog_ready IS NOT TRUE;

COMMIT;
