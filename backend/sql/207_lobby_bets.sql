-- 207: lobby_bets — staging table for LOBBY-PHASE betting.
--
-- WHAT THIS IS FOR
--
-- The ordinary bet tables (team_bets, ffa_bets) can only be written once the
-- thing being bet on EXISTS: team_bets.team_series_id is a NOT NULL FK to
-- team_series, and ffa_bets carries a game_number. Neither exists while the
-- lobby is still filling, so a spectator who wants to back a player before the
-- first game starts has nowhere to put the wager.
--
-- lobby_bets is that waiting room. A bet is placed against a LOBBY and a
-- target (a steam id, or a pair of them), held, and then BOUND to a real
-- team_bets/ffa_bets row at the moment the lobby produces the series/game that
-- makes the ordinary row insertable. Everything downstream of the bind —
-- odds, settlement, payout, the gold_transactions ledger — stays in the
-- existing bet tables and is untouched by this migration.
--
-- LIFECYCLE
--
--   open ──► bound            the bind sweep created the real bet row
--        ├─► refund_pending ──► refunded
--        └─► cancelled
--
--   open            wager taken, waiting for the lobby to start.
--   bound           a real team_bets/ffa_bets row now owns this wager;
--                   this row is a terminal audit record and nothing else.
--   refund_pending  the lobby died / the target left / the TTL lapsed, so the
--                   money is owed back but the refund has not been written to
--                   the ledger yet. This intermediate state exists so the
--                   decision to refund and the gold movement can be separate
--                   transactions without ever losing track of an owed refund:
--                   the janitor's catch-all index below finds anything stuck
--                   here and retries it.
--   refunded        the refund landed (payout = amount, settlement_kind
--                   'refunded', gold_spent decremented, positive
--                   GoldTransaction written) — see the money rules in
--                   CLAUDE.md; none of that is this table's job.
--   cancelled       resolved with no money owed (e.g. the wager was never
--                   actually debited, or it was voided before taking effect).
--
-- Terminal states are bound / refunded / cancelled. refund_pending is the only
-- non-terminal state other than open, and it is deliberately visible to the
-- janitor rather than hidden inside a single transaction.
--
-- WHY lobby_id HAS NO FOREIGN KEY
--
-- It points at ONE OF TWO parent tables — team_lobbies(id) for mode='team',
-- ffa_lobbies(id) for mode='ffa' — and PostgreSQL has no way to express a
-- disjoint FK. The (mode, lobby_id) pair is therefore validated in application
-- code at insert time, and every read must filter on mode as well as lobby_id
-- or it can collide across the two id spaces. That is also why the UNIQUE
-- constraint and the bind index both lead with mode.
--
-- Deleting a parent lobby row will NOT clean these up. That is intentional:
-- an unresolved wager must survive its lobby so the money can still be
-- refunded. The janitor resolves orphans via the (status, created_at) index.
--
-- NO DATA BACKFILL
--
-- This migration is pure DDL. Nothing here mutates existing rows, so the
-- re-run hazard of learning #168 (idempotent DDL wrapping a destructive
-- backfill) does not apply — there is no backfill to make idempotent.
--
-- Re-runnable statement by statement (learning #243: the deploy wrapper runs
-- "psql -f /migrations/FILE || psql < FILE", so the whole file executes again
-- whenever the first arm misses, and psql autocommits each statement).

CREATE TABLE IF NOT EXISTS lobby_bets (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- 'team' | 'ffa'. Selects which parent table lobby_id refers to.
    mode           VARCHAR(8)  NOT NULL,
    -- team_lobbies.id or ffa_lobbies.id. No FK — see header.
    lobby_id       UUID        NOT NULL,

    player_id      UUID        NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    amount         INTEGER     NOT NULL,

    -- Who the wager is on.
    --   ffa:  one steam id.
    --   team: the two steam ids of the pair being backed, SORTED and joined
    --         with ':'. The sort is what makes the value canonical — the same
    --         pair must always produce the same string, or two bets on the
    --         same duo compare as different targets at bind time.
    target_steams  TEXT        NOT NULL,

    status         VARCHAR(14) NOT NULL DEFAULT 'open',

    -- The ffa_bets row this became (ffa_bets.id is UUID).
    --
    -- NOTE for the endpoint author: team_bets.id is BIGSERIAL, not UUID, so a
    -- team-mode bind CANNOT be recorded here. bound_team_bet_id below exists
    -- for that side. Exactly one of the two is expected to be set on a 'bound'
    -- row, matching mode — deliberately NOT enforced as a CHECK, so a future
    -- two-step bind cannot be blocked by this table.
    bound_bet_id      UUID   NULL,
    bound_team_bet_id BIGINT NULL,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Stamped when status leaves 'open'. See the coherence constraint below.
    resolved_at    TIMESTAMPTZ NULL,
    resolve_reason VARCHAR(48) NULL,

    CONSTRAINT lobby_bets_mode_ck
        CHECK (mode IN ('team', 'ffa')),
    CONSTRAINT lobby_bets_amount_ck
        CHECK (amount BETWEEN 1 AND 2000),
    CONSTRAINT lobby_bets_status_ck
        CHECK (status IN ('open', 'bound', 'refund_pending', 'refunded', 'cancelled')),
    CONSTRAINT lobby_bets_target_ck
        CHECK (target_steams <> ''),

    -- Status/resolution coherence: an open wager has no resolution timestamp,
    -- and anything that has left 'open' has one.
    --
    -- This CANNOT block any intended transition, but only because of how it
    -- must be written against: a CHECK is evaluated per row at the end of the
    -- STATEMENT, so every status change has to set resolved_at in the SAME
    -- UPDATE. The claim-gated form the house rules already require does this
    -- naturally:
    --
    --   UPDATE lobby_bets
    --      SET status = 'refund_pending', resolved_at = NOW(), resolve_reason = :r
    --    WHERE id = :id AND status = 'open'
    --   RETURNING id
    --
    -- Splitting that into "set the status" then "set the timestamp" would
    -- abort on the first statement. refund_pending -> refunded is unaffected
    -- either way: resolved_at is already NOT NULL, so carrying it forward and
    -- re-stamping it are both legal.
    CONSTRAINT lobby_bets_resolution_ck
        CHECK (
            (status = 'open' AND resolved_at IS NULL)
            OR (status <> 'open' AND resolved_at IS NOT NULL)
        ),

    -- One lobby bet per player per lobby. mode leads because lobby_id alone is
    -- ambiguous across the two parent tables.
    CONSTRAINT lobby_bets_one_per_player_uq
        UNIQUE (mode, lobby_id, player_id)
);

