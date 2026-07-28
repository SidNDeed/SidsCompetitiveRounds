-- 155: FFA kill credits (placement tie-break, Sid's playtest item 3).
-- Placement is now (rounds desc, points_total desc, kills desc); the client
-- tallies kill credits from each death's lastSourceOfDamage and reports them
-- outside the frozen ffa: HMAC canonical. Old rows/clients default to 0,
-- which degrades to the previous two-key ordering.
ALTER TABLE ffa_match_players ADD COLUMN IF NOT EXISTS kills INTEGER NOT NULL DEFAULT 0;
