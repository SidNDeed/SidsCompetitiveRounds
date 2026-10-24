-- 330_mail_discord_relay.sql -- item 5, Mail <-> Discord relay (server+bot half)
--
-- Deployable BEFORE the 1.41.0 client ships. A 1.40.3 client never selects
-- `via` and never sends the relay flag, so every column added here is inert
-- until the api that reads it is deployed; the api is in turn inert for a
-- player with no linked Discord.
--
-- THE OUTBOX IS NOT NEW, AND THAT IS A DELIBERATE DEVIATION FROM THE PLAN.
-- PLAN.md item 5 specifies a fresh `mail_discord_outbox` table carrying
-- state ('queued'|'sending'|'sent'|'failed'), lease_until and attempts,
-- drained by a second bot poll loop, and cites learning #167 as the reason.
-- #167 is the learning that `pending_dms` (migration 129) ALREADY
-- implements, and implements in production: durable unacknowledged rows,
-- deterministic created_at order, an internal-key ack endpoint, and an
-- in-memory sent-but-unacked set so an ack retry does not repost. #167's
-- own words for the remaining window are "a crash between send and ack may
-- duplicate once, which is the correct at-least-once tradeoff" -- i.e. the
-- duplicate is the accepted outcome, not a defect to engineer away.
--
-- WHAT THIS FILE USED TO ARGUE, AND WHY IT NO LONGER DOES. An earlier
-- revision argued here that a lease was unnecessary because "the bot is a
-- singleton, so a lease would guard a concurrency that cannot happen".
-- That was a claim about the whole state space written from one state
-- (#351). Two things are wrong with it. Nothing in the runtime ENFORCES the
-- singleton -- it is a deployment convention recorded in a document, and a
-- guarantee no code checks is a guarantee the next deploy can withdraw
-- silently. And mutual exclusion was never the job: the claim added in
-- section 4 exists to give a hand-out an IDENTITY, so that the settlement
-- which arrives later can be matched to the hand-out that caused it. Two
-- processes are not required for an unidentified settlement to be applied
-- to the wrong hand-out; one process and a retry are enough.
--
-- So this migration adds what `pending_dms` genuinely lacks for this
-- feature and nothing else: which mail a row belongs to (section 3), the
-- thread name that makes a reply answerable (section 3), a durable claim
-- and attempt count (section 4), and the six indexes the new access
-- patterns need (section 5).

-- DEPLOY ORDER: this migration, then the BOT, then the api (primary, then
-- standby). Not the usual migration -> api -> bot.
--
-- The order is now a preference rather than a hazard, and the reason it was
-- once a hazard is worth recording because it is what the re-approach
-- removed. Previously the reply mapping was a Discord message id the BOT
-- reported after the fact; an old bot bare-ACKed those rows, nothing was
-- ever stamped, and every DM sent during the window promised a reply route
-- that could never work and could not be repaired afterwards, because the
-- mapping was never recorded.
--
-- The api now mints the thread name (section 3) in the same transaction
-- that composes the DM text, so a DM relayed during ANY mismatch window
-- still carries a resolvable name and becomes answerable the moment the new
-- bot lands. Both mismatch states fail into the same refusal: an old bot
-- posting the retired `use_recent` / `dm_message_id` fields to the new api,
-- and a new bot posting `relay_code` to an old api, are each read as "no
-- target named" and answered with the pick-a-thread listing.
--
-- Deploying the bot first still costs nothing: with only the migration
-- applied, no relay rows exist yet.
--
-- PREFLIGHT, between the migration and the api, against the PRIMARY:
--
--     SELECT count(*) FROM pending_dms WHERE mail_id IS NOT NULL;
--
-- It must return 0. That is not a formality -- the whole "no relay rows
-- exist yet" argument above rests on it, and the sentence is a CLAIM about a
-- window, not a fact about a database. A partial deploy, a rollback and
-- re-apply, or a second attempt after a failed run can all put rows in that
-- window; a non-zero count means relay rows were written by an api build
-- that is no longer the one about to land, and the window's reasoning does
-- not cover them. Stop and read them rather than continuing.

BEGIN;
SET LOCAL lock_timeout = '5s';

-- 1. The consent flag. Sid's decision (QUESTIONS.md #3): relay defaults ON
--    for players with a linked Discord, with off-switches in the mod's Mail
--    settings and `/mail relay off`.
--
--    DEFAULT true for EVERY row, not only linked ones, and the two facts are
--    independent on purpose: the flag means "relay when you can", and the
--    relay only fires where `discord_id IS NOT NULL`. A player who links
--    Discord next month then gets the decided default with no backfill, and
--    a player who turns the relay off BEFORE linking stays off. Storing the
--    default as "true only where currently linked" would silently re-enable
--    the second case at link time.
--
--    Explicit SQL default, not an ORM default (CLAUDE.md hard rule -- the
--    schema default is the one that wins, and `ranked_enabled` cost us this
--    lesson once already). The column IS declared on models.Player.
--
--    An earlier revision of this comment said that declaring it there "with
--    no Python-side default" keeps this line the only place the default is
--    written. That was false, and it was a false claim of the most expensive
--    kind, because the code was built on it. A column declared with NEITHER
--    a Python default NOR a `server_default` is not omitted from the ORM's
--    INSERT -- SQLAlchemy sends it explicitly as NULL, so this DEFAULT never
--    applies and the NOT NULL refuses the row. Verified by running it:
--    `INSERT ... (col) VALUES ($1)` with `None`, then NotNullViolationError;
--    the same column declared `server_default=FetchedValue()` was omitted
--    from the statement and read back afterwards. `get_or_create_player()`
--    does not set this field, so every first contact from a new Steam ID
--    would have failed at flush() once the api half landed.
--
--    models.Player therefore declares `server_default=FetchedValue()`, which
--    is what actually says "the database supplies this". Same for
--    mail_messages.via in section 2.
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS mail_discord_relay BOOLEAN NOT NULL DEFAULT true;

-- 2. Provenance on the message itself, so the 1.41.0 client can tag a reply
--    that came in from Discord. Existing rows take 'game' from the default,
--    which is true of every mail written before this migration.
ALTER TABLE mail_messages
    ADD COLUMN IF NOT EXISTS via TEXT NOT NULL DEFAULT 'game';

-- PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS and this file must stay
-- re-runnable, so the constraint is guarded on pg_constraint (same shape as
-- 332's pc_editions_planned_sane).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'ck_mail_messages_via'
                    AND conrelid = 'mail_messages'::regclass) THEN
    ALTER TABLE mail_messages ADD CONSTRAINT ck_mail_messages_via
      CHECK (via IN ('game', 'discord'));
  END IF;
END $$;

-- 3. The two columns that make `pending_dms` carry a mail relay.
--
--    `relay_code` is the DISCRIMINATOR; `mail_id` is a POINTER that may
--    become NULL. The queue is generic and has other writers (admin and
--    migration inserts), and the bot must treat a mail relay differently --
--    it appends the reply footer and the thread name. `relay_code IS NOT
--    NULL` is what tells it which kind of row it is holding, so no row needs
--    a type column and the existing writers stay untouched.
--
--    It was `mail_id IS NOT NULL` in the first draft. That is wrong the
--    moment the mail can go while the row stays, which is exactly what the
--    line below now arranges: a tombstone has mail_id NULL, and under the
--    old discriminator the drain's OPERATIONAL class would have claimed it
--    and sent a mail's body as a generic DM -- no footer, no thread name,
--    and nothing to answer.
--
--    SET NULL, not CASCADE. The earlier draft cascaded, under a comment
--    saying "mail's normal deletion is soft, so this is the abnormal path
--    only". That was false about this repo's own code:
--    `_mail_retention_sweep` (main.py) runs a HARD `DELETE FROM
--    mail_messages` hourly, and its predicate is `NOT EXISTS(live delivered
--    envelope) AND (deleted_by_sender_at IS NOT NULL OR age > 180d)` -- so
--    recipient deletes their copy, sender deletes theirs, and the mail is
--    purged at the next sweep. Minutes, not months. The cascade was the
--    NORMAL path, on a timer, and it took the thread's name with it.
--
--    What that cost was not a mis-routed reply -- the resolver INNER JOINs
--    mail_messages and refuses on anything but exactly one row, so a code
--    with no mail resolves to nothing rather than to something else. It
--    cost the ability to TELL THE TRUTH: with the row gone, "this code was
--    yours and its mail is gone" is indistinguishable from "this code is
--    not yours", and the player is told the second.
ALTER TABLE pending_dms
    ADD COLUMN IF NOT EXISTS mail_id UUID NULL
        REFERENCES mail_messages(id) ON DELETE SET NULL;

--    `relay_code` is the thread's NAME. It is minted in the same transaction
--    that composes the DM text and inserts this row, so it is durable
--    strictly BEFORE the Discord message exists. That ordering is the whole
--    design. A Discord snowflake can only be written AFTER the message it
--    names already exists, which is what every fallback deleted by this
--    revision was compensating for -- process-local maps, a content-substring
--    identity test, and a "most recent mail in 24h" inference. Learning #174
--    states the general form: request arrival time is not identity.
--
--    This replaces `dm_message_id`, which was the previous revision's reply
--    mapping and now has no reader.
--
--    RETENTION INVARIANT, restated because the first version of it was
--    false in this same file. It read "this queue has no prune today. Any
--    prune added later MUST exclude `mail_id IS NOT NULL` rows" -- and the
--    FK clause SEVENTEEN LINES ABOVE was such a prune, delivered through a
--    cascade instead of a DELETE statement. A second one already existed
--    too (the account-anonymisation sweep in main.py). An invariant a file
--    violates in its own text is worse than none: it reads as a guarantee
--    and is a description of what someone intended.
--
--    What is actually required: a row carrying `relay_code` must SURVIVE the
--    deletion of the mail it points at, because the code is printed in a
--    Discord DM that outlives this database's opinion of it. Losing the row
--    does not mis-route a reply; it makes a truthful answer impossible.
--
--    ONE exception, and it is deliberate: account anonymisation DELETES
--    these rows outright (main.py, the privacy route). The row holds the raw
--    Steam ID, the body text and the pre-anonymisation display name, so
--    erasure has to take it. That path is erasing the player, not pruning a
--    queue, and the DM it answers is the erased account's own.
ALTER TABLE pending_dms
    ADD COLUMN IF NOT EXISTS relay_code TEXT NULL;

-- 4. A DURABLE CLAIM AND A DURABLE RETRY BOUND.
--
--    `attempts` counts hand-outs that produced NO delivery. It is charged at
--    SETTLEMENT or at expiry-supersession -- never at hand-out, and never
--    decremented. Charging at hand-out is what let an api worker killed
--    after commit charge an entire batch with zero attempted sends, and what
--    made a credit-back statement necessary to undo it; that statement could
--    be replayed across requests and could cancel a LATER hand-out's charge.
--    With settlement charging 0 or 1 there is nothing to give back, and
--    ck_pending_dms_attempts_nonneg below is the standing proof that no
--    decrement was reintroduced -- it turns "check that nobody added one
--    back" from a review chore into something the database refuses.
--
--    `claim_id` / `claim_until` give a hand-out an IDENTITY. The settlement
--    that arrives later quotes the claim it is settling, and a settlement
--    quoting a claim the row no longer holds is a no-op. That is what makes
--    a replayed or superseded report harmless. `claim_until` is a BACKSTOP
--    for a bot that cannot report at all, not a mutual-exclusion timer:
--    normal release is the explicit settlement, which returns the row on the
--    very next poll.
--
--    A COLUMN rather than bot memory, so all of it survives the restart that
--    would reset an in-process counter.
--
--    `cancelled_at` records that the SENDER withdrew the mail. It is its own
--    column rather than a reuse of `undeliverable` so that "withdrawn" stays
--    distinguishable from "the bot named a permanent failure" and from
--    "retired by the bound", and so that the row SURVIVES -- a deleted row
--    takes its `relay_code` with it and makes an already-sent DM
--    permanently unanswerable.
ALTER TABLE pending_dms
    ADD COLUMN IF NOT EXISTS attempts     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS claim_id     UUID NULL,
    ADD COLUMN IF NOT EXISTS claim_until  TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ NULL;

DO $$
BEGIN
  -- A relay row without an answerable identity cannot exist, and the
  -- identity has to be WELL-FORMED rather than merely present. "NOT NULL"
  -- alone admits '', which satisfies the invariant this constraint is named
  -- for and produces a mail-relay row no reader can ever answer -- the
  -- readers match `^SCR-[0-9A-HJKMNP-TV-Z]{12}$`, so anything else is a row
  -- that exists and cannot be used. The pattern is the readers' own:
  -- Crockford base32 with I, L, O and U excluded.
  --
  -- Generic queue rows (relay_code NULL) are untouched, so the existing
  -- writers stay untouched. Validates instantly: both columns are added by
  -- this same file, so no pre-existing row can violate it.
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'ck_pending_dms_relay_code'
                    AND conrelid = 'pending_dms'::regclass) THEN
    ALTER TABLE pending_dms ADD CONSTRAINT ck_pending_dms_relay_code
      CHECK ((mail_id IS NULL OR relay_code IS NOT NULL)
             AND (relay_code IS NULL
                  OR relay_code ~ '^SCR-[0-9A-HJKMNP-TV-Z]{12}$'));
  END IF;
  -- The two halves of a claim move together or not at all; a row holding an
  -- expiry with no identity, or an identity with no expiry, is not a state
  -- any statement here knows how to settle.
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'ck_pending_dms_claim_paired'
                    AND conrelid = 'pending_dms'::regclass) THEN
    ALTER TABLE pending_dms ADD CONSTRAINT ck_pending_dms_claim_paired
      CHECK ((claim_id IS NULL) = (claim_until IS NULL));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'ck_pending_dms_attempts_nonneg'
                    AND conrelid = 'pending_dms'::regclass) THEN
    ALTER TABLE pending_dms ADD CONSTRAINT ck_pending_dms_attempts_nonneg
      CHECK (attempts >= 0);
  END IF;
