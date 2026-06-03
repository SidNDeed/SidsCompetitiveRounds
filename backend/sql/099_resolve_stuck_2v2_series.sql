-- 099_resolve_stuck_2v2_series.sql
--
-- Resolve three stuck 2v2 series surfaced 2026-06-01:
--
--   4af535c0  COMPLETE as team-1 win (Sid + MAX1T0P).  Sid+MAX vs Nix+NotHoly was
--             1-1 when Nix+NotHoly left; per the anti-abuse rule the non-DC team
--             that had already won a game takes the series. The two played games
--             already credited per-match gold/xp (15g/1500xp each) but the series
--             never got its completion bonus, winner, or counter. We finish it here.
--   cc487bcd  VOID (May 13). The team that was WINNING 1-0 disconnected; the
--             remaining team had not won a game, so no auto-win is warranted.
--   ff8ad31f  VOID (May 19). 'pre_match_leaver' — leave during setup before a real
--             series formed; 2+ weeks old, not worth rewriting.
--
-- Glicko ratings are NOT applied here — migration 100 rebuilds ALL 2v2 Glicko from
-- the completed-series history (this migration must run FIRST so 4af535c0 is
-- 'completed' when 100 replays). Verified against production via sql-readonly before
-- writing. Idempotent on re-run (guards on current status).

BEGIN;

-- ── 4af535c0: complete as team-1 win + series-completion gold (+50 win / +25 loss) ──
-- Slots (verified): t1a=Sid, t1b=MAX1T0P (winners); t2a=Nix, t2b=NotHoly (DC team).
UPDATE team_series
   SET status='completed', winner_team=1, completed_at='2026-06-01 19:58:12+00'::timestamptz,
       invalidation_reason='dc_leadforfeit',
       t1a_gold_earned = COALESCE(t1a_gold_earned,0) + 50,
       t1b_gold_earned = COALESCE(t1b_gold_earned,0) + 50,
       t2a_gold_earned = COALESCE(t2a_gold_earned,0) + 25,
       t2b_gold_earned = COALESCE(t2b_gold_earned,0) + 25
 WHERE id='4af535c0-3ed0-425d-a462-75e1e4bc9799' AND status='active';

-- Credit the series-completion gold to the four players (winners +50, losers +25)
-- + audit rows. Mirrors the live submit_team_match completion path.
UPDATE players SET gold_earned=COALESCE(gold_earned,0)+50, team_gold_earned=COALESCE(team_gold_earned,0)+50
 WHERE id IN ('fbb3d29d-b637-43c0-9787-357c2753e28c','2c5a8c23-950f-48dd-a293-df255f61831c')
   AND EXISTS (SELECT 1 FROM team_series WHERE id='4af535c0-3ed0-425d-a462-75e1e4bc9799' AND status='completed');
UPDATE players SET gold_earned=COALESCE(gold_earned,0)+25, team_gold_earned=COALESCE(team_gold_earned,0)+25
 WHERE id IN ('43b2cc39-5510-41ae-a2e0-a72a507ab76c','42b61a5c-2088-44c9-8032-73f95776e90b')
   AND EXISTS (SELECT 1 FROM team_series WHERE id='4af535c0-3ed0-425d-a462-75e1e4bc9799' AND status='completed');

INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT pid, amt, rsn, '4af535c0-3ed0-425d-a462-75e1e4bc9799'
  FROM (VALUES
        ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, 50, 'team_series_win'),
        ('2c5a8c23-950f-48dd-a293-df255f61831c'::uuid, 50, 'team_series_win'),
        ('43b2cc39-5510-41ae-a2e0-a72a507ab76c'::uuid, 25, 'team_series_loss'),
        ('42b61a5c-2088-44c9-8032-73f95776e90b'::uuid, 25, 'team_series_loss')
       ) AS v(pid, amt, rsn)
 WHERE NOT EXISTS (
     SELECT 1 FROM gold_transactions
      WHERE reference_id='4af535c0-3ed0-425d-a462-75e1e4bc9799'
        AND reason IN ('team_series_win','team_series_loss')
 );

-- ── cc487bcd: VOID (leading-leaver, no auto-win) ──
UPDATE team_series
   SET status='cancelled', completed_at=NOW(), invalidation_reason='admin_void_leading_leaver'
 WHERE id='cc487bcd-0792-428c-b402-a705e7a57d59' AND status IN ('dc_paused','active');
UPDATE team_matches SET invalidated_at=NOW(), invalidation_reason='admin_void_leading_leaver'
 WHERE series_id='cc487bcd-0792-428c-b402-a705e7a57d59' AND invalidated_at IS NULL;

-- ── ff8ad31f: VOID (pre-match leaver) ──
UPDATE team_series
   SET completed_at=COALESCE(completed_at, NOW()), invalidation_reason='admin_void_pre_match_leaver'
 WHERE id='ff8ad31f-95a8-46bf-9bc8-e2fbe3d0480e' AND status='cancelled';
UPDATE team_matches SET invalidated_at=NOW(), invalidation_reason='admin_void_pre_match_leaver'
 WHERE series_id='ff8ad31f-95a8-46bf-9bc8-e2fbe3d0480e' AND invalidated_at IS NULL;

COMMIT;
