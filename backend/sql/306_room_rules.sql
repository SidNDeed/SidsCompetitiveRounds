-- 306: per-room rules record — friendly fire (2v2 / 1v2) and the Same Cards
-- rule in every mode (Sept 10 batch; the shape decisions are recorded below).
--
-- A room's rules {ff, sc} are decided BEFORE the room exists (host knobs on the
-- 2v2 / 1v2 lobby rows; the per-player preference below for queue-matched
-- rooms), frozen by the server at issuance onto the issuance record AND the
-- series row, and delivered to every member in the ready/resolve payload. They
-- never change inside a room. NULL on a series = a game issued before this
-- release ("unknown"); histories render nothing for NULL.
--
-- Member-scoped versions: each queue row carries the version its OWN last
-- authenticated request advertised (never players.mod_version — a global
-- last-write-wins value that two seats on one account overwrite). The
-- settings_version / seen_settings_version pair makes a changed lobby rule
-- visible to every member before Start (echo of what was RENDERED).
--
-- Idempotent, IF NOT EXISTS — safe to re-run. Migration-only SHA: deploy this
-- file before the API that reads the columns.

BEGIN;

-- host knobs + settings generation on the lobby rows
ALTER TABLE team_lobbies ADD COLUMN IF NOT EXISTS friendly_fire    BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE team_lobbies ADD COLUMN IF NOT EXISTS same_cards       BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE team_lobbies ADD COLUMN IF NOT EXISTS settings_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ovt_lobbies  ADD COLUMN IF NOT EXISTS friendly_fire    BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE ovt_lobbies  ADD COLUMN IF NOT EXISTS same_cards       BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE ovt_lobbies  ADD COLUMN IF NOT EXISTS settings_version INTEGER NOT NULL DEFAULT 0;

-- member-scoped version + rendered-settings echo (lobby members ARE queue rows
-- with status = 'lobby'); frozen rules on the issuance records
ALTER TABLE ranked_queue ADD COLUMN IF NOT EXISTS mod_version TEXT NULL;
ALTER TABLE ranked_queue ADD COLUMN IF NOT EXISTS rules JSONB NULL;
ALTER TABLE team_queue   ADD COLUMN IF NOT EXISTS mod_version TEXT NULL;
ALTER TABLE team_queue   ADD COLUMN IF NOT EXISTS seen_settings_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE team_queue   ADD COLUMN IF NOT EXISTS rules JSONB NULL;
ALTER TABLE ovt_queue    ADD COLUMN IF NOT EXISTS mod_version TEXT NULL;
ALTER TABLE ovt_queue    ADD COLUMN IF NOT EXISTS seen_settings_version INTEGER NOT NULL DEFAULT 0;

-- the 1v1 (and queue-matched 2v2 / 1v2) preference: Same Cards is ON for a
-- queue-matched room only when EVERY member has this on
ALTER TABLE players ADD COLUMN IF NOT EXISTS pref_same_cards BOOLEAN NOT NULL DEFAULT false;

-- frozen rules on the room ledger (the 1v1 late-series fallback reads it) and
-- on the series rows every history endpoint reads
ALTER TABLE issued_room_regions ADD COLUMN IF NOT EXISTS rules JSONB NULL;
ALTER TABLE ranked_series       ADD COLUMN IF NOT EXISTS rules JSONB NULL;
ALTER TABLE team_series         ADD COLUMN IF NOT EXISTS rules JSONB NULL;
ALTER TABLE ovt_series          ADD COLUMN IF NOT EXISTS rules JSONB NULL;

COMMIT;
