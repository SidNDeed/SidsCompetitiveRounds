-- 299_rating_history_series_id.sql
-- Sept 6 batch, Group 4 item c (session report), review r1: the rating
-- snapshot a series completion writes gets the series it belongs to.
--
-- rating_history has carried no series identity since 001: the two snapshots
-- the inline Glicko update writes on series completion (main.py, "Save rating
-- history snapshots") were attributable to their series only by TIME — the
-- session report v1 looked 60 s either side of ranked_series.completed_at and
-- took the earliest hit, which associates the wrong series' rating whenever
-- two completions land close together. This column makes the link an
-- identity: the writer stamps it (raw SQL under a savepoint, so a box whose
-- schema predates this file keeps the rating update and skips the link) and
-- the report joins on it. NULLABLE (#257): NULL = "no series is attributable"
-- and the report shows the delta alone for such a set.
--
-- The column is deliberately NOT declared on the RatingHistory ORM model
-- (see the note there): the pinned-SHA deploy cannot run this file before the
-- api it ships with (#477), and an ORM column would put it on every INSERT.
-- Because of that, this migration is additive and order-independent: it can
-- ride the same SHA as the code, before or after the api build.
--
-- Backfill: one-off, deterministic, NULL rows only (re-running cannot move a
-- row that already carries a series — #168). Each unlinked snapshot is
-- attributed to the LATEST completed series of that player whose completed_at
-- is at or before the snapshot's period_end and within ten minutes of it
-- (the writer stamps period_end milliseconds after completed_at in the same
-- request, so two series 30 s apart resolve to their own snapshots). Rows
-- outside that window — the 097/104 backfills and anything anomalous — stay
-- NULL rather than be guessed. The series rows are unpivoted to one row per
-- (series, player) first so the join is an equality on player_id (hash-
-- joinable) rather than an OR across two columns. Dry-run the SELECT half
-- against the primary before applying (#313/#340); CTEs, no LATERAL.
BEGIN;

ALTER TABLE rating_history ADD COLUMN IF NOT EXISTS series_id UUID;

CREATE INDEX IF NOT EXISTS idx_rating_history_series
    ON rating_history (series_id) WHERE series_id IS NOT NULL;

WITH seats AS (
    SELECT rs.id AS series_id, rs.player1_id AS player_id, rs.completed_at
      FROM ranked_series rs
     WHERE rs.status = 'completed'
       AND rs.completed_at IS NOT NULL
       AND rs.invalidated_at IS NULL
    UNION ALL
    SELECT rs.id AS series_id, rs.player2_id AS player_id, rs.completed_at
      FROM ranked_series rs
     WHERE rs.status = 'completed'
       AND rs.completed_at IS NOT NULL
       AND rs.invalidated_at IS NULL
), cand AS (
    SELECT rh.id AS rh_id,
           s.series_id,
           ROW_NUMBER() OVER (PARTITION BY rh.id ORDER BY s.completed_at DESC) AS rn
      FROM rating_history rh
      JOIN seats s
        ON s.player_id = rh.player_id
       AND s.completed_at <= rh.period_end
       AND rh.period_end < s.completed_at + interval '10 minutes'
     WHERE rh.series_id IS NULL
)
UPDATE rating_history rh
   SET series_id = cand.series_id
  FROM cand
 WHERE cand.rh_id = rh.id
   AND cand.rn = 1;

COMMIT;
