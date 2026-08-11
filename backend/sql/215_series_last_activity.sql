-- 215: give ranked_series a real activity timestamp, so a RESUMED series is
-- visible on the live surfaces while it is actually being played.
--
-- WHY THIS EXISTS  (bug 199, Aug 11 2026)
--
-- Spirit vs NotNic played game 1 of a BO3 on Aug 6 17:45 and game 2 on
-- Aug 11 14:22 — the same series, resumed five days later. For the whole of
-- that second game the match was absent from the in-game Leaderboard's live
-- panel AND from the Discord live-bets channel. Sid watched the tab from
-- beginning to end and it never populated.
--
-- Both surfaces are fed by one endpoint, GET /series/active, whose liveness
-- filter was:
--
--     rs.created_at > NOW() - INTERVAL '2 hours'
--     OR EXISTS (SELECT 1 FROM matches m2
--                 WHERE m2.series_id = rs.id
--                   AND m2.ended_at > NOW() - INTERVAL '2 hours')
--
-- Both arms were 116 hours stale — 58x the window — so the row never entered
-- the result set. It never appeared even at the end, either: the winning
-- match INSERT and status='completed' share one commit, so the recency arm
-- going true and status='active' going false happen in the same instant.
--
-- THE ASYMMETRY THAT CAUSED IT
--
-- Since July, _find_current_active_series reattaches an undecided BO3 with
-- NO EXPIRY (a time-capped window let a losing player abandon a series and
-- bank the elo by waiting it out). Resume is therefore unbounded while
-- liveness was capped at two hours. Nothing bridged the two.
--
-- WHY THE OLD SECOND ARM COULD NEVER HAVE WORKED
--
-- Its comment claimed it "keeps a RESUMED cross-session series visible while
-- its games are actually happening". It cannot: it keys on matches.ended_at,
-- which only exists for a COMPLETED game. A resumed series was visible for
-- two hours AFTER a game and never DURING its first one. That comment is
-- corrected in the same pass.
--
-- WHAT THIS COLUMN IS
--
-- The server already receives an in-game signal — the reporter's live-points
-- POST — and threw it away: that UPDATE wrote the two point columns and
-- stamped nothing, and ranked_series had no activity timestamp at all
-- (created_at / completed_at / invalidated_at only).
--
-- That POST is NOT sent every point. The client gates it on the current game
-- being 0-0 in ROUNDS, so it arrives as a burst during each game's round 1 and
-- then stops until the next game. The resume sites carry the rest, and the
-- 30-minute liveness window is sized for a whole game (longest 1v1 game in
-- production: 1085s), not for a continuous stream.
-- last_activity_at is stamped by every resume site and by that endpoint, and
-- becomes a third arm of the liveness predicate on BOTH the listing and
-- POST /bets (same-predicate rule #159/#328 — the two must never drift, or
-- the panel advertises a series the endpoint 409s).
--
-- NO NEW BETTING SURFACE FOR RESUMED SERIES. The POST independently rejects
-- any series with a decided game ("Bets locked — a game in this series is
-- already decided"), and a resumed BO3 is 1-0 or 0-1 by definition. The
-- visible change for them is a grey "Game in progress — bets locked" card.
-- Confirmed with Sid Aug 11: the @Gambler ping must stay silent for these.
--
-- TOURNAMENT SERIES ARE DELIBERATELY WIDENED (Sid's call, Aug 11). An async
-- bracket match is created when the bracket activates and then waits for the
-- pair to sit down. Measured over every tournament series on record, the gap
-- from activation to first game was 131h, 163h and 1139h -- so the 2-hour arm
-- NEVER once covered real tournament play: betting opened for two hours while
-- nobody was playing, closed, and was still closed when they finally met.
-- That is the same bug 199 wearing a tournament hat.
--
-- The rule now: a tournament match stays bettable for the entire wait, via a
-- FOURTH liveness arm. It closes on EITHER the normal condition (a decided
-- game / 2 points scored) OR the bracket match reaching a terminal state
-- without being played. Both are required: a no-show writes only
-- tournament_matches.status and never touches ranked_series, and
-- _prune_stale_series excludes tournaments, so gating on the parent
-- tournament alone left a FORFEITED match bettable for the rest of the
-- tournament with no settle path and no refund path (caught in review;
-- production already holds a double_forfeit row carrying a series_id).
-- Fail-closed -- tournament_id is ON DELETE SET NULL, so an orphaned series
-- has a NULL status and falls back to the recency arms rather than staying
-- live forever.
--
-- IDEMPOTENT. The backfill is guarded on IS NULL, so a rerun (the migrate
-- wrapper's `psql -f || psql <` fallback re-executes the whole file, #243)
-- only touches rows nothing has stamped yet and can never clobber a live
-- value written by the running API.
--
-- DEPLOY ORDER: THIS MIGRATION MUST RUN BEFORE THE API DEPLOY. The column is
-- read AND written in raw SQL at six sites; an API running ahead of it 500s
-- /series/active, /bets, live-points, /series/preflight (resume branch) and
-- BOTH queue both_ready branches. The queue stamps sit before their commits,
-- so room issuance rolls back with them: inverting this order takes 1v1
-- MATCHMAKING down, not just the display panel (#235). Do not read the
-- migrate wrapper's first-arm "No such file or directory" line as failure —
-- it always prints that before the fallback succeeds (#243); confirm from the
-- statement tags and the post-check NOTICE below.

BEGIN;

-- Added WITHOUT a default on purpose. `ADD COLUMN ... DEFAULT NOW()` fills
-- existing rows with NOW() in PG11+, which would make every dormant
-- resumable series look like it was being played this minute — the exact
-- failure this migration exists to prevent, inverted. Historical rows get
-- their true value from the backfill below, and only then does the column
-- take a default for future inserts.
ALTER TABLE ranked_series ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ;

-- Best available estimate of "when did something last happen in this series":
-- the newest match's end time, falling back to creation. GREATEST guards the
-- degenerate case of a match row older than its own series.
UPDATE ranked_series rs
   SET last_activity_at = GREATEST(
           rs.created_at,
           COALESCE((SELECT MAX(m.ended_at)
                       FROM matches m
                      WHERE m.series_id = rs.id),
                    rs.created_at))
 WHERE rs.last_activity_at IS NULL;

ALTER TABLE ranked_series ALTER COLUMN last_activity_at SET DEFAULT NOW();

-- Partial index matching the liveness predicate's shape. Left nullable
-- deliberately: the predicate compares with `>`, and NULL > x is NULL, which
-- an OR-arm reads as "not live" — the safe direction if any future insert
-- path forgets the column.
CREATE INDEX IF NOT EXISTS idx_ranked_series_last_activity
    ON ranked_series (last_activity_at DESC)
 WHERE status = 'active';

-- Post-check: every row carries a value. Deliberately modest — and note what
-- it does NOT assert, because a check that cannot fail is worse than no check
-- (#342).
--
-- The other property that matters ("this migration did not stamp a historical
-- row into the live window") is guaranteed BY CONSTRUCTION, not asserted:
-- the backfill value is GREATEST(created_at, MAX(match.ended_at)), so any row
-- it places inside the 30-minute window already satisfied one of the two
-- pre-existing 2-hour arms and was already live. Measured against production
-- before writing this: 0 of 31 active series qualify.
--
-- The NULL count below is likewise near-guaranteed to pass (created_at is NOT
-- NULL, so GREATEST cannot yield NULL, and the ALTER holds ACCESS EXCLUSIVE to
-- COMMIT so no concurrent INSERT can land mid-file). It is kept as a cheap
-- assertion that the ALTER + UPDATE both actually ran, which is the one thing
-- a silently-skipped statement would break.
DO $$
DECLARE
    unstamped BIGINT;
BEGIN
    SELECT COUNT(*) INTO unstamped
      FROM ranked_series
     WHERE last_activity_at IS NULL;
    IF unstamped > 0 THEN
        RAISE EXCEPTION '215 post-check FAILED: % ranked_series rows still have NULL last_activity_at', unstamped;
    END IF;
    RAISE NOTICE '215 post-check OK: all ranked_series rows carry last_activity_at';
END $$;

COMMIT;
