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

# id: (piece, module file, [(anchor, mutant text)], [(anchor, control text)],
#      test file, -k selection of the tests that must fail)
MUTANTS = {
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
              [('    if window["settle_after"] <= now:\n'
                '        await _settle_locked(\n'
                '            db, window, room=room, game_id=game_id, now=now, settle=settle)\n'
                '        return {"status": "duplicate"}\n',
                '')],
              [('    if window["settle_after"] <= now:\n',
                '    if (window["settle_after"] <= now):\n')],
              WIN_T, "t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c"),
    "F1.H6": ('FIX1', 'match_report_window.py', [('            if not await _settle_and_mark(db, room, game_id, entry, now, settle):\n', '            if not await _settle_and_mark(db, room, game_id, dict(entry, payload=payload), now, settle):\n')], [('            if not await _settle_and_mark(db, room, game_id, entry, now, settle):\n', '            if not await _settle_and_mark(db, room, game_id, (entry), now, settle):\n')], 'test_match_report_window.py', 't5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c'),
    "F1.M5": ("FIX1", "match_report_window.py",
              [('        "   AND m.beat_at <= CAST(:now AS timestamptz)"\n', '')],
              [('        "   AND m.beat_at <= CAST(:now AS timestamptz)"\n',
                '        "   AND  m.beat_at <= CAST(:now AS timestamptz)"\n')],
              WIN_T, "t5_4_settles_at_receipt_only_for_the_lowest_fresh_class_c"),
    "F1.M4": ("FIX1", "match_report_window.py",
              [('    if chosen is not None and chosen["cls"] == CLASS_C:\n',
                '    if False and chosen is not None and chosen["cls"] == CLASS_C:\n')],
              [('    if chosen is not None and chosen["cls"] == CLASS_C:\n',
                '    if (chosen is not None and chosen["cls"] == CLASS_C):\n')],
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
             [('    return bool((await db.execute(text(\n'
               '        "SELECT 1 FROM team_queue WHERE player_id = CAST(:pid AS uuid)"',
               '    return False and bool((await db.execute(text(\n'
               '        "SELECT 1 FROM team_queue WHERE player_id = CAST(:pid AS uuid)"')],
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
             [("from datetime import timedelta\n",
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


def _run(dest, module, test_file, sel):
    env = dict(os.environ)
    env.pop("MATCH_HOLD_SRC", None)
    env.pop("MATCH_HOLD_M383", None)
    if module.endswith(".sql"):
        env["MATCH_HOLD_M383"] = os.path.join(dest, module)
    else:
        env["MATCH_HOLD_SRC"] = dest
    cmd = [sys.executable, "-m", "pytest", "--rootdir", BACKEND, "-p", "no:cacheprovider",
           "-q", "-rf", os.path.join(TESTS, test_file), "-k", f"census or ({sel})"]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    out = p.stdout + p.stderr
    failed = sorted(set(re.findall(r"^FAILED \S+::(\w+)", out, re.M)))
    return p.returncode, failed, out


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
        mrc, mfail, mout = _run(mdir, module, test_file, sel)
        crc, cfail, cout = _run(cdir, module, test_file, sel)
        with open(os.path.join(root, "mutant.out"), "w", encoding="utf-8") as f:
            f.write(mout)
        with open(os.path.join(root, "control.out"), "w", encoding="utf-8") as f:
            f.write(cout)
        killed = (mrc == 1 and mfail and not any("census" in t for t in mfail)
                  and all(re.search(sel.replace(" or ", "|"), t) for t in mfail))
        green = crc == 0 and not cfail
        verdict = "OK" if (killed and green) else "BAD"
        bad += verdict != "OK"
        print(f"{verdict} {mid} {piece} mutant rc={mrc} red={','.join(mfail) or '-'}"
              f" | control rc={crc} {'green' if green else 'NOT GREEN ' + ','.join(cfail)}")
    print(f"SUMMARY {len(ids) - bad}/{len(ids)} mutants red with controls green")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
