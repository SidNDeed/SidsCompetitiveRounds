-- Rollback of 399: put the approval placeholder back on the 19 faces, but
-- only on a row that still holds the text 399 wrote. A row whose description
-- someone changed after 399 is theirs and is left alone, with a NOTICE; a row
-- already holding its placeholder is a no-op, so a rerun changes nothing.
-- Rows are keyed by id; the sku and kind must agree or the whole file RAISES.
-- Same lock order, bounds and transaction as 399 (lock first, then judge;
-- #340, #1072).

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

DO $$
DECLARE
    -- [shop_item_id, sku, placeholder to restore, text 399 wrote]
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
    v_id       BIGINT;
    v_sku      TEXT;
    v_old      TEXT;
    v_new      TEXT;
    si_rec     RECORD;
    n_rows     INT;
    n_holding  INT;
    restored   INT := 0;
    already    INT := 0;
    left_alone INT := 0;
BEGIN
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

        SELECT si.sku, si.kind, si.description
          INTO si_rec
          FROM shop_items si
         WHERE si.id = v_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'rollback_399: shop item % (%) does not exist; nothing was changed', v_id, v_sku;
        END IF;
        IF si_rec.sku IS DISTINCT FROM v_sku THEN
            RAISE EXCEPTION 'rollback_399: shop item % holds sku %, not %; nothing was changed', v_id, si_rec.sku, v_sku;
        END IF;
        IF si_rec.kind IS DISTINCT FROM 'face' THEN
            RAISE EXCEPTION 'rollback_399: shop item % (%) is kind %, not face; nothing was changed', v_id, v_sku, si_rec.kind;
        END IF;

        IF si_rec.description IS NOT DISTINCT FROM v_old THEN
            already := already + 1;
        ELSIF si_rec.description IS NOT DISTINCT FROM v_new THEN
            UPDATE shop_items si
               SET description = v_old
             WHERE si.id = v_id
               AND si.description = v_new;
            GET DIAGNOSTICS n_rows = ROW_COUNT;
            IF n_rows IS DISTINCT FROM 1 THEN
                RAISE EXCEPTION 'rollback_399: % (%) changed % rows, not 1; nothing was changed', v_sku, v_id, n_rows;
            END IF;
            restored := restored + 1;
        ELSE
            left_alone := left_alone + 1;
            RAISE NOTICE 'rollback_399: % (%) left alone: its description is neither the text 399 wrote nor its placeholder', v_sku, v_id;
        END IF;
    END LOOP;

    SELECT count(*) INTO n_holding
      FROM generate_subscripts(expected, 1) AS j
      JOIN shop_items si
        ON si.id = CAST(expected[j][1] AS BIGINT)
       AND si.sku = expected[j][2]
       AND si.description = expected[j][3];
    IF n_holding IS DISTINCT FROM restored + already THEN
        RAISE EXCEPTION 'rollback_399: post-check found % rows holding the placeholder, expected %; nothing was changed', n_holding, restored + already;
    END IF;

    RAISE NOTICE 'rollback_399: % placeholders restored, % already restored, % left alone', restored, already, left_alone;
END $$;

COMMIT;
