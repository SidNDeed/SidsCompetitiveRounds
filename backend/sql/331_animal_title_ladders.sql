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
-- DEPLOY ORDER: THIS FILE FIRST, THE API SECOND.
-- -----------------------------------------------
-- In the batch's standard form, so the order can be read off every file in
-- the same place instead of inferred from prose -- which is what a reader at
-- deploy time actually needs, and what 333 omitted entirely. For THIS file
-- the order is the batch's convention rather than a hard requirement: no
-- path that runs today queries `title_ladders` or the new `shop_items` rows
-- (the progression hook is uncalled and the router unmounted), and the one
-- production reference -- main reading `title_ladders.GRANTED_ONLY_SKUS` --
-- is a python constant baked into the image, not a query. Both orders work;
-- migration-first is the order the batch deploys in and the one this file is
-- verified under.
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
--   * re-running reaches the same final state with only "already exists,
--     skipping" notices. That was true of the FINAL STATE and NOT of the
--     writes: the title_ladders insert was ON CONFLICT DO UPDATE, so every
--     re-run rewrote all 48 rows, and the catalog_ready repair was ungated,
--     so a re-run after the future activation release would have taken the
--     eight entry rungs back off sale. Both are fixed above and both are now
--     asserted by backend/tests/test_migration_reruns.py, which applies this
--     file twice against a live cluster and compares each row's VALUE AND ITS
--     xmin -- a rewrite-to-the-same-value is invisible to anything weaker.
--     Re-verified 2026-09-19 under `psql -f` (production's own invocation)
--     and under asyncpg: second run, zero rows written, zero objects
--     replaced.
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

-- HAS THIS FILE RUN BEFORE? Captured BEFORE the CREATE TABLEs below, because
-- the absence of `title_ladders` is the only first-run marker available --
-- this repo keeps no migrations ledger.
--
-- WHICH OF THIS FILE'S STATEMENTS ARE GUARDED, AND WHICH ARE NOT. The three
-- `CREATE TABLE IF NOT EXISTS` statements run unconditionally while the
-- `CREATE INDEX` below is guarded on the catalog, and the difference was
-- measured rather than assumed, and measured one holder at a time:
-- re-applying this file completes with any ONE of those three tables held by
-- an ordinary reader, and again with that one table held by an ordinary
-- writer, whereas the index's `IF NOT EXISTS` spelling takes SHARE before
-- it looks for the name and stops every writer to title_ladders for as long
-- as it queues. This paragraph used to settle the question for all of them at
-- once, on the grounds that re-establishing correct schema is a no-op -- true
-- of what a statement WRITES and not of what it LOCKS, and the lock is the
-- part of a re-run that ordinary traffic on a live primary can be stopped by.
-- See the index's own comment for the measurement and
-- `test_a_second_run_takes_no_blocking_lock` for the standing check.
--
-- AND THE REST OF WHAT A RE-RUN ISSUES, NAMED FOR THE SAME REASON. The
-- sentence above settles the two kinds of SCHEMA statement against each other
-- and stops, which reads as though those were the whole file. They are not.
-- Outside every guard block this file also issues a `CREATE TEMP TABLE` (the
-- first-run marker below), a `COMMENT ON TABLE`, two `INSERT INTO` statements
-- and an `UPDATE` -- five kinds of statement in all, counted off the file
-- rather than remembered: the disclosure check in `test_migration_headers`
-- parses this file and reds if it issues a kind this header does not name,
-- matching on a word boundary inside THIS comment block rather than anywhere
-- in the file, because `UPDATE` and `CREATE TABLE IF NOT EXISTS` each appear
-- elsewhere in these comments for unrelated reasons. That
-- check exists because 332's equivalent sentence named two of its three
-- statements, read as exhaustive, and nothing in the suite could disagree
-- with it.
--
-- What they WRITE on a re-run is the separate question, and it is the one the
-- post-checks at the foot of this file answer. The `CREATE TEMP TABLE` is
-- session-local and dropped at COMMIT. The `COMMENT ON TABLE` re-sets the
-- same text. Both `INSERT INTO` statements are `ON CONFLICT (sku) DO
-- NOTHING`, so a re-run adds no row and rewrites none. The `UPDATE` is the catalog_ready
-- repair, which keys on how MANY tier-1 rungs are ready rather than on
-- whether this file has run before, and is a no-op in every state but the
-- one it exists to correct.
--
-- WHAT IT IS AND IS NOT USED FOR. It is read by ONE thing: the money
-- post-check at the foot of this file, which admits eight ready tier-1 rungs
-- as the later activation release's doing and admits nothing but zero on a
-- first run, where that release cannot have happened yet.
--
-- It does NOT decide the catalog_ready repair any more. It used to, and that
-- was the wrong question asked of the right flag: "has this file run before"
-- is TRUE both after the activation release, where the repair would revoke a
-- live purchase, and on the ordinary re-run that is the documented remedy for
-- a rung wrongly flagged ready -- where the repair is the only thing that
-- clears it. One boolean cannot mean both (#430). The repair keys on how MANY
-- tier-1 rungs are ready instead; see the statement itself.
CREATE TEMP TABLE _m331_state ON COMMIT DROP AS
SELECT EXISTS (SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'title_ladders') AS already_applied;

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

-- Guarded on the catalog rather than spelled `IF NOT EXISTS`, which decides
-- the same thing and decides it too late: CREATE INDEX takes its SHARE lock
-- on the table before it looks for the name, so on a re-run that spelling
-- stops every WRITER to title_ladders for as long as it queues, and with the
-- lock_timeout above it aborts the file instead of waiting. Measured on
-- PostgreSQL 16.9: re-applying this file with one writer holding ROW
-- EXCLUSIVE on title_ladders died with "canceling statement due to lock
-- timeout". The three CREATE TABLE IF NOT EXISTS statements are left alone:
-- the same probe re-applies this file with each of those tables held by a
-- reader and by a writer and it completes, so whatever lock they take is one
-- ordinary traffic does not conflict with. That is what was measured; it is
-- not a claim that they take none.
DO $m331idx$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = current_schema()
                    AND c.relname = 'idx_title_ladders_line') THEN
    CREATE INDEX idx_title_ladders_line ON title_ladders (line, tier);
  END IF;
END $m331idx$;

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
-- ON CONFLICT DO NOTHING, NOT DO UPDATE. An earlier version of this statement
-- rewrote line/tier/threshold on every re-run. That looks harmless -- the
-- values come from the same generator -- but it makes a re-run a WRITE to
-- every one of the 48 rows, and it means this file silently reverts any
-- correction made to the table since, on a table whose thresholds are exactly
-- what an operator might correct in place. Re-running a migration must change
-- nothing. Drift between this file and `title_ladders.LADDERS` is caught by
-- `test_migration_rows_match_module`, which is the right place for it: a test
-- that reports a difference, not a migration that quietly imposes one.
ON CONFLICT (sku) DO NOTHING;

-- FINAL-STATE REPAIR: ALL EIGHT OR NONE, and the reason it is a separate
-- statement.
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
-- trusting the insert literals. The question is then only WHEN the statement
-- must hold back, because it is a repair in one direction and a revocation in
-- the other: after the later release that flips these rungs TRUE alongside
-- the progression hook, a repair that always ran would take eight live,
-- purchasable rungs off sale on the next replay of this file, silently.
--
-- WHAT IT KEYS ON, and what it used to key on. It used to key on
-- `already_applied` -- "has this file run before" -- and that one boolean was
-- carrying two different questions (#430). A rung flipped TRUE early, by a
-- hand edit or a half-applied activation or an operator trying the shop, is
-- exactly the state re-applying this file is the documented remedy for, and
-- `already_applied` is TRUE in that case too. So the remedy did nothing, and
-- the post-check below reported the rung instead of clearing it.
--
-- It keys on the COUNT instead. This file leaves none of the eight ready;
-- the activation release sets all eight, and it does so in one statement, so
-- eight of eight is the state this file must not touch. One to seven is a
-- state neither of them ends on, and it is the one that has to be cleared --
-- toward off-sale, which is the conservative direction for a purchase
-- (#283). The post-check below fails closed if any survive.
--
-- WHAT THIS ASKS OF THE FUTURE ACTIVATION RELEASE: set the eight in ONE
-- statement. If it ever lands them in several, re-applying this file between
-- two of them clears what it has done so far. That is the conservative
-- direction and it is recoverable by re-running that release, but it is a
-- real constraint and it is stated here rather than assumed.
--
-- The count is read from the snapshot this statement began with, so the rows
-- it is updating cannot change the answer underneath it.
--
-- This statement still only ever CLEARS the flag; nothing here can put a rung
-- on sale.
UPDATE shop_items si
   SET catalog_ready = FALSE
  FROM title_ladders tl
 WHERE tl.sku = si.sku
   AND tl.tier = 1
   AND si.catalog_ready IS TRUE
   AND (SELECT COUNT(*)
          FROM title_ladders t2 JOIN shop_items s2 ON s2.sku = t2.sku
         WHERE t2.tier = 1 AND s2.catalog_ready IS TRUE) < 8;

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
    v_applied  BOOLEAN;
BEGIN
    SELECT already_applied INTO v_applied FROM _m331_state;
    SELECT COUNT(*) INTO n_items FROM shop_items WHERE sku LIKE 'title\_ladder\_%';
    SELECT COUNT(*) INTO n_ladders FROM title_ladders;
    IF n_items <> 48 THEN
        RAISE EXCEPTION 'title ladders: expected % shop_items rows, found %', 48, n_items;
    END IF;
    IF n_ladders <> 48 THEN
        RAISE EXCEPTION 'title ladders: expected % title_ladders rows, found %', 48, n_ladders;
    END IF;

    -- Tier 1 is in the ORDINARY POOL and priced; every higher rung is
    -- granted only. Note what this count does NOT assert: readiness. Whether
    -- a tier-1 rung is on sale is the separate post-check further down --
    -- none of them is, until the activation release flips all eight -- and
    -- saying "purchasable" here would contradict it.
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
    --
    -- THE STATES THIS DISTINGUISHES. None ready is this file's own state.
    -- Eight ready is the activation release's, which flips them together with
    -- the progression hook -- failing there would make that release's own
    -- database un-migratable, so it is reported instead, and "the ladders are
    -- live" is worth seeing in a deploy log. Anything between the two is a
    -- state no release produces; the repair above clears exactly that case,
    -- so reaching it here means the repair could not, and it is the case
    -- where a player can spend 1000 gold on a ladder that cannot advance.
    -- That one fails, on a re-run as much as on a first run.
    --
    -- On a FIRST run eight-of-eight is not the activation release either --
    -- that release comes after this file -- so the first-run arm admits none
    -- and nothing else.
    SELECT COUNT(*) INTO bad
      FROM title_ladders tl JOIN shop_items si ON si.sku = tl.sku
     WHERE tl.tier = 1 AND si.catalog_ready IS TRUE;
    IF NOT v_applied THEN
        IF bad > 0 THEN
            RAISE EXCEPTION 'title ladders: % tier-1 rung(s) are catalog_ready on this file''s first run and would be on sale for a ladder that cannot advance; the repair above did not reach them', bad;
        END IF;
        RAISE NOTICE 'title ladders: first application -- 48 rungs, 8 entry rungs held off sale';
    ELSIF bad = 0 THEN
        RAISE NOTICE 'title ladders: already applied; the 8 entry rungs are held off sale.';
    ELSIF bad = 8 THEN
        RAISE NOTICE 'title ladders: already applied; all 8 entry rungs are catalog_ready -- the activation release has run, and this re-run left that flag alone.';
    ELSE
        RAISE EXCEPTION 'title ladders: % of the 8 tier-1 rungs are catalog_ready, which is neither this file''s state (none) nor the activation release''s (all 8). The repair above clears a partial set, so this means it could not reach these rows -- each one is listed by /shop/items at 1000 gold for a ladder whose progression hook is not wired', bad;
    END IF;
END $$;

COMMIT;

