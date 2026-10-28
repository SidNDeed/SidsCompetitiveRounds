"""Mutation evidence for the 2v2 and 1v2 readmission server half (Stage 2
design V3): every planted defect turns its named test red, and an inert edit
at the same site keeps the same selection green.

Each mutant is a COPY of backend/api/match_hold.py and match_report_window.py
written under MATCH_HOLD_SCRATCH/<mutant id>/{mutant,control}/ with exact
anchor replacements (every anchor must occur exactly once in the file it
edits, or the runner refuses). The tracked files are only ever read. The
test modules put MATCH_HOLD_SRC first on sys.path and their module census
proves the copy is the module the routes run (#742, #838); the census must
stay green inside a mutant run, so a red census is a runner failure, not a
kill.

usage: python match-hold-mutation-runner.py --piece N2 [--piece N3 ...]
       python match-hold-mutation-runner.py --mutant M1.7 [--mutant ...]
MATCH_HOLD_SCRATCH must name an existing directory outside the worktree.
Exit 0 only when every mutant is red with a named selected test failing and
every control is green.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", ".."))
API = os.path.join(BACKEND, "api")
TESTS = os.path.join(BACKEND, "tests")
SQL = os.path.join(BACKEND, "sql")
MODULES = ("match_hold.py", "match_report_window.py")

HOLD_T = "test_match_hold_pg.py"
ADMIT_T = "test_match_hold_admission_gate_pg.py"
WIN_T = "test_match_report_window.py"
MIG_T = "test_match_hold_migration_pg.py"
M383 = "383_match_hold_stage2.sql"
M384 = "384_i18n_keys_stage2_hold.sql"
R384 = "rollback_384_i18n_keys_stage2_hold.sql"
SQL_ENV = {M383: "MATCH_HOLD_M383", M384: "MATCH_HOLD_M384",
           R384: "MATCH_HOLD_R384"}

# id: (piece, module file, [(anchor, mutant text)], [(anchor, control text)],
#      test file, -k selection of the tests that must fail)
MUTANTS = {
    'FIX2.M4.HELD_RECEIPT.TEAM': ('FIX2', 'match_report_window.py', [('    if held:\n        await _hold_window(db, window, room=room, game_id=game_id)\n', '    if held:\n        await _arm_window(db, window, room=room, game_id=game_id, at=now)\n')], [('    if held:\n        await _hold_window(db, window, room=room, game_id=game_id)\n', '    if held:\n        await _hold_window(db, (window), room=room, game_id=game_id)\n')], 'test_match_hold_reports_pg.py', 'test_fix2_m4_team_held_receipt_deadline'),
    'FIX2.M4.HELD_RECEIPT.OVT': ('FIX2', 'match_report_window.py', [('    if held:\n        await _hold_window(db, window, room=room, game_id=game_id)\n', '    if held:\n        await _arm_window(db, window, room=room, game_id=game_id, at=now)\n')], [('    if held:\n        await _hold_window(db, window, room=room, game_id=game_id)\n', '    if held:\n        await _hold_window(db, (window), room=room, game_id=game_id)\n')], 'test_match_hold_reports_pg.py', 'test_fix2_m4_ovt_held_receipt_deadline'),
    "FIX2.M2.ACTION": ('FIX2', 'match_hold.py', [('         "opener": str(opener) if opener else None})).scalar()\n    return got is not None\n', '         "opener": str(opener) if opener else None})).scalar()\n    return True\n')], [('         "opener": str(opener) if opener else None})).scalar()\n    return got is not None\n', '         "opener": str(opener) if opener else None})).scalar()\n    return (got is not None)\n')], 'test_match_hold_pg.py', 'test_nx0a_concurrent_first_use_of_one_request_id_acts_once'),
    "FIX1B.R1.SAVEPOINT": ('FIX1B', 'match_report_window.py', [('    async with db.begin_nested():\n        try:\n            await settle(db, chosen)\n', '    if True:\n        try:\n            await settle(db, chosen)\n')], [('    async with db.begin_nested():\n        try:\n            await settle(db, chosen)\n', '    async with db.begin_nested():\n        try:\n            await settle(db, (chosen))\n')], 'test_match_hold_reports_pg.py', 'test_merged_fix1b_r1_permanent_then_valid_held_reports'),
    "F1.L2.BASELINE": ("FIX1", M384,
        [('SELECT e.key_id, to_jsonb(k)\n', 'SELECT e.key_id, NULL::jsonb\n')],
        [('SELECT e.key_id, to_jsonb(k)\n', 'SELECT e.key_id, (to_jsonb(k))\n')],
        MIG_T, "l2_384_owned_metadata_round_trips"),
    "F1.L2.INVERSE": ("FIX1", R384,
        [("    IF EXISTS (\n        SELECT 1 FROM i18n_keys_384_ownership b\n        LEFT JOIN i18n_keys k USING (key_id)\n        WHERE b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')\n          AND (b.owned IS NULL\n", "    IF FALSE AND EXISTS (\n        SELECT 1 FROM i18n_keys_384_ownership b\n        LEFT JOIN i18n_keys k USING (key_id)\n        WHERE b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')\n          AND (b.owned IS NULL\n"), ('   AND b.active AND b.baseline IS NULL\n   AND to_jsonb(k) = b.owned;', '   AND b.active AND b.baseline IS NULL\n   AND TRUE;'), ('   AND b.active AND b.baseline IS NOT NULL\n   AND to_jsonb(k) = b.owned;', '   AND b.active AND b.baseline IS NOT NULL\n   AND TRUE;'), ("                    (to_jsonb(k) - 'retired_at' - 'updated_at') IS DISTINCT FROM\n                    (b.owned - 'retired_at' - 'updated_at')", '                    FALSE')],
        [("    IF EXISTS (\n        SELECT 1 FROM i18n_keys_384_ownership b\n        LEFT JOIN i18n_keys k USING (key_id)\n        WHERE b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')\n          AND (b.owned IS NULL\n", "     IF EXISTS (\n        SELECT 1 FROM i18n_keys_384_ownership b\n        LEFT JOIN i18n_keys k USING (key_id)\n        WHERE b.key_id IN ('fe3e2890029979eb', 'e247d0f66676e2fa', '990a134373f4fe9b', '21a77f99b9e86f48', 'df1814deb572b30b', '5ff81c1cbcb1bc7b', 'dff040f0708dc38d', '690eba24c1191a59', 'b933f3c706c40e83', '98dca83410faa64d', '66acd1c2d1011708', 'bd57f21b2e779ae1', '5be7e933e570652e')\n          AND (b.owned IS NULL\n"), ('   AND b.active AND b.baseline IS NULL\n   AND to_jsonb(k) = b.owned;', '    AND b.active AND b.baseline IS NULL\n   AND to_jsonb(k) = b.owned;'), ('   AND b.active AND b.baseline IS NOT NULL\n   AND to_jsonb(k) = b.owned;', '    AND b.active AND b.baseline IS NOT NULL\n   AND to_jsonb(k) = b.owned;'), ("                    (to_jsonb(k) - 'retired_at' - 'updated_at') IS DISTINCT FROM\n                    (b.owned - 'retired_at' - 'updated_at')", "                     (to_jsonb(k) - 'retired_at' - 'updated_at') IS DISTINCT FROM\n                    (b.owned - 'retired_at' - 'updated_at')")],
        MIG_T, "l2_384_owned_metadata_round_trips"),
    'M5.10': ('FIX1', 'match_report_window.py', [('    held = held or (hold is not None and closure is None)\n', '    held = False\n')], [('    held = held or (hold is not None and closure is None)\n', '    held = held or ((hold is not None) and closure is None)\n')], 'test_match_hold_reports_pg.py', 'test_t5_7_held_game_over_settles_at_entry_and_is_superseded_at_lapse'),
    'MERGED.FIX1.H2.CAUSAL': ('FIX1', 'match_report_window.py', [('    return closure is not None and closure[1] == "entered"\n', '    return bool((await db.execute(text(\n        "SELECT 1 FROM match_seat_holds WHERE room_name = CAST(:room AS varchar)"\n        " AND game_id = CAST(:g AS uuid) AND closed_reason = \'entered\' LIMIT 1"),\n        {"room": hold["room_name"], "g": str(hold["game_id"])})).scalar())\n')], [('    return closure is not None and closure[1] == "entered"\n', '    return (closure is not None) and closure[1] == "entered"\n')], 'test_match_hold_reports_pg.py', 'merged_fix1_h2_causal_lapse_and_delayed_receipt'),
    'MERGED.FIX1.H2.EXPIRY': ('FIX1', 'match_report_window.py', [('    if not held and not _window_unarmed(window) and window["settle_after"] <= now:\n', '    if window["opened_at"] + timedelta(seconds=WINDOW_S) <= now:\n')], [('    if not held and not _window_unarmed(window) and window["settle_after"] <= now:\n', '    if (not held) and not _window_unarmed(window) and window["settle_after"] <= now:\n')], 'test_match_hold_reports_pg.py', 'merged_fix1_h2_held_receipts_outlive_first_receipt'),
    'MERGED.FIX1.H1.RECEIPT': ('FIX1', 'match_report_window.py', [('        if exc.receipt:\n            raise\n', '        if False:\n            raise\n')], [('        if exc.receipt:\n            raise\n', '        if (exc.receipt):\n            raise\n')], 'test_match_hold_reports_pg.py', 'test_fix1_h1_racing_duplicate_does_not_spend_next_reporter'),
    # Fix 1 - every stage 2 route requires a positively verified session
    "F1.H1": ("FIX1", "match_hold.py",
              [('    if not _session_was_verified(request):\n'
                '        raise HTTPException(status_code=401, detail="session_required")',
                '    if False:\n'
                '        raise HTTPException(status_code=401, detail="session_required")')],
              [('    if not _session_was_verified(request):\n'
                '        raise HTTPException(status_code=401, detail="session_required")',
                '    if not (_session_was_verified(request)):\n'
                '        raise HTTPException(status_code=401, detail="session_required")')],
              HOLD_T, "h1_real_helper_soft_fail_paths"),
    "F1.H2.OMIT": ("FIX1", "match_hold.py",
                   [('        "verifier": row["verifier"] if state in ("claimed", "bound") else None,\n',
                     '')],
                   [('        "verifier": row["verifier"] if state in ("claimed", "bound") else None,\n',
                     '        "verifier": (row["verifier"] if state in ("claimed", "bound") else None),\n')],
                   HOLD_T, "h2_verifier_lifecycle"),
    "F1.H2.STALE": ("FIX1", "match_hold.py",
                    [('        dict(hold, claimed_at=hold["claimed_at"] or now, verifier=verifier), now)',
                      '        dict(hold, claimed_at=hold["claimed_at"] or now), now)')],
                    [('        dict(hold, claimed_at=hold["claimed_at"] or now, verifier=verifier), now)',
                      '        dict(hold, claimed_at=hold["claimed_at"] or now, verifier=(verifier)), now)')],
                    HOLD_T, "h2_verifier_lifecycle"),
    "F1.H3.GATE": ("FIX1", "match_hold.py",
                   [('        if not admitted:\n'
                     '            # The player gate may have waited behind a winning formation.',
                     '        if False:\n'
                     '            # The player gate may have waited behind a winning formation.')],
                   [('        if not admitted:\n'
                     '            # The player gate may have waited behind a winning formation.',
                     '        if not (admitted):\n'
                     '            # The player gate may have waited behind a winning formation.')],
                   ADMIT_T, "h3_hold_open_and_claim_reject_another_live_commitment"),
    "F1.H3.RECHECK": ("FIX1", "match_hold.py",
                      [('    if not admitted:\n'
                        '        # Roll back the losing claim before its required audit row.',
                        '    if False:\n'
                        '        # Roll back the losing claim before its required audit row.')],
                      [('    if not admitted:\n'
                        '        # Roll back the losing claim before its required audit row.',
                        '    if not (admitted):\n'
                        '        # Roll back the losing claim before its required audit row.')],
                      ADMIT_T, "h3_hold_open_and_claim_reject_another_live_commitment"),
    "F1.M3": ("FIX1", "match_hold.py",
              [('        await _close_due_room_hold(db, room, now)\n',
                '        pass\n'),
               ('        "   AND held_until > CAST(:now AS timestamptz)"\n'
                '        "   AND (bound_at IS NULL OR entered_at IS NOT NULL"\n'
                '        "        OR bound_at + make_interval(secs => CAST(:eb AS integer))"\n'
                '        "             > CAST(:now AS timestamptz))"\n',
                '')],
              [('        await _close_due_room_hold(db, room, now)\n',
                '        await _close_due_room_hold(db, (room), now)\n'),
               ('        "   AND held_until > CAST(:now AS timestamptz)"\n',
                '        "   AND  held_until > CAST(:now AS timestamptz)"\n')],
              HOLD_T, "m3_due_prior_game_closes_before_later_open or "
                      "m3_bind_actor_conflict_uses_live_deadlines"),
    "F1.M2.CHECKOUT": ("FIX1", "match_hold.py",
                       [('        self.timer = asyncio.timeout_at(self.state["deadline"])',
                         '        self.timer = asyncio.timeout(None)')],
                       [('        self.timer = asyncio.timeout_at(self.state["deadline"])',
                         '        self.timer = asyncio.timeout_at((self.state["deadline"]))')],
                       HOLD_T, "m2_deadline_covers_checkout_before_any_route_work"),
    "F1.M2.LOCK": ("FIX1", "match_hold.py",
                   [('            await _install_database_timeouts(self.db)',
                     '            await self.db.execute(text("SELECT 1"))')],
                   [('            await _install_database_timeouts(self.db)',
                     '            await _install_database_timeouts((self.db))')],
                   WIN_T, "t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c"),
    "F1.H4": ("FIX1", "match_report_window.py",
              [('    if not held and not _window_unarmed(window) and window["settle_after"] <= now:\n'
                '        await _settle_locked(\n'
                '            db, window, room=room, game_id=game_id, now=now, settle=settle)\n'
                '        return {"status": "duplicate"}\n',
                '')],
              [('    if not held and not _window_unarmed(window) and window["settle_after"] <= now:\n',
                '    if not held and not _window_unarmed(window) and (window["settle_after"] <= now):\n')],
              WIN_T, "t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c"),
    "F1.H6": ('FIX1', 'match_report_window.py', [('            if not await _settle_and_mark(db, room, game_id, entry, now, settle):\n', '            if not await _settle_and_mark(db, room, game_id, dict(entry, payload=payload), now, settle):\n')], [('            if not await _settle_and_mark(db, room, game_id, entry, now, settle):\n', '            if not await _settle_and_mark(db, room, game_id, (entry), now, settle):\n')], 'test_match_report_window.py', 't5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c'),
    "F1.M5": ("FIX1", "match_report_window.py",
              [('        "   AND m.beat_at <= CAST(:now AS timestamptz)"\n', '')],
              [('        "   AND m.beat_at <= CAST(:now AS timestamptz)"\n',
                '        "   AND  m.beat_at <= CAST(:now AS timestamptz)"\n')],
              WIN_T, "t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c"),
    "F1.M4": ("FIX1", "match_report_window.py",
              [('    while chosen is not None and chosen["cls"] == CLASS_C:\n',
                '    while False and chosen is not None and chosen["cls"] == CLASS_C:\n')],
              [('    while chosen is not None and chosen["cls"] == CLASS_C:\n',
                '    while (chosen is not None and chosen["cls"] == CLASS_C):\n')],
              WIN_T, "t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c"),
    "F1.H5": ("FIX1", "match_report_window.py",
              [('    return window["settled_at"] is not None or '
                'window["superseded_at"] is not None\n',
                '    return window["settled_at"] is not None\n')],
              [('    return window["settled_at"] is not None or '
                'window["superseded_at"] is not None\n',
                '    return (window["settled_at"] is not None or '
                'window["superseded_at"] is not None)\n')],
              WIN_T, "t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c"),
    "F1.M8.LITERAL.DEFAULT": ("FIX1", M383,
        [('/* M3 normalize def */\n                   (SELECT coalesce(string_agg(\n                       CASE WHEN token[1] ~ \'^[[:space:]]$\' THEN \'\'\n                            ELSE token[1] END, \'\' ORDER BY ord), \'\')\n                      FROM regexp_matches(coalesce(pg_get_expr(d.adbin, d.adrelid, false), \'\'),\n                           $norm$([eE]\'(?:[^\'\\\\]|\\\\.|\'\')*\'|\'(?:[^\']|\'\')*\'|"(?:[^"]|"")*"|.)$norm$, \'gs\')\n                           WITH ORDINALITY AS part(token, ord))',
          "/* M3 normalize def */\n                   regexp_replace(coalesce(pg_get_expr(d.adbin, d.adrelid, false), ''),\n                                  '[[:space:]]+', '', 'g')")],
        [('/* M3 normalize def */\n                   (SELECT coalesce(string_agg(\n                       CASE WHEN token[1] ~ \'^[[:space:]]$\' THEN \'\'\n                            ELSE token[1] END, \'\' ORDER BY ord), \'\')\n                      FROM regexp_matches(coalesce(pg_get_expr(d.adbin, d.adrelid, false), \'\'),\n                           $norm$([eE]\'(?:[^\'\\\\]|\\\\.|\'\')*\'|\'(?:[^\']|\'\')*\'|"(?:[^"]|"")*"|.)$norm$, \'gs\')\n                           WITH ORDINALITY AS part(token, ord))',
          '/* M3 normalize def */\n                   (SELECT coalesce(string_agg(\n                       CASE  WHEN token[1] ~ \'^[[:space:]]$\' THEN \'\'\n                            ELSE token[1] END, \'\' ORDER BY ord), \'\')\n                      FROM regexp_matches(coalesce(pg_get_expr(d.adbin, d.adrelid, false), \'\'),\n                           $norm$([eE]\'(?:[^\'\\\\]|\\\\.|\'\')*\'|\'(?:[^\']|\'\')*\'|"(?:[^"]|"")*"|.)$norm$, \'gs\')\n                           WITH ORDINALITY AS part(token, ord))')],
        MIG_T, "normalizers_preserve_literal_bytes"),
    "F1.M8.LITERAL.CONSTRAINT": ("FIX1", M383,
        [('/* M3 normalize definition */\n                   (SELECT coalesce(string_agg(\n                       CASE WHEN token[1] ~ \'^[[:space:]]$\' THEN \'\'\n                            ELSE token[1] END, \'\' ORDER BY ord), \'\')\n                      FROM regexp_matches(pg_get_constraintdef(c.oid, false),\n                           $norm$([eE]\'(?:[^\'\\\\]|\\\\.|\'\')*\'|\'(?:[^\']|\'\')*\'|"(?:[^"]|"")*"|.)$norm$, \'gs\')\n                           WITH ORDINALITY AS part(token, ord))',
          "/* M3 normalize definition */\n                   regexp_replace(pg_get_constraintdef(c.oid, false),\n                                  '[[:space:]]+', '', 'g')")],
        [('/* M3 normalize definition */\n                   (SELECT coalesce(string_agg(\n                       CASE WHEN token[1] ~ \'^[[:space:]]$\' THEN \'\'\n                            ELSE token[1] END, \'\' ORDER BY ord), \'\')\n                      FROM regexp_matches(pg_get_constraintdef(c.oid, false),\n                           $norm$([eE]\'(?:[^\'\\\\]|\\\\.|\'\')*\'|\'(?:[^\']|\'\')*\'|"(?:[^"]|"")*"|.)$norm$, \'gs\')\n                           WITH ORDINALITY AS part(token, ord))',
          '/* M3 normalize definition */\n                   (SELECT coalesce(string_agg(\n                       CASE  WHEN token[1] ~ \'^[[:space:]]$\' THEN \'\'\n                            ELSE token[1] END, \'\' ORDER BY ord), \'\')\n                      FROM regexp_matches(pg_get_constraintdef(c.oid, false),\n                           $norm$([eE]\'(?:[^\'\\\\]|\\\\.|\'\')*\'|\'(?:[^\']|\'\')*\'|"(?:[^"]|"")*"|.)$norm$, \'gs\')\n                           WITH ORDINALITY AS part(token, ord))')],
        MIG_T, "normalizers_preserve_literal_bytes"),
    "F1.M8.LITERAL.INDEX": ("FIX1", M383,
        [('/* M3 normalize predicate */\n                   (SELECT coalesce(string_agg(\n                       CASE WHEN token[1] ~ \'^[[:space:]]$\' THEN \'\'\n                            ELSE token[1] END, \'\' ORDER BY ord), \'\')\n                      FROM regexp_matches(coalesce(pg_get_expr(i.indpred, i.indrelid, false), \'\'),\n                           $norm$([eE]\'(?:[^\'\\\\]|\\\\.|\'\')*\'|\'(?:[^\']|\'\')*\'|"(?:[^"]|"")*"|.)$norm$, \'gs\')\n                           WITH ORDINALITY AS part(token, ord))',
          "/* M3 normalize predicate */\n                   regexp_replace(coalesce(pg_get_expr(i.indpred, i.indrelid, false), ''),\n                                  '[[:space:]]+', '', 'g')")],
        [('/* M3 normalize predicate */\n                   (SELECT coalesce(string_agg(\n                       CASE WHEN token[1] ~ \'^[[:space:]]$\' THEN \'\'\n                            ELSE token[1] END, \'\' ORDER BY ord), \'\')\n                      FROM regexp_matches(coalesce(pg_get_expr(i.indpred, i.indrelid, false), \'\'),\n                           $norm$([eE]\'(?:[^\'\\\\]|\\\\.|\'\')*\'|\'(?:[^\']|\'\')*\'|"(?:[^"]|"")*"|.)$norm$, \'gs\')\n                           WITH ORDINALITY AS part(token, ord))',
          '/* M3 normalize predicate */\n                   (SELECT coalesce(string_agg(\n                       CASE  WHEN token[1] ~ \'^[[:space:]]$\' THEN \'\'\n                            ELSE token[1] END, \'\' ORDER BY ord), \'\')\n                      FROM regexp_matches(coalesce(pg_get_expr(i.indpred, i.indrelid, false), \'\'),\n                           $norm$([eE]\'(?:[^\'\\\\]|\\\\.|\'\')*\'|\'(?:[^\']|\'\')*\'|"(?:[^"]|"")*"|.)$norm$, \'gs\')\n                           WITH ORDINALITY AS part(token, ord))')],
        MIG_T, "normalizers_preserve_literal_bytes"),
    "F1.M8.COL": ("FIX1", M383,
                  [("            OR a.typ IS DISTINCT FROM e.typ\n",
                    "            OR FALSE\n")],
                  [("            OR a.typ IS DISTINCT FROM e.typ\n",
                    "            OR (a.typ IS DISTINCT FROM e.typ)\n")],
                  MIG_T, "proof_block_raises_on_a_gap"),
    "F1.M8.DEFAULT": ("FIX1", M383,
                      [("            OR a.def IS DISTINCT FROM e.def\n",
                        "            OR FALSE\n")],
                      [("            OR a.def IS DISTINCT FROM e.def\n",
                        "            OR (a.def IS DISTINCT FROM e.def)\n")],
                      MIG_T, "proof_block_raises_on_a_gap"),
    "F1.M8.CONSTRAINT": ("FIX1", M383,
                         [("            OR a.definition IS DISTINCT FROM e.definition\n",
                           "            OR FALSE\n")],
                         [("            OR a.definition IS DISTINCT FROM e.definition\n",
                           "            OR (a.definition IS DISTINCT FROM e.definition)\n")],
                         MIG_T, "proof_block_raises_on_a_gap"),
    "F1.M8.INDEX": ("FIX1", M383,
                    [("            OR a.predicate IS DISTINCT FROM e.predicate\n",
                      "            OR FALSE\n")],
                    [("            OR a.predicate IS DISTINCT FROM e.predicate\n",
                      "            OR (a.predicate IS DISTINCT FROM e.predicate)\n")],
                    MIG_T, "proof_block_raises_on_a_gap"),
    "F1.M1": ("FIX1", "match_hold.py",
              [('            or member_seats.get(held) != (req.slot, req.team)\n', '')],
              [('            or member_seats.get(held) != (req.slot, req.team)\n',
                '            or (member_seats.get(held) != (req.slot, req.team))\n')],
              HOLD_T, "m1_hold_open_requires_exact_roster_slot_and_team"),
    "F1.M6.TUPLE": ("FIX1", "match_hold.py",
                    # NX0a re-anchor: the tuple check now lives in _open_replay;
                    # the mutant still answers a reused id without its tuple check.
                    [('    if not _open_attempt_matches(known, req, room, held, opener):\n'
                      '        await db.rollback()\n'
                      '        return _refused("request_mismatch")',
                      '    if False:\n'
                      '        await db.rollback()\n'
                      '        return _refused("request_mismatch")')],
                    [('    if not _open_attempt_matches(known, req, room, held, opener):\n'
                      '        await db.rollback()\n'
                      '        return _refused("request_mismatch")',
                      '    if not (_open_attempt_matches(known, req, room, held, opener)):\n'
                      '        await db.rollback()\n'
                      '        return _refused("request_mismatch")')],
                    HOLD_T, "m6_open_request_id_replays_only_its_original_tuple"),
    "F1.M6.SIG": ("FIX1", "match_hold.py",
                  # NX0a re-anchor: the write now reports whether it inserted.
                  [('        if await _write_open_attempt(\n'
                    '                db, req, room, None, opener, now, "refused", "bad_signature", None):\n'
                    '            await db.commit()',
                    '        if False:\n'
                    '            await db.commit()')],
                  [('        if await _write_open_attempt(\n'
                    '                db, req, room, None, opener, now, "refused", "bad_signature", None):\n'
                    '            await db.commit()',
                    '        if await _write_open_attempt(\n'
                    '                db, req, room, None, opener, now, "refused", "bad_signature", None):\n'
                    '            await  db.commit()')],
                  HOLD_T, "m6_bad_signature_records_refusal_before_403"),
    # NX0a - the request-id ledger insert is the serialization point: the
    # mutant moves the insert after the action (a pre-read, then a
    # conflict-dropping insert at the outcome), the form fix 1 shipped.
    "NX0a": ("NX0a", "match_hold.py",
             [('    if not await _claim_open_ledger(db, req, room, held, opener):\n'
               '        return await _open_replay(db, req, room, held, opener)\n',
               '    if await _open_attempt_row(db, req.request_id) is not None:\n'
               '        return await _open_replay(db, req, room, held, opener)\n'),
              ('        "UPDATE match_hold_open_attempts SET at = CAST(:now AS timestamptz),"\n'
               '        "       outcome = CAST(:outcome AS varchar), reason = CAST(:reason AS varchar),"\n'
               '        "       hold_id = CAST(:hid AS uuid)"\n'
               '        " WHERE request_id = CAST(:rid AS varchar)"\n'
               '        "   AND outcome = \'refused\' AND reason = \'pending\'"),\n'
               '        {"rid": req.request_id, "now": now,',
               '        "INSERT INTO match_hold_open_attempts (request_id, room_name, game_id,"\n'
               '        "        held_player_id, opener_player_id, at, outcome, reason, hold_id)"\n'
               '        " SELECT CAST(:rid AS varchar), CAST(:room AS varchar), CAST(:g AS uuid),"\n'
               '        "        (SELECT id FROM players WHERE steam_id = CAST(:hs AS varchar)),"\n'
               '        "        (SELECT id FROM players WHERE steam_id = CAST(:os AS varchar)),"\n'
               '        "        CAST(:now AS timestamptz), CAST(:outcome AS varchar),"\n'
               '        "        CAST(:reason AS varchar), CAST(:hid AS uuid)"\n'
               '        " ON CONFLICT (request_id) DO NOTHING"),\n'
               '        {"rid": req.request_id, "now": now, "room": req.room.strip(),'
               ' "g": str(req.game_id), "hs": req.held_steam_id, "os": req.opener_steam_id,')],
             [('    if not await _claim_open_ledger(db, req, room, held, opener):\n'
               '        return await _open_replay(db, req, room, held, opener)\n',
               '    if not (await _claim_open_ledger(db, req, room, held, opener)):\n'
               '        return await _open_replay(db, req, room, held, opener)\n')],
             HOLD_T, "nx0a_concurrent_first_use"),
    "F1.M7": ("FIX1", "match_hold.py",
              [('    if (reason is None and mode == "team"\n'
                '            and (req.t1_points is None or req.t2_points is None)):\n'
                '        reason = "missing_points"\n', '')],
              [('    if (reason is None and mode == "team"\n'
                '            and (req.t1_points is None or req.t2_points is None)):\n'
                '        reason = "missing_points"\n',
                '    if (reason is None and mode == "team"\n'
                '            and ((req.t1_points is None) or req.t2_points is None)):\n'
                '        reason = "missing_points"\n')],
              HOLD_T, "m7_team_open_requires_both_point_snapshots"),
    "F1.L1": ("FIX1", "match_hold.py",
              [('        await _attempt(db, hold_id, "bind", now, "ok")\n'
                '        await db.commit()\n'
                '        out = _state_payload(hold, now)',
                '        await db.commit()\n'
                '        out = _state_payload(hold, now)')],
              [('        await _attempt(db, hold_id, "bind", now, "ok")\n'
                '        await db.commit()\n'
                '        out = _state_payload(hold, now)',
                '        await _attempt(db,  hold_id, "bind", now, "ok")\n'
                '        await db.commit()\n'
                '        out = _state_payload(hold, now)')],
              HOLD_T, "t3_7_bind_identity_and_entry"),
    # N2 - the game id chain and the hold latch
    "M1.7": ("N2", "match_hold.py",
             [('"   AND prev_game = CAST(:prev AS uuid)"), key)',
               '"   AND id = CAST(:prev AS uuid)"), key)')],
             [('"   AND prev_game = CAST(:prev AS uuid)"), key)',
               '"   AND  prev_game = CAST(:prev AS uuid)"), key)')],
             HOLD_T, "t1_4_game_id_chain"),
    "M1.8": ("N2", "match_hold.py",
             [("    if found is not None:\n        await db.commit()",
               "    if False:\n        await db.commit()")],
             [("    if found is not None:\n        await db.commit()",
               "    if (found is not None):\n        await db.commit()")],
             HOLD_T, "t1_4_game_id_chain"),
    "M1.L1": ("N2", "match_hold.py",
              [('hold_v2 = (SELECT count(*) = {n} FROM',
                'hold_v2 = (SELECT count(*) >= 1 FROM')],
              [('hold_v2 = (SELECT count(*) = {n} FROM',
                'hold_v2 = (SELECT count(*)  = {n} FROM')],
              HOLD_T, "hold_latch_helper"),
    "M1.L2": ("N2", "match_hold.py",
              [('        f" WHERE s.id = CAST(:sid AS uuid)"\n'
                '        f"   AND s.hold_room IS DISTINCT FROM CAST(:room AS varchar)")',
                '        f" WHERE s.id = CAST(:sid AS uuid)")')],
              [('        f" WHERE s.id = CAST(:sid AS uuid)"\n'
                '        f"   AND s.hold_room IS DISTINCT FROM CAST(:room AS varchar)")',
                '        f" WHERE s.id = CAST(:sid AS uuid)"\n'
                '        f"   AND  s.hold_room IS DISTINCT FROM CAST(:room AS varchar)")')],
              HOLD_T, "hold_latch_helper"),
    # N3 (the constraint half of S2): one hold per seat per game, in the file
    "M2.1": ("N3", M383,
             [("  CONSTRAINT uq_msh_room_game_player UNIQUE (room_name, game_id, player_id),\n",
               ""),
              ("            ('match_seat_holds', 'uq_msh_room_game_player', 'u',\n"
               "             ARRAY['room_name', 'game_id', 'player_id'], NULL, NULL,\n"
               "             $c$UNIQUE(room_name,game_id,player_id)$c$, true),\n", "")],
             [("  CONSTRAINT uq_msh_room_game_player UNIQUE (room_name, game_id, player_id),\n",
               "  CONSTRAINT  uq_msh_room_game_player UNIQUE (room_name, game_id, player_id),\n")],
             MIG_T, "first_apply_rerun"),
    # N3 - S2 server: the DB clock, the anchor, closure once, attempt rows
    "M2.2": ("N3", "match_hold.py",
             [('text("SELECT clock_timestamp()")', 'text("SELECT now()")')],
             [('text("SELECT clock_timestamp()")', 'text("SELECT  clock_timestamp()")')],
             HOLD_T, "t2_1_open_anchor"),
    "M2.3": ("N3", "match_hold.py",
             [("   SET closed_at = due.at, closed_reason = due.why\n",
               "   SET closed_at = due.at, closed_reason = due.why,"
               " held_until = CAST(:now AS timestamptz)\n")],
             [("   SET closed_at = due.at, closed_reason = due.why\n",
               "   SET closed_at = due.at,  closed_reason = due.why\n")],
             HOLD_T, "t2_2_closure"),
    "M2.4": ("N3", "match_hold.py",
             [('"anchor": pres["present_at"], "now": now,', '"anchor": now, "now": now,')],
             [('"anchor": pres["present_at"], "now": now,',
               '"anchor": pres["present_at"],  "now": now,')],
             HOLD_T, "t2_1_open_anchor"),
    "M2.5": ("N3", "match_hold.py",
             [("import uuid\n", "import uuid\nfrom datetime import datetime, timezone\n"),
              ('return (await db.execute(text("SELECT clock_timestamp()"))).scalar()',
               "return datetime.now(timezone.utc)")],
             [('return (await db.execute(text("SELECT clock_timestamp()"))).scalar()',
               'return ((await db.execute(text("SELECT clock_timestamp()"))).scalar())')],
             HOLD_T, "t2_1_open_anchor"),
    "M2.6": ("N3", "match_hold.py",
             [('    if latest != game["id"]:\n', "    if False:\n")],
             [('    if latest != game["id"]:\n', '    if (latest != game["id"]):\n')],
             HOLD_T, "t2_1_open_anchor or t2_8_open_attempt"),
    "M2.7": ("N3", "match_hold.py",
             [('" WHERE id = CAST(:hid AS uuid) AND closed_at IS NULL"),\n'
               '            {"at": closure[0]',
               '" WHERE FALSE AND id = CAST(:hid AS uuid) AND closed_at IS NULL"),\n'
               '            {"at": closure[0]')],
             [('" WHERE id = CAST(:hid AS uuid) AND closed_at IS NULL"),\n'
               '            {"at": closure[0]',
               '" WHERE  id = CAST(:hid AS uuid) AND closed_at IS NULL"),\n'
               '            {"at": closure[0]')],
             HOLD_T, "t2_2_closure"),
    "M2.14": ("N3", "match_hold.py",
              # NX0a re-anchor: the refusal now rewrites the owned ledger row.
              [('        await _finish_open_attempt(db, req, now, "refused", reason, None)\n',
                "        pass\n")],
              [('        await _finish_open_attempt(db, req, now, "refused", reason, None)\n',
                '        await _finish_open_attempt(db, req, now, "refused", reason,  None)\n')],
              HOLD_T, "t2_8_open_attempt"),
    # N4 - S3 server: the claim predicates, the rotation, the bind corroboration
    "M3.1": ("N4", "match_hold.py",
             [('    if not _hold_live(hold, now):\n'
               '        return await _refuse_attempt(db, hold_id, "claim", now, "hold_lapsed")',
               '    if False:\n'
               '        return await _refuse_attempt(db, hold_id, "claim", now, "hold_lapsed")')],
             [('    if not _hold_live(hold, now):\n'
               '        return await _refuse_attempt(db, hold_id, "claim", now, "hold_lapsed")',
               '    if (not _hold_live(hold, now)):\n'
               '        return await _refuse_attempt(db, hold_id, "claim", now, "hold_lapsed")')],
             HOLD_T, "t3_1_claim"),
    "M3.2": ("N4", "match_hold.py",
             [('        "       verifier = CAST(:v AS varchar)"\n',
               '        "       verifier = COALESCE(verifier, CAST(:v AS varchar))"\n')],
             [('        "       verifier = CAST(:v AS varchar)"\n',
               '        "       verifier =  CAST(:v AS varchar)"\n')],
             HOLD_T, "t3_1_claim"),
    "M3.3": ("N4", "match_hold.py",
             [('    admitted, now = await _lease_admission_gate(\n            db, [pid], hold["mode"], hold["series_id"],\n            allowed_hold_ids=(hold_id,), hold_entry_bound_seconds=ENTRY_BOUND_S,\n            strict_team_ovt_queue=True)', '    admitted, now = await _lease_admission_gate(\n            db, [pid], hold["mode"], hold["series_id"],\n            allowed_hold_ids=(hold_id,), hold_entry_bound_seconds=ENTRY_BOUND_S,\n            strict_team_ovt_queue=False)')],
             [('    return bool((await db.execute(text(\n'
               '        "SELECT 1 FROM team_queue WHERE player_id = CAST(:pid AS uuid)"',
               '    return (bool((await db.execute(text(\n'
               '        "SELECT 1 FROM team_queue WHERE player_id = CAST(:pid AS uuid)"'),
              ('        {"pid": str(pid), "sid": str(series_id)})).first())\n',
               '        {"pid": str(pid), "sid": str(series_id)})).first()))\n')],
             HOLD_T, "t3_1_claim"),
    "M3.18": ("N4", "match_hold.py",
              [('    if not await _corroborated(db, hold, req.actor, now):\n'
                '        return await _refuse_attempt(db, hold_id, "bind", now, "uncorroborated")',
                '    if False:\n'
                '        return await _refuse_attempt(db, hold_id, "bind", now, "uncorroborated")')],
              [('    if not await _corroborated(db, hold, req.actor, now):\n'
                '        return await _refuse_attempt(db, hold_id, "bind", now, "uncorroborated")',
                '    if not (await _corroborated(db, hold, req.actor, now)):\n'
                '        return await _refuse_attempt(db, hold_id, "bind", now, "uncorroborated")')],
              HOLD_T, "t3_7_bind"),
    # N5 - S5 server rules: the window and the class order
    "M5.4": ("N5", "match_report_window.py",
             [("        lo = start if start > v else v\n", "        lo = start\n")],
             [("        lo = start if start > v else v\n",
               "        lo = start if (start > v) else v\n")],
             WIN_T, "t5_3_overlap"),
    "M5.5": ("N5", "match_report_window.py",
             [("from datetime import datetime, timedelta\n",
               "from datetime import datetime, timedelta, timezone\n"),
              ("    return any(anchor_fresh(_get(row, col), holds, now=now, window=window)",
               "    return any(anchor_fresh(_get(row, col), holds,"
               " now=datetime.now(timezone.utc), window=window)")],
             [("    return any(anchor_fresh(_get(row, col), holds, now=now, window=window)",
               "    return any(anchor_fresh(_get(row, col), holds, now=(now), window=window)")],
             WIN_T, "t5_3_application_skew"),
    "M5.6": ("N5", "match_report_window.py",
             [('        key = (_CLASS_RANK[e["cls"]], steam_order(e["reporter_steam"]))\n',
               "        key = (0, 0)\n")],
             [('        key = (_CLASS_RANK[e["cls"]], steam_order(e["reporter_steam"]))\n',
               '        key = (_CLASS_RANK[e["cls"]], steam_order(e["reporter_steam"]),)\n')],
             WIN_T, "t5_4_matrix"),
    "M5.7": ("N5", "match_report_window.py",
             [("    for e in entries:\n",
               "    for e in entries:\n        if e[\"cls\"] == CLASS_R:\n            continue\n")],
             [("    for e in entries:\n", "    for e in list(entries):\n")],
             WIN_T, "t5_4_matrix"),
    # N6 - S6 attempt rows commit with their action, never ahead of it
    "M6.1": ("N6", "match_hold.py",
             [('    await _lease_acquire(db, pid, hold["mode"], hold["series_id"],\n'
               '                         LEASE_TTL_ASSEMBLY, _gate_held=True)\n',
                '    await _attempt(db, hold_id, "claim", now, "ok")\n'
                '    await db.commit()\n'
                '    await _lease_acquire(db, pid, hold["mode"], hold["series_id"],\n'
                '                         LEASE_TTL_ASSEMBLY, _gate_held=True)\n')],
             [('    await _lease_acquire(db, pid, hold["mode"], hold["series_id"],\n'
               '                         LEASE_TTL_ASSEMBLY, _gate_held=True)\n',
               '    await _lease_acquire(db,  pid, hold["mode"], hold["series_id"],\n'
               '                         LEASE_TTL_ASSEMBLY, _gate_held=True)\n')],
             HOLD_T, "t6_1"),
}


MUTANTS.update({'MERGED.FIX1.H4.BEAT': ('FIX1',
                         'match_hold.py',
                         [('async def _guard_identities(db, steam_ids):\n',
                           'async def _unguarded_identities(db, steam_ids):\n'
                           '    keys = sorted({str(s) for s in steam_ids if s is not None})\n'
                           '    rows = (await db.execute(text(\n'
                           '        "SELECT id, steam_id FROM players"\n'
                           '        " WHERE steam_id = ANY(CAST(:steams AS varchar[])) AND '
                           'deleted_at IS NULL"),\n'
                           '        {"steams": keys})).mappings().all()\n'
                           '    return {r["steam_id"]: r["id"] for r in rows}\n'
                           '\n'
                           '\n'
                           'async def _unguarded_hold_identities(db, hold_id, steam_id=None):\n'
                           '    return await _hold_row(db, hold_id), (await _player_id(db, '
                           'steam_id) if steam_id else None)\n'
                           '\n'
                           '\n'
                           'async def _guard_identities(db, steam_ids):\n'),
                          ('    live = await _guard_identities(db, [req.steam_id, *(s.u_id for s '
                           'in req.seen)])\n',
                           '    live = await _unguarded_identities(db, [req.steam_id, *(s.u_id for '
                           's in req.seen)])\n')],
                         [('    live = await _guard_identities(db, [req.steam_id, *(s.u_id for s '
                           'in req.seen)])\n',
                           '    live = await _guard_identities(db,  [req.steam_id, *(s.u_id for s '
                           'in req.seen)])\n')],
                         'test_match_hold_deletion_pg.py',
                         'fix1_h4_beat_deletion_orders_and_survivors'),
 'MERGED.FIX1.H4.OPEN_FINAL': ('FIX1',
                               'match_hold.py',
                               [('    case the insert waited for the recording transaction and '
                                 'changed nothing."""\n'
                                 '    await _guard_open_identities(db, req, held, opener)\n',
                                 '    case the insert waited for the recording transaction and '
                                 'changed nothing."""\n'
                                 '    pass\n')],
                               [('    case the insert waited for the recording transaction and '
                                 'changed nothing."""\n'
                                 '    await _guard_open_identities(db, req, held, opener)\n',
                                 '    case the insert waited for the recording transaction and '
                                 'changed nothing."""\n'
                                 '    await _guard_open_identities(db,  req, held, opener)\n')],
                               'test_match_hold_deletion_pg.py',
                               'fix1_h4_each_hold_writer_guards_before_downstream_lock or '
                               'fix1_h4_audit_revalidates_deleted_identity'),
 'MERGED.FIX1.H4.OPEN_CLAIM': ('FIX1',
                               'match_hold.py',
                               [('    True when this transaction owns the request id."""\n'
                                 '    await _guard_open_identities(db, req, held, opener)\n',
                                 '    True when this transaction owns the request id."""\n'
                                 '    pass\n')],
                               [('    True when this transaction owns the request id."""\n'
                                 '    await _guard_open_identities(db, req, held, opener)\n',
                                 '    True when this transaction owns the request id."""\n'
                                 '    await _guard_open_identities(db,  req, held, opener)\n')],
                               'test_match_hold_deletion_pg.py',
                               'fix1_h4_each_hold_writer_guards_before_downstream_lock or '
                               'fix1_h4_audit_revalidates_deleted_identity'),
 'MERGED.FIX1.H4.ATTEMPT': ('FIX1',
                            'match_hold.py',
                            [('    await _guard_hold_identities(db, hold_id)\n', '    pass\n')],
                            [('    await _guard_hold_identities(db, hold_id)\n',
                              '    await _guard_hold_identities(db,  hold_id)\n')],
                            'test_match_hold_deletion_pg.py',
                            'fix1_h4_each_hold_writer_guards_before_downstream_lock'),
 'MERGED.FIX1.H4.MINE': ('FIX1',
                         'match_hold.py',
                         [('async def _guard_identities(db, steam_ids):\n',
                           'async def _unguarded_identities(db, steam_ids):\n'
                           '    keys = sorted({str(s) for s in steam_ids if s is not None})\n'
                           '    rows = (await db.execute(text(\n'
                           '        "SELECT id, steam_id FROM players"\n'
                           '        " WHERE steam_id = ANY(CAST(:steams AS varchar[])) AND '
                           'deleted_at IS NULL"),\n'
                           '        {"steams": keys})).mappings().all()\n'
                           '    return {r["steam_id"]: r["id"] for r in rows}\n'
                           '\n'
                           '\n'
                           'async def _unguarded_hold_identities(db, hold_id, steam_id=None):\n'
                           '    return await _hold_row(db, hold_id), (await _player_id(db, '
                           'steam_id) if steam_id else None)\n'
                           '\n'
                           '\n'
                           'async def _guard_identities(db, steam_ids):\n'),
                          ('            _, pid = await _guard_hold_identities(db, peek, '
                           'steam_id)\n',
                           '            _, pid = await _unguarded_hold_identities(db, peek, '
                           'steam_id)\n')],
                         [('            _, pid = await _guard_hold_identities(db, peek, '
                           'steam_id)\n',
                           '            _, pid = await _guard_hold_identities(db,  peek, '
                           'steam_id)\n')],
                         'test_match_hold_deletion_pg.py',
                         'fix1_h4_each_hold_writer_guards_before_downstream_lock'),
 'MERGED.FIX1.H4.CLAIM': ('FIX1',
                          'match_hold.py',
                          [('async def _guard_identities(db, steam_ids):\n',
                            'async def _unguarded_identities(db, steam_ids):\n'
                            '    keys = sorted({str(s) for s in steam_ids if s is not None})\n'
                            '    rows = (await db.execute(text(\n'
                            '        "SELECT id, steam_id FROM players"\n'
                            '        " WHERE steam_id = ANY(CAST(:steams AS varchar[])) AND '
                            'deleted_at IS NULL"),\n'
                            '        {"steams": keys})).mappings().all()\n'
                            '    return {r["steam_id"]: r["id"] for r in rows}\n'
                            '\n'
                            '\n'
                            'async def _unguarded_hold_identities(db, hold_id, steam_id=None):\n'
                            '    return await _hold_row(db, hold_id), (await _player_id(db, '
                            'steam_id) if steam_id else None)\n'
                            '\n'
                            '\n'
                            'async def _guard_identities(db, steam_ids):\n'),
                           ('    peek, pid = await _guard_hold_identities(db, hold_id, '
                            'req.steam_id)\n',
                            '    peek, pid = await _unguarded_hold_identities(db, hold_id, '
                            'req.steam_id)\n')],
                          [('    peek, pid = await _guard_hold_identities(db, hold_id, '
                            'req.steam_id)\n',
                            '    peek, pid = await _guard_hold_identities(db,  hold_id, '
                            'req.steam_id)\n')],
                          'test_match_hold_deletion_pg.py',
                          'fix1_h4_each_hold_writer_guards_before_downstream_lock'),
 'MERGED.FIX1.H4.CLAIM_AUDIT': ('FIX1',
                                'match_hold.py',
                                [('async def _guard_identities(db, steam_ids):\n',
                                  'async def _unguarded_identities(db, steam_ids):\n'
                                  '    keys = sorted({str(s) for s in steam_ids if s is not '
                                  'None})\n'
                                  '    rows = (await db.execute(text(\n'
                                  '        "SELECT id, steam_id FROM players"\n'
                                  '        " WHERE steam_id = ANY(CAST(:steams AS varchar[])) AND '
                                  'deleted_at IS NULL"),\n'
                                  '        {"steams": keys})).mappings().all()\n'
                                  '    return {r["steam_id"]: r["id"] for r in rows}\n'
                                  '\n'
                                  '\n'
                                  'async def _unguarded_hold_identities(db, hold_id, '
                                  'steam_id=None):\n'
                                  '    return await _hold_row(db, hold_id), (await _player_id(db, '
                                  'steam_id) if steam_id else None)\n'
                                  '\n'
                                  '\n'
                                  'async def _guard_identities(db, steam_ids):\n'),
                                 ('        await _guard_hold_identities(db, hold_id, '
                                  'req.steam_id)\n',
                                  '        await _unguarded_hold_identities(db, hold_id, '
                                  'req.steam_id)\n')],
                                [('        await _guard_hold_identities(db, hold_id, '
                                  'req.steam_id)\n',
                                  '        await _guard_hold_identities(db,  hold_id, '
                                  'req.steam_id)\n')],
                                'test_match_hold_deletion_pg.py',
                                'fix1_h4_each_hold_writer_guards_before_downstream_lock'),
 'MERGED.FIX1.H4.BIND': ('FIX1',
                         'match_hold.py',
                         [('async def _guard_identities(db, steam_ids):\n',
                           'async def _unguarded_identities(db, steam_ids):\n'
                           '    keys = sorted({str(s) for s in steam_ids if s is not None})\n'
                           '    rows = (await db.execute(text(\n'
                           '        "SELECT id, steam_id FROM players"\n'
                           '        " WHERE steam_id = ANY(CAST(:steams AS varchar[])) AND '
                           'deleted_at IS NULL"),\n'
                           '        {"steams": keys})).mappings().all()\n'
                           '    return {r["steam_id"]: r["id"] for r in rows}\n'
                           '\n'
                           '\n'
                           'async def _unguarded_hold_identities(db, hold_id, steam_id=None):\n'
                           '    return await _hold_row(db, hold_id), (await _player_id(db, '
                           'steam_id) if steam_id else None)\n'
                           '\n'
                           '\n'
                           'async def _guard_identities(db, steam_ids):\n'),
                          ('    in one transaction."""\n'
                           '    await _require_verified_session(request, req.steam_id, db)\n'
                           '    _, pid = await _guard_hold_identities(db, hold_id, req.steam_id)\n',
                           '    in one transaction."""\n'
                           '    await _require_verified_session(request, req.steam_id, db)\n'
                           '    _, pid = await _unguarded_hold_identities(db, hold_id, '
                           'req.steam_id)\n')],
                         [('    in one transaction."""\n'
                           '    await _require_verified_session(request, req.steam_id, db)\n'
                           '    _, pid = await _guard_hold_identities(db, hold_id, req.steam_id)\n',
                           '    in one transaction."""\n'
                           '    await _require_verified_session(request, req.steam_id, db)\n'
                           '    _, pid = await _guard_hold_identities(db,  hold_id, '
                           'req.steam_id)\n')],
                         'test_match_hold_deletion_pg.py',
                         'fix1_h4_each_hold_writer_guards_before_downstream_lock'),
 'MERGED.FIX1.H4.ENTERED': ('FIX1',
                            'match_hold.py',
                            [('async def _guard_identities(db, steam_ids):\n',
                              'async def _unguarded_identities(db, steam_ids):\n'
                              '    keys = sorted({str(s) for s in steam_ids if s is not None})\n'
                              '    rows = (await db.execute(text(\n'
                              '        "SELECT id, steam_id FROM players"\n'
                              '        " WHERE steam_id = ANY(CAST(:steams AS varchar[])) AND '
                              'deleted_at IS NULL"),\n'
                              '        {"steams": keys})).mappings().all()\n'
                              '    return {r["steam_id"]: r["id"] for r in rows}\n'
                              '\n'
                              '\n'
                              'async def _unguarded_hold_identities(db, hold_id, steam_id=None):\n'
                              '    return await _hold_row(db, hold_id), (await _player_id(db, '
                              'steam_id) if steam_id else None)\n'
                              '\n'
                              '\n'
                              'async def _guard_identities(db, steam_ids):\n'),
                             ('    spends T (the verifier is cleared) and seq + 1, with its '
                              'attempt row."""\n'
                              '    await _require_verified_session(request, req.steam_id, db)\n'
                              '    _, pid = await _guard_hold_identities(db, hold_id, '
                              'req.steam_id)\n',
                              '    spends T (the verifier is cleared) and seq + 1, with its '
                              'attempt row."""\n'
                              '    await _require_verified_session(request, req.steam_id, db)\n'
                              '    _, pid = await _unguarded_hold_identities(db, hold_id, '
                              'req.steam_id)\n')],
                            [('    spends T (the verifier is cleared) and seq + 1, with its '
                              'attempt row."""\n'
                              '    await _require_verified_session(request, req.steam_id, db)\n'
                              '    _, pid = await _guard_hold_identities(db, hold_id, '
                              'req.steam_id)\n',
                              '    spends T (the verifier is cleared) and seq + 1, with its '
                              'attempt row."""\n'
                              '    await _require_verified_session(request, req.steam_id, db)\n'
                              '    _, pid = await _guard_hold_identities(db,  hold_id, '
                              'req.steam_id)\n')],
                            'test_match_hold_deletion_pg.py',
                            'fix1_h4_each_hold_writer_guards_before_downstream_lock'),
 'MERGED.FIX1.H4.END': ('FIX1',
                        'match_hold.py',
                        [('async def _guard_identities(db, steam_ids):\n',
                          'async def _unguarded_identities(db, steam_ids):\n'
                          '    keys = sorted({str(s) for s in steam_ids if s is not None})\n'
                          '    rows = (await db.execute(text(\n'
                          '        "SELECT id, steam_id FROM players"\n'
                          '        " WHERE steam_id = ANY(CAST(:steams AS varchar[])) AND '
                          'deleted_at IS NULL"),\n'
                          '        {"steams": keys})).mappings().all()\n'
                          '    return {r["steam_id"]: r["id"] for r in rows}\n'
                          '\n'
                          '\n'
                          'async def _unguarded_hold_identities(db, hold_id, steam_id=None):\n'
                          '    return await _hold_row(db, hold_id), (await _player_id(db, '
                          'steam_id) if steam_id else None)\n'
                          '\n'
                          '\n'
                          'async def _guard_identities(db, steam_ids):\n'),
                         ('        raise HTTPException(400, "unknown end reason")\n'
                          '    await _require_verified_session(request, req.steam_id, db)\n'
                          '    _, pid = await _guard_hold_identities(db, hold_id, req.steam_id)\n',
                          '        raise HTTPException(400, "unknown end reason")\n'
                          '    await _require_verified_session(request, req.steam_id, db)\n'
                          '    _, pid = await _unguarded_hold_identities(db, hold_id, '
                          'req.steam_id)\n')],
                        [('        raise HTTPException(400, "unknown end reason")\n'
                          '    await _require_verified_session(request, req.steam_id, db)\n'
                          '    _, pid = await _guard_hold_identities(db, hold_id, req.steam_id)\n',
                          '        raise HTTPException(400, "unknown end reason")\n'
                          '    await _require_verified_session(request, req.steam_id, db)\n'
                          '    _, pid = await _guard_hold_identities(db,  hold_id, '
                          'req.steam_id)\n')],
                        'test_match_hold_deletion_pg.py',
                        'fix1_h4_each_hold_writer_guards_before_downstream_lock'),
 'MERGED.FIX1.H4.SEEN': ('FIX1',
                         'match_hold.py',
                         [('                       if live.get(s.u_id) in members])\n',
                           '                       if True])\n')],
                         [('                       if live.get(s.u_id) in members])\n',
                           '                       if (live.get(s.u_id) in members)])\n')],
                         'test_match_hold_deletion_pg.py',
                         'fix1_h4_beat_deletion_orders_and_survivors')})

