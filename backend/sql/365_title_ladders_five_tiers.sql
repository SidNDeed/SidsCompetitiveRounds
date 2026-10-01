-- 365_title_ladders_five_tiers.sql
--
-- Title ladders, five tiers each (board row 29; proposal v2 with its five
-- decision points taken by default). Rewrites the catalogue migration 331
-- created: 32 ladders instead of 8, exactly five tiers each (tier 1 the entry
-- rung, on sale; tiers 2-5 earned, granted only), thresholds per ladder KIND,
-- and every ladder counted in ranked GAMES instead of series.
--
-- GENERATED from backend/api/title_ladders.py's LADDERS structure. Do not
-- hand-edit the row lists below: backend/tests/test_title_ladders.py
-- re-derives every row here from that module and fails on any drift.
--
-- WHAT THIS FILE DOES, on its FIRST application only:
--   0. PREFLIGHT. Refuses (RAISE, nothing written) unless nobody holds or
--      wears a rung this file deletes, and title_ladder_progress and
--      title_ladder_credits are empty. Census on the production primary,
--      2026-10-01 05:17Z (read-only): title_ladders 48 rows, progress 0,
--      credits 0, rung inventory rows 0, players wearing a rung 0. The empty
--      progress table is what makes the series-to-games unit change free:
--      no stored count is in the old unit.
--   1. Adds title_ladder_progress.streak (the current run of consecutive
--      ranked 1v1 wins, for the Apex ladder; its best run is `games`) and
--      title_ladder_progress.streak_at (the SERVER's clock when the run was
--      last written; informational, no decision reads it -- the run follows
--      the order in which the server claims each game under the player's row
--      lock; NULL until the first one). Makes title_ladder_credits.line
--      nullable: every participant of every ranked game is claimed, keyed
--      (player, game id), and the line is NULL when no ladder rung was worn.
--   2. Deletes the nine 331 rungs the new catalogue does not have (rat's two
--      tier-4 rungs and every tier 6); their title_ladders rows go with them
--      (ON DELETE CASCADE).
--   3. Upserts every rung's shop_items row. Existing shop titles that become
--      rungs keep their sku, rarity, colour and description; their name is
--      the tier name the proposal gives (Tracker -> Homing User, ...), a
--      tier above 1 moves to the granted-only pool at price 0, and a tier 1
--      keeps the price its buyers paid. Every tier-1 rung is catalog_ready
--      TRUE: on sale.
--   4. Upserts every rung's title_ladders row (line, tier, threshold).
-- On a RE-RUN (the streak column already exists) none of 1-4 runs: the file
-- applies once, and a re-run never rewrites a row an operator edited since.
-- The post-checks run on every application and assert the final state.
--
-- shop_items TRIGGERS. gate_new_face_shop_item acts on kind = 'face' only.
-- stamp_shop_item_catalog_release fires on catalog_ready FALSE -> TRUE, which
-- step 3 does for the eight animal entry rungs 331 held off sale: it stamps
-- released_at (wanted) and has no placement row to check for a title.
--
-- DEPLOY ORDER (#477): THIS FILE FIRST, alone in its own commit, then the api
-- that reads the new catalogue. In the window between the two, the old api
-- keeps crediting the old animal skus per series: a tier-1 bought in that
-- window is credited by the old rule until the new build lands. It cannot
-- move a match result, a rating or gold.
--
-- psql -f does not wrap a file in a transaction (#340): BEGIN/COMMIT below.

BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TEMP TABLE _m365_state ON COMMIT DROP AS
SELECT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'title_ladder_progress'
                  AND column_name = 'streak') AS already_applied;

DO $m365$
DECLARE
    v_applied  BOOLEAN;
    n_hold     INTEGER;
    n_wear     INTEGER;
    n_prog     INTEGER;
    n_cred     INTEGER;
BEGIN
    SELECT already_applied INTO v_applied FROM _m365_state;
    IF v_applied THEN
        RAISE NOTICE 'title ladders 365: already applied; nothing written, post-checks follow';
        RETURN;
    END IF;

    -- 0. Preflight.
    SELECT count(*) INTO n_hold
      FROM player_items pi JOIN shop_items si ON si.id = pi.item_id
     WHERE si.sku IN ('title_ladder_rat_4_king', 'title_ladder_rat_4_queen', 'title_ladder_cat_6', 'title_ladder_dog_6', 'title_ladder_turtle_6', 'title_ladder_rabbit_6', 'title_ladder_bear_6', 'title_ladder_eagle_6', 'title_ladder_shark_6');
    SELECT count(*) INTO n_wear
      FROM players p JOIN shop_items si ON si.id = p.active_title_id
     WHERE si.sku IN ('title_ladder_rat_4_king', 'title_ladder_rat_4_queen', 'title_ladder_cat_6', 'title_ladder_dog_6', 'title_ladder_turtle_6', 'title_ladder_rabbit_6', 'title_ladder_bear_6', 'title_ladder_eagle_6', 'title_ladder_shark_6');
    SELECT count(*) INTO n_prog FROM title_ladder_progress;
    SELECT count(*) INTO n_cred FROM title_ladder_credits;
    RAISE NOTICE 'title ladders 365 preflight: holders of a dropped rung %, wearers %, progress rows %, credit rows %',
        n_hold, n_wear, n_prog, n_cred;
    IF n_hold <> 0 OR n_wear <> 0 OR n_prog <> 0 OR n_cred <> 0 THEN
        RAISE EXCEPTION 'title ladders 365: refused -- the census found 0 holders, 0 wearers, 0 progress and 0 credit rows; this database has %, %, %, %. Re-census before rewriting the catalogue',
            n_hold, n_wear, n_prog, n_cred;
    END IF;

    -- 1. The Apex run.
    ALTER TABLE title_ladder_progress
        ADD COLUMN IF NOT EXISTS streak INTEGER NOT NULL DEFAULT 0 CHECK (streak >= 0),
        ADD COLUMN IF NOT EXISTS streak_at TIMESTAMPTZ DEFAULT NULL;
    ALTER TABLE title_ladder_credits ALTER COLUMN line DROP NOT NULL;

    COMMENT ON TABLE title_ladder_credits IS
        'One row per player per ranked GAME, claimed for every participant whatever they wear (migration 365): line is the ladder the worn rung belongs to, NULL when none. The PK (player_id, reference_id) is the unit and the double-credit gate: every caller passes the game id (1v1 matches.id, 2v2 team_matches.id, the FFA match id), so a re-reported game changes nothing, whatever is worn at the replay. Rows written before 365 (none existed in production) were keyed on a series id.';

    -- 2. The rungs the new catalogue does not have.
    DELETE FROM shop_items WHERE sku IN ('title_ladder_rat_4_king', 'title_ladder_rat_4_queen', 'title_ladder_cat_6', 'title_ladder_dog_6', 'title_ladder_turtle_6', 'title_ladder_rabbit_6', 'title_ladder_bear_6', 'title_ladder_eagle_6', 'title_ladder_shark_6');

    -- 3. Every rung's shop row.
    INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, catalog_ready, preview_color) VALUES
        ('title_ladder_rat_1', 'title', 'Baby Mouse', 'Wear it and play ranked games', 1000, 'rare', NULL, TRUE, '#9AA0A6'),
        ('title_ladder_rat_2', 'title', 'Mouse', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#B6BDC6'),
        ('title_ladder_rat_3', 'title', 'Rat', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#A88CE0'),
        ('title_ladder_rat_4', 'title', 'Rat Lord', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#E0B33A'),
        ('title_ladder_rat_5', 'title', 'CAPYBARA', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#FFE066'),
        ('title_ladder_cat_1', 'title', 'Stray', 'Wear it and play ranked games', 1000, 'rare', NULL, TRUE, '#F2C1A0'),
        ('title_ladder_cat_2', 'title', 'Prowler', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#E8A87C'),
        ('title_ladder_cat_3', 'title', 'Alley King', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#C97B4A'),
        ('title_ladder_cat_4', 'title', 'Sabertooth', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#B25E2E'),
        ('title_ladder_cat_5', 'title', 'Sekhmet', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#E5A83B'),
        ('title_ladder_dog_1', 'title', 'Pup', 'Wear it and play ranked games', 1000, 'rare', NULL, TRUE, '#C7A87B'),
        ('title_ladder_dog_2', 'title', 'Dog', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#B08D5A'),
        ('title_ladder_dog_3', 'title', 'Hound', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#98703C'),
        ('title_ladder_dog_4', 'title', 'Hellhound', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#D4913A'),
        ('title_ladder_dog_5', 'title', 'Cerberus', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#E9AE45'),
        ('title_ladder_turtle_1', 'title', 'Hatchling', 'Wear it and play ranked games', 1000, 'rare', NULL, TRUE, '#8FBF9F'),
        ('title_ladder_turtle_2', 'title', 'Turtle', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#6FA882'),
        ('title_ladder_turtle_3', 'title', 'Snapper', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#4E8C66'),
        ('title_ladder_turtle_4', 'title', 'Leatherback', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#3F7A57'),
        ('title_ladder_turtle_5', 'title', 'World Turtle', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#6BC49A'),
        ('title_ladder_rabbit_1', 'title', 'Bunny', 'Wear it and play ranked games', 1000, 'rare', NULL, TRUE, '#F3C6D6'),
        ('title_ladder_rabbit_2', 'title', 'Rabbit', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#E3A0BC'),
        ('title_ladder_rabbit_3', 'title', 'Jackrabbit', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#CE7A9E'),
        ('title_ladder_rabbit_4', 'title', 'Jackalope', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#B85C86'),
        ('title_ladder_rabbit_5', 'title', 'Moon Rabbit', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#C79BF0'),
        ('title_ladder_bear_1', 'title', 'Cub', 'Wear it and play ranked games', 1000, 'rare', NULL, TRUE, '#C59A6B'),
        ('title_ladder_bear_2', 'title', 'Bear', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#A87A4E'),
        ('title_ladder_bear_3', 'title', 'Grizzly', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#8A5C35'),
        ('title_ladder_bear_4', 'title', 'Kodiak', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#6F4526'),
        ('title_ladder_bear_5', 'title', 'Ursa Major', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#D9A85C'),
        ('title_ladder_eagle_1', 'title', 'Eaglet', 'Wear it and play ranked games', 1000, 'rare', NULL, TRUE, '#D9CBA3'),
        ('title_ladder_eagle_2', 'title', 'Eagle', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#BFA96B'),
        ('title_ladder_eagle_3', 'title', 'Golden Eagle', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#D4AF37'),
        ('title_ladder_eagle_4', 'title', 'Roc', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#9FC6E8'),
        ('title_ladder_eagle_5', 'title', 'Thunderbird', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#7FA9FF'),
        ('title_ladder_shark_1', 'title', 'Shark Pup', 'Wear it and play ranked games', 1000, 'rare', NULL, TRUE, '#A9C6D6'),
        ('title_ladder_shark_2', 'title', 'Reef Shark', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#7FA8BF'),
        ('title_ladder_shark_3', 'title', 'Great White', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#5B88A3'),
        ('title_ladder_shark_4', 'title', 'Megalodon', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#416B87'),
        ('title_ladder_shark_5', 'title', 'Leviathan', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#2F5570'),
        ('title_tracker', 'title', 'Homing User', 'Homing main', 2000, 'rare', NULL, TRUE, '#FF6677'),
        ('title_ladder_tracker_2', 'title', 'Target Bouncer', 'Wear it and play ranked 1v1 with Homing, Target Bounce or Remote', 0, 'rare', 'achievement', TRUE, '#FF6677'),
        ('title_ladder_tracker_3', 'title', 'Remote Killer', 'Wear it and play ranked 1v1 with Homing, Target Bounce or Remote', 0, 'epic', 'achievement', TRUE, '#FF6677'),
        ('title_ladder_tracker_4', 'title', 'Elite Tracker', 'Wear it and play ranked 1v1 with Homing, Target Bounce or Remote', 0, 'epic', 'achievement', TRUE, '#FF6677'),
        ('title_ladder_tracker_5', 'title', 'No Escape', 'Wear it and play ranked 1v1 with Homing, Target Bounce or Remote', 0, 'legendary', 'achievement', TRUE, '#FF6677'),
        ('title_poisoner', 'title', 'Poison', 'Poison main', 1500, 'rare', NULL, TRUE, '#66CC44'),
        ('title_ladder_poisoner_2', 'title', 'Toxic Cloud', 'Wear it and play ranked 1v1 with Poison, Toxic Cloud or Decay', 0, 'rare', 'achievement', TRUE, '#66CC44'),
        ('title_ladder_poisoner_3', 'title', 'Decay', 'Wear it and play ranked 1v1 with Poison, Toxic Cloud or Decay', 0, 'epic', 'achievement', TRUE, '#66CC44'),
        ('title_ladder_poisoner_4', 'title', 'Plague Doctor', 'Wear it and play ranked 1v1 with Poison, Toxic Cloud or Decay', 0, 'epic', 'achievement', TRUE, '#66CC44'),
        ('title_ladder_poisoner_5', 'title', 'Pestilence', 'Wear it and play ranked 1v1 with Poison, Toxic Cloud or Decay', 0, 'legendary', 'achievement', TRUE, '#66CC44'),
        ('title_windup', 'title', 'Wind Up', 'Windup main', 1500, 'rare', NULL, TRUE, '#AA66FF'),
        ('title_ladder_windup_2', 'title', 'Quick Shot', 'Wear it and play ranked 1v1 with Wind Up, Quick Shot, Fastball or Steady Shot', 0, 'rare', 'achievement', TRUE, '#AA66FF'),
        ('title_ladder_windup_3', 'title', 'Fastball', 'Wear it and play ranked 1v1 with Wind Up, Quick Shot, Fastball or Steady Shot', 0, 'epic', 'achievement', TRUE, '#AA66FF'),
        ('title_ladder_windup_4', 'title', 'Steady Shot', 'Wear it and play ranked 1v1 with Wind Up, Quick Shot, Fastball or Steady Shot', 0, 'epic', 'achievement', TRUE, '#AA66FF'),
        ('title_ladder_windup_5', 'title', 'Railgun', 'Wear it and play ranked 1v1 with Wind Up, Quick Shot, Fastball or Steady Shot', 0, 'legendary', 'achievement', TRUE, '#AA66FF'),
        ('title_reloader', 'title', 'Quick Reload', 'Quick Reload main', 1500, 'rare', NULL, TRUE, '#99CCDD'),
        ('title_ladder_reloader_2', 'title', 'Refresh', 'Wear it and play ranked 1v1 with Quick Reload, Refresh, Scavenger or Tactical Reload', 0, 'rare', 'achievement', TRUE, '#99CCDD'),
        ('title_ladder_reloader_3', 'title', 'Scavenger', 'Wear it and play ranked 1v1 with Quick Reload, Refresh, Scavenger or Tactical Reload', 0, 'epic', 'achievement', TRUE, '#99CCDD'),
        ('title_ladder_reloader_4', 'title', 'Tactical', 'Wear it and play ranked 1v1 with Quick Reload, Refresh, Scavenger or Tactical Reload', 0, 'epic', 'achievement', TRUE, '#99CCDD'),
        ('title_ladder_reloader_5', 'title', 'Bottomless', 'Wear it and play ranked 1v1 with Quick Reload, Refresh, Scavenger or Tactical Reload', 0, 'legendary', 'achievement', TRUE, '#99CCDD'),
        ('title_huge', 'title', 'Huge', 'Huge main', 1500, 'rare', NULL, TRUE, '#FFCC33'),
        ('title_ladder_colossus_2', 'title', 'Brawler', 'Wear it and play ranked 1v1 with Huge, Brawler, Tank, Pristine Perseverance or Defender', 0, 'rare', 'achievement', TRUE, '#FFCC33'),
        ('title_tank', 'title', 'Tank', 'Eats damage', 0, 'rare', 'achievement', TRUE, '#88AA88'),
        ('title_ladder_colossus_4', 'title', 'Pristine', 'Wear it and play ranked 1v1 with Huge, Brawler, Tank, Pristine Perseverance or Defender', 0, 'epic', 'achievement', TRUE, '#FFCC33'),
        ('title_ladder_colossus_5', 'title', 'Colossus', 'Wear it and play ranked 1v1 with Huge, Brawler, Tank, Pristine Perseverance or Defender', 0, 'legendary', 'achievement', TRUE, '#FFCC33'),
        ('title_hasty', 'title', 'Fast Forward', 'Fast Forward main', 1500, 'rare', NULL, TRUE, '#FF6633'),
        ('title_ladder_hasty_2', 'title', 'Chase', 'Wear it and play ranked 1v1 with Fast Forward, Chase, Sneaky or Thruster', 0, 'rare', 'achievement', TRUE, '#FF6633'),
        ('title_ladder_hasty_3', 'title', 'Sneaky', 'Wear it and play ranked 1v1 with Fast Forward, Chase, Sneaky or Thruster', 0, 'epic', 'achievement', TRUE, '#FF6633'),
        ('title_ladder_hasty_4', 'title', 'Thruster', 'Wear it and play ranked 1v1 with Fast Forward, Chase, Sneaky or Thruster', 0, 'epic', 'achievement', TRUE, '#FF6633'),
        ('title_ladder_hasty_5', 'title', 'Lightspeed', 'Wear it and play ranked 1v1 with Fast Forward, Chase, Sneaky or Thruster', 0, 'legendary', 'achievement', TRUE, '#FF6633'),
        ('title_bouncy', 'title', 'Bouncy', 'Bouncy main', 1500, 'rare', NULL, TRUE, '#66CCEE'),
        ('title_bouncer', 'title', 'Bouncer', 'Target Bounce main', 0, 'rare', 'achievement', TRUE, '#BBDD44'),
        ('title_ladder_bounce_3', 'title', 'Ricochet', 'Wear it and play ranked 1v1 with Bouncy, Ricochet, Mayhem or Trickster', 0, 'epic', 'achievement', TRUE, '#66CCEE'),
        ('title_ladder_bounce_4', 'title', 'Mayhem', 'Wear it and play ranked 1v1 with Bouncy, Ricochet, Mayhem or Trickster', 0, 'epic', 'achievement', TRUE, '#66CCEE'),
        ('title_ladder_bounce_5', 'title', 'Trick Shot', 'Wear it and play ranked 1v1 with Bouncy, Ricochet, Mayhem or Trickster', 0, 'legendary', 'achievement', TRUE, '#66CCEE'),
        ('title_healer', 'title', 'Healing Field', 'Healing Field main', 2000, 'rare', NULL, TRUE, '#44DD99'),
        ('title_ladder_healer_2', 'title', 'Leech', 'Wear it and play ranked 1v1 with Healing Field, Leech, Lifestealer or Parasite', 0, 'rare', 'achievement', TRUE, '#44DD99'),
        ('title_ladder_healer_3', 'title', 'Lifestealer', 'Wear it and play ranked 1v1 with Healing Field, Leech, Lifestealer or Parasite', 0, 'epic', 'achievement', TRUE, '#44DD99'),
        ('title_ladder_healer_4', 'title', 'Parasite', 'Wear it and play ranked 1v1 with Healing Field, Leech, Lifestealer or Parasite', 0, 'epic', 'achievement', TRUE, '#44DD99'),
        ('title_ladder_healer_5', 'title', 'Immortal', 'Wear it and play ranked 1v1 with Healing Field, Leech, Lifestealer or Parasite', 0, 'legendary', 'achievement', TRUE, '#44DD99'),
        ('title_echo', 'title', 'Echo', 'Echo main', 2000, 'rare', NULL, TRUE, '#88FFCC'),
        ('title_ladder_echo_2', 'title', 'Empower', 'Wear it and play ranked 1v1 with Echo, Empower, Shockwave or Supernova', 0, 'rare', 'achievement', TRUE, '#88FFCC'),
        ('title_ladder_echo_3', 'title', 'Shockwave', 'Wear it and play ranked 1v1 with Echo, Empower, Shockwave or Supernova', 0, 'epic', 'achievement', TRUE, '#88FFCC'),
        ('title_ladder_echo_4', 'title', 'Supernova', 'Wear it and play ranked 1v1 with Echo, Empower, Shockwave or Supernova', 0, 'epic', 'achievement', TRUE, '#88FFCC'),
        ('title_ladder_echo_5', 'title', 'Big Bang', 'Wear it and play ranked 1v1 with Echo, Empower, Shockwave or Supernova', 0, 'legendary', 'achievement', TRUE, '#88FFCC'),
        ('title_ladder_sniper_1', 'title', 'Marksman', 'Wear it and win ranked 1v1 with 30% accuracy over 40+ shots', 1000, 'rare', NULL, TRUE, '#88CCFF'),
        ('title_sniper', 'title', 'Sniper', 'Precision shooter', 0, 'rare', 'achievement', TRUE, '#88CCFF'),
        ('title_ladder_sniper_3', 'title', 'Sharpshooter', 'Wear it and win ranked 1v1 with 30% accuracy over 40+ shots', 0, 'epic', 'achievement', TRUE, '#88CCFF'),
        ('title_ladder_sniper_4', 'title', 'Deadeye', 'Wear it and win ranked 1v1 with 30% accuracy over 40+ shots', 0, 'epic', 'achievement', TRUE, '#88CCFF'),
        ('title_ladder_sniper_5', 'title', 'Headhunter', 'Wear it and win ranked 1v1 with 30% accuracy over 40+ shots', 0, 'legendary', 'achievement', TRUE, '#88CCFF'),
        ('title_ladder_berserker_1', 'title', 'Bruiser', 'Wear it and win ranked 1v1 games 5-0', 1000, 'rare', NULL, TRUE, '#FF3333'),
        ('title_berserker', 'title', 'Berserker', 'Pure aggression', 0, 'rare', 'achievement', TRUE, '#FF3333'),
        ('title_ladder_berserker_3', 'title', 'Rampage', 'Wear it and win ranked 1v1 games 5-0', 0, 'epic', 'achievement', TRUE, '#FF3333'),
        ('title_ladder_berserker_4', 'title', 'Bloodbath', 'Wear it and win ranked 1v1 games 5-0', 0, 'epic', 'achievement', TRUE, '#FF3333'),
        ('title_ladder_berserker_5', 'title', 'Warlord', 'Wear it and win ranked 1v1 games 5-0', 0, 'legendary', 'achievement', TRUE, '#FF3333'),
        ('title_ladder_blitz_1', 'title', 'Rush', 'Wear it and win ranked 1v1 games in 3:30 or less', 1000, 'rare', NULL, TRUE, '#FFEE33'),
        ('title_blitz', 'title', 'Blitz', 'Fast finisher', 0, 'rare', 'achievement', TRUE, '#FFEE33'),
        ('title_ladder_blitz_3', 'title', 'Lightning', 'Wear it and win ranked 1v1 games in 3:30 or less', 0, 'epic', 'achievement', TRUE, '#FFEE33'),
        ('title_ladder_blitz_4', 'title', 'Speedrunner', 'Wear it and win ranked 1v1 games in 3:30 or less', 0, 'epic', 'achievement', TRUE, '#FFEE33'),
        ('title_ladder_blitz_5', 'title', 'Warp Speed', 'Wear it and win ranked 1v1 games in 3:30 or less', 0, 'legendary', 'achievement', TRUE, '#FFEE33'),
        ('title_ladder_phoenix_1', 'title', 'Ember', 'Wear it and win ranked 1v1 after trailing by 5 points', 1000, 'rare', NULL, TRUE, '#FF8833'),
        ('title_phoenix', 'title', 'Phoenix', 'Reborn after defeat', 0, 'epic', 'achievement', TRUE, '#FF8833'),
        ('title_ladder_phoenix_3', 'title', 'Rebirth', 'Wear it and win ranked 1v1 after trailing by 5 points', 0, 'epic', 'achievement', TRUE, '#FF8833'),
        ('title_ladder_phoenix_4', 'title', 'From the Ashes', 'Wear it and win ranked 1v1 after trailing by 5 points', 0, 'epic', 'achievement', TRUE, '#FF8833'),
        ('title_ladder_phoenix_5', 'title', 'Undying', 'Wear it and win ranked 1v1 after trailing by 5 points', 0, 'legendary', 'achievement', TRUE, '#FF8833'),
        ('title_ladder_specter_1', 'title', 'Shade', 'Wear it and win ranked 1v1 conceding 2 points or fewer', 1000, 'rare', NULL, TRUE, '#AABBFF'),
        ('title_specter', 'title', 'Specter', 'Hard to hit', 0, 'epic', 'achievement', TRUE, '#AABBFF'),
        ('title_ladder_specter_3', 'title', 'Phantom', 'Wear it and win ranked 1v1 conceding 2 points or fewer', 0, 'epic', 'achievement', TRUE, '#AABBFF'),
        ('title_ladder_specter_4', 'title', 'Wraith', 'Wear it and win ranked 1v1 conceding 2 points or fewer', 0, 'epic', 'achievement', TRUE, '#AABBFF'),
        ('title_ladder_specter_5', 'title', 'Untouchable', 'Wear it and win ranked 1v1 conceding 2 points or fewer', 0, 'legendary', 'achievement', TRUE, '#AABBFF'),
        ('title_ladder_apex_1', 'title', 'Contender', 'Wear it and win ranked 1v1 games in a row', 1000, 'rare', NULL, TRUE, '#FFAA00'),
        ('title_ladder_apex_2', 'title', 'Predator', 'Wear it and win ranked 1v1 games in a row', 0, 'rare', 'achievement', TRUE, '#FFAA00'),
        ('title_apex', 'title', 'Apex', 'Top of the food chain', 0, 'epic', 'achievement', TRUE, '#FFAA00'),
        ('title_ladder_apex_4', 'title', 'Alpha', 'Wear it and win ranked 1v1 games in a row', 0, 'epic', 'achievement', TRUE, '#FFAA00'),
        ('title_ladder_apex_5', 'title', 'Undefeated', 'Wear it and win ranked 1v1 games in a row', 0, 'legendary', 'achievement', TRUE, '#FFAA00'),
        ('title_clown', 'title', 'Clown', 'Honk honk.', 800, 'common', NULL, TRUE, '#FF6688'),
        ('title_ladder_clown_2', 'title', 'Jester', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#FF6688'),
        ('title_ladder_clown_3', 'title', 'Harlequin', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#FF6688'),
        ('title_ladder_clown_4', 'title', 'Ringmaster', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#FF6688'),
        ('title_ladder_clown_5', 'title', 'The Joker', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#FF6688'),
        ('title_idiot', 'title', 'Idiot', 'Self-awareness is a virtue.', 1000, 'uncommon', NULL, TRUE, '#DDAA33'),
        ('title_ladder_idiot_2', 'title', 'Moron', 'Wear it and lose ranked games', 0, 'rare', 'achievement', TRUE, '#DDAA33'),
        ('title_ladder_idiot_3', 'title', 'Buffoon', 'Wear it and lose ranked games', 0, 'epic', 'achievement', TRUE, '#DDAA33'),
        ('title_ladder_idiot_4', 'title', 'Village Idiot', 'Wear it and lose ranked games', 0, 'epic', 'achievement', TRUE, '#DDAA33'),
        ('title_ladder_idiot_5', 'title', 'Idiot Savant', 'Wear it and lose ranked games', 0, 'legendary', 'achievement', TRUE, '#DDAA33'),
        ('title_grandma', 'title', 'Grandma', 'Wise beyond your years.', 1000, 'uncommon', NULL, TRUE, '#FF66EE'),
        ('title_ladder_grandma_2', 'title', 'Nana', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#FF66EE'),
        ('title_ladder_grandma_3', 'title', 'Great-Grandma', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#FF66EE'),
        ('title_ladder_grandma_4', 'title', 'Ancestor', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#FF66EE'),
        ('title_ladder_grandma_5', 'title', 'Ancient One', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#FF66EE'),
        ('title_decent', 'title', 'Decent', 'Not great. Not terrible.', 1000, 'uncommon', NULL, TRUE, '#88CC44'),
        ('title_ladder_decent_2', 'title', 'Fine', 'Wear it and win ranked games', 0, 'rare', 'achievement', TRUE, '#88CC44'),
        ('title_ladder_decent_3', 'title', 'Pretty Good', 'Wear it and win ranked games', 0, 'epic', 'achievement', TRUE, '#88CC44'),
        ('title_ladder_decent_4', 'title', 'Actually Good', 'Wear it and win ranked games', 0, 'epic', 'achievement', TRUE, '#88CC44'),
        ('title_ladder_decent_5', 'title', 'Too Good', 'Wear it and win ranked games', 0, 'legendary', 'achievement', TRUE, '#88CC44'),
        ('title_ladder_gold_rush_1', 'title', 'Prospector', 'Wear it and earn gold from ranked play', 1000, 'rare', NULL, TRUE, '#FFD94D'),
        ('title_gold_rush', 'title', 'Gold Rush', 'Worn by those who climbed the mountain.', 0, 'legendary', 'achievement', TRUE, '#FFD94D'),
        ('title_ladder_gold_rush_3', 'title', 'Forty-Niner', 'Wear it and earn gold from ranked play', 0, 'epic', 'achievement', TRUE, '#FFD94D'),
        ('title_ladder_gold_rush_4', 'title', 'Tycoon', 'Wear it and earn gold from ranked play', 0, 'epic', 'achievement', TRUE, '#FFD94D'),
        ('title_ladder_gold_rush_5', 'title', 'Midas', 'Wear it and earn gold from ranked play', 0, 'legendary', 'achievement', TRUE, '#FFD94D'),
        ('title_beginner', 'title', 'Noobie', 'Everyone starts somewhere.', 500, 'common', NULL, TRUE, '#AAAAAA'),
        ('title_regular', 'title', 'Regular', 'You show up.', 0, 'common', 'achievement', TRUE, '#FFFFFF'),
        ('title_active', 'title', 'Active', 'More ranked than not.', 0, 'common', 'achievement', TRUE, '#44CC88'),
        ('title_sweaty', 'title', 'Sweaty', 'Sweat is just XP in liquid form.', 0, 'rare', 'achievement', TRUE, '#FFCC33'),
        ('title_tryhard', 'title', 'Tryhard', 'Trying, hard.', 0, 'rare', 'achievement', TRUE, '#FF9933'),
        ('title_pronoun_he', 'title', 'He/him I', 'Pronoun title.', 100, 'common', NULL, TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_he_2', 'title', 'He/him II', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_he_3', 'title', 'He/him III', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_he_4', 'title', 'He/him IV', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_he_5', 'title', 'He/him V', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#EEEEEE'),
        ('title_pronoun_she', 'title', 'She/her I', 'Pronoun title.', 100, 'common', NULL, TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_she_2', 'title', 'She/her II', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_she_3', 'title', 'She/her III', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_she_4', 'title', 'She/her IV', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_she_5', 'title', 'She/her V', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#EEEEEE'),
        ('title_pronoun_they', 'title', 'They/them I', 'Pronoun title.', 100, 'common', NULL, TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_they_2', 'title', 'They/them II', 'Wear it and play ranked games', 0, 'rare', 'achievement', TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_they_3', 'title', 'They/them III', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_they_4', 'title', 'They/them IV', 'Wear it and play ranked games', 0, 'epic', 'achievement', TRUE, '#EEEEEE'),
        ('title_ladder_pronoun_they_5', 'title', 'They/them V', 'Wear it and play ranked games', 0, 'legendary', 'achievement', TRUE, '#EEEEEE')
    ON CONFLICT (sku) DO UPDATE
       SET name = EXCLUDED.name,
           description = EXCLUDED.description,
           price = EXCLUDED.price,
           rarity = EXCLUDED.rarity,
           rotation_pool = EXCLUDED.rotation_pool,
           catalog_ready = EXCLUDED.catalog_ready,
           preview_color = EXCLUDED.preview_color;

    -- 4. Every rung's ladder row.
    INSERT INTO title_ladders (sku, line, tier, threshold) VALUES
        ('title_ladder_rat_1', 'rat', 1, 0),
        ('title_ladder_rat_2', 'rat', 2, 15),
        ('title_ladder_rat_3', 'rat', 3, 40),
        ('title_ladder_rat_4', 'rat', 4, 100),
        ('title_ladder_rat_5', 'rat', 5, 200),
        ('title_ladder_cat_1', 'cat', 1, 0),
        ('title_ladder_cat_2', 'cat', 2, 15),
        ('title_ladder_cat_3', 'cat', 3, 40),
        ('title_ladder_cat_4', 'cat', 4, 100),
        ('title_ladder_cat_5', 'cat', 5, 200),
        ('title_ladder_dog_1', 'dog', 1, 0),
        ('title_ladder_dog_2', 'dog', 2, 15),
        ('title_ladder_dog_3', 'dog', 3, 40),
        ('title_ladder_dog_4', 'dog', 4, 100),
        ('title_ladder_dog_5', 'dog', 5, 200),
        ('title_ladder_turtle_1', 'turtle', 1, 0),
        ('title_ladder_turtle_2', 'turtle', 2, 15),
        ('title_ladder_turtle_3', 'turtle', 3, 40),
        ('title_ladder_turtle_4', 'turtle', 4, 100),
        ('title_ladder_turtle_5', 'turtle', 5, 200),
        ('title_ladder_rabbit_1', 'rabbit', 1, 0),
        ('title_ladder_rabbit_2', 'rabbit', 2, 15),
        ('title_ladder_rabbit_3', 'rabbit', 3, 40),
        ('title_ladder_rabbit_4', 'rabbit', 4, 100),
        ('title_ladder_rabbit_5', 'rabbit', 5, 200),
        ('title_ladder_bear_1', 'bear', 1, 0),
        ('title_ladder_bear_2', 'bear', 2, 15),
        ('title_ladder_bear_3', 'bear', 3, 40),
        ('title_ladder_bear_4', 'bear', 4, 100),
        ('title_ladder_bear_5', 'bear', 5, 200),
        ('title_ladder_eagle_1', 'eagle', 1, 0),
        ('title_ladder_eagle_2', 'eagle', 2, 15),
        ('title_ladder_eagle_3', 'eagle', 3, 40),
        ('title_ladder_eagle_4', 'eagle', 4, 100),
        ('title_ladder_eagle_5', 'eagle', 5, 200),
        ('title_ladder_shark_1', 'shark', 1, 0),
        ('title_ladder_shark_2', 'shark', 2, 15),
        ('title_ladder_shark_3', 'shark', 3, 40),
        ('title_ladder_shark_4', 'shark', 4, 100),
        ('title_ladder_shark_5', 'shark', 5, 200),
        ('title_tracker', 'tracker', 1, 0),
        ('title_ladder_tracker_2', 'tracker', 2, 10),
        ('title_ladder_tracker_3', 'tracker', 3, 25),
        ('title_ladder_tracker_4', 'tracker', 4, 60),
        ('title_ladder_tracker_5', 'tracker', 5, 120),
        ('title_poisoner', 'poisoner', 1, 0),
        ('title_ladder_poisoner_2', 'poisoner', 2, 10),
        ('title_ladder_poisoner_3', 'poisoner', 3, 25),
        ('title_ladder_poisoner_4', 'poisoner', 4, 60),
        ('title_ladder_poisoner_5', 'poisoner', 5, 120),
        ('title_windup', 'windup', 1, 0),
        ('title_ladder_windup_2', 'windup', 2, 10),
        ('title_ladder_windup_3', 'windup', 3, 25),
        ('title_ladder_windup_4', 'windup', 4, 60),
        ('title_ladder_windup_5', 'windup', 5, 120),
        ('title_reloader', 'reloader', 1, 0),
        ('title_ladder_reloader_2', 'reloader', 2, 10),
        ('title_ladder_reloader_3', 'reloader', 3, 25),
        ('title_ladder_reloader_4', 'reloader', 4, 60),
        ('title_ladder_reloader_5', 'reloader', 5, 120),
        ('title_huge', 'colossus', 1, 0),
        ('title_ladder_colossus_2', 'colossus', 2, 10),
        ('title_tank', 'colossus', 3, 25),
        ('title_ladder_colossus_4', 'colossus', 4, 60),
        ('title_ladder_colossus_5', 'colossus', 5, 120),
        ('title_hasty', 'hasty', 1, 0),
        ('title_ladder_hasty_2', 'hasty', 2, 10),
        ('title_ladder_hasty_3', 'hasty', 3, 25),
        ('title_ladder_hasty_4', 'hasty', 4, 60),
        ('title_ladder_hasty_5', 'hasty', 5, 120),
        ('title_bouncy', 'bounce', 1, 0),
        ('title_bouncer', 'bounce', 2, 10),
        ('title_ladder_bounce_3', 'bounce', 3, 25),
        ('title_ladder_bounce_4', 'bounce', 4, 60),
        ('title_ladder_bounce_5', 'bounce', 5, 120),
        ('title_healer', 'healer', 1, 0),
        ('title_ladder_healer_2', 'healer', 2, 10),
        ('title_ladder_healer_3', 'healer', 3, 25),
        ('title_ladder_healer_4', 'healer', 4, 60),
        ('title_ladder_healer_5', 'healer', 5, 120),
        ('title_echo', 'echo', 1, 0),
        ('title_ladder_echo_2', 'echo', 2, 10),
        ('title_ladder_echo_3', 'echo', 3, 25),
        ('title_ladder_echo_4', 'echo', 4, 60),
        ('title_ladder_echo_5', 'echo', 5, 120),
        ('title_ladder_sniper_1', 'sniper', 1, 0),
        ('title_sniper', 'sniper', 2, 3),
        ('title_ladder_sniper_3', 'sniper', 3, 8),
        ('title_ladder_sniper_4', 'sniper', 4, 18),
        ('title_ladder_sniper_5', 'sniper', 5, 35),
        ('title_ladder_berserker_1', 'berserker', 1, 0),
        ('title_berserker', 'berserker', 2, 3),
        ('title_ladder_berserker_3', 'berserker', 3, 8),
        ('title_ladder_berserker_4', 'berserker', 4, 20),
        ('title_ladder_berserker_5', 'berserker', 5, 40),
        ('title_ladder_blitz_1', 'blitz', 1, 0),
        ('title_blitz', 'blitz', 2, 3),
        ('title_ladder_blitz_3', 'blitz', 3, 8),
        ('title_ladder_blitz_4', 'blitz', 4, 16),
        ('title_ladder_blitz_5', 'blitz', 5, 30),
        ('title_ladder_phoenix_1', 'phoenix', 1, 0),
        ('title_phoenix', 'phoenix', 2, 2),
        ('title_ladder_phoenix_3', 'phoenix', 3, 4),
        ('title_ladder_phoenix_4', 'phoenix', 4, 8),
        ('title_ladder_phoenix_5', 'phoenix', 5, 15),
        ('title_ladder_specter_1', 'specter', 1, 0),
        ('title_specter', 'specter', 2, 2),
        ('title_ladder_specter_3', 'specter', 3, 5),
        ('title_ladder_specter_4', 'specter', 4, 10),
        ('title_ladder_specter_5', 'specter', 5, 20),
        ('title_ladder_apex_1', 'apex', 1, 0),
        ('title_ladder_apex_2', 'apex', 2, 5),
        ('title_apex', 'apex', 3, 8),
        ('title_ladder_apex_4', 'apex', 4, 12),
        ('title_ladder_apex_5', 'apex', 5, 20),
        ('title_clown', 'clown', 1, 0),
        ('title_ladder_clown_2', 'clown', 2, 15),
        ('title_ladder_clown_3', 'clown', 3, 40),
        ('title_ladder_clown_4', 'clown', 4, 100),
        ('title_ladder_clown_5', 'clown', 5, 200),
        ('title_idiot', 'idiot', 1, 0),
        ('title_ladder_idiot_2', 'idiot', 2, 8),
        ('title_ladder_idiot_3', 'idiot', 3, 20),
        ('title_ladder_idiot_4', 'idiot', 4, 50),
        ('title_ladder_idiot_5', 'idiot', 5, 100),
        ('title_grandma', 'grandma', 1, 0),
        ('title_ladder_grandma_2', 'grandma', 2, 15),
        ('title_ladder_grandma_3', 'grandma', 3, 40),
        ('title_ladder_grandma_4', 'grandma', 4, 100),
        ('title_ladder_grandma_5', 'grandma', 5, 200),
        ('title_decent', 'decent', 1, 0),
        ('title_ladder_decent_2', 'decent', 2, 8),
        ('title_ladder_decent_3', 'decent', 3, 20),
        ('title_ladder_decent_4', 'decent', 4, 50),
        ('title_ladder_decent_5', 'decent', 5, 100),
        ('title_ladder_gold_rush_1', 'gold_rush', 1, 0),
        ('title_gold_rush', 'gold_rush', 2, 500),
        ('title_ladder_gold_rush_3', 'gold_rush', 3, 1500),
        ('title_ladder_gold_rush_4', 'gold_rush', 4, 3000),
        ('title_ladder_gold_rush_5', 'gold_rush', 5, 6000),
        ('title_beginner', 'grinder', 1, 0),
        ('title_regular', 'grinder', 2, 15),
        ('title_active', 'grinder', 3, 40),
        ('title_sweaty', 'grinder', 4, 100),
        ('title_tryhard', 'grinder', 5, 200),
        ('title_pronoun_he', 'pronoun_he', 1, 0),
        ('title_ladder_pronoun_he_2', 'pronoun_he', 2, 15),
        ('title_ladder_pronoun_he_3', 'pronoun_he', 3, 40),
        ('title_ladder_pronoun_he_4', 'pronoun_he', 4, 100),
        ('title_ladder_pronoun_he_5', 'pronoun_he', 5, 200),
        ('title_pronoun_she', 'pronoun_she', 1, 0),
        ('title_ladder_pronoun_she_2', 'pronoun_she', 2, 15),
        ('title_ladder_pronoun_she_3', 'pronoun_she', 3, 40),
        ('title_ladder_pronoun_she_4', 'pronoun_she', 4, 100),
        ('title_ladder_pronoun_she_5', 'pronoun_she', 5, 200),
        ('title_pronoun_they', 'pronoun_they', 1, 0),
        ('title_ladder_pronoun_they_2', 'pronoun_they', 2, 15),
        ('title_ladder_pronoun_they_3', 'pronoun_they', 3, 40),
        ('title_ladder_pronoun_they_4', 'pronoun_they', 4, 100),
        ('title_ladder_pronoun_they_5', 'pronoun_they', 5, 200)
    ON CONFLICT (sku) DO UPDATE
       SET line = EXCLUDED.line, tier = EXCLUDED.tier, threshold = EXCLUDED.threshold;

    RAISE NOTICE 'title ladders 365: first application written';
END $m365$;

-- Post-checks, on every application: the final state, not what was written.
DO $m365post$
DECLARE
    n          INTEGER;
    bad        INTEGER;
BEGIN
    SELECT count(*) INTO n FROM title_ladders;
    IF n <> 160 THEN
        RAISE EXCEPTION 'title ladders 365: expected % title_ladders rows, found %', 160, n;
    END IF;
    SELECT count(DISTINCT line) INTO n FROM title_ladders;
    IF n <> 32 THEN
        RAISE EXCEPTION 'title ladders 365: expected % ladders, found %', 32, n;
    END IF;
    -- Exactly tiers 1..5 on every ladder, one rung each.
    SELECT count(*) INTO bad FROM (
        SELECT line FROM title_ladders GROUP BY line
        HAVING count(*) <> 5 OR count(DISTINCT tier) <> 5 OR min(tier) <> 1 OR max(tier) <> 5) x;
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders 365: % ladders are not exactly tiers 1..5', bad;
    END IF;
    -- Thresholds start at 0 and strictly increase.
    SELECT count(*) INTO bad FROM title_ladders WHERE tier = 1 AND threshold <> 0;
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders 365: % entry rungs have a non-zero threshold', bad;
    END IF;
    SELECT count(*) INTO bad FROM (
        SELECT threshold, LAG(threshold) OVER (PARTITION BY line ORDER BY tier) AS prev
          FROM title_ladders) x
     WHERE prev IS NOT NULL AND threshold <= prev;
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders 365: % tier steps do not increase the threshold', bad;
    END IF;
    -- Every rung is a title.
    SELECT count(*) INTO bad
      FROM title_ladders tl LEFT JOIN shop_items si ON si.sku = tl.sku
     WHERE si.id IS NULL OR si.kind <> 'title';
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders 365: % rungs have no title row in shop_items', bad;
    END IF;
    -- Tier 1 on sale in the ordinary pool; tiers 2-5 granted only, price 0.
    SELECT count(*) INTO bad
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier = 1 AND NOT (si.rotation_pool IS NULL AND si.price > 0 AND si.catalog_ready IS TRUE);
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders 365: % entry rungs are not on sale in the ordinary pool', bad;
    END IF;
    SELECT count(*) INTO bad
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier > 1 AND NOT (COALESCE(si.rotation_pool, '') = 'achievement' AND si.price = 0);
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders 365: % earned rungs are not granted-only at price 0', bad;
    END IF;
    -- The space budget: every rung name at most 14 characters.
    SELECT count(*) INTO bad
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE char_length(si.name) > 14;
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders 365: % rung names are longer than 14 characters', bad;
    END IF;
    -- The rungs 331 had and this catalogue does not are gone.
    SELECT count(*) INTO bad FROM shop_items WHERE sku IN ('title_ladder_rat_4_king', 'title_ladder_rat_4_queen', 'title_ladder_cat_6', 'title_ladder_dog_6', 'title_ladder_turtle_6', 'title_ladder_rabbit_6', 'title_ladder_bear_6', 'title_ladder_eagle_6', 'title_ladder_shark_6');
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders 365: % dropped rungs are still in shop_items', bad;
    END IF;
    SELECT count(*) INTO bad FROM information_schema.columns
     WHERE table_schema = current_schema() AND table_name = 'title_ladder_progress'
       AND column_name IN ('streak', 'streak_at');
    IF bad <> 2 THEN
        RAISE EXCEPTION 'title ladders 365: title_ladder_progress.streak or streak_at is missing';
    END IF;
    SELECT count(*) INTO bad FROM information_schema.columns
     WHERE table_schema = current_schema() AND table_name = 'title_ladder_credits'
       AND column_name = 'line' AND is_nullable = 'YES';
    IF bad <> 1 THEN
        RAISE EXCEPTION 'title ladders 365: title_ladder_credits.line is not nullable (a game claimed with no ladder worn needs it)';
    END IF;
    RAISE NOTICE 'title ladders 365: final state holds -- % ladders, % rungs, every entry rung on sale', 32, 160;
END $m365post$;

COMMIT;
