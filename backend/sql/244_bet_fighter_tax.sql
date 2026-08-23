-- 244: persist the profit redirected from winning low-odds bets to fighters.
-- Nullable with no default: only taxed wins carry a value. The API writes
-- these columns through raw claim UPDATEs, so no ORM mapping is required.
-- Pure idempotent DDL; explicit transaction because psql -f does not add one
-- (learning #340).

BEGIN;

ALTER TABLE bets
    ADD COLUMN IF NOT EXISTS fighter_tax INTEGER;

ALTER TABLE team_bets
    ADD COLUMN IF NOT EXISTS fighter_tax INTEGER;

ALTER TABLE ffa_bets
    ADD COLUMN IF NOT EXISTS fighter_tax INTEGER;

COMMIT;
