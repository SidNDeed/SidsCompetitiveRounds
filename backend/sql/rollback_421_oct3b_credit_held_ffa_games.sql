-- Rollback of 421 (OCT3-B): takes back the gold and XP credited for games 2
-- and 3 of FFA lobby a18d56f5-382f-4fd0-8312-d873412a5ace and returns both
-- held reports to pending.
--
-- As deltas: each player's gold_earned and ffa_gold_earned lose exactly the
-- sum of the gold_transactions rows that reference the two held rows, and
-- total_xp and ffa_xp_earned lose exactly the XP their 421 audit rows record;
-- then those ledger and audit rows are deleted and both rows read pending with
-- reviewed_at, reviewed_by and review_note NULL, as 421 found them.
--
-- STATES: neither held row present: NOTICE, nothing written. Both credited
-- by 421 (its note, 12 audit rows): the rollback. Anything else: RAISE,
-- nothing applied.

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
  actor CONSTANT pg_catalog.text := 'system:migration_421';
  note CONSTANT pg_catalog.text := 'Migration 421, option B: gold and XP credited, ratings not applied.';
  n_rows pg_catalog.int8;
  n_credited pg_catalog.int8;
  n pg_catalog.int8;
  pid pg_catalog.uuid;
  r record;
BEGIN
  PERFORM 1 FROM match_report_quarantine q
    WHERE q.id = ANY (qids) ORDER BY q.id FOR NO KEY UPDATE;
  SELECT pg_catalog.count(*),
         pg_catalog.count(*) FILTER (WHERE q.status = 'credited'::pg_catalog.text AND q.review_note = note)
    INTO n_rows, n_credited
    FROM match_report_quarantine q WHERE q.id = ANY (qids);
  IF n_rows = 0 THEN
    RAISE NOTICE 'rollback 421: neither held report is in this database; nothing written';
    RETURN;
  END IF;
  IF n_rows <> 2 OR n_credited <> 2 THEN
    RAISE EXCEPTION 'rollback 421: the held reports are not both credited by 421 (% present, % credited); nothing applied',
      n_rows, n_credited;
  END IF;
  SELECT pg_catalog.count(*) INTO n FROM admin_actions aa
   WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
     AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[]);
  IF n <> 12 THEN
    RAISE EXCEPTION 'rollback 421: % audit rows of 421, expected 12; nothing applied', n;
  END IF;

  -- The players, locked in settlement's order (str(player_id)).
  FOR pid IN
    SELECT pl.id FROM players pl
     WHERE pl.steam_id IN (SELECT aa.target_steam_id FROM admin_actions aa
                            WHERE aa.action = 'quarantine_credit'::pg_catalog.text
                              AND aa.admin_steam_id = actor
                              AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[]))
     ORDER BY pl.id::pg_catalog.text COLLATE "C"
  LOOP
    PERFORM 1 FROM players pl WHERE pl.id = pid FOR NO KEY UPDATE;
  END LOOP;

  FOR r IN
    SELECT pl.id AS pid,
           (SELECT COALESCE(pg_catalog.sum((aa.details->>'xp')::pg_catalog.int8), 0)
              FROM admin_actions aa
             WHERE aa.action = 'quarantine_credit'::pg_catalog.text AND aa.admin_steam_id = actor
               AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[])
               AND aa.target_steam_id = pl.steam_id::pg_catalog.text) AS xp,
           (SELECT COALESCE(pg_catalog.sum(g.amount), 0)
              FROM gold_transactions g
             WHERE g.player_id = pl.id AND g.reference_id = ANY (qids::pg_catalog.text[])) AS gold
      FROM players pl
     WHERE pl.steam_id IN (SELECT aa.target_steam_id FROM admin_actions aa
                            WHERE aa.action = 'quarantine_credit'::pg_catalog.text
                              AND aa.admin_steam_id = actor
                              AND (aa.details->>'qid') = ANY (qids::pg_catalog.text[]))
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
