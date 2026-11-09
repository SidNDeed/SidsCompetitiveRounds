-- rollback_404_player_reports.sql
--
-- Removes what 404_player_reports.sql added: the tables player_report_logs and
-- player_reports with every report and attached log stored in them, and the
-- runtime_settings row player_reports_accept. No other object references the
-- two tables. Re-runnable: every DROP is IF EXISTS and the DELETE of an absent
-- row deletes nothing.
--
-- THE SETTINGS ROW IS DELETED WHATEVER ITS VALUE. The key has no reader
-- without this lane, so an operator's '0' is not kept across a rollback; a
-- later forward run writes '1' again.
--
-- DEPLOY ORDER: THE API FIRST. Deploy an api build without this lane (one that
-- does not mount the player_reports router and whose delete_player_data does
-- not name player_reports), then run this file. An api that still names the
-- tables answers 500 on the five player-report routes and fails every account
-- deletion once the tables are gone.
--
-- Each DROP takes ACCESS EXCLUSIVE on its table for the drop itself, which is
-- short; `lock_timeout` bounds how long the file waits to start it, and a
-- timeout rolls the whole file back with nothing dropped.

BEGIN;
SET LOCAL lock_timeout = '5s';

DROP TABLE IF EXISTS player_report_logs;
DROP TABLE IF EXISTS player_reports;
DELETE FROM runtime_settings WHERE key = 'player_reports_accept';

COMMIT;
