-- 315: Player Cards — the cards of already-deleted players leave every binder (2026-09-13).
--
-- Since 314 (no opt-out) deleting all data is the one way a card leaves the
-- binders that hold it, and the api's deletion endpoint removes the prints
-- and the card rows of the deleted subject itself. Two kinds of subject are
-- not covered by that endpoint: players deleted BEFORE this batch (the old
-- endpoint emptied their own binder and left the cards of them in place),
-- and players deleted by the old endpoint in the interval between the
-- schema phase (314) and the code phase of the deploy. This file removes
-- both, idempotently, and is run AFTER the code phase so that the interval
-- is closed as well (release train: post-code SQL, before the i18n files).
-- Re-running it is always safe: every statement is a no-op once clean.
--
-- Read half, dry-run on the primary 2026-09-13 before this file was written:
-- 0 deleted players, 0 cards / 0 prints / 0 pending events of a deleted
-- subject (the feature is a day old), so the write half touches nothing
-- today and exists for the deletions that happen before the code phase.
--
-- Same order as the endpoint: events, leases, prints, cards.
BEGIN;
SET LOCAL lock_timeout = '5s';

DELETE FROM pc_events e
 USING players p
 WHERE p.id = e.subject_player_id AND p.deleted_at IS NOT NULL;

DELETE FROM pc_delivery_leases l
 USING players p
 WHERE p.id = l.subject_id AND p.deleted_at IS NOT NULL;

DELETE FROM pc_prints pr
 USING pc_cards c, players p
 WHERE c.id = pr.card_id AND p.id = c.subject_player_id AND p.deleted_at IS NOT NULL;

DELETE FROM pc_cards c
 USING players p
 WHERE p.id = c.subject_player_id AND p.deleted_at IS NOT NULL;

COMMIT;
