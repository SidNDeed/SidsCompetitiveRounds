-- 402_purgatory_map_skin.sql
-- The Purgatory map skin: one shop_items row (ask 4 of the 2026-11-04 batch).
--
-- Purgatory is Underworld's load-order state, held: for the first seconds
-- after an art switch the client's deferred tint pass has not run, so an
-- Underworld map shows its Soviet base art at the art's own colours (a
-- plum-violet haze, indigo at the edges, rust wall glow) over Underworld's
-- painted canvas, grading, lighting and embers. The client preset
-- mapcolor_purgatory (plugin/CustomMapColors.cs, KeepBaseArtColors) renders
-- that frame on purpose; this row sells it.
--
-- Pricing follows precedent and is SID'S BALANCE KNOB (#331): a skin that
-- carries an ambient particle effect (embers) is 150g rare, migration 246's
-- tier. rotation_pool is deliberately omitted (NULL): list_shop_items hides
-- any row with a pool. catalog_ready keeps its TRUE default (non-face kinds
-- need no bundled art). preview_color is the whole-frame colour measured on
-- the captured screenshots (ai-collab/asks/assets-2026-11-04/).
--
-- min_client_version (397): a client without the preset has no renderer for
-- the sku (CustomMapColors.IsCustomSku false) and would buy a skin it shows
-- as vanilla, so the row is hidden from, and refused to, clients below the
-- release that carries the preset. THE VALUE BELOW IS A PLACEHOLDER: the
-- integrator sets it to the carrying client release before applying.
--
-- Idempotent via ON CONFLICT (sku) DO NOTHING; explicit transaction because
-- psql -f does not add one (#340). A re-run inserts nothing. The INSERT is
-- the file's only statement and runs unconditionally on a FIRST application
-- by design: there is no catalog guard because the conflict target is the
-- row itself.
--
-- The shop_item_release_provenance table (397 section 2) records what a
-- RELEASE migration publishes for bundled faces (placement revision,
-- description before and after); a colour skin has no placement and no prior
-- description, so this file writes no provenance row, like 246.
--
-- Rollback: rollback_402_purgatory_map_skin.sql (refuses while any player
-- owns the item).
--
-- DEPLOY ORDER: THIS FILE FIRST, any time after 397 (the column it writes);
-- the api needs no change, and min_client_version keeps the row invisible to
-- every client below the carrying release until that release ships.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

INSERT INTO shop_items (sku, kind, name, description, price, rarity, preview_color, min_client_version) VALUES
('mapcolor_purgatory', 'color', 'Purgatory',
 'Plum-violet haze over a blood-dark sky, indigo at the edges, the walls glowing rust, red embers rising.',
 150, 'rare', '#4C1648', '1.42.0')
ON CONFLICT (sku) DO NOTHING;

COMMIT;
