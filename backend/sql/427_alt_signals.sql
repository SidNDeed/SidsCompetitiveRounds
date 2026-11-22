-- 427_alt_signals.sql
--
-- Records of what Steam reports at a verified sign-in and keyed codes of the
-- connection it came from, kept so that an admin can see which accounts are
-- related. The api writes them only at a verified sign-in, only while its
-- signal key is loaded, and only while the FAQ notice this file schedules is
-- posted and acknowledged. Every row is deleted no later than 90 days after
-- its own last sight, and at once with the account.
--
--   steam_signin_facts             NEW table, one row per account (steam_id,
--                                  the account's own id as text): first and
--                                  last recorded sign-in, the copy state Steam
--                                  reported (own, shared or unknown) with the
--                                  first and last sign-in that read shared,
--                                  the VAC and publisher ban flags with the
--                                  first and last sign-in that read each one
--                                  true, and a count of the days on which a
--                                  storage limit refused a row (with the last
--                                  such day).
--   ix_steam_signin_facts_last_seen  (last_seen_at): retention's delete.
--   steam_family_shares            NEW table, one row per account, key id and
--                                  owner mark: a keyed code of the account
--                                  that lent a borrowed copy, never its id,
--                                  with the first and last sign-in that read
--                                  it.
--   ix_steam_family_shares_owner   (key_id, owner_mark): accounts sharing one
--                                  lender.
--   ix_steam_family_shares_last_seen  (last_seen_at): retention's delete.
--   conn_markers                   NEW table, one row per account, UTC day,
--                                  key id and address code: keyed codes of
--                                  the address and of its network block,
--                                  never the address, the family (4 or 6),
--                                  the connection class word, and the first
--                                  and last sign-in of that day from it.
--   ix_conn_markers_addr           (key_id, addr_mark, day, steam_id): the
--                                  address relation.
--   ix_conn_markers_block          (key_id, block_mark, day, steam_id): the
--                                  block relation.
--   ix_conn_markers_last_at        (last_at): retention's delete.
--   pending_channel_posts          FAQ message 1 (the FAQ channel's row with
--                                  sort_order 1) gains a closing paragraph
--                                  saying what may be recorded; its revision
--                                  moves by one, so the bot edits the posted
--                                  message and acknowledges that revision.
--
-- No column holds a code of an account's own id, and no table has a foreign
-- key: a first sign-in can come before the players row exists, and account
-- deletion keeps the players row with its id replaced.
--
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND.
-- -----------------------------------------------
-- The api build carrying this change writes the three tables at a verified
-- sign-in, deletes from them in account deletion and in its retention pass,
-- and reads FAQ message 1 before it records anything. So the file lands
-- first: the migrate verb applies it on the primary, the standby receives it
-- by streaming replication, and only then does the code deploy. The previous
-- api build runs on the migrated schema unchanged: it never names the new
-- tables, and the bot it talks to edits message 1 the way it edits any FAQ
-- revision.
--
-- LOCKS. On a first run the three tables and their indexes are created empty
-- and no other session sees them before COMMIT; they have no foreign keys,
-- so no existing table is locked for them. The FAQ step updates one row of
-- pending_channel_posts: the bot's claim and acknowledgement of that row wait
-- from that statement until COMMIT, and reads do not.
--
-- HOLDING BOUND. lock_timeout bounds how long each step waits to start
-- behind a transaction already in flight. How long this file holds what it
-- took is bounded by the other settings: every statement by statement_timeout
-- (25 s) and any pause between statements by
-- idle_in_transaction_session_timeout (5 s), so the sum is 30 s, plus the
-- COMMIT's own flush, which no timeout covers; synchronous_commit = local
-- keeps that flush on this server, waiting for no standby. If a setting
-- expires the whole file rolls back with nothing changed and is re-applied.
--
-- CREATE OR REFUSE. The three tables are new and this file alone makes them,
-- so it either creates them or proves they are its own work, and refuses
-- every other state with nothing changed:
--   - none of the three names stands in the schema: the file creates all
--     three, with their keys and indexes, and stamps each with its mark, a
--     table comment holding the SHA-256 of the statements between the DDL
--     START and DDL END lines (comment and blank lines dropped, each line
--     trimmed). A name those statements create that already stands in the
--     schema (an index, a key's index, a table's row type) refuses the run
--     before any of them;
--   - all three are ordinary tables and all three carry exactly that mark:
--     they are this file's own committed work, and the file issues nothing
--     for them and takes no lock on them;
--   - anything else refuses: some without the others, any one unmarked or
--     marked otherwise, or any one not an ordinary table.
-- On the create path the applying role creates the tables in this
-- transaction, so it owns them, with the privileges a new table of that role
-- receives: the file grants and revokes nothing. A test recomputes the mark
-- from this text, so the statements between the markers cannot change
-- without the mark.
--
-- SEARCH PATH. PostgreSQL searches the session's temporary schema first for
-- relation and type names unless search_path names it, so an unqualified
-- name here could reach a temporary object. The first block therefore
-- appends pg_temp to search_path for this transaction (set_config, local to
-- it), which puts the temporary schema last. Before it changes anything it
-- refuses a search_path that names no existing schema or that already names
-- pg_temp.
--
-- THE FAQ ROW. The api records nothing until FAQ message 1 is exactly one
-- row, its acknowledged revision equals its revision, and its text holds the
-- paragraph this file adds. This file therefore requires the row it means:
--   - exactly one FAQ message 1 row, holding the text 338 wrote (carried here
--     as the earlier text): the file sets the new text (docs/FAQ.md's message
--     1 once this change lands) and moves the revision by one;
--   - exactly one FAQ message 1 row, already holding the new text: a re-run,
--     and the file writes nothing;
--   - anything else, an absent row included: the file raises, so nothing it
--     did commits.
--
-- RE-RUNS. A second run finds the three tables marked and the row already
-- revised: it issues no DDL, writes no row and takes no lock on any table;
-- it reads the catalogue and the one row. The only statements outside a
-- guard are BEGIN, the four SET LOCAL lines, the guard blocks themselves and
-- COMMIT.
--
-- POST-CHECK. The FAQ block reads the row back after its step, and a last
-- block reads back the three tables' comments: exactly one message 1 row
-- holding the new text, and all three tables carrying this file's mark.
-- Anything else aborts the file, naming what it found.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

-- The session's temporary schema goes last in search_path for this
-- transaction, or the file refuses (SEARCH PATH above).
DO $m427path$
DECLARE
  new_path text;
BEGIN
  IF current_schema() IS NULL THEN
    RAISE EXCEPTION '427: search_path names no schema to create in (found: %)',
      current_setting('search_path');
  END IF;
  IF position('pg_temp' IN lower(current_setting('search_path'))) > 0 THEN
    RAISE EXCEPTION '427: search_path names pg_temp (found: %)', current_setting('search_path');
  END IF;
  new_path := set_config('search_path', current_setting('search_path') || ', pg_temp', true);
END $m427path$;

-- The three tables: created and marked, or found marked, or refused (CREATE
-- OR REFUSE above).
DO $m427tables$
DECLARE
  mark CONSTANT text := 'alt signals, DDL sha256 64a8ef1a6824e3a6135e0630e8b85c5f835d6ebbe9560497a6f408dfba6f4dc2';
  taken text;
  found text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname IN ('steam_signin_facts', 'steam_family_shares', 'conn_markers')) THEN
    SELECT string_agg(x.name, ', ' ORDER BY x.name) INTO taken
      FROM (SELECT c.relname::text AS name
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = current_schema()
               AND c.relname IN ('steam_signin_facts_pkey', 'ix_steam_signin_facts_last_seen',
                                 'steam_family_shares_pkey', 'ix_steam_family_shares_owner',
                                 'ix_steam_family_shares_last_seen', 'conn_markers_pkey',
                                 'ix_conn_markers_addr', 'ix_conn_markers_block',
                                 'ix_conn_markers_last_at')
            UNION ALL
            SELECT t.typname::text
              FROM pg_type t
              JOIN pg_namespace n ON n.oid = t.typnamespace
             WHERE n.nspname = current_schema()
               AND t.typname IN ('steam_signin_facts', 'steam_family_shares', 'conn_markers')) x;
    IF taken IS NOT NULL THEN
      RAISE EXCEPTION '427: a name this file creates already stands in schema % (found: %)',
        current_schema(), taken;
    END IF;
    -- DDL START
    CREATE TABLE steam_signin_facts (
      steam_id                   TEXT        NOT NULL,
      first_seen_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
      last_seen_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
      copy_state                 VARCHAR(8)  NOT NULL DEFAULT 'unknown',
      shared_first_at            TIMESTAMPTZ NULL DEFAULT NULL,
      shared_last_at             TIMESTAMPTZ NULL DEFAULT NULL,
      vac_banned                 BOOLEAN     NULL DEFAULT NULL,
      vac_banned_first_at        TIMESTAMPTZ NULL DEFAULT NULL,
      vac_banned_last_at         TIMESTAMPTZ NULL DEFAULT NULL,
      publisher_banned           BOOLEAN     NULL DEFAULT NULL,
      publisher_banned_first_at  TIMESTAMPTZ NULL DEFAULT NULL,
      publisher_banned_last_at   TIMESTAMPTZ NULL DEFAULT NULL,
      over_limit_days            INTEGER     NOT NULL DEFAULT 0,
      over_limit_day             DATE        NULL DEFAULT NULL,
      CONSTRAINT steam_signin_facts_pkey PRIMARY KEY (steam_id),
      CONSTRAINT ck_steam_signin_facts_steam_id CHECK (steam_id ~ '^[0-9]{1,20}$'),
      CONSTRAINT ck_steam_signin_facts_copy_state CHECK (copy_state IN ('own', 'shared', 'unknown')),
      CONSTRAINT ck_steam_signin_facts_seen CHECK (last_seen_at >= first_seen_at),
      CONSTRAINT ck_steam_signin_facts_shared CHECK ((shared_first_at IS NULL) = (shared_last_at IS NULL) AND shared_last_at >= shared_first_at),
      CONSTRAINT ck_steam_signin_facts_vac CHECK ((vac_banned_first_at IS NULL) = (vac_banned_last_at IS NULL) AND vac_banned_last_at >= vac_banned_first_at),
      CONSTRAINT ck_steam_signin_facts_publisher CHECK ((publisher_banned_first_at IS NULL) = (publisher_banned_last_at IS NULL) AND publisher_banned_last_at >= publisher_banned_first_at),
      CONSTRAINT ck_steam_signin_facts_over_limit CHECK (over_limit_days >= 0 AND (over_limit_days = 0) = (over_limit_day IS NULL))
    );
    CREATE INDEX ix_steam_signin_facts_last_seen ON steam_signin_facts (last_seen_at);
    CREATE TABLE steam_family_shares (
      steam_id       TEXT        NOT NULL,
      key_id         TEXT        NOT NULL,
      owner_mark     BYTEA       NOT NULL,
      first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
      last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT steam_family_shares_pkey PRIMARY KEY (steam_id, key_id, owner_mark),
      CONSTRAINT ck_steam_family_shares_steam_id CHECK (steam_id ~ '^[0-9]{1,20}$'),
      CONSTRAINT ck_steam_family_shares_key_id CHECK (key_id ~ '^[0-9a-f]{12}$'),
      CONSTRAINT ck_steam_family_shares_owner_mark CHECK (octet_length(owner_mark) = 32),
      CONSTRAINT ck_steam_family_shares_seen CHECK (last_seen_at >= first_seen_at)
    );
    CREATE INDEX ix_steam_family_shares_owner ON steam_family_shares (key_id, owner_mark);
    CREATE INDEX ix_steam_family_shares_last_seen ON steam_family_shares (last_seen_at);
    CREATE TABLE conn_markers (
      steam_id    TEXT        NOT NULL,
      day         DATE        NOT NULL DEFAULT CAST((now() AT TIME ZONE 'UTC') AS date),
      key_id      TEXT        NOT NULL,
      addr_mark   BYTEA       NOT NULL,
      block_mark  BYTEA       NOT NULL,
      family      SMALLINT    NOT NULL,
      conn_class  VARCHAR(8)  NOT NULL DEFAULT 'unknown',
      first_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
      last_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT conn_markers_pkey PRIMARY KEY (steam_id, day, key_id, addr_mark),
      CONSTRAINT ck_conn_markers_steam_id CHECK (steam_id ~ '^[0-9]{1,20}$'),
      CONSTRAINT ck_conn_markers_key_id CHECK (key_id ~ '^[0-9a-f]{12}$'),
      CONSTRAINT ck_conn_markers_addr_mark CHECK (octet_length(addr_mark) = 32),
      CONSTRAINT ck_conn_markers_block_mark CHECK (octet_length(block_mark) = 32),
      CONSTRAINT ck_conn_markers_family CHECK (family IN (4, 6)),
      CONSTRAINT ck_conn_markers_conn_class CHECK (conn_class IN ('none', 'hosting', 'vpn', 'relay', 'tor', 'unknown')),
      CONSTRAINT ck_conn_markers_seen CHECK (last_at >= first_at)
    );
    CREATE INDEX ix_conn_markers_addr ON conn_markers (key_id, addr_mark, day, steam_id);
    CREATE INDEX ix_conn_markers_block ON conn_markers (key_id, block_mark, day, steam_id);
    CREATE INDEX ix_conn_markers_last_at ON conn_markers (last_at);
    -- DDL END
    EXECUTE format('COMMENT ON TABLE steam_signin_facts IS %L', mark);
    EXECUTE format('COMMENT ON TABLE steam_family_shares IS %L', mark);
    EXECUTE format('COMMENT ON TABLE conn_markers IS %L', mark);
  ELSE
    SELECT string_agg(format('%s %s', w.name, coalesce((
             SELECT CASE WHEN c.relkind <> 'r' THEN 'not a table'
                         WHEN obj_description(c.oid, 'pg_class') = mark THEN 'marked'
                         ELSE 'unmarked' END
               FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = current_schema() AND c.relname = w.name), 'absent')),
           ', ' ORDER BY w.name)
      INTO found
      FROM (VALUES ('conn_markers'), ('steam_family_shares'), ('steam_signin_facts')) AS w(name);
    IF found IS DISTINCT FROM 'conn_markers marked, steam_family_shares marked, steam_signin_facts marked' THEN
      RAISE EXCEPTION '427: conn_markers, steam_family_shares and steam_signin_facts are neither all absent nor all marked by this file (found: %)',
        found;
    END IF;
  END IF;
