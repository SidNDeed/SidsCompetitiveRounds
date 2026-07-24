-- Cosmetic placement proposals retain the last approved values while a later
-- artist adjustment is pending review. Match input peaks/timelines give admins
-- the per-second evidence behind suspected-macro flags.
-- Requires migration 147 (render_scale, catalog_ready, released_at) first.

BEGIN;

-- Capture whether this is the first application before ADD COLUMN makes that
-- impossible to distinguish. Backfills below must never reopen a placement an
-- admin denied after the migration first ran.
CREATE TEMP TABLE scr_migration_148_state (
    needs_placement_backfill BOOLEAN NOT NULL,
    needs_restoration_backfill BOOLEAN NOT NULL
) ON COMMIT DROP;
INSERT INTO scr_migration_148_state(
    needs_placement_backfill,
    needs_restoration_backfill
)
SELECT
    NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'cosmetic_submissions'
          AND column_name = 'approved_render_scale'
    ),
    NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'flagged_matches'
          AND column_name = 'restoration_required'
    );

ALTER TABLE cosmetic_submissions
    ADD COLUMN IF NOT EXISTS render_offset_x REAL NOT NULL DEFAULT 0
        CHECK (render_offset_x BETWEEN -4.50 AND 4.50),
    ADD COLUMN IF NOT EXISTS render_offset_y REAL NOT NULL DEFAULT 0
        CHECK (render_offset_y BETWEEN -4.50 AND 4.50),
    ADD COLUMN IF NOT EXISTS placement_revision INTEGER NOT NULL DEFAULT 1
        CHECK (placement_revision >= 1),
    ADD COLUMN IF NOT EXISTS approved_render_scale REAL,
    ADD COLUMN IF NOT EXISTS approved_render_offset_x REAL,
    ADD COLUMN IF NOT EXISTS approved_render_offset_y REAL,
    ADD COLUMN IF NOT EXISTS approved_placement_revision INTEGER,
    ADD COLUMN IF NOT EXISTS published_placement_revision INTEGER NOT NULL DEFAULT 0
        CHECK (published_placement_revision >= 0),
    ADD COLUMN IF NOT EXISTS placement_status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (placement_status IN ('pending', 'approved', 'denied')),
    ADD COLUMN IF NOT EXISTS placement_review_note TEXT,
    ADD COLUMN IF NOT EXISTS placement_reviewed_by VARCHAR(20),
    ADD COLUMN IF NOT EXISTS placement_reviewed_at TIMESTAMPTZ,
    -- When the CURRENT proposal was submitted. The admin queue is ordered by
    -- this (falling back to created_at) so a placement tweak on an old item
    -- queues by when it was tweaked, not by the art's original upload date —
    -- otherwise old items permanently occupy the LIMIT 10 window and starve
    -- brand-new art out of the review modal.
    ADD COLUMN IF NOT EXISTS placement_submitted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS submission_fingerprint VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cosmetic_submission_fingerprint
    ON cosmetic_submissions(submission_fingerprint);

-- Seed every already-shipped SKU from the exact append-only client catalog.
-- Database defaults are not authoritative for legacy art: several items ship
-- at non-1.0 scale and non-zero offsets.
UPDATE cosmetic_submissions cs
SET render_scale = v.render_scale,
    render_offset_x = v.render_offset_x,
    render_offset_y = v.render_offset_y
