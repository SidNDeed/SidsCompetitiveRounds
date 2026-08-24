-- 252: backfill tournament_matches.started_at for matches already READY when
-- the Aug 23 fix landed (started_at was written nowhere before it, which left
-- the bot's async pending-match reminder structurally dead - Codex wiki-batch
-- finding, fix-batch find 2). Source of truth: the linked ranked_series row's
-- created_at (stamped at match activation); fallback deadline - 7 days (the
-- async deadline is activation + 7d; an extension skews this by at most a
-- day), last-resort NOW(). 2 rows at write time, both series-linked.
-- Idempotent (started_at IS NULL guard); explicit transaction (#340).

BEGIN;

UPDATE tournament_matches tm
   SET started_at = rs.created_at
  FROM ranked_series rs
 WHERE rs.id = tm.series_id
   AND tm.started_at IS NULL
   AND tm.status = 'ready';

UPDATE tournament_matches
   SET started_at = COALESCE(deadline_at - INTERVAL '7 days', NOW())
 WHERE started_at IS NULL
   AND status = 'ready';

DO $$
DECLARE v_left INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_left FROM tournament_matches
     WHERE status = 'ready' AND started_at IS NULL;
    IF v_left <> 0 THEN
        RAISE EXCEPTION 'post-check FAILED: % ready matches still lack started_at', v_left;
    END IF;
    RAISE NOTICE 'post-check OK: every ready match carries started_at';
END $$;

COMMIT;
