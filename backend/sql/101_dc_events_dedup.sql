-- 101_dc_events_dedup.sql
-- Per-series disconnect dedup for the hardened /report-disconnect endpoint.
-- Before this, the endpoint was unauthenticated and loopable to inflate any
-- player's ranked_dc_count (leave-% smearing). The handler now (a) requires a
-- recent shared ranked series and (b) records the DC here so the same
-- (series, disconnected player) can only count once. Idempotent.
CREATE TABLE IF NOT EXISTS dc_events (
    id                      BIGSERIAL PRIMARY KEY,
    series_id               UUID NOT NULL,
    disconnected_player_id  UUID NOT NULL,
    reporter_player_id      UUID NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dc_event_series_player UNIQUE (series_id, disconnected_player_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_events_series ON dc_events (series_id);
