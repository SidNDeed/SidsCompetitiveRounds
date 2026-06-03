-- 100_rebuild_2v2_glicko.sql
--
-- Full from-scratch rebuild of every player's 2v2 Glicko rating + completed_series
-- counter, replayed chronologically through the repo's own glicko2.py.
--
-- WHY: prior recovery migrations (077-080) inserted completed team_series + credited
-- gold/xp but never created glicko_ratings_2v2 rows or bumped completed_series. Result:
-- NotHoly, feauxen, MAX1T0P (and others) had NO 2v2 rating row at all despite playing
-- completed series, so the 2v2 leaderboard (WHERE completed_series >= 1) filtered them
-- out entirely — "2v2s not showing up." This rebuild gives every participant an accurate
-- rating + series count so they all appear correctly.
--
-- MUST run AFTER 099 (which completes series 4af535c0) — the replay includes it.
-- Ratings-only: does NOT touch gold/xp (already credited; replaying would double-pay).
-- Idempotent: pure UPSERT of final values, re-runnable. Values computed locally via
-- scripts/replay_2v2_glicko.py (same math as POST /admin/team/rebuild-glicko), verified
-- against the live submit_team_match Glicko path.
BEGIN;
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('fbb3d29d-b637-43c0-9787-357c2753e28c', 2000.411670, 156.649542, 0.059994, 2000.411670, 0, 8, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=2000.411670, rating_deviation=156.649542, volatility=0.059994, peak_rating=2000.411670, completed_series=8, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('8837e5fd-6aed-429b-b545-49f1e1caaa63', 1820.337649, 215.946867, 0.059999, 1820.337649, 0, 2, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1820.337649, rating_deviation=215.946867, volatility=0.059999, peak_rating=1820.337649, completed_series=2, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('6c767014-6296-41cd-9879-78164d957ca9', 1819.755064, 215.393213, 0.059998, 1819.755064, 0, 3, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1819.755064, rating_deviation=215.393213, volatility=0.059998, peak_rating=1819.755064, completed_series=3, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('3c79fdd7-b55a-4cd2-987b-6451e942f88e', 1804.398163, 223.669689, 0.059999, 1804.398163, 0, 2, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1804.398163, rating_deviation=223.669689, volatility=0.059999, peak_rating=1804.398163, completed_series=2, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('f8ab7d72-0e5f-4943-a584-2505dcbd816a', 1793.368735, 228.775824, 0.059999, 1793.368735, 0, 2, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1793.368735, rating_deviation=228.775824, volatility=0.059999, peak_rating=1793.368735, completed_series=2, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('fbcad288-1be8-4387-9210-ddb7b1371fa4', 1793.368735, 228.775824, 0.059999, 1793.368735, 0, 2, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1793.368735, rating_deviation=228.775824, volatility=0.059999, peak_rating=1793.368735, completed_series=2, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('b3ac0a9a-1a8a-41b7-9143-5ac71a40eb35', 1747.318072, 253.404602, 0.060000, 1747.318072, 0, 1, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1747.318072, rating_deviation=253.404602, volatility=0.060000, peak_rating=1747.318072, completed_series=1, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('e21f904e-286a-4be9-9f0d-aa7d57fa5db9', 1747.318072, 253.404602, 0.060000, 1747.318072, 0, 1, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1747.318072, rating_deviation=253.404602, volatility=0.060000, peak_rating=1747.318072, completed_series=1, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('ef39f993-7ede-4017-901d-bc637dd743d2', 1747.318072, 253.404602, 0.060000, 1747.318072, 0, 1, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1747.318072, rating_deviation=253.404602, volatility=0.060000, peak_rating=1747.318072, completed_series=1, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('2c5a8c23-950f-48dd-a293-df255f61831c', 1515.348891, 196.264801, 0.060005, 1515.348891, 0, 3, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1515.348891, rating_deviation=196.264801, volatility=0.060005, peak_rating=1515.348891, completed_series=3, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('43b2cc39-5510-41ae-a2e0-a72a507ab76c', 1447.120570, 188.885797, 0.060003, 1747.318072, 0, 3, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1447.120570, rating_deviation=188.885797, volatility=0.060003, peak_rating=1747.318072, completed_series=3, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('9754e0f8-df1f-416d-ab61-cf7ea220754e', 1326.090227, 263.437624, 0.059999, 1500.000000, 0, 1, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1326.090227, rating_deviation=263.437624, volatility=0.059999, peak_rating=1500.000000, completed_series=1, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('1bd97e40-fed5-4385-b8e8-db6165f14fdf', 1326.090227, 263.437624, 0.059999, 1500.000000, 0, 1, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1326.090227, rating_deviation=263.437624, volatility=0.059999, peak_rating=1500.000000, completed_series=1, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('e6f737ea-0a12-443a-8e7b-90c9ee7f72bd', 1252.681928, 253.404602, 0.060000, 1500.000000, 0, 1, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1252.681928, rating_deviation=253.404602, volatility=0.060000, peak_rating=1500.000000, completed_series=1, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('35abb749-e5eb-4eaa-b8ba-4f2b361110de', 1252.681928, 253.404602, 0.060000, 1500.000000, 0, 1, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1252.681928, rating_deviation=253.404602, volatility=0.060000, peak_rating=1500.000000, completed_series=1, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('6b6e0548-1004-4483-876a-95d746e3a0af', 1252.681928, 253.404602, 0.060000, 1500.000000, 0, 1, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1252.681928, rating_deviation=253.404602, volatility=0.060000, peak_rating=1500.000000, completed_series=1, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('9c587ddf-556c-428b-bcb1-503029dc729a', 1221.590911, 236.279870, 0.059999, 1500.000000, 0, 2, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1221.590911, rating_deviation=236.279870, volatility=0.059999, peak_rating=1500.000000, completed_series=2, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('99409bf7-6594-48e8-a162-cb53be95eea1', 1206.631265, 228.775824, 0.059999, 1500.000000, 0, 2, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1206.631265, rating_deviation=228.775824, volatility=0.059999, peak_rating=1500.000000, completed_series=2, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('6262d712-81c5-4eff-aa0b-b8126e3d436b', 1206.631265, 228.775824, 0.059999, 1500.000000, 0, 2, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1206.631265, rating_deviation=228.775824, volatility=0.059999, peak_rating=1500.000000, completed_series=2, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('2ed82657-febe-458b-9981-71655b6ff2f7', 1180.244936, 215.393213, 0.059998, 1500.000000, 0, 3, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1180.244936, rating_deviation=215.393213, volatility=0.059998, peak_rating=1500.000000, completed_series=3, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('f88b5516-f780-44a4-8ccc-d1306b930336', 1180.244936, 215.393213, 0.059998, 1500.000000, 0, 3, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1180.244936, rating_deviation=215.393213, volatility=0.059998, peak_rating=1500.000000, completed_series=3, last_calculated=NOW(), updated_at=NOW();
INSERT INTO glicko_ratings_2v2 (player_id, rating, rating_deviation, volatility, peak_rating, games_in_period, completed_series, last_calculated, updated_at)
VALUES ('42b61a5c-2088-44c9-8032-73f95776e90b', 1171.547174, 200.617083, 0.059998, 1500.000000, 0, 3, NOW(), NOW())
ON CONFLICT (player_id) DO UPDATE SET rating=1171.547174, rating_deviation=200.617083, volatility=0.059998, peak_rating=1500.000000, completed_series=3, last_calculated=NOW(), updated_at=NOW();
COMMIT;
