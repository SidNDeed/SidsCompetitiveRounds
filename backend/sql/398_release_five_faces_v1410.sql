-- 398: publish the five approved community faces bundled into the v1.41.0
-- client. (First written as 395; renumbered 398 because it needs 397's
-- column and provenance table, and 396 is another lane's.)
--
-- DO NOT APPLY BEFORE THE RELEASE THAT SHIPS THE ART (learnings #163/#164):
-- catalog_ready=TRUE makes an item visible, giftable and purchasable, and a
-- client can only render it once CustomCosmetics.Catalog carries the
-- CosmeticDef and the LATEST GitHub release's cosmetics.zip carries the PNG.
-- Apply AFTER the v1.41.0 GitHub release (with cosmetics.zip) exists, and
-- after migration 397 and the api that reads its column.
--
-- OLDER CLIENTS. While the server still admits clients below 1.41.0, their
-- Catalog has no definition for these faces. So the same UPDATE that
-- publishes a face sets its min_client_version to 1.41.0 (397): the api then
-- omits it from an older caller's listings, refuses an older caller's
-- purchase, and refuses a gift to a recipient whose last-seen version is
-- older or unknown.
--
-- WHAT WAS COMPILED (read on the primary 2026-10-30 through the read-only
-- verb; each PNG extracted from cosmetic_submissions.png_data in 48-char
-- base64 chunks and written only after md5(png_data), png_bytes, the PNG
-- signature and a 512x512 IHDR matched):
--
--   sub  shop  sku                         bytes  md5                               scale  rev  frames
--   69   359   face_detail_gold_headband   24429  4242409ce643ec451420cf1976688506  1.45   1    1
--   70   358   face_detail_orbit           34839  412974a31b7569bd2a04275293b30787  1.60   1    1
--   71   569   face_detail_pumpking_hat    51759  06c4235ba87bf61cdb613169eee2c86c  1.40   1    1
--   72   570   face_detail_leafy_mushroom  23257  9e9b0421902c33077ca42c8bcea28882  1.30   1    1
--   73   571   face_detail_red_scarf       21241  6d43a388354876aabaf3808582832fbd  1.60   1    1
--
-- All five: slot detail, rarity rare, price 750, stock_limit -1, approved
-- offset (0,0), static (frame_count 1, anim_fps NULL), description the
-- approval placeholder. Scales and offsets come from the approved_* snapshot
-- only (#165).
--
-- DESCRIPTION. Approval writes "Detail: community cosmetic. Ships with the
-- next mod update; equip in the Character editor." on every new face. Once
-- published, that sentence is false, so the publishing UPDATE replaces it
-- with the shipped form, "Detail: community cosmetic. Equip in the Character
-- editor." -- only while the row still carries the placeholder exactly; a
-- description the artist wrote (artist/set-desc) is theirs and is left
-- alone, with a NOTICE.
--
-- Rows are keyed by BOTH ids (cosmetic_submissions.id and shop_items.id) and
-- the sku must agree with each. The guard RAISES (whole transaction) if any
-- approved value, or the stored art itself (md5 + byte count), moved between
-- bundle-cut and publish. released_at and published_placement_revision are
-- stamped by the migration-148 trigger (trg_shop_item_catalog_release, live
-- on the primary 2026-10-30) on the false -> true flip; stock stays closed
-- until the artist opens sales.
--
-- EVERY DECISION IS TOTAL: IS TRUE / IS FALSE / IS [NOT] DISTINCT FROM, so a
-- NULL operand never reads as a match. A NULL approved scale, offset,
-- revision or frame count is drift from the approved snapshot (whose values
-- are all non-NULL) and refuses. Per row the state must be EXACTLY one of:
--   pre-image  catalog_ready FALSE, min_client_version NULL, no 398
--              provenance row -> publish (exactly one row) and record what was
--              written in shop_item_release_provenance;
--   post-image catalog_ready TRUE and a 398 provenance row -> no-op, so a
--              rerun changes nothing (later edits by people are theirs);
-- anything else (published by someone else, unpublished with 398's record
-- still present, a minimum set by someone else) RAISES. The post-check names
-- the sku and the field of the first row that does not hold the result.
-- Rollback: rollback_398_release_five_faces_v1410.sql.
--
-- LOCK FIRST, THEN JUDGE. Every check reads a row this file later writes:
-- the five shop_items rows (the flip, the minimum, the description) and
-- the five submissions (the trigger stamps their published revision). The
-- DO's first statements lock all ten, FOR NO KEY UPDATE, in id order,
-- shop_items before submissions (the order the publishing UPDATE and its
-- trigger take them), and holds them to COMMIT. That is the weakest row
-- lock that conflicts with an UPDATE of the same row, so a concurrent
-- writer (an artist's description, a re-approval) either commits before
-- the lock is granted, and every later read sees its value, or waits
-- until this file commits. No decision rests on a value another
-- transaction can change before the write that acts on it: the
-- placeholder test, the approved-value checks, the flip and the
-- provenance row all read the locked rows. Provenance rows for '398' are
-- written only by this file and rollback_398, which take the same
-- shop_items locks first, so the two never interleave. A writer that
-- holds one of the rows longer than lock_timeout (5 s) aborts this file
-- whole, changing nothing; rerun it.
--
-- `psql -f` does not wrap a file in a transaction, so this file does (#340).
-- Lock bound (learning #1072): wait 5 s; hold 25 s + 5 s plus the COMMIT's
-- local completion.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $$
DECLARE
    -- [submission_id, shop_item_id, sku, approved_scale, png_bytes, md5]
    expected CONSTANT TEXT[][] := ARRAY[
        ['69', '359', 'face_detail_gold_headband',  '1.45', '24429', '4242409ce643ec451420cf1976688506'],
        ['70', '358', 'face_detail_orbit',          '1.60', '34839', '412974a31b7569bd2a04275293b30787'],
        ['71', '569', 'face_detail_pumpking_hat',   '1.40', '51759', '06c4235ba87bf61cdb613169eee2c86c'],
        ['72', '570', 'face_detail_leafy_mushroom', '1.30', '23257', '9e9b0421902c33077ca42c8bcea28882'],
        ['73', '571', 'face_detail_red_scarf',      '1.60', '21241', '6d43a388354876aabaf3808582832fbd']
    ];
    want_rev     CONSTANT INT  := 1;
    min_version  CONSTANT TEXT := '1.41.0';
    placeholder  CONSTANT TEXT := 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.';
    shipped_desc CONSTANT TEXT := 'Detail: community cosmetic. Equip in the Character editor.';
    -- v_ prefixes, never bare column names (#442: a bare identifier resolves
    -- as the PL/pgSQL variable and makes a WHERE ambiguous).
    v_sub     BIGINT;
    v_shop    BIGINT;
    v_sku     TEXT;
    v_scale   NUMERIC;
    v_bytes   INT;
    v_md5     TEXT;
    v_desc    TEXT;
    cs_rec    RECORD;
    si_rec    RECORD;
    pv_rec    RECORD;
    k         BIGINT;
    flipped   INT := 0;
    already   INT := 0;
    flipped_ids BIGINT[] := ARRAY[]::BIGINT[];
BEGIN
    -- Lock first, then judge (see the header): every row this DO writes,
    -- before the first check reads any of them.
    PERFORM 1 FROM shop_items si
     WHERE si.id IN (SELECT CAST(expected[j][2] AS BIGINT)
                       FROM generate_subscripts(expected, 1) AS j)
     ORDER BY si.id
       FOR NO KEY UPDATE;
    PERFORM 1 FROM cosmetic_submissions cs
     WHERE cs.id IN (SELECT CAST(expected[j][1] AS BIGINT)
                       FROM generate_subscripts(expected, 1) AS j)
     ORDER BY cs.id
       FOR NO KEY UPDATE;

    FOR i IN 1 .. array_length(expected, 1) LOOP
        v_sub   := CAST(expected[i][1] AS BIGINT);
        v_shop  := CAST(expected[i][2] AS BIGINT);
        v_sku   := expected[i][3];
        v_scale := CAST(expected[i][4] AS NUMERIC);
        v_bytes := CAST(expected[i][5] AS INT);
        v_md5   := expected[i][6];

        SELECT cs.shop_sku, cs.status, cs.slot,
               cs.approved_render_scale, cs.approved_render_offset_x,
               cs.approved_render_offset_y, cs.approved_placement_revision,
               cs.published_placement_revision, cs.frame_count,
               cs.png_bytes, md5(cs.png_data) AS art_md5
          INTO cs_rec
          FROM cosmetic_submissions cs
         WHERE cs.id = v_sub;
        IF NOT FOUND THEN
            RAISE EXCEPTION '398: no cosmetic_submissions row id=% (%)', v_sub, v_sku;
        END IF;
        IF cs_rec.shop_sku IS DISTINCT FROM v_sku THEN
            RAISE EXCEPTION '398: submission % carries sku % but the client bundled %',
                            v_sub, cs_rec.shop_sku, v_sku;
        END IF;
        IF cs_rec.status IS DISTINCT FROM 'approved' THEN
            RAISE EXCEPTION '398: % is no longer approved (status=%)', v_sku, cs_rec.status;
        END IF;
        IF cs_rec.slot IS DISTINCT FROM 'detail' THEN
            RAISE EXCEPTION '398: % slot is % but the client bundled it as detail',
                            v_sku, cs_rec.slot;
        END IF;
        IF cs_rec.approved_placement_revision IS DISTINCT FROM want_rev THEN
            RAISE EXCEPTION '398: % approved revision moved to % (client built against %) - recompile the catalog before publishing',
                            v_sku, cs_rec.approved_placement_revision, want_rev;
        END IF;
        IF (ROUND(CAST(cs_rec.approved_render_scale AS NUMERIC), 3)
                IS NOT DISTINCT FROM ROUND(v_scale, 3)) IS NOT TRUE THEN
            RAISE EXCEPTION '398: % approved scale is % but the client was built with % - recompile the catalog before publishing',
                            v_sku, cs_rec.approved_render_scale, v_scale;
        END IF;
        -- A NULL offset is not (0,0): IS DISTINCT FROM refuses it.
        IF cs_rec.approved_render_offset_x IS DISTINCT FROM CAST(0 AS REAL)
           OR cs_rec.approved_render_offset_y IS DISTINCT FROM CAST(0 AS REAL) THEN
            RAISE EXCEPTION '398: % approved offset is now (%,%) but the client was built with (0,0) - recompile the catalog before publishing',
                            v_sku, cs_rec.approved_render_offset_x, cs_rec.approved_render_offset_y;
        END IF;
        IF cs_rec.frame_count IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION '398: % frame_count is now % but the client bundled 1 frame - ship every frame or none (#317)', v_sku, cs_rec.frame_count;
        END IF;
        IF cs_rec.png_bytes IS DISTINCT FROM v_bytes
           OR cs_rec.art_md5 IS DISTINCT FROM v_md5 THEN
            RAISE EXCEPTION '398: % stored art is now % bytes md5 % but the client bundled % bytes md5 % - re-extract the PNG before publishing',
                            v_sku, cs_rec.png_bytes, cs_rec.art_md5, v_bytes, v_md5;
        END IF;

        SELECT si.sku, si.kind, si.catalog_ready, si.min_client_version, si.description
          INTO si_rec
          FROM shop_items si
         WHERE si.id = v_shop;
        IF NOT FOUND THEN
            RAISE EXCEPTION '398: no shop_items row id=% (%)', v_shop, v_sku;
        END IF;
        IF si_rec.sku IS DISTINCT FROM v_sku OR si_rec.kind IS DISTINCT FROM 'face' THEN
            RAISE EXCEPTION '398: shop item % is (%, %) - expected (%, face)',
                            v_shop, si_rec.sku, si_rec.kind, v_sku;
        END IF;

        SELECT p.released_at INTO pv_rec
          FROM shop_item_release_provenance p
         WHERE p.migration = '398' AND p.shop_item_id = v_shop;

        IF si_rec.catalog_ready IS TRUE THEN
            IF NOT FOUND THEN
                RAISE EXCEPTION '398: % is already published but not by 398 (no provenance row) - refusing to claim it', v_sku;
            END IF;
            already := already + 1;            -- post-image: rerun no-op
        ELSIF si_rec.catalog_ready IS FALSE THEN
            IF FOUND THEN
                RAISE EXCEPTION '398: % is unpublished but 398''s provenance row is still present - run rollback_398, or clear the row, first', v_sku;
            END IF;
            IF si_rec.min_client_version IS NOT NULL THEN
                RAISE EXCEPTION '398: % already carries min_client_version % (set outside 398) - refusing', v_sku, si_rec.min_client_version;
            END IF;
            IF si_rec.description IS NOT DISTINCT FROM placeholder THEN
                v_desc := shipped_desc;
            ELSE
                v_desc := si_rec.description;
                RAISE NOTICE '398: % carries its artist''s description; left as written', v_sku;
            END IF;
            -- Pre-image. One UPDATE publishes, sets the minimum and the
            -- description together; the flip fires the 148 trigger, which
            -- stamps released_at and published_placement_revision.
            UPDATE shop_items
               SET catalog_ready      = TRUE,
                   min_client_version = min_version,
                   description        = v_desc
             WHERE shop_items.id = v_shop
               AND shop_items.sku = v_sku
               AND shop_items.kind = 'face'
               AND shop_items.catalog_ready IS FALSE
               AND shop_items.min_client_version IS NULL;
            GET DIAGNOSTICS k = ROW_COUNT;
            IF k IS DISTINCT FROM CAST(1 AS BIGINT) THEN
                RAISE EXCEPTION '398: publishing % touched % rows, expected 1', v_sku, k;
            END IF;
            -- What the trigger stamped, checked per field before it is
            -- recorded (the post-check for this row; it names the field).
            SELECT si.released_at, cs.published_placement_revision AS pub
              INTO pv_rec
              FROM shop_items si
              JOIN cosmetic_submissions cs ON cs.id = v_sub AND cs.shop_sku = si.sku
             WHERE si.id = v_shop;
            IF pv_rec.released_at IS NULL THEN
                RAISE EXCEPTION '398: post-check FAILED: % released_at is NULL - the publish trigger did not stamp it', v_sku;
            END IF;
            IF pv_rec.pub IS DISTINCT FROM want_rev THEN
                RAISE EXCEPTION '398: post-check FAILED: % published_placement_revision is %, expected %', v_sku, pv_rec.pub, want_rev;
            END IF;
            -- Provenance: what this file wrote, read back after the trigger,
            -- so the rollback can tell 398's publication from a later one.
            INSERT INTO shop_item_release_provenance
                   (migration, shop_item_id, submission_id, released_at,
                    published_revision, min_client_version,
                    description_before, description_written)
            SELECT '398', si.id, cs.id, si.released_at,
                   cs.published_placement_revision, si.min_client_version,
                   si_rec.description,
                   CASE WHEN v_desc IS DISTINCT FROM si_rec.description THEN v_desc END
              FROM shop_items si
              JOIN cosmetic_submissions cs ON cs.id = v_sub AND cs.shop_sku = si.sku
             WHERE si.id = v_shop;
            GET DIAGNOSTICS k = ROW_COUNT;
            IF k IS DISTINCT FROM CAST(1 AS BIGINT) THEN
                RAISE EXCEPTION '398: recording % provenance wrote % rows, expected 1', v_sku, k;
            END IF;
            flipped := flipped + 1;
            flipped_ids := flipped_ids || v_shop;
        ELSE
            RAISE EXCEPTION '398: % catalog_ready is NULL - refusing', v_sku;
        END IF;
    END LOOP;

    -- Post-check, per row, naming the sku and the field: all five must be
    -- live with a 398 provenance row; each row published BY THIS RUN must
    -- also carry exactly what 398 wrote and what the trigger stamped.
    -- Reading by the expected ids (not by "unpublished rows") means an absent
    -- row cannot half-publish and still pass (the 264 finding).
    FOR i IN 1 .. array_length(expected, 1) LOOP
        v_sub  := CAST(expected[i][1] AS BIGINT);
        v_shop := CAST(expected[i][2] AS BIGINT);
        v_sku  := expected[i][3];
        SELECT si.catalog_ready, si.released_at, si.min_client_version, si.description,
               cs.published_placement_revision AS pub,
               p.released_at AS p_released_at, p.published_revision AS p_pub,
               p.min_client_version AS p_min, p.migration AS p_mig
          INTO si_rec
          FROM shop_items si
          JOIN cosmetic_submissions cs ON cs.id = v_sub AND cs.shop_sku = si.sku
          LEFT JOIN shop_item_release_provenance p
                 ON p.migration = '398' AND p.shop_item_id = si.id
         WHERE si.id = v_shop AND si.kind = 'face';
        IF NOT FOUND THEN
            RAISE EXCEPTION '398: post-check FAILED: % row (shop %, submission %) is missing',
                            v_sku, v_shop, v_sub;
        END IF;
        IF si_rec.catalog_ready IS NOT TRUE THEN
            RAISE EXCEPTION '398: post-check FAILED: % catalog_ready is %, expected true',
                            v_sku, si_rec.catalog_ready;
        END IF;
        IF si_rec.p_mig IS NULL THEN
            RAISE EXCEPTION '398: post-check FAILED: % has no 398 provenance row', v_sku;
        END IF;
        -- released_at and the published revision were checked per row
        -- right after the flip, before provenance was recorded.
        CONTINUE WHEN NOT (v_shop = ANY(flipped_ids));
        IF si_rec.min_client_version IS DISTINCT FROM min_version THEN
            RAISE EXCEPTION '398: post-check FAILED: % min_client_version is %, expected %',
                            v_sku, si_rec.min_client_version, min_version;
        END IF;
        IF si_rec.description IS NOT DISTINCT FROM placeholder THEN
            RAISE EXCEPTION '398: post-check FAILED: % description still says it ships with the next mod update', v_sku;
        END IF;
        IF si_rec.p_released_at IS DISTINCT FROM si_rec.released_at
           OR si_rec.p_pub IS DISTINCT FROM si_rec.pub
           OR si_rec.p_min IS DISTINCT FROM si_rec.min_client_version THEN
            RAISE EXCEPTION '398: post-check FAILED: % provenance (released_at %, revision %, minimum %) does not match the row (%, %, %)', v_sku,
                            si_rec.p_released_at, si_rec.p_pub, si_rec.p_min,
                            si_rec.released_at, si_rec.pub, si_rec.min_client_version;
        END IF;
    END LOOP;
    RAISE NOTICE '398: post-check OK: 5 of 5 v1.41.0 faces live (flipped %, already live %)',
                 flipped, already;
END $$;

COMMIT;
