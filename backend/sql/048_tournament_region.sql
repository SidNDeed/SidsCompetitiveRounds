-- ============================================================
-- Tournaments — region-aware auto-connect
-- ============================================================
-- Adds:
--   tournament_signups.region_at_signup  VARCHAR(16) — Photon region the
--     player was on when they signed up ("us", "eu", "asia", "jp", "usw",
--     "cae", "sa", "kr", etc.). Nullable for rows predating this migration
--     and for clients that failed to resolve a region at signup time.
--   tournaments.photon_region            VARCHAR(16) — region pinned at lock.
--     Picked as the most-common region across confirmed signups (alphabetical
--     tiebreak on count ties). All auto-connect handoffs for matches in this
--     tournament force both clients to reconnect to this region before
--     JoinOrCreateRoom, so cross-region pairings meet reliably in one Photon
--     room instead of silently creating two separate rooms.
-- Classification: additive-safe.
-- ============================================================

ALTER TABLE tournament_signups
    ADD COLUMN IF NOT EXISTS region_at_signup VARCHAR(16);

ALTER TABLE tournaments
    ADD COLUMN IF NOT EXISTS photon_region VARCHAR(16);

-- Verification:
--   \d+ tournament_signups
--   \d+ tournaments
