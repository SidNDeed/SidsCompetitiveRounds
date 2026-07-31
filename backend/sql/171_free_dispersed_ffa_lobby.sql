-- 171: manual kick (Sid, July 30 evening) — free the dispersed FFA sitting
-- 2e63a0fb (SlopsOn1 + NotNic + TechTara).
--
-- Game 2 of the sitting ended 00:34Z and no game followed; the members
-- dispersed (two clients stopped polling entirely) but their ready_join rows
-- remained, so all three were locked out of every queue in every mode —
-- SlopsOn1's client was looping on the dead row ("stuck in the queue").
-- The 60-minute dispersed sweep would have freed them at ~01:34Z; this just
-- does it now. The one unsettled bet on the lobby is NOT touched here: the
-- janitor's stranded-bet sweep reconciles bets on closed lobbies (settle
-- recorded games, refund the rest) within its next tick.
--
-- Idempotent: both statements are no-ops once applied.

UPDATE ffa_lobbies
   SET status = 'completed', completed_at = NOW()
 WHERE id = '2e63a0fb-3d9d-4f5d-9daa-60768593e28e'
   AND status = 'active';

DELETE FROM ffa_queue
 WHERE series_id = '2e63a0fb-3d9d-4f5d-9daa-60768593e28e';

DO $$
BEGIN
    RAISE NOTICE 'post-check: lobby status = %, remaining queue rows = %',
        (SELECT status FROM ffa_lobbies
          WHERE id = '2e63a0fb-3d9d-4f5d-9daa-60768593e28e'),
        (SELECT COUNT(*) FROM ffa_queue
          WHERE series_id = '2e63a0fb-3d9d-4f5d-9daa-60768593e28e');
END $$;
