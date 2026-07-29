-- 164_ffa_gold_backpay.sql
-- Bug #121: FFA had no flat completion bonus (every other mode has one:
-- SERIES_GOLD_BASE / TEAM_SERIES_WIN_GOLD / OVT_SERIES_WIN_GOLD), so a
-- 13-minute 5-player FFA paid its winner ~13g against 2v2's ~102g for a
-- comparable sitting. The new inline award adds `ffa_placement` gold.
-- Sid approved back-paying everyone who already played.
--
-- SCOPE: the flat placement bonus ONLY. This migration deliberately does NOT
-- recompute the XP-derived half of the payout, and does not touch total_xp.
--   * XP-derived gold is `floor(new_total_xp/100) - floor(old_total_xp/100)` —
--     a function of the player's LIFETIME xp (fed by 1v1/2v2/1v2 too) relative
--     to a 100 boundary. It is path-dependent and cannot be reproduced from
--     stored per-match columns; any SQL attempt is a stateless per-match floor
--     that systematically under-counts (~7% on the current data set).
--   * Raising total_xp retroactively would drag level crossings with it, and
--     FFA had no inline level-reward grant at all before this release, so
--     there is no idempotent way to award the deferred crossings without
--     double-paying whatever a later 1v1/2v2 match already caught.
-- The placement bonus, by contrast, is stateless per match and reproduces the
-- new inline formula EXACTLY from (placement, live-player count, beaten).
--
-- IDEMPOTENCY (#168 — `IF NOT EXISTS` on DDL does not make an UPDATE
-- rerun-safe, so the guard is explicit): a (player, match) pair is skipped if
-- the ledger already holds an `ffa_placement` row (a game recorded AFTER the
-- new code deployed — it was paid inline) or an `ffa_backpay` row (this
-- migration already ran). Both are covered by one NOT EXISTS, so a rerun is a
-- no-op.
--
-- *** RUN THIS **AFTER** THE API DEPLOY, NOT BEFORE. ***
-- The work list is a one-time snapshot. Any FFA game reported in the window
-- between the snapshot and the new code going live would be paid at the OLD
-- rate, carry no `ffa_placement` row, and be invisible to both this run and
-- every later rerun — a permanently under-paid game (Codex review, wave 4,
-- finding 1). Deploying first inverts that: every post-deploy game already has
-- its `ffa_placement` row and is excluded by the guard, and everything in the
-- snapshot is by definition pre-deploy. Order:
--     163 (index)  ->  deploy API  ->  164 (this file)
--
-- Gold can never go DOWN: every computed amount is >= 6 and is only ever added.

-- Mirrors _ffa_win_mult / _ffa_place_frac / _ffa_place_gold in main.py.
-- Kept in pg_temp so it cannot outlive the session and drift from the Python.
-- NOTE on rounding: Python's round() is banker's, Postgres ROUND() is
-- half-away-from-zero. For the shipped constants (base 10..50, size in
-- {0.6,0.8,...,2.0}) no product ever lands on an exact .5 for n_live in 3..10,
-- so the two agree on every reachable input. Re-check this if the constants
-- change.
CREATE OR REPLACE FUNCTION pg_temp.ffa_place_gold(p_place int, p_beaten int, p_n_live int)
RETURNS int AS $$
DECLARE
    v_top  numeric;
    v_size numeric;
    v_frac numeric;
