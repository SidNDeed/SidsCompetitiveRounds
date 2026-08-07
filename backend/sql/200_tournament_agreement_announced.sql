-- 200: marker for the sync-tournament "a start time is agreed" announcement.
--
-- THE BUG (Sid, screenshot, 2026-08-07). The Discord feed announced
-- "enough players have joined! The tournament will start <time>" the moment the
-- SIGNUP COUNT reached min_players, and the time it printed was
-- `default_start_ts` — the pre-vote placeholder. For a sync tournament neither
-- half is true: the roster agreeing to PLAY is not the roster agreeing to a
-- TIME, and the time actually played is the vote-resolved `scheduled_start_ts`,
-- chosen at lock from the slot tally. Players were being told a tournament was
-- ready at a time nobody had voted for.
--
-- Worse, the announcement could only ever fire from the signup endpoint. In a
-- sync tournament the threshold is normally crossed by someone VOTING, not
-- joining — so once signups were already above min_players, reaching actual
-- agreement announced nothing at all.
--
-- WHY A COLUMN. The corrected trigger ("some slot has >= min_players votes")
-- is re-evaluated on every signup and every vote, and votes can be changed or
-- withdrawn, so the condition can flap. Without a durable marker the feed would
-- re-announce each time it re-crossed. tournament_notices was considered and
-- rejected: it is keyed per PLAYER, and this is a tournament-level event.
--
-- Nullable with no default and no backfill: NULL means "not yet announced",
-- which is the correct state for every existing tournament. A currently-voting
-- tournament that already has agreement will announce once on the next signup
-- or vote — correct, and the message is accurate when it lands.

ALTER TABLE tournaments
    ADD COLUMN IF NOT EXISTS agreement_announced_at TIMESTAMPTZ;

DO $$
DECLARE
    ok BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'tournaments'
           AND column_name = 'agreement_announced_at'
    ) INTO ok;
    IF NOT ok THEN
        RAISE EXCEPTION 'migration 200: agreement_announced_at was not added';
    END IF;
    RAISE NOTICE 'migration 200 post-check OK';
END $$;
