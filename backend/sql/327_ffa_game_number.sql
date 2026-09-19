-- 327: ffa_matches.game_number -- which game of the sitting a row records
-- (2026-09-19, RJ-4).
--
-- RUN THIS BEFORE THE CODE. The api's pace anchor selects on this column;
-- against a schema without it every FFA report answers 500. The column is
-- nullable with no default, so the CURRENT api -- which never names it --
-- keeps working unchanged against a database that already carries it. Order:
-- this file, then deploy the api to the primary, then to the standby.
--
-- WHAT THE COLUMN IS FOR. `paid_battles` is metered against a window measured
-- from server receipt times: the anchor was `MAX(ended_at)` over every row of
-- the lobby, so ANY earlier row moved it -- including a second row recording
-- the SAME game. The one verified production instance (lobby
-- 0ea879a4-..., 2026-08-07) metered its second row against the 57-second gap
-- between the two receipts instead of the ~686-second game, and paid about a
-- tenth. The same arithmetic throttles the next legitimate game in any sitting
-- that carries such a row. Naming the game makes the anchor able to ask for
-- the PREVIOUS game rather than the previous row.
--
-- WHERE THE NUMBER COMES FROM. The report room id is
-- `<photon room>_<HHmmss>_r<N>`, built by the reporting client
-- (GameStateWatcher.cs) and covered by the report HMAC; `N` is that sitting's
-- game counter. The api already parses that tail for bet settlement
-- (main._ffa_room_game_no), so nothing new is asked of any client and a
-- 1.40.3 build keeps reporting exactly as it does today -- the number is
-- derived server-side from what it already sends.
--
-- NOT A DEDUP KEY, DELIBERATELY. The index below is NOT unique and no
-- constraint is added. The two rows of the verified instance disagree about
-- who won; folding them would make the server pick one unreconciled account
-- over the other, which a client-attested input may not do (learning #283).
-- Nothing here rewrites, invalidates or reverses any historical row: the only
-- write to existing rows is the backfill of this new column.
--
-- BACKFILL DOMAIN. One to four digits, value 1..999. The column is SMALLINT,
-- the room id is free text up to 64 characters, and a tail outside that
-- domain must not become a value: a row whose tail is unparseable or out of
-- range is left NULL, and the api treats a NULL row as "some earlier game" --
-- the same thing it assumed before this column existed, so an unbackfilled
-- row meters exactly as it does today.

BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS game_number SMALLINT;

COMMENT ON COLUMN ffa_matches.game_number IS
    'Which game of the sitting this row records, from the report room id''s _rN tail (1..999). NULL = not derivable; the pace anchor then treats the row as an earlier game. Not unique: a second row for one game is a recorded contradiction, not a key violation.';

-- The pace anchor asks one question per report: the earliest receipt of each
-- game of this lobby below the one being reported.
CREATE INDEX IF NOT EXISTS idx_ffa_matches_lobby_game
    ON ffa_matches (lobby_id, game_number);

UPDATE ffa_matches
   SET game_number = CAST(substring(photon_room_id FROM '_r([0-9]{1,4})$') AS SMALLINT)
 WHERE game_number IS NULL
   AND photon_room_id ~ '_r[0-9]{1,4}$'
   AND CAST(substring(photon_room_id FROM '_r([0-9]{1,4})$') AS INTEGER)
       BETWEEN 1 AND 999;

-- Post-check. The failure this must catch is a backfill that silently skipped
-- rows it could have derived -- a check that only counted NULLs would pass on
-- a table of legacy rows that never carried the tail, and fail on a healthy
-- one, so it measures the derivable set instead. The underivable count is
-- reported, not enforced.
DO $$
DECLARE
    missed  BIGINT;
    unknown BIGINT;
    total   BIGINT;
BEGIN
    SELECT COUNT(*) INTO missed
      FROM ffa_matches
     WHERE game_number IS NULL
       AND photon_room_id ~ '_r[0-9]{1,4}$'
       AND CAST(substring(photon_room_id FROM '_r([0-9]{1,4})$') AS INTEGER)
           BETWEEN 1 AND 999;
    IF missed > 0 THEN
        RAISE EXCEPTION
            'game_number backfill left % row(s) whose room id carries a derivable _rN tail', missed;
    END IF;
    SELECT COUNT(*) INTO unknown FROM ffa_matches WHERE game_number IS NULL;
    SELECT COUNT(*) INTO total   FROM ffa_matches;
    RAISE NOTICE 'ffa_matches.game_number: % of % row(s) numbered, % left NULL (no derivable tail)',
                 total - unknown, total, unknown;
END $$;

COMMIT;
