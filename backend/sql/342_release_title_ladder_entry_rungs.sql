-- 342_release_title_ladder_entry_rungs.sql — v1.41.0 item 12 release gate
--
-- Puts the eight tier-1 animal-title rungs on sale by flipping
-- shop_items.catalog_ready FALSE -> TRUE for them, and nothing else.
--
-- THIS FILE IS APPLIED LAST IN THE RELEASE TRAIN. Flipping catalog_ready is
-- the act of PUBLISHING, not a schema act (learning #164), so it belongs at
-- the end of the release that makes the thing it publishes usable — after the
-- api carrying the ladder route is live on BOTH boxes, and after the
-- completion hook that lets a bought rung advance. Applied early it sells a
-- player a 1000-gold entry rung on a line that cannot move, which is exactly
-- what migration 331 wrote its final-state guard to prevent. This is the
-- deliberate reverse of the usual migration-before-code order, and it is
-- reversed for that one reason.
--
-- IDEMPOTENT, AND THE REASON IS A TRIGGER. Migration 148 installs
-- `trg_shop_item_catalog_release` BEFORE UPDATE OF catalog_ready; its body
-- sits behind `IF NEW.catalog_ready AND NOT OLD.catalog_ready` and stamps
-- released_at = NOW(). Reading the migration cannot show you that — only the
-- server can (#714) — and a re-run that named the already-TRUE rows would
-- touch eight rows for no reason. The WHERE below excludes them, so a second
-- application updates ZERO rows and released_at keeps its first-release
-- timestamp. The trigger's other half (the approved-placement check) is
-- skipped for these rows because it is guarded on a `cosmetic_submissions`
-- row existing for the sku, and a title has none.
--
-- released_at is NEVER set by hand here. The trigger owns that column; a
-- manual write would disagree with every other release's stamp.
--
-- Requires migrations 147 (catalog_ready), 148 (the trigger) and 331 (the
-- ladder catalogue).

BEGIN;

-- Guard: the catalogue this file publishes must actually be present, in full.
-- A partial 331 would leave this flipping whichever rungs happened to exist,
-- and the post-check's "exactly 8" would then be satisfied by a different 8.
DO $migration$
DECLARE
    n_rungs   INTEGER;
    n_entry   INTEGER;
    n_missing INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_rungs FROM title_ladders;
    IF n_rungs <> 48 THEN
        RAISE EXCEPTION 'title ladders: expected 48 catalogue rungs, found % — apply 331 first', n_rungs;
    END IF;

    SELECT COUNT(*) INTO n_entry FROM title_ladders WHERE tier = 1;
    IF n_entry <> 8 THEN
        RAISE EXCEPTION 'title ladders: expected 8 entry rungs, found %', n_entry;
    END IF;

    -- Every catalogue rung must have its shop row, or an owner of a granted
    -- rung has nothing to equip and the read route reports item_id = null.
    SELECT COUNT(*) INTO n_missing
      FROM title_ladders tl
     WHERE NOT EXISTS (SELECT 1 FROM shop_items si WHERE si.sku = tl.sku);
    IF n_missing > 0 THEN
        RAISE EXCEPTION 'title ladders: % catalogue rung(s) have no shop_items row', n_missing;
    END IF;
END $migration$;

-- THE FLIP. Entry rungs only (tier = 1).
--
-- WHAT KEEPS THE OTHER 40 OUT OF THE SHOP IS NOT THIS FLAG. 331 inserts the
-- granted-only rungs with catalog_ready = TRUE already; what hides them is
-- rotation_pool = 'achievement', which /shop/items shows to an OWNER only and
-- which the purchase endpoint refuses by name. Reading their readiness as
-- the gate would be reading the wrong column — so the post-check below asserts
-- the pool and the price on those 40, not their readiness.
--
-- `IS DISTINCT FROM TRUE` is what makes a second run a no-op rather than a
-- second trigger firing.
UPDATE shop_items si
   SET catalog_ready = TRUE
  FROM title_ladders tl
 WHERE tl.sku = si.sku
   AND tl.tier = 1
   AND si.catalog_ready IS DISTINCT FROM TRUE;

-- Post-check on the FINAL STATE, not on what the UPDATE claimed to touch — so
-- it holds on the first run and on every re-run alike.
DO $migration$
DECLARE
    n_ready    INTEGER;
    n_leaked   INTEGER;
    n_pooled   INTEGER;
    n_unstamped INTEGER;
    n_priced   INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_ready
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier = 1 AND si.catalog_ready IS TRUE;
    IF n_ready <> 8 THEN
        RAISE EXCEPTION 'title ladders: expected 8 entry rungs on sale, found %', n_ready;
    END IF;

    -- The 40 above the entry rung must stay granted-only. They are already
    -- catalog_ready and priced 0, so the ONLY thing between them and a free
    -- legendary title for anyone who can name the sku is the pool string.
    SELECT COUNT(*) INTO n_leaked
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier > 1
       AND (si.rotation_pool IS DISTINCT FROM 'achievement' OR si.price <> 0);
    IF n_leaked <> 0 THEN
        RAISE EXCEPTION 'title ladders: % granted-only rung(s) left the achievement pool or gained a price', n_leaked;
    END IF;

    -- ...and the 8 must stay OUT of that pool, or the row this file just put
    -- on sale is refused at purchase and hidden from everyone who does not
    -- already own it.
    SELECT COUNT(*) INTO n_pooled
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier = 1 AND si.rotation_pool IS NOT NULL;
    IF n_pooled <> 0 THEN
        RAISE EXCEPTION 'title ladders: % entry rung(s) carry a rotation_pool and cannot be bought', n_pooled;
    END IF;

    -- The trigger owns released_at. If it did not stamp, the trigger is gone
    -- or was disabled, and this release is not recorded as having happened.
    SELECT COUNT(*) INTO n_unstamped
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier = 1 AND si.released_at IS NULL;
    IF n_unstamped > 0 THEN
        RAISE EXCEPTION 'title ladders: % entry rung(s) went on sale without released_at — is trg_shop_item_catalog_release installed?', n_unstamped;
    END IF;

    -- What a player is about to be charged. 331 wrote 1000; asserting it here
    -- means a price edit between the two migrations cannot ship silently.
    SELECT COUNT(*) INTO n_priced
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier = 1 AND si.price <> 1000;
    IF n_priced > 0 THEN
        RAISE EXCEPTION 'title ladders: % entry rung(s) are not priced 1000 g', n_priced;
    END IF;
END $migration$;

COMMIT;
