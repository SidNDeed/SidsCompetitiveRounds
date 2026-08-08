-- 204: Animated cosmetic submissions (Aug 7 batch item 8).
-- Frame 1 STAYS in cosmetic_submissions.png_data — every existing reader
-- (admin list, artist preview, release-candidates view, legacy bridge, the
-- 149/153/175/190/197 release-migration lineage) keeps working unmodified.
-- Frames 2..N live here; anim_fps is NULLABLE on purpose (#257): NULL means
-- "static submission", never "0 fps".
--
-- status='uploading' (new value on cosmetic_submissions.status) marks a
-- multi-frame upload in progress: invisible to admin review until the
-- finalize call proves frames 2..frame_count all arrived.
--
-- Deploy order: apply BEFORE the API deploy (new code writes these columns).

CREATE TABLE IF NOT EXISTS cosmetic_submission_frames (
    submission_id  BIGINT NOT NULL REFERENCES cosmetic_submissions(id) ON DELETE CASCADE,
    frame_no       INTEGER NOT NULL CHECK (frame_no >= 2),
    png_data       BYTEA   NOT NULL,
    png_bytes      INTEGER NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (submission_id, frame_no)
);

ALTER TABLE cosmetic_submissions ADD COLUMN IF NOT EXISTS frame_count INTEGER NOT NULL DEFAULT 1;
ALTER TABLE cosmetic_submissions ADD COLUMN IF NOT EXISTS anim_fps REAL;

-- Post-check.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'cosmetic_submission_frames' AND column_name = 'frame_no'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'cosmetic_submissions' AND column_name = 'anim_fps'
    ) THEN
        RAISE EXCEPTION 'post-check FAILED: animation frame schema missing';
    END IF;
    RAISE NOTICE 'migration 204 post-check OK: cosmetic_submission_frames + frame columns present';
END $$;