END $$;

-- 5. Six indexes the item-5 access patterns need and the table lacks.
--
--    mail_id: read by the ON DELETE SET NULL above, and by the account
--    deletion sweep's "DMs of mail this player sent" subquery. Without it
--    both seq-scan a queue that only ever grows.
CREATE INDEX IF NOT EXISTS idx_pending_dms_mail
    ON pending_dms(mail_id) WHERE mail_id IS NOT NULL;

--    (relay_code, steam_id) UNIQUE, not (relay_code): the name identifies a
--    MAIL, and every recipient of one mail shares it. mail_recipients is
--    PRIMARY KEY (message_id, recipient_id) (297_mail.sql:81), so one
--    fan-out writes at most one row per (mail, player) and cannot collide
--    with itself. What this index GUARANTEES is the property the resolver
--    relies on: for one player, one name resolves to at most one thread.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_dms_relay_code
    ON pending_dms(relay_code, steam_id) WHERE relay_code IS NOT NULL;

--    The pick-a-thread listing, shown when a reply names no thread.
--    created_at, not delivered_at: a row DMed seconds ago still has
--    delivered_at NULL until the ack lands, and it is exactly the thread the
--    player is most likely to have meant. Cancelled rows are excluded --
--    the recipient deleted that mail, so offering it back is offering a
--    thread that a reply would be refused for.
--    This one keeps `mail_id IS NOT NULL` DELIBERATELY, and it is the only
--    predicate in this file that should. It feeds the pick-a-thread
--    listing, and a tombstone is a thread the player can no longer write
--    to: offering it back would be offering a tap that is refused.
CREATE INDEX IF NOT EXISTS idx_pending_dms_relay_recent
    ON pending_dms(steam_id, created_at DESC)
 WHERE mail_id IS NOT NULL AND relay_code IS NOT NULL
   AND NOT undeliverable AND cancelled_at IS NULL;

