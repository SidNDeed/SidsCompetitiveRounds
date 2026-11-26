-- 431_ban_links.sql
--
-- Records kept for an account under an active ban: the rough region of a
-- verified connection, and the pairs of a banned account and another account
-- that recorded the same address code, so that an admin is told of each pair
-- once. The api writes them only at a verified sign-in of an account under an
-- active ban (the region) or from the recorded codes (the pairs), only while
-- the alternate-account lane's signal key is loaded, and only while the FAQ
-- notice this file schedules is posted and acknowledged. A region row is
-- deleted at the first retention pass after its account's ban has ended; a
-- pair when the ban of its banned account has ended (an unposted pair also
-- once its other account has no marker left; a posted one stays while the
-- ban stands), and both at once with the deletion of either account.
--
--   ban_regions                    NEW table, one row per account, region and
--                                  connection class: the region in plain words
--                                  (a country, or a country and its first
--                                  subdivision; never a city, a postcode or a
--                                  coordinate), the connection class word, and
--                                  the first and last sign-in that read it.
--   ix_ban_regions_last_at         (last_at): retention's delete.
--   ban_link_notices               NEW table, one row per pair of a banned
--                                  account and another account: when the pair
--                                  was found, and when its admin notice was
--                                  posted (NULL until then). It holds no
--                                  connection fact: the day, the class and the
--                                  count are read when the notice is written.
--   ix_ban_link_notices_other      (other_steam_id): deletion of the other
--                                  account.
--   ix_ban_link_notices_unposted   (noticed_at) WHERE posted_at IS NULL: the
--                                  notice pass's queue.
--   pending_channel_posts          FAQ message 1 (the FAQ channel's row with
--                                  sort_order 1) gains one closing sentence
--                                  after the paragraph 427 added, saying what
--                                  is recorded for a banned account; its
--                                  revision moves by one, so the bot edits the
--                                  posted message and acknowledges that
--                                  revision.
--
-- No column holds an address, a code of an account's own id, or a city; no
-- table has a foreign key (427's reasons: no players row is needed).
--
-- FAQ message 1 holds 1995 of Discord's 2000 characters after this file: the
-- next change of message 1 must take words out before it adds any.
--
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND; 427 BEFORE THIS FILE.
-- -------------------------------------------------------------------
-- The api build carrying this change writes the two tables, deletes from them
-- in account deletion and in its retention pass, and reads FAQ message 1 for
-- both sentences before it records anything for a banned account. So the
-- file lands first: the migrate verb applies it on the primary, the standby
-- receives it by streaming replication, and only then does the code deploy.
-- The previous api build runs on the migrated schema unchanged: it never
-- names the new tables, and its own notice check still finds 427's paragraph,
-- which message 1 keeps word for word.
--
-- 427 AND THIS FILE ON ONE DAY. This file requires message 1 at 427's text
-- (or at its own), so 427 runs first; in the other order this file raises
-- and changes nothing. The bot may post between the two files or only after
-- both: an acknowledgement of 427's revision is below the row's revision
-- once this file has run, so the row stays pending and is edited forward.
-- 427 run again after this file raises in its FAQ step and changes nothing.
--
-- LOCKS. On a first run the two tables and their indexes are created empty
-- and no other session sees them before COMMIT; they have no foreign keys,
-- so no existing table is locked for them. The FAQ step updates one row of
-- pending_channel_posts: the bot's claim and acknowledgement of that row wait
-- from that statement until COMMIT, and reads do not.
--
-- HOLDING BOUND. lock_timeout bounds how long each step waits to start
-- behind a transaction already in flight. How long this file holds what it
-- took is bounded by the other settings, each per statement or per pause:
-- every statement by its own statement_timeout (25 s) and every pause between
-- two statements by idle_in_transaction_session_timeout (5 s). PostgreSQL 16
-- has no limit for a whole transaction, and none is claimed. Over this
-- file's counted statements (the four DO blocks after the SET lines, and the
-- five pauses from the last SET line to COMMIT) the sum enforced is
-- 4 x 25 s + 5 x 5 s = 125 s, plus the
-- COMMIT's own flush, which no timeout covers; synchronous_commit = local
-- keeps that flush on this server, waiting for no standby. If a setting
-- expires the whole file rolls back with nothing changed and is re-applied.
--
-- CREATE OR REFUSE. The two tables are new and this file alone makes them,
-- so it either creates them or proves they are its own work, and refuses
-- every other state with nothing changed:
--   - neither name stands in the schema: the file creates both, with their
--     keys and indexes, and stamps each with its mark, a table comment
--     holding the SHA-256 of the statements between the DDL START and DDL END
--     lines (comment and blank lines dropped, each line trimmed). A name
--     those statements create that already stands in the schema (an index, a
--     key's index, a table's row type) refuses the run before any of them;
--   - both are ordinary tables and both carry exactly that mark: they are
--     this file's own committed work, and the file issues nothing for them
--     and takes no lock on them;
--   - anything else refuses: one without the other, either one unmarked or
--     marked otherwise, or either one not an ordinary table.
-- On the create path the applying role creates the tables in this
-- transaction, so it owns them, with the privileges a new table of that role
-- receives: the file grants and revokes nothing. A test recomputes the mark
-- from this text, so the statements between the markers cannot change
-- without the mark.
--
-- SEARCH PATH. As 427: the first block appends pg_temp to search_path for
-- this transaction (set_config, local to it), which puts the temporary
-- schema last, and before it changes anything it refuses a search_path that
-- names no existing schema or that already names pg_temp.
--
-- THE FAQ ROW. The api records nothing for a banned account until FAQ
-- message 1 is exactly one row, its acknowledged revision equals its
-- revision, and its text holds both 427's paragraph and the sentence this
-- file adds. This file therefore requires the row it means:
--   - exactly one FAQ message 1 row, holding the text 427 wrote (carried here
--     as the earlier text): the file sets the new text (docs/FAQ.md's message
--     1 once this change lands: 427's text, one space, the sentence) and
--     moves the revision by one;
--   - exactly one FAQ message 1 row, already holding the new text: a re-run,
--     and the file writes nothing;
--   - anything else, an absent row and 338's text included: the file raises,
--     so nothing it did commits.
--
-- RE-RUNS. A second run finds the two tables marked and the row already
-- revised: it issues no DDL, writes no row, takes no lock on the two new
-- tables and no row lock on the FAQ row; its read of the FAQ table takes
-- the ordinary read lock (ACCESS SHARE) that every SELECT takes. It reads
-- the catalogue and the one row. The only statements outside a
-- guard are BEGIN, the four SET LOCAL lines, the guard blocks themselves and
-- COMMIT.
--
-- POST-CHECK. The FAQ block reads the row back after its step, and a last
-- block reads back the two tables' comments: exactly one message 1 row
-- holding the new text, and both tables carrying this file's mark. Anything
-- else aborts the file, naming what it found.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

-- The session's temporary schema goes last in search_path for this
-- transaction, or the file refuses (SEARCH PATH above).
DO $m431path$
DECLARE
  new_path text;
BEGIN
  IF current_schema() IS NULL THEN
    RAISE EXCEPTION '431: search_path names no schema to create in (found: %)',
      current_setting('search_path');
  END IF;
  IF position('pg_temp' IN lower(current_setting('search_path'))) > 0 THEN
    RAISE EXCEPTION '431: search_path names pg_temp (found: %)', current_setting('search_path');
  END IF;
  new_path := set_config('search_path', current_setting('search_path') || ', pg_temp', true);
END $m431path$;

-- The two tables: created and marked, or found marked, or refused (CREATE
-- OR REFUSE above).
DO $m431tables$
DECLARE
  mark CONSTANT text := 'ban links, DDL sha256 3d65b484efa32db6f13bccb7d0e892239e25bea4cbab88ef487fc68418571734';
  taken text;
  found text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname IN ('ban_regions', 'ban_link_notices')) THEN
    SELECT string_agg(x.name, ', ' ORDER BY x.name) INTO taken
      FROM (SELECT c.relname::text AS name
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = current_schema()
               AND c.relname IN ('ban_regions_pkey', 'ix_ban_regions_last_at',
                                 'ban_link_notices_pkey', 'ix_ban_link_notices_other',
                                 'ix_ban_link_notices_unposted')
            UNION ALL
            SELECT t.typname::text
              FROM pg_type t
              JOIN pg_namespace n ON n.oid = t.typnamespace
             WHERE n.nspname = current_schema()
               AND t.typname IN ('ban_regions', 'ban_link_notices')) x;
    IF taken IS NOT NULL THEN
      RAISE EXCEPTION '431: a name this file creates already stands in schema % (found: %)',
        current_schema(), taken;
    END IF;
    -- DDL START
    CREATE TABLE ban_regions (
      steam_id    TEXT        NOT NULL,
      region      TEXT        NOT NULL,
      conn_class  VARCHAR(8)  NOT NULL DEFAULT 'unknown',
      first_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
      last_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT ban_regions_pkey PRIMARY KEY (steam_id, region, conn_class),
      CONSTRAINT ck_ban_regions_steam_id CHECK (steam_id ~ '^[0-9]{1,20}$'),
      CONSTRAINT ck_ban_regions_region CHECK (char_length(region) BETWEEN 1 AND 130 AND region !~ '[\x01-\x1f\x7f-\x9f]'),
      CONSTRAINT ck_ban_regions_conn_class CHECK (conn_class IN ('none', 'hosting', 'vpn', 'relay', 'tor', 'unknown')),
      CONSTRAINT ck_ban_regions_seen CHECK (last_at >= first_at)
    );
    CREATE INDEX ix_ban_regions_last_at ON ban_regions (last_at);
    CREATE TABLE ban_link_notices (
      banned_steam_id  TEXT        NOT NULL,
      other_steam_id   TEXT        NOT NULL,
      noticed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
      posted_at        TIMESTAMPTZ NULL DEFAULT NULL,
      CONSTRAINT ban_link_notices_pkey PRIMARY KEY (banned_steam_id, other_steam_id),
      CONSTRAINT ck_ban_link_notices_banned_steam_id CHECK (banned_steam_id ~ '^[0-9]{1,20}$'),
      CONSTRAINT ck_ban_link_notices_other_steam_id CHECK (other_steam_id ~ '^[0-9]{1,20}$'),
      CONSTRAINT ck_ban_link_notices_two CHECK (banned_steam_id <> other_steam_id)
    );
    CREATE INDEX ix_ban_link_notices_other ON ban_link_notices (other_steam_id);
    CREATE INDEX ix_ban_link_notices_unposted ON ban_link_notices (noticed_at) WHERE posted_at IS NULL;
    -- DDL END
    EXECUTE format('COMMENT ON TABLE ban_regions IS %L', mark);
    EXECUTE format('COMMENT ON TABLE ban_link_notices IS %L', mark);
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
      FROM (VALUES ('ban_link_notices'), ('ban_regions')) AS w(name);
    IF found IS DISTINCT FROM 'ban_link_notices marked, ban_regions marked' THEN
      RAISE EXCEPTION '431: ban_link_notices and ban_regions are neither both absent nor both marked by this file (found: %)',
        found;
    END IF;
  END IF;
