-- 178: FFA card-offer log (§10 measurement prerequisite).
--
-- card_offers.match_id FKs to matches(id), so FFA games cannot ride the 1v1
-- table — parallel table keyed to ffa_matches. Append-only telemetry: no
-- uniques beyond the pk, rows are bounded per report at ingest (the offers
-- list is client-supplied and OUTSIDE the HMAC canonical).
--
-- MUST run BEFORE the API deploy that writes it (learning #235's ordering).

CREATE TABLE IF NOT EXISTS ffa_card_offers (
    id          BIGSERIAL PRIMARY KEY,
    match_id    UUID NOT NULL REFERENCES ffa_matches(id) ON DELETE CASCADE,
    player_id   UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    card_name   VARCHAR(64) NOT NULL,
    was_picked  BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_ffa_card_offers_match  ON ffa_card_offers (match_id);
CREATE INDEX IF NOT EXISTS ix_ffa_card_offers_card   ON ffa_card_offers (card_name);

DO $$ BEGIN RAISE NOTICE '178 ffa_card_offers: post-check OK'; END $$;
