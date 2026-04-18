-- 020_economy.sql
--
-- Gold currency + transaction ledger.
--
-- `earned` and `spent` are split for legal hygiene: future purchased currency
-- can live in a separate column that never mixes with gameplay-earned gold, so
-- we don't accidentally cross the line into regulated gambling territory if we
-- ever add a shop that takes real money.
--
-- Balance is always derived: gold_earned - gold_spent.
--
-- gold_transactions is an append-only ledger so we can audit how anyone got
-- their balance and reverse mistakes without DB surgery.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS gold_earned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS gold_spent  INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS gold_transactions (
    id            BIGSERIAL PRIMARY KEY,
    player_id     UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    amount        INTEGER NOT NULL,                -- positive = earn, negative = spend
    reason        VARCHAR(64) NOT NULL,            -- 'xp', 'achievement', 'purchase', 'backfill', ...
    reference_id  TEXT,                            -- achievement key, item sku, etc.
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gold_tx_player ON gold_transactions (player_id, created_at DESC);

-- One-time backfill: 100 XP = 1 gold + 25 gold per achievement.
-- Skip deleted players so the ledger doesn't resurrect them.
WITH xp_grant AS (
    SELECT p.id AS player_id, (p.total_xp / 100)::int AS amount
    FROM players p
    WHERE p.deleted_at IS NULL AND (p.total_xp / 100)::int > 0
),
ach_grant AS (
    SELECT p.id AS player_id, (COUNT(pa.id) * 25)::int AS amount
    FROM players p
    LEFT JOIN player_achievements pa ON pa.player_id = p.id
    WHERE p.deleted_at IS NULL
    GROUP BY p.id
    HAVING COUNT(pa.id) > 0
)
INSERT INTO gold_transactions (player_id, amount, reason)
    SELECT player_id, amount, 'backfill_xp'         FROM xp_grant
    UNION ALL
    SELECT player_id, amount, 'backfill_achievement' FROM ach_grant;

-- Roll transactions into the denormalized column so stats queries are cheap.
UPDATE players p
SET gold_earned = COALESCE((
    SELECT SUM(amount) FROM gold_transactions gt
    WHERE gt.player_id = p.id AND gt.amount > 0
), 0)
WHERE p.deleted_at IS NULL;
