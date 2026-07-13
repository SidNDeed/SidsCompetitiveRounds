-- 115: Backfill the July 12 recording gap (bug reports #70 and #65).
--
-- Bug #70: the /team/series/continuation endpoint 500'd on its create path
-- (function-local import bug, fixed in code), so every 2v2 game after the
-- first completed series of the sitting was dropped client-side. The five
-- lost games are reconstructed from the reporter's BepInEx log attached to
-- report #70: all wins for T1 (Sid + Stan) vs (Farming on my mind +
-- genderswapday) — series 2: 5-1, 5-3; series 3: 5-0, 5-1; plus game 1 of an
-- unfinished 4th series: 5-2.
--
-- Bug #65: Stan's last casual match vs "enoch :)" (room 109775242904479663,
-- 5-0 Stan) was lost to a transient DNS outage on the reporter's machine
-- after 3 POST attempts. Sibling rows for the same sitting exist; this
-- mirrors their exact shape (casual, 475/250 xp).
--
-- Glicko values below were computed OFFLINE via scripts-equivalent replay
-- (backend/api/glicko2.calculate_new_rating, tau 0.5, one rating period per
-- series, each player vs both opponents from pre-series snapshots) on top of
-- the live glicko_ratings_2v2 snapshot taken 2026-07-13 — these two series
-- are chronologically the latest completed 2v2 series, so the incremental
-- application equals a full rebuild.
--   series 2 deltas: Sid +16.5, Stan +28.2, opponents -42.0 each
--   series 3 deltas: Sid +11.9, Stan +18.4, opponents -26.5 each
--
-- Not recoverable with confidence, deliberately omitted: per-game card picks
-- (team_match_cards / match_cards) and per-round points totals (left 0).
-- Match timestamps are evenly spaced estimates inside the known window
-- (series 1 completed 23:11:06Z; report #70 filed 23:50:44Z).
--
-- Idempotent: fixed UUIDs + IF NOT EXISTS-style guards on every insert.

BEGIN;

-- ── Players (ids verified against live DB) ──────────────────────────────
-- Sid   fbb3d29d-b637-43c0-9787-357c2753e28c   (76561198040410653)
-- Stan  ef39f993-7ede-4017-901d-bc637dd743d2   (76561198983423367)
-- Farm  ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d   (76561198295504414)
-- Gsd   7df6bcd5-a2af-4022-ac77-6b29337c77cf   (76561199050262261)
-- enoch 22b87892-a122-4355-afd8-31e18fed1424   (13040669204355181255)

-- ── 2v2 series 2 (games 3-4) ─────────────────────────────────────────────
INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id,
                         t1_series_wins, t2_series_wins, status, winner_team,
                         t1a_rating_change, t1b_rating_change, t2a_rating_change, t2b_rating_change,
                         photon_room_id, region, was_auto_balanced,
                         created_at, completed_at)
SELECT '9a1c7702-0000-4000-8000-000000000002',
       'fbb3d29d-b637-43c0-9787-357c2753e28c', 'ef39f993-7ede-4017-901d-bc637dd743d2',
       'ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d', '7df6bcd5-a2af-4022-ac77-6b29337c77cf',
       2, 0, 'completed', 1,
       16.5, 28.2, -42.0, -42.0,
       'team_cb2c661d688b', 'us', false,
       '2026-07-12 23:12:30+00', '2026-07-12 23:25:00+00'
WHERE NOT EXISTS (SELECT 1 FROM team_series WHERE id = '9a1c7702-0000-4000-8000-000000000002');

INSERT INTO team_matches (id, series_id, t1a_id, t1b_id, t2a_id, t2b_id,
                          t1_rounds_won, t2_rounds_won, winner_team, is_ranked,
                          photon_room_id, region, reported_by, started_at, ended_at, created_at)
SELECT '9a1c7702-0000-4000-8000-00000000a003', '9a1c7702-0000-4000-8000-000000000002',
       'fbb3d29d-b637-43c0-9787-357c2753e28c', 'ef39f993-7ede-4017-901d-bc637dd743d2',
       'ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d', '7df6bcd5-a2af-4022-ac77-6b29337c77cf',
       5, 1, 1, true,
       'team_cb2c661d688b_231230_r6', 'us', 'fbb3d29d-b637-43c0-9787-357c2753e28c',
       '2026-07-12 23:12:30+00', '2026-07-12 23:18:30+00', '2026-07-12 23:18:30+00'
WHERE NOT EXISTS (SELECT 1 FROM team_matches WHERE id = '9a1c7702-0000-4000-8000-00000000a003');

