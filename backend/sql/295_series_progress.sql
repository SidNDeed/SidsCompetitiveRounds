-- 295_series_progress.sql
-- Per-seat attestation that a seat was PRESENT in a sitting, recorded ONLY
-- when the post that carried it was bound to a verified Steam session.
--
-- Why this table exists. A disconnect report increments the accused player's
-- ranked_dc_count, which feeds the public leave-%. What that report is allowed
-- to name is decided by _DC_ELIGIBLE_TERMS, and for a leave during game 1 --
-- where no match row exists yet -- its only evidence used to be
-- ranked_series.live_p1_points / live_p2_points. Those columns are written by
-- POST /api/v1/series/{id}/live-points, which authenticates with a secret every
-- client holds and identifies its author by a QUERY PARAMETER. So the evidence
-- that a sitting happened could be written by the same seat that then filed the
-- report about it. This table records which seat posted, in a way that seat's
-- counterparty cannot forge.
--
-- WHY THERE IS NO session_verified COLUMN. There was one in the first draft,
-- and rows were recorded for unbound posts with it set false. That put the
-- forgery straight back: an unbound row naming a player is a row the OTHER
-- player could have written, and an attestation the counterparty can write is a
-- wrong answer rather than a missing one. Every row here is written by a
-- verified post, so a flag saying so would be true of every row -- and a column
-- that is always true answers nothing. The row's EXISTENCE is the attestation.
--
-- The sparsity that costs (162 of 4663 accounts have ever held a verified
-- session) is handled by the RULE, not by weakening the record: the evidence
-- predicate asks for an attestation only from an account whose
-- players.steam_auth_seen_at is set -- the same monotonic per-account arming
-- _check_steam_session already uses -- and falls back to the pre-M4 rule for
-- every account that cannot yet produce one.
--
-- One row per (surface, subject, player). `surface` names which table
-- subject_id points into: there are three live-points surfaces with three
-- different parent tables (ranked_series, team_series, ffa_lobbies), which is
-- why there is deliberately NO foreign key on subject_id. player_id does carry
-- one, and cascades, because an account deletion must not leave its
-- attestations behind.
--
-- Only the 'ranked' surface has a reader today (the disconnect predicate).
-- 'team' and 'ffa' are recorded so the three surfaces behave identically and so
-- the bet-lock hardening has a record to stand on; that item is filed, not
-- shipped, and this comment is here so nobody reads those rows as load-bearing.
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS series_progress (
    surface       TEXT        NOT NULL,
    subject_id    UUID        NOT NULL,
    player_id     UUID        NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_series_progress PRIMARY KEY (surface, subject_id, player_id),
    CONSTRAINT ck_series_progress_surface
        CHECK (surface IN ('ranked', 'team', 'ffa'))
);

-- The eligibility predicate looks up exactly one row by all three key columns,
-- which the primary key serves. No other access pattern exists. No further
-- index is warranted.
