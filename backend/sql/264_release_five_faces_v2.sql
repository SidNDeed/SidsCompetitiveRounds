-- 264: publish five approved community faces bundled into the v1.39.6 client.
--
-- DO NOT APPLY BEFORE THE RELEASE THAT SHIPS THE ART (learnings #163/#164):
-- catalog_ready=TRUE makes an item visible/purchasable, and clients can only
-- render it once CustomCosmetics.Catalog carries the CosmeticDef and
-- cosmetics.zip carries the PNG. Apply AFTER the v1.39.6 GitHub release exists.
--
-- WHAT WAS COMPILED (extracted from cosmetic_submissions.png_data in chunked
-- base64, verified against md5(png_data) + png_bytes + PNG magic before
-- writing — migration 260's technique):
--
--   sku                          slot    bytes   md5                               scale  rev  frames
--   face_detail_the_mobsta       detail  28810   006c2c69f9502479558f869740aedf51  1.55   1    1
--   face_detail_well_wraped_hat  detail  25425   6c69bf83d1d5616b807cdb24f26f5685  1.30   1    1
--   face_eyes_phoneix_gaze       eyes    48692*  e0ca9dee187039d68088e4dfcb19876e  1.80   2    4 @ 5fps
--   face_eyes_smart_specs        eyes    21565   cacdec415eec9d76802e8f9ee9923286  1.55   1    1
--   face_eyes_the_cryptid        eyes    20944   be7b15edce2d8a2599b3020fc23f16cd  1.45   1    1
--
--   * base frame; frames 2-4 from cosmetic_submission_frames, individually
--     verified: f2 32431/34d69ecf6ac27183c5c8b83f4c055d93, f3 33904/
--     7489071d6a73d02b7e246dcbe93e3c12, f4 38699/268513384ced05591434919fe91ff08d.
--     Bundled as eyes_phoneix_gaze__f2..__f4.png; CosmeticDef.Fps = 5 (the
--     artist's approved anim_fps, #317).
--
-- All approved offsets (0,0), scales/offsets from the approved_* snapshot only
-- (#165). Unlike 260, the expected array carries a PER-SKU revision, frame
-- count and fps — Phoneix Gaze was re-reviewed to revision 2 AND animated; the
-- guard pins exactly what the client was built against.
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
        ['face_detail_the_mobsta',      '1.55', '1', '1', '0'],
        ['face_detail_well_wraped_hat', '1.30', '1', '1', '0'],
        ['face_eyes_phoneix_gaze',      '1.80', '2', '4', '5'],
        ['face_eyes_smart_specs',       '1.55', '1', '1', '0'],
        ['face_eyes_the_cryptid',       '1.45', '1', '1', '0']
    ];
    -- v_sku, not sku (#442: a bare identifier resolves as the PL/pgSQL
    -- variable and makes the UPDATE's WHERE ambiguous).
    v_sku      TEXT;
    want       NUMERIC;
    want_rev   INT;
    want_frames INT;
    want_fps   INT;
    rec        RECORD;
    flipped    INT := 0;
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

-- Fails loudly unless ALL FIVE rows EXIST and are live. The old shape only
-- counted existing-but-unpublished rows, so an ABSENT shop_items row (schema-
-- valid: cosmetic_submissions.shop_sku carries no FK) would half-publish four
-- faces and still report success — the v1.39.6 focused review's one finding.
-- Asserting presence-by-expected-array closes it and stays rerun-safe (a
-- re-run sees all five already TRUE and passes).
DO $$
DECLARE live INT; missing TEXT;
BEGIN
    SELECT COUNT(*) INTO live
      FROM shop_items
     WHERE kind = 'face'
       AND sku IN ('face_detail_the_mobsta', 'face_detail_well_wraped_hat',
                   'face_eyes_phoneix_gaze', 'face_eyes_smart_specs',
                   'face_eyes_the_cryptid')
       AND catalog_ready IS TRUE;
    IF live <> 5 THEN
        SELECT string_agg(e.sku, ', ') INTO missing
          FROM unnest(ARRAY['face_detail_the_mobsta', 'face_detail_well_wraped_hat',
                            'face_eyes_phoneix_gaze', 'face_eyes_smart_specs',
                            'face_eyes_the_cryptid']) AS e(sku)
          LEFT JOIN shop_items si ON si.sku = e.sku AND si.kind = 'face'
                                 AND si.catalog_ready IS TRUE
         WHERE si.sku IS NULL;
        RAISE EXCEPTION 'post-check FAILED: only % of 5 faces live - missing or unpublished: %',
                        live, missing;
    END IF;
    RAISE NOTICE 'post-check OK: all five v1.39.6 faces are live';
END $$;

COMMIT;