INSERT INTO team_matches (id, series_id, t1a_id, t1b_id, t2a_id, t2b_id,
                          t1_rounds_won, t2_rounds_won, winner_team, is_ranked,
                          photon_room_id, region, reported_by, started_at, ended_at, created_at)
SELECT '9a1c7702-0000-4000-8000-00000000a004', '9a1c7702-0000-4000-8000-000000000002',
       'fbb3d29d-b637-43c0-9787-357c2753e28c', 'ef39f993-7ede-4017-901d-bc637dd743d2',
       'ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d', '7df6bcd5-a2af-4022-ac77-6b29337c77cf',
       5, 3, 1, true,
       'team_cb2c661d688b_231900_r8', 'us', 'fbb3d29d-b637-43c0-9787-357c2753e28c',
       '2026-07-12 23:19:00+00', '2026-07-12 23:25:00+00', '2026-07-12 23:25:00+00'
WHERE NOT EXISTS (SELECT 1 FROM team_matches WHERE id = '9a1c7702-0000-4000-8000-00000000a004');

-- ── 2v2 series 3 (games 5-6) ─────────────────────────────────────────────
INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id,
                         t1_series_wins, t2_series_wins, status, winner_team,
                         t1a_rating_change, t1b_rating_change, t2a_rating_change, t2b_rating_change,
                         photon_room_id, region, was_auto_balanced,
                         created_at, completed_at)
SELECT '9a1c7702-0000-4000-8000-000000000003',
       'fbb3d29d-b637-43c0-9787-357c2753e28c', 'ef39f993-7ede-4017-901d-bc637dd743d2',
       'ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d', '7df6bcd5-a2af-4022-ac77-6b29337c77cf',
       2, 0, 'completed', 1,
       11.9, 18.4, -26.5, -26.5,
       'team_cb2c661d688b', 'us', false,
       '2026-07-12 23:25:30+00', '2026-07-12 23:37:00+00'
WHERE NOT EXISTS (SELECT 1 FROM team_series WHERE id = '9a1c7702-0000-4000-8000-000000000003');

INSERT INTO team_matches (id, series_id, t1a_id, t1b_id, t2a_id, t2b_id,
                          t1_rounds_won, t2_rounds_won, winner_team, is_ranked,
                          photon_room_id, region, reported_by, started_at, ended_at, created_at)
SELECT '9a1c7702-0000-4000-8000-00000000a005', '9a1c7702-0000-4000-8000-000000000003',
       'fbb3d29d-b637-43c0-9787-357c2753e28c', 'ef39f993-7ede-4017-901d-bc637dd743d2',
       'ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d', '7df6bcd5-a2af-4022-ac77-6b29337c77cf',
       5, 0, 1, true,
       'team_cb2c661d688b_232530_r5', 'us', 'fbb3d29d-b637-43c0-9787-357c2753e28c',
       '2026-07-12 23:25:30+00', '2026-07-12 23:31:00+00', '2026-07-12 23:31:00+00'
WHERE NOT EXISTS (SELECT 1 FROM team_matches WHERE id = '9a1c7702-0000-4000-8000-00000000a005');

INSERT INTO team_matches (id, series_id, t1a_id, t1b_id, t2a_id, t2b_id,
                          t1_rounds_won, t2_rounds_won, winner_team, is_ranked,
                          photon_room_id, region, reported_by, started_at, ended_at, created_at)
SELECT '9a1c7702-0000-4000-8000-00000000a006', '9a1c7702-0000-4000-8000-000000000003',
       'fbb3d29d-b637-43c0-9787-357c2753e28c', 'ef39f993-7ede-4017-901d-bc637dd743d2',
       'ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d', '7df6bcd5-a2af-4022-ac77-6b29337c77cf',
       5, 1, 1, true,
       'team_cb2c661d688b_233130_r6', 'us', 'fbb3d29d-b637-43c0-9787-357c2753e28c',
       '2026-07-12 23:31:30+00', '2026-07-12 23:37:00+00', '2026-07-12 23:37:00+00'
WHERE NOT EXISTS (SELECT 1 FROM team_matches WHERE id = '9a1c7702-0000-4000-8000-00000000a006');

-- ── Game 7: first game of an unfinished 4th series (kept series-less; the
--     sitting ended before the series could resolve, so no series row and no
--     rating effect — same treatment the live pipeline gives a lone game
--     whose series is later expired without a decision) ────────────────────
INSERT INTO team_matches (id, series_id, t1a_id, t1b_id, t2a_id, t2b_id,
                          t1_rounds_won, t2_rounds_won, winner_team, is_ranked,
                          photon_room_id, region, reported_by, started_at, ended_at, created_at)
