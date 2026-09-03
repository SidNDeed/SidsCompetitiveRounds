-- 285: Clavar la Bala grows from 12 to 14 tracks (v1.40.1, music revision ar3).
--
-- The ar2 master missed two of the album's tracks ("Principio de Ronda" and
-- "Nube Toxica"); they are APPENDED as track_idx 12 and 13 so every existing
-- (sku, track_idx) identity — ratings, plays, previews — stays stable. This
-- migration deploys WITH the v1.40.1 API: POST /music/rate validates
-- track_idx against shop_items.music_track_count, so a 1.40.1 client rating
-- track 13 or 14 is rejected until this row says 14. Clients below 1.40.1
-- never address those indices (their compiled catalog stops at 12).
--
-- Guards pin ONLY the immutable identity of the row (sku, kind, the track
-- count); name and description are ARTIST-EDITABLE storefront text (the
-- Artist tab's Name / About actions, storefront-only per the API) and are
-- never a precondition or a postcondition (Codex r18 finding 2). The stock
-- "12-track" description is rewritten to "14-track" only while it is still
-- the stock text; an artist-authored description is preserved verbatim.
-- First application asserts ROW_COUNT = 1; a rerun (already 14) performs no
-- write; the post-check runs either way. Explicit BEGIN/COMMIT (#340);
-- v_ prefixed PL/pgSQL variables (#442); the row read takes FOR NO KEY
-- UPDATE, never FOR UPDATE (#202 — a concurrent purchase's player_items FK
-- insert holds KEY SHARE on this row).

BEGIN;

DO $$
DECLARE
    v_count   SMALLINT;
    v_updated INT;
BEGIN
    SELECT si.music_track_count
      INTO v_count
      FROM shop_items si
     WHERE si.sku = 'music_album_clavar_la_bala'
       AND si.kind = 'music_album'
       FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'pre-check FAILED: no music_album row for music_album_clavar_la_bala (279 not applied?)';
    END IF;

    IF v_count = 14 THEN
        RAISE NOTICE 'RERUN: music_album_clavar_la_bala already at 14 tracks - no update performed, post-check still enforced';
    ELSIF v_count <> 12 THEN
        RAISE EXCEPTION 'pre-check FAILED: music_album_clavar_la_bala is at % tracks - neither the 12-track pre-state nor the 14-track post-state; refusing to write',
                        v_count;
    ELSE
        UPDATE shop_items
           SET music_track_count = 14,
               description = CASE WHEN description = '12-track Flamenco Metal album'
                                  THEN '14-track Flamenco Metal album'
                                  ELSE description END
         WHERE shop_items.sku = 'music_album_clavar_la_bala'
           AND shop_items.kind = 'music_album'
           AND shop_items.music_track_count = 12;
        GET DIAGNOSTICS v_updated = ROW_COUNT;
        IF v_updated <> 1 THEN
            RAISE EXCEPTION 'first application FAILED: clavar track-count update affected % rows (want exactly 1)',
                            v_updated;
        END IF;
        RAISE NOTICE 'first application: music_album_clavar_la_bala now 14 tracks (1 row)';
    END IF;
END $$;

-- Post-check: identity + the new track count + the shipped/live state the
-- v1.40.1 client relies on. Name/description are NOT pinned (artist-editable);
-- the stale stock "12-track" text must be gone.
DO $$
DECLARE
    v_row RECORD;
BEGIN
    SELECT si.kind, si.description, si.catalog_ready, si.released_at, si.music_track_count
      INTO v_row
      FROM shop_items si
     WHERE si.sku = 'music_album_clavar_la_bala';
    IF NOT FOUND
       OR v_row.kind IS DISTINCT FROM 'music_album'
       OR v_row.music_track_count IS DISTINCT FROM 14::smallint
       OR v_row.catalog_ready IS DISTINCT FROM TRUE
       OR v_row.released_at IS NULL
       OR v_row.description = '12-track Flamenco Metal album' THEN
        RAISE EXCEPTION 'post-check FAILED: music_album_clavar_la_bala is not live at 14 tracks (kind=%, desc=%, ready=%, released=%, tracks=%)',
                        v_row.kind, v_row.description, v_row.catalog_ready, v_row.released_at, v_row.music_track_count;
    END IF;
    RAISE NOTICE 'post-check OK: music_album_clavar_la_bala LIVE at 14 tracks';
END $$;

COMMIT;
