-- 190: publish the v1.36.0 cosmetic batch.
--
-- Two DIFFERENT shapes, and only one of them the release trigger can handle:
--
--   face_detail_spilled_icecream — brand new (approved revision 1, never
--     bundled). Flipping catalog_ready is the act of publishing, and the
--     migration-148 trigger stamps released_at + published_placement_revision
--     on the FALSE -> TRUE transition.
--
--   face_detail_rounds_cat — already live and selling since 2026-07-18. The
--     artist's approved revision 2 rescales it 1.0 -> 1.7; the art is byte
--     identical (md5 verified against png_data before the bundle was cut).
--     Its catalog_ready is ALREADY true, and the trigger is transition-guarded
--     (`NEW.catalog_ready AND NOT OLD.catalog_ready`), so it cannot fire here.
--     published_placement_revision must therefore be advanced EXPLICITLY, or
--     the row reappears in the pending-release query at every future ship and
--     the client keeps rendering a placement the admin already superseded.
--
-- Both values below were compiled into plugin/CustomCosmetics.cs from the
-- approved_* columns verbatim (learnings #164/#165). The guards abort if the
-- artist has submitted and had approved a NEWER placement since the bundle was
-- built — in that case the shipped DLL and the DB would disagree about how the
-- item renders, and the correct move is to rebuild the bundle, not to publish.
--
-- Idempotent statement-by-statement: the deploy wrapper re-executes the whole
-- file when its first `psql -f` attempt fails, so a rerun must be a no-op
-- (learning #243).

BEGIN;

-- Guard 1: the new item's approved placement must still be what was compiled.
DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n
    FROM cosmetic_submissions
    WHERE shop_sku = 'face_detail_spilled_icecream'
      AND status = 'approved'
      AND approved_placement_revision = 1
      AND ROUND(approved_render_scale::numeric, 4) = 1.3000
      AND ROUND(approved_render_offset_x::numeric, 4) = 0.0000
      AND ROUND(approved_render_offset_y::numeric, 4) = 0.0000;
    IF n <> 1 THEN
        RAISE EXCEPTION
            'face_detail_spilled_icecream approved placement no longer matches the compiled bundle (expected revision 1, scale 1.3, offset 0/0). Rebuild the bundle before publishing.';
    END IF;
END $$;

-- Guard 2: same check for the rescaled live item.
DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n
    FROM cosmetic_submissions
    WHERE shop_sku = 'face_detail_rounds_cat'
      AND status = 'approved'
      AND approved_placement_revision = 2
      AND ROUND(approved_render_scale::numeric, 4) = 1.7000
      AND ROUND(approved_render_offset_x::numeric, 4) = 0.0000
      AND ROUND(approved_render_offset_y::numeric, 4) = 0.0000;
    IF n <> 1 THEN
        RAISE EXCEPTION
            'face_detail_rounds_cat approved placement no longer matches the compiled bundle (expected revision 2, scale 1.7, offset 0/0). Rebuild the bundle before publishing.';
    END IF;
END $$;

-- Publish the new item. stock_limit is deliberately untouched (-1 = not yet on
-- sale); the artist opens sales from the Artist tab. The trigger stamps
-- released_at and published_placement_revision = 1.
UPDATE shop_items
SET catalog_ready = TRUE
WHERE sku = 'face_detail_spilled_icecream'
  AND catalog_ready IS NOT TRUE;

-- Advance the live item's published placement. The trigger cannot do this
-- (see header), so it is explicit. The `<` guard makes a rerun a no-op and
-- prevents ever moving the revision backward.
UPDATE cosmetic_submissions
SET published_placement_revision = 2
WHERE shop_sku = 'face_detail_rounds_cat'
  AND status = 'approved'
  AND approved_placement_revision = 2
  AND published_placement_revision < 2;

-- Postcondition: nothing may remain pending after this migration, or the
-- release shipped art the database still considers unpublished.
DO $$
DECLARE
    pending INTEGER;
    ready   INTEGER;
BEGIN
    SELECT COUNT(*) INTO pending
    FROM cosmetic_submissions cs
    JOIN shop_items si ON si.sku = cs.shop_sku
    WHERE cs.status = 'approved'
      AND cs.approved_placement_revision IS NOT NULL
      AND (NOT si.catalog_ready
           OR cs.approved_placement_revision > COALESCE(cs.published_placement_revision, 0));
    IF pending <> 0 THEN
        RAISE EXCEPTION 'post-check FAILED: % cosmetic(s) still pending release', pending;
    END IF;

    -- The client catalog is append-only and hardcoded; this count must equal
    -- `grep -c 'Sku = "face_' plugin/CustomCosmetics.cs` in the shipped DLL.
    SELECT COUNT(*) INTO ready FROM shop_items WHERE kind = 'face' AND catalog_ready IS TRUE;
    IF ready <> 34 THEN
        RAISE EXCEPTION
            'post-check FAILED: % catalog_ready face rows, expected 34 (v1.36.0 ships 34 CosmeticDefs)', ready;
    END IF;

    RAISE NOTICE 'post-check OK: 0 pending, % catalog_ready face rows', ready;
END $$;

COMMIT;
