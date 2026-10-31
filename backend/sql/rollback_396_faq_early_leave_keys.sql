-- rollback_396_faq_early_leave_keys.sql
-- Takes back 396_faq_early_leave_keys.sql on the review surfaces: the four client keys
-- 396 registers are RETIRED (their rows, entries and proposal history kept), every
-- PENDING proposal on them is decided 'superseded', and the existing retired rows of the
-- four client keys migration 386 registered for the same strings are made live again.
-- The proposals 396 decided 'superseded' on the 386 keys stay superseded.
-- The file RAISES, and commits nothing, while an entry on one of the four 396 keys is
-- approved.
-- NOT a release-train migration. A second run writes no row.
-- DEPLOY ORDER: this file alone, only to take back a 396 that has committed.
-- Explicit transaction (#340): the same four SET LOCAL lines as 396, then one top-level
-- statement, a DO block.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $r396$
DECLARE
    v_approved INT;
BEGIN
    -- Approved work is never retired (see the header): lock, then read, then write.
    PERFORM 1 FROM i18n_keys
     WHERE key_id IN ('0ab13f648dd0175b', '3988c8d80e42f69d', '3bb08fc59139b367', '439cd5d90ee1b6d3',
                      '44732e465b16cee1', '6173541088dbb882', '79023ff50ab9d08e', '9d365a214640aebd')
     ORDER BY key_id
       FOR NO KEY UPDATE;
    PERFORM 1 FROM i18n_entries
     WHERE key_id IN ('0ab13f648dd0175b', '3988c8d80e42f69d', '3bb08fc59139b367', '439cd5d90ee1b6d3',
                      '44732e465b16cee1', '6173541088dbb882', '79023ff50ab9d08e', '9d365a214640aebd')
     ORDER BY key_id, language_code
       FOR NO KEY UPDATE;
    SELECT COUNT(*) INTO v_approved
      FROM i18n_entries e
     WHERE e.key_id IN ('44732e465b16cee1', '6173541088dbb882', '9d365a214640aebd', '0ab13f648dd0175b')
       AND e.state = 'approved';
    IF v_approved <> 0 THEN
        RAISE EXCEPTION 'rollback_396: % approved entr(ies) exist on the 396 FAQ early-leave keys - refusing to retire translator-approved work; nothing committed', v_approved;
    END IF;

    UPDATE i18n_keys
       SET retired_at = NOW(), updated_at = NOW()
     WHERE namespace = 'client'
       AND key_id IN ('44732e465b16cee1', '6173541088dbb882', '9d365a214640aebd', '0ab13f648dd0175b')
       AND retired_at IS NULL;

    UPDATE i18n_keys
       SET retired_at = NULL, updated_at = NOW()
     WHERE namespace = 'client'
       AND key_id IN ('3988c8d80e42f69d', '3bb08fc59139b367', '439cd5d90ee1b6d3', '79023ff50ab9d08e')
       AND retired_at IS NOT NULL;

    UPDATE i18n_proposals
       SET status = 'superseded', review_note = 'key retired by rollback_396',
           reviewed_at = NOW()
     WHERE key_id IN ('44732e465b16cee1', '6173541088dbb882', '9d365a214640aebd', '0ab13f648dd0175b')
       AND status = 'pending';
END $r396$;

COMMIT;
