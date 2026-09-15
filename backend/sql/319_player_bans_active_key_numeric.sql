-- 319: player_bans -- an ACTIVE ban's key is one to twenty ASCII digits
-- (2026-09-14, the Sept 12 batch's v4.13 fold, review r14).
--
-- 028 created player_bans.steam_id as TEXT, so the api's check on a new
-- ban's key (admin_ban's since v4.11; the moderation-case act's since v4.13)
-- was the only boundary, and the table held none. This file puts the same
-- pattern -- main._MOD_TARGET_PATTERN anchored at both ends; a test pins the
-- two spellings together -- on the table, for ACTIVE rows only: an unbanned
-- row keeps whatever key it was written with (the log is append-only), and
-- an unban, which sets unbanned_at, always leaves a row the CHECK admits.
-- PostgreSQL's `$` is the end of the string, the boundary the api's
-- fullmatch has (measured on the primary 2026-09-14: twenty digits admitted;
-- twenty-one digits, a trailing newline, Arabic-Indic and fullwidth digits
-- refused).
--
-- Read half, run on the primary 2026-09-14 before this file was written:
-- player_bans held 0 rows, active or not, and the constraint was absent.
-- While an ACTIVE row fails the pattern (a ban an api older than v4.11
-- stored), ADD CONSTRAINT's own validation fails; the DO block counts those
-- rows first only so that the error names how many there are and what to
-- do: release each through /api/v1/admin/unban (since v4.13 it releases a
-- key outside the domain when an active row carries it) and apply again.
-- Either way the transaction rolls back and nothing is applied. The
-- acceptance signal is the pg_constraint probe on both boxes, not the
-- migrate verb's output.
--
-- No DDL for the audit actor (v4.13): admin_actions.admin_steam_id has been
-- TEXT since 028, so the api binding a whole "discord:<id>" actor needs no
-- widening -- the cut was the api's own slice.
--
-- Additive: no api code needs it, so it rides the code SHA and is applied
-- after the code phase (learning #477's single-SHA case).
--
-- WHO applies it: a person, not the train. release_train.py carries neither
-- this file nor 320 in any of its SQL lists (schema_sql, post_code_sql,
-- i18n_sql, backfill_sql; a mention in a comment is not a list entry), so a
-- run of `--only code` followed by `--only verify` lands nothing of this file,
-- and nothing in the verify phase probes for this constraint (it checks
-- routes, tables, columns and indexes), so its absence is not caught there
-- either. The operator applies it BY HAND after the code phase and before
-- 320, with the migrate: verb on the PRIMARY, naming this file. It needs
-- no copy step: the file reaches the box with the clone update the deploy
-- playbook performs. The standby receives the constraint by streaming
-- replication -- do not apply it there. Acceptance stays the pg_constraint
-- probe on BOTH boxes (above), not the verb's output.
--
-- Re-running is a no-op: the constraint is added only when absent. Explicit
-- transaction: psql autocommits statement by statement otherwise (#340).
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $m319$
DECLARE
    bad bigint;
BEGIN
    SELECT COUNT(*) INTO bad FROM player_bans
     WHERE unbanned_at IS NULL AND steam_id !~ '^[0-9]{1,20}$';
    IF bad > 0 THEN
        RAISE EXCEPTION '319: % active player_bans row(s) have a key that is not 1-20 ASCII digits; release them through /api/v1/admin/unban, then apply again', bad;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'player_bans'::regclass
                      AND conname = 'player_bans_active_key_numeric') THEN
        ALTER TABLE player_bans ADD CONSTRAINT player_bans_active_key_numeric
            CHECK (unbanned_at IS NOT NULL OR steam_id ~ '^[0-9]{1,20}$');
    END IF;
END $m319$;

COMMIT;
