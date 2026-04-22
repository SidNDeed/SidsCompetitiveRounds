-- v1.23.x — One-shot: zero Sid's blocks_activated + blocks_successful so he can validate
-- the v1.23 block-dedup fix against a clean baseline. Other players' counters untouched.
--
-- Idempotent (UPDATE to 0 re-runs as a no-op).

UPDATE players
   SET blocks_activated = 0,
       blocks_successful = 0
 WHERE steam_id = '76561198040410653';
