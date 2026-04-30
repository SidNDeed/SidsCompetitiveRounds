-- v1.25.24: tag ranked_series rows that came from a private-room preflight
-- so /series/active can render a PRIVATE label and force-lock bets. Without
-- this, private games surface in the Live Ranked Games panel right at game
-- start with no real betting window — by the time a viewer poll picks them
-- up (~5s) the score has already advanced and bets auto-lock anyway. With
-- the tag, viewers see them as "PRIVATE — no bets" instead of a deceptive
-- bettable row.

ALTER TABLE ranked_series
    ADD COLUMN IF NOT EXISTS is_private BOOLEAN NOT NULL DEFAULT FALSE;
