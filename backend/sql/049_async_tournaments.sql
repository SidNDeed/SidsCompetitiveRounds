-- ============================================================
-- Phase 2 — async tournaments (double-elim BO3, 7-day match deadlines)
-- ============================================================
-- Adds:
--   tournament_matches.deadline_at    TIMESTAMPTZ — per-match deadline for
--     async tournaments. Past this, the no-show forfeit logic in the tick
--     awards the match to whichever player has a fresher ready_at (or a
--     coin-flip-ish deterministic tiebreak on mutual no-shows).
--
-- No changes to bracket_side: already a VARCHAR(4) with no CHECK constraint,
-- so the existing column accepts 'W', 'TP', 'L', 'GF', 'GF_RESET' without
-- any migration.
-- Classification: additive-safe.
-- ============================================================

ALTER TABLE tournament_matches
    ADD COLUMN IF NOT EXISTS deadline_at TIMESTAMPTZ;

-- prereq_roles: per-prereq tag of 'W' (take winner) or 'L' (take loser). Needed
-- for double-elim losers bracket matches, which pair [winner of earlier LB match]
-- with [loser of WB match]. For single-elim W/TP matches this stays empty —
-- activate logic falls back to the old bracket_side-based defaults.
ALTER TABLE tournament_matches
    ADD COLUMN IF NOT EXISTS prereq_roles VARCHAR(2)[] NOT NULL DEFAULT '{}';

-- Verification:
--   \d+ tournament_matches
