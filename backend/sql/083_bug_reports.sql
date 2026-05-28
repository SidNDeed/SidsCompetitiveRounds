-- 083_bug_reports.sql
--
-- In-game bug reporting (v1.26.7). Players submit reports through the F5 menu
-- — fields collected: description (required), repro steps, severity, category,
-- mod version, and an optional gzipped log blob persisted to disk at
-- /opt/competitive-rounds/bug-reports/<id>.log (paths are server-managed; the
-- column just stores the relative filename so logs can be rehomed without a
-- schema change). Discord linkage uses the existing players.discord_username.

CREATE TABLE IF NOT EXISTS bug_reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    player_id       UUID REFERENCES players(id) ON DELETE SET NULL,
    steam_id        VARCHAR(32),                          -- denormalized for query speed even after player deletion
    display_name    VARCHAR(64),                          -- snapshot at submit time
    mod_version     VARCHAR(32),
    game_version    VARCHAR(32),
    severity        VARCHAR(16) NOT NULL DEFAULT 'medium', -- low | medium | high | crash
    category        VARCHAR(16) NOT NULL DEFAULT 'other',  -- ui | gameplay | network | other
    description     TEXT NOT NULL,
    repro_steps     TEXT,
    log_filename    VARCHAR(96),                          -- e.g. "f23abc.log"; NULL if user opted out
    log_bytes       INTEGER,                              -- size of stored log file (after gzip), or NULL
    status          VARCHAR(16) NOT NULL DEFAULT 'open',  -- open | triaged | resolved | wontfix | dupe
    triage_notes    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bug_reports_created     ON bug_reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bug_reports_status      ON bug_reports(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bug_reports_steam       ON bug_reports(steam_id);
CREATE INDEX IF NOT EXISTS idx_bug_reports_severity    ON bug_reports(severity, created_at DESC);
