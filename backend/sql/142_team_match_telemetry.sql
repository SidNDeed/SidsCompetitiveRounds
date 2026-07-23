-- 142_team_match_telemetry.sql — July 22 (2v2 Recent Series stats/graphs parity)
--
-- ============================================================================
-- !! DEPLOY ORDER: apply BEFORE the API deploy — submit_team_match inserts
-- !! into this table and /team/all-series-paged SELECTs it.
-- ============================================================================
--
-- Per-player telemetry for 2v2 games, child table keyed like team_match_cards
-- (053). One row per (match, player); rows exist only for players whose data
-- reached the reporter (old-client peers produce no row — render as "-").
-- Timelines share the 1v1 wire formats: fps = "142,138,...", ping = "23,41,...",
-- hit = "fired:hit,...", block = "dmgTaken:blocksSucc,...".

CREATE TABLE IF NOT EXISTS team_match_telemetry (
    match_id  UUID NOT NULL REFERENCES team_matches(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id),
    fps_timeline   VARCHAR(512),
    ping_timeline  VARCHAR(512),
    ping_avg       SMALLINT,
    hit_timeline   VARCHAR(1024),
    block_timeline VARCHAR(1024),
    bullets_fired      INTEGER,
    bullets_hit        INTEGER,
    blocks_activated   INTEGER,
    blocks_successful  INTEGER,
    keys_pressed       INTEGER,
    active_seconds     DOUBLE PRECISION,
    PRIMARY KEY (match_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_tmt_match ON team_match_telemetry (match_id);
