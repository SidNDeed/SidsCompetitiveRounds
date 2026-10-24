"""The production-faithful schema the title-ladders migrations (365, 366) are
executed against, for test_title_ladders_five_tier.py and the lane dry runs.

Rebuilt from the PRIMARY's own catalogue (information_schema.columns and
pg_get_functiondef, read-only, 2026-10-01) for exactly the objects 331, 365
and 366 touch: shop_items with both of its triggers, players (the columns
these files read or write), player_items, gold_transactions, and the one
table the catalog-release trigger reads (cosmetic_submissions). Then 331 is
applied as production applied it, and the existing shop titles the new
catalogue reuses are seeded with the values their live rows carry.

Not a copy of the whole schema: a prerequisite block that grows into one is a
second source of truth for it.
"""
import os

SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")

BASE = """
CREATE TABLE shop_items (
    id                BIGSERIAL PRIMARY KEY,
    sku               VARCHAR(64) UNIQUE NOT NULL,
    kind              VARCHAR(16) NOT NULL,
    name              VARCHAR(128) NOT NULL,
    description       VARCHAR(256),
    price             INTEGER NOT NULL,
    rarity            VARCHAR(16) NOT NULL DEFAULT 'common',
    rotation_pool     VARCHAR(32),
    preview_color     VARCHAR(16),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    artist_steam_id   VARCHAR(20),
    stock_limit       INTEGER,
    released_at       TIMESTAMPTZ,
    catalog_ready     BOOLEAN NOT NULL DEFAULT TRUE,
    music_track_count SMALLINT);
CREATE TABLE players (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    steam_id         VARCHAR(20) NOT NULL UNIQUE,
    display_name     VARCHAR(64) NOT NULL,
    deleted_at       TIMESTAMPTZ,
    gold_earned      INTEGER NOT NULL DEFAULT 0,
    gold_spent       INTEGER NOT NULL DEFAULT 0,
    active_title_id  BIGINT REFERENCES shop_items(id) ON DELETE SET NULL);
CREATE TABLE player_items (
    player_id               UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    item_id                 BIGINT NOT NULL REFERENCES shop_items(id) ON DELETE CASCADE,
    purchased_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    purchase_price          INTEGER NOT NULL,
    royalty_paid            INTEGER,
    royalty_rate_pct        SMALLINT,
    royalty_artist_steam_id VARCHAR(20),
    royalty_resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (player_id, item_id));
CREATE TABLE gold_transactions (
    id           BIGSERIAL PRIMARY KEY,
    player_id    UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    amount       INTEGER NOT NULL,
    reason       VARCHAR(64) NOT NULL,
    reference_id TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE cosmetic_submissions (
    shop_sku                     VARCHAR(64),
    status                       VARCHAR(16),
    approved_placement_revision  INTEGER,
    published_placement_revision INTEGER NOT NULL DEFAULT 0);

CREATE FUNCTION stamp_shop_item_catalog_release() RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE
    approved_rev INTEGER;
BEGIN
    IF NEW.catalog_ready AND NOT OLD.catalog_ready THEN
        IF EXISTS (
            SELECT 1 FROM cosmetic_submissions cs WHERE cs.shop_sku = NEW.sku
        ) THEN
            SELECT cs.approved_placement_revision INTO approved_rev
            FROM cosmetic_submissions cs
            WHERE cs.shop_sku = NEW.sku
              AND cs.status = 'approved'
              AND cs.approved_placement_revision IS NOT NULL
            ORDER BY cs.approved_placement_revision DESC
            LIMIT 1;
            IF approved_rev IS NULL THEN
                RAISE EXCEPTION
                    'catalog_ready requires an admin-approved cosmetic placement revision for %', NEW.sku;
            END IF;
            UPDATE cosmetic_submissions
            SET published_placement_revision = approved_rev
            WHERE shop_sku = NEW.sku
              AND status = 'approved'
              AND approved_placement_revision = approved_rev
              AND published_placement_revision < approved_rev;
        END IF;
        IF NEW.released_at IS NULL THEN
            NEW.released_at = NOW();
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;
CREATE FUNCTION gate_new_face_shop_item() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    IF NEW.kind = 'face' AND NEW.catalog_ready THEN
        NEW.catalog_ready = FALSE;
        NEW.released_at = NULL;
    END IF;
    RETURN NEW;
END;
$function$;
CREATE TRIGGER trg_shop_item_catalog_release BEFORE UPDATE OF catalog_ready ON shop_items
    FOR EACH ROW EXECUTE FUNCTION stamp_shop_item_catalog_release();
CREATE TRIGGER trg_gate_new_face_shop_item BEFORE INSERT ON shop_items
    FOR EACH ROW EXECUTE FUNCTION gate_new_face_shop_item();
"""

