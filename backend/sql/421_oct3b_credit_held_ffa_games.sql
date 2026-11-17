-- 421: credit the gold and XP of games 2 and 3 of FFA lobby
-- a18d56f5-382f-4fd0-8312-d873412a5ace (OCT3-B, 17 Nov 2026). Ratings are
-- NOT applied.
--
-- Two ranked FFA reports of that lobby were held in match_report_quarantine
-- (reason lobby_completed) and never settled:
--   cb241216-41f9-49cc-aab5-3f0984c2c051  game 2, room ffa_58e81a62609a_040746_r2
--   1e419790-b377-402a-8455-20f4e39ebdc8  game 3, room ffa_58e81a62609a_042203_r3
-- Ruled (option B): each player gets the XP and the gold that settlement would
-- have paid for these two games; no rating, game row, card pack, title ladder
-- rung or mail is written.
--
-- WHAT IT WRITES, per game (2, then 3), per player in the order settlement
-- locks them (str(player_id), main.py submit_ffa_match, the players pass):
--   players.total_xp and ffa_xp_earned  += the XP literal below;
--   gold, three kinds, as settlement computes them (main.py, the "XP + gold"
--   block of submit_ffa_match):
--     ffa_xp        floor(new_xp / 100) - floor(old_xp / 100), from the row
--                   as found at apply;
--     ffa_placement the placement-gold literal below;
--     level_reward  level_reward_for over the levels crossed, from the row as
--                   found at apply (level_from_xp written in SQL below);
--   players.gold_earned and ffa_gold_earned += their sum (a delta, never an
--   absolute write); one gold_transactions row per kind above 0, its
--   reference_id the held row's id; one admin_actions row (action
--   quarantine_credit, admin_steam_id 'system:migration_421').
--   Where migration 420 (the moderator log) has run, that row also names
--   the player in affected_steam_ids and carries the note as its reason;
--   where it has not, 420's own fill of earlier rows names the player.
-- Then each held row: status 'credited', reviewed_at NOW(), reviewed_by NULL,
-- review_note naming this migration. The status column is VARCHAR(16) with no
-- CHECK (419 asserts that); 'credited' leaves every reader of pending rows.
--
-- The XP and placement-gold literals are what main's own helpers compute from
-- the two held bodies (backend/tests/test_oct3b_credit_pg.py, T5): v2 form,
-- kills breaking game 2's tie, opponent tiers from the ratings after game 1.
-- Each held body is pinned by md5(payload::text); each slot's Steam id is
-- read from the pinned body and checked against the lobby's roster.
--
-- STATES (the held rows are locked FOR NO KEY UPDATE NOWAIT first):
--   neither row present        NOTICE, nothing written (every test database);
--   both pending               the guards, then the credit;
--   both credited, and the     NOTICE, nothing written (a second run);
--   receipts check exact
--   anything else              RAISE, nothing applied.
-- LOCKS. Live writers lock players and held rows in orders of their own (a
-- shop purchase: the buyer, then the item's artist; the digest's posted
-- acknowledgement: held rows in scan order), so no order of this file's can
-- be one they share. Every lock the file waits for is therefore taken NOWAIT:
-- a row held elsewhere fails the run at once (SQLSTATE 55P03) with nothing
-- applied, and it can be run again. lock_timeout stays as a backstop for
-- table-level locks.
--
-- DEPLOY ORDER: THIS FILE FIRST and alone: it ships with no code change and
-- runs under the build that is live. Rollback:
-- rollback_421_oct3b_credit_held_ffa_games.sql.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL statement_timeout = '30s';
SELECT pg_catalog.set_config('search_path',
         'pg_catalog, ' || pg_catalog.quote_ident(pg_catalog.current_schema()) || ', pg_temp', true);

