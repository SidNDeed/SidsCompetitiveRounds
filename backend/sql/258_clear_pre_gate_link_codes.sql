-- 258: invalidate every Discord link code minted BEFORE the mint was gated.
--
-- Until 2026-08-25, POST /api/v1/players/link-code took a bare steam_id with NO
-- authentication: anyone could read a steam_id off the public leaderboard, mint
-- that account's code, and then bind their own Discord to it by typing
-- "!link <code>" (the /link-discord half is bot-gated, but that gate only ever
-- checked that the BOT was calling -- never that the caller owned the account).
--
-- The mint now requires a verified Steam session. Any code outstanding at that
-- moment was minted under the old rules and cannot be shown to have been
-- requested by the account's owner, so it is retired rather than left to live
-- out its TTL.
--
-- Cost of being wrong: one button press -- the player clicks "Get Link Code"
-- again. Cost of not doing it: honouring a credential minted under a rule that
-- has just been removed.
--
-- PROVENANCE CUTOFF, not a blanket DELETE (review find 4). The first version ran
-- an unconditional `DELETE FROM link_codes` and claimed a re-run was harmless.
-- It is not: the deploy wrapper re-executes the whole file on any nonzero exit,
-- and nothing stops this being applied again later by hand -- either of which
-- would silently delete a legitimate code a player had JUST minted under the new
-- gate and was in the middle of typing into Discord. Deleting only rows created
-- before the cutoff makes the statement mean what the comment says, on every
-- run, forever. Codes live 10 minutes, so anything minted post-gate is created
-- well after this timestamp and is untouched.

BEGIN;

DO $$
DECLARE
    cutoff  CONSTANT TIMESTAMPTZ := TIMESTAMPTZ '2026-08-25 07:00:00+00';
    killed  INT;
    kept    INT;
BEGIN
    DELETE FROM link_codes WHERE created_at < cutoff;
    GET DIAGNOSTICS killed = ROW_COUNT;

    SELECT COUNT(*) INTO kept FROM link_codes;

    -- Can actually fail: anything older than the cutoff still present means the
    -- delete did not do what this migration claims.
    IF EXISTS (SELECT 1 FROM link_codes WHERE created_at < cutoff) THEN
        RAISE EXCEPTION 'pre-gate link codes still present after delete';
    END IF;

    RAISE NOTICE 'post-check OK: retired % pre-gate link code(s); % post-gate code(s) left untouched',
                 killed, kept;
END $$;

COMMIT;
