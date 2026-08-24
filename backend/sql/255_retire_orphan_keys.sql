-- 255: retire the 4 orphaned client i18n keys left by the Aug 23 wiki batch
-- (migration 251's header named them and assigned retirement to "the next
-- real sync-keys run"; this seat's AdminSecret still 403s, #406/#421, so the
-- migration channel performs the same two writes the sync sweep would).
-- The four are the re-keyed mode docs + the old 'Stats' label - their
-- English sources no longer exist in the client catalogue
-- (tools/i18n_source.json, verified by id-diff against the live table), so
-- the portal was offering translators work on text no client can render.
-- Retirement hides them from the portal; their pending machine proposals
-- are marked superseded so the queue count stops advertising them.
-- Idempotent; explicit transaction (#340). Guard: refuses to run if any of
-- the four has an APPROVED entry (a translator's finished work must never
-- be silently retired by a hygiene pass - none exists today, but a rerun
-- after a surprise approval should fail loudly, #168).

BEGIN;

DO $$
DECLARE v_approved INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_approved
      FROM i18n_entries e
     WHERE e.key_id IN ('53e1c75349c012da','89014b0c6a59a3a5','c5b99e4ded85c126','e8ed682b2d08934d')
       AND e.state = 'approved';
    IF v_approved <> 0 THEN
        RAISE EXCEPTION 'migration 255: % approved entr(ies) exist on the orphan keys - refusing to retire translator-approved work; investigate first', v_approved;
    END IF;
END $$;

UPDATE i18n_keys
   SET retired_at = NOW(), updated_at = NOW()
 WHERE key_id IN ('53e1c75349c012da','89014b0c6a59a3a5','c5b99e4ded85c126','e8ed682b2d08934d')
   AND retired_at IS NULL;

UPDATE i18n_proposals
   SET status = 'superseded'
 WHERE key_id IN ('53e1c75349c012da','89014b0c6a59a3a5','c5b99e4ded85c126','e8ed682b2d08934d')
   AND status = 'pending';

-- Post-check: all four retired, zero pending proposals remain on them.
DO $$
DECLARE v_live INTEGER; v_pending INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_live FROM i18n_keys
     WHERE key_id IN ('53e1c75349c012da','89014b0c6a59a3a5','c5b99e4ded85c126','e8ed682b2d08934d')
       AND retired_at IS NULL;
    SELECT COUNT(*) INTO v_pending FROM i18n_proposals
     WHERE key_id IN ('53e1c75349c012da','89014b0c6a59a3a5','c5b99e4ded85c126','e8ed682b2d08934d')
       AND status = 'pending';
    IF v_live <> 0 OR v_pending <> 0 THEN
        RAISE EXCEPTION 'post-check FAILED: % still live, % proposals still pending', v_live, v_pending;
    END IF;
    RAISE NOTICE 'post-check OK: 4 orphan keys retired, their pending proposals superseded';
END $$;

COMMIT;