MUTANTS.update({'MERGED.FIX1.H4.WINDOW_RECEIVE': ('FIX1',
                                   'match_report_window.py',
                                   [('async def _guard_window_identities(',
                                     'async def _unguarded_player_ids(db, ids, keys):\n'
                                     '    discovered = (await db.execute(text(\n'
                                     '        "SELECT id, steam_id FROM players WHERE id = '
                                     'ANY(CAST(:ids AS uuid[]))"),\n'
                                     '        {"ids": [str(p) for p in ids]})).mappings().all()\n'
                                     '    keys = set(keys) | {r["steam_id"] for r in discovered}\n'
                                     '    rows = (await db.execute(text(\n'
                                     '        "SELECT id, steam_id FROM players"\n'
                                     '        " WHERE steam_id = ANY(CAST(:keys AS varchar[])) AND '
                                     'deleted_at IS NULL"),\n'
                                     '        {"keys": list(keys)})).mappings().all()\n'
                                     '    live = {r["steam_id"]: r["id"] for r in rows}\n'
                                     '    return {r["id"]: r["steam_id"] for r in discovered\n'
                                     '            if live.get(r["steam_id"]) == r["id"]}, live\n'
                                     '\n'
                                     '\n'
                                     'async def _unguarded_window_identities(db, *, room, game_id, '
                                     'mode=None, payload=None,\n'
                                     '                                   reporter_id=None, '
                                     'reporter_steam=None, member_ids=()):\n'
                                     '    """Take the complete identity set before window, series, '
                                     'hold or lease locks.\n'
                                     '\n'
                                     '    Discovery is unlocked and supplies guard keys only. '
                                     'Every identity-bearing\n'
                                     '    sink revalidates the identities it will store after '
                                     'acquisition. Existing\n'
                                     '    scrubbed payloads may remain for disposition without '
                                     'restoring their keys.\n'
                                     '    """\n'
                                     '    from match_hold import _members, _series_read\n'
                                     '    game = (await db.execute(text(\n'
                                     '        "SELECT mode, series_id FROM match_games WHERE id = '
                                     'CAST(:g AS uuid)"\n'
                                     '        " AND room_name = CAST(:room AS varchar)"),\n'
                                     '        {"g": str(game_id), "room": '
                                     'room})).mappings().first()\n'
                                     '    mode = mode or (game["mode"] if game is not None else '
                                     'None)\n'
                                     '    series = await _series_read(db, mode, game["series_id"]) '
                                     'if game is not None else None\n'
                                     '    roster = set(_members(mode, series)) if series is not '
                                     'None else None\n'
                                     '    rows = (await db.execute(text(\n'
                                     '        "SELECT reporter_id, reporter_steam, payload FROM '
                                     'match_report_journal"\n'
                                     '        " WHERE room_name = CAST(:room AS varchar) AND '
                                     'game_id = CAST(:g AS uuid)"),\n'
                                     '        {"room": room, "g": '
                                     'str(game_id)})).mappings().all()\n'
                                     '    ids = set(member_ids) | (roster or set())\n'
                                     '    keys = _payload_identity_keys(mode, payload)\n'
                                     '    if reporter_id is not None:\n'
                                     '        ids.add(reporter_id)\n'
                                     '    if reporter_steam is not None:\n'
                                     '        keys.add(reporter_steam)\n'
                                     '    for row in rows:\n'
                                     '        ids.add(row["reporter_id"])\n'
                                     '        keys.add(row["reporter_steam"])\n'
                                     '        keys.update(_payload_identity_keys(mode, '
                                     'row["payload"]))\n'
                                     '    owners, live = await _unguarded_player_ids(db, ids, '
                                     'keys)\n'
                                     '    return owners, live, roster\n'
                                     '\n'
                                     '\n'
                                     'async def _guard_window_identities('),
                                    ('    await _guard_window_identities(db, mode=mode, room=room, '
                                     'game_id=game_id,\n'
                                     '                                   payload=payload, '
                                     'reporter_id=reporter_id,\n'
                                     '                                   '
                                     'reporter_steam=reporter_steam, member_ids=member_ids)\n',
                                     '    await _unguarded_window_identities(db, mode=mode, '
                                     'room=room, game_id=game_id,\n'
                                     '                                   payload=payload, '
                                     'reporter_id=reporter_id,\n'
                                     '                                   '
                                     'reporter_steam=reporter_steam, member_ids=member_ids)\n')],
                                   [('    await _guard_window_identities(db, mode=mode, room=room, '
                                     'game_id=game_id,\n'
                                     '                                   payload=payload, '
                                     'reporter_id=reporter_id,\n'
                                     '                                   '
                                     'reporter_steam=reporter_steam, member_ids=member_ids)\n',
                                     '    await _guard_window_identities( db, mode=mode, '
                                     'room=room, game_id=game_id,\n'
                                     '                                   payload=payload, '
                                     'reporter_id=reporter_id,\n'
                                     '                                   '
                                     'reporter_steam=reporter_steam, member_ids=member_ids)\n')],
                                   'test_match_hold_deletion_pg.py',
                                   'fix1_h4_report_writers_guard_before_their_first_lock'),
 'MERGED.FIX1.H4.WINDOW_SETTLE': ('FIX1',
                                  'match_report_window.py',
                                  [('async def _guard_window_identities(',
                                    'async def _unguarded_player_ids(db, ids, keys):\n'
                                    '    discovered = (await db.execute(text(\n'
                                    '        "SELECT id, steam_id FROM players WHERE id = '
                                    'ANY(CAST(:ids AS uuid[]))"),\n'
                                    '        {"ids": [str(p) for p in ids]})).mappings().all()\n'
                                    '    keys = set(keys) | {r["steam_id"] for r in discovered}\n'
                                    '    rows = (await db.execute(text(\n'
                                    '        "SELECT id, steam_id FROM players"\n'
                                    '        " WHERE steam_id = ANY(CAST(:keys AS varchar[])) AND '
                                    'deleted_at IS NULL"),\n'
                                    '        {"keys": list(keys)})).mappings().all()\n'
                                    '    live = {r["steam_id"]: r["id"] for r in rows}\n'
                                    '    return {r["id"]: r["steam_id"] for r in discovered\n'
                                    '            if live.get(r["steam_id"]) == r["id"]}, live\n'
                                    '\n'
                                    '\n'
                                    'async def _unguarded_window_identities(db, *, room, game_id, '
                                    'mode=None, payload=None,\n'
                                    '                                   reporter_id=None, '
                                    'reporter_steam=None, member_ids=()):\n'
                                    '    """Take the complete identity set before window, series, '
                                    'hold or lease locks.\n'
                                    '\n'
                                    '    Discovery is unlocked and supplies guard keys only. Every '
                                    'identity-bearing\n'
                                    '    sink revalidates the identities it will store after '
                                    'acquisition. Existing\n'
                                    '    scrubbed payloads may remain for disposition without '
                                    'restoring their keys.\n'
                                    '    """\n'
                                    '    from match_hold import _members, _series_read\n'
                                    '    game = (await db.execute(text(\n'
                                    '        "SELECT mode, series_id FROM match_games WHERE id = '
                                    'CAST(:g AS uuid)"\n'
                                    '        " AND room_name = CAST(:room AS varchar)"),\n'
                                    '        {"g": str(game_id), "room": '
                                    'room})).mappings().first()\n'
                                    '    mode = mode or (game["mode"] if game is not None else '
                                    'None)\n'
                                    '    series = await _series_read(db, mode, game["series_id"]) '
                                    'if game is not None else None\n'
                                    '    roster = set(_members(mode, series)) if series is not '
                                    'None else None\n'
                                    '    rows = (await db.execute(text(\n'
                                    '        "SELECT reporter_id, reporter_steam, payload FROM '
                                    'match_report_journal"\n'
                                    '        " WHERE room_name = CAST(:room AS varchar) AND '
                                    'game_id = CAST(:g AS uuid)"),\n'
                                    '        {"room": room, "g": str(game_id)})).mappings().all()\n'
                                    '    ids = set(member_ids) | (roster or set())\n'
                                    '    keys = _payload_identity_keys(mode, payload)\n'
                                    '    if reporter_id is not None:\n'
                                    '        ids.add(reporter_id)\n'
                                    '    if reporter_steam is not None:\n'
                                    '        keys.add(reporter_steam)\n'
                                    '    for row in rows:\n'
                                    '        ids.add(row["reporter_id"])\n'
                                    '        keys.add(row["reporter_steam"])\n'
                                    '        keys.update(_payload_identity_keys(mode, '
                                    'row["payload"]))\n'
                                    '    owners, live = await _unguarded_player_ids(db, ids, '
                                    'keys)\n'
                                    '    return owners, live, roster\n'
                                    '\n'
                                    '\n'
                                    'async def _guard_window_identities('),
                                   ('    settled_at once. Returns the settled entry or None. The '
                                    'caller commits."""\n'
                                    '    await _guard_window_identities(db, mode=mode, room=room, '
                                    'game_id=game_id)\n',
                                    '    settled_at once. Returns the settled entry or None. The '
                                    'caller commits."""\n'
                                    '    await _unguarded_window_identities(db, mode=mode, '
                                    'room=room, game_id=game_id)\n')],
                                  [('    settled_at once. Returns the settled entry or None. The '
                                    'caller commits."""\n'
                                    '    await _guard_window_identities(db, mode=mode, room=room, '
                                    'game_id=game_id)\n',
                                    '    settled_at once. Returns the settled entry or None. The '
                                    'caller commits."""\n'
                                    '    await _guard_window_identities( db, mode=mode, room=room, '
                                    'game_id=game_id)\n')],
                                  'test_match_hold_deletion_pg.py',
                                  'fix1_h4_report_writers_guard_before_their_first_lock'),
 'MERGED.FIX1.H4.WINDOW_RELEASE': ('FIX1',
                                   'match_report_window.py',
                                   [('async def _guard_window_identities(',
                                     'async def _unguarded_player_ids(db, ids, keys):\n'
                                     '    discovered = (await db.execute(text(\n'
                                     '        "SELECT id, steam_id FROM players WHERE id = '
                                     'ANY(CAST(:ids AS uuid[]))"),\n'
                                     '        {"ids": [str(p) for p in ids]})).mappings().all()\n'
                                     '    keys = set(keys) | {r["steam_id"] for r in discovered}\n'
                                     '    rows = (await db.execute(text(\n'
                                     '        "SELECT id, steam_id FROM players"\n'
                                     '        " WHERE steam_id = ANY(CAST(:keys AS varchar[])) AND '
                                     'deleted_at IS NULL"),\n'
                                     '        {"keys": list(keys)})).mappings().all()\n'
                                     '    live = {r["steam_id"]: r["id"] for r in rows}\n'
                                     '    return {r["id"]: r["steam_id"] for r in discovered\n'
                                     '            if live.get(r["steam_id"]) == r["id"]}, live\n'
                                     '\n'
                                     '\n'
                                     'async def _unguarded_window_identities(db, *, room, game_id, '
                                     'mode=None, payload=None,\n'
                                     '                                   reporter_id=None, '
                                     'reporter_steam=None, member_ids=()):\n'
                                     '    """Take the complete identity set before window, series, '
                                     'hold or lease locks.\n'
                                     '\n'
                                     '    Discovery is unlocked and supplies guard keys only. '
                                     'Every identity-bearing\n'
                                     '    sink revalidates the identities it will store after '
                                     'acquisition. Existing\n'
                                     '    scrubbed payloads may remain for disposition without '
                                     'restoring their keys.\n'
                                     '    """\n'
                                     '    from match_hold import _members, _series_read\n'
                                     '    game = (await db.execute(text(\n'
                                     '        "SELECT mode, series_id FROM match_games WHERE id = '
                                     'CAST(:g AS uuid)"\n'
                                     '        " AND room_name = CAST(:room AS varchar)"),\n'
                                     '        {"g": str(game_id), "room": '
                                     'room})).mappings().first()\n'
                                     '    mode = mode or (game["mode"] if game is not None else '
                                     'None)\n'
                                     '    series = await _series_read(db, mode, game["series_id"]) '
                                     'if game is not None else None\n'
                                     '    roster = set(_members(mode, series)) if series is not '
                                     'None else None\n'
                                     '    rows = (await db.execute(text(\n'
                                     '        "SELECT reporter_id, reporter_steam, payload FROM '
                                     'match_report_journal"\n'
                                     '        " WHERE room_name = CAST(:room AS varchar) AND '
                                     'game_id = CAST(:g AS uuid)"),\n'
                                     '        {"room": room, "g": '
                                     'str(game_id)})).mappings().all()\n'
                                     '    ids = set(member_ids) | (roster or set())\n'
                                     '    keys = _payload_identity_keys(mode, payload)\n'
                                     '    if reporter_id is not None:\n'
                                     '        ids.add(reporter_id)\n'
                                     '    if reporter_steam is not None:\n'
                                     '        keys.add(reporter_steam)\n'
                                     '    for row in rows:\n'
                                     '        ids.add(row["reporter_id"])\n'
                                     '        keys.add(row["reporter_steam"])\n'
                                     '        keys.update(_payload_identity_keys(mode, '
                                     'row["payload"]))\n'
                                     '    owners, live = await _unguarded_player_ids(db, ids, '
                                     'keys)\n'
                                     '    return owners, live, roster\n'
                                     '\n'
                                     '\n'
                                     'async def _guard_window_identities('),
                                    ('    """Release entered causal holds together so class priority stays global.\n\n    The caller proved this hold entered and that no later live or nonentry\n    hold blocks release. Earlier entered holds become eligible together."""\n    await _guard_window_identities(db, mode=mode, room=room, game_id=game_id)\n',
                                     '    """Release entered causal holds together so class priority stays global.\n\n    The caller proved this hold entered and that no later live or nonentry\n    hold blocks release. Earlier entered holds become eligible together."""\n    await _unguarded_window_identities(db, mode=mode, room=room, game_id=game_id)\n')],
                                   [('    """Release entered causal holds together so class priority stays global.\n\n    The caller proved this hold entered and that no later live or nonentry\n    hold blocks release. Earlier entered holds become eligible together."""\n    await _guard_window_identities(db, mode=mode, room=room, game_id=game_id)\n',
                                     '    """Release entered causal holds together so class priority stays global.\n\n    The caller proved this hold entered and that no later live or nonentry\n    hold blocks release. Earlier entered holds become eligible together."""\n    await _guard_window_identities( db, mode=mode, room=room, game_id=game_id)\n')],
                                   'test_match_hold_deletion_pg.py',
                                   'fix1_h4_report_writers_guard_before_their_first_lock'),
 'MERGED.FIX1.H4.WINDOW_SUPERSEDE': ('FIX1',
                                     'match_report_window.py',
                                     [('async def _guard_window_identities(',
                                       'async def _unguarded_player_ids(db, ids, keys):\n'
                                       '    discovered = (await db.execute(text(\n'
                                       '        "SELECT id, steam_id FROM players WHERE id = '
                                       'ANY(CAST(:ids AS uuid[]))"),\n'
                                       '        {"ids": [str(p) for p in ids]})).mappings().all()\n'
                                       '    keys = set(keys) | {r["steam_id"] for r in '
                                       'discovered}\n'
                                       '    rows = (await db.execute(text(\n'
                                       '        "SELECT id, steam_id FROM players"\n'
                                       '        " WHERE steam_id = ANY(CAST(:keys AS varchar[])) '
                                       'AND deleted_at IS NULL"),\n'
                                       '        {"keys": list(keys)})).mappings().all()\n'
                                       '    live = {r["steam_id"]: r["id"] for r in rows}\n'
                                       '    return {r["id"]: r["steam_id"] for r in discovered\n'
                                       '            if live.get(r["steam_id"]) == r["id"]}, live\n'
                                       '\n'
                                       '\n'
                                       'async def _unguarded_window_identities(db, *, room, '
                                       'game_id, mode=None, payload=None,\n'
                                       '                                   reporter_id=None, '
                                       'reporter_steam=None, member_ids=()):\n'
                                       '    """Take the complete identity set before window, '
                                       'series, hold or lease locks.\n'
                                       '\n'
                                       '    Discovery is unlocked and supplies guard keys only. '
                                       'Every identity-bearing\n'
                                       '    sink revalidates the identities it will store after '
                                       'acquisition. Existing\n'
                                       '    scrubbed payloads may remain for disposition without '
                                       'restoring their keys.\n'
                                       '    """\n'
                                       '    from match_hold import _members, _series_read\n'
                                       '    game = (await db.execute(text(\n'
                                       '        "SELECT mode, series_id FROM match_games WHERE id '
                                       '= CAST(:g AS uuid)"\n'
                                       '        " AND room_name = CAST(:room AS varchar)"),\n'
                                       '        {"g": str(game_id), "room": '
                                       'room})).mappings().first()\n'
                                       '    mode = mode or (game["mode"] if game is not None else '
                                       'None)\n'
                                       '    series = await _series_read(db, mode, '
                                       'game["series_id"]) if game is not None else None\n'
                                       '    roster = set(_members(mode, series)) if series is not '
                                       'None else None\n'
                                       '    rows = (await db.execute(text(\n'
                                       '        "SELECT reporter_id, reporter_steam, payload FROM '
                                       'match_report_journal"\n'
                                       '        " WHERE room_name = CAST(:room AS varchar) AND '
                                       'game_id = CAST(:g AS uuid)"),\n'
                                       '        {"room": room, "g": '
                                       'str(game_id)})).mappings().all()\n'
                                       '    ids = set(member_ids) | (roster or set())\n'
                                       '    keys = _payload_identity_keys(mode, payload)\n'
                                       '    if reporter_id is not None:\n'
                                       '        ids.add(reporter_id)\n'
                                       '    if reporter_steam is not None:\n'
                                       '        keys.add(reporter_steam)\n'
                                       '    for row in rows:\n'
                                       '        ids.add(row["reporter_id"])\n'
                                       '        keys.add(row["reporter_steam"])\n'
                                       '        keys.update(_payload_identity_keys(mode, '
                                       'row["payload"]))\n'
                                       '    owners, live = await _unguarded_player_ids(db, ids, '
                                       'keys)\n'
                                       '    return owners, live, roster\n'
                                       '\n'
                                       '\n'
                                       'async def _guard_window_identities('),
                                      ('    review and never settled. Returns the rows '
                                       'superseded."""\n'
                                       '    await _guard_window_identities(db, mode=mode, '
                                       'room=room, game_id=game_id)\n',
                                       '    review and never settled. Returns the rows '
                                       'superseded."""\n'
                                       '    await _unguarded_window_identities(db, mode=mode, '
                                       'room=room, game_id=game_id)\n')],
                                     [('    review and never settled. Returns the rows '
                                       'superseded."""\n'
                                       '    await _guard_window_identities(db, mode=mode, '
                                       'room=room, game_id=game_id)\n',
                                       '    review and never settled. Returns the rows '
                                       'superseded."""\n'
                                       '    await _guard_window_identities( db, mode=mode, '
                                       'room=room, game_id=game_id)\n')],
                                     'test_match_hold_deletion_pg.py',
                                     'fix1_h4_report_writers_guard_before_their_first_lock'),
 'MERGED.FIX1.H4.WINDOW_FINISH': ('FIX1',
                                  'match_report_window.py',
                                  [('async def _guard_window_identities(',
                                    'async def _unguarded_player_ids(db, ids, keys):\n'
                                    '    discovered = (await db.execute(text(\n'
                                    '        "SELECT id, steam_id FROM players WHERE id = '
                                    'ANY(CAST(:ids AS uuid[]))"),\n'
                                    '        {"ids": [str(p) for p in ids]})).mappings().all()\n'
                                    '    keys = set(keys) | {r["steam_id"] for r in discovered}\n'
                                    '    rows = (await db.execute(text(\n'
                                    '        "SELECT id, steam_id FROM players"\n'
                                    '        " WHERE steam_id = ANY(CAST(:keys AS varchar[])) AND '
                                    'deleted_at IS NULL"),\n'
                                    '        {"keys": list(keys)})).mappings().all()\n'
                                    '    live = {r["steam_id"]: r["id"] for r in rows}\n'
                                    '    return {r["id"]: r["steam_id"] for r in discovered\n'
                                    '            if live.get(r["steam_id"]) == r["id"]}, live\n'
                                    '\n'
                                    '\n'
                                    'async def _unguarded_window_identities(db, *, room, game_id, '
                                    'mode=None, payload=None,\n'
                                    '                                   reporter_id=None, '
                                    'reporter_steam=None, member_ids=()):\n'
                                    '    """Take the complete identity set before window, series, '
                                    'hold or lease locks.\n'
                                    '\n'
                                    '    Discovery is unlocked and supplies guard keys only. Every '
                                    'identity-bearing\n'
                                    '    sink revalidates the identities it will store after '
                                    'acquisition. Existing\n'
                                    '    scrubbed payloads may remain for disposition without '
                                    'restoring their keys.\n'
                                    '    """\n'
                                    '    from match_hold import _members, _series_read\n'
                                    '    game = (await db.execute(text(\n'
                                    '        "SELECT mode, series_id FROM match_games WHERE id = '
                                    'CAST(:g AS uuid)"\n'
                                    '        " AND room_name = CAST(:room AS varchar)"),\n'
                                    '        {"g": str(game_id), "room": '
                                    'room})).mappings().first()\n'
                                    '    mode = mode or (game["mode"] if game is not None else '
                                    'None)\n'
                                    '    series = await _series_read(db, mode, game["series_id"]) '
                                    'if game is not None else None\n'
                                    '    roster = set(_members(mode, series)) if series is not '
                                    'None else None\n'
                                    '    rows = (await db.execute(text(\n'
                                    '        "SELECT reporter_id, reporter_steam, payload FROM '
                                    'match_report_journal"\n'
                                    '        " WHERE room_name = CAST(:room AS varchar) AND '
                                    'game_id = CAST(:g AS uuid)"),\n'
                                    '        {"room": room, "g": str(game_id)})).mappings().all()\n'
                                    '    ids = set(member_ids) | (roster or set())\n'
                                    '    keys = _payload_identity_keys(mode, payload)\n'
                                    '    if reporter_id is not None:\n'
                                    '        ids.add(reporter_id)\n'
                                    '    if reporter_steam is not None:\n'
                                    '        keys.add(reporter_steam)\n'
                                    '    for row in rows:\n'
                                    '        ids.add(row["reporter_id"])\n'
                                    '        keys.add(row["reporter_steam"])\n'
                                    '        keys.update(_payload_identity_keys(mode, '
                                    'row["payload"]))\n'
                                    '    owners, live = await _unguarded_player_ids(db, ids, '
                                    'keys)\n'
                                    '    return owners, live, roster\n'
                                    '\n'
                                    '\n'
                                    'async def _guard_window_identities('),
                                   ('        await _guard_window_identities(db, mode=mode, '
                                    'room=room, game_id=game_id)\n',
                                    '        await _unguarded_window_identities(db, mode=mode, '
                                    'room=room, game_id=game_id)\n')],
                                  [('        await _guard_window_identities(db, mode=mode, '
                                    'room=room, game_id=game_id)\n',
                                    '        await _guard_window_identities( db, mode=mode, '
                                    'room=room, game_id=game_id)\n')],
                                  'test_match_hold_deletion_pg.py',
                                  'fix1_h4_report_writers_guard_before_their_first_lock'),
 'MERGED.FIX1.H4.JOURNAL': ('FIX1',
                            'match_report_window.py',
                            [('async def _guard_window_identities(',
                              'async def _unguarded_player_ids(db, ids, keys):\n'
                              '    discovered = (await db.execute(text(\n'
                              '        "SELECT id, steam_id FROM players WHERE id = ANY(CAST(:ids '
                              'AS uuid[]))"),\n'
                              '        {"ids": [str(p) for p in ids]})).mappings().all()\n'
                              '    keys = set(keys) | {r["steam_id"] for r in discovered}\n'
                              '    rows = (await db.execute(text(\n'
                              '        "SELECT id, steam_id FROM players"\n'
                              '        " WHERE steam_id = ANY(CAST(:keys AS varchar[])) AND '
                              'deleted_at IS NULL"),\n'
                              '        {"keys": list(keys)})).mappings().all()\n'
                              '    live = {r["steam_id"]: r["id"] for r in rows}\n'
                              '    return {r["id"]: r["steam_id"] for r in discovered\n'
                              '            if live.get(r["steam_id"]) == r["id"]}, live\n'
                              '\n'
                              '\n'
                              'async def _unguarded_window_identities(db, *, room, game_id, '
                              'mode=None, payload=None,\n'
                              '                                   reporter_id=None, '
                              'reporter_steam=None, member_ids=()):\n'
                              '    """Take the complete identity set before window, series, hold '
                              'or lease locks.\n'
                              '\n'
                              '    Discovery is unlocked and supplies guard keys only. Every '
                              'identity-bearing\n'
                              '    sink revalidates the identities it will store after '
                              'acquisition. Existing\n'
                              '    scrubbed payloads may remain for disposition without restoring '
                              'their keys.\n'
                              '    """\n'
                              '    from match_hold import _members, _series_read\n'
                              '    game = (await db.execute(text(\n'
                              '        "SELECT mode, series_id FROM match_games WHERE id = CAST(:g '
                              'AS uuid)"\n'
                              '        " AND room_name = CAST(:room AS varchar)"),\n'
                              '        {"g": str(game_id), "room": room})).mappings().first()\n'
                              '    mode = mode or (game["mode"] if game is not None else None)\n'
                              '    series = await _series_read(db, mode, game["series_id"]) if '
                              'game is not None else None\n'
                              '    roster = set(_members(mode, series)) if series is not None else '
                              'None\n'
                              '    rows = (await db.execute(text(\n'
                              '        "SELECT reporter_id, reporter_steam, payload FROM '
                              'match_report_journal"\n'
                              '        " WHERE room_name = CAST(:room AS varchar) AND game_id = '
                              'CAST(:g AS uuid)"),\n'
                              '        {"room": room, "g": str(game_id)})).mappings().all()\n'
                              '    ids = set(member_ids) | (roster or set())\n'
                              '    keys = _payload_identity_keys(mode, payload)\n'
                              '    if reporter_id is not None:\n'
                              '        ids.add(reporter_id)\n'
                              '    if reporter_steam is not None:\n'
                              '        keys.add(reporter_steam)\n'
                              '    for row in rows:\n'
                              '        ids.add(row["reporter_id"])\n'
                              '        keys.add(row["reporter_steam"])\n'
                              '        keys.update(_payload_identity_keys(mode, row["payload"]))\n'
                              '    owners, live = await _unguarded_player_ids(db, ids, keys)\n'
                              '    return owners, live, roster\n'
                              '\n'
                              '\n'
                              'async def _guard_window_identities('),
                             ('    owners, live, roster = await _guard_window_identities(\n'
                              '        db, mode=mode, room=room, game_id=game_id, '
                              'payload=payload,\n'
                              '        reporter_id=reporter_id, reporter_steam=reporter_steam)\n',
                              '    owners, live, roster = await _unguarded_window_identities(\n'
                              '        db, mode=mode, room=room, game_id=game_id, '
                              'payload=payload,\n'
                              '        reporter_id=reporter_id, reporter_steam=reporter_steam)\n')],
                            [('    owners, live, roster = await _guard_window_identities(\n'
                              '        db, mode=mode, room=room, game_id=game_id, '
                              'payload=payload,\n'
                              '        reporter_id=reporter_id, reporter_steam=reporter_steam)\n',
                              '    owners, live, roster = await _guard_window_identities( \n'
                              '        db, mode=mode, room=room, game_id=game_id, '
                              'payload=payload,\n'
                              '        reporter_id=reporter_id, reporter_steam=reporter_steam)\n')],
                            'test_match_hold_deletion_pg.py',
                            'fix1_h4_report_writers_guard_before_their_first_lock'),
 'MERGED.FIX1.H4.MARK': ('FIX1',
                         'match_report_window.py',
                         [('async def _guard_window_identities(',
                           'async def _unguarded_player_ids(db, ids, keys):\n'
                           '    discovered = (await db.execute(text(\n'
                           '        "SELECT id, steam_id FROM players WHERE id = ANY(CAST(:ids AS '
                           'uuid[]))"),\n'
                           '        {"ids": [str(p) for p in ids]})).mappings().all()\n'
                           '    keys = set(keys) | {r["steam_id"] for r in discovered}\n'
                           '    rows = (await db.execute(text(\n'
                           '        "SELECT id, steam_id FROM players"\n'
                           '        " WHERE steam_id = ANY(CAST(:keys AS varchar[])) AND '
                           'deleted_at IS NULL"),\n'
                           '        {"keys": list(keys)})).mappings().all()\n'
                           '    live = {r["steam_id"]: r["id"] for r in rows}\n'
                           '    return {r["id"]: r["steam_id"] for r in discovered\n'
                           '            if live.get(r["steam_id"]) == r["id"]}, live\n'
                           '\n'
                           '\n'
                           'async def _unguarded_window_identities(db, *, room, game_id, '
                           'mode=None, payload=None,\n'
                           '                                   reporter_id=None, '
                           'reporter_steam=None, member_ids=()):\n'
                           '    """Take the complete identity set before window, series, hold or '
                           'lease locks.\n'
                           '\n'
                           '    Discovery is unlocked and supplies guard keys only. Every '
                           'identity-bearing\n'
                           '    sink revalidates the identities it will store after acquisition. '
                           'Existing\n'
                           '    scrubbed payloads may remain for disposition without restoring '
                           'their keys.\n'
                           '    """\n'
                           '    from match_hold import _members, _series_read\n'
                           '    game = (await db.execute(text(\n'
                           '        "SELECT mode, series_id FROM match_games WHERE id = CAST(:g AS '
                           'uuid)"\n'
                           '        " AND room_name = CAST(:room AS varchar)"),\n'
                           '        {"g": str(game_id), "room": room})).mappings().first()\n'
                           '    mode = mode or (game["mode"] if game is not None else None)\n'
                           '    series = await _series_read(db, mode, game["series_id"]) if game '
                           'is not None else None\n'
                           '    roster = set(_members(mode, series)) if series is not None else '
                           'None\n'
                           '    rows = (await db.execute(text(\n'
                           '        "SELECT reporter_id, reporter_steam, payload FROM '
                           'match_report_journal"\n'
                           '        " WHERE room_name = CAST(:room AS varchar) AND game_id = '
                           'CAST(:g AS uuid)"),\n'
                           '        {"room": room, "g": str(game_id)})).mappings().all()\n'
                           '    ids = set(member_ids) | (roster or set())\n'
                           '    keys = _payload_identity_keys(mode, payload)\n'
                           '    if reporter_id is not None:\n'
                           '        ids.add(reporter_id)\n'
                           '    if reporter_steam is not None:\n'
                           '        keys.add(reporter_steam)\n'
                           '    for row in rows:\n'
                           '        ids.add(row["reporter_id"])\n'
                           '        keys.add(row["reporter_steam"])\n'
                           '        keys.update(_payload_identity_keys(mode, row["payload"]))\n'
                           '    owners, live = await _unguarded_player_ids(db, ids, keys)\n'
                           '    return owners, live, roster\n'
                           '\n'
                           '\n'
                           'async def _guard_window_identities('),
                          ('    owners, _, _ = await _guard_window_identities(\n'
                           '        db, room=room, game_id=game_id, '
                           'reporter_id=chosen["reporter_id"])\n',
                           '    owners, _, _ = await _unguarded_window_identities(\n'
                           '        db, room=room, game_id=game_id, '
                           'reporter_id=chosen["reporter_id"])\n')],
                         [('    owners, _, _ = await _guard_window_identities(\n'
                           '        db, room=room, game_id=game_id, '
                           'reporter_id=chosen["reporter_id"])\n',
                           '    owners, _, _ = await _guard_window_identities( \n'
                           '        db, room=room, game_id=game_id, '
                           'reporter_id=chosen["reporter_id"])\n')],
                         'test_match_hold_deletion_pg.py',
                         'fix1_h4_report_writers_guard_before_their_first_lock'),
 'MERGED.FIX1.H4.TERMINAL_ATTRIBUTION': ('FIX1',
                                         'match_report_window.py',
                                         [('    if terminal:\n'
                                           '        # The result is already final. Deletion may '
                                           'have cleared its reporter;\n'
                                           '        # only dispose of released rows, preserving '
                                           'that NULL attribution.\n'
                                           '        await db.execute(text(\n'
                                           '            "UPDATE match_report_journal SET state = '
                                           'CASE"\n'
                                           '            " WHEN reporter_id = CAST(:pid AS uuid) '
                                           'THEN \'settled\' ELSE \'kept\' END,"\n'
                                           '            " decided_at = CAST(:now AS timestamptz)"\n'
                                           '            " WHERE room_name = CAST(:room AS varchar) '
                                           'AND game_id = CAST(:g AS uuid)"\n'
                                           '            " AND state = \'journaled\'"),\n'
                                           '            {**params, "pid": '
                                           'window["settled_reporter_id"]})\n'
                                           '        return released\n',
                                           '    if terminal:\n'
                                           '        await _mark_settled(db, room, game_id,\n'
                                           '            {"reporter_id": '
                                           'window["settled_reporter_id"], "cls": '
                                           'window["settled_cls"]}, now)\n'
                                           '        return released\n')],
                                         [('    if terminal:\n'
                                           '        # The result is already final. Deletion may '
                                           'have cleared its reporter;\n'
                                           '        # only dispose of released rows, preserving '
                                           'that NULL attribution.\n'
                                           '        await db.execute(text(\n'
                                           '            "UPDATE match_report_journal SET state = '
                                           'CASE"\n'
                                           '            " WHEN reporter_id = CAST(:pid AS uuid) '
                                           'THEN \'settled\' ELSE \'kept\' END,"\n'
                                           '            " decided_at = CAST(:now AS timestamptz)"\n'
                                           '            " WHERE room_name = CAST(:room AS varchar) '
                                           'AND game_id = CAST(:g AS uuid)"\n'
                                           '            " AND state = \'journaled\'"),\n'
                                           '            {**params, "pid": '
                                           'window["settled_reporter_id"]})\n'
                                           '        return released\n',
                                           '    if terminal:\n'
                                           '        # The result is already final. Deletion may '
                                           'have cleared its reporter;\n'
                                           '        # only dispose of released rows, preserving '
                                           'that NULL attribution.\n'
                                           '        await db.execute(text(\n'
                                           '            "UPDATE match_report_journal SET state = '
                                           'CASE"\n'
                                           '            " WHEN reporter_id = CAST(:pid AS uuid) '
                                           'THEN \'settled\' ELSE \'kept\' END,"\n'
                                           '            " decided_at = CAST(:now AS timestamptz)"\n'
                                           '            " WHERE room_name = CAST(:room AS varchar) '
                                           'AND game_id = CAST(:g AS uuid)"\n'
                                           '            " AND state = \'journaled\'"),\n'
                                           '            {**params, "pid": '
                                           'window["settled_reporter_id"]})\n'
                                           '        return (released)\n')],
                                         'test_match_hold_deletion_pg.py',
                                         'fix1_h4_terminal_release_preserves_cleared_attribution')})

