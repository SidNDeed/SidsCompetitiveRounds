-- 149_release_spooky_head_bouncers.sql — v1.34.3 cosmetic release gate
--
-- v1.34.3 bundles the first community submission that went through the artist
-- upload + admin placement review workflow. Its PNG now ships in the client
-- catalog (CustomCosmetics.Catalog, PngFile detail_spooky_head_bouncers.png)
-- at the ADMIN-APPROVED placement (scale 1.30, offset 0.113:3.665, approved
-- placement revision 1), so it can finally render and is safe to publish.
--
-- Flipping catalog_ready is the act of publishing (learning #164): the
-- stamp_shop_item_catalog_release trigger from migration 148 stamps
-- released_at and advances published_placement_revision to the approved
-- revision, so this file must NOT set either by hand.
--
-- Requires migrations 147 (catalog_ready) and 148 (placement columns/trigger).

BEGIN;

-- Guard: only publish art whose approved placement is exactly what this
-- release compiled into the client. If an artist submitted a NEWER revision
-- after the bundle was cut, publishing here would ship a placement that
-- disagrees with the DLL — abort instead.
DO $migration$
DECLARE
    approved_rev  INTEGER;
    approved_sc   REAL;
    approved_ox   REAL;
    approved_oy   REAL;
BEGIN
    SELECT approved_placement_revision, approved_render_scale,
           approved_render_offset_x, approved_render_offset_y
      INTO approved_rev, approved_sc, approved_ox, approved_oy
      FROM cosmetic_submissions
     WHERE shop_sku = 'face_detail_spooky_head_bouncers'
       AND status = 'approved';

    IF approved_rev IS NULL THEN
        RAISE EXCEPTION 'No approved placement for face_detail_spooky_head_bouncers';
    END IF;
    IF approved_rev <> 1
       OR round(approved_sc::numeric, 3) <> 1.300
       OR round(approved_ox::numeric, 3) <> 0.113
       OR round(approved_oy::numeric, 3) <> 3.665 THEN
        RAISE EXCEPTION
            'Approved placement (rev %, %x, %:%) does not match the values compiled into v1.34.3 (rev 1, 1.300x, 0.113:3.665) — rebundle before publishing',
            approved_rev, approved_sc, approved_ox, approved_oy;
    END IF;
END;
$migration$;

-- Publish. The 148 trigger stamps released_at + published_placement_revision.
UPDATE shop_items
   SET catalog_ready = TRUE
 WHERE sku = 'face_detail_spooky_head_bouncers'
   AND NOT catalog_ready;

-- Sales stay closed until the artist opens stock from the Artist tab, exactly
-- like every other artist item (stock_limit -1 = "not opened"). Home shows it
-- as a "coming soon!" tease in the meantime.

COMMIT;

-- Verification (run manually):
--   SELECT sku, catalog_ready, stock_limit, released_at FROM shop_items
--    WHERE sku = 'face_detail_spooky_head_bouncers';
--   SELECT approved_placement_revision, published_placement_revision
--     FROM cosmetic_submissions WHERE shop_sku = 'face_detail_spooky_head_bouncers';