END $m431tables$;

-- FAQ message 1: revised once, found revised, or refused (THE FAQ ROW above).
DO $m431faq$
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

Press **F5** in-game to open the competitive menu. That's the hub for everything: queue, stats, leaderboard, shop, settings.

**What the server may record at sign-in, for fair-play review:** what Steam reports about your account, namely whether your copy of ROUNDS is owned or borrowed through Steam Family Sharing (for a borrowed copy, a keyed one-way code of the lending account, never its id) and whether the account has a VAC ban or a game ban; and from your connection, keyed one-way codes of your internet address and of its network block (never the address itself), whether it is IPv4 or IPv6, and its connection class, such as VPN or hosting. With these go the times each was first and last seen, and on how many days a storage limit was reached. Each record is deleted no later than 90 days after it was last seen, and at once if you delete your account.$faq1was$;
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

**What the server may record at sign-in, for fair-play review:** what Steam reports about your account, namely whether your copy of ROUNDS is owned or borrowed through Steam Family Sharing (for a borrowed copy, a keyed one-way code of the lending account, never its id) and whether the account has a VAC ban or a game ban; and from your connection, keyed one-way codes of your internet address and of its network block (never the address itself), whether it is IPv4 or IPv6, and its connection class, such as VPN or hosting. With these go the times each was first and last seen, and on how many days a storage limit was reached. Each record is deleted no later than 90 days after it was last seen, and at once if you delete your account. For a banned account the server also records the rough region of its connection (country and state) and keeps these records until the ban has ended.$faq1$;
  rows_all integer;
  rows_was integer;
  rows_want integer;
  rows_set integer;
