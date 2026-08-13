-- 219: per-match Photon region for SYNC tournaments, and clear the stale
-- tournament-wide region that async no longer uses.
--
-- WHY THIS EXISTS  (Aug 13 2026, tournament batch items 4/5, region VERDICT)
--
-- THE [RU] BUG. tournaments.photon_region is picked at lock as the MODE of
-- every signup's region_at_signup, ignoring empties. The client's signup call
-- has never carried a region parameter, so region_at_signup is NULL for
-- everything the current client creates. Production, all 25 signups ever
-- recorded: 24 empty, 1 'ru'. The "us" fallback only fires when NOBODY
-- reported, and the population was not empty — it had exactly one element. So
-- the live async tournament a2d3c090 pinned photon_region='ru' off one legacy
-- row, and every player in it was being auto-connected to the Russian region.
--
-- WHAT CHANGES, AND WHY THE TWO KINDS DIVERGE
--
-- ASYNC drops the region entirely. main.py:744 rejects a non-"sct-" room for
-- SYNC ONLY; an async match binds by PLAYER PAIR from any room, its
-- ranked_series row is minted at bracket activation, and its forfeit is
-- deadline-driven. Nothing in the async lifecycle depends on the region, the
-- sct- room, or Ready Up — all three only existed because async reuses the
-- sync match panel. So there is nothing for async to converge on, and #49's
-- split-room failure cannot apply to it.
--
-- SYNC keeps it and gets a better one. The server puts a pair in a room at a
-- scheduled instant, so both clients MUST agree on a region — #49 is the
-- incident that proves it. A bracket re-pairs every round, so one
-- tournament-wide value provably cannot serve every pair; the new
-- tournament_matches.photon_region is resolved per pair at activation from
-- match-history pings, with tournaments.photon_region kept as the fallback
-- rung (and as the field old clients read through /current, which is already
-- per-requester and sits behind no HTTP cache — verified: backend/nginx/
-- app.conf has proxy_pass only, no proxy_cache).
--
-- NO BACKFILL of the new column, deliberately. NULL means "no per-match
-- answer" and every reader falls back to tournaments.photon_region, so deploy
-- order is safe in that direction and a rerun has nothing to redo (#168).
--
-- ACCEPTED RISK on the async clear, stated explicitly. A client older than
-- this batch still reads photon_region for async and, finding it empty, sets
-- m_ForceRegion=true against its own saved dropdown value (Plugin.cs:1091-99)
-- — so two old async clients may force different regions and their auto-join
-- will not converge. That is strictly better than the status quo: today they
-- all converge on RUSSIA because of one legacy signup row. Nobody forfeits
-- for it either — the async no-show sweep keys on ready_deadline_at, which for
-- async IS the 7-day match deadline — and an async series is accepted from any
-- room, so the pair can simply agree on a lobby and play.
--
-- IDEMPOTENT statement by statement (the migrate wrapper re-executes the whole
-- file on a nonzero exit, #243): ADD COLUMN IF NOT EXISTS, and the UPDATE is
-- targeted by id and already-guarded on photon_region IS NOT NULL, so a rerun
-- is a no-op rather than a re-clear of a value the API has since written.
--
-- Explicit BEGIN/COMMIT because `psql -f` does NOT wrap the file (#340).
--
-- DEPLOY ORDER: THIS MIGRATION MUST RUN BEFORE THE API DEPLOY. models.py
-- declares TournamentMatch.photon_region, which puts it in SQLAlchemy's INSERT
-- for every bracket row, and two endpoints SELECT it by name — an API running
-- ahead of this migration fails bracket construction at lock and 500s
-- /tournaments/current and /tournaments/my-active-matches (#235/#346). Do not
-- read the wrapper's first-arm "No such file or directory" line as failure —
-- it always prints that before the fallback succeeds (#243); confirm from the
-- statement tags and the post-check NOTICEs below.

BEGIN;

-- Nullable with no default. NULL is a meaningful value here ("this match has
-- no per-pair answer — use the tournament's"), which is also exactly what
-- async rows keep forever, so a default would erase the distinction.
ALTER TABLE tournament_matches ADD COLUMN IF NOT EXISTS photon_region VARCHAR(16);

-- Clear the stale 'ru' on the one running async tournament. Targeted by id AND
-- kind so it can never touch a sync tournament, and guarded on IS NOT NULL so
-- a rerun after the API has (correctly) left it NULL does nothing at all.
-- Completed history is left intact on purpose: c3c448f3 keeps its 'us' because
-- nothing reads a completed tournament's region and the record should stay
-- truthful about what was played.
UPDATE tournaments
   SET photon_region = NULL
 WHERE id = 'a2d3c090-54c9-46ae-a4e2-fa1b85f0f10c'::uuid
   AND kind = 'async'
   AND photon_region IS NOT NULL;

-- Post-checks. Both assert something a silently-skipped statement would break,
-- rather than something guaranteed by construction (#342).
DO $$
DECLARE
    have_col BIGINT;
    stale    BIGINT;
BEGIN
    SELECT COUNT(*) INTO have_col
      FROM information_schema.columns
     WHERE table_name = 'tournament_matches'
       AND column_name = 'photon_region';
    IF have_col <> 1 THEN
        RAISE EXCEPTION '219 post-check FAILED: tournament_matches.photon_region missing after ALTER';
    END IF;
    RAISE NOTICE '219 post-check OK: tournament_matches.photon_region exists';

    SELECT COUNT(*) INTO stale
      FROM tournaments
     WHERE kind = 'async'
       AND status IN ('voting', 'locked', 'running')
       AND photon_region IS NOT NULL;
    IF stale > 0 THEN
        RAISE EXCEPTION '219 post-check FAILED: % live async tournament(s) still pin a photon_region', stale;
    END IF;
    RAISE NOTICE '219 post-check OK: no live async tournament pins a region';
END $$;

COMMIT;