FROM (VALUES
    ('face_eyes_star', 1.00, 0.00, 0.10),
    ('face_eyes_hearts', 1.00, 0.00, 0.10),
    ('face_mouth_stache', 0.90, 0.00, -0.15),
    ('face_mouth_stitch', 0.80, 0.00, -0.15),
    ('face_detail_crown', 1.10, 0.00, 0.55),
    ('face_detail_halo', 1.10, 0.00, 0.75),
    ('face_detail_sprout', 1.10, 0.00, 0.55),
    ('face_detail_earmuffs', 1.10, 0.00, 0.20),
    ('face_eyes_crazed', 1.35, 0.00, 0.10),
    ('face_eyes_yinyang', 1.35, 0.00, 0.10),
    ('face_detail_devil_horns', 1.10, 0.00, 0.45),
    ('face_detail_alien_antennae', 1.10, 0.00, 0.55),
    ('face_detail_storm_halo', 1.20, 0.00, 0.80),
    ('face_detail_flame_crest', 1.10, 0.00, 0.60),
    ('face_detail_demon_wings', 2.10, 0.00, 0.05),
    ('face_detail_thorn_crown', 1.00, 0.00, 0.00),
    ('face_detail_sun_halo', 1.10, 0.00, 0.10),
    ('face_detail_knight_helm', 1.55, 0.00, 0.05),
    ('face_detail_mini_flags', 1.00, 0.00, 0.15),
    ('face_detail_dark_aura', 1.45, 0.00, 0.05),
    ('face_detail_energy_orbs', 1.00, 0.00, 0.05),
    ('face_detail_tattered_cape', 1.70, 0.00, -0.10),
    ('face_detail_party_crown', 1.20, 0.00, 0.55)
) AS v(sku, render_scale, render_offset_x, render_offset_y)
WHERE cs.shop_sku = v.sku
  AND cs.status = 'approved'
  AND cs.placement_revision = 1
  AND cs.approved_render_scale IS NULL
  AND (SELECT needs_placement_backfill FROM scr_migration_148_state);

-- Only catalog-ready art has a historical placement that was genuinely
-- reviewed-by-release and published. Approved but unbundled submissions must
-- enter the new placement queue before their first ship.
UPDATE cosmetic_submissions cs
SET approved_render_scale = cs.render_scale,
    approved_render_offset_x = cs.render_offset_x,
    approved_render_offset_y = cs.render_offset_y,
    approved_placement_revision = cs.placement_revision,
    placement_status = 'approved',
    placement_review_note = COALESCE(cs.placement_review_note, cs.review_note),
    placement_reviewed_by = COALESCE(cs.placement_reviewed_by, cs.reviewed_by),
    placement_reviewed_at = COALESCE(cs.placement_reviewed_at, cs.reviewed_at)
FROM shop_items si
WHERE cs.status = 'approved'
  AND cs.shop_sku = si.sku
  AND si.catalog_ready
  AND cs.approved_render_scale IS NULL
  AND (SELECT needs_placement_backfill FROM scr_migration_148_state);

UPDATE cosmetic_submissions cs
SET approved_render_scale = NULL,
    approved_render_offset_x = NULL,
    approved_render_offset_y = NULL,
    approved_placement_revision = NULL,
    placement_status = 'pending',
    placement_review_note = NULL,
    placement_reviewed_by = NULL,
    placement_reviewed_at = NULL
WHERE cs.status = 'approved'
  AND cs.approved_render_scale IS NULL
  AND (SELECT needs_placement_backfill FROM scr_migration_148_state)
  AND NOT EXISTS (
      SELECT 1
      FROM shop_items si
      WHERE si.sku = cs.shop_sku
        AND si.catalog_ready
  );

-- A ready catalog row means revision 1 was already bundled before this
-- revision-aware workflow existed. Approved-but-unbundled rows remain at 0.
UPDATE cosmetic_submissions cs
SET published_placement_revision = 1
FROM shop_items si
WHERE cs.status = 'approved'
  AND cs.placement_revision = 1
  AND cs.published_placement_revision = 0
  AND cs.shop_sku = si.sku
  AND si.catalog_ready
  AND (SELECT needs_placement_backfill FROM scr_migration_148_state);

