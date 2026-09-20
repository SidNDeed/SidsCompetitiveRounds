-- Minimal FFA schema for the bug #392 DSN-gated tests.
--
-- Transcribed from the PRIMARY's own catalogue (`ssh ccdeploy@<primary>
-- 'sql-readonly:\d ffa_lobbies'` / `\d ffa_match_players`, read 2026-09-20),
-- restricted to the tables and columns migration 326 and the changed
-- statements actually touch. Column TYPES and NOT NULL/DEFAULT are copied
-- exactly, because the whole point of running against a real PostgreSQL is
-- that the types are the ones production has: a uuid[] that were text[], or a
-- smallint default that were absent, would make every result here evidence
-- about a different schema.
--
-- Not a substitute for the migration series. Nothing here is shipped; it
-- exists only so the tests can build the tables that migration 326 alters.

DROP TABLE IF EXISTS ffa_match_players;
DROP TABLE IF EXISTS ffa_matches;
DROP TABLE IF EXISTS ffa_lobbies;
DROP TABLE IF EXISTS players;

CREATE TABLE players (
    id           UUID PRIMARY KEY,
    steam_id     VARCHAR(32) NOT NULL UNIQUE,
    display_name VARCHAR(64)
);

CREATE TABLE ffa_lobbies (
    id                  UUID PRIMARY KEY,
    status              VARCHAR(16) NOT NULL DEFAULT 'active',
    photon_room_id      VARCHAR(64),
    player_count        SMALLINT NOT NULL DEFAULT 0,
    member_ids          UUID[] NOT NULL DEFAULT '{}'::uuid[],
    games_played        INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    invalidated_at      TIMESTAMPTZ,
    invalidation_reason VARCHAR(64),
    departed_ids        UUID[] NOT NULL DEFAULT '{}'::uuid[],
    host_player_id      UUID,
    is_ranked           BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE ffa_matches (
    id        UUID PRIMARY KEY,
    lobby_id  UUID REFERENCES ffa_lobbies(id) ON DELETE CASCADE,
    ended_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ffa_match_players (
    match_id              UUID NOT NULL REFERENCES ffa_matches(id) ON DELETE CASCADE,
    player_id             UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    slot                  SMALLINT,
    rounds_won            SMALLINT NOT NULL DEFAULT 0,
    points_total          SMALLINT NOT NULL DEFAULT 0,
    placement             SMALLINT NOT NULL,
    left_early            BOOLEAN NOT NULL DEFAULT false,
    rating_before         DOUBLE PRECISION,
    rating_after          DOUBLE PRECISION,
    rating_change         DOUBLE PRECISION,
    xp_gained             INTEGER NOT NULL DEFAULT 0,
    gold_gained           INTEGER NOT NULL DEFAULT 0,
    fps_avg               SMALLINT,
    ping_avg              SMALLINT,
    bullets_fired         INTEGER,
    bullets_hit           INTEGER,
    blocks_activated      INTEGER,
    blocks_successful     INTEGER,
    keys_pressed          INTEGER,
    active_seconds        REAL,
    fps_timeline          VARCHAR(512),
    ping_timeline         VARCHAR(512),
    hit_timeline          VARCHAR(1024),
    block_timeline        VARCHAR(1024),
    kills                 INTEGER NOT NULL DEFAULT 0,
    damage_dealt          INTEGER,
    damage_dealt_timeline VARCHAR(1024),
    kill_timeline         VARCHAR(512),
    absent                BOOLEAN NOT NULL DEFAULT false,
    color_name            VARCHAR(40),
    color_hex             VARCHAR(9),
    end_stats             TEXT,
    game_points_at_leave  SMALLINT,
    PRIMARY KEY (match_id, player_id)
);