BEGIN
  SELECT count(*), count(*) FILTER (WHERE p.content = was), count(*) FILTER (WHERE p.content = want)
    INTO rows_all, rows_was, rows_want
    FROM pending_channel_posts p
   WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1;
  IF rows_all = 1 AND rows_was = 1 THEN
    -- The write path only (a rerun takes no row lock): lock the row, read
    -- it again under the lock, write it, require exactly one row changed.
    PERFORM 1 FROM pending_channel_posts p
     WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1
       FOR NO KEY UPDATE;
    SELECT count(*), count(*) FILTER (WHERE p.content = was)
      INTO rows_all, rows_was
      FROM pending_channel_posts p
     WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1;
    IF rows_all <> 1 OR rows_was <> 1 THEN
      RAISE EXCEPTION '431: FAQ message 1 changed before it was locked (rows %, holding 427''s text %)',
        rows_all, rows_was;
    END IF;
    UPDATE pending_channel_posts p
       SET content = want,
           revision = p.revision + 1
     WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1 AND p.content = was;
    GET DIAGNOSTICS rows_set = ROW_COUNT;
    IF rows_set <> 1 THEN
      RAISE EXCEPTION '431: FAQ message 1: % rows changed, not one', rows_set;
    END IF;
  ELSIF NOT (rows_all = 1 AND rows_want = 1) THEN
    RAISE EXCEPTION '431: FAQ message 1 is not exactly one row holding the text 427 wrote or the text this file writes (rows %, holding 427''s text %, holding this file''s text %)',
      rows_all, rows_was, rows_want;
  END IF;
  -- Post-check of the row (POST-CHECK above).
  SELECT count(*), count(*) FILTER (WHERE p.content = want)
    INTO rows_all, rows_want
    FROM pending_channel_posts p
   WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1;
  IF rows_all <> 1 OR rows_want <> 1 THEN
    RAISE EXCEPTION '431: post-check: FAQ message 1 rows %, holding this file''s text %', rows_all, rows_want;
  END IF;
END $m431faq$;

DO $m431check$
DECLARE
  mark CONSTANT text := 'ban links, DDL sha256 3d65b484efa32db6f13bccb7d0e892239e25bea4cbab88ef487fc68418571734';
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
    FROM (VALUES ('ban_link_notices'), ('ban_regions')) AS w(name);
  IF found IS DISTINCT FROM 'ban_link_notices marked, ban_regions marked' THEN
    RAISE EXCEPTION '431: post-check: the two tables are not both marked (found: %)', found;
  END IF;
END $m431check$;

COMMIT;