--    The drain, one partial index per class. The poll claims the oldest
--    rows of each class separately (operational rows take four slots in
--    five, relay rows one, so neither can starve the other), and both
--    halves are an ORDER BY created_at, id over rows still waiting.
--    Partial on exactly that predicate, so each index holds only the
--    pending set and not the history the table accumulates.
--
--    `claim_until` is INCLUDEd rather than filtered: the claimable test is
--    `claim_until IS NULL OR claim_until <= NOW()`, and NOW() is not
--    immutable, so it cannot appear in a partial predicate. INCLUDE is what
--    keeps the check off the heap.
--    On `relay_code`, NOT `mail_id`: these two predicates are what sort a
--    row into the operational class or the relay class, and a tombstone
--    (mail purged, name kept) has mail_id NULL. Keyed on mail_id it would
--    land in the OPERATIONAL class and be sent as a generic DM -- a mail's
--    body with no footer and no thread name.
CREATE INDEX IF NOT EXISTS idx_pending_dms_drain_op
    ON pending_dms(created_at, id) INCLUDE (claim_until)
 WHERE delivered_at IS NULL AND NOT undeliverable AND cancelled_at IS NULL
   AND relay_code IS NULL;
CREATE INDEX IF NOT EXISTS idx_pending_dms_drain_relay
    ON pending_dms(created_at, id) INCLUDE (claim_until)
 WHERE delivered_at IS NULL AND NOT undeliverable AND cancelled_at IS NULL
   AND relay_code IS NOT NULL;

