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
-- the table missing; expires_at or banned_at missing or not timestamp with
-- time zone; a constraint of this name whose definition is not this one.
--
-- RE-RUNS. When the constraint is present the DO takes no lock and changes
-- no row: it only re-reads the definition and refuses one that differs. Two
-- runs at once: the second waits on the first's ACCESS EXCLUSIVE lock (or
-- gives up after 5 s), then finds the constraint and changes nothing.
--
-- HOW LONG THE LOCK CAN LIVE (learning #1072, as in 417). lock_timeout
-- bounds the WAIT for player_bans' ACCESS EXCLUSIVE (5 s); once held it lives
-- until COMMIT. statement_timeout bounds the DO (25 s) and
-- idle_in_transaction_session_timeout ends a runner stopped between the DO
-- and COMMIT (5 s); synchronous_commit = local keeps the COMMIT's wait off
-- any standby. The table holds one row on the primary.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $m418$
DECLARE
  tbl regclass := to_regclass(format('%I.player_bans', current_schema()));
  t_end text;
  t_start text;
  def text;
  n_null bigint;
  n_long bigint;
  want constant text :=
    'CHECK (((expires_at IS NOT NULL) AND (banned_at IS NOT NULL) AND (expires_at <= (banned_at + ''8760:00:00''::interval))))';
BEGIN
  IF tbl IS NULL THEN
    RAISE EXCEPTION '418: table player_bans is missing';
  END IF;
  SELECT format_type(a.atttypid, a.atttypmod) INTO t_end
    FROM pg_attribute a WHERE a.attrelid = tbl AND a.attname = 'expires_at' AND NOT a.attisdropped;
  IF t_end IS DISTINCT FROM 'timestamp with time zone' THEN
    RAISE EXCEPTION '418: player_bans.expires_at is %, not timestamp with time zone (apply 417 first)',
      coalesce(t_end, 'missing');
  END IF;
  SELECT format_type(a.atttypid, a.atttypmod) INTO t_start
    FROM pg_attribute a WHERE a.attrelid = tbl AND a.attname = 'banned_at' AND NOT a.attisdropped;
  IF t_start IS DISTINCT FROM 'timestamp with time zone' THEN
    RAISE EXCEPTION '418: player_bans.banned_at is %, not timestamp with time zone',
      coalesce(t_start, 'missing');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint c
                  WHERE c.conrelid = tbl AND c.conname = 'player_bans_max_one_year') THEN
    EXECUTE 'LOCK TABLE player_bans IN ACCESS EXCLUSIVE MODE';
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
   WHERE c.conrelid = tbl AND c.conname = 'player_bans_max_one_year'
     AND c.contype = 'c' AND c.convalidated;
  IF def IS DISTINCT FROM want THEN
    RAISE EXCEPTION '418: player_bans_max_one_year is %, not the validated CHECK 418 adds',
      coalesce(def, 'missing or not a validated CHECK');
  END IF;
END $m418$;

COMMIT;
