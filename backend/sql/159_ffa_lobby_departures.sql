-- 159: FFA lobby departure tracking (Codex round-2 review finds 6/7).
-- A played lobby now survives member leaves (find 2 of the previous round),
-- so the lobby needs to KNOW who left: the bettable field must exclude
-- departed players, and the lobby closes when all-but-one member has left
-- (leave-driven closure instead of relying on queue rows that get deleted).
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS departed_ids UUID[] NOT NULL DEFAULT '{}';
