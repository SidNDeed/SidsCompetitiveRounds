-- 281: ACTIVATION migration (music batch 2 ship wave, design-v4-report M10):
--      attribute BOTH albums to the artist and flip Clavar la Bala live.
--
-- MACHINE-GATED (b2-impl-r1 N3): the first block asserts the
-- 'music_activation_v1400_ready' deploy_markers row that migration 280
-- writes — 280's header carries the five external probes the operator must
-- verify BEFORE setting it, so applying this file out of order aborts on the
-- assertion instead of attributing albums under an unhardened api. The old
-- prose "DO NOT APPLY UNTIL ALL FIVE HOLD" header is now 280's job.
--
-- Attribution consequences (deliberate, owner-authorized): the artist gains
-- set-name/set-price/set-desc/gift over both rows through the now
-- strict-session-guarded endpoints; music purchases start paying the 50%
-- royalty to the attributed artist. Album 1's price stays 1g until the artist
-- changes it in-game (this file changes no price).
--
-- The artist steam id appears as a LITERAL below (b2-impl-r1 N4, REFUTED by
-- the integrator): SHOP_OWNER_STEAM_IDS in tracked main.py is the standing
-- public precedent for a steam id in this repo — a steam id is a public
-- platform handle already shown on the artist's own shop rows, not a private
-- identity value, and an indirection table would only move the same literal
-- one file over. It stays inline so the migration is self-contained and
-- auditable.
--
-- Both writes are guarded on the exact pre-state (277 pattern: ROW_COUNT
-- assert on first application, a SEPARATELY-IDENTIFIED rerun branch, full
-- live-contract post-check either way). The 148 catalog_ready trigger fires
-- on the Clavar flip and stamps released_at (no cosmetic_submissions row may
-- exist for the sku — asserted below rather than trusted). Explicit
-- BEGIN/COMMIT (#340); v_ prefixed PL/pgSQL vars (#442); row reads take
-- FOR NO KEY UPDATE, never FOR UPDATE (#202 — a concurrent purchase's
-- player_items FK insert holds KEY SHARE on these rows).

BEGIN;

-- ── Gate: operator marker (N3) + live attributable target (N18) ─────────────
DO $$
DECLARE
    v_live_players INT;
BEGIN
    -- N3: the executable rollout fence. Migration 280 writes this row only
    -- after its header's five external probes pass.
    IF NOT EXISTS (SELECT 1 FROM deploy_markers dm
                    WHERE dm.key = 'music_activation_v1400_ready') THEN
        RAISE EXCEPTION 'gate FAILED: deploy_markers row music_activation_v1400_ready is absent - apply migration 280 (after verifying its five external probes) before this activation';
    END IF;

    -- N18: attribution needs a live beneficiary with the artist role — a
    -- revoked role or an anonymized/deleted account before this point would
    -- otherwise satisfy every row-shape post-check while leaving both albums
    -- unmanageable and royalties with no live recipient.
    SELECT COUNT(*) INTO v_live_players
      FROM players p
     WHERE p.steam_id = '76561198040410653'
       AND p.deleted_at IS NULL;
    IF v_live_players <> 1 THEN
        RAISE EXCEPTION 'gate FAILED: expected exactly 1 live non-deleted players row for the target artist, found % - refusing to attribute',
                        v_live_players;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM artist_users au
                    WHERE au.steam_id = '76561198040410653') THEN
        RAISE EXCEPTION 'gate FAILED: target has no artist_users role row - grant the artist role before attribution';
    END IF;
    RAISE NOTICE 'gate OK: activation marker present; target is a live player with the artist role';
END $$;

-- ── Album 1: attribute music_album_another_round ────────────────────────────
DO $$
DECLARE
    v_artist  VARCHAR;
    v_updated INT;
BEGIN
    SELECT si.artist_steam_id INTO v_artist
      FROM shop_items si
     WHERE si.sku = 'music_album_another_round'
       FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'pre-check FAILED: no shop_items row for music_album_another_round (276 not applied?)';
    END IF;

    IF v_artist = '76561198040410653' THEN
        RAISE NOTICE 'RERUN: music_album_another_round already attributed - no update performed';
    ELSIF v_artist IS NOT NULL THEN
        RAISE EXCEPTION 'pre-check FAILED: music_album_another_round is attributed to a DIFFERENT artist (%) - refusing to reassign',
                        v_artist;
    ELSE
        UPDATE shop_items SET artist_steam_id = '76561198040410653'
         WHERE shop_items.sku = 'music_album_another_round'
           AND shop_items.kind = 'music_album'
           AND shop_items.name = 'Another Round'
           AND shop_items.rarity = 'epic'
           AND shop_items.rotation_pool IS NULL
           AND shop_items.artist_steam_id IS NULL
           AND shop_items.stock_limit IS NULL
           AND shop_items.catalog_ready = TRUE
           AND shop_items.released_at IS NOT NULL
           AND shop_items.music_track_count = 7;
        GET DIAGNOSTICS v_updated = ROW_COUNT;
        IF v_updated <> 1 THEN
            RAISE EXCEPTION 'first application FAILED: album-1 attribution affected % rows (want exactly 1) - the row drifted from the expected live pre-state (277 flipped + 278 track count)',
                            v_updated;
        END IF;
        RAISE NOTICE 'first application: music_album_another_round attributed (1 row)';
    END IF;
