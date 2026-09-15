-- 320: Player Cards -- no Steam ID, no card. The prints owners still hold of
-- a subject whose players.steam_id is not a SteamID64 are retired (v4.13;
-- Sid, 2026-09-15).
--
-- The players table also holds every opponent a match report named
-- (get_or_create_player), ids from other platforms included. Until v4.13 the
-- card pool was every registered, unbanned player, so those rows were dealt as
-- card subjects. From the v4.13 api on, the pool word main._PC_POOL_MEMBER_SQL
-- carries steamid64's rule: no snapshot the api takes admits such a row, the
-- open re-rolls one an older snapshot still holds, and the janitor takes a new
-- snapshot at its next pass when the latest holds one. This file handles the
-- prints dealt before that.
--
-- Retirement is written where a print's status lives: its two discard
-- columns, which pc_prints_immutable freezes once discarded_at is set. Every
-- reader of a live print therefore stops showing a retired one exactly as it
-- stops showing a discarded one: the binder (/pc/collection and the bot's
-- /collection), /pc/card, the face routes, the delivery leases, the events
-- handout, the bot's /card counts, dup_at_pull and /pc/me. The owner's pack
-- history keeps it, marked discarded, as it keeps every discarded print.
-- pc_print_retirements records each retired print with the compensation and
-- the shards paid, so a retirement stays distinguishable from a discard.
--
-- THE SWITCH is the one value v_compensation holds in the DO block below:
--   'shards' (variant A): the owner receives exactly what a discard of that
--            print pays, by the print's rarity (the CASE is
--            player_cards.PC_ECONOMY["shards"]; test_pc_no_steam_no_card.py
--            pins both copies of it), as a delta on players.pc_shards (#326).
--   'none'   (variant B): the print is retired and nothing is paid
--            (discard_shards 0).
-- Any other value raises before anything is retired; the switch is a
-- constant, so only an edit to this file can make that check raise. This
-- file holds 'shards', Sid's decision of 2026-09-15.
--
-- ORDER: apply AFTER the v4.13 api code phase, on the primary, as 315 was: an
-- older api still deals these subjects, and a print it mints after this file
-- has run stays held. The retirement's last check raises while a live print
-- of such a subject is visible after the retirement.
--
-- READ HALF: the SELECT below writes nothing and runs as it is through the
-- read-only wrapper (joined onto one line). Its answer changes until the
-- v4.13 api is live on the primary, because an older api keeps dealing these
-- subjects: at 02:00 UTC on 2026-09-15 it was 16 prints of 16 subjects, held
-- by 3 owners, all Common with no foil or signed, 80 shards. Read it again
-- right before applying; the NOTICE reports the same counts unless an owner
-- discards one of those prints in between.
--
-- TWO TRANSACTIONS, each explicit because psql does not open one for a file
-- (#340):
--   1. The record table, alone. Its REFERENCES pc_prints takes SHARE ROW
--      EXCLUSIVE on pc_prints, a lock every write to pc_prints conflicts
--      with: the CREATE waits for the transactions that have written to
--      pc_prints to end (5 s at most, the lock timeout), writes that arrive
--      meanwhile wait behind it, and its COMMIT releases the lock before the
--      retirement takes any.
--   2. The retirement. Each of its statements reads a snapshot of its own,
--      so it reads the owners of the prints to retire once and restricts
--      its locks, both balance readings and the retirement to that set; only
--      the last check reads beyond it. It takes their locks in the discard
--      route's order: each owner's identity lock (shared), then the owners'
--      players rows, keeping the ids of the rows it locked; then it retires
--      only prints those owners hold. The identity locks are taken one owner
--      at a time in sorted steam_id order (COLLATE "C", byte order), the
--      canonical order of #197 that _mail_lock_identities and the api's
--      other loops over several identity locks use, and all of them before
--      the first players row. A print committed after the first read under
--      an owner outside that set is not retired, and the last check raises
--      on it. Nothing ahead of those locks writes a row or changes a table.
--
-- MONEY: the retirement reads the locked owners' pc_shards total before its
-- write and again after it, and raises unless the total moved by exactly the
-- shards recorded for the prints it retired. Those rows stay locked until
-- COMMIT, so no other transaction moves the total in between.
--
-- FAILURE: the migrate wrapper applies this file once, feeding it to psql
-- with ON_ERROR_STOP=1 on stdin. (The installed wrapper first tries psql -f
-- on a path the database container does not mount; that attempt fails
-- before reading the file, and only then does the stdin form run, #655.
-- Were that first attempt ever to run the file and fail, the stdin run would
-- be a re-run: see IDEMPOTENT.) The first error (a RAISE below, a lock
-- timeout, a deadlock) stops psql, which exits 3, so the migrate call fails,
-- and the transaction in progress is discarded when the session ends;
-- nothing after the error runs. When the error is in the retirement, the
-- record table the first transaction committed stays, holding the records
-- of any earlier run that committed (none on a first run), and no api code
-- reads it.
--
-- IDEMPOTENT: the CREATE is IF NOT EXISTS, and a retired print is discarded,
-- so nothing here selects it again; a re-run retires, and pays for, only
-- prints still live.

SELECT pr.owner_player_id,
       COUNT(*) AS prints_to_retire,
       COUNT(DISTINCT c.subject_player_id) AS subjects,
       COUNT(*) FILTER (WHERE pr.foil OR pr.signed) AS foil_or_signed,
       SUM(CASE pr.rarity WHEN 'common' THEN 5 WHEN 'uncommon' THEN 15 WHEN 'rare' THEN 40 WHEN 'epic' THEN 150 WHEN 'legendary' THEN 600 END) AS shards_if_compensated,
       MAX(o.pc_shards) AS owner_shards_now
  FROM pc_prints pr
  JOIN pc_cards c ON c.id = pr.card_id
  JOIN players s ON s.id = c.subject_player_id
  JOIN players o ON o.id = pr.owner_player_id
 WHERE pr.discarded_at IS NULL
   AND NOT (CASE WHEN s.steam_id ~ '^[0-9]{17}$' THEN CAST(s.steam_id AS bigint) BETWEEN 76561197960265728 AND 76561202255233023 ELSE false END)
 GROUP BY pr.owner_player_id
 ORDER BY pr.owner_player_id;

-- Transaction 1: the record table, alone. One row per retired print. ON
-- DELETE CASCADE: the data deletion endpoint deletes prints (an owner's own,
-- and every print of a deleted subject's card), and a record must never
-- refuse that.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE TABLE IF NOT EXISTS pc_print_retirements (
    print_id      UUID PRIMARY KEY REFERENCES pc_prints(id) ON DELETE CASCADE,
    reason        TEXT NOT NULL,
    compensation  TEXT NOT NULL CHECK (compensation IN ('shards', 'none')),
    shards        INTEGER NOT NULL CHECK (shards >= 0),
    retired_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMIT;

-- Transaction 2: the retirement.
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m320$
DECLARE
    v_compensation CONSTANT text := 'shards';   -- THE SWITCH: 'shards' (A) or 'none' (B)
    v_owner_ids uuid[];
    v_before    bigint;
    v_after     bigint;
    v_recorded  bigint;
    v_retired   integer;
    v_owners    integer;
    v_leases    integer;
    v_ids       uuid[];
    v_sid       text;
BEGIN
    -- A check on this file's own text (THE SWITCH above).
    IF v_compensation NOT IN ('shards', 'none') THEN
        RAISE EXCEPTION '320: the compensation switch holds %, not shards or none; the retirement is not applied', v_compensation;
    END IF;

    -- The owners of the prints to retire, read once. The locks, both balance
    -- readings and the retirement below are restricted to this set; only the
    -- last check reads beyond it, to find a print left outside the set.
    SELECT array_agg(DISTINCT pr.owner_player_id) INTO v_owner_ids
      FROM pc_prints pr
      JOIN pc_cards c ON c.id = pr.card_id
      JOIN players s ON s.id = c.subject_player_id
     WHERE pr.discarded_at IS NULL
       AND NOT (CASE WHEN s.steam_id ~ '^[0-9]{17}$' THEN CAST(s.steam_id AS bigint) BETWEEN 76561197960265728 AND 76561202255233023 ELSE false END);

    -- Their locks, as the discard route takes them before it touches a print:
    -- the identity lock (shared), then the players row. The identity locks
    -- come first, one owner at a time in sorted steam_id order (COLLATE "C":
    -- byte order, the order Python's sorted() gives _mail_lock_identities and
    -- the api's other loops over several identity locks, #197). From here
    -- v_owner_ids holds the owners whose rows this transaction has locked.
    FOR v_sid IN SELECT o.steam_id
                   FROM players o
                  WHERE o.id = ANY(v_owner_ids)
                  ORDER BY o.steam_id COLLATE "C"
    LOOP
        PERFORM pg_advisory_xact_lock_shared(hashtext(CAST(v_sid AS text)));
    END LOOP;
    SELECT array_agg(q.id) INTO v_owner_ids
      FROM (SELECT o.id
              FROM players o
             WHERE o.id = ANY(v_owner_ids)
             ORDER BY o.id
               FOR NO KEY UPDATE OF o) q;

    -- MONEY, the first reading: the locked owners' shards before the write.
    SELECT COALESCE(SUM(o.pc_shards), 0) INTO v_before
      FROM players o
     WHERE o.id = ANY(v_owner_ids);

    -- Retire the live prints of such subjects those owners hold, record them,
    -- pay (a delta, from what the retirement returned) and end the delivery
    -- leases naming a retired print, as the discard route does.
    WITH retired AS (
        UPDATE pc_prints pr
           SET discarded_at = now(),
               discard_shards = CASE WHEN v_compensation = 'shards'
                                     THEN CASE pr.rarity WHEN 'common' THEN 5 WHEN 'uncommon' THEN 15 WHEN 'rare' THEN 40 WHEN 'epic' THEN 150 WHEN 'legendary' THEN 600 END
                                     ELSE 0 END
          FROM pc_cards c, players s
         WHERE c.id = pr.card_id AND s.id = c.subject_player_id
           AND pr.discarded_at IS NULL
           AND NOT (CASE WHEN s.steam_id ~ '^[0-9]{17}$' THEN CAST(s.steam_id AS bigint) BETWEEN 76561197960265728 AND 76561202255233023 ELSE false END)
           AND pr.owner_player_id = ANY(v_owner_ids)
        RETURNING pr.id, pr.owner_player_id, pr.discard_shards
    ), recorded AS (
        INSERT INTO pc_print_retirements (print_id, reason, compensation, shards)
        SELECT r.id, 'no_steam_id', v_compensation, r.discard_shards
          FROM retired r
    ), paid AS (
        UPDATE players o SET pc_shards = o.pc_shards + d.shards
          FROM (SELECT r.owner_player_id, CAST(SUM(r.discard_shards) AS integer) AS shards
                  FROM retired r GROUP BY r.owner_player_id) d
         WHERE o.id = d.owner_player_id AND d.shards > 0
    ), released AS (
        DELETE FROM pc_delivery_leases l USING retired r WHERE l.print_id = r.id
        RETURNING l.id
    )
    SELECT (SELECT COUNT(*) FROM retired),
           (SELECT COUNT(DISTINCT r.owner_player_id) FROM retired r),
           (SELECT COUNT(*) FROM released),
           (SELECT array_agg(r.id) FROM retired r)
      INTO v_retired, v_owners, v_leases, v_ids;

    -- MONEY, the check. Later statements see what that one wrote: the shards
    -- recorded for the prints retired here, then the second reading of the
    -- locked owners' shards, which must have moved by exactly that much.
    SELECT COALESCE(SUM(rt.shards), 0) INTO v_recorded
      FROM pc_print_retirements rt
     WHERE rt.print_id = ANY(v_ids);
    SELECT COALESCE(SUM(o.pc_shards), 0) INTO v_after
      FROM players o
     WHERE o.id = ANY(v_owner_ids);
    IF v_after - v_before <> v_recorded THEN
        RAISE EXCEPTION '320: the owners'' shards moved by % but % shard(s) are recorded for the prints retired here; the retirement is not applied', v_after - v_before, v_recorded;
    END IF;

    -- No live print of such a subject may remain: one an older api dealt, or
    -- one committed after the first read under an owner outside that set.
    IF EXISTS (SELECT 1
                 FROM pc_prints pr
                 JOIN pc_cards c ON c.id = pr.card_id
                 JOIN players s ON s.id = c.subject_player_id
                WHERE pr.discarded_at IS NULL
                  AND NOT (CASE WHEN s.steam_id ~ '^[0-9]{17}$' THEN CAST(s.steam_id AS bigint) BETWEEN 76561197960265728 AND 76561202255233023 ELSE false END)) THEN
        RAISE EXCEPTION '320: a live print of a subject whose id is not a SteamID64 is visible after the retirement (an api older than v4.13 may still be dealing them, or one was committed under an owner this run did not read); the retirement is not applied';
    END IF;
    RAISE NOTICE '320: compensation %: % print(s) retired from % owner(s), % shard(s) paid, % lease(s) released',
        v_compensation, v_retired, v_owners, v_after - v_before, v_leases;
END $m320$;

COMMIT;
