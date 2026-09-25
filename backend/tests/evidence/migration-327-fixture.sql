
DROP TABLE IF EXISTS ffa_matches CASCADE;
CREATE TABLE ffa_matches (
    id UUID PRIMARY KEY,
    lobby_id UUID,
    photon_room_id VARCHAR(64) NOT NULL,
    player_count SMALLINT NOT NULL DEFAULT 3,
    ended_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at TIMESTAMPTZ,
    CONSTRAINT uq_ffa_match_room UNIQUE (photon_room_id)
);
INSERT INTO ffa_matches (id, lobby_id, photon_room_id, ended_at) VALUES
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1', 'rmA_211531_r1', '2026-08-07 21:15:31Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1', 'rmA_211532_r1', '2026-08-07 21:16:28Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1', 'rmA_212540_r2', '2026-08-07 21:25:40Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_100000_r4', '2026-08-08 10:00:00Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_101000_r0', '2026-08-08 10:10:00Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_102000_r99999', '2026-08-08 10:20:00Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_no_tail_here', '2026-08-08 10:30:00Z'),
  (gen_random_uuid(), NULL, 'orphan_room_no_tail', '2026-08-09 09:00:00Z');
