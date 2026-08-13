-- 218: per-GAME identity on casual DC events.
--
-- WHY. "Rage Quit %" (get_player_stats) needs to know whether the game the
-- opponent abandoned produced a match row, because the denominator is the UNION
-- of casual games the reporter took part in: recorded matches PLUS DC events
-- whose own game was never recorded. Until now the only identifier on the event
-- was room_id — the raw Photon room name — and a room hosts a whole SITTING
-- (production has one room with 7 recorded matches). Room granularity cannot
-- answer a per-game question, so the query leaned on an ordering heuristic
-- ("a match for this room that ended at or after the leave"), which is exact
-- for the DC-decided report and wrong in two directions otherwise. See the long
-- note at the query in main.py.
--
-- WHAT. game_room_id is the first two segments of the client's own report id:
--   matches.photon_room_id = BuildReportRoomId() = "{room}_{token}_r{rounds}"
--   casual_dc_events.game_room_id                = "{room}_{token}"
-- The "_r{rounds}" suffix is DELIBERATELY excluded and must never be added: it
-- is the round total at REPORT time, and the DC-decided path advances the
-- survivor to the terminal score before reporting (#179), so the suffix the
-- leave sees and the suffix the report writes differ by construction. Verified
-- against production: event 19 fired at a 4-0 leave and its match row landed 4s
-- later as "..._211428_r5" — matching on "..._211428_" succeeds, matching on the
-- full leave-time id would have failed and double-counted the game.
--
-- VARCHAR(64) matches matches.photon_room_id exactly; the game key is a strict
-- prefix of the report id, so anything that fits there fits here.
--
-- NULLABLE ON PURPOSE. Old clients send no game id, and every row that exists
-- today has none. NULL selects the legacy room-prefix path in the query, so this
-- migration changes no number on its own — it only lets newer clients be exact.
-- Nothing backfills it: the token is client-side per-game state that was never
-- transmitted, so it cannot be reconstructed for a historical row.
--
-- No index: the column is only ever read through the correlated NOT EXISTS for
-- a single reporter's own events, never filtered or joined on.
--
-- There is no ORM model for casual_dc_events (the endpoint uses raw SQL), so
-- models.py needs no companion Column — checked, not assumed (#346).

BEGIN;

ALTER TABLE casual_dc_events
    ADD COLUMN IF NOT EXISTS game_room_id VARCHAR(64);

COMMENT ON COLUMN casual_dc_events.game_room_id IS 'Per-game key "{photon_room}_{game_token}" = matches.photon_room_id minus its _r{rounds} suffix. NULL for clients that predate the field; those fall back to the room-prefix + ordering path in get_player_stats.';

-- Post-check. Idempotent and safe to rerun: the wrapper re-executes the whole
-- file on a nonzero exit (#243), and every statement above tolerates that.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'casual_dc_events'
           AND column_name = 'game_room_id'
    ) THEN
        RAISE EXCEPTION '218: casual_dc_events.game_room_id missing after ALTER';
    END IF;
    RAISE NOTICE '218: post-check OK (casual_dc_events.game_room_id present)';
END $$;

COMMIT;
