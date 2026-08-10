-- 211: Release face_detail_twisted_topper (v1.38.1 client bundles the PNG).
--
-- Flips catalog_ready for the one approved-but-unbundled cosmetic compiled
-- into this release's CustomCosmetics catalog (Scale 1.3, offset 0,0 from
-- the approved_* columns; png md5 cb85a0a18334670396f30cf513883b51).
-- The migration-148 trigger stamps released_at + published_placement_revision
-- when catalog_ready flips — never set them by hand (#183).
--
-- GUARD (#165/#183): abort if the artist advanced the approved placement
-- after this bundle was cut — shipping rev-1 art under a rev-2 placement
-- would render at the wrong size vs what the artist previewed.

DO $$
DECLARE
    rev INTEGER;
BEGIN
    SELECT approved_placement_revision INTO rev
      FROM cosmetic_submissions
     WHERE shop_sku = 'face_detail_twisted_topper' AND status = 'approved';
    IF rev IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'migration 211: approved placement revision is % (bundle compiled rev 1) — re-cut the bundle', rev;
    END IF;
END $$;

UPDATE shop_items
   SET catalog_ready = TRUE
 WHERE sku = 'face_detail_twisted_topper'
   AND catalog_ready IS NOT TRUE;

DO $$
BEGIN
    RAISE NOTICE 'migration 211: face_detail_twisted_topper released (post-check OK)';
END $$;
