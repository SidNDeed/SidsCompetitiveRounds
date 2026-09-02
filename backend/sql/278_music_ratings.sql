-- 278: music track ratings schema + server-authoritative track registry
--      (music batch 2, design-v4-report M11/M12/M20).
--
-- ADDITIVE ONLY — safe to apply before the hardened api deploys (the report's
-- Required order step 1: schema first, verify replica replay, then code).
-- Nothing reads these objects until the api that ships /music/rate lands.
--
-- music_ratings is TWO-PHASE by design (M11): a write lands in the pending_*
-- columns with a randomized 2-24h maturation stamp; published_stars moves ONLY
-- when the server folds a matured pending (UPDATE ... WHERE pending_effective_at
-- <= NOW()). Re-rates and clears therefore never produce an immediate public
-- edge — the old published contribution stands until the replacement (or the
-- clear tombstone, pending_is_clear) matures. Nothing outside the fold may
-- write published_stars.
--
-- shop_items.music_track_count is the server-authoritative track registry
-- (M12): a rating write is accepted only for 0 <= track_idx < the row's
-- registered count. NULL = not ratable (no registry), which also covers every
-- non-music row. The client catalog's track list must match this number at the
-- release that ships the album (#294-class ship coupling, asserted per-album by
-- the release migrations).
--
-- Idempotent statement-by-statement (#243: the migrate verb's || retry re-runs
-- the whole file). Explicit BEGIN/COMMIT (#340). v_ prefixed PL/pgSQL vars,
-- never bare column names (#442). Dry-run 2026-09-02 against prod (#313):
-- music_ratings absent, shop_items.music_track_count absent, exactly one
-- kind='music_album' row (music_album_another_round, live, 7 tracks in the
-- shipped MusicCatalog).

BEGIN;

CREATE TABLE IF NOT EXISTS music_ratings (
    id                   BIGSERIAL PRIMARY KEY,
    -- FK note (#437): delete_player_data ANONYMIZES the players row in place,
    -- so ON DELETE CASCADE is decorative there by construction — the endpoint
    -- deletes these rows EXPLICITLY (M15). The cascade still covers any true
    -- row deletion (manual repair, test cleanup).
    player_id            UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    sku                  VARCHAR(64) NOT NULL,
    track_idx            INT NOT NULL,
    -- The PUBLIC contribution. NULL = nothing published (fresh row, or a
    -- matured clear). 1..5 when set.
    published_stars      SMALLINT NULL CHECK (published_stars BETWEEN 1 AND 5),
    -- The latest un-matured intent. pending_effective_at IS NOT NULL <=> a
    -- pending exists; pending_is_clear TRUE = the intent is "remove my
    -- rating" (stars NULL), else pending_stars carries the new value.
    pending_stars        SMALLINT NULL CHECK (pending_stars BETWEEN 1 AND 5),
    pending_is_clear     BOOLEAN NOT NULL DEFAULT FALSE,
    pending_effective_at TIMESTAMPTZ NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One stored slot per player/track (M19's rewording): the UPSERT target.
    UNIQUE (player_id, sku, track_idx),
    -- Coherence: a pending payload cannot exist without its maturation stamp,
    -- and a clear-intent row cannot also carry pending stars.
    CONSTRAINT chk_music_ratings_pending_coherent
        CHECK (pending_effective_at IS NOT NULL
               OR (pending_stars IS NULL AND pending_is_clear = FALSE)),
    CONSTRAINT chk_music_ratings_clear_exclusive
        CHECK (NOT (pending_is_clear AND pending_stars IS NOT NULL))
);

-- Aggregate reads group by (sku, track_idx); the UNIQUE above already serves
-- per-player lookups (it is a btree on player_id, sku, track_idx).
CREATE INDEX IF NOT EXISTS idx_music_ratings_sku_track
    ON music_ratings (sku, track_idx);

-- Track registry column (M12). SMALLINT NULL: NULL = no registry = not
-- ratable. No CHECK here — the api validates 1..64 bounds on write, and the
-- release migrations pin each album's exact value.
ALTER TABLE shop_items ADD COLUMN IF NOT EXISTS music_track_count SMALLINT;

-- Register the live album's track count: 7 (the shipped MusicCatalog entry
-- for music_album_another_round — 7-track album, floor 1.39.7). Guarded +
-- ROW_COUNT-asserted (the 277 pattern): rerun-safe (7 -> 7 matches the guard
-- again), and a drifted value RAISES instead of being silently overwritten.
DO $$
DECLARE
    v_updated INT;
BEGIN
    UPDATE shop_items
       SET music_track_count = 7
     WHERE shop_items.sku = 'music_album_another_round'
       AND shop_items.kind = 'music_album'
       AND (shop_items.music_track_count IS NULL
            OR shop_items.music_track_count = 7);
    GET DIAGNOSTICS v_updated = ROW_COUNT;
    IF v_updated <> 1 THEN
        RAISE EXCEPTION 'post-check FAILED: track-count registration for music_album_another_round affected % rows (want exactly 1) - row missing, wrong kind, or a conflicting registered count',
                        v_updated;
    END IF;
    RAISE NOTICE 'post-check OK: music_album_another_round registered at 7 tracks';
END $$;

-- Structural post-check: the table + registry column exist with the expected
-- shape (a rerun after a partial first attempt must end in the same state).
DO $$
DECLARE
    v_cols INT;
BEGIN
    SELECT COUNT(*) INTO v_cols
      FROM information_schema.columns
     WHERE table_name = 'music_ratings'
       AND column_name IN ('id', 'player_id', 'sku', 'track_idx',
                           'published_stars', 'pending_stars',
                           'pending_is_clear', 'pending_effective_at',
                           'created_at', 'updated_at');
    IF v_cols <> 10 THEN
        RAISE EXCEPTION 'post-check FAILED: music_ratings has %/10 expected columns', v_cols;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'shop_items'
                      AND column_name = 'music_track_count') THEN
        RAISE EXCEPTION 'post-check FAILED: shop_items.music_track_count missing';
    END IF;
    RAISE NOTICE 'post-check OK: music_ratings table + shop_items.music_track_count in place';
END $$;

COMMIT;
