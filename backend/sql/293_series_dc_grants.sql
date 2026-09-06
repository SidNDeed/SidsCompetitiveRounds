-- 293: the server's own record of which sitting it last put a pair into.
--
-- A disconnect report names a series. Until now the server decided whether the
-- named series was one the report could be filed against by asking questions
-- about the SERIES ROW -- is it uncompleted, or is it the pair's most recent
-- one, and has anything happened in it lately. Those are questions about
-- recency, and recency is not authority: two players who met, left, and met
-- again were both times "the pair's most recent series" at some point, and a
-- report could be aimed at whichever of them suited it.
--
-- This table records the thing that is actually authoritative: the server put
-- THIS pair into THIS sitting, and here is when it last saw them in it. A
-- report may name the sitting the server most recently put its pair into, and
-- nothing else.
--
-- SHAPE NOTES, each of which is a design decision that cost a review round:
--
--   * Supersession is DERIVED, not stored. There is no `retired_at` column and
--     no partial unique index. Retiring on issue would need an un-retire step
--     when a series RESUMES -- and forgetting that step is a report refused
--     for a sitting the players are demonstrably still in. Instead the newest
--     grant for a pair wins, ordered by (last_seen_at, series_id), and a
--     resume simply re-stamps last_seen_at. Nothing to forget.
--
--   * Which also means issuance never writes an exclusivity constraint, so it
--     cannot raise a unique violation out of the room-issuing transaction and
--     needs no advisory lock on the queue hot path.
--
--   * The tuple comparison (last_seen_at, series_id) makes the order TOTAL.
--     last_seen_at is not unique within one (holder, counterparty): 294 stamps
--     each backfilled sitting with that series' own last activity, and NOW() is
--     the transaction timestamp, so two publishes for a pair in one transaction
--     carry the identical value. A tie makes "no strictly newer grant exists"
--     true of BOTH rows, which is a predicate two sittings can satisfy at once.
--
--   * One row PER DIRECTION. The holder is the player whose report is being
--     judged; the counterparty is the other seat. Both are written together,
--     but they are judged separately, so a lookup never has to know which side
--     of the pair it is on.
--
--   * spent_at is written when a report is accepted against the grant. It is
--     deliberately NOT part of any predicate here: one accepted report per
--     (series, leaver) is already enforced by uq_dc_event_series_player, and a
--     second bound that can disagree with the first is a second thing to keep
--     correct. It exists so the question "was this grant ever used" has an
--     answer in the data rather than in a join.
--
-- ON DELETE CASCADE on all three FKs: a grant is meaningless without its
-- players and its series, and it carries nothing that must outlive them.

CREATE TABLE IF NOT EXISTS series_dc_grants (
    holder_id       UUID        NOT NULL REFERENCES players(id)       ON DELETE CASCADE,
    counterparty_id UUID        NOT NULL REFERENCES players(id)       ON DELETE CASCADE,
    series_id       UUID        NOT NULL REFERENCES ranked_series(id) ON DELETE CASCADE,
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    spent_at        TIMESTAMPTZ,
    PRIMARY KEY (holder_id, series_id)
);

-- The one lookup this table exists for: "the newest grant for this pair", and
-- the supersession NOT EXISTS that asks the same question from inside the
-- eligibility predicate.
--
-- Leading columns are the equality terms, then the sort key in the DIRECTIONS
-- the query reads it: `ORDER BY last_seen_at DESC, series_id DESC`. Both
-- descending, and that is not decoration. An index scan satisfies an ORDER BY
-- forwards, or backwards with every direction reversed; a trailing ASC column
-- here would give (DESC, ASC), whose reverse is (ASC, DESC), and neither is
-- what the resolver asks for -- so the planner would sort and the comment
-- claiming a match would be false.
CREATE INDEX IF NOT EXISTS ix_grant_pair_seen
    ON series_dc_grants (holder_id, counterparty_id, last_seen_at DESC, series_id DESC);

-- Reached only by the ON DELETE CASCADE from ranked_series and by the backfill
-- in 294; without it a series delete sequential-scans this table.
CREATE INDEX IF NOT EXISTS ix_grant_series
    ON series_dc_grants (series_id);

COMMENT ON TABLE series_dc_grants IS
    'Which sitting the server last put a pair into. A disconnect report may '
    'name the newest grant for its pair and nothing else. Supersession is '
    'derived from (last_seen_at, series_id), never stored.';
