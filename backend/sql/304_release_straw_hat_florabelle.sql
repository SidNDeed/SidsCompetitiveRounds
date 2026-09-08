-- 304: publish two approved community faces bundled into the v1.40.2 client.
--
-- DO NOT APPLY BEFORE THE RELEASE THAT SHIPS THE ART (learnings #163/#164):
-- catalog_ready=TRUE makes an item visible/purchasable, and clients can only
-- render it once CustomCosmetics.Catalog carries the CosmeticDef and
-- cosmetics.zip carries the PNG. Apply AFTER the v1.40.2 GitHub release exists.
--
-- WHAT WAS COMPILED (extracted from cosmetic_submissions.png_data in chunked
-- base64, verified against md5(png_data) + png_bytes + PNG magic before
-- writing -- migration 260's technique):
--
--   sku                      slot    bytes   md5                               scale  rev  frames
--   face_detail_straw_hat    detail  32034   5951aa04237cfc791e79a6c759532896  1.75   1    1
--   face_detail_florabelle   detail  29988   aa73f8e2ca964fc9e22af3343bf4f500  1.60   1    1
--
-- Both static (frame_count 1, anim_fps NULL) with approved offset (0,0).
-- Scales/offsets come from the approved_* snapshot only (#165).
--
-- The guard ABORTS (loudly, whole transaction) if any approved value moved
-- between bundle-cut and publish. released_at + published_placement_revision
-- are stamped by the migration-148 trigger on the flip; stock stays closed
-- until the artist opens sales. Explicit BEGIN/COMMIT (#340).

BEGIN;

DO $$
DECLARE
    -- [sku, expected_scale, expected_revision, expected_frames, expected_fps]
    expected CONSTANT TEXT[][] := ARRAY[
        ['face_detail_straw_hat',  '1.75', '1', '1', '0'],
        ['face_detail_florabelle', '1.60', '1', '1', '0']
    ];
    -- v_sku, not sku (#442: a bare identifier resolves as the PL/pgSQL
    -- variable and makes the UPDATE's WHERE ambiguous).
    v_sku       TEXT;
    want        NUMERIC;
    want_rev    INT;
    want_frames INT;
    want_fps    INT;
    rec         RECORD;
    flipped     INT := 0;
BEGIN
    FOR i IN 1 .. array_length(expected, 1) LOOP
        v_sku       := expected[i][1];
        want        := expected[i][2]::numeric;
        want_rev    := expected[i][3]::int;
        want_frames := expected[i][4]::int;
        want_fps    := expected[i][5]::int;

        SELECT cs.approved_render_scale, cs.approved_render_offset_x,
               cs.approved_render_offset_y, cs.approved_placement_revision,
               cs.status, cs.frame_count, cs.anim_fps
          INTO rec
          FROM cosmetic_submissions cs
         WHERE cs.shop_sku = v_sku;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'no cosmetic_submissions row for %', v_sku;
        END IF;
        IF rec.status <> 'approved' THEN
            RAISE EXCEPTION '% is no longer approved (status=%)', v_sku, rec.status;
        END IF;
        IF rec.approved_placement_revision IS DISTINCT FROM want_rev THEN
            RAISE EXCEPTION '% approved revision moved to % (client built against %) - '
                            'recompile the catalog before publishing',
                            v_sku, rec.approved_placement_revision, want_rev;
        END IF;
        IF ROUND(rec.approved_render_scale::numeric, 3) <> ROUND(want, 3) THEN
            RAISE EXCEPTION '% approved scale is % but the client was built with % - '
                            'recompile the catalog before publishing',
                            v_sku, rec.approved_render_scale, want;
        END IF;
        IF COALESCE(rec.approved_render_offset_x, 0) <> 0
           OR COALESCE(rec.approved_render_offset_y, 0) <> 0 THEN
            RAISE EXCEPTION '% approved offset is now (%,%) but the client was built '
                            'with (0,0) - recompile the catalog before publishing',
                            v_sku, rec.approved_render_offset_x, rec.approved_render_offset_y;
        END IF;
        IF COALESCE(rec.frame_count, 1) <> want_frames THEN
            RAISE EXCEPTION '% frame_count is now % but the client bundled % frame(s) - '
                            'ship every frame or none (#317)',
                            v_sku, rec.frame_count, want_frames;
        END IF;
        IF want_frames > 1 AND COALESCE(rec.anim_fps, 0) <> want_fps THEN
            RAISE EXCEPTION '% anim_fps is now % but the client was built with % - '
                            'recompile the catalog before publishing (#317)',
                            v_sku, rec.anim_fps, want_fps;
        END IF;

        UPDATE shop_items SET catalog_ready = TRUE
         WHERE shop_items.sku = v_sku AND catalog_ready IS DISTINCT FROM TRUE;
        flipped := flipped + 1;
    END LOOP;

    RAISE NOTICE 'post-check OK: verified and published % face sku(s)', flipped;
END $$;

-- Fails loudly unless BOTH rows EXIST and are live. Counting only
-- existing-but-unpublished rows would let an ABSENT shop_items row
-- (schema-valid: cosmetic_submissions.shop_sku carries no FK) half-publish and
-- still report success -- the finding 264 was rewritten to close. Asserting
-- presence-by-expected-array stays rerun-safe: a re-run sees both already TRUE
-- and passes.
DO $$
DECLARE live INT; missing TEXT;
BEGIN
    SELECT COUNT(*) INTO live
      FROM shop_items
     WHERE kind = 'face'
       AND sku IN ('face_detail_straw_hat', 'face_detail_florabelle')
       AND catalog_ready IS TRUE;
    IF live <> 2 THEN
        SELECT string_agg(e.sku, ', ') INTO missing
          FROM unnest(ARRAY['face_detail_straw_hat', 'face_detail_florabelle']) AS e(sku)
          LEFT JOIN shop_items si ON si.sku = e.sku AND si.kind = 'face'
                                 AND si.catalog_ready IS TRUE
         WHERE si.sku IS NULL;
        RAISE EXCEPTION 'post-check FAILED: only % of 2 faces live - missing or unpublished: %',
                        live, missing;
    END IF;
    RAISE NOTICE 'post-check OK: both v1.40.2 faces are live';
END $$;

COMMIT;