# The live rows of every existing shop title the catalogue reuses, plus the
# two titles 366 retires and two that stay single (a control: 365 must not
# touch them). Values as the primary holds them (read-only, 2026-10-01).
EXISTING_TITLES = """
INSERT INTO shop_items (sku, kind, name, description, price, rarity, rotation_pool, catalog_ready, preview_color) VALUES
    ('title_active', 'title', 'Active', 'More ranked than not.', 500, 'common', NULL, TRUE, '#44CC88'),
    ('title_apex', 'title', 'Apex', 'Top of the food chain', 4500, 'epic', NULL, TRUE, '#FFAA00'),
    ('title_beginner', 'title', 'Noobie', 'Everyone starts somewhere.', 500, 'common', NULL, TRUE, '#AAAAAA'),
    ('title_berserker', 'title', 'Berserker', 'Pure aggression', 3000, 'rare', NULL, TRUE, '#FF3333'),
    ('title_blitz', 'title', 'Blitz', 'Fast finisher', 2500, 'rare', NULL, TRUE, '#FFEE33'),
    ('title_bouncer', 'title', 'Bouncer', 'Target Bounce main', 2000, 'rare', NULL, TRUE, '#BBDD44'),
    ('title_bouncy', 'title', 'Bouncy', 'Bouncy main', 1500, 'rare', NULL, TRUE, '#66CCEE'),
    ('title_clown', 'title', 'Clown', 'Honk honk.', 800, 'common', NULL, TRUE, '#FF6688'),
    ('title_decent', 'title', 'Decent', 'Not great. Not terrible.', 1000, 'uncommon', NULL, TRUE, '#88CC44'),
    ('title_echo', 'title', 'Echo', 'Echo main', 2000, 'rare', NULL, TRUE, '#88FFCC'),
    ('title_gold_rush', 'title', 'Royal', 'Worn by those who climbed the mountain.', 10000, 'legendary', NULL, TRUE, '#FFD94D'),
    ('title_grandma', 'title', 'Grandma', 'Wise beyond your years.', 1000, 'uncommon', NULL, TRUE, '#FF66EE'),
    ('title_grandmaster', 'title', 'Expert', 'Few reach it. Fewer afford the title.', 5000, 'legendary', NULL, TRUE, '#FF66EE'),
    ('title_hasty', 'title', 'Hasty', 'Fast Forward main', 1500, 'rare', NULL, TRUE, '#FF6633'),
    ('title_healer', 'title', 'Healer', 'Healing Field main', 2000, 'rare', NULL, TRUE, '#44DD99'),
    ('title_huge', 'title', 'Huge', 'Huge main', 1500, 'rare', NULL, TRUE, '#FFCC33'),
    ('title_idiot', 'title', 'Idiot', 'Self-awareness is a virtue.', 1000, 'uncommon', NULL, TRUE, '#DDAA33'),
    ('title_pacifist', 'title', 'Pacifist', 'Wins without firing', 3000, 'rare', NULL, TRUE, '#FFFFFF'),
    ('title_phoenix', 'title', 'Phoenix', 'Reborn after defeat', 3500, 'epic', NULL, TRUE, '#FF8833'),
    ('title_poisoner', 'title', 'Poisoner', 'Poison main', 1500, 'rare', NULL, TRUE, '#66CC44'),
    ('title_pronoun_he', 'title', 'He/him', 'Pronoun title.', 100, 'common', NULL, TRUE, '#EEEEEE'),
    ('title_pronoun_she', 'title', 'She/her', 'Pronoun title.', 100, 'common', NULL, TRUE, '#EEEEEE'),
    ('title_pronoun_they', 'title', 'They/them', 'Pronoun title.', 100, 'common', NULL, TRUE, '#EEEEEE'),
    ('title_regular', 'title', 'Regular', 'You show up.', 500, 'common', NULL, TRUE, '#FFFFFF'),
    ('title_reloader', 'title', 'Reloader', 'Quick Reload main', 1500, 'rare', NULL, TRUE, '#99CCDD'),
    ('title_sniper', 'title', 'Sniper', 'Precision shooter', 2500, 'rare', NULL, TRUE, '#88CCFF'),
    ('title_specter', 'title', 'Specter', 'Hard to hit', 3500, 'epic', NULL, TRUE, '#AABBFF'),
    ('title_sweaty', 'title', 'Sweaty', 'Sweat is just XP in liquid form.', 1500, 'rare', NULL, TRUE, '#FFCC33'),
    ('title_tank', 'title', 'Tank', 'Eats damage', 2500, 'rare', NULL, TRUE, '#88AA88'),
    ('title_tracker', 'title', 'Tracker', 'Homing main', 2000, 'rare', NULL, TRUE, '#FF6677'),
    ('title_tryhard', 'title', 'Tryhard', 'Trying, hard.', 1500, 'rare', NULL, TRUE, '#FF9933'),
    ('title_windup', 'title', 'Windup', 'Windup main', 1500, 'rare', NULL, TRUE, '#AA66FF'),
    ('title_voidshot', 'title', 'Voidshot', 'Empty Power main', 2500, 'rare', NULL, TRUE, '#7744AA'),
    ('title_regicide', 'title', 'Kingslayer', 'For those who earned the right. Still costs a fortune.', 3000, 'rare', NULL, TRUE, '#CC3366')
ON CONFLICT (sku) DO NOTHING;
"""


