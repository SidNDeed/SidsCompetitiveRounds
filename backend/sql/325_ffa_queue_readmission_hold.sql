-- 325_ffa_queue_readmission_hold.sql
--
-- FFA relaunched-seat readmission, Phase A: the two columns that mark an
-- ffa_queue row as RESERVED for a player whose game process died, so the seat
-- survives long enough for them to relaunch and claim it (2026-09-17).
--
-- NUMBERING: this is deliberately 325, not 322. The working tree carries
-- uncommitted i18n additions with no key/seed pair on disk above 321, and that
-- batch takes the next pair when it lands. A numbering GAP is harmless --
-- migrations are applied by filename, one at a time -- whereas two files both
-- named 322_*.sql reaching main is a real collision. Gap over duplicate.
--
-- WHAT A HOLD IS. When a fighter's process dies mid-sitting, their ffa_queue
-- row is NOT deleted: the process never called leave, so the row stays
-- status='ready_join', still bound to the lobby. The seat is therefore already
-- reserved server-side, by accident. This file makes that reservation explicit
-- and, crucially, BOUNDED -- held_until is what turns an accidental indefinite
-- lock into a deliberate expiring one.
--
--   held_until  -- when the reservation lapses. NULL = no hold, the ordinary
--                  case for every row in the table.
--   held_lobby  -- which lobby granted it. A hold is only ever meaningful for
--                  the lobby the row was bound to when the player dropped; if
--                  the row is re-bound or reset, the hold is void, not
--                  transferred. Carrying the lobby id makes that checkable
--                  rather than assumed.
--
-- WHY THE HOLD DOES NOT BLOCK ANYTHING. _locked_in_other_queue -- the check
-- that decides whether a player may join a queue in any mode -- reads
-- queue_leases ONLY, never this table (main.py, `_locked_in_other_queue` ->
-- `_lease_live_mode`). The claim path deletes the player's lease as it writes
-- the hold, so a held player is free to join any other queue for the whole
-- window. That is Sid's ruling ("I don't want to prevent people from joining
-- other games") satisfied structurally rather than by a rule someone has to
-- remember. It is also exactly why the poll needs a fence: with no lease, the
-- poll's lease-expired arm would otherwise free the very row the hold exists
-- to keep.
--
-- EXPIRES BY DEFAULT. There is no code path that must run to release a hold.
-- If every client vanishes and the api is restarted mid-window, held_until
-- passes and the janitor collects the row on its next tick. A blocking-by-
-- default reservation would need a positive cleanup that always runs; this one
-- self-heals (learnings #276, #430).
--
-- SAFE TO RUN BEFORE THE API. Both columns are nullable with no default, so
-- existing rows read as "no hold" and every current writer keeps working
-- untouched. Apply this first, deploy second.

BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE ffa_queue ADD COLUMN IF NOT EXISTS held_until TIMESTAMPTZ;
ALTER TABLE ffa_queue ADD COLUMN IF NOT EXISTS held_lobby UUID;

COMMENT ON COLUMN ffa_queue.held_until IS
    'Readmission hold expiry. NULL = not held. Set when a dropped fighter''s seat is reserved for their relaunch; the janitor collects the row once this passes.';
COMMENT ON COLUMN ffa_queue.held_lobby IS
    'Lobby that granted the hold. A hold is void if the row is re-bound to a different lobby or reset to searching -- never transferred.';

-- The janitor's lapse sweep asks exactly one question: which rows have a hold
-- that has expired. Partial on held_until IS NOT NULL, because the holds are a
-- handful of rows against a table that is otherwise entirely un-held -- a full
-- index here would be almost all dead entries.
CREATE INDEX IF NOT EXISTS idx_ffa_queue_held_until
    ON ffa_queue (held_until)
    WHERE held_until IS NOT NULL;

-- A hold without its lobby is unfenceable: every consumer checks the pair, and
-- a half-written hold would read as "held by nobody in particular" and survive
-- the re-bind checks that are supposed to void it. Both or neither.
ALTER TABLE ffa_queue DROP CONSTRAINT IF EXISTS ffa_queue_hold_pair;
ALTER TABLE ffa_queue ADD CONSTRAINT ffa_queue_hold_pair
    CHECK ((held_until IS NULL) = (held_lobby IS NULL));

COMMIT;
