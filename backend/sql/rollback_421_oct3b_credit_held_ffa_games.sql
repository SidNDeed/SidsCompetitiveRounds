-- Rollback of 421 (OCT3-B): takes back the gold and XP credited for games 2
-- and 3 of FFA lobby a18d56f5-382f-4fd0-8312-d873412a5ace and returns both
-- held reports to pending.
--
-- It runs only when the receipts check is exact: the same check, word for
-- word, as 421's second-run acceptance (between the oct3b:receipts markers;
-- a test requires the two texts equal). The reversal amounts are taken from
-- the 12 audit rows' details (XP from xp; gold from gold_ffa_xp +
-- gold_ffa_placement + gold_level_reward), as deltas: each player's total_xp
-- and ffa_xp_earned lose that XP, gold_earned and ffa_gold_earned that gold.
-- Then the ledger rows naming the two held rows and 421's audit rows (action
-- quarantine_credit, actor system:migration_421, details qid) are deleted and
-- both rows read pending with reviewed_at, reviewed_by and review_note NULL,
-- as 421 found them.
--
-- It refuses, with nothing applied, when any player's spendable gold after
-- the reversal would be below zero: COALESCE(gold_earned, 0) -
-- COALESCE(gold_spent, 0), the balance the shop's debit guards.
--
-- STATES: neither held row present: NOTICE, nothing written. Both credited
-- and the receipts check exact: the rollback. Anything else: RAISE, nothing
-- applied.
--
-- LOCKS: every row lock it waits for is taken NOWAIT (held rows, then the
-- players in str(player_id) order, then the ledger and audit rows it will
-- delete); a row held elsewhere fails the run at once (SQLSTATE 55P03) with
-- nothing applied. After them it waits for no row lock: its UPDATEs and
-- DELETEs touch only rows it holds.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL statement_timeout = '30s';
SELECT pg_catalog.set_config('search_path',
         'pg_catalog, ' || pg_catalog.quote_ident(pg_catalog.current_schema()) || ', pg_temp', true);

DO $r421$
DECLARE
  qids CONSTANT pg_catalog.uuid[] := ARRAY['cb241216-41f9-49cc-aab5-3f0984c2c051',
                                           '1e419790-b377-402a-8455-20f4e39ebdc8']::pg_catalog.uuid[];
  -- 421's amounts literal, word for word (a test requires the two equal).
  amounts CONSTANT pg_catalog.jsonb := '[
    {"q": "cb241216-41f9-49cc-aab5-3f0984c2c051", "slot": 0, "xp": 2330, "place_gold": 28},
    {"q": "cb241216-41f9-49cc-aab5-3f0984c2c051", "slot": 1, "xp": 1614, "place_gold": 20},
    {"q": "cb241216-41f9-49cc-aab5-3f0984c2c051", "slot": 2, "xp": 3046, "place_gold": 37},
    {"q": "cb241216-41f9-49cc-aab5-3f0984c2c051", "slot": 3, "xp": 2986, "place_gold": 36},
    {"q": "cb241216-41f9-49cc-aab5-3f0984c2c051", "slot": 4, "xp": 3763, "place_gold": 46},
    {"q": "cb241216-41f9-49cc-aab5-3f0984c2c051", "slot": 5, "xp": 898, "place_gold": 11},
    {"q": "1e419790-b377-402a-8455-20f4e39ebdc8", "slot": 0, "xp": 3323, "place_gold": 41},
    {"q": "1e419790-b377-402a-8455-20f4e39ebdc8", "slot": 1, "xp": 1761, "place_gold": 22},
    {"q": "1e419790-b377-402a-8455-20f4e39ebdc8", "slot": 2, "xp": 4105, "place_gold": 50},
    {"q": "1e419790-b377-402a-8455-20f4e39ebdc8", "slot": 3, "xp": 3257, "place_gold": 40},
    {"q": "1e419790-b377-402a-8455-20f4e39ebdc8", "slot": 4, "xp": 2542, "place_gold": 31},
    {"q": "1e419790-b377-402a-8455-20f4e39ebdc8", "slot": 5, "xp": 980, "place_gold": 12}
  ]';
  actor CONSTANT pg_catalog.text := 'system:migration_421';
  note CONSTANT pg_catalog.text := 'Migration 421, option B: gold and XP credited, ratings not applied.';
  n_rows pg_catalog.int8;
  n pg_catalog.int8;
  exact pg_catalog.bool;
  pid pg_catalog.uuid;
  r record;
