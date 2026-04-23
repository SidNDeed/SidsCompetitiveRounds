-- ============================================================
-- Migrate voting-state sync tournaments to double-elim BO3
-- ============================================================
-- Sync tournaments now run double-elim (same as async). Parallel play
-- makes the wall-clock time manageable (~90-120min for 16p). The bracket
-- isn't generated until lock, so updating the format in place on a
-- voting-state tournament is safe.
-- Classification: additive — only updates rows in 'voting' state.
-- ============================================================

UPDATE tournaments
   SET format = 'double_elim_bo3'
 WHERE kind = 'sync'
   AND status = 'voting'
   AND format = 'single_elim_bo3';