MUTANTS.update({'FIX2.M1.SETTLE': ('FIX2',
                    'match_report_window.py',
                    [('    if _window_terminal(window) or _window_unarmed(window) or '
                      'window["settle_after"] > now:\n',
                      '    if _window_terminal(window) or window["settle_after"] > now:\n')],
                    [('    if _window_terminal(window) or _window_unarmed(window) or '
                      'window["settle_after"] > now:\n',
                      '    # Inert twin at the same window protection.\n'
                      '    if _window_terminal(window) or _window_unarmed(window) or '
                      'window["settle_after"] > now:\n')],
                    'test_match_report_window.py',
                    'fix2_m1_unarmed_guards and [settle]'),
 'FIX2.M1.ARM': ('FIX2',
                 'match_report_window.py',
                 [('    elif _window_unarmed(window):\n', '    elif False:\n')],
                 [('    elif _window_unarmed(window):\n',
                   '    # Inert twin at the same window protection.\n'
                   '    elif _window_unarmed(window):\n')],
                 'test_match_report_window.py',
                 'fix2_m1_unarmed_guards and [arm]'),
 'FIX2.M1.RECEIVE': ('FIX2',
                     'match_report_window.py',
                     [('    if not held and not _window_unarmed(window) and window["settle_after"] '
                       '<= now:\n',
                       '    if not held and window["settle_after"] <= now:\n')],
                     [('    if not held and not _window_unarmed(window) and window["settle_after"] '
                       '<= now:\n',
                       '    # Inert twin at the same window protection.\n'
                       '    if not held and not _window_unarmed(window) and window["settle_after"] '
                       '<= now:\n')],
                     'test_match_report_window.py',
                     'fix2_m1_unarmed_guards and [receive]'),
 'FIX2.M1.DEADLINE': ('FIX2',
                      'match_report_window.py',
                      [('    if entered_at is not None or released or _window_unarmed(window):\n',
                        '    if True:\n')],
                      [('    if entered_at is not None or released or _window_unarmed(window):\n',
                        '    # Inert twin at the same window protection.\n'
                        '    if entered_at is not None or released or _window_unarmed(window):\n')],
                      'test_match_report_window.py',
                      'fix2_m1_deadline_preservation_and_causal_advance'),
 'FIX2.M1.CAUSAL': ('FIX2',
                    'match_report_window.py',
                    [('    if entered_at is not None or released or _window_unarmed(window):\n',
                      '    if released or _window_unarmed(window):\n')],
                    [('    if entered_at is not None or released or _window_unarmed(window):\n',
                      '    # Inert twin at the same window protection.\n'
                      '    if entered_at is not None or released or _window_unarmed(window):\n')],
                    'test_match_report_window.py',
                    'fix2_m1_deadline_preservation_and_causal_advance')})