-- Constraint repair path. On a fresh CREATE TABLE above every one of these is
-- already present and each block is a no-op; this exists so a table left
-- behind by a partial or hand-rolled earlier run converges to the same shape
-- instead of silently running unconstrained.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid = 'lobby_bets'::regclass AND conname = 'lobby_bets_mode_ck') THEN
        ALTER TABLE lobby_bets ADD CONSTRAINT lobby_bets_mode_ck
            CHECK (mode IN ('team', 'ffa'));
    END IF;

    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid = 'lobby_bets'::regclass AND conname = 'lobby_bets_amount_ck') THEN
        ALTER TABLE lobby_bets ADD CONSTRAINT lobby_bets_amount_ck
            CHECK (amount BETWEEN 1 AND 2000);
    END IF;

    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid = 'lobby_bets'::regclass AND conname = 'lobby_bets_status_ck') THEN
        ALTER TABLE lobby_bets ADD CONSTRAINT lobby_bets_status_ck
            CHECK (status IN ('open', 'bound', 'refund_pending', 'refunded', 'cancelled'));
    END IF;

    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid = 'lobby_bets'::regclass AND conname = 'lobby_bets_target_ck') THEN
        ALTER TABLE lobby_bets ADD CONSTRAINT lobby_bets_target_ck
            CHECK (target_steams <> '');
    END IF;

    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid = 'lobby_bets'::regclass AND conname = 'lobby_bets_resolution_ck') THEN
        ALTER TABLE lobby_bets ADD CONSTRAINT lobby_bets_resolution_ck
            CHECK (
                (status = 'open' AND resolved_at IS NULL)
                OR (status <> 'open' AND resolved_at IS NOT NULL)
            );
    END IF;

    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid = 'lobby_bets'::regclass AND conname = 'lobby_bets_one_per_player_uq') THEN
        ALTER TABLE lobby_bets ADD CONSTRAINT lobby_bets_one_per_player_uq
            UNIQUE (mode, lobby_id, player_id);
    END IF;
END $$;

-- The bind sweep: "every wager still waiting on this lobby". Partial on
-- status='open' so the index stays small — bound/refunded rows are terminal
-- audit history and are never read by this path.
CREATE INDEX IF NOT EXISTS idx_lobby_bets_open
    ON lobby_bets (mode, lobby_id)
    WHERE status = 'open';

-- The janitor's catch-all, serving two sweeps off one index: the TTL pass over
-- stale 'open' wagers whose lobby never started, and the retry pass over
-- 'refund_pending' rows whose gold movement has not landed yet. created_at is
-- the sort key for both, so an ordered scan of the oldest unresolved rows
-- needs no sort.
CREATE INDEX IF NOT EXISTS idx_lobby_bets_unresolved
    ON lobby_bets (status, created_at)
    WHERE status IN ('open', 'refund_pending');

-- "What has this player got riding on lobbies right now", and the lookup used
-- when a player leaves or is deleted.
CREATE INDEX IF NOT EXISTS idx_lobby_bets_player
    ON lobby_bets (player_id);

DO $$
DECLARE
    v_cols int;
    v_cks  int;
    v_idx  int;
BEGIN
    SELECT COUNT(*) INTO v_cols FROM information_schema.columns
     WHERE table_name = 'lobby_bets';
    SELECT COUNT(*) INTO v_cks FROM pg_constraint
     WHERE conrelid = 'lobby_bets'::regclass AND contype = 'c';
    SELECT COUNT(*) INTO v_idx FROM pg_indexes
     WHERE tablename = 'lobby_bets';

    RAISE NOTICE 'post-check: lobby_bets has % columns, % check constraints, % indexes',
        v_cols, v_cks, v_idx;

    -- 12 columns, 5 CHECKs, 5 indexes (PK + UNIQUE + the 3 above). Compared
    -- loosely: NOT NULL representation in pg_constraint differs by major
    -- version, so a mismatch here is a prompt to look, not a failure.
    IF v_cols = 12 AND v_cks >= 5 AND v_idx >= 5 THEN
        RAISE NOTICE 'post-check OK: lobby_bets ready';
    ELSE
        RAISE WARNING 'post-check UNEXPECTED shape - inspect before taking lobby bets';
    END IF;

    RAISE NOTICE 'post-check: % row(s) present (expected 0 on first apply - this migration has no backfill)',
        (SELECT COUNT(*) FROM lobby_bets);
END $$;
