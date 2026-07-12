-- Migration 108: Record the SECOND 2v2 series of the 2026-07-09 Sid/Nix vs
-- galaxy/Quilvet session, awarded to galaxy/Quilvet by DC forfeit.
--
-- What happened: the four played TWO back-to-back BO3 series in room
-- team_7bd0c62007fb (6 games total).
--   Series 1 (9369b7a5): games 1-3, Sid/Nix won 2-1 (5-4 T1, 4-5 T2, 5-3 T1).
--                        LEGITIMATE + already rated — this migration does NOT touch it.
--   Series 2 (this row): games 4-6. G4 Sid/Nix 5-4, G5 galaxy/Quilvet 5-4 (1-1),
--                        then Nix lost his internet on G6 (client log: NetworkRestart
--                        <- DoDisconnect, players 3/4, "Disconnect at 3-2"). The mod
--                        never created a server-side series 2 (the client stops
--                        reporting once series 1 locks at first-to-2), so games 4-6
--                        went unrecorded. Under the v1.28 lead-forfeit rule (a DC by
--                        one team when the other already has >=1 game win forfeits the
--                        series), series 2 goes to galaxy/Quilvet.
--
-- Ratings: series 2 is played immediately AFTER series 1, so its pre-series snapshot
-- is the CURRENT production 2v2 rating (series 1 is the most recent completed series,
-- so its results ARE production). One Glicko-2 rating period, galaxy/Quilvet win:
--   Sid     2014.9 -> 1810.8   (-204.1)   comp_series 9 -> 10
--   Nix     1627.0 -> 1464.0   (-163.0)   comp_series 5 -> 6   (DC'd)
--   galaxy  1347.0 -> 1784.6   (+437.6)   comp_series 1 -> 2
--   Quilvet 1194.8 -> 1595.7   (+400.9)   comp_series 2 -> 3
--
-- Idempotent: guarded on the series-2 row not already existing; a second run no-ops.

BEGIN;

DO $$
DECLARE
    v_s2    uuid := 'dcff0002-9369-4b7a-ab02-e4fe59af31b8';  -- deterministic series-2 id
    v_room  text := 'team_7bd0c62007fb';
    p_sid   uuid := 'fbb3d29d-b637-43c0-9787-357c2753e28c';
    p_nix   uuid := '43b2cc39-5510-41ae-a2e0-a72a507ab76c';   -- DC'd
    p_gal   uuid := '13941c3c-9c56-4181-ab08-cf5863f27f04';
    p_quil  uuid := '785e3150-761a-4fa6-8aae-c76ad06dbd90';
BEGIN
    IF EXISTS (SELECT 1 FROM team_series WHERE id = v_s2) THEN
        RAISE NOTICE 'Series 2 % already exists; skipping.', v_s2;
        RETURN;
    END IF;

    -- 1. Create series 2: Sid/Nix (t1) vs galaxy/Quilvet (t2), 1-1, forfeit win to t2.
    INSERT INTO team_series
        (id, t1a_id, t1b_id, t2a_id, t2b_id, t1_series_wins, t2_series_wins,
         status, winner_team, t1a_rating_change, t1b_rating_change,
         t2a_rating_change, t2b_rating_change, photon_room_id, region,
         rebalance_count, created_at, completed_at, invalidation_reason,
         dc_player_id, was_auto_balanced,
         t1a_gold_earned, t1b_gold_earned, t2a_gold_earned, t2b_gold_earned)
    VALUES
        (v_s2, p_sid, p_nix, p_gal, p_quil, 1, 1,
         'completed', 2, -204.1, -163.0, 437.6, 400.9, v_room, 'us',
         0, '2026-07-09 22:10:30+00', '2026-07-09 22:33:00+00', 'dc_leadforfeit',
         p_nix, true, 25, 25, 50, 50);

    -- 2. Ratings: series 2 stacked on current production. completed_series += 1.
    UPDATE glicko_ratings_2v2 SET rating=1810.848277, rating_deviation=150.828352, volatility=0.060024,
        peak_rating=GREATEST(COALESCE(peak_rating,0),1810.848277), completed_series=completed_series+1,
        last_calculated=NOW(), updated_at=NOW() WHERE player_id=p_sid;
    UPDATE glicko_ratings_2v2 SET rating=1463.996413, rating_deviation=145.102964, volatility=0.060021,
        peak_rating=GREATEST(COALESCE(peak_rating,0),1463.996413), completed_series=completed_series+1,
        last_calculated=NOW(), updated_at=NOW() WHERE player_id=p_nix;
    UPDATE glicko_ratings_2v2 SET rating=1784.552062, rating_deviation=218.013983, volatility=0.060018,
        peak_rating=GREATEST(COALESCE(peak_rating,0),1784.552062), completed_series=completed_series+1,
        last_calculated=NOW(), updated_at=NOW() WHERE player_id=p_gal;
    UPDATE glicko_ratings_2v2 SET rating=1595.709416, rating_deviation=202.519493, volatility=0.060029,
        peak_rating=GREATEST(COALESCE(peak_rating,0),1595.709416), completed_series=completed_series+1,
        last_calculated=NOW(), updated_at=NOW() WHERE player_id=p_quil;

    -- 3. Series-2 completion gold: winners +50, losers +25 (balance = earned - spent).
    UPDATE players SET gold_earned=gold_earned+25, team_gold_earned=team_gold_earned+25 WHERE id IN (p_sid, p_nix);
    UPDATE players SET gold_earned=gold_earned+50, team_gold_earned=team_gold_earned+50 WHERE id IN (p_gal, p_quil);
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id) VALUES
        (p_sid, 25, 'team_series_loss', v_s2::text),
        (p_nix, 25, 'team_series_loss', v_s2::text),
        (p_gal, 50, 'team_series_win',  v_s2::text),
        (p_quil,50, 'team_series_win',  v_s2::text);

    -- 4. Game history for series 2 (real G4/G5 from the client log + synthetic G6 forfeit).
    INSERT INTO team_matches
        (series_id, t1a_id, t1b_id, t2a_id, t2b_id, t1_rounds_won, t2_rounds_won,
         winner_team, dc_player_id, dc_at, started_at, ended_at, photon_room_id,
         region, is_ranked, reported_by, game_version)
    VALUES
        (v_s2, p_sid, p_nix, p_gal, p_quil, 5, 4, 1, NULL, NULL,
         '2026-07-09 22:11:00+00', '2026-07-09 22:18:00+00', v_room||'_221800_r9', 'us', true, p_sid, 'v1.1.2'),
        (v_s2, p_sid, p_nix, p_gal, p_quil, 4, 5, 2, NULL, NULL,
         '2026-07-09 22:19:00+00', '2026-07-09 22:26:00+00', v_room||'_222600_r9', 'us', true, p_sid, 'v1.1.2'),
        (v_s2, p_sid, p_nix, p_gal, p_quil, 0, 0, 2, p_nix, '2026-07-09 22:33:00+00',
         NULL, '2026-07-09 22:33:00+00', v_room||'_dcff', 'us', true, NULL, 'v1.1.2');
END $$;

COMMIT;
