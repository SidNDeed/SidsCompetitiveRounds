-- 257: revoke the Untouchable achievement from everyone, WITHOUT taking the gold.
--
-- Bug #268. Untouchable ("Win a game without taking any damage") was granted by
-- a detector that sampled a "took damage" STATE at 10Hz rather than hooking the
-- damage EVENT, so a player who went from full health to dead between two
-- samples never occupied the damaged-but-alive state the check looked for and
-- was awarded it anyway. v1.39.3 added a died-this-game guard which closes the
-- reported case; the grants already handed out remain wrong.
--
-- Owner's direction (2026-08-24): remove the achievement from everyone, let them
-- KEEP the gold, and let them re-earn it. Explicitly NOT the migration-088
-- treatment, which clawed gold back via 'achievement_revoked' rows -- these
-- players did nothing wrong and the error was ours.
--
-- Pairs with _achievement_payment_eligible, which all THREE paying grant paths
-- now consult (inline, the signed unlock endpoint, and the admin grant -- the
-- third was missed by two revisions of that fix and by a docstring that said
-- there were two). Without it, deleting these rows would make every re-earn pay the
-- 100g a second time: the only thing the grant paths consulted was the absence
-- of a PlayerAchievement row, which is exactly what this removes.
--
-- Idempotent: a re-run finds no holders, inserts no markers, deletes nothing,
-- and still passes its post-check. The deploy wrapper runs
-- `psql -f ... || psql < ...` and re-executes the whole file on any nonzero
-- exit. BEGIN/COMMIT are explicit because `psql -f` does NOT wrap a file in a
-- transaction (learning #340).

BEGIN;

-- Holders captured BEFORE the delete, with their unlock time: the delete is what
-- destroys the evidence, and the marker rule below needs the timestamp.
CREATE TEMP TABLE _untouchable_holders ON COMMIT DROP AS
SELECT player_id, MIN(unlocked_at) AS unlocked_at
FROM player_achievements
WHERE achievement_key = 'untouchable'
GROUP BY player_id;

-- 1. Prepaid markers -- ONLY with POSITIVE PROOF of payment.
--
--    Most holders have a per-key row (reason='achievement',
--    reference_id='untouchable'). A minority were paid by migration 020, which
--    booked ONE aggregate 'backfill_achievement' row per player with an EMPTY
--    reference_id, unattributable to any key.
--
--    Review find (HIGH): the first version of this marked every holder lacking a
--    per-key row as prepaid, INFERRING payment from absence. That is unsound and
--    errs toward denying money. The signed unlock endpoint deliberately records
--    an achievement WITHOUT gold when its HMAC is absent or invalid, so
--    "holds untouchable, has no per-key ledger row, was never in the 020
--    backfill" is a reachable state -- a player who was never paid. Marking them
--    prepaid would permanently deny the 100g they are actually owed when they
--    re-earn it.
--
--    So require an aggregate backfill row CREATED AFTER their unlock: that is
--    what actually proves migration 020 swept their grant. Anyone without that
--    proof is left unmarked, keeps paid=0, and is paid normally on re-earn.
--    Verified against production before writing this: all three currently
--    unattributable holders unlocked 2026-04-13/17 and carry a
--    'backfill_achievement' row dated 2026-04-18, so all three are covered.
--
--    The 0-amount row is deliberate and carries real information ("already paid
--    for this key, by a route that cannot be attributed to it"). It does not
--    disturb the gold_earned == SUM(positive amounts) invariant of migration
--    020, precisely because it is not positive.
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT h.player_id, 0, 'achievement_prepaid', 'untouchable'
FROM _untouchable_holders h
WHERE NOT EXISTS (
        SELECT 1 FROM gold_transactions gt
        WHERE gt.player_id = h.player_id
          AND gt.reference_id = 'untouchable'
          AND gt.reason IN ('achievement', 'achievement_prepaid')
  )
  AND EXISTS (
        SELECT 1 FROM gold_transactions bf
        WHERE bf.player_id = h.player_id
          AND bf.reason = 'backfill_achievement'
          AND bf.created_at > h.unlocked_at
  );

-- 2. Revoke. No gold movement of any kind.
DELETE FROM player_achievements WHERE achievement_key = 'untouchable';

-- 3. Post-checks. Both can actually fail.
DO $$
DECLARE
    remaining INT;
    holders   INT;
    marked    INT;
    unpaid    INT;
BEGIN
    SELECT COUNT(*) INTO holders FROM _untouchable_holders;

    SELECT COUNT(*) INTO remaining
      FROM player_achievements WHERE achievement_key = 'untouchable';
    IF remaining <> 0 THEN
        RAISE EXCEPTION 'untouchable still held by % row(s) after revoke', remaining;
    END IF;

    -- Informational, NOT a failure: "unpaid and therefore still owed" is a
    -- VALID outcome now (see the marker rule above). The old version raised on
    -- it, which would have forced exactly the unsound blanket-marking this
    -- migration was rewritten to avoid.
    SELECT COUNT(*) INTO marked
      FROM _untouchable_holders h
     WHERE EXISTS (SELECT 1 FROM gold_transactions gt
                   WHERE gt.player_id = h.player_id
                     AND gt.reference_id = 'untouchable'
                     AND gt.reason IN ('achievement', 'achievement_prepaid'));
    unpaid := holders - marked;

    RAISE NOTICE 'post-check OK: revoked from % holder(s); % attributable as already-paid; % left eligible for payment on re-earn; no gold moved',
                 holders, marked, unpaid;
END $$;

COMMIT;
