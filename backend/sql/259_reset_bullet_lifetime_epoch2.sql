-- 259: one-shot reset of the LIFETIME bullet counters at the #308 counting fix.
--
-- HELD - DO NOT APPLY WITHOUT THE OWNER'S EXPLICIT WORD. This wipes career
-- Hit% for every player who has one. There is precedent (migrations 040 and
-- 135 did the same thing for the same symptom class) but precedent is a record
-- of the owner approving it before, not standing authorisation.
--
-- WHY -------------------------------------------------------------------
-- Bug #308: career Hit% saturating at 100%. Pre-fix clients gated the FIRED
-- side of the counter on a pick-phase flag driven by ROUNDS' debug-log TEXT
-- while leaving the HIT side open. That flag is false from "Round over" until
-- "PICK PHASE" is logged ~2.3s later, so it never covered the window it was
-- named for - what it actually covered was live combat frames on either side
-- of the round boundary. Shots fired there were refused the denominator while
-- hits from earlier shots kept counting, so the ratio climbed, and a
-- hits<=fired budget clamp pinned it at exactly 100% rather than above it.
--
-- The mixed totals cannot be corrected in place: the lifetime accumulator is a
-- running sum with no per-era breakdown, and the per-match columns are not a
-- substitute (they include OPPONENT-sourced cr_gstats snapshots, possibly from
-- old clients, whereas the lifetime figure is reporter-only by design - the
-- same reason migration 135 chose zero-and-accumulate-forward over a
-- recompute).
--
-- SCOPE: bullets ONLY. blocks_activated / blocks_successful are NOT touched.
-- The block spec was fixed in 1.34.0 and has been correct for four releases;
-- discarding it would be a second, unrelated data loss. This is why main.py now
-- carries BULLET_STATS_CLEAN_MIN_VERSION separately from
-- STATS_CLEAN_MIN_VERSION - one shared floor could not express "bullets are
-- broken, blocks are fine".
--
-- Per-match history rows are untouched and stay historical.
--
-- DEPLOY ORDER (matters, learning #236) -----------------------------------
--   1. Deploy the API carrying the split floor FIRST. Its bullet floor is
--      above every released build, so bullet accumulation stops dead the
--      moment it is live. That freezes the pollution.
--   2. Apply THIS migration. Nothing can repollute, because no client in the
--      wild clears the new floor yet.
--   3. Ship the fixed client. Only then do clean numbers start accumulating.
-- Running this BEFORE step 1 leaves every 1.39.3-and-below client feeding the
-- freshly-zeroed columns for the length of the gap.
--
-- RERUN SAFETY ------------------------------------------------------------
-- A reset is NOT rerun-safe just because it is a reset, and migration 135's
-- "idempotent (no-op after the first pass)" claim is only true if it is never
-- run a second time. Its WHERE clause skips when the totals are ALREADY zero -
-- which does nothing to protect clean data accumulated afterwards. The deploy
-- wrapper re-executes the whole file on any nonzero exit, so a second pass is
-- reachable by accident, and it would silently destroy real player data.
-- Hence an explicit applied-marker: the reset runs if and only if this exact
-- epoch has never been applied.
--
-- BEGIN/COMMIT are explicit because `psql -f` does not wrap a file in a
-- transaction (learning #340).

BEGIN;

CREATE TABLE IF NOT EXISTS stats_epoch_resets (
    epoch_key   TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    rows_reset  INTEGER      NOT NULL
);

DO $$
DECLARE
    n         INTEGER;
    carriers  INTEGER;
BEGIN
    IF EXISTS (SELECT 1 FROM stats_epoch_resets WHERE epoch_key = 'bullets_epoch2') THEN
        RAISE NOTICE 'no-op: bullets_epoch2 reset already applied (marker present)';
        RETURN;
    END IF;

    SELECT COUNT(*) INTO carriers
      FROM players
     WHERE COALESCE(bullets_fired, 0) <> 0 OR COALESCE(bullets_hit, 0) <> 0;

    UPDATE players
       SET bullets_fired = 0,
           bullets_hit   = 0
     WHERE COALESCE(bullets_fired, 0) <> 0 OR COALESCE(bullets_hit, 0) <> 0;
    GET DIAGNOSTICS n = ROW_COUNT;

    INSERT INTO stats_epoch_resets (epoch_key, rows_reset)
    VALUES ('bullets_epoch2', n);

    -- Can actually fail: a surviving non-zero total means the UPDATE did not do
    -- what this migration claims, and the marker must not be trusted.
    IF EXISTS (SELECT 1 FROM players
                WHERE COALESCE(bullets_fired, 0) <> 0 OR COALESCE(bullets_hit, 0) <> 0) THEN
        RAISE EXCEPTION 'bullet totals still non-zero after reset';
    END IF;

    RAISE NOTICE 'post-check OK: zeroed lifetime bullet counters for % player(s) (% carried data); blocks untouched',
                 n, carriers;
END $$;

COMMIT;
