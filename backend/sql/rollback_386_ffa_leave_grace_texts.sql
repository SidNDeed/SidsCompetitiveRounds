-- rollback_386_ffa_leave_grace_texts.sql
-- Pre-rollback text restoration for migration 386. NOT a migration: the
-- release train never lists it under schema_sql, and it is idempotent.
-- Restore the applied migration 233 column comment exactly and retire only
-- the four additive client keys introduced by 386. Delete nothing.
-- Explicit transaction (learning #340).

BEGIN;

COMMENT ON COLUMN ffa_match_players.game_points_at_leave IS
    'Total points scored by the whole field at the moment this player left, '
    'reported by a surviving client. Only ever set for left_early rows. '
    'NULL = not reported (pre-v1.39 client, or a carried roster ghost). '
    'Below FFA_LEAVE_GRACE_POINTS the player is unrated for the game.';

UPDATE i18n_keys
   SET retired_at = NOW(), updated_at = NOW()
 WHERE namespace = 'client'
   AND key_id IN (
       '79023ff50ab9d08e',
       '3bb08fc59139b367',
       '3988c8d80e42f69d',
       '439cd5d90ee1b6d3'
   )
   AND retired_at IS NULL;

COMMIT;
