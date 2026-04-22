-- v1.23.x — Consolidate all observed near-duplicate card_name rows into their canonical
-- form. Third time this has happened (Poison was migration 043; Pristine this pass is the
-- biggest offender). Root cause: at least one code path (OnOpponentCardPicked) stored
-- opponent card names without going through CardRarityLookup.GetCanonicalName, leaving
-- ROUNDS' raw GameObject form in the DB. Fixed in-code this pass; this migration cleans
-- up the historical split.
--
-- Mappings come straight from the hardAliases dictionary in Plugin.cs
-- (CardRarityLookup). Anything else that splits in the future should be added here and
-- to the alias map simultaneously.
--
-- Idempotent — each UPDATE is a no-op after the first run.

DO $$
DECLARE
    alias RECORD;
    n_offers integer;
    n_cards integer;
    total_offers integer := 0;
    total_cards integer := 0;
BEGIN
    FOR alias IN SELECT * FROM (VALUES
        -- (variant, canonical)
        ('Leach',                   'Leech'),
        ('Riccochet',               'Ricochet'),
        ('BombsAway',               'Bombs Away'),
        ('Glasscannon',             'Glass Cannon'),
        ('ShieldCharge',            'Shield Charge'),
        ('Abyssalcountdown',        'Abyssal Countdown'),
        ('AbyssalCountdown',        'Abyssal Countdown'),
        ('Chillingpresence',        'Chilling Presence'),
        ('ChillingPresence',        'Chilling Presence'),
        ('Drillammo',               'Drill Ammo'),
        ('DrillAmmo',               'Drill Ammo'),
        ('Radarshot',               'Radar Shot'),
        ('RadarShot',               'Radar Shot'),
        ('Targetbounce',            'Target Bounce'),
        ('TargetBounce',            'Target Bounce'),
        ('Tasteofblood',            'Taste Of Blood'),
        ('TasteOfBlood',            'Taste Of Blood'),
        ('Fastball',                'Fast Ball'),
        ('Poison Bullets',          'Poison'),
        ('PoisonBullets',           'Poison'),
        ('Prisitne Perseverence',   'Pristine Perseverance'),
        ('Pristine Perseverence',   'Pristine Perseverance'),
        ('PristinePerseverance',    'Pristine Perseverance'),
        ('PristinePerseverence',    'Pristine Perseverance')
    ) AS v(variant, canonical) LOOP
        UPDATE card_offers SET card_name = alias.canonical WHERE card_name = alias.variant;
        GET DIAGNOSTICS n_offers = ROW_COUNT;
        UPDATE match_cards SET card_name = alias.canonical WHERE card_name = alias.variant;
        GET DIAGNOSTICS n_cards = ROW_COUNT;
        IF (n_offers > 0 OR n_cards > 0) THEN
            RAISE NOTICE '  %: % offers + % match_cards merged into %', alias.variant, n_offers, n_cards, alias.canonical;
        END IF;
        total_offers := total_offers + n_offers;
        total_cards := total_cards + n_cards;
    END LOOP;
    RAISE NOTICE 'Total: % card_offers + % match_cards consolidated', total_offers, total_cards;
END $$;
