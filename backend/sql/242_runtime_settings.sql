-- 242: generic runtime_settings key-value store.
-- First consumer: the MIN_MOD_VERSION auto-raise. Sid's rule (Aug 22):
-- 10+ unique adopters of LATEST + no older-version player online for 10
-- minutes -> the API raises the live floor and persists it here; boot
-- restores min(max(valid stored, compiled constant), LATEST), rejecting
-- non-dotted-integer values and capping values above LATEST. Deployment
-- invariant: after a raise, do not roll back to a pre-feature binary; it
-- cannot read this setting and uses its compiled floor.

BEGIN;

CREATE TABLE IF NOT EXISTS runtime_settings (
    key        VARCHAR(64) PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