UPDATE cosmetic_submissions
SET placement_status = 'denied'
WHERE status = 'denied'
  AND placement_status = 'pending'
  AND (SELECT needs_placement_backfill FROM scr_migration_148_state);

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_cosmetic_published_revision_approved'
          AND conrelid = 'cosmetic_submissions'::regclass
    ) THEN
        ALTER TABLE cosmetic_submissions
            ADD CONSTRAINT ck_cosmetic_published_revision_approved
            CHECK (
                published_placement_revision = 0
                OR (
                    approved_placement_revision IS NOT NULL
                    AND published_placement_revision <= approved_placement_revision
                )
            );
    END IF;
END;
$migration$;

-- Release tooling must consume this view rather than proposal render_* fields.
-- It exposes only admin-approved revisions that have not yet shipped.
CREATE OR REPLACE VIEW cosmetic_release_candidates AS
SELECT cs.id, cs.shop_sku, cs.name, cs.slot, cs.png_data, cs.png_bytes,
       cs.approved_render_scale AS render_scale,
       cs.approved_render_offset_x AS render_offset_x,
       cs.approved_render_offset_y AS render_offset_y,
       cs.approved_placement_revision AS placement_revision,
       cs.published_placement_revision
FROM cosmetic_submissions cs
WHERE cs.status = 'approved'
  AND cs.approved_placement_revision IS NOT NULL
  AND cs.approved_placement_revision > cs.published_placement_revision;

ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS local_macro_peak_kps SMALLINT,
    ADD COLUMN IF NOT EXISTS local_macro_peak_cps SMALLINT,
    ADD COLUMN IF NOT EXISTS local_macro_peak_eps SMALLINT,
    ADD COLUMN IF NOT EXISTS local_macro_timeline VARCHAR(1024);

ALTER TABLE flagged_matches
    ADD COLUMN IF NOT EXISTS restoration_required BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS discord_evidence_revision INTEGER NOT NULL DEFAULT 1
        CHECK (discord_evidence_revision >= 1);

-- Only flags whose match is STILL invalidated actually need manual repair. The
-- older review path already un-invalidated several historical false positives;
-- marking those restoration_required would put permanent phantom repair work in
-- the admin queue for matches that were fixed months ago.
UPDATE flagged_matches fm
SET restoration_required = TRUE
FROM matches m
WHERE fm.match_id = m.id
  AND fm.auto_invalidated
  AND fm.review_action = 'false_positive'
  AND m.invalidated_at IS NOT NULL
  AND (SELECT needs_restoration_backfill FROM scr_migration_148_state);

-- Durable Discord delivery: rows that predate this migration were handled by
-- the old cursor and must not be replayed en masse. New flags remain NULL until
-- the bot posts their evidence embed and acknowledges them.
DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'flagged_matches'
          AND column_name = 'discord_posted_at'
    ) THEN
        ALTER TABLE flagged_matches
            ADD COLUMN discord_posted_at TIMESTAMPTZ;
        UPDATE flagged_matches
        SET discord_posted_at = NOW()
        WHERE discord_posted_at IS NULL;
        -- Requeue only recent, still-unreviewed macro reports so the motivating
        -- cases receive the richer evidence embed. Historical clients did not
        -- retain exact windows; the embed labels that limitation explicitly.
        UPDATE flagged_matches
        SET discord_posted_at = NULL
        WHERE flag_reason = 'suspected_macro'
          AND reviewed_at IS NULL
          AND created_at >= NOW() - INTERVAL '14 days';
    END IF;
END;
$migration$;

-- Bind Discord acknowledgement to the exact evidence revision the bot
-- rendered. If details change between GET and ACK, the trigger advances the
-- revision and requeues the row; the stale ACK then cannot consume it.
CREATE OR REPLACE FUNCTION bump_flag_discord_evidence_revision()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.flag_details IS DISTINCT FROM OLD.flag_details THEN
        NEW.discord_evidence_revision =
            OLD.discord_evidence_revision + 1;
        NEW.discord_posted_at = NULL;
    END IF;
    RETURN NEW;