BEGIN
    IF p_n_live IS NULL OR p_n_live < 1 THEN RETURN 0; END IF;
    v_top  := LEAST(5.0, 1.5 + 0.5 * GREATEST(0, p_n_live - 3));   -- _ffa_win_mult
    v_size := v_top / 2.5;                                          -- normalised to n=5
    IF p_place <= 1 OR p_n_live <= 1 THEN
        v_frac := 1.0;
    ELSE
        v_frac := LEAST(1.0, GREATEST(0.0, p_beaten::numeric / (p_n_live - 1)));
    END IF;
    RETURN ROUND((10 + 40 * v_frac) * v_size)::int;   -- FFA_PLACE_GOLD_LAST/_TOP
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- The work list is materialised FIRST so the credit loop can COMMIT after
-- every row. A single wide transaction would hold a lock on every player row
-- it had touched until the end, which is exactly the hold-and-wait shape that
-- deadlocks against a live match report (#204); one row per transaction can
-- never be the middle of a wait chain. Committing inside a loop over a live
-- query is not portable, hence the temp table.
CREATE TEMP TABLE _ffa_backpay_work ON COMMIT PRESERVE ROWS AS
        -- Ghost rows (roster members who were absent for this game) earned no
        -- XP and no gold by design (#227 — leaving early must not dodge the
        -- loss, but you are not paid for a game you did not play). They are
        -- identified by xp_gained = 0: the live floor was 300 XP even for last
        -- place, so a live player can never look like a ghost.
        WITH live AS (
            SELECT match_id, player_id, placement
              FROM ffa_match_players
             WHERE xp_gained > 0
        ), derived AS (
            SELECT l.match_id,
                   l.player_id,
                   l.placement,
                   COUNT(*) OVER (PARTITION BY l.match_id)                    AS n_live,
                   -- strictly-beaten: same rule as beaten_count in main.py
                   (SELECT COUNT(*) FROM live l2
                     WHERE l2.match_id = l.match_id
                       AND l2.placement > l.placement)                        AS beaten
              FROM live l
        )
        SELECT d.match_id, d.player_id, d.placement, d.n_live, d.beaten
          FROM derived d
          JOIN ffa_matches m ON m.id = d.match_id
          JOIN players p     ON p.id = d.player_id
         WHERE m.invalidated_at IS NULL
           AND p.deleted_at IS NULL
           AND NOT EXISTS (
                 SELECT 1 FROM gold_transactions gt
                  WHERE gt.player_id = d.player_id
                    AND gt.reference_id = d.match_id::text
                    AND gt.reason IN ('ffa_placement', 'ffa_backpay'))
         ORDER BY d.player_id, d.match_id;     -- deterministic; one row locked at a time

DO $$
DECLARE
    r            RECORD;
    v_gold       int;
    v_rows       int := 0;
    v_total      int := 0;
BEGIN
    -- Pop one row at a time instead of iterating a query result: a plpgsql
    -- FOR-over-SELECT pins a portal, and COMMIT inside it errors with
    -- "cannot commit while a portal is pinned". Draining the temp table also
    -- makes the loop naturally resumable if the session dies mid-run.
    LOOP
        DELETE FROM _ffa_backpay_work
         WHERE ctid = (SELECT ctid FROM _ffa_backpay_work
                        ORDER BY player_id, match_id LIMIT 1)
        RETURNING * INTO r;
        EXIT WHEN NOT FOUND;

        v_gold := pg_temp.ffa_place_gold(r.placement::int, r.beaten::int, r.n_live::int);
        IF v_gold > 0 THEN
            -- FOR NO KEY UPDATE, not FOR UPDATE — the weakest mode that still
            -- conflicts with our own write, so FK inserts elsewhere (which take
            -- FOR KEY SHARE on players) are not enrolled in our lock graph (#202).
            PERFORM 1 FROM players WHERE id = r.player_id FOR NO KEY UPDATE;

            -- Re-check the guard UNDER the lock: a live report could have paid
            -- an ffa_placement row for this exact (player, match) between the
            -- work list being built and now.
            IF NOT EXISTS (
                SELECT 1 FROM gold_transactions gt
                 WHERE gt.player_id = r.player_id
                   AND gt.reference_id = r.match_id::text
                   AND gt.reason IN ('ffa_placement', 'ffa_backpay')) THEN

                UPDATE players
                   SET gold_earned     = COALESCE(gold_earned, 0) + v_gold,
                       ffa_gold_earned = COALESCE(ffa_gold_earned, 0) + v_gold
                 WHERE id = r.player_id;

                INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
                VALUES (r.player_id, v_gold, 'ffa_backpay', r.match_id::text);

                -- Keep the in-game match history honest: gold_gained becomes
                -- what the player was ultimately paid for that game. The
                -- original inline payment is still recoverable from the
                -- append-only ledger under reason 'ffa_xp'; this only rewrites
                -- the display total.
                UPDATE ffa_match_players
                   SET gold_gained = gold_gained + v_gold
                 WHERE match_id = r.match_id AND player_id = r.player_id;

                v_rows  := v_rows + 1;
                v_total := v_total + v_gold;
            END IF;
        END IF;
        -- Commit EVERY iteration, including the skipped ones: a CONTINUE that
        -- skipped the commit would carry this player's row lock into the next
        -- iteration and we would hold two players rows at once, which is the
        -- hold-and-wait shape this loop exists to avoid.
        COMMIT;
    END LOOP;

    RAISE NOTICE '164 ffa back-pay: % rows credited, % gold total', v_rows, v_total;
END $$;

DROP TABLE IF EXISTS _ffa_backpay_work;

-- Post-condition (#020's economy invariant, delta-scoped): every gold credited
-- above must be visible in players.gold_earned, not just in ffa_gold_earned —
-- gold_earned is what the shop actually spends. A mismatch here means the
-- balance rose somewhere the player cannot reach.
DO $$
DECLARE v_bad int;
BEGIN
    SELECT COUNT(*) INTO v_bad
      FROM (
        SELECT gt.player_id, SUM(gt.amount) AS backpaid
          FROM gold_transactions gt
         WHERE gt.reason = 'ffa_backpay'
         GROUP BY gt.player_id
      ) b
      JOIN players p ON p.id = b.player_id
     WHERE COALESCE(p.ffa_gold_earned, 0) < b.backpaid
        OR COALESCE(p.gold_earned, 0)     < b.backpaid;
    IF v_bad > 0 THEN
        RAISE EXCEPTION '164 post-check FAILED: % player(s) have ffa_backpay ledger rows exceeding their credited totals', v_bad;
    END IF;
    RAISE NOTICE '164 post-check OK';
END $$;
