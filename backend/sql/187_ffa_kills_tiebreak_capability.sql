-- 187: kills tie-break capability plumbing (Sid approved 2026-08-03;
-- Codex Aug-3 round-2 find 1).
--
-- ffa_queue.mod_version: stamped by each member's OWN session-authenticated
-- join/create/lobby-join call — the only version signal the lock computation
-- may trust. players.mod_version is deliberately NOT used for this: the
-- series preflight stamps that column from ONE caller's header, so any DLL
-- holder could poison another player's row and flip lobby semantics.
--
-- ffa_lobbies.kills_tiebreak: the capability DECISION, frozen at lock time
-- (both lock sites — host Start and the legacy gather decider). TRUE only
-- when every member's queue-row version >= FFA_KILLS_TIEBREAK_MIN_VERSION.
-- submit_ffa_match reads ONLY this frozen flag: no mid-sitting version
-- change, poll race, or reporter identity can flip placement semantics
-- between games of one sitting. Default FALSE = legacy shared-tie semantics
-- (the safe direction): every pre-187 row and every in-flight lobby during
-- the deploy keeps exactly today's behavior.
--
-- MUST be applied BEFORE the API deploy that reads/writes these columns
-- (the columns-first ordering of learning #236's inverse).

ALTER TABLE ffa_queue   ADD COLUMN IF NOT EXISTS mod_version VARCHAR(16);
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS kills_tiebreak BOOLEAN NOT NULL DEFAULT FALSE;

DO $$
BEGIN
  RAISE NOTICE 'migration 187 OK: ffa_queue.mod_version + ffa_lobbies.kills_tiebreak present';
END $$;