END $m427tables$;

-- FAQ message 1: revised once, found revised, or refused (THE FAQ ROW above).
DO $m427faq$
DECLARE
  was CONSTANT text := $faq1was$**INSTALLING THE MOD**

**Option A — the installer (recommended)**
1. Grab `CompetitiveRoundsInstaller.exe` from the pinned post in #releases.
2. Close ROUNDS, run the installer. It finds your Steam ROUNDS install automatically and sets up BepInEx + the mod.
3. Launch ROUNDS. You'll see a consent prompt on first launch — the mod is online-only, so it needs a yes to track your matches.

**Option B — Thunderstore / r2modman**
1. Install "SidsCompetitiveRounds" through r2modman or the Thunderstore app (it pulls BepInEx automatically).
2. **Launch through the mod manager**, not plain Steam.
3. Updates come from the mod manager — it will NOT self-update like the installer version.

**Requirements**
- ROUNDS on Steam (current version 1.1.2), Windows. Mac isn't supported.
- **No other mods.** This is a competitive mod — if it detects any other plugin at launch it disables itself to keep matches fair. Uninstall other mods (or use a clean r2modman profile with only this mod).

Press **F5** in-game to open the competitive menu. That's the hub for everything: queue, stats, leaderboard, shop, settings.$faq1was$;
  want CONSTANT text := $faq1$**INSTALLING THE MOD**

