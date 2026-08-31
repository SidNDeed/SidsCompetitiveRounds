-- 268: publish Party Crown's approved placement revision 2 (Scale 1.2 -> 1.4).
--
-- The artist adjusted the placement through the Artist Studio flow (#165/#184:
-- artist proposal -> admin-approved snapshot -> published-at-release); the
-- v1.39.6 client compiles Scale=1.4 from the approved_* snapshot (offset
-- unchanged at (0, 0.55); the art itself is untouched since v1.32.1 — the
-- stored png_data md5 differs from the bundled base frame because the shipped
-- animation's base came from the GIF pipeline, which predates this revision).
--
-- The migration-148 trigger stamps published_placement_revision only when
-- catalog_ready FLIPS; party_crown is already live, so an adjustment ship
-- advances it explicitly. Guarded 264-style: abort loudly if the approved
-- snapshot moved after the bundle was cut, so a rev-3 approval between
-- bundle and publish can never be silently marked published.
--
-- DO NOT APPLY BEFORE THE v1.39.6 GITHUB RELEASE EXISTS: old clients render
-- Scale 1.2 until they update, which is fine (same art, slightly smaller),
-- but marking rev 2 published before any client carries it would lie to the
-- Artist Studio's revision display. Explicit BEGIN/COMMIT (#340); idempotent
-- under the wrapper's || re-run (#243).

BEGIN;

DO $$
DECLARE
    v_approved_rev  INTEGER;
    v_published_rev INTEGER;
    v_scale         NUMERIC;
    v_off_x         NUMERIC;
    v_off_y         NUMERIC;
BEGIN
    -- FOR UPDATE (r2 review): without the row lock, a concurrent admin rev-3
    -- approval could commit between this read and the UPDATE below, and the
    -- migration would mark rev 2 published over a moved snapshot — the exact
    -- state the guard exists to abort on.
    SELECT approved_placement_revision, published_placement_revision,
           approved_render_scale, approved_render_offset_x, approved_render_offset_y
      INTO v_approved_rev, v_published_rev, v_scale, v_off_x, v_off_y
      FROM cosmetic_submissions
     WHERE shop_sku = 'face_detail_party_crown'
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION '268 ABORT: no cosmetic_submissions row for face_detail_party_crown';
    END IF;
    IF v_published_rev >= 2 THEN
        RAISE NOTICE '268 no-op: published_placement_revision already % (rerun)', v_published_rev;
        RETURN;
    END IF;
    -- The exact values the v1.39.6 client was compiled against. NULL-safe
    -- (r2 review: schema permits NULL offsets, and `NULL <> x` is NULL —
    -- the plain <> chain silently FAILED OPEN on a NULL field); numeric
    -- comparisons carry a tolerance in case the columns are ever floats.
    IF v_approved_rev IS DISTINCT FROM 2
       OR v_scale IS NULL OR abs(v_scale - 1.4)  > 0.0001
       OR v_off_x IS NULL OR abs(v_off_x - 0)    > 0.0001
       OR v_off_y IS NULL OR abs(v_off_y - 0.55) > 0.0001 THEN
        RAISE EXCEPTION '268 ABORT: approved snapshot moved since bundle-cut (rev=%, scale=%, off=%,%) — re-bundle before publishing',
            v_approved_rev, v_scale, v_off_x, v_off_y;
    END IF;

    UPDATE cosmetic_submissions
       SET published_placement_revision = 2
     WHERE shop_sku = 'face_detail_party_crown';

    RAISE NOTICE '268 OK: face_detail_party_crown published_placement_revision -> 2 (Scale 1.4)';
END $$;

COMMIT;
