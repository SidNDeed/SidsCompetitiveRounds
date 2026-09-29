-- 363_revoke_ffa_shutouts_below_finishing_count.sql
--
-- FFA-TROPHIES, item B: take back the four ranked-FFA shutout awards that fail
-- the corrected rule. Ruling (Sid, 2026-09-28): the same rule for everyone,
-- his own award included, and every award that fails it is revoked.
--
-- THE RULE THEY FAIL. Clean House, Party Crasher and Hostile Takeover
-- (ffa_shutout_3 / _4 / _5, 100 / 300 / 500 gold, nested) are tiered on the
-- number of players who FINISHED the game: _ffa_finishing_count in
-- backend/api/main.py, landing in the same batch. Until then the live rule
-- and migration 196's backfill both tiered on the lobby's seated roster
-- (ffa_lobbies.member_ids), which keeps every seat of the sitting, including
-- seats that had already left. Migration 196's roster rule is superseded; it
-- is NOT re-run (its own header: a re-run grants nothing new, and an edited
-- copy no-ops for everyone it already granted).
--
-- CENSUS (read-only SELECTs against the primary, 2026-09-28 15:08Z). Every
-- ranked FFA 5-0 on record, "finished" = rows with neither left_early nor
-- absent in ffa_match_players:
--
--   match     ended       seated  finished  awards on it
--   83c2e198  2026-07-29       3         3  Clean House (sound)
--   35c937fb  2026-08-01       3         3  Clean House (sound)
--   683b87b2  2026-08-06       4         3  Clean House (sound), Party Crasher (FAILS)
--   08f41a97  2026-09-08       5         2  all three (all FAIL)
--
-- Seven awards exist; four fail. Each is pinned below by its award row, its
-- holder, its key, its gold and the ledger row that paid it:
--
--   award  holder                                      key            gold  paid by ledger row
--   414    fbb3d29d-b637-43c0-9787-357c2753e28c (Sid)  ffa_shutout_4   300  25287 (migration 199 backpay)
--   567    ef39f993-7ede-4017-901d-bc637dd743d2        ffa_shutout_3   100  35699
--   568    ef39f993-7ede-4017-901d-bc637dd743d2        ffa_shutout_4   300  35700
--   569    ef39f993-7ede-4017-901d-bc637dd743d2        ffa_shutout_5   500  35701
--
-- 1200 gold in all: 900 from the second holder, 300 from Sid. Awards 411, 412
-- and 413 pass the rule and are untouched. Neither holder's gold_earned is
-- below the amount taken (165014 and 247894 at census), and the file refuses
-- if that stops being true, so the GREATEST(0, ...) floor below never clamps
-- and the ledger row always equals the balance move (#326).
--
-- PATTERN: migration 088 (the team_sweep revocation): a negative
-- gold_transactions row, reason 'achievement_revoked', reference_id = the key;
-- gold_earned lowered as a DELTA; the player_achievements row deleted. The
-- balance update is aggregated per PLAYER first: one holder has three rows,
-- and UPDATE ... FROM a per-award source updates each player row once, so an
-- unaggregated update would take back 100, 300 or 500 instead of 900 (#240).
--
-- RE-EARNING. _achievement_payment_eligible pays a key again when the clawbacks
-- for it are at least the payments (paid = 1, clawed = 1 after this file), so
-- a holder who later earns one of these under the corrected rule is paid again.
--
-- STATES, and what each run does. Every target is classified first:
--   pending        its award row, its one payment and no clawback
--   done           exactly one clawback of its gold (this file already ran)
--   no_holder      its holder is not in players at all
--   other          anything else
-- All four pending: revoke. All four done: already applied, change nothing.
-- All four no_holder: not the production database (a harness that applies
-- every later migration, such as the trading test's m53), change nothing.
-- Anything else: refuse, before any write, with the four states named.
--
-- DEPLOY ORDER: THIS FILE FIRST, as its own commit ahead of the rule's code
-- (#477's two-SHA order), then the api. Data only, no schema change, and
-- neither side needs the other to run: the api reads no state this file
-- creates. Between the two steps the OLD rule is still live, so a ranked FFA
-- 5-0 settled in that window could grant one of these keys again under the
-- roster count; the census SELECT is re-run after the api lands to confirm
-- none was.
--
-- EVERY APPLICATION, A RE-RUN INCLUDED, issues the same three statements: the
-- temporary table _m363_target (dropped at COMMIT), the preflight SELECT and
-- the DO block. Only the DO block writes, and only from the all-pending
-- state; from done or no_holder it returns before its write half. Explicit
-- transaction (#340); a refusal rolls back everything.

BEGIN;

-- The four targets and their state, kept for the preflight print and the
-- decision below: one definition of the classification, read by both.
CREATE TEMP TABLE _m363_target ON COMMIT DROP AS
WITH target(pa_id, player_id, achievement_key, gold, ledger_id) AS (
    VALUES
        (414, CAST('fbb3d29d-b637-43c0-9787-357c2753e28c' AS uuid), 'ffa_shutout_4', 300, CAST(25287 AS bigint)),
        (567, CAST('ef39f993-7ede-4017-901d-bc637dd743d2' AS uuid), 'ffa_shutout_3', 100, CAST(35699 AS bigint)),
        (568, CAST('ef39f993-7ede-4017-901d-bc637dd743d2' AS uuid), 'ffa_shutout_4', 300, CAST(35700 AS bigint)),
        (569, CAST('ef39f993-7ede-4017-901d-bc637dd743d2' AS uuid), 'ffa_shutout_5', 500, CAST(35701 AS bigint))
),
facts AS (
    SELECT t.pa_id, t.player_id, t.achievement_key, t.gold, t.ledger_id,
           (p.id IS NOT NULL) AS holder_exists,
           COALESCE(p.gold_earned, 0) AS gold_earned_before,
           (pa.id IS NOT NULL) AS award_present,
           pa.unlocked_at,
           (SELECT COUNT(*) FROM gold_transactions g
             WHERE g.player_id = t.player_id AND g.reference_id = t.achievement_key
               AND g.reason IN ('achievement', 'achievement_prepaid')) AS paid_rows,
           (SELECT COUNT(*) FROM gold_transactions g
             WHERE g.id = t.ledger_id AND g.player_id = t.player_id
               AND g.reference_id = t.achievement_key AND g.reason = 'achievement'
               AND g.amount = t.gold) AS pinned_payment,
           (SELECT COUNT(*) FROM gold_transactions g
             WHERE g.player_id = t.player_id AND g.reference_id = t.achievement_key
               AND g.reason = 'achievement_revoked') AS clawback_rows,
           (SELECT COUNT(*) FROM gold_transactions g
             WHERE g.player_id = t.player_id AND g.reference_id = t.achievement_key
               AND g.reason = 'achievement_revoked' AND g.amount = -t.gold) AS matching_clawbacks
      FROM target t
      LEFT JOIN players p ON p.id = t.player_id
      LEFT JOIN player_achievements pa
             ON pa.id = t.pa_id AND pa.player_id = t.player_id
            AND pa.achievement_key = t.achievement_key
)
SELECT f.*,
       CASE
           WHEN NOT f.holder_exists THEN 'no_holder'
           WHEN f.clawback_rows = 1 AND f.matching_clawbacks = 1 THEN 'done'
           WHEN f.clawback_rows = 0 AND f.award_present
                AND f.paid_rows = 1 AND f.pinned_payment = 1 THEN 'pending'
           ELSE 'other'
       END AS state
  FROM facts f;

-- Preflight: the four rows as this database holds them, before anything is
-- written.
SELECT pa_id, player_id, achievement_key, gold, ledger_id, unlocked_at,
       paid_rows, clawback_rows, gold_earned_before, state
  FROM _m363_target
 ORDER BY pa_id;

DO $m363$
DECLARE
    n_rows      INT;
    n_pending   INT;
    n_done      INT;
    n_absent    INT;
    states      TEXT;
    short       TEXT;
    n_ins       INT;
    n_upd       INT;
    n_del       INT;
    n_left      INT;
    n_owed      INT;
    n_drift     INT;
    revoked     TEXT;
    taken       INT;
    holders     INT;
BEGIN
    SELECT COUNT(*),
           COUNT(*) FILTER (WHERE state = 'pending'),
           COUNT(*) FILTER (WHERE state = 'done'),
           COUNT(*) FILTER (WHERE state = 'no_holder'),
           string_agg(pa_id || '=' || state, ', ' ORDER BY pa_id)
      INTO n_rows, n_pending, n_done, n_absent, states
      FROM _m363_target;

    IF n_rows <> 4 THEN
        RAISE EXCEPTION 'migration 363: expected 4 targets, classified %', n_rows;
    END IF;
    IF n_done = 4 THEN
        RAISE NOTICE 'migration 363: already applied (%), nothing changed', states;
        RETURN;
    END IF;
    IF n_absent = 4 THEN
        RAISE NOTICE 'migration 363: none of the holders is in players, so this is not '
                     'the production database; nothing changed';
        RETURN;
    END IF;
    IF n_pending <> 4 THEN
        RAISE EXCEPTION 'migration 363: refusing, the four targets are not all pending (%)',
                        states;
    END IF;

    -- #326: the floor must never be what decides the amount.
    SELECT string_agg(player_id || ' holds ' || earned || ' < ' || owed, ', ')
      INTO short
      FROM (SELECT player_id, MIN(gold_earned_before) AS earned, SUM(gold) AS owed
              FROM _m363_target GROUP BY player_id) s
     WHERE earned < owed;
    IF short IS NOT NULL THEN
        RAISE EXCEPTION 'migration 363: refusing, gold_earned below the amount taken: %', short;
    END IF;

    -- ---- Write half. ----
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
    SELECT player_id, -gold, 'achievement_revoked', achievement_key
      FROM _m363_target;
    GET DIAGNOSTICS n_ins = ROW_COUNT;

    UPDATE players p
       SET gold_earned = GREATEST(0, COALESCE(p.gold_earned, 0) - s.owed)
      FROM (SELECT player_id, SUM(gold)::int AS owed
              FROM _m363_target GROUP BY player_id) s
     WHERE p.id = s.player_id;
    GET DIAGNOSTICS n_upd = ROW_COUNT;

    DELETE FROM player_achievements pa
     USING _m363_target t
     WHERE pa.id = t.pa_id AND pa.player_id = t.player_id
       AND pa.achievement_key = t.achievement_key;
    GET DIAGNOSTICS n_del = ROW_COUNT;

    IF n_ins <> 4 OR n_upd <> 2 OR n_del <> 4 THEN
        RAISE EXCEPTION 'migration 363: wrote % clawback(s), % balance(s), % deletion(s); '
                        'expected 4, 2, 4', n_ins, n_upd, n_del;
    END IF;

    -- ---- Post-checks, inside the same transaction. ----
    SELECT COUNT(*) INTO n_left
      FROM player_achievements pa JOIN _m363_target t ON t.pa_id = pa.id;
    SELECT COUNT(*) INTO n_owed
      FROM _m363_target t
     WHERE (SELECT COUNT(*) FROM gold_transactions g
             WHERE g.player_id = t.player_id AND g.reference_id = t.achievement_key
               AND g.reason = 'achievement_revoked')
         < (SELECT COUNT(*) FROM gold_transactions g
             WHERE g.player_id = t.player_id AND g.reference_id = t.achievement_key
               AND g.reason IN ('achievement', 'achievement_prepaid'));
    SELECT COUNT(*) INTO n_drift
      FROM (SELECT player_id, MIN(gold_earned_before) AS before, SUM(gold) AS owed
              FROM _m363_target GROUP BY player_id) s
      JOIN players p ON p.id = s.player_id
     WHERE COALESCE(p.gold_earned, 0) <> s.before - s.owed;
    IF n_left <> 0 OR n_owed <> 0 OR n_drift <> 0 THEN
        RAISE EXCEPTION 'migration 363: post-check failed (awards left %, keys not '
                        're-payable %, balances off %)', n_left, n_owed, n_drift;
    END IF;

    SELECT string_agg(pa_id::text, ', ' ORDER BY pa_id), SUM(gold)::int,
           COUNT(DISTINCT player_id)::int
      INTO revoked, taken, holders
      FROM _m363_target;
    RAISE NOTICE 'migration 363: revoked awards %; % gold taken back from % player(s); '
                 'each key pays again if re-earned', revoked, taken, holders;
END
$m363$;

COMMIT;
