-- 353: Player Cards trading -- the schema of player-to-player card trades.
--
-- Cards for cards only: a trade moves prints between two binders and nothing
-- else (no gold, no shards, no packs, no rating). This file carries the
-- schema only; every tunable (caps, cooldowns, windows) lives in
-- player_cards.PC_TRADE, never here.
--
--   players.pc_trades_open        the trader-side switch, a third key of the
--                                 existing settings compare-and-set.
--   players.pc_trades_generation  its consent generation: every write of
--                                 "off" bumps it, a proposal stamps both
--                                 parties' values, and the accept refuses a
--                                 trade whose party has moved on.
--   pc_prints.acquired_by_trade   permanent provenance, set by a trade's move
--                                 and by nothing else; a print ever received
--                                 by trade discards for
--                                 PC_TRADE["traded_discard_shards"] (0).
--                                 PERMANENT: no later migration may drop or
--                                 rename it -- the api reads its absence as
--                                 "never installed" and pays the pre-trading
--                                 discard value on that reading alone.
--   pc_trades                     one row per proposal; its terms never change
--                                 after the insert, and its status moves only
--                                 along a whitelist (pc_trades_guard).
--   pc_trade_spent_nonces         the idempotency record of a proposal; it
--                                 outlives the trade row on purpose (no
--                                 foreign key), and only the data deletion of
--                                 its proposer removes it.
--   pc_trade_holds                one row per print on the PROPOSER's side of
--                                 an open trade: a print is offered in at most
--                                 one open trade.
--
-- Six triggers: pc_trades_guard, pc_trades_release_holds,
-- pc_trades_no_executing_commit (deferred: an 'executing' row cannot
-- outlive its transaction), pc_trade_holds_guard, pc_cards_immutable (a
-- card's subject never changes), and pc_prints_immutable re-created with
-- 308's body unchanged plus one rule for acquired_by_trade. The closing DO
-- block proves the one-open-proposal-per-pair index exists and all six are
-- armed before this transaction may commit (a positive signal, #438).
--
-- DEPLOY ORDER: THIS FILE FIRST -- then the api that carries the trade
-- routes, primary first, then the standby. The api before this file is safe
-- too: its schema probe reads schema_missing, every trade route answers 503
-- trading_unavailable, a settings write of the new trades_open key answers
-- 503 trading_unavailable (the build before it answered 422 for a key it did
-- not know), and every other route this release modified behaves as it did
-- before trading. The trade janitor step skips until the probe finds the
-- schema, but the boot janitor self-test EXPLAINs its statements and
-- reports them failed (relation does not exist) until the api's first
-- boot after this file: a report, not a behaviour, and the reason this
-- file goes first. Safe before the api in the other direction as well:
-- the running api never names anything here, its discard and ownership
-- writes leave the new flag alone, and its mint's card upsert rewrites
-- variant to the value it already has, which pc_cards_immutable admits.
--
-- Additive and re-runnable: IF NOT EXISTS on every column, table and index,
-- CREATE OR REPLACE on every function, DROP TRIGGER IF EXISTS before every
-- trigger; one explicit transaction (#340) with a bounded lock wait.

BEGIN;

SET LOCAL lock_timeout = '5s';

ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_trades_open BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_trades_generation INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pc_prints ADD COLUMN IF NOT EXISTS acquired_by_trade BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS pc_trades (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pair_lo        UUID NOT NULL REFERENCES players(id),
    pair_hi        UUID NOT NULL REFERENCES players(id),
    proposer       UUID NOT NULL REFERENCES players(id),
    a_prints       UUID[] NOT NULL,          -- what pair_lo gives, strictly ascending
    b_prints       UUID[] NOT NULL,          -- what pair_hi gives, strictly ascending
    digest         TEXT NOT NULL,            -- sha256 hex of the canonical item list (2.6)
    propose_nonce  TEXT NOT NULL,
    proposer_generation     INTEGER NOT NULL,  -- the proposer's pc_trades_generation at propose (F4)
    counterparty_generation INTEGER NOT NULL,  -- the other party's, read under the same lock
    status         TEXT NOT NULL DEFAULT 'proposed',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL,
    closed_at      TIMESTAMPTZ NULL,
    closed_by      UUID NULL REFERENCES players(id),
    close_nonce    TEXT NULL,
    void_reason    TEXT NULL,
    executed_at    TIMESTAMPTZ NULL,
    reversed_at    TIMESTAMPTZ NULL,
    reversed_by    TEXT NULL,                -- the admin's steam id, TEXT like admin_actions (028)
    CONSTRAINT pc_trades_pair_order CHECK (pair_lo < pair_hi),
    CONSTRAINT pc_trades_proposer_in_pair CHECK (proposer IN (pair_lo, pair_hi)),
    CONSTRAINT pc_trades_status_word CHECK (status IN ('proposed', 'executing', 'executed', 'declined',
                                                       'cancelled', 'expired', 'void', 'reversed')),
    CONSTRAINT pc_trades_two_sides CHECK (cardinality(a_prints) >= 1 AND cardinality(b_prints) >= 1
                                          AND NOT (a_prints && b_prints)),
    CONSTRAINT pc_trades_nonce_word CHECK (propose_nonce ~ '^[A-Za-z0-9_-]{8,64}$'),
    CONSTRAINT pc_trades_expiry CHECK (expires_at > created_at),
    CONSTRAINT pc_trades_stamps CHECK (
           (status IN ('proposed', 'executing') AND closed_at IS NULL AND executed_at IS NULL)
        OR (status IN ('executed', 'reversed') AND executed_at IS NOT NULL AND closed_at IS NOT NULL)
        OR (status IN ('declined', 'cancelled', 'expired', 'void') AND closed_at IS NOT NULL AND executed_at IS NULL)),
    CONSTRAINT pc_trades_reversal_stamps CHECK ((status = 'reversed') = (reversed_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS pc_trades_one_open_per_pair ON pc_trades (pair_lo, pair_hi) WHERE status = 'proposed';
CREATE UNIQUE INDEX IF NOT EXISTS pc_trades_proposer_nonce ON pc_trades (proposer, propose_nonce);
CREATE INDEX IF NOT EXISTS pc_trades_lo ON pc_trades (pair_lo, status);
CREATE INDEX IF NOT EXISTS pc_trades_hi ON pc_trades (pair_hi, status);
CREATE INDEX IF NOT EXISTS pc_trades_open_expiry ON pc_trades (expires_at) WHERE status = 'proposed';
CREATE INDEX IF NOT EXISTS pc_trades_executed_at ON pc_trades (executed_at) WHERE status IN ('executed', 'reversed');

CREATE TABLE IF NOT EXISTS pc_trade_spent_nonces (          -- revision 2, F2
    proposer      UUID NOT NULL REFERENCES players(id),
    propose_nonce TEXT NOT NULL,
    trade_id      UUID NOT NULL,                            -- no foreign key: it outlives the trade row on purpose
    spent_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (proposer, propose_nonce)
);

CREATE TABLE IF NOT EXISTS pc_trade_holds (
    print_id  UUID PRIMARY KEY,
    trade_id  UUID NOT NULL REFERENCES pc_trades(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS pc_trade_holds_trade ON pc_trade_holds (trade_id);

-- 1. pc_trades_guard. On INSERT: born 'proposed', no closing stamp, both
-- sides one-dimensional and strictly ascending (no NULL, no duplicate). On
-- UPDATE: the terms are immutable, and (OLD.status, NEW.status) is one of the
-- seven transitions of the status machine; anything else raises.
CREATE OR REPLACE FUNCTION pc_trades_guard() RETURNS trigger AS $$
DECLARE
    i integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status IS DISTINCT FROM 'proposed' THEN
            RAISE EXCEPTION 'pc_trades: a trade is inserted as proposed, not %', NEW.status;
        END IF;
        IF NEW.closed_at IS NOT NULL OR NEW.closed_by IS NOT NULL OR NEW.close_nonce IS NOT NULL
           OR NEW.void_reason IS NOT NULL OR NEW.executed_at IS NOT NULL
           OR NEW.reversed_at IS NOT NULL OR NEW.reversed_by IS NOT NULL THEN
            RAISE EXCEPTION 'pc_trades: a new trade carries no closing stamp';
        END IF;
        IF array_ndims(NEW.a_prints) IS DISTINCT FROM 1 OR array_ndims(NEW.b_prints) IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION 'pc_trades: each side is a one-dimensional list of print ids';
        END IF;
        FOR i IN array_lower(NEW.a_prints, 1) .. array_upper(NEW.a_prints, 1) LOOP
            IF NEW.a_prints[i] IS NULL
               OR (i > array_lower(NEW.a_prints, 1) AND NEW.a_prints[i - 1] >= NEW.a_prints[i]) THEN
                RAISE EXCEPTION 'pc_trades: a_prints must be strictly ascending, with no NULL or duplicate';
            END IF;
        END LOOP;
        FOR i IN array_lower(NEW.b_prints, 1) .. array_upper(NEW.b_prints, 1) LOOP
            IF NEW.b_prints[i] IS NULL
               OR (i > array_lower(NEW.b_prints, 1) AND NEW.b_prints[i - 1] >= NEW.b_prints[i]) THEN
                RAISE EXCEPTION 'pc_trades: b_prints must be strictly ascending, with no NULL or duplicate';
            END IF;
        END LOOP;
        RETURN NEW;
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.pair_lo IS DISTINCT FROM OLD.pair_lo
       OR NEW.pair_hi IS DISTINCT FROM OLD.pair_hi
       OR NEW.proposer IS DISTINCT FROM OLD.proposer
       OR NEW.a_prints IS DISTINCT FROM OLD.a_prints
       OR NEW.b_prints IS DISTINCT FROM OLD.b_prints
       OR NEW.digest IS DISTINCT FROM OLD.digest
       OR NEW.propose_nonce IS DISTINCT FROM OLD.propose_nonce
       OR NEW.proposer_generation IS DISTINCT FROM OLD.proposer_generation
       OR NEW.counterparty_generation IS DISTINCT FROM OLD.counterparty_generation
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.expires_at IS DISTINCT FROM OLD.expires_at THEN
        RAISE EXCEPTION 'pc_trades: the terms of a trade never change after the proposal';
    END IF;
    IF NOT ((OLD.status || '->' || NEW.status) = ANY (ARRAY[
            'proposed->executing', 'proposed->declined', 'proposed->cancelled', 'proposed->expired',
            'proposed->void', 'executing->executed', 'executed->reversed'])) THEN
        RAISE EXCEPTION 'pc_trades: % -> % is not a status transition', OLD.status, NEW.status;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS pc_trades_guard ON pc_trades;
CREATE TRIGGER pc_trades_guard BEFORE INSERT OR UPDATE ON pc_trades
    FOR EACH ROW EXECUTE FUNCTION pc_trades_guard();

-- 2. pc_trades_release_holds. Every exit from 'proposed' releases the trade's
-- holds -- the accept's move to 'executing' included, which a rollback undoes
-- together with this delete -- so no exit path added later can strand a
-- print. A deleted trade row releases its holds through the cascade.
CREATE OR REPLACE FUNCTION pc_trades_release_holds() RETURNS trigger AS $$
BEGIN
    DELETE FROM pc_trade_holds WHERE trade_id = NEW.id;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS pc_trades_release_holds ON pc_trades;
CREATE TRIGGER pc_trades_release_holds AFTER UPDATE OF status ON pc_trades
    FOR EACH ROW WHEN (OLD.status = 'proposed' AND NEW.status <> 'proposed')
    EXECUTE FUNCTION pc_trades_release_holds();

-- 3. pc_trades_no_executing_commit. At commit it re-reads the row by id (not
-- NEW, the version the queued event saw) and raises while it is still
-- 'executing': that state cannot outlive the transaction that entered it.
CREATE OR REPLACE FUNCTION pc_trades_no_executing_commit() RETURNS trigger AS $$
DECLARE
    st text;
BEGIN
    SELECT t.status INTO st FROM pc_trades t WHERE t.id = NEW.id;
    IF st = 'executing' THEN
        RAISE EXCEPTION 'pc_trades: trade % is still executing at commit', NEW.id;
    END IF;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS pc_trades_no_executing_commit ON pc_trades;
CREATE CONSTRAINT TRIGGER pc_trades_no_executing_commit AFTER INSERT OR UPDATE ON pc_trades
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION pc_trades_no_executing_commit();

-- 4. pc_trade_holds_guard. A hold names a 'proposed' trade and a print on
-- that trade's PROPOSER side; the requested side is never held.
CREATE OR REPLACE FUNCTION pc_trade_holds_guard() RETURNS trigger AS $$
DECLARE
    st text;
    side uuid[];
BEGIN
    SELECT t.status, CASE WHEN t.proposer = t.pair_lo THEN t.a_prints ELSE t.b_prints END
      INTO st, side
      FROM pc_trades t
     WHERE t.id = NEW.trade_id;
    IF st IS DISTINCT FROM 'proposed' THEN
        RAISE EXCEPTION 'pc_trade_holds: trade % is not proposed', NEW.trade_id;
    END IF;
    IF NEW.print_id IS NULL OR NOT (NEW.print_id = ANY (side)) THEN
        RAISE EXCEPTION 'pc_trade_holds: print % is not on the proposer side of trade %', NEW.print_id, NEW.trade_id;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS pc_trade_holds_guard ON pc_trade_holds;
CREATE TRIGGER pc_trade_holds_guard BEFORE INSERT ON pc_trade_holds
    FOR EACH ROW EXECUTE FUNCTION pc_trade_holds_guard();

-- 5. pc_cards_immutable. A card's identity never changes after insert, so a
-- print's subject never does either (the trade routes choose their identity
-- locks from one plain read of it). The mint's upsert (ON CONFLICT ... DO
-- UPDATE SET variant = EXCLUDED.variant) rewrites variant to the value it
-- already has, which this admits.
CREATE OR REPLACE FUNCTION pc_cards_immutable() RETURNS trigger AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.subject_player_id IS DISTINCT FROM OLD.subject_player_id
       OR NEW.edition_id IS DISTINCT FROM OLD.edition_id
       OR NEW.variant IS DISTINCT FROM OLD.variant
       OR NEW.first_minted_at IS DISTINCT FROM OLD.first_minted_at THEN
        RAISE EXCEPTION 'pc_cards is immutable: id, subject_player_id, edition_id, variant and first_minted_at never change';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS pc_cards_immutable ON pc_cards;
CREATE TRIGGER pc_cards_immutable BEFORE UPDATE ON pc_cards
    FOR EACH ROW EXECUTE FUNCTION pc_cards_immutable();

-- pc_prints_immutable: 308's body unchanged, plus one rule before RETURN NEW.
-- acquired_by_trade may change only from false to true, in an UPDATE that
-- also changes owner_player_id and leaves discarded_at and discard_shards as
-- they were -- a trade's move, and nothing else; nothing can clear it. The
-- trigger itself stays exactly as 308 declares it (BEFORE UPDATE, no column
-- list), re-created unchanged.
CREATE OR REPLACE FUNCTION pc_prints_immutable() RETURNS trigger AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.card_id IS DISTINCT FROM OLD.card_id
       OR NEW.minted_at IS DISTINCT FROM OLD.minted_at
       OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
       OR NEW.rarity IS DISTINCT FROM OLD.rarity
       OR NEW.foil IS DISTINCT FROM OLD.foil
       OR NEW.signed IS DISTINCT FROM OLD.signed
       OR NEW.pool_rank IS DISTINCT FROM OLD.pool_rank
       OR NEW.rating IS DISTINCT FROM OLD.rating
       OR NEW.peak_rating IS DISTINCT FROM OLD.peak_rating
       OR NEW.board_rank IS DISTINCT FROM OLD.board_rank
       OR NEW.series_wins IS DISTINCT FROM OLD.series_wins
       OR NEW.series_losses IS DISTINCT FROM OLD.series_losses
       OR NEW.top_card IS DISTINCT FROM OLD.top_card
       OR NEW.title IS DISTINCT FROM OLD.title
       OR NEW.source IS DISTINCT FROM OLD.source
       OR NEW.pack_id IS DISTINCT FROM OLD.pack_id
       OR NEW.slot IS DISTINCT FROM OLD.slot THEN
        RAISE EXCEPTION 'pc_prints is immutable except owner_player_id, discarded_at and discard_shards';
    END IF;
    IF OLD.discarded_at IS NOT NULL
       AND (NEW.discarded_at IS DISTINCT FROM OLD.discarded_at
            OR NEW.discard_shards IS DISTINCT FROM OLD.discard_shards
            OR NEW.owner_player_id IS DISTINCT FROM OLD.owner_player_id) THEN
        RAISE EXCEPTION 'a discarded print cannot change';
    END IF;
    IF NEW.acquired_by_trade IS DISTINCT FROM OLD.acquired_by_trade
       AND NOT (OLD.acquired_by_trade IS FALSE AND NEW.acquired_by_trade IS TRUE
                AND NEW.owner_player_id IS DISTINCT FROM OLD.owner_player_id
                AND NEW.discarded_at IS NOT DISTINCT FROM OLD.discarded_at
                AND NEW.discard_shards IS NOT DISTINCT FROM OLD.discard_shards) THEN
        RAISE EXCEPTION 'acquired_by_trade is set by a trade''s move and by nothing else, and is never cleared';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS pc_prints_immutable ON pc_prints;
CREATE TRIGGER pc_prints_immutable BEFORE UPDATE ON pc_prints
    FOR EACH ROW EXECUTE FUNCTION pc_prints_immutable();

-- Positive signal, not absence of error (#438): the one-open-proposal-per-
-- pair index exists as a UNIQUE PARTIAL index on pc_trades, and every one of
-- the six triggers is armed, before this transaction may commit.
DO $$
DECLARE
    st   "char";
    uniq boolean;
    part boolean;
    tbl  regclass;
    trig text;
BEGIN
    SELECT i.indisunique, i.indpred IS NOT NULL, i.indrelid::regclass
      INTO uniq, part, tbl
      FROM pg_index i
     WHERE i.indexrelid = to_regclass('pc_trades_one_open_per_pair');
    IF uniq IS DISTINCT FROM true OR part IS DISTINCT FROM true OR tbl IS DISTINCT FROM 'pc_trades'::regclass THEN
        RAISE EXCEPTION 'pc_trades_one_open_per_pair is not a unique partial index on pc_trades (unique=%, partial=%, table=%) -- refusing to commit', uniq, part, tbl;
    END IF;
    FOREACH trig IN ARRAY ARRAY[
            'pc_trades.pc_trades_guard', 'pc_trades.pc_trades_release_holds',
            'pc_trades.pc_trades_no_executing_commit', 'pc_trade_holds.pc_trade_holds_guard',
            'pc_cards.pc_cards_immutable', 'pc_prints.pc_prints_immutable'] LOOP
        st := NULL;
        SELECT g.tgenabled INTO st
          FROM pg_trigger g
         WHERE g.tgrelid = split_part(trig, '.', 1)::regclass
           AND g.tgname = split_part(trig, '.', 2);
        IF st IS DISTINCT FROM 'O' THEN
            RAISE EXCEPTION 'trigger % missing or not armed (tgenabled=%) -- refusing to commit', trig, st;
        END IF;
    END LOOP;
    RAISE NOTICE 'pc_trades: one-open-per-pair index present, six triggers armed';
END $$;

COMMIT;
