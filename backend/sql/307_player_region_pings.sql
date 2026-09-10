-- 307_player_region_pings.sql
-- Sept 10 batch: the multiplayer room-region pick (2v2 / 1v2 / FFA queue rooms
-- and hosted lobbies) — ai-collab/sept10-batch/02-region-v4.md over
-- ai-collab/sept9-plans/02-multiplayer-region.md §2.
--
-- Each member's own Photon ping map, one row per player, written by the
-- session-bound multiplayer polls (the 2v2 / 1v2 / FFA queue polls and the
-- 2v2 / 1v2 lobby state polls) from the X-Region-Pings header the 1v1 poll
-- already carries, for the authenticated caller only. At issuance the
-- members' rows are read and the room may leave the mode-of-homes baseline
-- when either half the room gains 20 ms or nobody loses more than 30 ms, and
-- then only if the room's total ping falls (main.py _group_region over the
-- pure rule in region_pick.py).
--
-- pings        {"us": 42, "eu": 31, ...}  <= 24 entries, ms in 1..5000
-- measured_at  when the client completed the sweep (now() - age at write);
--              judged against the 180 s issuance window only
-- received_at  the last write — the janitor deletes rows older than ONE HOUR,
--              which is what the ranked consent copy promises
-- gen_nonce /  the client process's random nonce and sweep counter (optional
-- gen_seq      X-Region-Pings-Gen header): a new nonce always replaces the
--              row, the same nonce needs a greater seq, and a map without a
--              generation replaces only a strictly older measured_at — so the
--              order of sweeps, not of arrivals, decides which map stands.
--
-- Not declared on the ORM: raw SQL on both ends (the 296 / 301 pattern).
-- delete-my-data deletes the row explicitly — the players row is anonymised,
-- never deleted, so the CASCADE is decorative under anonymise-in-place.
-- Deploy order: this file BEFORE the api (the janitor's purge names the table).
BEGIN;

CREATE TABLE IF NOT EXISTS player_region_pings (
    player_id   UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    pings       JSONB NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    gen_nonce   TEXT NULL,
    gen_seq     INTEGER NULL
);

COMMIT;
