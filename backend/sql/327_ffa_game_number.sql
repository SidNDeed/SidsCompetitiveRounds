-- 327: ffa_matches.game_number -- which game of the sitting a row records
-- (2026-09-19, RJ-4).
--
-- RUN THIS BEFORE THE CODE, on the primary; the standby takes it by streaming
-- replication. Then deploy the api to the primary, then to the standby.
--
-- WHAT THE OLD CODE DOES AGAINST THIS COLUMN DURING THE WINDOW. Between this
-- file and the new api, the CURRENT api (0266237) is what answers reports. It
-- never names game_number, so its INSERT supplies no value -- and this file
-- makes the column NOT NULL, which would reject that INSERT and 500 every FFA
-- report for the length of the window. The BEFORE INSERT trigger below is
-- what stops that: it numbers any row whose writer did not, from the row's own
-- room id when that carries a usable `_rN` tail and otherwise from the lobby's
-- own sequence. So the old api keeps working, unchanged, and every row it
-- writes in the window is numbered by the same rule the backfill used. The new
-- api supplies the number itself (the lobby's games_played + 1) and the
-- trigger leaves it alone.
-- The reverse order is what does NOT work: the new api's pace anchor and
-- duplicate lookup both select on this column, and against a schema without it
-- every FFA report answers 500.
--
-- WHAT THE COLUMN IS FOR. `paid_battles` is metered against a window measured
-- from server receipt times: the anchor was `MAX(ended_at)` over every row of
-- the lobby, so ANY earlier row moved it -- including a second row recording
-- the SAME game. The one verified production instance (lobby
-- 0ea879a4-..., 2026-08-07) metered its second row against the 57-second gap
-- between the two receipts instead of the ~686-second game, and paid about a
-- tenth. The same arithmetic throttles the next legitimate game in any sitting
-- that carries such a row. Naming the game lets the anchor ask for the other
-- GAMES of the sitting rather than the other ROWS.
--
-- WHERE THE NUMBER COMES FROM, LIVE. From the LOBBY, not the report:
-- submit_ffa_match stores `ffa_lobbies.games_played + 1`, read under the lobby
-- row's FOR UPDATE and incremented once per settlement in the same
-- transaction. It is the same expression ffa_bet_place requires of every wager
-- (`expected_game`) and the live-points UPDATE carries, so a match row, its
-- wagers and its live figure name one game by construction. The report room id
-- `<photon room>_<HHmmss>_r<N>` -- built by the reporting client
-- (GameStateWatcher.cs) and covered by the report HMAC -- is a cross-check,
-- never the source, and it HAS TO AGREE: a report whose tail names a number
-- this lobby already holds is compared against that row, and a report whose
-- tail is any other number than the lobby's next slot is refused and kept for
-- review. Nothing is ever stored under a number the report did not name, so
-- for every row this api writes, game_number and the `_rN` tail are one
-- number. (Historical rows are a different matter -- see the backfill below.)
--
-- WHERE THE NUMBER COMES FROM, HISTORICALLY. The backfill below numbers EVERY
-- pre-existing row, and records in game_number_source which rule gave it its
-- number:
--   'room_tail' -- the room id's `_rN` tail, 1..999, taken as-is.
--   'sequence'  -- everything else (no tail, an unparseable one, zero, or one
--                  out of range): the lobby's rows in ended_at order, numbered
--                  above the highest tail that lobby already carries, so a
--                  sequenced row can never collide with a tail-derived one.
-- Measured against production before writing this (read-only probe,
-- 2026-09-19): 246 rows over 126 lobbies, every one of them carrying a tail in
-- 1..9, no NULL lobby_id, and exactly one (lobby, tail) pair holding two rows
-- -- the 2026-08-07 instance. So the 'sequence' arm numbers nothing today; it
-- exists because the post-check refuses to leave a NULL behind and the column
-- becomes NOT NULL.
--
-- NOT A DEDUP KEY, DELIBERATELY. The index below is NOT unique. The two rows
-- of the verified instance disagree about who won; folding them would make the
-- server pick one unreconciled account over the other, which a client-attested
-- input may not do (learning #283). Nothing here rewrites, invalidates or
-- reverses any historical row: the only writes to existing rows are the two
-- new columns' backfill.
--
-- IDEMPOTENT. Re-running is a no-op: every DDL step is IF NOT EXISTS or a
-- guarded DO block, the backfills are `WHERE game_number IS NULL`, the trigger
-- is replaced rather than added, and the post-check re-asserts what the first
-- run established. Explicit BEGIN/COMMIT because `psql -f` autocommits each
-- statement otherwise (learning #340); every bind is CAST (#275/#448).

BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS game_number SMALLINT;
ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS game_number_source VARCHAR(16);
-- The two race lengths a settlement can involve. They are equal on every
-- normally configured lobby; they differ when a client that missed the
-- score-target room property plays a real, complete game to the module
-- default. That game IS settled -- refusing it would cost an honest player the
-- whole record -- but not with the frozen target's economics: its wagers were
-- priced for the frozen race length and are refunded, and its Glicko weight
-- takes the length actually played. Recorded here so the difference is a
-- readable fact about the row rather than a log line somebody has to still
-- have. NULL on every pre-327 row: `played` is not derivable for rows whose
-- per-player tallies may have been reversed, and a guessed number in a column
-- that decides pricing is worse than an honest absence.
ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS score_target_frozen SMALLINT;
ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS score_target_played SMALLINT;

COMMENT ON COLUMN ffa_matches.game_number IS
    'Which game of the sitting this row records (1..999, NOT NULL). Live rows take the lobby''s own games_played + 1, which the report room id''s _rN tail has to equal; historical rows were backfilled by migration 327. Not unique: a second row for one game is a recorded contradiction, not a key violation.';
COMMENT ON COLUMN ffa_matches.game_number_source IS
    'How this row got its number. writer = the inserting statement supplied it (the api, which supplies the lobby''s games_played + 1). room_tail = the report room id''s _rN tail, taken by migration 327''s backfill or by the insert trigger when the writer supplied none. sequence = neither was available: the lobby''s ended_at order for the backfill, one above the lobby''s highest number for the trigger.';
COMMENT ON COLUMN ffa_matches.score_target_frozen IS
    'The lobby''s frozen first-to-N at the time this game settled (NULL before migration 327).';
COMMENT ON COLUMN ffa_matches.score_target_played IS
    'The first-to-N this game was actually played to. Differs from score_target_frozen only on an accepted config skew, whose wagers are refunded rather than paid -- in the settling transaction, so a row that differs here never has a paid wager (NULL before migration 327).';

-- The pace anchor asks one question per report: the earliest receipt of each
-- of this lobby's OTHER games. The duplicate lookup asks a second: does this
-- lobby already hold a row for the ONE number the report named. (Round 3's
-- lookup bound a set of two candidates and took the earliest row of either,
-- which is not the same question and could answer with a different game.)
CREATE INDEX IF NOT EXISTS idx_ffa_matches_lobby_game
    ON ffa_matches (lobby_id, game_number);

-- ── Insert-time derivation ────────────────────────────────────────────────
-- A function from a row to a number for every lobby that has a free number
-- inside 1..999, so NOT NULL below is survivable by any writer, including the
-- api revision that predates this column and the one that follows it. It
-- NEVER overrides a number the writer supplied.
--
-- The one input it refuses is a lobby already holding all 999 numbers, which
-- no api revision can produce (FFA_MAX_GAMES_PER_LOBBY is 40 and the endpoint
-- refuses a report once a lobby has settled that many). It is stated as a
-- bound rather than claimed away: "total" was written here in round 3 while
-- the sequence arm raised for any lobby whose HIGHEST number was 999, which
-- is a far larger input class, and that exception leaves the pre-327 api as
-- an HTTP 500 the client can only retry.
CREATE OR REPLACE FUNCTION ffa_matches_derive_game_number()
RETURNS trigger AS $fn$
DECLARE
    tail INTEGER;
BEGIN
    IF NEW.game_number IS NOT NULL THEN
        NEW.game_number_source := COALESCE(NEW.game_number_source, 'writer');
        RETURN NEW;
    END IF;
    tail := NULLIF(substring(NEW.photon_room_id FROM '_r([0-9]{1,4})$'), '')::INTEGER;
    IF tail IS NOT NULL AND tail BETWEEN 1 AND 999 THEN
        NEW.game_number := tail::SMALLINT;
        NEW.game_number_source := 'room_tail';
        RETURN NEW;
    END IF;
    SELECT COALESCE(MAX(game_number), 0) + 1 INTO tail
      FROM ffa_matches
     WHERE lobby_id IS NOT DISTINCT FROM NEW.lobby_id;
    -- One above the lobby's highest number. That is the number the pre-327 api
    -- would have reached for anyway (it increments games_played per settled
    -- report), so an unnumbered insert from it lands where the sitting was.
    -- It is NOT "the next free number", which this expression does not compute:
    -- a lobby holding 1, 2 and 999 gets 1000 here. 1000 is outside the column,
    -- and an earlier revision wrote LEAST(tail, 999), which hands back a number
    -- the lobby is already using -- a silent collision, which is worse than an
    -- insert that names its own problem.
    --
    -- So the out-of-domain case falls back to the LOWEST FREE number of this
    -- lobby instead of raising, and only a lobby with no free number at all is
    -- refused. Round 3 raised for every lobby whose highest number was 999,
    -- and that exception reaches the pre-327 api as an HTTP 500 rather than as
    -- anything it can act on. The fallback cannot collide (it excludes the
    -- numbers in use) and cannot be mistaken for an identity claim: the row
    -- carries game_number_source = 'sequence', which says the number came from
    -- neither the writer nor the room id. Unreachable in the real domain --
    -- FFA_MAX_GAMES_PER_LOBBY is 40 and the endpoint refuses a report once a
    -- lobby has settled that many -- so both arms are guards, not paths.
    IF tail > 999 THEN
        SELECT MIN(n) INTO tail
          FROM generate_series(1, 999) AS n
         WHERE NOT EXISTS (
             SELECT 1 FROM ffa_matches m
              WHERE m.lobby_id IS NOT DISTINCT FROM NEW.lobby_id
                AND m.game_number = n::SMALLINT);
    END IF;
    IF tail IS NULL THEN
        RAISE EXCEPTION
            'ffa_matches: lobby % holds every number in 1..999, so an '
            'unnumbered insert has no number left', NEW.lobby_id;
    END IF;
    NEW.game_number := tail::SMALLINT;
    NEW.game_number_source := 'sequence';
    RETURN NEW;
END
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ffa_matches_game_number ON ffa_matches;
CREATE TRIGGER trg_ffa_matches_game_number
    BEFORE INSERT ON ffa_matches
    FOR EACH ROW EXECUTE FUNCTION ffa_matches_derive_game_number();

-- ── Backfill 1: the tail, where it is usable ──────────────────────────────
UPDATE ffa_matches
   SET game_number = CAST(substring(photon_room_id FROM '_r([0-9]{1,4})$') AS SMALLINT),
       game_number_source = 'room_tail'
 WHERE game_number IS NULL
   AND photon_room_id ~ '_r[0-9]{1,4}$'
   AND CAST(substring(photon_room_id FROM '_r([0-9]{1,4})$') AS INTEGER)
       BETWEEN 1 AND 999;

-- ── Pre-check: can the sequence arm stay inside the column's domain? ──────
-- Asserted BEFORE the UPDATE so a refusal names its cause instead of arriving
-- as a CHECK violation on a row nobody can point at.
DO $$
DECLARE
    over BIGINT;
BEGIN
    SELECT COUNT(*) INTO over FROM (
        SELECT COALESCE(b.top, 0) + row_number() OVER (
                   PARTITION BY m.lobby_id ORDER BY m.ended_at, m.id) AS n
          FROM ffa_matches m
          LEFT JOIN (SELECT lobby_id, MAX(game_number) AS top
                       FROM ffa_matches
                      WHERE game_number IS NOT NULL
                      GROUP BY lobby_id) b
                 ON b.lobby_id IS NOT DISTINCT FROM m.lobby_id
         WHERE m.game_number IS NULL
    ) q WHERE q.n > 999;
    IF over > 0 THEN
        RAISE EXCEPTION
            'game_number sequence backfill would place % row(s) above 999; '
            'inspect ffa_matches for a lobby carrying an out-of-domain tail', over;
    END IF;
END $$;

-- ── Backfill 2: everything the tail could not number ──────────────────────
-- Above the lobby's highest tail-derived number, in ended_at order, so a
-- sequenced row can never take a number a tail-derived row already holds.
-- `IS NOT DISTINCT FROM` because lobby_id is nullable (ffa_lobbies deletion
-- sets it NULL): those rows share one synthetic sequence and no live report
-- can ever look them up, since the lookup keys on lobby_id = :lid.
WITH top_per_lobby AS (
    SELECT lobby_id, MAX(game_number) AS top
      FROM ffa_matches
     WHERE game_number IS NOT NULL
     GROUP BY lobby_id
),
todo AS (
    SELECT id, lobby_id,
           row_number() OVER (PARTITION BY lobby_id ORDER BY ended_at, id) AS rn
      FROM ffa_matches
     WHERE game_number IS NULL
)
UPDATE ffa_matches m
   SET game_number = CAST(COALESCE(b.top, 0) + t.rn AS SMALLINT),
       game_number_source = 'sequence'
  FROM todo t
  LEFT JOIN top_per_lobby b ON b.lobby_id IS NOT DISTINCT FROM t.lobby_id
 WHERE m.id = t.id;

-- ── Post-check ────────────────────────────────────────────────────────────
-- Three assertions, each of which a plausible mistake makes FAIL:
--   1. no row was left NULL -- a backfill whose predicate skipped rows;
--   2. no row is outside 1..999 -- a sequence arm that ran past the domain;
--   3. every row whose room id carries a usable tail took THAT tail -- a
--      backfill that ran in the wrong order and sequenced a derivable row.
-- The third is the one a count of NULLs cannot see, and it is what the
-- 'neuter the backfill's WHERE' mutation control reddens.
--
-- The third covers rows of EVERY provenance, `writer` included. An earlier
-- revision restricted it to game_number_source = 'sequence', which made it
-- blind to exactly the rows it would matter most for on a re-run; and since
-- the api refuses any report whose tail is not the number it stores, a writer
-- row whose tail disagrees with its number is a real fault and not a
-- legitimate shape. Backfilled 'sequence' rows are excluded by the predicate
-- itself: a row was sequenced only because its tail was not usable, so the
-- `photon_room_id ~ ...` test never matches one.
DO $$
DECLARE
    nulls    BIGINT;
    outside  BIGINT;
    wrong    BIGINT;
    by_tail  BIGINT;
    by_seq   BIGINT;
BEGIN
    SELECT COUNT(*) INTO nulls FROM ffa_matches WHERE game_number IS NULL;
    IF nulls > 0 THEN
        RAISE EXCEPTION 'game_number backfill left % row(s) NULL', nulls;
    END IF;
    SELECT COUNT(*) INTO outside
      FROM ffa_matches WHERE game_number NOT BETWEEN 1 AND 999;
    IF outside > 0 THEN
        RAISE EXCEPTION 'game_number backfill left % row(s) outside 1..999', outside;
    END IF;
    SELECT COUNT(*) INTO wrong
      FROM ffa_matches
     WHERE photon_room_id ~ '_r[0-9]{1,4}$'
       AND CAST(substring(photon_room_id FROM '_r([0-9]{1,4})$') AS INTEGER)
           BETWEEN 1 AND 999
       AND game_number IS DISTINCT FROM
           CAST(substring(photon_room_id FROM '_r([0-9]{1,4})$') AS SMALLINT);
    IF wrong > 0 THEN
        RAISE EXCEPTION
            'game_number: % row(s) carry a derivable _rN tail that is not their '
            'game_number (a backfill that sequenced a derivable row, or a writer '
            'that stored a number it did not name)', wrong;
    END IF;
    SELECT COUNT(*) INTO by_tail FROM ffa_matches WHERE game_number_source = 'room_tail';
    SELECT COUNT(*) INTO by_seq  FROM ffa_matches WHERE game_number_source = 'sequence';
    RAISE NOTICE 'ffa_matches.game_number: % row(s) from the room tail, % sequenced',
                 by_tail, by_seq;
END $$;

-- ── The column's own guarantees, once the data satisfies them ─────────────
ALTER TABLE ffa_matches ALTER COLUMN game_number SET NOT NULL;

-- SMALLINT is a storage width, not a bound: it accepts 32767, and the api's
-- own domain for this number is 1..999 (FFA_GAME_NUMBER_MAX). Postgres has no
-- ADD CONSTRAINT IF NOT EXISTS, hence the guard.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'ck_ffa_matches_game_number_domain'
           AND conrelid = 'ffa_matches'::regclass
    ) THEN
        ALTER TABLE ffa_matches
            ADD CONSTRAINT ck_ffa_matches_game_number_domain
            CHECK (game_number BETWEEN 1 AND 999);
    END IF;
END $$;

COMMIT;