def _plant(src_text, edits, mid, kind):
    out = src_text
    crlf = "\r\n" in src_text
    for anchor, repl in edits:
        if crlf:
            # A checkout with CRLF line ends (core.autocrlf): the registry is
            # written in LF, so its anchors and texts take the file's ends.
            anchor, repl = anchor.replace("\n", "\r\n"), repl.replace("\n", "\r\n")
        n = out.count(anchor)
        if n != 1:
            raise SystemExit(f"REFUSED {mid} {kind}: anchor occurs {n} times: {anchor!r}")
        out = out.replace(anchor, repl)
    if out == src_text:
        raise SystemExit(f"REFUSED {mid} {kind}: the edit changed nothing")
    return out


def _write_copy(dest, module, text_out):
    os.makedirs(dest, exist_ok=False)
    if module.endswith(".sql"):
        with open(os.path.join(dest, module), "w", encoding="utf-8", newline="") as f:
            f.write(text_out)
        return
    for m in MODULES:
        p = os.path.join(API, m)
        if not os.path.exists(p):
            continue
        if m == module:
            with open(os.path.join(dest, m), "w", encoding="utf-8", newline="") as f:
                f.write(text_out)
        else:
            shutil.copyfile(p, os.path.join(dest, m))





# Exact constituents retain all parameters of the former broad selections.
_H4_WRITERS = ("ledger_final", "ledger_claim", "hold_open", "attempt", "mine",
               "claim", "claim_audit", "bind", "entered", "end")
