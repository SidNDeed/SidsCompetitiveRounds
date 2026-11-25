-- rollback_427_alt_signals.sql
--
-- Reverses migration 427: drops steam_signin_facts, steam_family_shares and
-- conn_markers where they carry 427's mark, and puts FAQ message 1 back to
-- the text 338 wrote, moving its revision by one so the bot edits the posted
-- message again.
--
-- ORDER: the api goes first. Deploy the previous api, which never names the
-- three tables, and then apply this file. (An api of 427's build against a
-- schema without the tables records nothing: its recording fails inside its
-- guard, and its notice check finds no paragraph once message 1 is back.)
--
-- What this loses: every row the three tables hold. Nothing else refers to
-- them.
--
-- HOLDING BOUND. As 427, per statement and per pause: each statement's own
-- statement_timeout (25 s) and each pause's
-- idle_in_transaction_session_timeout (5 s); PostgreSQL 16 has no limit for
-- a whole transaction, and none is claimed. Over this file's counted
-- statements (three DO blocks, four pauses from the last SET line to
-- COMMIT) the sum enforced is 3 x 25 s + 4 x 5 s = 95 s, plus the
-- COMMIT's own flush, which no timeout covers; synchronous_commit = local
-- keeps that flush on this server.
--
-- REFUSALS. A table of one of the three names that is not an ordinary table
-- or does not carry 427's mark makes the file raise before it drops
-- anything. FAQ message 1 must be exactly one row holding 427's text (it is
-- set back) or exactly one row holding 338's text (nothing to do); anything
-- else raises, so a later revision of message 1 is never overwritten. The
-- file is therefore valid while 427 is the newest file carrying message 1:
-- with 431 applied, rollback_431 runs first.
--
-- RE-RUNS. A second run finds the tables absent and message 1 at 338's text:
-- it drops nothing and writes nothing.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r427path$
DECLARE
  new_path text;
BEGIN
  IF current_schema() IS NULL THEN
    RAISE EXCEPTION 'rollback 427: search_path names no schema (found: %)',
      current_setting('search_path');
  END IF;
  IF position('pg_temp' IN lower(current_setting('search_path'))) > 0 THEN
    RAISE EXCEPTION 'rollback 427: search_path names pg_temp (found: %)', current_setting('search_path');
  END IF;
  new_path := set_config('search_path', current_setting('search_path') || ', pg_temp', true);
END $r427path$;

DO $r427tables$
DECLARE
  mark CONSTANT text := 'alt signals, DDL sha256 64a8ef1a6824e3a6135e0630e8b85c5f835d6ebbe9560497a6f408dfba6f4dc2';
  found text;
  t text;
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
  IF found ~ '(unmarked|not a table)' THEN
    RAISE EXCEPTION 'rollback 427: a table of these names is not 427''s (found: %)', found;
  END IF;
  FOR t IN
    SELECT c.relname::text
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = current_schema()
       AND c.relname IN ('conn_markers', 'steam_family_shares', 'steam_signin_facts')
       AND c.relkind = 'r'
       AND obj_description(c.oid, 'pg_class') = mark
     ORDER BY 1
  LOOP
    EXECUTE format('DROP TABLE %I', t);
  END LOOP;
END $r427tables$;

DO $r427faq$
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
  now_text CONSTANT text := $faq1now$**INSTALLING THE MOD**

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

**What the server may record at sign-in, for fair-play review:** what Steam reports about your account, namely whether your copy of ROUNDS is owned or borrowed through Steam Family Sharing (for a borrowed copy, a keyed one-way code of the lending account, never its id) and whether the account has a VAC ban or a game ban; and from your connection, keyed one-way codes of your internet address and of its network block (never the address itself), whether it is IPv4 or IPv6, and its connection class, such as VPN or hosting. With these go the times each was first and last seen, and on how many days a storage limit was reached. Each record is deleted no later than 90 days after it was last seen, and at once if you delete your account.$faq1now$;
  rows_all integer;
  rows_was integer;
  rows_now integer;
  rows_set integer;
  final_text text;
BEGIN
  -- The row is locked before it is read (finding R2-1). A writer that holds
  -- it makes this wait, for at most the lock_timeout set above (5 s): when
  -- the writer ends within it, this reads what the writer committed; past
  -- it, this statement fails, the transaction aborts and nothing changes.
  PERFORM 1 FROM pending_channel_posts p
   WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1
     FOR NO KEY UPDATE;
  SELECT count(*), count(*) FILTER (WHERE p.content = now_text), count(*) FILTER (WHERE p.content = was)
    INTO rows_all, rows_now, rows_was
    FROM pending_channel_posts p
   WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1;
  IF rows_all = 1 AND rows_now = 1 THEN
    UPDATE pending_channel_posts p
       SET content = was,
           revision = p.revision + 1
     WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1 AND p.content = now_text;
    GET DIAGNOSTICS rows_set = ROW_COUNT;
    IF rows_set <> 1 THEN
      RAISE EXCEPTION 'rollback 427: FAQ message 1: % rows changed, not one', rows_set;
    END IF;
  ELSIF NOT (rows_all = 1 AND rows_was = 1) THEN
    RAISE EXCEPTION 'rollback 427: FAQ message 1 is not exactly one row holding 427''s text or 338''s text (rows %, holding 427''s text %, holding 338''s text %)',
      rows_all, rows_now, rows_was;
  END IF;
  -- The final text, read back in the same transaction.
  SELECT min(p.content), count(*) INTO final_text, rows_all
    FROM pending_channel_posts p
   WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1;
  IF rows_all <> 1 OR final_text IS DISTINCT FROM was THEN
    RAISE EXCEPTION 'rollback 427: post-check: FAQ message 1 rows %, holding 338''s text %',
      rows_all, (final_text IS NOT DISTINCT FROM was);
  END IF;
END $r427faq$;

COMMIT;
