-- 414_evidence_refusal_daily.sql
--
-- EVIDENCE REFUSAL CENSUS. Additive only: one new, empty table. No existing
-- table, column, constraint or row is changed.
--
--   evidence_refusal_daily  one row per (UTC day, evidence kind, HTTP status
--                           answered, refusal field, mod version) for every
--                           evidence record an intake route did NOT store,
--                           with a counter raised by a delta (n = n + 1) and
--                           the time of the last one
--
-- Written by main._evidence_census, called by the four evidence intake routes
-- (seat-evidence, card-evidence, combat-evidence, identity-clock-evidence) on
-- every answer that does not store the record: 401 seat_session, 503 switch
-- off, 403 signature, 409 not_ready, 409 conflict, 400/413/422/429 refusals,
-- and 500 on an unexpected error. A stored record (200 recorded, or 200
-- already_recorded for the identical repeat) is not counted.
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
--   status       the HTTP status the route answered. CHECK: one of
--                400, 401, 403, 409, 413, 422, 429, 500, 503.
--   field        the refusal's field name, the server's own string: the
--                EvidenceRefused field or the route's fixed answer
--                (seat_session, not_ready, signature, *_evidence_off,
--                internal). A field the server did not author (a refusal that
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
-- DEPLOY ORDER: either. An api deployed before this file finds no table: the
-- census write fails, the route answers exactly the same refusal, and prints
-- one [EVIDENCE-CENSUS] line per refusal until this file runs.
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
    status       SMALLINT    NOT NULL CHECK (status IN (400, 401, 403, 409, 413, 422, 429, 500, 503)),
    field        TEXT        NOT NULL CHECK (field ~ '^[a-z][a-z0-9_.]{0,47}$'),
    mod_version  TEXT        NOT NULL CHECK (mod_version = 'other' OR mod_version ~
                     '^(0|[1-9][0-9]?)[.](0|[1-9][0-9]?)[.](0|[1-9][0-9]?)$'),
    n            BIGINT      NOT NULL CHECK (n >= 1),
    last_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (day, kind, status, field, mod_version)
);

COMMIT;
