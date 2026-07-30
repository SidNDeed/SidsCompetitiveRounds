-- 167: FFA damage-dealt + kill/damage timelines (bug reports #127 and #130)
--
-- Sid asked the Discord /game card for FFA to graph "kills scored and damage
-- dealt", and My Stats -> Record to show "avg damage done per game". Neither was
-- possible: the entire database had no damage column at all (only damage TAKEN,
-- which lives as the left half of ffa_match_players.block_timeline and is not
-- attributable to a dealer), and kills existed only as a per-match total.
--
-- Damage dealt IS attributable client-side: vanilla HealthHandler.DoDamage
-- receives the dealing Player, and CallTakeDamage RPCs to All, so every client
-- observes every attributed hit. The reporter therefore produces a complete
-- per-player table with no new Photon heartbeat fields.
--
-- Nullability is deliberate:
--   damage_dealt IS NULL          = this game predates the telemetry (or the
--                                   client didn't send it) -> excluded from the
--                                   avg-damage aggregate, which averages only
--                                   rows that actually carry the metric.
--   damage_dealt = 0              = the player genuinely dealt no damage.
-- A NOT NULL DEFAULT 0 here would silently drag every player's career average
-- toward zero for months of pre-existing games (learning #2: match the column
-- default to the intended semantics, not to what looks tidy).
--
-- Widths mirror the existing sibling timelines: the client caps at 128 samples
-- on a 3s cadence and clamps the strings before sending.
--
-- Idempotent; safe to re-run (the migrate wrapper re-executes the whole file on
-- its first-attempt path failure — learning #243).

-- `absent` (review find): an FFA sitting freezes its roster at lock, so every
-- later game's report must still carry a member who left in an EARLIER game --
-- they hold their slot but were never in THIS game, and the server already skips
-- rating/XP for them. The report has always sent that flag; the row never stored
-- it. Consequence for this bug: those all-zero ghost rows landed in the new
-- kills/damage averages as if they were played games, so a player who left after
-- one strong game watched their average decay with every later game of a sitting
-- they were not in. Storing it makes the ghosts identifiable to every future
-- query instead of forcing an all-zero-tallies heuristic (which #227 warns
-- against). Pre-existing rows default false; harmless, because damage_dealt is
-- NULL for all of them and the kills average uses the played-games denominator.

ALTER TABLE ffa_match_players
    ADD COLUMN IF NOT EXISTS damage_dealt INTEGER,
    ADD COLUMN IF NOT EXISTS damage_dealt_timeline VARCHAR(1024),
    ADD COLUMN IF NOT EXISTS kill_timeline VARCHAR(512),
    ADD COLUMN IF NOT EXISTS absent BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN ffa_match_players.damage_dealt IS
    'Total damage this player dealt to opponents this game (HP). NULL = not reported by the client (pre-v1.35.3 games); 0 = dealt none.';
COMMENT ON COLUMN ffa_match_players.damage_dealt_timeline IS
    'Cumulative damage dealt, comma-separated ints, one sample per 3s (cap 128).';
COMMENT ON COLUMN ffa_match_players.kill_timeline IS
    'Cumulative kills, comma-separated ints, one sample per 3s (cap 128).';
COMMENT ON COLUMN ffa_match_players.absent IS
    'TRUE = roster ghost: left in an EARLIER game of the sitting, holds the slot but did not play THIS game. Excluded from per-game stat averages.';

DO $$
DECLARE
    n_cols INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_cols
      FROM information_schema.columns
     WHERE table_name = 'ffa_match_players'
       AND column_name IN ('damage_dealt', 'damage_dealt_timeline', 'kill_timeline', 'absent');
    IF n_cols <> 4 THEN
        RAISE EXCEPTION 'post-check FAILED: expected 4 new columns on ffa_match_players, found %', n_cols;
    END IF;
    RAISE NOTICE 'post-check OK: ffa_match_players carries damage_dealt + damage_dealt_timeline + kill_timeline + absent';
END $$;
