-- 298_matches_session_uuid.sql
-- Sept 6 batch, Group 4 item c (session report): a reporter-minted opaque
-- room-occupancy id on every 1v1 match row. The reporting seat generates one
-- UUID v4 when it joins a room and sends it on every game it reports from
-- that sitting, so consecutive casual games can be grouped into ONE report
-- without any room identifier ever leaving the server (#463: a stored
-- photon_room_id is a room locator that must stay server-side, so the
-- previous room+date grouping was refused; this column replaces it).
--
-- NULLABLE, no default, no backfill (#257): NULL = "filed before this column
-- existed, or by a client that predates the field" and such games are served
-- as one-game reports. Nothing can reconstruct a grouping for old rows and
-- nothing should pretend to.
--
-- The field rides OUTSIDE the frozen 7-field match HMAC canonical
-- (p1:p2:p1_rounds:p2_rounds:is_ranked:reporter:room_id), which is unchanged.
--
-- Deploy order: apply on the primary BEFORE the api build that inserts and
-- selects the column — the ORM passes every column explicitly on INSERT, so
-- code-before-migration fails every match submit (the 141 precedent). ADD
-- COLUMN IF NOT EXISTS is harmless under the old code. The standby receives
-- it by streaming replication; deploy the api to both boxes as usual.
BEGIN;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS session_uuid UUID;
CREATE INDEX IF NOT EXISTS idx_matches_session_uuid
    ON matches (session_uuid) WHERE session_uuid IS NOT NULL;
COMMIT;
