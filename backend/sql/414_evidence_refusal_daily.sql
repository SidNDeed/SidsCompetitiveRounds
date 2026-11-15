-- 414_evidence_refusal_daily.sql
--
-- EVIDENCE REFUSAL CENSUS. Additive only: one new, empty table. No existing
-- table, column, constraint or row is changed.
--
--   evidence_refusal_daily  one row per (UTC day, evidence kind, HTTP status
--                           answered, refusal field, mod version) for every
--                           evidence record an intake route did NOT store,
--                           with a counter raised by a delta (n = n + d) and
--                           the time of the last one
--
-- Counted once for every FINAL answer of status 400..599 to a POST on one of
-- the four evidence intake paths (seat-evidence, card-evidence,
-- combat-evidence, identity-clock-evidence), by ONE place:
-- main.evidence_census_gate, which notes it in an in-memory tally of the api
-- process (no database work on the request's path). The field is the one the
-- route left when it refused (401 seat_session, 503 switch off, 403
-- signature, 409 not_ready, 409 conflict, 400/413/422/429 refusals, 500
-- internal on an unexpected error), else a fixed gate_* field (a
-- middleware's 413/426/429/503, a raised HTTPException, an unhandled error).
-- A stored record (200 recorded, or 200 already_recorded for the identical
-- repeat) is not counted. Written by main._evc_flush_janitor_step, a step of
-- queue_cleanup_loop on the primary, about once a minute: each key's delta
-- added in one transaction.
--
-- WHAT IT HOLDS, AND WHAT IT NEVER HOLDS. Counts only. No player id, steam id,
-- room or game key, attach key, address, session, signature, or any part of
-- a request body is stored in this table.
--
-- WHAT BOUNDS EACH COLUMN (the number of rows stays bounded whatever a client
-- sends; every value is the server's own, from a closed set or a validated
-- short pattern, and the CHECKs below enforce the shape):
--   day          the UTC date the server computes; one value per day.
--   kind         the route's fixed kind word; the code's closed set is
--                seat, card, clock, combat. CHECK: ^[a-z]{1,16}$, so a fifth
--                kind needs no migration.
--   status       the HTTP status answered. CHECK: 400 to 599.
--   field        the refusal's field name, the server's own string: the
--                EvidenceRefused field or the route's fixed answer
--                (seat_session, not_ready, signature, *_evidence_off,
--                internal), or for an answer decided outside the route one of
--                gate_size (413), gate_version (426), gate_rate (429),
--                gate_other (any other status). A field the server did not
--                author (a refusal that
--                names a key the client sent) is not in the code's closed
--                vocabulary and is stored as the fixed word `unlisted`.
--                CHECK: ^[a-z][a-z0-9_.]{0,47}$.
--   mod_version  the X-Mod-Version header only when it is a plain release
--                version (N.N.N, each part 0-99, no leading zero) between the
--                server's minimum accepted version and its latest release;
--                otherwise the fixed word `other`. CHECK: 'other' or that
--                shape.
--   A 401 (no verified session) is always counted under field seat_session
--   and version `other`, so an unauthenticated request adds at most one row
--   per kind per day whatever it sends.
--   n            CHECK n >= 1; last_at NOT NULL.
--
-- READ THE CENSUS (the operator query; aggregates only):
--   SELECT day, kind, status, field, mod_version, n, last_at
--     FROM evidence_refusal_daily
--    WHERE day >= CURRENT_DATE - 7
--    ORDER BY day DESC, n DESC;
--
-- DEPLOY ORDER: this file before the api. An api deployed before it answers
-- exactly the same, and its flush step finds no table by its schema probe,
-- skips and keeps the tally in memory; but the boot janitor self-test checks
-- the flush's statements against this table and reports them failed
-- (janitor_selftest 0) until this file runs.
--
-- ROLLBACK: no rollback file. The table is new and starts empty; removing it
-- is DROP TABLE evidence_refusal_daily, and nothing else depends on it.
--
-- Idempotent: IF NOT EXISTS throughout; a re-run changes nothing. Explicit
-- BEGIN/COMMIT (#340).
BEGIN;

CREATE TABLE IF NOT EXISTS evidence_refusal_daily (
    day          DATE        NOT NULL,
    kind         TEXT        NOT NULL CHECK (kind ~ '^[a-z]{1,16}$'),
    status       SMALLINT    NOT NULL CHECK (status BETWEEN 400 AND 599),
    field        TEXT        NOT NULL CHECK (field ~ '^[a-z][a-z0-9_.]{0,47}$'),
    mod_version  TEXT        NOT NULL CHECK (mod_version = 'other' OR mod_version ~
                     '^(0|[1-9][0-9]?)[.](0|[1-9][0-9]?)[.](0|[1-9][0-9]?)$'),
    n            BIGINT      NOT NULL CHECK (n >= 1),
    last_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (day, kind, status, field, mod_version)
);

COMMIT;
