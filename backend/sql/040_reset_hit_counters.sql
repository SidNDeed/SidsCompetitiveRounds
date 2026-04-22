-- v1.23.x — One-shot reset of bullets_fired/bullets_hit on all players.
--
-- The original v1.23 implementation counted bullets_hit as "every HealthHandler.TakeDamage
-- event triggered by the local player" and bullets_fired as "mouse trigger pulls." That
-- produced absurd ratios (one production row showed 43 fires / 429 hits = 998% accuracy)
-- because DOT ticks, shotgun pellets, bounces, and card-effect splash damage all counted
-- as "hits" while only trigger pulls counted as "fires."
--
-- The client-side fix (v1.23.x+) gates hit credit per-shot: each trigger pull arms the
-- gate, and only the FIRST damage event after that click increments bullets_hit. That
-- makes hit% bounded 0-100 and means "% of shots that connected with an enemy."
--
-- Existing rows mix old (uncapped) and new (gated) counts and can't recover a meaningful
-- percentage without a reset. Zero both columns so the gated counts accumulate cleanly.
-- blocks_activated / blocks_successful aren't affected — their semantics were fine.
--
-- Idempotent (UPDATE with no filter — re-running is a no-op after the first pass).

UPDATE players
   SET bullets_fired = 0,
       bullets_hit   = 0
 WHERE bullets_fired <> 0 OR bullets_hit <> 0;
