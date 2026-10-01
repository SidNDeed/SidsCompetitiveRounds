-- 366_title_refunds_voidshot_kingslayer.sql
--
-- Removes two titles from the game and refunds every buyer (board row 29, the
-- ruling of 2026-09-28 10:00Z): Voidshot (title_voidshot, 069:47, 2500 gold;
-- its card "Empty Power" does not exist) and Kingslayer (title_regicide,
-- 021:55, 3000 gold; confusing beside Sid Slayer).
--
-- CENSUS (production primary, sql-readonly, 2026-10-01 05:17Z):
--   title_voidshot  0 holders, 0 purchase rows.
--   title_regicide  1 holder, paid 3000 (player_items.purchase_price 3000,
--                   one 'purchase' row of -3000), not equipped.
--   gold_transactions with reason 'title_refunded': 0.
--
-- FOR EACH HOLDER, in one transaction:
--   * the price paid comes back as a DELTA on the column the purchase path
--     debits: players.gold_spent = gold_spent - paid, guarded
--     gold_spent >= paid in the statement itself (the _return_stake_exactly
--     shape, #326: a refund is the amount or it is refused, never clamped);
--   * one gold_transactions row, +paid, reason 'title_refunded', reference
--     the sku;
--   * the title is unequipped where it is worn (no title);
--   * the inventory row is deleted.
-- Then both catalogue rows are RETIRED: catalog_ready FALSE, so /shop/items
-- does not list them and the purchase path refuses them. Their rows stay (the
-- purchase ledger names the sku; translation rows may stay), and the api's
-- shop-owner carve-out (title_ladders.RETIRED_SKUS) keeps an exempt account
-- from equipping one by sku. Anyone wearing one without owning it is
-- unequipped too.
--
-- PREFLIGHT, which refuses rather than guesses: it prints every holder, then
-- requires (paid holders now) + (refunds already written) to equal the census
-- for each sku, and each holder's purchase_price to equal what their own
-- 'purchase' rows debited. A purchase made after the census therefore stops
-- the file (re-census, then edit the census numbers below); a second run finds
-- no holder and the census's refund rows and writes nothing.
--
-- No dependency on the api build: it can apply before or after it. Explicit
-- BEGIN/COMMIT (#340).

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m366$
DECLARE
    r          RECORD;
    c          RECORD;
    n_now      INTEGER;
    n_done     INTEGER;
    paid_now   BIGINT;
    paid_done  BIGINT;
    moved      INTEGER;
    n_unworn   INTEGER;
    n_retired  INTEGER;
BEGIN
    -- The census, per sku: holders who paid, and the gold they paid.
    CREATE TEMP TABLE _m366_census (sku VARCHAR(64) PRIMARY KEY, holders INTEGER, paid BIGINT) ON COMMIT DROP;
    INSERT INTO _m366_census VALUES ('title_voidshot', 0, 0), ('title_regicide', 1, 3000);

    FOR r IN
        SELECT si.sku, p.steam_id, pi.purchase_price,
               COALESCE(p.active_title_id = si.id, FALSE) AS worn,
               (SELECT COALESCE(SUM(-g.amount), 0) FROM gold_transactions g
                 WHERE g.player_id = p.id AND g.reason = 'purchase' AND g.reference_id = si.sku) AS debited
          FROM player_items pi
          JOIN shop_items si ON si.id = pi.item_id
          JOIN players p ON p.id = pi.player_id
         WHERE si.sku IN (SELECT sku FROM _m366_census)
         ORDER BY si.sku, p.steam_id
    LOOP
        RAISE NOTICE '366 holder: sku % steam_id % paid % debited % worn %',
            r.sku, r.steam_id, r.purchase_price, r.debited, r.worn;
        IF r.purchase_price <> r.debited THEN
            RAISE EXCEPTION '366 refused: % holder % has purchase_price % but their purchase rows debited %; refund amount is not certain',
                r.sku, r.steam_id, r.purchase_price, r.debited;
        END IF;
    END LOOP;

    FOR c IN SELECT * FROM _m366_census ORDER BY sku LOOP
        SELECT count(*), COALESCE(SUM(pi.purchase_price), 0) INTO n_now, paid_now
          FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
         WHERE si.sku = c.sku AND pi.purchase_price > 0;
        SELECT count(*), COALESCE(SUM(g.amount), 0) INTO n_done, paid_done
          FROM gold_transactions g
         WHERE g.reason = 'title_refunded' AND g.reference_id = c.sku;
        RAISE NOTICE '366 preflight %: paid holders now %, refunded already %, census % (gold now %, refunded %, census %)',
            c.sku, n_now, n_done, c.holders, paid_now, paid_done, c.paid;
        IF n_now + n_done <> c.holders OR paid_now + paid_done <> c.paid THEN
            RAISE EXCEPTION '366 refused: % has % paid holders now and % refunds written (gold % + %), the census says % holders and % gold. Re-census before refunding',
                c.sku, n_now, n_done, paid_now, paid_done, c.holders, c.paid;
        END IF;
    END LOOP;

    -- The refunds.
    FOR r IN
        SELECT pi.player_id, pi.item_id, pi.purchase_price, si.sku
          FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
         WHERE si.sku IN (SELECT sku FROM _m366_census)
         ORDER BY pi.player_id, si.sku
           FOR UPDATE OF pi
    LOOP
        IF r.purchase_price > 0 THEN
            UPDATE players SET gold_spent = gold_spent - r.purchase_price
             WHERE id = r.player_id AND gold_spent >= r.purchase_price;
            GET DIAGNOSTICS moved = ROW_COUNT;
            IF moved <> 1 THEN
                RAISE EXCEPTION '366 refused: player % gold_spent cannot return % for % exactly', r.player_id, r.purchase_price, r.sku;
            END IF;
            INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
            VALUES (r.player_id, r.purchase_price, 'title_refunded', r.sku);
        END IF;
        UPDATE players SET active_title_id = NULL
         WHERE id = r.player_id AND active_title_id = r.item_id;
        DELETE FROM player_items WHERE player_id = r.player_id AND item_id = r.item_id;
        RAISE NOTICE '366 refunded % gold for % and removed the item', r.purchase_price, r.sku;
    END LOOP;

    -- Anyone still wearing one (an account the shop-owner exemption covered).
    UPDATE players SET active_title_id = NULL
     WHERE active_title_id IN (SELECT id FROM shop_items WHERE sku IN (SELECT sku FROM _m366_census));
    GET DIAGNOSTICS n_unworn = ROW_COUNT;

    -- Retire both catalogue rows.
    UPDATE shop_items SET catalog_ready = FALSE
     WHERE sku IN (SELECT sku FROM _m366_census) AND catalog_ready IS TRUE;
    GET DIAGNOSTICS n_retired = ROW_COUNT;
    RAISE NOTICE '366: % unequipped without ownership, % catalogue rows retired now', n_unworn, n_retired;
END $m366$;

-- Post-checks, on every application.
DO $m366post$
DECLARE
    bad INTEGER;
BEGIN
    SELECT count(*) INTO bad FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
     WHERE si.sku IN ('title_voidshot', 'title_regicide');
    IF bad <> 0 THEN
        RAISE EXCEPTION '366: % inventory rows of a retired title remain', bad;
    END IF;
    SELECT count(*) INTO bad FROM players p JOIN shop_items si ON si.id = p.active_title_id
     WHERE si.sku IN ('title_voidshot', 'title_regicide');
    IF bad <> 0 THEN
        RAISE EXCEPTION '366: % players still wear a retired title', bad;
    END IF;
    SELECT count(*) INTO bad FROM shop_items
     WHERE sku IN ('title_voidshot', 'title_regicide') AND catalog_ready IS TRUE;
    IF bad <> 0 THEN
        RAISE EXCEPTION '366: % retired titles are still on sale', bad;
    END IF;
    SELECT count(*) INTO bad FROM gold_transactions
     WHERE reason = 'title_refunded' AND reference_id IN ('title_voidshot', 'title_regicide');
    IF bad <> 1 THEN
        RAISE EXCEPTION '366: expected the census''s 1 refund row, found %', bad;
    END IF;
    RAISE NOTICE '366: final state holds -- no holder, no wearer, both retired, 1 refund row';
END $m366post$;

COMMIT;
