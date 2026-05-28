-- 086_bug_report_number.sql
--
-- Human-friendly auto-incrementing bug ID. UUIDs are unwieldy in chat —
-- "bug #47" is what people actually quote. Backfills existing rows in
-- created_at order so #1 is the oldest report.

ALTER TABLE bug_reports ADD COLUMN IF NOT EXISTS bug_number BIGINT;

-- Backfill: assign sequential numbers to any rows missing one, ordered by
-- creation time so the numbering is intuitive.
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY created_at) AS rn
      FROM bug_reports
     WHERE bug_number IS NULL
)
UPDATE bug_reports b
   SET bug_number = ranked.rn
  FROM ranked
 WHERE b.id = ranked.id;

-- Sequence picks up where backfill left off so new reports get the next
-- number. Use the max existing value as the starting point.
DO $$
DECLARE
    next_num BIGINT;
BEGIN
    SELECT COALESCE(MAX(bug_number), 0) + 1 INTO next_num FROM bug_reports;
    EXECUTE format('CREATE SEQUENCE IF NOT EXISTS bug_reports_number_seq START WITH %s', next_num);
END
$$;

ALTER TABLE bug_reports
    ALTER COLUMN bug_number SET DEFAULT nextval('bug_reports_number_seq'),
    ALTER COLUMN bug_number SET NOT NULL;

-- Sequence is owned by the column so DROP TABLE will clean it up.
ALTER SEQUENCE bug_reports_number_seq OWNED BY bug_reports.bug_number;

CREATE UNIQUE INDEX IF NOT EXISTS idx_bug_reports_number ON bug_reports(bug_number);
