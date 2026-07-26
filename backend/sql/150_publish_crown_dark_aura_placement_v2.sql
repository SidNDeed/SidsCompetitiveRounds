-- 150_publish_crown_dark_aura_placement_v2.sql — v1.34.4
--
-- Marks placement revision 2 as PUBLISHED for two already-shipped cosmetics
-- whose art is unchanged but whose approved Scale/Offset moved. Fixes the
-- complaint in bug #84 ("approved cosmetic adjustments were not included in
-- v1.34.3") — the values below are compiled into CustomCosmetics.cs in the
-- SAME release that applies this migration.
--
-- Why this can't rely on migration 148's trigger: that trigger stamps
-- released_at + published_placement_revision when catalog_ready FLIPS to true.
-- Both of these SKUs are already catalog_ready, so nothing flips and nothing
-- would ever advance published_placement_revision — the row would stay
-- "pending release" forever and keep reappearing in every future ship's
-- release-candidate query (learning #183: a column nothing writes hard-blocks
-- the release it gates).
--
-- Guarded: if an artist has submitted and had approved a NEWER revision since
-- this bundle was cut, the compiled client no longer matches the DB and this
-- aborts rather than silently claiming the wrong placement is live.

DO $$
DECLARE
    bad_count INT;
BEGIN
    -- Every (sku, scale, offset_x, offset_y, revision) below must match exactly
    -- what CustomCosmetics.cs now carries. Compare with a tolerance because the
    -- client stores float32 and the column is double precision.
    SELECT COUNT(*) INTO bad_count
      FROM (VALUES
              ('face_detail_crown',     1.60::numeric, -0.028::numeric, 4.499::numeric, 2),
              ('face_detail_dark_aura', 2.25::numeric,  0.032::numeric, 1.170::numeric, 2)
           ) AS expected(sku, scale, ox, oy, rev)
      JOIN cosmetic_submissions cs ON cs.shop_sku = expected.sku
     WHERE cs.status <> 'approved'
        OR cs.approved_placement_revision IS DISTINCT FROM expected.rev
        OR ABS(cs.approved_render_scale::numeric    - expected.scale) > 0.001
        OR ABS(cs.approved_render_offset_x::numeric - expected.ox)    > 0.001
        OR ABS(cs.approved_render_offset_y::numeric - expected.oy)    > 0.001;

    IF bad_count > 0 THEN
        RAISE EXCEPTION
          'Aborting: % cosmetic(s) no longer match the placement compiled into this build. '
          'A newer revision was approved after the bundle was cut — re-bundle before releasing.',
          bad_count;
    END IF;
END $$;

UPDATE cosmetic_submissions
   SET published_placement_revision = approved_placement_revision
 WHERE shop_sku IN ('face_detail_crown', 'face_detail_dark_aura')
   AND status = 'approved'
   AND approved_placement_revision = 2;

-- Verification: both should report published = approved = 2 and drop out of
-- the release-candidate query on the next ship.
SELECT shop_sku, approved_placement_revision AS approved,
       published_placement_revision AS published,
       approved_render_scale AS scale,
       approved_render_offset_x AS ox, approved_render_offset_y AS oy
  FROM cosmetic_submissions
 WHERE shop_sku IN ('face_detail_crown', 'face_detail_dark_aura')
 ORDER BY shop_sku;
