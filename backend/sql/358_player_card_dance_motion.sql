-- 358: Player Card dance motion -- the dance a player selected for the card
-- and the one stored motion source per player (dance cards, design
-- S3.1-S3.2).
--
-- Number: taken by census 2026-09-27T05:47:23Z over main, every worktree and
-- every local and remote branch tip. The highest file found was 356; 357 is
-- reserved for the v1.41.0 beta lane's round 6, so this file is 358.
--
-- players gains four raw-SQL columns (no ORM declaration, like every other
-- Player Card column):
--   active_dance_id      the selected dance (shop_items.id, kind dance), NULL
--                        = none. Written by POST /api/v1/pc/dance; set NULL
--                        by this foreign key when the item row goes, by the
--                        janitor when ownership is lost, and by account
--                        deletion.
--   pc_motion_at         the last charged motion upload (the 30 s pacing).
--   pc_motion_day        the UTC day that pc_motion_day_count counts.
--   pc_motion_day_count  charged decode attempts on that day (cap 8), only
--                        ever moved by the upload's charge statement.
-- pc_motions holds at most one motion source per player: the canonical
-- container (bytes; byte_len at most 12 MiB), its hashes, the dance item it
-- was captured for, the recipe, frame count and period of the capture, and
-- the still (static_hash, static_descriptor) it was captured against. A row
-- is served only while that binding and the selection still hold.
--
-- Additive and idempotent: IF NOT EXISTS on every column and on the table,
-- the foreign key guarded by its name ON players (a name alone would match a
-- same-named constraint of another schema's players and skip this one), one
-- explicit transaction (psql -f wraps none). Nothing is dropped, renamed or backfilled, and no existing row
-- changes value (the new id and dates start NULL, the counter 0).
--
-- REQUIRES shop_items (id BIGSERIAL) and players (id UUID).
--
-- DEPLOY ORDER: THIS FILE FIRST, confirmed on the primary and replicated to
-- the standby; then the api at a pinned sha, primary then standby; then the
-- client, on Sid's word; then the bot, last. The pinned-sha deploy rebuilds
-- the api from the same sha this file is applied from, so this file must
-- complete on its own before that api deploy (#477). Only the new dance-card
-- code reads these columns and this table, and no existing route touches
-- them, so the api step is safe once this file is in.

BEGIN;

ALTER TABLE players ADD COLUMN IF NOT EXISTS active_dance_id BIGINT NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_motion_at TIMESTAMPTZ NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_motion_day DATE NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS pc_motion_day_count INTEGER NOT NULL DEFAULT 0;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'players_active_dance_id_fkey'
                    AND conrelid = 'players'::regclass) THEN
    ALTER TABLE players ADD CONSTRAINT players_active_dance_id_fkey
      FOREIGN KEY (active_dance_id) REFERENCES shop_items(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS pc_motions (
  player_id UUID PRIMARY KEY REFERENCES players(id),
  motion_hash TEXT NOT NULL CHECK (motion_hash ~ '^[0-9a-f]{64}$'),
  source_sha256 TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
  bytes BYTEA NOT NULL,
  byte_len INTEGER NOT NULL CHECK (byte_len BETWEEN 1 AND 12582912),
  dance_item_id BIGINT NOT NULL REFERENCES shop_items(id) ON DELETE CASCADE,
  motion_recipe SMALLINT NOT NULL CHECK (motion_recipe >= 1),
  frame_count SMALLINT NOT NULL CHECK (frame_count BETWEEN 1 AND 120),
  frame_ms SMALLINT NOT NULL CHECK (frame_ms IN (40, 50)),
  static_hash TEXT NOT NULL,
  static_descriptor TEXT NOT NULL,
  stored_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
