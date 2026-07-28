-- 156: FFA recent-panel data (Sid round-2 item 2). Additive.
-- rolled: card was pushed out by the rolling 5-card cap (rendered red).
-- timeline: compact per-half-point event list "slot[R][G],slot,..." recorded
-- by the reporter's engine — feeds the score-progression hover graph.
ALTER TABLE ffa_match_cards ADD COLUMN IF NOT EXISTS rolled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS timeline TEXT;