SELECT '9a1c7702-0000-4000-8000-00000000a007', NULL,
       'fbb3d29d-b637-43c0-9787-357c2753e28c', 'ef39f993-7ede-4017-901d-bc637dd743d2',
       'ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d', '7df6bcd5-a2af-4022-ac77-6b29337c77cf',
       5, 2, 1, true,
       'team_cb2c661d688b_233730_r7', 'us', 'fbb3d29d-b637-43c0-9787-357c2753e28c',
       '2026-07-12 23:37:30+00', '2026-07-12 23:44:00+00', '2026-07-12 23:44:00+00'
WHERE NOT EXISTS (SELECT 1 FROM team_matches WHERE id = '9a1c7702-0000-4000-8000-00000000a007');

-- ── Glicko-2 (precomputed, see header). Guarded so a re-run can't
--     double-apply: only fires while Sid's cs is still 12. ─────────────────
UPDATE glicko_ratings_2v2 SET
    rating = 1905.5528471344264, rating_deviation = 129.3724035185679,
    volatility = 0.06002007757525492,
    peak_rating = GREATEST(COALESCE(peak_rating, 0), 1905.5528471344264),
    completed_series = completed_series + 2, last_calculated = NOW(), updated_at = NOW()
WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c' AND completed_series = 12;

UPDATE glicko_ratings_2v2 SET
    rating = 1954.5214015492984, rating_deviation = 176.57195705555577,
    volatility = 0.059996474201818806,
    peak_rating = GREATEST(COALESCE(peak_rating, 0), 1954.5214015492984),
    completed_series = completed_series + 2, last_calculated = NOW(), updated_at = NOW()
WHERE player_id = 'ef39f993-7ede-4017-901d-bc637dd743d2' AND completed_series = 3;

UPDATE glicko_ratings_2v2 SET
    rating = 1328.2992294176029, rating_deviation = 219.81255352370962,
    volatility = 0.059996961218771926,
    peak_rating = GREATEST(COALESCE(peak_rating, 0), 1328.2992294176029),
    completed_series = completed_series + 2, last_calculated = NOW(), updated_at = NOW()
WHERE player_id = 'ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d' AND completed_series = 1;

UPDATE glicko_ratings_2v2 SET
    rating = 1328.2992294176029, rating_deviation = 219.81255352370962,
    volatility = 0.059996961218771926,
    peak_rating = GREATEST(COALESCE(peak_rating, 0), 1328.2992294176029),
    completed_series = completed_series + 2, last_calculated = NOW(), updated_at = NOW()
WHERE player_id = '7df6bcd5-a2af-4022-ac77-6b29337c77cf' AND completed_series = 1;

-- ── XP + gold, mirroring submit_team_match + series completion exactly:
--     per match: winners 900 xp, losers 600 xp, 100xp=1g conversion;
--     per completed series: +50g winners / +25g losers.
--     5 matches won by T1 (but only 4 belong to completed/counted play plus
--     game 7 which still pays match xp — the live path grants per-match xp
--     regardless of series state). Winners: 5*900=4500 xp; losers: 5*600=3000.
--     Series bonuses: 2 series * (50 winners / 25 losers).
--     Conversion delta computed against each player's live total_xp; the
--     accumulator columns and gold_transactions mirror the live reasons.
--     Guarded by the marker gold_transactions row inserted at the end. ─────
DO $mig$
DECLARE
    rec RECORD;
    old_xp BIGINT;
    new_xp BIGINT;
    conv INT;
    bonus INT;
    xp_add INT;
