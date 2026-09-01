-- Flip the six new dance rows live (see 274's header for the ordering design).
--
-- APPLY ONLY AFTER BOTH of:
--   1. the new api is deployed on BOTH boxes (#422 — the standby serves the
--      routed shop reads), so the DANCES_MIN_VERSION gate owns kind='dance'
--      exposure; and
--   2. the client release that ships Defs indexes 2-7 (the six routines in
--      plugin/DanceEmotes.cs) is published. DANCES_MIN_VERSION is per-KIND,
--      not per-sku, so it cannot distinguish a 2-dance client from an
--      8-dance client: flipping these before that release surfaces Buy-able
--      rows whose sku is unknown to shipped Defs — the preview self-clears
--      and the purchase renders nothing until the player updates. Timing
--      this flip at/after the client release is what closes that window
--      (raising DANCES_MIN_VERSION instead would also hide the original two
--      dances from clients that own them — do not).
-- Idempotent: the UPDATE is a no-op once the rows are TRUE.

BEGIN;

UPDATE shop_items SET catalog_ready = TRUE
 WHERE kind = 'dance' AND sku IN ('dance_jacks', 'dance_shimmy', 'dance_disco',
                                  'dance_helicopter', 'dance_robot', 'dance_floss');

-- The two v1 dances shipped with "Play it between rounds with the E wheel"
-- descriptions; CONTRACT v2 (this release) allows dancing mid-battle with
-- the input lock, so the stored text now asserts a retired rule (#351
-- class, in a DB row instead of a comment). Each WHERE pins the EXACT
-- retired text (#168: an unconditional rewrite would silently clobber any
-- later admin/migration revision on an accidental rerun — only the one
-- historical value is normalized).
UPDATE shop_items SET description = 'Hop to the beat, arms pumping. Dancing locks your controls for the duration.'
 WHERE sku = 'dance_bounce'
   AND description = 'Hop to the beat, arms pumping. Play it between rounds with the E wheel.';
UPDATE shop_items SET description = 'Sway and wave to the crowd. Dancing locks your controls for the duration.'
 WHERE sku = 'dance_wave'
   AND description = 'Sway and wave to the crowd. Play it between rounds with the E wheel.';

COMMIT;