DO $m421$
DECLARE
  -- The two held rows, their games, rooms and body pins (read on the primary).
  pins CONSTANT pg_catalog.jsonb := '[
    {"q": "cb241216-41f9-49cc-aab5-3f0984c2c051", "game": 2, "room": "ffa_58e81a62609a_040746_r2", "md5": "5b3a330d97fd669722eb23954ccc3dbc"},
    {"q": "1e419790-b377-402a-8455-20f4e39ebdc8", "game": 3, "room": "ffa_58e81a62609a_042203_r3", "md5": "761bb451e3f395c6ad26cd69aa5b60a0"}
  ]';
  -- Per (held row, slot): the XP and the placement gold.
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
  lobby CONSTANT pg_catalog.uuid := 'a18d56f5-382f-4fd0-8312-d873412a5ace';
  actor CONSTANT pg_catalog.text := 'system:migration_421';
  note CONSTANT pg_catalog.text := 'Migration 421, option B: gold and XP credited, ratings not applied.';
  qids pg_catalog.uuid[];
  n_rows pg_catalog.int8;
  n_pending pg_catalog.int8;
  n_credited pg_catalog.int8;
  n pg_catalog.int8;
  m pg_catalog.int8;
  cum pg_catalog.numeric[];
  pre_off pg_catalog.jsonb;
  post_off pg_catalog.jsonb;
  r record;
  pid pg_catalog.uuid;
  new_xp pg_catalog.int8;
  old_xp pg_catalog.int8;
  drip pg_catalog.int8;
  o_lvl pg_catalog.int8;
  n_lvl pg_catalog.int8;
  lvl_gold pg_catalog.int8;
  tot pg_catalog.int8;
  sum_xp pg_catalog.int8 := 0;
  sum_drip pg_catalog.int8 := 0;
  sum_place pg_catalog.int8 := 0;
  sum_level pg_catalog.int8 := 0;
  aa_rel pg_catalog.oid;
  aff_t pg_catalog.oid;
  reason_t pg_catalog.oid;
  modlog pg_catalog.bool;
  exact pg_catalog.bool;