BEGIN
    IF EXISTS (SELECT 1 FROM gold_transactions
               WHERE reference_id = '115_backfill_july12' AND reason = 'backfill_marker') THEN
        RETURN;  -- already applied
    END IF;

    FOR rec IN
        SELECT * FROM (VALUES
            ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, true),
            ('ef39f993-7ede-4017-901d-bc637dd743d2'::uuid, true),
            ('ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d'::uuid, false),
            ('7df6bcd5-a2af-4022-ac77-6b29337c77cf'::uuid, false)
        ) AS t(pid, won)
    LOOP
        xp_add := CASE WHEN rec.won THEN 4500 ELSE 3000 END;
        bonus  := CASE WHEN rec.won THEN 100  ELSE 50   END;  -- 2 series * (50/25)

        SELECT total_xp INTO old_xp FROM players WHERE id = rec.pid;
        new_xp := COALESCE(old_xp, 0) + xp_add;
        conv := (new_xp / 100) - (COALESCE(old_xp, 0) / 100);

        UPDATE players SET
            total_xp = new_xp,
            team_xp_earned = COALESCE(team_xp_earned, 0) + xp_add,
            gold_earned = COALESCE(gold_earned, 0) + conv + bonus,
            team_gold_earned = COALESCE(team_gold_earned, 0) + conv + bonus
        WHERE id = rec.pid;

        IF conv > 0 THEN
            INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
            VALUES (rec.pid, conv, 'team_xp', '115_backfill_july12');
        END IF;
        INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
        VALUES (rec.pid, bonus,
                CASE WHEN rec.won THEN 'team_series_win' ELSE 'team_series_loss' END,
                '115_backfill_july12');
    END LOOP;

    -- Per-slot accumulators on the two series rows (xp: 2 matches each;
    -- gold: series bonus attributed to its own series row; the xp-conversion
    -- gold is attributed to series 2 arbitrarily — display-only columns).
    UPDATE team_series SET
        t1a_xp_earned = 1800, t1b_xp_earned = 1800, t2a_xp_earned = 1200, t2b_xp_earned = 1200,
        t1a_gold_earned = 50, t1b_gold_earned = 50, t2a_gold_earned = 25, t2b_gold_earned = 25
    WHERE id = '9a1c7702-0000-4000-8000-000000000002';
    UPDATE team_series SET
        t1a_xp_earned = 1800, t1b_xp_earned = 1800, t2a_xp_earned = 1200, t2b_xp_earned = 1200,
        t1a_gold_earned = 50, t1b_gold_earned = 50, t2a_gold_earned = 25, t2b_gold_earned = 25
    WHERE id = '9a1c7702-0000-4000-8000-000000000003';

    -- ── Bug #65: Stan's lost casual match vs enoch (5-0, xp 475/250) ──
    INSERT INTO matches (id, player1_id, player2_id, p1_rounds_won, p2_rounds_won,
                         winner_id, is_ranked, photon_room_id, region, reported_by,
                         p1_xp_gained, p2_xp_gained, started_at, ended_at, created_at)
    VALUES ('9a1c7702-0000-4000-8000-00000000b001',
            'ef39f993-7ede-4017-901d-bc637dd743d2', '22b87892-a122-4355-afd8-31e18fed1424',
            5, 0, 'ef39f993-7ede-4017-901d-bc637dd743d2', false,
            '109775242904479663_213430_r5', 'us', 'ef39f993-7ede-4017-901d-bc637dd743d2',
            475, 250, '2026-07-12 21:34:30+00', '2026-07-12 21:37:30+00', '2026-07-12 21:37:30+00')
    ON CONFLICT DO NOTHING;

    -- Stan +475 xp with conversion.
    SELECT total_xp INTO old_xp FROM players WHERE id = 'ef39f993-7ede-4017-901d-bc637dd743d2';
    new_xp := COALESCE(old_xp, 0) + 475;
    conv := (new_xp / 100) - (COALESCE(old_xp, 0) / 100);
    UPDATE players SET total_xp = new_xp, gold_earned = COALESCE(gold_earned, 0) + conv
    WHERE id = 'ef39f993-7ede-4017-901d-bc637dd743d2';
    IF conv > 0 THEN
        INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
        VALUES ('ef39f993-7ede-4017-901d-bc637dd743d2', conv, 'xp', '115_backfill_july12');
    END IF;

    -- enoch +250 xp with conversion (auto-created opponent row, same as live).
    SELECT total_xp INTO old_xp FROM players WHERE id = '22b87892-a122-4355-afd8-31e18fed1424';
    new_xp := COALESCE(old_xp, 0) + 250;
    conv := (new_xp / 100) - (COALESCE(old_xp, 0) / 100);
    UPDATE players SET total_xp = new_xp, gold_earned = COALESCE(gold_earned, 0) + conv
    WHERE id = '22b87892-a122-4355-afd8-31e18fed1424';
    IF conv > 0 THEN
        INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
        VALUES ('22b87892-a122-4355-afd8-31e18fed1424', conv, 'xp', '115_backfill_july12');
    END IF;

    -- Marker LAST: only lands if everything above succeeded.
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
    VALUES ('fbb3d29d-b637-43c0-9787-357c2753e28c', 0, 'backfill_marker', '115_backfill_july12');
END
$mig$;

COMMIT;
