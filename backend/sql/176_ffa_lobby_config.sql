-- 176: FFA configurable-lobby config columns — ALL defaulted to today's
-- shipped values, so no behaviour changes until an endpoint writes them
-- (config plumbing increment: server validation switches from module
-- constants to these columns; no endpoint accepts non-default values yet).
--
-- MUST run BEFORE the code deploy that reads these columns (the submit path
-- reads the lobby row via SELECT * — learning #235's ordering rule).
--
-- initial_picks is the TOTAL opening draw count (base 1 + host knob 0-3),
-- not the knob value, so the §7d floor math (T >= clamp(C+1-N, 1, C)) reads
-- one column. settings_changed_at is NULL until a host actually changes a
-- setting — a lobby that never configures anything has no 60s start gate.

ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS score_target       SMALLINT     NOT NULL DEFAULT 5;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS card_candidates    SMALLINT     NOT NULL DEFAULT 5;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS initial_picks      SMALLINT     NOT NULL DEFAULT 1;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS card_cap           SMALLINT     NOT NULL DEFAULT 5;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS same_card_rule     BOOLEAN      NOT NULL DEFAULT FALSE;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS is_ranked          BOOLEAN      NOT NULL DEFAULT TRUE;
ALTER TABLE ffa_lobbies ADD COLUMN IF NOT EXISTS settings_changed_at TIMESTAMPTZ NULL;

-- Range CHECKs as defense-in-depth behind the endpoint validation. Idempotent
-- via duplicate_object catch (ADD CONSTRAINT has no IF NOT EXISTS).
DO $$
BEGIN
    BEGIN
        ALTER TABLE ffa_lobbies ADD CONSTRAINT ck_ffa_lobby_score_target
            CHECK (score_target BETWEEN 3 AND 10);
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_lobbies ADD CONSTRAINT ck_ffa_lobby_card_candidates
            CHECK (card_candidates BETWEEN 1 AND 5);
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_lobbies ADD CONSTRAINT ck_ffa_lobby_initial_picks
            CHECK (initial_picks BETWEEN 1 AND 6);
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
    BEGIN
        ALTER TABLE ffa_lobbies ADD CONSTRAINT ck_ffa_lobby_card_cap
            CHECK (card_cap BETWEEN 3 AND 6);
    EXCEPTION WHEN duplicate_object THEN NULL;
    END;
END $$;

DO $$ BEGIN RAISE NOTICE '176 ffa_lobby_config: post-check OK'; END $$;
