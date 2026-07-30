-- 168: restore two FFA games the janitor wiped on 2026-07-30
--
-- Both games completed and were reported by the client, but a self-heal timer had
-- already closed the lobby, so /ffa/matches answered 409 "Lobby is not active" and
-- the results were dropped. The timers are fixed in the same release; this makes
-- the six affected players whole.
--
--   Game A  19:26  5 players  galaxy ice > Sid > Snail > Stan > Nix
--   Game B  21:05  4 players  Sid > Spirit > galaxy ice > Snail (left early)
--
-- Standings were recovered from the reporter BepInEx log: the per-point score
-- lines carry each player running round count, and the rich-text nametag prefixes
-- act as stable per-player fingerprints across games. Two ties (Stan/Nix in A,
-- Spirit/galaxy ice in B) are not resolvable from the log; the order chosen only
-- moves those pairs against each other.
--
-- Ratings come from a FULL chronological replay of all 21 recorded FFA matches
-- plus these two, through backend/api/glicko2.calculate_new_rating using the same
-- placement-adjacent pairing the live submit path uses (FFA_MAX_RATED_OPPONENTS=4).
-- The replay is self-validating: run WITHOUT the two games it reproduces the live
-- ladder to within 0.1 elo for all six players. XP and placement gold come from
-- main.py OWN reward functions, executed rather than copied (learning #229).
--
-- Deliberately does NOT fabricate ffa_matches/ffa_match_players rows: the real
-- per-player kills/damage/points are unrecoverable, and inserting zeros would
-- corrupt the new per-game kills/damage averages for six real players. Documented
-- consequence: glicko_ratings_ffa.games_played counts these two games while
-- ffa_match_players has no rows for them.
--
-- Idempotent: keyed on the 'ffa_recovery' gold_transactions marker.

DO $$
DECLARE
    pid_ UUID; gold_ INT; oldxp_ BIGINT; conv_ INT;
BEGIN
    IF EXISTS (SELECT 1 FROM gold_transactions WHERE reason = 'ffa_recovery') THEN
        RAISE NOTICE 'already applied - skipping';
        RETURN;
    END IF;
    -- galaxy ice: 2057.9 -> 2011.8 elo (-46.1), +5900 xp, +69g placement
    SELECT id INTO pid_ FROM players WHERE steam_id = '76561199013169799';
    UPDATE glicko_ratings_ffa SET rating=2011.792762, rating_deviation=99.797887, volatility=0.05999406,
           peak_rating = GREATEST(peak_rating, 2011.792762), games_played = games_played + 2,
           wins = wins + 1, top3 = top3 + 2, placement_sum = placement_sum + 4,
           last_calculated = NOW(), updated_at = NOW()
     WHERE player_id = pid_;
    SELECT COALESCE(total_xp,0) INTO oldxp_ FROM players WHERE id = pid_;
    UPDATE players SET total_xp = COALESCE(total_xp,0) + 5900,
           ffa_xp_earned = COALESCE(ffa_xp_earned,0) + 5900 WHERE id = pid_;
    conv_ := GREATEST(0, ((oldxp_ + 5900) / 100)::INT - (oldxp_ / 100)::INT);
    gold_ := conv_ + 69 + 0;
    UPDATE players SET gold_earned = COALESCE(gold_earned,0) + gold_,
           ffa_gold_earned = COALESCE(ffa_gold_earned,0) + gold_ WHERE id = pid_;
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
         VALUES (pid_, gold_, 'ffa_recovery', 'wiped-2026-07-30');
    -- Sid: 2001.1 -> 2034.6 elo (+33.5), +7123 xp, +80g placement
    SELECT id INTO pid_ FROM players WHERE steam_id = '76561198040410653';
    UPDATE glicko_ratings_ffa SET rating=2034.556268, rating_deviation=85.245398, volatility=0.06004231,
           peak_rating = GREATEST(peak_rating, 2034.556268), games_played = games_played + 2,
           wins = wins + 1, top3 = top3 + 2, placement_sum = placement_sum + 3,
           last_calculated = NOW(), updated_at = NOW()
     WHERE player_id = pid_;
    SELECT COALESCE(total_xp,0) INTO oldxp_ FROM players WHERE id = pid_;
    UPDATE players SET total_xp = COALESCE(total_xp,0) + 7123,
           ffa_xp_earned = COALESCE(ffa_xp_earned,0) + 7123 WHERE id = pid_;
    conv_ := GREATEST(0, ((oldxp_ + 7123) / 100)::INT - (oldxp_ / 100)::INT);
    gold_ := conv_ + 80 + 0;
    UPDATE players SET gold_earned = COALESCE(gold_earned,0) + gold_,
           ffa_gold_earned = COALESCE(ffa_gold_earned,0) + gold_ WHERE id = pid_;
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
         VALUES (pid_, gold_, 'ffa_recovery', 'wiped-2026-07-30');
    -- Snail: 2013.6 -> 1857.6 elo (-156.0), +3930 xp, +38g placement
    SELECT id INTO pid_ FROM players WHERE steam_id = '76561198860111585';
    UPDATE glicko_ratings_ffa SET rating=1857.626244, rating_deviation=112.897486, volatility=0.06003214,
           peak_rating = GREATEST(peak_rating, 1857.626244), games_played = games_played + 2,
           wins = wins + 0, top3 = top3 + 1, placement_sum = placement_sum + 7,
           last_calculated = NOW(), updated_at = NOW()
     WHERE player_id = pid_;
    SELECT COALESCE(total_xp,0) INTO oldxp_ FROM players WHERE id = pid_;
    UPDATE players SET total_xp = COALESCE(total_xp,0) + 3930,
           ffa_xp_earned = COALESCE(ffa_xp_earned,0) + 3930 WHERE id = pid_;
    conv_ := GREATEST(0, ((oldxp_ + 3930) / 100)::INT - (oldxp_ / 100)::INT);
    gold_ := conv_ + 38 + 0;
    UPDATE players SET gold_earned = COALESCE(gold_earned,0) + gold_,
           ffa_gold_earned = COALESCE(ffa_gold_earned,0) + gold_ WHERE id = pid_;
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
         VALUES (pid_, gold_, 'ffa_recovery', 'wiped-2026-07-30');
    -- Stan: 1800.3 -> 1672.5 elo (-127.9), +1897 xp, +20g placement
    SELECT id INTO pid_ FROM players WHERE steam_id = '76561198983423367';
    UPDATE glicko_ratings_ffa SET rating=1672.453057, rating_deviation=170.614810, volatility=0.06000095,
           peak_rating = GREATEST(peak_rating, 1672.453057), games_played = games_played + 1,
           wins = wins + 0, top3 = top3 + 0, placement_sum = placement_sum + 4,
           last_calculated = NOW(), updated_at = NOW()
     WHERE player_id = pid_;
    SELECT COALESCE(total_xp,0) INTO oldxp_ FROM players WHERE id = pid_;
    UPDATE players SET total_xp = COALESCE(total_xp,0) + 1897,
           ffa_xp_earned = COALESCE(ffa_xp_earned,0) + 1897 WHERE id = pid_;
    conv_ := GREATEST(0, ((oldxp_ + 1897) / 100)::INT - (oldxp_ / 100)::INT);
    gold_ := conv_ + 20 + 0;
    UPDATE players SET gold_earned = COALESCE(gold_earned,0) + gold_,
           ffa_gold_earned = COALESCE(ffa_gold_earned,0) + gold_ WHERE id = pid_;
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
         VALUES (pid_, gold_, 'ffa_recovery', 'wiped-2026-07-30');
    -- Nix: 1417.5 -> 1351.8 elo (-65.7), +1200 xp, +10g placement
    SELECT id INTO pid_ FROM players WHERE steam_id = '76561199101676330';
    UPDATE glicko_ratings_ffa SET rating=1351.771562, rating_deviation=128.684915, volatility=0.05999417,
           peak_rating = GREATEST(peak_rating, 1351.771562), games_played = games_played + 1,
           wins = wins + 0, top3 = top3 + 0, placement_sum = placement_sum + 5,
           last_calculated = NOW(), updated_at = NOW()
     WHERE player_id = pid_;
    SELECT COALESCE(total_xp,0) INTO oldxp_ FROM players WHERE id = pid_;
    UPDATE players SET total_xp = COALESCE(total_xp,0) + 1200,
           ffa_xp_earned = COALESCE(ffa_xp_earned,0) + 1200 WHERE id = pid_;
    conv_ := GREATEST(0, ((oldxp_ + 1200) / 100)::INT - (oldxp_ / 100)::INT);
    gold_ := conv_ + 10 + 0;
    UPDATE players SET gold_earned = COALESCE(gold_earned,0) + gold_,
           ffa_gold_earned = COALESCE(ffa_gold_earned,0) + gold_ WHERE id = pid_;
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
         VALUES (pid_, gold_, 'ffa_recovery', 'wiped-2026-07-30');
    -- Spirit: 1823.2 -> 1854.2 elo (+31.0), +3249 xp, +29g placement
    SELECT id INTO pid_ FROM players WHERE steam_id = '76561198984811435';
    UPDATE glicko_ratings_ffa SET rating=1854.243904, rating_deviation=74.366818, volatility=0.05998833,
           peak_rating = GREATEST(peak_rating, 1854.243904), games_played = games_played + 1,
           wins = wins + 0, top3 = top3 + 1, placement_sum = placement_sum + 2,
           last_calculated = NOW(), updated_at = NOW()
     WHERE player_id = pid_;
    SELECT COALESCE(total_xp,0) INTO oldxp_ FROM players WHERE id = pid_;
    UPDATE players SET total_xp = COALESCE(total_xp,0) + 3249,
           ffa_xp_earned = COALESCE(ffa_xp_earned,0) + 3249 WHERE id = pid_;
    conv_ := GREATEST(0, ((oldxp_ + 3249) / 100)::INT - (oldxp_ / 100)::INT);
    gold_ := conv_ + 29 + 0;
    UPDATE players SET gold_earned = COALESCE(gold_earned,0) + gold_,
           ffa_gold_earned = COALESCE(ffa_gold_earned,0) + gold_ WHERE id = pid_;
    INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
         VALUES (pid_, gold_, 'ffa_recovery', 'wiped-2026-07-30');
    RAISE NOTICE 'ffa recovery applied to 6 players';
END $$;

DO $$
DECLARE r_ DOUBLE PRECISION;
BEGIN
    SELECT g.rating INTO r_ FROM glicko_ratings_ffa g JOIN players p ON p.id = g.player_id
     WHERE p.steam_id = '76561198040410653';
    IF r_ IS NULL OR ABS(r_ - 2034.6) > 1.0 THEN
        RAISE EXCEPTION 'post-check FAILED: expected ~2034.6, got %', r_;
    END IF;
    RAISE NOTICE 'post-check OK: reporter FFA rating is %', r_;
END $$;