**Option A — the installer (recommended)**
1. Grab `CompetitiveRoundsInstaller.exe` from the pinned post in #releases.
2. Close ROUNDS, run the installer. It finds your Steam ROUNDS install automatically and sets up BepInEx + the mod.
3. Launch ROUNDS. You'll see a consent prompt on first launch — the mod is online-only, so it needs a yes to track your matches.

**Option B — Thunderstore / r2modman**
1. Install "SidsCompetitiveRounds" through r2modman or the Thunderstore app (it pulls BepInEx automatically).
2. **Launch through the mod manager**, not plain Steam.
3. Updates come from the mod manager — it will NOT self-update like the installer version.

**Requirements**
- ROUNDS on Steam (current version 1.1.2), Windows. Mac isn't supported.
- **No other mods.** This is a competitive mod — if it detects any other plugin at launch it disables itself to keep matches fair. Uninstall other mods (or use a clean r2modman profile with only this mod).

Press **F5** in-game to open the competitive menu. That's the hub for everything: queue, stats, leaderboard, shop, settings.

**What the server may record at sign-in, for fair-play review:** what Steam reports about your account, namely whether your copy of ROUNDS is owned or borrowed through Steam Family Sharing (for a borrowed copy, a keyed one-way code of the lending account, never its id) and whether the account has a VAC ban or a game ban; and from your connection, keyed one-way codes of your internet address and of its network block (never the address itself), whether it is IPv4 or IPv6, and its connection class, such as VPN or hosting. With these go the times each was first and last seen, and on how many days a storage limit was reached. Each record is deleted no later than 90 days after it was last seen, and at once if you delete your account.$faq1$;
  rows_all integer;
  rows_was integer;
  rows_want integer;