--    The retirement sweep runs before every hand-out and had no index at
--    all, so it seq-scanned a table that only grows.
CREATE INDEX IF NOT EXISTS idx_pending_dms_retire
    ON pending_dms(created_at) INCLUDE (attempts, claim_until)
 WHERE delivered_at IS NULL AND NOT undeliverable AND cancelled_at IS NULL;

-- Sanity output. This asserts the columns and constraints exist and are
-- typed as intended, and nothing else -- in particular it does NOT assert
-- any row count, because this migration is pure DDL and adds no rows.
SELECT table_name, column_name, data_type, column_default, is_nullable
  FROM information_schema.columns
 WHERE (table_name = 'players'        AND column_name = 'mail_discord_relay')
    OR (table_name = 'mail_messages'  AND column_name = 'via')
    OR (table_name = 'pending_dms'    AND column_name IN
          ('mail_id', 'relay_code', 'attempts',
           'claim_id', 'claim_until', 'cancelled_at'))
 ORDER BY table_name, column_name;

SELECT conrelid::regclass AS on_table, conname
  FROM pg_constraint
 WHERE conname IN ('ck_mail_messages_via', 'ck_pending_dms_relay_code',
                   'ck_pending_dms_claim_paired',
                   'ck_pending_dms_attempts_nonneg')
 ORDER BY 1, 2;

COMMIT;
