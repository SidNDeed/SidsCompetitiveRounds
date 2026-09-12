-- 309: the 1v1 wait clock a rejoin keeps (Sept 12). NULL = joined_at.
-- joined_at stays the row's insert time, which the cross-queue eviction
-- reads as its fence; the candidate scan reads COALESCE(wait_since,
-- joined_at) and the poll applies the same rule. Nothing in the running api
-- reads the column before the code deploy, so this file ships as the
-- migrations-only precursor of the two-SHA order.
--
-- A kept clock belongs to ONE row incarnation. Whenever any writer moves
-- joined_at -- a join over a live row, a reset, or an api build that
-- predates this column and so cannot clear it -- the kept clock goes with
-- the old incarnation. The join's own UPDATE sets wait_since without
-- touching joined_at, so it never trips this.
BEGIN;
ALTER TABLE ranked_queue ADD COLUMN IF NOT EXISTS wait_since TIMESTAMPTZ;

CREATE OR REPLACE FUNCTION ranked_queue_clear_wait_since() RETURNS trigger AS $$
BEGIN
    IF NEW.joined_at IS DISTINCT FROM OLD.joined_at THEN
        NEW.wait_since := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ranked_queue_wait_since_reset ON ranked_queue;
CREATE TRIGGER ranked_queue_wait_since_reset
    BEFORE UPDATE OF joined_at ON ranked_queue
    FOR EACH ROW EXECUTE FUNCTION ranked_queue_clear_wait_since();
COMMIT;
