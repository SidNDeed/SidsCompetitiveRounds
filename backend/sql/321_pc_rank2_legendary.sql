-- 321_pc_rank2_legendary.sql
--
-- Rank 2 becomes Legendary. This file converts only the prints minted BEFORE the rule
-- changed; everything else is handled by code.
--
-- ORDER, ENFORCED — run AFTER the api deploy that carries `_PC_POOL_RULE = 3` and
-- `band_max_rank{legendary: 2}` (learning #236) AND after that api has RETAKEN the pool
-- (Sid ratified the stronger precondition 2026-09-15). Before that deploy the old code
-- still mints rank-2 prints as 'epic' from the old snapshot, and any print minted in the
-- gap would fall outside this one-time work list, excluded from every future rerun by the
-- very guard meant to protect it. The precondition was a COMMENT until 2026-09-15, and a
-- comment cannot refuse: the boot retake is awaited under a 30 s timeout and SWALLOWED on
-- failure (main.py `_pc_snapshot_boot_retake`), with `queue_cleanup_loop` as a ~60 s
-- backstop, so "the deploy finished" is not evidence the pool moved. The first DO block
-- below is that refusal.
--
-- Migration 316 adds the rule column as NOT NULL DEFAULT 1, so every existing snapshot
-- and every one the pre-deploy code writes is marked rule 1; the merged code's
-- `int(last_rule or 0) < _PC_POOL_RULE` then makes `_pc_snapshot_due` return 'rule'
-- and re-takes the pool
-- at deploy, so `pc_pool_members.rarity` and every NEW pull are already correct without
-- this file. The only stale copy is `pc_prints.rarity` on already-minted prints.
--
-- Nothing else needs rewriting: the discard value is DERIVED at discard time
-- (`shards_for(rarity)`), `pc_packs.result` is read only for dup detection and the wire
-- answer re-reads live prints, `pc_events` 'epic' rows are purged after 7 days, and the
-- cached card face self-invalidates because `band` is part of its revision spec.
--
-- DISCARDED PRINTS ARE DELIBERATELY EXCLUDED. `pc_prints.discard_shards` froze what was
-- actually paid at the epic rate, so promoting a settled print's rarity would contradict
-- its own payment record.
--
-- COUNT PINNED AT AUTHORING TIME: 3 live rank-2 epic prints (subject Stan; 2 owned by
-- one player, 1 by another), read from the primary 2026-09-15 and re-read 2026-09-16
-- (still 3 live, 0 discarded). The work list may only SHRINK under us — a player
-- discarding one of the three between the deploy and this run removes it on purpose, and
-- players are actively discarding — so a count BELOW the pin is reported and applied,
-- while a count ABOVE it means rows this file never looked at appeared, which is the
-- direction that means the set moved under us: that one REFUSES rather than guessing.
--
-- Dry-run both halves against the primary before applying (#313).

BEGIN;

-- ── precondition: the pool has actually been RETAKEN ──────────────────────────────
-- Read-only, and it takes no lock on pc_prints, so it runs before the lock/disable pair
-- that touches the table. It is a POSITIVE signal the new band table EMITTED (#438), not
-- a version number we trust: the newest snapshot must itself record rank 2 as
-- 'legendary'. Under the old band table that row reads 'epic' (verified on the primary
-- 2026-09-16: snapshot 6 records rank 2 = 'epic'), so this cannot pass early — the
-- negative control is the live database. It names no player id: a subject id would rot
-- the moment the pool reorders. The recorded `rule` is checked too, because "the pool was
-- retaken" is precisely "a snapshot was taken under the deployed pool word", and the band
-- table and the pool rule are two independent constants that only happen to ship
-- together; the snapshot's rule column is what the taker itself stamped from
-- `_PC_POOL_RULE`, not a claim about the deploy.
DO $$
DECLARE
  v_snap  integer;
  v_rule  integer;
  v_band  text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema = current_schema()
                    AND table_name = 'pc_pool_snapshots' AND column_name = 'rule') THEN
    RAISE EXCEPTION '321: pc_pool_snapshots.rule is missing -- migration 316 has not been applied on this box. Apply 316, deploy the api, let it retake the pool, then run this.';
  END IF;

  -- the same ordering _pc_snapshot_due reads the latest snapshot by
  SELECT id, rule INTO v_snap, v_rule
    FROM pc_pool_snapshots ORDER BY taken_at DESC, id DESC LIMIT 1;

  IF v_snap IS NULL THEN
    RAISE EXCEPTION '321: no pool snapshot exists at all -- nothing has taken one yet.';
  END IF;

  IF v_rule < 3 THEN
    RAISE EXCEPTION '321: the newest pool snapshot (id %) was taken under pool rule %, not 3 -- the merged api has not retaken the pool yet. Deploy it, confirm a fresh snapshot, then run this.', v_snap, v_rule;
  END IF;

  SELECT m.rarity INTO v_band
    FROM pc_pool_members m
   WHERE m.snapshot_id = v_snap AND m.pool_rank = 2;

  IF v_band IS NULL THEN
    RAISE EXCEPTION '321: the newest pool snapshot (id %, rule %) has no rank-2 member -- the pool is smaller than two, so there is nothing this migration should promote.', v_snap, v_rule;
  END IF;

  -- The one that matters. 'epic' here means the api that took this snapshot still carried
  -- the OLD band table, so promoting prints now would make them disagree with the pool
  -- that deals their band -- the exact inconsistency this migration exists to remove.
  IF v_band <> 'legendary' THEN
    RAISE EXCEPTION '321: the newest pool snapshot (id %, rule %) calls pool rank 2 "%", not legendary -- the api carrying band_max_rank{legendary: 2} has not retaken the pool yet. Deploy it, confirm a fresh snapshot, then run this.', v_snap, v_rule, v_band;
  END IF;

  RAISE NOTICE '321: pool snapshot % (rule %) agrees that rank 2 is legendary', v_snap, v_rule;
END $$;

-- ── the work list, under a lock that names itself ─────────────────────────────────
-- FIRST statement that touches pc_prints, on purpose: this explicit lock is what closes
-- the gap between the work list and the rewrite (learning #557). SHARE ROW EXCLUSIVE
-- conflicts with the ROW EXCLUSIVE every INSERT and UPDATE takes, so no writer can touch
-- pc_prints while this transaction runs — that is the whole guarantee, and it is a
-- guarantee about WRITERS. ACCESS SHARE readers are NOT blocked and are not meant to be:
-- reads of pc_prints stay served throughout.
--
-- Taking it explicitly rather than inheriting it: on PostgreSQL 16.15 (the live version)
-- `ALTER TABLE ... ENABLE/DISABLE TRIGGER` takes SHARE ROW EXCLUSIVE, not the ACCESS
-- EXCLUSIVE this file and its test both claimed until 2026-09-16. The guarantee survived
-- the mistake, but the wording implied readers were fenced as well; naming the mode makes
-- the statement match the claim instead of relying on a side effect of the ALTER.
--
-- lock_timeout so a lock request cannot pile a queue of writers behind one long-running
-- open: if the lock is not free within 5 s the transaction fails and nothing is applied.
SET LOCAL lock_timeout = '5s';
LOCK TABLE pc_prints IN SHARE ROW EXCLUSIVE MODE;

-- The trigger `pc_prints_immutable` (308_player_cards.sql:168) RAISES on any rarity
-- change, so the rewrite below cannot run while it is enabled.
ALTER TABLE pc_prints DISABLE TRIGGER pc_prints_immutable;

DO $$
DECLARE
  n integer;
  pinned CONSTANT integer := 3;   -- live rank-2 epic prints read from the primary at authoring time
BEGIN
  UPDATE pc_prints
     SET rarity = 'legendary'
   WHERE pool_rank = 2
     AND rarity = 'epic'
     AND discarded_at IS NULL;
  GET DIAGNOSTICS n = ROW_COUNT;

  -- Only ONE direction is a reason to refuse. More rows than the pin means prints this
  -- file never looked at exist -- the set grew under us -- and the conservative answer is
  -- to stop. Fewer is the expected shape of a live system: a discard between the deploy
  -- and this run takes a print out of the set on purpose, and an applied rerun finds 0.
  IF n > pinned THEN
    RAISE EXCEPTION '321: expected at most % live rank-2 epic prints, found % -- the set GREW since this file was authored; refusing', pinned, n;
  END IF;

  IF n = 0 THEN
    RAISE NOTICE '321: no live rank-2 epic print remains -- either this migration has already been applied, or all % pinned prints were discarded first. A discarded print is excluded on purpose: its discard_shards froze what was paid at the epic rate.', pinned;
  ELSIF n < pinned THEN
    RAISE NOTICE '321: % of the % rank-2 epic prints pinned at authoring time were promoted; % left the live set since. A discard explains the shortfall -- a discarded print is excluded on purpose and keeps its epic payout.', n, pinned, pinned - n;
  END IF;

  RAISE NOTICE '% rank-2 print(s) promoted to legendary', n;
END $$;

ALTER TABLE pc_prints ENABLE TRIGGER pc_prints_immutable;

-- Positive signal, not absence of error (#438): prove the trigger is armed again before
-- this transaction is allowed to commit.
DO $$
DECLARE
  st "char";
BEGIN
  SELECT tgenabled INTO st
    FROM pg_trigger
   WHERE tgrelid = 'pc_prints'::regclass
     AND tgname = 'pc_prints_immutable';

  IF st IS DISTINCT FROM 'O' THEN
    RAISE EXCEPTION 'pc_prints_immutable left disabled (tgenabled=%) -- refusing to commit', st;
  END IF;

  RAISE NOTICE 'pc_prints_immutable re-armed (tgenabled=%)', st;
END $$;

COMMIT;
