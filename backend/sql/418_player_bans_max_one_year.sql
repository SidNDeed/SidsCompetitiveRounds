-- 418_player_bans_max_one_year.sql
-- Every ban ends, at most 8760 hours (365 days of 24 hours) after its start.
--
-- The owner's ruling of 16 Nov 2026: every ban has a maximum length of one
-- year. The bound is models.BAN_MAX_HOURS (8760); this file's literal
-- '8760 hours' is pinned to that constant by test_ban_cap_pg.py. It is
-- written as HOURS, never as days, months or a year: a day or month interval
-- added to a timestamptz depends on the session's time zone, and a table
-- constraint must give the same verdict in every session.
--
-- 1. Every row whose end is NULL (a ban written before the cap; open and
--    closed rows alike) gets banned_at + 8760 hours, and every end later
--    than banned_at + 8760 hours is lowered to that bound. Both counts are
--    printed as NOTICE lines. An open row whose new end is already behind
--    the clock stops being active by the one definition
--    (models.player_ban_active_sql); the ban writer closes it as the system
--    at that key's next ban (migration 417). Measured on the primary
--    2026-11-16: 1 row, 1 open, none begun more than a year ago.
--
-- 2. CHECK player_bans_max_one_year: expires_at IS NOT NULL AND banned_at
--    IS NOT NULL AND expires_at <= banned_at + 8760 hours. banned_at is NOT
--    NULL since 028 (and the ORM declares it so); the check names it anyway,
--    because a NULL start would make the comparison NULL and let a CHECK pass.
--
-- DEPLOY ORDER: this file is applied AFTER the api that writes an end on
-- every ban (the ban-cap build, /health ban_cap_build = 1) answers on BOTH
-- boxes. The release train applies it in its post-code step (the batch names
-- it under post_code_sql, never schema_sql). The constraint depends on the
-- code, not the code on the constraint: an api before the cap writes a NULL
-- end for a ban without a length, which this CHECK refuses. The cap api is
-- correct with and without this file.
-- ROLLBACK ORDER: before any api rollback below the ban-cap build, apply
-- rollback_418_player_bans_max_one_year.sql first.
--
-- Applied by the migrate verb (ssh ccdeploy@<primary> 'migrate:418_player_bans_max_one_year.sql'),
-- which runs psql with ON_ERROR_STOP=1, the file on stdin; this file is its
-- own transaction (learning #340): BEGIN and COMMIT below.
--
-- REFUSALS (RAISE EXCEPTION, the transaction rolls back, nothing applied):
-- the table missing; the bare name player_bans, under the pinned search
-- path, naming another table or none; expires_at or banned_at missing or
-- not timestamp with time zone; a constraint of this name whose definition
-- is not this one; a read-only session (the first write fails).
--
-- RE-RUNS. When the constraint is present at the DO's first read, the DO
-- takes no lock and changes no row: it only re-reads the definition and
-- refuses one that differs. When it is absent, the DO takes player_bans'
-- ACCESS EXCLUSIVE lock and reads again UNDER the lock everything it acts
-- on: whether the constraint exists, both columns' types, and the rows the
-- two UPDATEs count. The transaction is READ COMMITTED whatever the session
-- brought, and only at READ COMMITTED does a read under the lock see a
-- commit made while this run waited for it. So of two first runs at once,
-- the second waits on the first's lock (or gives up after 5 s with nothing
-- applied), then finds the constraint under its own lock and changes
-- nothing, the same end state as a second run in sequence. A drop of the
-- constraint after the first read makes the post-check refuse, nothing
-- applied.
--
-- THE SESSION'S SETTINGS. The post-check compares deparsed text, and the
-- CHECK is parsed by name, so the file pins everything its parse, its
-- deparse and its re-read depend on, and no setting a session, a role or a
-- database brings moves its verdict:
--   * the transaction: BEGIN ISOLATION LEVEL READ COMMITTED (above). It
--     names no READ WRITE: a BEGIN that could fail would leave the rest of
--     the file running outside a transaction, and this one cannot fail.
--     Under a read-only default the first write (the lock) then fails
--     inside the transaction, nothing applied.
--   * the deparse: SET LOCAL IntervalStyle = postgres (the CHECK's interval
--     prints 8760:00:00 under it, PT8760H under iso_8601) and SET LOCAL
--     quote_all_identifiers = off (on, every column name prints quoted).
--   * the parse: the search path. The DO names the table first, in the
--     session's current schema, with every function it calls before the pin
--     and every type it declares qualified by pg_catalog (the declarations
--     are resolved when the block is compiled, before its first statement);
--     then pins the path for the rest of the
--     transaction to pg_catalog first, that schema second and the temporary
--     schema last, and refuses unless the bare name player_bans still names
--     that table. So the CHECK's <= and + are pg_catalog's, whatever operator
--     of that name another schema on the session's path holds, and the
--     deparser prints them bare.
--   * objects in another schema: the pinned path settles an operator only
--     against one with the same argument types (operator resolution takes
--     an exact match of the argument types before one that needs a
--     coercion, wherever on the path it sits). So every comparison here is
--     written on types pg_catalog holds an exact operator for: the catalog
--     reads and the identity check compare oids (tbl::oid, the oid of
--     pg_catalog's timestamptz, to_regclass(...)::oid); the
--     other comparisons are name = name, "char" = "char", text = text,
--     timestamptz <= timestamptz and timestamptz > timestamptz. An operator
--     of the same name and types in the table's schema comes after
--     pg_catalog's on the pinned path.
-- What does not enter: the definition holds no date or time constant
-- (DateStyle, TimeZone), no string literal holds a backslash
-- (standard_conforming_strings), no floating-point value
-- (extra_float_digits); its column names are never qualified, and the
-- interval type is never printed qualified. The column-type checks compare
-- type oids, not printed names. test_ban_cap_pg.py's SESSION_SETTINGS runs
-- this file under each of these settings and checks the CHECK's behaviour.
--
-- HOW LONG THE LOCK CAN LIVE (learning #1072, as in 417). lock_timeout
-- bounds the WAIT for player_bans' ACCESS EXCLUSIVE (5 s); once held it lives
-- until COMMIT. statement_timeout bounds the DO (25 s) and
-- idle_in_transaction_session_timeout ends a runner stopped between the DO
-- and COMMIT (5 s); synchronous_commit = local keeps the COMMIT's wait off
-- any standby. The table holds one row on the primary.

-- The pinned environment (header, THE SESSION'S SETTINGS); the search path
-- is pinned at the head of the DO, once the table is named.
-- the re-read under the lock sees another run's commit only at read committed
BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;
-- the post-check's deparsed text follows IntervalStyle
SET LOCAL IntervalStyle = 'postgres';
-- ... and quote_all_identifiers
SET LOCAL quote_all_identifiers = off;

DO $m418$
DECLARE
  sch pg_catalog.name := pg_catalog.current_schema();
  tbl pg_catalog.regclass := pg_catalog.to_regclass(pg_catalog.format('%I.player_bans', sch));
  present pg_catalog.bool;
  ty_end pg_catalog.oid;
  ty_start pg_catalog.oid;
  def pg_catalog.text;
  n_null pg_catalog.int8;
  n_long pg_catalog.int8;
  want constant pg_catalog.text :=
    'CHECK (((expires_at IS NOT NULL) AND (banned_at IS NOT NULL) AND (expires_at <= (banned_at + ''8760:00:00''::interval))))';
BEGIN
  IF tbl IS NULL THEN
    RAISE EXCEPTION '418: table player_bans is missing';
  END IF;

  -- The search path, pinned once the table is named: pg_catalog first, the
  -- table's schema second, the temporary schema last (header).
  PERFORM pg_catalog.set_config('search_path', pg_catalog.format('pg_catalog, %I, pg_temp', sch), true);
  IF pg_catalog.to_regclass('player_bans')::oid IS DISTINCT FROM tbl::oid THEN
    RAISE EXCEPTION '418: player_bans under the pinned search path is %, not %',
      coalesce(pg_catalog.to_regclass('player_bans')::text, 'missing'), tbl;
  END IF;

  -- First read, without a lock. Absent: lock, then read again under the
  -- lock, since a run that held the lock before us may have added it.
  present := EXISTS (SELECT 1 FROM pg_constraint c
                      WHERE c.conrelid = tbl::oid AND c.conname = 'player_bans_max_one_year');
  IF NOT present THEN
    EXECUTE 'LOCK TABLE player_bans IN ACCESS EXCLUSIVE MODE';
    present := EXISTS (SELECT 1 FROM pg_constraint c
                        WHERE c.conrelid = tbl::oid AND c.conname = 'player_bans_max_one_year');
  END IF;

  -- The columns, read after the lock whenever this run will write.
  SELECT a.atttypid INTO ty_end
    FROM pg_attribute a WHERE a.attrelid = tbl::oid AND a.attname = 'expires_at' AND NOT a.attisdropped;
  IF ty_end IS DISTINCT FROM 'pg_catalog.timestamptz'::regtype::oid THEN
    RAISE EXCEPTION '418: player_bans.expires_at is %, not timestamp with time zone (apply 417 first)',
      coalesce(format_type(ty_end, NULL), 'missing');
  END IF;
  SELECT a.atttypid INTO ty_start
    FROM pg_attribute a WHERE a.attrelid = tbl::oid AND a.attname = 'banned_at' AND NOT a.attisdropped;
  IF ty_start IS DISTINCT FROM 'pg_catalog.timestamptz'::regtype::oid THEN
    RAISE EXCEPTION '418: player_bans.banned_at is %, not timestamp with time zone',
      coalesce(format_type(ty_start, NULL), 'missing');
  END IF;

  IF NOT present THEN
    -- reached only under the lock taken above
    UPDATE player_bans SET expires_at = banned_at + interval '8760 hours'
     WHERE expires_at IS NULL;
    GET DIAGNOSTICS n_null = ROW_COUNT;
    UPDATE player_bans SET expires_at = banned_at + interval '8760 hours'
     WHERE expires_at > banned_at + interval '8760 hours';
    GET DIAGNOSTICS n_long = ROW_COUNT;
    RAISE NOTICE '418: % ban row(s) had no end and now end at banned_at + 8760 hours', n_null;
    RAISE NOTICE '418: % ban row(s) ended later than banned_at + 8760 hours and were lowered to it', n_long;
    ALTER TABLE player_bans ADD CONSTRAINT player_bans_max_one_year
      CHECK (expires_at IS NOT NULL AND banned_at IS NOT NULL
             AND expires_at <= banned_at + interval '8760 hours');
  ELSE
    RAISE NOTICE '418: player_bans_max_one_year is present; no row changed';
  END IF;

  -- Post-check: the guard above only asks whether the name exists.
  SELECT pg_get_constraintdef(c.oid) INTO def
    FROM pg_constraint c
   WHERE c.conrelid = tbl::oid AND c.conname = 'player_bans_max_one_year'
     AND c.contype = 'c' AND c.convalidated;
  IF def IS DISTINCT FROM want THEN
    RAISE EXCEPTION '418: player_bans_max_one_year is %, not the validated CHECK 418 adds',
      coalesce(def, 'missing or not a validated CHECK');
  END IF;
END $m418$;

COMMIT;
