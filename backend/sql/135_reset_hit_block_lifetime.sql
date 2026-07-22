-- 135_reset_hit_block_lifetime.sql — July 21
--
-- One-shot reset of the lifetime hit/block counters at the counting-fix
-- ship. Precedent: migration 040 did the identical zero in v1.23 for the
-- same reason (bad hit semantics). This time all four columns — the hit
-- counting moved to direct bullet impacts only AND the block spec changed
-- (July 21), so every pre-fix total mixes eras and cannot be corrected
-- per-game.
--
-- Zero-and-accumulate-forward, deliberately NOT recompute-from-matches: the
-- per-match p1_/p2_ columns include OPPONENT-sourced numbers (cr_gstats
-- snapshots, possibly from an old client), while the lifetime accumulator is
-- reporter-only by design — a recompute would silently change semantics and
-- import unattributable old-client data.
--
-- Idempotent (no-op after the first pass). The server-side version gate
-- (STATS_CLEAN_MIN_VERSION in main.py) keeps old clients from repolluting
-- these counters after the reset.

UPDATE players
   SET bullets_fired = 0, bullets_hit = 0,
       blocks_activated = 0, blocks_successful = 0
 WHERE bullets_fired <> 0 OR bullets_hit <> 0
    OR blocks_activated <> 0 OR blocks_successful <> 0;
