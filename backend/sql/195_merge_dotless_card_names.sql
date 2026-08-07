-- 195: merge Turkish dotless-i card names into their canonical spellings.
--
-- CAUSE (client fix ships alongside this): both `ToTitleCase` copies used
-- culture-sensitive casing, so on a tr-TR client "WIND UP".ToLower() produced
-- "wınd up" with U+0131. Those clients minted the dotless spelling as a
-- SEPARATE card_name key, which matches nothing in the CardInfo registry and
-- is therefore always stored with rarity 'Unknown'. Plugin.cs and
-- GameStateWatcher.cs now use ToLowerInvariant/ToUpperInvariant, so no NEW
-- dotless rows can appear; this migration cleans up the existing ones.
--
-- ── WHY AN EXPLICIT ALLOWLIST, NOT A BLANKET REWRITE ────────────────────────
-- The first draft rewrote EVERY U+0131 in every card name, and its own comment
-- claimed it did not (Codex Aug-7, HIGH — a false claim in a comment is itself
-- a defect, #277). Card names are free text from match reports: there is no
-- vanilla allowlist, mods add their own cards, and invariant casing now
-- PRESERVES a genuine U+0131. So a real mod card legitimately spelled with a
-- dotless i would have been silently merged into a different card's history,
-- irreversibly.
--
-- Instead every mapping below is one this migration has EVIDENCE for. Verified
-- read-only against production before writing this file: each canonical target
-- is an established card with 273-5628 recorded picks, while its dotless twin
-- has 1-11 — i.e. the target is unambiguously the real card and the twin is
-- the typo. A dotless name NOT in this list is left strictly alone.
--
-- CORRECTION (migration 198). This header used to end "...so this list is
-- complete for the data as it stands." THAT CLAIM WAS FALSE. The list was
-- derived from dotless names in `match_cards` — cards actually PICKED — and
-- three more (Homing, Shield Charge, Shields Up) existed only in `card_offers`,
-- having been offered to a tr-TR client and never picked. No match_cards query
-- could have found them.
--
-- The check that WAS run asked whether any dotless name in card_offers had a
-- canonical TARGET missing from match_cards (none did). That is a different
-- question from whether the allowlist covered every dotless SOURCE name;
-- answering one and asserting the other is the actual defect, and it is the
-- reusable lesson. Migration 198 merges the three and its post-check asserts
-- the whole class is empty across all seven card tables rather than only
-- checking its own allowlist — which is what let this one pass while leaving
-- rows behind.
--
-- Idempotent statement-by-statement (#243: the deploy wrapper's `||` fallback
-- re-runs the whole file after its first-attempt error).

-- EXPLICIT TRANSACTION (Codex Aug-7 r2, HIGH). psql runs in AUTOCOMMIT, so
-- `CREATE TEMP TABLE ... ON COMMIT DROP` committed immediately and dropped the
-- table before the very next statement could populate it: the INSERT below
-- failed with `relation "_dotless_map" does not exist` and ON_ERROR_STOP=1
-- aborted the whole migration before a single row was merged. Wrapping the
-- file makes the temp table live for the migration AND makes the merge atomic
-- — a failure now rolls back cleanly instead of leaving a half-merged table.
BEGIN;

CREATE TEMP TABLE _dotless_map (dotless TEXT PRIMARY KEY, canon TEXT NOT NULL) ON COMMIT DROP;

INSERT INTO _dotless_map (dotless, canon) VALUES
    ('Po' || chr(305) || 'son',                              'Poison'),
    ('W' || chr(305) || 'nd Up',                             'Wind Up'),
    ('Comb' || chr(305) || 'ne',                             'Combine'),
    ('B' || chr(305) || 'g Bullet',                          'Big Bullet'),
    ('Qu' || chr(305) || 'ck Reload',                        'Quick Reload'),
    ('Paras' || chr(305) || 'te',                            'Parasite'),
    ('T' || chr(305) || 'med Detonat' || chr(305) || 'on',   'Timed Detonation'),
    ('Qu' || chr(305) || 'ck Shot',                          'Quick Shot'),
    ('Careful Plann' || chr(305) || 'ng',                    'Careful Planning'),
    ('Explos' || chr(305) || 've Bullet',                    'Explosive Bullet'),
    ('Stat' || chr(305) || 'c F' || chr(305) || 'eld',       'Static Field'),
    ('S' || chr(305) || 'lence',                             'Silence'),
    ('Dr' || chr(305) || 'll Ammo',                          'Drill Ammo'),
    ('Tr' || chr(305) || 'ckster',                           'Trickster'),
    ('Phoen' || chr(305) || 'x',                             'Phoenix'),
    ('Tox' || chr(305) || 'c Cloud',                         'Toxic Cloud'),
    ('Rad' || chr(305) || 'ance',                            'Radiance'),
    ('L' || chr(305) || 'festealer',                         'Lifestealer'),
    ('Ch' || chr(305) || 'll' || chr(305) || 'ng Presence',  'Chilling Presence')
ON CONFLICT (dotless) DO NOTHING;

-- ── Surrogate-key tables: a plain UPDATE is safe (no uniqueness on name) ────
DO $$
DECLARE
    t TEXT;
    n BIGINT;
BEGIN
    FOREACH t IN ARRAY ARRAY['match_cards','card_offers','ffa_match_cards',
                             'ffa_card_offers','ovt_match_cards','team_match_cards']
    LOOP
        IF to_regclass(t) IS NULL THEN
            RAISE NOTICE 'migration 195: table % absent, skipped', t;
            CONTINUE;
        END IF;
        EXECUTE format(
            'UPDATE %I tgt SET card_name = m.canon
               FROM _dotless_map m
              WHERE tgt.card_name = m.dotless', t);
        GET DIAGNOSTICS n = ROW_COUNT;
        RAISE NOTICE 'migration 195: % rows merged in %', n, t;
    END LOOP;
END $$;

-- ── player_card_tiers: card_name is part of the PRIMARY KEY ─────────────────
-- A rename onto an existing (player_id, card_name, filter) is a duplicate-key
-- abort, so colliding source rows must go first.
--
-- Codex Aug-7 (HIGH): deleting only rows whose canonical target ALREADY exists
-- is not sufficient. Two DIFFERENT dotless spellings can normalise to the SAME
-- canonical (e.g. a name containing two i's typo'd in different positions);
-- with no pre-existing canonical row neither gets deleted, and then both
-- UPDATE to the identical key and the migration strands mid-run. The fix is to
-- keep exactly ONE source row per (player_id, filter, canon) group and delete
-- the rest, regardless of whether a canonical row exists.
DO $$
DECLARE
    n BIGINT;
BEGIN
    IF to_regclass('player_card_tiers') IS NULL THEN
        RAISE NOTICE 'migration 195: player_card_tiers absent, skipped';
        RETURN;
    END IF;

    -- (a) drop sources that would collide with an EXISTING canonical row
    DELETE FROM player_card_tiers t
     USING _dotless_map m
     WHERE t.card_name = m.dotless
       AND EXISTS (SELECT 1 FROM player_card_tiers c
                    WHERE c.player_id = t.player_id
                      AND c.filter    = t.filter
                      AND c.card_name = m.canon);
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE 'migration 195: % player_card_tiers rows dropped (canonical already present)', n;

    -- (b) collapse MANY dotless spellings mapping to one canonical: keep the
    --     lowest ctid per (player_id, filter, canon) and drop the others.
    DELETE FROM player_card_tiers t
     USING (
        SELECT t2.ctid AS victim
          FROM player_card_tiers t2
          JOIN _dotless_map m2 ON t2.card_name = m2.dotless
         WHERE t2.ctid <> (
                SELECT MIN(t3.ctid)
                  FROM player_card_tiers t3
                  JOIN _dotless_map m3 ON t3.card_name = m3.dotless
                 WHERE t3.player_id = t2.player_id
                   AND t3.filter    = t2.filter
                   AND m3.canon     = m2.canon)
     ) dup
     WHERE t.ctid = dup.victim;
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE 'migration 195: % player_card_tiers rows dropped (many-to-one collapse)', n;

    -- (c) rename what survives
    UPDATE player_card_tiers t SET card_name = m.canon
      FROM _dotless_map m
     WHERE t.card_name = m.dotless;
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE 'migration 195: % player_card_tiers rows merged', n;
END $$;

-- ── Post-check ─────────────────────────────────────────────────────────────
DO $$
DECLARE
    t TEXT;
    leftover BIGINT;
    total BIGINT := 0;
    other BIGINT;
BEGIN
    FOREACH t IN ARRAY ARRAY['match_cards','card_offers','ffa_match_cards',
                             'ffa_card_offers','ovt_match_cards','team_match_cards',
                             'player_card_tiers']
    LOOP
        IF to_regclass(t) IS NULL THEN CONTINUE; END IF;
        EXECUTE format(
            'SELECT COUNT(*) FROM %I tgt JOIN _dotless_map m ON tgt.card_name = m.dotless', t)
            INTO leftover;
        total := total + leftover;
        IF leftover > 0 THEN
            RAISE WARNING 'migration 195: % mapped dotless rows survive in %', leftover, t;
        END IF;
    END LOOP;
    IF total > 0 THEN
        RAISE EXCEPTION 'migration 195 post-check FAILED: % mapped dotless rows remain', total;
    END IF;

    -- Informational only, never rewritten: any dotless name NOT in the
    -- allowlist is deliberately untouched (it may be a legitimate mod card).
    IF to_regclass('match_cards') IS NOT NULL THEN
        SELECT COUNT(DISTINCT card_name) INTO other
          FROM match_cards
         WHERE card_name LIKE '%' || chr(305) || '%';
        IF other > 0 THEN
            RAISE NOTICE 'migration 195: % unmapped dotless name(s) left alone by design', other;
        END IF;
    END IF;

    RAISE NOTICE 'migration 195 post-check OK';
END $$;

COMMIT;
