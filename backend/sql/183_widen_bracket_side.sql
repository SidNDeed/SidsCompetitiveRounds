-- 183: widen tournament_matches.bracket_side VARCHAR(4) -> VARCHAR(16).
--
-- The double-elim grand-final bracket reset writes bracket_side='GF_RESET'
-- (8 chars). The column has been VARCHAR(4) since 047, so every bracket
-- reset insert would abort the enclosing transaction and the tick would
-- retry the same failure forever — a latent defect on the played-GF path
-- since double-elim shipped, made newly reachable by the forfeit-decided
-- GF terminal transitions. 049 confirms there is no CHECK constraint on
-- the column; the composite UNIQUE (tournament_id, round, bracket_side,
-- slot_idx) is unaffected by widening.
--
-- Statement-rerunnable: ALTER TYPE to the same type is a no-op-safe
-- statement (widening a varchar never rewrites rows).
ALTER TABLE tournament_matches
    ALTER COLUMN bracket_side TYPE VARCHAR(16);
