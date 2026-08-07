-- 198: merge the three dotless-i card names migration 195's allowlist missed.
--
-- HOW 195 MISSED THEM, because the mistake generalises: 195's 19-entry
-- allowlist was derived from the dotless names present in `match_cards` — the
-- table of cards actually PICKED. These three were only ever OFFERED to the
-- tr-TR client and never picked, so they exist solely in `card_offers` and no
-- query over match_cards could have found them.
--
-- 195's header states "this list is complete for the data as it stands". That
-- claim was false and is corrected there. The underlying error is narrower than
-- it looks: the completeness check that WAS run asked whether any dotless name
-- in card_offers had a canonical TARGET missing from match_cards (it did not),
-- which is a different question from whether the allowlist covered every
-- dotless SOURCE name. Checking one and claiming the other is the defect.
--
-- Found post-deploy by re-counting dotless rows per table rather than trusting
-- 195's post-check — which passed correctly, because it only ever asserts that
-- rows matching the ALLOWLIST are gone. A post-check scoped to the allowlist
-- cannot detect an incomplete allowlist. Sweeping all seven card tables found
-- exactly these 3 names / 9 rows and nothing else.
--
-- EVIDENCE (read-only, before writing this file) — same standard as 195: each
-- canonical target is an established card and each dotless twin is negligible.
--   Homing        2047 offers / 1765 picks   vs  Homing(dotless)        4 offers
--   Shield Charge 2194 offers / 1717 picks   vs  Shield Charge(dotless) 3 offers
--   Shields Up     528 offers /  336 picks   vs  Shields Up(dotless)    2 offers
--
-- IMPACT while unmerged: /cards LEFT JOINs offers on card_name, so the
-- canonical rows under-reported times_offered by 4/3/2 out of thousands, and
-- pass_rate with them. Statistically trivial, but it is wrong data and the
-- server-side normaliser (_canon_card_name) is being extended with the same
-- three names in this release so tr-TR clients cannot mint them again.
--
-- All seven card tables are swept, not just card_offers: nothing stops a future
-- pick of one of these landing elsewhere before clients update.
--
-- Idempotent statement-by-statement (#243 — the wrapper runs the file twice).

BEGIN;

CREATE TEMP TABLE _dotless_map2 (dotless TEXT PRIMARY KEY, canon TEXT NOT NULL) ON COMMIT DROP;

-- Explicit transaction for the same reason as 195: under psql autocommit an
-- ON COMMIT DROP temp table is destroyed before the next statement can use it.
INSERT INTO _dotless_map2 (dotless, canon) VALUES
    ('Hom' || chr(305) || 'ng',            'Homing'),
    ('Sh' || chr(305) || 'eld Charge',     'Shield Charge'),
    ('Sh' || chr(305) || 'elds Up',        'Shields Up')
ON CONFLICT (dotless) DO NOTHING;

-- ── Surrogate-key tables: plain UPDATE is safe (no uniqueness on name) ──────
DO $$
DECLARE
    t TEXT;
    n BIGINT;
BEGIN
    FOREACH t IN ARRAY ARRAY['match_cards','card_offers','ffa_match_cards',
                             'ffa_card_offers','ovt_match_cards','team_match_cards']
    LOOP
        IF to_regclass(t) IS NULL THEN
            RAISE NOTICE 'migration 198: table % absent, skipped', t;
            CONTINUE;
        END IF;
        EXECUTE format(
            'UPDATE %I tgt SET card_name = m.canon
               FROM _dotless_map2 m
              WHERE tgt.card_name = m.dotless', t);
        GET DIAGNOSTICS n = ROW_COUNT;
        RAISE NOTICE 'migration 198: % rows merged in %', n, t;
    END LOOP;
END $$;

-- ── player_card_tiers: card_name is part of the PRIMARY KEY ─────────────────
-- Same two-stage collision handling as 195 (drop sources that would collide
-- with an existing canonical row, then collapse many-to-one, then rename).
-- Expected to be a no-op here — the sweep found zero dotless tier rows — but a
-- rename onto an occupied key is a hard abort, so the guard stays.
DO $$
DECLARE
    n BIGINT;
BEGIN
    IF to_regclass('player_card_tiers') IS NULL THEN
        RAISE NOTICE 'migration 198: player_card_tiers absent, skipped';
        RETURN;
    END IF;

    DELETE FROM player_card_tiers t
     USING _dotless_map2 m
     WHERE t.card_name = m.dotless
       AND EXISTS (SELECT 1 FROM player_card_tiers c
                    WHERE c.player_id = t.player_id
                      AND c.filter    = t.filter
                      AND c.card_name = m.canon);
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE 'migration 198: % player_card_tiers rows dropped (canonical already present)', n;

    DELETE FROM player_card_tiers t
     USING (
        SELECT t2.ctid AS victim
          FROM player_card_tiers t2
          JOIN _dotless_map2 m2 ON t2.card_name = m2.dotless
         WHERE t2.ctid <> (
                SELECT MIN(t3.ctid)
                  FROM player_card_tiers t3
                  JOIN _dotless_map2 m3 ON t3.card_name = m3.dotless
                 WHERE t3.player_id = t2.player_id
                   AND t3.filter    = t2.filter
                   AND m3.canon     = m2.canon)
     ) dup
     WHERE t.ctid = dup.victim;
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE 'migration 198: % player_card_tiers rows dropped (many-to-one collapse)', n;

    UPDATE player_card_tiers t SET card_name = m.canon
      FROM _dotless_map2 m
     WHERE t.card_name = m.dotless;
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE 'migration 198: % player_card_tiers rows merged', n;
END $$;

-- ── Post-check ─────────────────────────────────────────────────────────────
-- Deliberately BROADER than 195's: it asserts that NO dotless name remains in
-- any card table at all, not merely that this file's own three are gone. A
-- post-check scoped to its own allowlist is exactly what let 195 pass while
-- leaving rows behind, so this one would fail loudly on a fourth missed name.
--
-- That makes it a genuine completeness assertion for the whole class as of this
-- release. If a legitimate mod card ever legitimately contains U+0131 this will
-- start failing — that is the correct moment to revisit it deliberately, rather
-- than discovering months of silently split history.
DO $$
DECLARE
    t TEXT;
    leftover BIGINT;
    total BIGINT := 0;
    detail TEXT := '';
BEGIN
    FOREACH t IN ARRAY ARRAY['match_cards','card_offers','ffa_match_cards',
                             'ffa_card_offers','ovt_match_cards','team_match_cards',
                             'player_card_tiers']
    LOOP
        IF to_regclass(t) IS NULL THEN CONTINUE; END IF;
        EXECUTE format(
            'SELECT COUNT(*) FROM %I WHERE card_name LIKE ''%%'' || chr(305) || ''%%''', t)
            INTO leftover;
        total := total + leftover;
        IF leftover > 0 THEN
            detail := detail || format(' %s=%s', t, leftover);
        END IF;
    END LOOP;

    IF total > 0 THEN
        RAISE EXCEPTION 'migration 198 post-check FAILED: % dotless card row(s) remain:%', total, detail;
    END IF;
    RAISE NOTICE 'migration 198 post-check OK — zero dotless card names remain in any card table';
END $$;

COMMIT;
