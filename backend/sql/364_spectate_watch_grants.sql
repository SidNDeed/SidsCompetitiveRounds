-- 364: spectate_watch_grants -- the durable record that a spectator seat
-- WATCHED a spectate game (session report lane, round 3, finding N1).
--
-- The broadcast seat's session-report reads (GET /api/v1/report with viewer=
-- and GET /api/v1/broadcast/report-status) answer only for a game that seat
-- watched. Until this file they decided that from spectate_leases, and the
-- master's validation sweep (POST /api/v1/spectate/validate) DELETES a lease
-- row once its authorization has ended and the seat is no longer observed in
-- the room, so ordinary cleanup could make a watched game vanish from the
-- status list and its report answer 404.
--
-- One row per (spectate game, spectator steam id, mode, source, roster) that
-- a master validation observed: the validation route writes it whenever a
-- validation binds that spectator's lease to an actor (the lease was
-- validated as OBSERVED in the room) AND the request carried the participant
-- tuple the master read with that spectator snapshot, verified equal to the
-- live room row under the room lock (round 5 MEDIUM 1: a request whose tuple
-- differs writes nothing and is answered retry; the released clients' shape,
-- which carries no tuple, records no watch), as INSERT ... ON CONFLICT DO NOTHING,
-- so a room whose roster or source changes while the seat watches (a code
-- room where one fighter is replaced, an FFA lobby losing a member) leaves
-- one row per tuple the seat was observed under, and a repeated validation
-- adds nothing. It carries what the watched binding compares, copied from
-- the spectate game at that moment:
--   mode             the game's server-recorded mode (1v1, 2v2, 1v2, ffa)
--   source_ref       the server-derived source identity ('' = none: 1v1 queue
--                    and code rooms), compared with the requested game's
--                    series, lobby or tournament match
--   roster           the fighters' steam ids (CSV); the viewer must be in it,
--                    and where source_ref is '' it must equal the requested
--                    game's played roster exactly
--   game_started_at  the spectate game's start, the window's opening edge
-- The window's closing edge is the spectate game's ended_at (game_id
-- references it; no statement deletes spectate game rows, and this key has
-- no cascade, so the referenced row cannot go while a grant names it).
--
-- RETENTION: kept for as long as the reports it authorizes exist. The report
-- is read from the game tables (matches, team_matches, ovt_matches,
-- ffa_matches), which no sweep deletes, so no sweep deletes a grant: no
-- statement anywhere updates or deletes this table (the lease cleanup
-- touches spectate_leases only), which is what makes the record immutable.
--
-- NO BACKFILL (round 4, MEDIUM 1): a grant carries only a tuple a master
-- validation actually observed. Before this file, a validation recorded no
-- tuple at all: the lease binding (spectate_leases.bound_actor) names the
-- Photon actor and nothing else, while the spectate game row's mode, source
-- and roster are the room's LAST attestation, rewritten in place by every
-- participant attest. Copying that row onto an earlier binding would record
-- a tuple the seat may never have watched (a seat validated on roster A-B
-- would be granted the room's later A-C). No row of any table records the
-- tuple a pre-364 binding observed, so every such binding fails closed: no
-- grant is written for it, and a seat still watching revalidates going
-- forward (the master's next validation writes the grant for the tuple it
-- observes then). What that costs: the broadcast seat's report of a set
-- whose every validation ran before the api that writes grants; the seat's
-- report queue holds only its recent watches.
--
-- REQUIRES spectate_games and spectate_leases (194, 210). Written by
-- POST /api/v1/spectate/validate; read by GET /api/v1/report (viewer=, the
-- _REPORT_WATCHED_SQL statement) and GET /api/v1/broadcast/report-status.
-- Not mapped in models.py: only raw SQL names it (#674).
--
-- DEPLOY ORDER (#477): THIS FILE FIRST, as its own commit and its own deploy,
-- then the API that reads and writes it. Until this file is applied under
-- that API, its two broadcast reads fail closed (no grant, no report) and
-- /health reports session_report=0, since its probe analyses
-- _REPORT_WATCHED_SQL; what its validation route answers without the table
-- is stated at the grant write in spectate_validate (main.py). The API from
-- before this file never names the table.
--
-- Idempotent: IF NOT EXISTS only (the file writes no rows), one explicit
-- transaction (#340).

BEGIN;

CREATE TABLE IF NOT EXISTS spectate_watch_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES spectate_games(id),
    spectator_steam_id VARCHAR(32) NOT NULL,
    mode VARCHAR(8) NOT NULL,
    source_ref VARCHAR(64) NOT NULL DEFAULT '',
    roster TEXT NOT NULL DEFAULT '',
    game_started_at TIMESTAMPTZ NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_spectate_watch_grants_tuple
        UNIQUE (game_id, spectator_steam_id, mode, source_ref, roster)
);

CREATE INDEX IF NOT EXISTS idx_spectate_watch_grants_spectator
    ON spectate_watch_grants (spectator_steam_id, game_started_at);

COMMIT;