BEGIN
  PERFORM 1 FROM match_report_quarantine q
    WHERE q.id = ANY (qids) ORDER BY q.id FOR NO KEY UPDATE NOWAIT;
  SELECT pg_catalog.count(*) INTO n_rows FROM match_report_quarantine q WHERE q.id = ANY (qids);
  IF n_rows = 0 THEN
    RAISE NOTICE 'rollback 421: neither held report is in this database; nothing written';
    RETURN;
  END IF;

  -- The players the audit rows name, NOWAIT in str(player_id) order; then the
  -- ledger and audit rows this file deletes.
  FOR pid IN
    SELECT pl.id FROM players pl
     WHERE pl.steam_id IN (SELECT aa.target_steam_id FROM admin_actions aa
                            WHERE aa.action = 'quarantine_credit'::pg_catalog.text
                              AND aa.admin_steam_id = actor
                              AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[]))
     ORDER BY pl.id::pg_catalog.text COLLATE "C"
  LOOP
    PERFORM 1 FROM players pl WHERE pl.id = pid FOR NO KEY UPDATE NOWAIT;
  END LOOP;
  PERFORM 1 FROM gold_transactions g
    WHERE g.reference_id = ANY (qids::pg_catalog.text[]) ORDER BY g.id FOR UPDATE NOWAIT;
  PERFORM 1 FROM admin_actions aa
    WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
      AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[])
    ORDER BY aa.id FOR UPDATE NOWAIT;

  SELECT
    -- oct3b:receipts-begin
      -- (1) both held rows read credited with this file's note
      (SELECT pg_catalog.count(*) FROM match_report_quarantine q
        WHERE q.id = ANY (qids) AND q.status = 'credited'::pg_catalog.text AND q.review_note = note) = 2
      -- (2) exactly 12 audit rows of this file, one per (held row, player)
      AND (SELECT pg_catalog.count(*) FROM admin_actions aa
            WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
              AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[])) = 12
      AND (SELECT pg_catalog.count(DISTINCT ((aa.details->>'qid'), aa.target_steam_id)) FROM admin_actions aa
            WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
              AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[])) = 12
      -- (3) each names the player of its (held row, slot) and that slot's XP
      --     and placement-gold literals
      AND (SELECT pg_catalog.count(*)
             FROM pg_catalog.jsonb_array_elements(amounts) AS a
             JOIN match_report_quarantine q ON q.id = (a->>'q')::pg_catalog.uuid
             JOIN LATERAL pg_catalog.jsonb_array_elements(q.payload->'players') AS e
               ON (e->>'slot')::pg_catalog.int4 = (a->>'slot')::pg_catalog.int4
             JOIN admin_actions aa
               ON aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
              AND (aa.details->>'qid') = (a->>'q')
              AND aa.target_steam_id = (e->>'steam_id')
              AND (aa.details->>'slot') = (a->>'slot')
              AND (aa.details->>'xp') = (a->>'xp')
              AND (aa.details->>'gold_ffa_placement') = (a->>'place_gold')) = 12
      -- (4) the ledger rows naming either held row are exactly the receipts
      --     the audit rows state: per (held row, player), one row of each
      --     kind whose figure is above 0, of that amount, and no other row
      AND NOT EXISTS (
        WITH want AS (
          SELECT (aa.details->>'qid') AS ref, pl.id AS pid, k.reason, k.amount
            FROM admin_actions aa
            JOIN players pl ON pl.steam_id = aa.target_steam_id
            CROSS JOIN LATERAL (VALUES
              ('ffa_xp'::pg_catalog.text, (aa.details->>'gold_ffa_xp')::pg_catalog.int8),
              ('ffa_placement'::pg_catalog.text, (aa.details->>'gold_ffa_placement')::pg_catalog.int8),
              ('level_reward'::pg_catalog.text, (aa.details->>'gold_level_reward')::pg_catalog.int8)
            ) AS k(reason, amount)
           WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
             AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[])
             AND k.amount > 0
        ), have AS (
          SELECT g.reference_id::pg_catalog.text AS ref, g.player_id AS pid, g.reason::pg_catalog.text AS reason,
                 g.amount::pg_catalog.int8 AS amount
            FROM gold_transactions g
           WHERE g.reference_id = ANY (qids::pg_catalog.text[])
        )
        (SELECT * FROM want EXCEPT ALL SELECT * FROM have)
        UNION ALL
        (SELECT * FROM have EXCEPT ALL SELECT * FROM want))
    -- oct3b:receipts-end
    INTO exact;
  IF NOT exact THEN
    RAISE EXCEPTION 'rollback 421: the held reports are not credited with exactly 421''s receipts; nothing applied';
  END IF;

  -- No player may be left with less than nothing to spend.
  SELECT pg_catalog.count(*) INTO n
    FROM players pl
    JOIN (SELECT aa.target_steam_id AS sid,
                 pg_catalog.sum((aa.details->>'gold_ffa_xp')::pg_catalog.int8
                                + (aa.details->>'gold_ffa_placement')::pg_catalog.int8
                                + (aa.details->>'gold_level_reward')::pg_catalog.int8) AS gold
            FROM admin_actions aa
           WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
             AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[])
           GROUP BY aa.target_steam_id) AS t ON pl.steam_id = t.sid
   WHERE COALESCE(pl.gold_earned, 0) - t.gold - COALESCE(pl.gold_spent, 0) < 0;
  IF n > 0 THEN
    RAISE EXCEPTION 'rollback 421: % player(s) would be left below zero gold to spend; nothing applied', n;
  END IF;

  FOR r IN
    SELECT pl.id AS pid,
           pg_catalog.sum((aa.details->>'xp')::pg_catalog.int8) AS xp,
           pg_catalog.sum((aa.details->>'gold_ffa_xp')::pg_catalog.int8
                          + (aa.details->>'gold_ffa_placement')::pg_catalog.int8
                          + (aa.details->>'gold_level_reward')::pg_catalog.int8) AS gold
      FROM admin_actions aa
      JOIN players pl ON pl.steam_id = aa.target_steam_id
     WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
       AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[])
     GROUP BY pl.id
     ORDER BY pl.id::pg_catalog.text COLLATE "C"
  LOOP
    UPDATE players pl
       SET total_xp = COALESCE(pl.total_xp, 0) - r.xp,
           ffa_xp_earned = COALESCE(pl.ffa_xp_earned, 0) - r.xp,
           gold_earned = COALESCE(pl.gold_earned, 0) - r.gold,
           ffa_gold_earned = COALESCE(pl.ffa_gold_earned, 0) - r.gold
     WHERE pl.id = r.pid;
  END LOOP;

  DELETE FROM gold_transactions g WHERE g.reference_id = ANY (qids::pg_catalog.text[]);
  DELETE FROM admin_actions aa
   WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
     AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[]);
  UPDATE match_report_quarantine q
     SET status = 'pending', reviewed_at = NULL, reviewed_by = NULL, review_note = NULL
   WHERE q.id = ANY (qids) AND q.status = 'credited'::pg_catalog.text;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 2 THEN
    RAISE EXCEPTION 'rollback 421: returning the held reports to pending touched % rows', n;
  END IF;
  RAISE NOTICE 'rollback 421: games 2 and 3 of lobby a18d56f5 returned to pending; their gold and XP taken back';
END $r421$;

COMMIT;
