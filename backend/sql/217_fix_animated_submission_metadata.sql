-- 217: correct frame_count / anim_fps on the two animated cosmetics whose
-- submission rows predate the animation columns.
--
-- Migration 204 added cosmetic_submissions.frame_count (NOT NULL DEFAULT 1)
-- and anim_fps (nullable). Two already-shipped cosmetics were approved BEFORE
-- that, so their rows still claim to be static while the shipped client
-- renders them animated:
--
--   face_detail_magical_hat  10 frames @ 2.50 fps   (migration 197, predates 204)
--   face_detail_dark_aura     4 frames @ 7.00 fps
--
-- The values below are read off the two sources that actually ship, not
-- guessed: the frame files in plugin/cosmetics/ (detail_magical_hat.png plus
-- __f2..__f10; detail_dark_aura.png plus __f2..__f4) and the Fps field on each
-- CosmeticDef in plugin/CustomCosmetics.cs (2.5f and 7f respectively).
--
-- WHY IT MATTERS: neither row is in the release-candidate set today
-- (approved_placement_revision = published_placement_revision on both — 1 for
-- magical_hat, 2 for dark_aura — and catalog_ready is already true on both
-- shop rows; verified against production). But the moment an artist proposes a new
-- placement, the row re-enters that set advertising itself as static, and the
-- packaging pass in the ship runbook keys its animated handling off exactly
-- these two columns.
--
-- KNOWN RESIDUAL, stated rather than implied: cosmetic_submission_frames holds
-- NO rows for either submission (the whole table is empty). Their frames were
-- produced by the offline scripts/gif_to_cosmetic.py path and live in the repo
-- under plugin/cosmetics/, which is what is actually bundled into
-- cosmetics.zip. So this migration makes the metadata truthful about the
-- shipped art; it does NOT make the frames re-extractable from the database.
-- For these two the repo is the source of truth for frame DATA. The NOTICE at
-- the bottom prints that state so it is visible in the migration output.
--
-- Rerun-safe: the WHERE clause only matches the un-corrected shape, so a
-- second run (the deploy wrapper re-runs the file on any nonzero exit) updates
-- zero rows. It also cannot reach any other row: both the sku list and the
-- pre-correction values must match.

BEGIN;

UPDATE cosmetic_submissions AS cs
   SET frame_count = v.frames,
       anim_fps    = v.fps
  FROM (VALUES
          ('face_detail_magical_hat', 10, 2.5::real),
          ('face_detail_dark_aura',    4, 7.0::real)
       ) AS v(sku, frames, fps)
 WHERE cs.shop_sku = v.sku
   -- Only the stale shape. Never overwrite a value someone has already fixed.
   AND cs.frame_count = 1
   AND cs.anim_fps IS NULL;

DO $$
DECLARE
    targets TEXT[] := ARRAY['face_detail_magical_hat', 'face_detail_dark_aura'];
    missing TEXT;
    wrong INTEGER;
    orphan_frames INTEGER;
BEGIN
    -- EXISTENCE FIRST (Codex Aug 12, server lens). The `wrong` count below can
    -- only see rows that exist, so a target row that is absent entirely left it
    -- at 0 and this migration reported success having corrected nothing —
    -- #314's shape, a check that cannot fail for the case it is meant to catch.
    -- Names the missing sku(s) rather than just failing, because "which one" is
    -- the whole question when this fires.
    SELECT string_agg(t, ', ' ORDER BY t) INTO missing
      FROM unnest(targets) AS t
     WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions cs WHERE cs.shop_sku = t);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION
            'post-check FAILED: no cosmetic_submissions row for %  (the frame_count/anim_fps correction had nothing to apply to)',
            missing;
    END IF;

    SELECT COUNT(*) INTO wrong
      FROM cosmetic_submissions cs
     WHERE cs.shop_sku = ANY(targets)
       AND (cs.frame_count IS DISTINCT FROM (CASE cs.shop_sku
                WHEN 'face_detail_magical_hat' THEN 10
                WHEN 'face_detail_dark_aura'   THEN 4 END)
        OR  cs.anim_fps IS DISTINCT FROM (CASE cs.shop_sku
                WHEN 'face_detail_magical_hat' THEN 2.5::real
                WHEN 'face_detail_dark_aura'   THEN 7.0::real END));
    IF wrong <> 0 THEN
        RAISE EXCEPTION
            'post-check FAILED: % animated submission row(s) still carry the wrong frame_count/anim_fps',
            wrong;
    END IF;

    SELECT COUNT(*) INTO orphan_frames
      FROM cosmetic_submissions cs
      LEFT JOIN cosmetic_submission_frames f ON f.submission_id = cs.id
     WHERE cs.shop_sku = ANY(targets)
       AND f.submission_id IS NULL;
    RAISE NOTICE 'post-check OK: both animated submissions corrected (% of 2 have no rows in cosmetic_submission_frames — expected, their frames ship from plugin/cosmetics/)',
        orphan_frames;
END $$;

COMMIT;
