-- 161: one-off (July 28 ~23:20 UTC) — dissolve FFA lobby 74f2a3de, whose
-- sitting ended after 2 recorded games but left Spirit/youmonster/SlopsOn1
-- ready_join-bound: their polls kept returning the dead room, so their
-- clients looped on a lobby that could never restart. Close the lobby as
-- completed (its 2 games are real) and free the rows; the clients' next
-- poll returns not_in_queue and menu-side recovery requeues them fresh.
-- Idempotent: status-guarded UPDATE + targeted DELETE.

BEGIN;

UPDATE ffa_lobbies
   SET status = 'completed', completed_at = NOW()
 WHERE id = '74f2a3de-0154-4375-ae7b-b17ecd10f2a3'
   AND status = 'active';

DELETE FROM ffa_queue
 WHERE series_id = '74f2a3de-0154-4375-ae7b-b17ecd10f2a3';

COMMIT;
