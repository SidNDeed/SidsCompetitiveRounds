-- 280: music batch 2 ACTIVATION MARKER (b2-impl-r1 N3): the operator-checked
--      gate that migration 281 (attribute + flip) asserts inside its own
--      transaction. Applying THIS file is the operator's signed statement
--      that every external precondition below has been verified — 281 cannot
--      run without it, which turns the old prose "DO NOT APPLY UNTIL" header
--      into an executable fence.
--
-- APPLY ONLY AFTER VERIFYING ALL FIVE EXTERNAL PROBES (the design-v4-report
-- Required order, steps 1-3 + constants + assets — none of these are
-- observable from inside the database, which is why the gate is a marker an
-- OPERATOR writes rather than a query 281 could run itself):
--   1. Migrations 278 + 279 are applied on the PRIMARY and the standby has
--      replayed them (sql-readonly on the standby: music_ratings exists with
--      intent_rev + the XOR check, shop_items.music_track_count populated,
--      chk_music_album_no_stock present, deploy_markers exists).
--   2. The HARDENED api is live on BOTH boxes (#422/#429): strict-session
--      artist mutations INCLUDING the submission/placement family and the
--      two private reads (N1), /artist/set-stock 409 for music,
--      strict-session music purchases with the attribution-keyed
--      expected_price contract (N2), fail-closed royalty accounting with
--      beneficiary persistence (N8), /music/rate with intent_rev ordering
--      (N5) + per-track debounce (N10), and music_ratings deletion coverage
--      in delete_player_data. Applying 281 against the OLD api exposes
--      historical buyers via the unauthenticated artist reads, activates
--      HMAC-only stock/block authority over a live album, and pays 30% on a
--      1000g album (M10's exact scenario).
--   3. The v1.40.0 client release EXISTS on GitHub (its MusicCatalog carries
--      music_album_clavar_la_bala with 12 tracks, sends expected_price +
--      intent_rev, and handles the price_changed 409 by refetching).
--   4. MUSIC_SKU_MIN_VERSIONS and MUSIC_PURCHASE_MIN_VERSION on BOTH boxes
--      carry the version Sid actually named (staged "1.40.0"; if he names
--      differently, fix the constants FIRST — #294).
--   5. The immutable music-ar2 asset release EXISTS and
--      scripts/verify_music_release.py passes for BOTH albums' zips at the
--      exact public client URLs.
--
-- Idempotent (#243): ON CONFLICT DO NOTHING — a rerun re-asserts, never
-- duplicates. Explicit BEGIN/COMMIT (#340). v_ prefixed PL/pgSQL vars (#442).

BEGIN;

INSERT INTO deploy_markers (key)
VALUES ('music_activation_v1400_ready')
ON CONFLICT (key) DO NOTHING;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM deploy_markers dm
                    WHERE dm.key = 'music_activation_v1400_ready') THEN
        RAISE EXCEPTION 'post-check FAILED: music_activation_v1400_ready marker row missing after insert';
    END IF;
    RAISE NOTICE 'post-check OK: music_activation_v1400_ready marker set — migration 281 is now unlocked';
END $$;

COMMIT;