END $$;

-- ── Album 2: attribute + flip music_album_clavar_la_bala ────────────────────
DO $$
DECLARE
    v_already_live BOOLEAN;
    v_artist       VARCHAR;
    v_updated      INT;
BEGIN
    -- The 148 trigger consults cosmetic_submissions on every catalog_ready
    -- flip; a row there would demand an approved placement revision and abort
    -- the flip. Music rows never have one — assert instead of trusting.
    IF EXISTS (SELECT 1 FROM cosmetic_submissions cs
                WHERE cs.shop_sku = 'music_album_clavar_la_bala') THEN
        RAISE EXCEPTION 'pre-check FAILED: unexpected cosmetic_submissions row for music_album_clavar_la_bala';
    END IF;

    SELECT si.catalog_ready, si.artist_steam_id
      INTO v_already_live, v_artist
      FROM shop_items si
     WHERE si.sku = 'music_album_clavar_la_bala'
       FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'pre-check FAILED: no shop_items row for music_album_clavar_la_bala (279 not applied?)';
    END IF;

    IF v_already_live AND v_artist = '76561198040410653' THEN
        RAISE NOTICE 'RERUN: music_album_clavar_la_bala already live + attributed - no update performed, post-check still enforced';
    ELSIF v_artist IS NOT NULL AND v_artist <> '76561198040410653' THEN
        RAISE EXCEPTION 'pre-check FAILED: music_album_clavar_la_bala is attributed to a DIFFERENT artist (%) - refusing to reassign',
                        v_artist;
    ELSE
        -- One UPDATE for both columns so the row is never live-but-unowned:
        -- guarded on the COMPLETE 279 pre-state (minus the two columns being
        -- written). Covers the partial rerun where a prior attempt died
        -- between the two DO blocks only via the full-contract post-check.
        UPDATE shop_items SET artist_steam_id = '76561198040410653',
                              catalog_ready   = TRUE
         WHERE shop_items.sku = 'music_album_clavar_la_bala'
           AND shop_items.kind = 'music_album'
           AND shop_items.name = 'Clavar la Bala'
           AND shop_items.description = '12-track Flamenco Metal album'
           AND shop_items.price = 1000
           AND shop_items.rarity = 'legendary'
           AND shop_items.preview_color = '#D62839'
           AND shop_items.rotation_pool IS NULL
           AND shop_items.artist_steam_id IS NULL
           AND shop_items.stock_limit IS NULL
           AND shop_items.catalog_ready = FALSE
           AND shop_items.released_at IS NULL
           AND shop_items.music_track_count = 12;
        GET DIAGNOSTICS v_updated = ROW_COUNT;
        IF v_updated <> 1 THEN
            RAISE EXCEPTION 'first application FAILED: clavar attribution+flip affected % rows (want exactly 1) - the row drifted from the 279 pre-state contract',
                            v_updated;
        END IF;
        RAISE NOTICE 'first application: music_album_clavar_la_bala attributed + flipped live (1 row)';
    END IF;
END $$;

-- ── Post-check: both albums live, attributed, correctly registered ──────────
DO $$
DECLARE
    v_row RECORD;
BEGIN
    FOR v_row IN
        SELECT si.sku, si.kind, si.artist_steam_id, si.stock_limit,
               si.catalog_ready, si.released_at, si.music_track_count,
               si.rotation_pool
          FROM shop_items si
         WHERE si.sku IN ('music_album_another_round',
                          'music_album_clavar_la_bala')
         ORDER BY si.sku
    LOOP
        IF v_row.kind IS DISTINCT FROM 'music_album'
           OR v_row.artist_steam_id IS DISTINCT FROM '76561198040410653'
           OR v_row.stock_limit IS NOT NULL
           OR v_row.rotation_pool IS NOT NULL
           OR v_row.catalog_ready IS DISTINCT FROM TRUE
           OR v_row.released_at IS NULL
           OR v_row.music_track_count IS DISTINCT FROM
              (CASE v_row.sku WHEN 'music_album_another_round' THEN 7::smallint
                              ELSE 12::smallint END) THEN
            RAISE EXCEPTION 'post-check FAILED: % is not live+attributed with the pinned contract (kind=%, artist=%, stock=%, pool=%, ready=%, released=%, tracks=%)',
                            v_row.sku, v_row.kind, v_row.artist_steam_id,
                            v_row.stock_limit, v_row.rotation_pool,
                            v_row.catalog_ready, v_row.released_at,
                            v_row.music_track_count;
        END IF;
    END LOOP;

    IF (SELECT COUNT(*) FROM shop_items si
         WHERE si.sku IN ('music_album_another_round',
                          'music_album_clavar_la_bala')) <> 2 THEN
        RAISE EXCEPTION 'post-check FAILED: expected exactly 2 album rows';
    END IF;

    RAISE NOTICE 'post-check OK: both albums LIVE and attributed to the artist';
END $$;

COMMIT;
