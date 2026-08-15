-- 220: soft-delete the stale/mis-routed language-channel chat rows feeding
-- the bot's Discord repost loop (bug 226).
--
-- WHY. The bot's 30s catchup polls /chat/recent, whose per-channel-fairness
-- window keeps a quiet channel's ENTIRE history permanently inside the fetch.
-- The es/ru/sv channels are quiet enough that the same ~27 rows were
-- re-fetched on every poll forever; the bot's in-memory dedup FIFO evicted
-- them as a chunk every ~300 claims and the next poll re-posted all of them
-- to the Discord language channels — repeatedly. The bot-side fix (a durable
-- max-id cursor) ships with this migration; this file removes the rows that
-- should never have been in the language channels at all, so the fairness
-- window carries real content instead of test noise:
--   - Sid's own test rows in es/ru/sv (steam_id 76561198040410653, non-global)
--   - the two Aug-4 Archnith mis-route rows (ids 4681/4682 — the second one
--     literally reads "why was i sent to spanish chat??")
-- DELIBERATELY NOT touched (scoped to confirmed-test/mis-route rows only):
--   - SuperBearxD's es rows (possibly a genuine Spanish-locale player)
--   - Archnith's later Aug-6 es rows (ids 4888, 4943 — not confirmed
--     mis-routes; only the two Aug-4 rows were named by the diagnosis)
--   - the one Discord-sourced "Sid" es row (id 6233, steam_id IS NULL — a
--     Discord relay, never re-forwarded by the bot, outside this cleanup)
--
-- Soft delete only: same mechanism as the live moderation path (main.py sets
-- deleted_at + deleted_by_steam_id); /chat/recent and the in-game scrollback
-- both filter `deleted_at IS NULL`, so these rows vanish from every window
-- while keeping the audit trail. deleted_by_steam_id stays NULL on purpose —
-- this is maintenance, not a moderator action, and a fabricated moderator id
-- would lie to any surface that renders "deleted by X".
--
-- created_at bound: belt-and-suspenders so a LATE apply can never eat a
-- genuine future Sid message in a language channel — every targeted row
-- predates 2026-08-15 (dry-run below), and the predicate says so explicitly.
--
-- Dry-run counts against production, 2026-08-15 (#313 — SELECT bodies were
-- executed via sql-readonly before this file was written):
--   Sid  es 17 (ids 4565..4935), ru 4 (ids 4571..4593), sv 1 (id 6051) = 22
--   Archnith mis-routes: ids 4681, 4682 (both live, channel 'es')      =  2
--   expected first-run total: 24
--
-- Idempotent: WHERE deleted_at IS NULL — a rerun (the deploy wrapper
-- re-executes the whole file on a nonzero first exit, #243) matches 0 rows
-- and the post-check still passes. Explicit BEGIN/COMMIT because psql -f
-- autocommits per statement (#340).

BEGIN;

DO $$
DECLARE
    n bigint;
    remaining bigint;
BEGIN
    UPDATE chat_messages
       SET deleted_at = NOW()
     WHERE deleted_at IS NULL
       AND created_at < TIMESTAMPTZ '2026-08-15 00:00:00+00'
       AND (
            (steam_id = '76561198040410653' AND channel <> 'global')
         OR id IN (4681, 4682)
       );
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE '220: soft-deleted % stale language-channel rows (expected 24 on first run, 0 on rerun)', n;

    -- Post-check on REMAINING LIVE rows, not this run's count — a rerun
    -- legitimately reports 0 deleted and must still pass.
    SELECT COUNT(*) INTO remaining
      FROM chat_messages
     WHERE deleted_at IS NULL
       AND created_at < TIMESTAMPTZ '2026-08-15 00:00:00+00'
       AND (
            (steam_id = '76561198040410653' AND channel <> 'global')
         OR id IN (4681, 4682)
       );
    IF remaining > 0 THEN
        RAISE EXCEPTION '220: % targeted rows still live after UPDATE', remaining;
    END IF;
    RAISE NOTICE '220: post-check OK (0 targeted rows remain live)';
END $$;

COMMIT;
