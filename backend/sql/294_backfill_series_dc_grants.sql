-- 294: one grant per live sitting that existed before 293 shipped.
--
-- RUN THIS AFTER THE API IS DEPLOYED, not with 293. The order is the one
-- #236/#477 record for every backfill of a table the new code also writes:
--
--   1. 293 (the table) -- old code ignores it, new code can write it.
--   2. the API, on the primary and then the standby.
--   3. this file.
--
-- Backwards, and every series published between the backfill and the deploy
-- has no grant, which is precisely the window this file exists to remove.
--
-- WHY IT IS NEEDED AT ALL. The eligibility predicate has two arms: a pair WITH
-- a grant is judged by the grant, and a pair with NO grant at all falls back to
-- the older row-shape test. Without this backfill every pair mid-sitting at
-- deploy time takes the fallback arm until their next publish -- which is
-- correct, but it means the new rule does not apply to the players it matters
-- most for, the ones already playing. With it, a report queued before the
-- deploy is judged exactly as one queued after.
--
-- WHAT QUALIFIES. The same four conditions the eligibility predicate uses, so
-- a backfilled grant is one the server would have issued had 293 existed:
--
--   status = 'active'         the sitting has not ended;
--   invalidated_at IS NULL    ...and was not thrown out. The NO_MATCH prune
--                             reason is deliberately NOT exempted here the way
--                             it is in the report path: that exemption exists
--                             so a leave during game 1 can still be reported,
--                             and it is applied when the report is judged. A
--                             backfill that minted grants for pruned series
--                             would be asserting the server had put the pair
--                             there, which by then it had stopped doing;
--   no decided bracket row    a forfeit-decided tournament series stays
--                             'active' on purpose -- bracket status owns that
--                             outcome, not series status. DECIDED is the
--                             enumeration, not open-ness: 'pending' is the
--                             column default and every bracket row starts
--                             there, so a list of open states that forgot it
--                             would have excluded every not-yet-readied match
--                             from this backfill. The four decided states are
--                             the same four main.py already enumerates in four
--                             other places;
--   fresh                     COALESCE(last_activity_at, created_at) within
--                             SIX HOURS -- the value DC_LIVE_WINDOW_SECONDS
--                             holds, and the bound the predicate's
--                             compatibility arm applies.
--
-- SIX HOURS AND NOT LONGER, and this is the one number in the file that has to
-- be right. A grant carries NO clock: once a sitting has one, it stays
-- nameable until the server puts that pair somewhere newer. So a backfill
-- window wider than the compatibility arm's does not merely add rows, it
-- CONVERTS sittings that the old rule had already stopped accepting reports
-- for into sittings that accept them indefinitely. Minting a grant for a
-- 13-day-old 'active' series would be asserting the server still has that pair
-- sitting there, which is exactly the claim it cannot make.
--
-- The reverse error is cheap: a sitting just outside the window gets no grant,
-- falls to the compatibility arm, and is judged by the rule that was already
-- refusing it. `test_the_backfill_selects_exactly_what_the_rule_would_have`
-- holds this file and the predicate together -- the window in both directions,
-- and the decided-bracket list -- so neither can drift.
--
-- last_seen_at is set to the series' own last activity, NOT to NOW(). Setting
-- it to NOW() would stamp every backfilled sitting with one identical
-- timestamp, and supersession between two of the same pair's series would then
-- be decided by series_id -- i.e. arbitrarily. The real activity time is what
-- the server actually observed.
--
-- Idempotent: ON CONFLICT DO NOTHING, so re-running cannot move a last_seen_at
-- that the live code has since advanced.

BEGIN;

INSERT INTO series_dc_grants (holder_id, counterparty_id, series_id, issued_at, last_seen_at)
SELECT s.player1_id,
       s.player2_id,
       s.id,
       COALESCE(s.last_activity_at, s.created_at),
       COALESCE(s.last_activity_at, s.created_at)
  FROM ranked_series s
 WHERE s.status = 'active'
   AND s.invalidated_at IS NULL
   AND s.player1_id IS NOT NULL
   AND s.player2_id IS NOT NULL
   AND COALESCE(s.last_activity_at, s.created_at) >= NOW() - INTERVAL '6 hours'
   AND NOT EXISTS (SELECT 1 FROM tournament_matches tm
                    WHERE tm.series_id = s.id
                      AND tm.status IN ('completed', 'forfeit',
                                        'double_forfeit', 'bye_auto'))
ON CONFLICT (holder_id, series_id) DO NOTHING;

-- The other direction, same rows. Written as a second statement rather than a
-- two-row VALUES list so each side's conflict is resolved independently.
INSERT INTO series_dc_grants (holder_id, counterparty_id, series_id, issued_at, last_seen_at)
SELECT s.player2_id,
       s.player1_id,
       s.id,
       COALESCE(s.last_activity_at, s.created_at),
       COALESCE(s.last_activity_at, s.created_at)
  FROM ranked_series s
 WHERE s.status = 'active'
   AND s.invalidated_at IS NULL
   AND s.player1_id IS NOT NULL
   AND s.player2_id IS NOT NULL
   AND COALESCE(s.last_activity_at, s.created_at) >= NOW() - INTERVAL '6 hours'
   AND NOT EXISTS (SELECT 1 FROM tournament_matches tm
                    WHERE tm.series_id = s.id
                      AND tm.status IN ('completed', 'forfeit',
                                        'double_forfeit', 'bye_auto'))
ON CONFLICT (holder_id, series_id) DO NOTHING;

COMMIT;

-- `psql -f` does not wrap a file in a transaction (#340), which is why the
-- BEGIN/COMMIT above are written out: both directions land together or neither
-- does, so no pair can end up with a grant in one direction only.
