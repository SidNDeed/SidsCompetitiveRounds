-- 356_team_series_dc_fallback_at.sql
--
-- 2v2 disconnect fallback: the DEFERRAL MARKER (2026-09-20, 886bed8 round 4).
--
-- WHAT THESE COLUMNS ARE FOR. A mid-series disconnect is reported to
-- /api/v1/team/series/{id}/report-dc by the surviving seat the room elected.
-- When that seat publishes a TERMINAL REFUSAL -- it will not be producing a
-- report -- another survivor posts a FALLBACK: a report carrying no point
-- totals, filed by a seat that knows only that the series looks abandoned.
-- (A seat whose own attempts merely go unanswered publishes "unknown" and the
-- survivors withhold instead, so no fallback is filed and no marker is
-- written; such a series is closed by the rowless-husk arm of the queue
-- cleanup loop, which cancels it and reconciles its bets.)
--
-- Until now both kinds settled the row the moment they arrived. The first one
-- to take the series lock wrote status='dc_incomplete', and the handler ignores
-- an already-settled row, so a real-totals report that arrived second was
-- discarded along with the rating and gold its branch would have applied.
-- Which of the two arrives first is a race between two client transactions and
-- is not orderable from inside either client.
--
-- The marker removes the race instead of guessing at it. A fallback report no
-- longer writes a terminal status at all; it stamps dc_fallback_at and returns
-- "deferred", which leaves the row 'active' so a real-totals report reaches its
-- normal branches, including the rated lead-forfeit, in either arrival order.
--
-- THE BOUND. Both lanes carry this sentence verbatim -- the API comment in the
-- deferral branch of report-dc, and the client comment beside the report it
-- composes:
--
--   A real-totals report wins while the deferred marker is younger than 420
--   seconds, and after that only until a sweep tick finds no live-game
--   evidence for the series and settles the row; once a row is settled, a
--   later report is refused at the settled-row exit and is not rated.
--
-- The round-4 header said "at ANY later moment", which the sweep contradicts:
-- the sweep exists to close a row nothing else ever settles, and a report that
-- arrives after it has done so is ignored.
--
--   dc_fallback_at         -- when a survivor first said "this series looks
--                             abandoned", stamped with clock_timestamp() AFTER
--                             the row lock was taken. NULL = no fallback has
--                             been filed, which is every row in the table today
--                             and the overwhelming majority afterwards.
--   dc_fallback_player_id  -- who that filing named as the disconnected player.
--                             The settling path records dc_player_id and
--                             dc_team_remaining; a deferred filing has nowhere
--                             to put them yet, and writing the live columns
--                             early would make an ACTIVE series read to every
--                             client as one with a recorded disconnect. Parked
--                             here instead, and copied across by the sweep at
--                             the moment it settles.
--
-- WHY clock_timestamp() AND NOT NOW(). NOW() is the transaction's START time
-- and is frozen before any lock wait. The report handler takes
-- FOR NO KEY UPDATE on this row and may wait behind another report; a marker
-- stamped with NOW() would be backdated by the whole wait, so a wait
-- approaching the bound would hand the sweep a marker already expired on
-- arrival and let it settle the series while a real-totals report was still in
-- flight. clock_timestamp() is read at statement time, after the wait. The same
-- correction already applies to the relock stamp this endpoint reads
-- (learning #277).
--
-- SET ONCE, NOT REFRESHED. The writer is
-- COALESCE(dc_fallback_at, clock_timestamp()), so repeated fallbacks -- from a
-- retrying client, or from a second survivor -- keep the FIRST stamp. A marker
-- a retry could push forward would let a client hold a dead series open
-- indefinitely by re-posting; the bound has to run from the first filing.
--
-- WHAT MAKES A MARKER INERT. Not a clear: the sweep's predicate requires
-- status IN ('active','dc_paused'), so the moment any writer moves the row out
-- of those two statuses -- a real-totals report completing or settling it
-- among them -- the marker cannot be acted on while the row stays out of them,
-- and it is left in place because "a fallback was filed for this series" is
-- worth having in the admin panel.
-- It IS cleared by the funnels that REVIVE a series
-- -- the ones that flip it back to 'active' and clear the other DC fields --
-- because a marker surviving a revival comes due on the first tick after it
-- passes the bound and settles the resumed series. The clear is
-- UNCONDITIONAL and reads no age: a revival says nothing about how old the
-- marker is -- a settlement inside the bound then an immediate revival leaves
-- a YOUNGER marker, a post-bound sweep then a later revival an OLDER one --
-- and both need the same clear. An earlier draft of this line said "older
-- than the bound by definition" and the helper's own comment in main.py said
-- the opposite; neither followed from the revival, and the code never
-- depended on either. There are
-- two such funnels, not one: the queue/sticky relock and the hosted-lobby
-- Start adoption, which _team_lock_family_pick also admits a 'dc_incomplete'
-- row into. An earlier draft of this header said "the ONE place", counted the
-- first and shipped the second unhandled; both now call the single helper
-- _team_clear_dc_fallback_marker, and the structural suite counts the revival
-- operation across the whole of main.py rather than inside one function.
--
-- THE MARKER PERSISTS; THE DEFERRAL IS ENDED BY A WRITER, NEVER BY THE CLOCK.
-- A deferral ends in one of two ways, and neither is a count to type here.
-- The row leaves ('active','dc_paused') with the marker still set: a sweep
-- tick after the bound, a real-totals report inside the bound (at its
-- lead-forfeit completion or its dc_incomplete exit), a completing game
-- report, an admin void or completion, a queue-janitor or queue-leave cancel
-- and the legacy dc_paused grace lapse among them. Or the marker itself is
-- cleared, which only the clearing helper's callers do: a revival funnel
-- clearing the marker, and the room-issue write in the queue poll, which
-- calls the same helper on the statement that stamps room_issued_at. The
-- structural suite derives both lists from main.py -- every def whose UPDATE
-- moves a series out of the two open statuses, and every caller of the
-- helper -- and holds them against a registry of its own, so a writer added
-- later reddens a test instead of going missing from this paragraph. Two
-- earlier drafts of this paragraph each typed a count, and each count was
-- short. The room-issue clear is expected to find nothing on today's flows
-- and is not guaranteed to run its UPDATE -- the helper swallows what the
-- attempt raises -- but a writer that sometimes ends a deferral is a writer
-- that ends one. The clock alone ends
-- nothing -- with no sweep ticking, a marked row stays deferred for as long as
-- the api is up. That is the direction the unhandled case fails in (#276, #430)
-- and it is why the sweep is a janitor self-test root rather than a loop nobody
-- watches. If the api is restarted mid-window the marker waits on disk for the
-- next tick, and the sweep's live-game veto refuses to act on restart-blinded
-- evidence.
--
-- APPLY THIS BEFORE THE API. Both columns are nullable with no default, so
-- every existing row reads as "no fallback filed" and no current writer touches
-- them. In the other order the api's boot-time janitor self-test EXPLAINs a
-- sweep naming a column that does not exist and fails loudly every boot, and
-- the sweep itself logs an error every tick.

BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE team_series ADD COLUMN IF NOT EXISTS dc_fallback_at TIMESTAMPTZ;
ALTER TABLE team_series ADD COLUMN IF NOT EXISTS dc_fallback_player_id UUID;

COMMENT ON COLUMN team_series.dc_fallback_at IS
    'First moment a survivor filed a disconnect fallback for this series -- the report carries is_fallback, and its point totals are whatever the client sent and are NOT read on this path, so the marker is not necessarily a zero-total one -- stamped with clock_timestamp() after the row lock. NULL = none filed. A fallback defers instead of settling; the scheduled sweep settles the row only once this stamp is older than the deferral bound and no live game is in evidence.';
COMMENT ON COLUMN team_series.dc_fallback_player_id IS
    'Player the deferred fallback named as disconnected. Parked here rather than in dc_player_id so an active series does not read as one with a recorded disconnect; the sweep copies it across when it settles.';

-- The sweep asks exactly one question: which live series carry a marker. The
-- marked rows are a handful against a table that is otherwise entirely
-- unmarked, so a full index here would be almost all dead entries.
CREATE INDEX IF NOT EXISTS idx_team_series_dc_fallback_at
    ON team_series (dc_fallback_at)
    WHERE dc_fallback_at IS NOT NULL;

COMMIT;
