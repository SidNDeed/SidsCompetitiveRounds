-- 227: Admin record-removal (Sid, Aug 18: "build a tool for admins to be
-- able to remove records (like ones cheated in)").
--
-- Records are MATCH-derived, so removal = excluding a (board, match, seat)
-- from the boards, never mutating the match itself (invalidation is a much
-- bigger hammer that claws back ratings/gold). board '*' excludes the row
-- from every board; player_id NULL covers both seats / match-scoped boards.
--
-- UNIQUE ... NULLS NOT DISTINCT (#147: a plain UNIQUE treats NULL player_id
-- rows as always-distinct and the replay guard silently vanishes).
-- Idempotent statement-by-statement (#243).

BEGIN;

CREATE TABLE IF NOT EXISTS record_exclusions (
    id          BIGSERIAL PRIMARY KEY,
    board       VARCHAR(32) NOT NULL,
    match_id    UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id   UUID REFERENCES players(id) ON DELETE CASCADE,
    reason      TEXT,
    created_by  VARCHAR(32) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (board, match_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_record_exclusions_match
    ON record_exclusions (match_id);

COMMIT;
