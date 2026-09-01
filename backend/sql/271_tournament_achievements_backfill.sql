-- 271_tournament_achievements_backfill.sql
-- Aug 31 batch: retroactive grant of the five tournament achievements
-- (tourn_champion_sync/async, tourn_second_sync/async, tourn_iron_bracket)
-- for tournaments completed BEFORE the live grant site shipped
-- (tournaments.py _grant_tournament_achievements, called from the completion
-- transaction). Mirrors the LIVE rules exactly; gold at the LIVE tiers
-- (champion 500 / second 300 / iron 100 — ACHIEVEMENT_GOLD_OVERRIDES + the
-- 100g default), guarded by NOT EXISTS on the achievement ledger so a rerun
-- (or the wrapper's `|| psql` retry, learning #243) can never double-pay.
-- Measured before writing (#314): production holds exactly ONE completed
-- tournament (c3c448f3, async, May 13) — expected grants: 1 champion_async,
-- 1 second_async, plus its iron-bracket survivors.
-- DEPLOY ORDER: STRICTLY AFTER the new API is live on BOTH boxes — this is
-- a one-time snapshot and the live grant site is the only writer for
-- tournaments completing later. Run early and a tournament that completes
-- in the gap (old API = no grant site; snapshot = already taken) misses its
-- rewards PERMANENTLY, and idempotency cannot repair it (#236's exact
-- shape: the guard key is written by the NEW code, so the new code must be
-- live first). Round-2 review blocker 3.
BEGIN;

CREATE TEMP TABLE _tourn_ach (player_id uuid, akey varchar(64), gold int)
    ON COMMIT DROP;

-- Champions + finalists, kind-split. Kind mapping mirrors the LIVE site
-- exactly (tournaments.py: sync stays sync, every OTHER kind maps to
-- async) — a divergent fail-closed guard here would silently skip a future
-- third kind the live path rewards (round-2 review H parity note).
INSERT INTO _tourn_ach
SELECT ws.player_id,
       'tourn_champion_' || (CASE WHEN t.kind = 'sync' THEN 'sync' ELSE 'async' END), 500
  FROM tournaments t
  JOIN tournament_signups ws ON ws.id = t.winner_signup_id
 WHERE t.status = 'completed'
   AND ws.player_id IS NOT NULL
UNION ALL
SELECT ru.player_id,
       'tourn_second_' || (CASE WHEN t.kind = 'sync' THEN 'sync' ELSE 'async' END), 300
  FROM tournaments t
  JOIN tournament_signups ru ON ru.id = t.runner_up_signup_id
 WHERE t.status = 'completed'
   AND ru.player_id IS NOT NULL;

-- Iron Bracket: non-speculative signups of completed tournaments who were in
-- at least one bracket match, never carried the no-show/ban flag, were never
-- in a double_forfeit, and were never the forfeiting seat of a 'forfeit'
-- (winner_signup_id is the NON-forfeiting side for that status; opponent
-- forfeits count as played, byes are neutral — Sid's spec, mirroring the
-- live SQL in _grant_tournament_achievements).
INSERT INTO _tourn_ach
SELECT DISTINCT s.player_id, 'tourn_iron_bracket', 100
  FROM tournaments t
  JOIN tournament_signups s ON s.tournament_id = t.id
 WHERE t.status = 'completed'
   AND NOT s.is_speculative
   AND s.player_id IS NOT NULL
   AND NOT s.forfeited
   AND EXISTS (SELECT 1 FROM tournament_matches mp
                WHERE mp.tournament_id = t.id
                  AND (mp.p1_signup_id = s.id OR mp.p2_signup_id = s.id))
   AND NOT EXISTS (
       SELECT 1 FROM tournament_matches m
        WHERE m.tournament_id = t.id
          AND (m.p1_signup_id = s.id OR m.p2_signup_id = s.id)
          AND (m.status = 'double_forfeit'
               OR (m.status = 'forfeit'
                   AND m.winner_signup_id IS DISTINCT FROM s.id)));

-- Achievement rows (idempotent).
INSERT INTO player_achievements (player_id, achievement_key)
SELECT DISTINCT player_id, akey FROM _tourn_ach
ON CONFLICT DO NOTHING;

-- Gold — once per (player, key), achievement-ledger-guarded (#229 live-tier
-- values are the temp table's own gold column, stated above), aggregated to
-- one row per player before touching players (#240).
WITH owed AS (
    SELECT DISTINCT e.player_id, e.akey, e.gold
      FROM _tourn_ach e
     WHERE NOT EXISTS (
             SELECT 1 FROM gold_transactions gt
              WHERE gt.player_id = e.player_id
                AND gt.reason = 'achievement'
                AND gt.reference_id = e.akey)
),
ledger AS (
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
    SELECT player_id, gold, 'achievement', akey FROM owed
    RETURNING player_id, amount
),
per_player AS (
    SELECT player_id, SUM(amount)::int AS total FROM ledger GROUP BY player_id
)
UPDATE players p
   SET gold_earned = COALESCE(p.gold_earned, 0) + pp.total
  FROM per_player pp
 WHERE p.id = pp.player_id;

-- Loud post-check (#183 pattern): every temp-table pair must now hold its
-- achievement row; abort the transaction if any is missing.
DO $$
DECLARE missing int;
BEGIN
    SELECT COUNT(*) INTO missing
      FROM (SELECT DISTINCT player_id, akey FROM _tourn_ach) e
     WHERE NOT EXISTS (
             SELECT 1 FROM player_achievements pa
              WHERE pa.player_id = e.player_id
                AND pa.achievement_key = e.akey);
    IF missing > 0 THEN
        RAISE EXCEPTION 'tournament achievement backfill incomplete: % pair(s) missing', missing;
    END IF;
    RAISE NOTICE 'tournament achievement backfill post-check OK';
END $$;

COMMIT;
