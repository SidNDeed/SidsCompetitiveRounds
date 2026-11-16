-- 420_admin_actions_modlog.sql
-- The moderator log per player (work order MODLOG-1): two columns on
-- admin_actions, their index, and the players and reasons of the rows
-- written before this file.
--
-- 1. admin_actions.affected_steam_ids (text[], NOT NULL, DEFAULT '{}'): every
--    player the action acts on, by Steam id, at most 16 (the api's writer,
--    main._modlog_write, refuses more). The GIN index
--    ix_admin_actions_affected serves "this id is in the array"
--    (affected_steam_ids @> ARRAY[id]), the per-player read of
--    /api/v1/admin/modlog.
-- 2. admin_actions.reason (text, NULL): the reason the actor gave, at most
--    256 characters (CHECK ck_admin_actions_reason_len).
--    The existing columns keep their meaning. The api before this file
--    names neither column, so this file goes BEFORE the code.
-- 3. The old rows (every row written before this file has '{}'): the array
--    is filled from what the row names, and reason from details->>'reason'.
--    An id enters the array only when it is 17 digits and comes from
--      - the row's own target_steam_id (delete_player_data replaces an
--        exact match of this column with the account's tombstone), or
--      - the CURRENT players row reached by a join (delete_player_data
--        rewrites players.steam_id to the tombstone): a 1v1 series' two
--        players (ranked_series.player1_id/player2_id), a 2v2 series' four
--        (team_series slots), a match's two (matches.player1_id/player2_id,
--        by target_match_id or by details->>'match_id' of a record
--        exclusion), a reversed trade's two parties (pc_trades.pair_lo/
--        pair_hi, by the trade id the row keeps in target_steam_id), and a
--        deleted chat message's author (chat_messages by details message_id
--        or message_ids, then players by the message's steam_id; deletion
--        rewrites chat_messages.steam_id to the tombstone too).
--    A source whose table this database does not have adds nothing (the
--    test schemas replay migrations out of order; pc_trades comes with 353).
--    No Steam id is read from details: delete_player_data does not scrub
--    details, so an id copied there may be a deleted account's raw id. A
--    row whose target_steam_id is already a tombstone keeps '{}'. Only rows
--    still at '{}' are filled (and only reasons still NULL), so a second
--    run changes no row.
--    THE LOOKUPS. Each compares in the looked-up id column's OWN type, so
--    the column's primary key or unique index answers it: a uuid id with a
--    uuid, the chat message id as int8, players.steam_id (varchar, which
--    pg_catalog compares with its text operator, the one its index is built
--    with) as text. A text taken from a record (a details value; the trade
--    id kept in target_steam_id) is first checked for the id's form (the
--    canonical lower-case UUID text; a decimal of at most 18 digits without
--    a leading zero) and only then cast to the column's type; a text not of
--    that form names no row, as the text comparison it replaces named none.
--    No lookup casts an indexed column to another type (a varchar read as
--    text is the same value relabelled, which its index serves). The bound:
--    for N records, at most one index scan per record and source (a
--    record's list of message ids is one scan over those ids), plus one
--    index probe of players per row found, whatever the size of the
--    looked-up tables (tests/test_modlog_pg.py reads the plan of this file's
--    fill with 50,000 rows in each of them).
--
-- Refusals (nothing is changed then, one transaction): no admin_actions in
-- the session's current schema; the bare name admin_actions naming another
-- table once the path below is set; a column of either name with another
-- type (compared by type oid); an index named ix_admin_actions_affected
-- that is not the valid GIN index (array_ops) on affected_steam_ids alone,
-- without predicate or expression (compared by catalog identity); a
-- constraint named ck_admin_actions_reason_len that is not the validated
-- CHECK this file adds.
--
-- WHAT THE RESULT CANNOT FOLLOW (the BEGIN line and the head of the first
-- block, one reason per line). The file runs at READ COMMITTED whatever the
-- session's default, so a read taken after the lock sees a concurrent run's
-- commit. The table's identity is resolved by the session's path (its
-- current schema), then the path is pinned for the rest of the transaction:
-- pg_catalog first, the table's schema second, the temporary schema last;
-- the bare name must then resolve to the same table. The pinned path
-- decides between same-named functions or operators only where their
-- argument types are IDENTICAL; one of the same name with other argument
-- types in the table's schema competes with pg_catalog's on an equal
-- footing wherever the call's arguments are no exact match of pg_catalog's
-- (an untyped literal argument, as in format('%I...', nsp) or
-- format_type(oid, NULL); a VARIADIC "any" function; jsonb ->> 'key', whose
-- literal is read as jsonb first, and pg_catalog has no ->> for jsonb with
-- jsonb). So every function call in this file, before the pin and after it,
-- is written pg_catalog.<name>(, every jsonb path operator
-- OPERATOR(pg_catalog.->>) or OPERATOR(pg_catalog.->), and the polymorphic
-- || on arrays OPERATOR(pg_catalog.||) (tests/test_modlog_sql_census.py
-- holds both files to this). Every other comparison is of a pair pg_catalog
-- has an operator for exactly: identities are oids compared as oid with
-- oid, varchar columns are cast to text, and a literal stands beside a
-- value of the type it is read as (text, name, "char"). An operator or
-- function of the table's schema is then never taken; the CHECK's
-- char_length and <= (text and integer) are pg_catalog's. quote_all_identifiers is off for the
-- rest of the transaction, for the one deparsed text the file compares (the
-- CHECK's). Types and the index are compared by identity, not by printed
-- text. No literal here holds a backslash, so standard_conforming_strings
-- does not enter; no value printed or compared is a date, time, interval or
-- float, so DateStyle, TimeZone, IntervalStyle and extra_float_digits do
-- not enter. Under a read-only session default the LOCK fails inside the
-- transaction and nothing is applied.
-- backend/tests/test_modlog_pg.py runs this file under each such setting.
--
-- ONE RUN AT A TIME. Every precondition is read after the table's ACCESS
-- EXCLUSIVE lock (the lock the first ALTER takes in any case, held until
-- COMMIT), so a second run started while the first is open waits, then
-- finds the first run's result and changes no row and no catalog row.
--
-- psql -f does not wrap a file in a transaction (learning #340): BEGIN and
-- COMMIT are explicit. admin_actions has no foreign key (migration 192
-- dropped its only one), so neither the fill nor a later insert locks
-- another table's row.

BEGIN ISOLATION LEVEL READ COMMITTED;   -- reads after the lock see a concurrent run's commit
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL statement_timeout = '60s';
SET LOCAL synchronous_commit = local;

-- ONE block. Its head is the environment: the table's identity by the
-- session's path, then the path and the deparse setting pinned for the rest
-- of the transaction. PL/pgSQL plans each statement when it first runs, so
-- every statement after the head is parsed under the pinned path. (One
-- block, not two: a migration replay that runs each statement on its own
-- keeps nothing from one block to the next.)
-- Exact operators: pg_catalog first on the path settles only an operator
-- whose argument types are exactly those of a pg_catalog operator; for any
-- other pair (oid with regclass, regclass with regclass, varchar with
-- varchar, text[] with text[]) an exact operator in the table's schema would
-- be taken. So every identity here is held as an oid and compared as oid
-- with oid, and every function call, here and below, names pg_catalog (the
-- header: the path does not settle a call whose arguments are no exact
-- match).
DO $m420$
DECLARE
  tbl pg_catalog.oid := pg_catalog.to_regclass(
    pg_catalog.format('%I.admin_actions', pg_catalog.current_schema()))::pg_catalog.oid;
  nsp pg_catalog.text;
  ty_aff pg_catalog.oid;
  att_aff pg_catalog.int2;
  ty_reason pg_catalog.oid;
  idx pg_catalog.oid;
  idx_ok pg_catalog.bool;
  con_oid pg_catalog.oid;
  con_ok pg_catalog.bool;
  gin_am pg_catalog.oid;
  gin_ops pg_catalog.oid;
  text_oid pg_catalog.oid;
  text_arr_oid pg_catalog.oid;
  want constant pg_catalog.text := 'CHECK (((reason IS NULL) OR (char_length(reason) <= 256)))';
BEGIN
  IF tbl IS NULL THEN
    RAISE EXCEPTION '420: admin_actions is missing from the current schema %; nothing changed',
      pg_catalog.current_schema();
  END IF;
  SELECT n.nspname INTO nsp
    FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid OPERATOR(pg_catalog.=) c.relnamespace
   WHERE c.oid OPERATOR(pg_catalog.=) tbl;
  PERFORM pg_catalog.set_config('search_path',
    pg_catalog.format('pg_catalog, %I, pg_temp', nsp), true);   -- names bind as written
  PERFORM pg_catalog.set_config('quote_all_identifiers', 'off', true);   -- the CHECK's deparsed text is compared below
  IF pg_catalog.to_regclass('admin_actions')::oid IS DISTINCT FROM tbl THEN   -- the bare name names the same table
    RAISE EXCEPTION '420: the name admin_actions resolves to %, not %; nothing changed',
      coalesce(pg_catalog.to_regclass('admin_actions')::text, 'nothing'), tbl::regclass;
  END IF;
  gin_am := (SELECT a.oid FROM pg_am a WHERE a.amname = 'gin');
  gin_ops := (SELECT o.oid FROM pg_opclass o
               WHERE o.opcmethod = gin_am AND o.opcname = 'array_ops'
                 AND o.opcnamespace = 'pg_catalog'::regnamespace::oid);
  text_oid := 'pg_catalog.text'::regtype::oid;
  text_arr_oid := 'pg_catalog.text[]'::regtype::oid;

  LOCK TABLE admin_actions IN ACCESS EXCLUSIVE MODE;   -- every read below runs under it

  -- Refusals: a name that exists with another shape.
  SELECT a.atttypid, a.attnum INTO ty_aff, att_aff
    FROM pg_attribute a WHERE a.attrelid = tbl AND a.attname = 'affected_steam_ids' AND NOT a.attisdropped;
  IF ty_aff IS NOT NULL AND ty_aff <> text_arr_oid THEN
    RAISE EXCEPTION '420: admin_actions.affected_steam_ids is %, not text[]; nothing changed',
      pg_catalog.format_type(ty_aff, NULL);
  END IF;
  SELECT a.atttypid INTO ty_reason
    FROM pg_attribute a WHERE a.attrelid = tbl AND a.attname = 'reason' AND NOT a.attisdropped;
  IF ty_reason IS NOT NULL AND ty_reason <> text_oid THEN
    RAISE EXCEPTION '420: admin_actions.reason is %, not text; nothing changed', pg_catalog.format_type(ty_reason, NULL);
  END IF;
  idx := pg_catalog.to_regclass(pg_catalog.format('%I.ix_admin_actions_affected', nsp))::oid;
  IF idx IS NOT NULL THEN
    idx_ok := EXISTS (
      SELECT 1 FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid
       WHERE i.indexrelid = idx AND i.indrelid = tbl AND i.indisvalid AND i.indisready
         AND i.indnatts = 1 AND att_aff IS NOT NULL AND i.indkey[0] = att_aff
         AND i.indexprs IS NULL AND i.indpred IS NULL
         AND ic.relam = gin_am AND i.indclass[0] = gin_ops);
    IF NOT idx_ok THEN
      RAISE EXCEPTION '420: ix_admin_actions_affected is not the GIN index 420 creates on affected_steam_ids; nothing changed';
    END IF;
  END IF;
  SELECT c.oid, (c.contype = 'c' AND c.convalidated AND pg_catalog.pg_get_constraintdef(c.oid) = want)
    INTO con_oid, con_ok
    FROM pg_constraint c WHERE c.conrelid = tbl AND c.conname = 'ck_admin_actions_reason_len';
  IF con_oid IS NOT NULL AND NOT con_ok THEN
    RAISE EXCEPTION '420: ck_admin_actions_reason_len is %, not the check 420 creates; nothing changed',
      pg_catalog.pg_get_constraintdef(con_oid);
  END IF;

  -- The columns, the check and the index: each only when absent, so a run
  -- that finds them writes no catalog row.
  IF ty_aff IS NULL THEN
    ALTER TABLE admin_actions ADD COLUMN affected_steam_ids TEXT[] NOT NULL DEFAULT '{}';
    COMMENT ON COLUMN admin_actions.affected_steam_ids IS
      'Every player the action acts on, by Steam id, at most 16 (migration 420); ''{}'' when it names none.';
  END IF;
  IF ty_reason IS NULL THEN
    ALTER TABLE admin_actions ADD COLUMN reason TEXT NULL;
    COMMENT ON COLUMN admin_actions.reason IS
      'The reason the actor gave, at most 256 characters (migration 420); NULL when none.';
  END IF;
  IF con_oid IS NULL THEN
    ALTER TABLE admin_actions ADD CONSTRAINT ck_admin_actions_reason_len
      CHECK (reason IS NULL OR pg_catalog.char_length(reason) <= 256);
  END IF;
  IF idx IS NULL THEN
    CREATE INDEX ix_admin_actions_affected ON admin_actions USING gin (affected_steam_ids);
  END IF;

  -- Post-check, by identity again: the shape the code relies on.
  SELECT a.atttypid, a.attnum INTO ty_aff, att_aff
    FROM pg_attribute a
   WHERE a.attrelid = tbl AND a.attname = 'affected_steam_ids' AND NOT a.attisdropped AND a.attnotnull;
  IF ty_aff IS DISTINCT FROM text_arr_oid THEN
    RAISE EXCEPTION '420: admin_actions.affected_steam_ids is not text[] NOT NULL after the file';
  END IF;
  IF NOT EXISTS (
      SELECT 1 FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid
       WHERE i.indexrelid = pg_catalog.to_regclass(pg_catalog.format('%I.ix_admin_actions_affected', nsp))::oid
         AND i.indrelid = tbl AND i.indisvalid AND i.indisready
         AND i.indnatts = 1 AND i.indkey[0] = att_aff
         AND i.indexprs IS NULL AND i.indpred IS NULL
         AND ic.relam = gin_am AND i.indclass[0] = gin_ops) THEN
    RAISE EXCEPTION '420: ix_admin_actions_affected is not the GIN index on affected_steam_ids after the file';
  END IF;
  IF NOT EXISTS (
      SELECT 1 FROM pg_constraint c
       WHERE c.conrelid = tbl AND c.conname = 'ck_admin_actions_reason_len'
         AND c.contype = 'c' AND c.convalidated AND pg_catalog.pg_get_constraintdef(c.oid) = want) THEN
    RAISE EXCEPTION '420: ck_admin_actions_reason_len is not the validated CHECK after the file';
  END IF;
END $m420$;

-- 3. The old rows' players. Only a row still at '{}' whose target is not a
-- tombstone; only 17-digit ids; at most 16 (a row's sources name at most 4).
-- Each source is added when its tables exist (header, point 3); the
-- statement is built from the fixed texts below and nothing else. Every
-- comparison is of two values of one type that pg_catalog has an operator
-- for (varchar columns are cast to text), and every function call, jsonb
-- path operator and || on arrays names pg_catalog, so no operator or
-- function of the table's schema is taken (the header).
DO $fill420$
DECLARE
  src text := 'ARRAY[a.target_steam_id::text]';
BEGIN
  IF pg_catalog.to_regclass('players') IS NOT NULL AND pg_catalog.to_regclass('ranked_series') IS NOT NULL THEN
    src := src || $s$
      OPERATOR(pg_catalog.||) COALESCE((SELECT ARRAY[p1.steam_id::text, p2.steam_id::text]
                     FROM ranked_series rs
                     JOIN players p1 ON p1.id = rs.player1_id
                     JOIN players p2 ON p2.id = rs.player2_id
                    WHERE rs.id = a.target_series_id), '{}'::text[])$s$;
  END IF;
  IF pg_catalog.to_regclass('players') IS NOT NULL AND pg_catalog.to_regclass('team_series') IS NOT NULL THEN
    src := src || $s$
      OPERATOR(pg_catalog.||) COALESCE((SELECT pg_catalog.array_agg(p.steam_id::text)
                     FROM team_series ts
                     JOIN players p ON p.id IN (ts.t1a_id, ts.t1b_id, ts.t2a_id, ts.t2b_id)
                    WHERE ts.id = a.target_series_id), '{}'::text[])$s$;
  END IF;
  IF pg_catalog.to_regclass('players') IS NOT NULL AND pg_catalog.to_regclass('matches') IS NOT NULL THEN
    src := src || $s$
      OPERATOR(pg_catalog.||) COALESCE((SELECT ARRAY[p1.steam_id::text, p2.steam_id::text]
                     FROM matches m
                     JOIN players p1 ON p1.id = m.player1_id
                     JOIN players p2 ON p2.id = m.player2_id
                    WHERE m.id = ANY (ARRAY[a.target_match_id,
                            CASE WHEN a.action::text = 'record_exclude' AND a.target_steam_id IS NULL
                                  AND (a.details OPERATOR(pg_catalog.->>) 'match_id')
                                      ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                 THEN CAST(a.details OPERATOR(pg_catalog.->>) 'match_id' AS pg_catalog.uuid)
                            END])
                    LIMIT 1), '{}'::text[])$s$;
  END IF;
  IF pg_catalog.to_regclass('players') IS NOT NULL AND pg_catalog.to_regclass('pc_trades') IS NOT NULL THEN
    src := src || $s$
      OPERATOR(pg_catalog.||) COALESCE((SELECT ARRAY[lo.steam_id::text, hi.steam_id::text]
                     FROM pc_trades t
                     JOIN players lo ON lo.id = t.pair_lo
                     JOIN players hi ON hi.id = t.pair_hi
                    WHERE a.action::text = 'pc_trade_reverse'
                      AND t.id = CASE WHEN a.target_steam_id::text
                                           ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                      THEN CAST(a.target_steam_id::text AS pg_catalog.uuid) END),
                  '{}'::text[])$s$;
  END IF;
  IF pg_catalog.to_regclass('players') IS NOT NULL AND pg_catalog.to_regclass('chat_messages') IS NOT NULL THEN
    src := src || $s$
      OPERATOR(pg_catalog.||) COALESCE((SELECT pg_catalog.array_agg(DISTINCT p.steam_id::text)
                     FROM chat_messages cm
                     JOIN players p ON p.steam_id::text = cm.steam_id::text
                    WHERE a.action::text = 'chat_delete'
                      AND pg_catalog.jsonb_typeof(a.details) = 'object'
                      AND cm.id = ANY (ARRAY(
                            SELECT CASE WHEN v.e ~ '^(0|[1-9][0-9]{0,17})$' THEN CAST(v.e AS pg_catalog.int8) END
                              FROM (SELECT a.details OPERATOR(pg_catalog.->>) 'message_id' AS e
                                    UNION ALL
                                    SELECT pg_catalog.jsonb_array_elements_text(
                                             a.details OPERATOR(pg_catalog.->) 'message_ids')
                                     WHERE pg_catalog.jsonb_typeof(
                                             a.details OPERATOR(pg_catalog.->) 'message_ids') = 'array') v))),
                  '{}'::text[])$s$;
  END IF;
  EXECUTE $q$
    UPDATE admin_actions aa
       SET affected_steam_ids = c.ids
      FROM (
        SELECT a.id,
               ARRAY(SELECT DISTINCT s FROM pg_catalog.unnest($q$ || src || $q$) s
                      WHERE s ~ '^[0-9]{17}$' ORDER BY s LIMIT 16) AS ids
          FROM admin_actions a
         WHERE pg_catalog.cardinality(a.affected_steam_ids) = 0
           AND (a.target_steam_id IS NULL OR NOT pg_catalog.starts_with(a.target_steam_id::text, 'deleted_'))
           -- the words that name no player (modlog.NAMES_NONE; the census
           -- test holds this list equal to it): a change to the server or
           -- its content, a refusal, or a platform user's id that is not a
           -- Steam id
           AND a.action::text NOT IN ('alert_create', 'alert_revoke', 'ban_rate_blocked',
                                'chat_lockdown', 'chat_purge_channel', 'chat_purge_user',
                                'chat_spam_pattern', 'chat_unmute_bridge', 'item-artist', 'mail_broadcast',
                                'operator_key_issue', 'operator_key_revoke', 'pc_snapshot',
                                'read_gate_mode', 'team_glicko_rebuild')
      ) c
     WHERE aa.id = c.id AND pg_catalog.cardinality(c.ids) > 0
  $q$;
END $fill420$;

-- 3. The old rows' reasons, from the reason their details carry.
UPDATE admin_actions
   SET reason = pg_catalog.left(details OPERATOR(pg_catalog.->>) 'reason', 256)
 WHERE reason IS NULL AND pg_catalog.jsonb_typeof(details) = 'object'
   AND COALESCE(details OPERATOR(pg_catalog.->>) 'reason', '') <> '';

COMMIT;
