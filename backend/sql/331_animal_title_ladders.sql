-- 331_animal_title_ladders.sql
--
-- Animal title ladders: upgradeable titles. A player buys the first rung of
-- a line (Rat, 1000 g, an ordinary shop title), equips it, and every
-- completed rated SERIES finished while a rung of that line is equipped counts
-- +1 toward the next rung. Crossing a threshold grants the rung, which is
-- owned for ever and auto-equipped.
--
-- GENERATED from backend/api/title_ladders.py's LADDERS structure. Do not
-- hand-edit the row lists below: backend/tests/test_title_ladders.py
-- re-derives every INSERT here from that module and fails on any drift, so a
-- manual edit here reads as a test failure rather than as a difference
-- between what the API believes and what the table holds.
--
-- WHY THE HIDDEN RUNGS SIT IN rotation_pool = 'achievement' AND NOT A NEW
-- 'ladder' POOL. Two behaviours in main.py are keyed on that exact string,
-- and a rung above the first needs both: /shop/items hides the pool from
-- everyone except an OWNER and appends an owned one so the Shop tab can
-- render its Set Active button (the surface achievement titles spent three
-- releases without, #151), and the purchase endpoint refuses the pool by
-- name. A pool called 'ladder' would be matched by neither: the rung would
-- be invisible to the player who earned it and buyable for its listed price
-- by anything that can name the sku. This is a deliberate deviation from
-- the item plan, which proposed the new name.
--
-- SAFE TO RUN BEFORE THE API, and the reason is the catalog_ready column
-- rather than an absence of readers. An earlier draft of this header said
-- the new rows were "inert until something grants them" while also calling
-- the tier-1 rows "ordinary purchasable titles" -- which is a contradiction,
-- and the second half was the true one. shop_items.catalog_ready is NOT NULL
-- DEFAULT TRUE (147:26, confirmed against the live schema), the BEFORE INSERT
-- gate that forces it FALSE fires only for kind='face' (148:353), and
-- /shop/items lists exactly rotation_pool IS NULL AND catalog_ready IS TRUE
-- (main.py). Eight tier-1 rungs at 1000 gold each carry rotation_pool NULL,
-- so on the default they would have gone on sale the moment this file was
-- applied -- for a ladder that cannot advance, because the progression hook
-- below is not wired. Migrations here are pre-authorized independently of
-- code SHAs, so nothing but this header stood between the file and a live
-- shop; a header is not a mechanism.
--
-- The eight entry rungs are therefore inserted with catalog_ready = FALSE.
-- A later release flips them TRUE in the same deploy that wires the hook --
-- the pattern 147 set up for exactly this. Gold spent is not recoverable and
-- a catalog flag is, so the gate fails in the safe direction.
--
-- Pooled rungs are written TRUE explicitly rather than left to the default:
-- the entry rungs carry FALSE two statements below, so leaving the pooled ones
-- to a default would make the difference between them look like an omission
-- instead of the decision it is.
--
-- It is a HEDGE, not a live guarantee, and an earlier version of this comment
-- overstated it -- it claimed gating them twice "could hide a title from the
-- player who earned it". It could not, because nothing reads readiness on that
-- path. `/shop/items` appends an owned achievement-pool row on rotation_pool
-- and ownership alone, with no readiness predicate, and the client's only row
-- skips are keyed on kind (a face with no local sprite, a music album this
-- build cannot render). FALSE here would hide nothing today. TRUE is written
-- anyway so that it is already correct if that ever changes --
-- test_the_owner_append_does_not_filter_on_readiness fails from the main.py
-- side on the day it does, because that edit happens nowhere near this file.
--
-- Apply this first, deploy second.
--
-- THE PROGRESSION HOOK IS NOT WIRED as this migration ships. The tables are
-- correct and empty; title_ladder_progress stays empty until the four
-- completion sites in main.py call title_ladders.record_completed_games.
-- An empty progress table after this migration is expected, not a fault.
--
-- EXECUTED, NOT ONLY READ (2026-09-18). Five runs on a local PostgreSQL 16.9
-- -- the primary runs postgres:16-alpine -- against the objects this file
-- touches, rebuilt from the primary's own catalogue rather than from the ORM,
-- INCLUDING both triggers on shop_items. What the runs settled:
--
--   * clean apply commits: 48 shop_items, 48 title_ladders, 8 ordinary-pool
--     entry rungs, 40 granted-only, ZERO tier-1 rungs left ready to sell.
--   * re-running is a genuine no-op -- same final state, only "already
--     exists, skipping" notices.
--   * BOTH shop_items triggers are inert for this file, and neither is
--     obvious from reading it. `gate_new_face_shop_item` fires BEFORE INSERT
--     but only acts on kind = 'face'. `stamp_shop_item_catalog_release`
--     fires BEFORE UPDATE OF catalog_ready -- which the repair below does --
--     but its whole body sits behind `NEW.catalog_ready AND NOT OLD
--     .catalog_ready`, and the repair moves TRUE to FALSE. Measured: zero
--     rungs come out with released_at set. A future activation migration
--     flipping these FALSE to TRUE WILL run that body; it stamps released_at
--     and skips the placement-revision check, which has no row for a title.
--   * an entry sku that already exists with the expected pool and price but
--     catalog_ready = TRUE is REPAIRED, not preserved: ON CONFLICT keeps the
--     row, the repair clears the flag, and the final-state post-check passes
--     with zero rungs on sale. That collision was the open question on this
--     file and it is now an executed result, not an argument.
--   * an entry sku colliding with the WRONG rotation_pool cannot be repaired
--     -- a pool is not a flag -- and the entry-rung post-check stops the file:
--     "expected 8 ordinary-pool entry rungs, found 7", psql exit 3 under the
--     wrapper's ON_ERROR_STOP, which is what makes the audit log say FAILED.
--   * and after that failure all three tables are ABSENT. The file really is
--     all-or-nothing, DDL included -- #340 verified by running it rather than
--     by counting keywords in a test.
--
-- This is evidence from one instance, not a proof about the primary. What it
-- does NOT cover: the primary's real data. The one fact read from the primary
-- directly is that it currently holds zero title_ladder_% skus, so the
-- collision paths above are not live there today.

BEGIN;
SET LOCAL lock_timeout = '5s';

-- The catalogue: which sku is which rung of which line, and what it costs
-- in games. PRIMARY KEY is the sku and NOT (line, tier), because rat's tier
-- 4 is TWO rungs -- Rat King and Rat Queen, either of which is rung 4 --
-- and a (line, tier) key cannot hold both. Every consumer therefore reads
-- a tier as a LIST of rungs.
CREATE TABLE IF NOT EXISTS title_ladders (
    sku        VARCHAR(64) PRIMARY KEY REFERENCES shop_items(sku) ON DELETE CASCADE,
    line       VARCHAR(32) NOT NULL,
    tier       INTEGER     NOT NULL CHECK (tier >= 1),
    threshold  INTEGER     NOT NULL CHECK (threshold >= 0)
);

CREATE INDEX IF NOT EXISTS idx_title_ladders_line ON title_ladders (line, tier);

-- Per-player progress on one line. `games` COUNTS COMPLETED SERIES, not
-- individual games -- the column keeps the shorter name, but one best-of-three
-- series increments it by one. `games` is only ever moved by a delta
-- (SET games = games + 1, #326); `tier` is derived from `games` and the
-- thresholds, and is stored so a threshold edit cannot retroactively take a
-- rung away from someone who already owns it.
CREATE TABLE IF NOT EXISTS title_ladder_progress (
    player_id   UUID        NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    line        VARCHAR(32) NOT NULL,
    games       INTEGER     NOT NULL DEFAULT 0 CHECK (games >= 0),
    tier        INTEGER     NOT NULL DEFAULT 1 CHECK (tier >= 1),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (player_id, line)
);

-- The once-per-completion gate. A completed series can reach the hook more
-- than once by construction -- 2v2 settles in TWO different code paths and a
-- report can be retried -- so the increment is not guarded by a caller
-- promise but by this key: the writer that wins the INSERT is the one that
-- increments. `mode` is recorded for audit and is deliberately NOT part of
-- the key; if it were, one series arriving under two mode strings would
-- count twice, which is exactly the 2v2 shape this is closing.
CREATE TABLE IF NOT EXISTS title_ladder_credits (
    player_id     UUID        NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    reference_id  VARCHAR(64) NOT NULL,
    line          VARCHAR(32) NOT NULL,
    mode          VARCHAR(16) NOT NULL,
    credited_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (player_id, reference_id)
);

COMMENT ON TABLE title_ladder_credits IS
    'One row per player per completed rated SERIES credited to a ladder. The PK (player_id, reference_id) IS the unit: whatever the caller passes as reference_id is what gets counted once, and every mode passes a series/sitting id, never a per-game id. It is therefore also the double-credit gate -- 2v2 has two completion paths and both pass the team series id, so the second loses the insert. An earlier version of this comment said "per completed game", which cannot be true at the same time as the series id.';

-- The rungs as shop items. ON CONFLICT (sku) DO NOTHING: re-running this
-- file changes nothing, and it will not overwrite a name Sid has since
-- edited in place.
INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, catalog_ready, preview_color) VALUES
    ('title_ladder_rat_1', 'title', 'Rat', 'Small, quick, everywhere.', 1000, 'rare', NULL, FALSE, '#9AA0A6'),
    ('title_ladder_rat_2', 'title', 'Rat Leader', 'The other rats listen.', 0, 'rare', 'achievement', TRUE, '#B6BDC6'),
    ('title_ladder_rat_3', 'title', 'Rat Lord', 'A lordship of gutters.', 0, 'epic', 'achievement', TRUE, '#A88CE0'),
    ('title_ladder_rat_4_king', 'title', 'Rat King', 'Crowned in the tunnels.', 0, 'epic', 'achievement', TRUE, '#E0B33A'),
    ('title_ladder_rat_4_queen', 'title', 'Rat Queen', 'Crowned in the tunnels.', 0, 'epic', 'achievement', TRUE, '#E0B33A'),
    ('title_ladder_rat_5', 'title', 'Rat God', 'Worshipped. Still a rat.', 0, 'legendary', 'achievement', TRUE, '#FFE066'),
    ('title_ladder_cat_1', 'title', 'Kitten', 'Mostly paws.', 1000, 'rare', NULL, FALSE, '#F2C1A0'),
    ('title_ladder_cat_2', 'title', 'Cat', 'Sovereign of the sofa.', 0, 'rare', 'achievement', TRUE, '#E8A87C'),
    ('title_ladder_cat_3', 'title', 'Big Cat', 'No longer a lap animal.', 0, 'epic', 'achievement', TRUE, '#C97B4A'),
    ('title_ladder_cat_4', 'title', 'Alpha Cat', 'The fight ends when you say.', 0, 'epic', 'achievement', TRUE, '#B25E2E'),
    ('title_ladder_cat_5', 'title', 'President Meow', 'Elected unopposed.', 0, 'legendary', 'achievement', TRUE, '#E5A83B'),
    ('title_ladder_cat_6', 'title', 'Cat Deity', 'Nine lives, one throne.', 0, 'legendary', 'achievement', TRUE, '#FFD966'),
    ('title_ladder_dog_1', 'title', 'Pup', 'Enthusiasm exceeds skill.', 1000, 'rare', NULL, FALSE, '#C7A87B'),
    ('title_ladder_dog_2', 'title', 'Dog', 'Reliable. Loud.', 0, 'rare', 'achievement', TRUE, '#B08D5A'),
    ('title_ladder_dog_3', 'title', 'Good Dog', 'Told so, repeatedly.', 0, 'epic', 'achievement', TRUE, '#98703C'),
    ('title_ladder_dog_4', 'title', 'Top Dog', 'Head of the pack.', 0, 'epic', 'achievement', TRUE, '#D4913A'),
    ('title_ladder_dog_5', 'title', 'Big Dog', 'The pack is now a problem.', 0, 'legendary', 'achievement', TRUE, '#E9AE45'),
    ('title_ladder_dog_6', 'title', 'Dog God', 'Very good. Divine, even.', 0, 'legendary', 'achievement', TRUE, '#FFDE8A'),
    ('title_ladder_turtle_1', 'title', 'Hatchling', 'Freshly out of the shell.', 1000, 'rare', NULL, FALSE, '#8FBF9F'),
    ('title_ladder_turtle_2', 'title', 'Turtle', 'Slow is a strategy.', 0, 'rare', 'achievement', TRUE, '#6FA882'),
    ('title_ladder_turtle_3', 'title', 'Snapper', 'The bite lands first.', 0, 'epic', 'achievement', TRUE, '#4E8C66'),
    ('title_ladder_turtle_4', 'title', 'Elder Turtle', 'Outlasted everyone.', 0, 'epic', 'achievement', TRUE, '#3F7A57'),
    ('title_ladder_turtle_5', 'title', 'Turtle Sage', 'Patience as a weapon.', 0, 'legendary', 'achievement', TRUE, '#6BC49A'),
    ('title_ladder_turtle_6', 'title', 'World Turtle', 'Everything rests on you.', 0, 'legendary', 'achievement', TRUE, '#9BF0C4'),
    ('title_ladder_rabbit_1', 'title', 'Bunny', 'Twitchy and fast.', 1000, 'rare', NULL, FALSE, '#F3C6D6'),
    ('title_ladder_rabbit_2', 'title', 'Rabbit', 'Gone before the shot.', 0, 'rare', 'achievement', TRUE, '#E3A0BC'),
    ('title_ladder_rabbit_3', 'title', 'Jackrabbit', 'Nothing catches you.', 0, 'epic', 'achievement', TRUE, '#CE7A9E'),
    ('title_ladder_rabbit_4', 'title', 'Hare Apparent', 'Next in line.', 0, 'epic', 'achievement', TRUE, '#B85C86'),
    ('title_ladder_rabbit_5', 'title', 'Moon Rabbit', 'Pounding something on the moon.', 0, 'legendary', 'achievement', TRUE, '#C79BF0'),
    ('title_ladder_rabbit_6', 'title', 'Rabbit God', 'A god of small quick things.', 0, 'legendary', 'achievement', TRUE, '#EBD1FF'),
    ('title_ladder_bear_1', 'title', 'Cub', 'Cute until it is not.', 1000, 'rare', NULL, FALSE, '#C59A6B'),
    ('title_ladder_bear_2', 'title', 'Bear', 'Simply large.', 0, 'rare', 'achievement', TRUE, '#A87A4E'),
    ('title_ladder_bear_3', 'title', 'Grizzly', 'The argument is over.', 0, 'epic', 'achievement', TRUE, '#8A5C35'),
    ('title_ladder_bear_4', 'title', 'Bear Boss', 'Runs the woods.', 0, 'epic', 'achievement', TRUE, '#6F4526'),
    ('title_ladder_bear_5', 'title', 'Ursa Major', 'Written into the sky.', 0, 'legendary', 'achievement', TRUE, '#D9A85C'),
    ('title_ladder_bear_6', 'title', 'Bear God', 'The woods run themselves now.', 0, 'legendary', 'achievement', TRUE, '#FFDDA1'),
    ('title_ladder_eagle_1', 'title', 'Eaglet', 'Not yet airborne.', 1000, 'rare', NULL, FALSE, '#D9CBA3'),
    ('title_ladder_eagle_2', 'title', 'Eagle', 'The sky is a map.', 0, 'rare', 'achievement', TRUE, '#BFA96B'),
    ('title_ladder_eagle_3', 'title', 'Golden Eagle', 'Gilded and patient.', 0, 'epic', 'achievement', TRUE, '#D4AF37'),
    ('title_ladder_eagle_4', 'title', 'Sky Lord', 'Owns the airspace.', 0, 'epic', 'achievement', TRUE, '#9FC6E8'),
    ('title_ladder_eagle_5', 'title', 'Thunderbird', 'Arrives with the storm.', 0, 'legendary', 'achievement', TRUE, '#7FA9FF'),
    ('title_ladder_eagle_6', 'title', 'Eagle God', 'The storm arrives with you.', 0, 'legendary', 'achievement', TRUE, '#CFE4FF'),
    ('title_ladder_shark_1', 'title', 'Shark Pup', 'Teeth already.', 1000, 'rare', NULL, FALSE, '#A9C6D6'),
    ('title_ladder_shark_2', 'title', 'Shark', 'Never stops moving.', 0, 'rare', 'achievement', TRUE, '#7FA8BF'),
    ('title_ladder_shark_3', 'title', 'Great White', 'The water empties.', 0, 'epic', 'achievement', TRUE, '#5B88A3'),
    ('title_ladder_shark_4', 'title', 'Apex Shark', 'Top of every chain here.', 0, 'epic', 'achievement', TRUE, '#416B87'),
    ('title_ladder_shark_5', 'title', 'Megalodon', 'Too big for the ocean.', 0, 'legendary', 'achievement', TRUE, '#2F5570'),
    ('title_ladder_shark_6', 'title', 'Shark God', 'The ocean is the pet.', 0, 'legendary', 'achievement', TRUE, '#8FD8FF')
ON CONFLICT (sku) DO NOTHING;

INSERT INTO title_ladders (sku, line, tier, threshold) VALUES
    ('title_ladder_rat_1', 'rat', 1, 0),
    ('title_ladder_rat_2', 'rat', 2, 10),
    ('title_ladder_rat_3', 'rat', 3, 30),
    ('title_ladder_rat_4_king', 'rat', 4, 75),
    ('title_ladder_rat_4_queen', 'rat', 4, 75),
    ('title_ladder_rat_5', 'rat', 5, 150),
    ('title_ladder_cat_1', 'cat', 1, 0),
    ('title_ladder_cat_2', 'cat', 2, 10),
    ('title_ladder_cat_3', 'cat', 3, 30),
    ('title_ladder_cat_4', 'cat', 4, 75),
    ('title_ladder_cat_5', 'cat', 5, 150),
    ('title_ladder_cat_6', 'cat', 6, 300),
    ('title_ladder_dog_1', 'dog', 1, 0),
    ('title_ladder_dog_2', 'dog', 2, 10),
    ('title_ladder_dog_3', 'dog', 3, 30),
    ('title_ladder_dog_4', 'dog', 4, 75),
    ('title_ladder_dog_5', 'dog', 5, 150),
    ('title_ladder_dog_6', 'dog', 6, 300),
    ('title_ladder_turtle_1', 'turtle', 1, 0),
    ('title_ladder_turtle_2', 'turtle', 2, 10),
    ('title_ladder_turtle_3', 'turtle', 3, 30),
    ('title_ladder_turtle_4', 'turtle', 4, 75),
    ('title_ladder_turtle_5', 'turtle', 5, 150),
    ('title_ladder_turtle_6', 'turtle', 6, 300),
    ('title_ladder_rabbit_1', 'rabbit', 1, 0),
    ('title_ladder_rabbit_2', 'rabbit', 2, 10),
    ('title_ladder_rabbit_3', 'rabbit', 3, 30),
    ('title_ladder_rabbit_4', 'rabbit', 4, 75),
    ('title_ladder_rabbit_5', 'rabbit', 5, 150),
    ('title_ladder_rabbit_6', 'rabbit', 6, 300),
    ('title_ladder_bear_1', 'bear', 1, 0),
    ('title_ladder_bear_2', 'bear', 2, 10),
    ('title_ladder_bear_3', 'bear', 3, 30),
    ('title_ladder_bear_4', 'bear', 4, 75),
    ('title_ladder_bear_5', 'bear', 5, 150),
    ('title_ladder_bear_6', 'bear', 6, 300),
    ('title_ladder_eagle_1', 'eagle', 1, 0),
    ('title_ladder_eagle_2', 'eagle', 2, 10),
    ('title_ladder_eagle_3', 'eagle', 3, 30),
    ('title_ladder_eagle_4', 'eagle', 4, 75),
    ('title_ladder_eagle_5', 'eagle', 5, 150),
    ('title_ladder_eagle_6', 'eagle', 6, 300),
    ('title_ladder_shark_1', 'shark', 1, 0),
    ('title_ladder_shark_2', 'shark', 2, 10),
    ('title_ladder_shark_3', 'shark', 3, 30),
    ('title_ladder_shark_4', 'shark', 4, 75),
    ('title_ladder_shark_5', 'shark', 5, 150),
    ('title_ladder_shark_6', 'shark', 6, 300)
ON CONFLICT (sku) DO UPDATE SET line = EXCLUDED.line, tier = EXCLUDED.tier, threshold = EXCLUDED.threshold;

-- FINAL-STATE REPAIR, and the reason it is a separate statement.
--
-- The shop_items INSERT above is ON CONFLICT (sku) DO NOTHING, which leaves a
-- row that already exists EXACTLY as it was. Writing catalog_ready = FALSE in
-- the VALUES list therefore fixes a clean database and does nothing at all to
-- one where an entry rung is already present -- a prior partial run, a
-- hand-created row, an earlier draft of this file. On such a database the
-- rung keeps catalog_ready = TRUE, /shop/items lists exactly
-- (rotation_pool IS NULL AND catalog_ready IS TRUE), and the row is a live
-- 1000-gold purchase for a ladder whose progression hook is not wired.
--
-- So state the invariant as an operation on the FINAL state instead of
-- trusting the insert literals. Idempotent, and it cannot widen anything:
-- it only ever clears the flag, never sets it.
UPDATE shop_items si
   SET catalog_ready = FALSE
  FROM title_ladders tl
 WHERE tl.sku = si.sku
   AND tl.tier = 1
   AND si.catalog_ready IS TRUE;

-- Post-checks. Each one can actually fail: they are counted against the
-- rows this file just wrote, not against a constant that was copied from
-- the same place the rows came from.
DO $$
DECLARE
    n_items    INTEGER;
    n_ladders  INTEGER;
    n_entry    INTEGER;
    n_hidden   INTEGER;
    bad        INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_items FROM shop_items WHERE sku LIKE 'title\_ladder\_%';
    SELECT COUNT(*) INTO n_ladders FROM title_ladders;
    IF n_items <> 48 THEN
        RAISE EXCEPTION 'title ladders: expected % shop_items rows, found %', 48, n_items;
    END IF;
    IF n_ladders <> 48 THEN
        RAISE EXCEPTION 'title ladders: expected % title_ladders rows, found %', 48, n_ladders;
    END IF;

    -- Tier 1 is in the ORDINARY POOL and priced; every higher rung is
    -- granted only. Note what this count does NOT assert: readiness. Tier-1
    -- rungs are deliberately left catalog_ready = FALSE by the repair above,
    -- so they are not on sale -- the separate post-check further down is the
    -- one that enforces that. Saying "purchasable" here would contradict it.
    SELECT COUNT(*) INTO n_entry
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier = 1 AND si.rotation_pool IS NULL AND si.price > 0;
    IF n_entry <> 8 THEN
        RAISE EXCEPTION 'title ladders: expected % ordinary-pool entry rungs, found %', 8, n_entry;
    END IF;
    SELECT COUNT(*) INTO n_hidden
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier > 1 AND si.rotation_pool = 'achievement' AND si.price = 0;
    IF n_hidden <> 40 THEN
        RAISE EXCEPTION 'title ladders: expected % granted-only rungs, found %', 40, n_hidden;
    END IF;

    -- Two rungs sharing a tier must share its threshold, or 'games to the
    -- next rung' has two answers and the client shows whichever it read.
    SELECT COUNT(*) INTO bad FROM (
        SELECT line, tier FROM title_ladders
         GROUP BY line, tier HAVING COUNT(DISTINCT threshold) > 1) x;
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders: % (line, tier) groups disagree on threshold', bad;
    END IF;

    -- Thresholds must climb with tier inside a line. A flat or inverted pair
    -- would grant two rungs at once for ever, or a lower rung never.
    SELECT COUNT(*) INTO bad FROM (
        SELECT line, tier, MIN(threshold) AS th,
               LAG(MIN(threshold)) OVER (PARTITION BY line ORDER BY tier) AS prev
          FROM title_ladders GROUP BY line, tier) x
     WHERE prev IS NOT NULL AND th <= prev;
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders: % tier steps do not increase the threshold', bad;
    END IF;

    -- Every line must start at 0, or its owner can buy rung 1 and be below
    -- the threshold of the rung they are already wearing.
    SELECT COUNT(*) INTO bad FROM title_ladders WHERE tier = 1 AND threshold <> 0;
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders: % entry rungs have a non-zero threshold', bad;
    END IF;

    -- THE ONE THAT GUARDS MONEY, asserted on the final state rather than on
    -- what this file tried to write. An entry rung that is catalog_ready is
    -- listed by /shop/items and costs 1000 gold, and the ladder it starts
    -- cannot advance yet. Counted AFTER the repair above, so it fails only if
    -- the repair was removed or could not reach the row.
    SELECT COUNT(*) INTO bad
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier = 1 AND si.catalog_ready IS TRUE;
    IF bad > 0 THEN
        RAISE EXCEPTION 'title ladders: % tier-1 rung(s) are catalog_ready and would be on sale for a ladder that cannot advance', bad;
    END IF;
END $$;

COMMIT;

