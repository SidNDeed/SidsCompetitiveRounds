-- 014_card_offers.sql
--
-- Pass-tracking schema. The mod sends, per match round, the set of cards a
-- player was offered plus which one they picked. From this we derive a
-- per-card "pass rate" — how often a card is rejected when offered, the
-- complement of pick rate over offerings.
--
-- Existing match_cards remains the source of truth for what was actually
-- picked. card_offers is purely additive — older matches without this data
-- simply have no offer rows.

CREATE TABLE IF NOT EXISTS card_offers (
    id           BIGSERIAL PRIMARY KEY,
    match_id     UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id    UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    card_name    VARCHAR(64) NOT NULL,
    was_picked   BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_card_offers_card    ON card_offers (card_name);
CREATE INDEX IF NOT EXISTS idx_card_offers_player  ON card_offers (player_id);
CREATE INDEX IF NOT EXISTS idx_card_offers_match   ON card_offers (match_id);
