-- 085_bug_report_events.sql
--
-- Activity log for bug reports (v1.26.7+). Captures status changes and
-- comments from human admins + the assistant ("Claude"). Ordered by
-- created_at for the detail view timeline.
--
-- actor identity:
--   actor_steam_id  — set for human admins (from admin_users.steam_id)
--   actor_name      — display label ("Sid", "Claude", "System", etc.)
-- One of the two should be set; both can be set for the human case.

CREATE TABLE IF NOT EXISTS bug_report_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    bug_report_id   UUID NOT NULL REFERENCES bug_reports(id) ON DELETE CASCADE,
    actor_steam_id  VARCHAR(32),
    actor_name      VARCHAR(96) NOT NULL,
    event_type      VARCHAR(24) NOT NULL,  -- comment | status_change | created
    old_status      VARCHAR(16),
    new_status      VARCHAR(16),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bre_report ON bug_report_events(bug_report_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_bre_actor  ON bug_report_events(actor_steam_id);
