-- 165_free_stuck_ffa_ready_join.sql
-- INCIDENT: four players stuck at ffa_queue.status='ready_join' for 38 minutes.
-- A ready_join row makes _locked_in_other_queue treat them as mid-match, so they
-- could not join ANY queue in ANY mode - the "stuck in the queue" report.
--
-- What happened (from the API log + in-game chat): the lobby played one game,
-- then the group agreed to "reset to add spirit in" and everyone left the room
-- to re-form. Leaving the ROOM does not leave the QUEUE, and the client stops
-- polling once it is at ready_join, so the sitting-over self-heal - which
-- requires EVERY member to be actively polling - can never fire for them. The
-- rows then sit until the 30-minute husk prune.
--
-- Also closes a second lobby abandoned ~2h ago with 6 games recorded and no
-- queue rows left pointing at it.
--
-- Idempotent: every statement is predicated on the state it is correcting, so a
-- rerun matches nothing.

-- Close lobbies whose sitting is plainly over: last game more than 20 minutes
-- ago (or none at all and locked more than 20 minutes ago).
UPDATE ffa_lobbies l
   SET status = 'completed', completed_at = NOW()
 WHERE l.status = 'active'
   AND COALESCE(
         (SELECT MAX(m.ended_at) FROM ffa_matches m WHERE m.lobby_id = l.id),
         l.created_at
       ) < NOW() - INTERVAL '20 minutes';

-- Free every queue row that points at a lobby which is no longer active. These
-- players requeue fresh; the roster was frozen at lock, so a partial group can
-- never reach N again in that room anyway.
DELETE FROM ffa_queue q
 WHERE q.status <> 'searching'
   AND (q.series_id IS NULL
        OR EXISTS (SELECT 1 FROM ffa_lobbies l
                    WHERE l.id = q.series_id AND l.status <> 'active'));

DO $$
DECLARE v_left int; v_lob int;
BEGIN
    SELECT COUNT(*) INTO v_left FROM ffa_queue WHERE status <> 'searching';
    SELECT COUNT(*) INTO v_lob  FROM ffa_lobbies WHERE status = 'active';
    RAISE NOTICE '165: % non-searching ffa_queue row(s) remain, % active lobbies', v_left, v_lob;
END $$;
