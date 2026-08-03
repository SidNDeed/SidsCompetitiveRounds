-- 188: repair the one structurally unapprovable seeded proposal (Codex Aug-3
-- r4 find 2). The RU draft for the 2v2 scroll hint substituted U+25BC for
-- the source's ASCII 'v'; U+25BC is outside the RU allowlist and not
-- source-carried, so approving that pending proposal 422s forever. The
-- embedded catalogue and migration 184's seed literal are already corrected
-- in-repo — but 184 is live and its rerun guard (correctly) skips
-- ever-seeded tuples, so the LIVE pending row needs this in-place fix.
-- Narrow by construction: pending only, sentinel proposer only, and only
-- while the target still contains the offending glyph — a moderator's
-- decided/edited state is never touched. Rerunnable: second run matches
-- zero rows.

UPDATE i18n_proposals
   SET proposed_target = REPLACE(proposed_target, U&'\25BC', 'v')
 WHERE key_id = '2b2a2115ec5b8f48'
   AND language_code = 'ru'
   AND proposer_steam_id = 'claude-mt'
   AND status = 'pending'
   AND proposed_target LIKE '%' || U&'\25BC' || '%';

-- (ROW_COUNT of the UPDATE is not observable from a separate DO statement;
-- the absence check below is the real postcondition.)
DO $$
DECLARE remaining INT;
BEGIN
  SELECT COUNT(*) INTO remaining FROM i18n_proposals
   WHERE proposer_steam_id = 'claude-mt' AND status = 'pending'
     AND proposed_target LIKE '%' || U&'\25BC' || '%';
  RAISE NOTICE 'migration 188 OK: % pending sentinel proposals still carry U+25BC (0 expected)', remaining;
END $$;
