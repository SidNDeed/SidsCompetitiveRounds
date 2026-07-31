-- 174: queue_leases — make queue exclusion EXPIRE BY DEFAULT.
--
-- WHY THIS EXISTS (the structural fix, not another cleanup branch).
--
-- Until now a player was blocked from queueing because a row EXISTED, and
-- freedom required one of ~15 independent cleanup paths to positively act:
-- the leave endpoint, five janitor sweeps, four in-poll self-heals, account
-- deletion, the lobby start/join prunes. Several of those depend on the
-- STUCK CLIENT cooperating, and each has its own preconditions. That design
-- fails in the unrecoverable direction: any path that does not fire leaves
-- the player blocked with no bound, which is why patching individual holes
-- never converged (migrations 165, 171 and 173 are all manual unsticks for
-- the same class, and the leave endpoint itself was returning 500 on 100% of
-- calls from v1.35.0 to v1.35.4 without anyone noticing).
--
-- The deeper defect: a finished sitting and a live 40-minute game are the
-- SAME database state — ffa_queue.status='ready_join' on an 'active' lobby —
-- because nothing ever writes "this sitting has ended" (submit_ffa_match only
-- increments games_played). Every cleanup path was therefore GUESSING which
-- of those two it was looking at, using four mutually inconsistent
-- definitions of "live" (_QUEUE_LOCK_LIVENESS_SQL: ranked = 90s freshness,
-- team = no recency bound AT ALL, ovt/ffa = 15-minute windows).
--
-- A lease replaces inference with one authoritative, bounded, renewable fact.
-- Exclusion is granted for a fixed window and must be RENEWED by evidence a
-- live game actually produces. Nothing renewing => it expires => the player
-- is free, with no cleanup path required and nothing to forget.
--
-- The failure direction inverts, which is the entire point:
--   before: a missed cleanup  => blocked forever (needs an operator)
--   after:  a missed renewal  => freed a few minutes early (player rejoins)
--
-- Lease expiry deliberately does NOT cancel a lobby/series or reject a match
-- report. A late report still validates against the frozen roster, so "freed
-- early" can never cost a recorded game.
--
-- Idempotent: safe to re-run (the deploy wrapper's migrate verb runs
-- "psql -f ... || psql < ..." and re-executes the whole file when the first
-- arm misses).

CREATE TABLE IF NOT EXISTS queue_leases (
    player_id   UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    -- Which mode owns the player right now. One row per player = one
    -- commitment at a time, enforced by the PK rather than by four
    -- cross-table checks that can disagree.
    mode        VARCHAR(8)  NOT NULL,
    -- series/lobby id when the mode has one (NULL for a 1v1 pre-series lock).
    -- Renewal must match it, so a heartbeat naming a stale group cannot
    -- extend a lease that has since been re-acquired for a different game.
    group_id    UUID,
    -- Bumped on every fresh acquire and on escape. A renewal carrying a stale
    -- generation is ignored, so an in-flight heartbeat cannot resurrect a
    -- lease the player just escaped from.
    generation  UUID        NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    renewed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    CONSTRAINT queue_leases_mode_ck
        CHECK (mode IN ('ranked', 'team', 'ovt', 'ffa')),
    CONSTRAINT queue_leases_future_ck
        CHECK (expires_at > renewed_at),
    -- Hard ceiling on a single extension. A future code path cannot grant an
    -- effectively-infinite lease by passing a huge TTL; the worst it can do
    -- is 30 minutes, and it must keep renewing after that. This is the
    -- constraint that stops the "blocked forever" class from being
    -- reintroduced by ordinary application code.
    -- Every TTL the application passes must stay STRICTLY below this. The
    -- writer sets renewed_at and expires_at from two separate clock reads
    -- microseconds apart, so a TTL of exactly 30 minutes could round over the
    -- bound and abort a match formation. Current TTLs are 5 and 15 minutes.
    CONSTRAINT queue_leases_max_extension_ck
        CHECK (expires_at <= renewed_at + INTERVAL '30 minutes')
);

-- The hot read is "is this player's lease live", served by the PK. This index
-- serves the janitor's expired-lease sweep instead.
CREATE INDEX IF NOT EXISTS idx_queue_leases_expires
    ON queue_leases (expires_at);

-- NOTE for anyone extending this: a partial index or CHECK using NOW() is NOT
-- possible (index predicates and CHECK expressions must be immutable), and no
-- trigger fires merely because wall-clock time passed. Expiry is therefore
-- enforced at READ time by _lease_live_player_ids / _locked_in_other_queue.
-- Keep every admission decision routed through those helpers; a new code path
-- that tests row existence instead reintroduces the bug this table removes.

-- ── Backfill: protect sittings that are ALREADY live across the deploy ────
--
-- Apply order matters and is one-way: this migration MUST run BEFORE the code
-- that reads queue_leases. _lease_acquire is deliberately not savepointed (a
-- lock that cannot record its lease must fail, not silently grant an
-- unbounded one), so deploying the code first would break matchmaking until
-- the table appeared. The reverse order is safe: old code ignores the table.
--
-- Without a backfill, every currently-locked player would lose their
-- cross-mode exclusion at the moment of deploy. Granting one assembly-length
-- lease keeps a genuinely live game protected while a dead husk simply
-- expires within 15 minutes — which is the outcome we want for both.
--
-- ON CONFLICT DO NOTHING with a fixed table order gives a player holding rows
-- in two modes (itself a symptom of the bug being fixed) exactly one lease,
-- deterministically. Re-running is a no-op once any lease exists.
INSERT INTO queue_leases (player_id, mode, group_id, generation,
                          acquired_at, renewed_at, expires_at)
SELECT player_id, mode, group_id, gen_random_uuid(), NOW(), NOW(),
       NOW() + INTERVAL '15 minutes'
  FROM (
        SELECT player_id, 'ffa'::varchar(8) AS mode, series_id AS group_id, 1 AS pri
          FROM ffa_queue WHERE status <> 'searching'
        UNION ALL
        SELECT player_id, 'ovt', series_id, 2 FROM ovt_queue WHERE status <> 'searching'
        UNION ALL
        SELECT player_id, 'team', series_id, 3 FROM team_queue WHERE status <> 'searching'
        UNION ALL
        SELECT player_id, 'ranked', NULL, 4 FROM ranked_queue WHERE status <> 'searching'
       ) src
 ORDER BY player_id, pri
ON CONFLICT (player_id) DO NOTHING;

DO $$
DECLARE
    v_cols int;
    v_cks  int;
BEGIN
    SELECT COUNT(*) INTO v_cols FROM information_schema.columns
     WHERE table_name = 'queue_leases';
    SELECT COUNT(*) INTO v_cks FROM pg_constraint
     WHERE conrelid = 'queue_leases'::regclass AND contype = 'c';
    RAISE NOTICE 'post-check: queue_leases has % columns, % check constraints', v_cols, v_cks;
    IF v_cols = 7 AND v_cks = 3 THEN
        RAISE NOTICE 'post-check OK: queue_leases ready';
    ELSE
        RAISE WARNING 'post-check UNEXPECTED shape - inspect before relying on the lease';
    END IF;
    RAISE NOTICE 'post-check: % lease(s) present, % live',
        (SELECT COUNT(*) FROM queue_leases),
        (SELECT COUNT(*) FROM queue_leases WHERE expires_at > NOW());
END $$;
