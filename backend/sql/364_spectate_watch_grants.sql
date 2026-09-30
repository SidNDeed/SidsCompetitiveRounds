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
-- One row per (spectate game, room generation, spectator steam id, mode,
-- source, roster) that a master validation observed (the generation since
-- round 7, below): the validation route writes it whenever a
-- validation binds that spectator's lease to an actor (the lease was
-- validated as OBSERVED in the room) AND the request carried the participant
-- tuple the master read with that spectator snapshot, verified equal to the
-- live room row under the room lock (round 5 MEDIUM 1: a request whose tuple
-- differs writes nothing and is answered retry; the released clients' shape,
-- which carries no tuple, records no watch), as INSERT ... ON CONFLICT on the
-- tuple DO UPDATE of observed_seq alone, so a room whose roster or source
-- changes while the seat watches (a code room where one fighter is replaced,
-- an FFA lobby losing a member) leaves one row per tuple the seat was
-- observed under, and a repeated validation of the same generation adds no
-- row. It carries what the watched binding compares: the game id,
-- generation, mode, source and roster the request observed, each compared
-- equal to the live room row before the write and written from the request
-- (round 6 MEDIUM 1; the generation since round 7), and the game's start by
-- that game id:
--   generation       the room row's generation the request observed and the
--                    server compared (round 7 MEDIUM 1); a room that returns
--                    to an earlier tuple is a new generation, so a new row
--   mode             the game's server-recorded mode (1v1, 2v2, 1v2, ffa)
--   source_ref       the server-derived source identity ('' = none: 1v1 queue
--                    and code rooms), compared with the requested game's
--                    series, lobby or tournament match
--   roster           the fighters' steam ids (CSV); the viewer must be in it,
--                    and where source_ref is '' it must equal the requested
--                    game's played roster exactly
--   game_started_at  the spectate game's start, the window's opening edge
-- and, for report-status alone (round 5 LOW 1), the ORDER of observation:
--   observed_seq     a value of spectate_watch_grants_observed_seq drawn by
--                    the validation route for every validation that observes
--                    the seat under this tuple - on the first (the insert)
--                    and on every repeat (the conflict refreshes it) - while
--                    that request holds the room's advisory lock, which it
--                    keeps until it commits. Two validations of one room
--                    therefore draw in the order they hold the lock, and a
--                    sequence value is never reused, so the row with the
--                    greatest observed_seq of a (game, seat) is the tuple of
--                    the MOST RECENT successful validation, including when the
--                    room returns to a tuple seen before (since round 7 that
--                    return is a new generation, so its row is a new one with
--                    a later value). granted_at (the
--                    transaction's start, NOW()) and id (random) order
--                    nothing. CACHE 1 (the default, written out): a cache per
--                    session would hand out values out of call order.
-- The window's closing edge is the spectate game's ended_at (game_id
-- references it; no statement deletes spectate game rows, and this key has
-- no cascade, so the referenced row cannot go while a grant names it).
--
-- RETENTION: kept for as long as the reports it authorizes exist. The report
-- is read from the game tables (matches, team_matches, ovt_matches,
-- ffa_matches), which no sweep deletes, so no sweep deletes a grant: no
-- statement anywhere deletes from this table (the lease cleanup touches
-- spectate_leases only), and the one statement that changes a row (the
-- validation's conflict clause) sets observed_seq and nothing else, which is
-- what keeps the recorded tuple immutable.
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
-- THE ROOM ROW'S GENERATION (round 7 MEDIUM 1). Comparing field values
-- against a row that participant attests rewrite in place cannot tell a row
-- that stayed on source X from one that went X, Y and back to X, so this file
-- also gives spectate_games a generation that only increases:
--   spectate_games.generation  a value of spectate_games_generation_seq,
--                    drawn by the BEFORE trigger below on every INSERT and on
--                    every UPDATE that changes any room value a grant carries
--                    (id, mode, source_ref, roster: the spectate_games columns
--                    of main._SPECTATE_GRANT_OBSERVED_TUPLE other than
--                    generation itself); every other UPDATE keeps the old
--                    value. The trigger owns the column: a value an INSERT or
--                    UPDATE supplies for it is replaced, so no statement that
--                    fires the trigger can set it back (a session that turns
--                    triggers off, e.g. a restore with triggers disabled, is
--                    outside this and is not an api path).
--                    A sequence value is never reused, so a row that returns
--                    to an earlier tuple carries a generation it never had.
-- The participant attest answers the generation of the row it wrote; the
-- master echoes it in its validation beside the tuple, and the validation
-- grants a watch only when the generation AND every tuple value equal the
-- live row's under the room lock. A grant records the generation it was
-- issued for (spectate_watch_grants.generation, part of its unique tuple).
-- Existing rows take distinct values from the column default when it is
-- added; a re-run adds nothing (IF NOT EXISTS, CREATE OR REPLACE).
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
-- Idempotent: IF NOT EXISTS / CREATE OR REPLACE only (the file inserts,
-- updates and deletes no rows; adding the generation column fills it on the
-- existing spectate game rows from its default), one explicit transaction
-- (#340).

BEGIN;

CREATE SEQUENCE IF NOT EXISTS spectate_watch_grants_observed_seq AS BIGINT CACHE 1;

CREATE SEQUENCE IF NOT EXISTS spectate_games_generation_seq AS BIGINT CACHE 1;

ALTER TABLE spectate_games
    ADD COLUMN IF NOT EXISTS generation BIGINT NOT NULL DEFAULT nextval('spectate_games_generation_seq');

CREATE OR REPLACE FUNCTION spectate_games_generation_advance() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.generation := nextval('spectate_games_generation_seq');
    ELSIF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.mode IS DISTINCT FROM OLD.mode
       OR NEW.source_ref IS DISTINCT FROM OLD.source_ref
       OR NEW.roster IS DISTINCT FROM OLD.roster THEN
        NEW.generation := nextval('spectate_games_generation_seq');
    ELSE
        NEW.generation := OLD.generation;
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE TRIGGER trg_spectate_games_generation
    BEFORE INSERT OR UPDATE ON spectate_games
    FOR EACH ROW EXECUTE FUNCTION spectate_games_generation_advance();

CREATE TABLE IF NOT EXISTS spectate_watch_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES spectate_games(id),
    generation BIGINT NOT NULL,
    spectator_steam_id VARCHAR(32) NOT NULL,
    mode VARCHAR(8) NOT NULL,
    source_ref VARCHAR(64) NOT NULL DEFAULT '',
    roster TEXT NOT NULL DEFAULT '',
    game_started_at TIMESTAMPTZ NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    observed_seq BIGINT NOT NULL DEFAULT nextval('spectate_watch_grants_observed_seq'),
    CONSTRAINT uq_spectate_watch_grants_tuple
        UNIQUE (game_id, generation, spectator_steam_id, mode, source_ref, roster)
);

CREATE INDEX IF NOT EXISTS idx_spectate_watch_grants_spectator
    ON spectate_watch_grants (spectator_steam_id, game_started_at);

COMMIT;