BOUNDED_NODES = {
    mid: tuple("test_fix1_h4_each_hold_writer_guards_before_downstream_lock[" + writer + "]"
               for writer in _H4_WRITERS)
    for mid in ("MERGED.FIX1.H4.CLAIM_AUDIT", "MERGED.FIX1.H4.BIND", "MERGED.FIX1.H4.END")
}
BOUNDED_NODES["MERGED.FIX1.H4.SEEN"] = tuple(
    "test_fix1_h4_beat_deletion_orders_and_survivors[%s-%s-%s]" % (caller, order, mode)
    for caller in (0, 1) for order in ("deletion_first", "writer_first") for mode in ("team", "ovt"))


def combine_registry_runs(results):
    """Combine observations without changing the strict adverse classifier."""
    codes, runs = zip(*results)
    exceptional = next((code for code in codes if code not in (0, 1)), None)
    code = exceptional if exceptional is not None else int(any(codes))
    return code, {"collected": sum(r.get("collected", 0) for r in runs),
                  "collection_errors": [e for r in runs for e in r.get("collection_errors", [])],
                  "reports": [e for r in runs for e in r.get("reports", [])],
                  "constituents": len(runs)}


def _run(dest, module, test_file, sel, mid=None):
    import tempfile
    import test_srv_registry_seat as seat

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("MATCH_HOLD_SRC", None)
    for variable in SQL_ENV.values():
        env.pop(variable, None)
    if module.endswith(".sql"):
        env[SQL_ENV[module]] = os.path.join(dest, module)
    else:
        env["MATCH_HOLD_SRC"] = dest
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    outputs, results = [], []
    for index, node in enumerate(BOUNDED_NODES.get(mid, (None,))):
        report = os.path.abspath(os.path.join(dest, "observations-%02d.json" % index))
        env["SRV_REGISTRY_REPORT"] = report
        env["SRV_REGISTRY_POOL_EVENTS"] = report + ".pool.jsonl"
        basetemp = os.path.abspath(tempfile.mkdtemp(prefix="pytest_", dir=dest))
        cmd = [sys.executable, "-B", "-m", "pytest", "--rootdir", BACKEND,
               "-p", "no:cacheprovider", "-p", "test_srv_registry_seat",
               "--basetemp", basetemp, "-q", "-rf"]
        target = os.path.join(TESTS, test_file)
        cmd += [target + "::" + node] if node else [target, "-k", "census or (" + sel + ")"]
        seat._read_seat_hold()
        lifecycle = seat._registry_database_begin(test_file, env, mid or sel)
        try:
            p = seat._run_registry_child(cmd, cwd=TESTS, env=env)
        except subprocess.TimeoutExpired:
            print("REGISTRY TIMEOUT " + json.dumps(seat._phase_evidence(report), sort_keys=True), flush=True)
            raise
        phases = seat._phase_evidence(report)
        child_output = p.stdout + p.stderr
        try:
            seat._registry_database_finish(test_file, env, lifecycle)
        except BaseException as error:
            print("REGISTRY VERIFICATION " + json.dumps({"phase": "database_finish",
                  "phases": phases, "database_unverified": True,
                  "exception": type(error).__name__}, sort_keys=True), flush=True)
            print(child_output, flush=True)
            raise
        outputs.append("REGISTRY PHASES " + json.dumps(phases, sort_keys=True)
                       + "\n" + child_output)
        results.append((p.returncode, read_registry_run(report)))
    code, observed = combine_registry_runs(results)
    out = "\n".join(outputs)
    failed = sorted(set(re.findall(r"^FAILED \S+::(\w+)", out, re.M)))
    return code, failed, out, observed


