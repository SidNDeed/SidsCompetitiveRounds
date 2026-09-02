-- 279: artist-commerce hardening invariants + seed the "Clavar la Bala" album
--      row born gated (music batch 2, design-v4-report M2/M9 + §1).
--
-- Requires 278 (shop_items.music_track_count). ADDITIVE + invariant-only —
-- safe to apply before the hardened api deploys (Required order step 1); the
-- new row is catalog_ready = FALSE and artist NULL, so it is invisible,
-- unpurchasable and has no artist mutation surface until migration 281 (the
-- ACTIVATION migration, gated by 280's operator marker) attributes + flips
-- it at the ship wave.
--
-- Three parts:
--   (a) player_items.royalty_paid / royalty_rate_pct /
--       royalty_artist_steam_id — persisted actual-paid royalty accounting
--       (M9) plus the BENEFICIARY the sale belonged to (N8: without it, an
--       admin reassignment moves historical /sales rows to the new artist
--       while the money went to the old one). NULL = legacy row (pre-column
--       purchase or gift/self-buy/no-royalty purchase); the hardened
--       purchase path writes all three IN THE PURCHASE TRANSACTION with no
--       savepoint swallow (this file deploys before that api per the
--       Required order, so the api-ahead window is gone), and
--       /artist/{id}/sales attributes rows by the stored beneficiary,
--       falling back to live item attribution only for legacy NULL rows.
--   (b) CHECK: music albums can never carry a stock cap (M2). NOT VALID +
--       VALIDATE so the ADD never rewrites the table; dry-run 2026-09-02
--       against prod (#313): 0 music rows with stock_limit set, so VALIDATE
--       passes. The api additionally 409s /artist/set-stock for the kind —
--       this constraint is the database's own word for it.
--   (c) The Clavar la Bala seed row (the 276 pattern: ON CONFLICT DO NOTHING
--       + full-contract post-check that RAISES on any mismatch). 12 tracks
--       registered at birth. Born gated: catalog_ready FALSE EXPLICITLY (the
--       148 INSERT trigger only forces FALSE for kind='face'; any other kind
--       inherits DEFAULT TRUE — the 276 lesson).
--
-- Idempotent statement-by-statement (#243). Explicit BEGIN/COMMIT (#340).
-- v_ prefixed PL/pgSQL vars (#442). Rerun-safe only UNTIL 281 attributes/
-- flips the row: after that a rerun RAISES on artist/catalog_ready by design
-- (a loud abort beats tolerating drift — 276's rule).

BEGIN;

-- (a) actual-paid royalty accounting (M9) + beneficiary link (N8)
ALTER TABLE player_items ADD COLUMN IF NOT EXISTS royalty_paid INTEGER;
ALTER TABLE player_items ADD COLUMN IF NOT EXISTS royalty_rate_pct SMALLINT;
-- Who the sale's royalty belonged to (the item's attributed artist at
-- purchase time — stored even when the credit could not land, with
-- royalty_paid = 0, so the sales log never migrates to a later assignee).
ALTER TABLE player_items ADD COLUMN IF NOT EXISTS royalty_artist_steam_id VARCHAR(20);

-- (b) music stock invariant (M2)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'chk_music_album_no_stock') THEN
        ALTER TABLE shop_items
            ADD CONSTRAINT chk_music_album_no_stock
            CHECK (kind <> 'music_album' OR stock_limit IS NULL) NOT VALID;
    END IF;
END $$;
-- Re-VALIDATE is a fast no-op on an already-valid constraint (rerun-safe).
ALTER TABLE shop_items VALIDATE CONSTRAINT chk_music_album_no_stock;

-- (c) Clavar la Bala, born gated. artist_steam_id NULL FOR NOW (no mutation
-- surface, no claimable royalty — attribution is 280's job, M10); price is
-- the launch price and, with artist NULL, can only change by migration until
-- attribution.
INSERT INTO shop_items (sku, kind, name, description, price, rarity,
                        preview_color, rotation_pool, artist_steam_id,
                        stock_limit, catalog_ready, music_track_count)
VALUES ('music_album_clavar_la_bala', 'music_album', 'Clavar la Bala',
        '12-track Flamenco Metal album', 1000, 'legendary', '#D62839',
        NULL, NULL, NULL, FALSE, 12)
ON CONFLICT (sku) DO NOTHING;

-- Full-contract post-check (the 276 pattern widened to music_track_count):
-- a pre-existing conflicting sku aborts the whole transaction loudly instead
-- of being silently adopted.
DO $$
DECLARE
    v_count INT;
    v_row   RECORD;
BEGIN
    SELECT COUNT(*) INTO v_count
      FROM shop_items si
     WHERE si.sku = 'music_album_clavar_la_bala';
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'post-check FAILED: % rows for music_album_clavar_la_bala (want exactly 1)',
                        v_count;
    END IF;

    SELECT si.kind, si.name, si.description, si.price, si.rarity,
           si.preview_color, si.rotation_pool, si.artist_steam_id,
           si.stock_limit, si.catalog_ready, si.released_at,
           si.music_track_count
      INTO v_row
      FROM shop_items si
     WHERE si.sku = 'music_album_clavar_la_bala';

    IF v_row.kind            IS DISTINCT FROM 'music_album'
       OR v_row.name         IS DISTINCT FROM 'Clavar la Bala'
       OR v_row.description  IS DISTINCT FROM '12-track Flamenco Metal album'
       OR v_row.price        IS DISTINCT FROM 1000
       OR v_row.rarity       IS DISTINCT FROM 'legendary'
       OR v_row.preview_color IS DISTINCT FROM '#D62839'
       OR v_row.rotation_pool IS NOT NULL
       OR v_row.artist_steam_id IS NOT NULL
       OR v_row.stock_limit  IS NOT NULL
       OR v_row.catalog_ready IS DISTINCT FROM FALSE
       OR v_row.released_at  IS NOT NULL
       OR v_row.music_track_count IS DISTINCT FROM 12::smallint THEN
        RAISE EXCEPTION 'post-check FAILED: music_album_clavar_la_bala does not match the pinned contract '
                        '(kind=%, name=%, desc=%, price=%, rarity=%, color=%, pool=%, artist=%, stock=%, ready=%, released=%, tracks=%)',
                        v_row.kind, v_row.name, v_row.description, v_row.price,
                        v_row.rarity, v_row.preview_color, v_row.rotation_pool,
                        v_row.artist_steam_id, v_row.stock_limit,
                        v_row.catalog_ready, v_row.released_at,
                        v_row.music_track_count;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'player_items'
                      AND column_name IN ('royalty_paid', 'royalty_rate_pct',
                                          'royalty_artist_steam_id')
                   HAVING COUNT(*) = 3) THEN
        RAISE EXCEPTION 'post-check FAILED: player_items royalty columns missing';
    END IF;

    RAISE NOTICE 'post-check OK: royalty columns + music-stock invariant in place; music_album_clavar_la_bala seeded, born gated (catalog_ready = FALSE, 12 tracks)';
END $$;

COMMIT;
