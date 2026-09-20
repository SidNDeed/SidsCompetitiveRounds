-- 326_ffa_departure_cause.sql
--
-- Bug #392, item A step 1 (2) and (3): persist the departure cause, and give
-- the match row somewhere to carry the reconciled label.
--
-- Today `cause` is read at the top of the FFA and 1v2 leave handlers,
-- compared against one literal, printed once and discarded. Nothing persists
-- it, so no later consumer can tell a seat that chose to go from a seat the
-- transport took out of the room. Two columns close that:
--
--   ffa_lobbies.departure_causes    the lobby's departure record already is
--                                   `departed_ids`; the cause rides beside it
--                                   on the same row, written by the same
--                                   statement, so the two can never disagree
--                                   about which lobby a departure belongs to.
--                                   Keys are player_id::text, values are the
--                                   16-character wire cause. First attestation
--                                   wins (the writers concat the new object on
--                                   the LEFT of the existing one, and `||`
--                                   lets the right operand keep the key), so a
--                                   retried or contradicting later leave
--                                   cannot rewrite a recorded cause.
--
--   ffa_match_players.left_early_involuntary
--                                   the DISPLAY reconciliation, and only
--                                   that. `left_early` keeps its meaning and
--                                   its value; this column says which kind of
--                                   departure it was. Nothing between the
--                                   report handler's write and the two
--                                   renderers' read consumes it: placement,
--                                   rating, XP and gold are computed before
--                                   it is even loaded.
--
-- Both are additive with defaults, so every row that predates this migration
-- reads exactly as it does today: an empty object means "no cause recorded"
-- and false means "not reconciled". PostgreSQL 11+ adds a column with a
-- non-volatile default as a catalogue change, so neither ALTER rewrites its
-- table.
--
-- ORDER: this file goes in BEFORE the api that writes the columns. The
-- reverse order gives an api whose INSERT names a column the table does not
-- have, which is a 500 on every FFA report.

BEGIN;

-- ── Dry run: the read half, before anything is written. ──────────────────
-- Each SELECT answers a question the write half depends on, and each one is
-- safe to run against a database that has already had this file applied.

-- 1. Do the target tables exist, and do the new columns already?
SELECT 'ffa_lobbies.departure_causes' AS target,
       EXISTS (SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'ffa_lobbies') AS table_present,
       EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'ffa_lobbies'
                  AND column_name = 'departure_causes') AS column_present
UNION ALL
SELECT 'ffa_match_players.left_early_involuntary',
       EXISTS (SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'ffa_match_players'),
       EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'ffa_match_players'
                  AND column_name = 'left_early_involuntary');

-- 2. How much existing data takes the defaults? Both numbers are expected to
--    equal the whole table on a first apply: no backfill is possible or
--    wanted, because the causes this migration stores were never recorded.
SELECT (SELECT COUNT(*) FROM ffa_lobbies)                            AS lobbies_defaulting_to_empty,
       (SELECT COUNT(*) FROM ffa_match_players WHERE left_early)     AS left_early_rows_defaulting_to_false;

-- ── Write half. ──────────────────────────────────────────────────────────

ALTER TABLE ffa_lobbies
    ADD COLUMN IF NOT EXISTS departure_causes JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE ffa_match_players
    ADD COLUMN IF NOT EXISTS left_early_involuntary BOOLEAN NOT NULL DEFAULT false;

-- ── Post-write verification, inside the same transaction. ────────────────
-- A positive signal, not an absence of errors: both rows must report true.
SELECT 'ffa_lobbies.departure_causes' AS target,
       EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'ffa_lobbies'
                  AND column_name = 'departure_causes'
                  AND data_type = 'jsonb' AND is_nullable = 'NO') AS applied
UNION ALL
SELECT 'ffa_match_players.left_early_involuntary',
       EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'ffa_match_players'
                  AND column_name = 'left_early_involuntary'
                  AND data_type = 'boolean' AND is_nullable = 'NO');

COMMIT;
