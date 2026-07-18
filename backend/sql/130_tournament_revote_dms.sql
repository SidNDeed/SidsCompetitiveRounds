-- 130_tournament_revote_dms.sql — July 17 (round 2 revision)
--
-- Companion to the mandatory-time-voting rework. Signups made while voting
-- was optional have zero tournament_time_votes rows, and the new lock
-- REMOVES any signup without a vote on the winning slot. Per the
-- maintainer's call: don't silently seed votes for them (the first revision
-- of this migration did) — DM them via the pending_dms queue so they
-- actively pick the times they can make; anyone who ignores it is removed
-- at lock with no penalty (and gets the removal DM).
--
-- APPLY ORDER: 129 (pending_dms table) must be applied first, and the bot
-- must be redeployed (its drain loop sends these) around the same time.

BEGIN;

INSERT INTO pending_dms (steam_id, content)
SELECT p.steam_id,
       'Heads up — the Synchronized tournament changed: you now pick which start times you can make, and the tournament locks on the time 8+ players agree on. You''re signed up but have NO times picked, so you''ll be removed at lock (no penalty) unless you open F5 -> Tournaments and pick your available slots. One more thing worth knowing before you commit: a full double-elim run takes a couple of hours (with short breaks between matches). — Sid'
FROM tournament_signups ts
JOIN tournaments t ON t.id = ts.tournament_id
JOIN players p ON p.id = ts.player_id
WHERE t.kind = 'sync' AND t.status = 'voting'
  AND NOT EXISTS (
      SELECT 1 FROM tournament_time_votes v
      WHERE v.tournament_id = ts.tournament_id
        AND v.player_id = ts.player_id);

-- Sanity output: who will be DMed.
SELECT p.display_name, p.steam_id
FROM tournament_signups ts
JOIN tournaments t ON t.id = ts.tournament_id
JOIN players p ON p.id = ts.player_id
WHERE t.kind = 'sync' AND t.status = 'voting'
  AND NOT EXISTS (
      SELECT 1 FROM tournament_time_votes v
      WHERE v.tournament_id = ts.tournament_id
        AND v.player_id = ts.player_id);

COMMIT;
