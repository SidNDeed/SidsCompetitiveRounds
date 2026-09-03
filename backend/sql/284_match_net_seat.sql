-- 284: reporter-seat network telemetry for Release A W1.
--
-- Each authenticated 1v1 reporter populates only its own p1/p2 seat. The
-- opposite seat remains NULL: zero means observed zero, while NULL means no
-- evidence was submitted for that seat. These advisory fields are not public
-- response data and are outside every frozen match HMAC canonical.
--
-- All 50 columns are nullable with no defaults. The migration is additive
-- and idempotent statement-by-statement; it must run before the API model
-- that includes these columns is deployed.

BEGIN;

ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_writes INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_unchanged INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_move_raise_attempted INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_move_raise_accepted INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_resent_reliable INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_discarded INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_crc_loss INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_queued_out_max INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_queued_in_max INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_fragment_cmds INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_view_update_faults INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_hitch50 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_hitch200 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_worst_frame_ms INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_gap300 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_gap750 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_gap1500 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_max_gap_ms INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_excess150 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_max_excess_ms INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_payload_equal_gaps INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_receiver_frame_gaps INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_phoenix_intervals INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_obs_batches INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p1_net_worst_frame_tags VARCHAR(48);

ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_writes INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_unchanged INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_move_raise_attempted INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_move_raise_accepted INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_resent_reliable INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_discarded INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_crc_loss INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_queued_out_max INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_queued_in_max INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_fragment_cmds INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_view_update_faults INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_hitch50 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_hitch200 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_worst_frame_ms INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_gap300 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_gap750 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_gap1500 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_max_gap_ms INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_excess150 INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_max_excess_ms INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_payload_equal_gaps INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_receiver_frame_gaps INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_phoenix_intervals INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_obs_batches INTEGER;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS p2_net_worst_frame_tags VARCHAR(48);

COMMIT;
