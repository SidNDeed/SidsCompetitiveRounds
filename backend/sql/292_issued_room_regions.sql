-- 292: the region the SERVER issued for a ranked room, keyed by the room name.
--
-- Review r13 HIGH. The region-corroboration map used to take its evidence from
-- the match report's `region` field. That field is outside the seven-field
-- match HMAC (p1:p2:p1_rounds:p2_rounds:is_ranked:reporter:room_id — a format
-- that does not change), so establishing the reporter's session proves who is
-- speaking and nothing about the region named in the sentence: two accounts
-- could play real games and label them with a region nobody can connect to,
-- corroborate it, and have it beat a real region in a tie-break.
--
-- The server already CHOOSES the region for every queue-issued ranked room and
-- tells both seats to connect there. This table keeps that decision, so the
-- evidence can be read back from what the server issued rather than from what a
-- client reports. The room name IS covered by the HMAC, so a report can only
-- reach the binding for the room it was actually signed for; and a room whose
-- region does not exist produces no accepted match, which is what stops the
-- server from corroborating its own guesses.
--
-- The row records WHO the room was issued to as well. Without the pair it
-- said only "this region was issued for this room", so any accepted report
-- naming the room fed the map; with it, the read can require the report's two
-- players to be the two the server actually sent there. Nullable because the
-- column is added by the same statement that may find rows already present.
--
-- Rows are evidence with a shelf life: the map's own TTL is 7 days, and rows
-- past 30 days are deleted by the issuance path itself (see main.py's
-- _queue_stamp_room_reciprocal). There is no cron for this and there was never
-- going to be one — a promise of pruning with nothing that prunes is how a
-- table grows forever while the comment says it does not.
-- Idempotent, IF NOT EXISTS — safe to re-run.

CREATE TABLE IF NOT EXISTS issued_room_regions (
    room_name  VARCHAR(64) PRIMARY KEY,
    region     VARCHAR(16) NOT NULL DEFAULT '',
    issued_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE issued_room_regions ADD COLUMN IF NOT EXISTS player1_id UUID;
ALTER TABLE issued_room_regions ADD COLUMN IF NOT EXISTS player2_id UUID;

CREATE INDEX IF NOT EXISTS idx_issued_room_regions_issued_at
    ON issued_room_regions (issued_at);
