-- 366_title_refunds_voidshot_kingslayer.sql
--
-- Removes two titles from the game and refunds every buyer (board row 29, the
-- ruling of 2026-09-28 10:00Z): Voidshot (title_voidshot, 069:47, 2500 gold;
-- its card "Empty Power" does not exist) and Kingslayer (title_regicide,
-- 021:55, 3000 gold; confusing beside Sid Slayer).
--
-- CENSUS (production primary, sql-readonly, counts only; first 2026-10-01
-- 05:17Z, re-taken for every holder at any price 2026-10-01 10:18Z, and with
-- the purchase evidence 2026-10-01 22:10Z):
--   title_voidshot  0 holders (0 paid, 0 at price 0), 0 gold paid; 0
--                   'purchase' rows, 0 buyers, 0 gold debited.
--   title_regicide  1 holder (1 paid, 0 at price 0), 3000 gold paid (the
--                   list price); 1 'purchase' row, 1 buyer, 3000 gold
--                   debited.
--   wearers of either 0; gold_transactions reason 'title_refunded' 0.
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
-- PREFLIGHT, which refuses rather than guesses, BEFORE ANY WRITE: it prints
-- every holder and requires each holder's purchase_price to equal what their
-- own 'purchase' rows debited. Then, for each sku, the database must be in
-- exactly one of two states, and BOTH carry the census's purchase evidence:
-- the 'purchase' rows naming the sku, the distinct buyers on them and the
-- gold they debited must equal the census's in either state (366 never
-- writes or removes a purchase row).
--   NOT YET APPLIED: every holder now (at ANY price, a zero-price or granted
--     holder included) equals the census's holders, the paying holders and
--     the gold they paid equal the census's, and no refund row exists;
--   APPLIED: no holder remains (all of the census's holders are gone), the
--     refund rows, the distinct players on them and their gold equal the
--     census's paying holders and gold, and every refunded player is one of
--     the sku's buyers.
-- Anything else refuses with nothing changed (re-census, then edit the census
-- numbers below): a holder gained or lost since the census at any price, a
-- purchase row gained or lost, a database the census does not describe. That
-- includes a schema these titles were never sold on while the census expects
-- a holder or a purchase: there is no third state. A migration-replay harness
-- that builds such a schema holds this file out (it is the production census's
-- refund, not schema). A second run is the APPLIED state and writes nothing.
--
-- No dependency on the api build: it can apply before or after it. Explicit
-- BEGIN/COMMIT (#340).

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m366$
DECLARE
    r          RECORD;
    c          RECORD;
    n_all      INTEGER;
    n_now      INTEGER;
    n_done     INTEGER;
    paid_now   BIGINT;
    paid_done  BIGINT;
    moved      INTEGER;
    n_unworn   INTEGER;
    n_retired  INTEGER;
    n_purch    INTEGER;
    n_buyers   INTEGER;
    debit_now  BIGINT;
    n_refunded INTEGER;
    n_stray    INTEGER;
    v_fresh    BOOLEAN;
    v_applied  BOOLEAN;
BEGIN
    -- The census, per sku: every holder at any price, the holders who paid,
    -- the gold they paid, and the purchase evidence: 'purchase' rows naming
    -- the sku, the distinct buyers on them, and the gold they debited.
    CREATE TEMP TABLE _m366_census (sku VARCHAR(64) PRIMARY KEY, holders INTEGER,
                                    paid_holders INTEGER, paid BIGINT,
                                    purchase_rows INTEGER, buyers INTEGER,
                                    debit BIGINT) ON COMMIT DROP;
    INSERT INTO _m366_census VALUES ('title_voidshot', 0, 0, 0, 0, 0, 0),
                                    ('title_regicide', 1, 1, 3000, 1, 1, 3000);

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
        SELECT count(*) INTO n_all
          FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
         WHERE si.sku = c.sku;
        SELECT count(*), COALESCE(SUM(pi.purchase_price), 0) INTO n_now, paid_now
          FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
         WHERE si.sku = c.sku AND pi.purchase_price > 0;
        SELECT count(*), COALESCE(SUM(g.amount), 0) INTO n_done, paid_done
          FROM gold_transactions g
         WHERE g.reason = 'title_refunded' AND g.reference_id = c.sku;
        SELECT count(*), count(DISTINCT g.player_id), COALESCE(SUM(-g.amount), 0)
          INTO n_purch, n_buyers, debit_now
          FROM gold_transactions g
         WHERE g.reason = 'purchase' AND g.reference_id = c.sku;
        SELECT count(DISTINCT g.player_id),
               count(DISTINCT g.player_id) FILTER (WHERE NOT EXISTS (
                   SELECT 1 FROM gold_transactions b
                    WHERE b.player_id = g.player_id AND b.reason = 'purchase'
                      AND b.reference_id = c.sku))
          INTO n_refunded, n_stray
          FROM gold_transactions g
         WHERE g.reason = 'title_refunded' AND g.reference_id = c.sku;
        RAISE NOTICE '366 preflight %: holders now % (census %), paying holders now % (census %), gold now % (census %), refunds written % for % gold to % players (% not buyers), purchase rows % (census %), buyers % (census %), debited % (census %)',
            c.sku, n_all, c.holders, n_now, c.paid_holders, paid_now, c.paid, n_done, paid_done,
            n_refunded, n_stray, n_purch, c.purchase_rows, n_buyers, c.buyers, debit_now, c.debit;
        v_fresh := n_all = c.holders AND n_now = c.paid_holders AND paid_now = c.paid
                   AND n_purch = c.purchase_rows AND n_buyers = c.buyers AND debit_now = c.debit
                   AND n_done = 0 AND paid_done = 0;
        v_applied := n_all = 0
                   AND n_purch = c.purchase_rows AND n_buyers = c.buyers AND debit_now = c.debit
                   AND n_done = c.paid_holders AND paid_done = c.paid
                   AND n_refunded = c.paid_holders AND n_stray = 0;
        IF NOT (v_fresh OR v_applied) THEN
            RAISE EXCEPTION '366 refused: % has % holders now (% paying, % gold), % purchase rows from % buyers debiting %, and % refunds written (% gold); the census says % holders (% paying, % gold), % purchase rows from % buyers debiting %. Re-census before refunding',
                c.sku, n_all, n_now, paid_now, n_purch, n_buyers, debit_now, n_done, paid_done,
                c.holders, c.paid_holders, c.paid, c.purchase_rows, c.buyers, c.debit;
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
    bad       INTEGER;
    want      INTEGER;
    gold      BIGINT;
    want_gold BIGINT;
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
    -- Exactly the refunds the EMBEDDED census expects: one row per census
    -- paying holder, for the census's gold. The expectation is the census
    -- table this transaction created above, never a count of rows the
    -- database could have lost.
    SELECT COALESCE(SUM(paid_holders), 0), COALESCE(SUM(paid), 0) INTO want, want_gold
      FROM _m366_census;
    SELECT count(*), COALESCE(SUM(amount), 0) INTO bad, gold FROM gold_transactions
     WHERE reason = 'title_refunded' AND reference_id IN ('title_voidshot', 'title_regicide');
    IF bad <> want OR gold <> want_gold THEN
        RAISE EXCEPTION '366: expected % refund row(s) for % gold (the census''s paying holders), found % for %',
            want, want_gold, bad, gold;
    END IF;
    RAISE NOTICE '366: final state holds -- no holder, no wearer, both retired, % refund row(s) for % gold', bad, gold;
END $m366post$;

COMMIT;
