-- 166: FFA host-lobby redesign — schema half.
-- Adds the host role to ffa_lobbies. New status values ('open' on ffa_lobbies,
-- 'lobby' on ffa_queue) need no DDL: both status columns are unconstrained
-- varchar(16). Idempotent; safe to run before the API deploy (the live code
-- never reads the new column until the lobby endpoints ship).

ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS host_player_id UUID REFERENCES players(id);

-- Browser listing: open lobbies newest-first.
CREATE INDEX IF NOT EXISTS idx_ffa_lobbies_open
    ON ffa_lobbies (created_at DESC) WHERE status = 'open';

DO $$
BEGIN
    RAISE NOTICE 'migration 166 post-check: host_player_id present = %',
        (SELECT COUNT(*) FROM information_schema.columns
          WHERE table_name = 'ffa_lobbies' AND column_name = 'host_player_id');
END $$;
