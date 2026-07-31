-- 172: publish Tattered Cape placement revision 2 (shipped in client v1.35.3).
--
-- The artist proposed a larger render scale, an admin approved it, and the
-- approved snapshot (scale 2.15, offset 0/-0.1) is now compiled verbatim into
-- plugin/CustomCosmetics.cs. This migration advances the PUBLISHED revision so
-- the three-state placement invariant (#165) stays honest: proposed ->
-- approved -> published, where published means "these exact values are in a
-- shipped client".
--
-- The art itself is unchanged (png md5 254dc7de6e2d35f84a0452a9b2c272a4 equals
-- the repo's plugin/cosmetics/detail_tattered_cape.png), and the item is
-- already catalog_ready from its original release, so nothing else moves.
--
-- GUARDED: only stamps when the approved revision is still exactly 2 with the
-- values that were compiled. If the artist submitted a newer revision after
-- this bundle was cut, the UPDATE matches nothing and the post-check RAISEs —
-- shipping a stale placement silently is the failure this guard exists for.

-- NOTE: approved_render_scale is `real` (float4), so `= 2.15` is ALWAYS FALSE
-- against the numeric literal 2.15 (float4 2.15 widens to 2.1500000953674316).
-- The first cut of this migration used equality and the guard tripped on
-- correct data. Compare with a tolerance; never test a float column for
-- exact equality in a shipping guard.
UPDATE cosmetic_submissions
   SET published_placement_revision = 2
 WHERE shop_sku = 'face_detail_tattered_cape'
   AND status = 'approved'
   AND approved_placement_revision = 2
   AND abs(approved_render_scale - 2.15) < 0.0001
   AND published_placement_revision < 2;

DO $$
DECLARE
    v_pub INTEGER;
    v_app INTEGER;
    v_scale NUMERIC;
BEGIN
    SELECT published_placement_revision, approved_placement_revision, approved_render_scale
      INTO v_pub, v_app, v_scale
      FROM cosmetic_submissions
     WHERE shop_sku = 'face_detail_tattered_cape';

    IF v_pub IS NULL THEN
        RAISE EXCEPTION 'post-check FAILED: no cosmetic_submissions row for face_detail_tattered_cape';
    END IF;

    IF v_pub <> v_app THEN
        RAISE EXCEPTION
            'post-check FAILED: published=% approved=% scale=% — the approved placement is not what v1.35.3 compiled (2.15). Do NOT ship this bundle; re-cut it against the current approved snapshot.',
            v_pub, v_app, v_scale;
    END IF;

    RAISE NOTICE 'post-check OK: Tattered Cape published revision % (scale %)', v_pub, v_scale;
END $$;