import ast
import json
from _pytest.mark.expression import Expression

RUNNER_ASSERTIONS = {'FIX1B.R1.SAVEPOINT': ({'file': 'test_match_hold_reports_pg.py',
                         'function': 'test_merged_fix1b_r1_permanent_then_valid_held_reports',
                         'expression': "result.get('released') == 2 and result.get('held_retry', 0) == 0",
                         'message_source': "('R1 one finishing pass', mode, result)",
                         'tag': 'R1 one finishing pass',
                         'occurrences': 1,
                         'ordinal': 0},
                        {'file': 'test_match_hold_reports_pg.py',
                         'function': 'test_merged_fix1b_r1_permanent_then_valid_held_reports',
                         'expression': 'kept_changes == [(str(s.pid(bad_i)), 1)]',
                         'message_source': "('R1 A kept once alone', mode, kept_changes)",
                         'tag': 'R1 A kept once alone',
                         'occurrences': 1,
                         'ordinal': 0},
                        {'file': 'test_match_hold_reports_pg.py',
                         'function': 'test_merged_fix1b_r1_permanent_then_valid_held_reports',
                         'expression': "after['journal'][s.steam(bad_i)]['state'] == 'kept' and "
                                       "after['journal'][s.steam(good_i)]['state'] == 'settled'",
                         'message_source': "('R1 exact disposition', mode, after)",
                         'tag': 'R1 exact disposition',
                         'occurrences': 1,
                         'ordinal': 0},
                        {'file': 'test_match_hold_reports_pg.py',
                         'function': 'test_merged_fix1b_r1_permanent_then_valid_held_reports',
                         'expression': "window['opened_at'] == before['window']['opened_at'] and "
                                       "(window['settle_after'] - entered_at).total_seconds() == 30 and "
                                       "(window['settled_at'] is not None) and (window['superseded_at'] is None) "
                                       "and (window['settled_reporter_id'] == s.pid(good_i)) and "
                                       "(window['settled_cls'] == 'c')",
                         'message_source': "('R1 release survives only settlement rolls back', mode, window)",
                         'tag': 'R1 release survives only settlement rolls back',
                         'occurrences': 1,
                         'ordinal': 0}),
 'F1.L2.BASELINE': ({'file': 'test_match_hold_migration_pg.py',
                     'function': 'test_l2_384_owned_metadata_round_trips',
                     'expression': '[r for r in restored if r[0] in shared] == baseline',
                     'message_source': "'L2 baseline differs'",
                     'tag': 'L2 baseline differs',
                     'occurrences': 1,
                     'ordinal': 0},),
 'F1.L2.INVERSE': ({'file': 'test_match_hold_migration_pg.py',
                    'function': 'test_l2_384_owned_metadata_round_trips',
                    'expression': "'ownership mismatch' in message",
                    'message_source': '(label, message)',
                    'tag': None,
                    'occurrences': 1,
                    'ordinal': 0},),
 'M5.10': ({'file': 'test_match_hold_reports_pg.py',
            'function': '_held_game_over',
            'expression': "r.status_code == 202 and r.json().get('state') == 'held'",
            'message_source': "('T5.7 held', mode, i, r.status_code, r.text[:300])",
            'tag': 'T5.7 held',
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_reports_pg.py',
            'function': 'test_t5_7_held_game_over_settles_at_entry_and_is_superseded_at_lapse',
            'expression': "(len(rec), w['settled_cls'], [k for k, v in j.items() if v[1] == 'settled']) == (1, 'c', "
                          '[low])',
            'message_source': "('T5.7 settled at entry', mode, rec, w and dict(w), j)",
            'tag': 'T5.7 settled at entry',
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_reports_pg.py',
            'function': 'test_t5_7_held_game_over_settles_at_entry_and_is_superseded_at_lapse',
            'expression': "(w['superseded_at'] is not None, w['settled_at'], sorted((v[1] for v in j.values())), await "
                          "recorded(env, mode, s)) == (True, None, ['superseded'] * len(present), [])",
            'message_source': "('T5.7 superseded at x', mode, w and dict(w), j)",
            'tag': 'T5.7 superseded at x',
            'occurrences': 1,
            'ordinal': 0}),
 'MERGED.FIX1.H2.CAUSAL': ({'file': 'test_match_hold_reports_pg.py',
                            'function': 'test_merged_fix1_h2_causal_lapse_and_delayed_receipt',
                            'expression': "(w['superseded_at'] is not None, w['settled_at'], sorted((v[1] for v "
                                          'in j.values())), await recorded(env, mode, s)) == (True, None, '
                                          "['superseded', 'superseded'], [])",
                            'message_source': "('H2 causal lapse', mode, w and dict(w), j)",
                            'tag': 'H2 causal lapse',
                            'occurrences': 1,
                            'ordinal': 0},
                           {'file': 'test_match_hold_reports_pg.py',
                            'function': 'test_merged_fix1_h2_causal_lapse_and_delayed_receipt',
                            'expression': "prior['superseded_at'] is not None and journal == {}",
                            'message_source': "('H2 no-journal closure', mode, prior, journal)",
                            'tag': 'H2 no-journal closure',
                            'occurrences': 1,
                            'ordinal': 0},
                           {'file': 'test_match_hold_reports_pg.py',
                            'function': 'test_merged_fix1_h2_causal_lapse_and_delayed_receipt',
                            'expression': "response.status_code == 202 and response.json().get('state') == "
                                          "'superseded'",
                            'message_source': "('H2 delayed first', mode, janitor_first, response.status_code, "
                                              'response.text)',
                            'tag': 'H2 delayed first',
                            'occurrences': 1,
                            'ordinal': 0}),
 'MERGED.FIX1.H2.EXPIRY': ({'file': 'test_match_hold_reports_pg.py',
                            'function': 'test_merged_fix1_h2_held_receipts_outlive_first_receipt',
                            'expression': "first.json().get('state') == second.json().get('state') == 'held'",
                            'message_source': "('H2 live hold keeps receipts eligible', mode, first.text, "
                                              'second.text)',
                            'tag': 'H2 live hold keeps receipts eligible',
                            'occurrences': 1,
                            'ordinal': 0},),
 'MERGED.FIX1.H1.RECEIPT': ({'file': 'test_match_hold_reports_pg.py',
                             'function': 'test_fix1_h1_racing_duplicate_does_not_spend_next_reporter',
                             'expression': 'r.status_code == 200 and w is None and (not j)',
                             'message_source': "('F1.H1 new settlement only', mode, r.status_code, r.text[:300], "
                                               'w, j)',
                             'tag': 'F1.H1 new settlement only',
                             'occurrences': 1,
                             'ordinal': 0},),
 'F1.H1': ({'file': 'test_match_hold_pg.py',
            'function': 'test_h1_real_helper_soft_fail_paths_require_verified_session',
            'expression': 'response is not None',
            'message_source': "('FIX3 H1 unauthorized request must complete', method, path)",
            'tag': 'FIX3 H1 unauthorized request must complete',
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_h1_real_helper_soft_fail_paths_require_verified_session',
            'expression': 'response.status_code == 401',
            'message_source': None,
            'tag': None,
            'occurrences': 1,
            'ordinal': 0}),
 'F1.H2.OMIT': ({'file': 'test_match_hold_pg.py',
                 'function': 'test_h2_verifier_lifecycle_on_claim_state_bind_and_entry',
                 'expression': "all(('verifier' in view for view in (state, by_room)))",
                 'message_source': "('FIX3 H2 every view names verifier', state, by_room)",
                 'tag': 'FIX3 H2 every view names verifier',
                 'occurrences': 1,
                 'ordinal': 0},
                {'file': 'test_match_hold_pg.py',
                 'function': 'test_h2_verifier_lifecycle_on_claim_state_bind_and_entry',
                 'expression': "'verifier' in first",
                 'message_source': "('FIX3 H2 answer names verifier', 'first')",
                 'tag': 'FIX3 H2 answer names verifier',
                 'occurrences': 1,
                 'ordinal': 0},
                {'file': 'test_match_hold_pg.py',
                 'function': 'test_h2_verifier_lifecycle_on_claim_state_bind_and_entry',
                 'expression': "'verifier' in second",
                 'message_source': "('FIX3 H2 answer names verifier', 'second')",
                 'tag': 'FIX3 H2 answer names verifier',
                 'occurrences': 1,
                 'ordinal': 0},
                {'file': 'test_match_hold_pg.py',
                 'function': 'test_h2_verifier_lifecycle_on_claim_state_bind_and_entry',
                 'expression': "'verifier' in bound",
                 'message_source': "('FIX3 H2 answer names verifier', 'bound')",
                 'tag': 'FIX3 H2 answer names verifier',
                 'occurrences': 1,
                 'ordinal': 0},
                {'file': 'test_match_hold_pg.py',
                 'function': 'test_h2_verifier_lifecycle_on_claim_state_bind_and_entry',
                 'expression': "'verifier' in accepted",
                 'message_source': "('FIX3 H2 answer names verifier', 'accepted')",
                 'tag': 'FIX3 H2 answer names verifier',
                 'occurrences': 1,
                 'ordinal': 0},
                {'file': 'test_match_hold_pg.py',
                 'function': 'test_h2_verifier_lifecycle_on_claim_state_bind_and_entry',
                 'expression': "[v['verifier'] for v in before] == [None, None]",
                 'message_source': None,
                 'tag': None,
                 'occurrences': 1,
                 'ordinal': 0}),
 'F1.H2.STALE': ({'file': 'test_match_hold_pg.py',
                  'function': 'test_h2_verifier_lifecycle_on_claim_state_bind_and_entry',
                  'expression': "first['verifier'] == first_hash",
                  'message_source': None,
                  'tag': None,
                  'occurrences': 1,
                  'ordinal': 0},
                 {'file': 'test_match_hold_pg.py',
                  'function': 'test_h2_verifier_lifecycle_on_claim_state_bind_and_entry',
                  'expression': "second['verifier'] == second_hash and second_hash != first_hash",
                  'message_source': None,
                  'tag': None,
                  'occurrences': 1,
                  'ordinal': 0}),
 'F1.H3.GATE': ({'file': 'test_match_hold_admission_gate_pg.py',
                 'function': 'test_h3_hold_open_and_claim_reject_another_live_commitment',
                 'expression': "refused.status_code == 200 and refused.json() == {'status': 'refused', 'reason': "
                               "'other_mode'}",
                 'message_source': None,
                 'tag': None,
                 'occurrences': 1,
                 'ordinal': 0},),
 'F1.H3.RECHECK': ({'file': 'test_match_hold_admission_gate_pg.py',
                    'function': 'test_h3_hold_open_and_claim_reject_another_live_commitment',
                    'expression': "claimed == {'status': 'refused', 'reason': 'other_mode'}",
                    'message_source': None,
                    'tag': None,
                    'occurrences': 1,
                    'ordinal': 0},),
 'F1.M3': ({'file': 'test_match_hold_pg.py',
            'function': 'test_m3_due_prior_game_closes_before_later_open',
            'expression': "'status' in later and later['status'] == 'opened'",
            'message_source': "('FIX3 M3 due predecessor permits open', later)",
            'tag': 'FIX3 M3 due predecessor permits open',
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_m3_due_prior_game_closes_before_later_open',
            'expression': "'repeat' in later",
            'message_source': "('FIX3 M3 opened answer names repeat', later)",
            'tag': 'FIX3 M3 opened answer names repeat',
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_m3_due_prior_game_closes_before_later_open',
            'expression': "'status' in after_bound",
            'message_source': "('FIX3 M3 expired bound answer names status', after_bound)",
            'tag': 'FIX3 M3 expired bound answer names status',
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_m3_bind_actor_conflict_uses_live_deadlines',
            'expression': "'status' in answer",
            'message_source': "('FIX3 M3 bind answer names status', answer)",
            'tag': 'FIX3 M3 bind answer names status',
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_m3_due_prior_game_closes_before_later_open',
            'expression': "(later['status'], later['repeat']) == ('opened', False)",
            'message_source': 'later',
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_m3_due_prior_game_closes_before_later_open',
            'expression': "after_bound['status'] == 'opened'",
            'message_source': 'after_bound',
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_m3_bind_actor_conflict_uses_live_deadlines',
            'expression': "answer['status'] == 'bound'",
            'message_source': 'answer',
            'tag': None,
            'occurrences': 1,
            'ordinal': 0}),
 'F1.M2.CHECKOUT': ({'file': 'test_match_hold_pg.py',
                     'function': 'test_m2_deadline_covers_checkout_before_any_route_work',
                     'expression': 'task in completed',
                     'message_source': "'FIX3 M2 checkout completes before watchdog'",
                     'tag': 'FIX3 M2 checkout completes before watchdog',
                     'occurrences': 1,
                     'ordinal': 0},
                    {'file': 'test_match_hold_pg.py',
                     'function': 'test_m2_deadline_covers_checkout_before_any_route_work',
                     'expression': 'response.status_code == 503',
                     'message_source': None,
                     'tag': None,
                     'occurrences': 1,
                     'ordinal': 0}),
 'F1.M2.LOCK': ({'file': 'test_match_report_window.py',
                 'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
                 'expression': 'task in completed',
                 'message_source': "('FIX3 M2 window completes before watchdog', operation)",
                 'tag': 'FIX3 M2 window completes before watchdog',
                 'occurrences': 1,
                 'ordinal': 0},
                {'file': 'test_match_report_window.py',
                 'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
                 'expression': 'caught is not None',
                 'message_source': "('FIX3 M2 blocked window must refuse', operation)",
                 'tag': 'FIX3 M2 blocked window must refuse',
                 'occurrences': 1,
                 'ordinal': 0},
                {'file': 'test_match_report_window.py',
                 'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
                 'expression': "(caught.status_code, caught.detail) == (503, 'database_deadline')",
                 'message_source': None,
                 'tag': None,
                 'occurrences': 1,
                 'ordinal': 0},
                {'file': 'test_match_report_window.py',
                 'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
                 'expression': '4.0 <= elapsed < 7.0',
                 'message_source': '(operation, elapsed)',
                 'tag': None,
                 'occurrences': 1,
                 'ordinal': 0},
                {'file': 'test_match_report_window.py',
                 'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
                 'expression': 'setups == 1',
                 'message_source': None,
                 'tag': None,
                 'occurrences': 1,
                 'ordinal': 0}),
 'F1.H4': ({'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "late == {'status': 'duplicate'}",
            'message_source': None,
            'tag': None,
            'occurrences': 2,
            'ordinal': 1},),
 'F1.H6': ({'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "settled_payload == {'proof': 'A'}",
            'message_source': None,
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "(stored['proof'], stored['state']) == ('A', 'settled')",
            'message_source': None,
            'tag': None,
            'occurrences': 1,
            'ordinal': 0}),
 'F1.M5': ({'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "answer == {'status': 'settled', 'cls': 'c'}",
            'message_source': None,
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},),
 'F1.M4': ({'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': 'len(settled) == n + 1',
            'message_source': None,
            'tag': None,
            'occurrences': 2,
            'ordinal': 0},
           {'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "await rec(room, g, 1) == {'status': 'settled', 'cls': 'c'}",
            'message_source': None,
            'tag': None,
            'occurrences': 2,
            'ordinal': 0},
           {'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "await rec(room, g, 1) == {'status': 'settled', 'cls': 'c'}",
            'message_source': None,
            'tag': None,
            'occurrences': 2,
            'ordinal': 1}),
 'F1.H5': ({'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "await mrw.settle_window(db, mode='team', room=room, game_id=g, now=now + "
                          'timedelta(seconds=31), settle=stub) is None',
            'message_source': None,
            'tag': None,
            'occurrences': 3,
            'ordinal': 2},
           {'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "await mrw.release_held(db, mode='team', room=room, game_id=g, now=now, settle=stub) == "
                          '0',
            'message_source': None,
            'tag': None,
            'occurrences': 2,
            'ordinal': 1},
           {'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "terminal['settled_at'] is None",
            'message_source': None,
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_report_window.py',
            'function': 'test_t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c',
            'expression': "late == {'status': 'duplicate'}",
            'message_source': None,
            'tag': None,
            'occurrences': 2,
            'ordinal': 0}),
 'F1.M8.LITERAL.DEFAULT': ({'file': 'test_match_hold_migration_pg.py',
                            'function': 'test_383_normalizers_preserve_literal_bytes',
                            'expression': 'actual == expected',
                            'message_source': "('M3 literal ' + alias, value, actual, expected)",
                            'tag': None,
                            'occurrences': 1,
                            'ordinal': 0},),
 'F1.M8.LITERAL.CONSTRAINT': ({'file': 'test_match_hold_migration_pg.py',
                               'function': 'test_383_normalizers_preserve_literal_bytes',
                               'expression': 'actual == expected',
                               'message_source': "('M3 literal ' + alias, value, actual, expected)",
                               'tag': None,
                               'occurrences': 1,
                               'ordinal': 0},),
 'F1.M8.LITERAL.INDEX': ({'file': 'test_match_hold_migration_pg.py',
                          'function': 'test_383_normalizers_preserve_literal_bytes',
                          'expression': 'actual == expected',
                          'message_source': "('M3 literal ' + alias, value, actual, expected)",
                          'tag': None,
                          'occurrences': 1,
                          'ordinal': 0},),
 'F1.M8.COL': ({'file': 'test_match_hold_migration_pg.py',
                'function': 'test_383_proof_block_raises_on_a_gap',
                'expression': 'label in msg',
                'message_source': '(label, msg)',
                'tag': None,
                'occurrences': 1,
                'ordinal': 0},),
 'F1.M8.DEFAULT': ({'file': 'test_match_hold_migration_pg.py',
                    'function': 'test_383_proof_block_raises_on_a_gap',
                    'expression': 'label in msg',
                    'message_source': '(label, msg)',
                    'tag': None,
                    'occurrences': 1,
                    'ordinal': 0},),
 'F1.M8.CONSTRAINT': ({'file': 'test_match_hold_migration_pg.py',
                       'function': 'test_383_proof_block_raises_on_a_gap',
                       'expression': 'label in msg',
                       'message_source': '(label, msg)',
                       'tag': None,
                       'occurrences': 1,
                       'ordinal': 0},),
 'F1.M8.INDEX': ({'file': 'test_match_hold_migration_pg.py',
                  'function': 'test_383_proof_block_raises_on_a_gap',
                  'expression': 'label in msg',
                  'message_source': '(label, msg)',
                  'tag': None,
                  'occurrences': 1,
                  'ordinal': 0},),
 'F1.M1': ({'file': 'test_match_hold_pg.py',
            'function': 'test_m1_hold_open_requires_exact_roster_slot_and_team',
            'expression': "swapped == {'status': 'refused', 'reason': 'not_member'}",
            'message_source': 'swapped',
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},),
 'F1.M6.TUPLE': ({'file': 'test_match_hold_pg.py',
                  'function': 'test_m6_open_request_id_replays_only_its_original_tuple',
                  'expression': "cross_game == {'status': 'refused', 'reason': 'request_mismatch'}",
                  'message_source': None,
                  'tag': None,
                  'occurrences': 1,
                  'ordinal': 0},
                 {'file': 'test_match_hold_pg.py',
                  'function': 'test_m6_open_request_id_replays_only_its_original_tuple',
                  'expression': "cross_seat == {'status': 'refused', 'reason': 'request_mismatch'}",
                  'message_source': None,
                  'tag': None,
                  'occurrences': 1,
                  'ordinal': 0}),
 'F1.M6.SIG': ({'file': 'test_match_hold_pg.py',
                'function': 'test_m6_bad_signature_records_refusal_before_403',
                'expression': 'row is not None',
                'message_source': "'FIX3 M6 signature refusal has ledger row'",
                'tag': 'FIX3 M6 signature refusal has ledger row',
                'occurrences': 1,
                'ordinal': 0},
               {'file': 'test_match_hold_pg.py',
                'function': 'test_m6_bad_signature_records_refusal_before_403',
                'expression': "(row['room_name'], row['game_id'], row['held_player_id'], row['opener_player_id'], "
                              "row['outcome'], row['reason'], row['hold_id']) == (s.room, uuid.UUID(g), None, s.pid(0), "
                              "'refused', 'bad_signature', None)",
                'message_source': None,
                'tag': None,
                'occurrences': 1,
                'ordinal': 0}),
 'F1.M7': ({'file': 'test_match_hold_pg.py',
            'function': 'test_m7_team_open_requires_both_point_snapshots',
            'expression': "refused == {'status': 'refused', 'reason': 'missing_points'}",
            'message_source': 'refused',
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},),
 'F1.L1': ({'file': 'test_match_hold_pg.py',
            'function': 'test_t3_7_bind_identity_and_entry',
            'expression': "kinds == [('bind', 'refused', 'not_claimed'), ('claim', 'ok', None), ('bind', "
                          "'refused', 'not_yours'), ('bind', 'refused', 'uncorroborated'), ('bind', 'refused', "
                          "'actor_identity_mismatch'), ('bind', 'refused', 'uncorroborated'), ('bind', 'ok', "
                          "None), ('bind', 'ok', None), ('bind', 'refused', 'already_bound'), ('entered', "
                          "'refused', 'not_yours'), ('entered', 'refused', 'actor_mismatch'), ('entered', "
                          "'refused', 'game_mismatch'), ('entered', 'ok', None), ('entered', 'refused', "
                          "'hold_lapsed'), ('claim', 'refused', 'hold_lapsed')]",
            'message_source': 'kinds',
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},),
 'M1.7': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t1_4_game_id_chain_rematch_delayed_and_handover',
           'expression': "b['game_id'] != a['game_id'] and b['seq'] == 2 and b['minted']",
           'message_source': 'b',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t1_4_game_id_chain_rematch_delayed_and_handover',
           'expression': "(hand['game_id'], hand['minted']) == (b['game_id'], False)",
           'message_source': 'hand',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t1_4_game_id_chain_rematch_delayed_and_handover',
           'expression': "(late['game_id'], late['minted']) == (b['game_id'], False)",
           'message_source': 'late',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0}),
 'M1.8': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t1_4_game_id_chain_rematch_delayed_and_handover',
           'expression': 'False',
           'message_source': "'FIX3 M1.8 repeat first game returns its existing row'",
           'tag': 'FIX3 M1.8 repeat first game returns its existing row',
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t1_4_game_id_chain_rematch_delayed_and_handover',
           'expression': "(again['game_id'], again['minted']) == (a['game_id'], False)",
           'message_source': 'again',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0}),
 'M1.L1': ({'file': 'test_match_hold_pg.py',
            'function': 'test_hold_latch_helper',
            'expression': "await latch(env, s, s.room + '_r') == (False, s.room + '_r')",
            'message_source': None,
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_hold_latch_helper',
            'expression': "row['hold_v2'] is flag",
            'message_source': None,
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_hold_latch_helper',
            'expression': 'await latch(env, t, t.room) == (False, t.room)',
            'message_source': "'a token prefix passed'",
            'tag': 'a token prefix passed',
            'occurrences': 1,
            'ordinal': 0}),
 'M1.L2': ({'file': 'test_match_hold_pg.py',
            'function': 'test_hold_latch_helper',
            'expression': 'await latch(env, s, s.room) == (True, s.room)',
            'message_source': "'a written flag moved'",
            'tag': 'a written flag moved',
            'occurrences': 1,
            'ordinal': 0},),
 'M2.1': ({'file': 'test_match_hold_migration_pg.py',
           'function': 'test_383_first_apply_rerun_defaults_and_constraints',
           'expression': "await refused(hold % ('', ''), 'team_pre383', tsid, g1, pids[0], 2, pids[1])",
           'message_source': "'a second hold of one seat in one game'",
           'tag': 'a second hold of one seat in one game',
           'occurrences': 1,
           'ordinal': 0},),
 'M2.2': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t2_1_open_anchor_idempotent_and_refusals',
           'expression': 'transaction_at < lower <= observed <= upper',
           'message_source': "('FIX3 M2 context clock follows PostgreSQL wait', transaction_at, lower, observed, "
                             'upper)',
           'tag': 'FIX3 M2 context clock follows PostgreSQL wait',
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t2_1_open_anchor_idempotent_and_refusals',
           'expression': "released <= h['held_at'] <= t1 and t0 <= h['held_at']",
           'message_source': "(released, h['held_at'])",
           'tag': None,
           'occurrences': 1,
           'ordinal': 0}),
 'M2.3': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t2_2_closure_once_for_every_reason',
           'expression': "h['held_until'] == until_before",
           'message_source': "'the sweep moved held_until'",
           'tag': 'the sweep moved held_until',
           'occurrences': 1,
           'ordinal': 0},),
 'M2.4': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t2_1_open_anchor_idempotent_and_refusals',
           'expression': "h['held_anchor_at'] == pres",
           'message_source': "(h['held_anchor_at'], pres)",
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},),
 'M2.5': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t2_1_open_anchor_idempotent_and_refusals',
           'expression': 'transaction_at < lower <= observed <= upper',
           'message_source': "('FIX3 M2 context clock follows PostgreSQL wait', transaction_at, lower, observed, "
                             'upper)',
           'tag': 'FIX3 M2 context clock follows PostgreSQL wait',
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t2_1_open_anchor_idempotent_and_refusals',
           'expression': 'await sweep(env) == {}',
           'message_source': None,
           'tag': None,
           'occurrences': 2,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t2_1_open_anchor_idempotent_and_refusals',
           'expression': "released <= h['held_at'] <= t1 and t0 <= h['held_at']",
           'message_source': "(released, h['held_at'])",
           'tag': None,
           'occurrences': 1,
           'ordinal': 0}),
 'M2.6': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t2_1_open_anchor_idempotent_and_refusals',
           'expression': "'status' in j and j['status'] == 'refused'",
           'message_source': "('FIX3 M2.6 open must refuse', j)",
           'tag': 'FIX3 M2.6 open must refuse',
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t2_1_open_anchor_idempotent_and_refusals',
           'expression': "'reason' in j",
           'message_source': "('FIX3 M2.6 refusal names reason', j)",
           'tag': 'FIX3 M2.6 refusal names reason',
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t2_1_open_anchor_idempotent_and_refusals',
           'expression': "await refusal(await open_hold(env, nc, 1, 0, g1)) == 'not_current_game'",
           'message_source': None,
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t2_8_open_attempt_rows',
           'expression': "got == {'req-unknown-g1': ('refused', 'not_current_game', False), 'req-unknown-g2': "
                         "('refused', 'not_current_game', False), 'req-stale-g001': ('refused', 'not_current_game', "
                         "False), 'req-opened-001': ('opened', None, True), 'req-repeat-001': ('repeat', None, True)}",
           'message_source': 'got',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0}),
 'M2.7': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t2_2_closure_once_for_every_reason',
           'expression': "h is not None and h['closed_at'] is not None",
           'message_source': "('FIX3 M2.7 closure persisted', reason)",
           'tag': 'FIX3 M2.7 closure persisted',
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t2_2_closure_once_for_every_reason',
           'expression': "h is not None and h['closed_at'] is not None",
           'message_source': "('FIX3 M2.7 swept closure persisted', hid)",
           'tag': 'FIX3 M2.7 swept closure persisted',
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t2_2_closure_once_for_every_reason',
           'expression': "(h['closed_reason'], h['closed_at'].isoformat()) == (reason, j['closed_at'])",
           'message_source': None,
           'tag': None,
           'occurrences': 1,
           'ordinal': 0}),
 'M2.14': ({'file': 'test_match_hold_pg.py',
            'function': 'test_t2_8_open_attempt_rows',
            'expression': "got == {'req-unknown-g1': ('refused', 'not_current_game', False), 'req-unknown-g2': "
                          "('refused', 'not_current_game', False), 'req-stale-g001': ('refused', "
                          "'not_current_game', False), 'req-opened-001': ('opened', None, True), "
                          "'req-repeat-001': ('repeat', None, True)}",
            'message_source': 'got',
            'tag': None,
            'occurrences': 1,
            'ordinal': 0},),
 'M3.1': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t3_1_claim_refusals_grant_and_rotation',
           'expression': "await claim(env, lp, 1, hidl) == {'status': 'refused', 'reason': 'hold_lapsed'}",
           'message_source': None,
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t3_1_claim_refusals_grant_and_rotation',
           'expression': "await claim(env, e, 1, hide) == {'status': 'refused', 'reason': 'hold_lapsed'}",
           'message_source': None,
           'tag': None,
           'occurrences': 1,
           'ordinal': 0}),
 'M3.2': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t3_1_claim_refusals_grant_and_rotation',
           'expression': "h2['verifier'] == _h.sha256(c2['token'].encode()).hexdigest()",
           'message_source': None,
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},),
 'M3.3': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t3_1_claim_refusals_grant_and_rotation',
           'expression': "await claim(env, hs, 1, hidh) == {'status': 'refused', 'reason': 'other_mode'}",
           'message_source': None,
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},),
 'M3.18': ({'file': 'test_match_hold_pg.py',
            'function': 'test_t3_7_bind_identity_and_entry',
            'expression': "await bind(env, s, 1, hid, 21) == {'status': 'refused', 'reason': 'uncorroborated'}",
            'message_source': None,
            'tag': None,
            'occurrences': 2,
            'ordinal': 0},
           {'file': 'test_match_hold_pg.py',
            'function': 'test_t3_7_bind_identity_and_entry',
            'expression': "await bind(env, s, 1, hid, 21) == {'status': 'refused', 'reason': 'uncorroborated'}",
            'message_source': None,
            'tag': None,
            'occurrences': 2,
            'ordinal': 1}),
 'M5.4': ({'file': 'test_match_report_window.py',
           'function': 'test_t5_3_overlap_per_anchor_sweep_end_relock_and_newer_anchor',
           'expression': 'mrw.anchor_fresh(newer, old, now=at(m), window=W30) == mrw.anchor_fresh(newer, [], '
                         'now=at(m), window=W30)',
           'message_source': 'm',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_report_window.py',
           'function': 'test_t5_3_overlap_per_anchor_sweep_end_relock_and_newer_anchor',
           'expression': 'mrw.held_overlap([straddle], newer, at(40)) == timedelta(seconds=60)',
           'message_source': None,
           'tag': None,
           'occurrences': 1,
           'ordinal': 0}),
 'M5.5': ({'file': 'test_match_report_window.py',
           'function': 'test_t5_3_application_skew_and_long_transaction',
           'expression': 'got == manual',
           'message_source': '(row, m)',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},),
 'M5.6': ({'file': 'test_match_report_window.py',
           'function': 'test_t5_4_matrix_every_class_assignment_both_modes',
           'expression': "(got['reporter_steam'], got['cls']) == (seats[want][1], classes[want])",
           'message_source': '(classes, order, got)',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},),
 'M5.7': ({'file': 'test_match_report_window.py',
           'function': 'test_t5_4_matrix_every_class_assignment_both_modes',
           'expression': 'len(settled) == before + 1',
           'message_source': '(classes, order)',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_report_window.py',
           'function': 'test_t5_4_matrix_every_class_assignment_both_modes',
           'expression': "(got['reporter_steam'], got['cls']) == (seats[want][1], classes[want])",
           'message_source': '(classes, order, got)',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0}),
 'M6.1': ({'file': 'test_match_hold_pg.py',
           'function': 'test_t6_1_attempt_rows_numbered_and_rolled_back_with_their_action',
           'expression': "await attempts(env, hid) == [(1, 'offered', 'ok', None), (2, 'claim', 'ok', None), (3, "
                         "'bind', 'refused', 'uncorroborated'), (4, 'bind', 'ok', None), (5, 'entered', 'ok', "
                         'None)]',
           'message_source': None,
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t6_1_attempt_rows_numbered_and_rolled_back_with_their_action',
           'expression': "(h['claimed_at'], h['verifier']) == (None, None)",
           'message_source': 'dict(h)',
           'tag': None,
           'occurrences': 1,
           'ordinal': 0},
          {'file': 'test_match_hold_pg.py',
           'function': 'test_t6_1_attempt_rows_numbered_and_rolled_back_with_their_action',
           'expression': 'await attempts(env, hidu) == []',
           'message_source': "'an attempt row outlived its rolled-back claim'",
           'tag': 'an attempt row outlived its rolled-back claim',
           'occurrences': 1,
           'ordinal': 0}),
 'MERGED.FIX1.H4.BEAT': ({'file': 'test_match_hold_deletion_pg.py',
                          'function': 'test_fix1_h4_beat_deletion_orders_and_survivors',
                          'expression': "'status' in answer and answer['status'] == 'refused'",
                          'message_source': "('FIX3 H4 deleted caller beat must refuse', answer)",
                          'tag': 'FIX3 H4 deleted caller beat must refuse',
                          'occurrences': 1,
                          'ordinal': 0},
                         {'file': 'test_match_hold_deletion_pg.py',
                          'function': 'test_fix1_h4_beat_deletion_orders_and_survivors',
                          'expression': 'not unlocked',
                          'message_source': "('FIX1 H4 beat guard', caller, steam == s.steam(victim))",
                          'tag': 'FIX1 H4 beat guard',
                          'occurrences': 1,
                          'ordinal': 0}),
 'MERGED.FIX1.H4.OPEN_FINAL': ({'file': 'test_match_hold_deletion_pg.py',
                                'function': 'test_fix1_h4_audit_revalidates_deleted_identity',
                                'expression': 'caught is not None',
                                'message_source': "('FIX3 H4 deleted audit must refuse', writer)",
                                'tag': 'FIX3 H4 deleted audit must refuse',
                                'occurrences': 1,
                                'ordinal': 0},
                               {'file': 'test_match_hold_deletion_pg.py',
                                'function': 'test_fix1_h4_audit_revalidates_deleted_identity',
                                'expression': 'caught.status_code == 404',
                                'message_source': "('FIX1 H4 stale audit', writer)",
                                'tag': 'FIX1 H4 stale audit',
                                'occurrences': 1,
                                'ordinal': 0},
                               {'file': 'test_match_hold_deletion_pg.py',
                                'function': 'test_fix1_h4_each_hold_writer_guards_before_downstream_lock',
                                'expression': 'not unlocked',
                                'message_source': "('FIX1 H4 writer guard', writer, i)",
                                'tag': 'FIX1 H4 writer guard',
                                'occurrences': 1,
                                'ordinal': 0}),
 'MERGED.FIX1.H4.OPEN_CLAIM': ({'file': 'test_match_hold_deletion_pg.py',
                                'function': 'test_fix1_h4_audit_revalidates_deleted_identity',
                                'expression': 'caught is not None',
                                'message_source': "('FIX3 H4 deleted audit must refuse', writer)",
                                'tag': 'FIX3 H4 deleted audit must refuse',
                                'occurrences': 1,
                                'ordinal': 0},
                               {'file': 'test_match_hold_deletion_pg.py',
                                'function': 'test_fix1_h4_audit_revalidates_deleted_identity',
                                'expression': 'caught.status_code == 404',
                                'message_source': "('FIX1 H4 stale audit', writer)",
                                'tag': 'FIX1 H4 stale audit',
                                'occurrences': 1,
                                'ordinal': 0},
                               {'file': 'test_match_hold_deletion_pg.py',
                                'function': 'test_fix1_h4_each_hold_writer_guards_before_downstream_lock',
                                'expression': 'not unlocked',
                                'message_source': "('FIX1 H4 writer guard', writer, i)",
                                'tag': 'FIX1 H4 writer guard',
                                'occurrences': 1,
                                'ordinal': 0}),
 'MERGED.FIX1.H4.ATTEMPT': ({'file': 'test_match_hold_deletion_pg.py',
                             'function': 'test_fix1_h4_each_hold_writer_guards_before_downstream_lock',
                             'expression': 'not unlocked',
                             'message_source': "('FIX1 H4 writer guard', writer, i)",
                             'tag': 'FIX1 H4 writer guard',
                             'occurrences': 1,
                             'ordinal': 0},),
 'MERGED.FIX1.H4.MINE': ({'file': 'test_match_hold_deletion_pg.py',
                          'function': 'test_fix1_h4_each_hold_writer_guards_before_downstream_lock',
                          'expression': 'not unlocked',
                          'message_source': "('FIX1 H4 writer guard', writer, i)",
                          'tag': 'FIX1 H4 writer guard',
                          'occurrences': 1,
                          'ordinal': 0},),
 'MERGED.FIX1.H4.CLAIM': ({'file': 'test_match_hold_deletion_pg.py',
                           'function': 'test_fix1_h4_each_hold_writer_guards_before_downstream_lock',
                           'expression': 'not unlocked',
                           'message_source': "('FIX1 H4 writer guard', writer, i)",
                           'tag': 'FIX1 H4 writer guard',
                           'occurrences': 1,
                           'ordinal': 0},),
 'MERGED.FIX1.H4.CLAIM_AUDIT': ({'file': 'test_match_hold_deletion_pg.py',
                                 'function': 'test_fix1_h4_each_hold_writer_guards_before_downstream_lock',
                                 'expression': 'not unlocked',
                                 'message_source': "('FIX1 H4 writer guard', writer, i)",
                                 'tag': 'FIX1 H4 writer guard',
                                 'occurrences': 1,
                                 'ordinal': 0},),
 'MERGED.FIX1.H4.BIND': ({'file': 'test_match_hold_deletion_pg.py',
                          'function': 'test_fix1_h4_each_hold_writer_guards_before_downstream_lock',
                          'expression': 'not unlocked',
                          'message_source': "('FIX1 H4 writer guard', writer, i)",
                          'tag': 'FIX1 H4 writer guard',
                          'occurrences': 1,
                          'ordinal': 0},),
 'MERGED.FIX1.H4.ENTERED': ({'file': 'test_match_hold_deletion_pg.py',
                             'function': 'test_fix1_h4_each_hold_writer_guards_before_downstream_lock',
                             'expression': 'not unlocked',
                             'message_source': "('FIX1 H4 writer guard', writer, i)",
                             'tag': 'FIX1 H4 writer guard',
                             'occurrences': 1,
                             'ordinal': 0},),
 'MERGED.FIX1.H4.END': ({'file': 'test_match_hold_deletion_pg.py',
                         'function': 'test_fix1_h4_each_hold_writer_guards_before_downstream_lock',
                         'expression': 'not unlocked',
                         'message_source': "('FIX1 H4 writer guard', writer, i)",
                         'tag': 'FIX1 H4 writer guard',
                         'occurrences': 1,
                         'ordinal': 0},),
 'MERGED.FIX1.H4.SEEN': ({'file': 'test_match_hold_deletion_pg.py',
                          'function': '_fix1_h4_clean',
                          'expression': 'found == ({}, {})',
                          'message_source': "('FIX1 H4 no identity', found)",
                          'tag': 'FIX1 H4 no identity',
                          'occurrences': 1,
                          'ordinal': 0},),
 'MERGED.FIX1.H4.WINDOW_RECEIVE': ({'file': 'test_match_hold_deletion_pg.py',
                                    'function': 'test_fix1_h4_report_writers_guard_before_their_first_lock',
                                    'expression': 'not unlocked',
                                    'message_source': "('FIX1 H4 report guard', writer, i)",
                                    'tag': 'FIX1 H4 report guard',
                                    'occurrences': 1,
                                    'ordinal': 0},),
 'MERGED.FIX1.H4.WINDOW_SETTLE': ({'file': 'test_match_hold_deletion_pg.py',
                                   'function': 'test_fix1_h4_report_writers_guard_before_their_first_lock',
                                   'expression': 'not unlocked',
                                   'message_source': "('FIX1 H4 report guard', writer, i)",
                                   'tag': 'FIX1 H4 report guard',
                                   'occurrences': 1,
                                   'ordinal': 0},),
 'MERGED.FIX1.H4.WINDOW_RELEASE': ({'file': 'test_match_hold_deletion_pg.py',
                                    'function': 'test_fix1_h4_report_writers_guard_before_their_first_lock',
                                    'expression': 'not unlocked',
                                    'message_source': "('FIX1 H4 report guard', writer, i)",
                                    'tag': 'FIX1 H4 report guard',
                                    'occurrences': 1,
                                    'ordinal': 0},),
 'MERGED.FIX1.H4.WINDOW_SUPERSEDE': ({'file': 'test_match_hold_deletion_pg.py',
                                      'function': 'test_fix1_h4_report_writers_guard_before_their_first_lock',
                                      'expression': 'not unlocked',
                                      'message_source': "('FIX1 H4 report guard', writer, i)",
                                      'tag': 'FIX1 H4 report guard',
                                      'occurrences': 1,
                                      'ordinal': 0},),
 'MERGED.FIX1.H4.WINDOW_FINISH': ({'file': 'test_match_hold_deletion_pg.py',
                                   'function': 'test_fix1_h4_report_writers_guard_before_their_first_lock',
                                   'expression': 'not unlocked',
                                   'message_source': "('FIX1 H4 report guard', writer, i)",
                                   'tag': 'FIX1 H4 report guard',
                                   'occurrences': 1,
                                   'ordinal': 0},),
 'MERGED.FIX1.H4.JOURNAL': ({'file': 'test_match_hold_deletion_pg.py',
                             'function': 'test_fix1_h4_report_writers_guard_before_their_first_lock',
                             'expression': 'not unlocked',
                             'message_source': "('FIX1 H4 report guard', writer, i)",
                             'tag': 'FIX1 H4 report guard',
                             'occurrences': 1,
                             'ordinal': 0},),
 'MERGED.FIX1.H4.MARK': ({'file': 'test_match_hold_deletion_pg.py',
                          'function': 'test_fix1_h4_report_writers_guard_before_their_first_lock',
                          'expression': 'not unlocked',
                          'message_source': "('FIX1 H4 report guard', writer, i)",
                          'tag': 'FIX1 H4 report guard',
                          'occurrences': 1,
                          'ordinal': 0},),
 'MERGED.FIX1.H4.TERMINAL_ATTRIBUTION': ({'file': 'test_match_hold_deletion_pg.py',
                                          'function': 'test_fix1_h4_terminal_release_preserves_cleared_attribution',
                                          'expression': 'False',
                                          'message_source': "'FIX3 H4 terminal must not rewrite attribution'",
                                          'tag': 'FIX3 H4 terminal must not rewrite attribution',
                                          'occurrences': 1,
                                          'ordinal': 0},
                                         {'file': 'test_match_hold_deletion_pg.py',
                                          'function': 'test_fix1_h4_terminal_release_preserves_cleared_attribution',
                                          'expression': "win['settled_at'] is not None and win['settled_reporter_id'] is None",
                                          'message_source': "('FIX1 H4 cleared attribution', dict(win))",
                                          'tag': 'FIX1 H4 cleared attribution',
                                          'occurrences': 1,
                                          'ordinal': 0},
                                         {'file': 'test_match_hold_deletion_pg.py',
                                          'function': 'test_fix1_h4_terminal_release_preserves_cleared_attribution',
                                          'expression': "not called and all((row['state'] == 'kept' for row in states))",
                                          'message_source': "('FIX1 H4 terminal disposition', called, states)",
                                          'tag': 'FIX1 H4 terminal disposition',
                                          'occurrences': 1,
                                          'ordinal': 0})}