# The census shape 366 refunds: one holder of title_regicide who paid the list
# price 3000 through one 'purchase' row of -3000. Every column value of the
# seeded rows is invented (identity, 8000 earned, 6000 spent, not worn; the
# worn arm is its own test), never copied from a production row.
# Plus a bystander who owns and wears a title that stays -- 366 must not touch
# either row.
CENSUS_SEED = """
INSERT INTO players (steam_id, display_name, gold_earned, gold_spent)
VALUES ('census-holder-1', 'census holder', 8000, 6000),
       ('census-bystander', 'bystander', 5000, 1000);
INSERT INTO player_items (player_id, item_id, purchase_price)
SELECT p.id, si.id, 3000 FROM players p, shop_items si
 WHERE p.steam_id = 'census-holder-1' AND si.sku = 'title_regicide';
INSERT INTO gold_transactions (player_id, amount, reason, reference_id)
SELECT p.id, -3000, 'purchase', 'title_regicide' FROM players p
 WHERE p.steam_id = 'census-holder-1';
INSERT INTO player_items (player_id, item_id, purchase_price)
SELECT p.id, si.id, 3000 FROM players p, shop_items si
 WHERE p.steam_id = 'census-bystander' AND si.sku = 'title_pacifist';
UPDATE players SET active_title_id = (SELECT id FROM shop_items WHERE sku = 'title_pacifist')
 WHERE steam_id = 'census-bystander';
"""


def migration_text(name: str) -> str:
    with open(os.path.join(SQL_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def prereq_sql() -> str:
    """BASE, then 331 exactly as it ships, then the existing titles."""
    return BASE + "\n" + migration_text("331_animal_title_ladders.sql") + "\n" + EXISTING_TITLES
