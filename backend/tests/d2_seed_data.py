"""Fixture rows the chain build applies right before the migration file named
by each key (d2_seed adds one ("sql", ...) step per key): data repairs,
releases and seeds whose own gates and post-checks refuse on a database
without production rows. Each value runs whole, as one prerequisite step,
under the admin role. Rows only: no DDL, no trigger or replication-role
change; mail_inbox_rev is never touched (test_every_migration_file_runs_
to_its_end asserts that prerequisite steps never touch it). Every block is
idempotent (NOT EXISTS / ON CONFLICT), because a file's seed runs after
every earlier file and seed in the chain. @FILE(path;md5)@ stands for the
bytea literal of that repo file (expanded and md5-checked by d2_seed)."""

SEEDS = {}

SEEDS['099_resolve_stuck_2v2_series.sql'] = r'''-- seed (hm) for backend/sql/099_resolve_stuck_2v2_series.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text),
    ('2c5a8c23-950f-48dd-a293-df255f61831c'::uuid, NULL::text, 'MAX1T0P'::text),
    ('43b2cc39-5510-41ae-a2e0-a72a507ab76c'::uuid, '76561199101676330'::text, 'Nix'::text),
    ('42b61a5c-2088-44c9-8032-73f95776e90b'::uuid, NULL::text, 'NotHoly'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;

-- 099 lines 23-31 complete series 4af535c0 only while it is 'active'; slots per the
-- file's comment (t1a Sid, t1b MAX1T0P, t2a Nix, t2b NotHoly), 1-1 when the DC hit.
INSERT INTO team_series (id, t1a_id, t1b_id, t2a_id, t2b_id, t1_series_wins, t2_series_wins,
                         status, created_at)
SELECT '4af535c0-3ed0-425d-a462-75e1e4bc9799', 'fbb3d29d-b637-43c0-9787-357c2753e28c',
       '2c5a8c23-950f-48dd-a293-df255f61831c', '43b2cc39-5510-41ae-a2e0-a72a507ab76c',
       '42b61a5c-2088-44c9-8032-73f95776e90b', 1, 1, 'active', '2026-06-01 19:30:00+00'
WHERE NOT EXISTS (SELECT 1 FROM team_series WHERE id = '4af535c0-3ed0-425d-a462-75e1e4bc9799');
'''

SEEDS['100_rebuild_2v2_glicko.sql'] = r'''-- seed (hm) for backend/sql/100_rebuild_2v2_glicko.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text),
    ('8837e5fd-6aed-429b-b545-49f1e1caaa63'::uuid, NULL::text, 'seed-8837e5fd'::text),
    ('6c767014-6296-41cd-9879-78164d957ca9'::uuid, NULL::text, 'seed-6c767014'::text),
    ('3c79fdd7-b55a-4cd2-987b-6451e942f88e'::uuid, NULL::text, 'seed-3c79fdd7'::text),
    ('f8ab7d72-0e5f-4943-a584-2505dcbd816a'::uuid, NULL::text, 'seed-f8ab7d72'::text),
    ('fbcad288-1be8-4387-9210-ddb7b1371fa4'::uuid, NULL::text, 'seed-fbcad288'::text),
    ('b3ac0a9a-1a8a-41b7-9143-5ac71a40eb35'::uuid, NULL::text, 'seed-b3ac0a9a'::text),
    ('e21f904e-286a-4be9-9f0d-aa7d57fa5db9'::uuid, NULL::text, 'seed-e21f904e'::text),
    ('ef39f993-7ede-4017-901d-bc637dd743d2'::uuid, '76561198983423367'::text, 'Stan'::text),
    ('2c5a8c23-950f-48dd-a293-df255f61831c'::uuid, NULL::text, 'MAX1T0P'::text),
    ('43b2cc39-5510-41ae-a2e0-a72a507ab76c'::uuid, '76561199101676330'::text, 'Nix'::text),
    ('9754e0f8-df1f-416d-ab61-cf7ea220754e'::uuid, NULL::text, 'seed-9754e0f8'::text),
    ('1bd97e40-fed5-4385-b8e8-db6165f14fdf'::uuid, NULL::text, 'seed-1bd97e40'::text),
    ('e6f737ea-0a12-443a-8e7b-90c9ee7f72bd'::uuid, NULL::text, 'seed-e6f737ea'::text),
    ('35abb749-e5eb-4eaa-b8ba-4f2b361110de'::uuid, NULL::text, 'seed-35abb749'::text),
    ('6b6e0548-1004-4483-876a-95d746e3a0af'::uuid, NULL::text, 'seed-6b6e0548'::text),
    ('9c587ddf-556c-428b-bcb1-503029dc729a'::uuid, NULL::text, 'seed-9c587ddf'::text),
    ('99409bf7-6594-48e8-a162-cb53be95eea1'::uuid, NULL::text, 'seed-99409bf7'::text),
    ('6262d712-81c5-4eff-aa0b-b8126e3d436b'::uuid, NULL::text, 'seed-6262d712'::text),
    ('2ed82657-febe-458b-9981-71655b6ff2f7'::uuid, NULL::text, 'seed-2ed82657'::text),
    ('f88b5516-f780-44a4-8ccc-d1306b930336'::uuid, NULL::text, 'seed-f88b5516'::text),
    ('42b61a5c-2088-44c9-8032-73f95776e90b'::uuid, NULL::text, 'NotHoly'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;

-- 100 lines 19-86 upsert glicko_ratings_2v2 for these 22 uuids (FK to players.id).
'''

SEEDS['108_fix_2v2_series_9369b7a5_dc_forfeit.sql'] = r'''-- seed (hm) for backend/sql/108_fix_2v2_series_9369b7a5_dc_forfeit.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text),
    ('43b2cc39-5510-41ae-a2e0-a72a507ab76c'::uuid, '76561199101676330'::text, 'Nix'::text),
    ('13941c3c-9c56-4181-ab08-cf5863f27f04'::uuid, '76561199013169799'::text, 'galaxy'::text),
    ('785e3150-761a-4fa6-8aae-c76ad06dbd90'::uuid, NULL::text, 'Quilvet'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;

-- 108 lines 59-70 update each seat's glicko_ratings_2v2 row; the header (lines 20-23)
-- gives the pre-series ratings and completed_series. Inserted only when absent.
INSERT INTO glicko_ratings_2v2 (player_id, rating, peak_rating, completed_series)
SELECT v.pid, v.r, v.r, v.cs
  FROM (VALUES ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, 2014.9::float8, 9),
               ('43b2cc39-5510-41ae-a2e0-a72a507ab76c'::uuid, 1627.0::float8, 5),
               ('13941c3c-9c56-4181-ab08-cf5863f27f04'::uuid, 1347.0::float8, 1),
               ('785e3150-761a-4fa6-8aae-c76ad06dbd90'::uuid, 1194.8::float8, 2)) AS v(pid, r, cs)
 WHERE NOT EXISTS (SELECT 1 FROM glicko_ratings_2v2 g WHERE g.player_id = v.pid);
'''

SEEDS['115_backfill_july12_lost_matches.sql'] = r'''-- seed (hm) for backend/sql/115_backfill_july12_lost_matches.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text),
    ('ef39f993-7ede-4017-901d-bc637dd743d2'::uuid, '76561198983423367'::text, 'Stan'::text),
    ('ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d'::uuid, '76561198295504414'::text, 'Farming on my mind'::text),
    ('7df6bcd5-a2af-4022-ac77-6b29337c77cf'::uuid, '76561199050262261'::text, 'genderswapday'::text),
    ('22b87892-a122-4355-afd8-31e18fed1424'::uuid, '13040669204355181255'::text, 'enoch :)'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;

-- 115 lines 136-162 update glicko_ratings_2v2 guarded on completed_series 12/3/1/1;
-- the rows are inserted at those values only when absent (an existing row is kept).
INSERT INTO glicko_ratings_2v2 (player_id, completed_series)
SELECT v.pid, v.cs
  FROM (VALUES ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, 12),
               ('ef39f993-7ede-4017-901d-bc637dd743d2'::uuid, 3),
               ('ad989127-9e0f-4a9b-9d4c-1b44b71e0e5d'::uuid, 1),
               ('7df6bcd5-a2af-4022-ac77-6b29337c77cf'::uuid, 1)) AS v(pid, cs)
 WHERE NOT EXISTS (SELECT 1 FROM glicko_ratings_2v2 g WHERE g.player_id = v.pid);
'''

SEEDS['149_release_spooky_head_bouncers.sql'] = r'''-- rf8 d2 seed (helper hc) for 149_release_spooky_head_bouncers.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 149 guard (lines 22-46): approved row, rev 1, scale 1.300, offset 0.113:3.665

-- shop row face_detail_spooky_head_bouncers
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880250, 'face_detail_spooky_head_bouncers', 'face', 'face_detail_spooky_head_bouncers', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_spooky_head_bouncers');

-- approved submission face_detail_spooky_head_bouncers: rev 1, scale 1.3, offset (0.113,3.665), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990250, '76561190000000149', 'face_detail_spooky_head_bouncers', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_spooky_head_bouncers', 1.3, 0.113, 3.665, 1, 1.3, 0.113, 3.665, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_spooky_head_bouncers');

COMMIT;
'''

SEEDS['168_ffa_recover_wiped_games.sql'] = r'''-- seed (hm) for backend/sql/168_ffa_recover_wiped_games.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('13941c3c-9c56-4181-ab08-cf5863f27f04'::uuid, '76561199013169799'::text, 'galaxy ice'::text),
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text),
    (NULL::uuid, '76561198860111585'::text, 'Snail'::text),
    ('ef39f993-7ede-4017-901d-bc637dd743d2'::uuid, '76561198983423367'::text, 'Stan'::text),
    ('43b2cc39-5510-41ae-a2e0-a72a507ab76c'::uuid, '76561199101676330'::text, 'Nix'::text),
    (NULL::uuid, '76561198984811435'::text, 'Spirit'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;

-- 168 looks each of the six up BY STEAM ID (lines 39-150) and inserts a gold row for
-- it, so the steam id must resolve; the uuid rows above give a placeholder steam id
-- only when the real one is held by another row, which then is the one found here.
INSERT INTO players (steam_id, display_name)
SELECT v.s, 'seed-' || right(v.s, 8)
  FROM (VALUES ('76561199013169799'), ('76561198040410653'), ('76561198860111585'),
               ('76561198983423367'), ('76561199101676330'), ('76561198984811435')) v(s)
 WHERE NOT EXISTS (SELECT 1 FROM players p WHERE p.steam_id = v.s);

-- 168 lines 42-150 update glicko_ratings_ffa; the post-check (lines 154-162) reads
-- the reporter's row. Pre-game ratings from the file's per-player comments
-- (galaxy ice 2057.9, Sid 2001.1, Snail 2013.6, Stan 1800.3, Nix 1417.5, Spirit 1823.2).
INSERT INTO glicko_ratings_ffa (player_id, rating, peak_rating)
SELECT p.id, v.r, v.r
  FROM (VALUES ('76561199013169799', 2057.9::float8), ('76561198040410653', 2001.1::float8),
               ('76561198860111585', 2013.6::float8), ('76561198983423367', 1800.3::float8),
               ('76561199101676330', 1417.5::float8), ('76561198984811435', 1823.2::float8)) AS v(s, r)
  JOIN players p ON p.steam_id = v.s
 WHERE NOT EXISTS (SELECT 1 FROM glicko_ratings_ffa g WHERE g.player_id = p.id);
'''

SEEDS['172_publish_tattered_cape_rev2.sql'] = r'''-- rf8 d2 seed (helper hc) for 172_publish_tattered_cape_rev2.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 172 UPDATE + post-check: approved rev 2, scale 2.15, published < 2 (live item)

-- shop row face_detail_tattered_cape - live since its first release
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881101, 'face_detail_tattered_cape', 'face', 'face_detail_tattered_cape', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_tattered_cape');
-- already live before this file: publish it (no submission row exists yet, so
-- the 148 trigger only stamps released_at)
UPDATE shop_items SET catalog_ready = TRUE WHERE sku = 'face_detail_tattered_cape' AND catalog_ready IS NOT TRUE;

-- approved submission face_detail_tattered_cape: rev 2, scale 2.15, offset (0,-0.1), published 1
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991101, '76561190000000149', 'face_detail_tattered_cape', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_tattered_cape', 2.15, 0, -0.1, 2, 2.15, 0, -0.1, 2, 1, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_tattered_cape');

COMMIT;
'''

SEEDS['175_release_v1355_cosmetics.sql'] = r'''-- rf8 d2 seed (helper hc) for 175_release_v1355_cosmetics.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 175 guard: the five approved at rev 1 (scale 1.3, offset 0,0) and their 5 shop rows

-- shop row face_detail_brain_cane
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880253, 'face_detail_brain_cane', 'face', 'face_detail_brain_cane', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_brain_cane');

-- approved submission face_detail_brain_cane: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990253, '76561190000000149', 'face_detail_brain_cane', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_brain_cane', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_brain_cane');

-- shop row face_mouth_casi_s_mouth
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880254, 'face_mouth_casi_s_mouth', 'face', 'face_mouth_casi_s_mouth', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_mouth_casi_s_mouth');

-- approved submission face_mouth_casi_s_mouth: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990254, '76561190000000149', 'face_mouth_casi_s_mouth', 'mouth', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_mouth_casi_s_mouth', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_mouth_casi_s_mouth');

-- shop row face_eyes_casicorn_s_eyes
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880255, 'face_eyes_casicorn_s_eyes', 'face', 'face_eyes_casicorn_s_eyes', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_eyes_casicorn_s_eyes');

-- approved submission face_eyes_casicorn_s_eyes: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990255, '76561190000000149', 'face_eyes_casicorn_s_eyes', 'eyes', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_eyes_casicorn_s_eyes', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_eyes_casicorn_s_eyes');

-- shop row face_detail_little_pink_buddy
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880256, 'face_detail_little_pink_buddy', 'face', 'face_detail_little_pink_buddy', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_little_pink_buddy');

-- approved submission face_detail_little_pink_buddy: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990256, '76561190000000149', 'face_detail_little_pink_buddy', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_little_pink_buddy', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_little_pink_buddy');

-- shop row face_detail_sniper_medal
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880257, 'face_detail_sniper_medal', 'face', 'face_detail_sniper_medal', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_sniper_medal');

-- approved submission face_detail_sniper_medal: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990257, '76561190000000149', 'face_detail_sniper_medal', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_sniper_medal', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_sniper_medal');

COMMIT;
'''

SEEDS['190_release_v1360_cosmetics.sql'] = r'''-- rf8 d2 seed (helper hc) for 190_release_v1360_cosmetics.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 190 guard 1: spilled_icecream approved rev 1, 1.3, 0/0 (new, not yet live)

-- shop row face_detail_spilled_icecream
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880258, 'face_detail_spilled_icecream', 'face', 'face_detail_spilled_icecream', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_spilled_icecream');

-- approved submission face_detail_spilled_icecream: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990258, '76561190000000149', 'face_detail_spilled_icecream', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_spilled_icecream', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_spilled_icecream');

-- 190 guard 2: rounds_cat approved rev 2, 1.7, 0/0, live, published 1

-- shop row face_detail_rounds_cat - live since 2026-07-18
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881102, 'face_detail_rounds_cat', 'face', 'face_detail_rounds_cat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_rounds_cat');
-- already live before this file: publish it (no submission row exists yet, so
-- the 148 trigger only stamps released_at)
UPDATE shop_items SET catalog_ready = TRUE WHERE sku = 'face_detail_rounds_cat' AND catalog_ready IS NOT TRUE;

-- approved submission face_detail_rounds_cat: rev 2, scale 1.7, offset (0,0), published 1
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991102, '76561190000000149', 'face_detail_rounds_cat', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_rounds_cat', 1.7, 0, 0, 2, 1.7, 0, 0, 2, 1, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_rounds_cat');

-- 190 post-check (lines 102-108): exactly 34 catalog_ready face rows after the flip.
-- The v1.36.0 client carried 34 faces: the earlier releases this chain's own
-- files publish (149 spooky, 153 ballooniphones + soda_helm, 175's five) plus
-- spilled_icecream. Publish those earlier-release faces, in release order, only
-- until the live count (counting spilled_icecream, which 190 flips) reaches 34;
-- in the chain they are already live and nothing is added. No submission rows
-- are created for them, so the post-check's pending query is unaffected.
DO $seed$
DECLARE
    f RECORD;
    have INT;
BEGIN
    FOR f IN SELECT * FROM (VALUES ('face_detail_spooky_head_bouncers', 880250), ('face_detail_ballooniphones', 880251), ('face_detail_soda_helm', 880252), ('face_detail_brain_cane', 880253), ('face_mouth_casi_s_mouth', 880254), ('face_eyes_casicorn_s_eyes', 880255), ('face_detail_little_pink_buddy', 880256), ('face_detail_sniper_medal', 880257)) AS v(sku, id) LOOP
        SELECT COUNT(*) FILTER (WHERE catalog_ready IS TRUE)
               + CASE WHEN EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_spilled_icecream'
                                    AND catalog_ready IS NOT TRUE) THEN 1 ELSE 0 END
          INTO have FROM shop_items WHERE kind = 'face';
        EXIT WHEN have >= 34;
        INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
        SELECT f.id, f.sku, 'face', f.sku, 'community cosmetic (rf seed filler)', 500, '76561190000000149', -1
        WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = f.sku);
        UPDATE shop_items SET catalog_ready = TRUE WHERE sku = f.sku AND catalog_ready IS NOT TRUE;
    END LOOP;
    RAISE NOTICE 'rf seed 190: % catalog_ready faces before the flip (34 expected after)',
        (SELECT COUNT(*) FROM shop_items WHERE kind = 'face' AND catalog_ready IS TRUE);
END $seed$;

COMMIT;
'''

SEEDS['197_publish_magical_hat_animated.sql'] = r'''-- rf8 d2 seed (helper hc) for 197_publish_magical_hat_animated.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 197 lines 39-43 + 107-109: submission id 16 for face_detail_magical_hat
-- (the file updates and reads it BY ID; explicit id 16, inserted only if the sku is absent);
-- guard lines 57-71: approved rev 1, scale 1.3, offset 0,0; never shipped (published 0)

-- shop row face_detail_magical_hat
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880259, 'face_detail_magical_hat', 'face', 'face_detail_magical_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_magical_hat');

-- approved submission face_detail_magical_hat: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 16, '76561190000000149', 'face_detail_magical_hat', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_magical_hat', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_magical_hat');

COMMIT;
'''

SEEDS['211_release_twisted_topper.sql'] = r'''-- rf8 d2 seed (helper hc) for 211_release_twisted_topper.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 211 guard: approved rev 1

-- shop row face_detail_twisted_topper
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880260, 'face_detail_twisted_topper', 'face', 'face_detail_twisted_topper', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_twisted_topper');

-- approved submission face_detail_twisted_topper: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990260, '76561190000000149', 'face_detail_twisted_topper', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_twisted_topper', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_twisted_topper');

COMMIT;
'''

SEEDS['213_seed_machine_translations_uk_sv.sql'] = r'''-- rf8 d2 seed (tag hi) for 213_seed_machine_translations_uk_sv.sql: i18n_keys fixtures.
-- The file's INSERT joins i18n_proposals onto LIVE i18n_keys rows with the SAME
-- source_hash, and its DO-block coverage check RAISEs when a seed pair did not land.
-- Production gets these key rows from tools/i18n_sync_keys.py; here they are
-- derived from the file itself: every (key_id, source_hash) in its _seed213 pairs (lines 41-4641) and the 242 game keys (line ~4703).
-- namespace: 'game' when key_id = sha1('game\0' + Table/KEY)[:16] over
-- tools/game_strings.json (or the file lists it as a game key), else 'client'.
-- msgctxt: the English whose sha1 equals the file's source_hash (found in
-- tools/i18n_source.json at HEAD or any earlier revision, tools/game_strings.json,
-- or the quoted text of backend/sql),
-- otherwise a labelled placeholder. Game keys carry a non-empty context.
-- 1950 keys: 1708 client with English, 242 game with English, 0 placeholder msgctxt.
-- Re-runnable: the upsert only touches a row that is retired, carries another hash,
-- or lacks context the file reads.
BEGIN;
INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
  ('0039162cb1a6ccf5', 'client', $s213$Same Cards: OFF$s213$, '45408601fd361fc80d80e08668d8bdf72085d6e0', FALSE, NULL),
  ('014e44ac3404b177', 'client', $s213$Elo over games$s213$, '7c76a991ae48f6c5f4aaca54f04c3451df0b6050', FALSE, NULL),
  ('0157a9143665e238', 'client', $s213$Cool grey-blue blocks on a dim cool backdrop.$s213$, '669a338cd831e006a68d71778ac389a20d8e40f3', FALSE, NULL),
  ('01598ec331fe3b04', 'client', $s213$Downloading update...$s213$, '097433a5c6393020b3ed7f568c2e5474c55e8a7c', FALSE, NULL),
  ('01a2f5687a851390', 'client', $s213$Stock$s213$, 'bcecf4562f1709b1448aff7c6b49edb6acecdb12', FALSE, NULL),
  ('0243596e5d193a51', 'client', $s213$<color=#FF6666>+{0} replaced</color> <color=#556270>(hover)</color>$s213$, '18aff0f77f00d58e0135fbbe73602eea442793d2', FALSE, NULL),
  ('02481d4bc4f0e5ee', 'client', $s213$<color=#888><i>Updates of {0} & {1} - grab them in the Shop tab.</i></color>$s213$, '69a9c6e275a41f86330f6c8e4513a47b83f6625e', FALSE, NULL),
  ('02a88da890abd1ce', 'client', $s213$Pass%$s213$, 'd0cfb954a9334a6c99881784734346cd543a750a', FALSE, NULL),
  ('02c6d926d2a73a47', 'client', $s213$<color=#888>sold {0}, gifted {1}</color>$s213$, '06d342169002a46b2dcd8b255afee37003292dad', FALSE, NULL),
  ('02d0a1f9b84af9cd', 'game', $s213$SUPERNOVA$s213$, 'd032c1d22752988e0185ad5e057b0e8bfc6775f1', FALSE, $s213$StringTableCards/CARD_SUPERNOVA$s213$),
  ('02f9fdc3b0163eb6', 'client', $s213$Team 1$s213$, '59e04589be76b7f5cd8daa060c3b716223b0255d', FALSE, NULL),
  ('0348defe86351f3c', 'client', $s213$Reloader$s213$, '35360f9710e178438cf0beacd29bc2cf155be508', FALSE, NULL),
  ('0366c6e45b629e99', 'client', $s213$Custom player body colors: <color=#FF9966>OFF</color>$s213$, '43a183043498ee5e5e63748c343d3c393dc71238', FALSE, NULL),
  ('03bc4458323fd933', 'client', $s213$<color=#FF8888>Purchase failed: {0}</color>$s213$, '5382a6697adcab5246f2e9a8c1ef6290ebaa2c09', TRUE, NULL),
  ('03c5a0d8e90d79de', 'client', $s213$Spectator session ended.$s213$, 'f06d063fd1257dcd929e9ecb82d3a0397267e285', FALSE, NULL),
  ('03e012cf2d13a440', 'client', $s213$<b><color=#FF6688>* Live 2v2 Now</color></b>  <color=#888>({0})</color>$s213$, 'b49834782c6f5863a88153d700c99fc2170b14a4', FALSE, NULL),
  ('03fd7046e9ef2d63', 'client', $s213$Screen shake: <color={0}>{1}</color>$s213$, 'd2ad76935ab2f3bb89bab2b67c98d79e2728d61e', FALSE, NULL),
  ('040fdcdc9fe82d97', 'client', $s213$Charred timber — warm dark brown verging on black.$s213$, '6fdc92710bf9a1c37713696ed1898bd196a848c9', FALSE, NULL),
  ('0443b0ff598772c5', 'client', $s213$Left all queues$s213$, '2336614c4008f5eaa1e5ed653494422d528620a1', FALSE, NULL),
  ('047de86df5071d35', 'client', $s213$Beta$s213$, 'f03b60f7e52b7ce49ed1e4f9fa511c452a2185bb', FALSE, NULL),
  ('049df31057f1ee37', 'client', $s213$Alert is live.$s213$, '49ec9e731f057222bf0dd06550c791aa806317ac', FALSE, NULL),
  ('04a881a93d60819b', 'client', $s213$Create Lobby$s213$, 'c2c427166ba31cc0e90127bf9aa5db6bd64c30a7', FALSE, NULL),
  ('04af4b0b1909b0cb', 'client', $s213$Energy Orbs$s213$, 'a13f4b9bac07d2b398f39f962a4e6e6f64ec7afb', FALSE, NULL),
  ('04b8eda0beb6c7c9', 'client', $s213$Select 2-12 players (left) to see who beats each of them most.$s213$, '48cbbdf0892841c2a1ddc258564365aa33ecbce3', FALSE, NULL),
  ('04d2dc2bea475b30', 'client', $s213$Both ready! Joining match...$s213$, 'b094a487f88ec8edb2f2ab91ef0e626b8a53024b', FALSE, NULL),
  ('04ea724f3226d3a6', 'client', $s213$<color=#66DD66>In a 1v2 match.</color>$s213$, 'f232d32135d7a1a9257b868b63a89efd1ef8d344', FALSE, NULL),
  ('052b546b4bb6c1b4', 'client', $s213$Finishing your previous leave first...$s213$, 'e5d1c56766741a3ff30884a7b6e5ab1f402dc14e', FALSE, NULL),
  ('05347a04a3a75031', 'client', $s213$<color=#CCC>Ping (ms)</color>$s213$, '8ea095243d5e72c3eddc0d586a212666cbd8b714', FALSE, NULL),
  ('054aa178a79fbbd0', 'client', $s213$A deep indigo between Purple and Cyan.$s213$, '8ccaaa302ea73bdb9bead1a6ec141229cea2d9dc', FALSE, NULL),
  ('0552e283e3175aac', 'client', $s213$Casual: {0}W / {1}L ({2})$s213$, '571d9fa39175e85bb1e887c25267c5b620e5e62e', FALSE, NULL),
  ('0578f75137c0ac92', 'client', $s213$<color=#FFD94D>Match found! Click <b>Ready Up</b>.</color>$s213$, 'd413a2bca5b58733396502254c2879888129a70b', FALSE, NULL),
  ('058a47753c6c57cf', 'client', $s213$FFA Damage per Second$s213$, 'd2cf10297a9ca4f2e86691018da78380fc281085', FALSE, NULL),
  ('058dfacd797a5c2d', 'client', $s213$Solo extra pick (host): OFF$s213$, 'f1cd44e286b70679cf49f8d1a6c1e892d290fd0d', FALSE, NULL),
  ('0599d7612e9c92b0', 'client', $s213$Detail: cozy star-studded earmuffs. Equip in the Character editor.$s213$, '3606ab5ea0cab3d56f0f7fb96596c962e44194b9', FALSE, NULL),
  ('059bb297892d12b5', 'client', $s213$Colossus$s213$, 'ce1c631db455b6205a45b767991b570a3cc36d42', FALSE, NULL),
  ('05a9b2435b114fb5', 'client', $s213$Warm honey-gold body color.$s213$, 'c148920398c05ff36e4fcbd84d182dc5c3cc1650', TRUE, NULL),
  ('05dc830214a8b91f', 'client', $s213$Casual: {0}W / {1}L$s213$, 'ed02eaec1b7cdfe54ca5d028db8b31807f7252fc', FALSE, NULL),
  ('0621e139a09a22b7', 'client', $s213$Grandma$s213$, '1e3c573a02d261117603239280b2414106d2de67', FALSE, NULL),
  ('06283c7ad737ef2a', 'client', $s213$Mustard$s213$, '931e8d8cc7286798b1633cc33805cf51193e14f9', FALSE, NULL),
  ('063fa1974155ab7a', 'game', $s213$TELEPORT$s213$, '0c952f6370ea34faf764b28b990b2dc9fea61c2d', FALSE, $s213$StringTableCards/CARD_TELEPORT$s213$),
  ('064556c685e85780', 'client', $s213$Machine translation - corrections welcome in Discord.$s213$, 'fb72a3491dd3efb40c0d57730cd453bc9d827b78', FALSE, NULL),
  ('066fa92cd9434a97', 'client', $s213$Older >$s213$, '48f932335abd4b7ab52177929989d5898e3fe3b3', FALSE, NULL),
  ('069eb166aa855aba', 'game', $s213$A lot lower$s213$, 'df1c20b44dc5a005ca96222f69051e6f45fc24d1', FALSE, $s213$StringTableCards/AMOUNT_ALOTLOWER$s213$),
  ('06cf09fad072b83f', 'client', $s213$Solo$s213$, '9fc93acaa44f3f647fae2ed40110f88b9561a474', FALSE, NULL),
  ('06d68c0c93bcc698', 'client', $s213$Removed from 1v2 queue after 30 minutes of searching - rejoin if you're still here!$s213$, 'd21a85952028305e60186b5da8eb8bf91d830d70', FALSE, NULL),
  ('06d95cefa1d007e6', 'client', $s213$Riveted steel great-helm with a T-slit visor.$s213$, 'c3916b69a2b9f6d25258ad6c41417cea07f376f8', FALSE, NULL),
  ('071c8c4641b18c3a', 'client', $s213$Homing main$s213$, '2b77056d8510cbf771ae1eabe376618a805c01e7', FALSE, NULL),
  ('0725d81ee01070b9', 'game', $s213$Searching$s213$, '98cc363c0119e35d1c8070755fc4d4c2387aad71', FALSE, $s213$StringTableDefault/PROMPT_SEARCHING$s213$),
  ('0727e7b2034857dc', 'client', $s213$Can't open the portal - this install is on an insecure backup connection. Restart ROUNDS to retry the secure one.$s213$, '3e0baa27512846c1a24260a1e63877576b7abd52', FALSE, NULL),
  ('077676d0bca7cfb9', 'client', $s213$God Build$s213$, '6dd2206f0985f5762623cca9ed3d8e1a74aa684b', FALSE, NULL),
  ('07b271831742817a', 'client', $s213$Rating History  ({0} Elo)$s213$, 'dffa7f7a058fb0d2e1dd78e84871a125326455aa', FALSE, NULL),
  ('07bbc695cbcbf94f', 'client', $s213$<color=#CCCCCC>Damage per second over the match</color>  <color=#99B3E6>you</color> <color=#888>vs</color> <color=#E69988>opponent</color>$s213$, '23d3c7247ce05cff78cc80a60b254f348e4ab9e7', FALSE, NULL),
  ('07dd3025878252db', 'client', $s213$Mute Player...$s213$, '04a185ca6b9d0f63271a00f42ced92d31d342803', FALSE, NULL),
  ('0844884be994ab63', 'client', $s213$Month/Day/Year (US)$s213$, '037358024aa12328fac8d7804df79d1552816c63', FALSE, NULL),
  ('08b1965af9d1ef0b', 'client', $s213$Admin$s213$, '4e7afebcfbae000b22c7c85e5560f89a2a0280b4', FALSE, NULL),
  ('08e57eb5ea26362e', 'client', $s213$<color=#888>No items assigned to you yet - art gets wired to your account when it ships in a mod update.</color>$s213$, '17ac025c7e380c8abcd7f65f12ff482a44d57839', FALSE, NULL),
  ('093cb8d328f0f8c8', 'client', $s213$Soviet$s213$, '42724976abf218f52fcf92c452432ec282de21a7', FALSE, NULL),
  ('0949f07beef44739', 'client', $s213$Show Discord on leaderboard: <color=#FF9966>OFF</color>$s213$, '4d9856099b56f185037bd58ccbdefdec3cf2f349', FALSE, NULL),
  ('096503131133e107', 'client', $s213$Competitor$s213$, '470568764445128dbbde3a4861ab484f4d7f3bb7', FALSE, NULL),
  ('09d89a5ed17a5b36', 'client', $s213$Export Tier List$s213$, '0f2ac9fc2d0300baafc50eda99f1f68f115de3a9', FALSE, NULL),
  ('09daf1b685b881ec', 'client', $s213$Couldn't join the FFA match — your lobby was dissolved. Please requeue.$s213$, '5d5248d4caab0e50ec6fd0364a251463d07bc466', FALSE, NULL),
  ('09deebcae22bfb20', 'client', $s213$<b>Your Lobby</b>  <color=#888>({0}/{1} - host starts at {2}+)</color>$s213$, '6090fa2a628d137cb9870d67b69616b188ef5dd3', FALSE, NULL),
  ('0a1304bbfc6f8b68', 'client', $s213$Win 500 casual games in a row$s213$, '4d2a378dce953a8292d517344fabdca770c713d7', FALSE, NULL),
  ('0a1bc5e0ce656d63', 'client', $s213$<b>Bet on Live FFA Lobbies</b>$s213$, '0d848de7a26cd51381e47b52443df86b1a53b5d2', FALSE, NULL),
  ('0a2e75ad695d3112', 'client', $s213$Who picks these cards the most$s213$, '7845471d1f67cb530d5de522f234514781b8b9b2', FALSE, NULL),
  ('0a51b869b20517e8', 'client', $s213$Frames per second, top-left corner. Handy for checking whether a setting actually helped.$s213$, 'f14bfe467e47f12a5514df9247ea036e5251f589', FALSE, NULL),
  ('0a6fd7b5a8bfc260', 'game', $s213$Fast forward$s213$, '7966f705b3d65923629592dd35195fb7a36bebdc', FALSE, $s213$StringTableCards/CARD_FAST_FORWARD$s213$),
  ('0a7da31bb71a460a', 'client', $s213$<color=#777>(bet placed)</color>$s213$, '86af06d8ad49429bceb0be6f1616d05dda47ec9f', FALSE, NULL),
  ('0a7f9dcfb7f7b30d', 'client', $s213$Win a game 5-0 with Barrage in your build$s213$, '0dc10933da1d6d92074a29c880208de24ac1736a', FALSE, NULL),
  ('0a8b00e11aa7e87c', 'client', $s213$Ban a player$s213$, 'd8bb8f01ecddcbb69753151666860f937807775f', TRUE, NULL),
  ('0aa6a16a1673de73', 'client', $s213$as SOLO vs {0} + {1}$s213$, '1bd88366f34ba7f14fb904e5ed1646c4644328cc', FALSE, NULL),
  ('0ab780cd5bee16fd', 'client', $s213$Win a game after being down 0-3$s213$, 'cc461b976cfa54f3f4fc80d112c44227fd752691', FALSE, NULL),
  ('0ac4a55c5f1ccb06', 'client', $s213$HIGH$s213$, 'd77d0b27955f008358918e195742c4c8208699e1', FALSE, NULL),
  ('0af12ce407aedc11', 'client', $s213$Search Ranked$s213$, '903dc15e26d8934a5bd54ce5dad491d5f406b9b4', TRUE, NULL),
  ('0b0990c45b3d1a1d', 'client', $s213$Bet failed: {0}$s213$, '8f54cd247fc90332d744f53159d73af22c2490ee', FALSE, NULL),
  ('0b1f4d1ce7905901', 'game', $s213$Lock aiming to 8 directions (Mouse)$s213$, '002acc9334a6a85859be46cb3c3bb7c47c8613cf', FALSE, $s213$StringTableDefault/OPTION_MOUSE_AIM8DIR$s213$),
  ('0b37036b006bc7c2', 'client', $s213$Royal$s213$, '2c16ea11eedff827b4e8ce41cee5f947d3418592', FALSE, NULL),
  ('0b8a96a36bbd6047', 'client', $s213$Healing Field main$s213$, '31f3455e822c8b2187691d06a5cbce86abba2ce1', FALSE, NULL),
  ('0bc4ff39724d6896', 'client', $s213$Lucky green clovers tumble around you.$s213$, '9fa8c9a61e28dd229fc118d6c8e04e77a7a2a087', FALSE, NULL),
  ('0bd62ee5c52d93de', 'client', $s213$Clown$s213$, '58d28d96646957acfa9a8c908d0d61aad25b77c4', FALSE, NULL),
  ('0bef6893b50362d8', 'client', $s213$<color=#CCC>FPS</color>$s213$, '098e8c6ff86c7d21c0e60cab817654f2b8c0e276', FALSE, NULL),
  ('0c1ad37d853b8de2', 'client', $s213$Open Upload Folder$s213$, '7b900634f9f53532c69e92a70ddf0d76c6727e0e', FALSE, NULL),
  ('0c24e5696ff0c465', 'game', $s213$Stand still to summon dark powers$s213$, '4711a33663d9b1cb6f9b4ff2946306f909bb44ac', FALSE, $s213$StringTableCards/CARD_ABYSSAL_COUNTDOWN_DESC$s213$),
  ('0c5fd3f91a3e6cd0', 'client', $s213$Match canceled (disconnect)$s213$, '6b674f19d542a98d03f86b68a07fa3979a3dcf26', FALSE, NULL),
  ('0c996f453fd078f8', 'client', $s213$Lowercase letters render as smaller capitals.$s213$, 'a47242e6772160f53510181c157f8401003ae798', FALSE, NULL),
  ('0caa0cb269d0e9b4', 'client', $s213$<color=#FF6666><b>LOST</b></color> {0}-{1}$s213$, '402a9cda67e01dc4345b39756827e04ea577666a', FALSE, NULL),
  ('0cab6cacbbc851b9', 'client', $s213$Tryhard$s213$, '0c06f367e6f129656bdd8dd841192a6f4d2dcb57', FALSE, NULL),
  ('0cb26d500e44e471', 'client', $s213$Could not decode one of the animation frames.$s213$, '121a6b29710d7dbf60c23a87312d793b55096118', FALSE, NULL),
  ('0cc384f0712b97cb', 'client', $s213$Leave Lobby$s213$, 'b9b062ac708c22c87b3d7c39fdf795e7536aaa1e', FALSE, NULL),
  ('0cd2498ace5eb5b1', 'client', $s213$custom 2v2 lobby$s213$, 'd317f861f54f6c4a8fd4dac6ff0efcea37ec2e1d', FALSE, NULL),
  ('0cff0a7295d0881c', 'client', $s213$Devil Horns$s213$, '0f2a3d6e36b590dba6e93f3a10088a8f34103cae', FALSE, NULL),
  ('0d6434110df619b3', 'client', $s213$Adjust Placement...$s213$, '6c8fc4ba295689e94a0b72bb52f19286b2b3303b', FALSE, NULL),
  ('0d7cc210312198ae', 'client', $s213$<color=#66DD66>Match found! Joining…</color>  <color=#FFB347>{0}</color> <color=#888>vs</color> <color=#88AAFF>{1}</color>$s213$, '34fa10fede90cb20a1ddf3da58a43404436557eb', FALSE, NULL),
  ('0d948bf9a085981a', 'client', $s213$<color=#888><i>Loading release notes...</i></color>$s213$, 'c2204d8738de607fe6ddbc5f3239ca27d17fb915', FALSE, NULL),
  ('0da8c2b28b8377a5', 'client', $s213$Wins$s213$, 'b6c015d12e1b59bd78fb246985e37730e38521f8', FALSE, NULL),
  ('0db9c0aeaf61a440', 'client', $s213$Unfocused deep idle (60s): <color=#88FF88>ON</color>$s213$, '93f9e18a8aa5cabddfdddc88fec3c5342da056fa', FALSE, NULL),
  ('0dbcd58642eb2db9', 'client', $s213$<color=#777>{0} activated · {1} successful · {2:F0}%</color>$s213$, '4b634e4f33c03a784c221f8526c5e6bdd335e67a', FALSE, NULL),
  ('0dc7d933cccba541', 'client', $s213$Rainbow Name$s213$, '153fd22a1e9af7179306e615f49ac52f49829bc6', FALSE, NULL),
  ('0dcd7fa5fff1e6d4', 'client', $s213$<color=#888>Loading members...</color>$s213$, 'c7c0a44eb576ee3f9ebbe9436946082e06cba1ec', FALSE, NULL),
  ('0e6859e372c55b36', 'client', $s213$Shows cosmetic trails on you and other modded players.$s213$, '5f080b6372a7db5231fcb8805edd4b8ada17f6be', FALSE, NULL),
  ('0e72750e37c7c6a4', 'client', $s213$Poisoner$s213$, '53b8d6d04b42c5527575738edfd453c84e07ad7f', FALSE, NULL),
  ('0e8218c38e24e14a', 'client', $s213$Glowing magenta neon name with a soft glow halo. Visible to everyone; modded players also see the glow.$s213$, '4ccdeb2b81cdab9d1fe2c4707b86bb05059e0f20', FALSE, NULL),
  ('0ea392bb4e864fa8', 'client', $s213$Hostile Takeover$s213$, '88993ad514a4bd209c99f98a2368669037c34285', FALSE, NULL),
  ('0eea28ade399f3c3', 'game', $s213$Reload time$s213$, '5e26878441512323613f2225e1881f25812714aa', FALSE, $s213$StringTableCards/STAT_RELOAD_TIME$s213$),
  ('0eef1f90d4357dc2', 'client', $s213$<color=#FFD94D>pending initial review</color>$s213$, '4a8962e2f2c84e3dce462d200654ced2b3d2d81d', FALSE, NULL),
  ('0f004b96432f2a20', 'client', $s213$Ranked Uniqueness %$s213$, 'f0ddbdf03fc9e3cf4e1d8d9835269feed90dee1c', TRUE, NULL),
  ('0f0e4598b4018d73', 'client', $s213$Olive$s213$, '8f62f4336f1907e6dc87f983416184094f6ff35d', FALSE, NULL),
  ('0f2503e67bb0f23f', 'game', $s213$Press [SPACE] when ready$s213$, 'c5a34c2887680c7eaf3082c6984bf4aa4f56160a', FALSE, $s213$StringTableDefault/PROMT_SPACE_WHEN_READY$s213$),
  ('0f3442d66b69918d', 'game', $s213$Steal HP from your opponent when near$s213$, 'f1d408316447410202b4d9caf659de8d93742fcb', FALSE, $s213$StringTableCards/CARD_LIFESTEALER_DESC — Health Points
2023-10-17: Added missing capitalization of "HP" to keep consistency$s213$),
  ('0f34e682111c0d18', 'client', $s213$Eyes: golden stars. Equip in the Character editor.$s213$, '0ac81439129159c9c49e680faf69be65fb6d761d', TRUE, NULL),
  ('0f54805e99c76854', 'client', $s213$A ragged black cloak with a blood-red lining.$s213$, 'a60ac5e701992bb53799c6435d8fa9cfeebbbcd0', FALSE, NULL),
  ('0f6b4c74dec1367c', 'client', $s213$Custom player body colors: <color=#88FF88>ON</color>$s213$, '3a6ee4336b7ca871681e18318b4ba037122dacf0', FALSE, NULL),
  ('0fc211da8b7173b4', 'client', $s213$<color=#9AD0FF>Your submissions:</color>$s213$, '72f0ed2b9b3989238388e7edddaf252c81a7cb9f', FALSE, NULL),
  ('0fc595b782b397ad', 'client', $s213$RLFP ping failed - server unreachable. Try again shortly.$s213$, '974727e8ed4995674b56ea6e9de859a6aa61ed4c', FALSE, NULL),
  ('101d281fb7725477', 'client', $s213$Kingslayer$s213$, '27e105212199fa01c8a9ddb8d5052a43b991fbae', FALSE, NULL),
  ('10cc5458fd27e27a', 'client', $s213$Dark red blocks on a dim warm backdrop.$s213$, '6400ddf76a965495252cffa62e366cd2e1e5670f', FALSE, NULL),
  ('111b9b5a0d6725d6', 'client', $s213$Cool teal body color.$s213$, '3f4e6fe068c428db8f08c82ec6f320768c3e77c4', FALSE, NULL),
  ('112f0a217f5a096e', 'client', $s213$Hard to hit$s213$, '6ce2c7378614f190440e5da3487b936abbd6781c', FALSE, NULL),
  ('115669d00bdf96b0', 'client', $s213$Unfocused 120 FPS cap: <color=#88FF88>ON</color>$s213$, 'c71884961136003db03094525edbbee7e5da42dc', FALSE, NULL),
  ('119b8c2381d56d77', 'client', $s213$Decline$s213$, 'b59cf9ed55bb5bd999077bce310a9641033b6485', FALSE, NULL),
  ('11a8ce3b24581f0d', 'client', $s213$MAX$s213$, '7b186e235f284107df6b4dbe6060d2b6a5d9f1e5', FALSE, NULL),
  ('11c7534fb8b7839c', 'client', $s213$<color=#FFD94D>APPROVED - awaiting mod update</color>$s213$, '22e12b0d3921df432cf0884ac46c4dce85a50d83', FALSE, NULL),
  ('11e75bf0cc1f9f07', 'client', $s213$English$s213$, '649df08a448ee3fa90f3746baaf6b0907df42c91', FALSE, NULL),
  ('1249b6f1e502b718', 'client', $s213$Ranked Series: {0}W / {1}L$s213$, '9010764c511b06ab2dc58692c34c829ba1fe04b3', TRUE, NULL),
  ('1256b14cad0e0458', 'client', $s213$Year/Month/Day$s213$, '4eb88001f59d0dff9c3b238ba04dce6e865ae9c1', FALSE, NULL),
  ('126074c573f27c2f', 'game', $s213$Spawn damaging sun waves when reloading.
The rate increases during the reload sequence.$s213$, 'a770314528bc1518e218a7a4d7cdaa88021cf428', FALSE, $s213$StringTableCards/CARD_RADIANCE_DESC$s213$),
  ('1271aee114daa4c4', 'client', $s213$Tier$s213$, '5bd44ebe63cd3b9445ca759f970513d78b28a61c', FALSE, NULL),
  ('12a147f5ca9dd638', 'client', $s213$Selected {0}/{1}  -  click a card to add/remove$s213$, '24ba3677ac4bfe9f46bbc7c35421d9b83c9842b0', FALSE, NULL),
  ('12a6edde67952b4e', 'client', $s213$Spilled Icecream$s213$, 'f2fa96206ed75c0ed163bf95a77c628c022205f2', FALSE, NULL),
  ('12e64c29d0a7dec2', 'client', $s213$<color=#CCC>Blocks vs successes</color>$s213$, '35a24924fe75063bee75a862f34ef86ecc927157', FALSE, NULL),
  ('12f7c7e33d999282', 'client', $s213$Three orbiting spheres of raw energy. ANIMATED.$s213$, 'cb7c351d80fb7f2eb5d656664b0709b7a3bd0416', FALSE, NULL),
  ('13035d18b3c5b6c2', 'client', $s213$Show Gold$s213$, 'b76e070645519586f2e8526c52fc8df857477430', TRUE, NULL),
  ('1322e8bebba60a17', 'client', $s213$Discord Link$s213$, '6853dca9066719a20454a8182b7bdbbf4d68df5e', FALSE, NULL),
  ('1343d05a1b0993f0', 'game', $s213$BRAWLER$s213$, '6dd77966414893447ed2b450a83c6fd263a13490', FALSE, $s213$StringTableCards/CARD_BRAWLER$s213$),
  ('137f5a2472426c2f', 'client', $s213$Ready-up failed — retrying search$s213$, '164da91182aa67abb68e074a1025d16f086001f3', FALSE, NULL),
  ('138e18857cac5a72', 'game', $s213$Yes$s213$, '5397e0583f14f6c88de06b1ef28f460a1fb5b0ae', FALSE, $s213$StringTableDefault/OPTION_YES$s213$),
  ('13ae50b4514bb95f', 'game', $s213$COMBINE$s213$, '1665da04efb16a2aec6e302e358745cc7ad78c35', FALSE, $s213$StringTableCards/CARD_COMBINE$s213$),
  ('13d0d287c990cb23', 'client', $s213$Deep forest green rising to bright jade. Two-color gradient.$s213$, '01d54aa6323503c2e4424a176601f7b00c366139', FALSE, NULL),
  ('1412a8a90c683fb3', 'client', $s213$Century Club$s213$, '65ab9f618934bfa3ace72bac702ee7ca3f2ecbab', FALSE, NULL),
  ('14315d8bfdc142da', 'client', $s213$Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.$s213$, '42004fbbdfdd9e28f20bc7b40b8340b1016a8473', FALSE, NULL),
  ('145afa63120ae9e4', 'client', $s213$Bet placed: {0}g on {1}. {2}$s213$, '4b47c71de405b7826bcc297c3c46ae5de8810bcb', FALSE, NULL),
  ('145d5e6640ad6679', 'client', $s213$Rich forest-green body color.$s213$, '64beb88d5891e40c3adbadb8b1959b410db02d70', FALSE, NULL),
  ('147271f0b1b11c48', 'game', $s213$<sprite name=BUTTON_WEST> To join room$s213$, 'cbe55da30bff13c4cb08fa7139870c0fc260385e', FALSE, $s213$StringTableDefault/PROMPT_JOINROOM$s213$),
  ('14796e67387865fd', 'client', $s213$He/him$s213$, '67cc0b8a50586de358efae7157a8c921a6fa5e8f', FALSE, NULL),
  ('1491ccbbab4f77f2', 'client', $s213$Hypno-spiral eyes. Completely unhinged.$s213$, 'e41832724539bffc1b27e6bf1721c3d4b02fee0a', FALSE, NULL),
  ('149bf365c330d13c', 'client', $s213$as DUO (w/ {0}) vs {1}$s213$, '8833ad12d379ff3fa61c32bb9e943d7b06b5856d', FALSE, NULL),
  ('14ac400eb74d19bd', 'game', $s213$Rematch?$s213$, '2b8ca1c6f332d7ac6f7dc56c8abc7aceaae03d75', FALSE, $s213$StringTableDefault/PROMPT_REMATCH$s213$),
  ('14e6e248ad06ea5b', 'client', $s213$Shows your Discord name on the leaderboard (opt-in; link Discord on the Home tab first).$s213$, '28e456cb2fc9eb62e6a90a66a3be46b85318cf16', FALSE, NULL),
  ('14ff90268c5dfe1d', 'client', $s213$Jumps$s213$, '933adea19eee0a6883654433bf5abd0a524cc8c6', FALSE, NULL),
  ('15452feadbac32bc', 'client', $s213$Link code: {0}$s213$, 'd5cc324443a8277d639cfc7dc37ca9a42af3ce3c', FALSE, NULL),
  ('154bb996c84705ea', 'client', $s213$Win a game without taking any damage$s213$, '25d565c70ac31cc9a4e68446aefbca42024c1db2', FALSE, NULL),
  ('1566b2c6e09119fc', 'client', $s213$Crimson$s213$, 'b3f39ab486dccbade852f17535c258ceb02694ae', FALSE, NULL),
  ('15902baa613f6be8', 'client', $s213$Purple Name$s213$, 'e1b4569dbbad3384f405de04efad13c425231ab2', FALSE, NULL),
  ('1605fe375cfc39fe', 'client', $s213$Get 5 copies of one card in a game$s213$, '76eda7d248ecf2792fc4875e7baac32b49a2cd96', FALSE, NULL),
  ('170c3fd168ea0be6', 'game', $s213$Resume$s213$, 'b3bd0b5a70497bec4a02b7eb1cb0d4f37eb71a2a', FALSE, $s213$StringTableDefault/BUTTON_RESUME$s213$),
  ('172cf193c3f24d78', 'client', $s213$Couldn't start the game.$s213$, '7e469436f604c67095e813dcd9af4a93194ba16d', FALSE, NULL),
  ('172d14a4aa6b80e1', 'game', $s213$Disconnected$s213$, '771e05f27b99fd59f638f41a7a4e977b1d4691fe', FALSE, $s213$StringTableDefault/PROMPT_DISCONNECT$s213$),
  ('174c36bafbe2956f', 'client', $s213$<color=#888><i>No sales yet.</i></color>$s213$, 'c651043d9c918c7ea08eaa0e45592b82520f6d5e', FALSE, NULL),
  ('1754376f6be23625', 'game', $s213$Press
[<sprite name=BUTTON_SOUTH>]
to join$s213$, '819fd6c09f58c6d18d248de0a4100cc6a42567fd', FALSE, $s213$StringTableDefault/PROMPT_SOUTH_TO_JOIN$s213$),
  ('17623eac4b59b734', 'client', $s213$Embers$s213$, 'f95951bd6069d431a0a73fc47ac7e0d3e44e622b', FALSE, NULL),
  ('1770758391fafe0f', 'game', $s213$Main menu$s213$, '37646650602612502263cd071e26789b69a70d88', FALSE, $s213$StringTableDefault/BUTTON_MAINMENU$s213$),
  ('17e39c5f5faa04a8', 'client', $s213$Bounces$s213$, 'fffb1ac23479a3b099333fa68dd4b912625af777', FALSE, NULL),
  ('180256f3c81a984e', 'game', $s213$Bullets home towards visible targets$s213$, '9d05fcdf7bcecc1ec4a38df4db8ecb2f7557f92c', FALSE, $s213$StringTableCards/CARD_HOMING_DESC$s213$),
  ('182e3a5b598b14a6', 'client', $s213$5-0 someone with Sneaky$s213$, '2179b8cbc74315cc138f2e55ff114e7aa047c749', FALSE, NULL),
  ('185819c37faec22c', 'client', $s213$A sleek black mouse cursor.$s213$, '5d67c42eb8f5c9f4a3e92e8852f30b18b536c4c9', FALSE, NULL),
  ('185ea4043021ff08', 'client', $s213$<b><color=#FFD94D>PRIZES</color></b> <color=#888>(at {0} players, live)</color>$s213$, '24a4b3b2e962abfb33dbb275b5574999fa2a3c1e', FALSE, NULL),
  ('18746c7ceab495d6', 'client', $s213$Sid Slayer$s213$, '6ab4534ed3f287fc8a0ea7a93221e16851853fb3', FALSE, NULL),
  ('19028acb5fad6b86', 'client', $s213$Radioactive yellow-green neon name with a hot glow halo. Visible to everyone; modded players also see the glow.$s213$, '75e2d41b04a8463628b2f2bc5c724326fc3488ac', FALSE, NULL),
  ('190526c2629dbea2', 'client', $s213$Top of the food chain$s213$, 'e5f48c13ee118dc3dacd8e536d53a9d26f5301df', FALSE, NULL),
  ('192168566e2a4d06', 'client', $s213$5-0 someone with Mayhem$s213$, '1f256a9c14d5d3d94832169123cda8455fa2d393', FALSE, NULL),
  ('19f025c8862581ab', 'client', $s213$Times Picked$s213$, '3ab26affbf74ac9caaef9e4f7750b9add285ee67', FALSE, NULL),
  ('1a177c3441888ac5', 'client', $s213$About$s213$, '6b21fb791ac05170893860c248401cd24a59b732', FALSE, NULL),
  ('1a2cbebcdb936308', 'client', $s213$Cursor$s213$, '2239943c8d0af354a467e6cc18b9ec9e32f2afcf', FALSE, NULL),
  ('1a4780f9f77a1025', 'client', $s213$Block {0}%$s213$, '574c53873b3f814c5f22b25e5a9fcf5772878724', FALSE, NULL),
  ('1a75ea9cccafc189', 'client', $s213$Warm coral-orange body color.$s213$, 'dbe4d86fb51352879c5bc4e9cb3c5823c4ee486c', FALSE, NULL),
  ('1ac50717539486a6', 'client', $s213$Fast finisher$s213$, '142cf28bcdc25525a041a6fdec70244bd7f34e83', FALSE, NULL),
  ('1ae13cdc903c028b', 'client', $s213$TOURNAMENT STARTS IN {0} - stay in ROUNDS at the main menu!$s213$, 'c32e6ef305f7305a05b6f89f622a0d6797911a18', FALSE, NULL),
  ('1b4effb239673333', 'client', $s213$Casi's mouth$s213$, '8a968fb7dbc2ab1fb3e31e87aea9d81c5b4fc4a1', FALSE, NULL),
  ('1b5a95c6021117d4', 'client', $s213$Player removed from the lobby.$s213$, '6513aeea6e95789c0cc2258d2dd9b48844073ba6', FALSE, NULL),
  ('1b9b94fd93c13e2e', 'client', $s213$Bullet-hit particle cap (2/frame)$s213$, 'ce55c51755db07c0da74f585b4c7a4582d55ac19', FALSE, NULL),
  ('1c025368bd76b722', 'game', $s213$Bullets$s213$, '7509c5747e5db3dfa3373afc42eca9f5b27a8599', FALSE, $s213$StringTableCards/STAT_BULLETS$s213$),
  ('1c1b39aab2fc963b', 'game', $s213$EMPOWER$s213$, 'c8d117e77eecb8f2e481fcaa326807dec2779527', FALSE, $s213$StringTableCards/CARD_EMPOWER$s213$),
  ('1c33f30868e74629', 'client', $s213$Opponent Variety % (unique opponents / series)$s213$, 'eb54efd7afacb04b38b40bd3cb5db7c2b094c1cd', FALSE, NULL),
  ('1c48751eaee33553', 'client', $s213$Chat Mutes...$s213$, '545716aba2b183be2c211309ef313d8dc26fa50f', FALSE, NULL),
  ('1c5a31cb31fb37f3', 'client', $s213$Trails$s213$, 'abe7e366ae1c1eacb6ef6af9bb1d6c200b03a458', FALSE, NULL),
  ('1c5acd21065ca4ea', 'client', $s213$<color=#7788AA>-> {0} bet {1}g on {2} - pending</color>$s213$, '3c8ec61681d4250b1d3d48235800cfb3557f2f9b', FALSE, NULL),
  ('1cd08b528d6cb3fb', 'client', $s213$Pick Your Start Times <color=#888>(multi-select, required to sign up)</color>  <color=#7FE8C3>best time: {0}/{1} agreed</color>$s213$, 'a1b97d981b566c2923f68b338c4d2b81ee2018a2', FALSE, NULL),
  ('1ce0cf2cdb6b1aa8', 'client', $s213$Neon Lime$s213$, '664681d96609b863f34e7bda85acda6b22882fc8', FALSE, NULL),
  ('1cfe92e5e2faa80d', 'client', $s213$Bet placed: {0}g on Team {1}$s213$, 'c51d1dc4be72787b45001281f94ad8d9d4d99c85', FALSE, NULL),
  ('1d06bcb7ee5096ad', 'client', $s213$Avg Key Presses per Game$s213$, '1d4a57f5312863f49c410c101712a44f6d8885ac', FALSE, NULL),
  ('1d0c46aee85e3de7', 'client', $s213$Mouth: a distinguished handlebar. Equip in the Character editor.$s213$, '7f2f10fba7859343ca2963aa166a642641709abe', FALSE, NULL),
  ('1d212540835c92ae', 'client', $s213$Sunburst Halo$s213$, 'dd5499d7f0a2d38242360148c069aa29f121ccbb', FALSE, NULL),
  ('1d3249d2a988a709', 'client', $s213$Dusty rose blocks on a warm dim backdrop.$s213$, 'abc5f75a23c865711420044ed601217ae35bea54', FALSE, NULL),
  ('1d473e51fc884c2a', 'client', $s213$Taken$s213$, 'c66c12b98882a2c74600f15115c65f693c8d5f34', FALSE, NULL),
  ('1d5cc2846a0a012c', 'client', $s213$1v2 match found, but you're in a game — removed from the 1v2 queue.$s213$, '54d0a493808ea0c5e0232a9699cbd5ed530fac16', FALSE, NULL),
  ('1d7d88d5ab1ccb40', 'client', $s213$Platinum$s213$, 'c93fa0a5953ea725bfad3d51caa53e0abd992fd2', FALSE, NULL),
  ('1d87122882bedc8a', 'client', $s213$No opponent has enough ranked series against this group yet.$s213$, 'd1a321b6ff6c3937294fa3d6a4e45c64e4cc49b4', TRUE, NULL),
  ('1d8bfec2606b8964', 'client', $s213$Grant a translation role - find the player$s213$, '6c9c8a13e709141fe143390523f4e2389a800362', FALSE, NULL),
  ('1da67081596a4e36', 'client', $s213$Map shadows: <color=#FF9966>OFF</color>$s213$, 'aea9c61229fe7166c9df86c5df526bf39f4d5312', FALSE, NULL),
  ('1dcbb7f9eb5c256c', 'client', $s213$Brain Cane$s213$, '32f934bf1243eb49222743a5d0f32e178fca1845', FALSE, NULL),
  ('1dea4fe7a34b66b0', 'client', $s213$Side: Solo$s213$, '5ea804d3a2d1d5bc3cb0429a135b43edc310bf0d', FALSE, NULL),
  ('1e088d00a6318256', 'client', $s213$Built for ranked.$s213$, 'ca3230fafdeab8aaaca7de56a4c8ece290129e03', TRUE, NULL),
  ('1e0ef297c1e3d8b3', 'client', $s213$one color at a time$s213$, 'f9c0c29d091d50a9086354e063e47954c59e1b90', FALSE, NULL),
  ('1e2571adc0faf416', 'client', $s213$Click a player$s213$, '5821ae9e99fd1b23089635ce0c78c13e11e76603', FALSE, NULL),
  ('1e5e8f7d43e5b601', 'client', $s213$Healer$s213$, '6cad85d7f7dcd1b52fab90c0435e0ef4df7ef791', FALSE, NULL),
  ('1e91995466d6d8ff', 'client', $s213$<color=#FF9988>Blocked buyers</color>  <color=#888>(can't purchase your items; gifts still work)</color>$s213$, '56b2f8794b6c6e5bfde3fa67fd25718e29f1b8b8', TRUE, NULL),
  ('1e9e0d2019681a60', 'client', $s213$Couldn't kick that player.$s213$, '635b1327e4909407ac4dd72c55143e124889caae', FALSE, NULL),
  ('1ea1bb377fdee4ff', 'client', $s213$Titles$s213$, 'a116f7255e19431f1fbf68cdd9f4dce3b66e6b04', FALSE, NULL),
  ('1ec90b2ecc0c22a7', 'client', $s213$Chrome$s213$, '218e75c7a912404b048fff0747e40108873b6334', FALSE, NULL),
  ('1ed575a86bc9d240', 'client', $s213$Cards:$s213$, 'a6bcb0b542f89a1109f41bfa09c4216c3cd8991f', FALSE, NULL),
  ('1edaccb2dca7ceaf', 'client', $s213$Cool desaturated slate-grey — easy on the eyes.$s213$, '0c4e7b1605bb2b6079143cb3ff386f3d2882a487', FALSE, NULL),
  ('1ee9d7c98695afd0', 'client', $s213$Rich purple blocks on a dim cool backdrop.$s213$, '969e7cedcc56832829613fa1b9a6909c8e2c57e4', FALSE, NULL),
  ('1f034970c93e4da5', 'client', $s213$Could not join as spectator - the game may have ended.$s213$, '030e0672400e1534d31172faec59cf7062e1222f', FALSE, NULL),
  ('1f35f046ca078416', 'client', $s213$Red Cursor$s213$, '8944bac56fb71a84e3ae82e1b90e93e2f2b4bb1d', FALSE, NULL),
  ('1f8130b364fad8c5', 'client', $s213$Done.$s213$, 'e2bcda84facb3954e32539ae66300758b6d834b2', FALSE, NULL),
  ('1fa81a239870be31', 'client', $s213$Get over 50 kills in a single ranked FFA$s213$, '358a314e30b7cdc651b30425ab046442b4e2e9d7', TRUE, NULL),
  ('1fd64c1efd7d9083', 'client', $s213$Empty Power main$s213$, '83bdd3b5230da99776ea3b56316a89419519fbcf', FALSE, NULL),
  ('201f4f9ee52b9f86', 'client', $s213$Posted to Discord - good luck!$s213$, '156ad8a2f775907515a8186cda3dc77ee4001e83', FALSE, NULL),
  ('203a31ab7377e279', 'game', $s213$Lower$s213$, 'b91eed4b7a80cd9572a27e65ebdff9caa4b3b9a4', FALSE, $s213$StringTableCards/AMOUNT_LOWER$s213$),
  ('204f8caeaf9b9177', 'client', $s213$Prismatic$s213$, 'ffad6acebcb46cb4a5b292d6ce8b9156bb2952e3', FALSE, NULL),
  ('2067d849636de5c3', 'client', $s213$Matchmaking hiccup — putting you back in the Quick Match queue...$s213$, '8e5941f5a7de20463239bacbbce5329c3a54bcb6', FALSE, NULL),
  ('206cc9338e586cf5', 'game', $s213$LET'S GOO!$s213$, '99a01cdc098e5a37f53c20fb706c096e097e09ef', FALSE, $s213$StringTableDefault/PROMPT_LETSGO — 2023-10-17: Added missing apostrophe in "LET'S".$s213$),
  ('20a200b93b0f4139', 'client', $s213$Balance: <color=#FFD94D>{0}</color> gold$s213$, 'c663090066ad025d9f11faa0246cd410f6c5acf4', TRUE, NULL),
  ('20a3c59e0a2ebcf4', 'game', $s213$Pick one$s213$, '490fd462becfdea6fe54ee4160229f09ae5f4178', FALSE, $s213$StringTableDefault/PROMPT_PICKONE$s213$),
  ('20d99221097e1fef', 'client', $s213$Amber$s213$, '27a01d4772038a3f83552908e0470604e773f8af', FALSE, NULL),
  ('20e937b53e50ddff', 'client', $s213$Thanks!$s213$, '1da20795f84bb9c5e16697aea34f14720e38fc37', FALSE, NULL),
  ('2130d9c2eb9e3c76', 'client', $s213$Lemon$s213$, '4459b791a680572873dc2cf033487dc21edfcb9c', FALSE, NULL),
  ('214528f7f4bc262d', 'client', $s213$1v2 - UNRATED$s213$, '74e647231db3f6b2acc2c4622670eb503571289e', FALSE, NULL),
  ('21464be1e8300f5e', 'client', $s213$Pine$s213$, '456e097f4ceb19803ed7d70dbf2d28a51848d23f', FALSE, NULL),
  ('2162e2c2b5f464fe', 'client', $s213$  <color=#66AACC>{0:F1}% of players have this</color>$s213$, 'e4f560bd5c376f04483f27e865429b9aa02616ec', FALSE, NULL),
  ('216f8c7dad3b04b0', 'client', $s213$Revoke Translator...$s213$, '5505effc85240d0187d0a19a306e36e6f38da3e7', TRUE, NULL),
  ('21a19e853e62a77b', 'client', $s213$Smoking$s213$, '7b3d0b443ce4a8405de90ed439b33999c90d489e', FALSE, NULL),
  ('21e20bf0ec019f0a', 'client', $s213$<color=#FFCC44>UNRATED</color> — stats, gold and XP count. Ratings never change.$s213$, '8f254dc7f4f1db04fb0efd2953a95b75e6d05c86', TRUE, NULL),
  ('21e8b9f068f73353', 'client', $s213$<color=#777>{0} fired / {1} hit ({2:F0}%)</color>$s213$, '1f835b9f9fadc2c1b294ebb286b32f3d73a2c2ae', FALSE, NULL),
  ('21ef2621e7ac1f10', 'client', $s213$Avoid in Ranked Matchmaking$s213$, 'd44f4d73ce000ba018ed8700a57bc3cbda8ece39', TRUE, NULL),
  ('222d85297c06217b', 'client', $s213$Discard$s213$, '36fff63ccbcd7bf96ac9014e3e482702fc2b02d4', FALSE, NULL),
  ('2252a0cefefdafdd', 'client', $s213$(no log content read from: {0})$s213$, 'c91246a5320a509c2bb9418d366d1f8825a028a9', FALSE, NULL),
  ('2267d5721109f6dc', 'client', $s213$First to:$s213$, '88c0562022ffeb4ef8821335d8fa3e20823550a1', FALSE, NULL),
  ('22aaa9cf5852d31c', 'client', $s213$PICK YOUR CARD - {0}s$s213$, '34b31f7c574f47f91bb097cc3a682e84995a9325', FALSE, NULL),
  ('22bbf3bbfc5851b3', 'client', $s213$TOURNAMENT STARTING - matches are being created, hold tight...$s213$, '23f7bcf444a010b5e29565495b64b0e169aab5bc', FALSE, NULL),
  ('22bca019fe79ef9e', 'game', $s213$Report opponent$s213$, '0ee07ba377d37ab0accfe1f82226824e83b15812', FALSE, $s213$StringTableDefault/BUTTON_REPORT$s213$),
  ('22d09513ec88a817', 'client', $s213$Left your game to join the queued match - no leave will be recorded.$s213$, 'a2c2f1934a27f01d835e8aae8fedba25a5432737', TRUE, NULL),
  ('22de6be221508bd8', 'game', $s213$Host room$s213$, 'e0bf717ef48a6002f8b798ea1e13f80279d0a579', FALSE, $s213$StringTableDefault/BUTTON_HOSTROOM$s213$),
  ('22eac961461ab249', 'client', $s213$Ascendant$s213$, 'c6db2ec02dcf3556a6323441f9db90a8db6c6932', FALSE, NULL),
  ('23047503aa37b788', 'game', $s213$BOUNCY$s213$, '0a6258c9f6ab3046dadd92968ae4c4d0e99ad04f', FALSE, $s213$StringTableCards/CARD_BOUNCY$s213$),
  ('2336cf45edf6056b', 'client', $s213$Casual Conqueror$s213$, '7f89e50558edac544825522ec264018f192008a5', FALSE, NULL),
  ('233be27e4f15d639', 'game', $s213$BUCKSHOT$s213$, '405deae30af72d5bc7285c4710f940268ad14dc6', FALSE, $s213$StringTableCards/CARD_BUCKSHOT$s213$),
  ('237b52a3029ad67f', 'client', $s213$you$s213$, '8af56de68279cb6f5ed022f31af18b9fcdcc2e92', FALSE, NULL),
  ('237b5d17e7ab0b7d', 'client', $s213$Private FFA lobby$s213$, '497ee30f36b72d164c36997c60d9b69233756437', FALSE, NULL),
  ('2380439a94a853ee', 'client', $s213$<color=#FF9988>Hit:</color> {0}% <color=#888>({1}/{2})</color>$s213$, 'c71e0391acbc34eefbfee6148971ec18fac0b669', FALSE, NULL),
  ('2384a8ba24996fe6', 'client', $s213$Grant$s213$, 'c02329c48f348eb633688f33c499b18b31dcb947', FALSE, NULL),
  ('23985dacf212b283', 'client', $s213$Block debug overlay: <color=#88FF88>ON</color>$s213$, 'dc8238b1d7f34c183b4144bb47f577c8643952ce', FALSE, NULL),
  ('23a2363525a63d2b', 'client', $s213$Constantly cycles through the rainbow during a match.$s213$, '7216727508f5cdbfb1e167595a4e44b10237b778', FALSE, NULL),
  ('23a58ca68c16b593', 'client', $s213$Win against Stan in a ranked series$s213$, '68d423046930d4adf98766d56162de081943e7f8', TRUE, NULL),
  ('23ba5ae4bf44caf7', 'client', $s213$Skip MenuControllerHandler.Update during an active match.$s213$, '237ffaf765bbff962746c4fd0c785881512d1eff', FALSE, NULL),
  ('23d6d84ae59939d7', 'client', $s213$Showing: Elo over games$s213$, '223b8527cddb50f542113f5f695eb3275b59e7d1', FALSE, NULL),
  ('23e7463a77676d31', 'client', $s213$Discord$s213$, 'bccc14ee7da1d20ff06b9ff2497087e8c7d9f28b', FALSE, NULL),
  ('23ee26b036ad3ca1', 'game', $s213$TACTICAL RELOAD$s213$, '655aa405686724cd398ca2779accf853b80fd3e0', FALSE, $s213$StringTableCards/CARD_TACTICAL_RELOAD$s213$),
  ('23f3e8961d9a6d6d', 'client', $s213${0} elo$s213$, '5519c24b363f6799a1bfaab8e067c25e0eca51e3', FALSE, NULL),
  ('24230f46ba7a76e6', 'client', $s213$The host removed you from this lobby.$s213$, '9f61b5edffaab420f9ca22f57f9f3dcf646c4a94', FALSE, NULL),
  ('242c8e57c8c66cb7', 'client', $s213$Couldn't join the 1v2 match — your lobby was dissolved. Please requeue.$s213$, '3a152fbb23e06aa19dd9ffdfa6a779c344fbeebd', FALSE, NULL),
  ('242f5f5f70d848b7', 'client', $s213$RLFP ping failed: {0}$s213$, '6136170d5d17ddca75e9d37f52c04c12fc73a7ea', FALSE, NULL),
  ('245a527fbb3a61ff', 'client', $s213$Times picked (all players)$s213$, 'e2993d8a67ea3605c1ca0272e53ca9c159870936', FALSE, NULL),
  ('247786047e006128', 'client', $s213$Tank$s213$, '0ba4d1aee6f233efc1f3b78141b4af7d08b86c3c', FALSE, NULL),
  ('248b6c3c08e4d317', 'client', $s213$Typing channel$s213$, '6f038cc9011f8772486e3ecf9af8265a33c6594a', FALSE, NULL),
  ('24f88664dcd4a628', 'game', $s213$Português (Brasil)$s213$, 'd53cc7ed60de7a3d7011da44b3d0e6c11cb1b68d', FALSE, $s213$StringTableDefault/LANG_PORTUGUESE_BR — 2023-10-23: Replaced the unlocalized name with its translated version
2023-10-17: Added missing "t" in "Portuguese"$s213$),
  ('250dcc5547b47d05', 'client', $s213$<color=#66DD66>Game starting! Joining as player {0} of {1}...</color>$s213$, 'a337367fad680421586b92e5238764e639863dbf', FALSE, NULL),
  ('254a6264214b6cca', 'client', $s213$Password$s213$, '8be3c943b1609fffbfc51aad666d0a04adf83c9d', FALSE, NULL),
  ('256d2b14212ba5d4', 'client', $s213${0} item(s), {1} cop(ies) out there.$s213$, '1ab5b75b0bfcc6c62c111b526749c2b8fdbd47ed', FALSE, NULL),
  ('25e3c84b4a5ba59f', 'client', $s213$Duo {0}W/{1}L$s213$, 'f9a96ae8d3343e98d3017e9bb5e94de28b0e57b9', FALSE, NULL),
  ('25efa481b1fb6700', 'game', $s213$Back$s213$, 'b52b36b7269fbfc58ec24bb724691951a3decbe8', FALSE, $s213$StringTableDefault/BUTTON_BACK — Action to go back to previous menu$s213$),
  ('26d766cf70a26dd6', 'client', $s213$Locks the map to ROUNDS' Rainbow palette.$s213$, '9ae747eccb6b6170ae4f18896e498142e45387f4', FALSE, NULL),
  ('26f48ec14590c3ae', 'client', $s213$Force your name to render uppercase.$s213$, '6038950c3ffe7f90843135db324457e4fa5b86b1', FALSE, NULL),
  ('272352f5117c660e', 'game', $s213$Spawns a field that pulls enemies in and stuns after a while$s213$, '6225ec18d5b84d94bcde33e55c1b3adc2562fd0a', FALSE, $s213$StringTableCards/CARD_SUPERNOVA_DESC$s213$),
  ('277d3dae33f6df39', 'game', $s213$Bullets aim for visible targets when bouncing$s213$, '7cb0894b38a9d409abcc0bd91c7fbe2bdae69678', FALSE, $s213$StringTableCards/CARD_TARGET_BOUNCE_DESC$s213$),
  ('2792e878bdb98dbe', 'game', $s213$Left stick aiming$s213$, 'cb308c1c33d95a03cccaadca89fc64592851331f', FALSE, $s213$StringTableDefault/OPTION_LEFTSTICKAIMING — Xbox Terminology: Left Stick$s213$),
  ('27972bcd47cb6e6e', 'client', $s213$Italic$s213$, '1616e2e5405e69c4e3914c67c644a9bd3ac00956', FALSE, NULL),
  ('279b058cb2249f39', 'game', $s213$Bullet slow$s213$, '1982b45375c2d30f60024c602fa49444a089bddb', FALSE, $s213$StringTableCards/STAT_BULLET_SLOW$s213$),
  ('27cea71fb855ef6e', 'client', $s213$<color=#888>Solo Extra Initial Pick: the solo gets one extra card in the game's FIRST draw only. The HOST's toggle decides it for the match.  <color=#7FDF7F>Active in-game</color> <color=#888>— the solo's first pick screen deals twice.</color>$s213$, '8b6fde081373c9db70aab9253e5979c308cdc9e7', FALSE, NULL),
  ('280a08e85e79e12d', 'client', $s213$Frost$s213$, '6032a672e309a4dfd10a6c41199d5fd8c5c83da9', FALSE, NULL),
  ('28221c7021c528aa', 'client', $s213$Clean House$s213$, '7889f8417d64298ad417c4d526a39ba7103ace7c', FALSE, NULL),
  ('2841f494f6f6cdd3', 'game', $s213$You have not blocked any users from other platforms$s213$, '3b665f98f5099560a4083a2a787f297c699a51a5', FALSE, $s213$StringTableDefault/PROMPT_BLOCKLIST_EMPTY — Shown when managing blocklist but the list is empty$s213$),
  ('2871e3c4ddf170ce', 'client', $s213$Left the 1v1 match queue - you joined a game$s213$, '452d97bc5ef6822c153b1404472aed1ce172d54d', FALSE, NULL),
  ('28753fa2516fa9a7', 'game', $s213$Bullet bounces$s213$, '62014f1a9ff0c5190b3b038653b4b8b0ce5a9f3c', FALSE, $s213$StringTableCards/STAT_BULLET_BOUNCES$s213$),
  ('287bb7dfc58feb5b', 'client', $s213$Rank: <b><color={0}>{1}</color></b>$s213$, '5ae95848f1654fdab6009b60a2e5515c472863d9', FALSE, NULL),
  ('288dbb0fdf1491bc', 'client', $s213$They/them$s213$, '2a94b32a35c314d000ef6cd80beca279a0e2067b', FALSE, NULL),
  ('289b33714e60ffc7', 'client', $s213$Map lighting: <color=#FF9966>OFF</color>$s213$, '253205f4630eeabef874bba5179933fc2284c0d9', FALSE, NULL),
  ('28ade4ed4e32aabe', 'client', $s213$Losers$s213$, '6ce79956bdb35a2d91a54cbcd83332de043345d7', FALSE, NULL),
  ('28d4ff2dae7455f9', 'client', $s213$A bright orange mouse cursor.$s213$, '23e39b1ad591fe7bb634d0bb71deb0af7c7f6c47', FALSE, NULL),
  ('28f008bfef758548', 'client', $s213$Wisps of living shadow crown your head. ANIMATED.$s213$, '504f4643d13463af8dc37482c5cbe0acc4a75d6b', FALSE, NULL),
  ('28f68e8f4b5e031a', 'client', $s213$<color=#FFB347>2v2:</color> {0}W / {1}L ({2})  <color=#888>Rating:</color> {3:F0}  <color=#888>Peak:</color> {4:F0}$s213$, '644c522f19a0e7153b4f63cb958665eb40c20b7e', FALSE, NULL),
  ('28fe1c29d7ee1982', 'client', $s213$Action Log...$s213$, '1f50d36eaab8e0a95f5ac611ea82dcce423107cc', FALSE, NULL),
  ('2925eb5deba3c50f', 'client', $s213$<color=#777>{0} fired · {1} hit · {2:F0}%</color>$s213$, '832d8562776bcde7b674087bf039a72089be6953', FALSE, NULL),
  ('293d08e159ee05b9', 'client', $s213$Broadcast [{0}] "{1}" to ALL players? It stands until revoked.$s213$, '773fb6d4f4bd4ea0effa809be6e54a854b2970ed', TRUE, NULL),
  ('296bc9618defb504', 'client', $s213$<color=#88FF88>Purchased!</color>$s213$, '9c6bbae583fc1361282e70616ace14758f6e8c73', TRUE, NULL),
  ('2974b8e5c24bb499', 'client', $s213$Severity:$s213$, '5d92c2e8b2137b358d6e0cee27dc8213007e445f', FALSE, NULL),
  ('29956eb093b192eb', 'client', $s213$<color=#888>Leaving...</color>$s213$, 'fcff73f47ee10219a3876754afb842f262ea44cb', FALSE, NULL),
  ('29acfd71fca68846', 'client', $s213$Idiot$s213$, 'b2c854c19c069e8f54d7bc38119fa68daba14613', FALSE, NULL),
  ('29bc540f182069e6', 'client', $s213$<b>2v2 Ranked</b>  <color={0}>({1} searching)</color>$s213$, 'ef44278d615ad0dfbd3a35bea5d164c5c9ded7d9', TRUE, NULL),
  ('29ca0ad33866e932', 'game', $s213$Save$s213$, 'efc007a393f66cdb14d57d385822a3d9e36ef873', FALSE, $s213$StringTableDefault/BUTTON_SAVE$s213$),
  ('29d71e9e09a5b08c', 'client', $s213$Server Alert...$s213$, '43e806fad57a21d2cddee2aeedc89b6c65c5fa14', FALSE, NULL),
  ('2a0816edad12844a', 'client', $s213$Obsidian$s213$, '24c869802c3e242e28585a1c90c21847f259e4f8', FALSE, NULL),
  ('2a2623aac4f692e4', 'client', $s213$Signup failed$s213$, '149dfa301d26bdabd63461fc21867bdbbe26f2d1', FALSE, NULL),
  ('2a302e5baecea9de', 'client', $s213$Won$s213$, 'b273fb28770817940a8c1ea6a33b69274996a898', FALSE, NULL),
  ('2a3b6394364daf02', 'client', $s213$Stop spectating?$s213$, '629d05ffa81ba4280ad433fd1298f4ee66e9a811', FALSE, NULL),
  ('2a6188ce0acf8037', 'client', $s213$<b><color=#FFD94D>HOW IT WORKS (Sync)</color></b>
  1. Pick every start time you can make, then sign up (Discord must be linked)
  2. It locks when <b>8+ players agree on one time</b> - decided <b>2 days before</b> the default start, so you always get 24h+ notice; players who can't make the winning time are removed (no penalty)
  3. <b>Have ROUNDS open at start time</b> (main menu is fine - no tab-sitting needed)
  4. Mod <b>auto-connects you to your opponent</b> - no queue, no invites
  5. Play BO3, bracket advances automatically - <b>plan for a couple of hours total</b>

<b><color=#FFD94D>BETWEEN MATCHES</color></b>
  * ~7 min breather before each of your matches after round 1
  * Both players press <b>Play Now</b> to skip the break and start early
  * Show up within 10 min of your match or forfeit
  * Bracket hidden until start (no scouting your first opponent)

<b><color=#FFD94D>FORMAT</color></b>
  * <b>Double-elim</b> BO3 (first to 2) - losing once drops you to the losers bracket
  * Matches run in parallel: your next match schedules the moment its players are known
  * Top seeds get byes when fewer than 16 sign up
  * Grand Final: WB champ vs LB champ (bracket reset if LB wins first BO3)
  * All matches count toward ranked Elo

<b><color=#FFD94D>PENALTY %</color></b>
  * Grows when you sign up but no-show at match time
  * Lower penalty = priority if more than 16 sign up$s213$, '630d5fe7b6a1288b2d2def76fbc528dd95a739c4', TRUE, NULL),
  ('2a8c1fdc9abb0582', 'client', $s213$Hello!$s213$, '69342c5c39e5ae5f0077aecc32c0f81811fb8193', FALSE, NULL),
  ('2aa987f867bde0fc', 'client', $s213${0} matches ({1}W / {2}L)  WR: {3}%$s213$, 'da5d5190f132c40421541404bfbc922fa7b4115e', FALSE, NULL),
  ('2aad25bde6099301', 'client', $s213$A deep woodland green.$s213$, 'c1855544914c1abd869dc681d7a531ee05833e2c', FALSE, NULL),
  ('2ab0436083a67623', 'client', $s213$games ->$s213$, '8d35ca7e43221d036bad3a81a6356555ee61ba8f', FALSE, NULL),
  ('2ae422d5d897c4cd', 'client', $s213$Wrong password - try again$s213$, 'd46cc0b91a618d588b82c99aabd80674a0044423', FALSE, NULL),
  ('2b07bbabfb8a43f6', 'client', $s213$Ammo$s213$, '407c60401b79318f2877683ed6df36f0bda6cfee', FALSE, NULL),
  ('2b298b7271502c6c', 'client', $s213$Players$s213$, '392feef07c53c9a7b2763d1fd30fb3f0d68099cc', FALSE, NULL),
  ('2b2a2115ec5b8f48', 'client', $s213$<color=#888><i>v  Scroll down for leaderboard + recent series  v</i></color>$s213$, 'a21ec038b09f098ffcc32f78e8bb80305b6f0ddb', FALSE, NULL),
  ('2b45ba05db9d02bf', 'client', $s213$Match canceled — searching again...$s213$, 'e26c6bb791ba1abe64e3a0009979a9e9ce23af69', FALSE, NULL),
  ('2b5b3a47fa9ab0b2', 'client', $s213$Electric sparks snap and dart around you.$s213$, 'b4ce3eb96421a2bc09e75479472c6baa5a0610ee', FALSE, NULL),
  ('2b6277b71e22c3a6', 'client', $s213$Series complete: {0}$s213$, '366f6b0c2e95252863a672eae68c35cf6c90ed1a', FALSE, NULL),
  ('2b6f6945b122da91', 'client', $s213$Bullet spd$s213$, '3f7097dd693481d4b33a1a1360bbaeab8ec78561', FALSE, NULL),
  ('2b9dc3fb741aa589', 'client', $s213$Royal purple drifting into pale cyan. Two-color gradient.$s213$, 'c085d0e3b3ec14e7c2c9f0463ff2c8a00dec591e', FALSE, NULL),
  ('2bb1bf93b17bd29d', 'client', $s213$   (Total Series {0} - {1})$s213$, '084be6fc3f55fa36a3d40c683fad5e686ff98f7a', FALSE, NULL),
  ('2bc7b81351452373', 'client', $s213$CANCELLED (not enough players)$s213$, 'ae687d91ac348704cf2ceb4910feaccbed518dfb', FALSE, NULL),
  ('2bd8936660a6d26d', 'client', $s213$That FFA lobby is private — enter its password.$s213$, 'd11656a4df6895daa62e6288538c2b8b353539da', FALSE, NULL),
  ('2bef0e5cdc0b94f1', 'client', $s213$Level {0}$s213$, '8051c09f7c6dfc8c86a8ea94b528253ae4137333', FALSE, NULL),
  ('2bf6225670195b64', 'game', $s213$Smaller$s213$, '30219022865242c8c328da5ba178d41684da1403', FALSE, $s213$StringTableCards/AMOUNT_SMALLER$s213$),
  ('2c0b482cb7fb2078', 'client', $s213$Cool blue energy crackling behind you.$s213$, 'b3184788eb8c6ab50e98bdded730901d8b5f4505', FALSE, NULL),
  ('2c0bcac005222b8a', 'client', $s213$All (merged)$s213$, '0cffeabac63123322aba0bfa89e7867134d572bf', FALSE, NULL),
  ('2c24e474e0752c0f', 'client', $s213$ranked 1v1 series vs anyone in the selection, minimum 5 series$s213$, '8573726b84feacf62a9d1bb6345a0386a66ff840', TRUE, NULL),
  ('2c2b83458da6e21e', 'client', $s213$Ember Gradient$s213$, '50b385ec12fd86912cc1c6ecc39e0abf1a282cca', FALSE, NULL),
  ('2c43f20e3923bb38', 'client', $s213$Left tournament signup$s213$, 'b073357d5e9db54d87493c1c4f5787a3a9747a53', FALSE, NULL),
  ('2c692d50a4ccf781', 'client', $s213$Knockback$s213$, 'f898dcaa913e7d96aa2f5cc90629d9e61f5f363e', FALSE, NULL),
  ('2c6ddebe063dbd3c', 'client', $s213$Avg Cards per Game  (lower = stronger)$s213$, '3b5cb53623777da9da001e365460faeffffe4707', FALSE, NULL),
  ('2c906a75c80db5cc', 'client', $s213$Target Steam ID$s213$, 'dc6bac792e0b1c0368b9569dd6e78dc6aedec1c8', FALSE, NULL),
  ('2cb12d5097621e42', 'client', $s213$Appear offline (Home lists): <color=#FF9966>OFF</color>$s213$, '8b978ab93e691bc57113c70eded0adb5b571eab3', TRUE, NULL),
  ('2cd796c73bb4cce7', 'client', $s213$Performance master switch — flips ALL the patches below at once.$s213$, 'baae5e74ea779b7a0764d7e688a498b8ce825e73', FALSE, NULL),
  ('2cddd33bf9f91479', 'client', $s213$Disable$s213$, '9a7d4e0687b14e2b7cda406900b802782cd50a62', FALSE, NULL),
  ('2d17a111ecfa7be7', 'client', $s213$<color=#888><i>Update of {0} - grab them in the Shop tab.</i></color>$s213$, '2fe8b21054cd17ebd00a292566d04d71f3148cde', FALSE, NULL),
  ('2d1a71bebc25ca03', 'client', $s213$Allow other players to spectate your ranked games. Turning this off also removes current spectators.$s213$, '2913e520b772748a9b47eac3f069e372230accaa', TRUE, NULL),
  ('2d22d53c0db971c0', 'client', $s213$Message (shown to every player)$s213$, 'fc0146814b0200189b4f3f9a58bc78b79468d526', FALSE, NULL),
  ('2da191e612f59089', 'client', $s213$Couldn't confirm 1v2 queue leave — the server will clear you shortly.$s213$, 'b0f81efdd534d46cae6d44d58077b1b6ed1a6553', FALSE, NULL),
  ('2dca86b596943f57', 'client', $s213$Void$s213$, '207c7c00630b836d3afb46848bdb24a92023331d', FALSE, NULL),
  ('2de3a943a045ca65', 'client', $s213$Double KO - nobody scored this round.$s213$, '019b92f53aad498f211a0607a94d18c8a47d2041', FALSE, NULL),
  ('2e2b91c63683c1e8', 'client', $s213$Connection was lost — returning to menu.$s213$, '84a7957aad998fb6f6f3519a2e375d954a068ec9', FALSE, NULL),
  ('2e42add77b4663b9', 'client', $s213$Bet placed: {0}g$s213$, '91a4e283dd12cb9b87870f138798c38ee0d8ea42', FALSE, NULL),
  ('2e4c76cb16213d58', 'client', $s213$Most-played ranked opponents$s213$, '7614bdc150cf8a7517747f76f15db5a13cc3aa57', TRUE, NULL),
  ('2eb11481c6e1d81c', 'client', $s213$Preview$s213$, 'f1fbb2b43dca281d0138f4fcc92543ad143ef0b1', FALSE, NULL),
  ('2eb242866aaaf376', 'client', $s213${0} players ranked$s213$, '65d4768dbb287c5c86628ac8189b2366ee6700ab', TRUE, NULL),
  ('2ecb6cb6c2115f85', 'client', $s213$<color={0}>damage taken</color> <color=#888>·</color> <color={1}>successful blocks</color>$s213$, '77e0830c9bc8e1fc14028e4bdd1aca34e982a104', FALSE, NULL),
  ('2ef8c7b3a201cae0', 'client', $s213${0} opening picks$s213$, 'a24642bb9528015ac471a91a10e938a1cbe5d461', FALSE, NULL),
  ('2f1cddec6e65ed6b', 'client', $s213$Nemesis Comparison - who beats this group most$s213$, '143e382ad9a59c9dd71fc64947fbc847787539b3', FALSE, NULL),
  ('2f4cf0864647f848', 'client', $s213$<color={0}>Orange</color>$s213$, '9d44c73676aa56f6df4f33a819ebcc1b81cd2034', FALSE, NULL),
  ('2fc6ee0492894d1d', 'client', $s213$Despawn off-screen bullets — host clears bullets that exit the camera viewport.$s213$, 'a1b943b041c4467fd8e874c41839ca774a8879e4', FALSE, NULL),
  ('2ff4e59a6ac2fe45', 'client', $s213$Sienna$s213$, '98f69d719183344b0e6cf41bda85c41161fb7494', FALSE, NULL),
  ('302286c7bebce02f', 'client', $s213$Your 2v2 lobby is starting — Ready Up in the 2v2 tab (F5)!$s213$, 'ed3eef7baa9af81e1bcad9ad0c5e50e73461bc01', FALSE, NULL),
  ('304f8c3468fc9885', 'game', $s213$DMG$s213$, 'f9f8e0e1ab62d56507241796e4d58bf672523306', FALSE, $s213$StringTableCards/STAT_DMG — Damage$s213$),
  ('30517b69c320de25', 'client', $s213$Purple Cursor$s213$, 'b9dff734194f8410236cfa4ea86d68ede85cdb6c', FALSE, NULL),
  ('306025349f761c7f', 'client', $s213$Cyan Cursor$s213$, '26744388a2aad194db923050c4fe31ade1973f3f', FALSE, NULL),
  ('3072afe4d390a26d', 'client', $s213$<color=#88FF88>{0}/{1} active</color>$s213$, '7458c742a0778b5861439c00af14c2518f2cbbcb', FALSE, NULL),
  ('3076a1f4dd6e2b2c', 'client', $s213$Loading...$s213$, 'b04ba49f848624bb97ab094a2631d2ad74913498', FALSE, NULL),
  ('3083d95d9140b745', 'client', $s213$GET READY - fire and block unlock in a moment$s213$, 'f4711dbd478dfa86591adfa28c7b9e2552cee2a3', FALSE, NULL),
  ('30a64ce0669078dc', 'client', $s213$Career records (all players)$s213$, '30cbda55fd6323b5341b0570a23ca7e627653499', FALSE, NULL),
  ('30ad5fe9e45c303f', 'client', $s213$Perfect balance. One light, one dark.$s213$, '32efb45b331be9c80dc68d23882fe31dcfb8b1f2', FALSE, NULL),
  ('30b0f82ce6dc5c3b', 'client', $s213$Ping / region display: <color=#88FF88>ON</color>$s213$, '4f795bce846c0e7c91c35b77741a9e4c2b77aaf2', FALSE, NULL),
  ('30b450ba41d7ad92', 'client', $s213$<color=#888>+pick</color>$s213$, '92738744d5b41f06fd27010c32808fb496c82066', FALSE, NULL),
  ('30f54024c484dfa7', 'client', $s213$Waiting for opponent...$s213$, 'e9ec8b04b776b9c340c2b12d163577e69c861c8f', FALSE, NULL),
  ('31223dfc8f728453', 'client', $s213$Game over - {0} wins$s213$, 'e7a9b89520887cc20a44255e10e1c0a8a9123dc2', FALSE, NULL),
  ('313626e2bedb1975', 'client', $s213$Secure connection unavailable - signed-in features are disabled this session.$s213$, '4d5a11e48db5fbe47f4e9cd221fc63eb1aa8fed9', FALSE, NULL),
  ('3142710df7c231f6', 'client', $s213$Rating History  ({0} Elo, {1} games)$s213$, 'e84f8f8af9ca7d8045a45616eeebdb971f4ba6d1', FALSE, NULL),
  ('31730649fbdd137e', 'client', $s213$Bracket Reset$s213$, '46ed5de23cef330d5db5771f01c745d52d1f1195', TRUE, NULL),
  ('317d4929f4752d06', 'client', $s213$Leave$s213$, '7e3520a9733111c30f7ea9191099a8c7d144a4d8', FALSE, NULL),
  ('319ab86ed9da45f2', 'client', $s213$Royal violet body color.$s213$, 'e13a8edd76d54551c7e4fbee3597e104900c26f7', FALSE, NULL),
  ('31af90c64e73ac01', 'client', $s213$Block CD$s213$, 'dae5a0121abb5fa0da729304b67493a1e3ea7978', FALSE, NULL),
  ('31d3f2a1c4e5d101', 'client', $s213$Everyone starts somewhere.$s213$, '2ded2d6e7d0c2c2df38250fac32026e3469bedad', FALSE, NULL),
  ('320035d28bb925e1', 'game', $s213$ABYSSAL COUNTDOWN$s213$, '386edac8a5be7c743569bb67a4f28c59f145c8ec', FALSE, $s213$StringTableCards/CARD_ABYSSAL_COUNTDOWN$s213$),
  ('321d3d0d79d4c6db', 'client', $s213$Sovereign$s213$, '65cfa78989387ca19f18d1d54af0d45dfb8fd9ee', FALSE, NULL),
  ('321e8a8231f9be1f', 'client', $s213$No Escape$s213$, '3b1fef494a099a3b85cd74865db0a55fc89dcc13', FALSE, NULL),
  ('32283fc1ea2d3ded', 'client', $s213$Avg Keystrokes per Second (in combat)$s213$, 'e130f4017b66a9d862b0106b351967a2bce36333', FALSE, NULL),
  ('3242c3ee66b19424', 'client', $s213$Coral$s213$, 'd27ca6c0dabe676d07af8742683d39325665cd59', FALSE, NULL),
  ('3242ce42885c8179', 'client', $s213$Open Report Form$s213$, '9a11776ea9b0901090a67e662d47f5e9fe990089', FALSE, NULL),
  ('3273d686feea4e85', 'client', $s213$Emerald Glow$s213$, 'd84efbd1322c23b8b2a9cc87004e3c450ea13a8c', FALSE, NULL),
  ('32e0e9f53990fa6d', 'client', $s213$All spectator seats are taken.$s213$, '6f9ee606b18a4b43b02ab28e1e3fa92283ccadbd', FALSE, NULL),
  ('32ef039ee20872b3', 'client', $s213$Menu update bail$s213$, 'ea6dfcad0bbb0197cc432580a763bdd37c55ef73', FALSE, NULL),
  ('330b2a3cb2dd7af7', 'client', $s213$<color=#FFD94D>({0} of {1} left)</color>$s213$, 'c6ace38f182cbc9fec7803e444562aadce3d2c54', FALSE, NULL),
  ('330d515b831a2877', 'client', $s213$Finish a game with the exact same 5 cards (and copies) as your opponent$s213$, '4731820fcd676f537c7e098544de7386184f7324', FALSE, NULL),
  ('33495944a2734539', 'client', $s213$<color=#888>(last approved placement stays active)</color>$s213$, '4cd18a046f43841d4fe50b03aa465f0e26bc5d92', FALSE, NULL),
  ('334e17a45a59367f', 'client', $s213$<b>{0}</b>  <color=#888>(empty)</color>$s213$, 'fd96da4284df8057fd8a9e8c7ed13ea5d22dbdc0', FALSE, NULL),
  ('3367c75f1b297a7e', 'client', $s213$Dusky pink burning into crimson. Two-color gradient.$s213$, '58f3cb1034a175e1d3f0bb7523c2449f731a9bb3', FALSE, NULL),
  ('3370f43648b2c0c3', 'client', $s213$Win a game 5-0 with Spray in your build$s213$, '6adaa65a59b1108cebdbaa309fc74aa603c266c8', FALSE, NULL),
  ('33bda1024d57e8dc', 'client', $s213$Collector$s213$, 'e3199d24849eb82131394ea88ac9c22db0dbf732', FALSE, NULL),
  ('340a5f64fddafe56', 'client', $s213$Win 25 ranked series in a row$s213$, '2a82cc109e90813127d860437aafeeb22673804e', TRUE, NULL),
  ('341bc3956a62a4c9', 'client', $s213$Hide your gold balance from everyone on the leaderboard. Toggle it on or off any time from the Other tab.$s213$, 'a14b11926312cad57e30de5af74a2d2f016fe58f', TRUE, NULL),
  ('3426d61e9ffeccc9', 'client', $s213$Green Cursor$s213$, '3ff31ec176822ae0d4a3602b4b80563f74ca6119', FALSE, NULL),
  ('34323f3c43b0f286', 'client', $s213$Abyss$s213$, '030d9312f32b78411ae6fd45521eafa5e3f16e4e', FALSE, NULL),
  ('3441b08a2609bf6c', 'client', $s213${0} Block Rate$s213$, '66eabd902fbdcda13ee03b9cb6457cb45d8178b3', FALSE, NULL),
  ('34655ad48dcbf535', 'client', $s213$Opening draws:$s213$, 'ac89cf0bce0114f396b22577093558484dbf3cb9', FALSE, NULL),
  ('3482219b5141fa38', 'client', $s213$Force exit room$s213$, 'bc90b7b7a0f89810a21b4c074f2a6a74152ea24e', FALSE, NULL),
  ('34aa06074e3d8576', 'game', $s213$Lock aiming to 8 directions (Controller)$s213$, '12f565353f4c5f3481dc7e91cba078f2af9f9a8d', FALSE, $s213$StringTableDefault/OPTION_CONTROLLER_AIM8DIR — Xbox Terminology: Controller (to take from "Xbox Wireless Controller")$s213$),
  ('34e9b914537df923', 'game', $s213$You get block back when deal damage$s213$, 'a5fa658c2c8c40f9ebfe56175f43426d1209cebd', FALSE, $s213$StringTableCards/CARD_REFRESH_DESC$s213$),
  ('3547320195741e93', 'game', $s213$HUGE$s213$, 'f972c365fd5f66835adf3e756e996923b2340fdb', FALSE, $s213$StringTableCards/CARD_HUGE$s213$),
  ('357effe73805facd', 'client', $s213$<color=#888>{0}</color>  <b>{1}</b> received <color=#C8A2FF>{2}</color>  <color=#888>(gift)</color>$s213$, '68d71224c58674c112890a7fb61d7191d171f9bc', FALSE, NULL),
  ('35a2b52c3f3448f1', 'client', $s213$Recent Tournaments$s213$, 'ef4016fa589e84e154f5828386f2d08741c1efea', FALSE, NULL),
  ('35ad337d5d3a9060', 'client', $s213$Rose$s213$, '51ad0eae3f66ecd3c72bfac9373650513d6f6603', FALSE, NULL),
  ('35da6249eafff7ec', 'client', $s213$opponent$s213$, '5fdeae599e43279dabc19756a63e0bf037b96fb2', FALSE, NULL),
  ('3633461f3484ae77', 'client', $s213$Send a bug report straight to the mod team — description, severity, and optionally your game logs. Use the Preview button to see what gets attached.$s213$, '7c6b3fea63421c1496aef5d5e0fcd1fe1105411a', FALSE, NULL),
  ('366e5c083f800ce2', 'client', $s213$Duo -$s213$, '872a0ac7105096e62dc0d9a9342fd454369241b3', FALSE, NULL),
  ('36871896766f51de', 'client', $s213$Leave your 2v2 lobby first.$s213$, '470b8d159bd13faf0cdd9899ee136ca7b5674a31', FALSE, NULL),
  ('36adad979132fdb6', 'client', $s213$Preview art isn't downloaded yet - try again in a minute.$s213$, 'e51313b1eafcf4cad2f1432dd1fbaae046aa0986', FALSE, NULL),
  ('36cecc4f534c115c', 'client', $s213$Avg Game Length (minutes)$s213$, '478919ec62b4c389cfdf173b807404a7e6536d53', FALSE, NULL),
  ('36d700539721f63f', 'client', $s213$NETWORK$s213$, '6845c6d90585c24d63de266c9a6da04090ed2dc2', FALSE, NULL),
  ('371c04da36be20b2', 'client', $s213$Searing-lime neon name with a soft glow halo. Visible to everyone; modded players also see the glow.$s213$, '6605cbf9da74dcde301ce970f5892a9c6f3697f1', FALSE, NULL),
  ('371ca2ac52232538', 'client', $s213$Play Now (skip break)$s213$, '791cf8113eee5c723d227c59846570d1b6283e08', FALSE, NULL),
  ('372406d1b8cd9ace', 'client', $s213$Win a game without ever jumping$s213$, '895f9f6d66f8bad245cd5e1e05e38d7705ea3470', FALSE, NULL),
  ('37343c87c3b2e4f5', 'client', $s213$XL Name$s213$, 'b8c7196ddeefdf59f5ef6da9406d00a866271c3a', FALSE, NULL),
  ('3739b2d530f6debd', 'client', $s213$A fiery bright red.$s213$, '04f6ac1ae02e6475938fb263bc4b7960aaa14465', FALSE, NULL),
  ('37501be191dd7d66', 'client', $s213$Aged metallic bronze with a warm gleam.$s213$, 'd738ebfc6a7ca0bfb0966d34a7228b7448258df0', FALSE, NULL),
  ('37545b9a9e7d68d5', 'client', $s213$Your {0} lobby closed.$s213$, 'a579e85fe77434bad2e5c6b95c5d6f7f3e165040', FALSE, NULL),
  ('3756e6cfebef3865', 'client', $s213$Status: <color=#DDDD66>Unset</color> - the consent prompt will appear on next launch.$s213$, '1701a52158cb5b8eee96db12e0453dc68ee4b165', TRUE, NULL),
  ('3768972fb7662437', 'client', $s213$Cursor: <color=#88CCFF>{0}</color>$s213$, '21a1cca38ce259e8e8241d9335c19da50c1c6eb3', FALSE, NULL),
  ('379b967ecad4c161', 'client', $s213$Typing: {0}  (Alt to change)$s213$, '53f026cd1d37677b0bfd74348669b189d24704a2', FALSE, NULL),
  ('37cef70e8e3c67b9', 'client', $s213$<color=#FFD94D>bets open</color>$s213$, '83e4d7479a0d6e1b9bc981e87ea959dfa0760ab0', FALSE, NULL),
  ('37d2b1b1c8b23a69', 'game', $s213$Half Orange$s213$, '70df01119382511ae43afdafff14d67d7a16f7c8', FALSE, $s213$StringTableDefault/PROMPT_HALF_ORANGE$s213$),
  ('37e257e16a522c12', 'client', $s213$Times offered$s213$, '997855b1a375e259990a47e51491808528f5295d', FALSE, NULL),
  ('37e3bb991b9d0230', 'client', $s213$Force-start unlocks at {0} signups ({1}/{2})$s213$, '3f93069046dd262e169342cd220aa004644ab861', FALSE, NULL),
  ('3828219f201c6509', 'client', $s213$Bigger Name$s213$, '28544273e2aef2357d775fe43b318ba43f33a6be', FALSE, NULL),
  ('3836763834fbb27e', 'client', $s213$Translate SCR (web portal)$s213$, 'f5b022a24101fc5adb935f8dd1359ad661f7ea15', FALSE, NULL),
  ('3859fd8d26c1bd89', 'client', $s213$FPS counter: <color=#88FF88>ON</color>$s213$, '43ba37bd870c8bada62d152083999e8646000ca0', FALSE, NULL),
  ('389ee87fa2b2226c', 'client', $s213$Region Time$s213$, 'ad0e59467721c89f6c98a699c6940779ba22d939', FALSE, NULL),
  ('38aa9603d3c8419b', 'client', $s213$Still leaving the queue — try again in a moment.$s213$, '6b9e7b491f7c6de0bf92e73dc268f45f08938d85', FALSE, NULL),
  ('38cc6e054ab4d13c', 'client', $s213$point won$s213$, '84042146ce1d2bd8175899ff7ce91ec8e89f4032', FALSE, NULL),
  ('38fee15438b6075b', 'client', $s213$Stop spectating first (Esc).$s213$, '1927c7d20bf152a7d31fb746172c9c770ee4c761', FALSE, NULL),
  ('390f22c995b624ac', 'client', $s213$Bug report sent. Thanks!$s213$, '89183a133ac470f8daf7ceb62ad266022b240fc8', FALSE, NULL),
  ('394f228c337224fb', 'client', $s213$Apex$s213$, '4c459601c34257dd40797c08e6fe2bcf0ee51d72', FALSE, NULL),
  ('3950da75a154598a', 'client', $s213$Vivid orange neon name with a soft glow halo. Visible to everyone; modded players also see the glow.$s213$, '9a39b423a562fe4943decb524e92851ad0c94a4f', FALSE, NULL),
  ('3960a6d82453549a', 'client', $s213$Hasty$s213$, '06e27642e791a899db92ec7fc9fc01900dd8d863', FALSE, NULL),
  ('3961b1463268849f', 'client', $s213$<color=#777>(hover for score graph)</color>$s213$, '730b09723eeadb523d9b0aa6dacbb50480fb8ec0', FALSE, NULL),
  ('3a1384cf68cbafa9', 'client', $s213$Deep ocean midnight — black with a hint of cold blue.$s213$, '6b2e6d11146de2269d0295012c6fd7f7061101b1', FALSE, NULL),
  ('3a3b109343e207d9', 'game', $s213$QUICK RELOAD$s213$, 'a836984427e52623bb34564ac49ad4a73e397bc4', FALSE, $s213$StringTableCards/CARD_QUICK_RELOAD$s213$),
  ('3a5238859631d3ae', 'game', $s213$COLD BULLETS$s213$, '54b8053dda16aad844f4de22eb0c06b14d0ac05c', FALSE, $s213$StringTableCards/CARD_COLD_BULLETS$s213$),
  ('3a644e4611722c81', 'client', $s213$Win with two Glass Cannons in your build$s213$, '6411369e12cb04569d5e4f57f3eab0cad4248a7f', FALSE, NULL),
  ('3a6fa8317706a4e2', 'client', $s213$Highest Single Hit$s213$, '03b42042514ededa387f0563828ce9b5825ca636', FALSE, NULL),
  ('3a70a1caae7433a3', 'client', $s213$Add an underline to your name. Stackable with other name styles.$s213$, '5bcd1bc127edaf471cf8fc9daae11e05d0ea4bac', FALSE, NULL),
  ('3a765650a0fabfe1', 'client', $s213$A sun-kissed medium skin tone.$s213$, '084e935f9f75ddb12ece11b4db28468ba8e41034', FALSE, NULL),
  ('3a86a25f6f851f48', 'client', $s213$Worst Cards$s213$, '7f1deb6a2004a9be435217ff05ec93fbbbabd6e8', FALSE, NULL),
  ('3a98b73fa17d67ba', 'client', $s213$Reach 1980 rating in ranked (1v1 or 2v2)$s213$, 'c7d01b0524369fe5b3c996b27223026f6c017607', TRUE, NULL),
  ('3af3d6023d5ff20e', 'client', $s213$Decent$s213$, 'a10292c3bb3a1332f06c324215d42310757b082c', FALSE, NULL),
  ('3b01b61b340a5223', 'client', $s213$Tattered crimson bat wings straight from the pit. Soul sold separately.$s213$, '619a16e83766383c2d21a829f80bd5d01c671c25', FALSE, NULL),
  ('3b0db3500eaa50f3', 'client', $s213${0:N0} XP$s213$, '8fa729e9316bef96c0d4cd7ce5decbcde8605aef', FALSE, NULL),
  ('3b26d48525873580', 'game', $s213$Press
[SPACE]
to join$s213$, '165c7d6cfbeef2876075725c4166be0c612ebb20', FALSE, $s213$StringTableDefault/PROMPT_SPACE_TO_JOIN$s213$),
  ('3b30a2d648e8ded6', 'client', $s213$Nemesis Comparison$s213$, '23b1ea126c6eb6126356776d0f7ed2f40985168f', FALSE, NULL),
  ('3b4605576de92799', 'client', $s213$Little Pink Buddy$s213$, '0582db7c610c15142547997e9e2b19457eef92cc', FALSE, NULL),
  ('3b5bc59fb0737c26', 'client', $s213$Opponent Hit Rate$s213$, '4f54721965f9ca16978f3a54a352efd6ded9c369', FALSE, NULL),
  ('3b78230aff37b0bf', 'game', $s213$Other player left$s213$, '3d32564b9b9cc7a7c8b6c71b28839862d67aa664', FALSE, $s213$StringTableDefault/ERROR_PLAYER_LEFT$s213$),
  ('3b79a005c95703c1', 'game', $s213$Bullets avoid the ground$s213$, '041fd1d4160a5658ae47bca05f21a00978b748da', FALSE, $s213$StringTableCards/CARD_SNEAKY_DESC$s213$),
  ('3bb6abceb257a687', 'client', $s213$<color=#FF6666>LOST</color>$s213$, 'da927b7271e6f8d59cbacce1b80066741b590663', FALSE, NULL),
  ('3bc81240cf6b8795', 'client', $s213$Player {0}$s213$, '315b1f52cdff2bd5975f933f866c66ac0a84f8ac', FALSE, NULL),
  ('3bd7fbbab2fca8f1', 'client', $s213$one glow at a time - modded players only$s213$, '35a7375e3bb813dfde5e763661731fac75a6e0d2', FALSE, NULL),
  ('3bdf1f73a2397b9a', 'game', $s213$SILENCE$s213$, '18773d628381f0718a9bdcd419e80bd93cedfaef', FALSE, $s213$StringTableCards/CARD_SILENCE$s213$),
  ('3bdfb7d09a20f37b', 'game', $s213$Sandbox$s213$, '0a771c36be05d64f376a7d57849bb33ee0c53884', FALSE, $s213$StringTableDefault/BUTTON_SANDBOX$s213$),
  ('3be1d34ee41432a2', 'client', $s213$A player in this game has spectating disabled.$s213$, '24ad5e206229cc67502993213938522f279d44a4', FALSE, NULL),
  ('3bfd7c6902ea31e2', 'client', $s213$Team {0}$s213$, '005d371b5e9cc256798c59db0a9b65adb2f7c2a6', FALSE, NULL),
  ('3c0e4e88889a9d01', 'client', $s213$Avg FPS$s213$, 'a5e9d8eff751109a07f683414c26a66ede6965fe', FALSE, NULL),
  ('3c3c5f6eac20881b', 'client', $s213$Unity / Game$s213$, '1b1d817f13affedf2bc1117a61c3b4ca949b2e62', FALSE, NULL),
  ('3c6690dcdecbb716', 'client', $s213$Average FPS$s213$, '54f2de771fcc83e1f79f766de250ec3b99058fc1', FALSE, NULL),
  ('3c754dc5b807de93', 'client', $s213$<b>2v2 Ranked</b>  <color=#888>(own Glicko, friendly fire on, BO3)</color>$s213$, '923e761583bf029d9278ca8e77fa54f0d8a2ee6e', TRUE, NULL),
  ('3c78beb9819d89e3', 'client', $s213$Shows community chat in the corner while you play. Press T to type a reply.$s213$, '9bab7bd9168724dde1e704ed3a7103e7399a2e30', FALSE, NULL),
  ('3ccac216ea7253bf', 'game', $s213$Blocking launches you forward and gives you a second automatic block upon ending the charge$s213$, '3e0066058eff1eb3572f51d4dcd7ad63e596e2fc', FALSE, $s213$StringTableCards/CARD_SHIELD_CHARGE_DESC$s213$),
  ('3cceb107a990d449', 'client', $s213$Double Nova$s213$, 'dd9ef4e5a287b8269c0300bdefaaa072c8f4148e', FALSE, NULL),
  ('3ce97f27667af200', 'client', $s213$Stats still loading - try again in a moment.$s213$, '638ae8141a1065604158abda467ced3f31d00246', FALSE, NULL),
  ('3d216c23dff44220', 'client', $s213$Win a game 5-0 with Explosive Bullet in your build$s213$, '0ef4874f3aef9de833424d6a9cef72c32e0f0291', FALSE, NULL),
  ('3d37b7ba02553145', 'client', $s213$<b>Recent Casual FFAs</b>  <color=#888>- none yet</color>$s213$, 'aed453ecdecb7d986af81013f773383e4624f25b', FALSE, NULL),
  ('3d47d9209dfb6005', 'client', $s213$Casual Rage-Quit % (lower is better)$s213$, '3f4aaff2204d591ca797f24469a6b7f559b15175', FALSE, NULL),
  ('3d78d0a5bb742b0b', 'game', $s213$[RIGHT STICK]
To move items$s213$, '1df8742b04067aaa6bb9f9630983534f7e52c794', FALSE, $s213$StringTableDefault/PROMPT_MOVE_ITEMS_CONTROLLER_PS — PS Terminology$s213$),
  ('3d7912fb4dd0438d', 'client', $s213$Casual$s213$, '1001e6a796363a864472abf12ae1e511fb8778a6', FALSE, NULL),
  ('3dd84ae90274fdaf', 'client', $s213$Enter a denial reason first.$s213$, 'a5432a4a6da4ff9019bded83cad12076454c3412', FALSE, NULL),
  ('3df52f1d70da786e', 'client', $s213$  Best: {0}W$s213$, 'de13cba6d1b25ba9af841a7cc5323f04b74b5fd7', FALSE, NULL),
  ('3df86d4f495fbeb2', 'game', $s213$GROW$s213$, '5e7dbabf8c70be19b6c8be0167a746f206f57969', FALSE, $s213$StringTableCards/CARD_GROW$s213$),
  ('3e45786ce06b8b01', 'game', $s213$THRUSTER$s213$, '0c544e0e51697d2d58d88172c038c2fa8f6fab61', FALSE, $s213$StringTableCards/CARD_THRUSTER$s213$),
  ('3e6bea2210f7f3f3', 'client', $s213$Immovable Object$s213$, '6be2477292a2c7282275bcb131607912fcdac752', FALSE, NULL),
  ('3e6d65a6be5e46d4', 'client', $s213$Glowing fire embers crackle and rise.$s213$, '4f7ba9d9a46c7284d51a3dc4e628fabb3acec15c', FALSE, NULL),
  ('3e776304a375d625', 'client', $s213$Soft pastel violet body color.$s213$, '1b7253a3591f76e461aebe6335506a201a17601e', FALSE, NULL),
  ('3e892a1a275b71e0', 'client', $s213$<color=#00FF00>Linked to Discord</color> <color=#888>(Click to show)</color>$s213$, '0052bf33f0e0a2fca12bc8925dbe2a6505d7419b', FALSE, NULL),
  ('3e904fd09a6358ea', 'client', $s213$Opponent Blocks$s213$, 'fc3c91253ead8a2d4252b720998f7ddc0dec0366', FALSE, NULL),
  ('3eacc35f9d7b18aa', 'game', $s213$Steer bullet with right stick$s213$, 'd5e636522abecde6fa4b84788a1858739a98936e', FALSE, $s213$StringTableCards/CARD_REMOTE_DESC_XBOX — Xbox Terminology: right stick$s213$),
  ('3ec608bd07df3fb0', 'client', $s213$Stan Slayer$s213$, 'ae97475ace60cadda4ce2988ba3066b956b847c9', FALSE, NULL),
  ('3f3e4849188126ca', 'client', $s213${0} of {1} players$s213$, '1b349c2c85da7aa6f6fce0e2315fe90c1db905ef', FALSE, NULL),
  ('3f5362876ef8816d', 'game', $s213$[ESC] Cancel$s213$, 'd8b97299b3dbc1213b24cc7d3a3d0a220452f6b8', FALSE, $s213$StringTableDefault/PROMPT_CANCEL_MOUSE$s213$),
  ('3f5d0dc0170cb607', 'client', $s213$Hit$s213$, 'ea490aaa629a0704301cf91e7a4910b910278662', FALSE, NULL),
  ('3f6dd33f95a50171', 'client', $s213$Report failed to send - try again in a moment.$s213$, 'cb3df1b14988aa02a85af24309f57e8594a845eb', FALSE, NULL),
  ('3f6f9cd86c97db07', 'game', $s213$Bullets stun the oponent multiple times$s213$, 'ce910a4320ada733c71205e850ff8259839ef1f8', FALSE, $s213$StringTableCards/CARD_DAZZLE_DESC$s213$),
  ('3f7d936b214a5c44', 'client', $s213$  <color={0}>Series streak: {1}L</color>$s213$, 'e6ef24456d8cc38ec788b19b6efe193194317345', FALSE, NULL),
  ('3f7dc0cdea2a6ffc', 'client', $s213$Cosmetic trails: <color=#FF9966>OFF</color>$s213$, 'd84f4bebe1e56b6360f04a4f94744ffea77a4f35', FALSE, NULL),
  ('3f8729c67d14be5f', 'client', $s213$<color=#888>No custom 1v2 lobbies — create one and invite your friends!</color>$s213$, '87b89a0c0a87f85517e612bccb1eea6d502412b6', FALSE, NULL),
  ('3f9c471fc9e220dc', 'client', $s213$The selected cosmetic is still loading.$s213$, 'e5701337d8b35a274ac925afbd1394d8ba3e2c4d', FALSE, NULL),
  ('3fa033f6c6325cd1', 'client', $s213$Still leaving the 1v2 queue — try again in a moment.$s213$, 'b1dbb6b7f6928d913e2e5e7ac7f8eab739b0a73c', FALSE, NULL),
  ('3fa2e1d1b7b13d65', 'client', $s213$<b><color=#FFD94D>PRIZES</color></b> <color=#888>(at {0} players)</color>$s213$, '1681c1ad66e8b53940d57f71ec05cd6f6cbd6f17', FALSE, NULL),
  ('3fb6e8f61142d09f', 'client', $s213$<color=#FFD94D>Custom bet</color> on <color=#FFFFFF>{0}</color>$s213$, 'b9513bd50f6f2b2febd1b0b20d5f97faec07384b', FALSE, NULL),
  ('3feec5e324dfa40d', 'client', $s213$Next tournament match vs {0} in {1}{2}$s213$, '31d4e7e7f8198ecfd215007826c85110b751108d', FALSE, NULL),
  ('400e7c9ceac83d8a', 'game', $s213$Press jump
to join$s213$, '48beb18d1e3cd72aaa6740af8058b1a545be0aa3', FALSE, $s213$StringTableDefault/PROMPT_JUMP_TO_JOIN$s213$),
  ('4012cf85c5136b08', 'game', $s213$Bullet bounce$s213$, '12b4854c1fe7f858dba582f76f0630a3db01a6cf', FALSE, $s213$StringTableCards/STAT_BULLET_BOUNCE$s213$),
  ('4012ddaf0c5772db', 'client', $s213$Blackwood$s213$, '5b07f7088b0080a88cd696619c5ce3aaef4e8bfd', FALSE, NULL),
  ('403c28519696a825', 'client', $s213$Windup main$s213$, '7bef0c61f63c0bafbdd397fcdb4fd5388041c31f', FALSE, NULL),
  ('40d13cf83efbf1df', 'client', $s213$Admins - type to search$s213$, 'd565f607bd7cf6e750de762ad7f46ad0633acf6a', FALSE, NULL),
  ('40db0a284e076c04', 'client', $s213$OOB bullet despawn$s213$, 'dcf9125b0badf4d4589de22a864504ddd27927f6', FALSE, NULL),
  ('410a15ed4e513db1', 'client', $s213$Silent Assassin$s213$, '1fd0163116cd53e22c4f164b9e475b32f563431f', FALSE, NULL),
  ('410c6b3196db19e4', 'client', $s213$  <color={0}>Game streak: {1}L</color>$s213$, '491a2892516650e2efb2b13a1bbef1914af24555', FALSE, NULL),
  ('411f4757ae88db90', 'client', $s213$Which channel for {0}?$s213$, '6c7e2155b7b8c086656478fb6bd75fa3eb755085', FALSE, NULL),
  ('41261dfa6845c60f', 'client', $s213$Glowing magenta body color.$s213$, '0c0de17323ea7ac0e7c27b2c1521765db1278f0d', FALSE, NULL),
  ('419fd13304fe9781', 'client', $s213$Bet cancelled - your gold is back.$s213$, '2b9d852b5536ed20addbc334cacbc63738c9f6ca', TRUE, NULL),
  ('41a1ec5a6ed468da', 'client', $s213$  <color={0}>Streak: {1}W</color>$s213$, '80e78a92f3f309fc0c1a71575668bfebae1fdbc0', FALSE, NULL),
  ('41d1c5a37795be68', 'client', $s213$Left your FFA lobby - you joined a competitive game$s213$, '76b21b7b1f5ea9e9b18f11b00e148fc98d09c54d', FALSE, NULL),
  ('41d390e62fe2dede', 'client', $s213$Refresh$s213$, '56e3badc4e6c5cc95e0ea5a9a878b9bd09f319d4', FALSE, NULL),
  ('41f5f5cf24a035df', 'client', $s213$Clutch$s213$, '4c26512201170dc20cac5a9bf043bfea51b6eb2b', FALSE, NULL),
  ('41fd1756bebbcf9c', 'client', $s213$* <color=#D4894A>3rd</color> - {0}g / {1} XP / 3rd Place role (loser of LB final)$s213$, 'd7c39a6a3788feb33bcaa658e81338bf0f548e22', FALSE, NULL),
  ('4234e8415df49e3c', 'client', $s213$Max {0} cards$s213$, '4a6c6c9a7c4691e7c475ce41f0a53dcc7401d0d2', FALSE, NULL),
  ('42457c2a96aab1c1', 'client', $s213$Your message was removed and you are muted for {0} minutes (auto-moderation).$s213$, '71214d59685431088efe8e890fe68b9123c092b3', FALSE, NULL),
  ('4254217c1c4f7bf9', 'client', $s213$Tournament in progress - your next match will connect automatically. Keep ROUNDS open.$s213$, 'fb10fa9913c39f956d36b21c5e77b85f398b20f2', FALSE, NULL),
  ('426d72c497d1fb76', 'client', $s213$Twins!$s213$, 'd16e8b753f78e3ec681fc4f9b2778ef39c3809cc', FALSE, NULL),
  ('42814ecc2b658aff', 'client', $s213$<color=#666>—</color>  <b>Game {0}</b>: {1} {2}-{3}$s213$, 'c914a0dd6b7a82aa21bbc158bcd04239601f6345', FALSE, NULL),
  ('42836d81ac36a09a', 'game', $s213$SCAVENGER$s213$, 'cf6a5c76ea7c05b4a42a43c86b8d66a0c51435d2', FALSE, $s213$StringTableCards/CARD_SCAVENGER$s213$),
  ('429a5c67e4ea3a05', 'client', $s213$Mute a player in chat - find the player$s213$, '825304eeee2991262ee1dbad0d762e52aa6014e1', FALSE, NULL),
  ('42b58b0e9f96b45e', 'client', $s213$Buying {0}...$s213$, '7db325b3e21b1a5687cdeadba0a48cc535576391', FALSE, NULL),
  ('432fb528f53d3c97', 'game', $s213$POISON$s213$, 'b8eaf34112191ee93d21c9795faa3ea2e2095694', FALSE, $s213$StringTableCards/CARD_POISON$s213$),
  ('4356e1f9e0e4cc96', 'client', $s213$Rise from the Ashes$s213$, '97800f5d41e76e932cfd498fd7502f99f1e80a04', FALSE, NULL),
  ('43a8dbc807b7024c', 'client', $s213$Revoke consent$s213$, '13255b407052cfd4a359f6e8e175137b48388a31', TRUE, NULL),
  ('43b2f69fc34f5d0d', 'client', $s213$Flame Crest$s213$, 'cdc31cb72e817957694d9471984bd835a93dafc1', FALSE, NULL),
  ('440f04d7b67d73ef', 'client', $s213$Quick chat — click a phrase (or keys 1-0). Y/Esc closes.$s213$, '450961a87aca9d045af79ef3fa934b85d2af5c86', FALSE, NULL),
  ('44182e48830d89b0', 'client', $s213$Create Private 2v2 Lobby$s213$, '0ad69726899bc7c2f873cdd276a1e2a2b22111d8', FALSE, NULL),
  ('44296b8aa369d553', 'client', $s213$Moustache$s213$, '3d934064bc875a99085c8782d09dde442c97d696', FALSE, NULL),
  ('444f6214f679a435', 'client', $s213$Achievements$s213$, 'a6634f24b2db61aafb90e6954e00e3a9ba699d80', FALSE, NULL),
  ('44817929693030e4', 'client', $s213$Win with two or more Supernovas$s213$, '6309e3b549f2e05f7a832b5a3ceee711e45eb469', FALSE, NULL),
  ('44958e96b42c92ac', 'client', $s213$Bullets$s213$, '7509c5747e5db3dfa3373afc42eca9f5b27a8599', FALSE, NULL),
  ('44a291e8d72f6864', 'client', $s213$Untouchable$s213$, '32363366360c0121e17ca2a47b773d8e15bd3bc0', FALSE, NULL),
  ('44a663da8c3a7fdd', 'client', $s213$Sign up to unlock force-start$s213$, '393bd9e94e9108ea7fcbcb67d93d3269709ea07b', FALSE, NULL),
  ('44a9ae7c639fd2e4', 'client', $s213$<color=#777>rounds on the left - each step is one point scored</color>$s213$, '0b847feca26a4748195b25eedff430653aebabb0', FALSE, NULL),
  ('44bd426b0542d87a', 'client', $s213$Reverse Series...$s213$, '583d156c59fe2e53385c84b50e54a60e4aa6f593', FALSE, NULL),
  ('4500828df2e65566', 'game', $s213$English$s213$, '649df08a448ee3fa90f3746baaf6b0907df42c91', FALSE, $s213$StringTableDefault/LANG_ENGLISH$s213$),
  ('4521b53dc97ef02b', 'client', $s213$Chat [{0}]  —  Enter to send, Esc to cancel, Alt switches channel$s213$, '671adde235e0b4351df3c5994e6c51b671dd22fa', FALSE, NULL),
  ('45482b9b7668a66b', 'client', $s213$Couldn't record the match$s213$, 'fdf89f537d6eed53d362bb783ee9bcba1a2bc496', FALSE, NULL),
  ('455b205f737f7f07', 'client', $s213$Tournaments$s213$, 'fee20df1963ec9531d0a42884334083687be1d13', FALSE, NULL),
  ('4567acb803377649', 'client', $s213$Loading the reviewed cosmetic...$s213$, '835607ccc7a2843df2fea8d0f4b416f9c91b1195', FALSE, NULL),
  ('456d85ea1d8bfabd', 'client', $s213$   -   {0}-CARD DRAW$s213$, '10c1aa938eb56ce3e9eda95a5e8dc74f082440e5', FALSE, NULL),
  ('45cc733ef5540b01', 'client', $s213$<b>FFA Leaderboard</b>  <color=#888>- no ranked FFAs yet</color>$s213$, 'a33b19409eb5e945af5ac6000a7f968edb0f0d95', TRUE, NULL),
  ('45e188ed96a19905', 'client', $s213$Kick$s213$, '8c5ec4edfe9a6f4f388a0204b0e6d5ccfee6ff5b', FALSE, NULL),
  ('45faa04dd395d9ae', 'client', $s213$Opp:$s213$, '1e9ed67a9b31975b8a43893fcd351af7231d2512', FALSE, NULL),
  ('4602ccfcb6641ef3', 'client', $s213$Total: {0} ({1}W / {2}L)  <color=#FFD94D>Gold: {3}</color>$s213$, '21d10582916e120d4c8320df023f92494b61642c', TRUE, NULL),
  ('464d409e47ac187e', 'client', $s213$Update failed — the download didn't finish. Try again.$s213$, '0895fbf0cb0205381394acf72281d4c28b6f17d9', FALSE, NULL),
  ('4686f7188c6efe31', 'client', $s213$Couldn't confirm FFA leave — the server will clear you shortly.$s213$, '1cac419dc5eb69061e2b951c738307f031b99f0a', FALSE, NULL),
  ('468bc45e2ba8d698', 'game', $s213$Blocking spawns a ring of slowing projectiles$s213$, 'a0195c0cf38236ac5eb965e5e8ca13816c32e316', FALSE, $s213$StringTableCards/CARD_EMP_DESC$s213$),
  ('468d3f428f3909bf', 'game', $s213$Press enter to chat
Type names of the cards to spawn them
Shoot the cards to pick them$s213$, '7dc68189b96ecec024485a3328c4a307f5f160c9', FALSE, $s213$StringTableDefault/PROMPT_SANDBOX_MOUSE$s213$),
  ('469f96b6fdf6a7e3', 'client', $s213$Bullet Hell$s213$, 'c2d5519c0f2e7db2a59a35a4ac44acbc2a6b42f6', FALSE, NULL),
  ('46fe5bdea432ddc2', 'client', $s213$Revoke which translation role?$s213$, 'd609539d8e0863475418b15564c55edfe9667fb6', TRUE, NULL),
  ('472e0596956b3ea1', 'client', $s213$Couldn't confirm the {0} lobby leave — retrying in the background.$s213$, '06222814ef4a26870f746258d2275f2d7016dda0', FALSE, NULL),
  ('473227dfcf7069a9', 'client', $s213$Chromatic aberration: <color=#88FF88>ON</color>$s213$, 'b59d2949c1166ebc227ebbd6c96c355c303cbc9f', FALSE, NULL),
  ('476093e331464f11', 'client', $s213$Submit$s213$, '2dacf65959849884a011f36f76a04eebea94c5ea', FALSE, NULL),
  ('476d5eee623bc2a9', 'client', $s213$Teams will rebalance next match!$s213$, '60598b80b4712d9934525f8ac9e220b8cf27dbcc', FALSE, NULL),
  ('47b4415f4d6a7d63', 'client', $s213$Effects$s213$, '8f25a859269ca51039632dd6bba28fb061cfb8d4', FALSE, NULL),
  ('47f317fc0868a03f', 'client', $s213$Finish or leave your current game before joining the FFA queue.$s213$, '339670b58cfcb9b061922b19ad0c9fe1970a63c2', FALSE, NULL),
  ('4801bc4d1ad5528f', 'client', $s213$Confirm — really delete$s213$, 'cfd434e1ceba2df1cecded3fef55e8783672c543', TRUE, NULL),
  ('4829edfbd8946d0c', 'client', $s213$Total XP$s213$, 'de22faa36e05c70dc66d022852845a823e484fe8', FALSE, NULL),
  ('4831593966605443', 'client', $s213$Admins...$s213$, '993ae96a5bc8a29e1ad8a10810f1b6cf60e712eb', FALSE, NULL),
  ('4833ee202e07d685', 'client', $s213$<color=#88FF88>In a custom 1v2 lobby</color> <color=#888>— manage it in the panel below.</color>$s213$, '4588e08cd640a17c66b6a8513687db9e110b4869', FALSE, NULL),
  ('486870fd71c49d67', 'client', $s213$<color=#FFD94D>Upcoming Match Bets</color>$s213$, 'd53c35475cec1d741f62a4a6cad340d2a491423e', FALSE, NULL),
  ('48aac4d36fe4eab8', 'client', $s213$Showing: {0}$s213$, 'bc2c02ad63ef5932a9bfb803d1d3de1db0bc9cd4', FALSE, NULL),
  ('48ab37a3b4f0c7b3', 'client', $s213$Which language for {0}?$s213$, '8f6f68e46a3e45f48d74027000b9b28312ed6fe1', FALSE, NULL),
  ('48c9d127e51bbf72', 'client', $s213$Your {0} lobby seat expired — join or create a new one.$s213$, 'bcece8c6a3f5cadce3449b5db2ac668778dcaf13', FALSE, NULL),
  ('48fd57c668c63dc7', 'client', $s213$<color={0}>Leave: {1}/{2} ({3}%)</color>$s213$, '68e41b4c2415fc16a601f9284cc62d1a0d1e1253', FALSE, NULL),
  ('493df93f52bd5e55', 'client', $s213$<color=#666>(click to copy)</color>$s213$, '185f137dbfc6210724da22e7a90deda846e8ce92', FALSE, NULL),
  ('49418f9ec59f58ec', 'client', $s213$SPECTATING$s213$, 'a93910c41c841b78441c8c7061a07ca8a698dc3f', FALSE, NULL),
  ('496970286b950065', 'client', $s213$FFA DPS$s213$, '757933a26349a81ff9017db9c2dc2688f5cfbe68', FALSE, NULL),
  ('498e2111639dc482', 'client', $s213$Win a 2v2 game 5-0$s213$, '52c738eb71779ebebb572ab7101e3ba0c99a061f', FALSE, NULL),
  ('49923e671981b95e', 'client', $s213$Pristine Perfection$s213$, '960ab5ab0edb01f24063eaa58f2593eab46db25c', FALSE, NULL),
  ('49c8adce945e10af', 'client', $s213$SID'S COMPETITIVE ROUNDS$s213$, 'd9baef5110422c5e7f32144bde9656cc19bc8806', FALSE, NULL),
  ('49e1dea08aba7261', 'client', $s213$<b><color=#FFD94D>HOW IT WORKS (Async)</color></b>
  1. Sign up any time during the 7-day signup window (Discord must be linked)
  2. On lock, bracket is built and first-round matches activate
  3. Coordinate with your opponent via <b>/dm-opponent</b> on Discord
  4. Both of you enable Ranked, join any private lobby in ROUNDS, play the BO3
  5. <b>Mod records the result automatically</b> - no manual report, no room code needed
  6. Winner advances in bracket; loser drops to LB (or is eliminated)

<b><color=#FFD94D>AUTO-RECORDING REQUIREMENTS</color></b>
  * Both players must have <b>Ranked</b> toggled ON in-game when playing
  * Any private ROUNDS lobby works - tournament doesn't force a specific room
  * Once you hit 2 BO3 wins, the mod advances the bracket and notifies you

<b><color=#FFD94D>SCHEDULING</color></b>
  * No fixed start time - self-paced, <b>7 days per match</b>
  * Total tournament runs up to 6-9 weeks depending on how fast matches happen
  * Miss the deadline and you forfeit that match (tracked in penalty %)

<b><color=#FFD94D>FORMAT</color></b>
  * <b>Double-elim</b> BO3 - lose once, you drop to losers bracket
  * Grand Final: WB champ vs LB champ (bracket reset if LB wins first BO3)
  * All matches count toward ranked Elo

<b><color=#FFD94D>PENALTY %</color></b>
  * Grows when you sign up but forfeit a match by missing the 7-day deadline$s213$, '99ad986f0701d66b8842024bfda93a105359e48d', TRUE, NULL),
  ('4a7be244b1f524a1', 'client', $s213$Couldn't confirm queue leave — the server will clear you shortly.$s213$, 'c3026e4015a9f4d6b0f6241292787249bc291cf9', FALSE, NULL),
  ('4adb844bfc227e4e', 'client', $s213$Couldn't record the match — retrying in the background$s213$, '7a62d6a8bd7e6b2ef66132ff1e4c1d57c8c65794', FALSE, NULL),
  ('4af3c9568c8e3ff0', 'client', $s213$Admin action$s213$, '53acd6e7e3c30fdf792e093fb553fcc69a49eea6', FALSE, NULL),
  ('4b1650a5cc411411', 'game', $s213$DEFENDER$s213$, '885fdc9aa0ab665c2dcc9e35a8c3078398b9ae73', FALSE, $s213$StringTableCards/CARD_DEFENDER$s213$),
  ('4b1ee0227f1bf12a', 'client', $s213$Be right back$s213$, '3f16022a617b9c281f8300015f5cf25016949f01', FALSE, NULL),
  ('4b213ee4dd01cc14', 'game', $s213$Life steal$s213$, '417f106adb9eb8a88f7f754dff056d4ad92f62fa', FALSE, $s213$StringTableCards/STAT_LIFE_STEAL$s213$),
  ('4b40a37c0f75e082', 'client', $s213$<b><color={0}>{1}</color></b>  <color=#888>(unranked - loading...)</color>$s213$, '5d0cfe13e0112ed053a0d334953c1a598ef0f059', TRUE, NULL),
  ('4b4e998d002aa314', 'game', $s213$Enter card name$s213$, 'dcfdf8113edb226febe26c5bbd29e7ffce9b6075', FALSE, $s213$StringTableDefault/PROMPT_ENTER_CARD_NAME$s213$),
  ('4b7b3bb3843c5b2a', 'client', $s213$Achievement comparison$s213$, '079b57c26436586e5179bd49537d3492f766534d', FALSE, NULL),
  ('4b91176bba6fd963', 'client', $s213$Could not cancel: {0}$s213$, '80718cedfe6e4c0f70b119b6e03dc51a4650447a', FALSE, NULL),
  ('4bb91d4741ebaf17', 'client', $s213$Pink Cursor$s213$, 'b12540f76b8ae0ed79395737854d6d05a71804a7', FALSE, NULL),
  ('4bdf43c6198c4944', 'client', $s213$Held by the top 3 on the ranked leaderboard$s213$, '9de786a3c943e4fc74c3ab105df60d4a8cd2b8f9', TRUE, NULL),
  ('4be253b8080d3f06', 'client', $s213$Picks$s213$, 'f5f61efb04cc0bde68137d2124c1656a262a2038', FALSE, NULL),
  ('4c2271c1d508dbbb', 'client', $s213$Bracket$s213$, 'e42a1e70b4003a66462fd8b1b6f1d551425eedd6', FALSE, NULL),
  ('4c3422795023e95d', 'client', $s213$Stopped searching$s213$, 'db825a8ff1b5076df3201c8038e1efe1606429ba', FALSE, NULL),
  ('4c68914b7aabfcfa', 'client', $s213$<b>{0} Performance patches</b>  {1}$s213$, 'bf002f47ea0d0549603ae705e59cb5f1a515bf3e', FALSE, NULL),
  ('4c7655180a482cad', 'game', $s213$V-SYNC$s213$, '0babceedb41c6bc469bc9a859dcab6b82a8411e3', FALSE, $s213$StringTableDefault/OPTION_VSYNC$s213$),
  ('4cd4d837219a7f6f', 'client', $s213$<color=#888>Loading earners...</color>$s213$, '0de89b2afc192a9c7edfa75e67da4482ff3c9fc7', FALSE, NULL),
  ('4cd5305755696722', 'client', $s213$Artist$s213$, '6c3f3d3203630ce74ffd9609307833fc4f052892', FALSE, NULL),
  ('4d0ae42a5167a39c', 'client', $s213$Floating Name$s213$, '455a8cfec6c15aa9f024bd2cb4d2dd92bafc3c6d', FALSE, NULL),
  ('4d2f0d8391e9a531', 'client', $s213$1v2 — Solo vs Duo$s213$, '7fc0f9fd178d5e0ff6bc432e6e4e01c715a6371f', FALSE, NULL),
  ('4d4720dda0a927bb', 'client', $s213$COMPLETED$s213$, '6dc2daaed756f492c0b47af2ae68dfc26d827fab', FALSE, NULL),
  ('4d580a51b66a9839', 'client', $s213$Silly Drill$s213$, 'b5c2df0ee1dc21486cd644213de53f3f076f6371', FALSE, NULL),
  ('4d87829d1cd53cb7', 'client', $s213$Win with four copies of the same card$s213$, '2c1c7702a7580ec61b8151a66d8ca50c49965c34', FALSE, NULL),
  ('4d8c0cc6fc7fefd5', 'client', $s213$Opponent's picks$s213$, '783dedc30ac7f71e7f9b2ebba24f435e2f0ea30c', FALSE, NULL),
  ('4dd589a0e595aa79', 'client', $s213$Reborn after defeat$s213$, 'c4097eedd44962a5de126d3bf379be9849404efc', FALSE, NULL),
  ('4de0cd53889e1dbf', 'client', $s213$Tag Team Sweep$s213$, '4e4cd33a2506596163f467a032d1305efd4c07bd', FALSE, NULL),
  ('4de9de6e1f656ebe', 'client', $s213$Sparks$s213$, '45bfc012fbf82490776101b9c6b63887c8a0fb1d', FALSE, NULL),
  ('4e05f277a8a868e9', 'game', $s213$Shockwave$s213$, 'f9cf560f7be04bf83ae4c79a06b27119a6f9fb24', FALSE, $s213$StringTableCards/CARD_SHOCKWAVE$s213$),
  ('4e17aa7c25efb66c', 'client', $s213$Fragile Perfection$s213$, '93c0c7428061d19b5ae907ba7820e19445811f4b', FALSE, NULL),
  ('4e1a7e002aa898fb', 'client', $s213$Select players (left) to chart {0}.$s213$, '653473b68ffd7d51aa82c742fe125934177dd762', FALSE, NULL),
  ('4e3adbbd8a6ed18f', 'client', $s213$BepInEx (current)$s213$, 'd8b47f574662c9e2de4a022fe7f25db087c9b9b9', FALSE, NULL),
  ('4e8fc7c0e6288df8', 'client', $s213$Void Ripple$s213$, 'ec5f447f3fa0edd8c92f7101ef7f729f6466b96d', FALSE, NULL),
  ('4e9df1482c91e705', 'client', $s213$<color=#DDDDDD>{0}</color> <color=#777>-</color> {1} players <color=#777>-</color> <color=#8FA3B8>{2}</color> <color=#777>-</color> {3}$s213$, '77768f2cddef5881738c018e0d4d539bbfb2df96', FALSE, NULL),
  ('4ec92382f6f9cb9d', 'client', $s213$0 in queue$s213$, '9791b16ad92597fac04aa01430afe801ee5efe2a', FALSE, NULL),
  ('4f2532a4d52ec616', 'client', $s213$This account isn't registered as an artist.$s213$, '8d3f894fef9a0d6167b3bc9a6cbb1e4536c3656b', FALSE, NULL),
  ('4f840542dec022c0', 'client', $s213$<color=#FF6666>NOT OPENED - set stock to start selling!</color>$s213$, '8aa97ef1388ab04f260985fe6a7f5c5f08b4a5a4', FALSE, NULL),
  ('4f87758656255ee4', 'client', $s213$Monochrome$s213$, '1dda992b70d55b62ecc5e22ba264afe7a9f07d02', FALSE, NULL),
  ('4fab04e5db11f52a', 'client', $s213$Allow spectators: <color=#88FF88>ON</color>$s213$, '9be86673cda0c0007bf2d4f313d7c5a5c805c626', FALSE, NULL),
  ('503299a3e558e34f', 'client', $s213$<color=#7788AA><i>search players...</i></color>$s213$, '87f809301f9f7b489483cdf2291ee0be17560216', FALSE, NULL),
  ('504938ea1a6af0af', 'client', $s213$Update failed — that release has no download attached. Update manually from GitHub.$s213$, '80045841ca2a8c433297c3f4ba3fa635e6a807db', FALSE, NULL),
  ('505d826bac112c1d', 'client', $s213$Red Name$s213$, '126a8e3bc4cc743f66d97a23baa4fbd94bca9cd1', FALSE, NULL),
  ('5075e7603c2f7d95', 'client', $s213$<b><color=#88AAFF>Duo Leaderboard</color></b>  <color=#888>(unranked)</color>$s213$, 'ba8d07355c743611822b60ec2429d74cb614e614', TRUE, NULL),
  ('50ac155d36ece430', 'client', $s213$Tattered Cape$s213$, '5f6aa78e382c01b370e8b343a9c1b5a2b5fa6705', FALSE, NULL),
  ('50ddb14a1a0ebbbe', 'game', $s213$Match found$s213$, '14846ed7d50293587e98be171845ca9900f7e207', FALSE, $s213$StringTableDefault/PROMPT_MATCHFOUND$s213$),
  ('5102a46fc36366ae', 'client', $s213$Bouncer$s213$, '4e36289d0951a7bd412ec33c4053fe33bef6b588', FALSE, NULL),
  ('510bbb2d5c28e2ed', 'client', $s213$<color=#00FF00><b>WON</b></color> {0}-{1}$s213$, '23e6796a6dd6767a12be4b513543ebf8e5e4abb7', FALSE, NULL),
  ('511bd6cc33ca9a98', 'client', $s213$Input overlay (bottom-left): shows W, A, S, D, Space and both mouse buttons. Lights up red when pressed. Useful for streams or spotting missed inputs.$s213$, '1b5500a5682ab59e4d75826a732e0c2b221fef3b', FALSE, NULL),
  ('513a6e57e933a9fa', 'client', $s213$Highest Health$s213$, '0bfbda6cb5bd27c04cfdb09fa9a2df07105f83f7', FALSE, NULL),
  ('51820a6184b82f3f', 'client', $s213$Spectators ({0})$s213$, 'f1c9ae81fc7e2bbd19ab01bae113f28fd40d5456', FALSE, NULL),
  ('519e272ed084c741', 'client', $s213$Ranked$s213$, '092579473a08bd70d7ac3465596a270bce98cb2a', TRUE, NULL),
  ('51a65b45048ed861', 'game', $s213$CHILLING PRESENCE$s213$, '69f0c1d7433aeaaed0da797fa67ff46cf4c1f997', FALSE, $s213$StringTableCards/CARD_CHILLING_PRESENCE$s213$),
  ('51a6d0e98b96103e', 'client', $s213$Start Game ({0}/{1})$s213$, '95434373b1524d272dcd9345ec874d2a8b03b516', FALSE, NULL),
  ('51afe625aeb8a965', 'client', $s213$Premium: molten gold walls that glint to white-gold, over a deep bronze vault$s213$, '22f4f84ddb194e43610ebb98e62014a7317abfe9', TRUE, NULL),
  ('51b860af248239b9', 'client', $s213$Pale mint blocks on a cool dim backdrop.$s213$, '33965e30fc529ff12defc4f985185e526707cd07', FALSE, NULL),
  ('51bc6ddfd6c32b36', 'client', $s213$ (pays {0}g)$s213$, '6f3c170bd545215b8832f0798382db9a53474f4b', FALSE, NULL),
  ('5215a7389616213e', 'client', $s213$Locks the map to ROUNDS' Soviet palette (deep red).$s213$, '2dc9a74a3d4c4d4552153339ca5aaf59af7a8a61', FALSE, NULL),
  ('5215fcf61178e3e3', 'client', $s213$<b>Recent 1v2 Games</b>  <color=#888>- none yet</color>$s213$, '54e706d52a91eaf6738072af7af1ea59473bdfc0', FALSE, NULL),
  ('52237a4b42e100b7', 'game', $s213$Music volume$s213$, '0d49fceb8d4a4c2a1998a342c9e3bbca56602384', FALSE, $s213$StringTableDefault/OPTION_VOLUME_MUSIC — 2023-10-17: Fixed a typo in "Music" ("Mucis")$s213$),
  ('5228b8e02c86210c', 'client', $s213$  <color=#888>(page {0}/{1}, {2} total)</color>$s213$, '53b74b7f2271d94b654a77d49d0bb23fa6af9042', FALSE, NULL),
  ('5286435b58b15502', 'client', $s213$Cool grey body color.$s213$, 'd47ddde92346ea04ff6d780400e1c300eb81639e', FALSE, NULL),
  ('52d71cf9cc89962c', 'game', $s213$Language$s213$, '89b86ab0e66f527166d98df92ddbcf5416ed58f6', FALSE, $s213$StringTableDefault/OPTION_LANGUAGE$s213$),
  ('531d54a0f2f7c81f', 'client', $s213$Block debug overlay: <color=#FF9966>OFF</color>$s213$, 'f33f04e2451d11d0224bbe724edef933399e7826', FALSE, NULL),
  ('53236f8f806d6a56', 'client', $s213$Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.$s213$, '9b4279e882d9e4eb0133e566ccdea4fd7247638b', FALSE, NULL),
  ('5346ec349129ccdd', 'client', $s213$Animated cosmetics: prismatic/chrome body colors, prism trail, player effects, map-skin shimmer, animated faces. Off = everything freezes on a static frame.$s213$, '5529efca285a7da8d70b2fe896a6b3c9168f9870', FALSE, NULL),
  ('5390ad8a16180923', 'game', $s213$Roomcode: {ROOMCODE}$s213$, 'ab2966c3678546323d365369fae08e7a4eda6ce8', FALSE, $s213$StringTableDefault/PROMPT_ROOMCODE$s213$),
  ('53c66fd08ebd68b6', 'client', $s213$Ranked build types$s213$, '9467ad59cd362c01604269f825c554e56b6b103e', TRUE, NULL),
  ('53c81b79be7734cc', 'client', $s213$<color=#88FF88>Sent! Thank you. Filed as <b>#{0}</b>.</color>$s213$, '72eb49bc0c8d4b39c1a19186f6230c1c6173dd38', FALSE, NULL),
  ('53dc540a825baa09', 'client', $s213$Flawless$s213$, '22b9ee43aaa645b2356c82a81cf4f411e51328e8', FALSE, NULL),
  ('53e1c75349c012da', 'client', $s213$One solo player faces a duo in a best-of-3 series.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- This is a consent queue with no Elo band and no ready-up.
- The server assigns one solo and two duo players.
- Solo Extra Initial Pick is optional.
  If anyone enables it, the solo draws 2 cards on the
  opening pick.

<color=#FFD94D><b>SCORING</b></color>

- The first side to win 2 games wins the series.
- 1v2 is an UNRANKED beta. No rating is applied yet.
- Games are recorded and will count when ranked play launches.

<color=#FFD94D><b>REWARDS</b></color>

- Each game gives 500 XP.
  A game win gets x1.5, for 750 XP.
- A series win gives each winner 40 Gold.
  A series loss gives each loser 20 Gold.
- Game XP converts to Gold at 100 XP = 1 Gold.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

- The tab has separate Solo and Duo boards.
- You appear only on boards for roles you have played.
<color=#7FD4FF>Rank</color> - Activity order: wins, then WR, then games.
<color=#7FD4FF>Player</color> - The player's display name.
<color=#7FD4FF>W-L</color> - Games won and lost in that role only.
<color=#7FD4FF>WR</color> - Win rate for games in that role.
- These are activity boards. They are not sorted by Gold.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving mid-game is recorded.$s213$, 'f6deacd33a1819ebbb127e5a239bc44ccd4c7302', TRUE, NULL),
  ('53eb03940dd9126a', 'client', $s213$Approved Update Queue...$s213$, 'a07ed85fc63acdd4554a17f354ed0ddefe01bb6b', FALSE, NULL),
  ('53fc58107ad3018e', 'client', $s213$More ranked than not.$s213$, '6938f3389402f793e6adddb682e3586aec57a2e4', TRUE, NULL),
  ('5420efacc2031eb3', 'client', $s213$Start unlocks in {0}s (settings changed)$s213$, 'e225fc35916c02082cbc4b761f753aef8048e0fa', FALSE, NULL),
  ('5431d62eb89eb032', 'client', $s213$Lifts your nametag a fraction above its baseline so it appears to hover.$s213$, '647b0df3eb0dc7b333f9063728d3b2e3785878de', FALSE, NULL),
  ('545cded3a4c7556c', 'client', $s213$recently online$s213$, '9480ffe6b949b61541654d37159b5729522647c9', FALSE, NULL),
  ('54860c61d03a34f6', 'client', $s213$Search players$s213$, 'e3799504761fb5e522c834bcab8d7cdafae515bf', FALSE, NULL),
  ('54c5a179c0572f49', 'client', $s213$<color=#777><i>hover the panel and scroll for more</i></color>$s213$, 'b838ddc26b3bb55f1248d3403aa57b22d0d8f271', FALSE, NULL),
  ('54cce0f779303fff', 'client', $s213$Leave your current game first.$s213$, '62820e3a31c40e97fa8a7a30023f6f103d6ec56a', FALSE, NULL),
  ('54eee8c1199323da', 'client', $s213$RLFP ping available in {0}m {1}s (1 per hour).$s213$, 'f55cf47ab80a74cedc526b6091d08157c647d6d3', FALSE, NULL),
  ('54f6a34eb41233e6', 'client', $s213${0} Hit Rate$s213$, 'fbea93183790813787fd128dedfee3c20e02181f', FALSE, NULL),
  ('54fcd59ad6dea5f5', 'game', $s213$Press enter key to join with roomcode$s213$, 'be54c03cac3d35478d0776ba7fd7440b95bb5937', FALSE, $s213$StringTableDefault/PROMPT_JOINROOM_ENTER$s213$),
  ('554216dc58af09c4', 'client', $s213$Each letter of your name in a different color of the rainbow.$s213$, '9b0acd4461ab7da7585950db970135db010f6aa8', FALSE, NULL),
  ('5567eee60b51362d', 'client', $s213$Instinct$s213$, '8b466a9d6a804f6268778e511de8a9906c9260cf', FALSE, NULL),
  ('558fc3496ae9d9c9', 'client', $s213$Day/Month/Year$s213$, '689cd25e4f221a18734b96f3bf83f166c4a7115a', FALSE, NULL),
  ('5593dbe5ca8039d3', 'client', $s213$Unstoppable$s213$, '39e6741f25d3f45d31f8790ca0b6174dca928597', FALSE, NULL),
  ('55a19058450cfc82', 'client', $s213$<b><color=#999999>Start (saving...)</color></b>$s213$, 'dd42a7196864aca35fa2ef4811eb1c4074641ca8', FALSE, NULL),
  ('55d6340624531595', 'client', $s213$Uncommon$s213$, '630e0b25835dd27620dc4ef0c6b4d0300696b62f', FALSE, NULL),
  ('55f3321c97728ac1', 'client', $s213$<b>Recent 1v2 Games</b>$s213$, '57c6442982f612283de11e71c840a251ded99dc0', FALSE, NULL),
  ('560a32b0d16aa441', 'client', $s213${0} / {1} unlocked$s213$, 'f44e9fd85b7ae7b1813d58f357d0ec3c223627aa', FALSE, NULL),
  ('563f328fb4d4aa1d', 'client', $s213${0} half-point events$s213$, '60af1d144ac434a965bf13bb977aa7aadb4bb8d3', FALSE, NULL),
  ('567890efd6eb4e17', 'client', $s213$Sleek black body color.$s213$, 'b0476d817e62b78a6d6b13910299b1a6c90d3d83', FALSE, NULL),
  ('568bed8b059b93ef', 'client', $s213$no card data$s213$, '3865e6152a8c60511725d508e1493e63c71e47c3', FALSE, NULL),
  ('569d888f5c7acfb1', 'game', $s213$Blocking reloads your weapon
$s213$, '86c53fb59b278b65b63de1b597b229c080cc44d3', FALSE, $s213$StringTableCards/CARD_TACTICAL_RELOAD_DESC$s213$),
  ('56c1bc4c9f3d0585', 'client', $s213$Bye!$s213$, '749de5cc8ef9ff0fb0869179ea66555c2dff2fbf', FALSE, NULL),
  ('56cb480415159ed5', 'client', $s213$You can't kick yourself.$s213$, '721206543a1129dbde968828564469c8dc9920bd', FALSE, NULL),
  ('56eeae7c606f171b', 'client', $s213$Cards: <color=#FFCC66>chips</color>$s213$, '72e5a30e619dd5488bc8f47b9a2b6c904e40e38e', FALSE, NULL),
  ('56f4b006168b90b0', 'client', $s213$Series {0}  vs {1}  (in progress)$s213$, '31b7561e9ca64f61bfd860c5d4af7ecf229dabfe', FALSE, NULL),
  ('56fa9eaf1e7fd735', 'game', $s213$CAREFUL PLANNING$s213$, 'cc11eaa53476ff46ab4c677bd5023765dc9263a9', FALSE, $s213$StringTableCards/CARD_CAREFUL_PLANNING$s213$),
  ('572dd774b6ee6a62', 'client', $s213$Orange-to-yellow gradient that sears the arena.$s213$, '3997c754c441e48d35184d2d9db0a028a6c9346d', FALSE, NULL),
  ('57458ad5ed088b18', 'client', $s213$Force Start$s213$, '2b653211244b09239b9e1d00d3de5a10b288a0dd', FALSE, NULL),
  ('5783daaa33663872', 'client', $s213$Good game!$s213$, 'f08bdc8d0c0c317f3d084df0ff652848b30ae3d7', FALSE, NULL),
  ('5792fedf4221d0da', 'client', $s213$Cannot spectate: {0}$s213$, '56b8eff201e82ce113ba38a7ebf7f2d87849f328', FALSE, NULL),
  ('57ca58671cb6dc1c', 'client', $s213$Ranked DPS$s213$, '70461d2426e78a0ca406ba56d2790b61569d7f54', TRUE, NULL),
  ('57da6b22ccc01814', 'client', $s213$<color=#99AAEE>Achievements:</color>$s213$, '3be3caf7dc4aae34dc52ce4e084379b3f38f3e0c', FALSE, NULL),
  ('57f1bdcef79892ac', 'client', $s213$Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.$s213$, '91e791312991c216c7bdca715ee22fa1062f21d0', FALSE, NULL),
  ('57f539baa20955f8', 'client', $s213$A bold red mouse cursor.$s213$, '28329a6c2291ab34539160eafed7e0a58654883f', FALSE, NULL),
  ('580d15e9663872e6', 'client', $s213${0} keys/s$s213$, 'a2df9cb008e9644c6620b3985803262c7bd369d3', FALSE, NULL),
  ('582670124134c55f', 'client', $s213$Equip$s213$, 'd764961a0190b30c20bb741496306ead9a1ea719', FALSE, NULL),
  ('583edabb1e09ee16', 'client', $s213$A muted, earthy olive green.$s213$, '9f3a21630b49c6794c32656c33e432d3bf84e405', FALSE, NULL),
  ('5849f232f351cc51', 'client', $s213$This release only ships a zip — opening the releases page to update manually$s213$, '27694ce8fa62968aaec88d052b20071f9e6a3402', FALSE, NULL),
  ('585c940fef29ab1e', 'client', $s213$<b>Recent 2v2 Series</b>  <color=#888>({0} total)</color>$s213$, '48f98d176879695850180ebf56c1e062da18d1be', FALSE, NULL),
  ('5873dfb6d6ce0071', 'client', $s213$Price$s213$, '3e8248e32edfca0c629622b5b669c2d9ce4d0917', FALSE, NULL),
  ('5884139e3a1c369e', 'client', $s213$Hit / Block %$s213$, 'bfa62d12f6552fa084e5624db91e8f809cc967fc', FALSE, NULL),
  ('58978992916fe6a0', 'game', $s213$Continue$s213$, '2e02623966f9391facf6eaefc8b079ed5b630bee', FALSE, $s213$StringTableDefault/BUTTON_CONTINUE$s213$),
  ('58adc2e93f0e5669', 'client', $s213$How It Works - Sync (weekly)$s213$, 'b4a5f85c718b851bc30c568fe28f4ef79037ce0b', FALSE, NULL),
  ('58b772f9792e7de7', 'client', $s213$In-game chat overlay: <color=#88FF88>ON</color>$s213$, 'be77e0d452a5b253d62f1b462dca9f79853f28df', FALSE, NULL),
  ('58c74152577b5c36', 'client', $s213$No messages in this channel yet.$s213$, '21c960d176f4b50c4fa7595f1e57dd48dba53808', FALSE, NULL),
  ('58deaa5e3f8e5168', 'game', $s213$Lock aiming to 8 directions (Controller)$s213$, '12f565353f4c5f3481dc7e91cba078f2af9f9a8d', FALSE, $s213$StringTableDefault/OPTION_CONTROLLER_AIM8DIR_PS — PS Terminology: Controller (to take from "wireless controller")$s213$),
  ('58e34f41f31eb642', 'client', $s213$Resuming series at {0}-{1}$s213$, '51e8026c9a204f54a6bd4b1a2d8953138483eb22', FALSE, NULL),
  ('58fbea629e3fa26a', 'client', $s213$Unfocused deep idle (60s): <color=#FF9966>OFF</color>$s213$, '2f22b1bc82be022594e05b9ce2b5a2246c921b6a', FALSE, NULL),
  ('590709f4939b85b6', 'client', $s213$<color=#66CCFF>Searching for {0}...</color>  <b>{1}/4</b>$s213$, '07bd257b33b6b7dae2457c8b3cfe4b5949484973', FALSE, NULL),
  ('594d65c7ebdb366f', 'client', $s213$Session {0}-{1}$s213$, 'c9a1eaa86777152a8484d1f89531c86f5c9a5bf0', FALSE, NULL),
  ('5960a9ad7ea21934', 'client', $s213$<color=#FF6666>(SOLD OUT)</color>$s213$, '3459beeb88871e1e04b203c8a2bae6ad0c375949', FALSE, NULL),
  ('59e3487efe729e16', 'client', $s213$  vs {0}:  <color={1}>{2}W-{3}L lifetime</color>{4}$s213$, '69dbcae41ae96b4d28fd39fbc75d2d0d810cd266', FALSE, NULL),
  ('59f6bde0a7f60351', 'client', $s213$Select players (left) to compare {0}.$s213$, '1175545bb73a476b0d1a87051cb90a94ed11cc7e', FALSE, NULL),
  ('59f9beed30cbc149', 'game', $s213$Round Orange$s213$, '56a03cc77d4a6b636621118f0e0e4af7ee180cca', FALSE, $s213$StringTableDefault/PROMPT_ROUND_ORANGE$s213$),
  ('5a632213b986a0b0', 'client', $s213$Ban$s213$, 'bfa1bfbf6c1cd85f3d2b4f696a8d5761ff6c91ee', TRUE, NULL),
  ('5aa6d8c6966b7d57', 'client', $s213$Mint$s213$, 'aaa70f58c89e39722304f18ce50db0b7bf8907e1', FALSE, NULL),
  ('5ab18e987855fcf3', 'client', $s213$Rising Star$s213$, 'f2f5d68e6499e7eddf0b08d8dbbc483e134f6843', FALSE, NULL),
  ('5adf29d4453a8219', 'client', $s213$<b>Chat Moderation</b>  <color=#888>(your granted channels only)</color>$s213$, 'def1a1de4c1e2ca98fdc5a3f1bce6342a4492543', FALSE, NULL),
  ('5aecb28115473fc1', 'game', $s213$Invite friend$s213$, '18d228b022c63aa8346d7ece8fc455f05f14c051', FALSE, $s213$StringTableDefault/BUTTON_INVITEFRIEND$s213$),
  ('5b1fa8823faaa4dd', 'client', $s213$Slate$s213$, '26d7b218c9b5641b37dfddc13b955184f3ce868f', FALSE, NULL),
  ('5b4560f5fd3ca74d', 'client', $s213$<b>You</b>$s213$, 'dbc49e21b64e298c965187ecea7dcf1bcdd62263', FALSE, NULL),
  ('5b55ed08358bfee9', 'client', $s213$   -   CASUAL (UNRATED)$s213$, '50e2e93f65bd2bd960221ee26b92edfba8b35840', FALSE, NULL),
  ('5b789e3f0dcae3da', 'client', $s213$Sustained Power$s213$, '24e70c2af4a5fd7a4c77d10b257d272c6d49b649', FALSE, NULL),
  ('5b92f3c6a6bc9bba', 'game', $s213$VS$s213$, 'b8a1e1dc56dfb4912a6dd518664883f8000965ae', FALSE, $s213$StringTableDefault/PROMPT_VS — Versus$s213$),
  ('5bb3b488dc9259b7', 'client', $s213$Next >$s213$, 'f80fd0c9d9fb230fee5ea75092709ea8f07d8023', FALSE, NULL),
  ('5bb89ae8f8fe797b', 'client', $s213${0} Blocks$s213$, 'bf913700cbab41212cf3ad715dd81da699639b50', FALSE, NULL),
  ('5be23ab4dd2dbd3a', 'game', $s213$Enter chat message$s213$, 'fa99bae9c84a05cb3c9d2b65df0abd496e728db9', FALSE, $s213$StringTableDefault/PROMPT_ENTER_CHAT_MESSAGE$s213$),
  ('5bebdfe868db2544', 'client', $s213$Ivory$s213$, '39973be20679a94e4c998a58c0f6c76daaf6cd11', FALSE, NULL),
  ('5c4c865c87f70972', 'client', $s213$Ranked History$s213$, 'd7108e6ab5e6f45e23c2ec5fe23f129cf7d5631a', TRUE, NULL),
  ('5c528222367454fd', 'client', $s213$<color=#666>no cards</color>$s213$, '568602877de41bc9414cac985c77b8c26ac84eaa', FALSE, NULL),
  ('5c65ef160d2f5147', 'client', $s213$SERIES COMPLETE {0}!$s213$, '420b7ab0cb9993c4d5ddeec670cee91d97fb4b2c', FALSE, NULL),
  ('5c7f514fa12c66ce', 'client', $s213$<color=#88AAFF>duo won</color>$s213$, '239e7d1a3132fda68ccef926a05bad2726b26e2f', FALSE, NULL),
  ('5c819efd5e47b749', 'client', $s213$Cooled lava — volcanic oxblood at the edge of black.$s213$, 'a7a705f4f6e2ae44ccf76ce8ec20cb3f7825828f', FALSE, NULL),
  ('5d2ca42b2c4789b8', 'client', $s213$Cards: <color=#88FF88>FULL</color>$s213$, '5fafc6ce92411f8dd5808ec5a87bc12b0a48c8d9', FALSE, NULL),
  ('5d3d20c7e814733e', 'client', $s213$Pick at least one start time first$s213$, 'f9177c4826c3a708fde02435090893f66afa4a98', FALSE, NULL),
  ('5d3ed3204781011a', 'client', $s213$<b>2v2 Leaderboard</b>  <color=#888>— no completed series yet</color>$s213$, '5c9c793345b996017a4330b1ceed5fe76f937c44', FALSE, NULL),
  ('5d86deb9c0e3f802', 'client', $s213$Sign Up for Tournament$s213$, '16c45d0311571f2a5866f4739eee429063e075cf', FALSE, NULL),
  ('5d98387d164dafd9', 'client', $s213$Leave Signup$s213$, 'b184a204463eaea71321073fcd40120e63116faf', FALSE, NULL),
  ('5db13011ad111262', 'client', $s213${0} and {1} more$s213$, '616f33b46c1533c1418ef7509c1e8dfd23521644', FALSE, NULL),
  ('5dbdcd2c139f60eb', 'client', $s213$no data yet$s213$, '5721ec14c55e6b84fcb1167530b5e59891bc4d54', FALSE, NULL),
  ('5dd21d2b1effe3ed', 'client', $s213$FIRST TO {0}   -   {1} OPENING DRAW   -   {2}-CARD HAND$s213$, '37ec0acb9e53c4780bc0c0fe2454681fee5cab89', FALSE, NULL),
  ('5deba6276fd8a551', 'client', $s213$* <color=#FFE580>1st</color> - {0}g / {1} XP / Winner role$s213$, '905ab236d174b26450639245ec52f92ca75cc3a9', FALSE, NULL),
  ('5def38b6c29f4d9c', 'client', $s213$Soda Helm$s213$, 'f9d59a6ea8c756838f928f0d95c9d34e4d99db37', FALSE, NULL),
  ('5e52fd220fd26006', 'client', $s213$Unban$s213$, 'd2671bfbfdd28d9143047f6a5239296f8a690156', TRUE, NULL),
  ('5e6611223ccd2e52', 'client', $s213$<color=#FFE580>Report a Bug</color>$s213$, '38a56a2898844a92391b086b48afb2f86e9b282d', FALSE, NULL),
  ('5e96f965b35fd77c', 'client', $s213$Save Votes$s213$, '71b36cbeefd3cb3cc776984731e0f86c9c663c32', FALSE, NULL),
  ('5e9f0e30afc2a578', 'client', $s213$Odds are set when the lobby starts. Refunded if the exact person/team you bet on is not in the game.$s213$, '169b553fcca1b1d0892fdfb4527b94f323bcdaa1', FALSE, NULL),
  ('5ef0b9cf34f0aff2', 'client', $s213$Yin & Yang$s213$, '89ffbc49c5cd513fb7f444af55b747d977cda309', FALSE, NULL),
  ('5ef4114e5d236a69', 'client', $s213$Matchmaking keeps failing - returning to menu. Please try again in a minute.$s213$, '0fefb03e0915bf2eb7ff03cc56f927fc0efb5d5e', FALSE, NULL),
  ('5ef70f53892e5f41', 'client', $s213$On-screen pop-ups for incoming chat and XP/level notifications. The chat log on the Home tab updates either way.$s213$, 'e3e83bc594cc7ecde3071f3c0b105ca0345809b2', FALSE, NULL),
  ('5eff08c9ac85a416', 'client', $s213$5-0s Given / Taken$s213$, '53c3940e8df73697c97ab5edce695bfe72450d7d', FALSE, NULL),
  ('5effd06b69376e5b', 'client', $s213$<color=#FFCC44>You are the host.</color> Waiting for players - {0}/{1} needed to start.$s213$, '5c1fa7d0cda455f717492a0bd5cfa35aee09c9a7', FALSE, NULL),
  ('5f180b79d0ac42fa', 'client', $s213$Leave Queue$s213$, '38c987b3019663c25cb284dbb39be1249e4505be', FALSE, NULL),
  ('5f1ededf6306d873', 'client', $s213$Eats damage$s213$, '7efda4c6d275389b1bfd26f7a15ac191beb583c8', FALSE, NULL),
  ('5f7558f212422e9c', 'client', $s213$Rainbow$s213$, 'b4a9395d25398654fd5d000e4b82a1d8273339bd', FALSE, NULL),
  ('5f7707fef861204c', 'client', $s213$Ranked: OFF$s213$, 'd25149b5a5f3f6d2741e28fb6dfc7c7c7ae8fd5b', TRUE, NULL),
  ('5f848b3eb8cb35f5', 'game', $s213$SAW$s213$, 'e2d1b2b887c37d8de2e52efcd6756c609ae4930a', FALSE, $s213$StringTableCards/CARD_SAW$s213$),
  ('5f8bd23a48bfb8ae', 'game', $s213$Twitch matchmaking$s213$, 'cfe8c15588f8ba75d26a5b2fabe5e381f05f1004', FALSE, $s213$StringTableDefault/BUTTON_TWITCH — Do no translate "Twitch"$s213$),
  ('5fb50f8fc41b94e9', 'client', $s213$FPS counter: <color=#FF9966>OFF</color>$s213$, 'e1ebe8c3f2f26102477a3f062945ebe18bf2ef2d', FALSE, NULL),
  ('5fbaf7ccbe5a45d2', 'game', $s213$RICCOCHET$s213$, '1b39d9c3d5a0f2c828b58a4be84d7aa0c9443993', FALSE, $s213$StringTableCards/CARD_RICCOCHET$s213$),
  ('5fc280a4ee756126', 'client', $s213$Sold out$s213$, '02ff65909856c0d4c47e5496f4e5df4964c3982f', FALSE, NULL),
  ('5fdeeb0b9c1ec66a', 'client', $s213$<color=#888><i>Nobody visible right now.</i></color>$s213$, '6b1ea4c0eeeb654cbd9aa79535b60b966080d110', FALSE, NULL),
  ('5ffa7b8c124f7f33', 'client', $s213$(click to change)$s213$, '7ac566c71a837d873f12e3d2542010fc455bbd3b', FALSE, NULL),
  ('6023f2dc69b9be58', 'client', $s213$Voidshot$s213$, 'd44941df851133e25121f54f10ddffbc79ed5ed4', FALSE, NULL),
  ('6028e9eac2094a5a', 'client', $s213$Sweden$s213$, '72ddd2b619af6d6a73febf80f7fcad22495498cd', FALSE, NULL),
  ('603409ff6c82dce6', 'client', $s213$<color=#8899AA>Pings the Ranked Looking For Player role (max 1 per hour). Optional message:</color>$s213$, '40e65024e861fed568d872aea26bc7171255c387', TRUE, NULL),
  ('605658c249cc8630', 'game', $s213$BOMBS AWAY$s213$, '0ee58998762310019739faa1cbaf6bae20cb8d63', FALSE, $s213$StringTableCards/CARD_BOMBS_AWAY$s213$),
  ('605b23aab951f318', 'client', $s213$MATCH STATS  <color=#888><size=12>(hold Tab)</size></color>$s213$, 'aaebd0c4faae71a489204727bee2e9b3773fd5a8', FALSE, NULL),
  ('6066a6cb536f4b96', 'client', $s213$Win with two or more Saws$s213$, '809eb193730a6e60b092ac15cb906006e2d0c47d', FALSE, NULL),
  ('608561ba53ff573f', 'client', $s213$Starry Eyes$s213$, '6134bd38cec65de46eba3419acc1c714ffe1cd20', FALSE, NULL),
  ('60979d8da1b597d1', 'client', $s213$Bet on which pair? Pick 2$s213$, 'f6194328ef7b4d6ab5cc23907ac2b2d57d87657e', FALSE, NULL),
  ('60bbbc527e3744da', 'client', $s213$Sunset$s213$, '181bcd5760fd32163554c899301a30b2cd381cf4', FALSE, NULL),
  ('6104d7afb98b0f0f', 'game', $s213$Dealing damage reloads your weapon$s213$, '53bea03dbb1bf46302373ebc4248c5be987848fb', FALSE, $s213$StringTableCards/CARD_SCAVENGER_DESC$s213$),
  ('614fa528bd87d77f', 'game', $s213$Options$s213$, '6bf5da9c080bee3a8142586c412aa39971137eee', FALSE, $s213$StringTableDefault/BUTTON_OPTIONS$s213$),
  ('6155cc874330ae15', 'client', $s213$Industrial steel grey with the warmth bled out.$s213$, 'ad8477c02907e0acf0430c6c33bcc17614b5cbe2', FALSE, NULL),
  ('61611d5f98241ddd', 'client', $s213$Bets Won / Lost$s213$, '97762f31a5a61b013e1f4eebdfdd835d94ad7923', FALSE, NULL),
  ('616fd119d706cddd', 'client', $s213$Back in the Quick Match queue — searching for an opponent.$s213$, '0b3b3ac66cd2cf8925317cf45e29992a8629264e', FALSE, NULL),
  ('61873d24740b083e', 'client', $s213$Scarlet$s213$, '1207638e87127a3ee0ecce2ac2254ea4a7aa6c90', FALSE, NULL),
  ('61abcf4400fd7a42', 'client', $s213$Magma$s213$, '3548c9250892c509047e2c7ec04d76bf39c63524', FALSE, NULL),
  ('61bb06cc51843ce1', 'client', $s213$Two crossed battle standards. For the cause!$s213$, 'a9b6b056b13b501af43880063da2ed0de4059f24', FALSE, NULL),
  ('61ecc3a70166ed11', 'client', $s213$Azure Comet$s213$, 'caacb9c4120653ddad8aa9d39ba9c52e144d097d', FALSE, NULL),
  ('61f1806355fbefaa', 'client', $s213$Couldn't change Appear offline - try again$s213$, '034bec883ab3debd39fbe97e1a8ea46dd6aeced8', TRUE, NULL),
  ('62017cfb23dc8d2b', 'client', $s213$Map lighting: <color=#88FF88>ON</color>$s213$, 'f9cdd3d419e43beb090cc154a41152fc7693148f', FALSE, NULL),
  ('620a77e0a38cd666', 'client', $s213$Black Cursor$s213$, 'cee82537870ea52d5f32f6a15bd0752b3c43183d', FALSE, NULL),
  ('622f53aec8cd587f', 'client', $s213$Still leaving the 2v2 queue — try again in a moment.$s213$, 'a11144e953fe745349754c33552d7fe771913b62', FALSE, NULL),
  ('625836003d87ac6f', 'client', $s213$She/her$s213$, '444a011d29f4155587f4e755e604c1fa955899e9', FALSE, NULL),
  ('6269332e5e9b9dcb', 'game', $s213$Fullscreen Window$s213$, 'd6590b268a500fed2f76419209b48b42acbec865', FALSE, $s213$StringTableDefault/OPTION_FULLSCREENWINDOW$s213$),
  ('62945646ff725873', 'client', $s213$Sweaty$s213$, '0c95f4a83a19eb2e8965d24c44c42df5b61d5388', FALSE, NULL),
  ('62ce5181e5a602ca', 'client', $s213$FFA$s213$, '90ce5340a6531dab9e5c720670abf91bb7d42fc4', FALSE, NULL),
  ('62d51247bd7470f7', 'client', $s213$Bright electric-cyan body color.$s213$, 'c93e38d0d4ff579fde2f4a80a077a881667a17f9', FALSE, NULL),
  ('633dc1e39f94d3a0', 'client', $s213$Your placements: <color=#888>no completed tournaments yet</color>$s213$, 'a1a912243dc59524cca780830160df18bf83b01c', FALSE, NULL),
  ('63ca8f483529510b', 'game', $s213$Blocking creates a healing field$s213$, 'c18a33d7d3ef2b00ae81989322977ae3e326e1ac', FALSE, $s213$StringTableCards/CARD_HEALING_FIELD_DESC$s213$),
  ('63f4d64f58ce3cab', 'client', $s213$Password must be 64 characters or fewer.$s213$, '0959b55c3ce21f8d75c8a6f3f53d766d21925fd0', FALSE, NULL),
  ('63f7bab1460114b8', 'client', $s213$Search cards$s213$, '580d82bb1d98c79f2293e2759772ad0075ac0045', FALSE, NULL),
  ('63f971a282654786', 'client', $s213$  {0}  <color=#888>{1} their side</color>  <color=#666>{2}</color>$s213$, 'b0247bb4bb0764888d3c797e0f15daaa92c2ca9e', FALSE, NULL),
  ('640ae8a86f2e1d0f', 'client', $s213$Pick a card! (left/right + jump)$s213$, '875ac7dcd6f646d6220442f1a02bf5b1e803b167', FALSE, NULL),
  ('6417f5d13dc1cd9b', 'client', $s213$Sweeps: <color=#00FF00>5-0 x{0}</color>  <color=#FF6666>0-5 x{1}</color>$s213$, 'c992e487ff19ddc4ae5cc59132442aaf46dd9b5a', FALSE, NULL),
  ('644852b751fe9f28', 'game', $s213$Health$s213$, '3703cd216881d3303a10a898fe54439bf05685b6', FALSE, $s213$StringTableCards/STAT_HEALTH$s213$),
  ('6449179f9d1f38ce', 'client', $s213$TOURNAMENT MATCH vs {0} IS WAITING - LEAVE THIS GAME NOW!{1}$s213$, '09e233dea356e6cd5e938852f8755d561df79d21', FALSE, NULL),
  ('644ccc8abba37deb', 'client', $s213$<i>The bracket appears once players sign up.</i>$s213$, 'cc431e8b80c8979c751fb43424e33c02902d1388', FALSE, NULL),
  ('646589db10bb5f2c', 'client', $s213$Soft shadow beams cast by map lighting. Off = no shadows (lighting stays on) for extra FPS.$s213$, '908c1137c947ee99598d692d1d247169b67b174c', FALSE, NULL),
  ('6466039f078b9b29', 'game', $s213$Bullets gets more damage over time when travelling$s213$, 'fae8fc513192afe1f5a8bd331194881fb86df3c2', FALSE, $s213$StringTableCards/CARD_GROW_DESC$s213$),
  ('64e8a47541007536', 'client', $s213$Your name fades from warm amber into deep pink.$s213$, '2bbe77e5794acb118c3f9cadfd5a8b5130e9a46d', FALSE, NULL),
  ('64f50d41089a0db6', 'client', $s213$Spooky Head-Bouncers$s213$, 'a6a7b70436b1cb9914649ca0f29a787099ee1c15', FALSE, NULL),
  ('64f83a9de1531aa1', 'game', $s213$No$s213$, '816c52fd2bdd94a63cd0944823a6c0aa9384c103', FALSE, $s213$StringTableDefault/OPTION_NO$s213$),
  ('6527d25181574b70', 'client', $s213$<color=#FF9988>Hit:</color> {0:F1}% ({1}/{2})$s213$, '39a0a4745696d6845086d5a0a336ee7ae6cedaf1', FALSE, NULL),
  ('6543831301a89f5e', 'client', $s213$< Prev$s213$, '8e1cffbecc609338e0ea0ba1b86c0512b1bdc972', FALSE, NULL),
  ('65459268621110a8', 'client', $s213$Touch Grass$s213$, 'a2c06f13201a8b0dd13595ac4dd0d24a7c4670c6', FALSE, NULL),
  ('65643a73af1222dd', 'client', $s213$same-card$s213$, '289751437f860828c589bd3ecdcf0c5d29fe8c9d', FALSE, NULL),
  ('65702329da800b20', 'game', $s213$Mute Chat$s213$, '4fc9b771f03771106b19f552f29437db4e82e5d4', FALSE, $s213$StringTableDefault/OPTION_MUTE$s213$),
  ('658d71d742121ed2', 'client', $s213$Solo Leaderboard$s213$, '3d40c20821471e017a6f118ca7911fbcea797946', FALSE, NULL),
  ('65a32e66177882b6', 'client', $s213$<color=#66DD66>Your lobby is ready.</color> {0} in - press Start, or wait for more (up to {1}).$s213$, '8bfb3dcc1c64782da5cc10b57aa42cab47e08f32', FALSE, NULL),
  ('65c15ec0c162c4b3', 'game', $s213$Press [<sprite name=BUTTON_START>] when ready$s213$, 'd759a34e84df44091ff5dfc06ca78d66c960a21f', FALSE, $s213$StringTableDefault/PROMPT_START_WHEN_READY$s213$),
  ('65d7670c7a57530a', 'client', $s213$<color=#CCC>Dmg taken vs blocks</color>$s213$, 'cf3d5ce1d2f0ce340da36b8cb047d330a7e541bb', FALSE, NULL),
  ('65d78156773abdb8', 'game', $s213$Healing field$s213$, '541a369258ece062bf593b14ce24004e457be136', FALSE, $s213$StringTableCards/CARD_HEALING_FIELD$s213$),
  ('65fcf4378f18e10e', 'client', $s213$Pacifist$s213$, 'eacde01371d3cfecd1d6868ac0dc890330df9229', FALSE, NULL),
  ('6620333e3e9989e6', 'client', $s213$Admin action log ({0}-{1} of {2})$s213$, '3db1798f11598eedd49a8cbcbeadd842f8088b4a', FALSE, NULL),
  ('6628289042207194', 'client', $s213$Random Queue$s213$, '09e9637fcb1efff7cf0100fe0a14567427177caa', FALSE, NULL),
  ('664c773cdf0bb4c7', 'client', $s213$Demon Wings$s213$, 'a957d1b7bc867ae01a8723a614a867b018c111b4', FALSE, NULL),
  ('667904796cde2009', 'client', $s213${0} dps$s213$, 'f274e414cfaafd05ff3a007da9a995bc7723be59', FALSE, NULL),
  ('66b1bfa0c7da43ad', 'client', $s213$Umber$s213$, '1255b7d12b59020bccf9dffde6b463bb84d3eedb', FALSE, NULL),
  ('674dc4e5522d0f23', 'client', $s213$MATCH POINT - {0} are half a point from the win!$s213$, '1e5d0858e09b08bab630a076267ce09e581733d9', FALSE, NULL),
  ('675047dd2ba5fab9', 'client', $s213$Controlled Burst$s213$, 'a4e08a5b9cbd3ab4220ac58c80a41675bdeb184e', FALSE, NULL),
  ('675638018d7fbb3d', 'game', $s213$Master volume$s213$, 'a444d635bd13bba529ac69d96957db504df25517', FALSE, $s213$StringTableDefault/OPTION_VOLUME_MASTER — Main audio volume$s213$),
  ('67639960c926c58e', 'client', $s213$Star Spin$s213$, 'f2698c4901757c1e713246a5a58dd359698f9f54', FALSE, NULL),
  ('67a6d0f456b16987', 'client', $s213$Moss$s213$, '752fbb36578511afe3527c40c95abe3e1f95d7bd', FALSE, NULL),
  ('67bfd40e0352aa95', 'client', $s213$Settings$s213$, 'c7f73bb54d928922c3838bb789ee9fb8a5b1eb37', FALSE, NULL),
  ('67c04e155d92e2fb', 'client', $s213$Expert$s213$, 'd7a501f83242fd940b8190529432e0703dd7606f', FALSE, NULL),
  ('6828d481f25f271e', 'game', $s213$More$s213$, '4bab2d8fe13fa6ab57f80098b414f0f734c5dd25', FALSE, $s213$StringTableCards/AMOUNT_SOME$s213$),
  ('6832a0eedc02a7c1', 'client', $s213$<color=#888><i>None yet.</i></color>$s213$, '2448f40ccec1a30c81bf740ffe85b7d30837e2d4', FALSE, NULL),
  ('683bcd6f2e8b0c87', 'client', $s213$LIVE$s213$, '6990f01ad9d2dd9bf6acbd5330b2a51dc97e62e5', FALSE, NULL),
  ('683fba7afbb36532', 'client', $s213$<color=#D8A7FF>FFA:</color> {0}W-{1}L$s213$, 'd9e3fd10875116ad5e4e38dca5bf31fbc487fdf5', FALSE, NULL),
  ('687c1dcb181ecf45', 'client', $s213$<b>Recent Ranked FFAs</b>  <color=#888>- none yet</color>$s213$, 'c655a4e371ec3c52666e977042a3cc98eb9de6dc', TRUE, NULL),
  ('687db26d8cbaa35d', 'client', $s213$Couldn't change the spectator setting - try again$s213$, 'a2945647946c1f17765c352675467add28162452', FALSE, NULL),
  ('68a61bb1c87662ca', 'client', $s213$Removed from queue after 30 minutes of searching - rejoin if you're still here!$s213$, '77e4aa898269d071d37354feabcd688601921fb9', FALSE, NULL),
  ('68aa309ca4b16cef', 'client', $s213$<color=#888>Ranked by default - the host can switch a lobby to Casual before starting.</color>$s213$, 'feac8a420c0e222781e205e9983eddbc6fa462c3', TRUE, NULL),
  ('68b06756b591710e', 'client', $s213$Precision shooter$s213$, 'd603c62a187b010ba86e02a8a3eae5477f7da9ca', FALSE, NULL),
  ('68d7eb35f0d51174', 'client', $s213$Rarity$s213$, 'a3e1e99f26208eb83034e08c40d2fa9b9e636088', FALSE, NULL),
  ('68df4873f949229d', 'client', $s213$<color={0}>*</color> <color=#FF6688>Live Ranked Games</color>$s213$, 'f474f703aeed6b41dfd3481051df0c1ce534977e', TRUE, NULL),
  ('68ebe98e1a246198', 'client', $s213$Hit % vs Block %$s213$, 'c93d8b77434bdab2d626ebd548390c53fe4108b6', FALSE, NULL),
  ('68ffce8bbb14ce05', 'client', $s213$<b>How to reproduce?</b> <color=#888>(optional)</color>$s213$, '8f377602579db81b3a6824ecb1e4175b54dbc1fd', FALSE, NULL),
  ('691b58372128513f', 'client', $s213$<color=#88FF88>In a hosted 2v2 lobby</color> <color=#888>— manage it in the panel below.</color>$s213$, '1035e8e76e03f4db596c6ca81bd098321002bcbd', FALSE, NULL),
  ('692dbb3bbe0f1257', 'client', $s213$Not great. Not terrible.$s213$, 'b8a8dabdec32830a601c4453d32a42f6722011b4', FALSE, NULL),
  ('694b7bbd6fe29463', 'client', $s213$Series {0} {1}  vs {2}$s213$, 'cbf8b1e91683087706a4ed11db627eb9673a72b2', FALSE, NULL),
  ('695949eccf2a3eb4', 'client', $s213$Wrap your name in <b>bold</b>. Stackable with other name styles.$s213$, 'c99d12a2a8f36120e482c0fc40e974443dba78bb', FALSE, NULL),
  ('6973c9ec580a6e8d', 'client', $s213$Card draw:$s213$, 'fe6dc37f7af5909d3e95e049fb3a30d820aea9ce', FALSE, NULL),
  ('698827c82f5162bc', 'client', $s213$Your placements:  <color=#FFE580>1stx{0}</color>  <color=#C8C8C8>2ndx{1}</color>  <color=#D4894A>3rdx{2}</color>  <color=#888>(played {3})</color>$s213$, '07165fcd109bbf9198d1f39c2f4d6149df178a3c', FALSE, NULL),
  ('6994bb12f92bd491', 'client', $s213$Attack spd$s213$, '2b4881723e1320d2b12e0ad31fc9dfc27794c0a8', FALSE, NULL),
  ('699eebe6e98c8a83', 'game', $s213$Blocking spawns a saw around you for a short while$s213$, '3fb749ccb42970013bf69b55ad8c2fc03c57753c', FALSE, $s213$StringTableCards/CARD_SAW_DESC$s213$),
  ('69db31eb590f12ae', 'client', $s213$<color=#C48CFF>FFA:</color> -$s213$, 'eacf603f30c34bd78459c3d1302b34e33822dbb4', FALSE, NULL),
  ('69df762b04945155', 'client', $s213$Evergreen forest at dusk.$s213$, '747064df7c49f0b13a9bb661d6209045ec2e3fdd', FALSE, NULL),
  ('6a77c5ad69934952', 'client', $s213$Few reach it. Fewer afford the title.$s213$, '9727f8a805db983c5d5372d96d511ce90094cbe2', FALSE, NULL),
  ('6ad9912372f78640', 'client', $s213$Ranked (series)$s213$, '749826ec9c02cfbac0274840d905f2c374fab239', TRUE, NULL),
  ('6aefe5059d63d0e1', 'client', $s213$Restore the vanilla random map color rotation.$s213$, '3e4d1a0220051e28866e692fcc1749e765c15125', FALSE, NULL),
  ('6af9389a92c0a962', 'client', $s213$Stop$s213$, '9e253470c876ee6d5c720eb777aeb82d4c26e28f', FALSE, NULL),
  ('6b1f73c4d8328319', 'client', $s213$   -   SUDDEN DEATH: everyone else cannot damage each other$s213$, '9833cb8825f1f4d90e0a19ac6b712bce64ed47ef', FALSE, NULL),
  ('6b43ebc09b19e182', 'client', $s213$Reverse {0}$s213$, '36d3898776980beda04f3c0a05601498b581a63d', FALSE, NULL),
  ('6b7ead97a78496f6', 'game', $s213$Italiano$s213$, '21df73947a06d77d2ad5fe166c8ddfcdc53a6fdb', FALSE, $s213$StringTableDefault/LANG_ITALIAN — 2023-10-23: Replaced the unlocalized name with its translated version$s213$),
  ('6b912c60e510d768', 'client', $s213$<color=#777>(your lobby)</color>$s213$, '13c8a3c88fb5be85116ae4e6a94a3dc35feeb24e', FALSE, NULL),
  ('6b9cd2a1a0ab7b42', 'client', $s213$Couldn't confirm 2v2 queue leave — the server will clear you shortly.$s213$, '68ec5a075ef700240242fa9a050ea434ed66e3cb', FALSE, NULL),
  ('6baeab76d10f6515', 'client', $s213$Failed$s213$, '09fef5d8d9a3c86b2523fef60d512606e7fe0003', FALSE, NULL),
  ('6bf7254f8bd481e1', 'game', $s213$EXPLOSIVE BULLET$s213$, 'ff849afde5ff08801cd474e6a1996a75ae87f195', FALSE, $s213$StringTableCards/CARD_EXPLOSIVE_BULLET$s213$),
  ('6bfdd85f5ded36f0', 'game', $s213$Reload speed$s213$, '634b59c88dd54e7bc5e5537d65050cf556efec66', FALSE, $s213$StringTableCards/STAT_RELOAD_SPEED$s213$),
  ('6c3530c8c280b3ff', 'client', $s213$now: <b>{0}</b>$s213$, '11ef3b2ae60a4251cd73fef09e480569d29ecdfd', FALSE, NULL),
  ('6c60e1d8262b75b2', 'client', $s213$3rd Place$s213$, 'de0ac0c428d1d09d04ae156d8084da226a9774b6', FALSE, NULL),
  ('6c69f7bf3992f0e5', 'client', $s213$Couldn't join the 1v2 match — left the queue. Please requeue.$s213$, '4fc6fcfe986a0768c6810872195ff1572267939f', FALSE, NULL),
  ('6c69fb2032e145c6', 'client', $s213$1v2 lobby never filled — returning to menu. Requeue when ready.$s213$, '254e5c235d478498f37e652155097dfb8c0603b4', FALSE, NULL),
  ('6c8b90ec9540ad5e', 'client', $s213$Gold Name$s213$, '72fdf7b43d255bfca709ad5b2f17f4c501334a6b', TRUE, NULL),
  ('6ca9dd38e68467c1', 'client', $s213$Porcelain$s213$, '79e59b6d40ad67a86922bb3f5937e4a051c43f13', FALSE, NULL),
  ('6cb131cbfe9994a0', 'game', $s213$DECAY$s213$, 'eb866db5850f7f76706cc98aa681c751d787ec10', FALSE, $s213$StringTableCards/CARD_DECAY$s213$),
  ('6d74d0c0e8ae9292', 'client', $s213$Chat has language channels - use the dropdown on the Home tab, or Tab while typing, to switch.$s213$, '5d378529c5ccf974fbf710c541fe49c260696b4a', FALSE, NULL),
  ('6da1ea02cbaf11d9', 'client', $s213$<b>2v2 Leaderboard</b>$s213$, '0f70b6db5879e40f505af9989b9439ecf621cbf5', FALSE, NULL),
  ('6db0703509c1dfd1', 'client', $s213$Near-black volcanic glass. Disappears into the night.$s213$, '7633072baa568d07dcc6acf347d8e0c67d78267f', FALSE, NULL),
  ('6dbbe5597bf64f50', 'game', $s213$Slightly slow nearby enemies$s213$, '7be668a4fe8a476e93552a44baa7e48df4ec24fc', FALSE, $s213$StringTableCards/CARD_CHILLING_PRESENCE_DESC$s213$),
  ('6de5dddf9737eec7', 'client', $s213$Banned$s213$, 'c8cd83f62e9d6c906f2b825ab8537bb5704a478d', TRUE, NULL),
  ('6de93f8b9886247b', 'client', $s213$No server-issued chat lines are in this session's log.

Only messages this client received from the server can be deleted - the request keys on the server's row id, which a local echo does not carry.$s213$, '31c3631d596f2157e5fdf1abd25d8ac629fc7b91', TRUE, NULL),
  ('6decaed07b4160c0', 'client', $s213$Delete My Data...$s213$, '5d3105ed80dc94bd4e080cbe35b6389a727a444f', TRUE, NULL),
  ('6df0149175e82e19', 'client', $s213$Soft pastel lavender — minimum contrast.$s213$, '2394bba21d20d3da5d703014c5a214f15bcef2be', FALSE, NULL),
  ('6e609efa1850f406', 'client', $s213$not enough data (4+ picks)$s213$, 'b812a48694a85178a169e0758e8e3d81298192fc', FALSE, NULL),
  ('6e6dc7f3133d7aed', 'client', $s213$vs {0}: {1}-{2} this session$s213$, 'a3917c0620dd986c7fd0b4339f378788e8a55cff', FALSE, NULL),
  ('6e855ac0bf320887', 'client', $s213$Allow spectators: <color=#888>...</color>$s213$, 'ae54dd55b18547fd56be56e76e010b16192a24b8', FALSE, NULL),
  ('6eb830e1335e559c', 'client', $s213$Only the host decides this.$s213$, '8eb88ab7faee9a89b8e4f794cd9786e217cc6f2b', FALSE, NULL),
  ('6ebdd285f3b71ef8', 'client', $s213$Sweat is just XP in liquid form.$s213$, 'f53f0af5f87f3ba660422807a1435727faeed72b', FALSE, NULL),
  ('6ecfb3dab02b8467', 'client', $s213$Your FFA match continued without you - you've been removed from it.$s213$, '28271452910576a33933fb47d894f1e4d8a6eb87', FALSE, NULL),
  ('6f22a3d809f5159c', 'client', $s213$<color=#FF6666>DENIED</color>$s213$, '77f34486d741bddbd1feecfab4257ae67faa108b', FALSE, NULL),
  ('6f43d60195f6d487', 'client', $s213$Rejected Reports$s213$, '89891d2edf2bd28e5b4952ef12239ee6da11ebd6', FALSE, NULL),
  ('6f4efddd4bda07b6', 'client', $s213$Tride$s213$, '1599ddb3455a45ccc59a3fac422049947650292b', FALSE, NULL),
  ('6f4fe42459b183a0', 'client', $s213$<color=#888><i>No stat data available for this card.</i></color>$s213$, 'ce21b94e03ec948163cb7c43df1ca15c2aaa6415', FALSE, NULL),
  ('6f684f202dcec6e0', 'client', $s213$Grant Translator...$s213$, 'cd357517fe20e286565b56385f12c4c3af9c4563', FALSE, NULL),
  ('6f6c3c254ccd07de', 'client', $s213$Stacked Deck$s213$, '72a0000376276a7f054fdf34cbbc166d639c06e8', FALSE, NULL),
  ('6f6f3c7c31dcf277', 'game', $s213$Allow cross platform multiplayer$s213$, 'a7c388a0ede2c4f26f4295589ab2b13c395d2d34', FALSE, $s213$StringTableDefault/OPTION_CROSSPLAY$s213$),
  ('6f9b0bd67cb50128', 'client', $s213$3/3 ready! Joining 1v2 — you are the SOLO...$s213$, 'c8bafd89a7a5719e44bc9857d22ce1be42c5a0df', FALSE, NULL),
  ('6fa6116e48d185fc', 'client', $s213$Player Nemesis$s213$, '15353c406b7afd5870e69defa94cbbc53009ede8', FALSE, NULL),
  ('6fb3f056a5481e85', 'client', $s213$Detail: a shooting star circling overhead (animated). Equip in the Character editor.$s213$, '55a2bf4d07dee2378de337391d28fcb235be8066', FALSE, NULL),
  ('6fe9842db9d19141', 'client', $s213$Render your name at 130% size.$s213$, 'f8f842c1e0272e4182ba74a5e1e671b7f8a60f30', FALSE, NULL),
  ('6ff4816bd7be86fa', 'game', $s213$Press <sprite name=BUTTON_NORTH> to open text input
Type names of the cards to spawn them
Shoot the cards to pick them$s213$, '8881d7e62e56565f8dea1d988f38d923617623ad', FALSE, $s213$StringTableDefault/PROMPT_SANDBOX_CONTROLLER$s213$),
  ('701947c757af5fa3', 'client', $s213$Unclosed quote — usage: /report "Multi Word Name" [reason]$s213$, '6df7395e6a96187a22b6cfc54a7672e0323a6d78', FALSE, NULL),
  ('7044fcd18b0d4eee', 'game', $s213$STEADY SHOT$s213$, '12a79b9c26ef6e3d05a9b0c0de56f9caa740313f', FALSE, $s213$StringTableCards/CARD_STEADY_SHOT$s213$),
  ('70483da324b9a680', 'client', $s213$CRASH$s213$, '1c1bcb24cffa054e5fd7d06de56bf73a3e74d02e', FALSE, NULL),
  ('705f3184942e5c20', 'client', $s213$A zesty yellow-green.$s213$, '093f93f6bc96df2c125019d556d7ef7a8e6b54e2', FALSE, NULL),
  ('709024e93f016139', 'client', $s213$ASYNC (6-week)$s213$, '7c4bd3155e01af462f64d585c6c85694a525cccd', FALSE, NULL),
  ('70ea7889f7bbb8aa', 'client', $s213$MATCH FOUND!$s213$, '11a9c89722334e53865de12f16e44151a6372071', FALSE, NULL),
  ('70ef6c5c94097ef3', 'client', $s213$Knight Great-Helm$s213$, 'f5b75e673715471ccd9edc10e29ada4d24f5dfdf', FALSE, NULL),
  ('70fd04265821e7cd', 'client', $s213$<color=#FFD94D>earned {0}g</color>$s213$, '447bf00a8adf3e15948428f8d350b4499a403d82', FALSE, NULL),
  ('7124fad98f05cda2', 'client', $s213${0} players online now$s213$, '18b717861013be8d79565ed16af73c668bcacd51', FALSE, NULL),
  ('712e95e3e33f7a8d', 'client', $s213$<color=#888>No hosted 2v2 lobbies — create one and invite your friends!</color>$s213$, 'f7c6206a8abf917b8d099d0e6ed4a44c6f66e48b', FALSE, NULL),
  ('713349054ad238c7', 'client', $s213$Get over 100 kills in a single ranked FFA$s213$, '68c08456174ff352b83fd491248983caedf0563b', TRUE, NULL),
  ('713c1176bf2b2b9e', 'client', $s213$<color=#99AAEE>Ranked History</color>  <color=#888>(recent series)</color>$s213$, '12fb0ff3ca8074a3192cd4aaaf78ba614b8a4d6b', TRUE, NULL),
  ('7188ba9ad803f323', 'game', $s213$Bigger bullets$s213$, '739e1d923303bddc618583ae50a45b0cdaf6f22c', FALSE, $s213$StringTableCards/CARD_BIG_BULLET_DESC$s213$),
  ('7193e2d43f8462f7', 'client', $s213$Left 1v1 queue - you joined a game$s213$, '2aa0b0b1a20afa22143208aeebcc1c6c787453c4', FALSE, NULL),
  ('71ab18d24bbd5f46', 'client', $s213$Dismiss (1 min)$s213$, '170d1f2f961db1e8e435c04f979012f0c4813bb2', FALSE, NULL),
  ('71c7cc75d6b8beb2', 'game', $s213$Firing your last bullet triggers a block.
Disabled continuous reloading.$s213$, 'ce53c9742edad3d2129a95c55cb2ad881e5fb7af', FALSE, $s213$StringTableCards/CARD_SHIELDS_UP_DESC$s213$),
  ('71e3ee43149aa274', 'client', $s213$A clean white line. The basics.$s213$, 'd1bf71529da76b7d1a3d412a4db22ec2f634c046', FALSE, NULL),
  ('72227ce31f4e8e6c', 'client', $s213$Revoke$s213$, '0be720759ff04d13c5706881d5d227a2621f91a6', TRUE, NULL),
  ('7238f6a0f006bd2f', 'client', $s213$Colorize your name in gold.$s213$, 'ce90982b634c51797500d1fa3c0537d9160f3cc4', TRUE, NULL),
  ('72516c9f1b1624dc', 'client', $s213$<color=#CCCCCC>Damage per second over the match</color>  <color=#99B3E6>{0}</color>$s213$, '55988d2481d6c10a64e86a342aa8d8f261b564dd', FALSE, NULL),
  ('725a66f0f66e8076', 'client', $s213$<color={0}>Blue</color>$s213$, '2aa5db947eb5e12f3d13857640ae1a52c1cee360', FALSE, NULL),
  ('725c315d1c164ba0', 'client', $s213$Regen$s213$, 'eb5c821caab94e7e985a15dfcbf1150b086c8ba2', FALSE, NULL),
  ('72667efc1834c251', 'client', $s213$Ranked Friends$s213$, '624fd377566b56ead5befdc372a3ee7c6794eab0', TRUE, NULL),
  ('72839b0611990203', 'client', $s213$Noobie$s213$, 'b47b90daf74ab5d4bbf2b814f199f2ddf3ca8ded', FALSE, NULL),
  ('72c46d73f688cf70', 'client', $s213$Allow data reporting$s213$, '1f8b1718e42040156e0683e7453e89a25bcad08f', TRUE, NULL),
  ('72f872abc86378a5', 'client', $s213$A sunny yellow mouse cursor.$s213$, '0e3adaa92340b7253fd391d5801e47286f66c549', FALSE, NULL),
  ('72fc87c339c9fc3f', 'client', $s213$Lose a ranked FFA holding 10 or more half points that never became a point$s213$, '9843b00eccc4fb151913c11e40b8acb9dd2398d7', TRUE, NULL),
  ('72ffea5fd21a2465', 'game', $s213$Get OAUTH$s213$, '8db5fed15ee21019f29337511a4422c2b3bf1ce0', FALSE, $s213$StringTableDefault/BUTTON_GETOAUTH$s213$),
  ('7308c734b8170dad', 'client', $s213$New$s213$, '6403f2b7eb2aaafe6de34cbf2a029b01afebc512', FALSE, NULL),
  ('7337988d9c68d788', 'game', $s213$Exclusive Fullscreen$s213$, 'de1e144ae13f8076061282171ad9a317ccbdd141', FALSE, $s213$StringTableDefault/OPTION_EXCLUSIVEFULLSCREEN$s213$),
  ('7360e52eca7e232d', 'client', $s213$Map lighting: the light and shade the map is drawn with. Off = flat, evenly-lit maps for extra FPS.$s213$, 'b9654a7b502b417a86b62f424f8d295435911770', FALSE, NULL),
  ('73be4f1b886889cd', 'client', $s213$Session Info$s213$, 'ee7f6b62b61a12ec18d69e017d11a4a8e7c9c4aa', FALSE, NULL),
  ('73dbf9f880098214', 'client', $s213$Leaving queue...$s213$, '02dceaeb2b12aa88ec87fcbae1520e6f97dd1690', FALSE, NULL),
  ('741922dd9e900e6a', 'client', $s213$On Fire$s213$, '8059b63e8a2ec48a76d5c678ff28583c5d065bed', FALSE, NULL),
  ('7420d8cc3e98ff5e', 'client', $s213$A braided crown of twisted thorns, blood-tipped.$s213$, 'f26aed94347cea2e644f80d3c4339839bf4741c5', FALSE, NULL),
  ('742b61a27b8f06c2', 'client', $s213$Iron$s213$, '8564fe3b4b674b36c08f22266d713f860a15ca99', FALSE, NULL),
  ('74417706603d0c5e', 'client', $s213$Bodycount$s213$, '688ca84d5148e1ce7841f6ada7f27396fa613bb8', FALSE, NULL),
  ('7443446e8638c23d', 'client', $s213$Couldn't join the 2v2 queue$s213$, '4df170619d634fa47e5daae97b531745de58200e', FALSE, NULL),
  ('7443c379c3eebac2', 'client', $s213$Slow connection — still trying to join the match...$s213$, '97437fc4808f9960b11e40fee6fd73da6ee76029', FALSE, NULL),
  ('7487b825669e2214', 'client', $s213$Details$s213$, 'dc3decbb93847518f1a049dcf49d0d7c6560bcc6', FALSE, NULL),
  ('74892e8d7d529b3c', 'client', $s213$Spread$s213$, '2bde101117a83786a9fe359d813c1badf4a6b2ee', FALSE, NULL),
  ('7491833f08beadc5', 'client', $s213$Berserker$s213$, '7d812b6c0cf9b06224698bf549532e4dfa84626f', FALSE, NULL),
  ('7499ab9b304a83eb', 'client', $s213$Couldn't change Show Discord on leaderboard - try again$s213$, '6fd5880619ade7b9b8f14cfd6e99c6aefb2aa25a', FALSE, NULL),
  ('74eeb293eb5406f0', 'client', $s213$SPECTATOR$s213$, '589d489cd61eb2b32e5d41f1253f6d4f5a176a55', FALSE, NULL),
  ('753b9026b589b7e3', 'client', $s213$Not in queue.$s213$, 'bcdd436f6f0ca66e0f43f93e286fcf6b21dd8688', FALSE, NULL),
  ('755e04f636c21f2a', 'client', $s213$Clamp ObjectPool init-spawn to 4 in-match — reduces frame stutter from new pool allocation.$s213$, '568dba56e5fadf7f411898e5b4c5ee9790606f36', FALSE, NULL),
  ('7567c90e85adfb18', 'client', $s213$Unblock$s213$, '12aabd251c4213f1cebfe4cb83e6547df55552c3', FALSE, NULL),
  ('756f628a3b169a47', 'game', $s213$Bullets drill through walls$s213$, '54c75b16453513030f98e6cc097b0158d92e2edd', FALSE, $s213$StringTableCards/STAT_BULLETS_DRILL_THROUGH_WALLS$s213$),
  ('75b1089a156c0abe', 'game', $s213$Quick match$s213$, 'a370fa498a53d254ea33c4d045026b32ed7b70cc', FALSE, $s213$StringTableDefault/BUTTON_QUICKMATCH$s213$),
  ('75b908029624d68e', 'client', $s213$Preview: {0}  <color=#888>({1})</color>$s213$, 'd2b78d262308d18630b0a15b9c03018be74b5d16', FALSE, NULL),
  ('75f7ef63c5238e27', 'client', $s213$Blue Cursor$s213$, '1aecb54aae1e2b5ed8dfe32d82d5a452ea62616c', FALSE, NULL),
  ('76304d064ecdaf0b', 'client', $s213$Chromatic aberration: the RGB color-fringing that pulses on shots/hits/deaths. Off = crisp edges, tiny FPS gain. Visual only, local only.$s213$, '0a298dccb65dad64a770d7e3fdae567c30ef4331', FALSE, NULL),
  ('765e3059472dff50', 'client', $s213$Couldn't join the FFA match — left the queue. Please requeue.$s213$, 'fd844b771d0a82bf96939a889060c8bd1fb63920', FALSE, NULL),
  ('7681ff2674d18619', 'client', $s213$Team: <color=#88AAFF>2</color>$s213$, 'a66ab0a55a17f97cf4a7b747ce97435384eebac3', FALSE, NULL),
  ('76839b71857b49bc', 'client', $s213$FFA lobby never filled — returning to menu. Requeue when ready.$s213$, 'c87f9c252d42a96f48c508b0dad1d7cb197bbf27', FALSE, NULL),
  ('7693b881f9bb10d2', 'client', $s213$Clear$s213$, '719ea396ad92e01b4757ec2b93bb1e5f270f771d', FALSE, NULL),
  ('76a3b977b8f74add', 'client', $s213$Neon Cyan$s213$, 'e91fae69ed9d52f9a959fd0aa232df98f563c6ee', FALSE, NULL),
  ('76d0b8ff54ba17d8', 'client', $s213$Heartbreak$s213$, '8affa8effd7087ecbab966e0ab6f5d70c951060a', FALSE, NULL),
  ('76de6671a0e43d50', 'client', $s213$A shimmering rainbow of particles cycles around you.$s213$, '12d7c24417f733987cc887cc155326577389eee7', FALSE, NULL),
  ('76fd56cb105bdb10', 'client', $s213$Enable$s213$, '20063ad9053289cecaa20ae630ed2dd758282a07', FALSE, NULL),
  ('770b1cee5bc3959f', 'client', $s213$Cosmetic trails: <color=#88FF88>ON</color>$s213$, 'd002a24ab224f0957250799b98672bb07e8e316f', FALSE, NULL),
  ('773e6de3fed90eab', 'game', $s213$Detail 1$s213$, 'ba3736eeae70ec057418be4390a2bdb189db2b00', FALSE, $s213$StringTableDefault/CATEGORY_DETAIL1$s213$),
  ('77501ba1887630dc', 'client', $s213$Locks the map to ROUNDS' Sky palette (light blue).$s213$, 'e07f293196ef7e0937ab9343b1984c5ffaf4e71a', FALSE, NULL),
  ('77698eafc221e602', 'client', $s213$Default start: <color=#AABBEE>{0}</color>   Signups close: {1}$s213$, '133e5f657b000e24c75606ccd1808f5d6fb5a618', FALSE, NULL),
  ('777608da05a9cc4a', 'client', $s213$Latest Releases$s213$, '53cd5d1778decb934a189c78a5655d1a89e0b9a2', FALSE, NULL),
  ('777a4ed3a4e9d1b0', 'client', $s213$ <color=#888888>(left)</color>$s213$, 'e0aa04851ac53a1bd32f85ccfe859005fe4e0a5e', FALSE, NULL),
  ('77b1c8d67327bc59', 'client', $s213$Blitz$s213$, '8882e4bb2a3ab29b02ac332ae19a66cdb130dbad', FALSE, NULL),
  ('77b6364f7604291c', 'client', $s213$Reach 2330 rating in ranked (1v1 or 2v2)$s213$, '4739f3bac2dbf726d75cb84d2cbe3551845e51db', TRUE, NULL),
  ('77ea4429fec09c29', 'client', $s213$Clear Search$s213$, '87e328dc94be6ee1930cf45d7a3e28999e9fa412', FALSE, NULL),
  ('77f5fa96a313fa19', 'client', $s213$Maroon$s213$, 'ca6ebdf49e3b17cc5b9a43d5ab6a00aef37e3a3f', FALSE, NULL),
  ('7811a5db8d47eda1', 'client', $s213$Bug report sent. Thanks! (#{0})$s213$, '9fe72981cc879912316e26db5261095ec4da3688', FALSE, NULL),
  ('7839675d71513a87', 'client', $s213$Honk honk.$s213$, '0a651c070742e5b205bdf0d6ec0b389fa0524d53', FALSE, NULL),
  ('783de471a77b0e7d', 'client', $s213$  Top 3: {0:F0}%  Kills/game: {1:F1}  Avg place: {2:F1}{3}$s213$, 'f4b973bce333a3966b7fb58036443649af4dd861', FALSE, NULL),
  ('785b325c520dbc5b', 'client', $s213$BepInEx (prev session)$s213$, '072719c3fc70bbe17a0c02b6968f63fb1de66a2d', FALSE, NULL),
  ('7878af0d6218e40f', 'client', $s213$Win 100 ranked series in a row$s213$, '2b7036dfd10c1a088708a60f75f3ca0d3c38080c', TRUE, NULL),
  ('78ac1eab1e0868c7', 'client', $s213$Input overlay: <color=#FF9966>OFF</color>$s213$, '2ffcc999b9210eec5e69ba494dded93b5eecc4ce', FALSE, NULL),
  ('78b3d4e42121719e', 'client', $s213${0} player online now$s213$, '52a835c16e77c4e0732602eddc7d23596d83990b', FALSE, NULL),
  ('78d960de3938c3aa', 'game', $s213$Slightly more$s213$, '39ffa12afa64c78190e0d3e9c9d534b3f120fd76', FALSE, $s213$StringTableCards/AMOUNT_ALITTLEBITOF$s213$),
  ('78f8e040217c152e', 'client', $s213$  In room with {0}$s213$, 'fe8ecd2e7ce2de3f4e5cd9f5d0455d92809bdbc6', FALSE, NULL),
  ('79188657d578e83a', 'client', $s213$Choose cards (left) to compare {0}.$s213$, '745fffa486b3d6bc7f6739e20fad006aa69a84ff', FALSE, NULL),
  ('795584614209151d', 'client', $s213$Animated cosmetics: <color=#88FF88>ON</color>$s213$, '953db08d420badd7066c9c7eb5e205966ed7ad27', FALSE, NULL),
  ('79a0762ddaf41128', 'client', $s213$Game ?$s213$, 'd9cc3dc4f2aba64784ee730953c68b885afbe01c', FALSE, NULL),
  ('79c01a16a77d59a1', 'client', $s213$Only the host can kick players.$s213$, '69ff3f5a19a3cf26411915fe4df7e457be5ecf05', FALSE, NULL),
  ('79d12f448ea4ecb8', 'client', $s213$<color=#FF9966>PLACEMENT CHANGE REJECTED</color>$s213$, 'f2c531693552d14d45c172e385c65845c14edac4', FALSE, NULL),
  ('79dfe1086dd7baf2', 'client', $s213$5-0 someone with Glass Cannon$s213$, '432a2d747a8cecaee4d8b0bbd8d11cbd131b8264', FALSE, NULL),
  ('7a1462b739334b88', 'client', $s213$<b>Recent 2v2 Series</b>$s213$, '99c2bd9a81258b1b9643ff1b723870cef5e1fc54', FALSE, NULL),
  ('7a2f8bfdc21c1700', 'game', $s213$Attack Speed$s213$, 'f33d401006f73851c505f11dbbcdbc71a877088c', FALSE, $s213$StringTableCards/STAT_ATTACK_SPEED$s213$),
  ('7a31d257e2cc1ca8', 'client', $s213$Opening the upload folder - drop a 512x512 transparent PNG (or a GIF) in there.$s213$, 'a7b8acc459f8bc8fe2e704045d98a585850e2667', FALSE, NULL),
  ('7a7823c2087f2573', 'client', $s213$<color=#CCCCCC>FPS over the match</color>  <color=#99B3E6>{0}</color>$s213$, 'a42b5210eecd90c46304776157124b18a67cc340', FALSE, NULL),
  ('7a9dce7f07ce4812', 'client', $s213$A soft green aura that says you know what you're doing.$s213$, 'd6682c54bc14e1ceeaab8f5c5f4d028edeb46ae9', FALSE, NULL),
  ('7abf29cd482ae2c3', 'client', $s213$RD: {0:F0}    Peak: {1:F0}$s213$, '585c9f8bfdd65b7176d0906cacf12b63bd0a5a16', FALSE, NULL),
  ('7ae8c98cd55250eb', 'client', $s213$Cream$s213$, 'd1e2abc18a8b508f620471e42c72adf3818c6480', FALSE, NULL),
  ('7b00a1e34b238a38', 'client', $s213$Avg Game Length$s213$, '733c052b3ccea1ff310008f67ea79002e90d3f23', FALSE, NULL),
  ('7b0dc0b4d08487af', 'client', $s213$Game {0}$s213$, '70016b079c5047ff972d699f67163ceeabf3ab5f', FALSE, NULL),
  ('7b10209c6ab33112', 'client', $s213$Bouncy$s213$, '0861596efe0b8976d831f3ea080decca2798d09b', FALSE, NULL),
  ('7b16a85fbc14efad', 'game', $s213$Steer bullet with right stick$s213$, 'd5e636522abecde6fa4b84788a1858739a98936e', FALSE, $s213$StringTableCards/CARD_REMOTE_DESC_PS — PS Terminology: right stick$s213$),
  ('7b1f1233cd6900a1', 'client', $s213$Loading recent series...$s213$, 'a47ce0315faa83adea0805be565fd26648ba3f45', FALSE, NULL),
  ('7b2d866aafe24425', 'client', $s213$Team: <color=#FFB347>1</color>$s213$, 'a6bbf1bfddd51781e6a302a6358026ff922a3651', FALSE, NULL),
  ('7b3594ded210db30', 'client', $s213$<color=#888>Pick <b>Search Random</b> for ranked matchmaking, or host a 2v2 lobby below to choose teams.</color>$s213$, '5f059e9dff7712f1d53c443cc1a341a060e3a29f', TRUE, NULL),
  ('7b55f022da9fc830', 'client', $s213$Quick Reload main$s213$, 'fa664531b4a41c6178b16cb21826ade02ac9de83', FALSE, NULL),
  ('7b5aaa66e23a080d', 'client', $s213$Deep blue-violet of the moment after sunset.$s213$, 'bda30be42cb140a97c3e1a67751c1da38c2ceb11', FALSE, NULL),
  ('7ba2d9bab03e78cb', 'game', $s213$RADIANCE$s213$, '5167d60b8ae929cbbb30e35c7fb111fd5b32ca5a', FALSE, $s213$StringTableCards/CARD_RADIANCE$s213$),
  ('7bd54751dd308e5e', 'game', $s213$Bullet speed$s213$, 'b3ffdc1b829c231e7a4594def624fcbe0e95fa1b', FALSE, $s213$StringTableCards/STAT_BULLET_SPEED$s213$),
  ('7bd90439fec0cae8', 'client', $s213$Caps the game at 120 FPS while the window is not focused. Saves GPU/CPU when alt-tabbed; lifts instantly when you come back.$s213$, 'eaa1ca32ac9d14098318df716ccaf7b619a568c5', FALSE, NULL),
  ('7be9b5f7a848839b', 'client', $s213$A festive crown of twinkling lights topped with a pulsing gold star.$s213$, 'ef5205084dc052e1551b3a5b29613d80ee2d61be', TRUE, NULL),
  ('7c40182849a2b50d', 'client', $s213$Top Streaks$s213$, '2bcded4477fbc29b2189244d26662a863ff2e0e2', FALSE, NULL),
  ('7c822307c6b1c668', 'client', $s213$Report dismissed for good.$s213$, '699209ea2c9bafabb100f17a87ff4792d228abaf', FALSE, NULL),
  ('7ca5ac14f4529d8a', 'client', $s213$<color=#AABBEE>{0}</color>  Winner: <color=#FFE580>{1}</color>  <color=#888>({2}p)</color>$s213$, '215a414b3ec2e0a6014946b0e501d09b88707d21', FALSE, NULL),
  ('7cabc97b10238e5c', 'client', $s213$<color=#44AA44>Up to date</color>$s213$, 'd8a969615148d5bc5db796e2f895f39763583cb0', FALSE, NULL),
  ('7ccc1a98abe848cc', 'game', $s213$+400% HP when above 90% HP$s213$, '15e14617a6182f0dcb9af8bdeeab14110bb680e0', FALSE, $s213$StringTableCards/CARD_PRISITNE_PERSEVERENCE_DESC — Health Points$s213$),
  ('7ce4510e0289c059', 'client', $s213$Neon Orange$s213$, '02140665ff58b93bef26879f6a7975a896f578d5', FALSE, NULL),
  ('7cf635369783ef29', 'client', $s213$+{0} gold$s213$, '4b4df825f33c5b554ba0e5497502d215a9312846', TRUE, NULL),
  ('7d55d57f5ad506dd', 'client', $s213$Card picks close in {0}s$s213$, '1e0bf83f8ad8121c68bb5c86364ed4e207d8098c', FALSE, NULL),
  ('7d6b3939f985247d', 'client', $s213$Strike$s213$, 'f9ae58aa354c851627202a2bbae82b33dd0da9c6', FALSE, NULL),
  ('7d817ff529af1f06', 'client', $s213$<b>FFA Leaderboard</b>  <color=#888>({0} ranked)</color>$s213$, '58139b6f61ab48387be44eb29431ba6209e10f4e', TRUE, NULL),
  ('7d8e43ec3c542605', 'client', $s213$<color=#8899AA>Search</color>$s213$, '2a30c4721b799ef8018b7e5b23cfe8062c17039c', FALSE, NULL),
  ('7da210afed1bb3ea', 'client', $s213$Ocean Gradient$s213$, '7e4c3a7dbaa079df9174e3a12981708587d175ed', FALSE, NULL),
  ('7dcb9d52c481ee91', 'client', $s213$FFA match found, but you're in a game — removed from the FFA queue.$s213$, '6d3d0e01344b51cfabdd664eec29029841a4dffd', FALSE, NULL),
  ('7df16c97f1097a3f', 'game', $s213$OVERPOWER$s213$, 'ef9d45a08107a968c244afdc6d05ebc19d9004b8', FALSE, $s213$StringTableCards/CARD_OVERPOWER$s213$),
  ('7df6272aa44de13e', 'client', $s213$Phoenix$s213$, '3e978fbf8aad93b7520fcec25f666a8823b47615', FALSE, NULL),
  ('7e0a40783617fcb7', 'game', $s213$Unblock opponent$s213$, 'c20a70fb6d864af3710aac16a3e8859972d1ef97', FALSE, $s213$StringTableDefault/BUTTON_UNBLOCK — Opposite action from above$s213$),
  ('7e1141fef186c747', 'client', $s213$Opponent hasn't connected yet — hang tight...$s213$, '00611e720d436d942093ef05ad8481bacf52f082', FALSE, NULL),
  ('7e2771250479b7a2', 'client', $s213$<b>Hosted 2v2 Lobbies</b>$s213$, 'aadbc1edbe90d83acf1c91d89ddf8fe85845bdc4', FALSE, NULL),
  ('7e4aa27012d8b519', 'game', $s213$TANK$s213$, 'db5987d0f64d0eaf17d2eb3dade36af46a56c522', FALSE, $s213$StringTableCards/CARD_TANK$s213$),
  ('7e65b027a3e3fb77', 'game', $s213$Fullscreen Mode$s213$, '55d050edae26d24cc822c7a7b3d9b4f00cc44f8f', FALSE, $s213$StringTableDefault/OPTION_FULLSCREEN$s213$),
  ('7e7de6c72b86824d', 'client', $s213$Blocks$s213$, '54c45c033f5eb914fae27a646cbd9e23d3750d19', FALSE, NULL),
  ('7ea032680df267bf', 'client', $s213$Banned players - type to search$s213$, '2b1074ee9054cc37d9f0d63b8e74753ecee5b495', TRUE, NULL),
  ('7ebcbde6dbe69280', 'client', $s213$Times Offered$s213$, 'eb04a56fc82f93bea4cf4d1b01baf017e892076b', FALSE, NULL),
  ('7ec612c4edc75150', 'client', $s213$OTHER$s213$, '957c024b38ce820878f03177ce3d2b83c26a82d0', FALSE, NULL),
  ('7f1e2dff680a21ea', 'client', $s213$A royal purple mouse cursor.$s213$, '26435e21d715685d5614c144df3ac5faaf6a77e5', FALSE, NULL),
  ('7f3d1d82b2323384', 'client', $s213$Finish or leave your current game first.$s213$, 'c500c2a4bc293add3f1d785c1db705e7095ad87c', FALSE, NULL),
  ('7f68781b5d95c2be', 'client', $s213$Win a game 5-0 with Healing Field in your build$s213$, '51684c861757561dafef3e283514ebf103cd7b8f', FALSE, NULL),
  ('7f80629f57a37126', 'client', $s213$<color=#CCCCCC>Latency (ms) over the match</color>  <color=#99B3E6>you</color> <color=#888>vs</color> <color=#E69988>opponent</color>$s213$, 'b9e3805cbd8a09cb53f502d1ee059cbe83bfa270', FALSE, NULL),
  ('7f8d50b8e50f6ae4', 'client', $s213$Ready Up$s213$, '55ad58fffa08821614376510977de2bd74d273c5', FALSE, NULL),
  ('7fbedacc6efea800', 'client', $s213$Swallow RayHitBulletSound NREs from destroyed parents.$s213$, '13b3faceb8360fa55fb94098c6b1e5b6b8d19f27', FALSE, NULL),
  ('7ff5a7c44329fddf', 'client', $s213$Win a game without firing a single shot$s213$, '0d164072c1c67cc0f40de17a0e756df812a9f276', FALSE, NULL),
  ('809359b5ebebe8d5', 'client', $s213$A deep, dark skin tone.$s213$, '067b43f4b1519da09b0ac300e59a647f12ae7d65', FALSE, NULL),
  ('80a36c40325aac15', 'client', $s213$<color=#666><i>Hide yourself here: Settings -> Appear offline.</i></color>$s213$, '593d09650a9947c940874fcff9cb819b859aef53', TRUE, NULL),
  ('80c96a889f9f5af9', 'client', $s213$Lost$s213$, '75a7bf994e9ac1b9d14062213673cc0a85729869', FALSE, NULL),
  ('80d04622a6a5d196', 'client', $s213$RANKED: ON$s213$, '07a2ae0633edf8be3f1fc68f659230f653255a99', TRUE, NULL),
  ('80f22c97cc0aac83', 'client', $s213$Hides you from the Home tab's online and recently-online lists.$s213$, '391e23160a547aa2386bfc6e88136f01474e87ec', FALSE, NULL),
  ('8107c94687b5513e', 'client', $s213$Confirm$s213$, '04a212215ef9fbf686d280802eb81ee7a6e681cd', FALSE, NULL),
  ('81104076ee39cd42', 'client', $s213$Most Similar Player$s213$, '62f6ac59d2ee7076a358664caf080ea992984f56', FALSE, NULL),
  ('811bf05184f39e45', 'client', $s213$SmAlLcApS$s213$, 'a8e56ef9b0223468ffe7a2e5ba21d538d23afc66', FALSE, NULL),
  ('811f0b6757adca50', 'client', $s213$<color=#FFD94D>Ranked Looking For Player</color> - Discord ping$s213$, '0112ccb6625408665001abf2b2b43ef9105e6e86', TRUE, NULL),
  ('81252e5360b78a3e', 'client', $s213$Delete Chat Message...$s213$, 'e29fa79082af77a532d9b616ea13c8b6b7538782', TRUE, NULL),
  ('8130edc9d99316e3', 'client', $s213$Unequip$s213$, '11442128172c9afd9632fadcdf0aa392e5083094', FALSE, NULL),
  ('81463339a0cf951c', 'game', $s213$PHOENIX$s213$, 'c6fbb606ae021f2cfa297f136b2b7c9e4ac0e21a', FALSE, $s213$StringTableCards/CARD_PHOENIX$s213$),
  ('817265dacfc7951b', 'client', $s213$Joined the match!$s213$, '479f27815777e46c802e3a188583f9e3496dd859', FALSE, NULL),
  ('819c9c1c3c9acf27', 'client', $s213$Win %$s213$, 'a7c9d3c0a5e39ccbb537414aa21bf930c5134232', FALSE, NULL),
  ('81b4817c1b10412f', 'client', $s213$Could not open that cosmetic preview.$s213$, 'c5df9fd9a7f89cc706132600acab54fdb3ffa145', FALSE, NULL),
  ('81d1594bd1091bc2', 'client', $s213$<color=#888>{0}</color>  <b>{1}</b> bought <color=#C8A2FF>{2}</color> for <color=#FFD94D>{3}g</color>  <color=#7FE8C3>+{4}g to you</color>$s213$, '07a8c3315325a7a113f2f1fc08be063c770e592e', FALSE, NULL),
  ('81d48a92efee6579', 'client', $s213$Series: {0}$s213$, '7d8e33e493d338e360b00d9457e0ae44f44857c4', FALSE, NULL),
  ('8212f50c48a591d2', 'client', $s213$<color=#7788AA><i>search cards...</i></color>$s213$, 'e86e5680239707b58a5b4998249bc5aae1a05f1e', FALSE, NULL),
  ('8227d56c911268e1', 'client', $s213$Per-letter bright cyan → deep indigo gradient. Surface to trench.$s213$, 'f08ec7ca421c33b887294dd88f4ba78c26fd48d7', FALSE, NULL),
  ('822906cf983c697d', 'client', $s213$<b>Your 2v2 Lobby</b>$s213$, '738d870e4c7f52b34268d8ae94969c6d08a7b2b0', FALSE, NULL),
  ('824fe214604ba4a1', 'client', $s213$Hearts$s213$, '99f9bf69ff7f179b358e1191419dafa45a0d75db', FALSE, NULL),
  ('825271b6ccbea3da', 'client', $s213$<color=#7FE8C3>Every signup past 8 grows the pot - 16 players doubles it! (now: {0})</color>$s213$, '96ee7b1438ffe3f13aa82d7096953dfa1ad77687', FALSE, NULL),
  ('8269a27433f4d383', 'client', $s213$Grant Achievement...$s213$, 'f33ee72ceeb88cb5f896985ce5aab3403f5b5c47', FALSE, NULL),
  ('8276060936caacd4', 'client', $s213$Party Crown$s213$, '9d32fee8673386fcb48650a016fe7874c5c0f377', FALSE, NULL),
  ('82a50967a8775147', 'client', $s213$A vivid green mouse cursor.$s213$, 'b6ccb321cd37c9a941a874741f8a5b53b4e22012', FALSE, NULL),
  ('82c76d6424138550', 'client', $s213$Card Win Rate$s213$, 'a8165c9103b6edfcfb72b05ba463860dcf26e92b', FALSE, NULL),
  ('83036a2c18f9f131', 'client', $s213$YES$s213$, '8fff039853f5c2bbb8a28d056b579c7dcb7d137f', FALSE, NULL),
  ('8311a697b4bf1aac', 'client', $s213$<color=#7FD4FF>1v2 History</color>$s213$, '4b40a0907e3234e0cc2fe724d87f31cc5cbe9cdc', FALSE, NULL),
  ('831575d2b0643a21', 'client', $s213$Next tournament match vs {0} soon{1}$s213$, 'ac0a3ea3db64d301c566b0246f5375709f7a6b14', FALSE, NULL),
  ('83394acf5203df01', 'client', $s213$Neon Toxic$s213$, '3b3e75bdc737be9d9289b248cf3318803f001c65', FALSE, NULL),
  ('8345415cab034679', 'client', $s213$Pick$s213$, '04d2414cddc1052e6f0278073dbb8ff76f134db2', FALSE, NULL),
  ('834d2735f544cc7a', 'game', $s213$HP$s213$, '5200bdfc01a139a753c6eb52ee1911cadd069dd9', FALSE, $s213$StringTableCards/STAT_HP — Health Points$s213$),
  ('835d7f9bb4c99884', 'client', $s213$<color=#FFD94D>your bet: {0}g on {1}</color>$s213$, '3742df76f32ab0da59ea2444feba18ecbdbb7ebf', FALSE, NULL),
  ('836f724fe5b3074d', 'client', $s213$Custom player body colors: shows shop-bought Body Colors on you and other modded players. Off = everyone falls back to default orange/blue.$s213$, '175c48cf6528b593772f727b6247f068ca95d6a8', FALSE, NULL),
  ('8385611059aa9da2', 'client', $s213$Win five games 5-0 in a row$s213$, '7f852990398165dad77d4ed415dac0e63d4a1149', FALSE, NULL),
  ('83c7c50f88df9d10', 'client', $s213$Detail: certified angel. Equip in the Character editor.$s213$, 'b76e06ba2922bd5320f09988df4115981726164b', FALSE, NULL),
  ('83d97e35f6f9a3e4', 'game', $s213$[RIGHT STICK]
To move items$s213$, '1df8742b04067aaa6bb9f9630983534f7e52c794', FALSE, $s213$StringTableDefault/PROMPT_MOVE_ITEMS_CONTROLLER$s213$),
  ('83dff324198dd780', 'client', $s213$  (last: {0})$s213$, '33de31eaa86df586fc5cdac587e01a4da1d8fcd6', FALSE, NULL),
  ('83f263b559925710', 'client', $s213$Render your name at 160% size.$s213$, '452eca3c01172368dcdcba51547a09396c0414a5', FALSE, NULL),
  ('8424897272503312', 'client', $s213$<color=#888>(solo extra pick)</color>$s213$, '227fdfe98dd6eb33929a1358e01817cbd13f6e83', FALSE, NULL),
  ('842765e862019d78', 'game', $s213$HOMING$s213$, '98f028708d8bf5eb14f0722193dc31b2ebc0fc9b', FALSE, $s213$StringTableCards/CARD_HOMING$s213$),
  ('843f580e89a1c339', 'client', $s213$Select up to 12 players$s213$, 'fb4e2d95d98953646b6c1b210ec64b47348fe61b', FALSE, NULL),
  ('84521b8589cb5bc1', 'client', $s213$They already left the lobby.$s213$, 'db33e30c2adcc157e72c999486438d03b7b67162', FALSE, NULL),
  ('848f3e18208e508c', 'client', $s213$RANKED: OFF$s213$, '1998dd66a03e45362865bc40663d644bf13e7641', TRUE, NULL),
  ('8491027df4c0bf40', 'client', $s213$You're in a live {0} game — finish or leave it first.$s213$, '0c37cdb67a8d79b797a1543e2a928ce02dc0c279', FALSE, NULL),
  ('84dea13d4f8749b7', 'client', $s213$A warm coral pink with hints of orange.$s213$, '4d33160cf65e8ee1374dbcda15cd04d741ffbaf8', FALSE, NULL),
  ('84ed7380201d44df', 'client', $s213$MEDIUM$s213$, 'f68525ad751f8a1d932458c4c58a214bdf0b30e9', FALSE, NULL),
  ('85126096ca57c79a', 'client', $s213$<color=#888><i>Loading match history...</i></color>$s213$, '46a5af2585c769ed0e95767115d47c4374011355', FALSE, NULL),
  ('8516a2f129517456', 'client', $s213$Glow Yellow$s213$, 'db4c6e762d551cdd15ce81da6fa4d2916ee2c8e3', FALSE, NULL),
  ('85322f19a78eccdd', 'client', $s213$the host$s213$, 'd1788f386fb5e576b73f0c14aa294dd1c2977898', FALSE, NULL),
  ('854774247858c849', 'client', $s213$Status: <color=#88FF88>Allowed</color> - match data and linking are active.$s213$, '084282a69463a804d2336837e4f92bd0b0d0160c', FALSE, NULL),
  ('857d64183e061d3e', 'client', $s213$Floating pink hearts rise from your body.$s213$, '6c741cc15dd127d0473f2b78bab3176ede8c2057', FALSE, NULL),
  ('859a1106591dae82', 'client', $s213$Sign-in still pending - try again in a moment.$s213$, '884cce215dc902e05a82734b801f86c2bd420142', FALSE, NULL),
  ('85ecd41da4fb57e5', 'client', $s213$<color=#FFD94D>Tournaments:</color>$s213$, 'd93c51495c04409d37e36b4dce1930a45ce9de61', FALSE, NULL),
  ('8618c3d156db5aa5', 'client', $s213$Common$s213$, '7de90a65241a6cdbd9ade485d777715d99285a1e', FALSE, NULL),
  ('86369abfe6bb0dd4', 'client', $s213$<color=#8899AA>1 - 2,000 gold</color>$s213$, '8b5f2ed9c71b4f4d439f18f5e87d00c642ab65a5', TRUE, NULL),
  ('8652c96055f60c8c', 'client', $s213${0}: <color=#888>(not bound)</color>$s213$, '2968d53cd798cf7fb980789d461ea11b3a0d2aa4', FALSE, NULL),
  ('86a17d42b414bd16', 'game', $s213$Eyes$s213$, '62be7f51429e4e104e01fe3131805c3195ede1d0', FALSE, $s213$StringTableDefault/CATEGORY_EYES$s213$),
  ('86ab357492065501', 'game', $s213$Versus$s213$, '6c2a9ad9d5afa593beebde44fdababc7ff75a34e', FALSE, $s213$StringTableDefault/BUTTON_VERSUS$s213$),
  ('86aba1ed8b31ffb9', 'client', $s213$<color=#888><i>Nobody has earned this yet. Be the first!</i></color>$s213$, '9c70ce915a157bec860acbb486261f358ee50449', FALSE, NULL),
  ('86c12d3915d8a3fe', 'game', $s213$Demonic pact$s213$, '493f137ec26e3c4890c0428655f2eb36f1e390fd', FALSE, $s213$StringTableCards/CARD_DEMONIC_PACT$s213$),
  ('8705eacf4540222f', 'client', $s213$Signed up for tournament$s213$, '6c2863573ff2c669344d201e3e7677616346d856', FALSE, NULL),
  ('8709d2a7417a8af1', 'client', $s213$Search Random$s213$, 'fb043b0389a26d7aed0805a82374ca520672afa6', FALSE, NULL),
  ('8730307706a420b3', 'client', $s213$Match recorded$s213$, 'f30dff73c6d29fd03731fcf0d22aee0f7b19ab52', FALSE, NULL),
  ('8746ab9f9b6503e4', 'client', $s213$Render your name at 80% size.$s213$, '1c9cc5f67a8641039f1e6e54ad1f7adec3a9c7c9', FALSE, NULL),
  ('878cbf198b4c88e0', 'client', $s213$A deep blue mouse cursor.$s213$, 'ad047b0b34bba2c06aa7eaf784f0aa9c665c11bc', FALSE, NULL),
  ('87a67ab6de450391', 'client', $s213$Update failed — couldn't save the updater. Update manually from GitHub.$s213$, '551a4339d7ce4a648c8047eff421de9e2b83d944', FALSE, NULL),
  ('87ca1318e268efac', 'client', $s213$<color={1}>{0}</color> <color=#888>— match telemetry</color>$s213$, 'b25566068f7a1de5405117c1faedecb7c5f826a6', FALSE, NULL),
  ('87edb6ceb5f1e62f', 'client', $s213$< Newer$s213$, '92199f3eb03e1fe3f9cbb34338d9f8f1f34e3b96', FALSE, NULL),
  ('87f5c64d95c1513d', 'client', $s213$Hide Gold$s213$, 'd393cc8c5a9dfa381e77aa7f447053858f2910bf', TRUE, NULL),
  ('885802821e8af4f4', 'client', $s213$<color=#888>Leaving queue…</color>$s213$, '875ba602929e490fa025f4fab86ce7d1bcaa9674', FALSE, NULL),
  ('88a3763ecd68c926', 'game', $s213$Slightly smaller$s213$, 'd2ae97a6f9a1028baa25b15030d29e626167e46f', FALSE, $s213$StringTableCards/AMOUNT_SLIGHTLYSMALLER$s213$),
  ('88bde4fad5c5ecd8', 'game', $s213$MAYHEM$s213$, '0f04a4b49adbb4532514eaae422ea58bac4112a9', FALSE, $s213$StringTableCards/CARD_MAYHEM$s213$),
  ('88d9415535dd3e6d', 'client', $s213$Pink Name$s213$, 'b6744ad14e80c3f4975d1874d4abeac76118559c', FALSE, NULL),
  ('88e636ffe6099863', 'client', $s213$Win 50 ranked series in a row$s213$, '7f8c92d2df2ed7b9d2de661abde38c650a78b757', TRUE, NULL),
  ('88f039c46bf3aef2', 'game', $s213$Online$s213$, 'c3e839df608469149df1ef34a1c9bb26b62b5452', FALSE, $s213$StringTableDefault/BUTTON_ONLINE$s213$),
  ('88fd0dc2b471baea', 'client', $s213$Prismatic Wake$s213$, '04a4408655caed1756da3dd8fddd01e0563e0a94', FALSE, NULL),
  ('89014b0c6a59a3a5', 'client', $s213$Stats$s213$, 'be763e9aba2af6b8baabada85d5e26c043c93fed', FALSE, NULL),
  ('892f1b97985931c1', 'client', $s213$Spray and Pray$s213$, 'c5db1144d4106184ee6562dda8f16d44f9d21068', FALSE, NULL),
  ('895fec08427896c1', 'client', $s213$Steam ID not ready yet — try again in a few seconds$s213$, 'b9569b433797c5bc74d5184f5ead8ef83695cec6', FALSE, NULL),
  ('898597131b854727', 'game', $s213$简体中文$s213$, '93659150d0e56377fc3a57cb9bb7d958fd637a74', FALSE, $s213$StringTableDefault/LANG_CHINESE — 2023-10-23: Replaced the unlocalized name with its translated version$s213$),
  ('89a698611907f9ec', 'client', $s213$<color=#D8A7FF>FFA History</color>$s213$, '2fa2251cb22a70a509d217abe8ec11e024e0aaae', FALSE, NULL),
  ('8a4c4be43c067b23', 'client', $s213$Ballooniphones$s213$, '63b68012cb0fa6028ec65f7f56bd1e09a7ecad78', FALSE, NULL),
  ('8a633c693695b715', 'client', $s213$A radiant golden sunburst. Blindingly righteous.$s213$, '5393acd21dc5762f827bd626eb1baa00e2a5f856', TRUE, NULL),
  ('8a9eeeb61d6172d8', 'client', $s213$Bet placed: {0}g{1}{2}$s213$, '6e38da544ee550b4c1c1ee181a958f6aa9b2dda0', FALSE, NULL),
  ('8aa3777be23776ab', 'client', $s213$Crimson Streak$s213$, 'e1d3d4a4ebd01690499f49db911a9f70902a7e8c', FALSE, NULL),
  ('8ab0cac8979c2a8e', 'client', $s213$<color=#99AAEE>Recently online</color>$s213$, '4f6b1c688d3001ecdab71a07919714cf0227e832', FALSE, NULL),
  ('8ab8f916e666eb1a', 'client', $s213$Pale icy blue, like a winter sky.$s213$, '998da40bba23a7b05d2c404389849f0f793b49dd', FALSE, NULL),
  ('8ac709afc941fd09', 'game', $s213$Bullets spawn bombs that explode after half a second$s213$, 'b66487b42373c8811e76677f9220c0611923c4c5', FALSE, $s213$StringTableCards/CARD_TIMED_DETONATION_DESC$s213$),
  ('8ae99931f06e822d', 'client', $s213$Browse open lobbies below, or create your own.$s213$, '0ad03cedb111af624eaf1c61118c7d5ca7ebabb3', FALSE, NULL),
  ('8b00982d542b583f', 'client', $s213$<color=#FF9988>Hit</color> {0}%$s213$, 'f48e8d83176749e28e622b50540c3ae0f29b907c', FALSE, NULL),
  ('8b51734bf0cceea4', 'client', $s213$Searing electric-green body color.$s213$, 'c2e5f7ff5a1b8a7c192fd6c5c49f8ff3a27c1d45', FALSE, NULL),
  ('8b5f2687f21600fb', 'client', $s213$5-0 someone with Chase$s213$, '7ac0188cbabf0fd05b7d9632be98fdd87d9a2909', FALSE, NULL),
  ('8b736b068bcaa904', 'client', $s213$Date format: <color=#88CCFF>{0}</color>$s213$, '08596d25c886c9f955df32042b64f4be840b7528', FALSE, NULL),
  ('8bcb3efd4061dec8', 'client', $s213$(loading...)$s213$, 'f28e610419f1325a85ac26b611cf6f96e8d60876', FALSE, NULL),
  ('8bdb5aaa3ae04a72', 'client', $s213$Date Earned$s213$, 'c58b1c0f2b7a976f48dbdb8ed79e649f25068847', FALSE, NULL),
  ('8c0133547ab53ad0', 'client', $s213$Wise beyond your years.$s213$, '05cb4b22604d22cab8e2fae50a1050c33fa3521a', FALSE, NULL),
  ('8c162f5acbf077d9', 'client', $s213$Chat  <color=#888>(press T to chat)</color>$s213$, '32c0692f72a53311bf1fdb49b83aaf1ba875f629', FALSE, NULL),
  ('8c303afe63579dd8', 'client', $s213$Storm Halo$s213$, 'e6dc9396aa17a023a695be860dd2f06ed4399346', FALSE, NULL),
  ('8c64a22bde49bfff', 'game', $s213$Block cooldown$s213$, 'c07d9b19ee315214241c27deef929d12e1be0e65', FALSE, $s213$StringTableCards/STAT_BLOCK_COOLDOWN$s213$),
  ('8c7e9c3d3b46e123', 'client', $s213$Update downloaded! Close ROUNDS to apply.$s213$, '3be557abee2dda3ad206f2e43fd11ca7e1ad1986', FALSE, NULL),
  ('8cad63c636cdcf6f', 'client', $s213$one font at a time$s213$, 'ff83a9a220be04b92113dda6c44401123dc40b01', FALSE, NULL),
  ('8cb4eac07551b7ab', 'client', $s213$Allow the mod to report your match results and stats to the community server.$s213$, '43555f317525b8d8043a88c97bc8432a0500d549', TRUE, NULL),
  ('8cc6d8d3d47ce7f7', 'client', $s213$Your Blocks$s213$, '0276f6c79774a509341d5391c2d18d92221b2cd4', FALSE, NULL),
  ('8ccfa9de20b7c034', 'client', $s213$Couldn't recover automatically - please restart matchmaking from the menu.$s213$, '295366d9ca40b6620c84fa1c9fce8a1a64cbb417', FALSE, NULL),
  ('8d3bc6bf3cb691f6', 'client', $s213$Cold violet and cyan motes swirl in a dark halo.$s213$, '4fac4cec0922ba3d0b40514b9e35526635575dcf', FALSE, NULL),
  ('8d3e5929f807c196', 'client', $s213$Bronze$s213$, 'af3102527f03c95d8e79825f965d8663c7fdf780', FALSE, NULL),
  ('8d4da05aac8b3d93', 'client', $s213$Pass rate (offered but not taken)$s213$, 'd1d9c15b7cec70ba637e349496b36e872f13c793', FALSE, NULL),
  ('8d72e526755bc717', 'client', $s213$Click <b>Search Random</b> to start finding a 2v2.$s213$, '99767352d7331ce5b7a9be4ca342d6b8d73171d8', FALSE, NULL),
  ('8dcd95733f0c2303', 'client', $s213$Pronoun title.$s213$, 'f33e1d33043740f2b9906fcb880abd6d11a6a22c', FALSE, NULL),
  ('8de6c27992aeba7b', 'client', $s213$Glossy volcanic-black body color.$s213$, 'acbaf66b3f491443e004f29007d7da47b05d138d', FALSE, NULL),
  ('8de9bc69b1fa7a20', 'game', $s213$Detail 2$s213$, '8d8e49016abeb10257cc8a87b2cdb720de04044f', FALSE, $s213$StringTableDefault/CATEGORY_DETAIL2$s213$),
  ('8def21f3d72fb6f6', 'client', $s213$Showing {0} of {1}$s213$, '4fc8a40beb83bfd8ca70c4d2a78a7cfdf518c7de', FALSE, NULL),
  ('8df13dd67b62c005', 'client', $s213$Enable Ranked first - the RLFP ping is for ranked matches.$s213$, 'feb0e5bf902bee5c1c71b9014353f7717948e8d0', TRUE, NULL),
  ('8dfae9b58d919fe0', 'client', $s213$Huge$s213$, '32978fbe93d3be31d803d0f25bc182a893e9a2f2', FALSE, NULL),
  ('8e209f74638dbafd', 'client', $s213$<color=#888><i>(This card's effect isn't a number - read the card description above.)</i></color>$s213$, '23254fd9dd2f5f8dc320a34ecb2cfaea96d2eb49', FALSE, NULL),
  ('8e2573140ef55a27', 'client', $s213$Bubbles$s213$, '58356fb4cac0b801f011b397f9dff45adb863892', FALSE, NULL),
  ('8e3dc78d1bfc533d', 'client', $s213$Couldn't reach the server - retrying in the background.$s213$, '55b12af2f1fc56486ff3c27b5e32668306a5b9f8', FALSE, NULL),
  ('8e4bd5a8e9eec6ae', 'client', $s213$one typeface at a time - modded players only$s213$, '0570f3e02cc6e225a109dc75f565ed8681b8252e', FALSE, NULL),
  ('8e5062f3dfe20e9a', 'client', $s213$Gift$s213$, '8d0a32ed63390771166c129d77e7019ed5faf21b', FALSE, NULL),
  ('8e9e659354925cdc', 'client', $s213$Leave All Queues$s213$, '0079a58339aa6045be471f8a0850cdbdbe1ee2b9', FALSE, NULL),
  ('8e9f5c5b8f417285', 'client', $s213$Ranked Form  <color={0}>{1}W-{2}L</color>$s213$, 'debb4916739eaee8059bb06b20b9668167be4310', TRUE, NULL),
  ('8ed72e941d7dcbde', 'client', $s213$Reverse a ranked 1v1 series$s213$, 'ec6c6716f30d035b002548cf9e1db208386774b0', TRUE, NULL),
  ('8f40cf6222ae1cf0', 'client', $s213$<b>Admin Panel</b>  <color=#888>(admins only)</color>$s213$, '3cca33596bd837c6a34cb127d9af34df91da4a62', FALSE, NULL),
  ('8f6303a38f0e3f52', 'game', $s213$Ready$s213$, '20c7c5522fc28c5817550dd82bc3272eb6a991c7', FALSE, $s213$StringTableDefault/PROMPT_READY$s213$),
  ('8f7d96d5e823b55f', 'client', $s213$Winners$s213$, '1d50bf1d8b44e075c6690ac4d150713976be836d', FALSE, NULL),
  ('8f901a543698298d', 'client', $s213$Max {0} players$s213$, 'fe604db7833da029b6d91b9e285ed91762c30526', FALSE, NULL),
  ('8fc96ffa03aaafbe', 'client', $s213$Sunset Gradient$s213$, 'e6e56698abc25872406e861b0aa5e10015632ae8', FALSE, NULL),
  ('8fec4bc289417df0', 'client', $s213$Halo$s213$, 'f3681d8bf189692334f17228e4c6f6976fc76e68', FALSE, NULL),
  ('8fff31eb51a2e6ee', 'client', $s213$Achievements unlocked$s213$, 'a50b9dbf33783b0f870ae078af30d1dd7c756577', FALSE, NULL),
  ('903bd2d1530486a8', 'client', $s213$Win a game without moving or jumping$s213$, '7ff9c6a9ec21ae6eee1aa022097cc772d6981aa5', FALSE, NULL),
  ('9041d79180a7885a', 'game', $s213$SHIELDS UP$s213$, 'e01575b4fb24b245a5ea4b8c4c2f488477cb0e60', FALSE, $s213$StringTableCards/CARD_SHIELDS_UP$s213$),
  ('9065d0a94556a6f9', 'client', $s213${0} searching$s213$, 'e515dbabaae121a13462690c0904e09c4db7d0ed', FALSE, NULL),
  ('9098cedd9b6f8315', 'client', $s213$Camera screen shake on shots/hits/deaths. Full = vanilla. Reduced = softer, keeps the hit feedback. Off = a perfectly steady camera. Local only.$s213$, '30134da01318f2520601f331d7a7ad2967d0af9b', FALSE, NULL),
  ('90c59f6f9a2fdb41', 'client', $s213$Heart Eyes$s213$, '48ee9e4fba600c1e5238b5b30afe832cee3f4452', FALSE, NULL),
  ('90d0551d9d3aec2a', 'client', $s213$Premium: cold silver walls that glint to pure white, over gunmetal dark$s213$, '2fd710fc7265cbfa6686c3f0b03de6975d70e6f7', FALSE, NULL),
  ('90df54c06a4560da', 'client', $s213$Other$s213$, '6e6a6f2086bb5fe5dbfd17d8d5f502d48759834b', FALSE, NULL),
  ('91796b933251df6c', 'client', $s213$<color=#EEEEEE>solid = {0}</color>   <color=#888888>dim = {1}</color>$s213$, '102200e3e75f1f63cb91b136385e50d3b8648dc9', FALSE, NULL),
  ('91af34b15810dcd7', 'client', $s213$Full log...$s213$, 'b13b4fc382a1c06e5100ffce87362532289efdb2', FALSE, NULL),
  ('91be82a18dd171cd', 'client', $s213$  ({0} in queue)$s213$, '62bc9bd22039bdff56e0bd4fcee58186d7e082de', FALSE, NULL),
  ('91d61c894d41c995', 'client', $s213$Sniper Medal$s213$, 'a3ad936a7ceda44469920ce62fe5947bde0aa040', FALSE, NULL),
  ('91dc11e808ee40a1', 'client', $s213$Deep royal purple, the kind that absorbs every photon.$s213$, 'cba6e53a33069151fb549a1f0e6934023b31955b', FALSE, NULL),
  ('920dfd8aa0a16e2e', 'client', $s213$Well played!$s213$, '58361b407af345d54448bd228158566a1d188ca7', FALSE, NULL),
  ('9234ccf14b5a0045', 'client', $s213$Galaxy Gradient$s213$, 'bf317bc7c73647140d56b21fbf2329d373e385cd', FALSE, NULL),
  ('9237062066f5d776', 'client', $s213$Smaller Name$s213$, 'bb79f3faedd4b8feda0906367e3938079bb3cd8c', FALSE, NULL),
  ('928589c9dfa0518c', 'client', $s213$Multiplayer$s213$, '21bd0337ae7922983486f37b7c1fea1c1a9c14eb', FALSE, NULL),
  ('930d340d5de3eafd', 'game', $s213$Half Blue$s213$, '40b746d43e17c67de98407d8d7f0a76a389bca04', FALSE, $s213$StringTableDefault/PROMPT_HALF_BLUE$s213$),
  ('933906c0a8b7a70f', 'client', $s213$Block debug overlay (corner): blocks you started vs blocks that actually absorbed a hit, plus why each one missed (too early / too slow / unblockable).$s213$, '9393db627b5e19257ba529826c55d7246cc0dca5', FALSE, NULL),
  ('9342dc04639e8c4a', 'client', $s213$Bet on which player?$s213$, '62e2e4c1ec4fb5744b5022aa1aa4e286a5f0d357', FALSE, NULL),
  ('936c8c700ad2e14e', 'client', $s213$A bright, sunny yellow.$s213$, '09760c239e5f1eaaaed919af1b3c0b4b59cde787', FALSE, NULL),
  ('937a7d64c4e5b069', 'client', $s213$Interface$s213$, '7b4db7ef1fa23cfb5e115a2a2c89d46a6a2ebc4a', FALSE, NULL),
  ('93cce73d376d842d', 'client', $s213$Delete a chat message - type to search$s213$, '13030ba667c11d4293b2cc90dd33bf612197ee3e', TRUE, NULL),
  ('9409ce3813df7c43', 'client', $s213$Aurora$s213$, 'eeee9b76ec5d1cfa27c511f2def4981c9c5b667c', FALSE, NULL),
  ('94289445357e1566', 'client', $s213$Echo main$s213$, '4899aea0ad7311f429c135299da2adc96ca17eda', FALSE, NULL),
  ('946a03bb72a4fe72', 'client', $s213$Immortal$s213$, '599812412c8e063215968af7cc448d65f2b3faa9', FALSE, NULL),
  ('94816db7715ff443', 'client', $s213$Password (share it with friends)$s213$, '29f453def2a2e1cf0ecf97c82e500a959343939f', FALSE, NULL),
  ('948adf594528007a', 'client', $s213$Rating$s213$, '6437b7bf655854909262d5f53fbe3bc7a6665b48', FALSE, NULL),
  ('949e54f8da1fbbb3', 'client', $s213$Grand Master$s213$, '0de1a3e213e5f886d02a66057987fc8a8fbd3036', FALSE, NULL),
  ('94d8eeb7835cacb2', 'client', $s213$<color=#888>Mod: <i>not detected</i></color>$s213$, '988e5666d9c440209aa8a616f309be4c3d8d7c7b', FALSE, NULL),
  ('94db66918d546008', 'client', $s213$<color=#888><i>Release notes unavailable right now.</i></color>$s213$, '631013e0362fd55c596915e3fe91b9e867fc6537', FALSE, NULL),
  ('94f1cace756e2725', 'client', $s213$Specter$s213$, 'e0ad3ab875f57eac75ebd47534939215a9b96daa', FALSE, NULL),
  ('951b9b16227f135f', 'client', $s213$<b>Game logs (tail)</b> — included with your report when the box is checked.$s213$, 'cd95b4632dc60bdec486a3611eed91c56d5736bb', FALSE, NULL),
  ('954e55728c5ebdb5', 'game', $s213$Steer bullet with right stick / mouse$s213$, '75753bf610345ff4b4900107c07fa3eef681f7cc', FALSE, $s213$StringTableCards/CARD_REMOTE_DESC — Xbox Terminology: right stick$s213$),
  ('95521f0cd0fac665', 'game', $s213$DRILL AMMO$s213$, '981988b465f43590b3f024711420ab51ba303b0a', FALSE, $s213$StringTableCards/CARD_DRILL_AMMO$s213$),
  ('955f576bcd5935c1', 'game', $s213$Slows enemies around you when you block$s213$, '958cf206bee03fc02e32bd57e886f30feb15b182', FALSE, $s213$StringTableCards/CARD_FROST_SLAM_DESC$s213$),
  ('9566e3ebe6920019', 'client', $s213$View channel$s213$, '3cf575503d0141f8791e89998e508076168963e3', FALSE, NULL),
  ('957d8be836adfa00', 'client', $s213$Next$s213$, 'bc981983e7f547dc62e19a1e383acfe00782a6d5', FALSE, NULL),
  ('95e4edfd85ad0058', 'client', $s213$No leaderboard data$s213$, 'eddf8963477756fa3f004564792411af5a20f827', FALSE, NULL),
  ('95e880d9ec642215', 'client', $s213$Manage your cosmetics and earn 30% on each paid purchase - gifts and your own buys pay nothing. Size or placement changes return to admin review; unsuitable art may be rejected or adjusted.$s213$, 'abf0c9e2bd591cf88dfd596663185ee446929460', TRUE, NULL),
  ('95ebb11b87cdd04e', 'client', $s213$<b><color=#FF6688>* Live 2v2 Series</color></b>$s213$, '0143f1c8ceedf9023223f7101de313a2e03ea3fc', FALSE, NULL),
  ('95f4cbc38f450bc9', 'client', $s213$A deep, earthy yellow.$s213$, '841134a9aa1e8b90a49cb4c5b535ebb37e812e5a', FALSE, NULL),
  ('9627e7f6ba78de6b', 'client', $s213$Win a ranked FFA 5-0 with 5 or more players (nobody else takes a point)$s213$, 'bdbc3e58e6cd0fa0f137fc0a2b5142a105ca4788', TRUE, NULL),
  ('9633ce2741a0b7cb', 'client', $s213$Demolitionist$s213$, '3d44114e197112dc928b1b5e54ab7c91d191dd29', FALSE, NULL),
  ('964287e89050ad74', 'game', $s213$TASTE OF BLOOD$s213$, '66436cc2f7f9253f178561921da7ebd06d6cad25', FALSE, $s213$StringTableCards/CARD_TASTE_OF_BLOOD$s213$),
  ('9643b3e6281b9dcc', 'client', $s213$Master$s213$, '78f3842f0201c993fec13905f2ff9ec3fdd39056', FALSE, NULL),
  ('96bbbba49c28ed43', 'game', $s213$+200% HP 3s after dealing DMG$s213$, '4cf72f0360afeabe6839c60a545d8afa8f8c8b64', FALSE, $s213$StringTableCards/CARD_BRAWLER_DESC — Health Points, Damage$s213$),
  ('96ed0e7311a525a3', 'client', $s213$Cobalt$s213$, 'c509eac2111b5bd8b67314feb259572255c6f6cc', FALSE, NULL),
  ('97048d0dbba0b0ad', 'client', $s213$A rich, warm brown skin tone.$s213$, '6b92c53eadd095e5577c7c13641831ea4e80d518', FALSE, NULL),
  ('970796f2ee569bbc', 'client', $s213$Sapphire$s213$, '52086129a3b5fc408aafd7614d3de4b7de05c35a', FALSE, NULL),
  ('9711b68fef7e1eb9', 'client', $s213$Shop$s213$, '55de88709232ec03a7618ceae9b2248419fdc862', FALSE, NULL),
  ('9725a834b50f6946', 'game', $s213$FROST SLAM$s213$, '82ff102374c8ed60f1e51721cc6396e8c3ef3512', FALSE, $s213$StringTableCards/CARD_FROST_SLAM$s213$),
  ('975079e2e5226011', 'client', $s213$<color=#888>(none right now)</color>$s213$, 'cd2e09e54b4c40bc15a7973607cf97f92f11742f', FALSE, NULL),
  ('979f21663871da12', 'game', $s213$Bullets deal damage over 3 seconds$s213$, '7c50b022cbbe130e1acaa569843fb7c6fea512d6', FALSE, $s213$StringTableCards/CARD_POISON_DESC$s213$),
  ('97af61d8389c2364', 'client', $s213$(no previous-session log yet — gets written by the mod when ROUNDS is closed cleanly, so on first ever launch this is empty)

Expected path: {0}$s213$, 'fbcf4b3dcfbb44db1dbf490faaf83040b2bdeee5', FALSE, NULL),
  ('97b2232a5765faa8', 'client', $s213$RLFP Ping$s213$, 'd405f3f3916bbffcbf17431e5a7a548cb15320cf', FALSE, NULL),
  ('97ba222b4778e023', 'client', $s213$Chat mutes - type to search$s213$, '12d0c6e09634a234a341926502ca2c0403d6ebb4', FALSE, NULL),
  ('97bf484344ec2873', 'client', $s213$Colorize your name in pink.$s213$, '2ec2ab8e8e10dd4bac423d81ba3df5fb10f5a85b', FALSE, NULL),
  ('97eed477558a8ce8', 'client', $s213$<color=#AAAAAA>Reports go to the mod team. Be specific — what happened, when, what you were doing.</color>$s213$, 'cdedff3bd78198557df9dfac25d6db4d5e4f0d8c', FALSE, NULL),
  ('9808e56f61cea810', 'client', $s213$<color=#88FF88>Sent! Thank you.</color>$s213$, '3d51ed996dee97375f2a58108ab35dd1d4c07482', FALSE, NULL),
  ('984d68e9a86f1e92', 'game', $s213$Fire many bullets at the same time$s213$, '6da9fab9c4bc66166d0ad99277842237b8a79d37', FALSE, $s213$StringTableCards/CARD_BARRAGE_DESC$s213$),
  ('986b75b09a88bcc4', 'client', $s213$Link your Discord account first (Home tab) to use RLFP pings.$s213$, '9a079643ddf3158131c3009521073761bd7ef4fa', FALSE, NULL),
  ('98a3fad8f87afa66', 'client', $s213$How It Works$s213$, '8cecc82d72d68f9151cb0901cfe40eeac15bfca6', FALSE, NULL),
  ('98e3859cbd3ba125', 'client', $s213$Flag marked as confirmed.$s213$, '6d56e1c35678ccc6ae1324012172bb5876774aa4', FALSE, NULL),
  ('9914bb866193f854', 'client', $s213$Home$s213$, '70f8bb9a8a5393ef080507a89e4b98d139000d65', FALSE, NULL),
  ('993e08b5d2c4f5c7', 'client', $s213$Self-Inflicted Deaths % (boundary + own bullet)$s213$, 'c9d191ab8825e1463b0e2f91bdd314cd2bf88b0c', FALSE, NULL),
  ('9985a0d2f6e36dc7', 'client', $s213$Team: Any$s213$, 'f29811bf00e4e54584f121a0460cacd3fd862599', FALSE, NULL),
  ('99a1c6367212642d', 'client', $s213$<color=#FFB347>solo won</color>$s213$, '50fc7f597d225aa9330d5d5c4c309e5a30070477', FALSE, NULL),
  ('99fb1e843ffa48b1', 'client', $s213$  <color=#7FDBFF>|</color>  <color=#AAAAAA>{0} online</color>$s213$, 'b6de50bf861dc8814de845b4ea604d7139f92ae4', FALSE, NULL),
  ('99fe63301300574c', 'game', $s213$SHIELD CHARGE$s213$, 'fd39ea1533bf5cbae0a8f95fef32b3dd3fcff7eb', FALSE, $s213$StringTableCards/CARD_SHIELD_CHARGE$s213$),
  ('99ff755f76298b3a', 'client', $s213$Block$s213$, '82dd2cdf36f9436d89f404454654ad3e53fd428d', FALSE, NULL),
  ('9a146c1abc14a051', 'game', $s213$Waiting$s213$, '33d30632848d3fd0ed2340adbd7be3e3e8e61010', FALSE, $s213$StringTableDefault/PROMPT_WAITING$s213$),
  ('9aa15709e7599312', 'client', $s213$Opponent failed to join — returning to menu. Requeue when ready.$s213$, '1d82b1402be0f0e5cdcf5c6bfbb510b84cf551d3', FALSE, NULL),
  ('9acd5548c4af6f72', 'game', $s213$Blocking silences enemies nearby$s213$, '601a761df2846692cecc9620f5b5b51386fba28d', FALSE, $s213$StringTableCards/CARD_SILENCE_DESC$s213$),
  ('9acf80614042428d', 'game', $s213$Maximize Window$s213$, '202a9d0d5201007a969ade291e676a04ac106223', FALSE, $s213$StringTableDefault/OPTION_MAXIMIZEWINDOW$s213$),
  ('9ad25dd88adfebfa', 'client', $s213$Alien Antennae$s213$, 'cee5ec293ece08f8b8d87a2b278c5a6bcd35fe37', FALSE, NULL),
  ('9afbb108fc3616ee', 'client', $s213$Why is {0} being muted?$s213$, '8f838a7b9a41c37488c3198ef9d9bb91e2882c3e', FALSE, NULL),
  ('9b151c658a5ec994', 'game', $s213$Русский$s213$, '5537fc8e69d7e9830f739eb94071c2212b4027ad', FALSE, $s213$StringTableDefault/LANG_RUSSIAN — 2023-10-23: Replaced the unlocalized name with its translated version$s213$),
  ('9b1e4c75087fb1f8', 'game', $s213$LIFESTEALER$s213$, 'c52dbdd11a2ef54e34f56252333f2573f2a08c95', FALSE, $s213$StringTableCards/CARD_LIFESTEALER$s213$),
  ('9b6756e2e3392101', 'game', $s213$Waiting for friend$s213$, 'd0481d10e87426be70e916ceb26124fd75be3f9e', FALSE, $s213$StringTableDefault/PROMPT_WAITING_FOR_FRIEND$s213$),
  ('9b898dc5487d84cd', 'client', $s213$Submitting...$s213$, '46a1a6919d196b4d95a74a37cc19f2ed4c66d0eb', FALSE, NULL),
  ('9c494c7f25abb2c3', 'client', $s213$Trans pride colors with particle sparkles.$s213$, '502598c638643dedcad27c187b7569ebb08e4615', FALSE, NULL),
  ('9c528b8f8d623258', 'client', $s213$Detail: heavy is the head. Equip in the Character editor.$s213$, 'd35ece05488a58ed9adbf2fd9423a0e4bd0c206c', FALSE, NULL),
  ('9c7b9e8923006966', 'client', $s213$A vibrant green between Gold and Cyan.$s213$, '2b5232add8ebb0b0b10d3340988527aba0746bcd', TRUE, NULL),
  ('9c9228360f345cff', 'client', $s213$Your picks$s213$, 'f8acd4ea8b53c8e63f98ea885d48befcc946b1e1', FALSE, NULL),
  ('9c9b2f5a2d506195', 'client', $s213$Avg Mate Elo$s213$, '122a68a5ef9fadcd527704d0d89be3776ce44871', FALSE, NULL),
  ('9cab5fc40afc9b86', 'client', $s213$Bet$s213$, '40880286482e1363c39814b2ce3d66651ef98349', FALSE, NULL),
  ('9cb79e28fba384b2', 'client', $s213$Create Private 1v2 Lobby$s213$, 'f908121ac9e34b2d0a9e9cdfd8d8014cea010503', FALSE, NULL),
  ('9d033a263ddf51d5', 'client', $s213$<b>Recent Casual FFAs</b>$s213$, '1f710e4b0e713951c4646e1f85cdf30df5e941b9', FALSE, NULL),
  ('9d3a2b5d82d50d94', 'client', $s213$Couldn't join the queue$s213$, '2197066bc8988e5594dd0acffb78593cd79b43e8', FALSE, NULL),
  ('9d4b0c7cd2d8e0ec', 'client', $s213$Finish or leave your current game before joining the 1v2 queue.$s213$, '53a962a3ba05b581c9979e4983949df4258c0026', FALSE, NULL),
  ('9d4c37736ff9f3b7', 'client', $s213$<b>2v2 Leaderboard</b>  <color=#888>({0} ranked)</color>$s213$, '34daab9d40d35ab456c9e77cc9ccc2f623be684a', TRUE, NULL),
  ('9d6041fbc550ee63', 'client', $s213$Synchronizing - viewing begins next battle$s213$, '2eb822ed968828545908f7861d809bcd44850127', FALSE, NULL),
  ('9d675c20af88ac85', 'client', $s213$EdgeBounce NRE swallow$s213$, '29ff1525ee6fdd2e6fd0e55e379a4e224f5776e5', FALSE, NULL),
  ('9d8c564216c4fca8', 'game', $s213$Victory!$s213$, '25296a531b53ddf34c2ed0da107c44afa1167d07', FALSE, $s213$StringTableDefault/PROMPT_VICTORY$s213$),
  ('9d92b32fc6bd63f4', 'client', $s213$Cosmetic Reviews...$s213$, 'fa8c098d8f7e544d019a8621d1fafe84fc8f4188', FALSE, NULL),
  ('9d9a02388f682516', 'client', $s213$Soft pink body color.$s213$, 'f7bce6256e4c4cbfffd0c61e2708265490027f17', FALSE, NULL),
  ('9da49dab4e160e9e', 'client', $s213$Your opponent is banned from the mod - leaving match.$s213$, '9928a61ba2ff67208eefea21eb021f851ef71662', TRUE, NULL),
  ('9e1369ddd08e1d16', 'client', $s213$RANKED - Recording$s213$, '6ad85c9fff5b14b6cf3d9aae3688c935e8f4cbe6', TRUE, NULL),
  ('9e3df6c9efe7a876', 'client', $s213$Side: Any$s213$, '928414d3088da4bcd44cf4682de27b4a7a01317b', FALSE, NULL),
  ('9e63f090e317f40c', 'client', $s213$Buy$s213$, '7ceca51fcafe42567c1c49ed6ab3604d7c962875', FALSE, NULL),
  ('9e6e059ee1f6f9d8', 'client', $s213$  <color={0}>Game streak: {1}W</color>$s213$, '131ff12826d9ed6fe685a77c1fbee5a166346b70', FALSE, NULL),
  ('9ef2d087c80357dc', 'client', $s213$Bursts$s213$, 'c3523aedb7179f0f1ed0e80801a4c320b1e398fa', FALSE, NULL),
  ('9eff451fa8b7f65e', 'client', $s213$Attach game logs (recommended)$s213$, '67d0b166e08a2db71d9486f96ac1bb9a2c9ad486', FALSE, NULL),
  ('9f0ca6838edea649', 'client', $s213$<color=#88FF88>Profile anonymized. Data reporting is now off; past matches stay.</color>$s213$, '6a39a247e137ecd2bc8324bbc4a98b4031f0fe11', TRUE, NULL),
  ('9f1db78d42bdc3b7', 'client', $s213$<color=#FF4444>UPDATE REQUIRED</color>$s213$, '7438392c1065e86ecd48fa2fcff8e7d82b51bd77', FALSE, NULL),
  ('9f1e5c442c451f91', 'client', $s213$MATCH POINT - {0} is half a point from the win!$s213$, 'c9f79b176fc44a3c38255b25082c7f51e315190f', FALSE, NULL),
  ('9f57ff0905238412', 'client', $s213$Clean Trail$s213$, 'a3b330fc7dec25ff7c2417fdf084196120632e2b', FALSE, NULL),
  ('9f62981453f64b39', 'client', $s213$<color=#C48CFF>FFA:</color> {0}W / {1}L ({2:F0}% win)$s213$, '70ae4797d016b4c6d8c1dba02cc9c83aac00df86', FALSE, NULL),
  ('9f6ba43f78157173', 'client', $s213$Prizes$s213$, '4a4300888933d180d78056ae2875609cc168712b', FALSE, NULL),
  ('9f872c3b36543248', 'client', $s213$watching$s213$, '874e70e6ab4d774bd2950cff37e0f6d516a63a5d', FALSE, NULL),
  ('9fac189ff37e47b3', 'client', $s213$No recent series$s213$, '29ac10d1f29b9a817ad176f846413aba22dcb719', FALSE, NULL),
  ('9fc067aacc4b389f', 'client', $s213$Neon Violet$s213$, '25e66746dc67e99386bfd26e11749d59a7a08c7e', FALSE, NULL),
  ('a095bbad6cb4b1cd', 'game', $s213$SFX volume$s213$, '7418091711590856caa989340bb1dac687a9f70f', FALSE, $s213$StringTableDefault/OPTION_VOLUME_SFX — Sound effects volume$s213$),
  ('a0a84bb37b74480c', 'client', $s213$<color=#888>(in progress)</color>$s213$, '4623a6a3410fc70b8cc383dcf0a6cb4c4f933517', FALSE, NULL),
  ('a11c16b210120f55', 'client', $s213$<color=#888>Loading…</color>$s213$, '2552c92999af87111790f7a90d41be061c01da98', FALSE, NULL),
  ('a1244673752f5b09', 'client', $s213$<color=#88CC88>-> {0} bet {1}g on {2} -> <b>+{3}g</b></color>$s213$, '63e3488e68c75920133d1af00d41414a0297f6b5', FALSE, NULL),
  ('a13104d1f01151a6', 'client', $s213$Hit-sound NRE swallow$s213$, '7d45cd2bcca78ca9b078914744db3bdc40609f21', FALSE, NULL),
  ('a13ace4753916354', 'client', $s213$<color=#8FA3B8>{0} fps</color>$s213$, '794de690ee3249fb9aff60d3748de5b98a0f7388', FALSE, NULL),
  ('a13c00bda9999966', 'client', $s213$Win a ranked FFA 5-0 with 4 or more players (nobody else takes a point)$s213$, 'f42664a4f550e9c09802217faaead6fb06d950cb', TRUE, NULL),
  ('a13da205cf3e6b93', 'client', $s213$Type !link CODE in Discord$s213$, 'de6c0edd74bd11469c959c7269b1894c011895fc', FALSE, NULL),
  ('a14b37e38fc546ec', 'client', $s213$Delete chat message$s213$, '0e629a058d09bbfb532b8e03465452fb92425570', TRUE, NULL),
  ('a18255a7c68182e3', 'client', $s213$Crazed Eyes$s213$, '52b4f7979734d5a9daa6702b008bc4dd1047377f', FALSE, NULL),
  ('a1b12781f1dcf408', 'client', $s213$Premium: northern-lights walls shimmering between polar teal and violet in a polar night$s213$, '381ae69d6dec239a744146b21683d1da1f3ef1c0', FALSE, NULL),
  ('a1b5a04f8d591cb8', 'client', $s213$Preview logs$s213$, 'd42e29e77884854a5e8b41eb4d0996d9758c52e4', FALSE, NULL),
  ('a204547475823743', 'client', $s213$Life steal$s213$, '417f106adb9eb8a88f7f754dff056d4ad92f62fa', FALSE, NULL),
  ('a21309559a923a8c', 'game', $s213$Bullets have thrusters that push targets$s213$, '8b76d9f6d1734fe097d6b5b82addc77bfcbca8db', FALSE, $s213$StringTableCards/CARD_THRUSTER_DESC$s213$),
  ('a244b647cf231b38', 'client', $s213$Casual (games)$s213$, '22189563e809c4944aac68940714bc157ddcba63', FALSE, NULL),
  ('a2667beef62b6d0c', 'client', $s213$Living on the Edge$s213$, 'ece6bccb7dadb22b3b86139b68efb42a8ea3c7c1', FALSE, NULL),
  ('a2702c0ad7e96b07', 'client', $s213$Keep watching$s213$, '6fbe1fba437a2e21a359398c39005cb4b8e76491', FALSE, NULL),
  ('a28f48411a5bcb0c', 'client', $s213$Lucky Clover$s213$, '939ab68bfd22b3400b502c8401ff4be78f05031e', FALSE, NULL),
  ('a29939fd5310702c', 'client', $s213$Colorize your name in green.$s213$, '378e60aaa1606276e4ecbe32a4488f37421a3a4a', FALSE, NULL),
  ('a29f86876ba4a433', 'client', $s213$After 60s unfocused at the menu, drops the engine to 15 FPS. Never active in online rooms or when a match is found; wakes instantly on focus.$s213$, '2a58a099d42258b34d81bba814b8b531cc638c51', FALSE, NULL),
  ('a2bbca7fa2249434', 'client', $s213$Reconnect to Match$s213$, '8386805ac1a372885719e9a22b45ad0ee7a6a723', FALSE, NULL),
  ('a30778fa3d629f33', 'client', $s213$Displays your live rank tier (updates automatically as you rank up or down)$s213$, 'b7453a2df406d0e7a753fa2a13a759aea4dd2294', FALSE, NULL),
  ('a3167976ce15fa39', 'client', $s213$Rampage$s213$, 'a3efb7df8f742e808e896ac1c37a46b8f2c8547c', FALSE, NULL),
  ('a36511ec6cccf2af', 'client', $s213$Gold$s213$, 'c57604db5869f60539c66f7caa4809f27133d314', TRUE, NULL),
  ('a37a7555118c2dae', 'client', $s213$Name Styles$s213$, 'accb4a8ddf0f4d799e252e947a9e7c1de73a8dd1', FALSE, NULL),
  ('a380719c62368c34', 'client', $s213$Chat notifications: <color=#FF9966>OFF</color>$s213$, 'b377a298478828076e8b6b4f4be229a2b8478521', FALSE, NULL),
  ('a39999e17f4758a1', 'client', $s213$Place bet$s213$, '96ef7f60b0e12322ce4490d8ea26c66eb5e0576c', FALSE, NULL),
  ('a3e748141eea4dda', 'game', $s213$Quit$s213$, '1a2285d8881f226e13430515a9dd2b9fb6294200', FALSE, $s213$StringTableDefault/BUTTON_QUIT — Close the game$s213$),
  ('a463905a21f99458', 'client', $s213$<color=#666><i>No live ranked series right now.</i></color>$s213$, 'c37ace37eb278bbb801475948e3df81925c3dcc0', TRUE, NULL),
  ('a48aabea4f23dd8e', 'client', $s213$<color={0}>blocks activated</color> <color=#888>·</color> <color={1}>blocks successful</color>$s213$, '4cd08e5b924d614d8b7d2101d897878e723e183e', FALSE, NULL),
  ('a48da658c2be2d8d', 'client', $s213$Not enough players to continue the FFA - returning to menu.$s213$, '337636a6937781e64b036aec8af783146cbaf3c0', FALSE, NULL),
  ('a48e13d370e30ad1', 'client', $s213$Lives$s213$, 'ce6afbd4b60bf8dfe8e4a2a6327ac8598e740559', FALSE, NULL),
  ('a499e490a762a41a', 'client', $s213$Locks the map to ROUNDS' Sweden palette (blue + yellow).$s213$, 'c2cb065aefa60150ca2e076e295363c45308b3d6', FALSE, NULL),
  ('a4d81bd7fbd09eff', 'game', $s213$A huge amount of$s213$, 'cce292ce06a96fe2893d663fb2e7510e849218c8', FALSE, $s213$StringTableCards/AMOUNT_AHUGEAMOUNTOF$s213$),
  ('a5213a20493acf09', 'game', $s213$Host$s213$, '3960ec4ca5fb5e5d8cdb2cc1c5121c003e426517', FALSE, $s213$StringTableDefault/BUTTON_HOST — Verb$s213$),
  ('a55f45e878c399c3', 'client', $s213$Mouth: sewn shut. Equip in the Character editor.$s213$, '1e7a29d5061a52a7f293263e92f9a5aba4275e1e', FALSE, NULL),
  ('a593067a8ec0d1b5', 'client', $s213$Revoke Artist...$s213$, '633f1246d9f9fb9ac561e393879b8a28b0bc7814', TRUE, NULL),
  ('a59a55265cfb11eb', 'client', $s213$Lime$s213$, '7e845d62d2ff38633cd16021f0b03eb78640abe0', FALSE, NULL),
  ('a6027f92c31ba8ae', 'client', $s213$ at x{0}$s213$, '2446ef58482e38247e7a667e3e9d471dd04f3d0b', FALSE, NULL),
  ('a62668dd4b76a121', 'client', $s213$Create Private FFA Lobby$s213$, '3c1c959cd4d733eda596e5e262349e9e9caef386', FALSE, NULL),
  ('a65804c100e5f740', 'client', $s213$My Stats$s213$, '0cb450ece94fd1c07223dd69e80d9684937e8b96', FALSE, NULL),
  ('a68b1f17c3436d85', 'client', $s213$Glow (bloom): the soft halo around bright cosmetics, map art and effects. Reduced = smaller, dimmer halo. Off = no halo. Local only — nothing is hidden, the cosmetic itself still renders the same. A few items have their glow painted into the artwork, and that part stays.$s213$, 'a632ac0544d4b5dea727409a10ffa2a23c246da0', FALSE, NULL),
  ('a6a35197bee61edc', 'client', $s213$<color=#667788>none held</color>$s213$, '7a9481236d37894202154793757d34325a34387c', FALSE, NULL),
  ('a6a7046f4bb0c262', 'client', $s213$Your Block Rate$s213$, 'e03e13e5bb0bbe771dbd3eb0a4c64c1e041c0aae', FALSE, NULL),
  ('a6b6ef816a86dfbd', 'client', $s213$Your opponent never joined. Returning to menu - you stay ready, and the server forfeits the match to you if they don't show.$s213$, '57d3eb1060253f9b1b0ac4f595b7ca7fc35b74f7', TRUE, NULL),
  ('a6d07574629f099c', 'client', $s213$<color=#99B3E6>You: Hit {0}%</color>$s213$, '2e7ba4b2a8d879503b315cf86da06a7eef63cde3', FALSE, NULL),
  ('a6d88b76ef5d1086', 'client', $s213$WATCH$s213$, 'f187dbf97ca89e5c15383b3fa7d810b24a33323e', FALSE, NULL),
  ('a70f99966e0958b8', 'client', $s213$A crackling ring of living lightning. ANIMATED.$s213$, '3d27acca20b71363bd39579002d1e2d47ab735bd', FALSE, NULL),
  ('a719fac14ec5fa11', 'client', $s213$ObjectPool init clamp (in-match)$s213$, '72d696a4f4dc7c22c8686bf0360cf923d40de5aa', FALSE, NULL),
  ('a72ae56c0ded3702', 'client', $s213$Coral Name$s213$, '57a485e2451d558c03fa971091c39322dd7ab285', FALSE, NULL),
  ('a77c56b241124324', 'client', $s213$<color=#FFB347>2v2:</color> {0}W/{1}L$s213$, '7b102ce6e585783508febe4bddb64faf39b56156', FALSE, NULL),
  ('a7c09f9477311f3f', 'client', $s213$Neon Pink$s213$, 'ff2c0cb639d80711db062bae5aec601a4e61ce51', FALSE, NULL),
  ('a7fcf02867fbd4d7', 'client', $s213$by hit %, block %, ranked DPS, keys/sec and build-type mix$s213$, '651f6d70cd3ed3c066cebcf7be52166bbfa8091d', TRUE, NULL),
  ('a7fd3731ab075f9e', 'game', $s213$Slightly lower$s213$, 'ab87fc42ed5f4607ee3eedaaed654d8c65be9890', FALSE, $s213$StringTableCards/AMOUNT_SLIGHTLYLOWER$s213$),
  ('a8064a9ac9627e7d', 'client', $s213$You show up.$s213$, 'bfcb6f0bdfeaee7d87fac66f8d55ddb559b17ec6', FALSE, NULL),
  ('a82a78bd04c6f072', 'client', $s213$Win rate holding this card$s213$, '85c14bca8ee898db2c83eccfda879d9e0447a251', FALSE, NULL),
  ('a864fb68e6c542dd', 'client', $s213$Top Pickers$s213$, 'ae6dae198291b6d03a3f1f168f1e35ac35551a54', FALSE, NULL),
  ('a8834cee75e9ea18', 'game', $s213$TRICKSTER$s213$, '90c4b8a73c7bb53ccfced47868e1d46a633e3629', FALSE, $s213$StringTableCards/CARD_TRICKSTER$s213$),
  ('a8cde029eaa51955', 'game', $s213$Target BOUNCE$s213$, '2c43fb7e5e1cf0a6af307b0e14f36aed31de5420', FALSE, $s213$StringTableCards/CARD_TARGET_BOUNCE$s213$),
  ('a8d53a5354d4295b', 'client', $s213$Couldn't join the ranked match — please requeue.$s213$, '0e2c60155a4e9abfda0b24362270bd9977695975', TRUE, NULL),
  ('a8d697bbf97db263', 'client', $s213$Update failed — couldn't reach GitHub. Check your connection and try again.$s213$, '17fa6818aea10b37cf9fbfdd4a24e3f33f9526cb', FALSE, NULL),
  ('a8e7491399151552', 'client', $s213$Time's up - {0} picked automatically.$s213$, '698e542479926ac30ba7d470149597aaecb9e425', FALSE, NULL),
  ('a915f28966712ddc', 'client', $s213$Twisted Topper$s213$, 'fe369661beab47e8efc5972a9b686463867affe5', FALSE, NULL),
  ('a91acddb9c66607f', 'game', $s213$Left stick aiming$s213$, 'cb308c1c33d95a03cccaadca89fc64592851331f', FALSE, $s213$StringTableDefault/OPTION_LEFTSTICKAIMING_PS — PS Terminology: Left Stick$s213$),
  ('a95527c4eb90449a', 'client', $s213$Huge Name$s213$, '96096beb7426ce6ce5e38c347d4d90ad2a3f936b', FALSE, NULL),
  ('a9959f9679e83eae', 'client', $s213$Team 2$s213$, '60aff4035bca07e449351eb0f02141feadf9dcd5', FALSE, NULL),
  ('a9d50d7f27f69d23', 'client', $s213$Spectators ({0}): {1}$s213$, 'cf2b0afff61ccbb6fe42bdc5683912fcf1a7c736', FALSE, NULL),
  ('a9e4235a8b94ba63', 'client', $s213$Start Game$s213$, '365f992a0a10615ba2ae06d707bb66c9e6c66bbe', FALSE, NULL),
  ('a9fd32601c4651d7', 'client', $s213$Private 1v2 lobby$s213$, 'd67b2b5c07267670c3b6718695df939fe870078d', FALSE, NULL),
  ('aa2ab030a7e8ca31', 'client', $s213$Alert revoked.$s213$, '56ca995f75e4f3ad0f6d006eeec8862fbae7d5bb', TRUE, NULL),
  ('aa4e258db8b6ccf9', 'game', $s213$SNEAKY$s213$, 'e766fbb63609c13053ed95c2861eb92b6c3a1c9b', FALSE, $s213$StringTableCards/CARD_SNEAKY$s213$),
  ('aa62f023a76d12a0', 'client', $s213$  <color={0}>Streak: {1}L</color>$s213$, '43662c1f038c90a664be45e6511968bab3328abf', FALSE, NULL),
  ('aa6e72b3c95d1980', 'client', $s213$Hold on!$s213$, 'edcfe3cc16fde6891e557f59a48f9c2f1c2b4510', FALSE, NULL),
  ('aa96a51a1e9af834', 'client', $s213$GAMEPLAY$s213$, '9905006070eedb6ae48e11bb4b977e1ba02955c6', FALSE, NULL),
  ('aabf3a6bbef39977', 'client', $s213$Emerald$s213$, 'da32ecab00cdd3a4cfccfe58a62338d64fbe94a2', FALSE, NULL),
  ('ab0f98bd6a6bf5f1', 'client', $s213$Default$s213$, '808d7dca8a74d84af27a2d6602c3d786de45fe1e', FALSE, NULL),
  ('ab95166595686da5', 'client', $s213$In-game chat overlay: <color=#FF9966>OFF</color>$s213$, '747f336134ffc5ee335d36ce3ae94cebbd293a87', FALSE, NULL),
  ('aba91628ab0e4069', 'client', $s213${0} can now translate {1}.$s213$, '352e94ec0f7361050981402124252d03ad906990', FALSE, NULL),
  ('abc5b7574b8d23f1', 'client', $s213$Create Private...$s213$, '1cc92e26adf309a65f9715f72031f81420b4f7f5', FALSE, NULL),
  ('abd355e13a15e46d', 'client', $s213$Target Bounce main$s213$, 'f9fb8665cb51f149f63f06a976a3324713219468', FALSE, NULL),
  ('abe3b20d82427246', 'client', $s213$A hot pink mouse cursor.$s213$, 'e0b04f7776991125df7976fc25df6c378d7ee39d', FALSE, NULL),
  ('abf4f1283922dcc9', 'client', $s213$Cosmetics$s213$, '9555b604bb2b33b5e29fe2c53ae409befbe84d79', FALSE, NULL),
  ('abfd82940ef7a3a4', 'client', $s213$<color=#88AAFF>Type to filter</color>$s213$, 'd88dae34bc051ac23f54fe476b438db01f4ea9c0', FALSE, NULL),
  ('abffd73269054ce5', 'client', $s213$Choose a metric$s213$, 'f9491ed1720722bc9eb22d885d3f0ee467ac651a', FALSE, NULL),
  ('ac2ac9790f0283fc', 'client', $s213$Status: <color=#FF9966>Denied</color> - mod runs offline. No data leaves your machine.$s213$, '593dddce7c4ef2c47cc34038dd0fc0cc18c8e576', TRUE, NULL),
  ('ac2f3c9d04c1d307', 'client', $s213$<color=#888><i>Hidden</i></color>$s213$, '29b2cfb1815a45fe5f93cce227df3453f78ad1dd', FALSE, NULL),
  ('ac3f9e4803a9463c', 'client', $s213$Aurora Gradient$s213$, '96fe497e8d08bf63fbd473f4404b51f515bb3dac', FALSE, NULL),
  ('ac53cb1d4b497deb', 'client', $s213$<color=#888><i>Grab them in the Shop tab.</i></color>$s213$, 'd64a6ab3ed242d778aac287190982a900e112064', FALSE, NULL),
  ('ac570864590c58d5', 'client', $s213$Win with Abyssal Countdown as your FIRST pick, activating it every round$s213$, '35fce3934da3c301073ba9a0ba73e8eba28a197a', FALSE, NULL),
  ('ac71054abd96ce73', 'client', $s213$Level 1$s213$, 'f25d3c50abaee5db733fdf971a931d354780082c', FALSE, NULL),
  ('ac777af161d15bde', 'game', $s213$Continue?$s213$, '4e6302ed03494c9085e960acbd0bb635e148ed80', FALSE, $s213$StringTableDefault/PROMPT_CONTINUE$s213$),
  ('aca467037c8e7cc6', 'client', $s213$Party Crasher$s213$, '8b2a28c3db542d4b6043903e5419fef8c4156cea', FALSE, NULL),
  ('acadcc6ff4c590b4', 'client', $s213$Compare Cards$s213$, '09ee70122eab9a6320da7896d79280ff7c68f676', FALSE, NULL),
  ('acb991947bff96e9', 'client', $s213$Alert category$s213$, 'd86a6e9a016d86b1c6146341dea428756ce4a5a0', FALSE, NULL),
  ('acbb2acd18c65dd7', 'client', $s213$Force-start votes: {0}/{1}$s213$, '86bb334f8ed2d24e6c396de77e5ca2c7be2bb490', FALSE, NULL),
  ('acc86de9b59c25db', 'client', $s213$Lumberjack$s213$, '32ed08835c994efa3c32d263129bb8a259d54463', FALSE, NULL),
  ('accb99d11995227c', 'client', $s213$<color=#66CCFF>Downloading...</color>$s213$, 'f79172f515472bfbdcf012289d572cba03244088', FALSE, NULL),
  ('acda0f3497987f2a', 'client', $s213$Decline (offline mode)$s213$, 'bbe6a0d4c7d69d2481e2d3224d708c68e8e22709', TRUE, NULL),
  ('ad08ff14df37c264', 'game', $s213$Mouths$s213$, '8ddd5fb683bbb8507b7a2af05877758767701743', FALSE, $s213$StringTableDefault/CATEGORY_MOUTHS — Plural$s213$),
  ('ad0a6dae771517ad', 'client', $s213$Bright industrial blue body color.$s213$, '9ec32ed642cbdcae1c042f9b03791ebc2d4e9c6a', FALSE, NULL),
  ('ad1e59715a6ba031', 'client', $s213$LOCKED - STARTING SOON$s213$, '826eff5d83a7f019b3d90ef265f759162f982ea5', FALSE, NULL),
  ('ad342332ae4f797c', 'game', $s213$Español$s213$, '2001ca082b2d2742765d8ac9182678bfe0374fbf', FALSE, $s213$StringTableDefault/LANG_SPANISH — 2023-10-23: Replaced the unlocalized name with its translated version$s213$),
  ('ad65a56975f3e7b4', 'game', $s213$To edit$s213$, '1b83a841db1d77b3da9721da75ae6856edbcda21', FALSE, $s213$StringTableDefault/PROMPT_TOEDIT$s213$),
  ('ad7b3abe61db1a27', 'client', $s213$Artist Studio$s213$, 'adca584b7f8c32ece93a46b17db60f483cd68dc6', FALSE, NULL),
  ('ada862d6c0f469e7', 'client', $s213$Wrap your name in <i>italic</i>. Stackable with other name styles.$s213$, '609dfb565c93a98b2b30104355b3a4232da847f4', FALSE, NULL),
  ('adbb4d619548dbdc', 'client', $s213$Server alert$s213$, 'acd13dafca8e5749f8e6a1a9b53ce55919ccf5f2', FALSE, NULL),
  ('ade79993560f1bf0', 'client', $s213$Update$s213$, 'fb91e24fa52d8d2b32937bf04d843f730319a902', FALSE, NULL),
  ('ae1b61d68f6be632', 'game', $s213$Bullets lose half of their speed when they bounce$s213$, 'eeb2b4041d5a2b1404a7b053ef143cbb21cd597e', FALSE, $s213$StringTableCards/CARD_RICCOCHET_DESC$s213$),
  ('ae45d23094ff342e', 'game', $s213$A bunch more$s213$, 'bd05371fad5d297d48e01fcca5e59f55c92a5388', FALSE, $s213$StringTableCards/AMOUNT_ALOTOF$s213$),
  ('aea09b3828dbdedf', 'client', $s213$TOURNAMENT MATCH vs {0} - connecting automatically, hold tight...{1}$s213$, '000192d1a8bc97d6ee60930274a5576366c228af', FALSE, NULL),
  ('aea133c530e2eb26', 'client', $s213$Private {0} lobby$s213$, 'c533468e20d8365bef12ca8e3ee43dfac8f32e29', FALSE, NULL),
  ('af20dfcde4e40158', 'client', $s213$Link your Discord first (Home tab)$s213$, 'f3168e1294a51faf76e336c00dde31bf9be8684e', FALSE, NULL),
  ('af3d1bf4c8be9543', 'client', $s213$<color=#FFD94D>Ranked (series):</color> {0}W / {1}L ({2})$s213$, 'f89bf703606cf6e63f8874ef15d32c00fac7e208', TRUE, NULL),
  ('af50d15ccc91d824', 'client', $s213$Same cards: ON$s213$, 'fb37e857128f8e9e6452c1511f0f974a99accbca', FALSE, NULL),
  ('afda56e261c5dbc8', 'client', $s213$<color=#99AAEE>Top Cards:</color>$s213$, 'f9f7dc430ffd04be72b8680756d5da9a0e4a961b', FALSE, NULL),
  ('aff01af270318894', 'client', $s213$<b>Open FFA Lobbies</b>$s213$, '69436f4e093ec1bfbb5f78046f3ce964cfcafba9', FALSE, NULL),
  ('b0196ae3471ab703', 'client', $s213$  <color={0}>Series streak: {1}W</color>$s213$, 'b1c82e918d4d6bc3462d09c8a72e196ccc681b2c', FALSE, NULL),
  ('b01fdd24bef99b35', 'client', $s213$Rating: {0}   RD: {1}   Peak: {2}$s213$, 'f6c0bd7cdb978fec1a5df08a6c5cea49360c6da7', FALSE, NULL),
  ('b03342feaff2e735', 'client', $s213$Per-letter bright yellow → deep red gradient. Flame to coal.$s213$, '3f1c0d14e823390910e171a2cb32a8ad991d59c2', FALSE, NULL),
  ('b0435f9624a0ff08', 'client', $s213$<color=#CCCCCC>In this Photon room for <b>{0}s</b> with no match started. Vanilla matchmaking sometimes hangs here when one player has ROUNDS unfocused. Click into the ROUNDS window first and try space again, or use the escape hatch below.</color>$s213$, '0f187adf4f36222c3e229d3a7cfc62c483482453', FALSE, NULL),
  ('b0818db3177b092e', 'client', $s213$Win with Sneaky and Drill together$s213$, '1c1206ecc70c025967719deee7ea420f8a770c9d', FALSE, NULL),
  ('b0af469852baf260', 'client', $s213$Where their gold came from$s213$, 'b7333d5b1bdacbc317e77f570a617109fb32f3da', TRUE, NULL),
  ('b0b49ff92e08c74a', 'client', $s213$A deep wine red.$s213$, '70b6c54dc1c13ff24f68f5b1e66b0170e9871bd4', FALSE, NULL),
  ('b0bbeabb2c6af5f3', 'client', $s213$Win after being down 0-4$s213$, '098f5df305727f005ed1895b5994020e1cc19406', FALSE, NULL),
  ('b1106ea1ec6e7b1e', 'client', $s213$expired$s213$, '45a6f9adb1df3a78aafc71391c7d3bfa7680229b', FALSE, NULL),
  ('b11e9b8eb932f992', 'client', $s213$Win 100 casual games in a row$s213$, 'a62db852b1d4fd67229d8c1db9abc212214d14f9', FALSE, NULL),
  ('b12c7a7c8d1efcb9', 'game', $s213$Windowed$s213$, '7d22ecce0385c959845f551d5a3b5ab183398dfa', FALSE, $s213$StringTableDefault/OPTION_WINDOWED$s213$),
  ('b14cb9f81053d278', 'game', $s213$Block and mute opponent$s213$, '0335d5dbbe4561d4eeda25021a567c465906ce25', FALSE, $s213$StringTableDefault/BUTTON_BLOCK — Block as in blacklisting the player$s213$),
  ('b184685895afcf0d', 'client', $s213$Purple-black shadow trail. Feels wrong in the best way.$s213$, 'ac2f7ec50caa3e176d76d18c4b08ddc29913a773', FALSE, NULL),
  ('b1ab6e33f7326e5b', 'client', $s213$Cyan Name$s213$, '747761927d1053584caa147babb5f8bb92befb6e', FALSE, NULL),
  ('b1bbe5774b2b4dfd', 'client', $s213$Win with two or more Pristines$s213$, 'c53e157e2a81efdacfd391f05f42b4dc1b608a64', FALSE, NULL),
  ('b1e7b0efa8b13273', 'client', $s213$point lost$s213$, 'edc079e759d1a31c643e22a7b51cad76aad0a5b9', FALSE, NULL),
  ('b1eef294c20d4576', 'client', $s213$<color=#FF9966>MASTER OFF</color>$s213$, 'bb8114dd2fbea5b0ee5612f9aae23305f631796a', FALSE, NULL),
  ('b210c9c9bbda0065', 'client', $s213$Still joining - one moment...$s213$, 'd71c4ede722c792578ac6c7cab00113b2e7fabae', FALSE, NULL),
  ('b234d0122bbaa63f', 'client', $s213$Thanks for testing the mod during beta. Free, removed after beta ends.$s213$, '117e0234bc721029ca23bc4468eaaf69939a267a', FALSE, NULL),
  ('b2589813d7fe449c', 'client', $s213$Achievement Unlocked: {0}!$s213$, '5bf5fdcdb65caf6b9ba3b018c97ee583e7630856', FALSE, NULL),
  ('b25a2fb5ec8a68e0', 'client', $s213$White Cursor$s213$, '7afa3cb197e2dfdfb6813dd41d7d5de2c47e7c19', FALSE, NULL),
  ('b28c6095513b6482', 'client', $s213$Mod display language. Machine-translated drafts until community moderators review them — card text in matches follows ROUNDS' own language setting.$s213$, '2f86234d58aeb5c42903f4860c359d45fe00fdf8', FALSE, NULL),
  ('b2afe4968bcc4aa7', 'client', $s213$Get Link Code$s213$, '120606dcac1a829f37539d9af0708360d5453e69', FALSE, NULL),
  ('b2d58f4b596f2040', 'client', $s213$Ban Steam ID...$s213$, 'b5f65d80008ad5bc2dcac7a6c3249f23338f989e', TRUE, NULL),
  ('b35287596dfd384c', 'client', $s213$Ranked: ON$s213$, '98194ebda82e053bbdfb5e3c3810d48876a1aaf9', TRUE, NULL),
  ('b35fb4ad612dfe48', 'client', $s213$Trying, hard.$s213$, '05622e2e52c968bbde79af9c43a01a69c348ffd0', FALSE, NULL),
  ('b386ce912e7da2db', 'game', $s213$Local$s213$, 'dc99d54d9990e3c134420be3918e88f28531e630', FALSE, $s213$StringTableDefault/BUTTON_LOCAL$s213$),
  ('b391ace447463335', 'game', $s213$STATIC FIELD$s213$, 'ab988966c77076dd620838a48f1bb75c8925b7d8', FALSE, $s213$StringTableCards/CARD_STATIC_FIELD$s213$),
  ('b3c7d24dc7d7d5f0', 'client', $s213$<color=#6677AA>You:</color>$s213$, '5e3ff648c349f07d096defc5f364a9bf02be7bd1', FALSE, NULL),
  ('b3e2957858fb3018', 'client', $s213${0}: <color=#FF9966>OFF</color>$s213$, '22d79b7411b323a43df61650426791552bdec4ae', FALSE, NULL),
  ('b3eb79e601bb099b', 'client', $s213$<color=#66FF88>Online now</color>$s213$, '1b796b9e660114c40780b5f70ed1977413c71cbd', FALSE, NULL),
  ('b40fb3b19f66c416', 'client', $s213$Avg Cards / Game$s213$, 'a9cb3b230f62baaa2a50a30ae4021bc185ff4cf7', FALSE, NULL),
  ('b42387c8be516f9e', 'client', $s213$Per-letter magenta → cyan gradient. Interstellar nebula.$s213$, '57a7a6cdae35659fdaab629a1af89418c8b819e0', FALSE, NULL),
  ('b427669f556ea7bb', 'client', $s213$<color=#FFD94D>Map skin:</color> <color=#FFFFFF>{0}</color>$s213$, '02915b624b288814df3f1ae1b33365dcc0c576b3', FALSE, NULL),
  ('b43af19169139958', 'game', $s213$Implode$s213$, 'cab8414810031a7944ef39bef893c146fc126bdf', FALSE, $s213$StringTableCards/CARD_IMPLODE$s213$),
  ('b43c450431d13f59', 'client', $s213$Gentle soap bubbles float up around you.$s213$, 'f75572ef86d5cfaece368a57351d584911134e8e', FALSE, NULL),
  ('b4489e1753b09ca0', 'client', $s213$Same cards: OFF$s213$, 'b0b2b820bcfb2fa8bcf150c069f23c562d765014', FALSE, NULL),
  ('b4753d0471a2e6ff', 'client', $s213$Compare Players$s213$, 'bcfc616c401341442e28f27345987840dfbac509', FALSE, NULL),
  ('b4874c5e05d6538d', 'client', $s213$Damage$s213$, '7bf6d1d3a58a22ee49f3b78fc132bc5e98633e4a', FALSE, NULL),
  ('b4afe6f94d8a1b3b', 'client', $s213$Poison$s213$, '6de0b0c656444c55bac48c2e467aa0f841083cdc', FALSE, NULL),
  ('b4cb6205235dd418', 'client', $s213$1v2 series: {0}$s213$, '109cf27fd85482c00b4a6b6dbb2bbc91dcfba193', FALSE, NULL),
  ('b4d0bf3130aeccad', 'client', $s213$Thicker menu text: <color=#FF9966>OFF</color>$s213$, '5898784be18a6aba413074e338d99a93783068ef', FALSE, NULL),
  ('b4e0e0eaa97ba3d2', 'client', $s213$Gold Sources$s213$, 'e8a08aa75e862bc78c2d3eb56e21e2a04e8a45ba', TRUE, NULL),
  ('b50df2e13f58ab02', 'client', $s213$  [Opponent Ready]$s213$, '3b88585ccc7066af5df23fdfd4cd1d8b7d835a49', FALSE, NULL),
  ('b51b794698a1cd64', 'client', $s213$w/ {0}   vs {1}$s213$, '96d510eecdc8dec60e5e9065d67fb5b7cfb4f49c', FALSE, NULL),
  ('b5482b7b080c47bf', 'client', $s213$Opponent Block Rate$s213$, 'db62e93e34ee47cb1527eb4f39ebb57b0f1b5c2c', FALSE, NULL),
  ('b55e98320a2c5883', 'client', $s213$A warm coral pink matching the new Coral body.$s213$, 'c0d79153a0f91fd7a0675abc1920dbfb911a8244', FALSE, NULL),
  ('b5699b2c6706d70a', 'client', $s213$<color=#AA9955>-> {0} bet {1}g on {2} - refunded</color>$s213$, '9e8ba6414d716552ea534ba3d65e2773b984fe5e', FALSE, NULL),
  ('b5a636572c560a3f', 'client', $s213$Dark Aura$s213$, 'd1337bd66502e493e3dd898db928623e5e720ba0', FALSE, NULL),
  ('b5cadb3a41019d3e', 'client', $s213$Visuals & Effects$s213$, '4a26389c62013544b114efb52635035677621f0e', FALSE, NULL),
  ('b5d62dcee8924655', 'client', $s213$<b>Open FFA Lobbies</b>  <color=#888>({0})</color>$s213$, '1780f3134b55989a3e3145349cc2a4097f142ddd', FALSE, NULL),
  ('b5e4bc86afedf812', 'client', $s213$Translation role revoked.$s213$, '68708e68355c1424ba1010b04a7d02bbf94ac448', TRUE, NULL),
  ('b609dd2a7d2ae301', 'client', $s213$Records$s213$, 'e51c55255be9007d473b3c04b4553c2a27d6f03b', FALSE, NULL),
  ('b62d5ca0a5ad78ca', 'client', $s213$<b>Open FFA Lobbies</b>  <color=#888>(none right now)</color>$s213$, 'b8aaf38308c25d47561a9defc03824a7d17b61d8', FALSE, NULL),
  ('b635111b3aa9f6db', 'client', $s213$<b><color=#FFB347>Solo Leaderboard</color></b>  <color=#888>(unranked)</color>$s213$, 'a3e061c9d22e1a76cc6e8364ffb5c439c3d0125a', TRUE, NULL),
  ('b6862f5ae4f76951', 'client', $s213$Rainbow Aura$s213$, '9b8cce5d7eccd2e22579b152d9d9be67ab1466fc', FALSE, NULL),
  ('b691e2adfcfdea9f', 'client', $s213$<color=#667>click an achievement to see who earned it</color>$s213$, 'b4e3df6ec7261496a4f2f8ee7f590f710f05d3e6', FALSE, NULL),
  ('b75b645fcf4adb75', 'client', $s213$Colorize your name in purple.$s213$, '2889f9f551f5371f6892e307d5cf5c60025bb0c1', FALSE, NULL),
  ('b75fe59845fa7ecd', 'client', $s213$A light, warm skin tone.$s213$, '4a82ef21d0b89f6ba37a2b6c2fe3be74c8e23d34', FALSE, NULL),
  ('b7a35a4da059181f', 'game', $s213$Multiple bullets are fired in a sequence$s213$, '8e163db9f28e935dc30bf475a4c62ecd23d6c95e', FALSE, $s213$StringTableCards/CARD_BURST_DESC$s213$),
  ('b7cb3e6397fae3d6', 'client', $s213$1v2 series complete: {0}$s213$, '14d9e8634fcda42da86d1e2e895ca982372d4091', FALSE, NULL),
  ('b7f586245cf37349', 'client', $s213$<b>vs You:</b> <color={0}>{1}W - {2}L ({3} games)</color>$s213$, '49c3d520a6cf011fc93ce62b10afbe9e6bdfaec3', FALSE, NULL),
  ('b802826c7bb214e1', 'client', $s213$Shows your current server region and your ping to it.$s213$, '415d6233a087d283a4ca8030301edf6599dfe13d', FALSE, NULL),
  ('b8037a9a2a6f7770', 'client', $s213${0}-player FFA starting in 5 seconds!$s213$, '06869a27250bbb2bd445d71839cd9317c2551ab4', FALSE, NULL),
  ('b805204de1dc17d6', 'client', $s213$FFA cancelled - not enough players for a fresh game.$s213$, 'a926b4d61bf2b690aff0b07a8b6c41bdebdde9c9', FALSE, NULL),
  ('b80541264eef3b60', 'client', $s213$Solo extra pick (host): ON$s213$, 'c90b3620b9c40f5f3056d7ffcb0e1f311d7891f4', FALSE, NULL),
  ('b842e9bcebcddf77', 'client', $s213$A soft amber distinct from Gold.$s213$, 'bb1a91bcbeb57bb030beb06e6801c3123650ebc8', TRUE, NULL),
  ('b84788a98e84201d', 'client', $s213$<color=#66DD66>In FFA match.</color>$s213$, 'a7e2659bd9f21d6579b628236a12968cdc7e4d87', FALSE, NULL),
  ('b85e68945bf5ad76', 'client', $s213$Your Hit Rate$s213$, '068fd40efe11d831b1df4bcbec07d05060b33675', FALSE, NULL),
  ('b8726a2e1acd9dfe', 'client', $s213$Use$s213$, '1d4d43cc6f3a833e0340a0d1794b6d7b9958657e', FALSE, NULL),
  ('b882dfc5e49a8b27', 'game', $s213$Blocking pushes enemies away$s213$, 'be2dcc180690ac2b28b36f3bc5b2de4e86cedbc8', FALSE, $s213$StringTableCards/CARD_SHOCKWAVE_DESC$s213$),
  ('b89dfee35f251973', 'client', $s213$ (Play Now sent - waiting on them)$s213$, 'c94d1c070e24745e5257b847aa68b945bb5b953c', FALSE, NULL),
  ('b89ffcf2f3023062', 'client', $s213$Aged wine — deep red with a brown undertone.$s213$, 'cc6b2a579218473a35deacda2f0d5d288cf56c9d', FALSE, NULL),
  ('b8adf2986f373097', 'client', $s213$stackable$s213$, 'bea1572501beca2ebef3a391a800868da0c570a0', FALSE, NULL),
  ('b8c027d3e3a34c81', 'client', $s213$Eyes: lovestruck hearts. Equip in the Character editor.$s213$, '2684f8c6647a0ec56162173475a06b2700f4688d', FALSE, NULL),
  ('b8fdc86007277b7b', 'client', $s213$Pure greyscale — minimum visual distraction.$s213$, '58574a4f8f3a1703dd84bf2e5628e34cc1c666c9', FALSE, NULL),
  ('b90ef63e7495e242', 'client', $s213$Pure aggression$s213$, '1bd8f1b24f475d07e65940615d102d138bfb866b', FALSE, NULL),
  ('b939a9ae4f89cb0f', 'client', $s213$SYNC (weekly)$s213$, 'c4477dfa9e0ef6b9e35433b86e32cb10888ee6a8', FALSE, NULL),
  ('b94b0705d8006de4', 'client', $s213$Animated cosmetics: <color=#FF9966>OFF</color>$s213$, 'b504da153c3770cd3fc15e8be88d51230b4c8f01', FALSE, NULL),
  ('b9595d19d276b71f', 'client', $s213$Still leaving the FFA queue — try again in a moment.$s213$, '8c7b742a4127cf1254e34bdebc3322d3a7369c50', FALSE, NULL),
  ('b95f34ace2fa0325', 'client', $s213$Deep ocean-blue body color.$s213$, '0c7459d1da70cc3b119267a865e39cb294ce276a', FALSE, NULL),
  ('b99e6172f212d16b', 'client', $s213$Orange Cursor$s213$, '1af2afeff5d2f90ab6966cb74e75ab1e1082b53d', FALSE, NULL),
  ('b9c39cbeb97ffb3d', 'client', $s213$This mod sends data to a private server run by the mod author to power the leaderboard and ranked matchmaking.

What gets recorded if you allow:
  • Your Steam ID and in-game display name
  • Your Discord ID and username, ONLY if you link your Discord via the in-game link code
  • Each match you play: rounds won, points, duration, cards picked, cards offered, opponent
  • Your Glicko-2 rating history

What you can do later:
  • Revoke consent anytime (F5 → Settings → Revoke). Reporting stops.
  • Delete your data (F5 → Settings → Delete my data). Steam ID, display name, and Discord link are scrubbed. Matches stay so other players' ratings and histories aren't disturbed. Deletion is IRREVERSIBLE — you cannot re-register this Steam ID later.

Choose Allow to use the leaderboard. Choose Decline to run the mod fully offline.$s213$, '0b4859fc9d77ed14bb61337fbaa484d5a31a7980', TRUE, NULL),
  ('b9da26eccc254410', 'client', $s213$Press Enable on the RANKED row first - the RLFP ping is only for ranked matches.$s213$, 'f759566b7428a79b95a6d43e534fa03154485cf6', TRUE, NULL),
  ('b9f849c45fd22952', 'client', $s213$Leave your custom 1v2 lobby first.$s213$, '3a727fff861b715551b3e0a3e3daee8d433363a2', FALSE, NULL),
  ('b9fbea5d65e6e66e', 'game', $s213$CHASE$s213$, 'd65eb6205af9b7f4e475e3f6fc087a34422883c6', FALSE, $s213$StringTableCards/CARD_CHASE$s213$),
  ('ba02c82796b6e9ad', 'client', $s213$Match could not start — only {0} of {1} players connected. Leave to the menu to requeue.$s213$, 'a4b0d5dbc856f49bb8c060ac21ce0a9bb60889df', FALSE, NULL),
  ('ba0b8dc8f6cd3b7d', 'client', $s213$<color=#99AAEE>Ranked History:</color> <color=#888><i>no ranked series yet</i></color>$s213$, '99179cc9e74d882fb29effe8c3d16396cba0d1b2', TRUE, NULL),
  ('ba17468c6b466990', 'client', $s213$Enter a whole number from 1 to 2000 gold for this bet.$s213$, '597fe2e793459992f591bb2fffb5da571a767476', TRUE, NULL),
  ('ba292685c6b16f5e', 'client', $s213$Win with Empower and Healing Field together$s213$, '061542f4315766fa49452c133d2445cf3c714521', FALSE, NULL),
  ('ba3394d24a886db0', 'client', $s213$Rally Flags$s213$, '41434103e0f30de4583dbd5d09e8fbdce6268ecc', FALSE, NULL),
  ('ba7370f908154504', 'client', $s213$Sand$s213$, 'b36fbc6e8df68fb14280742f8b5bf0c0460a6fe0', FALSE, NULL),
  ('ba7dca8a4cbe7f6d', 'client', $s213$Show Discord on leaderboard: <color=#888>link Discord first</color>$s213$, 'da679c68be32dbace626c9a143329c3cc63c44cf', FALSE, NULL),
  ('ba96fca51968f524', 'game', $s213$Deal 15% of your max HP to enemies around you when you block$s213$, '8504325bff4c363ff45f4d70c743aa1a1c314a00', FALSE, $s213$StringTableCards/CARD_OVERPOWER_DESC — Health Points$s213$),
  ('baba0a75c39bf4ee', 'client', $s213$Move spd$s213$, 'ae53d6915d23e165765583cc340533e6e418cbd7', FALSE, NULL),
  ('bac8aa401a36bac7', 'client', $s213$Open Tier List Folder$s213$, '44a5bdcfc33755caee572a800d414defd6733252', FALSE, NULL),
  ('bad2106299b6b752', 'client', $s213$<color=#888>No one in {0} right now.</color>$s213$, 'f4364485a44965c7c825bb1e59144457e7b4ec5e', FALSE, NULL),
  ('badd96d7af08d83e', 'client', $s213$Grand Final$s213$, '361a685997549953a08875007aa5a09476ac95de', FALSE, NULL),
  ('bb1576b33cca66ca', 'client', $s213$<color=#88FF88>Ready! Waiting for the other 3...</color>$s213$, '0f8972798a7dc8831f9c0d900bead94bda16f1e6', FALSE, NULL),
  ('bbafbcbefeee1a04', 'client', $s213$Pale spearmint body color.$s213$, 'afd15ef89657a69cc8d382f43cae628b459cc1b2', FALSE, NULL),
  ('bbe3197e69738bd2', 'client', $s213$Deep blood-red body color.$s213$, '698769e3384f77f8587a7217e7ac7b3a9c9990c7', FALSE, NULL),
  ('bc030c06fe5a0335', 'client', $s213$Failed: {0}$s213$, '40fc0b8e623cda2ad22b652d0c886c5580af6837', FALSE, NULL),
  ('bc4565d2dfd86677', 'client', $s213$Data & Privacy$s213$, '43cd04b1d12ecf152fe28138809f095b8750be57', FALSE, NULL),
  ('bc5daf52ecfcb394', 'client', $s213$ALL CAPS$s213$, 'baf48506da4f8fcb158b020e9780f52833d663a4', FALSE, NULL),
  ('bc5ef555d953bee2', 'game', $s213$FASTBALL$s213$, '289df29919cf2bb172118b41fe4e024750ac144c', FALSE, $s213$StringTableCards/CARD_FASTBALL$s213$),
  ('bc72b559149cb624', 'client', $s213$FFA Elo over time$s213$, 'e7404031ae51ade0a69a6a4d48f8d2f4b548eeef', FALSE, NULL),
  ('bca35b7294be96d0', 'client', $s213$Side: Duo$s213$, '2cffbd4cb1fe7e951322c8698624d869e8e79a69', FALSE, NULL),
  ('bcc7673bc97a4ef3', 'client', $s213$Stop Avoiding in Ranked$s213$, '24338c588a7c02e9f6f4cbf38c0da960808fc6e9', TRUE, NULL),
  ('bcdf653ee83bbe53', 'client', $s213$<color=#99CCFF>Block:</color> {0:F1}% ({1}/{2})$s213$, 'c7635e1e070552f04640a363f9b42688d920f5c7', FALSE, NULL),
  ('bcdff3edc272aa6b', 'client', $s213$<color=#FFD94D>Ranked:</color> {0}W/{1}L$s213$, 'c41e0c77ac7efea07d68b205c2ecda2ffefff35e', TRUE, NULL),
  ('bce06d48a403b9a4', 'client', $s213$Win against Sid in a ranked series$s213$, '1792eca0039ac2d3327c9bf01f4dbca43e48e063', TRUE, NULL),
  ('bce10b6d42caa61d', 'client', $s213$<color=#888>Discord:</color>$s213$, 'c34d4b466d6b20a538710fabf9f43f8d410d46fb', FALSE, NULL),
  ('bce43d5b196d8359', 'client', $s213$Huge main$s213$, '0c99c0f89091cfd5c213bec88778fa6d7c4b67e1', FALSE, NULL),
  ('bced5e3b4f62b4c4', 'client', $s213$Remove$s213$, 'e963907dac5cd5c017869b4c96c18021c9bd058b', FALSE, NULL),
  ('bd293819f288ad8a', 'client', $s213$<color=#8899AA>Which modes? (pick any)</color>$s213$, 'addcf9ab680552843b3418632fa1361fde9a6581', FALSE, NULL),
  ('bd2d56f21f25ea85', 'client', $s213$Show Discord on leaderboard: <color=#88FF88>ON</color>$s213$, '0b42ec74cc3cc6599f998efde1002207e0d842bd', FALSE, NULL),
  ('bd560f79298369cd', 'client', $s213$<color=#7FE8C3>Sales log</color>  <color=#888>(every purchase and gift, newest first - gifts earn 0)</color>$s213$, '803af7293eaf4ae774d92dd3026c7a8ff205d355', TRUE, NULL),
  ('bd5f6718ab6205d7', 'client', $s213$LOW$s213$, 'd8b9679fad55bd0178081bc796a093eec7fd845c', FALSE, NULL),
  ('bd6d31d0b058348d', 'client', $s213$duo$s213$, '16ef1d431149d2a08902873a443dbbe54c85cddb', FALSE, NULL),
  ('bd85c879cf3ba261', 'client', $s213$Search...$s213$, '6d7a30a931a35ef0373a28fc4507bf29ba239fda', FALSE, NULL),
  ('bd8b0169d8b34641', 'client', $s213$Leaderboard$s213$, '0381247a698736fe9930328a814e5263eeff72fd', FALSE, NULL),
  ('bd97142ff2899914', 'client', $s213$Your no-show penalty: <color=#FFCC44>{0}%</color>$s213$, '932d39ba6afffe50ecdb9d96f8e9953fc8738c51', TRUE, NULL),
  ('bdab55d88a917902', 'client', $s213$<b><color=#FF6688>* Live 1v2 Games</color></b>$s213$, 'efd69a2faad3252122e8e13305f6d4595a8bdea2', FALSE, NULL),
  ('be2399036371a377', 'client', $s213$Glow (bloom): <color={0}>{1}</color>$s213$, '73a2014a6c0b4134cdd1bfd287bf0685a71ec92e', FALSE, NULL),
  ('be4894b729971733', 'client', $s213$The Comeback Kid$s213$, 'f3e5625b48f6d3cb48733417bcdcf70a949419ae', FALSE, NULL),
  ('be93e1ed6ec90fec', 'client', $s213$Sniper$s213$, '2081d06ecb8f68cbf79e9de820f81f7f82fa4625', FALSE, NULL),
  ('be9560e3832c8bb9', 'client', $s213$Wins without firing$s213$, '1b48a60b0d625b75c26ce2cf730ff892e74f4114', FALSE, NULL),
  ('beb56c01fc312e7e', 'client', $s213$Win with Shields Up, exactly 1 ammo, and a lightning-fast reload$s213$, '9cc4287e6d1f7c078c8ac963e9cd8f292f0f1f02', FALSE, NULL),
  ('bf1f2179915227a5', 'client', $s213$Update failed — couldn't find your installed mod file. Update manually from GitHub.$s213$, '99bec94bc84f0b7bfa76f4cf90729acdc10c32aa', FALSE, NULL),
  ('bf2537cfc9a000af', 'client', $s213$Usage: /report [name] [reason]  (quote multi-word names: /report "Bad Actor" reason)$s213$, '6e902bbd6abba18b61d96350cc916b45c58bf725', FALSE, NULL),
  ('bf327ab5b8dbdcc1', 'client', $s213$<color=#FFD94D>Ranked Series vs You</color>$s213$, '0278a637c0b4224f4b2e502196bbf1aeac42848f', TRUE, NULL),
  ('bf950976d4c6643b', 'client', $s213$Pale luminous yellow name with a matching glow halo. Mimics the classic Steam-name color trick.$s213$, '9c702f519475562bf73e49dc3a37c10b50a87674', FALSE, NULL),
  ('bf972197bededb7f', 'client', $s213$Given$s213$, '6839d82e03f5268d9a7cc97802db76c48c8cce6e', FALSE, NULL),
  ('bff6b92b6c3e21d9', 'client', $s213$1v2 Series: Duo {0} - {1} Solo$s213$, 'a18f84a9578aa306f34357a39593e4ed8dbd4bd2', FALSE, NULL),
  ('c014368fb258c367', 'client', $s213$<b><color={0}>{1}</color></b>  <color=#888>(unranked - no games yet)</color>$s213$, '964083dde3b9086daa465f67dd2f060fef1afe91', TRUE, NULL),
  ('c032272018bc8288', 'game', $s213$<sprite name=BUTTON_EAST> Cancel$s213$, '33fce666d786872962f01375310f69ada281385f', FALSE, $s213$StringTableDefault/PROMPT_CANCEL_CONTROLLER$s213$),
  ('c07af5ea08c763b7', 'game', $s213$WIND UP$s213$, '4254bda1022380ff63c6b4df5489fe82ac2bdbb2', FALSE, $s213$StringTableCards/CARD_WIND_UP$s213$),
  ('c0a5a045dc1b1281', 'client', $s213$Private 2v2 lobby$s213$, '96c3146d3bc48dfa0b86a5911c497bd3462cb006', FALSE, NULL),
  ('c0b1c898d81f830c', 'client', $s213$Marked false positive. You still need to repair the rewards and series by hand.$s213$, '8605f969b685627b504e2187118f04a140ae4590', FALSE, NULL),
  ('c0b74f3dc3058639', 'client', $s213$* <color=#C8C8C8>2nd</color> - {0}g / {1} XP / Runner Up role$s213$, '0598c8fb1fcafc544b9570ef561d84c8e7941f27', FALSE, NULL),
  ('c0ba4e9ce075ba67', 'game', $s213$PARASITE$s213$, '78b869238b083d9f178baf9d1617edeecae134cc', FALSE, $s213$StringTableCards/CARD_PARASITE$s213$),
  ('c0be4316b3888ca4', 'client', $s213$<color=#FFD94D>Ranked (series): {0}W / {1}L</color>$s213$, '2466fa8171f0d173bff6eb5ad9409cf0d6e423cd', TRUE, NULL),
  ('c10e71128f6d67cd', 'client', $s213$Searching for ranked match...$s213$, 'c88d0a58ce821760b76ba78c6eb1393bc951fab6', TRUE, NULL),
  ('c13921814b798a44', 'client', $s213$lost {0} of {1}$s213$, 'e0b4578475d11bc2affdf781c63bf10d756ba3b8', FALSE, NULL),
  ('c146b1aae124b5ba', 'client', $s213$Changes the menu cursor's shape. Works alongside an equipped cursor color.$s213$, '37765cd85528b28ffef42e72a647700728327e82', FALSE, NULL),
  ('c15981b970bb074f', 'client', $s213$Change view$s213$, 'c401ce5826bb2f72ec8429df08aa320c18f4c542', FALSE, NULL),
  ('c15ad1cfef2807c3', 'client', $s213$Still leaving — try again in a moment.$s213$, 'a4f0773c75560f9643008820d0e70714619dcd1a', FALSE, NULL),
  ('c181f97737843bb1', 'client', $s213$Stitched Grin$s213$, '79144fb22b8fe57dc5e4025fa2451b9c9fbe973a', FALSE, NULL),
  ('c198ec18f335a171', 'client', $s213$Warm desert sand tones.$s213$, '427a3cd1255e088f822589a37ac6636241598de9', FALSE, NULL),
  ('c2080414dc4ad407', 'client', $s213$Win 200 casual games in a row$s213$, '6a83a7c5726697f6747faae9710baf615f3c39fd', FALSE, NULL),
  ('c20b8a9de411169d', 'client', $s213$End Alert...$s213$, '05ccca75986b9d013eae70af4841312e1a408f2e', FALSE, NULL),
  ('c2145c8238c29395', 'game', $s213$Bullet$s213$, 'b98da0ccc81f4f734434572f19ccc66972aae344', FALSE, $s213$StringTableCards/STAT_BULLET$s213$),
  ('c23c3f556d4a1843', 'client', $s213$  Dmg/game: {0:F0}$s213$, '774994f54715e39266a6307618d901ad7fd66269', FALSE, NULL),
  ('c2e6d9d121cad78b', 'client', $s213$Waiting for {0} ({1:F0})...$s213$, 'a5213556d4c72afdc8eb34d8c9c1b6854bc20ddd', FALSE, NULL),
  ('c30091482c3aed14', 'client', $s213$Card Stats$s213$, '2cf7c1c459ffac7b7755411c28a0fbd27b7ec2db', FALSE, NULL),
  ('c309e50ffbaede37', 'client', $s213$Pass Rate$s213$, '4078fad860e77d0ec91f4ee504d465200b137ffe', FALSE, NULL),
  ('c332f8d24db253b1', 'client', $s213$Field Medic$s213$, '9c456cc81aecc69b660c85dcac67dc9de04f91cf', FALSE, NULL),
  ('c38e5d2842896ff4', 'client', $s213$Accept$s213$, 'bb54db510a92908a5a4df79fc1ad1eae8df50ec3', FALSE, NULL),
  ('c3a399f195fc8086', 'client', $s213$FFA Elo over games$s213$, '7d822a612b6d69bce9382c06ce95b3915febf148', FALSE, NULL),
  ('c3a60b1d43f0cc1b', 'client', $s213$Series {0}-{1}$s213$, '353a9486426bb0d11106b53d29d363978e9ffcf1', FALSE, NULL),
  ('c3dcb3a7c99fa461', 'client', $s213$Into the Deep End$s213$, '104715a881fa08ef642df3c97be967c6383f5a4a', FALSE, NULL),
  ('c41b2ce8fb195cfb', 'client', $s213$Pick Your Start Times (as many as you like)$s213$, '34bd1f98b5ff53c0ec64db58e11c8ba454e1c881', FALSE, NULL),
  ('c4318aa1ebd2a555', 'client', $s213$< BACK$s213$, '2fa9e5cc35fd1f7d883c58d9c8b1c429811951fb', FALSE, NULL),
  ('c470426e6955e200', 'client', $s213$Glicko-2 Rating$s213$, 'fe7f3ff2587e3d130e5d52db5004c675ee655866', FALSE, NULL),
  ('c4abfe07405d45b5', 'client', $s213$unknown path$s213$, '4902794a18b07e5f86e7f33d4029788b2034de4f', FALSE, NULL),
  ('c4c4f162ef3a08eb', 'client', $s213$<color=#FFCC44>Searching…</color> {0} in lobby <color=#888>(locks at 3)</color>$s213$, 'a3fd02a92f217c87cd4ec996e33fe07c4b77ebca', FALSE, NULL),
  ('c4d1897e0b92927e', 'client', $s213$Bullet slow$s213$, '1982b45375c2d30f60024c602fa49444a089bddb', FALSE, NULL),
  ('c4e26bdf43287f07', 'client', $s213$Unfocused 120 FPS cap: <color=#FF9966>OFF</color>$s213$, 'c2d1908e08f8d3629bf1f765acdb632a6ddf7b34', FALSE, NULL),
  ('c52cca2c773022ae', 'client', $s213$<color=#CCCCCC>Latency (ms) over the match</color>  <color=#99B3E6>{0}</color>$s213$, '4ec13493affca1bdbebebe9038ae5d87d1b035f2', FALSE, NULL),
  ('c543f55c8141978b', 'client', $s213$Your FFA lobby closed.$s213$, '340d94cdc21e867be6acbc8abc8ef344e8b19f6c', FALSE, NULL),
  ('c56cdc211517120c', 'client', $s213$Apple Stem$s213$, '5f7ffa4a353bda2e5e403cc3f8b5fcbf11e82722', FALSE, NULL),
  ('c5768a1032dce392', 'client', $s213$Lavender$s213$, '75c88f3a0072cbd028982b65a0fcf2db0c4a5b15', FALSE, NULL),
  ('c5b99e4ded85c126', 'client', $s213$Free-for-all for 3-10 players. Every player is their own team.
Standard ROUNDS scoring - first to {0} points takes the game.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- There is no Elo band. Joining a lobby is consent to play.

- Create a lobby, or join an open one from the browser.
  The HOST presses Start once at least 3 players are in
  (up to 10). Several lobbies can be open at once.

- If the host leaves, the longest-waiting member becomes
  the new host automatically.

- After each point, everyone except the point winner
  picks a card at the same time.

- The pick timer is shown on screen. A pick landing
  near the end grants everyone a little extra time.
  When your timer hits zero, your highlighted card is
  picked for you automatically. You always get a
  card - skipping a pick is not possible.

- You hold up to {1} cards.
  Picking one more replaces your oldest card.

<color=#FFD94D><b>HOST SETTINGS</b></color>

- The host can tune the lobby before starting: score
  target (3-10), opening draws, max cards held (3-6),
  the Same Cards rule, and ranked/casual.

- Same Cards rule: everyone's Nth card draw offers the
  SAME candidates, in the same order - if you and a rival
  were offered identical cards all game, no result can be
  blamed on draw luck. One-copy cards (like Phoenix)
  appear at most once per game for everyone.

- After a settings change the lobby cannot start for 60
  seconds (and briefly after someone new joins), so
  everyone can read what changed. Casual lobbies pay
  reduced rewards and never touch ratings.

<color=#FFD94D><b>RATING</b></color>

- FFA is ranked with its own Glicko rating.

- Placement uses points, then all round wins earned
  (spent ones included), then kills.
  Remaining ties share a place using competition
  order: 1, 2, 2, 4.

- Your rating is scored against the players placed
  nearest to you (up to 4 of them), so one game can't
  swing your rating several times harder in a 10-player
  lobby than in a 3-player one.

- A tied placement counts as a draw. New ratings move
  fast and settle down as you play more.

<color=#FFD94D><b>REWARDS</b></color>

- Pay is metered on the FIGHTING, not on flat per-game
  numbers: decisive rounds are the work unit, and
  elapsed time caps how fast they cash in - stall
  tactics are held to a bounded edge, and longer,
  bigger games pay more.

- Bigger lobbies pay a better rate per minute, and a
  10-player FFA is the best gold rate in the game.

- Your placement shapes your share: 1st earns about
  five times last place's cut. Part pays as XP, part as
  Placement Gold, and a stronger opposing field
  multiplies the pot (the usual tier bonus).

- XP converts to Gold at 100 XP = 1 Gold, and level-ups
  pay their usual bonus Gold. A level-up landing during
  a game shows up inside that game's +g number - that is
  how a last place can occasionally out-earn the winner.

- Spectators can bet Gold on FFA lobbies from this tab.

<color=#FFD94D><b>READING THE RECENT FFAS LIST</b></color>

<color=#7FD4FF>Dots + N(P)</color> - Full points won.
<color=#7FD4FF>Half dots + N(H)</color> - Round wins that
  did not become one of that player's full points.
<color=#7FD4FF>Nk</color> - Kills.
<color=#7FD4FF>+xp +g</color> - That game's XP and Gold
  (including any level-up bonus).
<color=#7FD4FF>Green/red number</color> - FFA rating change.
<color=#7FD4FF>Cards</color> - The hand held at game end.
  <color=#FF6666>+N replaced</color> counts picks that were
  pushed out by the card cap - hover the line to see
  every pick in order.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

<color=#7FD4FF>Rank</color> - Position in the currently selected sort.
<color=#7FD4FF>Player</color> - The player's display name.
<color=#7FD4FF>Rating</color> - The player's separate FFA Glicko rating.
<color=#7FD4FF>Games</color> - Recorded FFA games played.
<color=#7FD4FF>Wins</color> - Games finished in 1st place.
<color=#7FD4FF>Top3</color> - Games finished in 1st, 2nd, or 3rd.
<color=#7FD4FF>AvgPl</color> - Average finishing place. Lower is
  better - 1.0 means winning every game.
<color=#7FD4FF>WR</color> - Share of games won outright.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving mid-game is recorded.
  A leaver keeps their tallies for placement.$s213$, '9d483832cb5867ebec6781d58957b7499d904cd6', TRUE, NULL),
  ('c5e1da03052cc027', 'client', $s213$FFA Average Kills per Game$s213$, 'b245fe34c71ef357ff38fa3da3be5ff787482568', FALSE, NULL),
  ('c60975242010a2c8', 'client', $s213$<color=#E69988>Opp: Hit {0}%</color>$s213$, '4fbccb024c897c74e187b3121bf5a8fae54a0244', FALSE, NULL),
  ('c68ef3507d15e173', 'client', $s213$FFA Average Placement (lower is better)$s213$, '0be14823081a2c5dc92e44eb3082c4f996504ae1', FALSE, NULL),
  ('c6d361b961c42895', 'client', $s213$Chromatic aberration: <color=#FF9966>OFF</color>$s213$, '6b9ac421159f3f8fee143c8f71b93aa5666b6190', FALSE, NULL),
  ('c6deea52290a01d3', 'client', $s213$Join$s213$, 'e0d73143de80d17e82de2e017ac156ca3b9c4e01', FALSE, NULL),
  ('c6e48e66ff28d8d5', 'client', $s213$Send ping$s213$, '3054ab05070e872c716ae126a3e99c407fdf4eb1', FALSE, NULL),
  ('c6ea11f664524a12', 'client', $s213$How It Works - Async (6-week)$s213$, 'cf4e2230ffef8a783fcf4ea4e36306115c1023c3', FALSE, NULL),
  ('c71afca6cc3af501', 'client', $s213$Keys / Sec$s213$, 'd76083989d43f7f7ade72236e5280c68f1313816', FALSE, NULL),
  ('c731a1c891e2ba81', 'client', $s213$Locks the map to ROUNDS' Gold palette (warm yellow).$s213$, '7ecb9e49219df7f9e2fafd4f4cd75eb164d24290', TRUE, NULL),
  ('c7400849ff3404d4', 'client', $s213$Card$s213$, '4d4ce73b15660f20977ad7efab2283c51bdae008', FALSE, NULL),
  ('c748ad775e67676a', 'client', $s213$<color=#888>No open lobbies — create one and invite players on Discord!</color>$s213$, 'feea14636f4f98ce478d1447ce2614d4b8cf8231', FALSE, NULL),
  ('c750bf9316216979', 'game', $s213$Ammo$s213$, '407c60401b79318f2877683ed6df36f0bda6cfee', FALSE, $s213$StringTableCards/STAT_AMMO$s213$),
  ('c76ede26fcd816e4', 'client', $s213$Submit Report$s213$, '1ca00033fee3d4e5ee3de55b2d380368d9310d48', FALSE, NULL),
  ('c79a4645d2d603b4', 'client', $s213$1v2 Series: You {0} - {1} Duo$s213$, '21632c13e41daeae9f16c3ca8ba543066827c789', FALSE, NULL),
  ('c7a5a26638393134', 'client', $s213$Swallow ScreenEdgeBounce NREs from destroyed bullets.$s213$, '868d0b7d0ffa614abcff7ba14ad2d6bde86a1b2c', FALSE, NULL),
  ('c7c6e4fba9dcb3c6', 'client', $s213$Wisps of grey smoke drift off your body.$s213$, '6f3c2cb5e1f2e4a068c8389405e3e496e4f9ef97', FALSE, NULL),
  ('c7cd96f7c337c372', 'client', $s213$<color=#888>(equip in the character editor)</color>$s213$, '89e542520d4d04153f795491a4d854749727701f', FALSE, NULL),
  ('c7db091c6a0581e2', 'client', $s213$<color=#88FF88>Equipped.</color>$s213$, '6535f8599ca23255d61a3b1d7d6ffe9e652dccb1', FALSE, NULL),
  ('c7e1faeda4aff802', 'client', $s213$<color=#667788>series:</color>$s213$, 'd0fde2869f5db199bb2e6fc56d6ec641b7e9ff32', FALSE, NULL),
  ('c7ff4f384e1ed8c3', 'client', $s213$Poison main$s213$, '994ef00e3288928269240324105bb35e1304c87e', FALSE, NULL),
  ('c81155b0fa7eca7b', 'client', $s213${0}h ago$s213$, 'f7ce37d55c66b97cbd23a453b13f007c5a09ac19', FALSE, NULL),
  ('c88a9fc809cbd08c', 'client', $s213$Appear offline (Home lists): <color=#88FF88>ON</color>$s213$, 'fa7e5eb35adccb3eb968b6ecc50791ea1b621f85', TRUE, NULL),
  ('c8a0e2e08bdb7f47', 'client', $s213$Current Rank$s213$, 'f996d22f90fe3880c9bf2c0026b7e64b2c9d234a', FALSE, NULL),
  ('c8a63c1732410b70', 'client', $s213$Electric-cyan neon name with a soft glow halo. Visible to everyone; modded players also see the glow.$s213$, '9d2514d92ca9b022beab74865f8146bd878801be', FALSE, NULL),
  ('c8a7d841ea12ccc7', 'client', $s213$Self-awareness is a virtue.$s213$, '4e759bc7fb00171c1450a5abdb85e63a0d4be467', FALSE, NULL),
  ('c8b11f4b97ff6849', 'client', $s213$Forest$s213$, 'f41c4e4dab0b44d75dad0c04a0156d326c95b774', FALSE, NULL),
  ('c8c1cc84c8764b32', 'game', $s213$Blocking teleports you forward$s213$, '6187fec97811787020169fb281a6d49e70351094', FALSE, $s213$StringTableCards/CARD_TELEPORT_DESC$s213$),
  ('c8e19ea38805cd06', 'client', $s213$<color=#8899AA>How long are you searching? (shown to players as an expiry)</color>$s213$, '9a62a068439228473cef75e0adeea9dea9ffe2ee', FALSE, NULL),
  ('c91478ec31d61956', 'client', $s213$Green Name$s213$, '3f508506b3bbc0e084dffe7ce76e5c8ec800e0ad', FALSE, NULL),
  ('c92f5f7bded0170e', 'client', $s213$Mirrored chrome with a soft shifting tint.$s213$, 'b6af76411b6d6bc9e35cd94b8b7ea98f83b14aaf', FALSE, NULL),
  ('c9630c50abedb69b', 'client', $s213$Allow spectators: <color=#FF9966>OFF</color>$s213$, '85ff4e3ddc16a8c134e81be751bc9b2ee9717b30', FALSE, NULL),
  ('c97d35b45f398d79', 'client', $s213$Peak Elo$s213$, '5a581465bae3c00caeb7577b0eba5949d87517a7', FALSE, NULL),
  ('c9a51e0e1ea11854', 'game', $s213$Spawn a bunch of small bombs around you when you block$s213$, '742b8f036853bf5ee788a595cfb952653c588b27', FALSE, $s213$StringTableCards/CARD_BOMBS_AWAY_DESC$s213$),
  ('c9bf79f4e691db5d', 'game', $s213$Show card stat numbers$s213$, 'ca9663eaa2390d8afe9dd01f6980661c2dc8af30', FALSE, $s213$StringTableDefault/OPTION_SHOWSTATNUMBERS$s213$),
  ('c9cc67272a1c866f', 'client', $s213${0} of {1} left$s213$, 'ce9deb48ef00eef45a5b3b38a2161430725ea158', FALSE, NULL),
  ('ca42603f393a8386', 'client', $s213$<color=#99CCFF>Block:</color> {0}% <color=#888>({1}/{2})</color>$s213$, '55d0abe95e269b9549242e572909ab1b7406f21c', FALSE, NULL),
  ('cab4937719a22718', 'client', $s213$Tan$s213$, '133552ebfbcce8310f8920695422699d5256bac9', FALSE, NULL),
  ('cada077cba6f8b7c', 'client', $s213$Betting Record$s213$, 'a40dbe4a1c7aebbf45414b3121bea1d5361d57d5', FALSE, NULL),
  ('caf5eeeec3117ec3', 'client', $s213$Prizes & Rules$s213$, 'e04ea281201a233a32fca1d38f18e6f2ac668552', FALSE, NULL),
  ('cb173826046b9943', 'client', $s213$Regular$s213$, '8d4e4ef3ea5252ec5235e4b1dd463ae9c302422c', FALSE, NULL),
  ('cb5be6eb1a54e3b3', 'client', $s213$Jump$s213$, '1eba140fdd9c6860a1730c408e3064aa417ca2a3', FALSE, NULL),
  ('cb766e20e27fc2fc', 'game', $s213$Svenska$s213$, 'f344580ac42f760d329f42fd603592846f6ea50b', FALSE, $s213$StringTableDefault/LANG_SWEDISH — Not used, for testing purposes
2023-10-23: Replaced the unlocalized name with its translated version$s213$),
  ('cb88c065adf80933', 'client', $s213$Bigger than Bigger, smaller than Huge.$s213$, 'dcce1b666e42b2516c4264ee76dabb367fb176b1', FALSE, NULL),
  ('cbc1f7ce7819d980', 'client', $s213$vs {0}: first game this session$s213$, 'e944ac9b80a010f18e34cd58514c85d670852aca', FALSE, NULL),
  ('cbe8c30cbcc7634d', 'client', $s213$Series Score: {0} - {1}$s213$, '35b9dec4c725630964642fc46ef9413ab161ff40', FALSE, NULL),
  ('cbea0bc6281f33a2', 'client', $s213$Machine translation - the English notes are on GitHub.$s213$, 'e2ae05adfe58ad36b43154dad1a22d319d314df9', FALSE, NULL),
  ('cc1575ac7ddebd3f', 'game', $s213$Bullets deal damage over 5 seconds$s213$, '87afc1bd217963a2c1ea4fdf261ad830297d0f4c', FALSE, $s213$StringTableCards/CARD_PARASITE_DESC$s213$),
  ('cc1b40e3619a5039', 'game', $s213$RADAR SHOT$s213$, 'e869e9148290b94902ca3a0cfd22a7d1b74e5306', FALSE, $s213$StringTableCards/CARD_RADAR_SHOT$s213$),
  ('cc411aefa047c15a', 'client', $s213$<color=#888>click anywhere to close</color>$s213$, '9a8cae38683e4f3e98c1303af44231665436fcbc', FALSE, NULL),
  ('cc7fc9633cd6dc97', 'client', $s213$no profit at these odds$s213$, '2220d7c0a8777ada584d790974e9a04202b70c3c', FALSE, NULL),
  ('cc9d2a3ae8673ac4', 'client', $s213$Sort:$s213$, '8b335a234e4193e8787a2bbc9ebdddb99c39f38c', FALSE, NULL),
  ('ccd6c2ba67bfee1e', 'client', $s213$  vs {0}:  First time playing!$s213$, 'c25067a12dfc7a94ec107c6073e215ab8f45ec06', FALSE, NULL),
  ('cd0163493ecac4fa', 'client', $s213$<b>Recent 1v2 Games</b>  <color=#888>({0} series)</color>$s213$, 'c0dafbb700e42748454366596685977879f28bbe', FALSE, NULL),
  ('cd5edd2dfb625384', 'client', $s213$Twilight$s213$, '6caad4cda78d3c6ad47660162f70accf6748494f', FALSE, NULL),
  ('cd7de4ecc01c1d92', 'client', $s213$Colorize your name in red.$s213$, 'e076968ac0727a056d40623d209ebf3b394200e1', FALSE, NULL),
  ('cd8f5194e9e82b41', 'client', $s213$+{0} more bets$s213$, '304e2e4321f7e7d845773c97f6c4ca8e4c771440', FALSE, NULL),
  ('cde7ff6ff03c626f', 'client', $s213$S p a c e d$s213$, '2ba111743a13e4814bdbebc66f111af1605fcea4', FALSE, NULL),
  ('cdf6bf28ca817ee2', 'client', $s213$Podium$s213$, '971b5de3da8d8c6ca118ca7ced01592c6e67bf00', FALSE, NULL),
  ('ce525d05913ef730', 'client', $s213$HOST$s213$, 'e645477f66e745ec37b00fdc6d45d4196a39d1b0', FALSE, NULL),
  ('ce5c7a3baf9b6aa4', 'client', $s213$Deep evergreen blocks on a dimmed green-tinged backdrop.$s213$, 'ef88541ebbea1230910389468e407d07bf0c5d46', FALSE, NULL),
  ('ce72d18e916b01cb', 'client', $s213$<b>Start (need {0})</b>$s213$, '2ae94b94fa1cb8b9cea06583b16fb473b7cf95e1', FALSE, NULL),
  ('cea03e78dc4b3f47', 'client', $s213$Each player's worst ranked 1v1 opponents - minimum 3 series, top 5$s213$, '9d1ab2eac2466b4807b2f3d089264504bb335017', TRUE, NULL),
  ('cecd4fa7f2642aba', 'client', $s213$Beat Stan in a ranked series$s213$, '315b3a7ff79a5d9a069de5c4b40c89545a06f6e7', TRUE, NULL),
  ('cf1c3f9f78d8e96b', 'client', $s213$<color=#777>{0} dmg / {1} blocks</color>$s213$, 'd264b77b8a1c62b1fabaf5152b21d294d589c9bd', FALSE, NULL),
  ('cf5674f2c394e9f5', 'client', $s213$<color=#CCCCCC>FPS over the match</color>  <color=#99B3E6>you</color> <color=#888>vs</color> <color=#E69988>opponent</color>$s213$, 'fe71233ddf90b089c1810f30aa5db406e4137f50', FALSE, NULL),
  ('cf5aad12a3f6733b', 'client', $s213$Per-letter teal → violet gradient. Cold-night-sky shimmer.$s213$, 'e33445036b26cc0c43db07baa039c326346c1692', FALSE, NULL),
  ('cf5d29191379b896', 'game', $s213$+60% movement when moving towards the opponent$s213$, 'dd12999157ae0b9a1e421a24ae72f53a7e3b5572', FALSE, $s213$StringTableCards/CARD_CHASE_DESC$s213$),
  ('cf6154247e010be9', 'client', $s213$Indigo Name$s213$, '896aeebe623741dcf08c97d02e0111f4311b39e9', FALSE, NULL),
  ('d0083333e06cfaf1', 'client', $s213$<b>Recent Casual FFAs</b>  <color=#888>({0} total)</color>$s213$, 'ef69c20bdd62dbc159ca5c52064ba8b5eed1773e', FALSE, NULL),
  ('d07b8c2b5af84abf', 'client', $s213$Earned by {0} player  <color=#888>(in the order they got it - click again to close)</color>$s213$, '92cfc28e94f00f9407f870995c85eeaf388a1e30', FALSE, NULL),
  ('d0de71ee40ca3cbb', 'client', $s213$Newest Cosmetics$s213$, '2ee61b35c40fa92c9003c05e1d840a53a57de02b', FALSE, NULL),
  ('d0fb1e23e0d0e771', 'client', $s213$Grounded$s213$, 'd5580b73bfb2949ac6d9534c49ecd66ceba94e8c', FALSE, NULL),
  ('d13261664319d348', 'game', $s213$SPRAY$s213$, 'c075dbc1d193b8693966c4419c37347c4b26c0e8', FALSE, $s213$StringTableCards/CARD_SPRAY$s213$),
  ('d1444d8ccb532eed', 'client', $s213$StunPlayer null-guard — stops NRE spam when a player is destroyed mid-stun.$s213$, '702282ee3b8e83ab98bab528edd90b1983df3f06', FALSE, NULL),
  ('d14c7abccdd8c306', 'client', $s213$So close!$s213$, '6af055dbcaca305f2ac257c36800215d90053a17', FALSE, NULL),
  ('d14df263eb7a220f', 'client', $s213$FFA - {0} players - first to {1} points!$s213$, '67a5c91fdef543bcdf7b7bdc9f5efedaee64ff1b', FALSE, NULL),
  ('d1e0f9e0812bfad8', 'client', $s213$Close$s213$, 'bbfa773e5a63a5ea58c9b6207e608ca0120e592a', FALSE, NULL),
  ('d20bb0a584961c1a', 'client', $s213$w/ {0}$s213$, '4b6ebac7f834ce8bb4f4d9fb1155b902d4dac0ce', FALSE, NULL),
  ('d20df8f73196964a', 'client', $s213$Magical Hat$s213$, '2264719fbd4ee4267ba4f0518eff40062ee2c222', FALSE, NULL),
  ('d24503f7cd674e50', 'game', $s213$Projectile speed$s213$, '4136b3ae32a2e2c8926110d85348d158497cb1aa', FALSE, $s213$StringTableCards/STAT_PROJECTILE_SPEED$s213$),
  ('d2522009e9b6df5d', 'client', $s213$<color=#888>+{0} more live games - see the mode tabs</color>$s213$, 'b3f7940e3a2e53a3c6998385bb3eb9ecb181b4a2', FALSE, NULL),
  ('d26d0c08c02e905f', 'client', $s213$Removed from FFA queue after 30 minutes of searching - rejoin if you're still here!$s213$, '6bf365c0a188bdb8f985479b260fb60969b94fde', FALSE, NULL),
  ('d2f82d54461dd992', 'game', $s213$Press
[<sprite name=BUTTON_START>]
to save$s213$, '8aeb98f766a942b626836ca0bb0556dce68a8593', FALSE, $s213$StringTableDefault/PROMPT_START_TO_SAVE$s213$),
  ('d35f4660f0bbfa40', 'client', $s213$Most similar players$s213$, 'e587b0c4eec7778f4fbaca2fb50ebd61a8281422', FALSE, NULL),
  ('d3932de27d2daea3', 'client', $s213$Windup$s213$, 'c0365b235944850932d02480035816faa8e51970', FALSE, NULL),
  ('d3a2f4060b4d4faa', 'client', $s213$Charcoal$s213$, 'c81e2a08f7e0b5c4162685cc5b5ede3c1ec05062', FALSE, NULL),
  ('d3b7f9d9c9b6c4e4', 'client', $s213$Max cards:$s213$, '63168ee6a276883f20338ce8d90a19f0d972d8bd', FALSE, NULL),
  ('d413e1ab8ea0bfad', 'client', $s213$Win a ranked FFA 5-0 with 3 or more players (nobody else takes a point)$s213$, 'f4f2000844c532969d18577cc7de63b3bf1991d0', TRUE, NULL),
  ('d42e053f6b13ff64', 'client', $s213$<color=#66DD66>APPROVED</color>$s213$, 'bbcb83eae9983000e8f0f516b4318bb399bf67be', FALSE, NULL),
  ('d430467a2a2ef6c4', 'client', $s213$Couldn't get a link code$s213$, '81e4f95fa0ae1b315f8ca7ba3839315534787986', FALSE, NULL),
  ('d43beaf2e3883572', 'client', $s213$1v2 - How It Works$s213$, '07ea834b31ed15ee1715eb167f8547bad7f65dd2', FALSE, NULL),
  ('d4409b54016af376', 'client', $s213$Viewing: {0}  <color=#888>(press T to chat)</color>$s213$, 'b1b05687ebbfc658992e07a3906848c0791945fe', FALSE, NULL),
  ('d44b7e9515f5e841', 'client', $s213$Duo Leaderboard$s213$, 'bd67e561431b21dc42d2874a3fa3ff6248e3fa8a', FALSE, NULL),
  ('d493c9301c56b2ee', 'client', $s213$Rage Quit %$s213$, 'efd0aba4aac4e819dd347ce1f242e3276cb03825', FALSE, NULL),
  ('d4fad156d78d0d23', 'client', $s213$ (both press Play Now in F5 to start early)$s213$, '79ee5562e90ab9cb7bff0affa6fe06d4ff9292d7', FALSE, NULL),
  ('d538750901232607', 'client', $s213$Everyone else left the FFA — returning to menu.$s213$, '6416f89b4cb8bed2c6328f06cd044dcce9ff4570', FALSE, NULL),
  ('d561d401c70c4984', 'client', $s213$<color=#CCC>Shots fired vs hits</color>$s213$, '9d4ae048ec09950231d3ec5f92e1f1588918a061', FALSE, NULL),
  ('d57237dcfcae73a0', 'client', $s213$Portal session failed - are you signed in to Steam?$s213$, '43637cfe355335aa2af0c5f7474edd1bbe4ddf5e', FALSE, NULL),
  ('d5984dd5e64c618a', 'client', $s213$<color=#FFFFFF>{0}'s lobby</color>  <color=#7FD4FF>{1}/{2}</color>  <color=#888>open {3}</color>$s213$, '670a333677a5cc92eb43fc800aa6d4eebb14a325', FALSE, NULL),
  ('d5d0b8093f2eeaaa', 'game', $s213$REMOTE$s213$, '56ddbcf248ccde5c85f33b60acf834452cc75e80', FALSE, $s213$StringTableCards/CARD_REMOTE$s213$),
  ('d62cb7c9d2512266', 'client', $s213$<b>FFA Leaderboard</b>$s213$, '40f3cae7c67fa3d1910d78e9c52b02d732be942d', FALSE, NULL),
  ('d65e985d67ed0fe9', 'client', $s213$Stun null-guard$s213$, 'e41871fcab992523ffd460e45c652811a5aa37cb', FALSE, NULL),
  ('d689c0344f85b91a', 'client', $s213$Burgundy$s213$, 'f48fa5b998d1a20e5aefa573097ab4dfd104f679', FALSE, NULL),
  ('d69ecbdd58e9a4e3', 'game', $s213$QUICK SHOT$s213$, '470cb98a2d91b7adc7ff74ad3896f437d4593c85', FALSE, $s213$StringTableCards/CARD_QUICK_SHOT$s213$),
  ('d6bc949089d7ca60', 'client', $s213$Cancel$s213$, '77dfd2135f4db726c47299bb55be26f7f4525a46', FALSE, NULL),
  ('d6e8bd0bdac54aca', 'game', $s213$Blocking creates a field that slows and deals damage$s213$, '8dbd56da69dd06aaf006e5832ae4057cee231335', FALSE, $s213$StringTableCards/CARD_STATIC_FIELD_DESC$s213$),
  ('d6f2bbfbd961e078', 'client', $s213$Near-black blocks on a black background — max contrast.$s213$, '8c4507cb4fa8d59453f7770418e0681c1acdcfa1', FALSE, NULL),
  ('d7128fcb45c3d75f', 'game', $s213$Respawn once on death$s213$, '75cfd015a64587260d6a87421c3abab5a18ea801', FALSE, $s213$StringTableCards/CARD_PHOENIX_DESC$s213$),
  ('d714153f5c99e2a3', 'game', $s213$TOXIC CLOUD$s213$, '6c7af6f071afda6157b0ea5fff370b11d5c1dcc3', FALSE, $s213$StringTableCards/CARD_TOXIC_CLOUD$s213$),
  ('d71cb0cd1bf730ff', 'client', $s213$no opponent has taken 3+ series from them$s213$, '2ecd6485173e509e08f96a4f140ca72a57dfb91b', FALSE, NULL),
  ('d71f03de6cb4e7fa', 'client', $s213$<color=#888>Select 2+ players with rated FFA history to compare FFA Elo.</color>$s213$, '175f5e107a8f5d07e827fc11096c4a76d25bd3f2', FALSE, NULL),
  ('d72fb22fa6163e81', 'game', $s213$DAZZLE$s213$, '9387b0cb1f5e6881cdf630c309fdd4572750c3c1', FALSE, $s213$StringTableCards/CARD_DAZZLE$s213$),
  ('d76fe8f87a017c84', 'client', $s213$Select 2-12 players to find their common nemesis.$s213$, 'e80e8a6caafd8578b93bf98472d9d2e28b8940fd', FALSE, NULL),
  ('d77a171170a17a8d', 'client', $s213$No matches.$s213$, '0be6a25758e1f32b4250b6bc396b331ac0338f59', FALSE, NULL),
  ('d78da2b0a30c5e23', 'client', $s213$Only the host can change lobby settings.$s213$, 'f729ffc338677e9fbcc52e7444381ddaa17edbc4', FALSE, NULL),
  ('d7951aef0fa367af', 'client', $s213$Searching... {0}m {1}s  +/-{2}$s213$, '7e0098e5bb901181e4f78f50b98fe1c46abf73b9', FALSE, NULL),
  ('d7d0e9e219b53281', 'client', $s213$Casicorn's Eyes$s213$, '75114685463170b6592d652473ef40eb0a6eceb7', FALSE, NULL),
  ('d7dc886afa083aff', 'client', $s213$Achievement Grid$s213$, '6a57dfd4acb6187e4a37477d30874ac5ee9bffb7', FALSE, NULL),
  ('d820383e18f33ceb', 'client', $s213$FFA - How It Works$s213$, 'bc6c4123d4239b8e45bc714df9bdbcd2cfadd872', FALSE, NULL),
  ('d8852fbbce7d5315', 'client', $s213$Clean white body color.$s213$, 'b9a010b399b7896b4c0e26e06e1b2d16738d947f', FALSE, NULL),
  ('d8ba12181cae06db', 'client', $s213$Icy blue trail fading to white. Two-color gradient.$s213$, 'b18f1b30f790bc9203c185bcbf4e886783ef9d75', FALSE, NULL),
  ('d8dffa7fcf53bf24', 'client', $s213$<color={0}>shots fired</color> <color=#888>·</color> <color={1}>shots hit</color>$s213$, 'e82e104b11bebbce91bb2e80656c0a1caa7ff995', FALSE, NULL),
  ('d8ede9573dbac9c7', 'client', $s213$<color=#FFE580>1stx{0}</color>  <color=#C8C8C8>2ndx{1}</color>  <color=#D4894A>3rdx{2}</color>  <color=#888>(played {3})</color>$s213$, '7e01cae4dee9862c4d799b06bd66d619c0c0bf92', FALSE, NULL),
  ('d8fb230540e18c73', 'client', $s213$<color=#FFB088>Link Discord first (Home tab) to sign up.</color>$s213$, '0587b7ed95b4b633c385c0ebe89543cd3733df52', FALSE, NULL),
  ('d97792202e616ada', 'client', $s213$Ranked turned ON so your tournament results record - and it stays ON after the match. Turn it off in Settings if you don't want later games rated.$s213$, '75b494a0a2d8f1b4213f4d55bf0235723548ac18', TRUE, NULL),
  ('d997b5b7f17ee80f', 'client', $s213$Grant Artist...$s213$, 'b37dab8c0ef031eeb7a1530584d3d3a7c80629de', FALSE, NULL),
  ('d9f0ab270fa95deb', 'client', $s213$Locks the map to ROUNDS' Poison palette (acid green).$s213$, '1ca68d13c18e8e434805d0a510762510ca601ac1', FALSE, NULL),
  ('da1b72d2fb954b57', 'game', $s213$Adds a shotgun vibe to your attack$s213$, 'faa00a67e6ef39a491f7eb2cbde4edb5d12c1f06', FALSE, $s213$StringTableCards/CARD_BUCKSHOT_DESC$s213$),
  ('da364c22af80c86d', 'client', $s213$FFA: placed #{0} (+{1}xp)$s213$, '514a72f6e0de5d80e678c0de5bd652d724192627', FALSE, NULL),
  ('da58a93eac39ac88', 'client', $s213$Last game for me$s213$, '92e69a3f1985413e1879f796e1558f0285185041', FALSE, NULL),
  ('da6813ba66e8657e', 'client', $s213$Moderation$s213$, '28f3ebe279d7e2b400db6b5d769827993abc0a51', FALSE, NULL),
  ('da749f60b9684f21', 'client', $s213$<color=#FF6666>Deletion failed: {0}</color>$s213$, 'd7e0867b602018ada5fd37c4c1a1842af50c54b1', FALSE, NULL),
  ('da7931ad7df4a64a', 'client', $s213$FFA VICTORY! +{0}xp$s213$, '16bc5bdd632da2ad2fd7bce2af52ce21d3809eb5', FALSE, NULL),
  ('da9f507760953b88', 'client', $s213$<color=#FF6688>* Live Ranked Series</color>$s213$, 'f28720141e74a4c015a37e1d151f0924da55a676', TRUE, NULL),
  ('dae179ea3b8774a4', 'client', $s213$Unknown$s213$, 'bc7819b34ff87570745fbe461e36a16f80e562ce', FALSE, NULL),
  ('db241e1d44efebf0', 'game', $s213$Waiting for$s213$, '20e0b197969178eebc409975c732488b57d52839', FALSE, $s213$StringTableDefault/PROMPT_HOSTING$s213$),
  ('db3b02b95016e341', 'client', $s213$Play Now sent - starts when your opponent presses it too$s213$, '3e9e7a22260ce183e8a00a562ad305510c9221a5', FALSE, NULL),
  ('db64d34801d9c8ef', 'client', $s213$Maps$s213$, '80071cd75107cd5c4afdb2571725ea6733631038', FALSE, NULL),
  ('db7dd81ac45d3a49', 'client', $s213$<color=#7FE8C3>Max pot - 16 players!</color>$s213$, '1933cbafaed52c8b035f1a5e2855631e4afbee83', FALSE, NULL),
  ('db8d28abe7a0803f', 'client', $s213$Series ID (UUID)$s213$, '3618548cc4b479da3739bc2676fcb6cabf91722e', FALSE, NULL),
  ('db8fec39d72e6a3e', 'client', $s213$Play Now failed$s213$, 'd4407fed7110ec6103497b2404163e92ec4df375', FALSE, NULL),
  ('dbcea9ac17806e03', 'client', $s213$VOTING / SIGNUPS OPEN$s213$, '67e7a92881ae1200be8d73f68942f37d8b841edd', FALSE, NULL),
  ('dc0301976907f1c2', 'game', $s213$Blocking scans the area for enemies. You automatically shoot any enemy found.$s213$, 'd8e25405f0eeb973e84b4db5dc0781c1378f1773', FALSE, $s213$StringTableCards/CARD_RADAR_SHOT_DESC$s213$),
  ('dc6588862dd02f39', 'client', $s213${0} <b>won</b> {1}-{2}$s213$, '6aefdf8cf3774a76db4f21466926eaa31e1bf15c', FALSE, NULL),
  ('dc89fb90826ebe05', 'client', $s213$4/4 ready! Joining 2v2...$s213$, '30cd3f91a4a9bd43638702fb0b3a04ee0f4306c8', FALSE, NULL),
  ('dc9683e025054f9e', 'client', $s213$All$s213$, '6a72085653e4c5be8c7640c868ef787cbcf063d1', FALSE, NULL),
  ('dca0e950beda5275', 'client', $s213$Loading achievements...$s213$, '1fd2394cf3947091a4cce007bdc3ba63bac85efe', FALSE, NULL),
  ('dca34071afb963ee', 'client', $s213$Solo -$s213$, '52381ad42460aca3d0250e9c8261b125d52754dd', FALSE, NULL),
  ('dca50b9ed118cbdb', 'client', $s213$Beat Sid in a ranked series$s213$, 'c079b59c65f4a283f90f1a0511b37ff20c393880', TRUE, NULL),
  ('dcbcb0e4299e1c29', 'client', $s213$Amethyst$s213$, '1ef532cce6fea64ba94eed1237cc785bcbd74ad0', FALSE, NULL),
  ('dcc9b37fdb87b814', 'client', $s213$Yellow Cursor$s213$, 'ee87adceb5e62cb4131c19198f5051250f0d91c2', FALSE, NULL),
  ('dcea6ed7a205f942', 'client', $s213$Win 5-0 with Phoenix without losing a life$s213$, 'c35aa7a4bc5418558d8050151209b86ec073635d', FALSE, NULL),
  ('dd4ea253253e8050', 'client', $s213$<color=#FFD94D>in progress</color>$s213$, '4aa5a0655e06b7f207582228c71b66d5028d5cb9', FALSE, NULL),
  ('dd76e64b87e0aa28', 'client', $s213$Warm cream + tan palette.$s213$, '4700ad8692d08573598fbb4950115440b6c1c7ac', FALSE, NULL),
  ('dd9ed6335db7e352', 'client', $s213$MATCH FOUND!  vs {0} ({1:F0})$s213$, '8d42a8ff760a17a66d663d7b77b0ee840976a372', FALSE, NULL),
  ('de20704300c6edfd', 'client', $s213$LEVEL UP!  Level {0}$s213$, '3a7f6bd064529d32665a9bfdacf161baab97a428', FALSE, NULL),
  ('de467d3edb721838', 'client', $s213$Cap bullet-hit particles at 2/frame — biggest user-visible win on heavy firefights.$s213$, '4b1b1758c6a36dfe7213f6432757a25f25b44fb6', FALSE, NULL),
  ('de85918db7d321c6', 'game', $s213$GLASS CANNON$s213$, '4bc00f32ce4492bacd5886b88fbe94204aca6313', FALSE, $s213$StringTableCards/CARD_GLASS_CANNON$s213$),
  ('dec78d4fd2107f1e', 'game', $s213$Blocking triggers another, delayed block$s213$, 'bf738ce6ebe2c2bbaa10a74cccfbcda05b0ec0d4', FALSE, $s213$StringTableCards/CARD_ECHO_DESC$s213$),
  ('deffcecb2408c130', 'client', $s213$No ranked 1v1 series recorded for the selected players yet.$s213$, '7b6404043fbac5592409655ce21c338538da12d1', TRUE, NULL),
  ('df1a102e003bcc28', 'client', $s213$Recent Ranked Series$s213$, 'cd1b79232cfd3e7f9b778644754e2edcd0055747', TRUE, NULL),
  ('df78316425dc18c5', 'game', $s213$BURST$s213$, '9ce5d0f6a1f87b8df6a22465f8b3ef966431e2d9', FALSE, $s213$StringTableCards/CARD_BURST$s213$),
  ('e06dcf032f5a37d2', 'game', $s213$Manage blocklist$s213$, '4c1894bd6aa5379146515a928925ad1ff8c88735', FALSE, $s213$StringTableDefault/BUTTON_BLOCKLIST$s213$),
  ('e089833a65a32244', 'game', $s213$BARRAGE$s213$, '36458d1195b5500723ec845ebe1335f5377c2109', FALSE, $s213$StringTableCards/CARD_BARRAGE$s213$),
  ('e08afd75068a4ec9', 'game', $s213$Refresh$s213$, '56e3badc4e6c5cc95e0ea5a9a878b9bd09f319d4', FALSE, $s213$StringTableCards/CARD_REFRESH$s213$),
  ('e08bba79fc405bb1', 'client', $s213$<color=#00FF00>Linked to Discord</color> ({0})$s213$, '0be65425d5df8a3381741d8b1359dde94d3a039a', FALSE, NULL),
  ('e0b4ad50d4d4d3b6', 'client', $s213$Wrong password — try again.$s213$, '6703be73dbca5860e567df343a6ee94a965a7cee', FALSE, NULL),
  ('e0c9d155171ec734', 'client', $s213$Couldn't join that lobby.$s213$, '6deea8800284674bfc7e7982c407d937829ef446', FALSE, NULL),
  ('e0ddb10fc3343e26', 'client', $s213$Build Types$s213$, 'f698b4cf5e65de3e16b37e9eec6578bda803cbe5', FALSE, NULL),
  ('e0ed74112b5d0272', 'client', $s213$Ranked 1v1 - 2v2 - tournaments - cosmetics   <color=#666>v{0}</color>$s213$, '4e02c65a3230ab22a99e846d79d4b4d46cd9901e', TRUE, NULL),
  ('e0fcf786dd7b7b90', 'client', $s213$   -   SAME CARDS FOR EVERYONE$s213$, '715f30506d8f436b4787b770a4cc87eabfae38f5', FALSE, NULL),
  ('e11202f27fe397f2', 'client', $s213$<color=#44FF44>Close ROUNDS to apply update</color>$s213$, '5591a9faf2a275842c5e3b9d932091abfda415ee', FALSE, NULL),
  ('e12cdd99b210ce07', 'client', $s213$<color=#7788AA><i>search...</i></color>$s213$, 'b86f3dee9b32aff1281ab7302c8f65308a6457fe', FALSE, NULL),
  ('e136defac1fab317', 'game', $s213$Blocking increases the damage and speed of your next shot.
The shot also triggers any on block abilities where it lands.$s213$, '92ba9cabfe72adbfba042e4ed214cf98c61f66aa', FALSE, $s213$StringTableCards/CARD_EMPOWER_DESC$s213$),
  ('e1430b629fdd11db', 'client', $s213$Your FFA is already starting — leave it first if you meant to switch.$s213$, '474d42f7f1bc7ec4fb3361d3ab3259f46e3e8969', FALSE, NULL),
  ('e15f7f445c46ae93', 'client', $s213$Dusk$s213$, '4db13aa08e06f68b46f6d3819cdb45cae2b882d0', FALSE, NULL),
  ('e165e5ae840a62fb', 'client', $s213$one size at a time$s213$, '7ab9c8362a5abfb2e9bfcbaa02d5a3f8fc771179', FALSE, NULL),
  ('e16b3887c2129190', 'game', $s213$Being 
Edited$s213$, '94d0af801156cf4c3f4cca8b7efaecf25aeaaf0d', FALSE, $s213$StringTableDefault/PROMPT_BEINGEDITED$s213$),
  ('e18bda3d30d526af', 'client', $s213$Thorn Crown$s213$, '526a09199b53f93b3d5427114172a2671c6cd74e', FALSE, NULL),
  ('e195217b8dd18c80', 'client', $s213$GitHub$s213$, '5442e2b64fa09764b9f593867e59a97292c84059', FALSE, NULL),
  ('e1c6a7b3b01a5ea3', 'game', $s213$+50% movement speed 3s after dealing DMG$s213$, 'c54531dc5619aa09aa7340a024d95f61b7343a33', FALSE, $s213$StringTableCards/CARD_TASTE_OF_BLOOD_DESC — Damage$s213$),
  ('e1dbf69f1828cbc7', 'client', $s213$Worn by those who climbed the mountain.$s213$, 'bca16e3079936dcb4198b1cfc3ffba6610a7e47d', FALSE, NULL),
  ('e1e93a22eecf9cea', 'client', $s213$Ping / region display: <color=#FF9966>OFF</color>$s213$, '57352048202016805118230d31272211e396b95f', FALSE, NULL),
  ('e209685ce7cdc480', 'client', $s213$Balance: -$s213$, 'ee03e71aa0ce092fd93e310a80b158302071fec0', FALSE, NULL),
  ('e20ec9323e546397', 'client', $s213$Shifts through the spectrum as you move. Pure show-off.$s213$, 'a35631709ba4e1f56d3e2be869b3d25dd947b31a', FALSE, NULL),
  ('e222892ca8d0f4f1', 'client', $s213$Velvet$s213$, '50c8e9195e5ecd5791a33f4dc54310bbea98a77f', FALSE, NULL),
  ('e23866b89558a941', 'client', $s213$Sky$s213$, 'b3d97fd6dece388a968e367f3ac4b9e64d739f52', FALSE, NULL),
  ('e257fa5f452ec7c9', 'client', $s213$Input overlay: <color=#88FF88>ON</color>$s213$, 'a24644dfa7613e54acd8966b3c2c10881854a735', FALSE, NULL),
  ('e268f01337cec8c0', 'client', $s213$Signups$s213$, '09c26725abca4f5f770be1e26e44b5ee79b7a7bd', FALSE, NULL),
  ('e2b1e7177aa1f43b', 'client', $s213$Manual restoration marked complete.$s213$, '357c98d97ceb16fd653205ebffc3a150b4f65503', FALSE, NULL),
  ('e2d0ca300c5016eb', 'client', $s213$How the mod counts your combat and match stats, in plain terms.

<color=#FFD94D><b>HIT %</b></color>

- The denominator counts BULLETS fired, not clicks.
  One Buckshot click counts every pellet; bursts and
  charge volleys multiply it too.
- Clicks during reload or cooldown don't count, and
  card-spawned shooters never count.
- The numerator counts direct, unblocked hits on
  enemies only. Self-hits, teammates, poison and burn
  ticks, explosions and thorns never count.

<color=#FFD94D><b>BLOCK SUCCESS</b></color>

- One OFF-COOLDOWN block activation = one attempt
  (right-clicks during cooldown don't count), and at
  most ONE success no matter how many bullets that
  block absorbs.
- Echo repeats and Shield Charge dashes belong to the
  right-click that started them - they never add
  attempts.
- Abyssal / Shields Up auto-blocks are not attempts,
  though an auto-block absorbing within the right-click's
  short credit window can claim its success.
- Blocking your OWN reflected bullet DOES count as a
  success.

<color=#FFD94D><b>RAGE QUIT % VS LEAVE %</b></color>

- Rage Quit % (Compare tab) is CASUAL 1v1 only:
  casual disconnects divided by casual matches plus
  counted casual DCs.
- The leaderboard's Leave column is the RANKED formula:
  ranked DCs divided by ranked series wins + losses + DCs.

<color=#FFD94D><b>AVG GAME LENGTH</b></color>

- The clock starts when the first round's movement
  begins (after the initial picks) and includes every
  later card pick and transition until game over.

<color=#FFD94D><b>WHAT FEEDS LIFETIME STATS</b></color>

- Lifetime Hit/Block/Keys stats accumulate from 1v1
  games only (ranked + casual), and only from the match
  reporter's own side.
- 2v2 and FFA record the same stats per game (visible
  on each game's row) but they don't feed the lifetime
  percentages.
- FFA / 2v2 / 1v2 metrics in Compare come from their
  own tables.

<color=#FFD94D><b>TIMELINE GRAPHS</b></color>

- Graphs sample every 3-5 seconds (longer games
  compress older samples), so graph ratios can differ
  slightly from the exact totals.$s213$, '9b7d3ac769f76e71e202bc1fded94a850259a301', TRUE, NULL),
  ('e2d283f46c6565a8', 'client', $s213$<color=#FFB347>1v2 lobby pending</color> — Leave to dissolve it if nothing happens.$s213$, 'e80eed1854086d8b9db4aefdb9f0edcdfe901eb8', FALSE, NULL),
  ('e307fa465c2af7fb', 'client', $s213$Curved crimson horns for your inner demon.$s213$, 'fc9e3a357cf300a24d8e3496e2a38f19a2b8d2ee', FALSE, NULL),
  ('e316e9a339cb0454', 'client', $s213$Rare$s213$, 'cce370d2f9781af0f85d591ccdfad1fe365a619f', FALSE, NULL),
  ('e31bb2a57a268bb8', 'client', $s213$<color=#CCCCCC>Scoring history</color>  <color=#66DD66>you</color> <color=#888>vs</color> <color=#DD7777>opponent</color>$s213$, '1a2d6cafc8df6926eaa128130f8910894b888c8e', FALSE, NULL),
  ('e32ff3a09330d729', 'client', $s213$(placements {0})$s213$, '4199a762764740366c8e076eb4282d07e375c215', FALSE, NULL),
  ('e360df22fbb855ff', 'client', $s213$Couldn't rejoin your private {0} lobby — join it again from the browser.$s213$, 'b6ebcb596b839d72bedab659eb0497ee464a5e48', FALSE, NULL),
  ('e3ab55dbf190f7a0', 'game', $s213$ATKSPD$s213$, '500b368d2548c54ca3b29a3fff6ec8f61e959fed', FALSE, $s213$StringTableCards/STAT_ATKSPD — Attack Speed$s213$),
  ('e3abcd5edb274ed5', 'client', $s213$FFA Avg Kills$s213$, '9d050af1c4807da1efe90831e72c93ef6cea41fe', FALSE, NULL),
  ('e3bb623ce7ca2b09', 'client', $s213${0} ready! Joining...$s213$, '62abf774b7f12a0871590e49783f1c035359ecda', FALSE, NULL),
  ('e3e5ec5ee886c897', 'client', $s213$A small grey cat based on my real cat$s213$, '1c8cdb1aadf7440df733f47304d419a4e7dc9ab2', FALSE, NULL),
  ('e438c01d296a47e9', 'game', $s213$Bullets spawn a poison cloud on impact. 
Clouds deal damage and slow.$s213$, '63c22c07f95b9c77b5278d3b10a80e002f857070', FALSE, $s213$StringTableCards/CARD_TOXIC_CLOUD_DESC$s213$),
  ('e46943688b727f28', 'client', $s213$FFA STARTING IN {0}...$s213$, '3b64921f2960bf7a10b9e3f462af56594d56d312', FALSE, NULL),
  ('e46a4b0fa0cb3b10', 'client', $s213$Clock:$s213$, '4665f476a8337513ecd7afa6957a8c4210c50459', FALSE, NULL),
  ('e48c0380bfbd05a1', 'client', $s213$Delete My Data$s213$, '07c349dd6285cec25ea784f21704b057dbf48f57', TRUE, NULL),
  ('e494424cf053f992', 'client', $s213$<color=#00FFFF>{0}</color>  - type <color=#FFFFFF>!link {1}</color> in Discord$s213$, '4b8ca35da1156502e8dd33e7421caeb030b28894', FALSE, NULL),
  ('e49544b02de62bd7', 'game', $s213$TIMED DETONATION$s213$, 'ae11dfcd56c2fca956df64ec5938f7deed89ba27', FALSE, $s213$StringTableCards/CARD_TIMED_DETONATION$s213$),
  ('e4b1a55872ab7dc2', 'client', $s213$Reload$s213$, 'cce7155371fc26686b89c7452337d8419692f31e', FALSE, NULL),
  ('e4e808986976f25b', 'client', $s213$<color=#7FD4FF>1v2:</color> {0}W/{1}L$s213$, '5223c763248dbdfa305993651bdeeca05fe2509e', FALSE, NULL),
  ('e4ed2e45c87a71a4', 'client', $s213$Hot-pink neon name with a soft glow halo. Visible to everyone; modded players also see the glow.$s213$, '55d34abe601f847d5d3c021c49f5bf80f5db5d6e', FALSE, NULL),
  ('e5473f59c2cad614', 'game', $s213$Blocking pulls enemies towards you$s213$, '91bbac2d58276906897f7c86f4e6ce9799b15ae9', FALSE, $s213$StringTableCards/CARD_IMPLODE_DESC$s213$),
  ('e56a017d8db3c1c0', 'client', $s213$Top Cards$s213$, '48acb7066a69a96da3b4f6d5b775f433ce711dfd', FALSE, NULL),
  ('e571d7422af03bcb', 'client', $s213$Titan$s213$, '0ce8e5dac8f6f61d3eba42d016f55230f093a2c7', FALSE, NULL),
  ('e573bb0bf4f2ab3b', 'client', $s213$Report approved for recovery - an ordered replay is still required.$s213$, '025d23a1daab37a02af4e5ffc59a9a15b88553a4', FALSE, NULL),
  ('e59b71033ad70521', 'client', $s213$Waiting for all 3 players to connect — hang tight...$s213$, 'f7585ab975d96d0a37f8cb0b66d945ba600cafd2', FALSE, NULL),
  ('e5a406b81a6a55f6', 'client', $s213$Now spectating.$s213$, '22ad4e1e5ad8f9ccd91c08cfc29e216684bad88b', FALSE, NULL),
  ('e5afdc07523f8396', 'client', $s213$Game {0} - {1} players$s213$, '0b9ce69dc04eeb6c6027497ff1dc0da1030da5d2', FALSE, NULL),
  ('e5e3095c005a72cc', 'client', $s213$Warm orange blocks on a sunset-toned backdrop.$s213$, '8b99503fef5328110821262702556cf11f1dc23b', FALSE, NULL),
  ('e5e8c7a46ed4b12e', 'game', $s213$Splash DMG$s213$, 'f83bdc9ec4bdd67182052b7358c6b54b4a49b185', FALSE, $s213$StringTableCards/STAT_SPLASH_DMG — Damage$s213$),
  ('e6066223b0b305c1', 'client', $s213$unknown$s213$, '50d8b4a941c26b89482c94ab324b5a274f9ced66', FALSE, NULL),
  ('e635b598d330a8e2', 'client', $s213$<color=#FFCC44>In {0}'s lobby</color> - waiting for the host to start ({1} in).$s213$, '7ae1c8b04ad592dfcf2b268a33874715bec934da', FALSE, NULL),
  ('e6683e03f8794bf3', 'client', $s213$<b>FFA - FREE-FOR-ALL (3-10 players)</b>$s213$, 'cd8b5dda58ee78702ca1791aad1288a0c39510ff', FALSE, NULL),
  ('e673a6b24221e740', 'client', $s213$Chat notifications: <color=#88FF88>ON</color>$s213$, '00c68073e93e01b847fdeeb7d6d09c4b0775dc02', FALSE, NULL),
  ('e683e24fa226fac0', 'client', $s213$Ban {0}$s213$, 'eb7f64cd8b72a17bf3d79c29522fb9ef26afc5fa', TRUE, NULL),
  ('e6e6c58af19307ec', 'client', $s213$<color=#888>{0}% pen</color>$s213$, 'bac173ecd4e58b18541d82f573f1faaa20dff16c', FALSE, NULL),
  ('e6ed090bbd8195be', 'client', $s213$Removes you from every queue and lobby in every mode — 1v1, 2v2, 1v2 and FFA.
Use this if the game thinks you're still in a match you've already left, or if joining a queue keeps telling you you're busy. It won't affect a game you're actually playing, and it never touches your stats, gold or rating.$s213$, '2a1b006c4b79cdc5a4c7c30b4ee51652307056c3', TRUE, NULL),
  ('e74a5c961fcffa93', 'client', $s213$Amber Name$s213$, '55879cd931aa5e3de8d5fdf3e442cf30a8cc34c8', FALSE, NULL),
  ('e75c80cd71770ea9', 'client', $s213$In a game — no results yet$s213$, '3c81f3e5dbb58583795d18d6b4d1d5d6fb61fd43', FALSE, NULL),
  ('e763ddfa52f56c01', 'client', $s213$A rich, gleaming gold.$s213$, 'f9440b94808ba8103d9205ae89bd4358d0263fec', TRUE, NULL),
  ('e76f8724d967828e', 'client', $s213$2v2 Rating$s213$, 'e3fc7fd1e8476c924415195ceb0e256825cca8af', FALSE, NULL),
  ('e77878efbc01c8b8', 'client', $s213$Total Mayhem$s213$, '584febf2226943cce895111f9b1ff34d68fa3a3a', FALSE, NULL),
  ('e77e0b2592889257', 'client', $s213$Phoenix Flame$s213$, 'e667878de6874deec7efb0c65ddf39bb296521af', FALSE, NULL),
  ('e7f929f2fc14ab9b', 'client', $s213$<b><color={0}>{1}</color></b>  <color=#888>(unranked - {2} players)</color>$s213$, '37e09b5ca64b2263c149efe2e584442a59ccf277', TRUE, NULL),
  ('e82cae6d83d41b06', 'client', $s213$No active tournament$s213$, '7688eb7fae9a048dbbeed0e73b646bf684cc09f2', FALSE, NULL),
  ('e836f1d3f21f7e01', 'client', $s213$Duo$s213$, '3c5d9cd03387fb41a856eb94a3f12c1e7c45d2c1', FALSE, NULL),
  ('e848a724fd07283d', 'client', $s213$Reason (optional)$s213$, 'f6826f8fc9b458f2ce8117b27474b6a55d07dc28', FALSE, NULL),
  ('e851feffcafec1cc', 'client', $s213$Opponent hasn't connected yet — they have a few minutes of grace. Hang tight...$s213$, 'cb6da8e1dc6f7c4664c82d774f5454107035e07d', FALSE, NULL),
  ('e86c99634581b48f', 'client', $s213$Win a game 5-0 with Burst in your build$s213$, 'a00c23aea46eb757db62174a1007698f8d5679b6', FALSE, NULL),
  ('e8e4896cddd754fe', 'client', $s213$Steam ID copied to clipboard$s213$, '18f1faa5e7e0cbe5ab8a7a7fd26904d28973e2fd', FALSE, NULL),
  ('e8ed682b2d08934d', 'client', $s213$Two teams of two play a best-of-3 series.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- Random queue uses an Elo band that widens as you wait.
  The server auto-balances the teams.
- Custom lobbies have no Elo band.
  Joining the lobby is consent to play.
- All 4 players have 120 seconds to ready up.
  If time expires, everyone returns to searching.
- After an auto-queue game with a point margin of 3 or more,
  the weakest winner may swap with the strongest loser.

<color=#FFD94D><b>SCORING</b></color>

- The first team to win 2 games wins the series.
- 2v2 uses its own Glicko rating.
  It does not change your 1v1 rating.
- Rating updates after the completed series.
- W-L and WR count completed series, not individual games.

<color=#FFD94D><b>REWARDS</b></color>

- Each game gives 600 base XP.
  A game win gets x1.5, for 900 base XP.
- A series win gives 50 base Gold.
  A series loss gives 25 base Gold.
- The opposing team's rating tier can multiply base rewards.
- Game XP converts to Gold at 100 XP = 1 Gold.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

<color=#7FD4FF>Rank</color> - Position in the currently selected sort.
<color=#7FD4FF>Player</color> - The player's display name.
<color=#7FD4FF>Rating</color> - The player's separate 2v2 Glicko rating.
<color=#7FD4FF>W-L</color> - Completed series won and lost.
<color=#7FD4FF>WR</color> - Series wins divided by completed series.
<color=#7FD4FF>Avg Mate Elo</color> - Average rating of past teammates.
  A teammate uses 2v2 rating after 5 completed series.
  Before that, their 1v1 rating is used, or 1500 if absent.
<color=#7FD4FF>Gold</color> - Lifetime Gold earned from 2v2 only.
<color=#7FD4FF>XP</color> - Lifetime XP earned from 2v2 only.
  Gold and XP do not affect your rating-based rank.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving mid-game is recorded.$s213$, '8291e35ae377151b9711fbbc7c1b59a5e1517881', TRUE, NULL),
  ('e8f48481d4bd7c9c', 'client', $s213$Starts: <color=#FFDE88>{0}</color>$s213$, 'e3c95802a4529c0f536dbb1eaf80bab813a2d5c0', FALSE, NULL),
  ('e9039fd4f6a491aa', 'client', $s213$Language / Idioma / Язык / Мова / Språk$s213$, '640dd4aaa45df7e6f11465d07dd43664017a2e9b', FALSE, NULL),
  ('e91af1cc53639bfd', 'client', $s213$Bold$s213$, '19e07430eed6d97d6d73cb4a2967b1f316520f54', FALSE, NULL),
  ('e91d1e0a65eab267', 'client', $s213$<color=#99CCFF>Block:</color> -$s213$, '8f1df6a51b94dd5af8db679c73a8d3cb4f2eea32', FALSE, NULL),
  ('e93c7974349c8d09', 'client', $s213$<b>What happened?</b> <color=#FF9966>(required)</color>$s213$, '8500bc4d384b9f21e290610ab0c760e7ca028ba7', FALSE, NULL),
  ('e94131143feaca60', 'client', $s213$Help translate the mod - opens the web portal in your browser. An admin has to give you translator access before you can submit.$s213$, '665bfd72831ac98231ad8352f88ee64ae4aacbef', FALSE, NULL),
  ('e9939d439ec9d4f0', 'client', $s213$Player$s213$, 'e53407cfe1a5156b9f0d1eed3bab5ef3ae75cfd8', FALSE, NULL),
  ('e9d2426ce52ddf48', 'client', $s213$Faced by$s213$, '68ba0f7e976a1c577ac93fb93ab0080fae538776', FALSE, NULL),
  ('e9e3c0515899c568', 'client', $s213$Sorry!$s213$, '22959ede33b65d25ed4762705597fb8b954d3a6b', FALSE, NULL),
  ('e9fb8ffbaab655f7', 'client', $s213$Syncing...$s213$, 'e5c7727a106e2f8e5e183ec9a8b5c48855e2b834', FALSE, NULL),
  ('ea0992cf6e04fc9f', 'client', $s213$Category:$s213$, '61b9204fa30ab100d2a82ad42f62e455b1d2df3a', FALSE, NULL),
  ('ea83337993a45755', 'client', $s213$<color=#00FF00>WON</color>$s213$, '585d7397eb695e72f42e0bacc337f5de1767d40a', FALSE, NULL),
  ('eaa378854b4ff2f1', 'game', $s213$Bullet explodes on impact$s213$, 'c18d7d533a5f061b72ed65db5e75de2cb0bc4b4d', FALSE, $s213$StringTableCards/CARD_EXPLOSIVE_BULLET_DESC$s213$),
  ('eaae164b9973a5a5', 'client', $s213$Name$s213$, '709a23220f2c3d64d1e1d6d18c4d5280f8d82fca', FALSE, NULL),
  ('eae155f580deb959', 'client', $s213$Reach 1700 rating in ranked (1v1 or 2v2)$s213$, '9fcd0e210699f50c689ecb8e2fc7fa9105367085', TRUE, NULL),
  ('eb1386dc31e8fcf3', 'client', $s213$Rematch?$s213$, '2b8ca1c6f332d7ac6f7dc56c8abc7aceaae03d75', FALSE, NULL),
  ('eb382d1678858a9c', 'client', $s213$Teal$s213$, 'df0ad373b7ff60d6a8987458fb00c1e4832ef605', FALSE, NULL),
  ('eb598318c184738f', 'client', $s213$No achievement data.$s213$, 'b701924a9d0c728225b76f6f434ef89766a3c2bf', FALSE, NULL),
  ('eb897bb9be7c79b8', 'client', $s213$unlimited$s213$, 'e1a6f0b6f73a57a8b3ee30419e28f6cb95143908', FALSE, NULL),
  ('eba3826ea7d1aee5', 'client', $s213$no data$s213$, '4d968a30a022f41e9826f0cf09d36c2b6a22bfa4', FALSE, NULL),
  ('ebb00fa13d937164', 'client', $s213$<color=#664444>-> {0} bet {1}g on {2} - lost</color>$s213$, '6d963ba9ef802936517c691221c2197fe179c635', FALSE, NULL),
  ('ec056671a7384f77', 'client', $s213$Timezone:$s213$, '777fcbd0b5a6a370b32741af5ca3cdb45c6a347a', FALSE, NULL),
  ('ec3284a5904bb9a1', 'client', $s213$vs {0}$s213$, '8941784e7b51bc9575c6ad7277d273019630104a', FALSE, NULL),
  ('ec3afa95260402c3', 'client', $s213$Casual History$s213$, '7d4c84fbad4425fa4f4502f5b3057dccd0a14f3b', FALSE, NULL),
  ('ec3bbc79c58671cc', 'client', $s213$Casual: -$s213$, 'fc34d0bcd4850d867f1b6d5e71e32128dfd8ec52', FALSE, NULL),
  ('ec409b24b6baa83d', 'client', $s213$<color=#FFD080>Match-found screen might be stuck</color>$s213$, '1a7f980a682a95d6db7309ad484f1c7ff80776a2', FALSE, NULL),
  ('ec771eaf68f39ebf', 'client', $s213$Info$s213$, '4b631f69842530d659306c8f06dbad594a6b1807', FALSE, NULL),
  ('ecd2dadccaae041d', 'client', $s213$Competitive ROUNDS — Data Consent$s213$, '8b7d0e0643225d0905a09fd3c73bf19c5d45ad5f', TRUE, NULL),
  ('ed148bb9c7be8e8c', 'client', $s213$Fast Forward main$s213$, 'fabb304f63738fae1d8b8290dfa48d39166bd688', FALSE, NULL),
  ('ed2b3ea93e519ce2', 'client', $s213$Could not spectate this game.$s213$, 'ea1ef48f04095e33d74e44ac5f55806cdc6f039e', FALSE, NULL),
  ('ed2bee0265a07157', 'client', $s213$Removed from 2v2 queue after 30 minutes of searching - rejoin if you're still here!$s213$, '518c2f6c92751ed83a03f0e954f5f1656bd529c0', FALSE, NULL),
  ('ed2d10114d8fa1c7', 'client', $s213$Gilded$s213$, '109fe33ee568cdbfcc2bccb3d5667edb0cfcc4a9', FALSE, NULL),
  ('ed811fd03e3e7985', 'client', $s213$Set Active$s213$, '758d7f7281c0192f6d09ba1663e7af25cc8c0e15', FALSE, NULL),
  ('edad4bf793d2498e', 'client', $s213$<b>Custom 1v2 Lobbies</b>$s213$, '9296b97e93a753fb9f80a32d3fcba31eeafa3d14', FALSE, NULL),
  ('ee0f83d5227f6a52', 'game', $s213$LEECH$s213$, 'dd70321d7b240369f6a0ad5758908c5b1d76d121', FALSE, $s213$StringTableCards/CARD_LEECH$s213$),
  ('ee360168cd7b0d3e', 'game', $s213$ECHO$s213$, '6781cfc8284296eb70ba05270579b9deac096a80', FALSE, $s213$StringTableCards/CARD_ECHO$s213$),
  ('ee3d06226c9c2b97', 'client', $s213$<color=#888>Select 2+ players with ranked history to compare Elo.</color>$s213$, 'c2dad79a078f8c3687a8d89f0aefb84a1d2cf78c', TRUE, NULL),
  ('ee8257609579ab51', 'client', $s213$Refreshing too fast - give it a sec$s213$, 'c3d2925a7bdb78bf6843c08b909c46a2f966f744', FALSE, NULL),
  ('ee94aba8b4c71411', 'client', $s213$Good luck, have fun!$s213$, 'a7a3d544f2e165ee5b1d0c26d4ff3e158cca81a1', FALSE, NULL),
  ('eed713d9e5b7fa6a', 'client', $s213$Block a Player...$s213$, '8c8871a730c2975c44c4ee6bc331c76a40aebf00', FALSE, NULL),
  ('eef6ec9b90a29c49', 'client', $s213$Admins can't be kicked.$s213$, '978584de4b6f7d4fc7b8b46acca9ebd63346d699', FALSE, NULL),
  ('ef2ee75085947329', 'client', $s213$<b>Recent Ranked FFAs</b>  <color=#888>({0} total)</color>$s213$, '18c28fcab9c64bd35ce03e8e016602b6795ecc8f', TRUE, NULL),
  ('ef416e27d17769c6', 'client', $s213$FIRST TO {0}   -   {1} OPENING DRAWS   -   {2}-CARD HAND$s213$, '3473dbe7c23ff2a47b4c0db0213ea2c31730da1d', FALSE, NULL),
  ('ef5de162affbd1c3', 'client', $s213${0}-card draw$s213$, '33279a7d64b9594ed34377d1a28a94f4855fb062', FALSE, NULL),
  ('ef8767b213eb3ea5', 'client', $s213$Bug Reports...$s213$, '59269e612dac82734fb0bff3e7d60948afe84748', FALSE, NULL),
  ('ef8b357138a3ef69', 'client', $s213$Underline$s213$, '39773aa3efa19090c918baedac1fe737dea25b92', FALSE, NULL),
  ('ef93fe294836d086', 'game', $s213$日本語$s213$, 'c12140a0ffb4e56481b4fe0a7a25040c2eafa9ca', FALSE, $s213$StringTableDefault/LANG_JAPANESE — 2023-10-23: Replaced the unlocalized name with its translated version$s213$),
  ('ef9e76cea86e1996', 'client', $s213$Body/Team Color$s213$, '8b6936a29f32dc8b820b8a11be9a1ea4beebb429', FALSE, NULL),
  ('efa284500294a4ba', 'client', $s213$Banned Players$s213$, '82dc4c9ba2d0d3898232429a34fce3451ac22165', TRUE, NULL),
  ('efc2c3f495527644', 'client', $s213$Connecting to the game...$s213$, 'be82ac865c3763a408fbf6144162c42a37ecf19d', FALSE, NULL),
  ('efc2f9902bbd8f88', 'client', $s213$Lv {0}$s213$, '921f739afc4507740d70462d75a775f0b1de78a3', FALSE, NULL),
  ('efe79bae30a5be47', 'client', $s213$Deep cool dusk blues with dimmed exposure.$s213$, 'b30ee14d6f5a4695053e04642b94ecb60916730f', FALSE, NULL),
  ('f011a454829fac7c', 'client', $s213$Prizes are announced when signups open.$s213$, '122c17aad3eda08a61675ed1002bce10fde0233a', FALSE, NULL),
  ('f027d1391cc75d18', 'client', $s213$Crown$s213$, '410494f2cf468cb98b4655657880ea42f72183c0', FALSE, NULL),
  ('f05cbe9e346dc452', 'client', $s213$Deep red smoke following your every move.$s213$, '343c93580548bc432445ab81ff3add7560c3d74c', FALSE, NULL),
  ('f05fce1b70186512', 'game', $s213$BIG BULLET$s213$, '0a24e48b811ae17a79b0b12e291acb7fc7642df0', FALSE, $s213$StringTableCards/CARD_BIG_BULLET$s213$),
  ('f0607d4b143a64b0', 'client', $s213$Thicker menu text: <color=#88FF88>ON</color>$s213$, '34a21e05c30ded2a040b26c49002ff123c162768', FALSE, NULL),
  ('f095c13abf6b5329', 'client', $s213$<b>Start Game ({0}/{1})</b>$s213$, '60e8be4e971f1fedfeacc23100c7c7185b92ab25', FALSE, NULL),
  ('f0c37983395b1b27', 'client', $s213$<color=#FFB347>Series paused — same 4 can re-queue to resume</color>  <color=#FF6688>{0}:{1}</color>  <color=#888>(score {2}-{3})</color>$s213$, '1fe1aeab7143e93fea9d5b783b4e71539de01982', FALSE, NULL),
  ('f0ca80932eaf824e', 'client', $s213$Strike through your name. Stackable with other name styles.$s213$, '78d736bb8b31ffc0d1147e4a8bb2bbb2bf209874', FALSE, NULL),
  ('f0dc3f4c961b805e', 'client', $s213$Earned by {0} players  <color=#888>(in the order they got it - click again to close)</color>$s213$, '09d9fbb99911bd6d0227907a47221c12a2db9ca4', FALSE, NULL),
  ('f0f169d5182d3441', 'client', $s213$Star Earmuffs$s213$, '1c0cb5239f106c2576fc15b5249d073c7cf406e0', FALSE, NULL),
  ('f101e7dfe9aebb16', 'client', $s213$<size=80%><color=#7CFF7C>(you)</color></size>$s213$, 'e831ea71c515905031066ca0811cc3514f4b19eb', FALSE, NULL),
  ('f10f7f8c8bc75fdb', 'client', $s213$Elo over time$s213$, '00539e5e55904cbf26d075a6f2f7a22533056c61', FALSE, NULL),
  ('f1144eb024aa03eb', 'client', $s213$All picks (oldest first) - red = replaced:$s213$, '940bbeb152752a33c9934bdce09b0298902a4d0e', FALSE, NULL),
  ('f12a5f43bddffefa', 'client', $s213$3/3 ready! Joining 1v2 — you are on the DUO...$s213$, '1cd566ededf6a75719a91e6e081a7e8c4114edd6', FALSE, NULL),
  ('f175d5d9643750aa', 'client', $s213${0} games    {1}W - {2}L    {3}$s213$, 'cceed712efad9af4f4ef2b04ce0b8d5a66f086ce', FALSE, NULL),
  ('f191cfa21f829bad', 'client', $s213$Map shadows: <color=#88FF88>ON</color>$s213$, '56b5171f1b34b209c2562ac1138f47cba321d54a', FALSE, NULL),
  ('f1a7d88d4ab987b7', 'client', $s213$Update failed — couldn't start the updater. Update manually from GitHub.$s213$, 'ba7ee6a74491308d3b2c4ef062a67a3f46c8805c', FALSE, NULL),
  ('f1ad6bb2e30613b4', 'client', $s213$Active$s213$, 'a733b809d2f1233496ab516eed0f3ef75cf3791a', FALSE, NULL),
  ('f212ef10a93e2dcd', 'client', $s213$<color=#777>{0} activated / {1} successful</color>$s213$, '68fe6a69bfba20998445f3f4a9bd8baecc77a336', FALSE, NULL),
  ('f21486a74e18c3bb', 'client', $s213$Upload a Cosmetic...$s213$, '7b0543786aca645a0c22d2b047ede094e3ca42c4', FALSE, NULL),
  ('f21a648d0ad01def', 'game', $s213$Deutsch$s213$, 'a6a7709266d3a74cd8c4657eb32a56d5727b91eb', FALSE, $s213$StringTableDefault/LANG_GERMAN — 2023-10-23: Replaced the unlocalized name with its translated version$s213$),
  ('f235df555d002514', 'client', $s213$Thicker menu text. Uses the game's own font at a heavier weight - not a different typeface.$s213$, 'e2c34a89258190d36f1eb34cb0743e6fea492528', FALSE, NULL),
  ('f2ee58084f8d02ee', 'client', $s213$FFA VICTORY!$s213$, '72a3946768a62051739daf64745f3fda6a9e9294', FALSE, NULL),
  ('f3111e697b8a3499', 'client', $s213$<color=#FF6666>(OUT OF STOCK - artist hasn't opened sales yet)</color>$s213$, '503a6feddafea172e50dcab91e9b6ca9fd5c5415', FALSE, NULL),
  ('f3522d9082eb1df1', 'game', $s213$Bullets keep the default trajectory$s213$, '9349c2e2cdd88afa6330264145134e6b1ce0e088', FALSE, $s213$StringTableCards/CARD_FAST_FORWARD_DESC$s213$),
  ('f3812bc2b6293012', 'client', $s213$Anonymizes your Steam ID, display name, and Discord link. Matches stay so other players' Elo and histories aren't affected. You will no longer appear on leaderboards.
<b><color=#FF8888>IRREVERSIBLE:</color></b> this Steam ID can never re-register. Future matches from this account will show as [Deleted User] and won't count toward stats.$s213$, 'c294dd8cfffa97ad51155538b632d042aace7e03', TRUE, NULL),
  ('f3d059d8adc3972f', 'client', $s213$Start (need {0}+)$s213$, 'af0151e8d21f97ebebc04a4921272e598ec5146e', FALSE, NULL),
  ('f3e1ca269a596f07', 'client', $s213$Compare$s213$, '8d105cf44d3926289e65c1c83d8e37cb23fd049e', FALSE, NULL),
  ('f444dd90b18a22de', 'client', $s213$Region distribution$s213$, 'd3c9dbb10b2776caea1c1e5bca8f578467f17836', FALSE, NULL),
  ('f45db7482d67a389', 'client', $s213$Calm forest-green tint with low saturation.$s213$, '58e286b87091b07259c44d7904e679e9be73eddf', FALSE, NULL),
  ('f469e16744d7e631', 'client', $s213$<color=#FF9BE0>coming soon!</color>$s213$, '025b122607398d54c7dac36a0d9b0fdb10f1ab8e', FALSE, NULL),
  ('f472c39b32f507f1', 'client', $s213$<color=#888><i>No messages yet. Messages sent here or in #scr-discussion on Discord show up here.</i></color>$s213$, 'cabff10c1e2283f066cd7894bde61a83efc05eb4', FALSE, NULL),
  ('f472e0b120dc8c99', 'game', $s213$Français$s213$, '2ca514ebd7c3a61fe53823a0785c326287c4ede8', FALSE, $s213$StringTableDefault/LANG_FRENCH — 2023-10-23: Replaced the unlocalized name with its translated version$s213$),
  ('f492ecc3e3307ab6', 'client', $s213$Best Win Streak$s213$, '0e13a694c06a1734230915e4b3206b568908870c', FALSE, NULL),
  ('f4999184f00fd765', 'client', $s213$Default (random)$s213$, 'ab5e0dd7f1c6d715060995c24097c27dabc964a1', FALSE, NULL),
  ('f4c3fa898d37040e', 'client', $s213$Series$s213$, '40c20d94e78fa142819df8cc9440d30e65329975', FALSE, NULL),
  ('f4fe99e5fc999ad4', 'client', $s213$That {0} lobby is private — enter its password.$s213$, 'd8882b460efd6a4c262200be3f970ca10fa92fdb', FALSE, NULL),
  ('f501fa2dd1f5cbc4', 'client', $s213$How dates are written across the mod's menus (history rows, leaderboards, tournaments).$s213$, '5eb10c630fc6887d4a44e6d2b996c378edff9152', FALSE, NULL),
  ('f51760d7b4a0ccaf', 'client', $s213$Selected {0}/{1}  -  click a player to add/remove$s213$, '757692270a6215efdebe1d9ef46bef9c6c10f012', FALSE, NULL),
  ('f522e76707a4e0d9', 'client', $s213$Size$s213$, 'b7152342a267362add3c0d7f69f720f7a9c76c9e', FALSE, NULL),
  ('f559411bd6b00928', 'game', $s213$Bullets deal 80% more DMG per bounce$s213$, 'b5b743ca14140d1f46ee0d54f4ad9cd52eac6b4f', FALSE, $s213$StringTableCards/CARD_TRICKSTER_DESC — Damage$s213$),
  ('f5802f04b6f64ceb', 'client', $s213$Press Esc to leave$s213$, '425872a6007bf09700428cd4751ff944086fbdbd', FALSE, NULL),
  ('f58abfbaabcef3be', 'game', $s213$EMP$s213$, '316f7985b2196ffa3985a411b212a6da8a548709', FALSE, $s213$StringTableCards/CARD_EMP — Electromagnetic pulse$s213$),
  ('f59a6c6967acba5c', 'client', $s213$FFA Avg Placement$s213$, '8ccdb6e6b11f321d1e82ca9cd4db9f53fdf278d4', FALSE, NULL),
  ('f5e4b15f8ec88880', 'client', $s213$<color=#FFAA55>Lobby browser unavailable right now — the server may be updating.</color>$s213$, 'af57de8670a28aeeae77335bea05fc79ebb02c01', FALSE, NULL),
  ('f5fa897d8e716419', 'client', $s213$A cool cyan mouse cursor.$s213$, '72115355dca2abe0a4c5925cae462041c92fb3f3', FALSE, NULL),
  ('f6461162d7642d8a', 'client', $s213$Revoke which alert?$s213$, 'afe7fa9dd2a7353a1536ab0cd1948d49a119f36a', TRUE, NULL),
  ('f66df2fe117a9ae1', 'client', $s213$Your pick missed the cutoff - no card this round.$s213$, '81aad0f1de7edc9038fb058738030cd6cadfd48a', FALSE, NULL),
  ('f67efe800c180000', 'client', $s213$How long for {0}?$s213$, '28160d3239f84bf7543ffb33ba400f72c19fef0e', FALSE, NULL),
  ('f68275e9faed6821', 'client', $s213$A clean white mouse cursor.$s213$, 'e5f0c878ca68b6046f356f8b4e10dff4be9ab299', FALSE, NULL),
  ('f69708bf886ba7c7', 'client', $s213$Colorize your name in cyan.$s213$, 'e355071ea9b079a72d85687e2ac34ec406ee7927', FALSE, NULL),
  ('f6a637efb68bcea0', 'client', $s213$Casual: {0}W/{1}L$s213$, '33aed4926d6006ad15fdb8c60b6fa786a37b41f9', FALSE, NULL),
  ('f6f333d6d350d69b', 'client', $s213$Self-Death %$s213$, '3b6bd1fc36ae8d7a9152257169589b6859bfdd29', FALSE, NULL),
  ('f6f34d9ac2417621', 'client', $s213$Nice shot!$s213$, 'aac668d23d8155efd9f13bd5e05a3464762a97d5', FALSE, NULL),
  ('f72488c19efdac04', 'client', $s213$From the art of the "Healing Field" card$s213$, '8be4bf379229e1042e85793249e4608bdaa255c8', FALSE, NULL),
  ('f7269abe66c04b31', 'game', $s213$Resolution$s213$, '516aae52959dcf5398a9985414a78b8c24a4f0e5', FALSE, $s213$StringTableDefault/OPTION_RESOLUTION$s213$),
  ('f732fa3292ba6a54', 'client', $s213$Ranked Damage per Second$s213$, '9350fb281abfe3f6db7df17312a701fccc03b427', TRUE, NULL),
  ('f734b208caa4f204', 'client', $s213$Tracker$s213$, 'c15771fc77a45dae33911c04bb171e6f49fa33cb', FALSE, NULL),
  ('f796bdc42be79e7b', 'client', $s213$No games this session$s213$, '9e6c07e8e40fc239b215195f80470cb40f0f80bb', FALSE, NULL),
  ('f7a262877a996f15', 'client', $s213$private$s213$, 'e80721793c24ae14edfca9b26ad406a9815cd3ff', FALSE, NULL),
  ('f7c0cd90c321493a', 'client', $s213$Score progression$s213$, '3295f8d8261083d7f28652ae6b6758ca2369e347', FALSE, NULL),
  ('f7c82f02b929a7d6', 'client', $s213$Bouncy main$s213$, 'a9c34a32e6e79b3c17f81be6765ab239ba111db6', FALSE, NULL),
  ('f80787f5bedc87aa', 'client', $s213$That game is no longer live.$s213$, 'f336e5fc9ed94a2e1ad76933b8b20b01fad18e70', FALSE, NULL),
  ('f8218f1964c0c094', 'client', $s213$How stats are tracked$s213$, 'be82f1dfcef7b0d0b8db7689f8c76a538da23f82', FALSE, NULL),
  ('f8465990452e8309', 'client', $s213$Win/Loss Record$s213$, '297f06ad75081de5ae834632a5e00a251ff00202', FALSE, NULL),
  ('f8722c358b268c6e', 'client', $s213$Eye-watering hot-pink body color.$s213$, '16b52078a6f08d64300bd48fcb78dec76756adbb', FALSE, NULL),
  ('f8ced7340afd321a', 'game', $s213$Damage done to you is dealt over 4 seconds$s213$, 'e9e58f05b790744b31ac42de18725afe12a06459', FALSE, $s213$StringTableCards/CARD_DECAY_DESC$s213$),
  ('f8f0279d2c6f32dd', 'game', $s213$Round Blue$s213$, 'aa66f9301cd5132398ccebb906809c284e321c08', FALSE, $s213$StringTableDefault/PROMPT_ROUND_BLUE$s213$),
  ('f9485d399e197e12', 'client', $s213$<b>Your Custom 1v2 Lobby</b>$s213$, '7a582054703f8b7cc36a4b682f78cc6cd773c259', FALSE, NULL),
  ('f97b3c500645df08', 'client', $s213$Couldn't rejoin your private FFA lobby — join it again from the browser.$s213$, 'e99f756b015752cfcf948712eaa513501b978d24', FALSE, NULL),
  ('f9af58f6147262d9', 'game', $s213$Shooting costs 10HP
Removes shooting cooldown$s213$, '7eb1d0ef257bb78989f40d9f8e434bd56fddf5e7', FALSE, $s213$StringTableCards/CARD_DEMONIC_PACT_DESC — Health Points$s213$),
  ('fa1183ae7a5066c9', 'client', $s213$Usage: /report [name] [reason]$s213$, '22696fce4a6f219c2d5ddd1ee161c0b74cf82250', FALSE, NULL),
  ('fa2645b70f9f5d77', 'client', $s213$<color=#FFD94D>Ranked:</color> -$s213$, 'a777582de015d6aa189d5e987dbb22330ea290f1', TRUE, NULL),
  ('fa6435193f8ec7ab', 'client', $s213$<color=#FFD94D>PLACEMENT PENDING REVIEW</color> <color=#888>(last approved placement stays active)</color>$s213$, '5201388e750ee115b4d891876b605efd08ef984e', FALSE, NULL),
  ('faad0c987e1f8490', 'client', $s213$For those who earned the right. Still costs a fortune.$s213$, 'c6b8dfc0f49980b4284e35414a755c6e2d0fa5f9', FALSE, NULL),
  ('fae2abbd1d51f67d', 'client', $s213$<color=#888>Mod:</color>$s213$, 'c40c6b2fcce0e40b069812932bfe25f200cac3ab', FALSE, NULL),
  ('fafe22194f8ed4aa', 'client', $s213$Update available — update through your mod manager$s213$, '89716467dcde7378aa43d06eef69031d0d9df6e8', FALSE, NULL),
  ('fb0725b41f178ef8', 'client', $s213$Language: <color=#88CCFF>{0}</color>$s213$, 'ce2864f02b751fa6f9f141839fa847756de688c5', FALSE, NULL),
  ('fb110029669916f2', 'client', $s213$<color=#FF9988>Hit:</color> -$s213$, '995bd7e24afe7fc688d2026b7dd199ce6cbec2a3', FALSE, NULL),
  ('fb141f420287e2e0', 'client', $s213$Add extra character spacing.$s213$, '7f73305879a039b508248f80ce6511bbd64ef4b4', FALSE, NULL),
  ('fb1478c1f65baa33', 'client', $s213$Grey Cat$s213$, '82974e1f3b7ac1ae1fd1714ea5e215b421da1805', FALSE, NULL),
  ('fb1a4b3a5f4e1d5d', 'client', $s213$<color=#66DD66>APPROVED</color> <color=#888>(rev {0} awaits a mod update)</color>$s213$, 'dc2a54c6ab19d126c840dfe2b19216c508821c64', FALSE, NULL),
  ('fb81d413056c7042', 'client', $s213$I'm ready$s213$, 'c3ba5714684266f4b723efee3630b3f044e02fac', FALSE, NULL),
  ('fbb9ace819dbb6d6', 'client', $s213$2v2 - How It Works$s213$, '733e7baa95c66d1bfbac67551bcb7ada2719b69e', FALSE, NULL),
  ('fbbce02111ccebf0', 'client', $s213$Two glowing green feelers. Take me to your leader.$s213$, 'fc31465be9e079dfb54cb2d55d591edc83fd4ceb', FALSE, NULL),
  ('fc23457a57683e0e', 'client', $s213$A burning crown of fire. ANIMATED.$s213$, 'fd205b824b53ed05147b7286bfcdbef4e9d8c77a', FALSE, NULL),
  ('fc4c40059bf20748', 'client', $s213$<color=#777>{0} dmg taken · {1} successful blocks</color>$s213$, '3784f0862c740244742696aceeb08ec3e94cae1e', FALSE, NULL),
  ('fc89dabf25a1093d', 'client', $s213$Report a bug$s213$, 'fbb446a61a4468f5ad96947bdc0040fe036d44ee', FALSE, NULL),
  ('fcd7c1e7500aa9d6', 'game', $s213$To move items$s213$, 'ac9bca845b7b754ba930e7a133eeb8fc5946d006', FALSE, $s213$StringTableDefault/PROMPT_MOVE_ITEMS$s213$),
  ('fcdaa994cb09a325', 'client', $s213$Soft Slate$s213$, 'ce8d0da33206ab07f9dad187d28ae162ccc22b29', FALSE, NULL),
  ('fd4d752a09b135c7', 'client', $s213$<color=#888>Steam ID:</color>$s213$, 'c33489a0e5e55f1129255554ed18ba2ac2a49972', FALSE, NULL),
  ('fd68f9ec138655b1', 'client', $s213$Action Log$s213$, 'be93470195f3332d7adfd1047a5c6c18dc1f1b8c', FALSE, NULL),
  ('fd870b0522ab9f12', 'client', $s213$<b>Recent 2v2 Series</b>  <color=#888>— none yet</color>$s213$, '3f7a0932c8fe2823698affa487d5b60a9aceba20', FALSE, NULL),
  ('fd8d7e51279627ed', 'client', $s213$Game {0} score progression$s213$, '4200a0fa64073d825b8861ad95ee0536180ae1f7', FALSE, NULL),
  ('fdb683f06819a160', 'client', $s213$<color=#FFB347>2v2 History</color>$s213$, 'c0db3cd062a38f3cacf680a2109f3dd736a64c13', FALSE, NULL),
  ('fdbd0ecf1244c020', 'client', $s213$5-0 Sweeps$s213$, '1890b7a9d93676cbf2707078cbfba41e5787666e', FALSE, NULL),
  ('fde511fb7c73ed95', 'client', $s213$Echo$s213$, 'e738c7d89afb7a9acb548496f7ce7ca8d6b2a2f0', FALSE, NULL),
  ('fdea4fee02fc1df2', 'client', $s213$Searching... {0}s  +/-{1}$s213$, '122661d9a77d8948a4efb1c1cf20a6a3cae1bfa9', FALSE, NULL),
  ('fe35b612219f0afc', 'client', $s213$Flagged Matches$s213$, 'a2e6462d89b355f988344af13d5467d6bd4d10b3', FALSE, NULL),
  ('fe6d0b0c1c99dfc1', 'client', $s213$Solo {0}W/{1}L$s213$, 'ad4c0e8211de1e439cf86a7e625f06c86317b74c', FALSE, NULL),
  ('fe7a4ade88f61c42', 'client', $s213$Flag marked false positive.$s213$, '66640520cbee31c09da657ee2488012ccc40f1c5', FALSE, NULL),
  ('fe7ef6236573f7e7', 'client', $s213$<color=#888>+{0} more</color>$s213$, '65658659a09127dac71302da8c2c0e403214484f', FALSE, NULL),
  ('fe85ade52f92f64e', 'client', $s213$Emerald Name$s213$, '2c9dde1029ae34d4232e975c93a7a04067eb085b', FALSE, NULL),
  ('fe95157ea5d812b9', 'client', $s213$Date format$s213$, '94ee8869082873abf458deca86a2b8e3a3091aa0', FALSE, NULL),
  ('feb59a76f97cc1b2', 'client', $s213$Win taking only the left-most card on every pick, without ever looking at the others$s213$, '82e21ae0bb23c7bf1a5dadd5a70daa9e562ab824', FALSE, NULL),
  ('feb7846e483876c6', 'client', $s213$Cards$s213$, '0f830bc25e52f96121b00a67378be1abeaa3f274', FALSE, NULL),
  ('fee8d8d629009cb5', 'game', $s213$PRISTINE PERSEVERENCE$s213$, '35492c772884120ab86449b6a74bd87231823230', FALSE, $s213$StringTableCards/CARD_PRISITNE_PERSEVERENCE — 2023-10-20: ENG: Fixed a typo in "PRISTINE" ("PRISITNE")$s213$),
  ('fefd29b7cdc2891d', 'client', $s213$Keys / Game$s213$, '3e766191a84859276c20faa0e8ef0e675f15ce42', FALSE, NULL),
  ('ff02bb99d53e2f5d', 'client', $s213$<b>Recent Ranked FFAs</b>$s213$, '8c633183bfd632ab1fe76c7dcc732e7d831f646a', TRUE, NULL),
  ('fff050a62953a165', 'client', $s213$AvgPl$s213$, 'b2df7e1ebbcf4c9557f59de9e8d9e16ff8b7817a', FALSE, NULL),
  ('fff10c9a1a7ab76e', 'client', $s213$Games$s213$, '398ed329814977519b9f899253338884a2ba941f', FALSE, NULL)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET source_hash = EXCLUDED.source_hash,
       msgctxt     = EXCLUDED.msgctxt,
       context     = COALESCE(NULLIF(i18n_keys.context, ''), EXCLUDED.context),
       retired_at  = NULL,
       updated_at  = NOW()
 WHERE i18n_keys.retired_at IS NOT NULL
    OR i18n_keys.source_hash <> EXCLUDED.source_hash
    OR (EXCLUDED.context IS NOT NULL AND COALESCE(i18n_keys.context, '') = '');
COMMIT;
'''

SEEDS['214_translator_titles.sql'] = r'''-- rf8 d2 seed (tag hi) for 214_translator_titles.sql: i18n_keys fixtures.
-- The file's INSERT joins i18n_proposals onto LIVE i18n_keys rows with the SAME
-- source_hash, and its DO-block coverage check RAISEs when a seed pair did not land.
-- Production gets these key rows from tools/i18n_sync_keys.py; here they are
-- derived from the file itself: every (key_id, source_hash) in its section 6 VALUES (lines 114-168) and the msgctxt list of the post-check (lines 197-210).
-- namespace: 'game' when key_id = sha1('game\0' + Table/KEY)[:16] over
-- tools/game_strings.json (or the file lists it as a game key), else 'client'.
-- msgctxt: the English whose sha1 equals the file's source_hash (found in
-- tools/i18n_source.json at HEAD or any earlier revision, tools/game_strings.json,
-- or the quoted text of backend/sql),
-- otherwise a labelled placeholder. Game keys carry a non-empty context.
-- 9 keys: 9 client with English, 0 game with English, 0 placeholder msgctxt.
-- Re-runnable: the upsert only touches a row that is retired, carries another hash,
-- or lacks context the file reads.
BEGIN;
INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
  ('09223fd5f61ba258', 'client', $s214$Dragoman$s214$, '689010aa4282379f0479c0e024108c2a963ef5f7', FALSE, NULL),
  ('15d202c6a4014604', 'client', $s214$Get 1000 translations approved (yours, or ones you reviewed)$s214$, '3da5563a1b208c34fb55b011341811074297bc21', FALSE, NULL),
  ('39617d899fccdbad', 'client', $s214$Get 10 translations approved (yours, or ones you reviewed)$s214$, '9db8b316fbbff3ed5262eb85f448b40ee0ec13ff', FALSE, NULL),
  ('61e297eba181127f', 'client', $s214$Got 10 translations approved$s214$, '7903e247cb949cf5d7b432707df4d104ed3c81aa', FALSE, NULL),
  ('716553e5d4ffcdf8', 'client', $s214$Rosetta$s214$, 'db73904ee194bd4fd1333249d0a3c3d19476c274', FALSE, NULL),
  ('ce25ae7de19d2198', 'client', $s214$Got 1000 translations approved$s214$, 'a66a92451d0146f81caa567f1627e7e235745728', FALSE, NULL),
  ('d704b66a9fc187c3', 'client', $s214$Babel$s214$, 'f3bf8dee016caf43ae3970fbea5f976d54898ed9', FALSE, NULL),
  ('dcc82a2b178d2cf1', 'client', $s214$Get 100 translations approved (yours, or ones you reviewed)$s214$, 'a4d4f3f811aa4c65da7efed58dbc34c2a927a36e', FALSE, NULL),
  ('e7f9f0fb5a2c0786', 'client', $s214$Got 100 translations approved$s214$, 'f6fe7b03c53f86154d56f1afe95a158361e7c559', FALSE, NULL)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET source_hash = EXCLUDED.source_hash,
       msgctxt     = EXCLUDED.msgctxt,
       context     = COALESCE(NULLIF(i18n_keys.context, ''), EXCLUDED.context),
       retired_at  = NULL,
       updated_at  = NOW()
 WHERE i18n_keys.retired_at IS NOT NULL
    OR i18n_keys.source_hash <> EXCLUDED.source_hash
    OR (EXCLUDED.context IS NOT NULL AND COALESCE(i18n_keys.context, '') = '');
COMMIT;
'''

SEEDS['217_fix_animated_submission_metadata.sql'] = r'''-- rf8 d2 seed (helper hc) for 217_fix_animated_submission_metadata.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 217 existence post-check: submission rows for magical_hat and dark_aura, both in
-- the stale static shape (frame_count 1 default, anim_fps NULL) the UPDATE corrects.
-- magical_hat: shipped by 197 (rev 1 published 1), id 16 as in 197.

-- shop row face_detail_magical_hat - published by 197
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880259, 'face_detail_magical_hat', 'face', 'face_detail_magical_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_magical_hat');
-- already live before this file: publish it (no submission row exists yet, so
-- the 148 trigger only stamps released_at)
UPDATE shop_items SET catalog_ready = TRUE WHERE sku = 'face_detail_magical_hat' AND catalog_ready IS NOT TRUE;

-- approved submission face_detail_magical_hat: rev 1, scale 1.3, offset (0,0), published 1
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 16, '76561190000000149', 'face_detail_magical_hat', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_magical_hat', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 1, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_magical_hat');
-- dark_aura: live face (rev 2 published 2, per the file header)

-- shop row face_detail_dark_aura
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881104, 'face_detail_dark_aura', 'face', 'face_detail_dark_aura', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_dark_aura');
-- already live before this file: publish it (no submission row exists yet, so
-- the 148 trigger only stamps released_at)
UPDATE shop_items SET catalog_ready = TRUE WHERE sku = 'face_detail_dark_aura' AND catalog_ready IS NOT TRUE;

-- approved submission face_detail_dark_aura: rev 2, scale 1.3, offset (0,0), published 2
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991104, '76561190000000149', 'face_detail_dark_aura', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_dark_aura', 1.3, 0, 0, 2, 1.3, 0, 0, 2, 2, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_dark_aura');

COMMIT;
'''

SEEDS['223_seed_vocab_and_new_shop_strings.sql'] = r'''-- rf8 d2 seed (tag hi) for 223_seed_vocab_and_new_shop_strings.sql: i18n_keys fixtures.
-- The file's INSERT joins i18n_proposals onto LIVE i18n_keys rows with the SAME
-- source_hash, and its DO-block coverage check RAISEs when a seed pair did not land.
-- Production gets these key rows from tools/i18n_sync_keys.py; here they are
-- derived from the file itself: every (key_id, source_hash) in its _seed223 pairs.
-- namespace: 'game' when key_id = sha1('game\0' + Table/KEY)[:16] over
-- tools/game_strings.json (or the file lists it as a game key), else 'client'.
-- msgctxt: the English whose sha1 equals the file's source_hash (found in
-- tools/i18n_source.json at HEAD or any earlier revision, tools/game_strings.json,
-- or the quoted text of backend/sql),
-- otherwise a labelled placeholder. Game keys carry a non-empty context.
-- 19 keys: 19 client with English, 0 game with English, 0 placeholder msgctxt.
-- Re-runnable: the upsert only touches a row that is retired, carries another hash,
-- or lacks context the file reads.
BEGIN;
INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
  ('167c8c2ffec8b6e8', 'client', $s223$title$s223$, '3c6de1b7dd91465d437ef415f94f36afc1fbc8a8', FALSE, NULL),
  ('1f906dd204f11211', 'client', $s223$color$s223$, '6dd0fe8001145bec4a12d0e22da711c4970d000b', FALSE, NULL),
  ('2e97ebb1aa9833a1', 'client', $s223$Held by the top 3 on the FFA leaderboard$s223$, 'd1a8bbfa7d6b67955b884b1abf9db358b26123f2', FALSE, NULL),
  ('33189667ce7b6ff8', 'client', $s223$rare$s223$, 'd5e62fc1fc3b3a64ea4fc20d640432c8bd216663', FALSE, NULL),
  ('3581c4eb186d0477', 'client', $s223$player color$s223$, '871899515bc960165cb986ba61c6b0e2fdfc4483', FALSE, NULL),
  ('65b696f2c39bd5da', 'client', $s223$face$s223$, '49dc1cb094dffe3a42dd5f448ac612b0786a67e4', FALSE, NULL),
  ('73384d8d31140e09', 'client', $s223$epic$s223$, '31fe23de06e7a9e05684f021f52cfc0e2832c19d', FALSE, NULL),
  ('73b4e1fa08ae8958', 'client', $s223$FFA Podium$s223$, 'a75329613f268c94057ba2625c7b2e2c8af204ea', FALSE, NULL),
  ('878c2724efc99f6c', 'client', $s223$utility$s223$, '8884fd30d64e5cf97054c14e8a217a1fb0cd7e16', FALSE, NULL),
  ('9f6f3ff506740ea8', 'client', $s223$Held by the top 3 on the 2v2 leaderboard$s223$, 'd8c7c8cf4f9fea827b5d13a5e50e94756615d394', FALSE, NULL),
  ('a1a070bd7dc66637', 'client', $s223$legendary$s223$, '4c87891558ebeb3be19116efc8e9037e43f0ad1e', FALSE, NULL),
  ('a8aa6f63a0e7347f', 'client', $s223$trail$s223$, '81a85c613b3fd4aa49573b381f6d6fc5c683c9aa', FALSE, NULL),
  ('b21c41222533d93c', 'client', $s223$cursor color$s223$, '31ca1a3367bac9b6b3ab51e57ae6a31edca9ad7c', FALSE, NULL),
  ('c92a9fa248bfbe4e', 'client', $s223$nametag$s223$, '4a16571080b2d5ec503066ad09664991bc0338bb', FALSE, NULL),
  ('c9f4654b7eb77513', 'client', $s223$2v2 Podium$s223$, '74bf5bd38e9052a870e6f6b0ae66bf64b39b86b7', FALSE, NULL),
  ('d55388f40533f056', 'client', $s223$player effect$s223$, '2b5305a40a645b84a38ed158244a3dde340433b5', FALSE, NULL),
  ('d9ba1c95478f3c23', 'client', $s223$The exact green a poison tick flashes on its victim.$s223$, 'e6299bcf304aaf6ab99368c3b9166ad2b1ec5549', FALSE, NULL),
  ('e1057c640d9c18b6', 'client', $s223$common$s223$, '94c8c21d08740f5da9eaa38d1f175c592692f0d1', FALSE, NULL),
  ('fe8425e82c256c70', 'client', $s223$uncommon$s223$, '8d13318ea523c584ca30b15fad027045157b076b', FALSE, NULL)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET source_hash = EXCLUDED.source_hash,
       msgctxt     = EXCLUDED.msgctxt,
       context     = COALESCE(NULLIF(i18n_keys.context, ''), EXCLUDED.context),
       retired_at  = NULL,
       updated_at  = NOW()
 WHERE i18n_keys.retired_at IS NOT NULL
    OR i18n_keys.source_hash <> EXCLUDED.source_hash
    OR (EXCLUDED.context IS NOT NULL AND COALESCE(i18n_keys.context, '') = '');
COMMIT;
'''

SEEDS['228_release_poison_set.sql'] = r'''-- rf8 d2 seed (helper hc) for 228_release_poison_set.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 228 guard: exactly 3 approved Poison-set submissions, each rev 1

-- shop row face_eyes_poison_s_eyes
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880267, 'face_eyes_poison_s_eyes', 'face', 'face_eyes_poison_s_eyes', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_eyes_poison_s_eyes');

-- approved submission face_eyes_poison_s_eyes: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990267, '76561190000000149', 'face_eyes_poison_s_eyes', 'eyes', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_eyes_poison_s_eyes', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_eyes_poison_s_eyes');

-- shop row face_mouth_poison_s_mouth
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880268, 'face_mouth_poison_s_mouth', 'face', 'face_mouth_poison_s_mouth', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_mouth_poison_s_mouth');

-- approved submission face_mouth_poison_s_mouth: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990268, '76561190000000149', 'face_mouth_poison_s_mouth', 'mouth', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_mouth_poison_s_mouth', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_mouth_poison_s_mouth');

-- shop row face_detail_poison_s_weeping
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880269, 'face_detail_poison_s_weeping', 'face', 'face_detail_poison_s_weeping', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_poison_s_weeping');

-- approved submission face_detail_poison_s_weeping: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990269, '76561190000000149', 'face_detail_poison_s_weeping', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_poison_s_weeping', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_poison_s_weeping');

COMMIT;
'''

SEEDS['231_grant_notnic_gold.sql'] = r'''-- seed (hm) for backend/sql/231_grant_notnic_gold.sql: fixture rows only, idempotent.
-- 231 lines 44-47 and the post-check read the live (deleted_at NULL) players row with
-- NotNic's steam id; gold_earned 6865 is the counter the header (line 27) quotes.
INSERT INTO players (steam_id, display_name, gold_earned)
SELECT '76561199311926326', 'NotNic', 6865
WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = '76561199311926326');
'''

SEEDS['239_seed_machine_translations_v1391.sql'] = r'''-- rf8 d2 seed (tag hi) for 239_seed_machine_translations_v1391.sql: i18n_keys fixtures.
-- The file's INSERT joins i18n_proposals onto LIVE i18n_keys rows with the SAME
-- source_hash, and its DO-block coverage check RAISEs when a seed pair did not land.
-- Production gets these key rows from tools/i18n_sync_keys.py; here they are
-- derived from the file itself: every (key_id, source_hash) in its _seed239 pairs.
-- namespace: 'game' when key_id = sha1('game\0' + Table/KEY)[:16] over
-- tools/game_strings.json (or the file lists it as a game key), else 'client'.
-- msgctxt: the English whose sha1 equals the file's source_hash (found in
-- tools/i18n_source.json at HEAD or any earlier revision, tools/game_strings.json,
-- or the quoted text of backend/sql),
-- otherwise a labelled placeholder. Game keys carry a non-empty context.
-- 44 keys: 44 client with English, 0 game with English, 0 placeholder msgctxt.
-- Re-runnable: the upsert only touches a row that is retired, carries another hash,
-- or lacks context the file reads.
BEGIN;
INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
  ('0323dba24dc4ca77', 'client', $s239$Session games ({0})$s239$, '32be664aa6c0a222a968b2bcdc905e2598a5ca54', FALSE, NULL),
  ('0d08c15acf64fc37', 'client', $s239$Top cards (all modes)$s239$, '618c86600676077552bc3fcb0201a11317e768d5', FALSE, NULL),
  ('108905e2123ecbc7', 'client', $s239${0} series played$s239$, 'fdbd930f257ec2e3bbc02d2dfd80bd59887488ca', FALSE, NULL),
  ('11746e605482ad0f', 'client', $s239$showing {0} of {1}$s239$, '46ec2f98b00b79b27fba942b4baae134d4ddfacd', FALSE, NULL),
  ('1230b280e4d1ca09', 'client', $s239$1v1 record: series {0}W-{1}L ({2}%)   games {3}W-{4}L$s239$, 'e5af4ce71a82113afedde43f70c35c40229f887c', FALSE, NULL),
  ('12a2ee7e09002750', 'client', $s239$Game {0}   {1} players$s239$, '60067c6a686e7a3821f641d7c33e0dc78179d882', FALSE, NULL),
  ('19c2a45c2ec2988a', 'client', $s239$Score$s239$, '489f4877244a299131d309f0ca10733c1a41251c', FALSE, NULL),
  ('3d2ea36308963515', 'client', $s239$(partial)$s239$, '384e8e993068a9d3b73fbdac34f69d0bbc19ffa2', FALSE, NULL),
  ('3e1302982adf89d9', 'client', $s239$Session games$s239$, 'a8261c72e1c14f8f93320767108077b4c0196a16', FALSE, NULL),
  ('4932eaba51eabdd1', 'client', $s239$Ping$s239$, '6b68e97973994116d837d4de74f29d77f895c097', FALSE, NULL),
  ('4bded0062544c6c1', 'client', $s239$Current Game: {0}$s239$, '548bc7d4e4c72a8c8109d05c37ba08480735912b', FALSE, NULL),
  ('515b68d89b1340f5', 'client', $s239${0} players$s239$, '152c34217212e77f1f0a331aeb6b60286b866830', FALSE, NULL),
  ('59bf3e91608fa618', 'client', $s239$Favorite ranked cards$s239$, '367483822a4e8f99275ed1daad31fe06fda784e9', TRUE, NULL),
  ('5b3e863917a976af', 'client', $s239$Hit rate - {0}$s239$, 'ad63b1980e7f9c3bba418b541020bc56100c81bf', FALSE, NULL),
  ('5c9bcb043b857bb2', 'client', $s239$Game {0}: {1}-{2}$s239$, 'fd70315e6afaa97df008369227cf0b0b4a8a6b77', FALSE, NULL),
  ('6b0ae7187440ed3c', 'client', $s239$Block rate - {0}$s239$, 'c7168a4f8553df38c93f5bcdf33499da2eaa326c', FALSE, NULL),
  ('6b2353195492bb8f', 'client', $s239$FPS$s239$, 'fce204ae554cd5820b35e0ae8653db07910f77d5', FALSE, NULL),
  ('6c07743895412e87', 'client', $s239$Session Series: {0}$s239$, '88f7371eb24196978c257d2c1cc4a782622f8329', FALSE, NULL),
  ('745857a8dca56064', 'client', $s239$Hit {0}% Blk {1}%$s239$, 'da0484d06004a9aca15a1d045da97cb7447fee94', FALSE, NULL),
  ('7aa6dd3d9c00eecb', 'client', $s239$Series {0} {1}$s239$, '50bcfef87aaad308e18c1ebef30e73433fa21993', FALSE, NULL),
  ('844df63fc7799788', 'client', $s239$Session series$s239$, '4ce68df25afe5893260f76998322877642b58529', FALSE, NULL),
  ('8d1eb7f439d936f8', 'client', $s239${0} + {1} more$s239$, '01af2476cdb74ff6297b08f331bcd2a1c276cf52', FALSE, NULL),
  ('8d2f51bb322a407c', 'client', $s239${0} kills   {1} dmg$s239$, 'b752606308eb98d088cea0df5ed83d968850cc18', FALSE, NULL),
  ('918e61d0f4abde33', 'client', $s239$match data unavailable$s239$, 'b51992409edca91e5f36b8af904c5f333dff1f5c', FALSE, NULL),
  ('9503cca363369365', 'client', $s239$FFA session - {0} players, {1} games$s239$, 'f374c265a0669927968583a277fce4434415e7ee', FALSE, NULL),
  ('99713d7607aafd3f', 'client', $s239$Session: {0} games, series {1}-{2}$s239$, 'b4b229ac922197e28e6f9420c0376c910f8f7fe3', FALSE, NULL),
  ('9de65b2549d666fa', 'client', $s239$Recent Async Tournaments$s239$, '2d3f4c8923cfcfdb406bad65aba2d2e8e958f521', FALSE, NULL),
  ('9e93a32d4754dbb4', 'client', $s239$Graphs {0}/{1}$s239$, '01054b0109229cab306423442f0ce81891a39f58', FALSE, NULL),
  ('a3e2201f0fd7c9b3', 'client', $s239$Session: {0} series$s239$, '6e2cdaa7ba0d3d15aa4ceecce82e43494145efe2', FALSE, NULL),
  ('adc860031b5295e6', 'client', $s239$<color=#CCCCCC>Scoring history</color>  <color=#66DD66>{0}</color> <color=#888>vs</color> <color=#DD7777>opponent</color>$s239$, '9aa5d08a389c60c574c2edc82c05d79e411ac131', FALSE, NULL),
  ('b91c29dbe86f7b7f', 'client', $s239$No games recorded for this session yet.$s239$, '36b2d3606e2ae66c86595dad5736d619ea5b7993', FALSE, NULL),
  ('bdd76249bfe4b65a', 'client', $s239$Session series ({0})$s239$, 'fa37d118d2801580d4a50deda71f91b82a8190d1', FALSE, NULL),
  ('c60b3fb177ffdaaa', 'client', $s239$FFA session - {0} players$s239$, 'b59bfaaceed86fdb77668457fd1267dc817f3da0', FALSE, NULL),
  ('e2dccdf13c763727', 'client', $s239${0}  {1}%  ({2} picks)$s239$, 'f6150e902e7ef2d4c9b43cb55901ba01a77039a4', FALSE, NULL),
  ('e8dc06c32c0e1fac', 'client', $s239$Recent Sync Tournaments$s239$, 'c32af79262e2e235f95d678dc3e8ce1a7dbe6775', FALSE, NULL),
  ('ea1f96e30b6c6737', 'client', $s239$Game {0}   {1} {2} {3}$s239$, '5153f35507471943f8acdcfbb27f18b027db8af7', FALSE, NULL),
  ('ea5a4baa04c86c8d', 'client', $s239${0} games  {1} wins  Top3 {2}%  Avg place {3}$s239$, '74461284c35ce3294a098d44ec320782994dba20', FALSE, NULL),
  ('ec8d7a94985d2f92', 'client', $s239$All-time: {0} games ({1}W-{2}L), series {3}-{4}$s239$, '7c6eec66c9a19dfba83a37b6f5d91874f364b468', FALSE, NULL),
  ('ed8b774e24ef3273', 'client', $s239$Series {0} (in progress)$s239$, '8191b3f362a11adcdfb94a6adf53f0c3ddcdc46e', FALSE, NULL),
  ('f32e779b43ec84c1', 'client', $s239$Peak {0}$s239$, '692b07e24b3da4d3c88ffc89a129035c6b3249a9', FALSE, NULL),
  ('f8eda8388cbfb9d1', 'client', $s239$Current Series: {0}$s239$, '896bb6be6b7ff1931057c51860c1493a0857087d', FALSE, NULL),
  ('f9c988548e02a432', 'client', $s239$DPS$s239$, 'f3cec91c2f03b8c3dd9c2dfd2ad1f22b511ff8be', FALSE, NULL),
  ('fd708efa416a95e0', 'client', $s239$Overall Series: {0}$s239$, 'b8da5460b86f1e75d07c7208311170d7c9b2bc81', FALSE, NULL),
  ('fe4a63da748dfc1e', 'client', $s239$casual$s239$, '7b664f70da8a35f2e7c6ef8428a7141ea0cf3c3c', FALSE, NULL)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET source_hash = EXCLUDED.source_hash,
       msgctxt     = EXCLUDED.msgctxt,
       context     = COALESCE(NULLIF(i18n_keys.context, ''), EXCLUDED.context),
       retired_at  = NULL,
       updated_at  = NOW()
 WHERE i18n_keys.retired_at IS NOT NULL
    OR i18n_keys.source_hash <> EXCLUDED.source_hash
    OR (EXCLUDED.context IS NOT NULL AND COALESCE(i18n_keys.context, '') = '');
COMMIT;
'''

SEEDS['240_release_spring_nuclear.sql'] = r'''-- rf8 d2 seed (helper hc) for 240_release_spring_nuclear.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 240 guard: seasonal_spring approved rev 2, nuclear_glasses rev 1; exactly 2 approved

-- shop row face_detail_seasonal_spring
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880270, 'face_detail_seasonal_spring', 'face', 'face_detail_seasonal_spring', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_seasonal_spring');

-- approved submission face_detail_seasonal_spring: rev 2, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990270, '76561190000000149', 'face_detail_seasonal_spring', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_seasonal_spring', 1.3, 0, 0, 2, 1.3, 0, 0, 2, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_seasonal_spring');

-- shop row face_eyes_nuclear_glasses
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880271, 'face_eyes_nuclear_glasses', 'face', 'face_eyes_nuclear_glasses', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_eyes_nuclear_glasses');

-- approved submission face_eyes_nuclear_glasses: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990271, '76561190000000149', 'face_eyes_nuclear_glasses', 'eyes', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_eyes_nuclear_glasses', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_eyes_nuclear_glasses');

COMMIT;
'''

SEEDS['243_seed_machine_translations_forfeit.sql'] = r'''-- rf8 d2 seed (tag hi) for 243_seed_machine_translations_forfeit.sql: i18n_keys fixtures.
-- The file's INSERT joins i18n_proposals onto LIVE i18n_keys rows with the SAME
-- source_hash, and its DO-block coverage check RAISEs when a seed pair did not land.
-- Production gets these key rows from tools/i18n_sync_keys.py; here they are
-- derived from the file itself: every (key_id, source_hash) in its _seed243 pairs.
-- namespace: 'game' when key_id = sha1('game\0' + Table/KEY)[:16] over
-- tools/game_strings.json (or the file lists it as a game key), else 'client'.
-- msgctxt: the English whose sha1 equals the file's source_hash (found in
-- tools/i18n_source.json at HEAD or any earlier revision, tools/game_strings.json,
-- or the quoted text of backend/sql),
-- otherwise a labelled placeholder. Game keys carry a non-empty context.
-- 4 keys: 4 client with English, 0 game with English, 0 placeholder msgctxt.
-- Re-runnable: the upsert only touches a row that is retired, carries another hash,
-- or lacks context the file reads.
BEGIN;
INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
  ('203775486c7a82a6', 'client', $s243$Click again to forfeit$s243$, '6af3fdd7b6c6bd9921d66438a79392f88442f1d3', TRUE, NULL),
  ('29dd7d7b1c852928', 'client', $s243$Forfeit$s243$, '79424e785ea2fcce076a8fbcdba199e4a0edaa1d', TRUE, NULL),
  ('d1136733b5c62c42', 'client', $s243$Forfeit failed$s243$, '22333d4dfcca347a29c73248ab2e93e9930e41be', TRUE, NULL),
  ('df07898130ca13ef', 'client', $s243$Forfeit recorded - the match will be resolved shortly.$s243$, '012cc72f181623655f86f1ab4b06654ca4412740', TRUE, NULL)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET source_hash = EXCLUDED.source_hash,
       msgctxt     = EXCLUDED.msgctxt,
       context     = COALESCE(NULLIF(i18n_keys.context, ''), EXCLUDED.context),
       retired_at  = NULL,
       updated_at  = NOW()
 WHERE i18n_keys.retired_at IS NOT NULL
    OR i18n_keys.source_hash <> EXCLUDED.source_hash
    OR (EXCLUDED.context IS NOT NULL AND COALESCE(i18n_keys.context, '') = '');
COMMIT;
'''

SEEDS['247_release_v1392_cosmetics.sql'] = r'''-- rf8 d2 seed (helper hc) for 247_release_v1392_cosmetics.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 247 guard: five new at rev 1 with these scales; exactly 6 approved incl. seasonal_spring

-- shop row face_eyes_shock_shades
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881001, 'face_eyes_shock_shades', 'face', 'face_eyes_shock_shades', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_eyes_shock_shades');

-- approved submission face_eyes_shock_shades: rev 1, scale 1.55, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991001, '76561190000000149', 'face_eyes_shock_shades', 'eyes', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_eyes_shock_shades', 1.55, 0, 0, 1, 1.55, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_eyes_shock_shades');

-- shop row face_mouth_cat_mouth
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881002, 'face_mouth_cat_mouth', 'face', 'face_mouth_cat_mouth', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_mouth_cat_mouth');

-- approved submission face_mouth_cat_mouth: rev 1, scale 1.55, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991002, '76561190000000149', 'face_mouth_cat_mouth', 'mouth', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_mouth_cat_mouth', 1.55, 0, 0, 1, 1.55, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_mouth_cat_mouth');

-- shop row face_eyes_cat_eyes
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881003, 'face_eyes_cat_eyes', 'face', 'face_eyes_cat_eyes', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_eyes_cat_eyes');

-- approved submission face_eyes_cat_eyes: rev 1, scale 1.5, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991003, '76561190000000149', 'face_eyes_cat_eyes', 'eyes', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_eyes_cat_eyes', 1.5, 0, 0, 1, 1.5, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_eyes_cat_eyes');

-- shop row face_mouth_the_challenger
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881004, 'face_mouth_the_challenger', 'face', 'face_mouth_the_challenger', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_mouth_the_challenger');

-- approved submission face_mouth_the_challenger: rev 1, scale 1.7, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991004, '76561190000000149', 'face_mouth_the_challenger', 'mouth', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_mouth_the_challenger', 1.7, 0, 0, 1, 1.7, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_mouth_the_challenger');

-- shop row face_mouth_goober
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881005, 'face_mouth_goober', 'face', 'face_mouth_goober', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_mouth_goober');

-- approved submission face_mouth_goober: rev 1, scale 1.8, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991005, '76561190000000149', 'face_mouth_goober', 'mouth', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_mouth_goober', 1.8, 0, 0, 1, 1.8, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_mouth_goober');

-- seasonal_spring: live since 240 (rev 2 published 2); 247 needs approved rev 3,
-- scale 1.4, published < 3 (the re-placement the admin approved after 240)

-- shop row face_detail_seasonal_spring - published by 240
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880270, 'face_detail_seasonal_spring', 'face', 'face_detail_seasonal_spring', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_seasonal_spring');
-- already live before this file: publish it (no submission row exists yet, so
-- the 148 trigger only stamps released_at)
UPDATE shop_items SET catalog_ready = TRUE WHERE sku = 'face_detail_seasonal_spring' AND catalog_ready IS NOT TRUE;

-- approved submission face_detail_seasonal_spring: rev 3, scale 1.4, offset (0,0), published 2
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990270, '76561190000000149', 'face_detail_seasonal_spring', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_seasonal_spring', 1.4, 0, 0, 3, 1.4, 0, 0, 3, 2, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_seasonal_spring');
-- in the chain the row exists at rev 2 (from 240's seed + 240): advance the
-- proposal and the approved snapshot to rev 3 / scale 1.4 (the values 247's guard checks)
UPDATE cosmetic_submissions
   SET placement_revision = 3, render_scale = 1.4,
       approved_placement_revision = 3, approved_render_scale = 1.4
 WHERE shop_sku = 'face_detail_seasonal_spring' AND status = 'approved'
   AND approved_placement_revision < 3;

COMMIT;
'''

SEEDS['248_i18n_keys_v1392.sql'] = r'''-- rf8 d2 seed (tag hi) for 248_i18n_keys_v1392.sql: live client key count.
-- The file's post-check (the DO block after its INSERT) RAISEs P0001 unless EXACTLY
-- 1890 live client keys exist after its 53-key insert. Production reached it
-- through tools/i18n_sync_keys.py; here the seed brings the live client count, measured
-- NOW, to 1890 minus the keys the file itself will newly make live (a key it names
-- that is absent, or retired with the same source_hash, which its ON CONFLICT arm
-- un-retires). The shortfall is filled with stand-in client keys whose key_id starts
-- 'zzrf8' (not hex, so no collision with any sha1-derived key_id); a surplus first
-- retires such stand-ins. The file's key list below is copied from its VALUES block.
BEGIN;
CREATE TEMP TABLE _hi248_file (key_id VARCHAR(16), source_hash VARCHAR(40)) ON COMMIT DROP;
INSERT INTO _hi248_file (key_id, source_hash) VALUES
  ('5c299cdd5181a941', 'fbc862283106c3ad11970e3d7528cb421283e2e5'),
  ('1b3f3ff1f8bc538e', 'ac1861b407332050c7ad8ece653fde7c0a2885e5'),
  ('511b49694beadfab', '6f2d396e557b5f76d31e56571112c890b8ee7430'),
  ('84e17af7112e2c2c', '03cb2764ec60add600368e21f4fdda7ea811af9f'),
  ('e0c347af1c2e8c45', 'a5c48a631fa6ac8b9e71d1b9a78e93f88f013c43'),
  ('38ae3616902f9e47', '527774087ad99d4cbf98e04c8c027506f3dfaa89'),
  ('bb044ac5a0ad150f', '8ca39fdb3e24dc0164815c29c778320c3477b994'),
  ('e8d68fce3701fe2e', '0da332b305a132002eabd6a4d3b1dade76c79582'),
  ('d4ffe97d52355fb3', 'b4816f88de2979e10fa5707a46a4176b09682f23'),
  ('a9aa7dd7e345eacb', 'eef8bc1daff28c5ee9b334003283b6ce9b14141b'),
  ('0b90ace75370115b', 'cc83269496c01ca47b98e106203958dcc350fa97'),
  ('730802fcc588b2ac', 'e2cf54d378b402a3681ccc88f012f93dd28b5de5'),
  ('75eccff6b3ce7be0', '8f963207651b6b17c88011cc9a1cf5016ff08143'),
  ('52eb10fe5a54bd85', '45fc6c80b5f40c599a9996e4565f6c3c0441f578'),
  ('9922fbe350152757', 'a58ad4865dc2d5fdf3c26319e1ec8c4619cf3819'),
  ('cdac92171e43b9bf', 'c547d9751e2e1075a2d5db9846f7bd630adf98ce'),
  ('7c8d1536eb0fd36a', '95f3d46ddbd9f0400b8e07572a25f0f6dc0d6fc9'),
  ('8586bec2443a2aa0', 'b22b408fe071ebbc3d1087b8f7009a9a237ebcf6'),
  ('17c00df433739b35', '5ab5f51856f65ede67445fa3f1e37faeff8c86d8'),
  ('d453de367dadaf91', '558287ddcc3557b09ec00ca17b3e4be7e6645858'),
  ('5d29024a4d44289a', '3568c7491babebb953c769947cc8f490da802f47'),
  ('41f8d6df2156cb5a', '101288b594e03b935789b8a597f09d42680fa7d0'),
  ('f8387a7add74f327', 'd6c0ceed4033b33fc562d60d9b914946e813d9b7'),
  ('8dc459eeaa15acb6', '22584937a4a8382e23a56fbd261ae0dbda2c028a'),
  ('900bfdd2c5aaf566', '8114ab3a57601ffcee1b9eaafffb4c8561adea9b'),
  ('f4db3fff7c36a085', '95e92e3918fc6682050e39c82964ff3edb266fff'),
  ('7122e0c69ba45d2d', 'f2817a9b2c0417af68309b2a6e5dbab82f161295'),
  ('81c7b7cb050ea26d', '7fd885137d973cf162fe2417eadbd70ecd9734ae'),
  ('9a7fe17e2d48c091', 'e6cc9035282ccdebffc0f56f58f1b8d6c8a79311'),
  ('65c931b05122cf6c', '908554507507c82ec5bd2d28fe10e6b51fd4fe5a'),
  ('0429c34a08c40ee2', 'a15667a26f8fbd09ac67a9c4155551d0eff857fd'),
  ('10fc19103bfc00a4', 'b62204bc74efd9da27cf3ebbc7002c6e71a1a5ad'),
  ('e8318953ee3473cc', 'ffe6b732761562041ff44d44571715b12b5027da'),
  ('17fee1da703692c3', 'a6ed417fdbecf9d7cea95373bb7f74ab8b4f42d6'),
  ('9447c4a194d0bbf6', 'cbdb204cfdf3376735d0ed1cea0b9985b3bfe912'),
  ('d93ccfb1df90a055', '7e378d24d3eb1dd3ad959fd0244ac122c1944bca'),
  ('2114443a269971a4', '8566174efb4eb4edb2ed35464668e45a1334b95c'),
  ('47d9b036144dbc30', 'f6b5a94241188908466dd4e8866efdd71a095f00'),
  ('3c0f844e8017bc56', '670012d71850926c55cf6e4df5b125e67d1e988e'),
  ('df98d4645ac79249', '26c1d2970bb104ebf25377d761feeed044bbf63b'),
  ('aa1cc75adcac35af', 'a8dbee7af410ed602b17d9c2e9c7516d63d649b1'),
  ('a5239cbe85ee4b07', '3c6ddde8fbcc54626a1b093d38b2e1f79ccb5b71'),
  ('24217068bcc775e9', '1c933f68509c9bed6e49ae0ae73a5485f1006267'),
  ('35bd46d542291519', 'fbdf3954fe302a9669bb5146924faa655c14bd1e'),
  ('193478fa57528850', 'c49dfd91243662405690056d72d5545ffed41a88'),
  ('1ab9372118365ce8', '61ad233cad804ff442749806e155e661d6cb1fe8'),
  ('ac0a136fc03bd3ed', '5052759c37603ebc59fa10a45f0d8819b759e480'),
  ('a2747db45e42ad62', '26d43bc6493e51b1047f9b89c7a4247b7c236a04'),
  ('3cf0b30ec7dd441c', 'f665c772bf8a49dd52bfeb8ad1a6ac44b38cabc8'),
  ('8dce4de87ebefc5b', 'f54d4c1fe052a1040ab35be570d899d745e18151'),
  ('2d379480e63e50b0', '79e69b6303e570c6ed379ee5c5ee18bfd257b9db'),
  ('b61b00ae9924cd72', '68c5aaeaec955f166f73912d182f66e281c95d95'),
  ('34b4e4fcb0da7041', 'dbfa8132673eda37733efbad711f380ae714de0a');

DO $hi$
DECLARE
  d        BIGINT;
  r        BIGINT;
  newly    BIGINT;
  base     BIGINT;
  live     BIGINT;
BEGIN
  SELECT COUNT(*) INTO newly FROM _hi248_file f
   WHERE NOT EXISTS (SELECT 1 FROM i18n_keys k WHERE k.key_id = f.key_id)
      OR EXISTS (SELECT 1 FROM i18n_keys k WHERE k.key_id = f.key_id
                   AND k.retired_at IS NOT NULL AND k.source_hash = f.source_hash);
  SELECT COUNT(*) INTO live FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
  d := 1890 - newly - live;
  IF d > 0 THEN
    -- shortfall: re-activate retired stand-ins first, then add new ones
    UPDATE i18n_keys k SET retired_at = NULL, updated_at = NOW()
      FROM (SELECT key_id FROM i18n_keys
             WHERE key_id LIKE 'zzrf8%' AND retired_at IS NOT NULL
             ORDER BY key_id LIMIT d) s
     WHERE k.key_id = s.key_id;
    GET DIAGNOSTICS r = ROW_COUNT;
    d := d - r;
    SELECT COALESCE(MAX(substr(key_id, 6)::bigint), 0) INTO base
      FROM i18n_keys WHERE key_id LIKE 'zzrf8%';
    INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
    SELECT 'zzrf8' || lpad(n::text, 11, '0'), 'client',
           'rf8 stand-in client key ' || n, md5('rf8 stand-in ' || n) || '00000000',
           FALSE, NULL, NULL, NOW()
      FROM generate_series(base + 1, base + d) AS g(n);
  ELSIF d < 0 THEN
    -- surplus: retire live stand-ins only (never a real key)
    UPDATE i18n_keys k SET retired_at = NOW(), updated_at = NOW()
      FROM (SELECT key_id FROM i18n_keys
             WHERE key_id LIKE 'zzrf8%' AND retired_at IS NULL
             ORDER BY key_id DESC LIMIT -d) s
     WHERE k.key_id = s.key_id;
  END IF;
  SELECT COUNT(*) INTO live FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
  IF live + newly <> 1890 THEN
    RAISE EXCEPTION 'rf8 seed hi 248: % live client keys + % the file adds <> 1890 (surplus of real keys; no stand-ins left to retire)', live, newly;
  END IF;
  RAISE NOTICE 'rf8 seed hi 248: % live client keys now, the file adds %', live, newly;
END $hi$;
COMMIT;
'''

SEEDS['249_seed_machine_translations_v1392.sql'] = r'''-- rf8 d2 seed (tag hi) for 249_seed_machine_translations_v1392.sql: i18n_keys fixtures.
-- The file's INSERT joins i18n_proposals onto LIVE i18n_keys rows with the SAME
-- source_hash, and its DO-block coverage check RAISEs when a seed pair did not land.
-- Production gets these key rows from tools/i18n_sync_keys.py; here they are
-- derived from the file itself: every (key_id, source_hash) in its _seed249 pairs.
-- namespace: 'game' when key_id = sha1('game\0' + Table/KEY)[:16] over
-- tools/game_strings.json (or the file lists it as a game key), else 'client'.
-- msgctxt: the English whose sha1 equals the file's source_hash (found in
-- tools/i18n_source.json at HEAD or any earlier revision, tools/game_strings.json,
-- or the quoted text of backend/sql),
-- otherwise a labelled placeholder. Game keys carry a non-empty context.
-- 53 keys: 53 client with English, 0 game with English, 0 placeholder msgctxt.
-- Re-runnable: the upsert only touches a row that is retired, carries another hash,
-- or lacks context the file reads.
BEGIN;
INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
  ('0429c34a08c40ee2', 'client', $s249$Per-letter rich gold → ivory white gradient.$s249$, 'a15667a26f8fbd09ac67a9c4155551d0eff857fd', TRUE, NULL),
  ('0b90ace75370115b', 'client', $s249$Dark steel walls with amber window glow against a black-navy sky, city lights twinkling behind.$s249$, 'cc83269496c01ca47b98e106203958dcc350fa97', FALSE, NULL),
  ('10fc19103bfc00a4', 'client', $s249$Per-letter silver → gunmetal blue gradient. Cold and clean.$s249$, 'b62204bc74efd9da27cf3ebbc7002c6e71a1a5ad', FALSE, NULL),
  ('17c00df433739b35', 'client', $s249$Goober$s249$, '5ab5f51856f65ede67445fa3f1e37faeff8c86d8', FALSE, NULL),
  ('17fee1da703692c3', 'client', $s249$Per-letter sunset orange → dusk purple gradient.$s249$, 'a6ed417fdbecf9d7cea95373bb7f74ab8b4f42d6', FALSE, NULL),
  ('193478fa57528850', 'client', $s249$Shock Shades$s249$, 'c49dfd91243662405690056d72d5545ffed41a88', FALSE, NULL),
  ('1ab9372118365ce8', 'client', $s249$Speacial eyes for the feline enthused$s249$, '61ad233cad804ff442749806e155e661d6cb1fe8', FALSE, NULL),
  ('1b3f3ff1f8bc538e', 'client', $s249$Ash Gradient$s249$, 'ac1861b407332050c7ad8ece653fde7c0a2885e5', FALSE, NULL),
  ('2114443a269971a4', 'client', $s249$Per-letter white → dark charcoal gradient. Fades out as it goes.$s249$, '8566174efb4eb4edb2ed35464668e45a1334b95c', FALSE, NULL),
  ('24217068bcc775e9', 'client', $s249$Sapphire Gradient$s249$, '1c933f68509c9bed6e49ae0ae73a5485f1006267', FALSE, NULL),
  ('2d379480e63e50b0', 'client', $s249$Twilight Gradient$s249$, '79e69b6303e570c6ed379ee5c5ee18bfd257b9db', FALSE, NULL),
  ('34b4e4fcb0da7041', 'client', $s249$Wet teal-grey stone walls under an overcast slate sky, rain streaking down the backdrop.$s249$, 'dbfa8132673eda37733efbad711f380ae714de0a', FALSE, NULL),
  ('35bd46d542291519', 'client', $s249$Seasonal Spring$s249$, 'fbdf3954fe302a9669bb5146924faa655c14bd1e', FALSE, NULL),
  ('38ae3616902f9e47', 'client', $s249$Cat Eyes$s249$, '527774087ad99d4cbf98e04c8c027506f3dfaa89', FALSE, NULL),
  ('3c0f844e8017bc56', 'client', $s249$Poison's mouth$s249$, '670012d71850926c55cf6e4df5b125e67d1e988e', FALSE, NULL),
  ('3cf0b30ec7dd441c', 'client', $s249$The expression of a true warrior going into battle. Takes up the mouth slot$s249$, 'f665c772bf8a49dd52bfeb8ad1a6ac44b38cabc8', FALSE, NULL),
  ('41f8d6df2156cb5a', 'client', $s249$Night City$s249$, '101288b594e03b935789b8a597f09d42680fa7d0', FALSE, NULL),
  ('47d9b036144dbc30', 'client', $s249$Poison's eyes$s249$, 'f6b5a94241188908466dd4e8866efdd71a095f00', FALSE, NULL),
  ('511b49694beadfab', 'client', $s249$Ash walls with a dark crimson accent over a deep blood-red dark, red embers rising.$s249$, '6f2d396e557b5f76d31e56571112c890b8ee7430', FALSE, NULL),
  ('52eb10fe5a54bd85', 'client', $s249$Eclipse$s249$, '45fc6c80b5f40c599a9996e4565f6c3c0441f578', FALSE, NULL),
  ('5c299cdd5181a941', 'client', $s249$A silly little mouth for feline ethusiasts$s249$, 'fbc862283106c3ad11970e3d7528cb421283e2e5', FALSE, NULL),
  ('5d29024a4d44289a', 'client', $s249$Moonlit$s249$, '3568c7491babebb953c769947cc8f490da802f47', FALSE, NULL),
  ('65c931b05122cf6c', 'client', $s249$Per-letter mint → deep forest green gradient.$s249$, '908554507507c82ec5bd2d28fe10e6b51fd4fe5a', FALSE, NULL),
  ('7122e0c69ba45d2d', 'client', $s249$Pale silver-blue walls over a pitch-black night, with a faint star glint.$s249$, 'f2817a9b2c0417af68309b2a6e5dbab82f161295', FALSE, NULL),
  ('730802fcc588b2ac', 'client', $s249$Deep green hedges and bark-brown walls on a dark brown night.$s249$, 'e2cf54d378b402a3681ccc88f012f93dd28b5de5', FALSE, NULL),
  ('75eccff6b3ce7be0', 'client', $s249$Earth Gradient$s249$, '8f963207651b6b17c88011cc9a1cf5016ff08143', FALSE, NULL),
  ('7c8d1536eb0fd36a', 'client', $s249$For the silly ones. Takes up the mouth slot$s249$, '95f3d46ddbd9f0400b8e07572a25f0f6dc0d6fc9', FALSE, NULL),
  ('81c7b7cb050ea26d', 'client', $s249$Per-letter bright red → dark wine gradient.$s249$, '7fd885137d973cf162fe2417eadbd70ecd9734ae', FALSE, NULL),
  ('84e17af7112e2c2c', 'client', $s249$Blood Gradient$s249$, '03cb2764ec60add600368e21f4fdda7ea811af9f', FALSE, NULL),
  ('8586bec2443a2aa0', 'client', $s249$Forest Fire$s249$, 'b22b408fe071ebbc3d1087b8f7009a9a237ebcf6', FALSE, NULL),
  ('8dc459eeaa15acb6', 'client', $s249$Night-forest green and bark walls under a dark smoky sky, with embers drifting up through the backdrop.$s249$, '22584937a4a8382e23a56fbd261ae0dbda2c028a', FALSE, NULL),
  ('8dce4de87ebefc5b', 'client', $s249$Time to show them who is the coolest dude around! A pair of glasses that takes up the eye slot$s249$, 'f54d4c1fe052a1040ab35be570d899d745e18151', FALSE, NULL),
  ('900bfdd2c5aaf566', 'client', $s249$Nuclear glasses$s249$, '8114ab3a57601ffcee1b9eaafffb4c8561adea9b', FALSE, NULL),
  ('9447c4a194d0bbf6', 'client', $s249$Per-letter violet → hot pink gradient.$s249$, 'cbdb204cfdf3376735d0ed1cea0b9985b3bfe912', FALSE, NULL),
  ('9922fbe350152757', 'client', $s249$Emerald Gradient$s249$, 'a58ad4865dc2d5fdf3c26319e1ec8c4619cf3819', FALSE, NULL),
  ('9a7fe17e2d48c091', 'client', $s249$Per-letter leaf green → bark brown gradient. Canopy to roots.$s249$, 'e6cc9035282ccdebffc0f56f58f1b8d6c8a79311', FALSE, NULL),
  ('a2747db45e42ad62', 'client', $s249$The Challenger$s249$, '26d43bc6493e51b1047f9b89c7a4247b7c236a04', FALSE, NULL),
  ('a5239cbe85ee4b07', 'client', $s249$Royal Gradient$s249$, '3c6ddde8fbcc54626a1b093d38b2e1f79ccb5b71', FALSE, NULL),
  ('a9aa7dd7e345eacb', 'client', $s249$Dark indigo walls on the purest black background in the catalogue.$s249$, 'eef8bc1daff28c5ee9b334003283b6ce9b14141b', FALSE, NULL),
  ('aa1cc75adcac35af', 'client', $s249$Rainy Day$s249$, 'a8dbee7af410ed602b17d9c2e9c7516d63d649b1', FALSE, NULL),
  ('ac0a136fc03bd3ed', 'client', $s249$Steel Gradient$s249$, '5052759c37603ebc59fa10a45f0d8819b759e480', FALSE, NULL),
  ('b61b00ae9924cd72', 'client', $s249$Underworld$s249$, '68c5aaeaec955f166f73912d182f66e281c95d95', FALSE, NULL),
  ('bb044ac5a0ad150f', 'client', $s249$Cat Mouth$s249$, '8ca39fdb3e24dc0164815c29c778320c3477b994', FALSE, NULL),
  ('cdac92171e43b9bf', 'client', $s249$Fade Gradient$s249$, 'c547d9751e2e1075a2d5db9846f7bd630adf98ce', FALSE, NULL),
  ('d453de367dadaf91', 'client', $s249$Midnight$s249$, '558287ddcc3557b09ec00ca17b3e4be7e6645858', FALSE, NULL),
  ('d4ffe97d52355fb3', 'client', $s249$Dark ash walls with a pale rose-silver accent over a deep red night, with a faint red glint.$s249$, 'b4816f88de2979e10fa5707a46a4176b09682f23', FALSE, NULL),
  ('d93ccfb1df90a055', 'client', $s249$Per-letter warm grey → ember red gradient. Cooling coals.$s249$, '7e378d24d3eb1dd3ad959fd0244ac122c1944bca', FALSE, NULL),
  ('df98d4645ac79249', 'client', $s249$Poison's weeping$s249$, '26c1d2970bb104ebf25377d761feeed044bbf63b', FALSE, NULL),
  ('e0c347af1c2e8c45', 'client', $s249$Blood Moon$s249$, 'a5c48a631fa6ac8b9e71d1b9a78e93f88f013c43', FALSE, NULL),
  ('e8318953ee3473cc', 'client', $s249$Per-letter sky blue → deep royal blue gradient.$s249$, 'ffe6b732761562041ff44d44571715b12b5027da', FALSE, NULL),
  ('e8d68fce3701fe2e', 'client', $s249$Charcoal walls rimmed with corona amber on a true black sky.$s249$, '0da332b305a132002eabd6a4d3b1dade76c79582', FALSE, NULL),
  ('f4db3fff7c36a085', 'client', $s249$Orchid Gradient$s249$, '95e92e3918fc6682050e39c82964ff3edb266fff', FALSE, NULL),
  ('f8387a7add74f327', 'client', $s249$Night Park$s249$, 'd6c0ceed4033b33fc562d60d9b914946e813d9b7', FALSE, NULL)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET source_hash = EXCLUDED.source_hash,
       msgctxt     = EXCLUDED.msgctxt,
       context     = COALESCE(NULLIF(i18n_keys.context, ''), EXCLUDED.context),
       retired_at  = NULL,
       updated_at  = NOW()
 WHERE i18n_keys.retired_at IS NOT NULL
    OR i18n_keys.source_hash <> EXCLUDED.source_hash
    OR (EXCLUDED.context IS NOT NULL AND COALESCE(i18n_keys.context, '') = '');
COMMIT;
'''

SEEDS['260_release_five_faces.sql'] = r'''-- rf8 d2 seed (helper hc) for 260_release_five_faces.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 260 guard: five approved rows, rev 1, these scales, offset 0,0, frame_count 1; shop rows kind face

-- shop row face_detail_lucky_coin
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881006, 'face_detail_lucky_coin', 'face', 'face_detail_lucky_coin', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_lucky_coin');

-- approved submission face_detail_lucky_coin: rev 1, scale 1.65, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991006, '76561190000000149', 'face_detail_lucky_coin', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_lucky_coin', 1.65, 0, 0, 1, 1.65, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_lucky_coin');

-- shop row face_detail_lucky_ears
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881007, 'face_detail_lucky_ears', 'face', 'face_detail_lucky_ears', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_lucky_ears');

-- approved submission face_detail_lucky_ears: rev 1, scale 1.4, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991007, '76561190000000149', 'face_detail_lucky_ears', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_lucky_ears', 1.4, 0, 0, 1, 1.4, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_lucky_ears');

-- shop row face_detail_militia_man
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881008, 'face_detail_militia_man', 'face', 'face_detail_militia_man', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_militia_man');

-- approved submission face_detail_militia_man: rev 1, scale 1.45, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991008, '76561190000000149', 'face_detail_militia_man', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_militia_man', 1.45, 0, 0, 1, 1.45, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_militia_man');

-- shop row face_eyes_sadness
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881009, 'face_eyes_sadness', 'face', 'face_eyes_sadness', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_eyes_sadness');

-- approved submission face_eyes_sadness: rev 1, scale 1.55, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991009, '76561190000000149', 'face_eyes_sadness', 'eyes', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_eyes_sadness', 1.55, 0, 0, 1, 1.55, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_eyes_sadness');

-- shop row face_mouth_sinister_smile
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881010, 'face_mouth_sinister_smile', 'face', 'face_mouth_sinister_smile', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_mouth_sinister_smile');

-- approved submission face_mouth_sinister_smile: rev 1, scale 1.55, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991010, '76561190000000149', 'face_mouth_sinister_smile', 'mouth', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_mouth_sinister_smile', 1.55, 0, 0, 1, 1.55, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_mouth_sinister_smile');

COMMIT;
'''

SEEDS['264_release_five_faces_v2.sql'] = r'''-- rf8 d2 seed (helper hc) for 264_release_five_faces_v2.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 264 guard: per-sku rev/scale/frames/fps (phoneix_gaze rev 2, 4 frames @ 5 fps); offset 0,0

-- shop row face_detail_the_mobsta
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881011, 'face_detail_the_mobsta', 'face', 'face_detail_the_mobsta', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_the_mobsta');

-- approved submission face_detail_the_mobsta: rev 1, scale 1.55, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991011, '76561190000000149', 'face_detail_the_mobsta', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_the_mobsta', 1.55, 0, 0, 1, 1.55, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_the_mobsta');

-- shop row face_detail_well_wraped_hat
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880329, 'face_detail_well_wraped_hat', 'face', 'face_detail_well_wraped_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_well_wraped_hat');

-- approved submission face_detail_well_wraped_hat: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990329, '76561190000000149', 'face_detail_well_wraped_hat', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_well_wraped_hat', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_well_wraped_hat');

-- shop row face_eyes_phoneix_gaze
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881012, 'face_eyes_phoneix_gaze', 'face', 'face_eyes_phoneix_gaze', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_eyes_phoneix_gaze');

-- approved submission face_eyes_phoneix_gaze: rev 2, scale 1.8, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status, frame_count, anim_fps)
SELECT 991012, '76561190000000149', 'face_eyes_phoneix_gaze', 'eyes', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_eyes_phoneix_gaze', 1.8, 0, 0, 2, 1.8, 0, 0, 2, 0, 'approved', 4, 5
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_eyes_phoneix_gaze');

-- shop row face_eyes_smart_specs
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881013, 'face_eyes_smart_specs', 'face', 'face_eyes_smart_specs', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_eyes_smart_specs');

-- approved submission face_eyes_smart_specs: rev 1, scale 1.55, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991013, '76561190000000149', 'face_eyes_smart_specs', 'eyes', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_eyes_smart_specs', 1.55, 0, 0, 1, 1.55, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_eyes_smart_specs');

-- shop row face_eyes_the_cryptid
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881014, 'face_eyes_the_cryptid', 'face', 'face_eyes_the_cryptid', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_eyes_the_cryptid');

-- approved submission face_eyes_the_cryptid: rev 1, scale 1.45, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991014, '76561190000000149', 'face_eyes_the_cryptid', 'eyes', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_eyes_the_cryptid', 1.45, 0, 0, 1, 1.45, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_eyes_the_cryptid');

COMMIT;
'''

SEEDS['265_seed_machine_translations_chatmod.sql'] = r'''-- rf8 d2 seed (tag hi) for 265_seed_machine_translations_chatmod.sql: i18n_keys fixtures.
-- The file's INSERT joins i18n_proposals onto LIVE i18n_keys rows with the SAME
-- source_hash, and its DO-block coverage check RAISEs when a seed pair did not land.
-- Production gets these key rows from tools/i18n_sync_keys.py; here they are
-- derived from the file itself: every (key_id, source_hash) in its _seed265 pairs.
-- namespace: 'game' when key_id = sha1('game\0' + Table/KEY)[:16] over
-- tools/game_strings.json (or the file lists it as a game key), else 'client'.
-- msgctxt: the English whose sha1 equals the file's source_hash (found in
-- tools/i18n_source.json at HEAD or any earlier revision, tools/game_strings.json,
-- or the quoted text of backend/sql),
-- otherwise a labelled placeholder. Game keys carry a non-empty context.
-- 18 keys: 18 client with English, 0 game with English, 0 placeholder msgctxt.
-- Re-runnable: the upsert only touches a row that is retired, carries another hash,
-- or lacks context the file reads.
BEGIN;
INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
  ('0334124c315ddfdb', 'client', $s265$Link codes are disabled on the broadcast seat.$s265$, '275b7baf4f13ac034f94fad11c497b83c09a0630', FALSE, NULL),
  ('0b5dc7250d46a753', 'client', $s265$Leave it open$s265$, '7d0bac8c87e12fa00925f00cc2726a6442ee30e5', FALSE, NULL),
  ('101c48b93dc18a1c', 'client', $s265$Chat has been unlocked - carry on.$s265$, '229b63d4752af1d5e5266b484a27b937791c450f', FALSE, NULL),
  ('16f08519634a53a5', 'client', $s265$Steam sign-in still pending - try again in a moment.$s265$, '593d57b50f41ff087c272df7180b1ab47974acb9', FALSE, NULL),
  ('17b168c59cb4e7f1', 'client', $s265$Chat is currently LOCKED.$s265$, '43c150859e877ae3f3011e3f47320e8383b13d67', FALSE, NULL),
  ('3120a8bba946965b', 'client', $s265$Chat has been locked by moderators - messages are paused.$s265$, '00e6378fd0ad4c8296ae49a11a180f2b8f595139', FALSE, NULL),
  ('4e893d4679622bc9', 'client', $s265$Mute From Message...$s265$, '52e0adc5e18938e15f75d0f573f7e2f782f03a2a', FALSE, NULL),
  ('50b200539b8c78ee', 'client', $s265$No server-issued chat lines are in this session's log.

Pick a message the author sent; the mute lands on whatever platform identity wrote it (Steam, Discord, Twitch or YouTube).$s265$, '29873ae5ee3063929231f7ca5477418031d025e4', FALSE, NULL),
  ('529d48be14697fb0', 'client', $s265$Chat Lockdown...$s265$, 'c1487c661b3824edef495d3a1e179de9b6fd9df3', FALSE, NULL),
  ('56bb047fa0c21ad1', 'client', $s265$How long?$s265$, '9ce819198916f31ef18b3eb733d0c0f8f44ae386', FALSE, NULL),
  ('75b31f59dc8e438a', 'client', $s265$Chat is locked by moderators right now - your message was not sent.$s265$, 'ccf89e944f211bc90ff3942034ef0fa9402e2a52', FALSE, NULL),
  ('7aff9f0847fdcbe2', 'client', $s265$Chat is currently open.$s265$, 'b490c649eb08657196c358270e67e5c0d5f8036b', FALSE, NULL),
  ('85792e54b843280f', 'client', $s265$Mute the author of which message?$s265$, '30075a9c0c58a4307ec963912d41bb023e00e4d9', FALSE, NULL),
  ('9caebef13ee3df25', 'client', $s265$Why are they being muted?$s265$, 'f7684920539e981571f6a088e2ab56e1cadbf00f', FALSE, NULL),
  ('ad4eadb6ec8876c5', 'client', $s265$Mute from message$s265$, 'cf62c5356606def907e33a05301d822b3ecd1e35', FALSE, NULL),
  ('b9ddc17d768fa1b3', 'client', $s265$Keep it locked$s265$, '68d7017152dfa47134be41079d6cf5f23253371a', FALSE, NULL),
  ('cb26de5eb6b8bae9', 'client', $s265$Unlock chat everywhere$s265$, '0c02be9dbb6c822f3fc0b908d522d6d420a801ad', FALSE, NULL),
  ('db538c880f1cfde9', 'client', $s265$LOCK chat everywhere$s265$, '14103e23af3a7925ed4bf8b9c7e796d2b82e9751', FALSE, NULL)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET source_hash = EXCLUDED.source_hash,
       msgctxt     = EXCLUDED.msgctxt,
       context     = COALESCE(NULLIF(i18n_keys.context, ''), EXCLUDED.context),
       retired_at  = NULL,
       updated_at  = NOW()
 WHERE i18n_keys.retired_at IS NOT NULL
    OR i18n_keys.source_hash <> EXCLUDED.source_hash
    OR (EXCLUDED.context IS NOT NULL AND COALESCE(i18n_keys.context, '') = '');
COMMIT;
'''

SEEDS['266_i18n_keys_v1396.sql'] = r'''-- rf8 d2 seed (tag hi) for 266_i18n_keys_v1396.sql: live client key count.
-- The file's post-check (the DO block after its INSERT) RAISEs P0001 unless EXACTLY
-- 2071 live client keys exist after its 109-key insert. Production reached it
-- through tools/i18n_sync_keys.py; here the seed brings the live client count, measured
-- NOW, to 2071 minus the keys the file itself will newly make live (a key it names
-- that is absent, or retired with the same source_hash, which its ON CONFLICT arm
-- un-retires). The shortfall is filled with stand-in client keys whose key_id starts
-- 'zzrf8' (not hex, so no collision with any sha1-derived key_id); a surplus first
-- retires such stand-ins. The file's key list below is copied from its VALUES block.
BEGIN;
CREATE TEMP TABLE _hi266_file (key_id VARCHAR(16), source_hash VARCHAR(40)) ON COMMIT DROP;
INSERT INTO _hi266_file (key_id, source_hash) VALUES
  ('00066ff57ca04552', '5e5ecdae061097113bb0fc42625366227134dd5a'),
  ('0156bb7493bde398', 'ebfc95a4d5d9026a3d1e27e28ddc63b61698aac0'),
  ('0334124c315ddfdb', '275b7baf4f13ac034f94fad11c497b83c09a0630'),
  ('05b59a3c5f48d4e8', '724727fd048b142ad054df2241736afd1046a59d'),
  ('08e4b089323f0e2d', '4e0b21fb9bea2e824b17f811cb690017e9a9e984'),
  ('092b5f6f69738677', 'bdd2b2634fd3d1c82582c6d17bbf13f48f0f6b64'),
  ('0b5dc7250d46a753', '7d0bac8c87e12fa00925f00cc2726a6442ee30e5'),
  ('0d05a0ee7f392081', '671b7f7e4974e37ade6d2c6f72a8413565573f3d'),
  ('0f250d61631c5546', '4d064726954a17487f94e931f5b157b733ec22ed'),
  ('0fee8e919c17a19d', 'fc39b18f287d8bbfaceae020f4a4eb32ac5c1e70'),
  ('101c48b93dc18a1c', '229b63d4752af1d5e5266b484a27b937791c450f'),
  ('11ba9036331b2f6c', 'c4d37600fe6a8b34ececbfffaf5ba84d5bfe876c'),
  ('16f08519634a53a5', '593d57b50f41ff087c272df7180b1ab47974acb9'),
  ('17b168c59cb4e7f1', '43c150859e877ae3f3011e3f47320e8383b13d67'),
  ('1880d7803c54ac9d', 'e3e82846c32567811615378f30240185871e08e5'),
  ('203775486c7a82a6', '6af3fdd7b6c6bd9921d66438a79392f88442f1d3'),
  ('23a74746442c4c65', 'd9a3a948f03f6021f1f8317e899698c4663d22b5'),
  ('24268d2ea1640f9f', 'ddd6c173bb4cc9055abb2cb3d69a2fecbb208747'),
  ('29dd7d7b1c852928', '79424e785ea2fcce076a8fbcdba199e4a0edaa1d'),
  ('2f256b33d79dee66', 'a651b4acb3daeba9b52b9efa76cb07e0661bc6af'),
  ('3120a8bba946965b', '00e6378fd0ad4c8296ae49a11a180f2b8f595139'),
  ('34eaa39f9e9f80a2', 'f579c8b1fa341ce3edef722783b5f58bc7d152ce'),
  ('368adc406bc7cf17', '60575a6ebba9f780b4312324662169830d12bea1'),
  ('39a9fd7c9aef944d', '573dd2c2ed953b97e3c31f3090925fe92109b779'),
  ('3a0f1f521d0087b1', 'a360cd1a4517c555248721ed7c005b0978680c08'),
  ('3d63d417e0763f1a', '00ead328a3d6b748c93fcafb7260e9cc0a45baba'),
  ('3f657265a8382ffb', '0458a184cf383c785aa5094125d6491b775dbb63'),
  ('406b02c730784003', '0ef565eb43156859af82b408109cafaedaa9cb35'),
  ('41371036864d76c5', '7e45cc8c4037f981e655aac54372fe576c73f315'),
  ('4e893d4679622bc9', '52e0adc5e18938e15f75d0f573f7e2f782f03a2a'),
  ('4ef49a8a6d86b7f0', 'ae857850d9f6a01df5c6318de07ba3b3d87eedbc'),
  ('50b200539b8c78ee', '29873ae5ee3063929231f7ca5477418031d025e4'),
  ('5150a5bb7cbaf0bf', 'cd09e18a9bd74edaca7d487211db598da4416565'),
  ('529d48be14697fb0', 'c1487c661b3824edef495d3a1e179de9b6fd9df3'),
  ('563586da39b3814b', '4f07327b6b2ffcb74a720b247fdf065d8ebb7891'),
  ('56bb047fa0c21ad1', '9ce819198916f31ef18b3eb733d0c0f8f44ae386'),
  ('5870ba76aee47a05', 'fb17e73c809a9abb8768087eae063849f63b9412'),
  ('5ae909299d5434a1', '3d56e9cc99258ab6de6f89390be351705194253e'),
  ('5eb6d5777bd80861', '07519800157f4a2da4b48a1d0b215d7c5b5a8cde'),
  ('62696896c58079eb', '286e61e5c91f29635f56fae46d6fa62ff77b3552'),
  ('63db72595c4c8d68', 'abe457a4002adffed941a8e45e388126aa40c730'),
  ('64969edef9932b86', 'a667fae512b63902faee00b07f06f45b68f99092'),
  ('665d16d4b2840e40', 'b1cfe72fd27178870354f9f4e07bb82072caea55'),
  ('68118d0219af41cf', 'f6768922f2f9a8ed554246089a769ac9601ad6c2'),
  ('68a41081df125636', '3a78197a6777de78e110c24747b2bb709b093d5d'),
  ('696b16741d564cbe', '11909a5d9524d840fe00140ae23bfe7861fcabf3'),
  ('6b91a0c0f2c14c99', '56e6b3b32501d5af9853e7f97e93a55b819286c2'),
  ('6dc9646c05027ed8', '8fa659fa9f6fda8264f786e2bd627a2917418221'),
  ('6ea3113de6680882', '47899b0bf8c2b9dd3fd5ee49700c77ed0d8f56a2'),
  ('7025fdd06041768e', 'f031701805141ea08448cbd97997244fc8148058'),
  ('738daca5c3f26df9', '439df3824c961ecc56f1fe97caa5ffd60c2a740b'),
  ('739b01547fcbd9a4', '03a24c219a319f77774cd07b8c2225f4929f8e24'),
  ('74a3ffbd1b2e254b', '3582b0f3e9efe01dc8ee0d184bda1f3b466825df'),
  ('7540291f1a032c7b', '522d8de7ef9c668bd7130111c9ddb031294192fa'),
  ('75b31f59dc8e438a', 'ccf89e944f211bc90ff3942034ef0fa9402e2a52'),
  ('79d45b2ce8d63afa', 'a1c54a88a06fa44bfb072b8e23ae00e2ff16bc1e'),
  ('7aff9f0847fdcbe2', 'b490c649eb08657196c358270e67e5c0d5f8036b'),
  ('7c8c5a19b3c15dcc', 'c11af80bae28e54048d1c71ecd63f75bd729f0c6'),
  ('7e318ed8676d0e52', '7dd30f0a95d522bfc058be4e75847f8b6df9f76b'),
  ('855d1e8b07c2e7d5', '48b0c1f86d79f0e617c9eee867b1aaff41d758b9'),
  ('856fa04b654ab1e5', 'eab48914f0422378fab091ccee6ce862c737f5d4'),
  ('85792e54b843280f', '30075a9c0c58a4307ec963912d41bb023e00e4d9'),
  ('85ef80364c159655', 'fc051e48bec64b6c5b9f5f7a8795c8c9e4f9c7eb'),
  ('86b037a625d0b9b4', '8bb57a9623bacb4a696286be7447896412172cb2'),
  ('907371d0551605f7', '24808976280582a15b1721fc0d411d73a086f625'),
  ('9caebef13ee3df25', 'f7684920539e981571f6a088e2ab56e1cadbf00f'),
  ('9dbeace378dd4e1b', '3b3b2afc3f0b1587e298a86559403fee7db4e4d0'),
  ('ad4eadb6ec8876c5', 'cf62c5356606def907e33a05301d822b3ecd1e35'),
  ('ae21bb12835baffa', '4f6eba21524da93b7eea907d03f93668ee66ebb6'),
  ('b0020c192e5a1183', 'e4264ec8fb10bdf6a4e134e6320886298061a4b5'),
  ('b4bae31e5af0891d', '047c66202cfc53f93a8901d3d5f5e13c724815fa'),
  ('b4d316822b96ba26', '0cb58f388e3dde80555698a33dd62ee6f8cd6af5'),
  ('b6a4621d6912a7e6', 'c790d4c7e5ac933c97c61a08108a8515f1549902'),
  ('b782b304c02b0e85', '28c2d827acda4509832481f6d4ed5eacb610f759'),
  ('b9ddc17d768fa1b3', '68d7017152dfa47134be41079d6cf5f23253371a'),
  ('bd0bc7f08f0598fa', 'ba1d0e86c4762d03e8cf3638291ac7575929c326'),
  ('be620029c980686a', '3a12dba0070937a0c83d2c3a55dce1eea0c9e793'),
  ('bffaa52506c86556', '92c0c56a90c4346196b1221605638694fbc876e4'),
  ('cb26de5eb6b8bae9', '0c02be9dbb6c822f3fc0b908d522d6d420a801ad'),
  ('cb5928d5a704187d', '5dd1972661f7c6dc1c186c74e14b7d40854af096'),
  ('cb7ebf1fcc9cbffa', '046dcf45ba01218e7d000fd0a8a3914ae591c6ea'),
  ('cbb0440aa5052d96', 'effa17fb09544b590f3e2505d9d125d726ed1f86'),
  ('d1136733b5c62c42', '22333d4dfcca347a29c73248ab2e93e9930e41be'),
  ('d1568a20c1c5c81f', 'ecdbdbbb2c39fd700bb4ae334fd2615defb3172f'),
  ('d1b0bffe890cc265', '2d0910f5c35e9d87fffb89b1c2ab084e35940195'),
  ('d3dc6e977ef36a1f', 'b1a78dcbad0d2834c3cf2f89267746a475b04459'),
  ('d463ba4d3fe6c730', '2bc4f5879207567e69e8be799e9c265524714089'),
  ('d4b6c2192ee2be64', '07a76104d37f51b66843ad75694bac1918b012b0'),
  ('d84d735748f37ad0', '5c143e75d051c3859764af514e48c9912cbe519b'),
  ('da8d672ca0b035a3', 'ae0907b9efcaa8302a0a5d6e533d255a39c9a968'),
  ('db538c880f1cfde9', '14103e23af3a7925ed4bf8b9c7e796d2b82e9751'),
  ('db5fee62fd6d46d6', '319dfc18c3c743c697453e2e356cc1a786dc6a7b'),
  ('dbf7b69987b7393d', '1c2493a2cffcc002e422dca455556ce4ebdd1b22'),
  ('dbfcf5cb5e976351', '81dc80bb5cad62384352a74489b0ad8f36a90d30'),
  ('df07898130ca13ef', '012cc72f181623655f86f1ab4b06654ca4412740'),
  ('dff0df94a8c1250d', 'e313b4f3c742df2b6bf812407bd145e84a1f9b39'),
  ('e042a7be97677db8', 'aa1b3d9c7ef709cd7b74a271ae640f04b027c6fd'),
  ('e05f733dc555566c', 'eb2d72144a8eb56074736534e4fda9d819d267c0'),
  ('e3b65fff831bda23', 'ab92d11f5f3ed5e802b7409a9fe778e877afb9a7'),
  ('e5dadf69deec4be8', 'cd2dd9251a1e2b57b766c5972c39c07ad8e015d6'),
  ('e8fffd61d2b123c0', '77a406f15d46fbb8fcb9db489eb464c6e0c590cb'),
  ('eb4037a9f3bbf1a3', '8ac4bdca240a00d1d6e951be2f2c6a56c23f1fd6'),
  ('ec2abf1508ba136a', '998c82568cf86e63a5076cdd864f7c9f28f67328'),
  ('ecee43db04e473cc', '984d0e19218e75b60f1a78f14bcdd2f6ce92af7d'),
  ('f8cfffdbc154226a', '97f13afb5db03819911341e5b7e782561f069219'),
  ('f95da11526f422b8', 'd4935ba458a53152ac538277ca378c07b264d9f2'),
  ('fc38e4476e514059', '4c2d87bcd6cb6da3b237d31d45dc55d25eb664ec'),
  ('fdfe7ec82dafaf6d', '2df908378d5e5235eb570a2c8b7a70a509279c87'),
  ('ff097547403cfb2a', 'ad60c535ff88e85bf0254452fe3934f24e9668d5');

DO $hi$
DECLARE
  d        BIGINT;
  r        BIGINT;
  newly    BIGINT;
  base     BIGINT;
  live     BIGINT;
BEGIN
  SELECT COUNT(*) INTO newly FROM _hi266_file f
   WHERE NOT EXISTS (SELECT 1 FROM i18n_keys k WHERE k.key_id = f.key_id)
      OR EXISTS (SELECT 1 FROM i18n_keys k WHERE k.key_id = f.key_id
                   AND k.retired_at IS NOT NULL AND k.source_hash = f.source_hash);
  SELECT COUNT(*) INTO live FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
  d := 2071 - newly - live;
  IF d > 0 THEN
    -- shortfall: re-activate retired stand-ins first, then add new ones
    UPDATE i18n_keys k SET retired_at = NULL, updated_at = NOW()
      FROM (SELECT key_id FROM i18n_keys
             WHERE key_id LIKE 'zzrf8%' AND retired_at IS NOT NULL
             ORDER BY key_id LIMIT d) s
     WHERE k.key_id = s.key_id;
    GET DIAGNOSTICS r = ROW_COUNT;
    d := d - r;
    SELECT COALESCE(MAX(substr(key_id, 6)::bigint), 0) INTO base
      FROM i18n_keys WHERE key_id LIKE 'zzrf8%';
    INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
    SELECT 'zzrf8' || lpad(n::text, 11, '0'), 'client',
           'rf8 stand-in client key ' || n, md5('rf8 stand-in ' || n) || '00000000',
           FALSE, NULL, NULL, NOW()
      FROM generate_series(base + 1, base + d) AS g(n);
  ELSIF d < 0 THEN
    -- surplus: retire live stand-ins only (never a real key)
    UPDATE i18n_keys k SET retired_at = NOW(), updated_at = NOW()
      FROM (SELECT key_id FROM i18n_keys
             WHERE key_id LIKE 'zzrf8%' AND retired_at IS NULL
             ORDER BY key_id DESC LIMIT -d) s
     WHERE k.key_id = s.key_id;
  END IF;
  SELECT COUNT(*) INTO live FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
  IF live + newly <> 2071 THEN
    RAISE EXCEPTION 'rf8 seed hi 266: % live client keys + % the file adds <> 2071 (surplus of real keys; no stand-ins left to retire)', live, newly;
  END IF;
  RAISE NOTICE 'rf8 seed hi 266: % live client keys now, the file adds %', live, newly;
END $hi$;
COMMIT;
'''

SEEDS['268_publish_party_crown_rev2.sql'] = r'''-- rf8 d2 seed (helper hc) for 268_publish_party_crown_rev2.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 268 guard: party_crown approved rev 2, scale 1.4, offset (0, 0.55), published 1 (live item)

-- shop row face_detail_party_crown - live since v1.32.1
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 881103, 'face_detail_party_crown', 'face', 'face_detail_party_crown', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_party_crown');
-- already live before this file: publish it (no submission row exists yet, so
-- the 148 trigger only stamps released_at)
UPDATE shop_items SET catalog_ready = TRUE WHERE sku = 'face_detail_party_crown' AND catalog_ready IS NOT TRUE;

-- approved submission face_detail_party_crown: rev 2, scale 1.4, offset (0,0.55), published 1
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 991103, '76561190000000149', 'face_detail_party_crown', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_party_crown', 1.4, 0, 0.55, 2, 1.4, 0, 0.55, 2, 1, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_party_crown');

COMMIT;
'''

SEEDS['281_clavar_activation.sql'] = r'''-- seed (hm) for backend/sql/281_clavar_activation.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;

-- 281 gate (lines 49-60): exactly one live players row with the artist's steam id.
-- The uuid row above carries a placeholder only if the steam id is held elsewhere,
-- and then that row is the live one; this insert covers the remaining case.
INSERT INTO players (steam_id, display_name)
SELECT '76561198040410653', 'Sid'
WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = '76561198040410653');

-- 281 gate (lines 61-64): the artist_users role row for that steam id.
INSERT INTO artist_users (steam_id, display_name, notes)
SELECT '76561198040410653', 'Sid', 'rehearsal seed'
WHERE NOT EXISTS (SELECT 1 FROM artist_users WHERE steam_id = '76561198040410653');
'''

SEEDS['282_i18n_keys_v1400.sql'] = r'''-- rf8 d2 seed (tag hi) for 282_i18n_keys_v1400.sql: live client key count.
-- The file's post-check (the DO block after its INSERT) RAISEs P0001 unless EXACTLY
-- 2427 live client keys exist after its 356-key insert. Production reached it
-- through tools/i18n_sync_keys.py; here the seed brings the live client count, measured
-- NOW, to 2427 minus the keys the file itself will newly make live (a key it names
-- that is absent, or retired with the same source_hash, which its ON CONFLICT arm
-- un-retires). The shortfall is filled with stand-in client keys whose key_id starts
-- 'zzrf8' (not hex, so no collision with any sha1-derived key_id); a surplus first
-- retires such stand-ins. The file's key list below is copied from its VALUES block.
BEGIN;
CREATE TEMP TABLE _hi282_file (key_id VARCHAR(16), source_hash VARCHAR(40)) ON COMMIT DROP;
INSERT INTO _hi282_file (key_id, source_hash) VALUES
  ('018e099fd8ed2dc5', '3d3d4c5ad7b1daa8ce5a6f622acab3916a7e666f'),
  ('0195071f9f835b41', '0feca720e2c29dafb2c900713ba560e03b758711'),
  ('01a4b599f350abae', '0297fb1e6c176b4d67ea304108c33235fbb5d723'),
  ('027931eb075e1aa4', '6462a1a2c3dc92512ae5dce25012908d66eaea5d'),
  ('0322c42f001ed4a7', '5e337b6470b963b592464ec5c40d56150f192cf7'),
  ('039bc0c9d5cf3e9a', '3fb910cdf01afaf3a6efa8bfb22b2882ac1e6831'),
  ('04f0f934efc4061e', 'bdb3ef244fabc64235cd611c73655326395a986c'),
  ('054a9e0ffa32420a', '9e76c2cfaa74237c4667dda1106096059423809a'),
  ('07ddf0eb2233d445', '085c6d7c375032aee0da676b3f0a7b0f029d62ea'),
  ('0938287c5f713cf1', '1a8e5468168f7afe3c5ddf6cc716dbb6674d4cc5'),
  ('09a1aa463f338351', 'b86445f0e6c41a5f76bc9faa3b81b6b4f2fb8959'),
  ('0aff582e300474d4', '8c2e0e1d55b890163a0578eee7d56dc9a8163f4e'),
  ('0b27001b6759297e', 'c57c6f7f29a8f6c42980ae80a5dd755b51421483'),
  ('0c0c58a969ea6324', 'f51730ea676e6268149dc283145a89fd42e55431'),
  ('0c88e1a2a371e57d', '9413f2a8d079b061160c6cce7968b08bb38bf16b'),
  ('0cfce7055946c432', 'bb086b36eb4297b438e04630658cb14db77ba543'),
  ('0d18b8f43d73161e', '874a0591fc04611262fdd744ebec93993dacecc5'),
  ('0da56f0ef6ca392b', '9d84d798f14ca14192b5a722f8deba3488997934'),
  ('0f3d1f351e4a7862', 'c40497b1048c1314d0ed1d417cba50705d6627b3'),
  ('107f9e44420b6a70', '2e5c88d9dff1ac89fe4c65eb5841e1a969463c87'),
  ('1107099ffb76a22b', '132a8134e5e820d1aa9b05a3dde48da1d3c25f44'),
  ('1152b9c31dbaa74f', 'cfe537a5f3289e5512190c65186f14dd08253154'),
  ('1198284ca4ddd03a', 'dfca1636d73096541e96ab0c3463eea6b8867dde'),
  ('1318e9afd85da213', 'f81fae96e119e012ff27043537c33c26f0545e75'),
  ('136ec55c8ce85296', '35cf82f9d2a9c8ba5943837ec0d6646d49a7a51e'),
  ('13b5e24f84f0ed66', 'a7eaf6bc6f5bfd2e69d581a14dda0fd9d27bbc20'),
  ('13e7a1792e8abd1e', '35f58c657c654b247ae5592e9450f5a69c96ebff'),
  ('144f088248385b4a', '0493923fe233433dacf26ffe427e4790aacc9f7c'),
  ('1497e4b80e5a3664', '16b24a0952726b5c0d2889f8abde87eec79d5dba'),
  ('14b128653a9a6e6f', '05d289b3fe377471612bbe291e5e3f293827ed30'),
  ('15320b7b158aa43d', '4453348acf4193bd357d9dedd76c9c00ea33234e'),
  ('16270e075ff09c38', 'f76a4926ab971b67975e14dbee83d6872ac9bb50'),
  ('16f2e4dd38463d7b', '908c526215debbd4ee1363e3666282a9b9c82697'),
  ('1810e65fb6bc6f81', 'd7bb69fb19763c09ddf7ae009395afc7badcfc2e'),
  ('190cf3b65caa555e', '8d8fcef4337c7ea051f3066658a0ba94861ea8b0'),
  ('1928b19204130de1', 'b0b19f7da5a641c8cd96fdb91d53b19ae2d2e36b'),
  ('1931b64f5776ffe6', 'ec27f4e8a660e892b1e898de326c873c402f9da8'),
  ('19cf70accfab0f0d', '5f95d9a80a176c2d1425c1953e1eb7aafd071e43'),
  ('1a6c33ac1dff9370', 'b97598910533b3e47d54e5684ae3d32280929726'),
  ('1bd56f0d3fbd9153', '2452413e142aae220bf50fbfa426f638b7816ce4'),
  ('1bf9b5aeb836afe7', '7c6f286eedfab90b66922459d09fc9166e5b14d3'),
  ('1c854c38083d1b76', '8d4ba065ae312536d8bdc5b787d19bb682bdc302'),
  ('1d3095cabdbc923a', '7c8dc31180d2f22bff91272414ca074254e9957e'),
  ('1d4b353260bcecaf', '51932d71c2a90560a3906a6e9fb9ab42ab946fce'),
  ('1d7fa00018397e5b', '5e8adebb89e8a50a78020624ead3f89d2f40de6f'),
  ('1dd3db8c064d9654', '246386952c55f6e0b6f2ee074517a11ea3b7cb02'),
  ('1dfcc098b4da261c', '1c15dd7ddb9d813d9dc6cfb93e6d07cca1ff84cc'),
  ('1e52aed7fca8a685', 'c7e4e114997188bbd97b7fab1b85eecfed1376c7'),
  ('1ee66467a63c926b', '2d45294cfb5df3152b549d461df19d0ddc8c8414'),
  ('200548f66e07ef64', '8a57dce3d90f3f7cfde4e62c118f13581c918e12'),
  ('20d7d7730e89c1a0', '7d592751d4d4fafee4c845a55414581c35ac1dfd'),
  ('20db26c30c3100cb', 'cd56cc98a81ff4372bfb6936afdb2fc3c63b2d7d'),
  ('20f0dec1c5491a83', '60e7dc38d58fa8d4dd69f14b8056f4fa75478377'),
  ('23312ec72122ea17', 'fc8aa74b208bf96597dfceec0adc76284bd94eab'),
  ('235e32ddb1201875', 'fd2f5c58c6a2ab9b9b61e5b1e568db7a14f2b934'),
  ('2397da0da5fcc65e', 'a986c975fdbd804c9f7c6192cc28951d219f32e5'),
  ('24a8bf4272627e03', '3c9a7b75e6c2a22994653b2e73cc4ca9ec71f098'),
  ('2540afb343a5f6b0', '8a2584377c89eac38f632458e5033c953d620077'),
  ('25b56b01dc34efe4', 'dea9d1370e983ae7e4bed0df6cf3b161e81228f4'),
  ('25c0e9b2f1f58bfc', 'eb6ba65224fddbc1c969f37bc2b49e0744e4fef5'),
  ('261d9ebb1aeac0dc', '2d29f93bb633e5c66e01b643ad7b153868d9a451'),
  ('2657ecf2564002d6', 'c3ed4e612af7644a8c04b0bb56878797d9751c8d'),
  ('26f0f8a2335ba795', 'fc64ad2e2aed235943184651399172baabb8d6c4'),
  ('26f78c1badaa8ce3', '6e348c0357c64c677e6641a1ce0d64222506b9c1'),
  ('2768f7fef66286bb', 'b1656ecb60391d107bea3e96f0db721368eaba93'),
  ('2830536e6c923330', 'b436e67207eb767fb094726f88bc196c02ec2cfe'),
  ('2862bc6be01046aa', '1b613ddf1549425f05d9b31e4bdd762382c123ec'),
  ('28664eb4ad65366d', '4b98983397b11a2cf0b05ae55891d3d7a35221b7'),
  ('291ff30d5079e949', '9cf80338abce8b567d68f64cfdbc22acaed2d62c'),
  ('2ca17fb22ceeb91e', '732bc6ebb89a10d9399dafcf3162dc41462e2371'),
  ('2ca28458c1bba16f', '3041bad1187c20fb9675fb2ee260fb4efa4a8055'),
  ('2cf57bd52862f8bd', '8e92ea5917efa32360585d08790d531fdb553521'),
  ('2f7eefed49e94df2', '341bb8dd1de413c75605a0c3834651ef423f01ec'),
  ('2fce258a62d8ca9f', '9848405c532ef118e7d6f79df0719e454c91ffda'),
  ('30d4db904ff26b1f', '710f35c028bf084903e82e5b9b737dd62abd1136'),
  ('3375a7a17a28e03e', '7fe1293aa75e21cb2297dc2d43e8dc0d8f248425'),
  ('33bfac719482404c', '0e2aa9db2a51762cc7ef7e2472f33a421dc2776e'),
  ('33d92083da701bc8', '4c1dc591501192d873bff90728e05c837a820f95'),
  ('3422362fcfe614f0', 'be5467fdb8c2f0918b82a4a46b9f0cf6a6a75115'),
  ('34c4b0f8d3827925', 'e6560d9c298e72db56c00c64c9c0c9c6a63ca288'),
  ('34e94342172ccc16', '7c6b93acbc4088c277552ad8ef6ab2f2dd378d59'),
  ('35a41c9dae50afd8', '1e58e349feb201eaf84819b8cbf5ce95e3251093'),
  ('3641c4073564f471', 'b6fe8586434a4165d8531d4cc3c065a8a9e700df'),
  ('3786a6bd207e499c', '1b7065ae1c038de8c69cfa7e56294b2e33055ce8'),
  ('3878e9a06f200884', 'eeb8efa38b04f77978c1af0170aa5d063ac81369'),
  ('3890f0cbb586ff4b', '66f3ac75224897b518295f324d2eaaffcbdae888'),
  ('38cb3a00ec4aae7f', '6415fc8a6d53f7a4d32943d64d274f346316f7f7'),
  ('392b2a7a739ec173', '680eee018198c6a159af8cf43ac17b9336e05343'),
  ('3b839398da0a7306', '60c939e8c8b5a9eee31173dadc4d14d0f36d8887'),
  ('3bc15e26749d12d3', 'cae59f99028ccdf1803e8bd4384e23450ec0a46f'),
  ('3c0d5358f8d4d5bf', 'f0db6799b034ff866597cee74eff4ea14f74175d'),
  ('3cadba6cb4d299db', 'e735d970c376d796959969c8839aece4074458dc'),
  ('3ceb575bb104e67a', 'aaabc04650aab77b47f331f4aacd9649ab02c710'),
  ('3d771675aa9386e3', 'f2e1c7fad591bf812899592b3df6cde5ff734de6'),
  ('3df637f1d1f20327', '571a19ec45d137f48cfba3989f252ecc1b8d8fce'),
  ('3e02a22d69671a03', 'faa338188b2b5cdec06937f45f707599ae35d7eb'),
  ('3ec5a312dd9938e0', '86a984947ac8c52cf4500bcfe364a187dd27444a'),
  ('3ef6e666a4087849', '8044c2aa3964a194eff018e055d8259fe024ad05'),
  ('3fd3cdb18f2f274c', '18350a4c720998d2321ea9fb4be9972b87283f36'),
  ('40389559a5d3a7c2', '99cf818cabe3e4801c06b9427a9ce4f4d1500280'),
  ('404cd01710201dc0', '78c3dc0e955697c34e9dfcdb511092a48644b44d'),
  ('423228a4fc37960b', '355b09f4e293431128ee7c4e69fa7ef1838b03b1'),
  ('4242863b150cbda8', '38d6c96d36ce8a29693c24c898c7948d153eb801'),
  ('42453248177629c2', '3c25ce154a917b9c1539c47ac2d217ea7f6b9cf5'),
  ('426e6d1b01fdabd1', '438d7ff95d32eb9ec0be883747768af8db8f4a80'),
  ('42b363065f7bc00c', 'e923dca9795b936117ea5017d3a38acd54af0566'),
  ('435a4b2bbc8034c8', '4f3db459147e54b55553a20c115fcf8572173c35'),
  ('444e1ff03b6093fd', '2b0f48724a24afff6f64901d1b39e182338465d0'),
  ('47d1650b03894f39', '7c0d87a15587ef5cae2edf1d482863312cd9e5de'),
  ('4813d16325219e3b', '7cdfe78ce185ab16eb859aa0ec1cf81fa1a15ac7'),
  ('4867ccd0ab09b4b7', '5015bc8802ef6f39234ea8b46bd73b2a9ca5ec1f'),
  ('492e7a1185b61208', '932268f69f8abd8f78fcb54324acbb153db7695f'),
  ('49365749c7b1c2de', '60c988b15337b0f7139c96ec178e4dc424949c85'),
  ('49f54b769f831d85', '7e1e863c271feae27da33fc702d797697314a93b'),
  ('4a16145380f98364', 'dead726bfa96a471da1ee009d3a1b131af1380c3'),
  ('4ad250fa964a3477', '745c907a5bceb3e19de222759912533d47907064'),
  ('4ade614fa0dc0708', '7263a1edd582c7b3ef9fbe39bf7fea9c382188ef'),
  ('4bbd82317abb0839', 'c2cd71ebabf6233304c88629eb6587714c60ac1f'),
  ('4e8e19e76bc1131d', 'd48d8147cd24c327b544b44a62303e65da6feca6'),
  ('4f7e0e667293a970', '146fb58ce6a9e9e0c19f9433130c9b3e0431f1b8'),
  ('50514f77be6d49ff', 'bea6098ea458b065476f3ec8a265587f5a25be11'),
  ('51fa309a2660b60c', '6365d6a9d800c10fa6e483c59e130301bb787840'),
  ('530f0fe2b09f05af', 'df39fedad614b9e9ab0ed078f3d133f684213b7a'),
  ('530f79859164bfc5', 'b6930ee4436274d073a3d615ae030956e78e7e28'),
  ('538ea7a3863c3322', '320ea28ff8cf9fb1c048c77e5311c2c2ccbda228'),
  ('53c4654c16ccc2d1', '538071b476b87fe12f052546400549b2e321210c'),
  ('54f27396051fa05c', '33906a7dfdec01bb765c738946d88161600ca35d'),
  ('5678fc6bff05c631', '1cadad1503961af2e4f1a03cf9083519e5d26a7d'),
  ('569b4265e5397abd', '558865a16feb9f751b8bcebf46a954afbeba0b24'),
  ('572f63ba8113eadc', '6a395052c9ebc4235d024c28291d96b8cac3053b'),
  ('577b16be2ddd5908', '3a0bdc132cd5be4ced44219ee0d007f2880b21d5'),
  ('590afb688bd26848', '15fe0cc914c02a1b50fbad57027e5bdb10d7a371'),
  ('5981cfc4bec6d2aa', '2568e0420d78a050256fff684957c4eb34011abe'),
  ('5b6c67eb59c7ad5a', 'b63228b8b8d05bc27009feeff1265e8eac3e82c1'),
  ('5c61ac09c8790e5a', 'dcc6f8c98198485da8208044f04ac1ea4a225177'),
  ('5d9749b7d1d2cd50', 'd8796d7466c24ad713a37062fa958677b0622370'),
  ('5e2f844126994bca', '16f5853cbde985dccf1dea304da084cc7b21813c'),
  ('631a133c537677af', '9c2e955e1da510a3a7ac7128096bed12c608b737'),
  ('63e41c49cb39356f', '646aceb36023cfb5fa89dc1111b69bfd7c8ec40d'),
  ('64dc51615fc974c9', 'f8dfbbe866f95cc4ec4b4480ee1ecaf3956c6a33'),
  ('64fbafa71c64ea5b', '1d4c4223850b4c5a79983792395382208c8f79c8'),
  ('66173b472176d55a', 'f21e9b7f054b8df1f3badc742f510743bbbf019f'),
  ('66cfc06b58cc1eb9', '2895057a632eb8e91dfe420d751a813655e0432d'),
  ('66f0a10fe77a4874', 'd90a22c31ec7bdaf4e9f528f58c63a30ac020e29'),
  ('6743a3837d3b1790', 'ca0de51d37da52488bbe822980c08e8f4b54ea66'),
  ('67fde0c40c147a46', '9ffc71853c15ce02fa37020b54707f5690435f6c'),
  ('682d02d713ebead0', '0b5c4206710a5a0dd90dba2856fd460845b06573'),
  ('689a1b913ca5b95f', 'e3b2c4d88bb44675b4d10d5aa3f7a001254164b9'),
  ('68ae3ba5bde0a1c6', 'c19286c4efd42e3a0809eb95f62008936dc218fb'),
  ('68c4b3a3a991374b', '4932f159926656102e9a366a3b5482b27c1c0811'),
  ('6917a6295e2296eb', '32ef70ca2278f2060923c0806c0b9b46af7a2341'),
  ('6a9b064b1f6c4773', 'c63b8683892a259a8e3463e0f29a8dea1e962304'),
  ('6acb2025439df09b', '17b8b7386ad2a3ed4cf024889d17f1cac584e54e'),
  ('6b7e447c165e9e5a', '9638ffe3063b448179253fb1100806c4c854316b'),
  ('6c12e59cb06be91e', '857132eebe84c050a0d8339923da43657fdfcb15'),
  ('6ccaa73650023797', 'ad50489054ddaae044be8b3054bf4d67480648d6'),
  ('6cd6ad59ec9f0ff5', '131260cbfbb0c821f8eae5e7c3c296c7aa4d50b9'),
  ('6d56f30dd3dd50f7', 'a1f04d4d1e7f99b9139640cf2e9b7fa3a6154903'),
  ('6db3bbf4f54c0cb1', '0782adb78e6c9b99ee3bcd1ef5f675a1b8147757'),
  ('6eac4ea23c0996dd', '3fa1667ada7e05444855ca035afd6b2f5282594e'),
  ('6ec8b00fdee94097', 'c78fc60f816f6151cfedc59e75bc5099d887665f'),
  ('6edb1352e795ee14', '5fb0b4362428b56ff9d74047337ff4f264be5e21'),
  ('6fde99ccb04c9464', 'a113da2015d647a799efb39468a15c241df25809'),
  ('718d188e4455bdc5', '3f95bde7012ad5270801b8142efe43e5c9a8ae95'),
  ('71b012c4704288df', '38d4aa698a701e2288a153e115d12aab45de5940'),
  ('73d934a944709623', '8b8b2dee5ff2ae6048c22012233bb467d8c909da'),
  ('73fdcc5f35928195', '9a9f207e68bab4a7126b9ec05121eecc23a57a4b'),
  ('747964099bb289f7', '93b4180f31d99408aadbdd42d402569ad35d84ae'),
  ('74b15a6e53f51a1e', '20bdbf8143b5d78b30c7701b6fd05c824e7f6d93'),
  ('74ebc17cfc494570', 'e9a1a8a21f79f89a312697ef0c500e016f93e43c'),
  ('757475070fae24d1', '9c40e6c83966edf6af71bfd2f2102c7b0d01024a'),
  ('76ca3828c8c44f21', 'b1a9647bbf64260e0acbc6c4172aeba96327b59b'),
  ('772a3d4462b7ff96', '695f4b556a22ea8f0d77cbd168f3bb8fe91512e2'),
  ('78c89c8ea5a01801', '75c4d27c742d1f6e7f36095b70192842a6fb0217'),
  ('799b6e13c11f28dd', '06f7d0b555da9ef521a214c28fdb6bacf5ce74cc'),
  ('7a80d7e68ec2f588', 'ba803cb03686e743d6e9702d329b5bfe5c5e2a94'),
  ('7ae14936a4754653', '35bcd8643f8ac67f525e911a2088afb8d31d4e78'),
  ('7b3149fddf2edfb3', '06d49afa15d06ec94bfe72d56446e09c74d5962f'),
  ('7bdae0bc3cd1610d', 'aa38e5e141e048571e807299696f02731a996dd5'),
  ('7c348c3bd4aca5bd', '5faea509660c2904fe179e85631f377cebebe5b5'),
  ('7cc033f4e2ccee08', '9c4cc5ddd54ef465a817bc3d4ad390d86342f142'),
  ('7ce772413df76f97', '99bc7c117c72c2123f3c96eb3dd62d003748821e'),
  ('7d3238c8a8377e00', 'c6f750e3606cb1acabf51eaa12518b3cac219656'),
  ('7e7ce5225b69fa21', '6a35e13d6078bf6447b978d8d41795fc54c18658'),
  ('7ee66c85b18c5bb0', '9f5cd8a2e8807d73efa02c844bfbca9fe552b283'),
  ('801db4ac576038b9', '31412d98b3bdcdd01a31a2e05f02c6c31f34a24e'),
  ('8156d646ed5d3762', 'bc85baafd8bb80ab1dbe6764cb0d771feba2fe72'),
  ('8242f437f1ba7af8', 'f723884c1a8f207248e9f8bb98e7019a979c9d0f'),
  ('828f105fce189c49', '251a6cbf14c3adbb715cea7913f49fac0b956c85'),
  ('82db2967d6278668', '13ae374e9d0eb2c240c688ebb7932cc3dbb4a275'),
  ('84560648012ce2e1', '5ecbe3fc814b3bedd3ae2f8e48735110c17a7e27'),
  ('84603418a58395c8', '380985fee96b8861416b2c6ba8f200ba045c59e0'),
  ('868d9fbdce7103c3', 'c0df998c8501ac754421472bd3a94844fcb67326'),
  ('87c6e8bf8e7ae780', 'b896146b87f9453da24ac71dee61c5e301b13a6a'),
  ('87fcd616bdd6fcd8', '8b665bae87464c9df3296fae2077214efc5ab31a'),
  ('889d5548ce21e996', 'a8e9a6158d251d77ba30554805e11a731a6d3e1f'),
  ('89e56876664535f9', 'e8ea5fe2a6a5083495e58e7939264d6fc4a08efe'),
  ('8b17e8b203c35266', '090784407ecb4e04e63455bbe866f5a003ad9f06'),
  ('8c1eb356c1525df3', '3d54b658e24e84cbd5bf677fdcb229ba5796f7d2'),
  ('8c4ab8bbb2d8c374', '10b2a3262b0f0a229a73e14c516db37e4a51d930'),
  ('8cd713a42dc28b19', '28f7fc6c7106e01bbdbd4bdcdff80262b106c5cc'),
  ('8db61be6a2860732', 'da9ec544c59c98e53c9aaf2442e3d81d2725ec08'),
  ('8e55c28baa95c60c', '94658d7c8c878f44e18d73f9c8affbfa3f8aa94f'),
  ('8e79cc7c9152efb9', '5d12bd53552cafc41ca6146c04870df2e1574e13'),
  ('8ec026c42940c6d2', 'c814dc7375c9e38a44272ffd35f78577ece5f21d'),
  ('90c58689d7c96644', 'fe8dce1485bae8c21fe8add8173abcc34654bc7b'),
  ('912677eb32da6ab4', '149b8de2b0282bcde23304b8948eaaf895a98809'),
  ('918ff09cc73c9768', 'c66d3912b0770404d0b1b5a491d20937bab1bf16'),
  ('91d0e41ce8239cee', 'd6be16ee6ad11c21c61667420b3ea858ce6fef2d'),
  ('93242dc563a40eaa', '5bf308cf1d016503a4a74b2849cc00b563192617'),
  ('933131317eca7e8d', 'ed3b73cc402c48f39ce1b90ef1d8947bda12267d'),
  ('934ede0ef4f25930', '427951d00b193b43a44cfc0af03c9d67cf6edb60'),
  ('93ad7abdc83e80b3', '478712e443993e3d89008450795a14a38a876383'),
  ('95a1dd042c370b2a', 'a672274429e29ead95f174ff943a96fd99e2de74'),
  ('96e1ded8751a35de', 'da41f778f7ed3ad1dbcef4e78c5582014b07121a'),
  ('974671d54b95adb3', 'bad9bfbb27bf708a96616e3cb17bf14ecb178567'),
  ('9789ec57aacffa6f', '680bce4b84ac071af8bf71cc98932d5dde018070'),
  ('97ed03fa320e46f3', '8e9ab1eb27d0a3fe5bff1c54133eb397a100592a'),
  ('9861281a93a3c0c0', 'e3ee0a9ff9034e3b2ca8c19b278b01ac6248cc55'),
  ('99396dedb5f2d0cd', 'f97d3b31bdb725fbe43f10f3481dba557c7aa946'),
  ('99c7f1983a568f7e', '05599a662494b836496c17e39d7810966b42c27b'),
  ('99ff6d9d5d869554', 'c3f2d0282552ceccb72ae077467142fd8eb4b486'),
  ('9bb3752670ea25f8', '69ed28b1105d8d9da2f97744cfa4365f1058cff5'),
  ('9c3600034286ad0a', '6bc6c5a526fc83f0257710772097ebe1885b2b2b'),
  ('9d39ae971605ed24', 'da6bac2901375736cf9f663da7a9942169e4774f'),
  ('9d452a3cc7e4d696', '667404cccb112645b3632eca1c8ed8b4a0c12407'),
  ('a056950ff82a33c6', '1660bad3f82d6d49f38461bde6cfddfe9830caae'),
  ('a0b809cf10f75d41', '692f254e30158dac89e251017eaff0948bcc4bf7'),
  ('a0fd44d7de2285c6', 'c582339cc3887c3a38bfa00b7a7c8e9ff54b118c'),
  ('a274aad4509f84e6', 'ff0a085bff181fc81a692033955e81c60b5eed54'),
  ('a2f116ee16145bcb', 'e159f84a4239ebdebbb028d2c001ae78b388aa1a'),
  ('a352871ddde71056', '672504530777b1b681d9f21d05eddcb13559c535'),
  ('a35754f4e143ed36', 'ba6f9d8321e8ac1ce86fc8e723247cfb4453cfa8'),
  ('a37e12e0c7749da9', '1231f90b40c299944a06340b5ca7e8a2f92e4170'),
  ('a3825c2ab956ca64', '6287c791cf7634cffd62a205b30593f7bc398ca0'),
  ('a39001b83c5b81c1', '1f9a8b41a664901e7686ee4caca99a56d3beee86'),
  ('a41a6a516319d6c0', '30833899ea88dc9cb31c326cc8c85a2666cda7de'),
  ('a4255a4114972113', '861be15995b350b7675a1c2783e64e1d6d1e2414'),
  ('a54351b7fa8f4bf7', '5f8ea57e0f4aa31e85b064a66d579d79972eb768'),
  ('a662402c35b6f0bf', '58632221da3c855ed9e898cb8e3496ec9c4a261e'),
  ('a719629c97ed0c38', '80906f59d6ca0f6e312bafd4c6582951097803b6'),
  ('a907a9bcecb375bf', 'e5296ed2f8b67d8cc42d2dc7ff153822c1575f4e'),
  ('a9260e7026739931', '83e43e66b11a38d83ba77abdfad13d330f58e224'),
  ('a952b80387530503', '02947f4f39f84289021e16e1b6436a5e33a0b16c'),
  ('aa98c15b3fd5db76', '30c66db52a244cf8b873a828ba4941dc3bf1b105'),
  ('ab3f5cd6e8d0692c', 'b6d58313c976fea70b5d632b3f1250c39de2282c'),
  ('abe8e5a9fd37471a', 'aa50bfd83ec8c8109f2b439405fd8292fadace98'),
  ('ac354c1e95bc9f0d', '24ebe978ab7453659552dbeb029bebba00495fe3'),
  ('acf6218467f33f12', '6f2c72bec243a655d2179316134a66cc9d19533e'),
  ('ad11b6f7ca557add', '05353af9d3b5d51ef1e6ad31b9a4042675e7a13c'),
  ('ae24752fcf1f3aee', '3c688a6b39eb7b8e1a0d5c5f4759c3a79586679f'),
  ('ae2dc0c4a783a120', '2b08101b6b9bc6d8943aacefab6589145b277707'),
  ('af192920f8bd310e', 'f48902bd433ae6ef4d653cc3eff2ed4d03a50591'),
  ('afcf70b297ca5d26', 'c64430c93ebef3dbe560293a486c6b3b5785e504'),
  ('afecea29bc7bb5b5', 'd732cf6647f10509dfd37d789f659c18dce662c4'),
  ('affd5382eaca97d3', '3f4bed95c640cfa39f522b142b1ae86ed421fee3'),
  ('b10f784abe59d8ef', '0ed3ea4113b2726f9870b87104a8eea6a7e5e2d8'),
  ('b1d1da9612c4011d', '6dde9dc4ea9619bfcd9b8dcbc48605479fb1cbf9'),
  ('b272a9274980ddf9', '20632bc30721b7b1111cc82ebfe4420e4ad7d5d8'),
  ('b2b856cabfe69155', 'e466f5b100a24b17e640948976a1fef4fe86681f'),
  ('b447f84a0cecd9e6', '9532d22227de6928e6b0dd3e54e9c0afeed8738a'),
  ('b492fedfe366aaf0', 'b3c71efa1b2e2068d719a2aa9dab639c4e5aa362'),
  ('b618aff81c272358', '7356f9d83ad3ebef5aa96ab01b52e61f12c1cbe6'),
  ('b652886c9f750c58', '8358d9cff2953c92267bb21092fff91232279340'),
  ('b6c259ff73599f88', '256eaeedbdddb39dbb730009c35d8a52e25f9a61'),
  ('b7465dcd1fcafeca', '28b99c3f6732cdc8eac5aed4e05cf8c47868fba6'),
  ('b8b614d78b815e1f', 'bb41346607f1ed37851b0126c59333ae05444d97'),
  ('bb0cbec539928a34', 'c60f08db0bad1ed802b2acf74f4b6d03af15d01c'),
  ('bc49fa6684de77c3', '5ae5564648a3decf4f1564b4f1973cfc7ca0d622'),
  ('be14fd775fc8c284', 'bd2754668fb8f42a6f97ec724714677c6f41d803'),
  ('be9eea5c45cb8307', 'ea0646b8da2ad450dbcd915b4bf8b8ad9b500d0d'),
  ('bea16a781a4dd7d5', 'e5398f883daa5f89eb09ddf30c9d5b97f7ec8978'),
  ('c0a0607f3e2d6394', '3eaf750e8d8107db4ca83f8176b53e0e3a3e30e4'),
  ('c221bbb17e0f44d6', '792d1bb864cc19bcaf69fc46f39ecdfeabaf85f6'),
  ('c372037f23bf8282', '95a3328110c7692a26084ccda18cf878c13df0d3'),
  ('c3d2282d14e75714', '6a446a531aa163cbfb6355753f8ff17e98c909b3'),
  ('c3ff7b61de7b2cb2', '7a7005c30bcb5cd09fb1489f56c4acbf5968dbf1'),
  ('c612c77fc68ea0c9', '78efcc153076dcd201fc27282452c0dd0c62e4f9'),
  ('c61fa7034ff70a0e', 'fb360f9c09ac8c5edb2f18be5de4e80ea4c430d0'),
  ('c748f274fd740798', '661e06440fb85ef6750ea1fa15b10d3d1d12096c'),
  ('c952a39f8d2c92f3', 'd4e4e53c827126fca1c39f8ee242bc7e1857b9a7'),
  ('c9a9a504784c0fdd', 'bcca96d7c97b106a652be1b5520bf9861a73b560'),
  ('ca40e68882698352', '03d2d9f81c45084e0afbb42bab8d676369477d72'),
  ('ca67f6bba15bf734', 'f3dbe5f67e8948cd7dab46f833832ddc3020a155'),
  ('caff242c617e9b2c', '9b2aab6b06a8501fc157f91e020a7376de7c5078'),
  ('cb214dd8fdcdef80', '5bfb30cdbd1b6e637c5e3fdd9b7cc5cbc4498c7b'),
  ('cb6770434c10f8c3', '00d3b5a6efce0c118a61bcc07602e886b96a9ca4'),
  ('cb93e4d862f0d5d8', 'b385fed762cbac170a73be10adb8a477f1761794'),
  ('cbc8740b1695a190', 'af1789e79d5ee6ea9fa8d5ec234ff48c8db3e8b9'),
  ('cca48f0cfd3864b2', 'c2a50d949d2b8b52c35753dee3c405940bad2ac2'),
  ('ce0e1f95541897c6', '4cbe09f6351f1f3546faeafe30805718ab64e2a4'),
  ('ce473d718d21724f', '4682e10052d183bd1b01ae10f9420e7a8baba6b2'),
  ('cee62f37b4113baf', '78c5fbf3c125733d57b79e440509b7494ac71551'),
  ('ceee15a894860be2', '758692850822b2769fe7459a6ba3ded3dd35e5cc'),
  ('d170dbccf38117ac', 'cf083d74ed75bf0158f1c485f1c87ab9b2ec1b4b'),
  ('d2e1c859dbdcdf34', '257f305b043a469cf483af28b88025aeffa6e98d'),
  ('d32d128d5ac713ea', '9757b29440e4b4ef49e94e10094e5706dbe5cb93'),
  ('d34a0d31083dd876', '1be0a8f67aa11f43b03ea32d1dd277f75954722e'),
  ('d500172fde31785a', '675c88e46ce412aa6494219653a480445cc66633'),
  ('d6b2086f3537ac5a', '51965c0404a0449c99b8e16f493f6b7c5bd1ec18'),
  ('d77eb2ed30c92497', '8f0a822b86368ce0db1e0c6a787e4c03742f7b35'),
  ('d7d5fc77fbb32d5f', '798a99d1d8ff14b5e88ac1facc0ac563d5377c0d'),
  ('d84edc438cf970b4', '758f79de372b7abe0da36f7a47150319187a120b'),
  ('d89af6b095fa7a6e', 'a9a4378b07fb2a7eb676e4d7a5babcd48893621a'),
  ('d8cf14d63c80e35e', '9deec55bcab0c91176b8e30340256189cb1302b5'),
  ('d9253ed2b22e05f4', 'cc15912c399aa848c449dacc5e83fe084a0fa5f3'),
  ('d94f5b08f27af934', '77ca2284c1b7b0157881d45cb033ce75ddf1aab4'),
  ('db1c0f8507f229d7', 'b8daf3245d0bb316337366d100c95c7e657c362f'),
  ('dbf4faef919486db', '85b95acdb74387a141ac27ee0aa79640ecfdfb13'),
  ('dc38ca0bb8c08c98', '7bb41e1db3a4c09552453ba3496fed9fc7b13845'),
  ('dc8ca2a55307498d', 'd6d2248bd5af439f06e478bb3297bce222bdb7f2'),
  ('dd01ededf1c8c18c', '271330d994ea7546d2efc98de562966a6a530b38'),
  ('dd0cbe6d69e1e26b', '464ed8f164b2f378ec5c9090ee0ac8b522b1c081'),
  ('dd2445017b5ffa41', 'f1fbdca78de260855c81cbd171d9379eb4c1394a'),
  ('ddcce7205b472382', '8319e5a5268114bf58d0eb608ded75db9b2095a7'),
  ('de022e1f770c414f', '12a0d60f9f881a3edc74172253daa3ce062126af'),
  ('defcda03b0e04429', 'cc26754a33fbc8129208643f3bb5fe69742c8053'),
  ('df0ebeb8748ad0fc', '42c5cda0ffa59a8691d0bf44578f236901d42363'),
  ('e06b0ea27a685763', '6fed6440264c173b26f2225b8cebd0eeae8b9a0d'),
  ('e128123d770ddbe2', '83788d4175517bd358cfab6754397adc8ccb40c5'),
  ('e181752d3a2abb1c', '16c142f517d5cd3cc3b465b392c9ea438374786d'),
  ('e3dd7dfe3582f5e6', '28a0d9d1ba64751d2992ae548aa39bcdbfc975ca'),
  ('e41cbfd220932ab2', 'a0ad0ecead7d6f934d389fc1ccb31c50dbdeb30b'),
  ('e66cb18f68b63ea3', 'e076f29122f30e52c0c072566963e93522d67fd6'),
  ('e6d82c7fecd456b5', '2f5b1a23c18d38b64e27517e40dd5a639ea270db'),
  ('e81331915974fd55', '9e10ff0f8b9d89c366d06e06ba24fd30da382f7a'),
  ('e9cbfed6a11d404e', 'c4c85cf747ada8e52cc6035e7744b26c75a13e40'),
  ('ea66c841fb926192', 'ed6912ad70e7f5f44c4e228e2168918d894d50ce'),
  ('ec0db0eef9a77b84', 'fef54a0228deda825b33fcb615fc718603b433b7'),
  ('ec3ba28ef8180508', '1c0bdb37df4c2cc2ffd2c3090286f5e5399cfc7c'),
  ('ec58935c8e62aad7', '1a2420720ae16deb2834e7dcc92b8fa67fdf8c8f'),
  ('efa2db577712bf34', '0462fea2f9874e1ca9333be1562c930ed280d248'),
  ('f0879faeb75eb0b1', 'f69ff6e8d889fd11305a1035f80d7cfb42c367f0'),
  ('f1ae60f8bed4f5b8', '4bf611ca20f506ef1cfbbe3c15e669598075a558'),
  ('f1f232b77a6b7397', '55ca1d6fd64c1aa2b8364c095427f5b23e923720'),
  ('f2b2d44102db58c5', '8b7c4dd82c77a28db0f41a622064aad9ee8b1ef8'),
  ('f2d0a7e6347ff683', 'a415c1bcab4833e32dd4d2f7760f355aca5d935b'),
  ('f2f9b149b9bdc2ff', '34f4ba41ace1cf468ce976bb2d07104bfcb302a1'),
  ('f2ffe8af3edaa0a5', 'e381da8384a70e3b854918ffa0340328e99a7890'),
  ('f3d6ba57b5fb6eaf', '9752a30de8b8b560ac88841e9d20469390e55604'),
  ('f4d726ae9f55a9fe', '53cb1f455d882f798601207af0839bff46ad3b46'),
  ('f538fc29da07e500', 'cf3c872f8fb22c2234c807eaa7edd9a9e2d07c1f'),
  ('f604cbceb3fd8af0', '1312c12a42b9a5d0d5417d78e7ded8fa439e98a0'),
  ('f63dc62e1917bfe1', 'ddcb991b57e50d9e3d28f6969711a34b411c5a79'),
  ('f6e7a6de91dd5197', '6d1039cf610e6208ecf5f37f7debd6ad05afa84c'),
  ('f7a22af2b0e1e50b', 'b6ab482e980abd109633aac2a2d069bcc17bedda'),
  ('f8911a22f310a60e', '9c22dec522b1a7430c72799f83d17ab2283012af'),
  ('f96d89a65de6bc21', 'd8010d74929ce9a0815f1768239e5630c11eea1e'),
  ('fbe88305123b5f30', 'd254ab8e5f7189a6076b2a12d4502e9ec8f8a59e'),
  ('fc5ddef17a60d95a', '38ecddf69e8409bc60fb8e1f9bcbc3d7ef5c603b'),
  ('fddf3191109ad367', '3f5e663ffe95270650b331c4256b3a81fbff7c68'),
  ('fe155ed1d897c0ce', 'ac7d200fa1ec6ce18c2d700dbaef2f32e2a9efa4'),
  ('fe55f5cffac7f3b9', '43bbf6ddbbd6c835b405870a184d3714afa6b12d'),
  ('fed41b1541e5ebd2', '182fb22139d51c8a8129e6ed9c2391f7d226eb32'),
  ('ff0b8a8cff784697', '7f8a9cb51f9b131918fcb642bde7c062c1cbed24'),
  ('ff24240b91d77c97', 'f0bc18fb5a18627d161794eb9056a83fe3ba03fd');

DO $hi$
DECLARE
  d        BIGINT;
  r        BIGINT;
  newly    BIGINT;
  base     BIGINT;
  live     BIGINT;
BEGIN
  SELECT COUNT(*) INTO newly FROM _hi282_file f
   WHERE NOT EXISTS (SELECT 1 FROM i18n_keys k WHERE k.key_id = f.key_id)
      OR EXISTS (SELECT 1 FROM i18n_keys k WHERE k.key_id = f.key_id
                   AND k.retired_at IS NOT NULL AND k.source_hash = f.source_hash);
  SELECT COUNT(*) INTO live FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
  d := 2427 - newly - live;
  IF d > 0 THEN
    -- shortfall: re-activate retired stand-ins first, then add new ones
    UPDATE i18n_keys k SET retired_at = NULL, updated_at = NOW()
      FROM (SELECT key_id FROM i18n_keys
             WHERE key_id LIKE 'zzrf8%' AND retired_at IS NOT NULL
             ORDER BY key_id LIMIT d) s
     WHERE k.key_id = s.key_id;
    GET DIAGNOSTICS r = ROW_COUNT;
    d := d - r;
    SELECT COALESCE(MAX(substr(key_id, 6)::bigint), 0) INTO base
      FROM i18n_keys WHERE key_id LIKE 'zzrf8%';
    INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
    SELECT 'zzrf8' || lpad(n::text, 11, '0'), 'client',
           'rf8 stand-in client key ' || n, md5('rf8 stand-in ' || n) || '00000000',
           FALSE, NULL, NULL, NOW()
      FROM generate_series(base + 1, base + d) AS g(n);
  ELSIF d < 0 THEN
    -- surplus: retire live stand-ins only (never a real key)
    UPDATE i18n_keys k SET retired_at = NOW(), updated_at = NOW()
      FROM (SELECT key_id FROM i18n_keys
             WHERE key_id LIKE 'zzrf8%' AND retired_at IS NULL
             ORDER BY key_id DESC LIMIT -d) s
     WHERE k.key_id = s.key_id;
  END IF;
  SELECT COUNT(*) INTO live FROM i18n_keys WHERE namespace = 'client' AND retired_at IS NULL;
  IF live + newly <> 2427 THEN
    RAISE EXCEPTION 'rf8 seed hi 282: % live client keys + % the file adds <> 2427 (surplus of real keys; no stand-ins left to retire)', live, newly;
  END IF;
  RAISE NOTICE 'rf8 seed hi 282: % live client keys now, the file adds %', live, newly;
END $hi$;
COMMIT;
'''

SEEDS['285_clavar_track_count_14.sql'] = r'''-- seed (hm) for backend/sql/285_clavar_track_count_14.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;

-- 281 gate (lines 49-60): exactly one live players row with the artist's steam id.
-- The uuid row above carries a placeholder only if the steam id is held elsewhere,
-- and then that row is the live one; this insert covers the remaining case.
INSERT INTO players (steam_id, display_name)
SELECT '76561198040410653', 'Sid'
WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = '76561198040410653');

-- 281 gate (lines 61-64): the artist_users role row for that steam id.
INSERT INTO artist_users (steam_id, display_name, notes)
SELECT '76561198040410653', 'Sid', 'rehearsal seed'
WHERE NOT EXISTS (SELECT 1 FROM artist_users WHERE steam_id = '76561198040410653');

-- 285 post-check (lines 66-84) needs Clavar la Bala live (catalog_ready TRUE,
-- released_at set), which is migration 281's flip (281 lines 140-155). In the chain
-- 281 has run and this matches no row; on a checkpoint where 281 refused, this
-- applies the same single-row write on the same 279 pre-state guard (the 148
-- trigger stamps released_at).
UPDATE shop_items SET artist_steam_id = '76561198040410653', catalog_ready = TRUE
 WHERE sku = 'music_album_clavar_la_bala' AND kind = 'music_album'
   AND catalog_ready = FALSE AND artist_steam_id IS NULL AND released_at IS NULL
   AND music_track_count = 12;
'''

SEEDS['304_release_straw_hat_florabelle.sql'] = r'''-- rf8 d2 seed (helper hc) for 304_release_straw_hat_florabelle.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 304 guard: two approved rows, rev 1, these scales, offset 0,0, frame_count 1

-- shop row face_detail_straw_hat
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880356, 'face_detail_straw_hat', 'face', 'face_detail_straw_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_straw_hat');

-- approved submission face_detail_straw_hat: rev 1, scale 1.75, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990356, '76561190000000149', 'face_detail_straw_hat', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_straw_hat', 1.75, 0, 0, 1, 1.75, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_straw_hat');

-- shop row face_detail_florabelle
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 880357, 'face_detail_florabelle', 'face', 'face_detail_florabelle', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_florabelle');

-- approved submission face_detail_florabelle: rev 1, scale 1.6, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status)
SELECT 990357, '76561190000000149', 'face_detail_florabelle', 'detail', '\x89504e470d0a1a0a'::bytea, 8, 'approved', 'rf-seed', now(), 'face_detail_florabelle', 1.6, 0, 0, 1, 1.6, 0, 0, 1, 0, 'approved'
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_florabelle');

COMMIT;
'''

SEEDS['321_pc_rank2_legendary.sql'] = r'''-- seed (hm) for backend/sql/321_pc_rank2_legendary.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text),
    ('ef39f993-7ede-4017-901d-bc637dd743d2'::uuid, '76561198983423367'::text, 'Stan'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;

-- 321 gate (lines 1-40 of the code): the NEWEST pc_pool_snapshots row (taken_at DESC,
-- id DESC) has rule >= 3 and a pool_rank 2 member whose rarity is 'legendary'. If
-- the newest snapshot does not already say so, take a newer rule-3 snapshot with
-- ranks 1 and 2 legendary.
DO $hm_321$
DECLARE v_snap integer; v_rule integer; v_band text; v_new integer;
BEGIN
  SELECT id, rule INTO v_snap, v_rule FROM pc_pool_snapshots ORDER BY taken_at DESC, id DESC LIMIT 1;
  SELECT m.rarity INTO v_band FROM pc_pool_members m WHERE m.snapshot_id = v_snap AND m.pool_rank = 2;
  IF v_snap IS NOT NULL AND v_rule >= 3 AND v_band = 'legendary' THEN
    RETURN;
  END IF;
  INSERT INTO pc_pool_snapshots (taken_at, member_count, rule)
  SELECT GREATEST(now(), COALESCE(max(taken_at), now()) + interval '1 second'), 2, 3
    FROM pc_pool_snapshots
  RETURNING id INTO v_new;
  INSERT INTO pc_pool_members (snapshot_id, player_id, pool_rank, rarity)
  VALUES (v_new, 'fbb3d29d-b637-43c0-9787-357c2753e28c', 1, 'legendary'),
         (v_new, 'ef39f993-7ede-4017-901d-bc637dd743d2', 2, 'legendary');
END $hm_321$;
'''

SEEDS['363_revoke_ffa_shutouts_below_finishing_count.sql'] = r'''-- rf8 d2 seed (d2) for 363_revoke_ffa_shutouts_below_finishing_count.sql: fixture rows only, rerun-safe.
-- 363 classifies four targets (lines 84-88) and revokes only when all four are 'pending'
-- (lines 115-121): the holder exists, the award row sits at its pinned id with its
-- (player, key), exactly one 'achievement'/'achievement_prepaid' payment exists, the pinned
-- ledger row (its id, player, key, reason 'achievement', amount = gold) is that payment,
-- and no clawback exists. Earlier seeds (115's players) create both holders, so 363 no
-- longer takes its all-'no_holder' branch. Its #326 guard (line 175) also wants each
-- holder's gold_earned to be at least the gold taken (300 for the first, 900 for the
-- second). Explicit ids are the file's own (award 414/567/568/569, ledger
-- 25287/35699/35700/35701); no sequence value is consumed.
BEGIN;

DO $seed363$
DECLARE
    r RECORD;
BEGIN
    FOR r IN SELECT * FROM (VALUES
        (414, CAST('fbb3d29d-b637-43c0-9787-357c2753e28c' AS uuid), 'ffa_shutout_4', 300, CAST(25287 AS bigint)),
        (567, CAST('ef39f993-7ede-4017-901d-bc637dd743d2' AS uuid), 'ffa_shutout_3', 100, CAST(35699 AS bigint)),
        (568, CAST('ef39f993-7ede-4017-901d-bc637dd743d2' AS uuid), 'ffa_shutout_4', 300, CAST(35700 AS bigint)),
        (569, CAST('ef39f993-7ede-4017-901d-bc637dd743d2' AS uuid), 'ffa_shutout_5', 500, CAST(35701 AS bigint))
    ) AS t(pa_id, player_id, achievement_key, gold, ledger_id)
    LOOP
        -- only where the holder exists (an earlier seed or the chain made it); a
        -- database without the holders keeps 363's no_holder branch
        CONTINUE WHEN NOT EXISTS (SELECT 1 FROM players WHERE id = r.player_id);
        -- the award row at its pinned id
        UPDATE player_achievements SET id = r.pa_id
         WHERE player_id = r.player_id AND achievement_key = r.achievement_key AND id <> r.pa_id
           AND NOT EXISTS (SELECT 1 FROM player_achievements WHERE id = r.pa_id);
        INSERT INTO player_achievements (id, player_id, achievement_key, unlocked_at)
        SELECT r.pa_id, r.player_id, r.achievement_key, TIMESTAMPTZ '2026-09-08 12:00:00+00'
         WHERE NOT EXISTS (SELECT 1 FROM player_achievements
                            WHERE player_id = r.player_id AND achievement_key = r.achievement_key)
           AND NOT EXISTS (SELECT 1 FROM gold_transactions g
                            WHERE g.player_id = r.player_id AND g.reference_id = r.achievement_key
                              AND g.reason = 'achievement_revoked');
        -- its one payment, the pinned ledger row
        INSERT INTO gold_transactions (id, player_id, amount, reason, reference_id)
        SELECT r.ledger_id, r.player_id, r.gold, 'achievement', r.achievement_key
         WHERE NOT EXISTS (SELECT 1 FROM gold_transactions g
                            WHERE g.player_id = r.player_id AND g.reference_id = r.achievement_key
                              AND g.reason IN ('achievement', 'achievement_prepaid', 'achievement_revoked'));
    END LOOP;
    -- line 175: gold_earned at least the gold taken from each holder
    UPDATE players p SET gold_earned = s.owed
      FROM (VALUES (CAST('fbb3d29d-b637-43c0-9787-357c2753e28c' AS uuid), 300),
                   (CAST('ef39f993-7ede-4017-901d-bc637dd743d2' AS uuid), 900)) AS s(player_id, owed)
     WHERE p.id = s.player_id AND COALESCE(p.gold_earned, 0) < s.owed
       AND NOT EXISTS (SELECT 1 FROM gold_transactions g
                        WHERE g.player_id = s.player_id AND g.reason = 'achievement_revoked'
                          AND g.reference_id LIKE 'ffa_shutout_%');
END
$seed363$;

COMMIT;
'''

SEEDS['366_title_refunds_voidshot_kingslayer.sql'] = r'''-- seed (hm) for backend/sql/366_title_refunds_voidshot_kingslayer.sql: fixture rows only, idempotent.
-- 366's census (code lines 10-11): title_voidshot 0 holders; title_regicide exactly
-- 1 paying holder at 3000g with one 'purchase' ledger row debiting 3000, and that
-- holder's gold_spent >= 3000 (the refund returns it). The file does not name the
-- holder, so a fixture player stands in. Only written while title_regicide has no
-- holder, no purchase row and no refund row (a re-run, or a chain where 366 has
-- applied, writes nothing).
DO $hm_366$
DECLARE v_item bigint; v_pid uuid;
BEGIN
  SELECT id INTO v_item FROM shop_items WHERE sku = 'title_regicide';
  IF v_item IS NULL
     OR EXISTS (SELECT 1 FROM player_items WHERE item_id = v_item)
     OR EXISTS (SELECT 1 FROM gold_transactions WHERE reference_id = 'title_regicide'
                 AND reason IN ('purchase', 'title_refunded')) THEN
    RETURN;
  END IF;
  INSERT INTO players (steam_id, display_name, gold_earned, gold_spent)
  SELECT '76561100000000366', 'seed-kingslayer', 3000, 3000
  WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = '76561100000000366');
  SELECT id INTO v_pid FROM players WHERE steam_id = '76561100000000366';
  UPDATE players SET gold_earned = gold_earned + 3000, gold_spent = gold_spent + 3000
   WHERE id = v_pid AND gold_spent < 3000;
  INSERT INTO player_items (player_id, item_id, purchase_price) VALUES (v_pid, v_item, 3000);
  INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
  VALUES (v_pid, -3000, 'purchase', 'title_regicide');
END $hm_366$;
'''

SEEDS['376_i18n_337_demonic_proposals.sql'] = r'''-- rf8 d2 seed (tag hi) for 376_i18n_337_demonic_proposals.sql: i18n_keys fixtures.
-- The file's INSERT joins i18n_proposals onto LIVE i18n_keys rows with the SAME
-- source_hash, and its DO-block coverage check RAISEs when a seed pair did not land.
-- Production gets these key rows from tools/i18n_sync_keys.py; here they are
-- derived from the file itself: every (key_id, source_hash) in its _seed376 pairs.
-- namespace: 'game' when key_id = sha1('game\0' + Table/KEY)[:16] over
-- tools/game_strings.json (or the file lists it as a game key), else 'client'.
-- msgctxt: the English whose sha1 equals the file's source_hash (found in
-- tools/i18n_source.json at HEAD or any earlier revision, tools/game_strings.json,
-- or the quoted text of backend/sql),
-- otherwise a labelled placeholder. Game keys carry a non-empty context.
-- 1 keys: 1 client with English, 0 game with English, 0 placeholder msgctxt.
-- Re-runnable: the upsert only touches a row that is retired, carries another hash,
-- or lacks context the file reads.
BEGIN;
INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, NOW()
  FROM (VALUES
  ('a3ba08a25171bc89', 'client', $s376$The purple the Demonic Pact card is drawn in.$s376$, '50a9d67312296bed3f5bcb9316939538b5ab0e4d', FALSE, NULL)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
ON CONFLICT (key_id) DO UPDATE
   SET source_hash = EXCLUDED.source_hash,
       msgctxt     = EXCLUDED.msgctxt,
       context     = COALESCE(NULLIF(i18n_keys.context, ''), EXCLUDED.context),
       retired_at  = NULL,
       updated_at  = NOW()
 WHERE i18n_keys.retired_at IS NOT NULL
    OR i18n_keys.source_hash <> EXCLUDED.source_hash
    OR (EXCLUDED.context IS NOT NULL AND COALESCE(i18n_keys.context, '') = '');
COMMIT;
'''

SEEDS['387_ffa_rating_restore_2f60481d.sql'] = r'''-- seed (hm) for backend/sql/387_ffa_rating_restore_2f60481d.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;


-- The voided game: ffa_matches 2f60481d (ranked, not invalidated, ended_at as 388
-- line 20 measures it) and the seat's ffa_match_players row in the measured
-- pre-image (387 lines 74-83 / 388 header: rating_before 2087.094158271577,
-- rating_after 2024.3941582715768, change -62.7, left_early voluntary, not absent,
-- 1 game point at leave, points_total 1, rounds_won 0, placement 4). Inserted only
-- when absent; an existing (e.g. already zeroed) row is kept.
INSERT INTO ffa_matches (id, photon_room_id, player_count, is_ranked, ended_at, created_at, game_number)
SELECT '2f60481d-ea6c-40e4-bda2-0ed47af8e990', 'seed_hm_ffa_2f60481d', 4, TRUE,
       TIMESTAMPTZ '2026-10-18 04:59:48.93124+00', TIMESTAMPTZ '2026-10-18 04:59:48.93124+00', 1
WHERE NOT EXISTS (SELECT 1 FROM ffa_matches WHERE id = '2f60481d-ea6c-40e4-bda2-0ed47af8e990');

INSERT INTO ffa_match_players (match_id, player_id, placement, rounds_won, points_total,
                               left_early, left_early_involuntary, absent, game_points_at_leave,
                               rating_before, rating_after, rating_change)
SELECT '2f60481d-ea6c-40e4-bda2-0ed47af8e990', 'fbb3d29d-b637-43c0-9787-357c2753e28c', 4, 0, 1,
       TRUE, FALSE, FALSE, 1,
       CAST(2087.094158271577 AS double precision), CAST(2024.3941582715768 AS double precision),
       CAST(-62.7 AS double precision)
WHERE NOT EXISTS (SELECT 1 FROM ffa_match_players
                   WHERE match_id = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
                     AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c');

-- 387 is_pre (lines 99-102): the seat's glicko_ratings_ffa row at the measured
-- pre-image (rating 2024.405412230633, peak 2087.094158271577, updated_at
-- 2026-10-18 04:59:48.803927+00). Written only while the match row above is still
-- in its pre-image (387 not applied yet); an earlier file's or seed's row for the
-- seat is moved to that pre-image, a missing one inserted.
DO $hm_387$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM ffa_match_players
                  WHERE match_id = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
                    AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
                    AND rating_after IS NOT DISTINCT FROM CAST(2024.3941582715768 AS double precision)
                    AND rating_change IS NOT DISTINCT FROM CAST(-62.7 AS double precision)) THEN
    RETURN;
  END IF;
  INSERT INTO glicko_ratings_ffa (player_id, rating, peak_rating, updated_at)
  SELECT 'fbb3d29d-b637-43c0-9787-357c2753e28c', CAST(2024.405412230633 AS double precision),
         CAST(2087.094158271577 AS double precision), TIMESTAMPTZ '2026-10-18 04:59:48.803927+00'
  WHERE NOT EXISTS (SELECT 1 FROM glicko_ratings_ffa WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c');
  UPDATE glicko_ratings_ffa
     SET rating = CAST(2024.405412230633 AS double precision),
         peak_rating = CAST(2087.094158271577 AS double precision),
         updated_at = TIMESTAMPTZ '2026-10-18 04:59:48.803927+00'
   WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';
END $hm_387$;
'''

SEEDS['388_ffa_rating_restore_2f60481d.sql'] = r'''-- seed (hm) for backend/sql/388_ffa_rating_restore_2f60481d.sql: fixture rows only, idempotent.
-- Players the file names (pid = production uuid the file uses, steam = production
-- steam id where a migration names it, else NULL). A row whose uuid exists already
-- is kept; it adopts the real steam id only if it still carries a seed placeholder
-- (7656110 prefix) and the real id is free. A new uuid gets the real steam id if
-- free, else a deterministic placeholder. pid NULL = the file looks the player up
-- by steam id only.
DO $hm_players$
DECLARE v record; v_syn text;
BEGIN
  FOR v IN SELECT * FROM (VALUES
    ('fbb3d29d-b637-43c0-9787-357c2753e28c'::uuid, '76561198040410653'::text, 'Sid'::text)
  ) AS t(pid, steam, name) LOOP
    IF v.pid IS NULL THEN
      INSERT INTO players (steam_id, display_name) SELECT v.steam, v.name
       WHERE NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      CONTINUE;
    END IF;
    v_syn := '7656110' || lpad(((('x' || substr(replace(v.pid::text, '-', ''), 1, 8))::bit(32)::bigint) % 10000000000)::text, 10, '0');
    IF EXISTS (SELECT 1 FROM players WHERE id = v.pid) THEN
      IF v.steam IS NOT NULL THEN
        UPDATE players SET steam_id = v.steam
         WHERE id = v.pid AND steam_id LIKE '7656110%'
           AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam);
      END IF;
    ELSE
      INSERT INTO players (id, steam_id, display_name)
      VALUES (v.pid,
              CASE WHEN v.steam IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM players WHERE steam_id = v.steam)
                   THEN v.steam ELSE v_syn END,
              v.name);
    END IF;
  END LOOP;
END $hm_players$;


-- The voided game: ffa_matches 2f60481d (ranked, not invalidated, ended_at as 388
-- line 20 measures it) and the seat's ffa_match_players row in the measured
-- pre-image (387 lines 74-83 / 388 header: rating_before 2087.094158271577,
-- rating_after 2024.3941582715768, change -62.7, left_early voluntary, not absent,
-- 1 game point at leave, points_total 1, rounds_won 0, placement 4). Inserted only
-- when absent; an existing (e.g. already zeroed) row is kept.
INSERT INTO ffa_matches (id, photon_room_id, player_count, is_ranked, ended_at, created_at, game_number)
SELECT '2f60481d-ea6c-40e4-bda2-0ed47af8e990', 'seed_hm_ffa_2f60481d', 4, TRUE,
       TIMESTAMPTZ '2026-10-18 04:59:48.93124+00', TIMESTAMPTZ '2026-10-18 04:59:48.93124+00', 1
WHERE NOT EXISTS (SELECT 1 FROM ffa_matches WHERE id = '2f60481d-ea6c-40e4-bda2-0ed47af8e990');

INSERT INTO ffa_match_players (match_id, player_id, placement, rounds_won, points_total,
                               left_early, left_early_involuntary, absent, game_points_at_leave,
                               rating_before, rating_after, rating_change)
SELECT '2f60481d-ea6c-40e4-bda2-0ed47af8e990', 'fbb3d29d-b637-43c0-9787-357c2753e28c', 4, 0, 1,
       TRUE, FALSE, FALSE, 1,
       CAST(2087.094158271577 AS double precision), CAST(2024.3941582715768 AS double precision),
       CAST(-62.7 AS double precision)
WHERE NOT EXISTS (SELECT 1 FROM ffa_match_players
                   WHERE match_id = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
                     AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c');

-- 388 lines 82-104: the first rated row after the voided game is match 6e8c2f1c,
-- ended_at 2026-10-19 04:30:37.00626+00, rating_before 2024.405412230633, the only
-- rated row in [voided ended_at, that ended_at] (header lines 26-29).
INSERT INTO ffa_matches (id, photon_room_id, player_count, is_ranked, ended_at, created_at, game_number)
SELECT '6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d', 'seed_hm_ffa_6e8c2f1c', 4, TRUE,
       TIMESTAMPTZ '2026-10-19 04:30:37.00626+00', TIMESTAMPTZ '2026-10-19 04:30:37.00626+00', 1
WHERE NOT EXISTS (SELECT 1 FROM ffa_matches WHERE id = '6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d');

INSERT INTO ffa_match_players (match_id, player_id, placement, rounds_won, points_total,
                               rating_before, rating_after, rating_change)
SELECT '6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d', 'fbb3d29d-b637-43c0-9787-357c2753e28c', 1, 5, 5,
       CAST(2024.405412230633 AS double precision), CAST(2047.068334188351 AS double precision),
       CAST(22.7 AS double precision)
WHERE NOT EXISTS (SELECT 1 FROM ffa_match_players
                   WHERE match_id = '6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d'
                     AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c');

-- 388 pre-image of the rating row (header lines 14-17: rating 2047.068334188351,
-- peak 2087.094158271577, updated_at 2026-10-19 06:03:20.051746+00), written only
-- while the voided match row is still in its pre-image. Once 387 has zeroed it
-- (the chain), 388 takes its already-applied branch and the row is left alone.
DO $hm_388$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM ffa_match_players
                  WHERE match_id = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
                    AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
                    AND rating_after IS NOT DISTINCT FROM CAST(2024.3941582715768 AS double precision)
                    AND rating_change IS NOT DISTINCT FROM CAST(-62.7 AS double precision)) THEN
    RETURN;
  END IF;
  INSERT INTO glicko_ratings_ffa (player_id, rating, peak_rating, updated_at)
  SELECT 'fbb3d29d-b637-43c0-9787-357c2753e28c', CAST(2047.068334188351 AS double precision),
         CAST(2087.094158271577 AS double precision), TIMESTAMPTZ '2026-10-19 06:03:20.051746+00'
  WHERE NOT EXISTS (SELECT 1 FROM glicko_ratings_ffa WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c');
  UPDATE glicko_ratings_ffa
     SET rating = CAST(2047.068334188351 AS double precision),
         peak_rating = CAST(2087.094158271577 AS double precision),
         updated_at = TIMESTAMPTZ '2026-10-19 06:03:20.051746+00'
   WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c';
END $hm_388$;
'''

SEEDS['398_release_five_faces_v1410.sql'] = r'''-- rf8 d2 seed (helper hc) for 398_release_five_faces_v1410.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 398 reads its rows BY ID (expected array, lines ~95-100): submission ids 69-73 and
-- shop_items ids 359, 358, 569, 570, 571. Explicit ids, as the gate demands.
-- If an id is held by a different row (chain rows take ids by sequence), that row is
-- moved to 870000+id first (shop_items) / 970000+id (cosmetic_submissions); the
-- moved rows keep every other column. The stored art must be the bundled PNG
-- (png_bytes + md5 checked): png_data below is the exact bytes of
-- plugin/cosmetics/detail_<name>.png from the repo (md5 verified at generation).

-- face_detail_gold_headband: shop id 359, submission id 69, scale 1.45, 24429 bytes md5 4242409ce643ec451420cf1976688506
UPDATE shop_items SET id = 870359 WHERE id = 359 AND sku <> 'face_detail_gold_headband';
UPDATE shop_items SET id = 359 WHERE sku = 'face_detail_gold_headband' AND id <> 359;
UPDATE cosmetic_submissions SET id = 970069
 WHERE id = 69 AND shop_sku IS DISTINCT FROM 'face_detail_gold_headband';
UPDATE cosmetic_submissions SET id = 69 WHERE shop_sku = 'face_detail_gold_headband' AND id <> 69;

-- shop row face_detail_gold_headband
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 359, 'face_detail_gold_headband', 'face', 'face_detail_gold_headband', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_gold_headband');

-- approved submission face_detail_gold_headband: rev 1, scale 1.45, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status, frame_count)
SELECT 69, '76561190000000149', 'face_detail_gold_headband', 'detail', @FILE(plugin/cosmetics/detail_gold_headband.png;4242409ce643ec451420cf1976688506)@::bytea, 24429, 'approved', 'rf-seed', now(), 'face_detail_gold_headband', 1.45, 0, 0, 1, 1.45, 0, 0, 1, 0, 'approved', 1
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_gold_headband');

-- face_detail_orbit: shop id 358, submission id 70, scale 1.6, 34839 bytes md5 412974a31b7569bd2a04275293b30787
UPDATE shop_items SET id = 870358 WHERE id = 358 AND sku <> 'face_detail_orbit';
UPDATE shop_items SET id = 358 WHERE sku = 'face_detail_orbit' AND id <> 358;
UPDATE cosmetic_submissions SET id = 970070
 WHERE id = 70 AND shop_sku IS DISTINCT FROM 'face_detail_orbit';
UPDATE cosmetic_submissions SET id = 70 WHERE shop_sku = 'face_detail_orbit' AND id <> 70;

-- shop row face_detail_orbit
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 358, 'face_detail_orbit', 'face', 'face_detail_orbit', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_orbit');

-- approved submission face_detail_orbit: rev 1, scale 1.6, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status, frame_count)
SELECT 70, '76561190000000149', 'face_detail_orbit', 'detail', @FILE(plugin/cosmetics/detail_orbit.png;412974a31b7569bd2a04275293b30787)@::bytea, 34839, 'approved', 'rf-seed', now(), 'face_detail_orbit', 1.6, 0, 0, 1, 1.6, 0, 0, 1, 0, 'approved', 1
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_orbit');

-- face_detail_pumpking_hat: shop id 569, submission id 71, scale 1.4, 51759 bytes md5 06c4235ba87bf61cdb613169eee2c86c
UPDATE shop_items SET id = 870569 WHERE id = 569 AND sku <> 'face_detail_pumpking_hat';
UPDATE shop_items SET id = 569 WHERE sku = 'face_detail_pumpking_hat' AND id <> 569;
UPDATE cosmetic_submissions SET id = 970071
 WHERE id = 71 AND shop_sku IS DISTINCT FROM 'face_detail_pumpking_hat';
UPDATE cosmetic_submissions SET id = 71 WHERE shop_sku = 'face_detail_pumpking_hat' AND id <> 71;

-- shop row face_detail_pumpking_hat
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 569, 'face_detail_pumpking_hat', 'face', 'face_detail_pumpking_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_pumpking_hat');

-- approved submission face_detail_pumpking_hat: rev 1, scale 1.4, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status, frame_count)
SELECT 71, '76561190000000149', 'face_detail_pumpking_hat', 'detail', @FILE(plugin/cosmetics/detail_pumpking_hat.png;06c4235ba87bf61cdb613169eee2c86c)@::bytea, 51759, 'approved', 'rf-seed', now(), 'face_detail_pumpking_hat', 1.4, 0, 0, 1, 1.4, 0, 0, 1, 0, 'approved', 1
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_pumpking_hat');

-- face_detail_leafy_mushroom: shop id 570, submission id 72, scale 1.3, 23257 bytes md5 9e9b0421902c33077ca42c8bcea28882
UPDATE shop_items SET id = 870570 WHERE id = 570 AND sku <> 'face_detail_leafy_mushroom';
UPDATE shop_items SET id = 570 WHERE sku = 'face_detail_leafy_mushroom' AND id <> 570;
UPDATE cosmetic_submissions SET id = 970072
 WHERE id = 72 AND shop_sku IS DISTINCT FROM 'face_detail_leafy_mushroom';
UPDATE cosmetic_submissions SET id = 72 WHERE shop_sku = 'face_detail_leafy_mushroom' AND id <> 72;

-- shop row face_detail_leafy_mushroom
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 570, 'face_detail_leafy_mushroom', 'face', 'face_detail_leafy_mushroom', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_leafy_mushroom');

-- approved submission face_detail_leafy_mushroom: rev 1, scale 1.3, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status, frame_count)
SELECT 72, '76561190000000149', 'face_detail_leafy_mushroom', 'detail', @FILE(plugin/cosmetics/detail_leafy_mushroom.png;9e9b0421902c33077ca42c8bcea28882)@::bytea, 23257, 'approved', 'rf-seed', now(), 'face_detail_leafy_mushroom', 1.3, 0, 0, 1, 1.3, 0, 0, 1, 0, 'approved', 1
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_leafy_mushroom');

-- face_detail_red_scarf: shop id 571, submission id 73, scale 1.6, 21241 bytes md5 6d43a388354876aabaf3808582832fbd
UPDATE shop_items SET id = 870571 WHERE id = 571 AND sku <> 'face_detail_red_scarf';
UPDATE shop_items SET id = 571 WHERE sku = 'face_detail_red_scarf' AND id <> 571;
UPDATE cosmetic_submissions SET id = 970073
 WHERE id = 73 AND shop_sku IS DISTINCT FROM 'face_detail_red_scarf';
UPDATE cosmetic_submissions SET id = 73 WHERE shop_sku = 'face_detail_red_scarf' AND id <> 73;

-- shop row face_detail_red_scarf
INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
SELECT 571, 'face_detail_red_scarf', 'face', 'face_detail_red_scarf', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 500, '76561190000000149', -1
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'face_detail_red_scarf');

-- approved submission face_detail_red_scarf: rev 1, scale 1.6, offset (0,0), published 0
INSERT INTO cosmetic_submissions (id, artist_steam_id, name, slot, png_data, png_bytes, status, reviewed_by, reviewed_at, shop_sku, render_scale, render_offset_x, render_offset_y, placement_revision, approved_render_scale, approved_render_offset_x, approved_render_offset_y, approved_placement_revision, published_placement_revision, placement_status, frame_count)
SELECT 73, '76561190000000149', 'face_detail_red_scarf', 'detail', @FILE(plugin/cosmetics/detail_red_scarf.png;6d43a388354876aabaf3808582832fbd)@::bytea, 21241, 'approved', 'rf-seed', now(), 'face_detail_red_scarf', 1.6, 0, 0, 1, 1.6, 0, 0, 1, 0, 'approved', 1
WHERE NOT EXISTS (SELECT 1 FROM cosmetic_submissions WHERE shop_sku = 'face_detail_red_scarf');

COMMIT;
'''

SEEDS['399_shop_face_descriptions.sql'] = r'''-- rf8 d2 seed (helper hc) for 399_shop_face_descriptions.sql: fixture rows only, rerun-safe.
-- Fixture artist 76561190000000149; fixture ids: shop_items 880000+n, cosmetic_submissions
-- 990000+n (outside both sequences' reach; no sequence value consumed).
BEGIN;

INSERT INTO artist_users (steam_id, display_name, notes)
VALUES ('76561190000000149', 'rf seed artist', 'rehearsal fixture')
ON CONFLICT (steam_id) DO NOTHING;

-- 399 checks, per expected row (lines ~70-85), that shop_items id N exists, holds
-- exactly that sku, and is kind face (its production ids). In this chain those ids
-- are held by other items that took them by sequence (map colors 250-258, name tags
-- 259-260/267-268, trails 269-271, title_ladder_eagle_3 at 329), and the face rows,
-- when present, sit at the seeds' fixture ids. For each expected (id, sku):
--   1. a row at that id holding a DIFFERENT sku is moved to id 870000+N (only the
--      id changes; sku and every other column are kept);
--   2. the face row, if it exists at another id, is moved to id N;
--   3. otherwise the face row is inserted at id N (unpublished, placeholder text:
--      399 leaves such a row alone, which its post-check accepts).
-- 399's description rewrite itself is not pre-applied.
DO $seed$
DECLARE
    r RECORD;
BEGIN
    FOR r IN SELECT * FROM (VALUES
        (250, 'face_detail_spooky_head_bouncers', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (251, 'face_detail_ballooniphones', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (252, 'face_detail_soda_helm', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (253, 'face_detail_brain_cane', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (254, 'face_mouth_casi_s_mouth', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (255, 'face_eyes_casicorn_s_eyes', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (256, 'face_detail_little_pink_buddy', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (257, 'face_detail_sniper_medal', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (258, 'face_detail_spilled_icecream', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (259, 'face_detail_magical_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (260, 'face_detail_twisted_topper', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (267, 'face_eyes_poison_s_eyes', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (268, 'face_mouth_poison_s_mouth', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (269, 'face_detail_poison_s_weeping', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (270, 'face_detail_seasonal_spring', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (271, 'face_eyes_nuclear_glasses', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (329, 'face_detail_well_wraped_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (356, 'face_detail_straw_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.'),
        (357, 'face_detail_florabelle', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.')
    ) AS v(id, sku, ph) LOOP
        UPDATE shop_items SET id = 870000 + r.id WHERE id = r.id AND sku <> r.sku;
        UPDATE shop_items SET id = r.id WHERE sku = r.sku AND id <> r.id;
        INSERT INTO shop_items (id, sku, kind, name, description, price, artist_steam_id, stock_limit)
        SELECT r.id, r.sku, 'face', r.sku, r.ph, 500, '76561190000000149', -1
        WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = r.sku);
    END LOOP;
END $seed$;

COMMIT;
'''

SEEDS['rollback_387_ffa_rating_restore_2f60481d.sql'] = r'''-- rf8 d2 seed (d2) for rollback_387_ffa_rating_restore_2f60481d.sql: fixture rows only, rerun-safe.
-- rollback_387 refuses while a later rated FFA row of the seat exists (lines 66-74, 88-90):
-- its pre-image literals only apply to the state right after 387. In the chain the later
-- row is the FIXTURE match 6e8c2f1c that the 388 seed inserted (photon_room_id
-- 'seed_hm_ffa_6e8c2f1c'); rollback_388 has already run (newest first). This removes
-- exactly that fixture's rows, keyed on the fixture's own room marker, so the rollback's
-- apply half runs and is measured. A non-fixture row is never touched.
BEGIN;
DELETE FROM ffa_match_players
 WHERE match_id = '6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d'
   AND EXISTS (SELECT 1 FROM ffa_matches
                WHERE id = '6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d'
                  AND photon_room_id = 'seed_hm_ffa_6e8c2f1c');
DELETE FROM ffa_matches
 WHERE id = '6e8c2f1c-e6df-46e9-bce9-3e31cc5fec7d'
   AND photon_room_id = 'seed_hm_ffa_6e8c2f1c';
-- rollback_387's apply half needs 387's POST-image (lines 115-117: rating and the seat
-- row's rating_after at m_before, rating_change 0). In the chain 388 ran after 387 and
-- rollback_388 (applied first, newest first) restored 388's pre-image instead (rating
-- 2024.405412230633 with the later match's stamp, the seat row at m_after/m_change),
-- which rollback_387 by design neither applies to nor treats as done. The two updates
-- below put exactly those FIXTURE rows (the 387 seed's seat and rating rows) into the 387
-- post-image, as if 388 had never run, keyed on the exact values rollback_388 leaves, so
-- any other state is left alone and rollback_387 decides on it itself.
UPDATE ffa_match_players
   SET rating_after = CAST(2087.094158271577 AS double precision),
       rating_change = CAST(0 AS double precision)
 WHERE match_id = '2f60481d-ea6c-40e4-bda2-0ed47af8e990'
   AND player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
   AND rating_before IS NOT DISTINCT FROM CAST(2087.094158271577 AS double precision)
   AND rating_after  IS NOT DISTINCT FROM CAST(2024.3941582715768 AS double precision)
   AND rating_change IS NOT DISTINCT FROM CAST(-62.7 AS double precision);
UPDATE glicko_ratings_ffa
   SET rating = CAST(2087.094158271577 AS double precision)
 WHERE player_id = 'fbb3d29d-b637-43c0-9787-357c2753e28c'
   AND rating      IS NOT DISTINCT FROM CAST(2024.405412230633 AS double precision)
   AND peak_rating IS NOT DISTINCT FROM CAST(2087.094158271577 AS double precision)
   AND updated_at  IS DISTINCT FROM TIMESTAMPTZ '2026-10-18 04:59:48.803927+00';
COMMIT;
'''
