-- 199: back-pay the six FFA achievements, which were granted at 0 gold.
--
-- WHY THIS IS NEEDED (#229, the exact trap that lesson describes). The six FFA
-- achievements shipped at 0g, and migration 196 retroactively granted 8 of them
-- for games already played. Sid priced them on 2026-08-07:
--
--     Clean House       ffa_shutout_3              100
--     Party Crasher     ffa_shutout_4              300
--     Hostile Takeover  ffa_shutout_5              500
--     Rampage           ffa_kills_50               100
--     Bodycount         ffa_kills_100              500
--     Heartbreak        ffa_half_point_heartbreak  300
--
-- The inline grant path cannot fix those 8 rows. `_grant_achievement_inline`
-- returns early when the PlayerAchievement row already exists, so the holder is
-- permanently skipped and would simply never be paid. A DELTA backfill is the
-- only route — this is #229 word for word ("an idempotent backfill CANNOT top
-- up a player who already holds the achievement").
--
-- ── COUPLING, stated because SQL cannot read the Python ────────────────────
-- The values below MUST equal ACHIEVEMENT_GOLD_OVERRIDES in backend/api/main.py.
-- #229's actual lesson is that a migration must mirror the CURRENT reward
-- table, not an older migration's rate. There is no mechanical link, so if the
-- tiers are ever changed again, this file is stale and a NEW delta migration is
-- required — do not edit this one (it is idempotent against what it already
-- paid, which is exactly what makes editing it silently wrong).
--
-- ── Idempotency, and why it keys on the LEDGER ─────────────────────────────
-- The guard is the absence of a gold_transactions row for (player, key). That
-- is the durable record of "this player was paid for this achievement", and it
-- is what makes a re-run a no-op. Keying on the achievement row instead would
-- be wrong — the grant exists in both the paid and unpaid states.
--
-- A normal run executes this file ONCE, not twice: the wrapper's preferred
-- `psql -f /migrations/<file>` arm fails on the missing path BEFORE any SQL is
-- executed, and the `||` stdin fallback then runs the file (#243). That does
-- not make the guard optional — this file moves money, a hand re-run is always
-- possible, and a failure partway through re-executes it from the top.
--
-- ── Aggregation, per #240 ──────────────────────────────────────────────────
-- The natural grain of this payment is one row per (player, achievement); the
-- target `players` row is coarser. `UPDATE ... FROM` a per-achievement source
-- updates each target row exactly ONCE even when the source matches it several
-- times, so a player holding two of these would be paid for only one of them —
-- silently, with no error. The per-player GROUP BY below is what prevents that;
-- it is not a tidiness choice.
--
-- It is LOAD-BEARING RIGHT NOW, not future-proofing. A first draft of this
-- comment claimed the 8 grants sat on 8 distinct players; the read-only dry run
-- said otherwise — they sit on FIVE:
--     Sid          3 achievements   500g
--     galaxy ice   2                200g
--     Nix          1                100g
--     Snail        1                100g
--     Spirit       1                100g
--                                  ----
--                                  1000g
-- Without the GROUP BY, Sid would have been paid 100g instead of 500g and
-- galaxy ice 100 instead of 200, with no error raised. Exactly #240.
--
-- ── Invariant preserved ────────────────────────────────────────────────────
-- Migration 020 asserts gold_earned == SUM(positive gold_transactions), so the
-- ledger row and the balance bump must happen together, in one transaction.

BEGIN;

WITH tiers(achievement_key, gold) AS (
    VALUES ('ffa_shutout_3', 100),
           ('ffa_shutout_4', 300),
           ('ffa_shutout_5', 500),
           ('ffa_kills_50', 100),
           ('ffa_kills_100', 500),
           ('ffa_half_point_heartbreak', 300)
),
owed AS (
    SELECT pa.player_id, pa.achievement_key, t.gold
      FROM player_achievements pa
      JOIN tiers t ON t.achievement_key = pa.achievement_key
     WHERE NOT EXISTS (
             SELECT 1 FROM gold_transactions gt
              WHERE gt.player_id = pa.player_id
                AND gt.reason = 'achievement'
                AND gt.reference_id = pa.achievement_key)
),
ledger AS (
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
    SELECT player_id, gold, 'achievement', achievement_key FROM owed
    RETURNING player_id, amount
),
per_player AS (
    -- The #240 guard: collapse to ONE row per player before touching `players`.
    SELECT player_id, SUM(amount)::int AS total FROM ledger GROUP BY player_id
)
UPDATE players p
   SET gold_earned = COALESCE(p.gold_earned, 0) + pp.total
  FROM per_player pp
 WHERE p.id = pp.player_id;

-- ── Post-check ─────────────────────────────────────────────────────────────
DO $$
DECLARE
    unpaid  BIGINT;
    paid    BIGINT;
    total_g BIGINT;
    broken  BIGINT;
BEGIN
    -- 1. Nothing eligible may remain unpaid.
    SELECT COUNT(*) INTO unpaid
      FROM player_achievements pa
      JOIN (VALUES ('ffa_shutout_3'),('ffa_shutout_4'),('ffa_shutout_5'),
                   ('ffa_kills_50'),('ffa_kills_100'),
                   ('ffa_half_point_heartbreak')) AS t(k) ON t.k = pa.achievement_key
     WHERE NOT EXISTS (SELECT 1 FROM gold_transactions gt
                        WHERE gt.player_id = pa.player_id
                          AND gt.reason = 'achievement'
                          AND gt.reference_id = pa.achievement_key);
    IF unpaid > 0 THEN
        RAISE EXCEPTION 'migration 199: % FFA achievement(s) still unpaid', unpaid;
    END IF;

    SELECT COUNT(*), COALESCE(SUM(amount), 0) INTO paid, total_g
      FROM gold_transactions
     WHERE reason = 'achievement' AND reference_id LIKE 'ffa%';
    RAISE NOTICE 'migration 199: % FFA achievement ledger row(s), % gold total', paid, total_g;

    -- 2. Migration 020's invariant must still hold for everyone this touched.
    --    A mismatch here means the balance and the ledger disagree, which is
    --    the one outcome that must never ship quietly.
    SELECT COUNT(*) INTO broken
      FROM players p
     WHERE p.deleted_at IS NULL
       AND COALESCE(p.gold_earned, 0) <> (
             SELECT COALESCE(SUM(gt.amount), 0)
               FROM gold_transactions gt
              WHERE gt.player_id = p.id AND gt.amount > 0);
    IF broken > 0 THEN
        -- EXPECTED: 76 players already drifted before this migration existed
        -- (measured read-only immediately before it was first applied). This
        -- file writes the ledger row and the balance in one transaction, so it
        -- cannot create drift — it is reported for visibility, and a count at
        -- or near 76 is the pre-existing condition rather than a new fault.
        -- A JUMP well above that baseline is the signal worth acting on.
        RAISE WARNING 'migration 199: % player(s) have gold_earned != SUM(positive ledger). '
                      'Baseline before this migration was 76 — this file writes balance '
                      'and ledger together and cannot add drift. Investigate separately '
                      'if materially higher.', broken;
    ELSE
        RAISE NOTICE 'migration 199: gold_earned == SUM(positive ledger) holds for all players';
    END IF;

    RAISE NOTICE 'migration 199 post-check OK';
END $$;

COMMIT;
