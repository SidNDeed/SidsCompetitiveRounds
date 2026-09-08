-- 300_mail_inbox_rev.sql — the inbox delivery counter behind /mail/status
-- (Sept 6 batch, Group 4 item b, reviews r1 + r2; follows 297_mail.sql).
--
-- /mail/status's `revision` was the newest delivered message id by
-- created_at. A send that starts first but commits last carries the OLDER
-- created_at, so after it lands the unread count rises while the revision
-- stays on the other message and the client never toasts it. An insert-time
-- sequence has the same flaw (its numbers are handed out at INSERT, not at
-- COMMIT). What is needed is a cursor that moves once per delivered envelope
-- in commit order: one row per recipient whose counter is bumped by a
-- row-locked DB delta (`rev = rev + 1`) inside the sending transaction.
-- Concurrent sends to one recipient serialise on that row, so whichever
-- commits later still advances it.
--
-- Backfill: existing inboxes start at their delivered-envelope count, so a
-- client's persisted baseline moves once (its own guard — nothing newer
-- than what it has listed — keeps that silent).
--
-- The FK cascade is decorative under anonymise-in-place (#437):
-- delete_player_data removes the row by name.
--
-- Review r2 adds two pieces:
--
-- 1. The delivery TRIGGER. Between this migration and the api rebuild the
--    previous api build is still serving: its fan-out inserts envelopes
--    without touching this table, so a client whose inbox was empty at its
--    first status fetch would see `unread` rise with no revision change and
--    no toast. A statement-level AFTER INSERT trigger on mail_recipients
--    advances the counter for EVERY writer, old or new, inside the inserting
--    transaction — the same set-wise, sorted, row-locked delta the api runs
--    itself (two overlapping sends take their rows in one order). The
--    table lock at the top of this file (review r3) closes the gap between
--    the backfill's snapshot and the trigger's installation: a delivery
--    is counted by exactly one of the two, never by neither. The api
--    keeps its own bump as well, so under the new build a send advances the
--    counter twice. That is fine and intended: the value is a CHANGE signal
--    — the client compares it for inequality and never reads it as a count
--    — and the api's statement stays an executed, test-pinned step of the
--    send.
-- 2. mail_messages.recipient_count: a broadcast's delivered-envelope count,
--    written in the sending transaction and replayed verbatim by a same-key
--    retry, so a recipient who deleted their account between the commit and
--    the retry cannot change the replayed answer. NULL on direct messages.
--
-- Deploy order: after 297, BEFORE the api build that bumps and reads the
-- table (the fan-out inserts into it on every send; /mail/status selects
-- from it); the trigger covers sends made by the old build in between.
-- Idempotent: IF NOT EXISTS + ON CONFLICT DO NOTHING + CREATE OR REPLACE +
-- DROP TRIGGER IF EXISTS, so a second application is a no-op.

BEGIN;

-- Review r3: taken FIRST so the backfill below and the trigger installed
-- after it see one consistent set of deliveries. SHARE ROW EXCLUSIVE
-- conflicts with the ROW EXCLUSIVE lock every INSERT takes, so a send
-- that started before this point commits before the backfill counts
-- (counted there) and one that starts after it waits for COMMIT (counted
-- by the trigger); nothing lands in the gap between the two. Readers are
-- not blocked. Released at COMMIT, so a rerun holds it for one no-op pass.
LOCK TABLE mail_recipients IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE IF NOT EXISTS mail_inbox_rev (
    recipient_id UUID        PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    rev          BIGINT      NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO mail_inbox_rev (recipient_id, rev)
SELECT recipient_id, COUNT(*)
  FROM mail_recipients
 WHERE delivery = 'delivered'
 GROUP BY recipient_id
ON CONFLICT (recipient_id) DO NOTHING;

ALTER TABLE mail_messages ADD COLUMN IF NOT EXISTS recipient_count INTEGER NULL;

-- One delta per recipient per INSERT statement, visited in recipient order
-- (the api's _MAIL_REV_BUMP_SQL shape): a transition table keeps this
-- set-wise, so the lock order never follows the insert order of the rows.
CREATE OR REPLACE FUNCTION mail_inbox_rev_bump()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO mail_inbox_rev (recipient_id, rev)
    SELECT recipient_id, COUNT(*)
      FROM inserted
     WHERE delivery = 'delivered'
     GROUP BY recipient_id
     ORDER BY recipient_id
    ON CONFLICT (recipient_id) DO UPDATE
       SET rev = mail_inbox_rev.rev + EXCLUDED.rev, updated_at = NOW();
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_mail_inbox_rev_bump ON mail_recipients;
CREATE TRIGGER trg_mail_inbox_rev_bump
    AFTER INSERT ON mail_recipients
    REFERENCING NEW TABLE AS inserted
    FOR EACH STATEMENT
    EXECUTE FUNCTION mail_inbox_rev_bump();

COMMIT;
