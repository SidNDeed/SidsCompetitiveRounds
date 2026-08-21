-- 231_grant_notnic_gold.sql
-- One-shot 20,000g grant to NotNic (76561199311926326), per Sid's request: he
-- is recording a promo video for the mod and wants trails to show off.
--
-- Shape follows 067 (the lopidav grant -- the only prior admin_grant), but adds
-- the three guards that file predates. They matter because this file moves
-- money and the deploy wrapper can execute it more than once: the preferred
-- `psql -f /migrations/<file>` arm fails on the missing path and the `||`
-- stdin fallback then runs the file, and ANY nonzero exit re-runs it from the
-- top (#243).
--
--  * BEGIN/COMMIT. `psql -f` does NOT wrap a file in a transaction (#340), so
--    without this an error between the ledger insert and the counter update
--    would commit one half and leave the two permanently disagreeing.
--  * Ledger-keyed idempotency. The guard is the absence of the
--    ('admin_grant','notnic_20k') row -- the durable record of "already paid".
--    A re-run inserts nothing, and because the UPDATE is driven BY the insert's
--    RETURNING, the counter cannot move a second time either. This covers the
--    sequential re-run above, which is the reachable failure mode for a
--    hand-applied one-shot; the row lock below covers a concurrent live write.
--  * An atomic delta (gold_earned + 20000), never an absolute write (#326).
--
-- Balance is derived as gold_earned - gold_spent, so the grant must write BOTH
-- the ledger row and the counter -- either one alone is a silent drift.
--
-- NOT asserted here: the 020 "gold_earned = SUM(positive gold_transactions)"
-- invariant. It does not hold for this player TODAY (gold_earned 6865 against
-- 8399 of positive rows) and that is BY DESIGN, not damage -- a refund writes a
-- positive ledger row but applies as `gold_spent -= x` (#241), and he holds
-- 1500g of refund_abandoned + ffa_bet_refund. Asserting it would abort a
-- correct grant on a pre-existing, deliberate condition. The post-check
-- therefore asserts only what THIS file owns: exactly one grant row, and
-- exactly +20,000 on the counter.

BEGIN;

WITH target AS (
    -- FOR NO KEY UPDATE, not FOR UPDATE: this is an ordering/serialisation
    -- lock, and FOR UPDATE is the one mode that conflicts with the FOR KEY
    -- SHARE every FK insert takes on the referenced row -- including the
    -- gold_transactions insert immediately below (#202). Weakest mode that
    -- still conflicts with our own later write.
    SELECT id FROM players
    WHERE steam_id = '76561199311926326'
      AND deleted_at IS NULL
    FOR NO KEY UPDATE
), paid AS (
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
    SELECT t.id, 20000, 'admin_grant', 'notnic_20k'
    FROM target t
    WHERE NOT EXISTS (
        SELECT 1 FROM gold_transactions g
        WHERE g.player_id = t.id
          AND g.reason = 'admin_grant'
          AND g.reference_id = 'notnic_20k'
    )
    RETURNING player_id
)
UPDATE players p
SET gold_earned = COALESCE(p.gold_earned, 0) + 20000
FROM paid
WHERE p.id = paid.player_id;

DO $$
DECLARE
    n_rows   INTEGER;
    n_amount INTEGER;
    bal      INTEGER;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(g.amount), 0)
      INTO n_rows, n_amount
      FROM gold_transactions g
      JOIN players p ON p.id = g.player_id
     WHERE p.steam_id = '76561199311926326'
       AND g.reason = 'admin_grant'
       AND g.reference_id = 'notnic_20k';

    -- Loud abort rather than silent partial work (#183). A missing/deleted
    -- player lands here as 0 rows, which is exactly the case worth failing on.
    IF n_rows <> 1 OR n_amount <> 20000 THEN
        RAISE EXCEPTION 'post-check FAILED: expected exactly one 20000g grant row, got % row(s) totalling %g', n_rows, n_amount;
    END IF;

    SELECT COALESCE(gold_earned, 0) - COALESCE(gold_spent, 0)
      INTO bal
      FROM players WHERE steam_id = '76561199311926326';

    RAISE NOTICE 'post-check OK: NotNic admin_grant 20000g present; spendable balance now %g', bal;
END $$;

COMMIT;
