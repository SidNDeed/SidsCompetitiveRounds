-- 336_bug_reports_kind.sql
--
-- bug_reports.kind — what put this row here (v1.41.0 Item 3, 2026-09-18).
--
--   'report'  a player filed it from the F5 bug form. Every row that exists
--             today is one of these, and nothing about them changes.
--   'auto'    the opt-in automatic post-match log upload wrote it
--             (POST /api/v1/logs/auto, backend/api/auto_logs.py).
--
-- WHY ONE TABLE AND NOT TWO. An auto upload is the same artifact as a bug
-- report's attachment: the same bundle, the same gzipped blob under
-- BUG_REPORT_LOG_DIR, the same admin detail view, the same read-time scrub,
-- the same ops `bug-log:N` verb. A separate table would have needed a second
-- copy of every one of those readers. One column and one discriminator
-- instead.
--
-- NUMBERING. 336 is inside the 330-339 block the v1.41.0 batch reserved.
-- 331, 332, 337 and 338 belong to other items in the same batch; the highest
-- number merged in main is 325.
--
-- WHAT DEPENDS ON THIS COLUMN, i.e. what breaks if the code deploys first.
-- Enumerated as WRITERS and READERS, because a deploy-order note that lists
-- only readers has already been wrong here once (#346):
--
--   WRITER  auto_logs.upload_auto_log        INSERT ... kind = 'auto'
--   WRITER  auto_logs.prune_auto_logs        DELETE ... WHERE kind = 'auto'
--   READER  main.submit_bug_report           the 10/24h count, now scoped to
--                                            kind = 'report' so automatic
--                                            uploads cannot spend a player's
--                                            report budget
--   READER  main.recent_bug_reports          the Discord #bug-reports feed,
--                                            now scoped to kind = 'report' so
--                                            automatic uploads are silent
--
-- The two READERS are on paths players and the bot use every day, so this
-- file MUST be applied before the code SHA that carries them — the ordinary
-- two-SHA order for this batch (migration precursor, then code). It is
-- otherwise safe to apply at any time and to leave applied with no code: the
-- column has a default, every existing row gets 'report', and no current
-- writer names it.
--
-- The ORM does NOT map this column. models.BugReport is deliberately left
-- without it so that submit_bug_report's INSERT keeps working unchanged if
-- this file has not run yet — the conservative direction is that a player can
-- always file a bug. Because an ORM assignment to an undeclared column is a
-- silent no-op rather than an error (#346), the reason is recorded in
-- models.py at the class as well as here, and auto_logs.py writes kind with
-- raw SQL.

BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE bug_reports
    ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'report';

COMMENT ON COLUMN bug_reports.kind IS
    'What created this row: ''report'' = player-filed via the F5 bug form; ''auto'' = opt-in automatic post-match log upload. Retention applies to ''auto'' only.';

-- Redundant on a first run -- ADD COLUMN already set it -- and NOT redundant
-- on any other: ADD COLUMN IF NOT EXISTS is a no-op against a column that is
-- already there, so a re-run over a hand-added or partially-applied column
-- would otherwise leave it with no default at all. The schema default is the
-- ONLY default this column has: models.py deliberately does not map it, so
-- there is no ORM default to disagree with it (which is the direction that
-- once made every auto-created opponent come out ranked).
ALTER TABLE bug_reports ALTER COLUMN kind SET DEFAULT 'report';

-- Only two values are meant to exist. A third arriving from a typo would be
-- invisible: it would simply fall out of both the report feed and the auto
-- retention sweep, i.e. a row nobody announces and nobody ever deletes.
ALTER TABLE bug_reports DROP CONSTRAINT IF EXISTS bug_reports_kind_known;
ALTER TABLE bug_reports ADD CONSTRAINT bug_reports_kind_known
    CHECK (kind IN ('report', 'auto'));

-- The two questions asked of this column, both of them with a time bound:
-- "which auto rows are older than the retention window" (the sweep) and
-- "which report rows are new" (the feed and the admin list). One composite
-- index serves both. Built in-transaction and therefore NOT CONCURRENTLY,
-- which holds a write lock on bug_reports for the build: the table is a few
-- thousand player-filed rows, so that is milliseconds, and CONCURRENTLY is
-- not available inside the BEGIN/COMMIT this file needs (#340).
CREATE INDEX IF NOT EXISTS idx_bug_reports_kind_created
    ON bug_reports (kind, created_at DESC);

-- The per-steam bucket the auto route counts against: (steam_id, kind) with
-- the timestamp, so the 24 h count is an index-only range and does not walk
-- a player's whole report history.
CREATE INDEX IF NOT EXISTS idx_bug_reports_steam_kind_created
    ON bug_reports (steam_id, kind, created_at DESC);

-- Post-check: assert the END STATE, not that the statements above parsed.
DO $m336$
DECLARE
    v_default TEXT;
    v_notnull BOOLEAN;
    v_unlabelled BIGINT;
BEGIN
    SELECT column_default, (is_nullable = 'NO')
      INTO v_default, v_notnull
      FROM information_schema.columns
     WHERE table_schema = current_schema()
       AND table_name = 'bug_reports' AND column_name = 'kind';

    IF v_default IS NULL THEN
        RAISE EXCEPTION '336: bug_reports.kind is absent or has no default; the auto-upload route would insert rows the report feed cannot distinguish';
    END IF;
    -- column_default renders as 'report'::character varying, so the test is
    -- on the literal at the head and not a substring anywhere in it.
    IF v_default NOT LIKE '''report''%' THEN
        RAISE EXCEPTION '336: bug_reports.kind defaults to % and not to ''report''; every new player-filed report would be mislabelled', v_default;
    END IF;
    IF NOT v_notnull THEN
        RAISE EXCEPTION '336: bug_reports.kind is nullable; a NULL row matches neither the report feed nor the auto retention sweep';
    END IF;

    -- Every row carries a value the two consumers recognise. Stated as a
    -- membership test and NOT as "every row is 'report'": on the first run
    -- that is the same assertion, but this file could be re-applied after the
    -- auto route has landed rows, and a post-check that fails on a legitimate
    -- re-run is a trap rather than a guarantee.
    SELECT COUNT(*) INTO v_unlabelled FROM bug_reports WHERE kind IS NULL OR kind NOT IN ('report', 'auto');
    IF v_unlabelled > 0 THEN
        RAISE EXCEPTION '336: % bug_reports row(s) carry a kind that is neither ''report'' nor ''auto''; such a row is announced by nothing and collected by nothing', v_unlabelled;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = 'bug_reports' AND indexname = 'idx_bug_reports_kind_created') THEN
        RAISE EXCEPTION '336: idx_bug_reports_kind_created is missing; the retention sweep would seq-scan bug_reports';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = 'bug_reports' AND indexname = 'idx_bug_reports_steam_kind_created') THEN
        RAISE EXCEPTION '336: idx_bug_reports_steam_kind_created is missing; the per-steam auto bucket would seq-scan bug_reports';
    END IF;

    RAISE NOTICE '336: bug_reports.kind present, NOT NULL, default ''report''; % row(s) report, % auto; both indexes present',
        (SELECT COUNT(*) FROM bug_reports WHERE kind = 'report'),
        (SELECT COUNT(*) FROM bug_reports WHERE kind = 'auto');
END $m336$;

COMMIT;
