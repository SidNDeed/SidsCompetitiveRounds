-- 153: Release the two community face cosmetics bundled in v1.34.5.
--
-- Ballooniphones and Soda Helm were approved in the artist review workflow but
-- their art lives only in cosmetic_submissions.png_data until a client release
-- compiles it into CustomCosmetics.Catalog. v1.34.5 ships both PNGs and their
-- approved placements, so they can finally be revealed (learning #163/#164).
--
-- GUARD: abort unless the approved placement still equals exactly what was
-- compiled into the client. If the artist submitted a newer revision after the
-- bundle was cut, publishing here would advertise a placement the shipped art
-- does not render (learning #165's three-state invariant).
--
-- catalog_ready flip only. released_at and published_placement_revision are
-- stamped by migration 148's trigger; stock_limit stays -1 so the artist opens
-- sales themselves from the Artist tab.

DO $$
DECLARE
    bad INTEGER;
BEGIN
    SELECT COUNT(*) INTO bad
      FROM cosmetic_submissions
     WHERE shop_sku = 'face_detail_ballooniphones'
       AND NOT (status = 'approved'
                AND approved_placement_revision = 1
                AND ROUND(approved_render_scale::numeric, 3) = 1.700
                AND ROUND(approved_render_offset_x::numeric, 3) = -0.192
                AND ROUND(approved_render_offset_y::numeric, 3) = 2.112);
    IF bad > 0 THEN
        RAISE EXCEPTION 'face_detail_ballooniphones approved placement changed since the v1.34.5 bundle was cut - do not publish';
    END IF;

    SELECT COUNT(*) INTO bad
      FROM cosmetic_submissions
     WHERE shop_sku = 'face_detail_soda_helm'
       AND NOT (status = 'approved'
                AND approved_placement_revision = 1
                AND ROUND(approved_render_scale::numeric, 3) = 1.300
                AND ROUND(approved_render_offset_x::numeric, 3) = -0.096
                AND ROUND(approved_render_offset_y::numeric, 3) = 2.400);
    IF bad > 0 THEN
        RAISE EXCEPTION 'face_detail_soda_helm approved placement changed since the v1.34.5 bundle was cut - do not publish';
    END IF;
END $$;

UPDATE shop_items
   SET catalog_ready = TRUE
 WHERE sku IN ('face_detail_ballooniphones', 'face_detail_soda_helm')
   AND catalog_ready IS NOT TRUE;
