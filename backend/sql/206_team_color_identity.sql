-- 206: body-colour team identity (Sid, Aug 8 — team-color-v2).
--
-- 2v2: a team is named after its colour holder's equipped body colour
-- (kind='player_color' shop item). Decided ONCE server-side at series
-- creation — sole holder wins, two holders coin-flip, mirror match leaves
-- team 2 vanilla — and PERSISTED here so every client renders the same
-- identity and a mid-series re-equip cannot shift it (freeze at series
-- start). Continuations INHERIT the prior series' stamp (side-swapped when
-- the split flipped) so a sitting keeps one identity.
--
-- FFA: per-player match-time stamp for the Recent Ranked FFA point tinting.
-- NULL = no colour equipped / pre-feature row — deliberately NULLable so
-- history stays honest (#257); consumers must treat NULL as vanilla, never
-- as black.
--
-- Order: apply BEFORE the API deploy is not required — every writer is
-- savepointed (#235) and degrades to unstamped — but apply in the same
-- deploy window so stamps start landing.

ALTER TABLE team_series ADD COLUMN IF NOT EXISTS t1_color_name VARCHAR(40);
ALTER TABLE team_series ADD COLUMN IF NOT EXISTS t1_color_hex  VARCHAR(9);
ALTER TABLE team_series ADD COLUMN IF NOT EXISTS t2_color_name VARCHAR(40);
ALTER TABLE team_series ADD COLUMN IF NOT EXISTS t2_color_hex  VARCHAR(9);

ALTER TABLE ffa_match_players ADD COLUMN IF NOT EXISTS color_name VARCHAR(40);
ALTER TABLE ffa_match_players ADD COLUMN IF NOT EXISTS color_hex  VARCHAR(9);

DO $$
BEGIN
  RAISE NOTICE 'migration 206 OK: team/FFA colour identity columns ready';
END $$;
