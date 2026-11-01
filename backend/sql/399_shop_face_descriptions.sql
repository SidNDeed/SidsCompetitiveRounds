-- 399: real shop descriptions for the 19 published community faces that still
-- carry the approval placeholder.
--
-- DATA ONLY: one column (shop_items.description) on 19 rows. No schema, no
-- api, no client change. Client-compatible on every client: the api serves the
-- column as-is (GET /api/v1/shop/items, "description": r.description) and the
-- client shows it through I18n.Tr (plugin/NativeUI.cs, the shop card).
--
-- WHY. Approval writes "<Slot>: community cosmetic. Ships with the next mod
-- update; equip in the Character editor." on every new face (backend/api/
-- main.py, the approve path). Once the face is published that sentence is
-- false. Migration 398 replaces it on the five faces it publishes; these 19
-- were published earlier and kept it. Read on the primary 2026-10-30 through
-- the read-only verb: exactly 19 rows are catalog_ready with one of the three
-- placeholders (14 Detail, 3 Eyes, 2 Mouth), all kind face, rotation_pool
-- NULL; the other five placeholder rows are 398's (catalog_ready false).
--
-- THE NEW TEXT keeps the house form of the shop's own face descriptions
-- ("Detail: heavy is the head. Equip in the Character editor."): the slot,
-- what the item is, and where to equip it. Each was written from the bundled
-- art (plugin/cosmetics/<file>.png); the two animated faces (Fps in their
-- CosmeticDef) say "(animated)", as Star Spin does.
--
-- TRANSLATIONS. The client translates a description by its exact English
-- text from the catalogues bundled in the DLL (plugin/I18nCatalogues.cs). The
-- placeholders have es/ru/uk/sv rows in every shipped client; the 19 new
-- texts get theirs on the client-strings branch
-- (claude/shop-descriptions-1410-i18n). Until a client carrying those rows is
-- out, a reader in those four languages sees the new text in English. Land
-- this file after that client ships to keep their descriptions translated.
--
-- GUARDS. Rows are keyed by id, and the sku and kind must agree (a mismatch
-- RAISES, whole transaction). A row changes only while it is published
-- (catalog_ready IS TRUE) and still holds ITS exact placeholder; a row already
-- carrying the new text is a no-op, so a rerun changes nothing; any other
-- description (an artist's own, set through artist/set-desc) is left alone
-- with a NOTICE. Every decision is total (IS TRUE / IS [NOT] DISTINCT FROM).
-- The post-check counts the rows holding the new text and RAISES unless it
-- equals the rows written plus the rows found already written.
-- Rollback: rollback_399_shop_face_descriptions.sql.
--
-- LOCK FIRST, THEN JUDGE. The DO block's first statement locks the 19 rows
-- FOR NO KEY UPDATE in id order and holds them to COMMIT, so the value each
-- decision reads is the value the UPDATE replaces. A writer holding one of
-- them past lock_timeout (5 s) aborts this file whole, changing nothing;
-- rerun it. `psql -f` does not wrap a file in a transaction, so this file
-- does (#340). Lock bound (#1072): wait 5 s; hold 25 s + 5 s plus the
-- COMMIT's local completion.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $$
DECLARE
    -- [shop_item_id, sku, placeholder it holds now, new description]
    expected CONSTANT TEXT[][] := ARRAY[
        ['250', 'face_detail_spooky_head_bouncers', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a headband of grinning pumpkins and a little ghost bobbing on springs. Equip in the Character editor.'],
        ['251', 'face_detail_ballooniphones', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a pink headband with round ears, puffy ear pads and a unicorn horn. Equip in the Character editor.'],
        ['252', 'face_detail_soda_helm', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a headband with two fizzy soda cans and a long drinking straw. Equip in the Character editor.'],
        ['253', 'face_detail_brain_cane', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a candy cane that looks stuck right through your head. Equip in the Character editor.'],
        ['254', 'face_mouth_casi_s_mouth', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Mouth: a wide open grin with a red tongue. Equip in the Character editor.'],
        ['255', 'face_eyes_casicorn_s_eyes', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Eyes: big round eyes with lashes and a bright shine. Equip in the Character editor.'],
        ['256', 'face_detail_little_pink_buddy', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a small round pink buddy with a surprised face. Equip in the Character editor.'],
        ['257', 'face_detail_sniper_medal', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a gold medal with a crosshair, hung on a red ribbon. Equip in the Character editor.'],
        ['258', 'face_detail_spilled_icecream', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: an ice cream cone tipped upside down, melting over your head. Equip in the Character editor.'],
        ['259', 'face_detail_magical_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a blue top hat with a red band and a star wand, held up by two white gloves (animated). Equip in the Character editor.'],
        ['260', 'face_detail_twisted_topper', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: an orange and grey striped top hat with a grumpy face badge. Equip in the Character editor.'],
        ['267', 'face_eyes_poison_s_eyes', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Eyes: two green curves for calm, closed eyes. Equip in the Character editor.'],
        ['268', 'face_mouth_poison_s_mouth', 'Mouth: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Mouth: a small green frown. Equip in the Character editor.'],
        ['269', 'face_detail_poison_s_weeping', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: green tear streaks running down both cheeks. Equip in the Character editor.'],
        ['270', 'face_detail_seasonal_spring', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a green coiled spring dressed as a festive tree, with baubles and a gold star on top (animated). Equip in the Character editor.'],
        ['271', 'face_eyes_nuclear_glasses', 'Eyes: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Eyes: red and yellow goggles marked with the radiation symbol. Equip in the Character editor.'],
        ['329', 'face_detail_well_wraped_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a top hat wrapped like a present, with an orange ribbon and bow. Equip in the Character editor.'],
        ['356', 'face_detail_straw_hat', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a wide woven straw hat with a red band. Equip in the Character editor.'],
        ['357', 'face_detail_florabelle', 'Detail: community cosmetic. Ships with the next mod update; equip in the Character editor.', 'Detail: a green vine crown with white daisies. Equip in the Character editor.']
    ];
    -- v_ prefixes, never bare column names (#442: a bare identifier resolves
    -- as the PL/pgSQL variable and makes a WHERE ambiguous).
    v_id       BIGINT;
    v_sku      TEXT;
    v_old      TEXT;
    v_new      TEXT;
    si_rec     RECORD;
    n_rows     INT;
    n_holding  INT;
    written    INT := 0;
    already    INT := 0;
    left_alone INT := 0;
BEGIN
    -- Lock first, then judge (see the header).
    PERFORM 1 FROM shop_items si
     WHERE si.id IN (SELECT CAST(expected[j][1] AS BIGINT)
                       FROM generate_subscripts(expected, 1) AS j)
     ORDER BY si.id
       FOR NO KEY UPDATE;

    FOR i IN 1 .. array_length(expected, 1) LOOP
        v_id  := CAST(expected[i][1] AS BIGINT);
        v_sku := expected[i][2];
        v_old := expected[i][3];
        v_new := expected[i][4];

        SELECT si.sku, si.kind, si.catalog_ready, si.description
          INTO si_rec
          FROM shop_items si
         WHERE si.id = v_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION '399: shop item % (%) does not exist; nothing was changed', v_id, v_sku;
        END IF;
        IF si_rec.sku IS DISTINCT FROM v_sku THEN
            RAISE EXCEPTION '399: shop item % holds sku %, not %; nothing was changed', v_id, si_rec.sku, v_sku;
        END IF;
        IF si_rec.kind IS DISTINCT FROM 'face' THEN
            RAISE EXCEPTION '399: shop item % (%) is kind %, not face; nothing was changed', v_id, v_sku, si_rec.kind;
        END IF;

        IF si_rec.description IS NOT DISTINCT FROM v_new THEN
            already := already + 1;
        ELSIF si_rec.description IS NOT DISTINCT FROM v_old AND si_rec.catalog_ready IS TRUE THEN
            UPDATE shop_items si
               SET description = v_new
             WHERE si.id = v_id
               AND si.description = v_old
               AND si.catalog_ready IS TRUE;
            GET DIAGNOSTICS n_rows = ROW_COUNT;
            IF n_rows IS DISTINCT FROM 1 THEN
                RAISE EXCEPTION '399: % (%) changed % rows, not 1; nothing was changed', v_sku, v_id, n_rows;
            END IF;
            written := written + 1;
        ELSE
            left_alone := left_alone + 1;
            RAISE NOTICE '399: % (%) left alone: it is unpublished, or its description is neither its placeholder nor the new text', v_sku, v_id;
        END IF;
    END LOOP;

    -- Post-check: every row this file wrote, or found written, holds its new
    -- text now.
    SELECT count(*) INTO n_holding
      FROM generate_subscripts(expected, 1) AS j
      JOIN shop_items si
        ON si.id = CAST(expected[j][1] AS BIGINT)
       AND si.sku = expected[j][2]
       AND si.description = expected[j][4];
    IF n_holding IS DISTINCT FROM written + already THEN
        RAISE EXCEPTION '399: post-check found % rows holding the new text, expected %; nothing was changed', n_holding, written + already;
    END IF;

    RAISE NOTICE '399: % descriptions written, % already written, % left alone', written, already, left_alone;
END $$;

COMMIT;
