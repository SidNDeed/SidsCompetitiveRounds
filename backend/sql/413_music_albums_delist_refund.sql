-- 413_music_albums_delist_refund.sql
-- The two music albums are withdrawn after community feedback; every purchase
-- is refunded in full.
--
-- In one transaction this file:
--   1. delists both shop rows (catalog_ready FALSE, named by sku), then takes
--      every players row the run changes, NOWAIT (below);
--   2. creates music_album_refund_archive (one row per removed ownership row);
--   3. refuses, changing nothing, on a state it was not written for (below);
--   4. in ONE data-modifying statement: deletes every player_items row of the
--      two skus, paid or free, archives exactly the deleted rows, returns to
--      each buyer the sum of the prices that buyer paid as one delta on
--      gold_spent, takes back from each artist account the royalty those rows
--      paid it as one delta on gold_earned, and writes the ledger rows
--      (reason 'music_album_refund', +price per paid row; reason
--      'music_royalty_reversal', -royalty per artist account and sku;
--      reference_id = the sku);
--   5. checks its own result and raises unless it holds.
-- The shop rows themselves stay; a later step removes them.
--
-- THE DELIST IS THE FIRST DATA STATEMENT, and it locks both shop rows FOR
-- UPDATE. The purchase path reads the shop row FOR SHARE and checks
-- catalog_ready again under that lock (main.purchase_item), so this statement
-- waits for a purchase in flight to commit, and a purchase that starts later
-- waits for this transaction and then reads catalog_ready FALSE: it is
-- refused with 409 before any debit. FOR UPDATE (not the NO KEY UPDATE the
-- UPDATE alone takes) also conflicts with the KEY SHARE every player_items
-- insert takes on its shop row, so any other writer of an ownership row of
-- these items that is in flight finishes before this file reads ownership
-- rows, and one that starts later waits until this file commits. Each
-- statement below reads a fresh snapshot (READ COMMITTED), so it sees every
-- row the delist waited for.
--
-- THE PLAYERS ROWS ARE LOCKED NEXT, ALL AT ONCE, AND NEVER WAITED FOR. Right
-- after the delist one statement takes every players row this run changes
-- (every owner of an ownership row of the two skus, and every artist account
-- a royalty row paid) FOR NO KEY UPDATE NOWAIT, in players.id order. A row
-- another transaction holds makes the file fail at once with its own message,
-- nothing changed, and the operator applies it again; a player's request is
-- never the transaction PostgreSQL aborts. Waiting instead could close a
-- cycle: a purchase that has debited one of these buyers and is about to
-- credit the royalty to an artist this file already holds. FOR NO KEY UPDATE
-- is the weakest mode that still conflicts with this file's own later UPDATE
-- of those rows (which takes the same mode) and with every other writer's
-- UPDATE of them; it does not conflict with the KEY SHARE that a foreign-key
-- insert referencing a players row takes, so ledger and other inserts for
-- these players elsewhere keep running (lessons 202, 203). The set is derived
-- from ownership rows the delist's FOR UPDATE has frozen: no ownership row of
-- these items can be inserted while it is held, so no later statement can
-- find an owner the lock statement did not see (lesson 207). The refund step
-- still refuses if it would change a players row outside the locked set.
--
-- REFUSALS (RAISE EXCEPTION; the transaction rolls back, nothing changes):
--   - the number of shop rows of kind music_album is not 2, or a named sku is
--     absent or of another kind;
--   - an ownership row of these skus has a NULL or negative purchase_price;
--   - a paid ownership row has no ledger row 'purchase' of the same player
--     and sku with amount = -purchase_price;
--   - a player's gold_spent is smaller than that player's refund;
--   - an ownership row paid a royalty to a steam id with no live account;
--   - per artist account and sku, the royalty to take back differs from the
--     net of that account's 'artist_royalty' and 'music_royalty_reversal'
--     ledger rows of that sku;
--   - an artist account's balance (gold_earned - gold_spent) would fall
--     below 0 after this run.
--
-- RE-RUNS. A second application never moves gold again and never touches
-- what an earlier run archived: both rows are already delisted (no row
-- updated), the earlier run's ownership rows are gone, and the royalty
-- ledger's net per account and sku is 0. An ownership row that appeared
-- after an earlier run IS removed and archived by a re-run. Only a free one
-- can appear (the artist gift path checks catalog_ready without a lock, so a
-- gift that read TRUE before the run can commit its row after it); it is
-- archived with gold_refunded 0 and no ledger row. A paid one cannot appear:
-- the purchase path re-checks catalog_ready under its lock.
--
-- HOW TO APPLY. Apply only after the api that classes the two new ledger
-- reasons (the gold-source pie, the sales board, the artist's item list) is
-- live on both boxes; before that, the old readers count each refund as
-- income. The only supported way to apply it is the migrate verb, which runs
-- psql -v ON_ERROR_STOP=1 with this file on stdin: a refusal ends psql with
-- exit 3, and the transaction is rolled back.
--
-- THE ARCHIVE holds no steam id and no name: a buyer is players.id, and the
-- artist the royalty went to is the artist's players.id, resolved from the
-- row's royalty_artist_steam_id at this run (NULL when the row paid no
-- royalty and the steam id names no account). Account deletion
-- (delete_player_data) anonymises the players row in place and keeps the rows
-- keyed by players.id, as it keeps gold_transactions; after it, an archive
-- row resolves only to the anonymised row. A deliberate restoration is a new
-- forward migration that reads, per archive row: player_id (skipping rows
-- whose players.deleted_at is set), item_id or sku, purchased_at,
-- purchase_price, and the royalty columns; refund_ledger_id names the refund's
-- ledger row. player_id carries no foreign key on purpose: creating one takes
-- a SHARE ROW EXCLUSIVE lock on players, which would wait for every
-- transaction writing a players row and hold every later one until this file
-- commits; an ON DELETE action would be inert anyway, because the deletion
-- path anonymises the row and never deletes it (#437).
--
-- NO ROLLBACK FILE, by design: this change returns gold, and a reversal would
-- debit players who may have spent it; a restoration is a new forward
-- migration that reads the archive.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

-- 413-delist
WITH locked AS (
    SELECT id FROM shop_items
     WHERE sku IN ('music_album_another_round', 'music_album_clavar_la_bala')
     FOR UPDATE
)
UPDATE shop_items si
   SET catalog_ready = FALSE
  FROM locked
 WHERE si.id = locked.id
   AND si.catalog_ready IS DISTINCT FROM FALSE;

-- 413-players-lock
DO $lock$
DECLARE
    v_skus CONSTANT TEXT[] := ARRAY['music_album_another_round', 'music_album_clavar_la_bala'];
    v_ids  TEXT;
BEGIN
    WITH changed AS (
        SELECT pi.player_id AS pid
          FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
         WHERE si.sku = ANY (v_skus)
        UNION
        SELECT a.id
          FROM player_items pi
          JOIN shop_items si ON si.id = pi.item_id
          JOIN players a ON a.steam_id = pi.royalty_artist_steam_id
         WHERE si.sku = ANY (v_skus) AND COALESCE(pi.royalty_paid, 0) <> 0
    ), locked AS (
        SELECT p.id FROM players p
         WHERE p.id IN (SELECT pid FROM changed)
         ORDER BY p.id
           FOR NO KEY UPDATE NOWAIT
    )
    SELECT COALESCE(string_agg(id::text, ',' ORDER BY id), '') INTO v_ids FROM locked;
    PERFORM set_config('scr413.locked_players', v_ids, true);
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION '413 refused: a players row this run changes is held by another transaction; nothing was changed, apply the file again';
END $lock$;
-- 413-players-lock-end

CREATE TABLE IF NOT EXISTS music_album_refund_archive (
    id                       BIGSERIAL PRIMARY KEY,
    run_at                   TIMESTAMPTZ NOT NULL,
    player_id                UUID NOT NULL,
    item_id                  BIGINT NOT NULL,
    sku                      VARCHAR(64) NOT NULL,
    purchased_at             TIMESTAMPTZ NOT NULL,
    purchase_price           INTEGER NOT NULL,
    royalty_paid             INTEGER,
    royalty_rate_pct         SMALLINT,
    royalty_artist_player_id UUID,
    royalty_resolved         BOOLEAN NOT NULL,
    gold_refunded            INTEGER NOT NULL,
    royalty_taken_back       INTEGER NOT NULL,
    refund_ledger_id         BIGINT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_music_album_refund_archive_player
    ON music_album_refund_archive (player_id);

DO $pre$
DECLARE
    v_skus CONSTANT TEXT[] := ARRAY['music_album_another_round', 'music_album_clavar_la_bala'];
    v_sku  TEXT;
    n      BIGINT;
BEGIN
    SELECT count(*) INTO n FROM shop_items WHERE kind = 'music_album';
    IF n <> 2 THEN
        RAISE EXCEPTION '413 refused: % shop rows of kind music_album, expected 2; nothing was changed', n;
    END IF;
    FOREACH v_sku IN ARRAY v_skus LOOP
        IF NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = v_sku AND kind = 'music_album') THEN
            RAISE EXCEPTION '413 refused: shop row % is absent or not a music_album; nothing was changed', v_sku;
        END IF;
    END LOOP;

    SELECT count(*) INTO n
      FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
     WHERE si.sku = ANY (v_skus)
       AND (pi.purchase_price IS NULL OR pi.purchase_price < 0);
    IF n > 0 THEN
        RAISE EXCEPTION '413 refused: % ownership row(s) have a NULL or negative purchase_price; nothing was changed', n;
    END IF;

    SELECT count(*) INTO n
      FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
     WHERE si.sku = ANY (v_skus)
       AND pi.purchase_price > 0
       AND NOT EXISTS (SELECT 1 FROM gold_transactions gt
                        WHERE gt.player_id = pi.player_id
                          AND gt.reason = 'purchase'
                          AND gt.reference_id = si.sku
                          AND gt.amount = -pi.purchase_price);
    IF n > 0 THEN
        RAISE EXCEPTION '413 refused: % paid ownership row(s) have no purchase ledger row of the same player, sku and amount; nothing was changed', n;
    END IF;

    SELECT count(*) INTO n
      FROM (SELECT pi.player_id, SUM(pi.purchase_price) AS refund
              FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
             WHERE si.sku = ANY (v_skus)
             GROUP BY pi.player_id) r
      JOIN players p ON p.id = r.player_id
     WHERE COALESCE(p.gold_spent, 0) < r.refund;
    IF n > 0 THEN
        RAISE EXCEPTION '413 refused: % player(s) have gold_spent below their refund; nothing was changed', n;
    END IF;

    SELECT count(*) INTO n
      FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
     WHERE si.sku = ANY (v_skus)
       AND COALESCE(pi.royalty_paid, 0) <> 0
       AND NOT EXISTS (SELECT 1 FROM players a
                        WHERE a.steam_id = pi.royalty_artist_steam_id
                          AND a.deleted_at IS NULL);
    IF n > 0 THEN
        RAISE EXCEPTION '413 refused: % ownership row(s) paid a royalty to a steam id with no live account; nothing was changed', n;
    END IF;

    SELECT count(*) INTO n
      FROM (SELECT a.id AS pid, si.sku, SUM(pi.royalty_paid) AS takeback
              FROM player_items pi
              JOIN shop_items si ON si.id = pi.item_id
              JOIN players a ON a.steam_id = pi.royalty_artist_steam_id
             WHERE si.sku = ANY (v_skus) AND COALESCE(pi.royalty_paid, 0) <> 0
             GROUP BY a.id, si.sku) r
      FULL JOIN (SELECT gt.player_id AS pid, gt.reference_id AS sku, SUM(gt.amount) AS net
                   FROM gold_transactions gt
                  WHERE gt.reason IN ('artist_royalty', 'music_royalty_reversal')
                    AND gt.reference_id = ANY (v_skus)
                  GROUP BY gt.player_id, gt.reference_id) l
        ON l.pid = r.pid AND l.sku = r.sku
     WHERE COALESCE(r.takeback, 0) <> COALESCE(l.net, 0);
    IF n > 0 THEN
        RAISE EXCEPTION '413 refused: for % artist account and sku pair(s) the royalty to take back differs from the artist_royalty ledger; nothing was changed', n;
    END IF;

    SELECT count(*) INTO n
      FROM (SELECT a.id AS pid, SUM(pi.royalty_paid) AS takeback
              FROM player_items pi
              JOIN shop_items si ON si.id = pi.item_id
              JOIN players a ON a.steam_id = pi.royalty_artist_steam_id
             WHERE si.sku = ANY (v_skus) AND COALESCE(pi.royalty_paid, 0) <> 0
             GROUP BY a.id) t
      JOIN players p ON p.id = t.pid
      LEFT JOIN (SELECT pi.player_id, SUM(pi.purchase_price) AS refund
                   FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
                  WHERE si.sku = ANY (v_skus)
                  GROUP BY pi.player_id) r ON r.player_id = t.pid
     WHERE COALESCE(p.gold_earned, 0) - t.takeback < 0
        OR (COALESCE(p.gold_earned, 0) - t.takeback)
           - (COALESCE(p.gold_spent, 0) - COALESCE(r.refund, 0)) < 0;
    IF n > 0 THEN
        RAISE EXCEPTION '413 refused: % artist account(s) would fall below a zero balance; nothing was changed', n;
    END IF;
END $pre$;

DO $refund$
DECLARE
    v_skus CONSTANT TEXT[] := ARRAY['music_album_another_round', 'music_album_clavar_la_bala'];
    n_deleted   BIGINT;
    n_archived  BIGINT;
    n_moved     BIGINT;
    n_movers    BIGINT;
    n_refunds   BIGINT;
    n_paid_rows BIGINT;
    n_reversals BIGINT;
    n_takers    BIGINT;
    g_refunded  BIGINT;
    g_archived  BIGINT;
    g_taken     BIGINT;
    g_royalty   BIGINT;
    n_round     BIGINT;
    n_clavar    BIGINT;
    n_players   BIGINT;
    n_unlocked  BIGINT;
BEGIN
    -- 413-lock-membership
    SELECT count(*) INTO n_unlocked
      FROM (SELECT pi.player_id AS pid
              FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
             WHERE si.sku = ANY (v_skus) AND pi.purchase_price <> 0
            UNION
            SELECT a.id
              FROM player_items pi
              JOIN shop_items si ON si.id = pi.item_id
              JOIN players a ON a.steam_id = pi.royalty_artist_steam_id
             WHERE si.sku = ANY (v_skus) AND COALESCE(pi.royalty_paid, 0) <> 0) c
     WHERE NOT COALESCE(c.pid::text = ANY (string_to_array(
               current_setting('scr413.locked_players', true), ',')), FALSE);
    IF n_unlocked > 0 THEN
        RAISE EXCEPTION '413 refused: % players row(s) this run would change were not taken by its lock statement; nothing was changed', n_unlocked;
    END IF;
    -- 413-lock-membership-end

    WITH del AS (
        DELETE FROM player_items pi
         USING shop_items si
         WHERE si.id = pi.item_id
           AND si.sku = ANY (v_skus)
        RETURNING pi.player_id, pi.item_id, si.sku, pi.purchased_at, pi.purchase_price,
                  pi.royalty_paid, pi.royalty_rate_pct, pi.royalty_artist_steam_id,
                  pi.royalty_resolved
    ), rws AS (
        SELECT d.*, COALESCE(d.royalty_paid, 0) AS takeback,
               (SELECT a.id FROM players a
                 WHERE a.steam_id = d.royalty_artist_steam_id) AS artist_id
          FROM del d
    ), buyer AS (
        SELECT player_id AS pid, SUM(purchase_price) AS refund
          FROM rws GROUP BY player_id
    ), artist AS (
        SELECT artist_id AS pid, SUM(takeback) AS takeback
          FROM rws WHERE takeback <> 0 GROUP BY artist_id
    ), delta AS (
        SELECT COALESCE(b.pid, a.pid) AS pid,
               COALESCE(b.refund, 0) AS refund,
               COALESCE(a.takeback, 0) AS takeback
          FROM buyer b FULL JOIN artist a ON a.pid = b.pid
    ), moved AS (
        UPDATE players p
           SET gold_spent  = COALESCE(p.gold_spent, 0) - d.refund,
               gold_earned = COALESCE(p.gold_earned, 0) - d.takeback
          FROM delta d
         WHERE p.id = d.pid
           AND (d.refund <> 0 OR d.takeback <> 0)
           AND COALESCE(p.gold_spent, 0) >= d.refund
           AND COALESCE(p.gold_earned, 0) - d.takeback >= 0
           AND (COALESCE(p.gold_earned, 0) - d.takeback)
               - (COALESCE(p.gold_spent, 0) - d.refund) >= 0
        RETURNING p.id
    ), refund_ledger AS (
        INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
        SELECT player_id, purchase_price, 'music_album_refund', sku, now()
          FROM rws WHERE purchase_price > 0
        RETURNING id, player_id, reference_id, amount
    ), royalty_ledger AS (
        INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
        SELECT artist_id, -SUM(takeback), 'music_royalty_reversal', sku, now()
          FROM rws WHERE takeback <> 0
         GROUP BY artist_id, sku
        RETURNING id, amount
    ), archived AS (
        INSERT INTO music_album_refund_archive
               (run_at, player_id, item_id, sku, purchased_at, purchase_price,
                royalty_paid, royalty_rate_pct, royalty_artist_player_id, royalty_resolved,
                gold_refunded, royalty_taken_back, refund_ledger_id)
        SELECT now(), r.player_id, r.item_id, r.sku, r.purchased_at, r.purchase_price,
               r.royalty_paid, r.royalty_rate_pct, r.artist_id, r.royalty_resolved,
               r.purchase_price, r.takeback, l.id
          FROM rws r
          LEFT JOIN refund_ledger l ON l.player_id = r.player_id AND l.reference_id = r.sku
        RETURNING sku, purchase_price, gold_refunded, royalty_taken_back, refund_ledger_id
    )
    SELECT (SELECT count(*) FROM del),
           (SELECT count(*) FROM archived),
           (SELECT count(*) FROM moved),
           (SELECT count(*) FROM delta WHERE refund <> 0 OR takeback <> 0),
           (SELECT count(*) FROM refund_ledger),
           (SELECT count(*) FROM rws WHERE purchase_price > 0),
           (SELECT count(*) FROM royalty_ledger),
           (SELECT count(*) FROM (SELECT DISTINCT artist_id, sku FROM rws WHERE takeback <> 0) x),
           (SELECT COALESCE(SUM(amount), 0) FROM refund_ledger),
           (SELECT COALESCE(SUM(gold_refunded), 0) FROM archived),
           (SELECT COALESCE(-SUM(amount), 0) FROM royalty_ledger),
           (SELECT COALESCE(SUM(royalty_taken_back), 0) FROM archived),
           (SELECT count(*) FROM archived WHERE sku = 'music_album_another_round'),
           (SELECT count(*) FROM archived WHERE sku = 'music_album_clavar_la_bala'),
           (SELECT count(*) FROM buyer WHERE refund > 0)
      INTO n_deleted, n_archived, n_moved, n_movers, n_refunds, n_paid_rows, n_reversals,
           n_takers, g_refunded, g_archived, g_taken, g_royalty, n_round, n_clavar, n_players;

    IF n_archived <> n_deleted THEN
        RAISE EXCEPTION '413 failed: % ownership row(s) deleted but % archived', n_deleted, n_archived;
    END IF;
    IF n_moved <> n_movers THEN
        RAISE EXCEPTION '413 failed: % player balance(s) moved, expected %: a balance no longer covers its delta', n_moved, n_movers;
    END IF;
    IF n_refunds <> n_paid_rows OR g_refunded <> g_archived THEN
        RAISE EXCEPTION '413 failed: % refund ledger row(s) for % gold, expected % for %', n_refunds, g_refunded, n_paid_rows, g_archived;
    END IF;
    IF n_reversals <> n_takers OR g_taken <> g_royalty THEN
        RAISE EXCEPTION '413 failed: % royalty reversal row(s) for % gold, expected % for %', n_reversals, g_taken, n_takers, g_royalty;
    END IF;
    RAISE NOTICE '413: archived % row(s) of music_album_another_round and % of music_album_clavar_la_bala; refunded % gold to % player(s); took back % royalty gold in % ledger row(s)',
        n_round, n_clavar, g_refunded, n_players, g_taken, n_reversals;
END $refund$;

DO $post$
DECLARE
    v_skus CONSTANT TEXT[] := ARRAY['music_album_another_round', 'music_album_clavar_la_bala'];
    n       BIGINT;
    g_led   BIGINT;
    g_arch  BIGINT;
    n_led   BIGINT;
    n_arch  BIGINT;
BEGIN
    SELECT count(*) INTO n
      FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
     WHERE si.sku = ANY (v_skus);
    IF n <> 0 THEN
        RAISE EXCEPTION '413 post-check FAILED: % ownership row(s) of the two albums remain', n;
    END IF;

    SELECT count(*), COALESCE(SUM(amount), 0) INTO n_led, g_led
      FROM gold_transactions
     WHERE reason = 'music_album_refund' AND created_at = now()
       AND reference_id = ANY (v_skus);
    SELECT count(*) FILTER (WHERE purchase_price > 0), COALESCE(SUM(purchase_price), 0)
      INTO n_arch, g_arch
      FROM music_album_refund_archive
     WHERE run_at = now();
    IF n_led <> n_arch OR g_led <> g_arch THEN
        RAISE EXCEPTION '413 post-check FAILED: this run''s refund ledger rows (% for % gold) do not match its archived prices (% for % gold)', n_led, g_led, n_arch, g_arch;
    END IF;

    SELECT count(*) INTO n
      FROM shop_items
     WHERE sku = ANY (v_skus) AND catalog_ready IS FALSE;
    IF n <> 2 THEN
        RAISE EXCEPTION '413 post-check FAILED: % of the 2 album rows are catalog_ready FALSE', n;
    END IF;
    RAISE NOTICE '413: post-check OK: no ownership row left, % refund row(s) for % gold match the archive, both albums delisted',
        n_led, g_led;
END $post$;

COMMIT;
