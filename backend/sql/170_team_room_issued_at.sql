-- 170: 2v2 assembly deadline needs its own clock (July 30 lifecycle audit item 4).
--
-- The 60s assembly cancel measured from team_series.created_at, which is set
-- when the four players are MATCHED — so the deadline also had to cover
-- ready-up (up to 120s), Photon connect, map load and spawn-confirm delivery.
-- A state poll landing right after room issue could cancel a healthy assembly
-- because the earlier clock had already expired.
--
-- room_issued_at is stamped by the queue poll that generates the Photon room
-- (the moment all four are committed); the assembly deadline now measures from
-- it. NULL for every pre-migration row and for series that never reached room
-- issue — consumers COALESCE back to created_at, which is exactly the old
-- (conservative) behaviour.

ALTER TABLE team_series ADD COLUMN IF NOT EXISTS room_issued_at TIMESTAMPTZ;
