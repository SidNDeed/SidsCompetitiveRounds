-- 169: quarantine for rejected match reports (Sid: "if it fails again, send it to
-- the admin tab instead of having it straight deleted")
--
-- Tonight two completed FFA games were destroyed: a lifecycle timer closed the
-- lobby, /ffa/matches answered 409 "Lobby is not active", and the client then
-- deleted the payload from its outbox (any 4xx was classed permanent). Six
-- players' ratings had to be rebuilt by replaying the whole ladder (migration
-- 168). Nothing anywhere held a copy of the report.
--
-- This table is that copy. A report rejected for a LIFECYCLE reason lands here
-- with its full payload instead of evaporating, and an admin can recover it.
--
-- WHAT MAY BE STORED — the boundary is mechanical, not a judgement call:
--   quarantine  = the check's predicate reads a DB ROW (lobby not active, series
--                 resolved, roster missing, game limit). The report is genuine;
--                 the server state moved on.
--   reject only = the check reads the REQUEST alone (bad HMAC, unknown player,
--                 impossible score, malformed id). Storing these would make the
--                 table an unauthenticated write primitive.
-- HMAC is verified BEFORE anything is written here, so every stored row is a
-- report the server already believes came from a real client.
--
-- Every lifecycle gate in all four submit endpoints fires BEFORE the first write,
-- so capture is a clean rollback -> insert -> commit -> raise and cannot corrupt
-- the caller's transaction.
--
-- ON ACCEPT (deliberately NOT implemented in this migration): applying an old
-- report by re-running the submit path would apply Glicko at the wrong point in
-- history - tonight's recovery needed a full chronological replay precisely
-- because rating order matters. Accept is therefore safe only when no
-- participant has a later rated result, and otherwise has to mean "approve for
-- ordered replay". Until that exists this table is capture + visibility +
-- discard, which is already the difference between a recoverable incident and a
-- lost game.

CREATE TABLE IF NOT EXISTS match_report_quarantine (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode            VARCHAR(8)  NOT NULL,          -- '1v1' | '2v2' | '1v2' | 'ffa'
    reason          VARCHAR(64) NOT NULL,          -- the rejection detail, verbatim
    http_status     SMALLINT    NOT NULL,
    -- Group identity: the lobby (FFA) or series (2v2/1v2) the report targeted.
    group_id        UUID,
    photon_room_id  VARCHAR(64),
    reporter_id     UUID REFERENCES players(id) ON DELETE SET NULL,
    player_ids      UUID[]      NOT NULL DEFAULT '{}',
    payload         JSONB       NOT NULL,          -- the entire report body
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',   -- pending|accepted|discarded
    reviewed_by     UUID REFERENCES players(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    review_note     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedupe: the client POSTs 3x and then retries from its outbox, so one dead game
-- would otherwise land 4+ times. Room id is per-game-suffixed and is already the
-- dedupe key the live FFA insert relies on (and #147 forbids a NULL in a UNIQUE
-- used as a replay guard, so the partial index is restricted to non-null rooms).
CREATE UNIQUE INDEX IF NOT EXISTS uq_quarantine_room
    ON match_report_quarantine (mode, photon_room_id)
    WHERE photon_room_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_quarantine_pending
    ON match_report_quarantine (created_at DESC) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_quarantine_group
    ON match_report_quarantine (group_id) WHERE group_id IS NOT NULL;

COMMENT ON TABLE match_report_quarantine IS
    'Match reports rejected for a lifecycle reason (server state moved on), kept for admin recovery instead of being dropped. Integrity failures are never stored here.';

DO $$
DECLARE n_ INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_ FROM information_schema.tables
     WHERE table_name = 'match_report_quarantine';
    IF n_ <> 1 THEN
        RAISE EXCEPTION 'post-check FAILED: match_report_quarantine not created';
    END IF;
    RAISE NOTICE 'post-check OK: match_report_quarantine ready';
END $$;
