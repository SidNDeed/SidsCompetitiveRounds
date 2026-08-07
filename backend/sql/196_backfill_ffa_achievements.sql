-- 196: retroactive grants for the six Aug-7 FFA achievements.
--
-- Sid asked for these to be awarded for games already played. Every rule below
-- mirrors the LIVE evaluation in submit_ffa_match exactly; where the live rule
-- reads something this migration cannot see, the difference is called out.
--
-- ── NO GOLD IS MOVED ───────────────────────────────────────────────────────
-- All six sat at 0 in ACHIEVEMENT_GOLD_OVERRIDES when this was written (they
-- were badge-only because every value they read is reporter-attested — see the
-- block there), so this file writes player_achievements rows and nothing else:
-- no balance to top up, no gold_transactions row, and none of migration 138's
-- delta arithmetic (#229).
--
-- Sid priced them the next day onto the 100/300/500 tiers (migration 199's
-- header carries the exact per-key values), which is exactly the
-- "if a payout is ever introduced, THAT release owes a separate delta backfill"
-- case this paragraph anticipated — migration 199 is that backfill. Do NOT fold
-- a payout into this file instead: it is idempotent against GRANTS, so an edit
-- here silently no-ops for everyone it has already granted.
--
-- ── Idempotent ─────────────────────────────────────────────────────────────
-- ON CONFLICT DO NOTHING against the (player_id, achievement_key) uniqueness
-- the table already enforces, so a re-run grants nothing new and a player who
-- has already earned one live keeps their original unlocked_at.
--
-- A normal run executes this file ONCE, not twice: the wrapper's preferred
-- `psql -f /migrations/<file>` arm fails on the missing path BEFORE any SQL is
-- executed, and the `||` stdin fallback then runs the file (#243). Idempotency
-- is still required — a hand re-run is always possible, and a failure partway
-- through re-executes the whole file from the top.
--
-- ── Measured against production before writing (read-only) ─────────────────
--   98 ranked FFA matches on record.
--   ffa_shutout_3           3 matches      ffa_kills_50    6 instances / 4 players
--   ffa_shutout_4           1 match        ffa_kills_100   0
--   ffa_shutout_5           0              ffa_half_point_heartbreak  0
--
-- The heartbreak count is ZERO because the highest leftover-half-point total
-- ever recorded is 9 while the threshold is 10. Not a bug here — a tuning
-- question with Sid. Two earlier statements about it were WRONG and are
-- corrected in place rather than left to mislead:
--
--   * "the ceiling in a 3-player first-to-5 is exactly 10" — false. Measured
--     max leftover by lobby size (ranked, non-ghost, losers): 3p -> 6,
--     4p -> 6, 5p -> 8, 6p -> 9. Nothing has ever reached 10 at ANY size.
--   * "therefore the badge is unearnable" — also false. score_target is
--     host-configurable 3-10 (main.py, ffa lobby settings), and a longer
--     target raises the ceiling. Production has only ever played target 5
--     (97 matches) and target 4 (1), which is why nobody has earned it.
--
-- So it is a long-game trophy, not an impossibility. Historical earners by
-- threshold, if Sid wants it reachable in standard first-to-5 play:
--   >=5: 43 instances / 14 players    >=8: 4 / 2
--   >=6: 21 / 8                       >=9: 1 / 1
--   >=7:  8 / 3                       >=10: 0 / 0
-- Changing it means editing the literal in BOTH this file and the live rule in
-- submit_ffa_match; re-running this file afterwards is safe (ON CONFLICT).
--
-- ── Why a raw INSERT instead of _grant_achievement_inline ──────────────────
-- That helper has exactly two side effects beyond the row: gold (skipped when
-- the payout is falsy — all six are 0) and an equippable title via
-- ACHIEVEMENT_TITLE_SKUS, which contains ONLY regicide and stan_slayer.
-- Neither branch can fire for any of the six, so a direct INSERT is equivalent
-- to the live path rather than a shortcut around it. Verified, not assumed.

BEGIN;

-- ── 1-3: shutout tiers ─────────────────────────────────────────────────────
-- Live rule: rated, winner rounds_won == 5, EVERY other reported player
-- rounds_won == 0, granted to the winner, tier by seated-roster size.
--
-- Roster basis is ffa_lobbies.member_ids — the lock-time roster, server state
-- the client cannot author. Same basis the live rule uses since the round-1
-- review (the client's absent/left_early flags are unsigned and could inflate
-- the tier). COALESCE to the reported row count for any historical match whose
-- lobby row is gone, which is the best evidence remaining.
-- The winner expression is `array_agg(...)[1]`, NOT `MIN(...)`: PostgreSQL 16
-- has no built-in min(uuid) aggregate, so MIN(p.player_id) raises
-- `function min(uuid) does not exist` and — because this file is one
-- transaction — rolls back the kills and heartbreak grants along with it.
-- Caught by running this SELECT read-only against production before shipping;
-- it is valid-looking SQL that fails only against the real server (#219).
-- The HAVING below guarantees exactly one row passes the FILTER, so taking
-- element [1] is a genuine singleton pick, not a choice among candidates.
WITH shutout AS (
    SELECT m.id AS match_id,
           COALESCE(array_length(l.member_ids, 1), COUNT(*)) AS roster,
           (array_agg(p.player_id) FILTER (WHERE p.rounds_won = 5))[1] AS winner_id
      FROM ffa_matches m
      JOIN ffa_match_players p ON p.match_id = m.id
      LEFT JOIN ffa_lobbies l ON l.id = m.lobby_id
     WHERE m.is_ranked
     GROUP BY m.id, l.member_ids
    HAVING COUNT(*) FILTER (WHERE p.rounds_won = 5) = 1
       AND COUNT(*) FILTER (WHERE p.rounds_won > 0) = 1
)
INSERT INTO player_achievements (player_id, achievement_key)
-- DISTINCT: a player who won several qualifying shutouts yields the same
-- (player, key) more than once. ON CONFLICT DO NOTHING copes, but deduping in
-- the SELECT means the statement never depends on conflict semantics for
-- intra-statement duplicates at all.
SELECT DISTINCT s.winner_id, k.key
  FROM shutout s
  JOIN (VALUES ('ffa_shutout_3', 3),
               ('ffa_shutout_4', 4),
               ('ffa_shutout_5', 5)) AS k(key, need)
    ON s.roster >= k.need
 WHERE s.winner_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- ── 4-5: kill counts ───────────────────────────────────────────────────────
-- Live rule: rated, not a ghost, kills > 50 / > 100, per player.
--
-- DIFFERENCE FROM LIVE, stated deliberately: the live rule additionally
-- requires the report to have verified under the v2 HMAC canonical
-- (kills_in_canonical), because kills are only covered by the signature in v2.
-- A historical row does not record which canonical form verified it.
--
-- An earlier draft substituted the lobby's frozen kills_tiebreak capability as
-- a proxy. That substitute is defensible on correctness grounds — a
-- kills-capable lobby quarantines a v1 report, so such a row effectively WAS
-- v2 — but measuring it against production showed it defeats the purpose of the
-- backfill entirely. Every ranked non-ghost row with kills > 50:
--
--     kills 53  2026-07-29   capable=false
--     kills 57  2026-07-30   capable=false
--     kills 51  2026-07-31   capable=false
--     kills 93  2026-08-01   capable=false
--     kills 55  2026-08-04   capable=false
--     kills 56  2026-08-06   capable=TRUE
--
-- The capability shipped on Aug 6, so the gate excludes ALL history and admits
-- only the one game the live rule already covers: 1 player instead of 4. A
-- backfill that grants nothing the live path wouldn't have granted anyway is
-- not a backfill.
--
-- The gate is therefore dropped, and the reasoning is worth stating plainly:
-- unsigned historical kills are exactly as forgeable as the signed-but-
-- client-attested kills of every FUTURE game, because the HMAC key ships in
-- the client. The residual is identical either way, it is already accepted for
-- these six keys (they pay 0 gold, grant no title, and move no rating), and
-- refusing history on signature grounds while accepting the same exposure
-- forever forward is not a security posture — it just costs three players a
-- badge they genuinely earned. Ranked + non-ghost filters stay.
INSERT INTO player_achievements (player_id, achievement_key)
SELECT DISTINCT p.player_id, k.key      -- same intra-statement dedupe
  FROM ffa_match_players p
  JOIN ffa_matches m ON m.id = p.match_id
  JOIN (VALUES ('ffa_kills_50', 50),
               ('ffa_kills_100', 100)) AS k(key, need)
    ON p.kills > k.need
 WHERE m.is_ranked
   AND NOT COALESCE(p.absent, FALSE)
ON CONFLICT DO NOTHING;

-- ── 6: half-point heartbreak ───────────────────────────────────────────────
-- Live rule: rated, not a ghost, placement > 1 (lost), and
-- points_total - 2*rounds_won >= 10 leftover half points.
-- The literal 2 is FFA_POINTS_TO_WIN_ROUND, which is a compile-time constant
-- in the engine (FfaMode.PointsToWinRound, explicitly not configurable), so
-- there is no per-lobby value to join against.
INSERT INTO player_achievements (player_id, achievement_key)
SELECT DISTINCT p.player_id, 'ffa_half_point_heartbreak'   -- same dedupe
  FROM ffa_match_players p
  JOIN ffa_matches m ON m.id = p.match_id
 WHERE m.is_ranked
   AND NOT COALESCE(p.absent, FALSE)
   AND p.placement > 1
   AND (p.points_total - 2 * p.rounds_won) >= 10
ON CONFLICT DO NOTHING;

-- ── Post-check ─────────────────────────────────────────────────────────────
DO $$
DECLARE
    k TEXT;
    n BIGINT;
    total BIGINT := 0;
BEGIN
    FOREACH k IN ARRAY ARRAY['ffa_shutout_3','ffa_shutout_4','ffa_shutout_5',
                             'ffa_kills_50','ffa_kills_100',
                             'ffa_half_point_heartbreak']
    LOOP
        SELECT COUNT(*) INTO n FROM player_achievements WHERE achievement_key = k;
        total := total + n;
        RAISE NOTICE 'migration 196: % now held by % player(s)', k, n;
    END LOOP;

    -- Sanity, not a gate: zero grants is a legitimate outcome for the two keys
    -- with no historical earners (kills_100 and heartbreak), so this must NOT
    -- RAISE on a low total. It exists so the deploy log carries the numbers.
    RAISE NOTICE 'migration 196 post-check OK (% FFA achievement rows total)', total;

    -- An earlier draft raised here if ANY ffa_* key outside the six existed.
    -- That check validated no property of this file (every key it inserts is a
    -- literal from the six) while giving a future `ffa_marathon` badge the power
    -- to abort a rerun of this migration and roll back its grants. A post-check
    -- must only assert things the migration itself controls; policing unrelated
    -- rows is how an idempotent file acquires a failure mode it never needed.
    --
    -- The real invariant worth asserting is that every row this file could have
    -- written is attributable to a qualifying match. A grant with no supporting
    -- ffa_match_players row would mean the SELECTs matched something they should
    -- not have.
    SELECT COUNT(*) INTO n
      FROM player_achievements pa
     WHERE pa.achievement_key IN ('ffa_shutout_3','ffa_shutout_4','ffa_shutout_5',
                                  'ffa_kills_50','ffa_kills_100',
                                  'ffa_half_point_heartbreak')
       AND NOT EXISTS (SELECT 1
                         FROM ffa_match_players p
                         JOIN ffa_matches m ON m.id = p.match_id
                        WHERE p.player_id = pa.player_id
                          AND m.is_ranked);
    IF n > 0 THEN
        RAISE EXCEPTION
            'migration 196: % FFA achievement row(s) held by players with no ranked FFA match', n;
    END IF;
END $$;

COMMIT;
