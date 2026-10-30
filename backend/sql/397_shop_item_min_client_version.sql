-- 397_shop_item_min_client_version.sql
-- A shop item's minimum client version, and the table a release migration
-- records what it published in.
--
-- 1. shop_items.min_client_version (VARCHAR(16), NULL = no minimum). A face
--    is equippable only by a client whose CustomCosmetics.Catalog carries its
--    definition, and an older client the server still admits has none. The
--    api honours the column on every surface that lists or transfers an item
--    (main._client_meets_item_floor): /shop/items and /shop/newest omit an
--    item whose minimum is above the caller's X-Mod-Version, /shop/purchase
--    refuses such a caller before any gold moves, and /artist/gift refuses
--    unless the recipient's last-seen version (players.mod_version) is at or
--    above it -- a recipient with no recorded version is refused. The
--    comparison is numeric (a dotted version parsed to integers), never a
--    string compare. The CHECK admits dotted decimal numbers only; a value
--    the api cannot parse would hide the item from everyone (fail closed).
--    Every existing row stays NULL: nothing changes for any item until a
--    release migration sets a minimum (398 sets 1.41.0 on the five faces it
--    publishes).
--
-- 2. shop_item_release_provenance: one row per (release migration, shop
--    item) that a release migration published, holding what that migration
--    wrote: the release timestamp the publish trigger stamped, the published
--    placement revision, the minimum it set, and the description before and
--    after. A release rollback reverts a row only while it still carries
--    exactly those values, so it never undoes a later publication by a person
--    (a revision 2, a re-publish after an earlier rollback). The api never
--    reads it.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api, as two SHAs (learning #477):
-- the api's ShopItem model names the column, so an api deployed before this
-- file fails every shop read. Applying this file alone changes no behaviour
-- (every row NULL), so it may land any time before the api. Migration 398
-- (the v1.41.0 faces) needs both and lands only after the v1.41.0 release.
--
-- RE-RUNS. The ADD is guarded on the catalog, so a second run issues no
-- ALTER and takes no lock (ADD COLUMN IF NOT EXISTS alone takes ACCESS
-- EXCLUSIVE before it looks for the column). The post-check refuses a
-- same-named column of another type, which the guard alone would accept.
-- The table is CREATE ... IF NOT EXISTS and its post-check reads its columns.
-- Two runs at once need no extra lock: a second run whose guard read the
-- column as missing waits on the first's ACCESS EXCLUSIVE, and ADD COLUMN
-- IF NOT EXISTS looks again only once it holds that lock, so it adds
-- nothing; its CREATE TABLE runs after the first has committed. This file
-- reads no row value before writing one.
-- Explicit transaction (learning #340).
--
-- HOW LONG THE LOCK CAN LIVE (learning #1072). lock_timeout bounds only the
-- WAIT for shop_items' ACCESS EXCLUSIVE (5 s); once held it lives until
-- COMMIT. statement_timeout bounds the DO (25 s) and
-- idle_in_transaction_session_timeout ends a runner stopped between the DO
-- and COMMIT (5 s); they have separate budgets and PostgreSQL 16 has no
-- transaction_timeout, so the hold is bounded by 25 s + 5 s = 30 s plus the
-- COMMIT's local completion. PostgreSQL disables the statement timer before
-- it commits; synchronous_commit = local keeps that wait off any standby.
-- The ALTER rewrites no row (nullable, no default); its CHECK is validated
-- by one scan of shop_items (417 rows on the primary, read 2026-10-30).

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $m397$
DECLARE
  got text;
  cols text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_attribute a
                  WHERE a.attrelid = to_regclass(format('%I.shop_items', current_schema()))
                    AND a.attname = 'min_client_version'
                    AND NOT a.attisdropped) THEN
    ALTER TABLE shop_items ADD COLUMN IF NOT EXISTS min_client_version VARCHAR(16)
      CONSTRAINT ck_shop_items_min_client_version
      CHECK (min_client_version ~ '^[0-9]+(\.[0-9]+)*$');
    COMMENT ON COLUMN shop_items.min_client_version IS
      'The first client version that can equip or render this item. NULL = '
      'any admitted client. The api omits the item from listings for an older '
      'caller, refuses its purchase, and refuses a gift to a recipient whose '
      'last-seen version is older or unknown (migration 397).';
  END IF;

  CREATE TABLE IF NOT EXISTS shop_item_release_provenance (
    migration           TEXT         NOT NULL,
    shop_item_id        BIGINT       NOT NULL,
    submission_id       BIGINT       NOT NULL,
    released_at         TIMESTAMPTZ  NOT NULL,
    published_revision  INTEGER      NOT NULL,
    min_client_version  VARCHAR(16),
    description_before  VARCHAR(256),
    description_written VARCHAR(256),
    recorded_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (migration, shop_item_id)
  );

  -- Post-checks: the guards above only ask whether the names exist.
  SELECT format_type(a.atttypid, a.atttypmod) INTO got
    FROM pg_attribute a
   WHERE a.attrelid = to_regclass(format('%I.shop_items', current_schema()))
     AND a.attname = 'min_client_version'
     AND NOT a.attisdropped;
  IF got IS DISTINCT FROM 'character varying(16)' THEN
    RAISE EXCEPTION '397: shop_items.min_client_version is %, not character varying(16)',
      coalesce(got, 'missing');
  END IF;
  SELECT string_agg(a.attname, ',' ORDER BY a.attname) INTO cols
    FROM pg_attribute a
   WHERE a.attrelid = to_regclass(format('%I.shop_item_release_provenance', current_schema()))
     AND a.attnum > 0 AND NOT a.attisdropped;
  IF cols IS DISTINCT FROM 'description_before,description_written,migration,'
                           'min_client_version,published_revision,recorded_at,'
                           'released_at,shop_item_id,submission_id' THEN
    RAISE EXCEPTION '397: shop_item_release_provenance has columns (%), not the ones 397 creates',
      coalesce(cols, 'missing');
  END IF;
END $m397$;

COMMIT;
