-- 173: free every FFA ready_join row stranded by the broken leave endpoint.
--
-- ROOT CAUSE (fixed in the same pass, main.py ffa_queue_leave): both
-- "UPDATE ffa_lobbies SET departed_ids = ... unnest(departed_ids || :pid) ..."
-- statements bound a scalar UUID into an array-concat whose parameter Postgres
-- types as uuid[]. asyncpg raised DataError, the transaction aborted, and the
-- endpoint's trailing "DELETE FROM ffa_queue WHERE player_id = :pid" never ran.
-- Every leave from a locked FFA lobby returned HTTP 500 from v1.35.0 through
-- v1.35.4 (34/34 leave requests in one prod nginx window were 500s), so the
-- caller kept a ready_join row -- which _locked_in_other_queue reads as
-- "mid-match" and which therefore locks them out of EVERY queue in EVERY mode.
--
-- Migrations 165 and 171 hand-swept single lobbies for this same symptom
-- without the cause being known. This one is PREDICATE-based so it clears
-- whatever is stranded at apply time, and is a no-op when nothing is.
--
-- Deliberately conservative -- it must never touch a live sitting:
--   * lobby still 'active', and its newest game (or its creation, for a lobby
--     that never reported one) is older than 20 minutes;
--   * NO member has been seen in 15 minutes. players.last_seen is throttled to
--     one write per 5 minutes per player, so 15 is comfortably past "online
--     but between stamps" -- it means the mod is not running;
--   * the lobby carries at least one ready_join row (this migration only ever
--     does what its name says; husk lobbies are the janitor's business);
--   * the lobby has NO unsettled bets. This migration moves no money. A lobby
--     with open wagers is skipped and reported so the janitor's stranded-bet
--     reconciliation (settle against recorded games, refund the rest) owns it.
--
-- Idempotent: once a lobby is 'completed' it no longer matches, and the queue
-- rows are gone. Safe to re-run -- which matters, because the deploy wrapper's
-- migrate verb runs "psql -f ... || psql < ..." and re-executes the whole file
-- when the first arm misses.

WITH targets AS (
    SELECT l.id
      FROM ffa_lobbies l
     WHERE l.status = 'active'
       AND COALESCE(
             (SELECT MAX(m.ended_at) FROM ffa_matches m WHERE m.lobby_id = l.id),
             l.created_at
           ) < NOW() - INTERVAL '20 minutes'
       AND EXISTS (
             SELECT 1 FROM ffa_queue q
              WHERE q.series_id = l.id AND q.status = 'ready_join')
       AND NOT EXISTS (
             SELECT 1 FROM ffa_queue q
               JOIN players p ON p.id = q.player_id
              WHERE q.series_id = l.id
                AND p.last_seen > NOW() - INTERVAL '15 minutes')
       AND NOT EXISTS (
             SELECT 1 FROM ffa_bets b
              WHERE b.lobby_id = l.id AND b.settled_at IS NULL)
), closed AS (
    UPDATE ffa_lobbies
       SET status = 'completed', completed_at = NOW()
     WHERE id IN (SELECT id FROM targets)
       AND status = 'active'
    RETURNING id
), freed AS (
    -- Every member row, not just ready_join: a lobby being closed here has no
    -- valid queue row of any status left behind it.
    DELETE FROM ffa_queue
     WHERE series_id IN (SELECT id FROM targets)
    RETURNING steam_id, display_name, status
)
SELECT (SELECT COUNT(*) FROM closed) AS lobbies_closed,
       (SELECT COUNT(*) FROM freed)  AS rows_freed,
       (SELECT COALESCE(string_agg(display_name || ' (' || steam_id || ')', ', '), '-')
          FROM freed)                AS players_freed;

DO $$
DECLARE
    v_remaining  int;
    v_skipped    int;
    v_bet_locked int;
BEGIN
    SELECT COUNT(*) INTO v_remaining
      FROM ffa_queue q JOIN ffa_lobbies l ON l.id = q.series_id
     WHERE q.status = 'ready_join' AND l.status = 'active';

    -- Anything still held is held DELIBERATELY by one of the guards above.
    -- Report why, so a leftover row is never mistaken for a failed migration.
    SELECT COUNT(*) INTO v_bet_locked
      FROM ffa_lobbies l
     WHERE l.status = 'active'
       AND EXISTS (SELECT 1 FROM ffa_queue q
                    WHERE q.series_id = l.id AND q.status = 'ready_join')
       AND EXISTS (SELECT 1 FROM ffa_bets b
                    WHERE b.lobby_id = l.id AND b.settled_at IS NULL);

    SELECT COUNT(*) INTO v_skipped
      FROM ffa_lobbies l
     WHERE l.status = 'active'
       AND EXISTS (SELECT 1 FROM ffa_queue q
                    WHERE q.series_id = l.id AND q.status = 'ready_join')
       AND (COALESCE((SELECT MAX(m.ended_at) FROM ffa_matches m WHERE m.lobby_id = l.id),
                     l.created_at) >= NOW() - INTERVAL '20 minutes'
            OR EXISTS (SELECT 1 FROM ffa_queue q
                         JOIN players p ON p.id = q.player_id
                        WHERE q.series_id = l.id
                          AND p.last_seen > NOW() - INTERVAL '15 minutes'));

    RAISE NOTICE 'post-check: % ready_join row(s) still on an active lobby '
                 '(% held as possibly-live, % held by unsettled bets)',
                 v_remaining, v_skipped, v_bet_locked;
    IF v_remaining = 0 THEN
        RAISE NOTICE 'post-check OK: no stranded FFA ready_join rows remain';
    END IF;
END $$;