# Add new tagged rows here; values are tuples of exact stable assertion tags.
INTENDED_ASSERTIONS = {'NX0a': ('FIX2 M2 one action',),
 'FIX2.M1.SETTLE': ('FIX2 M1 unarmed settle',),
 'FIX2.M1.ARM': ('FIX2 M1 unarmed arm',),
 'FIX2.M1.RECEIVE': ('FIX2 M1 unarmed receive',),
 'FIX2.M1.DEADLINE': ('FIX2 M1 finite deadline',),
 'FIX2.M1.CAUSAL': ('FIX2 M1 causal advance',),
 'FIX2.M2.ACTION': ('FIX2 M2 one action',),
 'FIX2.M4.HELD_RECEIPT.TEAM': ('FIX2 M4 held receipt deadline',),
 'FIX2.M4.HELD_RECEIPT.OVT': ('FIX2 M4 held receipt deadline',)}

def read_registry_run(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return {"collection_errors": ["missing or invalid child record"], "reports": []}


def registry_run_verdict(returncode, run, *, mid=None, tag=None, selector=None, selector_is_node=False):
    """Fail closed; only exact intended AssertionErrors qualify as kills.

    selector is the existing U -k expression, or the C node name when
    selector_is_node=True. Boolean expressions use pytest's own parser;
    literal node ids are never parsed as expressions.
    The returned first-failure message can also be checked by
    rdm_controls.verdict_mutant, preserving that registry's tag rule.
    """
    reports = run.get("reports", [])
    if run.get("collection_errors"):
        return "ERROR", "collection errors"
    if any(r.get("outcome") == "failed" and r.get("phase") != "call" for r in reports):
        return "ERROR", "setup or teardown error"
    calls = [r for r in reports if r.get("phase") == "call"]
    if any(r.get("outcome") == "skipped" for r in reports):
        return "SKIPPED", "skipped child coverage"
    if not calls or not run.get("collected"):
        return "EMPTY", "no executed test case"
    if selector_is_node:
        def matches(node):
            name = node.split("::", 1)[-1]
            return (not selector or name == selector
                    or ("[" not in selector and name.startswith(selector + "[")))
    else:
        try:
            expression = Expression.compile(selector or "")
        except SyntaxError:
            return "ERROR", "invalid pytest selection expression"

        def matches(node):
            return not selector or expression.evaluate(lambda name: name.casefold() in node.casefold())
    selected = [r for r in calls if "census" not in r.get("node", "") and matches(r.get("node", ""))]
    if not selected:
        return "EMPTY", "no selected non-census test executed"
    failures = [r for r in calls if r.get("outcome") == "failed"]
    if returncode == 0 and not failures and all(r.get("outcome") == "passed" for r in calls):
        return "GREEN", {"passed": len(calls), "errors": 0, "skipped": 0}
    if returncode != 1 or not failures:
        return "ERROR", {"returncode": returncode, "failures": len(failures)}
    for failure in failures:
        if failure not in selected:
            return "RED-OTHER", "a census or unselected node failed"
        if failure.get("exception") != "builtins.AssertionError":
            return "RED-EXCEPTION", failure.get("exception")
        if tag is not None:
            if failure.get("tag") != tag:
                return "RED-OTHER", failure.get("tag")
        elif mid in INTENDED_ASSERTIONS:
            if failure.get("tag") not in INTENDED_ASSERTIONS[mid]:
                return "RED-OTHER", failure.get("tag")
        elif mid is not None:
            observed = failure.get("assertion")
            if not observed or not any(
                    all(observed.get(k) == wanted[k]
                        for k in ("file", "function", "expression", "message_source", "occurrences", "ordinal"))
                    and (wanted["tag"] is None or wanted["tag"] == failure.get("tag"))
                    for wanted in RUNNER_ASSERTIONS.get(mid, ())):
                return "RED-OTHER", observed
        else:
            return "RED-OTHER", "no intended assertion specified"
    return "RED-NAMED", failures[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--piece", action="append", default=[])
    ap.add_argument("--mutant", action="append", default=[])
    a = ap.parse_args()
    scratch = os.environ.get("MATCH_HOLD_SCRATCH") or ""
    if not scratch or not os.path.isdir(scratch):
        raise SystemExit("REFUSED: MATCH_HOLD_SCRATCH must name an existing directory")
    if os.path.normcase(os.path.abspath(scratch)).startswith(
            os.path.normcase(os.path.dirname(BACKEND))):
        raise SystemExit("REFUSED: MATCH_HOLD_SCRATCH is inside the worktree")
    ids = [m for m, v in MUTANTS.items() if v[0] in a.piece] + a.mutant
    if not ids:
        raise SystemExit("REFUSED: no mutant selected")
    bad = 0
    for mid in ids:
        piece, module, medits, cedits, test_file, sel = MUTANTS[mid]
        src_dir = SQL if module.endswith(".sql") else API
        with open(os.path.join(src_dir, module), encoding="utf-8", newline="") as f:
            base = f.read()
        root = os.path.join(scratch, mid)
        if os.path.exists(root):
            raise SystemExit(f"REFUSED {mid}: {root} exists (never overwrite evidence)")
        mdir, cdir = os.path.join(root, "mutant"), os.path.join(root, "control")
        _write_copy(mdir, module, _plant(base, medits, mid, "mutant"))
        _write_copy(cdir, module, _plant(base, cedits, mid, "control"))
        mrc, mfail, mout, mrecord = _run(mdir, module, test_file, sel, mid=mid)
        crc, cfail, cout, crecord = _run(cdir, module, test_file, sel, mid=mid)
        with open(os.path.join(root, "mutant.out"), "w", encoding="utf-8") as f:
            f.write(mout)
        with open(os.path.join(root, "control.out"), "w", encoding="utf-8") as f:
            f.write(cout)
        killed = registry_run_verdict(mrc, mrecord, mid=mid, selector=sel)[0] == "RED-NAMED"
        green = registry_run_verdict(crc, crecord, selector=sel)[0] == "GREEN"
        verdict = "OK" if (killed and green) else "BAD"
        bad += verdict != "OK"
        print(f"{verdict} {mid} {piece} mutant rc={mrc} red={','.join(mfail) or '-'}"
              f" | control rc={crc} {'green' if green else 'NOT GREEN ' + ','.join(cfail)}")
    print(f"SUMMARY {len(ids) - bad}/{len(ids)} mutants red with controls green")
    return 1 if bad else 0



if __name__ == "__main__":
    sys.exit(main())
