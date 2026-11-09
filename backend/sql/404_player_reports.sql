-- 404_player_reports.sql
--
-- Ask 14 (the player report form): the store of one player's report about
-- another player of one of the reporter's own recent games, and of the log the
-- reporter chose to attach. The ask 14 design note states each rule (its
-- sections 4 to 6, with the integrator's conditions C1 to C5).
--
--   player_reports       One row per report. reporter_id is the account of the
--                        request's verified session; the request body carries
--                        no reporter. game_kind and game_id name a row of
--                        matches ('1v1'), team_matches ('2v2'), ovt_matches
--                        ('1v2') or ffa_matches ('ffa') that the reporter took
--                        part in, and reported_id is another player of that
--                        game: POST /api/v1/player-reports verifies both before
--                        it writes. There is no foreign key on game_id because
--                        it names one of four tables; game_ended_at is copied
--                        so a list row needs no join to them.
--                        The row holds player ids only. No Steam id and no
--                        display name is copied into it, so an account that is
--                        anonymised in place reads as anonymised here too
--                        (lesson 437); the readers join players.
--   player_report_logs   The attached log, gzipped, at most one row per report,
--                        deleted with its report (ON DELETE CASCADE). It is in
--                        the database, not on the log volume, so it replicates
--                        with its report and the account deletion path reaches
--                        it through the report.
--   runtime_settings     One row, key player_reports_accept, written '1': the
--                        two player routes are ON. With '0', or with no row,
--                        they answer 503 player_reports_off; the admin routes
--                        do not read it. An operator turns the form off with
--                        UPDATE runtime_settings SET value = '0', updated_at =
--                        now() WHERE key = 'player_reports_accept'.
--
-- THE CLOSED LISTS ARE CHECKS. game_kind, reason and status each accept exactly
-- the values backend/api/player_report_rules.py names (GAME_KINDS, REASONS,
-- REPORT_STATUSES); test_player_report_rules.py compares the two.
--
-- ONE REPORT PER REPORTER, GAME AND PLAYER: the UNIQUE constraint
-- player_reports_once. The route reads for an earlier row under the reporter's
-- identity lock and answers 409 already_reported; the constraint is what holds
-- if two requests ever pass that read together. Its index (reporter_id first)
-- also serves the route's count of a reporter's reports in the last 24 hours
-- and the reporter side of the account deletion.
--
-- WHO READS THESE ROWS: the three admin routes under
-- /api/v1/admin/player-reports, each requiring an admin account and an admin
-- signature. No route returns a report to a player, and nothing here is read
-- by the bot.
--
-- ACCOUNT DELETION: delete_player_data deletes every report in which the
-- account is the reporter or the reported player, and clears closed_by where
-- the account closed a report. The ON DELETE clauses below cover a hard delete
-- of a players row only; an account is anonymised in place, so they are not
-- the deletion path.
--
-- LOG RETENTION is a rule of the readers (player_report_rules.log_readable): a
-- log is served until 30 days after its report was closed, or until 90 days
-- after filing while it is open. The rows past that bound are deleted by one
-- statement inside the submit and the close transactions. No GET writes.
--
-- Re-runnable: every CREATE is IF NOT EXISTS and the settings row is written
-- ON CONFLICT DO NOTHING, so a second run changes nothing, and an operator's
-- own value for the key is kept. Nothing existing is altered and no existing
-- table is locked: both tables are new.
-- Rollback: rollback_404_player_reports.sql.

BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS player_reports (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    reporter_id    UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    reported_id    UUID         NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    game_kind      VARCHAR(4)   NOT NULL,
    game_id        UUID         NOT NULL,
    game_ended_at  TIMESTAMPTZ  NOT NULL,
    reason         VARCHAR(16)  NOT NULL,
    details        TEXT         NOT NULL DEFAULT '',
    status         VARCHAR(12)  NOT NULL DEFAULT 'open',
    closed_by      UUID         NULL REFERENCES players(id) ON DELETE SET NULL,
    closed_at      TIMESTAMPTZ  NULL,
    close_note     TEXT         NOT NULL DEFAULT '',
    CONSTRAINT player_reports_two_players CHECK (reporter_id <> reported_id),
    CONSTRAINT player_reports_kind CHECK (game_kind IN ('1v1', '2v2', '1v2', 'ffa')),
    CONSTRAINT player_reports_reason CHECK (reason IN
        ('cheating', 'harassment', 'griefing', 'leaving', 'name', 'other')),
    CONSTRAINT player_reports_details_len CHECK (char_length(details) <= 1000),
    CONSTRAINT player_reports_status CHECK (status IN ('open', 'dismissed', 'actioned')),
    CONSTRAINT player_reports_closed CHECK ((status = 'open') = (closed_at IS NULL)),
    CONSTRAINT player_reports_note_len CHECK (char_length(close_note) <= 500),
    CONSTRAINT player_reports_once UNIQUE (reporter_id, game_kind, game_id, reported_id)
);
-- The admin list: open first, newest first, optionally one status.
CREATE INDEX IF NOT EXISTS ix_player_reports_status_time
    ON player_reports (status, created_at DESC);
-- The list's count of distinct reporters who named a player in 30 days, and
-- the reported side of the account deletion.
CREATE INDEX IF NOT EXISTS ix_player_reports_reported_time
    ON player_reports (reported_id, created_at);

CREATE TABLE IF NOT EXISTS player_report_logs (
    report_id  UUID         PRIMARY KEY REFERENCES player_reports(id) ON DELETE CASCADE,
    gz         BYTEA        NOT NULL,
    raw_chars  INTEGER      NOT NULL,
    stored_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT player_report_logs_size CHECK (octet_length(gz) <= 4000000 AND raw_chars >= 0)
);
-- gz is already compressed: keep it out of line with no second compression pass.
ALTER TABLE player_report_logs ALTER COLUMN gz SET STORAGE EXTERNAL;

-- C1: the switch's row, with its value spelled out. ON.
INSERT INTO runtime_settings (key, value) VALUES ('player_reports_accept', '1')
ON CONFLICT (key) DO NOTHING;

COMMIT;