BEGIN
  SELECT pg_catalog.array_agg((p->>'q')::pg_catalog.uuid ORDER BY (p->>'game')::pg_catalog.int4)
    INTO qids FROM pg_catalog.jsonb_array_elements(pins) AS p;

  -- 1. The held rows, locked; their state decides everything after.
  PERFORM 1 FROM match_report_quarantine q
    WHERE q.id = ANY (qids) ORDER BY q.id FOR NO KEY UPDATE NOWAIT;
  SELECT pg_catalog.count(*),
         pg_catalog.count(*) FILTER (WHERE q.status = 'pending'::pg_catalog.text),
         pg_catalog.count(*) FILTER (WHERE q.status = 'credited'::pg_catalog.text)
    INTO n_rows, n_pending, n_credited
    FROM match_report_quarantine q WHERE q.id = ANY (qids);

  IF n_rows = 0 THEN
    RAISE NOTICE '421: neither held report of lobby % is in this database; nothing written', lobby;
    RETURN;
  END IF;
  IF n_rows <> 2 THEN
    RAISE EXCEPTION '421: % of the 2 held reports are present; nothing applied', n_rows;
  END IF;

  IF n_credited = 2 THEN
    -- A second run: accepted only when the receipts check is exact; any
    -- other credited state is one this file did not leave.
    SELECT
    -- oct3b:receipts-begin
      -- The figures of every audit row are proved in their domains (2b)
      -- before anything reads them as numbers: the CASE evaluates its
      -- condition first, and the rest only when it holds.
      CASE WHEN
      -- (1) both held rows read credited with this file's note
      (SELECT pg_catalog.count(*) FROM match_report_quarantine q
        WHERE q.id = ANY (qids) AND q.status = 'credited'::pg_catalog.text AND q.review_note = note) = 2
      -- (2) exactly 12 audit rows of this file
      AND (SELECT pg_catalog.count(*) FROM admin_actions aa
            WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
              AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[])) = 12
      -- (2b) and each carries xp, gold_ffa_xp, gold_ffa_placement,
      --      gold_level_reward and slot as JSON numbers, integral, in their
      --      domains: xp 1 to 2147483647, each gold kind 0 to 2147483647,
      --      slot 0 to 5. A figure missing, of another type, fractional or
      --      out of range fails the check; it is never read as 0.
      AND (SELECT pg_catalog.count(*) FROM admin_actions aa
             CROSS JOIN LATERAL (SELECT
               CASE WHEN pg_catalog.jsonb_typeof(aa.details->'xp') = 'number'::pg_catalog.text
                    THEN (aa.details->'xp')::pg_catalog.numeric END AS xp,
               CASE WHEN pg_catalog.jsonb_typeof(aa.details->'gold_ffa_xp') = 'number'::pg_catalog.text
                    THEN (aa.details->'gold_ffa_xp')::pg_catalog.numeric END AS gx,
               CASE WHEN pg_catalog.jsonb_typeof(aa.details->'gold_ffa_placement') = 'number'::pg_catalog.text
                    THEN (aa.details->'gold_ffa_placement')::pg_catalog.numeric END AS gp,
               CASE WHEN pg_catalog.jsonb_typeof(aa.details->'gold_level_reward') = 'number'::pg_catalog.text
                    THEN (aa.details->'gold_level_reward')::pg_catalog.numeric END AS gl,
               CASE WHEN pg_catalog.jsonb_typeof(aa.details->'slot') = 'number'::pg_catalog.text
                    THEN (aa.details->'slot')::pg_catalog.numeric END AS slot) AS d
            WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
              AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[])
              AND d.xp BETWEEN 1 AND 2147483647 AND d.xp = pg_catalog.trunc(d.xp)
              AND d.gx BETWEEN 0 AND 2147483647 AND d.gx = pg_catalog.trunc(d.gx)
              AND d.gp BETWEEN 0 AND 2147483647 AND d.gp = pg_catalog.trunc(d.gp)
              AND d.gl BETWEEN 0 AND 2147483647 AND d.gl = pg_catalog.trunc(d.gl)
              AND d.slot BETWEEN 0 AND 5 AND d.slot = pg_catalog.trunc(d.slot)) = 12
      THEN
      -- (2c) one audit row per (held row, player)
      (SELECT pg_catalog.count(DISTINCT ((aa.details->>'qid'), aa.target_steam_id)) FROM admin_actions aa
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
      ELSE false END
    -- oct3b:receipts-end
      INTO exact;
    IF exact THEN
      RAISE NOTICE '421: already applied (both held reports credited, every receipt exact); nothing written';
      RETURN;
    END IF;
    RAISE EXCEPTION '421: both held reports read credited but their receipts are not exactly this file''s; nothing applied';
  END IF;

  IF n_pending <> 2 THEN
    RAISE EXCEPTION '421: the held reports are not both pending (pending %, credited %); nothing applied',
      n_pending, n_credited;
  END IF;

  -- 2. Each held row is the report the amounts were computed from.
  SELECT pg_catalog.count(*) INTO n
    FROM pg_catalog.jsonb_array_elements(pins) AS p
    JOIN match_report_quarantine q ON q.id = (p->>'q')::pg_catalog.uuid
   WHERE q.mode = 'ffa'::pg_catalog.text
     AND q.group_id = lobby
     AND q.photon_room_id = (p->>'room')
     AND pg_catalog.md5(q.payload::pg_catalog.text) = (p->>'md5')
     AND (q.payload->>'lobby_id') = lobby::pg_catalog.text;
  IF n <> 2 THEN
    RAISE EXCEPTION '421: % of the 2 held reports match their pinned body, room and lobby; nothing applied', n;
  END IF;

  -- 3. The slots: six per body, slots 0 to 5, nobody left or absent, the same
  -- six Steam ids in both bodies, and those six are the lobby's roster.
  SELECT pg_catalog.count(*),
         pg_catalog.count(DISTINCT (q.id, (e->>'slot')::pg_catalog.int4)),
         pg_catalog.count(DISTINCT (q.id, e->>'steam_id')),
         pg_catalog.count(DISTINCT e->>'steam_id')
    INTO n_rows, n, m, n_pending
    FROM match_report_quarantine q, pg_catalog.jsonb_array_elements(q.payload->'players') AS e
   WHERE q.id = ANY (qids)
     AND (e->>'slot')::pg_catalog.int4 BETWEEN 0 AND 5
     AND (e->'left_early') = 'false'::pg_catalog.jsonb
     AND (e->'absent') = 'false'::pg_catalog.jsonb;
  IF n_rows <> 12 OR n <> 12 OR m <> 12 OR n_pending <> 6
     OR (SELECT pg_catalog.count(*) FROM match_report_quarantine q,
                pg_catalog.jsonb_array_elements(q.payload->'players') AS e
          WHERE q.id = ANY (qids)) <> 12 THEN
    RAISE EXCEPTION '421: the held bodies do not carry six present players on slots 0 to 5 each; nothing applied';
  END IF;
  IF EXISTS (
       (SELECT e->>'steam_id' FROM match_report_quarantine q,
               pg_catalog.jsonb_array_elements(q.payload->'players') AS e
         WHERE q.id = ANY (qids)
        EXCEPT
        SELECT pl.steam_id::pg_catalog.text FROM ffa_lobbies l JOIN players pl ON pl.id = ANY (l.member_ids)
         WHERE l.id = lobby)
       UNION ALL
       (SELECT pl.steam_id::pg_catalog.text FROM ffa_lobbies l JOIN players pl ON pl.id = ANY (l.member_ids)
         WHERE l.id = lobby
        EXCEPT
        SELECT e->>'steam_id' FROM match_report_quarantine q,
               pg_catalog.jsonb_array_elements(q.payload->'players') AS e
         WHERE q.id = ANY (qids))) THEN
    RAISE EXCEPTION '421: the held bodies'' players are not the lobby''s roster; nothing applied';
  END IF;
  SELECT pg_catalog.count(*) INTO n
    FROM pg_catalog.jsonb_array_elements(amounts) AS a
    JOIN match_report_quarantine q ON q.id = (a->>'q')::pg_catalog.uuid
    JOIN LATERAL pg_catalog.jsonb_array_elements(q.payload->'players') AS e
      ON (e->>'slot')::pg_catalog.int4 = (a->>'slot')::pg_catalog.int4;
  IF n <> 12 OR pg_catalog.jsonb_array_length(amounts) <> 12 THEN
    RAISE EXCEPTION '421: % of the 12 amounts name a slot of their held body; nothing applied', n;
  END IF;

  -- The audit table's form. Migration 420 (the moderator log) adds
  -- admin_actions.affected_steam_ids (text[], NOT NULL, DEFAULT '{}') and
  -- admin_actions.reason (text) in one file, and fills the rows written
  -- before it. Where both columns stand, each audit row names its player in
  -- affected_steam_ids and carries the note as its reason; where neither
  -- does, the row is written without them and 420's own fill names the
  -- player. One column alone, or affected_steam_ids of another type, is a
  -- form neither file leaves: RAISE, nothing applied.
  aa_rel := pg_catalog.to_regclass('admin_actions'::pg_catalog.text)::pg_catalog.oid;
  SELECT a.atttypid INTO aff_t FROM pg_catalog.pg_attribute a
   WHERE a.attrelid OPERATOR(pg_catalog.=) aa_rel
     AND a.attname OPERATOR(pg_catalog.=) 'affected_steam_ids'::pg_catalog.name AND NOT a.attisdropped;
  SELECT a.atttypid INTO reason_t FROM pg_catalog.pg_attribute a
   WHERE a.attrelid OPERATOR(pg_catalog.=) aa_rel
     AND a.attname OPERATOR(pg_catalog.=) 'reason'::pg_catalog.name AND NOT a.attisdropped;
  IF aa_rel IS NULL OR (aff_t IS NULL) <> (reason_t IS NULL) THEN
    RAISE EXCEPTION '421: admin_actions carries one of affected_steam_ids and reason without the other; nothing applied';
  END IF;
  IF aff_t IS NOT NULL
     AND aff_t OPERATOR(pg_catalog.<>) 'pg_catalog.text[]'::pg_catalog.regtype::pg_catalog.oid THEN
    RAISE EXCEPTION '421: admin_actions.affected_steam_ids is %, not text[]; nothing applied',
      pg_catalog.format_type(aff_t, NULL);
  END IF;
  modlog := aff_t IS NOT NULL;

  -- 4. The six players, locked NOWAIT in a fixed order (str(player_id): byte
  -- order of the text form), then re-read under the lock.
  FOR pid IN
    SELECT pl.id FROM players pl
     WHERE pl.steam_id IN (SELECT e->>'steam_id' FROM match_report_quarantine q,
                                  pg_catalog.jsonb_array_elements(q.payload->'players') AS e
                            WHERE q.id = ANY (qids))
     ORDER BY pl.id::pg_catalog.text COLLATE "C"
  LOOP
    PERFORM 1 FROM players pl WHERE pl.id = pid FOR NO KEY UPDATE NOWAIT;
  END LOOP;
  -- From here on the file waits for no row lock. Every later statement that
  -- takes one takes it on a row this transaction already holds:
  --   UPDATE players (XP, then gold): the six rows held FOR NO KEY UPDATE
  --     just above, the mode a non-key UPDATE takes;
  --   INSERT INTO gold_transactions: its foreign key takes FOR KEY SHARE on
  --     the player's row, held here in a stronger mode by this transaction;
  --   INSERT INTO admin_actions: a new row; the table has no foreign key
  --     (192);
  --   UPDATE match_report_quarantine: the two held rows, held FOR NO KEY
  --     UPDATE in step 1; reviewed_by is set NULL, which checks no key, and
  --     no other key column changes.
  SELECT pg_catalog.count(*), pg_catalog.count(DISTINCT pl.steam_id) INTO n, m
    FROM players pl
   WHERE pl.deleted_at IS NULL
     AND pl.steam_id IN (SELECT e->>'steam_id' FROM match_report_quarantine q,
                                pg_catalog.jsonb_array_elements(q.payload->'players') AS e
                          WHERE q.id = ANY (qids));
  IF n <> 6 OR m <> 6 OR (SELECT pg_catalog.count(*) FROM players pl
       WHERE pl.steam_id IN (SELECT e->>'steam_id' FROM match_report_quarantine q,
                                    pg_catalog.jsonb_array_elements(q.payload->'players') AS e
                              WHERE q.id = ANY (qids))) <> 6 THEN
    RAISE EXCEPTION '421: % of the 6 players exist once and are not deleted; nothing applied', n;
  END IF;

  -- 5. Nothing has been paid against either held row yet, and no audit row
  -- of any action names either one: not by this file's key (details qid),
  -- not by the key the moderator log writes for an accept or a discard
  -- (details quarantine_id, migration 420's lane), not in a target column,
  -- and not anywhere else in its details.
  IF EXISTS (SELECT 1 FROM gold_transactions g WHERE g.reference_id = ANY (qids::pg_catalog.text[]))
     OR EXISTS (SELECT 1 FROM admin_actions aa
                 WHERE (aa.target_steam_id = ANY (qids::pg_catalog.text[])
                        OR aa.target_match_id = ANY (qids)
                        OR aa.target_series_id = ANY (qids)
                        OR (aa.details->>'qid') = ANY (qids::pg_catalog.text[])
                        OR (aa.details->>'quarantine_id') = ANY (qids::pg_catalog.text[])
                        OR EXISTS (SELECT 1 FROM pg_catalog.unnest(qids) AS u(q)
                                    WHERE pg_catalog.strpos(aa.details::pg_catalog.text,
                                                            u.q::pg_catalog.text) > 0))) THEN
    RAISE EXCEPTION '421: a ledger or audit row already references a held report; nothing applied';
  END IF;

  -- Each player's gold_earned less the sum of their positive ledger rows
  -- (migration 020's invariant); the credit must leave it as found.
  SELECT pg_catalog.jsonb_object_agg(pl.id::pg_catalog.text,
           COALESCE(pl.gold_earned, 0)
           - COALESCE((SELECT pg_catalog.sum(g.amount) FROM gold_transactions g
                                   WHERE g.player_id = pl.id AND g.amount > 0), 0))
    INTO pre_off
    FROM players pl
   WHERE pl.steam_id IN (SELECT e->>'steam_id' FROM match_report_quarantine q,
                                pg_catalog.jsonb_array_elements(q.payload->'players') AS e
                          WHERE q.id = ANY (qids));

  -- level_from_xp in SQL: cum[n] is the total XP that reaches level n
  -- (xp_for_level(n) = int(100 * n ** 1.5) = floor(sqrt(10000 * n^3))), so the
  -- level of x is the number of cum entries <= x, at most 100.
  cum := (
    -- oct3b:thresholds-begin
    SELECT pg_catalog.array_agg(t.c ORDER BY t.n)
      FROM (SELECT g.n, pg_catalog.sum(pg_catalog.floor(pg_catalog.sqrt(
                          10000::pg_catalog.numeric * g.n * g.n * g.n))) OVER (ORDER BY g.n) AS c
              FROM pg_catalog.generate_series(1, 100) AS g(n)) AS t
    -- oct3b:thresholds-end
  );

  -- 6. The credit: game 2 then game 3, each in settlement's player order.
  FOR r IN
    SELECT (a->>'q')::pg_catalog.uuid AS qid, (p->>'game')::pg_catalog.int4 AS game,
           (p->>'room') AS room, (a->>'slot')::pg_catalog.int4 AS slot,
           pl.id AS pid, pl.steam_id::pg_catalog.text AS steam_id,
           (a->>'xp')::pg_catalog.int8 AS xp, (a->>'place_gold')::pg_catalog.int8 AS place_gold
      FROM pg_catalog.jsonb_array_elements(amounts) AS a
      JOIN pg_catalog.jsonb_array_elements(pins) AS p ON (p->>'q') = (a->>'q')
      JOIN match_report_quarantine q ON q.id = (a->>'q')::pg_catalog.uuid
      JOIN LATERAL pg_catalog.jsonb_array_elements(q.payload->'players') AS e
        ON (e->>'slot')::pg_catalog.int4 = (a->>'slot')::pg_catalog.int4
      JOIN players pl ON pl.steam_id = (e->>'steam_id')
     ORDER BY 2, pl.id::pg_catalog.text COLLATE "C"
  LOOP
    UPDATE players pl
       SET total_xp = COALESCE(pl.total_xp, 0) + r.xp,
           ffa_xp_earned = COALESCE(pl.ffa_xp_earned, 0) + r.xp
     WHERE pl.id = r.pid
    RETURNING pl.total_xp INTO new_xp;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
      RAISE EXCEPTION '421: the XP update of a player of game % touched % rows', r.game, n;
    END IF;
    old_xp := new_xp - r.xp;
    drip := GREATEST(0, pg_catalog.floor(new_xp::pg_catalog.numeric / 100)
                        - pg_catalog.floor(old_xp::pg_catalog.numeric / 100));
    SELECT b.old_lvl, b.new_lvl, b.level_gold INTO o_lvl, n_lvl, lvl_gold FROM (
      -- oct3b:level-begin
      SELECT pg_catalog.width_bucket(old_xp::pg_catalog.numeric, cum) AS old_lvl,
             pg_catalog.width_bucket(new_xp::pg_catalog.numeric, cum) AS new_lvl,
             COALESCE((
               SELECT pg_catalog.sum(CASE WHEN lv.n >= 5 AND lv.n % 5 = 0
                                          THEN CASE WHEN lv.n <= 50 THEN 100 ELSE 500 END
                                          ELSE 0 END)
                 FROM pg_catalog.generate_series(pg_catalog.width_bucket(old_xp::pg_catalog.numeric, cum) + 1,
                                                 pg_catalog.width_bucket(new_xp::pg_catalog.numeric, cum)) AS lv(n)
             ), 0)::pg_catalog.int8 AS level_gold
      -- oct3b:level-end
    ) AS b;
    tot := drip + r.place_gold + lvl_gold;
    IF tot > 0 THEN
      UPDATE players pl
         SET gold_earned = COALESCE(pl.gold_earned, 0) + tot,
             ffa_gold_earned = COALESCE(pl.ffa_gold_earned, 0) + tot
       WHERE pl.id = r.pid;
    END IF;
    IF drip > 0 THEN
      INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
      VALUES (r.pid, drip, 'ffa_xp', r.qid::pg_catalog.text, pg_catalog.now());
    END IF;
    IF r.place_gold > 0 THEN
      INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
      VALUES (r.pid, r.place_gold, 'ffa_placement', r.qid::pg_catalog.text, pg_catalog.now());
    END IF;
    IF lvl_gold > 0 THEN
      INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
      VALUES (r.pid, lvl_gold, 'level_reward', r.qid::pg_catalog.text, pg_catalog.now());
    END IF;
    IF modlog THEN
      INSERT INTO admin_actions (admin_steam_id, action, target_steam_id, target_match_id, details, created_at,
                                 affected_steam_ids, reason)
      VALUES (actor, 'quarantine_credit', r.steam_id, NULL,
              pg_catalog.jsonb_build_object(
                'qid'::pg_catalog.text, r.qid::pg_catalog.text,
                'game'::pg_catalog.text, r.game,
                'room'::pg_catalog.text, r.room,
                'slot'::pg_catalog.text, r.slot,
                'xp'::pg_catalog.text, r.xp,
                'gold_ffa_xp'::pg_catalog.text, drip,
                'gold_ffa_placement'::pg_catalog.text, r.place_gold,
                'gold_level_reward'::pg_catalog.text, lvl_gold,
                'ratings'::pg_catalog.text, 'not applied'::pg_catalog.text,
                'migration'::pg_catalog.text, 421),
              pg_catalog.now(), ARRAY[r.steam_id]::pg_catalog.text[], note);
    ELSE
      INSERT INTO admin_actions (admin_steam_id, action, target_steam_id, target_match_id, details, created_at)
      VALUES (actor, 'quarantine_credit', r.steam_id, NULL,
              pg_catalog.jsonb_build_object(
                'qid'::pg_catalog.text, r.qid::pg_catalog.text,
                'game'::pg_catalog.text, r.game,
                'room'::pg_catalog.text, r.room,
                'slot'::pg_catalog.text, r.slot,
                'xp'::pg_catalog.text, r.xp,
                'gold_ffa_xp'::pg_catalog.text, drip,
                'gold_ffa_placement'::pg_catalog.text, r.place_gold,
                'gold_level_reward'::pg_catalog.text, lvl_gold,
                'ratings'::pg_catalog.text, 'not applied'::pg_catalog.text,
                'migration'::pg_catalog.text, 421),
              pg_catalog.now());
    END IF;
    sum_xp := sum_xp + r.xp;
    sum_drip := sum_drip + drip;
    sum_place := sum_place + r.place_gold;
    sum_level := sum_level + lvl_gold;
  END LOOP;

  -- 7. The mark.
  FOR pid IN SELECT pg_catalog.unnest(qids) LOOP
    UPDATE match_report_quarantine q
       SET status = 'credited', reviewed_at = pg_catalog.now(), reviewed_by = NULL, review_note = note
     WHERE q.id = pid AND q.status = 'pending'::pg_catalog.text;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
      RAISE EXCEPTION '421: marking held report % credited touched % rows', pid, n;
    END IF;
  END LOOP;

  -- 8. Post-checks, inside the transaction.
  SELECT pg_catalog.count(*) FILTER (WHERE g.reason = 'ffa_placement'::pg_catalog.text),
         COALESCE(pg_catalog.sum(g.amount) FILTER (WHERE g.reason = 'ffa_placement'::pg_catalog.text), 0)
    INTO n, m
    FROM gold_transactions g WHERE g.reference_id = ANY (qids::pg_catalog.text[]);
  IF n <> 12 OR m <> sum_place THEN
    RAISE EXCEPTION '421: post-check: % placement rows summing %, expected 12 summing %', n, m, sum_place;
  END IF;
  SELECT COALESCE(pg_catalog.sum(g.amount) FILTER (WHERE g.reason = 'ffa_xp'::pg_catalog.text), 0),
         COALESCE(pg_catalog.sum(g.amount) FILTER (WHERE g.reason = 'level_reward'::pg_catalog.text), 0)
    INTO n, m
    FROM gold_transactions g WHERE g.reference_id = ANY (qids::pg_catalog.text[]);
  IF n <> sum_drip OR m <> sum_level THEN
    RAISE EXCEPTION '421: post-check: ledger drip % and level gold %, computed % and %', n, m, sum_drip, sum_level;
  END IF;
  SELECT pg_catalog.count(*) INTO n FROM admin_actions aa
   WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
     AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[]);
  IF n <> 12 THEN
    RAISE EXCEPTION '421: post-check: % audit rows, expected 12', n;
  END IF;
  SELECT pg_catalog.jsonb_object_agg(pl.id::pg_catalog.text,
           COALESCE(pl.gold_earned, 0)
           - COALESCE((SELECT pg_catalog.sum(g.amount) FROM gold_transactions g
                                   WHERE g.player_id = pl.id AND g.amount > 0), 0))
    INTO post_off
    FROM players pl
   WHERE pl.steam_id IN (SELECT e->>'steam_id' FROM match_report_quarantine q,
                                pg_catalog.jsonb_array_elements(q.payload->'players') AS e
                          WHERE q.id = ANY (qids));
  IF post_off IS DISTINCT FROM pre_off THEN
    RAISE EXCEPTION '421: post-check: gold_earned less the positive ledger moved for a player';
  END IF;

  RAISE NOTICE '421: credited games 2 and 3 of lobby %: XP %, gold % (drip %, placement %, level %); ratings not applied',
    lobby, sum_xp, sum_drip + sum_place + sum_level, sum_drip, sum_place, sum_level;
END $m421$;

COMMIT;