BEGIN
  SELECT count(*), count(*) FILTER (WHERE p.content = was), count(*) FILTER (WHERE p.content = want)
    INTO rows_all, rows_was, rows_want
    FROM pending_channel_posts p
   WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1;
  IF rows_all = 1 AND rows_was = 1 THEN
    UPDATE pending_channel_posts p
       SET content = want,
           revision = p.revision + 1
     WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1 AND p.content = was;
  ELSIF NOT (rows_all = 1 AND rows_want = 1) THEN
    RAISE EXCEPTION '427: FAQ message 1 is not exactly one row holding the text 338 wrote or the text this file writes (rows %, holding 338''s text %, holding this file''s text %)',
      rows_all, rows_was, rows_want;
  END IF;
  -- Post-check of the row (POST-CHECK above).
  SELECT count(*), count(*) FILTER (WHERE p.content = want)
    INTO rows_all, rows_want
    FROM pending_channel_posts p
   WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1;
  IF rows_all <> 1 OR rows_want <> 1 THEN
    RAISE EXCEPTION '427: post-check: FAQ message 1 rows %, holding this file''s text %', rows_all, rows_want;
  END IF;
END $m427faq$;

DO $m427check$
DECLARE
  mark CONSTANT text := 'alt signals, DDL sha256 64a8ef1a6824e3a6135e0630e8b85c5f835d6ebbe9560497a6f408dfba6f4dc2';
  found text;
BEGIN
  SELECT string_agg(format('%s %s', w.name, coalesce((
           SELECT CASE WHEN c.relkind <> 'r' THEN 'not a table'
                       WHEN obj_description(c.oid, 'pg_class') = mark THEN 'marked'
                       ELSE 'unmarked' END
             FROM pg_class c
             JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = w.name), 'absent')),
         ', ' ORDER BY w.name)
    INTO found
    FROM (VALUES ('conn_markers'), ('steam_family_shares'), ('steam_signin_facts')) AS w(name);
  IF found IS DISTINCT FROM 'conn_markers marked, steam_family_shares marked, steam_signin_facts marked' THEN
    RAISE EXCEPTION '427: post-check: the three tables are not all marked (found: %)', found;
  END IF;
END $m427check$;

COMMIT;
