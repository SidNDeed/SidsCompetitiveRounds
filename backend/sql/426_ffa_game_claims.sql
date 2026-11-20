-- 426_ffa_game_claims.sql
-- One claim per FFA game that an admin applied or credited from a held
-- report (QAPPLY-1). A game is named by its lobby and its game number; the
-- primary key makes a second claim of one game impossible, whatever number
-- of held rows describe that game.
--
-- The api's held-report Accept writes a row of kind 'accept' in the game's
-- own transaction; Credit writes a row of kind 'credit' before it pays. Both
-- read the table under the lobby's row lock and refuse a game that holds a
-- row; the insert itself is ON CONFLICT DO NOTHING and the api refuses when
-- it returns nothing, so the key refuses a second claim even where a read
-- was skipped. quarantine_id is the held row the claim was made from.
--
-- THE SEED. A game paid from a held row before this table existed has no
-- claim of its own (migration 421 credited two such games). In the same
-- transaction, after the table exists, the seed covers every held row with
-- mode 'ffa' and status 'credited', and writes for each one claim of kind
-- 'credit': lobby_id = the row's group_id, game_number = the number its room
-- names, quarantine_id = the row's id; ON CONFLICT DO NOTHING.
--
-- THE STRICT RULE. A room names a game here exactly when it ends with _r,
-- then one or more ASCII digits 0-9, then at most one final newline, and the
-- number is 1 to 999 (FFA_GAME_NUMBER_MAX). On every such name the api's
-- reader (_ffa_named_game_number) gives the same number. The api's reader is
-- WIDER: it also reads decimal digits of other scripts. No equality is
-- claimed beyond the strict names.
--
-- ANY COVERED ROW OUTSIDE THE STRICT RULE REFUSES THE WHOLE FILE: a covered
-- row with no group_id, or whose room has no tail, a tail of 0 or above 999,
-- or a tail the strict rule cannot read (a letter, a digit of another
-- script, anything malformed) makes the file RAISE with nothing applied,
-- naming the row's id and which case it is as far as SQL can tell. A person
-- must look at that row: which game of which lobby it paid.
--
-- States: no covered row (every test database): a NOTICE, nothing seeded;
-- every covered row read by the strict rule, at most one per game: one claim
-- per game seeded, a NOTICE; two covered rows of one game with different
-- ids: RAISE, nothing applied (a game is paid once; look at both).
-- The held table is locked SHARE for the reading and the seed, so no row is
-- credited between the two.
--
-- The seed's reading is the SELECT between the SEED SELECT markers below.
-- The same text stands alone in backend/tests/qapply_seed_select.sql, to be
-- read before the deploy (a test holds the two equal). Per covered row it
-- prints the id, the room, the strict number or NULL, and seed or refuse.
--
-- A RERUN: the table is IF NOT EXISTS and each claim ON CONFLICT DO NOTHING,
-- so a second run changes nothing when no held row was credited in between.
-- A held row that some file credited in between without a claim is seeded by
-- the next run.
--
-- FOR WHOEVER WRITES A LATER MIGRATION: a file numbered above 426 that sets a
-- held row to 'credited' writes that game's ffa_game_claims row in the same
-- file (test_qapply_pg.py holds this over backend/sql).
--
-- DEPLOY ORDER: this file first, then the api (the api of this lane writes
-- the table on every Accept and Credit of a held report; the api before it
-- never names the table).

BEGIN;

CREATE TABLE IF NOT EXISTS ffa_game_claims (
    lobby_id UUID NOT NULL,
    game_number SMALLINT NOT NULL,
    kind TEXT NOT NULL,
    quarantine_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_ffa_game_claims PRIMARY KEY (lobby_id, game_number),
    CONSTRAINT ck_ffa_game_claims_kind CHECK (kind IN ('accept', 'credit')),
    CONSTRAINT ck_ffa_game_claims_game CHECK (game_number BETWEEN 1 AND 999)
);

DO $$
DECLARE
  r record;
  n_rows int8 := 0;
  n_new int8 := 0;
  n_dup int8 := 0;
  why text;
  lobbies uuid[] := '{}';
  games int4[] := '{}';
  qids uuid[] := '{}';
BEGIN
  LOCK TABLE match_report_quarantine IN SHARE MODE;
  FOR r IN
    -- SEED SELECT BEGIN
    SELECT q.id AS quarantine_id,
           q.photon_room_id AS room,
           q.group_id AS lobby_id,
           CASE WHEN CAST(substring(q.photon_room_id FROM '_r([0-9]+)\n?$') AS numeric) BETWEEN 1 AND 999
                THEN CAST(CAST(substring(q.photon_room_id FROM '_r([0-9]+)\n?$') AS numeric) AS int4)
           END AS game_number,
           CASE WHEN q.group_id IS NOT NULL
                 AND CAST(substring(q.photon_room_id FROM '_r([0-9]+)\n?$') AS numeric) BETWEEN 1 AND 999
                THEN 'seed' ELSE 'refuse'
           END AS decision
      FROM match_report_quarantine q
     WHERE q.mode = 'ffa' AND q.status = 'credited'
     ORDER BY q.group_id, q.id
    -- SEED SELECT END
  LOOP
    n_rows := n_rows + 1;
    IF r.decision <> 'seed' THEN
      why := CASE
        WHEN r.lobby_id IS NULL THEN 'no lobby (group_id is NULL)'
        WHEN substring(r.room FROM '_r([0-9]+)\n?$') IS NOT NULL THEN 'a tail out of range (1 to 999)'
        WHEN r.room ~ '_r[^_]*$' THEN 'a tail the strict rule cannot read'
        ELSE 'no tail' END;
      RAISE EXCEPTION '426: credited FFA held report % has %; nothing applied. A person must look at this row: which game of which lobby it paid', r.quarantine_id, why;
    END IF;
    lobbies := lobbies || r.lobby_id;
    games := games || r.game_number;
    qids := qids || r.quarantine_id;
  END LOOP;

  IF n_rows = 0 THEN
    RAISE NOTICE '426: no credited FFA held report; no claim seeded';
    RETURN;
  END IF;
  SELECT count(*) INTO n_dup FROM (
    SELECT t.l, t.g FROM unnest(lobbies, games, qids) AS t(l, g, q)
     GROUP BY t.l, t.g HAVING count(DISTINCT t.q) > 1) d;
  IF n_dup > 0 THEN
    RAISE EXCEPTION '426: % game(s) were credited from two or more held reports; nothing applied. A person must look at the credited FFA held rows of each such game: a game is paid once', n_dup;
  END IF;

  INSERT INTO ffa_game_claims (lobby_id, game_number, kind, quarantine_id)
  SELECT t.l, CAST(t.g AS int2), 'credit', t.q FROM unnest(lobbies, games, qids) AS t(l, g, q)
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS n_new = ROW_COUNT;
  RAISE NOTICE '426: % credited FFA held report(s); % claim(s) seeded, the rest already held', n_rows, n_new;
END
$$;

COMMIT;