END;
$$;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_flag_discord_evidence_revision'
          AND tgrelid = 'flagged_matches'::regclass
    ) THEN
        CREATE TRIGGER trg_flag_discord_evidence_revision
        BEFORE UPDATE OF flag_details ON flagged_matches
        FOR EACH ROW
        EXECUTE FUNCTION bump_flag_discord_evidence_revision();
    END IF;
END;
$migration$;

CREATE INDEX IF NOT EXISTS idx_flagged_matches_discord_pending
    ON flagged_matches(created_at, id)
    WHERE discord_posted_at IS NULL;

-- Publication time is the day an item becomes renderable in the shipped
-- catalog, not the earlier approval/row-creation day. This makes every future
-- readiness flip stamp Newest Cosmetics correctly even if a release migration
-- forgets to set released_at explicitly.
CREATE OR REPLACE FUNCTION stamp_shop_item_catalog_release()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    approved_rev INTEGER;
BEGIN
    IF NEW.catalog_ready AND NOT OLD.catalog_ready THEN
        IF EXISTS (
            SELECT 1 FROM cosmetic_submissions cs WHERE cs.shop_sku = NEW.sku
        ) THEN
            SELECT cs.approved_placement_revision INTO approved_rev
            FROM cosmetic_submissions cs
            WHERE cs.shop_sku = NEW.sku
              AND cs.status = 'approved'
              AND cs.approved_placement_revision IS NOT NULL
            ORDER BY cs.approved_placement_revision DESC
            LIMIT 1;
            IF approved_rev IS NULL THEN
                -- No admin-approved placement exists: the art has no reviewed
                -- scale/offset to bundle, so shipping it would render wrong.
                RAISE EXCEPTION
                    'catalog_ready requires an admin-approved cosmetic placement revision for %', NEW.sku;
            END IF;
            -- Flipping catalog_ready IS the act of publishing: the release
            -- migration that sets it is the one shipping the PNG + CosmeticDef.
            -- Stamp the published revision here so the release cannot deadlock
            -- on a column nothing else writes.
            UPDATE cosmetic_submissions
            SET published_placement_revision = approved_rev
            WHERE shop_sku = NEW.sku
              AND status = 'approved'
              AND approved_placement_revision = approved_rev
              AND published_placement_revision < approved_rev;
        END IF;
        IF NEW.released_at IS NULL THEN
            NEW.released_at = NOW();
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_shop_item_catalog_release ON shop_items;
CREATE TRIGGER trg_shop_item_catalog_release
    BEFORE UPDATE OF catalog_ready ON shop_items
    FOR EACH ROW
    EXECUTE FUNCTION stamp_shop_item_catalog_release();

-- Face cosmetics render from a PNG + CosmeticDef bundled INTO the client, so a
-- newly inserted face row can never be renderable yet no matter how it was
-- created (admin approval, a direct INSERT, or a future release script). The
-- column DEFAULT is TRUE for non-face kinds (titles/trails/colors/nametags need
-- no bundled art), so gate faces at INSERT time instead of changing the default.
-- This is the durable fix for "an unreleased batch appeared in Newest Cosmetics
-- and pushed the real latest batch off the Home panel": the two rows that caused
-- it were inserted straight into shop_items and inherited catalog_ready = TRUE.
-- CONSEQUENCE FOR RELEASES: a migration that ships new face art must INSERT the
-- row and then explicitly `UPDATE shop_items SET catalog_ready = TRUE WHERE
-- sku = ...`. That is the documented flow anyway (learning #164) and the UPDATE
-- is what stamps released_at + publishes the approved placement revision.
CREATE OR REPLACE FUNCTION gate_new_face_shop_item()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.kind = 'face' AND NEW.catalog_ready THEN
        NEW.catalog_ready = FALSE;
        NEW.released_at = NULL;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_gate_new_face_shop_item ON shop_items;
CREATE TRIGGER trg_gate_new_face_shop_item
    BEFORE INSERT ON shop_items
    FOR EACH ROW
    EXECUTE FUNCTION gate_new_face_shop_item();

COMMIT;
