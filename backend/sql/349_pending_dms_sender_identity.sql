-- 349: pending_dms.sender_steam_id -- who SENT a relay DM, kept on the row
-- itself (v1.41.0 beta review, round 2, finding 8).
--
-- The account erasure (main.py delete_player_data) removes a player's relay
-- DMs in both directions: addressed TO them, and SENT by them (the queued
-- text carries the sender's display name as it read at send time). The
-- sent-by half found its rows through the mail: mail_id IN (the mails this
-- player sent). A relay row outlives its mail as a tombstone -- the mail's
-- hard purge sets mail_id NULL (ON DELETE SET NULL, migration 330) and
-- relay_code stays -- and from then on nothing on the row said who sent it,
-- so erasing the sender left the copied body and the sender's name in place.
--
-- This column is that identity, written by the relay fan-out
-- (mail_discord._RELAY_FANOUT_SQL) in the mail's own transaction, from the
-- sender's steam_id. A plain snapshot, NOT a foreign key: a foreign key with
-- ON DELETE SET NULL is the same gap again, and one with RESTRICT would block
-- the anonymisation the erasure performs. NULL on operational rows, which
-- have no sender.
--
-- Backfill: a relay row written before this column existed takes it from its
-- mail, while the mail still exists. A row whose mail was already purged has
-- nothing left to derive it from and stays NULL.
--
-- No index: the account erasure is the only statement that reads it, once
-- per erased account.
--
-- DEPLOY ORDER: THIS FILE FIRST (after 330, whose relay columns the backfill
-- reads), then the api. The api that writes and reads this column cannot run
-- without it: its relay fan-out stops queueing DMs (the mail itself still
-- sends, because the fan-out is savepointed) and the account erasure's
-- sent-by DELETE errors, which fails the whole erasure.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS, and the backfill touches only relay
-- rows whose column is still NULL and whose mail still exists. A second run
-- therefore rewrites no row the first run wrote; it fills only a relay row
-- written in between by an api that predates the column. One explicit
-- transaction (#340).

BEGIN;

ALTER TABLE pending_dms ADD COLUMN IF NOT EXISTS sender_steam_id TEXT NULL;

UPDATE pending_dms d
   SET sender_steam_id = p.steam_id
  FROM mail_messages m
  JOIN players p ON p.id = m.sender_id
 WHERE d.mail_id = m.id
   AND d.relay_code IS NOT NULL
   AND d.sender_steam_id IS NULL;

COMMIT;
