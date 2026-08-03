-- 185: localized release notes.
--
-- Sid, 2026-08-03: "for the mod update text, i'd like you to do your best
-- translation of each update as they're released (make it part of the flow)
-- and have that show for those language players."
--
-- The client reads release notes straight from the GitHub API, which only
-- ever has the English text. This table is an OVERLAY keyed by release tag:
-- the client asks for its locale, and any tag without a row simply keeps the
-- English body. That degrade-to-English behaviour is the whole point — a
-- missing translation must never blank the release notes.
--
-- NOT stored in i18n_entries: those are keyed by a hash of the source STRING
-- for short UI labels under a propose/approve workflow. Release notes are
-- per-release prose that changes wholesale each version, and they are written
-- by the integrator at ship time rather than proposed by translators.
CREATE TABLE IF NOT EXISTS release_notes_i18n (
    tag             VARCHAR(32)  NOT NULL,
    language_code   VARCHAR(8)   NOT NULL,
    title           TEXT         NOT NULL DEFAULT '',
    body            TEXT         NOT NULL,
    -- 'machine' until a human reviews it. The client labels machine text so a
    -- player knows why the phrasing may be rough (same honesty rule as the
    -- bundled machine-translated UI drafts).
    source          VARCHAR(16)  NOT NULL DEFAULT 'machine',
    translated_by   VARCHAR(20),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tag, language_code)
);

CREATE INDEX IF NOT EXISTS idx_release_notes_i18n_tag
    ON release_notes_i18n (tag);

DO $$
BEGIN
  RAISE NOTICE 'migration 185 OK: release_notes_i18n ready';
END $$;
