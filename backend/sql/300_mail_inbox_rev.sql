-- 300_mail_inbox_rev.sql — the inbox delivery counter behind /mail/status
-- (Sept 6 batch, Group 4 item b, review r1; follows 297_mail.sql).
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
-- Deploy order: after 297 and BEFORE the api build that bumps and reads the
-- table (the fan-out inserts into it on every send; /mail/status selects
-- from it). Idempotent: IF NOT EXISTS + ON CONFLICT DO NOTHING, so a second
-- application is a no-op.

BEGIN;

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

COMMIT;
