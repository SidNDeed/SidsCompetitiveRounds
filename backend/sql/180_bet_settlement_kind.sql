-- 180: persisted settlement cause on all three bet tables.
--
-- WHY (Codex v1.36 client-review find 16): the ledger's outcome_recorded
-- discriminator is derived from the parent's CURRENT status, which is not
-- immutable. A 1g ranked bet at raw odds ~1.497 refunded by the stalled-series
-- prune has payout == amount; if the series later completes, outcome_recorded
-- flips true and the arithmetic tiebreak reconstructs a 1g "winning" payout —
-- relabelling a historical refund as "won". The settlement KIND must be
-- stamped by the settling code path itself, at settle time, and never
-- re-derived.
--
-- Values: 'won' | 'lost' | 'refunded' (code-enforced; older rows backfilled
-- below, frozen as of this migration's run). NULL = settled by pre-1.36 code
-- with an ambiguous payout — the API falls back to the old derivation.
--
-- ORDER: apply BEFORE deploying the v1.36 API (the new ledger SELECT reads
-- the column). Rerun-safe: the UPDATEs only touch settlement_kind IS NULL
-- rows, so a re-run after the deploy merely backfills any row settled by old
-- code during the migrate->deploy gap.

ALTER TABLE bets      ADD COLUMN IF NOT EXISTS settlement_kind VARCHAR(10);
ALTER TABLE team_bets ADD COLUMN IF NOT EXISTS settlement_kind VARCHAR(10);
ALTER TABLE ffa_bets  ADD COLUMN IF NOT EXISTS settlement_kind VARCHAR(10);

-- ── Unambiguous rows (payout <> amount): arithmetic alone decides. ──
-- payout < amount cannot occur with the >=1.10 odds floor, but label it
-- 'lost' defensively, matching the API helper.

UPDATE bets SET settlement_kind =
    CASE WHEN payout = 0 THEN 'lost'
         WHEN payout > amount THEN 'won'
         ELSE 'lost' END
 WHERE settled_at IS NOT NULL AND settlement_kind IS NULL AND payout <> amount;

UPDATE team_bets SET settlement_kind =
    CASE WHEN payout = 0 THEN 'lost'
         WHEN payout > amount THEN 'won'
         ELSE 'lost' END
 WHERE settled_at IS NOT NULL AND settlement_kind IS NULL AND payout <> amount;

UPDATE ffa_bets SET settlement_kind =
    CASE WHEN payout = 0 THEN 'lost'
         WHEN payout > amount THEN 'won'
         ELSE 'lost' END
 WHERE settled_at IS NOT NULL AND settlement_kind IS NULL AND payout <> amount;

-- ── Ambiguous rows (payout == amount): refund unless a recorded outcome ──
-- says this bet WON and the mode's own settle arithmetic reproduces this
-- exact payout. Frozen NOW, which is precisely the point: a refunded bet on
-- a still-active series stays 'refunded' forever even if the series
-- completes tomorrow. (Rounding note: SQL ROUND is half-away-from-zero while
-- the Python settle sites round half-even on exact .5 products; an exact .5
-- can only arise at the 1-4g ambiguous stakes with a .25/.75-ending odds —
-- vanishingly rare, and mislabels toward 'refunded', the pre-existing
-- behaviour.)

-- Codex round-2 find 16: the current parent state cannot prove a HISTORICAL
-- payout==amount row's cause — a pre-completion refund and an at-completion
-- floored small win are indistinguishable once the parent has completed
-- (there is no persisted parent-transition timestamp to order against).
-- So stamp ONLY the provable rows, and leave the genuinely ambiguous class
-- NULL — the API's legacy derivation then applies, which is exactly today's
-- behaviour (no NEW misclassification is ever frozen in).
--   Provable 'refunded' (wave-2 verification narrowed this AGAIN — the
--   previous "no valid winning outcome NOW" shape mislabelled a completed-
--   then-invalidated parent's historical win):
--   * ranked/team: the parent is STILL ACTIVE and never invalidated. A win
--     settle only ever happens at completion, completion is terminal, so a
--     settled payout==amount row under an active parent can only be the
--     stalled-sweep refund (#107's resumable-series population — exactly the
--     rows the ledger needs labelled).
--   * FFA (round-3 find N14 narrowed this once more): the lobby has NO
--     recorded match rows AT ALL. The _rN-suffix predicate was unsound —
--     the API accepts non-canonical room ids and its settlement helper
--     falls back to games_played+1, so a game's row can exist under a room
--     that never matches '%_rN'. With ZERO rows on the whole lobby, nothing
--     could ever have settled a win, so every settled bet is a refund by
--     construction.
--   Everything else — any completed, cancelled, or invalidated parent, and
--   any FFA lobby with at least one recorded game — stays NULL: the cause
--   at settlement time is unknowable from a snapshot.

UPDATE bets b SET settlement_kind = 'refunded'
  FROM ranked_series rs
 WHERE rs.id = b.series_id
   AND b.settled_at IS NOT NULL AND b.settlement_kind IS NULL
   AND rs.status = 'active'
   AND rs.invalidated_at IS NULL;

UPDATE team_bets tb SET settlement_kind = 'refunded'
  FROM team_series ts
 WHERE ts.id = tb.team_series_id
   AND tb.settled_at IS NOT NULL AND tb.settlement_kind IS NULL
   AND ts.status = 'active'
   AND ts.invalidated_at IS NULL;

UPDATE ffa_bets fb SET settlement_kind = 'refunded'
 WHERE fb.settled_at IS NOT NULL AND fb.settlement_kind IS NULL
   AND NOT EXISTS (SELECT 1 FROM ffa_matches fm
                    WHERE fm.lobby_id = fb.lobby_id);

-- Post-check: report (never fail on) the ambiguous residue left to the
-- legacy derivation.
DO $$
DECLARE n int;
BEGIN
    SELECT (SELECT COUNT(*) FROM bets      WHERE settled_at IS NOT NULL AND settlement_kind IS NULL)
         + (SELECT COUNT(*) FROM team_bets WHERE settled_at IS NOT NULL AND settlement_kind IS NULL)
         + (SELECT COUNT(*) FROM ffa_bets  WHERE settled_at IS NOT NULL AND settlement_kind IS NULL)
      INTO n;
    RAISE NOTICE 'migration 180 OK: % historically ambiguous settled row(s) left NULL for the legacy derivation', n;
END $$;
