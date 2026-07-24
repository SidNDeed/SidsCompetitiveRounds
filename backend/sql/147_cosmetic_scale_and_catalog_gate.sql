-- 147_cosmetic_scale_and_catalog_gate.sql — artist preview scale + publication gate
--
-- Artist submissions record the exact runtime scale reviewed in-game.
-- Approved art is not sellable until the matching PNG/catalog entry ships in
-- the client; a later release migration flips catalog_ready to TRUE.

BEGIN;

CREATE TEMP TABLE scr_migration_147_state (
    needs_catalog_backfill BOOLEAN NOT NULL
) ON COMMIT DROP;
INSERT INTO scr_migration_147_state(needs_catalog_backfill)
SELECT NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'shop_items'
      AND column_name = 'catalog_ready'
);

ALTER TABLE cosmetic_submissions
    ADD COLUMN IF NOT EXISTS render_scale REAL NOT NULL DEFAULT 1.0
    CHECK (render_scale >= 0.50 AND render_scale <= 2.25);

ALTER TABLE shop_items
    ADD COLUMN IF NOT EXISTS catalog_ready BOOLEAN NOT NULL DEFAULT TRUE;

-- Safety net: the allowlist below is hand-maintained and MUST mirror
-- CustomCosmetics.Catalog exactly. If it ever drifts, the backfill would close
-- sales and blank released_at on a live, selling cosmetic (this happened in
-- review: rounds_cat/star_spin shipped in v1.33.0 but were missing from the
-- list). An actively-stocked row reaching the gate means the list is wrong —
-- fail the migration loudly instead of destroying artist stock configuration.
DO $migration$
DECLARE
    live_but_gated TEXT;
BEGIN
    IF (SELECT needs_catalog_backfill FROM scr_migration_147_state) THEN
        SELECT string_agg(sku, ', ') INTO live_but_gated
        FROM shop_items
        WHERE kind = 'face'
          AND COALESCE(stock_limit, 0) > 0
          AND sku NOT IN (
            'face_eyes_star','face_eyes_hearts','face_mouth_stache','face_mouth_stitch',
            'face_detail_crown','face_detail_halo','face_detail_sprout','face_detail_earmuffs',
            'face_eyes_crazed','face_eyes_yinyang','face_detail_devil_horns',
            'face_detail_alien_antennae','face_detail_storm_halo','face_detail_flame_crest',
            'face_detail_demon_wings','face_detail_thorn_crown','face_detail_sun_halo',
            'face_detail_knight_helm','face_detail_mini_flags','face_detail_dark_aura',
            'face_detail_energy_orbs','face_detail_tattered_cape','face_detail_party_crown',
            'face_detail_rounds_cat','face_detail_star_spin'
          );
        IF live_but_gated IS NOT NULL THEN
            RAISE EXCEPTION
                'Refusing to gate actively-selling cosmetics (%). Update the allowlist to match CustomCosmetics.Catalog.',
                live_but_gated;
        END IF;
    END IF;
END;
$migration$;

-- Gate every face row that was absent from the last released client catalog.
-- Some legacy artist items were inserted directly into shop_items and have no
-- cosmetic_submissions row, so this must not depend on that join.
UPDATE shop_items si
SET catalog_ready = FALSE,
    stock_limit = -1,
    released_at = NULL
WHERE (SELECT needs_catalog_backfill FROM scr_migration_147_state)
  AND si.kind = 'face'
  AND si.sku NOT IN (
    'face_eyes_star',
    'face_eyes_hearts',
    'face_mouth_stache',
    'face_mouth_stitch',
    'face_detail_crown',
    'face_detail_halo',
    'face_detail_sprout',
    'face_detail_earmuffs',
    'face_eyes_crazed',
    'face_eyes_yinyang',
    'face_detail_devil_horns',
    'face_detail_alien_antennae',
    'face_detail_storm_halo',
    'face_detail_flame_crest',
    'face_detail_demon_wings',
    'face_detail_thorn_crown',
    'face_detail_sun_halo',
    'face_detail_knight_helm',
    'face_detail_mini_flags',
    'face_detail_dark_aura',
    'face_detail_energy_orbs',
    'face_detail_tattered_cape',
    'face_detail_party_crown',
    -- Shipped in v1.33.0 (client catalog entries + PNGs), opened for sale
    -- 2026-07-18. They are renderable in every released client, so they must
    -- stay catalog_ready — gating them would close live sales and blank their
    -- release date. The allowlist must mirror CustomCosmetics.Catalog exactly.
    'face_detail_rounds_cat',
    'face_detail_star_spin'
  );

COMMIT;
