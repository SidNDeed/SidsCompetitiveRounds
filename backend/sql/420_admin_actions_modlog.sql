-- 420_admin_actions_modlog.sql
-- The moderator log per player (work order MODLOG-1): two columns on
-- admin_actions, their index, and the players and reasons of the rows
-- written before this file.
--
-- 1. admin_actions.affected_steam_ids (text[], NOT NULL, DEFAULT '{}'): every
--    player the action acts on, by Steam id, at most 16 (the api's writer,
--    main._modlog_write, refuses more). The GIN index
--    ix_admin_actions_affected serves "this id is in the array"
--    (affected_steam_ids @> ARRAY[id]), the per-player read of
--    /api/v1/admin/modlog.
-- 2. admin_actions.reason (text, NULL): the reason the actor gave, at most
--    256 characters (CHECK ck_admin_actions_reason_len).
--    The existing columns keep their meaning. The api before this file
--    names neither column, so this file goes BEFORE the code.
-- 3. The old rows (every row written before this file has '{}'): the array
--    is filled from what the row names, and reason from details->>'reason'.
--    An id enters the array only when it is 17 digits and comes from
--      - the row's own target_steam_id (delete_player_data replaces an
--        exact match of this column with the account's tombstone), or
--      - the CURRENT players row reached by a join (delete_player_data
--        rewrites players.steam_id to the tombstone): a 1v1 series' two
--        players (ranked_series.player1_id/player2_id), a 2v2 series' four
--        (team_series slots), a match's two (matches.player1_id/player2_id,
--        by target_match_id or by details->>'match_id' of a record
--        exclusion), a reversed trade's two parties (pc_trades.pair_lo/
--        pair_hi, by the trade id the row keeps in target_steam_id), and a
--        deleted chat message's author (chat_messages by details message_id
--        or message_ids, then players by the message's steam_id; deletion
--        rewrites chat_messages.steam_id to the tombstone too).
--    No id is read from details: delete_player_data does not scrub details,
--    so an id copied there may be a deleted account's raw id. A row whose
--    target_steam_id is already a tombstone keeps '{}'. Only rows still at
--    '{}' are filled (and only reasons still NULL), so a second run changes
--    nothing.
--
-- Refusals (nothing is changed then, one transaction): a column of either
-- name with another type, an index named ix_admin_actions_affected that is
-- not the GIN index on affected_steam_ids, or a constraint named
-- ck_admin_actions_reason_len with another definition.
--
-- psql -f does not wrap a file in a transaction (learning #340): BEGIN and
-- COMMIT are explicit. Re-runnable: every DDL is guarded on the catalog and
-- each fill on the absence of its own result. admin_actions has no foreign
-- key (migration 192 dropped its only one), so neither the fill nor a later
-- insert locks another table's row.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL statement_timeout = '60s';
SET LOCAL synchronous_commit = local;

DO $m420$
DECLARE
  got text;
  idx text;
  con text;
BEGIN
  -- Refusals first: a name that exists with another shape.
  SELECT format_type(a.atttypid, a.atttypmod) INTO got
    FROM pg_attribute a
   WHERE a.attrelid = to_regclass(format('%I.admin_actions', current_schema()))
     AND a.attname = 'affected_steam_ids' AND NOT a.attisdropped;
  IF got IS NOT NULL AND got <> 'text[]' THEN
    RAISE EXCEPTION '420: admin_actions.affected_steam_ids is %, not text[]; nothing changed', got;
  END IF;
  SELECT format_type(a.atttypid, a.atttypmod) INTO got
    FROM pg_attribute a
   WHERE a.attrelid = to_regclass(format('%I.admin_actions', current_schema()))
     AND a.attname = 'reason' AND NOT a.attisdropped;
  IF got IS NOT NULL AND got <> 'text' THEN
    RAISE EXCEPTION '420: admin_actions.reason is %, not text; nothing changed', got;
  END IF;
  IF to_regclass(format('%I.ix_admin_actions_affected', current_schema())) IS NOT NULL THEN
    SELECT pg_get_indexdef(i.indexrelid) INTO idx
      FROM pg_index i
     WHERE i.indexrelid = to_regclass(format('%I.ix_admin_actions_affected', current_schema()))
       AND i.indrelid = to_regclass(format('%I.admin_actions', current_schema()))
       AND i.indisvalid;
    IF idx IS NULL OR idx NOT LIKE '%INDEX ix_admin_actions_affected ON %admin_actions USING gin (affected_steam_ids)' THEN
      RAISE EXCEPTION '420: ix_admin_actions_affected is %, not the GIN index 420 creates; nothing changed',
        coalesce(idx, 'not an index of admin_actions');
    END IF;
  END IF;
  SELECT pg_get_constraintdef(c.oid) INTO con
    FROM pg_constraint c
   WHERE c.conname = 'ck_admin_actions_reason_len'
     AND c.conrelid = to_regclass(format('%I.admin_actions', current_schema()));
  IF con IS NOT NULL AND con <> 'CHECK (((reason IS NULL) OR (char_length(reason) <= 256)))' THEN
    RAISE EXCEPTION '420: ck_admin_actions_reason_len is %, not the check 420 creates; nothing changed', con;
  END IF;

  -- The columns, the check and the index.
  ALTER TABLE admin_actions ADD COLUMN IF NOT EXISTS affected_steam_ids TEXT[] NOT NULL DEFAULT '{}';
  ALTER TABLE admin_actions ADD COLUMN IF NOT EXISTS reason TEXT NULL;
  IF con IS NULL THEN
    ALTER TABLE admin_actions ADD CONSTRAINT ck_admin_actions_reason_len
      CHECK (reason IS NULL OR char_length(reason) <= 256);
  END IF;
  CREATE INDEX IF NOT EXISTS ix_admin_actions_affected
      ON admin_actions USING gin (affected_steam_ids);
  COMMENT ON COLUMN admin_actions.affected_steam_ids IS
    'Every player the action acts on, by Steam id, at most 16 (migration 420); ''{}'' when it names none.';
  COMMENT ON COLUMN admin_actions.reason IS
    'The reason the actor gave, at most 256 characters (migration 420); NULL when none.';

  -- Post-check: the shape the code relies on.
  SELECT format_type(a.atttypid, a.atttypmod) INTO got
    FROM pg_attribute a
   WHERE a.attrelid = to_regclass(format('%I.admin_actions', current_schema()))
     AND a.attname = 'affected_steam_ids' AND NOT a.attisdropped AND a.attnotnull;
  IF got IS DISTINCT FROM 'text[]' THEN
    RAISE EXCEPTION '420: admin_actions.affected_steam_ids is %, not text[] NOT NULL', coalesce(got, 'missing');
  END IF;
END $m420$;

-- 3. The old rows' players. Only a row still at '{}' whose target is not a
-- tombstone; only 17-digit ids; at most 16 (a row's sources name at most 4).
UPDATE admin_actions aa
   SET affected_steam_ids = c.ids
  FROM (
    SELECT a.id,
           ARRAY(SELECT DISTINCT s FROM unnest(
                   ARRAY[a.target_steam_id]::text[]
                   || COALESCE((SELECT ARRAY[p1.steam_id::text, p2.steam_id::text]
                                  FROM ranked_series rs
                                  JOIN players p1 ON p1.id = rs.player1_id
                                  JOIN players p2 ON p2.id = rs.player2_id
                                 WHERE rs.id = a.target_series_id), '{}'::text[])
                   || COALESCE((SELECT array_agg(p.steam_id::text)
                                  FROM team_series ts
                                  JOIN players p ON p.id IN (ts.t1a_id, ts.t1b_id, ts.t2a_id, ts.t2b_id)
                                 WHERE ts.id = a.target_series_id), '{}'::text[])
                   || COALESCE((SELECT ARRAY[p1.steam_id::text, p2.steam_id::text]
                                  FROM matches m
                                  JOIN players p1 ON p1.id = m.player1_id
                                  JOIN players p2 ON p2.id = m.player2_id
                                 WHERE m.id = a.target_match_id
                                    OR (a.action = 'record_exclude' AND a.target_steam_id IS NULL
                                        AND m.id::text = a.details->>'match_id')
                                 LIMIT 1), '{}'::text[])
                   || COALESCE((SELECT ARRAY[lo.steam_id::text, hi.steam_id::text]
                                  FROM pc_trades t
                                  JOIN players lo ON lo.id = t.pair_lo
                                  JOIN players hi ON hi.id = t.pair_hi
                                 WHERE a.action = 'pc_trade_reverse'
                                   AND t.id::text = a.target_steam_id), '{}'::text[])
                   || COALESCE((SELECT array_agg(DISTINCT p.steam_id::text)
                                  FROM chat_messages cm
                                  JOIN players p ON p.steam_id = cm.steam_id
                                 WHERE a.action = 'chat_delete'
                                   AND jsonb_typeof(a.details) = 'object'
                                   AND (cm.id::text = a.details->>'message_id'
                                        OR (jsonb_typeof(a.details->'message_ids') = 'array'
                                            AND cm.id::text IN (SELECT jsonb_array_elements_text(a.details->'message_ids'))))),
                               '{}'::text[])
                 ) s
                 WHERE s ~ '^[0-9]{17}$' ORDER BY s LIMIT 16) AS ids
      FROM admin_actions a
     WHERE a.affected_steam_ids = '{}'::text[]
       AND (a.target_steam_id IS NULL OR a.target_steam_id NOT LIKE 'deleted\_%')
       -- the words that name no player (modlog.NAMES_NONE; the census test
       -- holds this list equal to it): a change to the server or its content,
       -- a refusal, or a platform user's id that is not a Steam id
       AND a.action NOT IN ('alert_create', 'alert_revoke', 'ban_rate_blocked',
                            'chat_lockdown', 'chat_purge_channel', 'chat_purge_user',
                            'chat_spam_pattern', 'chat_unmute_bridge', 'item-artist', 'mail_broadcast',
                            'operator_key_issue', 'operator_key_revoke', 'pc_snapshot',
                            'read_gate_mode', 'team_glicko_rebuild')
  ) c
 WHERE aa.id = c.id AND cardinality(c.ids) > 0;

-- 3. The old rows' reasons, from the reason their details carry.
UPDATE admin_actions
   SET reason = left(details->>'reason', 256)
 WHERE reason IS NULL AND jsonb_typeof(details) = 'object'
   AND COALESCE(details->>'reason', '') <> '';

COMMIT;
