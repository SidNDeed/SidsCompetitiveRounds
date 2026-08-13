-- 216: (a) per-player end-of-game BUILD STATS storage in all four modes, and
--      (b) the 2v2 + FFA placement titles.
--
-- ── PART 1: end-of-game build stats ─────────────────────────────────────────
--
-- The hold-Tab overlay shows 21 build stats per player (HP, damage, attack
-- speed, reload, bullets, block cooldown, move speed, size, ...). Every one of
-- them is a LIVE per-frame read off the Unity objects: nothing was ever
-- accumulated, transmitted or stored, so a finished game's build was gone the
-- moment the round ended. These columns give match history the final build.
--
-- WIRE FORMAT (fixed; the client sends ONLY numbers, never labels):
--
--   1|hp|maxhp|dmg|aspd|reload|ammo|bullets|bursts|bounces|bspd|slow|knock|
--    spread|lifesteal|blockcd|blocks|regen|movespd|jump|jumps|size
--
-- 22 pipe-separated fields. Field 0 is the literal format version "1"; fields
-- 1..21 are each a decimal number (optionally negative, at most 3 decimal
-- places) or the literal "-" for "unavailable". Labels are rendered by the
-- client from its own localised catalogue, so nothing here needs translating
-- and nothing user-authored ever reaches the column.
--
-- The API validates every value against an anchored regex before it is bound
-- (main.py _clean_end_stats / _END_STATS_RE) and NULLs out anything that does
-- not match, so a malformed or hostile string can never be stored and can
-- never fail an otherwise-valid match report. Structural cap is 274 chars.
--
-- NULLABLE WITH NO DEFAULT, on purpose (#257): a metric that starts mid-history
-- must read as "not recorded", never as a real zero. Every game played before
-- this ships, and every game reported by a client that predates the field,
-- stays NULL and every consumer renders "no data" rather than a build of all
-- zeroes.
--
-- These columns are ADVISORY and sit OUTSIDE every frozen HMAC canonical (1v1
-- 7-field, 1v2 10-field, 2v2 11-field, FFA "ffa:"-tagged variable-length).
-- None of those strings change here — see hard rule #5.
--
-- ── PART 2: 2v2 + FFA placement titles ──────────────────────────────────────
--
-- 'title_podium' has always been 1v1-only, both in its grant path and in its
-- rendered text ("1st Place"). Cross-granting it from another ladder would
-- silently widen an existing cosmetic's meaning, so 2v2 and FFA get their own
-- skus, granted from their own boards and rendered with their own text
-- ("2v2 1st Place" / "FFA 1st Place"), same gold/silver/bronze palette.
--
-- Both follow migration 123's shape exactly: price 0, rarity legendary,
-- rotation_pool 'achievement' (hidden from the public shop listing, surfaced
-- to owners, purchase blocked with 403). The catalog_ready BEFORE-INSERT
-- trigger from migration 148 only forces FALSE for kind='face', so titles
-- inherit TRUE and need nothing extra.
--
-- ── DEPLOY ORDER: THIS MIGRATION MUST RUN BEFORE THE API DEPLOY ─────────────
--
-- The 1v1 and 2v2 writers go through the ORM (Match / TeamMatch), so the new
-- columns are declared on those models and SQLAlchemy emits them in every
-- INSERT. Against a database without the columns, EVERY 1v1 and 2v2 match
-- report would fail. There is no savepoint that helps: the columns are part of
-- the row being written, not an optional read. Migrate first, then deploy.
--
-- Idempotent statement-by-statement: the deploy wrapper re-runs the whole file
-- on any nonzero exit (#243). No data backfill is attempted anywhere here —
-- there is nothing to backfill, because no historical game ever captured these
-- values (#168 does not apply).

BEGIN;

-- ── Part 1a: 1v1 ────────────────────────────────────────────────────────────
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_end_stats TEXT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_end_stats TEXT;

-- ── Part 1b: 2v2 (per slot, matching the t1a/t1b/t2a/t2b column family) ─────
ALTER TABLE team_matches ADD COLUMN IF NOT EXISTS t1a_end_stats TEXT;
ALTER TABLE team_matches ADD COLUMN IF NOT EXISTS t1b_end_stats TEXT;
ALTER TABLE team_matches ADD COLUMN IF NOT EXISTS t2a_end_stats TEXT;
ALTER TABLE team_matches ADD COLUMN IF NOT EXISTS t2b_end_stats TEXT;

-- ── Part 1c: 1v2 (per seat; 1v2 has no telemetry table, so these hang off the
--            match row beside solo_fps_avg / solo_damage_timeline) ───────────
ALTER TABLE ovt_matches ADD COLUMN IF NOT EXISTS solo_end_stats  TEXT;
ALTER TABLE ovt_matches ADD COLUMN IF NOT EXISTS duo_a_end_stats TEXT;
ALTER TABLE ovt_matches ADD COLUMN IF NOT EXISTS duo_b_end_stats TEXT;

-- ── Part 1d: FFA (already one row per player) ───────────────────────────────
ALTER TABLE ffa_match_players ADD COLUMN IF NOT EXISTS end_stats TEXT;

-- ── Part 2: placement title seeds ───────────────────────────────────────────
-- Display text and colour are resolved at RENDER time by _display_title_sync
-- (the name/description below are only what the shop and inventory show), so
-- these rows never need updating when a board reshuffles.

INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
SELECT 'title_podium_2v2', 'title', '2v2 Podium',
       'Held by the top 3 on the 2v2 leaderboard',
       0, 'legendary', 'achievement', '#FFD700'
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'title_podium_2v2');

INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, preview_color)
SELECT 'title_podium_ffa', 'title', 'FFA Podium',
       'Held by the top 3 on the FFA leaderboard',
       0, 'legendary', 'achievement', '#FFD700'
WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE sku = 'title_podium_ffa');

-- ── Post-check (visible in /migrate output) ─────────────────────────────────
-- Fails loudly rather than reporting a half-applied wave as a success.
DO $$
DECLARE
    n_cols  INTEGER;
    n_skus  INTEGER;
BEGIN
    -- table_schema pinned: information_schema.columns spans every schema, so
    -- an unpinned count could exceed 10 and RAISE on a correct migration.
    SELECT COUNT(*) INTO n_cols
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND (
              (table_name = 'matches'           AND column_name IN ('p1_end_stats', 'p2_end_stats'))
           OR (table_name = 'team_matches'      AND column_name IN ('t1a_end_stats', 't1b_end_stats',
                                                                    't2a_end_stats', 't2b_end_stats'))
           OR (table_name = 'ovt_matches'       AND column_name IN ('solo_end_stats', 'duo_a_end_stats',
                                                                    'duo_b_end_stats'))
           OR (table_name = 'ffa_match_players' AND column_name = 'end_stats')
           );
    IF n_cols <> 10 THEN
        RAISE EXCEPTION 'migration 216: expected 10 end_stats columns, found %', n_cols;
    END IF;

    SELECT COUNT(*) INTO n_skus
      FROM shop_items
     WHERE sku IN ('title_podium_2v2', 'title_podium_ffa')
       AND kind = 'title' AND rotation_pool = 'achievement';
    IF n_skus <> 2 THEN
        RAISE EXCEPTION 'migration 216: expected 2 placement title skus, found %', n_skus;
    END IF;

    RAISE NOTICE 'migration 216 post-check OK: % end_stats columns, % placement titles', n_cols, n_skus;
END $$;

COMMIT;
