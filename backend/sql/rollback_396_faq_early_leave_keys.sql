-- rollback_396_faq_early_leave_keys.sql
-- Takes back what 396_faq_early_leave_keys.sql does to the review surfaces, the way the
-- key sync's retirement does: the four FAQ early-leave client keys 396 registers are
-- RETIRED, never deleted, so entries and proposal history survive; the four 386 keys
-- 396 retired are live again; and every PENDING proposal on the four 396 keys (its
-- sixteen machine seeds, plus anything proposed on them since) is decided 'superseded'
-- (the review endpoints refuse to approve or reject a proposal on a retired key, so one
-- left pending would sit in the queue for good). The proposals 396 decided
-- 'superseded' on the 386 keys stay superseded: a translator re-proposes through the
-- portal if that text is wanted again. Keys before proposals, the order the key sync and
-- the review endpoint take. Approved entries on either side are never written.
-- APPROVED WORK IS NEVER RETIRED: the file REFUSES, and commits nothing, while any of
-- the four 396 keys carries an approved entry (a translation a portal reviewer
-- approved), the refusal 396 applies to approved entries on the 386 keys. Retiring
-- such a key would keep the entry but drop it from every served pack (the pack
-- endpoint serves live keys only). Before any write it locks the eight key rows (396's
-- four and 386's four) FOR NO KEY UPDATE in key order, then their entries in (key,
-- language) order, and reads the approved count under those locks. The locks are there
-- for the portal's approval write (main.py i18n_review): in one transaction it locks ONE
-- key row FOR NO KEY UPDATE, before anything else, then that proposal, then writes one
-- entry row. It holds no other key row and no entry row while it waits for that key
-- row, so it and this file cannot wait on each other in a cycle; whichever takes the
-- shared key row first goes first. An approval that commits first is counted (each
-- statement here reads what has committed when it runs); one that waits behind this
-- file finds the key retired and is refused with 409. This file and 396 are never
-- concurrent: migrations run one at a time, under the landing lease and the release
-- train, so no lock order between the two files is relied on, and none is claimed.
-- NOT a release-train migration. Re-runnable: with the 396 keys retired, the 386 keys
-- live and nothing pending on the 396 keys, it writes no row.
-- DEPLOY ORDER: only while no shipped client carries the four new strings, or with that
-- client's rollback; and only while no translation on the four 396 keys is approved
-- (otherwise it refuses, above). A client that already shows them keeps its bundled drafts, and the
-- next key sync from such a client makes the keys live again and retires the 386 keys.
-- It makes the 386 keys live whoever retired them, so run it only to take 396 back.
-- 396 never re-proposes a claude-mt draft of a text it already proposed, and this file
-- decides those drafts 'superseded', so applying 396 again after this file stops at
-- 396's coverage check with nothing committed, unless every pair is covered some other
-- way (a pending proposal, or a translation approved against the current text). Taking
-- the keys forward again after this rollback is a new migration.
-- Explicit transaction (learning #340) under the same four lines as 396: 5 s on each lock
-- wait, 25 s on each top-level statement, 5 s on a pause between statements, and
-- synchronous_commit = local. The statement and idle budgets are separate (PostgreSQL 16
-- has no transaction_timeout), so the longest this file can hold locks before its COMMIT
-- is their SUM, 30 s, and that holds because the locks, the approved check and all three
-- UPDATEs run inside ONE statement, a DO block whose inner statements share its 25 s.
-- THE COMMIT. PostgreSQL disables the statement timer before it commits, so the COMMIT's
-- own work is outside every timeout above, and the locks are held until it ends.
-- synchronous_commit = local keeps that work LOCAL: it never waits for a standby's
-- confirmation, whatever synchronous_standby_names says now or later.
-- BOUNDED: everything before COMMIT -- each lock wait (5 s, and every one sits inside the
-- DO block's 25 s) and the hold up to COMMIT (statement 25 s + idle 5 s = 30 s).
-- NOT BOUNDED: the COMMIT's local completion -- the WAL flush and the transaction-status
-- (pg_xact) write, which can read an evicted page -- I/O that no PostgreSQL setting
-- bounds, for this or any transaction. The hold is therefore 30 s plus the COMMIT's local
-- completion.

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
