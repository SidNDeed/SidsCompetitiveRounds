-- 090_fix_series_win_gold_misrouting.sql
--
-- The 1v1 ranked series-completion logic in submit_match was selecting the
-- gold recipient by match-report p1/p2 ordering instead of by series's own
-- player1/player2 ordering. When the deciding match's reporter happened to
-- land in the opposite slot from how the series was originally created, the
-- bonus went to the wrong player. 62 grants between 2026-05-21 and
-- 2026-05-29 were affected (Sid x4, Stan x9, others).
--
-- Code fix landed in v1.26.8 (see comment near line 1138 of main.py).
-- This migration retroactively reverses each misrouted grant and credits
-- the actual series winner, with a paired pair of audit rows so the
-- transaction history is symmetric.

BEGIN;

CREATE TEMP TABLE _misrouted_series_gold AS
SELECT gt.id                  AS gt_id,
       gt.player_id           AS wrong_recipient_id,
       rs.winner_id           AS correct_recipient_id,
       gt.amount,
       gt.reference_id
  FROM gold_transactions gt
  JOIN ranked_series rs ON rs.id::text = gt.reference_id
 WHERE gt.reason = 'series_win'
   AND rs.winner_id IS NOT NULL
   AND rs.winner_id != gt.player_id;

-- Refund the wrong recipient (subtract the amount they shouldn't have got).
UPDATE players p
   SET gold_earned = GREATEST(0, COALESCE(p.gold_earned, 0) - m.amount)
  FROM _misrouted_series_gold m
 WHERE p.id = m.wrong_recipient_id;

-- Credit the actual winner.
UPDATE players p
   SET gold_earned = COALESCE(p.gold_earned, 0) + m.amount
  FROM _misrouted_series_gold m
 WHERE p.id = m.correct_recipient_id;

-- Audit: negative reversal row on the wrong recipient.
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT wrong_recipient_id, -amount, 'series_win_reversal', reference_id
  FROM _misrouted_series_gold;

-- Audit: corrective credit on the actual winner.
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT correct_recipient_id, amount, 'series_win_recredit', reference_id
  FROM _misrouted_series_gold;

DO $$
DECLARE n INT;
BEGIN
    SELECT COUNT(*) INTO n FROM _misrouted_series_gold;
    RAISE NOTICE 'fix_series_win_gold_misrouting: corrected % grants', n;
END $$;

DROP TABLE _misrouted_series_gold;

COMMIT;
