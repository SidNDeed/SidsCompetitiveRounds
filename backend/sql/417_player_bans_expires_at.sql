-- 417_player_bans_expires_at.sql
-- A ban's end time, and one open ban row per account.
--
-- 1. player_bans.expires_at (TIMESTAMPTZ, NULL = permanent). A ban is ACTIVE
--    while its row is not lifted and its end time, if it has one, is ahead of
--    the database's clock:
--        unbanned_at IS NULL AND (expires_at IS NULL OR expires_at > NOW())
--    (models.player_ban_active_sql, the one definition every api reader of
--    this table uses). A timed ban ends by that comparison at read time; no
--    job, sweep or timer touches the row. Every existing row stays NULL, so
--    every ban written before this file stays permanent and nothing changes
--    for any account until an admin sets a length.
--
-- 2. Unique index player_bans_one_open_per_key on (steam_id) WHERE
--    unbanned_at IS NULL: one open row per key. Before this file the rule
--    "one active ban per account" was held only by the ban writer
--    (main._apply_ban_core), which re-reads the target's active ban under the
--    target's advisory lock and inserts only when there is none; the 028
--    index idx_player_bans_active is not unique. An ended timed ban keeps
--    unbanned_at NULL, so the writer closes it (unbanned_at = expires_at,
--    unbanned_by_steam_id = 'system:expired') in the same transaction and
--    under the same lock as the next insert, and this index refuses any
--    insert that would leave two open rows for one key. Migration 319's CHECK
--    reads only unbanned_at: it holds an ended, unclosed row to the numeric
--    key domain like an active one, and admits a closed row whatever its key.
--    The DO refuses (and the transaction rolls back, nothing applied) while
--    any key holds two or more open rows; measured on the primary 2026-11-14:
--    1 row in the table, 1 open, no key with two.
--
-- DEPLOY ORDER: THIS FILE FIRST, then the api, as two SHAs (learning #477):
-- the api's PlayerBan model names the column and every ban reader compares
-- it, so an api deployed before this file fails every ban check. Applying
-- this file alone changes no behaviour (every row NULL; the index admits the
-- table as it stands), so it may land any time before the api.
--
-- RE-RUNS. The ADD is guarded on the catalog, so a second run issues no
-- ALTER and takes no lock (ADD COLUMN IF NOT EXISTS alone takes ACCESS
-- EXCLUSIVE before it looks for the column); the index is guarded on the
-- catalog the same way. The post-checks refuse a same-named column of
-- another type and a same-named index that is not this one, which the
-- guards alone would accept. Two runs at once need no extra lock: a second
-- run whose guard read the column as missing waits on the first's ACCESS
-- EXCLUSIVE, and ADD COLUMN IF NOT EXISTS looks again only once it holds
-- that lock, so it adds nothing; CREATE UNIQUE INDEX IF NOT EXISTS likewise.
-- The duplicate count only names the cause of a refusal: the unique build
-- refuses a duplicate by itself, and while it runs its SHARE lock holds off
-- every insert. The count reads keys, never a row value it then writes.
-- Explicit transaction (learning #340).
--
-- HOW LONG THE LOCK CAN LIVE (learning #1072). lock_timeout bounds only the
-- WAIT for player_bans' ACCESS EXCLUSIVE (5 s); once held it lives until
-- COMMIT. statement_timeout bounds the DO (25 s) and
-- idle_in_transaction_session_timeout ends a runner stopped between the DO
-- and COMMIT (5 s), so the hold is bounded by 25 s + 5 s = 30 s plus the
-- COMMIT's local completion; synchronous_commit = local keeps that wait off
-- any standby. The ALTER rewrites no row (nullable, no default); the index
-- build reads the table once (1 row on the primary).

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $m417$
DECLARE
  got text;
  dup bigint;
  idx text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_attribute a
                  WHERE a.attrelid = to_regclass(format('%I.player_bans', current_schema()))
                    AND a.attname = 'expires_at'
                    AND NOT a.attisdropped) THEN
    ALTER TABLE player_bans ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NULL;
    COMMENT ON COLUMN player_bans.expires_at IS
      'When this ban ends; NULL = permanent. A ban is active while unbanned_at '
      'IS NULL AND (expires_at IS NULL OR expires_at > NOW()) (migration 417).';
  END IF;

  IF to_regclass(format('%I.player_bans_one_open_per_key', current_schema())) IS NULL THEN
    SELECT count(*) INTO dup FROM (
      SELECT steam_id FROM player_bans WHERE unbanned_at IS NULL
       GROUP BY steam_id HAVING count(*) > 1) d;
    IF dup > 0 THEN
      RAISE EXCEPTION '417: % key(s) hold two or more open player_bans rows; release the extra '
                      'rows through /api/v1/admin/unban, then apply again', dup;
    END IF;
    CREATE UNIQUE INDEX IF NOT EXISTS player_bans_one_open_per_key
        ON player_bans (steam_id) WHERE unbanned_at IS NULL;
  END IF;

  -- Post-checks: the guards above only ask whether the names exist.
  SELECT format_type(a.atttypid, a.atttypmod) INTO got
    FROM pg_attribute a
   WHERE a.attrelid = to_regclass(format('%I.player_bans', current_schema()))
     AND a.attname = 'expires_at'
     AND NOT a.attisdropped;
  IF got IS DISTINCT FROM 'timestamp with time zone' THEN
    RAISE EXCEPTION '417: player_bans.expires_at is %, not timestamp with time zone',
      coalesce(got, 'missing');
  END IF;
  SELECT pg_get_indexdef(i.indexrelid) INTO idx
    FROM pg_index i
   WHERE i.indexrelid = to_regclass(format('%I.player_bans_one_open_per_key', current_schema()))
     AND i.indrelid = to_regclass(format('%I.player_bans', current_schema()))
     AND i.indisunique AND i.indisvalid;
  IF idx IS NULL OR idx NOT LIKE '%UNIQUE INDEX player_bans_one_open_per_key ON %player_bans USING btree (steam_id) WHERE (unbanned_at IS NULL)' THEN
    RAISE EXCEPTION '417: player_bans_one_open_per_key is %, not the unique index 417 creates',
      coalesce(idx, 'missing');
  END IF;
END $m417$;

COMMIT;
