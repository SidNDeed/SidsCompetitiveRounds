"""The control registry for cf_controls.py: one entry per S row of the
evidence file (V11:2824-2890), each with its test node, its mutants (exact
text replacements plus the assertion tag each must turn red) and its twin.

The mutant texts follow the row's MUTANTS column as written; where the
column names a mechanism of the design (a SQL clause, a helper) the mutant
applies that mechanism to the code this build shipped, and its note says so.
A tag ending in '*' names a fixture whose assertions share that prefix.
"""

MAIN = "backend/api/main.py"
DBPY = "backend/api/database.py"
M355 = "backend/sql/355_ffa_assembly.sql"
PG = "test_ffa_assembly_pg.py::"

ROWS = []
ORDER = {}


def E(path, old, new, count=1):
    return (path, old, new, count)


def M(mid, tag, *edits, note="", nodes=None, equivalent=None):
    return {"id": mid, "tag": tag, "edits": list(edits), "note": note, "nodes": nodes,
            "equivalent": equivalent}


def T(mid, *edits, note="", nodes=None):
    return {"id": mid, "tag": None, "edits": list(edits), "note": note, "nodes": nodes}


def row(rid, nodes, mutants, twin, extra=()):
    if isinstance(nodes, str):
        nodes = [nodes]
    ROWS.append({"row": rid, "nodes": [PG + n if "::" not in n else n for n in nodes],
                 "mutants": mutants, "twin": twin, "extra": tuple(extra)})
    ORDER[rid] = len(ORDER)


# -- S1 --------------------------------------------------------------------
_B1 = 'elif some and t >= ASM_BASE_S and not spawning and not hold_adm:'
_B2 = 'elif t >= ASM_BASE_S and not hold_att and not hold_adm:'
row("S1", "test_s1_rule_b_boundary_both_tables", [
    M("ge_to_gt_table1", "S1 40.0",
      E(MAIN, _B1, _B1.replace("t >= ASM_BASE_S", "t > ASM_BASE_S"))),
    M("ge_to_gt_table2", "S1 40.0",
      E(MAIN, _B2, _B2.replace("t >= ASM_BASE_S", "t > ASM_BASE_S"))),
    M("base_41", "S1 40.0",
      E(MAIN, "ASM_BASE_S = 40 ", "ASM_BASE_S = 41 ")),
], T("interval_from_constant",
     E(MAIN, _B1, _B1.replace("t >= ASM_BASE_S",
                              '(ctx.now - lob["created_at"]) >= timedelta(seconds=ASM_BASE_S)')),
     E(MAIN, _B2, _B2.replace("t >= ASM_BASE_S",
                              '(ctx.now - lob["created_at"]) >= timedelta(seconds=ASM_BASE_S)')),
     note="the make_interval twin: the threshold compared as an interval built from "
          "the constant"))

# -- S2 --------------------------------------------------------------------
_HOLD_ATT = ('hold_att = any(int(p["attempt"] or 0) >= 1 and p["attempt_at"] is not None\n'
             '                       and p["attempt_at"] >= ctx.now - '
             'timedelta(seconds=ASM_ATTEMPT_FRESH_S)\n'
             '                       for p in pending)')
row("S2", "test_s2_attempt_hold_is_table_two_only", [
    M("drop_attempt_table2", "S2 hold",
      E(MAIN, _B2, _B2.replace(" and not hold_att", ""))),
    M("add_attempt_table1", "S2 hold",
      E(MAIN, _B1, _B1.replace(
          "and not hold_adm:",
          'and not hold_adm and not any(int(p["attempt"] or 0) >= 1 and p["attempt_at"] '
          'is not None and p["attempt_at"] >= ctx.now - '
          'timedelta(seconds=ASM_ATTEMPT_FRESH_S) for p in pending):'))),
], T("fresh_window_in_ms",
     E(MAIN, _HOLD_ATT, _HOLD_ATT.replace(
         "timedelta(seconds=ASM_ATTEMPT_FRESH_S)",
         "timedelta(milliseconds=ASM_ATTEMPT_FRESH_S * 1000)")),
     note="the constant's twin: the same window through the same constant in ms"))

# -- S3 --------------------------------------------------------------------
_UNOFF = 'unoffered = bool(pending) and all(p["lock_offered_at"] is None for p in pending)'
row("S3", "test_s3_rule_e_reads_lock_offered_at_only", [
    M("key_on_lock_seen", "S3 offered",
      E(MAIN, _UNOFF, _UNOFF.replace('p["lock_offered_at"]', 'p["lock_seen_at"]'))),
], T("not_exists",
     E(MAIN, _UNOFF, 'unoffered = bool(pending) and not any(p["lock_offered_at"] is not None '
                     'for p in pending)'),
     note="NOT EXISTS: the negated existential over the same column"))

# -- S4 --------------------------------------------------------------------
_SEEN = ('    for q in seats:\n'
         '        if q["player_id"] == p["player_id"] or not _asm_nonfinal(q):\n'
         '            continue\n'
         '        if _asm_fresh(q, now) and q["census_region"] == p["claim_region"] \\\n'
         '                and _asm_lists(q, p["slot"], p["actor_claim"]):\n'
         '            return True\n')
_CORR = ('    return (_asm_fresh(p, now) and p["actor_nr"] is not None\n'
         '            and p["actor_nr"] == p["actor_claim"]\n')
_LISTS = ('    return any(sl == slot and a == actor\n'
          '               for sl, a in zip(s["census_slots"] or [], s["census_actors"] or []))\n')
row("S4", "test_s4_corroboration", [
    M("single_source", "S4 self only",
      E(MAIN, _SEEN, _SEEN.replace('if q["player_id"] == p["player_id"] or not',
                                   'if not')),
      note="the seat's own census corroborates its own claim"),
    M("two_others", "S4 two peers without own",
      E(MAIN, _CORR, _CORR.replace(
          "return (_asm_fresh(p, now) and",
          'return ((_asm_fresh(p, now) or sum(1 for q in seats if q["player_id"] != '
          'p["player_id"] and _asm_fresh(q, now) and _asm_lists(q, p["slot"], '
          'p["actor_claim"])) >= 2) and')),
      note="V3's two-others path: two peer entries stand in for the seat's own census"),
], T("dedup",
     E(MAIN, _LISTS, _LISTS.replace(
         'for sl, a in zip(s["census_slots"] or [], s["census_actors"] or []))',
         'for sl, a in set(zip(s["census_slots"] or [], s["census_actors"] or [])))')),
     note="de-duplicated entries: any() over a set of the same pairs"))

# -- S5 --------------------------------------------------------------------
_GATED = 'gated = bool(lob.get("assembly_v1"))'
_VETO_V = 'if not FFA_ASSEMBLY_ENABLED or not lob.get("assembly_v1"):'
row("S5", "test_s5_ungated_leave_is_todays_dissolve", [
    M("room_name_gate", "S5 ungated*",
      E(MAIN, _GATED, 'gated = str(lob.get("photon_room_id") or "").startswith("ffa_")'),
      E(MAIN, _VETO_V, 'if not FFA_ASSEMBLY_ENABLED or not str(lob.get("photon_room_id") '
                       'or "").startswith("ffa_"):'),
      note="the gate keyed on the room name (LIKE 'ffa_%') in place of assembly_v1, at "
           "the leave plan and the verdict's veto (#286)"),
], T("named_local",
     E(MAIN, _GATED, 'asm_flag = lob.get("assembly_v1")\n    gated = bool(asm_flag)')))

# -- S6 --------------------------------------------------------------------
_LOCKCALL = ('    lob, k = await _ffa_lock_lobby_slot(db, lobby_id)\n'
             '    if lob is None:\n'
             '        raise HTTPException(404, "No seat in that lobby")\n'
             '    seat = (await db.execute(text(\n')
row("S6", "test_s6_answers_and_the_lobby_lock", [
    M("answer_before_lock", "S6 blocks",
      E(MAIN, _LOCKCALL, _LOCKCALL.replace(
          '    lob, k = await _ffa_lock_lobby_slot(db, lobby_id)\n',
          '    lob = (await db.execute(text("SELECT * FROM ffa_lobbies WHERE id = :lid"),\n'
          '                            {"lid": lobby_id})).mappings().first()\n'
          '    k = int(lob["games_played"] or 0) + 1 if lob is not None else 0\n')),
      note="the rows read with no lobby row lock: the arrived answers while a second "
           "session holds the lock"),
], T("helper_identical_select",
     E(MAIN, _LOCKCALL, _LOCKCALL.replace(
         '    lob, k = await _ffa_lock_lobby_slot(db, lobby_id)\n',
         '    _lock_of = _ffa_lock_lobby_slot\n'
         '    lob, k = await _lock_of(db, lobby_id)\n'))))

# -- S7 --------------------------------------------------------------------
_CARRY = ('    await ctx.db.execute(text(\n'
          '        "UPDATE ffa_bets SET lobby_id = :new WHERE lobby_id = :old AND settled_at IS NULL"),\n'
          '        {"new": new, "old": old})\n')
row("S7", "test_s7_reform_carries_wagers_and_refunds_none", [
    M("refund_at_reform", "S7 carried",
      E(MAIN, _CARRY, '    await _reconcile_ffa_lobby_bets(ctx.db, old, "assembly reformed")\n'),
      note="today's refund at the close in place of the carry"),
    M("carry_skipped", "S7 carried",
      E(MAIN, _CARRY, '')),
], T("conjunct_order",
     E(MAIN, _CARRY, _CARRY.replace("WHERE lobby_id = :old AND settled_at IS NULL",
                                    "WHERE settled_at IS NULL AND lobby_id = :old"))))

# -- S8 --------------------------------------------------------------------
_C = 'elif t >= ASM_CAP_S and not hold_adm:'
_K = 'elif t >= ASM_ABS_CAP_S:'
_HOLD_ADM = ('    hold_adm = any(p["admitted_at"] is not None\n'
             '                   and p["admitted_at"] >= ctx.now - timedelta(seconds=ASM_ADMIT_HOLD_S)\n'
             '                   for p in pending)\n')
row("S8", "test_s8_rule_c_honours_the_admission_hold_and_k_does_not", [
    M("c_ignores_hold", "S8 C 75.0", E(MAIN, _C, 'elif t >= ASM_CAP_S:')),
    M("k_honours_hold", "S8 K 81.0 held", E(MAIN, _K, 'elif t >= ASM_ABS_CAP_S and not hold_adm:')),
], T("named_local",
     E(MAIN, _HOLD_ADM,
       '    adm_recent = [p for p in pending if p["admitted_at"] is not None\n'
       '                  and p["admitted_at"] >= ctx.now - timedelta(seconds=ASM_ADMIT_HOLD_S)]\n'
       '    hold_adm = bool(adm_recent)\n')))

# -- S9 --------------------------------------------------------------------
_INROOM = 'if not pre_room and _is_in_room_exit_cause(cause):'
_LEFTSET = 'left = [p for p in ctx.seats if cls.get(p["player_id"]) == "LEFT"]'
row("S9", "test_s9_labels_cannot_change_a_decision", [
    M("label_as_cause", "S9 pre-room",
      E(MAIN, _INROOM, 'if not pre_room and _is_in_room_exit_cause(label):')),
    M("verdict_reads_left_label", "S9 verdict reads a label",
      E(MAIN, '    left = [p for p in ctx.seats if cls.get(p["player_id"]) == "LEFT"]\n'
              '    admission = bool(lob.get("admission_v1"))\n',
        '    left = [p for p in ctx.seats if cls.get(p["player_id"]) == "LEFT"\n'
        '            and p.get("left_label") != "menu_leave"]\n'
        '    admission = bool(lob.get("admission_v1"))\n')),
], T("cause_through_helper",
     E(MAIN, '{"now": ctx.now, "lc": _persistable_exit_cause(cause),',
       '{"now": ctx.now, "lc": (lambda c: _persistable_exit_cause(c))(cause),')))

# -- S10 -------------------------------------------------------------------
_LOCKUPD = 'player_count=:n, member_ids=:members, created_at=NOW(),'
_ADMTOK = 'if ADM_CAPS_TOKEN not in toks or not (ADM_PRODUCTION_ENABLED or r["enrolled"]):'
row("S10", "test_s10_the_start_refactor_is_equivalent", [
    M("no_created_at", "S10 created_at",
      E(MAIN, _LOCKUPD, 'player_count=:n, member_ids=:members,')),
    M("host_not_offered", "S10 host offered",
      E(MAIN, '    await _asm_insert_seat_rows(db, lobby_id, ordered, offered_pid)\n',
        '    await _asm_insert_seat_rows(db, lobby_id, ordered, None)\n')),
    M("no_adm_token", "S10 gates",
      E(MAIN, _ADMTOK, 'if not (ADM_PRODUCTION_ENABLED or r["enrolled"]):'),
      note="the ffa_adm1 conjunct dropped: the enrolled member without the token "
           "gates admission_v1 TRUE"),
], T("rename_local",
     E(MAIN, '    _a1, _a2 = await _ffa_asm_gates(db, _pids)\n',
       '    _g1, _g2 = await _ffa_asm_gates(db, _pids)\n    _a1, _a2 = _g1, _g2\n')))

# -- S11a-j ----------------------------------------------------------------
_W1 = ('        await db.execute(text(\n'
       '            "INSERT INTO ffa_assembly_seats (lobby_id, player_id, slot, locked_at, lock_offered_at)"')
_W2 = ('    await db.execute(text(\n'
       '        "UPDATE ffa_assembly_seats SET lock_offered_at = COALESCE(lock_offered_at, NOW())"\n'
       '        " WHERE lobby_id = :lid AND player_id = :pid AND lock_offered_at IS NULL"),')
_W3 = ('    await ctx.db.execute(text(\n'
       '        "UPDATE ffa_assembly_seats SET " + ", ".join(sets) +\n'
       '        " WHERE lobby_id = :lid AND player_id = :pid"), p)\n'
       '    return info\n')
_W3D = ('        sets += ["attempt_at = CASE WHEN CAST(:a AS smallint) >= attempt"\n'
        '                 " THEN CAST(:now AS timestamptz) ELSE attempt_at END",\n'
        '                 "attempt_phase = CASE WHEN CAST(:a AS smallint) >= attempt"\n'
        '                 " THEN CAST(:ph AS varchar) ELSE attempt_phase END",\n'
        '                 "first_attempt_at = COALESCE(first_attempt_at, CAST(:now AS timestamptz))",\n'
        '                 "attempt = GREATEST(attempt, CAST(:a AS smallint))"]\n')
_W4 = ('    await ctx.db.execute(text(\n'
       '        "UPDATE ffa_assembly_seats SET " + ", ".join(sets) +\n'
       '        " WHERE lobby_id = :lid AND player_id = :pid"), p)\n'
       '\n\nasync def _asm_assembly_work(ctx, pid, req) -> dict:')
_W5 = ('    await ctx.db.execute(text(\n'
       '        "UPDATE ffa_assembly_seats"\n'
       '        "   SET left_at = COALESCE(left_at, CAST(:now AS timestamptz)),"')
_W6 = ('    await ctx.db.execute(text(\n'
       '        "UPDATE ffa_assembly_seats"\n'
       '        "   SET dec_at = COALESCE(dec_at, CAST(:now AS timestamptz)),"')
_W7H = ('        res = await ctx.db.execute(text(\n'
        '            "UPDATE ffa_assembly_seats"\n'
        '            "   SET actor_nr = CAST(:a AS smallint), actor_region = :r,"\n'
        '            "       verdict = \'admitted_late\', late_admitted_at = CAST(:now AS timestamptz),"')
_W8I = ('        await db.execute(text(\n'
        '            "UPDATE ffa_assembly_seats SET verdict = \'excluded\', verdict_at = CAST(:now AS timestamptz)"\n'
        '            " WHERE lobby_id = :lid AND player_id = :pid AND verdict = \'admissible\'"),')
_WJ = ('    await db.execute(text(\n'
       '        "UPDATE ffa_assembly_seats SET entered_game = late_body_game"')
_S11 = ["test_s11a_the_lock_seat_rows", "test_s11b_the_poll_offer",
        "test_s11c_the_connect_receipts", "test_s11d_the_attempt_columns",
        "test_s11e_census_claim_binding_body", "test_s11f_the_leave_columns",
        "test_s11g_the_verdict_and_the_decision_record", "test_s11h_the_admission_columns",
        "test_s11i_the_expiry_verdict", "test_s11j_spawn_entered_late_body_entered_game"]


def _skip(first):
    """The writer's statement deleted: `if False:` in front of its await."""
    return E(MAIN, first, first.replace("await ", "if False: await ", 1))


row("S11a-j", _S11, [
    M("a_seat_rows", "S11a rows", _skip(_W1), nodes=[PG + _S11[0]]),
    M("b_poll_offer", "S11b", _skip(_W2), nodes=[PG + _S11[1]]),
    M("c_connect_receipts", "S11c", _skip(_W3), nodes=[PG + _S11[2]]),
    M("d_attempt_columns", "S11d first", E(MAIN, _W3D, "        pass\n"),
      nodes=[PG + _S11[3]]),
    M("e_census", "S11e census", _skip(_W4), nodes=[PG + _S11[4]]),
    M("f_leave_receipts", "S11f", _skip(_W5), nodes=[PG + _S11[5]]),
    M("g_decision_record", "S11g dec_at", _skip(_W6), nodes=[PG + _S11[6]]),
    M("h_admission", "S11h",
      E(MAIN, _W7H, _W7H.replace(
          "        res = await ctx.db.execute(text(\n",
          "        res = type('R', (), {'rowcount': 0})() if True else "
          "await ctx.db.execute(text(\n")),
      nodes=[PG + _S11[7]],
      note="the admission's statement never runs (rowcount 0: the seat is skipped)"),
    M("i_expiry", "S11i", _skip(_W8I), nodes=[PG + _S11[8]]),
    M("j_entered_game", "S11j entered_game", _skip(_WJ), nodes=[PG + _S11[9]]),
], T("coalesce_to_case",
     E(MAIN, '"UPDATE ffa_assembly_seats SET body_seen_at = COALESCE(body_seen_at, '
             'CAST(:now AS timestamptz))"',
       '"UPDATE ffa_assembly_seats SET body_seen_at = CASE WHEN body_seen_at IS NULL '
       'THEN CAST(:now AS timestamptz) ELSE body_seen_at END"'),
     E(MAIN, '"UPDATE ffa_assembly_seats SET lock_offered_at = COALESCE(lock_offered_at, NOW())"\n'
             '        " WHERE lobby_id = :lid AND player_id = :pid AND lock_offered_at IS NULL"),',
       '"UPDATE ffa_assembly_seats SET lock_offered_at = CASE WHEN lock_offered_at IS NULL '
       'THEN NOW() ELSE lock_offered_at END"\n'
       '        " WHERE lobby_id = :lid AND player_id = :pid AND lock_offered_at IS NULL"),'),
     E(MAIN, '"UPDATE ffa_assembly_seats SET left_path = COALESCE(left_path, CAST(:p AS varchar))"',
       '"UPDATE ffa_assembly_seats SET left_path = CASE WHEN left_path IS NULL '
       'THEN CAST(:p AS varchar) ELSE left_path END"')))

# -- S12 -------------------------------------------------------------------
_SS_CALL = ('    if outcome == "start_short":\n'
            '        done = await _asm_start_short(ctx, rule, cls)\n')
_SS_UPD = ('        "UPDATE ffa_lobbies SET start_granted_at = NOW(), short_started_at = NOW(),"\n'
           '        "       bets_disabled = TRUE, asm_rule = :r"\n')
_SS_END = ('    ctx.log(f"short start n={len(roster)} admissible={len(admissible)} '
           't=+{ctx.t_ms()} rule={rule}")\n    return True\n')
row("S12", "test_s12_start_short_is_one_transaction_and_refunds_none", [
    M("commit_before_step5", "S12 fault",
      E(MAIN, _SS_CALL, _SS_CALL + '        await ctx.db.commit()\n')),
    M("reconcile_at_step5", "S12 clean wagers",
      E(MAIN, _SS_END, '    await _reconcile_ffa_lobby_bets(ctx.db, ctx.lid, "assembly short start")\n'
        + _SS_END)),
], T("reorder_set",
     E(MAIN, _SS_UPD, '        "UPDATE ffa_lobbies SET asm_rule = :r, bets_disabled = TRUE,"\n'
                      '        "       short_started_at = NOW(), start_granted_at = NOW()"\n')))

# -- S12b ------------------------------------------------------------------
_LR_END = ('    await _lease_acquire_many(db, _pids, "ffa", lobby_id, LEASE_TTL_ASSEMBLY)\n'
           '    return room, region, ordered\n')
_RF_UPD = ('        "UPDATE ffa_lobbies SET status = \'canceled\', invalidation_reason = '
           '\'assembly_reformed\',"\n')
row("S12b", "test_s12b_reform_is_one_transaction", [
    M("commit_inside_lock_roster", "S12b no L'",
      E(MAIN, _LR_END, _LR_END.replace("    return room", "    await db.commit()\n    return room"))),
], T("reorder_set",
     E(MAIN, _RF_UPD, '        "UPDATE ffa_lobbies SET invalidation_reason = \'assembly_reformed\', '
                      'status = \'canceled\',"\n')))

# -- S14 -------------------------------------------------------------------
_CAP = 'if cap and int(seat["writes"] or 0) >= ASM_WRITES_CAP:'
row("S14", "test_s14_the_writes_cap", [
    M("cap_171", "S14 cap", E(MAIN, "ASM_WRITES_CAP = 170 ", "ASM_WRITES_CAP = 171 ")),
    M("cap_150", "S14 167", E(MAIN, "ASM_WRITES_CAP = 170 ", "ASM_WRITES_CAP = 150 ")),
], T("writes_plus_one",
     E(MAIN, _CAP, 'if cap and int(seat["writes"] or 0) + 1 > ASM_WRITES_CAP:')))

# -- S15 -------------------------------------------------------------------
_ST_A = ('    if st == "A":\n'
         '        if info.get("wrong_region"):\n')
_SEATREAD = ('"SELECT writes FROM ffa_assembly_seats WHERE lobby_id = :lid AND player_id = :pid"),')
row("S15", "test_s15_the_seat_row_answer", [
    M("fall_through_to_verdict", "S15 reformed",
      E(MAIN, _ST_A, _ST_A.replace('if st == "A":', 'if st in ("A", "E"):')),
      note="a final seat row answered as state A (the verdict's answer)"),
    M("lock_callers_queue_lobby", "S15 reformed",
      E(MAIN, _LOCKCALL, _LOCKCALL.replace(
          '    lob, k = await _ffa_lock_lobby_slot(db, lobby_id)\n',
          '    lobby_id = str((await db.execute(text(\n'
          '        "SELECT series_id FROM ffa_queue WHERE player_id = :pid"),\n'
          '        {"pid": pid})).scalar() or lobby_id)\n'
          '    lob, k = await _ffa_lock_lobby_slot(db, lobby_id)\n')),
      note="_lock_queue_group_for_player's rule: the caller's queue row names the lobby"
           " (str(): the driver hands back a UUID, the route carries the id as text)"),
], T("cte_read",
     E(MAIN, _SEATREAD,
       '"WITH s AS (SELECT writes FROM ffa_assembly_seats WHERE lobby_id = :lid AND '
       'player_id = :pid) SELECT writes FROM s"),')))

# -- S16 -------------------------------------------------------------------
_ATT_AT = ('"attempt_at = CASE WHEN CAST(:a AS smallint) >= attempt"\n'
           '                 " THEN CAST(:now AS timestamptz) ELSE attempt_at END",')
_ATT_PH = ('"attempt_phase = CASE WHEN CAST(:a AS smallint) >= attempt"\n'
           '                 " THEN CAST(:ph AS varchar) ELSE attempt_phase END",')
row("S16", "test_s16_the_attempt_hold", [
    M("attempt_at_on_gt", "S16 ii refresh",
      E(MAIN, _ATT_AT, _ATT_AT.replace(">= attempt", "> attempt"))),
    M("attempt_at_every_post", "S16 iii",
      E(MAIN, _ATT_AT, '"attempt_at = CAST(:now AS timestamptz)",')),
    M("accept_zero", "S16 iv",
      E(MAIN, "        if not 1 <= req.attempt <= 9:\n",
        "        if not 0 <= req.attempt <= 9:\n")),
], T("not_less_than",
     E(MAIN, _ATT_AT, _ATT_AT.replace("CAST(:a AS smallint) >= attempt",
                                      "NOT (CAST(:a AS smallint) < attempt)")),
     E(MAIN, _ATT_PH, _ATT_PH.replace("CAST(:a AS smallint) >= attempt",
                                      "NOT (CAST(:a AS smallint) < attempt)"))))

# -- S17 -------------------------------------------------------------------
_HOP = '    _asm_hop = bool(expected_lobby_id and lobby_id is not None\n'
_RFSEL = ('    rf = (await db.execute(text("SELECT reformed_from FROM ffa_lobbies WHERE id = :lid"),\n'
          '                           {"lid": lobby_id})).scalar()\n')
row("S17", "test_s17_the_reform_aware_fence", [
    M("fence_as_today", "S17 hop answer",
      E(MAIN, _HOP, '    _asm_hop = False and bool(expected_lobby_id and lobby_id is not None\n')),
    M("honour_in_room_cause", "S17 pre-room",
      E(MAIN, '                                          pre_room=_asm_hop)\n',
        '                                          pre_room=False)\n')),
], T("helper_second_select",
     E(MAIN, _RFSEL,
       '    async def _read_rf():\n'
       '        return (await db.execute(text("SELECT reformed_from FROM ffa_lobbies WHERE id = :lid"),\n'
       '                                 {"lid": lobby_id})).scalar()\n'
       '    rf = await _read_rf()\n')))

# -- S18 -------------------------------------------------------------------
_FLOOR = ('    if t < ASM_EARLY_S:\n'
          '        return ans\n'
          '    hold_adm = any(')
_D0 = ('        if left and len(ready) + len(pending) < 3:\n'
       '            rule = "D"          # D0: dissolves at once, recorded as D\n')
row("S18", "test_s18_rule_d_and_d0", [
    M("decide_on_left_before_20", "S18 t8",
      E(MAIN, _FLOOR, _FLOOR.replace("if t < ASM_EARLY_S:", "if t < ASM_EARLY_S and not left:"))),
    M("d0_waits_for_holds", "S18 D0",
      E(MAIN, _D0, _D0.replace("< 3:", "< 3 and not hold_att and not hold_adm:"))),
], T("floor_as_interval",
     E(MAIN, _FLOOR, _FLOOR.replace(
         "if t < ASM_EARLY_S:",
         'if (ctx.now - lob["created_at"]) < timedelta(seconds=ASM_EARLY_S):'))))

# -- S19 -------------------------------------------------------------------
_GUARD = ('            if JOIN_REGION_GUARD:\n'
          '                sets += ["wrong_region_n = wrong_region_n + 1", "fail_count = fail_count + 1"]\n')
_DIFF = 'differs = req.region is not None and region is not None and req.region != region'
row("S19", "test_s19_join_region_guard_gates_the_region_answer", [
    M("wrong_region_regardless", "S19 off",
      E(MAIN, _GUARD, _GUARD.replace("if JOIN_REGION_GUARD:", "if True:"))),
], T("helper",
     E(MAIN, _DIFF, 'differs = (lambda a, b: a is not None and b is not None and a != b)'
                    '(req.region, region)')))

# -- S20 -------------------------------------------------------------------
_POLL_HEAD = ('    ctx = await _asm_ctx_slot(db, lid, route="poll", trigger="poll")\n'
              '    await _asm_poll_offer(db, lid, pid)\n'
              '    ctx.prints.extend(_asm_log_expired(ctx, await _ffa_expire_admissions(\n'
              '        db, lid, now=ctx.now)))\n')
_POLL_COMMIT = ('    await db.commit()\n'
                '    ctx.emit()\n'
                '    if ctx.refund_flush:\n'
                '        try:\n'
                '            await _flush_lobby_bet_refunds(db, "ffa", lid)\n')
row("S20", "test_s20_writer_2_commits", [
    M("offer_after_commit", "S20 offered",
      E(MAIN, _POLL_HEAD, _POLL_HEAD.replace("    await _asm_poll_offer(db, lid, pid)\n", "")),
      E(MAIN, _POLL_COMMIT, _POLL_COMMIT.replace(
          "    ctx.emit()\n", "    ctx.emit()\n    await _asm_poll_offer(db, lid, pid)\n"))),
    M("expiry_after_commit", "S20 expiry",
      E(MAIN, _POLL_HEAD, _POLL_HEAD.replace(
          '    ctx.prints.extend(_asm_log_expired(ctx, await _ffa_expire_admissions(\n'
          '        db, lid, now=ctx.now)))\n', "")),
      E(MAIN, _POLL_COMMIT, _POLL_COMMIT.replace(
          "    ctx.emit()\n",
          "    ctx.emit()\n"
          "    ctx.prints.extend(_asm_log_expired(ctx, await _ffa_expire_admissions(\n"
          "        db, lid, now=ctx.now)))\n"))),
], T("helper",
     E(MAIN, _POLL_HEAD, _POLL_HEAD.replace(
         "    await _asm_poll_offer(db, lid, pid)\n",
         "    _offer = _asm_poll_offer\n    await _offer(db, lid, pid)\n"))))

# -- helpers for the rows below ---------------------------------------------
PIN = "@pin/main.py"
TST = "backend/tests/test_ffa_assembly_pg.py"


def L(n, s):
    """One source line: n spaces, the text, a newline."""
    return " " * n + s + "\n"


# -- S21 -------------------------------------------------------------------
_S21_LOCK = ('    lob, k = await _ffa_lock_lobby_slot(db, lobby_id)\n'
             '    if lob is None:\n')
_S21_RET = '    await ctx.reload()\n    return ctx, pid\n'
_S21_WORK = ('    info = await _asm_connect_write(ctx, me, req, state)\n'
             '    await ctx.reload(lobby=False)\n'
             '    me = ctx.seat_of(pid)\n')
_S21_GRANT = ('    got = (await ctx.db.execute(text(\n'
              '        "UPDATE ffa_lobbies SET start_granted_at = NOW()"\n'
              '        " WHERE id = :lid AND status = \'active\' AND games_played = 0"\n'
              '        "   AND start_granted_at IS NULL RETURNING id"), {"lid": ctx.lid})).scalar()\n')
_S21_SHORT = ('        "       bets_disabled = TRUE, asm_rule = :r"\n'
              '        " WHERE id = :lid AND status = \'active\' AND games_played = 0"\n'
              '        "   AND start_granted_at IS NULL RETURNING id"),\n')
_VETO3 = '    if lob.get("start_granted_at") is not None:\n        return ans\n'
row("S21", "test_s21_grant_and_verdict_exclude_each_other", [
    M("pre_lock_read_unconditional_grant", "S21 vi grant",
      E(MAIN, _S21_LOCK,
        '    if route == "connect":\n'
        '        _pre = _AsmCtx(db, lobby_id, route=route, trigger=route, t0=t0)\n'
        '        _pre.now, _pre.mono = await _asm_clock(db)\n'
        '        await _pre.reload()\n' + _S21_LOCK),
      E(MAIN, _S21_RET,
        '    await ctx.reload()\n'
        '    if route == "connect":\n'
        '        ctx.lobby, ctx.seats = _pre.lobby, _pre.seats\n'
        '    return ctx, pid\n'),
      E(MAIN, _S21_WORK,
        '    info = await _asm_connect_write(ctx, me, req, state)\n'
        '    me = ctx.seat_of(pid)\n'),
      E(MAIN, _S21_GRANT, _S21_GRANT.replace(
          '        " WHERE id = :lid AND status = \'active\' AND games_played = 0"\n'
          '        "   AND start_granted_at IS NULL RETURNING id"), ',
          '        " WHERE id = :lid RETURNING id"), ')),
      note="the connect route reads the lobby and seat rows before the lobby lock and "
           "grants from them with an unconditional UPDATE ... WHERE id = :lid"),
    M("short_without_grant_null", "S21 ii second",
      E(MAIN, _S21_SHORT, _S21_SHORT.replace(
          '        "   AND start_granted_at IS NULL RETURNING id"),\n',
          '        "   RETURNING id"),\n'))),
    M("no_veto_3", "S21 v", E(MAIN, _VETO3, "")),
], T("predicate_constant",
     E(MAIN, 'async def _asm_full_grant(ctx) -> bool:\n',
       '_ASM_GRANT_PRED = (" WHERE id = :lid AND status = \'active\' AND games_played = 0"\n'
       '                   "   AND start_granted_at IS NULL RETURNING id")\n'
       '\n\nasync def _asm_full_grant(ctx) -> bool:\n'),
     E(MAIN, _S21_GRANT,
       '    got = (await ctx.db.execute(text(\n'
       '        "UPDATE ffa_lobbies SET start_granted_at = NOW()"\n'
       '        + _ASM_GRANT_PRED), {"lid": ctx.lid})).scalar()\n')))

# -- S22 -------------------------------------------------------------------
_S_LINE = '        elif t >= ASM_SHORT_ABS_S and len(ready) - len(spawning) >= 3:\n'
_C_LINE = '        elif t >= ASM_CAP_S and not hold_adm:\n'
_K_LINE = '        elif t >= ASM_ABS_CAP_S:\n'


def _n22(rule):
    return PG + "test_s22_every_rule_at_its_threshold[%s]" % rule


row("S22", ["test_s22_every_rule_at_its_threshold[%s]" % r
            for r in ("E", "B", "S", "C", "K", "D", "D-floor")], [
    M("floor_19", "S22 D-floor 19.9",
      E(MAIN, _FLOOR, _FLOOR.replace("if t < ASM_EARLY_S:", "if t < 19:")),
      nodes=[_n22("D-floor")]),
    M("e_at_floor_le", "S22 E 20.0",
      E(MAIN, _FLOOR, _FLOOR.replace("if t < ASM_EARLY_S:", "if t <= ASM_EARLY_S:")),
      nodes=[_n22("E")], note="rule E's threshold is the floor"),
    M("b_gt", "S22 B 40.0",
      E(MAIN, _B2, _B2.replace("t >= ASM_BASE_S", "t > ASM_BASE_S")), nodes=[_n22("B")]),
    M("s_gt", "S22 S 46.0",
      E(MAIN, _S_LINE, _S_LINE.replace(">= ASM_SHORT_ABS_S", "> ASM_SHORT_ABS_S")),
      nodes=[_n22("S")]),
    M("c_gt", "S22 C 75.0",
      E(MAIN, _C_LINE, _C_LINE.replace(">= ASM_CAP_S", "> ASM_CAP_S")), nodes=[_n22("C")]),
    M("k_gt", "S22 K 81.0",
      E(MAIN, _K_LINE, _K_LINE.replace(">= ASM_ABS_CAP_S", "> ASM_ABS_CAP_S")),
      nodes=[_n22("K")]),
    M("d_without_floor", "S22 D-floor 19.9",
      E(MAIN, _FLOOR, _FLOOR.replace("if t < ASM_EARLY_S:",
                                     "if t < ASM_EARLY_S and not left:")),
      nodes=[_n22("D-floor")]),
], T("thresholds_by_name",
     E(MAIN, _FLOOR, _FLOOR.replace(
         "    if t < ASM_EARLY_S:\n",
         "    _th = (ASM_EARLY_S, ASM_BASE_S, ASM_SHORT_ABS_S, ASM_CAP_S, ASM_ABS_CAP_S)\n"
         "    if t < _th[0]:\n")),
     E(MAIN, _B1, _B1.replace("t >= ASM_BASE_S", "t >= _th[1]")),
     E(MAIN, _B2, _B2.replace("t >= ASM_BASE_S", "t >= _th[1]")),
     E(MAIN, _S_LINE, _S_LINE.replace("ASM_SHORT_ABS_S", "_th[2]")),
     E(MAIN, _C_LINE, _C_LINE.replace("ASM_CAP_S", "_th[3]")),
     E(MAIN, _K_LINE, _K_LINE.replace("ASM_ABS_CAP_S", "_th[4]")),
     note="each threshold read through a tuple of its named constants"))

# -- S23 -------------------------------------------------------------------
_LIST = L(11, "AND NOT l.bets_disabled  -- a re-formed or short-started lobby")
row("S23", "test_s23_the_listing_excludes_bets_disabled", [
    M("drop_predicate", "S23 excluded", E(MAIN, _LIST, "")),
], T("equals_false",
     E(MAIN, _LIST, _LIST.replace("AND NOT l.bets_disabled", "AND l.bets_disabled = FALSE"))))

# -- S24 -------------------------------------------------------------------
_BETREAD = ('    lobby = (await db.execute(text(\n'
            '        "SELECT id, status, member_ids, departed_ids, games_played, created_at,"\n'
            '        "       score_target, is_ranked, live_total_points, live_points_game,"\n'
            '        "       bets_disabled,"\n')
_BETCHK = ('    if lobby["bets_disabled"]:\n'
           '        # The connect-failure design (I3): a re-formed or short-started lobby\n'
           '        # takes no new wagers -- the listing\'s own predicate.\n'
           '        raise HTTPException(status_code=409, detail="Betting is closed for this lobby")\n')
row("S24", "test_s24_the_bet_post_refuses_from_the_locked_row", [
    M("plain_read_before_lock", "S24 refused",
      E(MAIN, _BETREAD,
        '    _pre_closed = (await db.execute(text(\n'
        '        "SELECT bets_disabled FROM ffa_lobbies WHERE id = :lid"), {"lid": lid})).scalar()\n'
        + _BETREAD),
      E(MAIN, _BETCHK, _BETCHK.replace('    if lobby["bets_disabled"]:', '    if _pre_closed:')),
      note="the flag read by a plain SELECT issued before the locked SELECT"),
], T("helper_on_the_locked_row",
     E(MAIN, _BETCHK,
       '    def _refuse_closed(row):\n'
       '        if row["bets_disabled"]:\n'
       '            raise HTTPException(status_code=409, detail="Betting is closed for this lobby")\n'
       '    _refuse_closed(lobby)\n')))

# -- S25 -------------------------------------------------------------------
_BIND = ('    if reform_of is None:\n'
         '        # Lobby-phase wagers resolve against the roster just frozen above\n')
_BIND_SIG = ('async def _bind_lobby_bets(db: AsyncSession, mode: str, lobby_id, roster: dict,\n'
             '                           refund_all_reason: str | None = None) -> None:\n')
_BIND_GUARD = ('    shape of #204."""\n'
               '    if mode not in _LOBBY_BET_PARENT or lobby_id is None:\n'
               '        return\n')
_BIND_CALL = ('            "steam_by_pid": {r["player_id"]: r["steam_id"] for r in ordered},\n'
              '        })\n')
row("S25", "test_s25_lobby_phase_wagers_after_a_reform", [
    M("bind_on_reform", "S25 no lobby_bets statement",
      E(MAIN, _BIND, _BIND.replace("if reform_of is None:", "if True:")),
      note="_bind_lobby_bets called on the reform path"),
], T("skip_keyword",
     E(MAIN, _BIND_SIG, _BIND_SIG.replace(
         "refund_all_reason: str | None = None) -> None:",
         "refund_all_reason: str | None = None, *,\n"
         "                           skip: bool = False) -> None:")),
     E(MAIN, _BIND_GUARD, _BIND_GUARD.replace("    if mode not in", "    if skip or mode not in")),
     E(MAIN, _BIND, _BIND.replace("if reform_of is None:", "if True:")),
     E(MAIN, _BIND_CALL, _BIND_CALL.replace("        })\n",
                                            "        }, skip=reform_of is not None)\n")),
     note="the reform path reaches the call and skips it through a keyword flag"))

# -- S26 -------------------------------------------------------------------
_INS_BLOCK = (
    '    INSERT INTO ffa_lobbies (\n'
    '        id, status, photon_room_id, region, player_count, member_ids, created_at,\n'
    '        host_player_id, reformed_from, bets_disabled, assembly_v1, admission_v1,\n'
    '        region_why, region_detail,\n'
    '        score_target, card_candidates, initial_picks, card_cap, same_card_rule,\n'
    '        is_ranked, settings_known, settings_changed_at, password_hash, kicked_steam_ids,\n'
    '        kills_tiebreak, sudden_death,\n'
    '        games_played, departed_ids, departure_causes, live_total_points, live_points_game,\n'
    '        completed_at, invalidated_at, invalidation_reason, reformed_to,\n'
    '        start_granted_at, short_started_at, asm_rule, dissolve_path, dissolve_trigger,\n'
    '        first_leaver, first_leave_label, dissolve_after_ms, present_at_dissolve,\n'
    '        absent_at_dissolve, arrived_at_dissolve)\n'
    '    VALUES (\n'
    '        :new, \'open\', NULL, NULL, CAST(:n AS smallint), CAST(:members AS uuid[]), NOW(),\n'
    '        :host, :old, TRUE, FALSE, FALSE,\n'
    '        NULL, NULL,\n'
    '        :score_target, :card_candidates, :initial_picks, :card_cap, :same_card_rule,\n'
    '        :is_ranked, :settings_known, :settings_changed_at, :password_hash, :kicked_steam_ids,\n'
    '        :kills_tiebreak, :sudden_death,\n'
    '        0, CAST(\'{}\' AS uuid[]), CAST(\'{}\' AS jsonb), 0, 0,\n'
    '        NULL, NULL, NULL, NULL,\n'
    '        NULL, NULL, NULL, NULL, NULL,\n'
    '        NULL, NULL, NULL, NULL,\n'
    '        NULL, NULL)\n')
_INS_HEAD, _INS_SEP, _INS_VALS = _INS_BLOCK.partition("    VALUES (\n")
_COPY = ("score_target", "card_candidates", "initial_picks", "card_cap", "same_card_rule",
         "is_ranked", "settings_known", "settings_changed_at", "password_hash",
         "kicked_steam_ids")
_COPY_AND = ("kills_tiebreak", "sudden_death")


def _omit(f):
    """The INSERT with column f and its value left out (f takes its default)."""
    assert _INS_HEAD.count(" %s," % f) == 1 and _INS_VALS.count(" :%s," % f) == 1, f
    return (_INS_HEAD.replace(" %s," % f, "", 1) + _INS_SEP
            + _INS_VALS.replace(" :%s," % f, "", 1))


_COLLAPSE = ('    if reform_of is None:\n'
             '        # Config feature floor (sec3a): the server is the real authority, and it\n')
_KT_AND = '        _kills_tiebreak = bool(_kt_copied) and _kills_tiebreak\n'
_SD_GATE = ('    if not _sd_capable:\n'
            '        await db.execute(text(\n'
            '            "UPDATE ffa_lobbies SET sudden_death=FALSE WHERE id=:lid"\n')
row("S26", "test_s26_the_reform_copies_every_field",
    [M("omit_" + f, "S26 COPY-AND" if f in _COPY_AND else "S26 COPY",
       E(MAIN, _INS_BLOCK, _omit(f)), note="the INSERT omits %s" % f)
     for f in _COPY + _COPY_AND] + [
    M("collapse_on_reform", "S26 COPY",
      E(MAIN, _COLLAPSE, _COLLAPSE.replace("if reform_of is None:", "if True:"))),
    M("drop_the_and_kills_tiebreak", "S26 COPY-AND",
      E(MAIN, _KT_AND, "        _kills_tiebreak = bool(_kt_copied)\n")),
    M("drop_the_and_sudden_death", "S26 COPY-AND",
      E(MAIN, _SD_GATE, _SD_GATE.replace("if not _sd_capable:",
                                         "if not _sd_capable and reform_of is None:"))),
], T("insert_column_order",
     E(MAIN, _INS_BLOCK, _INS_BLOCK.replace(
         "        score_target, card_candidates,", "        card_candidates, score_target,")
       .replace("        :score_target, :card_candidates,", "        :card_candidates, :score_target,"))))

# -- S27 -------------------------------------------------------------------
_M355_TAIL = ("    IF cardinality(missing) > 0 THEN\n"
              "        RAISE EXCEPTION '355_ffa_assembly: missing after apply: %', missing;\n"
              "    END IF;\n"
              "END $$;\n"
              "\n"
              "COMMIT;\n")
_RESET_END = '              "arrived_at_dissolve"),\n}\n'
_COPY_AND_LINE = '    "COPY_AND": ("kills_tiebreak", "sudden_death"),\n'
row("S27", "test_s27_the_schema_census_both_directions", [
    M("fixture_migration_column", "S27 live not classed",
      E(M355, _M355_TAIL, _M355_TAIL.replace(
          "\nCOMMIT;\n", "\nALTER TABLE ffa_lobbies ADD COLUMN cf_fixture_col integer;\n\nCOMMIT;\n")),
      note="a fixture migration adds a column in no class"),
    M("class_keeps_live_top_points", "S27 class not live",
      E(MAIN, _RESET_END, _RESET_END.replace('"arrived_at_dissolve"),',
                                             '"arrived_at_dissolve", "live_top_points"),'))),
], T("class_order",
     E(MAIN, _COPY_AND_LINE, _COPY_AND_LINE.replace('("kills_tiebreak", "sudden_death")',
                                                   '("sudden_death", "kills_tiebreak")'))))

# -- S27b ------------------------------------------------------------------
_INS_COLS = [c.strip() for c in _INS_HEAD.split("(", 1)[1].rsplit(")", 1)[0].split(",")
             if c.strip()]
row("S27b", "test_s27b_a_committed_baseline_reform", [
    M("insert_names_a_missing_column", "S27b read",
      E(MAIN, _INS_BLOCK, _INS_BLOCK.replace("        id, status, photon_room_id, region,",
                                             "        id, status, photon_room_idx, region,"))),
], T("columns_from_named_tuple",
     E(MAIN, '_ASM_REFORM_INSERT_SQL = """\n' + _INS_HEAD + _INS_SEP,
       '_ASM_REFORM_COLS = (' + ", ".join('"%s"' % c for c in _INS_COLS) + ')\n'
       '_ASM_REFORM_INSERT_SQL = """\n'
       '    INSERT INTO ffa_lobbies (\n'
       '        """ + ", ".join(_ASM_REFORM_COLS) + """)\n'
       '    VALUES (\n')))

# -- S28 -------------------------------------------------------------------
_NOREC = '" dissolve_path = ffa_lobbies.dissolve_path "'
_CLOSERS = [
    ("janitor_dead_lock", "S28 dead",
     L(39, "invalidation_reason = 'janitor_dead_lock',\"\"\"")
     + L(29, '+ _FFA_CLOSE_RECORD_SET + """')),
    ("dispersed_close", "S28 dispersed",
     L(24, "+ _FFA_CLOSE_RECORD_SET +")
     + L(24, "\" WHERE id = :lid AND status = 'active'\"),")
     + L(24, '{"lid": r[0], "rec_path": "dispersed_close", "rec_trigger": "janitor"})')),
    ("quiet_close", "S28 quiet",
     L(24, "+ _FFA_CLOSE_RECORD_SET +")
     + L(24, "\" WHERE id=:lid AND status='active'\"),")
     + L(24, '{"lid": qrow["id"], "rec_path": "quiet_close", "rec_trigger": "janitor"})')),
    ("member_deleted", "S28 member_deleted",
     L(22, 'invalidated_at=NOW(),""" + _FFA_CLOSE_RECORD_SET + """')
     + L(16, "WHERE id=:lid AND status='active' AND games_played = 0")),
    ("member_deleted_played", "S28 member_deleted_played",
     L(12, '+ _FFA_CLOSE_RECORD_SET + """')
     + L(16, "WHERE id=:lid AND status='active'")
     + L(18, 'AND (games_played > 0 OR start_granted_at IS NOT NULL)"""),')),
    ("leave_dissolve", "S28 leave_dissolve",
     L(16, '"       invalidated_at=NOW()," + _FFA_CLOSE_RECORD_SET +')
     + L(16, "\" WHERE id=:lid AND status='active' AND start_granted_at IS NULL\"")),
    ("leave_all_but_one", "S28 all_but_one",
     L(24, '"UPDATE ffa_lobbies SET" + _FFA_CLOSE_RECORD_SET +')),
    ("asm_reform", "S28 asm_reform",
     L(8, "+ _FFA_CLOSE_RECORD_SET +")
     + L(8, "\" WHERE id = :lid AND status = 'active'\"),")
     + L(8, '{"new": new, "r": rule, "lid": old, "rec_path": "asm_reform", '
            '"rec_trigger": trigger})')),
    ("asm_dissolve", "S28 asm_dissolve",
     L(8, "+ _FFA_CLOSE_RECORD_SET +")
     + L(8, "\" WHERE id = :lid AND status = 'active' AND start_granted_at IS NULL "
            "RETURNING id\"),")),
    ("sitting_over", "S28 sitting_over",
     L(16, "+ _FFA_CLOSE_RECORD_SET +")
     + L(16, "\" WHERE id=:lid AND status='active'\"),")
     + L(16, '{"lid": me["series_id"], "rec_path": "sitting_over", "rec_trigger": "poll"})')),
    ("poll_dead_lock_or_failed", "S28 poll_dead_lock",
     L(20, '"       invalidated_at=NOW()," + _FFA_CLOSE_RECORD_SET +')
     + L(20, "\" WHERE id=:lid AND status='active'\"")),
]
_PRESENT = (L(41, "AND pc.census_at >= NOW() - interval '6 seconds') pu")
            + L(35, "WHERE pu.e NOT IN (SELECT pl.slot FROM ffa_assembly_seats pl")
            + L(55, "WHERE pl.lobby_id = ffa_lobbies.id")
            + L(57, "AND pl.left_at IS NOT NULL)"))
_FL = (L(7, "first_leaver = (SELECT fl.player_id FROM ffa_assembly_seats fl")
       + L(24, "WHERE fl.lobby_id = ffa_lobbies.id AND fl.left_at IS NOT NULL")
       + L(24, "ORDER BY fl.left_at, fl.slot LIMIT 1),"))
_FB = (L(7, "first_leave_label = (SELECT COALESCE(NULLIF(fb.left_label, ''), fb.left_cause)")
       + L(30, "FROM ffa_assembly_seats fb")
       + L(29, "WHERE fb.lobby_id = ffa_lobbies.id AND fb.left_at IS NOT NULL")
       + L(29, "ORDER BY fb.left_at, fb.slot LIMIT 1),"))
row("S28", "test_s28_every_closer_writes_its_record",
    [M("omit_record_" + path, tag,
       E(MAIN, anchor, anchor.replace("_FFA_CLOSE_RECORD_SET", _NOREC)),
       note="the %s closer writes no record columns" % path)
     for path, tag, anchor in _CLOSERS] + [
    M("ever_arrived_is_present", "S28 present",
      E(MAIN, _PRESENT,
        L(41, "AND pc.census_at >= NOW() - interval '6 seconds'")
        + L(38, "UNION SELECT pv.slot FROM ffa_assembly_seats pv")
        + L(39, "WHERE pv.lobby_id = ffa_lobbies.id AND pv.arrived_at IS NOT NULL) pu")
        + L(35, "WHERE pu.e NOT IN (SELECT pl.slot FROM ffa_assembly_seats pl")
        + L(55, "WHERE pl.lobby_id = ffa_lobbies.id")
        + L(57, "AND pl.left_at IS NOT NULL AND pl.arrived_at IS NULL)")),
      note="V2's rule: a seat that ever arrived counts as present, leaver or not"),
    M("trigger_as_first_leaver", "S28 first_leaver",
      E(MAIN, L(24, "ORDER BY fl.left_at, fl.slot LIMIT 1),"),
        L(24, "ORDER BY fl.left_at DESC, fl.slot LIMIT 1),")),
      note="the latest leaver, the one whose leave triggers the close"),
], T("distinct_on",
     E(MAIN, _FL,
       L(7, "first_leaver = (SELECT DISTINCT ON (fl.lobby_id) fl.player_id"
            " FROM ffa_assembly_seats fl")
       + L(24, "WHERE fl.lobby_id = ffa_lobbies.id AND fl.left_at IS NOT NULL")
       + L(24, "ORDER BY fl.lobby_id, fl.left_at, fl.slot),")),
     E(MAIN, _FB,
       L(7, "first_leave_label = (SELECT DISTINCT ON (fb.lobby_id)"
            " COALESCE(NULLIF(fb.left_label, ''), fb.left_cause)")
       + L(30, "FROM ffa_assembly_seats fb")
       + L(29, "WHERE fb.lobby_id = ffa_lobbies.id AND fb.left_at IS NOT NULL")
       + L(29, "ORDER BY fb.lobby_id, fb.left_at, fb.slot),"))))

# -- S29 -------------------------------------------------------------------
_NOTICE_IF = ('    if row is not None:\n'
              '        outcome = ("reformed" if row["reformed_to"] is not None\n')
_NOTICE_SET = ('        out["asm_notice"] = {"lobby_id": str(row["lobby_id"]), "outcome": outcome,'
               ' "upload": 1}\n'
               '    return out\n')
_NOTICE_SQL = ('            "SELECT s.lobby_id, l.reformed_to, l.short_started_at"\n'
               '            "  FROM ffa_assembly_seats s JOIN ffa_lobbies l ON l.id = s.lobby_id"\n'
               '            " WHERE s.player_id = :pid AND s.verdict = \'excluded\'"\n'
               '            "   AND s.notice_seen_at IS NULL"\n'
               '            "   AND s.verdict_at > NOW() - make_interval(mins => CAST(:w AS integer))"\n'
               '            " ORDER BY s.verdict_at DESC LIMIT 1"),\n')
row("S29", "test_s29_the_notice", [
    M("only_without_a_queue_row", "S29 searching",
      E(MAIN, _NOTICE_IF, _NOTICE_IF.replace(
          "if row is not None:", 'if row is not None and out.get("status") == "not_in_queue":'))),
    M("poll_writes_notice_seen", "S29 rows unchanged",
      E(MAIN, _NOTICE_SET, _NOTICE_SET.replace(
          "    return out\n",
          '        await db.execute(text("UPDATE ffa_assembly_seats SET notice_seen_at = NOW()"\n'
          '                              " WHERE lobby_id = :l AND player_id = :p"),\n'
          '                         {"l": row["lobby_id"], "p": pid})\n'
          '        await db.commit()\n'
          '    return out\n'))),
], T("cte_read",
     E(MAIN, _NOTICE_SQL,
       '            "WITH cand AS ("\n'
       '            "SELECT s.lobby_id, l.reformed_to, l.short_started_at, s.verdict_at"\n'
       '            "  FROM ffa_assembly_seats s JOIN ffa_lobbies l ON l.id = s.lobby_id"\n'
       '            " WHERE s.player_id = :pid AND s.verdict = \'excluded\'"\n'
       '            "   AND s.notice_seen_at IS NULL"\n'
       '            "   AND s.verdict_at > NOW() - make_interval(mins => CAST(:w AS integer)))"\n'
       '            " SELECT lobby_id, reformed_to, short_started_at FROM cand"\n'
       '            " ORDER BY verdict_at DESC LIMIT 1"),\n')))

# -- S30 -------------------------------------------------------------------
_PROJ_RET = '        out["candidates"] = cands\n        return token, out\n'
_PROJ_EXC = ('        return token, out\n'
             '    except Exception:\n'
             '        return token, {"v": 1, "error": True}\n')
_PROJ_LOOP = ('        for key in ("sum_b", "sum_pick", "worst_b", "worst_pick", "gain", "max_regret"):\n'
              '            out[key] = _region_int(raw.get(key))\n')
row("S30", "test_s30_the_region_projection", [
    M("pass_raw_through", "S30 keys",
      E(MAIN, _PROJ_RET, _PROJ_RET.replace("return token, out", "return token, dict(raw, v=1)"))),
    M("keep_the_id", "S30 seats",
      E(MAIN, '            seats.append({"slot": int(slot_of[sid]),\n',
        '            seats.append({"id": sid, "slot": int(slot_of[sid]),\n')),
    M("keep_the_exception_text", "S30 error form",
      E(MAIN, _PROJ_EXC, _PROJ_EXC.replace(
          '    except Exception:\n        return token, {"v": 1, "error": True}\n',
          '    except Exception as _exc:\n'
          '        return token, {"v": 1, "error": True, "text": str(_exc)}\n'))),
], T("comprehension",
     E(MAIN, _PROJ_LOOP,
       '        out.update({key: _region_int(raw.get(key))\n'
       '                    for key in ("sum_b", "sum_pick", "worst_b", "worst_pick", "gain",\n'
       '                                "max_regret")})\n')))

# -- S31 -------------------------------------------------------------------
_EARLY = ('    if (ctx.now - lob["created_at"]).total_seconds() < ASM_EARLY_S:\n'
          '        cls = _asm_classify(ctx)\n')
_REST = ('        rest = sum(1 for p, c in cls.items()\n'
         '                   if p != player_id and c in ("READY", "SPAWNING", "PENDING"))\n')
row("S31", "test_s31_the_leave_before_20", [
    M("verdict_before_20", "S31 kept",
      E(MAIN, _EARLY, _EARLY.replace(
          '    if (ctx.now - lob["created_at"]).total_seconds() < ASM_EARLY_S:\n', "    if False:\n")),
      note="the verdict runs at t = 8 and writes a decision (asm_rule set), which the"
           " lobby-row assertion 'S31 kept' reads before the seat's left_path"),
    M("always_dissolve", "S31 kept",
      E(MAIN, '        if rest < 3:\n            plan.today = True\n',
        '        if True:\n            plan.today = True\n')),
], T("named_remainder",
     E(MAIN, _REST,
       '        _remaining = [p for p, c in cls.items()\n'
       '                      if p != player_id and c in ("READY", "SPAWNING", "PENDING")]\n'
       '        rest = len(_remaining)\n')))

# -- S32 -------------------------------------------------------------------
_GR = ('    if gated and lob.get("start_granted_at") is not None:\n'
       '        plan.started = True\n'
       '        plan.may_dissolve = False\n')
row("S32", "test_s32_the_started_lobby_departure", [
    M("ignore_the_grant", "S32 granted",
      E(MAIN, _GR, _GR.replace('if gated and lob.get("start_granted_at") is not None:',
                               "if False:"))),
], T("grant_through_helper",
     E(MAIN, _GR,
       '    def _granted(row):\n'
       '        return row.get("start_granted_at") is not None\n'
       '    if gated and _granted(lob):\n'
       '        plan.started = True\n'
       '        plan.may_dissolve = False\n')))

# -- S33 -------------------------------------------------------------------
_PIN_SIG = ('async def ffa_queue_leave(request: Request, steam_id: str = Query(...),\n'
            '                          expected_lobby_id: str | None = Query(None),\n'
            '                          cause: str = Query("", max_length=16),\n'
            '                          db: AsyncSession = Depends(get_db)):\n')
_PIN_USE = ('    await _check_steam_session(request, steam_id, db)\n'
            '    # Bug #392 lens find 7: narrowed ONCE, here, so all three writers below\n')
row("S33", "test_s33_the_undeclared_label_at_the_pin", [
    M("declare_label_as_cause", "S33 dissolves",
      E(PIN, _PIN_SIG, _PIN_SIG.replace(
          '                          db: AsyncSession',
          '                          label: str = Query("", max_length=24),\n'
          '                          db: AsyncSession')),
      E(PIN, _PIN_USE, _PIN_USE.replace(
          "    await _check_steam_session(request, steam_id, db)\n",
          "    await _check_steam_session(request, steam_id, db)\n    cause = cause or label\n")),
      note="applied to the pin's own main.py (edf9aee)"),
], T("query_parameter_order",
     E(TST, '{"cause": "", "label": "in_room_exit"}', '{"label": "in_room_exit", "cause": ""}')))

# -- S34 -------------------------------------------------------------------
_PAYLOAD_AGE = '        "server_age_ms": age,\n'
_ANS_AGE = '    ans["server_age_ms"] = ctx.age_now_ms()\n'
_AGE_BODY = ('        base = (self.now - self.lobby["created_at"]).total_seconds()\n'
             '        return max(0, int((base + (time.monotonic() - self.mono)) * 1000))\n')
row("S34", "test_s34_server_age_ms_on_every_answer", [
    M("omit_from_the_lock_payload", "S34", E(MAIN, _PAYLOAD_AGE, "")),
    M("omit_from_the_route_answers", "S34", E(MAIN, _ANS_AGE, "")),
    M("from_verdict_at", "S34",
      E(MAIN, _AGE_BODY,
        '        _va = [s["verdict_at"] for s in self.seats if s.get("verdict_at") is not None]\n'
        '        base = ((max(_va) if _va else self.now) - self.lobby["created_at"]).total_seconds()\n'
        '        return max(0, int(base * 1000))\n')),
], T("named_helper",
     E(MAIN, '\n\nclass _AsmCtx:\n',
       '\n\ndef _asm_age_ms(now, created, mono) -> int:\n'
       '    base = (now - created).total_seconds()\n'
       '    return max(0, int((base + (time.monotonic() - mono)) * 1000))\n'
       '\n\nclass _AsmCtx:\n'),
     E(MAIN, _AGE_BODY,
       '        return _asm_age_ms(self.now, self.lobby["created_at"], self.mono)\n')))

# -- S35 -------------------------------------------------------------------
_PEND_REL = '    for pid in pending:\n        await _asm_release_row(ctx.db, ctx.lid, pid)\n'
_REL_Q = ('    await db.execute(text("DELETE FROM ffa_queue WHERE player_id = :pid AND series_id = :lid"),\n'
          '                     {"pid": player_id, "lid": lobby_id})\n')
row("S35", "test_s35_dissolve_releases_the_pending_seats", [
    M("pending_back_to_searching", "S35 pending released",
      E(MAIN, _PEND_REL,
        '    if pending:\n'
        '        await ctx.db.execute(text("""\n'
        "            UPDATE ffa_queue SET status='searching', series_id=NULL, slot=NULL,\n"
        '                   room_name=NULL, room_region=NULL, matched_at=NULL, joined_at=NOW(),\n'
        '                   held_until=NULL, held_lobby=NULL\n'
        '             WHERE series_id = :lid AND player_id = ANY(:ids)\n'
        '        """), {"lid": ctx.lid, "ids": pending})\n')),
], T("delete_using",
     E(MAIN, _REL_Q,
       '    await db.execute(text("DELETE FROM ffa_queue q USING (SELECT CAST(:pid AS uuid) AS pid) x"\n'
       '                          " WHERE q.player_id = x.pid AND q.series_id = :lid"),\n'
       '                     {"pid": player_id, "lid": lobby_id})\n')))

# -- S36a-k: one sub-row per closer, all on the one started-lobby node -------
_S36 = "test_s36_every_closer_on_a_started_lobby"
_JAN_SEL = L(31, "AND l.start_granted_at IS NULL")
_JAN_UPD = L(35, "AND start_granted_at IS NULL")
row("S36a", _S36, [
    M("drop_the_grant_terms", "S36 a", E(MAIN, _JAN_SEL, ""), E(MAIN, _JAN_UPD, ""),
      note="row 1's two terms, the candidate query's and the UPDATE's: either alone is "
           "masked by the other"),
], T("not_is_not_null",
     E(MAIN, _JAN_SEL, L(31, "AND NOT (l.start_granted_at IS NOT NULL)")),
     E(MAIN, _JAN_UPD, L(35, "AND NOT (start_granted_at IS NOT NULL)"))))

_CANCEL_ZERO = ("\"UPDATE ffa_lobbies SET status='completed', completed_at=NOW(),\"",
                "\"UPDATE ffa_lobbies SET status=CASE WHEN games_played = 0 THEN 'canceled'"
                " ELSE 'completed' END, completed_at=NOW(),\"")
_DISP_WHERE = L(24, "WHERE l.status = 'active'") + L(26, "AND COALESCE(")
_DISP_UPD = (L(20, "await db.execute(text(")
             + L(24, "\"UPDATE ffa_lobbies SET status='completed', completed_at=NOW(),\"")
             + L(24, "+ _FFA_CLOSE_RECORD_SET +")
             + L(24, "\" WHERE id = :lid AND status = 'active'\"),")
             + L(24, '{"lid": r[0], "rec_path": "dispersed_close", "rec_trigger": "janitor"})')
             + L(20, 'await _reconcile_ffa_lobby_bets(db, r[0], "dispersed close")'))
row("S36b", _S36, [
    M("candidate_excludes_started", "S36 b",
      E(MAIN, _DISP_WHERE, L(24, "WHERE l.status = 'active'")
        + L(26, "AND l.start_granted_at IS NULL") + L(26, "AND COALESCE("))),
    M("zero_games_cancels", "S36 b", E(MAIN, _DISP_UPD, _DISP_UPD.replace(*_CANCEL_ZERO))),
], T("named_local",
     E(MAIN, _DISP_UPD, L(20, "_disp_lid = r[0]") + _DISP_UPD.replace(
         '{"lid": r[0],', '{"lid": _disp_lid,').replace(
         "_reconcile_ffa_lobby_bets(db, r[0],", "_reconcile_ffa_lobby_bets(db, _disp_lid,"))))

_QUIET_WHERE = (L(21, "WHERE l.status = 'active'")
                + L(23, "AND l.created_at < NOW() - INTERVAL '6 minutes'"))
_QUIET_UPD = (L(20, "await db.execute(text(")
              + L(24, "\"UPDATE ffa_lobbies SET status='completed', completed_at=NOW(),\"")
              + L(24, "+ _FFA_CLOSE_RECORD_SET +")
              + L(24, "\" WHERE id=:lid AND status='active'\"),")
              + L(24, '{"lid": qrow["id"], "rec_path": "quiet_close", "rec_trigger": "janitor"})')
              + L(20, 'await _reconcile_ffa_lobby_bets(db, qrow["id"], "nobody online close")'))
row("S36c", _S36, [
    M("candidate_excludes_started", "S36 c",
      E(MAIN, _QUIET_WHERE, _QUIET_WHERE + L(23, "AND l.start_granted_at IS NULL"))),
    M("zero_games_cancels", "S36 c", E(MAIN, _QUIET_UPD, _QUIET_UPD.replace(*_CANCEL_ZERO))),
], T("named_local",
     E(MAIN, _QUIET_UPD, L(20, '_quiet_lid = qrow["id"]') + _QUIET_UPD.replace(
         '{"lid": qrow["id"],', '{"lid": _quiet_lid,').replace(
         '_reconcile_ffa_lobby_bets(db, qrow["id"],', "_reconcile_ffa_lobby_bets(db, _quiet_lid,"))))

_MD0 = (L(16, "WHERE id=:lid AND status='active' AND games_played = 0")
        + L(18, 'AND start_granted_at IS NULL"""),'))
row("S36d", _S36, [
    M("drop_the_grant_term", "S36 d",
      E(MAIN, _MD0, L(16, "WHERE id=:lid AND status='active' AND games_played = 0\"\"\"),"))),
], T("not_is_not_null",
     E(MAIN, _MD0, _MD0.replace("AND start_granted_at IS NULL",
                                "AND NOT (start_granted_at IS NOT NULL)"))))

_MD1 = L(18, 'AND (games_played > 0 OR start_granted_at IS NOT NULL)"""),')
row("S36e", _S36, [
    M("drop_the_started_term", "S36 e", E(MAIN, _MD1, L(18, 'AND (games_played > 0)"""),'))),
], T("not_is_null",
     E(MAIN, _MD1, _MD1.replace("OR start_granted_at IS NOT NULL",
                                "OR NOT (start_granted_at IS NULL)"))))

_LD = L(16, "\" WHERE id=:lid AND status='active' AND start_granted_at IS NULL\"")
row("S36f", _S36, [
    M("drop_the_grant_term", "S36 f", E(MAIN, _LD, L(16, "\" WHERE id=:lid AND status='active'\"")),
      note="reddens on the fixture's ungated pass, where the statement's term is the only "
           "guard"),
], T("not_is_not_null",
     E(MAIN, _LD, _LD.replace("AND start_granted_at IS NULL",
                              "AND NOT (start_granted_at IS NOT NULL)"))))

_LIVE5 = L(29, "or (_asm_plan is not None and _asm_plan.started))")
_GLN = L(12, "game_live_now = (_group_game_positively_live(str(lobby_id))")
row("S36g", _S36, [
    M("drop_the_live_term", "S36 g", E(MAIN, _LIVE5, L(29, "or False)")),
      note="the else branch restored on a started gated lobby (I2 writer 5's live term)"),
], T("named_local",
     E(MAIN, _GLN, L(12, "_glid = str(lobby_id)")
       + L(12, "game_live_now = (_group_game_positively_live(_glid)"))))

_SIT = L(32, 'or lrow["start_granted_at"] is not None):')
row("S36h", _S36, [
    M("drop_the_started_extension", "S36 h", E(MAIN, _SIT, L(32, "or False):"))),
], T("not_is_null", E(MAIN, _SIT, L(32, 'or not (lrow["start_granted_at"] is None)):'))))

_DEAD9 = L(27, 'and lrow["start_granted_at"] is None)')
_FAIL9 = L(18, 'and lrow["start_granted_at"] is None   # I3 row 9')
row("S36i", _S36, [
    M("drop_the_stale_term", "S36 i", E(MAIN, _DEAD9, L(27, "and True)")),
      note="row 9's first input, zero_game_stale"),
    M("drop_the_failed_term", "S36 i", E(MAIN, _FAIL9, ""),
      note="row 9's second input, assembly_failed",
      equivalent="masked by I3 row 8: the elif runs only when the sitting-over if is"
                 " false, and with all_polling true that needs games_played = 0 AND"
                 " start_granted_at IS NULL, so the dropped conjunct is implied; with"
                 " all_polling false the elif's own first conjunct is false. The double"
                 " mutant drop_rows_8_and_9 below removes the mask and goes red"),
    M("drop_rows_8_and_9", "S36 i", E(MAIN, _SIT, L(32, "or False):")), E(MAIN, _FAIL9, ""),
      note="row 8's started extension and row 9's failed term together: the started"
           " lobby reaches the assembly_failed branch and is canceled"),
], T("not_is_not_null",
     E(MAIN, _DEAD9, L(27, 'and not (lrow["start_granted_at"] is not None))')),
     E(MAIN, _FAIL9, L(18, 'and not (lrow["start_granted_at"] is not None)   # I3 row 9'))))

row("S36jk", _S36, [
    M("delete_veto_3", "S36 jk", E(MAIN, _VETO3, ""),
      note="one mutant for rows 10 and 11: the tag names both fixtures deciding"),
], T("named_local",
     E(MAIN, _VETO3, '    _granted_at = lob.get("start_granted_at")\n'
                     '    if _granted_at is not None:\n'
                     '        return ans\n')))

# -- S37: one node per fixture -----------------------------------------------


def _n37(case):
    return PG + "test_s37_identity_and_substitution[%s]" % case


_RESOLVE = ('    by_steam = {s["seat_steam_id"]: s for s in ctx.seats}\n'
            '    resolved, anon = [], 0\n'
            '    for e in req.census:\n'
            '        s = by_steam.get(e.s) if e.s else None\n'
            '        if s is None:\n'
            '            anon += 1\n'
            '            continue\n'
            '        resolved.append((int(s["slot"]), int(e.a), int(e.b), int(e.k)))\n')
_V3 = (E(MAIN, _RESOLVE, _RESOLVE.replace(
           '            anon += 1\n',
           '            resolved.append((-1, int(e.a), int(e.b), int(e.k)))\n')),
       E(MAIN, _LISTS, _LISTS.replace("sl == slot and a == actor",
                                      "sl in (slot, -1) and a == actor")))
_SEEN_REG = ('        if _asm_fresh(q, now) and q["census_region"] == p["claim_region"] \\\n'
             '                and _asm_lists(q, p["slot"], p["actor_claim"]):\n')
_BIND_CONF = ('        if not _asm_claim_seen(p, ctx.seats, ctx.now):\n'
              '            continue\n'
              '        if any(r["player_id"] != p["player_id"]\n')
_CLS_CORR = '        elif _asm_corroborated(p, ctx.seats, ctx.now) and not (\n'
row("S37", ["test_s37_identity_and_substitution[%s]" % c for c in ("i", "ii", "iii", "iv")], [
    M("v3_path", "S37 ii substitution", *_V3, nodes=[_n37("ii")],
      note="V3's path: an anonymous entry is kept (slot -1) and corroborates any seat "
           "claiming its actor, so X binds"),
    M("v3_path_on_fixture_i", "S37 i bound", *_V3, nodes=[_n37("i")],
      note="the same mutant on fixture (i): the fourth seat binds from anonymous entries"),
    M("drop_the_region_term", "S37 iv region",
      E(MAIN, _SEEN_REG, _SEEN_REG.replace(' and q["census_region"] == p["claim_region"]', "")),
      nodes=[_n37("iv")]),
    M("second_claimant_binds", "S37 iii second unbound",
      E(MAIN, _BIND_CONF, _BIND_CONF.replace('        if any(r["player_id"]',
                                             '        if False and any(r["player_id"]')),
      nodes=[_n37("iii")]),
    M("two_others_path", "S37 ii absent",
      E(MAIN, _CLS_CORR,
        '        elif (_asm_corroborated(p, ctx.seats, ctx.now)\n'
        '              or sum(1 for q in ctx.seats if q["player_id"] != p["player_id"]\n'
        '                     and _asm_fresh(q, ctx.now)\n'
        '                     and int(p["slot"]) in (q["census_slots"] or [])) >= 2) and not (\n'),
      nodes=[_n37("ii")],
      note="V2's two-others path: two peers listing the slot stand in for the seat's own "
           "census and binding"),
], T("comprehension",
     E(MAIN, _RESOLVE,
       '    by_steam = {s["seat_steam_id"]: s for s in ctx.seats}\n'
       '    _pairs = [(by_steam.get(e.s) if e.s else None, e) for e in req.census]\n'
       '    resolved = [(int(s["slot"]), int(e.a), int(e.b), int(e.k))\n'
       '                for s, e in _pairs if s is not None]\n'
       '    anon = sum(1 for s, _e in _pairs if s is None)\n'),
     note="the resolution is Python here, not a statement: the twin re-expresses the loop "
          "as comprehensions"))

# -- S38 -------------------------------------------------------------------
_CLS_LEFT = ('        if p["left_at"] is not None or v == "left" or not p["in_queue"]:\n'
             '            out[p["player_id"]] = "LEFT"\n')
_IRE = ('    if not pre_room and _is_in_room_exit_cause(cause):\n'
        '        plan.path = "departure"\n'
        '        return plan\n')
row("S38", "test_s38_the_leave_cause", [
    M("drop_the_grant_from_the_dissolve", "S38 i",
      E(MAIN, _GR, _GR.replace('if gated and lob.get("start_granted_at") is not None:',
                               "if False:")),
      E(MAIN, _LD, L(16, "\" WHERE id=:lid AND status='active'\"")),
      note="the dissolve predicate is the plan's grant test and the statement's term; "
           "both are dropped"),
    M("verdict_reads_the_cause", "S38 ii",
      E(MAIN, _CLS_LEFT,
        '        if (p["left_at"] is not None or v == "left" or not p["in_queue"]) \\\n'
        '                and p["left_cause"] != "in_room_exit":\n'
        '            out[p["player_id"]] = "LEFT"\n'),
      note="the verdict reads the persisted cause: an in-room exit is not LEFT"),
], T("cause_in_a_local",
     E(MAIN, _IRE, '    _in_room = _is_in_room_exit_cause(cause)\n'
                   '    if not pre_room and _in_room:\n'
                   '        plan.path = "departure"\n'
                   '        return plan\n')))

# -- S39 -------------------------------------------------------------------
row("S39", "test_s39_rule_s_ignores_the_admission_hold", [
    M("s_honours_the_hold", "S39 46.0",
      E(MAIN, _S_LINE, _S_LINE.replace(">= 3:", ">= 3 and not hold_adm:"))),
    M("s_at_47", "S39 46.0", E(MAIN, "ASM_SHORT_ABS_S = 46 ", "ASM_SHORT_ABS_S = 47 ")),
], T("interval_from_constant",
     E(MAIN, _S_LINE, _S_LINE.replace(
         "t >= ASM_SHORT_ABS_S",
         '(ctx.now - lob["created_at"]) >= timedelta(seconds=ASM_SHORT_ABS_S)'))))

# -- S40 -------------------------------------------------------------------
_ADM_HEAD = ('    for p in adm:\n'
             '        if not _asm_fresh(p, ctx.now) or not _asm_claim_seen(p, ctx.seats, ctx.now):\n'
             '            continue\n'
             '        claim = (p["actor_claim"], p["claim_region"])\n')
_ADM_SQL = ('            "UPDATE ffa_assembly_seats"\n'
            '            "   SET actor_nr = CAST(:a AS smallint), actor_region = :r,"\n'
            '            "       verdict = \'admitted_late\', late_admitted_at = CAST(:now AS timestamptz),"\n'
            '            "       late_game = CAST(:g AS smallint), verdict_at = CAST(:now AS timestamptz)"\n'
            '            " WHERE lobby_id = :lid AND player_id = :pid AND verdict = \'admissible\'"),\n'
            '            {"a": claim[0], "r": claim[1], "now": ctx.now, "g": g,\n'
            '             "lid": ctx.lid, "pid": p["player_id"]})\n')
_ADM_UPD = '        res = await ctx.db.execute(text(\n' + _ADM_SQL
_LATE = '             if s["verdict"] == "admitted_late" and s["late_body_game"] is None\n'
row("S40", "test_s40_the_admission", [
    M("own_census_alone", "S40 own only",
      E(MAIN, _ADM_HEAD, _ADM_HEAD.replace(
          " or not _asm_claim_seen(p, ctx.seats, ctx.now):", ":"))),
    M("two_peers_without_own", "S40 peers only",
      E(MAIN, _ADM_HEAD,
        '    for p in adm:\n'
        '        _peers = [q for q in ctx.seats if q["player_id"] != p["player_id"]\n'
        '                  and _asm_fresh(q, ctx.now)\n'
        '                  and int(p["slot"]) in (q["census_slots"] or [])]\n'
        '        if len(_peers) >= 2 and not _asm_fresh(p, ctx.now):\n'
        '            claim = ([a for sl, a in zip(_peers[0]["census_slots"],\n'
        '                                         _peers[0]["census_actors"])\n'
        '                      if sl == int(p["slot"])][0], _peers[0]["census_region"])\n'
        '        elif not _asm_fresh(p, ctx.now) or not _asm_claim_seen(p, ctx.seats, ctx.now):\n'
        '            continue\n'
        '        else:\n'
        '            claim = (p["actor_claim"], p["claim_region"])\n'),
      note="V3's path: two fresh peer censuses listing the slot stand in for the seat's "
           "own census and claim"),
    M("verdict_committed_before_the_binding", "S40 fault",
      E(MAIN, _ADM_UPD,
        '        res = await ctx.db.execute(text(\n'
        '            "UPDATE ffa_assembly_seats"\n'
        '            "   SET verdict = \'admitted_late\', late_admitted_at = CAST(:now AS timestamptz),"\n'
        '            "       late_game = CAST(:g AS smallint), verdict_at = CAST(:now AS timestamptz)"\n'
        '            " WHERE lobby_id = :lid AND player_id = :pid AND verdict = \'admissible\'"),\n'
        '            {"now": ctx.now, "g": g, "lid": ctx.lid, "pid": p["player_id"]})\n'
        '        await ctx.db.commit()\n'
        '        await ctx.db.execute(text(\n'
        '            "UPDATE ffa_assembly_seats SET actor_nr = CAST(:a AS smallint), actor_region = :r"\n'
        '            " WHERE lobby_id = :lid AND player_id = :pid"),\n'
        '            {"a": claim[0], "r": claim[1], "lid": ctx.lid, "pid": p["player_id"]})\n')),
    M("out_of_late", "S40 late",
      E(MAIN, _LATE, _LATE.replace('if s["verdict"] == "admitted_late"', "if False"))),
    M("entered_removes_the_seat", "S40 entered removes nothing",
      E(MAIN, _LATE, _LATE.replace(' is None\n', ' is None and s["late_entered_at"] is None\n'))),
], T("helper",
     E(MAIN, _ADM_UPD, '        res = await _asm_admit_write(ctx, p, claim, g)\n'),
     E(MAIN, "\n\nasync def _ffa_admission_check(ctx) -> list:\n",
       "\n\nasync def _asm_admit_write(ctx, p, claim, g):\n"
       "    return await ctx.db.execute(text(\n"
       + _ADM_SQL.replace("\n            ", "\n        ").replace("            \"UPDATE", "        \"UPDATE", 1)
       + "\n\nasync def _ffa_admission_check(ctx) -> list:\n"),
     note="the admission's statement issued by a helper, identical text and binds"))


# -- S41: one node per route -------------------------------------------------


def _n41(route):
    return PG + "test_s41_the_expiry_at_a[%s]" % route


_SS_LEFT = ('    if left:\n'
            '        await ctx.db.execute(text(\n'
            '            "UPDATE ffa_lobbies SET departed_ids = (SELECT ARRAY(SELECT DISTINCT e FROM"\n'
            '            " unnest(departed_ids || CAST(:ids AS uuid[])) e)) WHERE id = :lid"),\n'
            '            {"lid": ctx.lid, "ids": left})\n')
_SS_ADM = E(MAIN, _SS_LEFT, _SS_LEFT.replace("    if left:\n", "    if left or admissible:\n")
            .replace('"ids": left})', '"ids": left + admissible})'))
_EXP_REL = ('        await _asm_release_row(db, lobby_id, r["player_id"])\n'
            '        out.append((int(r["slot"]), t_ms))\n')
_EXP_DEP = ('        "UPDATE ffa_lobbies SET departed_ids = (SELECT ARRAY(SELECT DISTINCT e FROM"\n'
            '        " unnest(departed_ids || CAST(:ids AS uuid[])) e)) WHERE id = :lid"),\n'
            '        {"lid": lobby_id, "ids": [r["player_id"] for r in rows]})\n')
_EXP_A = '    if now < lob["created_at"] + timedelta(seconds=ASM_ADMIT_LATE_S):\n'
_ADM_A = '    if ctx.now >= lob["created_at"] + timedelta(seconds=ASM_ADMIT_LATE_S):\n'
_EXP_SEL = ('    lob = (await db.execute(text(\n'
            '        "SELECT status, created_at, short_started_at FROM ffa_lobbies WHERE id = :lid"),\n'
            '        {"lid": lobby_id})).mappings().first()\n')
row("S41", ["test_s41_the_expiry_at_a[%s]" % r
            for r in ("connect", "assembly", "poll", "leave", "report")], [
    M("append_admissible_at_start_short", "S41 139.9 dep", _SS_ADM, nodes=[_n41("connect")],
      note="#686: START-SHORT appends its admissible seats with its LEFT ones"),
    M("skip_the_lease_release", "S41 released",
      E(MAIN, _EXP_REL,
        '        await db.execute(text("DELETE FROM ffa_queue WHERE player_id = :pid AND series_id = :lid"),\n'
        '                         {"pid": r["player_id"], "lid": lobby_id})\n'
        '        out.append((int(r["slot"]), t_ms))\n'), nodes=[_n41("connect")]),
    M("append_twice", "S41 once",
      E(MAIN, _EXP_DEP,
        '        "UPDATE ffa_lobbies SET departed_ids = departed_ids || CAST(:ids AS uuid[])"\n'
        '        " || CAST(:ids AS uuid[]) WHERE id = :lid"),\n'
        '        {"lid": lobby_id, "ids": [r["player_id"] for r in rows]})\n'),
      nodes=[_n41("connect")]),
    M("admit_at_a", "S41 excluded",
      E(MAIN, _EXP_A, _EXP_A.replace("if now < ", "if now <= ")),
      E(MAIN, _ADM_A, _ADM_A.replace("if ctx.now >= ", "if ctx.now > ")),
      nodes=[_n41("assembly")],
      note="A moved past 140.0 for the expiry and the admission together; the assembly "
           "route's admission check then admits the corroborated seat at 140.0"),
    M("admit_after_a_bound_only", "S41 excluded", E(MAIN, _ADM_A, "    if False:\n"),
      nodes=[_n41("assembly")],
      equivalent="masked: the lock step of every route that reaches the admission check "
                 "runs the expiry first with the same ctx.now, so no seat is admissible "
                 "when the admission's own bound is read"),
], T("deadline_through_make_interval",
     E(MAIN, _EXP_SEL,
       '    lob = (await db.execute(text(\n'
       '        "SELECT status, created_at, short_started_at,"\n'
       '        "       created_at + make_interval(secs => CAST(:a AS double precision)) AS a_at"\n'
       '        "  FROM ffa_lobbies WHERE id = :lid"),\n'
       '        {"lid": lobby_id, "a": ASM_ADMIT_LATE_S})).mappings().first()\n'),
     E(MAIN, _EXP_A, '    if now < lob["a_at"]:\n')))

# -- S42 -------------------------------------------------------------------
_HOST_Q = ('            "SELECT player_id FROM ffa_queue WHERE series_id = :lid AND player_id = ANY(:ids)"\n'
           '            " ORDER BY joined_at, CAST(player_id AS text) LIMIT 1"),\n')
_HOST_BLOCK = ('        host = (await ctx.db.execute(text(\n' + _HOST_Q
               + '            {"lid": ctx.lid, "ids": roster})).scalar()\n')
row("S42", "test_s42_start_shorts_rows", [
    M("append_the_admissible_seats", "S42 departed", _SS_ADM),
    M("host_by_slot", "S42 host",
      E(MAIN, _HOST_Q, _HOST_Q.replace(" ORDER BY joined_at, CAST(player_id AS text) LIMIT 1",
                                       " ORDER BY slot LIMIT 1"))),
    M("host_by_sort_key", "S42 host",
      E(MAIN, _HOST_BLOCK,
        '        host = min((p for p in ctx.seats if p["player_id"] in roster),\n'
        '                   key=lambda p: _ffa_sort_key(p["seat_steam_id"]))["player_id"]\n')),
    M("omit_bets_disabled", "S42 start",
      E(MAIN, '        "       bets_disabled = TRUE, asm_rule = :r"\n', '        "       asm_rule = :r"\n'),
      note="the CHECK (short_started_at IS NULL OR bets_disabled) rolls START-SHORT back"),
], T("host_through_a_cte",
     E(MAIN, _HOST_Q,
       '            "WITH r AS (SELECT player_id, joined_at FROM ffa_queue"\n'
       '            "            WHERE series_id = :lid AND player_id = ANY(:ids))"\n'
       '            " SELECT player_id FROM r ORDER BY joined_at, CAST(player_id AS text) LIMIT 1"),\n')))

# -- S43 -------------------------------------------------------------------
_W7A = '        if admitted_for_g and (r["late_body_game"] is None or g <= int(r["late_body_game"])):\n'
_W7_SEL = ('        "SELECT p.steam_id, s.slot, s.start_roster, s.late_admitted_at, s.late_game,"\n'
           '        "       s.late_body_game, s.gone_game, s.lag_games"\n')
_W7_CLAIM = (E(MAIN, _W7_SEL, _W7_SEL.replace("s.lag_games\"", "s.lag_games, s.late_game_claim\"")),
             E(MAIN, _W7A, _W7A.replace('r["late_body_game"]', 'r["late_game_claim"]')))
_ENT_COPY = ('        "UPDATE ffa_assembly_seats SET entered_game = late_body_game"\n'
             '        " WHERE lobby_id = :lid AND late_body_game IS NOT NULL AND entered_game IS NULL"\n'
             '        "   AND late_body_game <= CAST(:g AS smallint)"), {"lid": lobby_uuid, "g": int(g)})\n')
row("S43", "test_s43_writer_7_on_the_late_body_evidence", [
    M("entered_from_the_report", "S43 i",
      E(MAIN, _W7A,
        '        if admitted_for_g and r["late_body_game"] is None and sid not in unrated:\n'
        '            await db.execute(text(\n'
        '                "UPDATE ffa_assembly_seats SET late_body_game = CAST(:g AS smallint)"\n'
        '                " WHERE lobby_id = :lid AND player_id ="\n'
        '                "       (SELECT id FROM players WHERE steam_id = :sid)"),\n'
        '                {"g": g, "lid": lobby_uuid, "sid": sid})\n' + _W7A),
      note="V4's path: a report listing the seat present records the game it entered"),
    M("unrated_on_late_admitted_at", "S43 ii",
      E(MAIN, _W7A, '        if r["late_admitted_at"] is not None:\n')),
    M("read_late_game_claim", "S43 ii", *_W7_CLAIM,
      note="rule (a) keyed on the client's claimed game"),
    M("copy_late_game_claim", "S43 iii copy",
      E(MAIN, _ENT_COPY, _ENT_COPY.replace("late_body_game", "late_game_claim"))),
    M("skip_writer_7_b", "S43 iv",
      E(MAIN, '        elif short and not r["start_roster"] and not admitted_for_g:\n',
        '        elif False:\n')),
], T("local_compare",
     E(MAIN, _W7A, '        _lbg = r["late_body_game"]\n'
                   '        if admitted_for_g and (_lbg is None or g <= int(_lbg)):\n')))

# -- S44 -------------------------------------------------------------------
_SN = '    start_n = len(roster) if short else int(lob["player_count"] or len(roster))\n'
_RF = '              and not (short and before_a and s["gone_game"] is not None)]\n'
_BA = '    before_a = ctx.now < lob["created_at"] + timedelta(seconds=ASM_ADMIT_LATE_S)\n'
_SPF = ('        if req.phase == "spawn":\n'
        '            sets.append("spawn_failed_at = COALESCE(spawn_failed_at, CAST(:now AS timestamptz))")\n')
row("S44", "test_s44_the_live_start_n", [
    M("start_n_at_the_decision", "S44 lowered",
      E(MAIN, _SN, '    start_n = (sum(1 for s in ctx.seats if s["start_roster"]) if short\n'
                   '               else int(lob["player_count"] or len(roster)))\n')),
    M("lower_on_the_leave", "S44 after leave",
      E(MAIN, _RF, '              and not (short and before_a and (s["gone_game"] is not None\n'
                   '                                               or s["left_at"] is not None))]\n'),
      note="V10's path (N8)"),
    M("lower_on_bodiless", "S44 seeded bodiless",
      E(MAIN, _RF, '              and not (short and before_a and (s["gone_game"] is not None\n'
                   '                                               or s["bodiless_at"] is not None))]\n'),
      note="V4's path"),
    M("move_on_its_own_failed_spawn", "S44 no body start_n",
      E(MAIN, _SPF, _SPF + '            sets += ["gone_game = COALESCE(gone_game, CAST(1 AS smallint))",\n'
                           '                     "gone_path = COALESCE(gone_path, \'witness\')"]\n'),
      note="the seat's own failed phase=spawn writes its gone record"),
    M("lower_a_full_grant", "S44 full grant",
      E(MAIN, _RF, '              and not (before_a and s["gone_game"] is not None)]\n'),
      E(MAIN, _SN, '    start_n = len(roster)\n')),
    M("move_after_a", "S44 after A", E(MAIN, _BA, '    before_a = True\n')),
], T("count_by_generator",
     E(MAIN, _SN, '    start_n = sum(1 for _r in roster) if short else int(lob["player_count"] or len(roster))\n'),
     note="start_n is counted in Python here: the twin re-expresses the count"))

# -- S45 -------------------------------------------------------------------
_SPOK = '        ok = t < ASM_SPAWN_EARLY_S or _asm_corroborated(me, ctx.seats, ctx.now)\n'
_SPAGE = '            ans["spawn_ok_age_ms"] = max(0, int((at - lob["created_at"]).total_seconds() * 1000))\n'
row("S45", "test_s45_spawn_ok_and_its_window", [
    M("le_15", "S45 15.0", E(MAIN, _SPOK, _SPOK.replace("t < ASM_SPAWN_EARLY_S", "t <= ASM_SPAWN_EARLY_S"))),
    M("one_in_admitting", "S45",
      E(MAIN, '        ans.update(status="admitting", granted=_asm_answer_lists(ctx)["granted"], spawn_ok=0)\n',
        '        ans.update(status="admitting", granted=_asm_answer_lists(ctx)["granted"], spawn_ok=1)\n')),
    M("rewritten_on_every_answer", "S45 14",
      E(MAIN, '        "UPDATE ffa_assembly_seats SET spawn_ok_at = COALESCE(spawn_ok_at, CAST(:now AS timestamptz))"\n',
        '        "UPDATE ffa_assembly_seats SET spawn_ok_at = CAST(:now AS timestamptz)"\n')),
    M("omitted_on_the_assembly_route", "S45 11",
      E(MAIN, _ANS_AGE, _ANS_AGE + '    if ctx.route == "assembly":\n'
                                   '        ans.pop("spawn_ok_age_ms", None)\n')),
], T("threshold_and_age_by_name",
     E(MAIN, _SPOK, '        ok = ((ctx.now - lob["created_at"]) < timedelta(seconds=ASM_SPAWN_EARLY_S)\n'
                    '              or _asm_corroborated(me, ctx.seats, ctx.now))\n'),
     E(MAIN, _SPAGE, '            ans["spawn_ok_age_ms"] = _asm_ms_since(at, lob["created_at"])\n'),
     E(MAIN, '\n\n_ASM_STAMP_SQL = {\n',
       '\n\ndef _asm_ms_since(at, created) -> int:\n'
       '    return max(0, int((at - created).total_seconds() * 1000))\n'
       '\n\n_ASM_STAMP_SQL = {\n')))

# -- S46: one node per fixture -----------------------------------------------


def _n46(case):
    return PG + "test_s46_the_body_rule[%s]" % case


_GRACE_C = "ASM_SPAWN_GRACE_S = 23 "
_OTHERS = '                  if q["player_id"] != p["player_id"] and _asm_nonfinal(q)\n'
row("S46", ["test_s46_the_body_rule[%s]" % c for c in ("i", "i-late", "iii", "iv", "v")], [
    M("grace_15", "S46 v +49", E(MAIN, _GRACE_C, "ASM_SPAWN_GRACE_S = 15 "), nodes=[_n46("v")]),
    M("grace_22", "S46 v", E(MAIN, _GRACE_C, "ASM_SPAWN_GRACE_S = 22 "), nodes=[_n46("v")],
      note="V6: the two censuses built at +55.5 count"),
    M("grace_on_census_at", "S46 i 22.9",
      E(MAIN, '                     and q["census_seen_at"] >= grace\n',
        '                     and q["census_at"] >= grace\n'), nodes=[_n46("i-late")]),
    M("accept_one_census", "S46 i one census",
      E(MAIN, '        if misses >= 2:\n', '        if misses >= 1:\n'), nodes=[_n46("i")]),
    M("count_the_seats_own", "S46 iii own bodiless",
      E(MAIN, _OTHERS, '                  if _asm_nonfinal(q)\n'), nodes=[_n46("iii")]),
    M("read_a_final_rows_census", "S46 iv final bodiless",
      E(MAIN, _OTHERS, '                  if q["player_id"] != p["player_id"]\n'), nodes=[_n46("iv")]),
], T("grace_by_name",
     E(MAIN, '        grace = ref + timedelta(seconds=ASM_SPAWN_GRACE_S)\n',
       '        grace = ref + timedelta(seconds=1) * ASM_SPAWN_GRACE_S\n')))

# -- S47 -------------------------------------------------------------------
_ENT = ('        sets += ["late_game_claim = CASE WHEN late_entered_at IS NULL"\n'
        '                 " THEN CAST(:g AS smallint) ELSE late_game_claim END",\n'
        '                 "late_entered_at = COALESCE(late_entered_at, CAST(:now AS timestamptz))"]\n')
row("S47", "test_s47_entered_is_telemetry", [
    M("entered_writes_late_game", "S47 cell",
      E(MAIN, _ENT, _ENT + '        sets.append("late_game = CAST(:g AS smallint)")\n')),
    M("entered_writes_late_body_game", "S47 cell",
      E(MAIN, _ENT, _ENT + '        sets.append("late_body_game = COALESCE(late_body_game, CAST(:g AS smallint))")\n')),
    M("entered_writes_entered_game", "S47 cell",
      E(MAIN, _ENT, _ENT + '        sets.append("entered_game = COALESCE(entered_game, CAST(:g AS smallint))")\n')),
    M("out_of_late_on_the_post", "S47 answer",
      E(MAIN, _LATE, _LATE.replace(' is None\n', ' is None and s["late_entered_at"] is None\n')),
      note="V4's rule"),
    M("writer_7_reads_the_claim", "S47 rated at game 2", *_W7_CLAIM,
      note="the literal swap unrates the seat in both sittings (no claim reads as None,"
           " which the rule treats as not yet seen), so the two sittings stay equal and"
           " the game-2 rating is what goes red"),
    M("writer_7_prefers_the_claim", "S47 identical",
      E(MAIN, _W7_SEL, _W7_SEL.replace("s.lag_games\"", "s.lag_games, s.late_game_claim\"")),
      E(MAIN, _W7A, _W7A.replace(
          'r["late_body_game"]',
          '(r["late_game_claim"] if r["late_game_claim"] is not None else r["late_body_game"])')),
      note="COALESCE(late_game_claim, late_body_game): the sitting with the POST unrates"
           " game 2 on the claim of 3, the one without rates it"),
], T("claim_in_a_local",
     E(MAIN, '        p["g"] = req.game\n    elif step == "notice_seen":\n',
       '        _claimed = req.game\n        p["g"] = _claimed\n    elif step == "notice_seen":\n')))


# -- S48 -------------------------------------------------------------------
_W7C = '        if rep["late_admitted_at"] is not None or (short and not rep["start_roster"]):\n'
_W7E = '        if g in [int(x) for x in (rep["lag_games"] or [])]:\n'
_LAG = '        ctx.log(f"lag slot={me[\'slot\']} game={req.game} k={req.k} why={req.why}")\n'
_LATE_DETAIL = '                detail="This seat may not report this sitting\'s games", progress=progress)\n'
row("S48", "test_s48_the_sticky_reporter_rule", [
    M("refuse_only_the_entered_game", "S48 sticky",
      E(MAIN, _W7C,
        '        if (rep["late_admitted_at"] is not None or (short and not rep["start_roster"])) \\\n'
        '                and (rep["late_game"] is None or g == int(rep["late_game"])):\n')),
    M("keyed_on_the_clients_cr_late", "S48 late game 1",
      E(MAIN, _W7C, '        if getattr(report, "cr_late", None):\n'),
      note="the report carries no such field: the client-keyed rule refuses nobody"),
    M("drop_e", "S48 lag", E(MAIN, _W7E, '        if False:\n')),
    M("refuse_game_1_once_any_seat_lagged", "S48 lag others",
      E(MAIN, _W7E, '        if any(g in [int(x) for x in (x2["lag_games"] or [])] for x2 in rows):\n')),
    M("lag_step_to_every_seat", "S48 lag row",
      E(MAIN, _LAG, _LAG + '        await ctx.db.execute(text(\n'
                           '            "UPDATE ffa_assembly_seats SET lag_games = ARRAY(SELECT DISTINCT e FROM"\n'
                           '            " unnest(lag_games || CAST(:g AS smallint)) e ORDER BY e) WHERE lobby_id = :lid"),\n'
                           '            {"g": req.game, "lid": ctx.lid})\n')),
], T("detail_helper_and_lag_local",
     E(MAIN, _LATE_DETAIL, '                detail=_asm_late_detail(), progress=progress)\n'),
     E(MAIN, "\n\nasync def _asm_report_rules(",
       "\n\ndef _asm_late_detail() -> str:\n"
       "    return \"This seat may not report this sitting's games\"\n"
       "\n\nasync def _asm_report_rules("),
     E(MAIN, _W7E, '        _lags = [int(x) for x in (rep["lag_games"] or [])]\n'
                   '        if g in _lags:\n')))

# -- S49 -------------------------------------------------------------------
_STARTED = ('        if ctx.lobby.get("start_granted_at") is not None and (\n'
            '                me["start_roster"] or me["late_admitted_at"] is not None):\n')
row("S49", "test_s49_an_unbacked_started", [
    M("write_started_at_unbacked", "S49 i", E(MAIN, _STARTED, '        if True:\n')),
    M("v3_veto_on_started_at", "S49 iii",
      E(MAIN, _VETO3, _VETO3 + '    if any(s.get("started_at") is not None for s in ctx.seats):\n'
                               '        return ans\n')),
    M("a_closer_reads_started_at", "S49 iii",
      E(MAIN, _QUIET_WHERE, _QUIET_WHERE
        + L(23, "AND NOT EXISTS (SELECT 1 FROM ffa_assembly_seats s")
        + L(39, "WHERE s.lobby_id = l.id AND s.started_at IS NOT NULL)")),
      note="the quiet close's candidate query reads started_at"),
], T("backing_in_a_local",
     E(MAIN, _STARTED, '        _backed = ctx.lobby.get("start_granted_at") is not None and (\n'
                       '            me["start_roster"] or me["late_admitted_at"] is not None)\n'
                       '        if _backed:\n')))

# -- S50 -------------------------------------------------------------------
_SEEN_LOOP = ('    for q in seats:\n'
              '        if q["player_id"] == p["player_id"] or not _asm_nonfinal(q):\n'
              '            continue\n'
              '        if _asm_fresh(q, now) and q["census_region"] == p["claim_region"] \\\n'
              '                and _asm_lists(q, p["slot"], p["actor_claim"]):\n'
              '            return True\n'
              '    return False\n')
_TWO_OTHERS = E(MAIN, _CLS_CORR,
                '        elif (_asm_corroborated(p, ctx.seats, ctx.now)\n'
                '              or sum(1 for q in ctx.seats if q["player_id"] != p["player_id"]\n'
                '                     and _asm_fresh(q, ctx.now)\n'
                '                     and int(p["slot"]) in (q["census_slots"] or [])) >= 2) and not (\n')
row("S50", "test_s50_ready_needs_the_seats_own_census", [
    M("two_others_path", "S50 39.9", _TWO_OTHERS,
      note="the seat READY from two peers' entries: the first answer (39.9) already "
           "counts it, before START-SHORT puts it in the roster"),
], T("peer_entries_through_any",
     E(MAIN, _SEEN_LOOP,
       '    return any(q["player_id"] != p["player_id"] and _asm_nonfinal(q)\n'
       '               and _asm_fresh(q, now) and q["census_region"] == p["claim_region"]\n'
       '               and _asm_lists(q, p["slot"], p["actor_claim"]) for q in seats)\n'),
     note="the peer entries are read in Python here: the twin re-expresses the loop"))

# -- S51 -------------------------------------------------------------------
_ALM = ('    left = (lob["created_at"] + timedelta(seconds=ASM_ADMIT_LATE_S) - now).total_seconds()\n'
        '    return max(0, int(left * 1000))\n')
_PAY_ALM = ('        "admit_left_ms": (max(0, int(((created + timedelta(seconds=ASM_ADMIT_LATE_S)) - now)\n'
            + L(38, ".total_seconds() * 1000))"))
row("S51", "test_s51_admit_left_ms", [
    M("omit_from_admitting", "S51",
      E(MAIN, '        plan["admit_left"] = True\n        return plan\n    if st == "D":\n',
        '        return plan\n    if st == "D":\n')),
    M("from_verdict_at", "S51",
      E(MAIN, _ALM, '    _va = max((s["verdict_at"] for s in ctx.seats if s.get("verdict_at") is not None),\n'
                    '              default=lob["created_at"])\n'
                    '    left = (_va + timedelta(seconds=ASM_ADMIT_LATE_S) - now).total_seconds()\n'
                    '    return max(0, int(left * 1000))\n')),
], T("through_a_helper",
     E(MAIN, _ALM, '    return _asm_ms_left(lob["created_at"] + timedelta(seconds=ASM_ADMIT_LATE_S), now)\n'),
     E(MAIN, _PAY_ALM,
       '        "admit_left_ms": (_asm_ms_left(created + timedelta(seconds=ASM_ADMIT_LATE_S), now)\n'),
     E(MAIN, "\n\ndef _asm_admit_left_ms(ctx) -> int:\n",
       "\n\ndef _asm_ms_left(deadline, now) -> int:\n"
       "    return max(0, int((deadline - now).total_seconds() * 1000))\n"
       "\n\ndef _asm_admit_left_ms(ctx) -> int:\n")))

# -- S52: one node per part ----------------------------------------------------


def _n52(part):
    return PG + "test_s52_the_final_row_matrix[%s]" % part


_SEEN_HEAD = ('        if q["player_id"] == p["player_id"] or not _asm_nonfinal(q):\n'
              '            continue\n'
              '        if _asm_fresh(q, now) and q["census_region"] == p["claim_region"] \\\n')
_ARR = '    elif step == "arrived":\n        region = ctx.lobby["region"]\n'
_BOUND_SELF = ('    if (me["actor_claim"], me["claim_region"]) == (me["actor_nr"], me["actor_region"]):\n'
               '        return\n'
               '    if _asm_claim_seen(me, ctx.seats, ctx.now):\n')
row("S52", ["test_s52_the_final_row_matrix[%s]" % p for p in ("matrix", "gone", "classification")], [
    M("final_rows_census_in_the_classification", "S52 classification P unbound",
      E(MAIN, _SEEN_HEAD, _SEEN_HEAD.replace(
          '        if q["player_id"] == p["player_id"] or not _asm_nonfinal(q):\n',
          '        if q["player_id"] == p["player_id"]:\n')),
      nodes=[_n52("classification")], note="the V4 mutant: F's census corroborates P"),
    M("arrived_in_e_changes_the_verdict", "S52 cell",
      E(MAIN, _ARR, '    elif step == "arrived":\n'
                    '        if state == "E":\n'
                    '            sets.append("verdict = NULL")\n'
                    '        region = ctx.lobby["region"]\n'), nodes=[_n52("matrix")]),
    M("entered_in_c_writes", "S52 cell",
      E(MAIN, _ENT, _ENT + '        if state == "C":\n'
                           '            sets.append("late_game = CAST(:g AS smallint)")\n'),
      nodes=[_n52("matrix")]),
    M("the_bound_actors_own_claim_fires", "S52 gone bound claim",
      E(MAIN, _BOUND_SELF, '    if _asm_claim_seen(me, ctx.seats, ctx.now):\n'),
      nodes=[_n52("gone")], note="V9's claim path"),
], T("census_rows_by_name",
     E(MAIN, '    for q in seats:\n' + _SEEN_HEAD,
       '    _census_rows = [q for q in seats\n'
       '                    if q["player_id"] != p["player_id"] and _asm_nonfinal(q)]\n'
       '    for q in _census_rows:\n'
       '        if _asm_fresh(q, now) and q["census_region"] == p["claim_region"] \\\n'),
     note="the classification's census rows selected into a named list"))


# -- S53 -------------------------------------------------------------------
_ASM_ROUTE = ('async def ffa_lobby_assembly(lobby_id: uuid.UUID, req: _AsmAssemblyReq, request: Request,\n'
              '                             db: AsyncSession = Depends(get_asm_db)):\n')
_ASM_ENGINE = ('    return create_async_engine(\n'
               '        url,\n'
               '        echo=False,\n'
               '        pool_size=ASM_POOL_SIZE,\n'
               '        max_overflow=ASM_POOL_OVERFLOW,\n'
               '        pool_timeout=ASM_POOL_TIMEOUT_S,\n'
               '        pool_pre_ping=True,\n'
               '        pool_recycle=1800,\n'
               '        connect_args=args,\n'
               '    )\n')
row("S53", "test_s53_the_deadline_pool", [
    M("through_get_db", "S53 503",
      E(MAIN, _ASM_ROUTE, _ASM_ROUTE.replace("Depends(get_asm_db)", "Depends(get_db)"))),
    M("pool_timeout_30", "S53 503", E(DBPY, "ASM_POOL_TIMEOUT_S = 3\n", "ASM_POOL_TIMEOUT_S = 30\n")),
], T("engine_through_a_helper",
     E(DBPY, _ASM_ENGINE, '    return create_async_engine(url, **_asm_engine_kwargs(args))\n'),
     E(DBPY, "\n\ndef make_asm_engine(",
       "\n\ndef _asm_engine_kwargs(args):\n"
       "    return dict(echo=False, pool_size=ASM_POOL_SIZE, max_overflow=ASM_POOL_OVERFLOW,\n"
       "                pool_timeout=ASM_POOL_TIMEOUT_S, pool_pre_ping=True, pool_recycle=1800,\n"
       "                connect_args=args)\n"
       "\n\ndef make_asm_engine("),
     note="the engine the fixture builds (make_asm_engine) takes its arguments from a helper"))

# -- S54 -------------------------------------------------------------------
_SETCFG = ('        "SELECT set_config(\'lock_timeout\', CAST(:lv AS text), true),"\n'
           '        "       set_config(\'statement_timeout\', CAST(:v AS text), true)"),\n')
_ASM_WORK_RELOAD = ('    await _asm_census_write(ctx, me, state, req, resolved, anon, seen_at)\n'
                    '    await ctx.reload(lobby=False)\n'
                    '    me = ctx.seat_of(pid)\n')
_LEFT_TWIN = (
    E(MAIN, '    left = ASM_TXN_DEADLINE_S * 1000 - _asm_elapsed_ms(t0)\n', '    left = _asm_left_ms(t0)\n'),
    E(MAIN, "\n\nasync def _asm_begin(db, t0) -> None:\n",
      "\n\ndef _asm_left_ms(t0) -> int:\n"
      "    return ASM_TXN_DEADLINE_S * 1000 - _asm_elapsed_ms(t0)\n"
      "\n\nasync def _asm_begin(db, t0) -> None:\n"))
row("S54", "test_s54_the_lock_deadline_ordered", [
    M("drop_lock_timeout", "S54 i log",
      E(MAIN, _SETCFG, '        "SELECT set_config(\'statement_timeout\', CAST(:v AS text), true)"),\n'),
      note="statement_timeout also bounds a lock wait here, so fixture (i) still answers "
           "inside 3.5 s; the stage it reports moves from lock to stmt"),
    M("read_before_the_lock", "S54 ii no grant",
      E(MAIN, _S21_LOCK,
        '    if route == "assembly":\n'
        '        _pre = _AsmCtx(db, lobby_id, route=route, trigger=route, t0=t0)\n'
        '        _pre.now, _pre.mono = await _asm_clock(db)\n'
        '        await _pre.reload()\n' + _S21_LOCK),
      E(MAIN, _S21_RET,
        '    await ctx.reload()\n'
        '    if route == "assembly":\n'
        '        ctx.lobby, ctx.seats = _pre.lobby, _pre.seats\n'
        '    return ctx, pid\n'),
      E(MAIN, _ASM_WORK_RELOAD,
        '    await _asm_census_write(ctx, me, state, req, resolved, anon, seen_at)\n'
        '    me = ctx.seat_of(pid)\n'),
      E(MAIN, _S21_SHORT, '        "       bets_disabled = TRUE, asm_rule = :r"\n'
                          '        " WHERE id = :lid RETURNING id"),\n'),
      note="the assembly route decides from rows read before the lobby lock and starts "
           "short with an unconditional UPDATE ... WHERE id = :lid"),
], T("remaining_ms_helper", *_LEFT_TWIN))

# -- S55 -------------------------------------------------------------------
_PRE = ('        pre_ms = _asm_elapsed_ms(t0)\n'
        '        if pre_ms > ASM_TXN_DEADLINE_S * 1000:\n'
        '            raise _AsmDeadline("precommit")\n'
        '        await db.commit()\n')
row("S55", "test_s55_statement_precommit_and_the_slow_commit", [
    M("deadline_check_after_the_commit", "S55 ii no write",
      E(MAIN, _PRE, '        pre_ms = _asm_elapsed_ms(t0)\n'
                    '        await db.commit()\n'
                    '        if pre_ms > ASM_TXN_DEADLINE_S * 1000:\n'
                    '            raise _AsmDeadline("precommit")\n')),
    M("drop_statement_timeout", "S55 i",
      E(MAIN, _SETCFG, '        "SELECT set_config(\'lock_timeout\', CAST(:lv AS text), true)"),\n'),
      note="the slow statement runs to its end; the pre-COMMIT check then refuses it "
           "(stage precommit, not stmt)"),
    M("second_post_unlocked", "S55 iv waits",
      E(MAIN, _S21_LOCK,
        '    _plain = (await db.execute(text("SELECT * FROM ffa_lobbies WHERE id = :lid"),\n'
        '                               {"lid": lobby_id})).mappings().first()\n'
        '    lob = dict(_plain) if _plain is not None else None\n'
        '    k = int(_plain["games_played"] or 0) + 1 if _plain is not None else 0\n'
        '    if lob is None:\n'),
      E(MAIN, _S21_RET, '    await ctx.reload()\n    ctx.lobby = lob\n    return ctx, pid\n'),
      note="the lobby row read without FOR NO KEY UPDATE, and that read is the one decided "
           "from: the second POST queues on no ffa_lobbies row (it may still wait on a seat "
           "row, which the unrestricted probe counted, so the answer came out the same)"),
], T("remaining_ms_helper", *_LEFT_TWIN))

# -- S56 -------------------------------------------------------------------
_CLAIM_I = ('        if claim is not None and claim >= p["late_game"] \\\n'
            '                and any(q["census_game"] == claim for q in ws):\n')
_WIT = ('    out = []\n'
        '    for q in ctx.seats:\n'
        '        if q["player_id"] == subject["player_id"]:\n'
        '            continue\n'
        '        v = q["verdict"]\n'
        '        if not (v == "granted" or (v == "admitted_late" and q["late_body_game"] is not None)):\n'
        '            continue\n'
        '        if not _asm_fresh(q, ctx.now) or q["census_seen_at"] is None:\n'
        '            continue\n'
        '        if q["census_seen_at"] <= subject["late_admitted_at"]:\n'
        '            continue\n'
        '        if q["census_region"] != subject["actor_region"]:\n'
        '            continue\n'
        '        out.append(q)\n'
        '    return out\n')
row("S56", "test_s56_the_late_body_rule_and_the_lone_report", [
    M("accept_entered_alone", "S56 i",
      E(MAIN, _CLAIM_I, '        if claim is not None and claim >= p["late_game"]:\n')),
    M("accept_one_witness", "S56 iv one witness",
      E(MAIN, '        for g, n in counts.items():\n            if n >= 2:\n',
        '        for g, n in counts.items():\n            if n >= 1:\n')),
    M("accept_a_census_before_the_admission", "S56 iv before the admission",
      E(MAIN, '        if q["census_seen_at"] <= subject["late_admitted_at"]:\n            continue\n', "")),
    M("report_writes_late_body_game", "S56 vi",
      E(MAIN, _W7A,
        '        if admitted_for_g and r["late_body_game"] is None and sid not in unrated:\n'
        '            await db.execute(text(\n'
        '                "UPDATE ffa_assembly_seats SET late_body_game = CAST(:g AS smallint)"\n'
        '                " WHERE lobby_id = :lid AND player_id ="\n'
        '                "       (SELECT id FROM players WHERE steam_id = :sid)"),\n'
        '                {"g": g, "lid": lobby_uuid, "sid": sid})\n' + _W7A)),
    M("report_rates_the_seat", "S56 vi",
      E(MAIN, _W7A, _W7A.replace("):\n", ") and sid in unrated:\n")),
      note="rule (a) unrates only a ghost: a present listing rates L"),
], T("witnesses_by_comprehension",
     E(MAIN, _WIT,
       '    return [q for q in ctx.seats\n'
       '            if q["player_id"] != subject["player_id"]\n'
       '            and (q["verdict"] == "granted"\n'
       '                 or (q["verdict"] == "admitted_late" and q["late_body_game"] is not None))\n'
       '            and _asm_fresh(q, ctx.now) and q["census_seen_at"] is not None\n'
       '            and q["census_seen_at"] > subject["late_admitted_at"]\n'
       '            and q["census_region"] == subject["actor_region"]]\n'),
     note="the witnesses are selected in Python here: one comprehension, the same predicate"))

# -- S57 -------------------------------------------------------------------
_G3_Q = ('        "SELECT q.player_id, q.caps, (g.player_id IS NOT NULL) AS enrolled"\n'
         '        "  FROM ffa_queue q"\n'
         '        "  LEFT JOIN ffa_g3_seats g ON g.player_id = q.player_id AND g.expires_at > now()"\n'
         '        " WHERE q.player_id = ANY(:ids)"), {"ids": ids})).mappings().all()\n')
row("S57", "test_s57_the_g3_server_gate", [
    M("drop_the_enrolment_clause", "S57 unenrolled",
      E(MAIN, '        if ADM_CAPS_TOKEN not in toks or not (ADM_PRODUCTION_ENABLED or r["enrolled"]):\n',
        '        if ADM_CAPS_TOKEN not in toks:\n')),
    M("ignore_expires_at", "S57 expired",
      E(MAIN, '        "  LEFT JOIN ffa_g3_seats g ON g.player_id = q.player_id AND g.expires_at > now()"\n',
        '        "  LEFT JOIN ffa_g3_seats g ON g.player_id = q.player_id"\n')),
    M("sign_the_target_without_the_hours", "S57 other duration",
      E(MAIN, '    await _require_admin(db, admin_id, "ffa_g3_seat", f"{target}:{hours}", _sig)\n',
        '    await _require_admin(db, admin_id, "ffa_g3_seat", target, _sig)\n')),
], T("enrolment_through_a_cte",
     E(MAIN, _G3_Q,
       '        "WITH q AS (SELECT player_id, caps FROM ffa_queue WHERE player_id = ANY(:ids)),"\n'
       '        "     g AS (SELECT player_id FROM ffa_g3_seats WHERE expires_at > now())"\n'
       '        " SELECT q.player_id, q.caps, (g.player_id IS NOT NULL) AS enrolled"\n'
       '        "  FROM q LEFT JOIN g ON g.player_id = q.player_id"), {"ids": ids})).mappings().all()\n'),
     note="the queue rows' CTE comes first so the statement still reads ffa_queue first"))


# -- S58: structural, both states ----------------------------------------------
_G3_FLAG = ("ADM_PRODUCTION_ENABLED = False    # while False, admission_v1 also needs every"
            " member in ffa_g3_seats\n")
_G3_DOC = '    holds an unexpired ffa_g3_seats enrolment. A member with no queue row, or\n'
_G3_INS = '        "INSERT INTO ffa_g3_seats (player_id, added_at, expires_at)"\n'
_G3_ROUTE = '@app.post("/api/v1/admin/ffa-g3-seats", tags=["Admin"])\n'
_S58_ASSERTS = (
    '        assert "LEFT JOIN ffa_g3_seats g ON g.player_id = q.player_id AND g.expires_at > now()" \\\n'
    '            in src, "S58 clause"\n'
    '        assert "/api/v1/admin/ffa-g3-seats" in paths, "S58 route"\n')
row("S58", "test_s58_the_g3_fence", [
    M("clause_left_in_production", "S58 production query",
      E(MAIN, _G3_FLAG, "ADM_PRODUCTION_ENABLED = True\n"),
      note="the production release with the enrolment clause (and the route) still in"),
    M("route_left_in_production", "S58 production route",
      E(MAIN, _G3_FLAG, "ADM_PRODUCTION_ENABLED = True\n"),
      E(MAIN, _G3_DOC, '    holds an unexpired G3 enrolment. A member with no queue row, or\n'),
      E(MAIN, _G3_Q, '        "SELECT q.player_id, q.caps, FALSE AS enrolled"\n'
                     '        "  FROM ffa_queue q"\n'
                     '        " WHERE q.player_id = ANY(:ids)"), {"ids": ids})).mappings().all()\n'),
      E(MAIN, _G3_INS, '        "INSERT INTO ffa_g3_enrolment (player_id, added_at, expires_at)"\n'),
      note="the clause and every ffa_g3_seats query gone, the route path still registered"),
    M("route_deleted_before_it", "S58 route", E(MAIN, _G3_ROUTE, "")),
    M("configuration_kept_after_release", "S58 production configuration",
      E(MAIN, _G3_FLAG, "ADM_PRODUCTION_ENABLED = True\n"),
      E(MAIN, _G3_DOC, '    holds an unexpired G3 enrolment. A member with no queue row, or\n'),
      E(MAIN, _G3_Q, '        "SELECT q.player_id, q.caps, FALSE AS enrolled"\n'
                     '        "  FROM ffa_queue q"\n'
                     '        " WHERE q.player_id = ANY(:ids)"), {"ids": ids})).mappings().all()\n'),
      E(MAIN, _G3_INS, '        "INSERT INTO ffa_g3_enrolment (player_id, added_at, expires_at)"\n'),
      E(MAIN, _G3_ROUTE, ""),
      E("backend/sql/355_ffa_assembly.sql", "\nCOMMIT;\n",
        "\nCOMMIT;\n-- planted by the S58 control: the release's DROP TABLE IF EXISTS ffa_g3_seats;\n"),
      note="K46's post-release mutant, paired with S58 (V11:2944): the production release with no"
           " ffa_g3_seats query, no route and a drop, and the csproj's G3 configuration kept"),
], T("assertions_reordered",
     E(TST, _S58_ASSERTS,
       '        assert "/api/v1/admin/ffa-g3-seats" in paths, "S58 route"\n'
       '        assert "LEFT JOIN ffa_g3_seats g ON g.player_id = q.player_id AND g.expires_at > now()" \\\n'
       '            in src, "S58 clause"\n'),
     note="a structural test: the twin reorders its assertions (V11's twin)"),
    extra=("plugin",))

# -- S59 -------------------------------------------------------------------
_B_LINE = '        elif some and t >= ASM_BASE_S and not spawning and not hold_adm:\n'
_ROSTER_SS = '    roster = [p["player_id"] for p in ctx.seats if cls.get(p["player_id"]) == "READY"]\n'
_ADM_AFTER = ('        if outcome == "start_short":\n'
              '            await _ffa_admission_check(ctx)\n'
              '            await ctx.reload()\n')
_SPAWN_CLS = '            out[p["player_id"]] = "SPAWNING" if p["body_seen_at"] is None else "READY"\n'
row("S59", "test_s59_rule_s_and_the_spawning_hold", [
    M("s_holds_for_a_spawning_seat", "S59 S",
      E(MAIN, _S_LINE, _S_LINE.replace(">= 3:\n", ">= 3 and not spawning:\n"))),
    M("b_without_the_spawning_hold", "S59 B held",
      E(MAIN, _B_LINE, _B_LINE.replace(" and not spawning", ""))),
    M("spawning_seat_in_the_roster", "S59 roster",
      E(MAIN, _ROSTER_SS, _ROSTER_SS.replace('== "READY"]', 'in ("READY", "SPAWNING")]'))),
    M("skip_the_admission_check", "S59 admitted", E(MAIN, _ADM_AFTER, "")),
], T("spawning_by_name",
     E(MAIN, _SPAWN_CLS, '            _spawning = p["body_seen_at"] is None\n'
                         '            out[p["player_id"]] = "SPAWNING" if _spawning else "READY"\n'),
     note="SPAWNING is classified in Python here: the twin names the predicate"))

# -- S60 -------------------------------------------------------------------
_ECHO = ('    if req.seen_age_ms > at_receipt_ms:\n'
         '        raise HTTPException(422, "seen_age_ms is later than the server\'s age at receipt")\n')
_SEEN_AT = '    seen_at = lob["created_at"] + timedelta(milliseconds=req.seen_age_ms)\n'
_SEEN_SET = ('            "census_seen_at = CAST(:seen AS timestamptz)",'
             ' "epoch_seen = CAST(:ep AS smallint)",\n')
_SEEN_P = '    p = {"lid": ctx.lid, "pid": me["player_id"], "now": ctx.now, "seen": seen_at,\n'
row("S60", "test_s60_the_census_echo", [
    M("accept_a_future_echo", "S60 future", E(MAIN, _ECHO, "")),
    M("census_at_as_census_seen_at", "S60 seen", E(MAIN, _SEEN_AT, "    seen_at = ctx.now\n")),
], T("seen_through_make_interval",
     E(MAIN, _SEEN_SET,
       '            "census_seen_at = CAST(:cr AS timestamptz)"\n'
       '            " + make_interval(secs => CAST(:sa AS double precision) / 1000)",\n'
       '            "epoch_seen = CAST(:ep AS smallint)",\n'),
     E(MAIN, _SEEN_P, '    p = {"lid": ctx.lid, "pid": me["player_id"], "now": ctx.now,\n'
                      '         "cr": ctx.lobby["created_at"], "sa": req.seen_age_ms,\n'),
     note="census_seen_at built in the statement with make_interval"))

# -- S61 -------------------------------------------------------------------
_GRANTED = ('    granted = [{"slot": int(s["slot"]), "actor": int(s["actor_nr"]),\n'
            '                "kind": "s" if s["verdict"] == "granted" else "l"}\n'
            '               for s in ctx.seats\n'
            '               if s["verdict"] in _ASM_GRANTED and s["actor_nr"] is not None\n'
            '               and not _asm_is_left(s)]\n')
row("S61", "test_s61_the_granted_list", [
    M("listed_by_claim", "S61 claim is not a binding",
      E(MAIN, _GRANTED, _GRANTED.replace(
          '"actor": int(s["actor_nr"]),',
          '"actor": int(s["actor_claim"] if s["actor_claim"] is not None else s["actor_nr"]),'))),
    M("left_listed", "S61 left omitted",
      E(MAIN, _GRANTED, _GRANTED.replace("\n               and not _asm_is_left(s)]", "]"))),
    M("admissible_listed", "S61 before",
      E(MAIN, _GRANTED, _GRANTED.replace('if s["verdict"] in _ASM_GRANTED and',
                                         'if s["verdict"] in (_ASM_GRANTED | {"admissible"}) and')),
      note="slot 2 is bound and admissible: listed as kind l"),
    M("admitted_marked_s", "S61 admitted",
      E(MAIN, _GRANTED, _GRANTED.replace('"kind": "s" if s["verdict"] == "granted" else "l"',
                                         '"kind": "s"'))),
], T("granted_through_a_helper",
     E(MAIN, _GRANTED, '    granted = _asm_granted_list(ctx)\n'),
     E(MAIN, "\n\ndef _asm_answer_lists(ctx) -> dict:\n",
       "\n\ndef _asm_granted_list(ctx) -> list:\n"
       + _GRANTED.replace("    granted = [", "    return [", 1)
       + "\n\ndef _asm_answer_lists(ctx) -> dict:\n"),
     note="the list is built in Python from the locked rows: a named helper"))

# -- S62 -------------------------------------------------------------------
_REFUSE = ('    if _asm_claim_seen(me, ctx.seats, ctx.now):\n'
           '        ctx.log(f"rebind_refused slot={me[\'slot\']}")\n')
row("S62", "test_s62_no_rebinding_after_a_grant", [
    M("rebind_a_granted_seat", "S62 binding kept",
      E(MAIN, _REFUSE, '    if _asm_claim_seen(me, ctx.seats, ctx.now):\n'
                       '        await ctx.db.execute(text(\n'
                       '            "UPDATE ffa_assembly_seats SET actor_nr = actor_claim,"\n'
                       '            " actor_region = claim_region"\n'
                       '            " WHERE lobby_id = :lid AND player_id = :pid"),\n'
                       '            {"lid": ctx.lid, "pid": me["player_id"]})\n'
                       '        return\n'),
      note="fixture (i): the row's binding check precedes its granted check"),
], T("refusal_through_a_helper",
     E(MAIN, _REFUSE, '    if _asm_rebind_refused(me, ctx):\n'
                      '        ctx.log(f"rebind_refused slot={me[\'slot\']}")\n'),
     E(MAIN, "\n\nasync def _asm_claim_trigger(ctx, me) -> None:\n",
       "\n\ndef _asm_rebind_refused(me, ctx) -> bool:\n"
       "    return _asm_claim_seen(me, ctx.seats, ctx.now)\n"
       "\n\nasync def _asm_claim_trigger(ctx, me) -> None:\n")))

# -- S63 -------------------------------------------------------------------
_EPI = ('        await ctx.db.execute(text(\n'
        '            "INSERT INTO ffa_kept_epochs (lobby_id, epoch_no, slot, actor_nr, chain)"\n'
        '            " VALUES (:lid, CAST(:n AS smallint), CAST(:slot AS smallint),"\n'
        '            "         CAST(:a AS smallint), :chain)"),\n'
        '            {"lid": ctx.lid, "n": n, "slot": int(p["slot"]), "a": int(claim[0]), "chain": chain})\n')
_PREV = ('        prev = (await ctx.db.execute(text(\n'
         '            "SELECT epoch_no, chain FROM ffa_kept_epochs WHERE lobby_id = :lid"\n'
         '            " ORDER BY epoch_no DESC LIMIT 1"), {"lid": ctx.lid})).mappings().first()\n')
_CHAIN = ('        chain = _ffa_epoch_chain(prev["chain"] if prev is not None else "0",\n'
          '                                 _asm_id8(ctx.lid), n, int(p["slot"]), int(claim[0]))\n')
_RUN_COMMIT = '        await db.commit()\n    except _AsmDeadline as d:\n'
row("S63", "test_s63_the_kept_epoch", [
    M("rechain_row_1", "S63 ii row 1 unchanged",
      E(MAIN, _EPI, _EPI + '        if n > 1:\n'
                           '            await ctx.db.execute(text(\n'
                           '                "UPDATE ffa_kept_epochs SET chain = :chain"\n'
                           '                " WHERE lobby_id = :lid AND epoch_no = 1"),\n'
                           '                {"chain": chain, "lid": ctx.lid})\n')),
    M("row_after_the_commit", "S63 i admitting answer",
      E(MAIN, _EPI, '        ctx.__dict__.setdefault("late_epochs", []).append(\n'
                    '            {"lid": ctx.lid, "n": n, "slot": int(p["slot"]), "a": int(claim[0]),\n'
                    '             "chain": chain})\n'),
      E(MAIN, _RUN_COMMIT,
        '        await db.commit()\n'
        '        for _e in ctx.__dict__.get("late_epochs", []):\n'
        '            await db.execute(text(\n'
        '                "INSERT INTO ffa_kept_epochs (lobby_id, epoch_no, slot, actor_nr, chain)"\n'
        '                " VALUES (:lid, CAST(:n AS smallint), CAST(:slot AS smallint),"\n'
        '                "         CAST(:a AS smallint), :chain)"), _e)\n'
        '        if ctx.__dict__.get("late_epochs"):\n'
        '            await db.commit()\n'
        '    except _AsmDeadline as d:\n'),
      note="the epoch row in a second transaction after the admission's COMMIT"),
    M("numbered_per_slot", "S63 ii",
      E(MAIN, _PREV, '        prev = (await ctx.db.execute(text(\n'
                     '            "SELECT epoch_no, chain FROM ffa_kept_epochs WHERE lobby_id = :lid"\n'
                     '            "   AND slot = CAST(:slot AS smallint)"\n'
                     '            " ORDER BY epoch_no DESC LIMIT 1"),\n'
                     '            {"lid": ctx.lid, "slot": int(p["slot"])})).mappings().first()\n'),
      note="slot 4's row takes epoch_no 1 again and the primary key refuses it: (ii) reads "
           "the refusal"),
    M("epoch_read_before_the_lock", "S63 iv",
      E(MAIN, _S21_LOCK,
        '    _pre_ep = (await db.execute(text(\n'
        '        "SELECT epoch_no, chain FROM ffa_kept_epochs WHERE lobby_id = :lid"\n'
        '        " ORDER BY epoch_no DESC LIMIT 1"), {"lid": lobby_id})).mappings().first()\n'
        + _S21_LOCK),
      E(MAIN, _S21_RET, '    await ctx.reload()\n'
                        '    ctx.pre_epoch = dict(_pre_ep) if _pre_ep is not None else None\n'
                        '    return ctx, pid\n'),
      E(MAIN, _PREV, '        prev = (ctx.__dict__["pre_epoch"] if "pre_epoch" in ctx.__dict__ else\n'
                     '                (await ctx.db.execute(text(\n'
                     '            "SELECT epoch_no, chain FROM ffa_kept_epochs WHERE lobby_id = :lid"\n'
                     '            " ORDER BY epoch_no DESC LIMIT 1"), {"lid": ctx.lid})).mappings().first())\n'),
      note="both concurrent admissions read no row before the lobby lock; the second one's "
           "epoch_no 1 is refused by the primary key"),
], T("chain_through_a_helper",
     E(MAIN, _CHAIN, '        chain = _asm_next_chain(prev, ctx.lid, n, p["slot"], claim[0])\n'),
     E(MAIN, "\n\nasync def _ffa_admission_check(ctx) -> list:\n",
       "\n\ndef _asm_next_chain(prev, lid, n, slot, actor) -> str:\n"
       "    return _ffa_epoch_chain(prev[\"chain\"] if prev is not None else \"0\",\n"
       "                            _asm_id8(lid), n, int(slot), int(actor))\n"
       "\n\nasync def _ffa_admission_check(ctx) -> list:\n")))

# -- S64: one node per fixture test --------------------------------------------
_S64 = ["test_s64_i_ii_the_false_mark_and_the_refuted_tally",
        "test_s64_iii_the_seats_own_leave_corroborated",
        "test_s64_iv_the_false_claim", "test_s64_iv_a_the_true_leave",
        "test_s64_iv_b_the_corroborated_absence", "test_s64_v_the_witness_path",
        "test_s64_vi_the_omitted_report", "test_s64_vii_the_in_flight_leave",
        "test_s64_viii_first_write_wins_and_the_negatives", "test_s64_x_the_lock",
        "test_s64_xi_the_false_leave[leave]", "test_s64_xi_the_false_leave[all_but_one]",
        "test_s64_xi_a_the_corroborated_leave",
        "test_s64_xi_b_the_absence_corroborated_at_the_leave"]


def _n64(prefix):
    hit = [n for n in _S64 if n.startswith(prefix)]
    assert len(hit) == 1, (prefix, hit)
    return PG + hit[0]


_D_UNRATE = ('        elif r["gone_game"] is not None and g > int(r["gone_game"]):\n'
             '            reason = "d"\n')
_D_REFUSE = '        if rep["gone_game"] is not None and g > int(rep["gone_game"]):\n'
_RULES_OUT = '    out = set(unrated)\n    added = []\n'
_W_LISTING = ('    if any(subject["actor_nr"] in (q["census_actors"] or []) for q in ws):\n'
              '        return None\n')
_W_TWO = '    if len(omit) < 2:\n        return None\n'
_W_OWN = ('        if own_age <= ASM_WITNESS_FRESH_S * 1000 and own_lists:\n'
          '            return None\n')
_GONE_PATH = '    path = "leave" if subject["left_at"] is not None else "witness"\n'
_GONE_K = '    k = int(ctx.expected_game)\n'
_CLAIM_BLOCK = ('    if _asm_gone_subject(ctx, me):\n'
                '        found = _asm_gone_test(ctx, me)\n'
                '        if found is not None and await _asm_gone_write(ctx, me, found):\n'
                '            result = "witness"\n')
_LEAVE_BLOCK = ('    if _asm_gone_subject(ctx, me):\n'
                '        found = _asm_gone_test(ctx, me)\n'
                '        if found is not None and await _asm_gone_write(ctx, me, found, deferred_ok=False):\n'
                '            result = "witness"\n')
_LEAVE_BODY = ('    result = "none"\n' + _LEAVE_BLOCK
               + '    ctx.log(f"gone_trigger slot={me[\'slot\']} path=leave result={result}")\n'
                 '    return result == "witness"\n')
_LEAVE_DOC_END = ('    row lock. Returns True when the record was written (gone_path \'leave\')."""\n'
                  '    result = "none"\n')
_CENSUS_BLOCK = ('        if _asm_gone_subject(ctx, s):\n'
                 '            found = _asm_gone_test(ctx, s)\n'
                 '            if found is not None:\n'
                 '                await _asm_gone_write(ctx, s, found)\n')
_STARTED_LEAVE = ('        if me["verdict"] in _ASM_GRANTED:\n'
                  '            await _asm_leave_trigger(ctx, me)\n')
_SLOT_LOCK = '    _row, k = await _ffa_lock_lobby_slot(db, lobby_id)\n'
_K0 = ('    _k0 = (await db.execute(text("SELECT games_played FROM ffa_lobbies WHERE id = :lid"),\n'
       '                            {"lid": lobby_id})).scalar()\n')
_W7_ROWS = ('        "SELECT p.steam_id, s.slot, s.start_roster, s.late_admitted_at, s.late_game,"\n'
            '        "       s.late_body_game, s.gone_game, s.lag_games"\n'
            '        "  FROM ffa_assembly_seats s JOIN players p ON p.id = s.player_id"\n'
            '        " WHERE s.lobby_id = :lid ORDER BY s.slot"), {"lid": lobby_uuid})).mappings().all()\n')
row("S64", _S64, [
    M("v8_left_early_rule", "S64 mark game 2 rated",
      E(MAIN, _RULES_OUT,
        '    _v8 = set((await db.execute(text(\n'
        '        "SELECT p.steam_id FROM ffa_match_players mp JOIN ffa_matches m ON m.id = mp.match_id"\n'
        '        "  JOIN players p ON p.id = mp.player_id"\n'
        '        " WHERE m.lobby_id = :lid AND m.game_number < :g AND mp.left_early"),\n'
        '        {"lid": lobby_uuid, "g": g})).scalars().all())\n' + _RULES_OUT),
      E(MAIN, _D_UNRATE, '        elif (r["gone_game"] is not None and g > int(r["gone_game"])) or sid in _v8:\n'
                         '            reason = "d"\n'),
      nodes=[_n64("test_s64_i_ii")],
      note="V8's rule: an earlier accepted report's left_early unrates the seat"),
    M("leave_fields_after_the_gone_game", "S64 vii game 2 leave unrated",
      E(MAIN, _D_UNRATE,
        '        elif r["gone_game"] is not None and g > int(r["gone_game"]) and not (\n'
        '                g == int(r["gone_game"]) + 1\n'
        '                and any(q.steam_id == sid and q.left_early for q in report.players)):\n'
        '            reason = "d"\n'),
      nodes=[_n64("test_s64_vii_the")]),
    M("delete_d", "S64 iii game 2 unrated", E(MAIN, _D_UNRATE, ""), nodes=[_n64("test_s64_iii")]),
    M("d_at_the_gone_game", "S64 iii game 1 rated",
      E(MAIN, _D_UNRATE, _D_UNRATE.replace("g > int(", "g >= int(")),
      nodes=[_n64("test_s64_iii")]),
    M("d_after_the_next_game", "S64 iii game 2 unrated",
      E(MAIN, _D_UNRATE, _D_UNRATE.replace('g > int(r["gone_game"])', 'g > int(r["gone_game"]) + 1')),
      nodes=[_n64("test_s64_iii")]),
    M("accept_the_reporter", "S64 iii refused", E(MAIN, _D_REFUSE, "        if False:\n"),
      nodes=[_n64("test_s64_iii")]),
    M("one_witness", "S64 v", E(MAIN, _W_TWO, "    if len(omit) < 1:\n        return None\n"),
      nodes=[_n64("test_s64_v_")]),
    M("ignore_a_listing_witness", "S64 v", E(MAIN, _W_LISTING, ""), nodes=[_n64("test_s64_v_")]),
    M("ignore_the_own_fresh_census", "S64 v", E(MAIN, _W_OWN, ""), nodes=[_n64("test_s64_v_")]),
    M("games_played_before_the_lock", "S64 x",
      E(MAIN, _S21_LOCK, _K0 + '    lob, k = await _ffa_lock_lobby_slot(db, lobby_id)\n'
                                '    k = int(_k0 or 0) + 1\n'
                                '    if lob is None:\n'),
      E(MAIN, _SLOT_LOCK, _K0 + _SLOT_LOCK + '    k = int(_k0 or 0) + 1\n'),
      nodes=[_n64("test_s64_x_")],
      note="k from a read before the lobby row lock, at both lock sites"),
    M("v9_lone_claim", "S64 iv trigger",
      E(MAIN, _CLAIM_BLOCK, _CLAIM_BLOCK.replace("found = _asm_gone_test(ctx, me)\n",
                                                 "found = _asm_gone_test(ctx, me) or ([], None, 0)\n")),
      nodes=[_n64("test_s64_iv_the")],
      note="V9's claim path; V9's label 'claim' is refused by ck_ffa_seat_gone since V10, so "
           "the lone claim writes under the label the writer computes"),
    M("no_test_at_a_claim", "S64 iv-b record", E(MAIN, _CLAIM_BLOCK, ""),
      nodes=[_n64("test_s64_iv_b")]),
    M("v10_leave_writes_alone", "S64 xi leave",
      E(MAIN, _LEAVE_BLOCK, _LEAVE_BLOCK.replace("found = _asm_gone_test(ctx, me)\n",
                                                 "found = _asm_gone_test(ctx, me) or ([], None, 0)\n")),
      nodes=[_n64("test_s64_xi_the_false_leave[leave]")],
      note="V10's writer 5: the leave writes the record by itself"),
    M("no_test_at_a_leave", "S64 xi-b record", E(MAIN, _LEAVE_BLOCK, ""),
      nodes=[_n64("test_s64_xi_b")]),
    M("no_leave_trigger", "S64 xi-b record", E(MAIN, _LEAVE_BODY, "    return False\n"),
      nodes=[_n64("test_s64_xi_b")]),
    M("label_without_left_at", "S64 xi-a record", E(MAIN, _GONE_PATH, '    path = "witness"\n'),
      nodes=[_n64("test_s64_xi_a")]),
    M("staged_leave_game", "S64 xi-a later record",
      E(MAIN, "\n\nasync def _asm_leave_trigger(ctx, me) -> bool:\n",
        "\n\n_ASM_STAGED = {}\n\n\nasync def _asm_leave_trigger(ctx, me) -> bool:\n"),
      E(MAIN, _LEAVE_DOC_END,
        _LEAVE_DOC_END.replace('    result = "none"\n',
                               '    _ASM_STAGED.setdefault((str(ctx.lid), str(me["player_id"])),\n'
                               '                           int(ctx.expected_game))\n'
                               '    result = "none"\n')),
      E(MAIN, _GONE_K, '    k = _ASM_STAGED.get((str(ctx.lid), str(subject["player_id"])),\n'
                       '                        int(ctx.expected_game))\n'),
      nodes=[_n64("test_s64_xi_a")],
      note="the game the leave read, staged at the leave, names the census's record"),
    M("verdict_left_on_a_started_leave", "S64 xi seat",
      E(MAIN, _STARTED_LEAVE,
        '        if me["verdict"] in _ASM_GRANTED:\n'
        '            await db.execute(text(\n'
        '                "UPDATE ffa_assembly_seats SET verdict = \'left\',"\n'
        '                " verdict_at = CAST(:now AS timestamptz)"\n'
        '                " WHERE lobby_id = :lid AND player_id = :pid"),\n'
        '                {"now": ctx.now, "lid": lobby_id, "pid": player_id})\n'
        '            await _asm_leave_trigger(ctx, me)\n'),
      nodes=[_n64("test_s64_xi_the_false_leave[leave]")]),
    M("else_branch_when_started", "S64 xi all but one", E(MAIN, _LIVE5, L(29, "or False)")),
      nodes=[_n64("test_s64_xi_the_false_leave[all_but_one]")],
      note="the else branch on a started gated lobby: it completes at all but one"),
], T("gone_through_a_cte_and_one_test",
     E(MAIN, _W7_ROWS,
       '        "WITH s AS (SELECT * FROM ffa_assembly_seats WHERE lobby_id = :lid)"\n'
       '        " SELECT p.steam_id, s.slot, s.start_roster, s.late_admitted_at, s.late_game,"\n'
       '        "       s.late_body_game, s.gone_game, s.lag_games"\n'
       '        "  FROM s JOIN players p ON p.id = s.player_id"\n'
       '        " ORDER BY s.slot"), {"lid": lobby_uuid})).mappings().all()\n'),
     E(MAIN, _CENSUS_BLOCK, '        found = _asm_gone_found(ctx, s)\n'
                            '        if found is not None:\n'
                            '            await _asm_gone_write(ctx, s, found)\n'),
     E(MAIN, _CLAIM_BLOCK, '    found = _asm_gone_found(ctx, me)\n'
                           '    if found is not None and await _asm_gone_write(ctx, me, found):\n'
                           '        result = "witness"\n'),
     E(MAIN, _LEAVE_BLOCK, '    found = _asm_gone_found(ctx, me)\n'
                           '    if found is not None and await _asm_gone_write(ctx, me, found,\n'
                           '                                                   deferred_ok=False):\n'
                           '        result = "witness"\n'),
     E(MAIN, "\n\nasync def _asm_gone_census(ctx, exclude_pid=None) -> None:\n",
       "\n\ndef _asm_gone_found(ctx, s):\n"
       "    return _asm_gone_test(ctx, s) if _asm_gone_subject(ctx, s) else None\n"
       "\n\nasync def _asm_gone_census(ctx, exclude_pid=None) -> None:\n"),
     note="writer 7 reads the record through a CTE; the census, claim and leave triggers "
          "run the witness test through one helper"))

# -- S65 -------------------------------------------------------------------
_ANS_KEYS = ('    ans = {"assembly": 1 if lob.get("assembly_v1") else 0,\n'
             '           "asm_started": 1 if lob.get("start_granted_at") is not None else 0}\n')
_PAY_KEYS = ('        "assembly": 1 if lobby.get("assembly_v1") else 0,\n'
             '        "asm_started": 1 if lobby.get("start_granted_at") is not None else 0,\n')
row("S65", "test_s65_the_sittings_state_on_every_answer", [
    M("omitted_in_state_b", "S65 keys",
      E(MAIN, _ANS_KEYS, '    ans = ({} if st == "B" else\n'
                         '           {"assembly": 1 if lob.get("assembly_v1") else 0,\n'
                         '            "asm_started": 1 if lob.get("start_granted_at") is not None else 0})\n')),
    M("started_after_game_1", "S65 asm_started",
      E(MAIN, _ANS_KEYS, _ANS_KEYS.replace('1 if lob.get("start_granted_at") is not None else 0',
                                           '1 if int(lob.get("games_played") or 0) > 0 else 0')),
      E(MAIN, _PAY_KEYS, _PAY_KEYS.replace('1 if lobby.get("start_granted_at") is not None else 0',
                                           '1 if int(lobby.get("games_played") or 0) > 0 else 0'))),
], T("keys_through_a_helper",
     E(MAIN, _ANS_KEYS, '    ans = dict(_asm_sitting_keys(lob))\n'),
     E(MAIN, _PAY_KEYS, '        **_asm_sitting_keys(lobby),\n'),
     E(MAIN, "\n\nasync def _asm_answer_plan(ctx, pid, *, vans=None, info=None) -> dict:\n",
       "\n\ndef _asm_sitting_keys(lobby) -> dict:\n"
       "    return {\"assembly\": 1 if lobby.get(\"assembly_v1\") else 0,\n"
       "            \"asm_started\": 1 if lobby.get(\"start_granted_at\") is not None else 0}\n"
       "\n\nasync def _asm_answer_plan(ctx, pid, *, vans=None, info=None) -> dict:\n")))

# -- S66: one node per part ------------------------------------------------------


def _n66(part):
    return PG + "test_s66_the_release[%s]" % part


_REL_ROUTE = ('    held = {"lease": 0}\n'
              '    return await _asm_run("release", lobby_id, req.steam_id, request, db,\n'
              '                          _asm_release_work, (req, held),\n'
              '                          pre=_asm_release_pre(req.steam_id, lobby_id, held))\n')
_REL_UPD = ('        "UPDATE ffa_assembly_seats SET released_at = NOW(), release_why = CAST(:why AS varchar)"\n'
            '        " WHERE lobby_id = :lid AND player_id = :pid AND released_at IS NULL"),\n')
_REL_DEL = ('    row = (await ctx.db.execute(text(\n'
            '        "DELETE FROM ffa_queue WHERE player_id = :pid AND series_id = :lid RETURNING player_id"),\n'
            '        {"pid": pid, "lid": ctx.lid})).scalar()\n')
_REL_WHY = '    if req.why not in _ASM_RELEASE_WHY or not _pg_text_ok(req.steam_id):\n'
_REL_PRE = '        await _lease_release_by_steam(db, steam_id, str(lobby_id))\n'
_REL_ME = ('    me = ctx.seat_of(pid)\n'
           '    await ctx.db.execute(text(\n'
           '        "UPDATE ffa_assembly_seats SET released_at = NOW()')
_REL_RET = '    return {"release": {"status": "ok"}}\n'
row("S66", ["test_s66_the_release[%s]" % p for p in ("i-iii", "iv", "v", "check")], [
    M("through_the_leave", "S66 i byte-identical",
      E(MAIN, _REL_ROUTE, '    held = {"lease": 0}\n'
                          '    out = await _asm_run("release", lobby_id, req.steam_id, request, db,\n'
                          '                         _asm_release_work, (req, held),\n'
                          '                         pre=_asm_release_pre(req.steam_id, lobby_id, held))\n'
                          '    await ffa_queue_leave(request, steam_id=req.steam_id,\n'
                          '                          expected_lobby_id=str(lobby_id), cause="", label="",\n'
                          '                          db=db)\n'
                          '    return out\n'),
      nodes=[_n66("i-iii")], note="the leave route's body runs for the release (V10's FfaLeaveQueue)"),
    M("write_departed_ids", "S66 i byte-identical",
      E(MAIN, _REL_DEL, _REL_DEL + '    await ctx.db.execute(text(\n'
                                   '        "UPDATE ffa_lobbies SET departed_ids = (SELECT ARRAY(SELECT DISTINCT e FROM"\n'
                                   '        " unnest(departed_ids || CAST(:ids AS uuid[])) e)) WHERE id = :lid"),\n'
                                   '        {"lid": ctx.lid, "ids": [pid]})\n'),
      nodes=[_n66("i-iii")]),
    M("write_departure_causes", "S66 i byte-identical",
      E(MAIN, _REL_DEL, _REL_DEL + '    await ctx.db.execute(text(\n'
                                   '        "UPDATE ffa_lobbies SET departure_causes ="\n'
                                   '        " jsonb_build_object(CAST(:p AS text), \'release\') || departure_causes"\n'
                                   '        " WHERE id = :lid"), {"lid": ctx.lid, "p": str(pid)})\n'),
      nodes=[_n66("i-iii")]),
    M("write_a_left_receipt", "S66 i byte-identical",
      E(MAIN, _REL_DEL, _REL_DEL + '    await ctx.db.execute(text(\n'
                                   '        "UPDATE ffa_assembly_seats SET left_at = NOW()"\n'
                                   '        " WHERE lobby_id = :lid AND player_id = :pid"),\n'
                                   '        {"lid": ctx.lid, "pid": pid})\n'),
      nodes=[_n66("i-iii")]),
    M("release_every_seat", "S66 i byte-identical",
      E(MAIN, _REL_UPD, _REL_UPD.replace(" AND player_id = :pid", "")),
      E(MAIN, _REL_DEL, '    row = (await ctx.db.execute(text(\n'
                        '        "DELETE FROM ffa_queue WHERE series_id = :lid RETURNING player_id"),\n'
                        '        {"lid": ctx.lid})).scalars().first()\n'
                        '    await ctx.db.execute(text(\n'
                        '        "DELETE FROM queue_leases WHERE mode = \'ffa\' AND group_id = :lid"),\n'
                        '        {"lid": ctx.lid})\n'),
      nodes=[_n66("i-iii")]),
    M("lease_by_steam_alone", "S66 v the held lobby's rows",
      E(MAIN, _REL_PRE, "        await _lease_release_by_steam(db, steam_id)\n"),
      nodes=[_n66("v")]),
    M("queue_row_by_player_alone", "S66 v",
      E(MAIN, _REL_DEL, _REL_DEL.replace(" AND series_id = :lid", "")), nodes=[_n66("v")],
      note="the held lobby's queue row is deleted: the print says row=1"),
    M("accept_any_why", "S66 iv why", E(MAIN, _REL_WHY, "    if not _pg_text_ok(req.steam_id):\n"),
      nodes=[_n66("iv")],
      note="ck_ffa_seat_release refuses the stored value, so the answer is the refusal's "
           "error rather than V11's 200 with a write; (iv) reads it"),
], T("answer_across_lines_and_a_seat_helper",
     E(MAIN, _REL_ME, _REL_ME.replace("    me = ctx.seat_of(pid)\n", "    me = _asm_release_seat(ctx, pid)\n")),
     E(MAIN, _REL_RET, '    out = {\n'
                       '        "release": {\n'
                       '            "status": "ok",\n'
                       '        },\n'
                       '    }\n'
                       '    return out\n'),
     E(MAIN, "\n\nasync def _asm_release_work(ctx, pid, arg) -> dict:\n",
       "\n\ndef _asm_release_seat(ctx, pid):\n"
       "    return ctx.seat_of(pid)\n"
       "\n\nasync def _asm_release_work(ctx, pid, arg) -> dict:\n")))


# -- Section 12 (the round-11 findings carried): N8, N10, N12 ------------------
_DEFER = '                _asm_defer = _asm_plan is not None and _asm_plan.defer_departure\n'
row("N8", "test_n8_a_delayed_leave_touches_no_other_row", [
    M("unconditional_append_and_release", "N8 no append",
      E(MAIN, _DEFER, "                _asm_defer = False\n"),
      note="V10's writer 5: the leave appends its departure and releases the survivors "
           "by itself"),
], T("defer_by_truth",
     E(MAIN, _DEFER, "                _asm_defer = bool(_asm_plan and _asm_plan.defer_departure)\n")))

_SUBJ_REL = '            and s["gone_game"] is None and s["released_at"] is None\n'
_WRITE_REL = '        "   AND gone_game IS NULL AND released_at IS NULL"),\n'
_WIT_REL = '        if q["gone_game"] is not None or q["released_at"] is not None:\n'
row("N10", "test_n10_a_released_seat_never_reaches_the_gone_rule", [
    M("released_seat_through_the_gone_rule", "N10 no record",
      E(MAIN, _SUBJ_REL, '            and s["gone_game"] is None\n'),
      E(MAIN, _WRITE_REL, '        "   AND gone_game IS NULL"),\n'),
      note="the subject predicate and the record's own UPDATE both admit a released seat"),
    M("released_seat_a_witness", "N10 released witness",
      E(MAIN, _WIT_REL, '        if q["gone_game"] is not None:\n')),
], T("released_by_truth",
     E(MAIN, _SUBJ_REL, '            and s["gone_game"] is None and not s["released_at"]\n'),
     E(MAIN, _WIT_REL, '        if q["gone_game"] is not None or bool(q["released_at"]):\n')))

_CLS_COPY = ('    "COPY": ("score_target", "card_candidates", "initial_picks", "card_cap",\n'
             '             "same_card_rule", "is_ranked", "settings_known", "settings_changed_at",\n')
_CLS_RESET_END = ('              "dissolve_after_ms", "present_at_dissolve", "absent_at_dissolve",\n'
                  '              "arrived_at_dissolve"),\n')
row("N12a", "test_n12_the_46_column_partition", [
    M("a_column_moved", "N12 classes",
      E(MAIN, _CLS_COPY, _CLS_COPY.replace('"is_ranked", ', "")),
      E(MAIN, _CLS_RESET_END, _CLS_RESET_END.replace('"arrived_at_dissolve"),',
                                                     '"arrived_at_dissolve", "is_ranked"),'))),
], T("order_within_a_class",
     E(MAIN, _CLS_COPY, _CLS_COPY.replace('("score_target", "card_candidates",',
                                          '("card_candidates", "score_target",'))))

_INS_RANKED = '        is_ranked, settings_known, settings_changed_at, password_hash, kicked_steam_ids,\n'
_VAL_RANKED = '        :is_ranked, :settings_known, :settings_changed_at, :password_hash, :kicked_steam_ids,\n'
_MAP_RANKED = '        "same_card_rule": lob["same_card_rule"], "is_ranked": lob["is_ranked"],\n'
row("N12b", "test_n12_reform_keeps_the_ranked_flag", [
    M("is_ranked_left_to_the_default", "N12 is_ranked",
      E(MAIN, _INS_RANKED, _INS_RANKED.replace("is_ranked, ", "")),
      E(MAIN, _VAL_RANKED, _VAL_RANKED.replace(":is_ranked, ", "")),
      note="the schema default (TRUE) makes the casual lobby's re-form rated"),
], T("ranked_through_bool",
     E(MAIN, _MAP_RANKED, _MAP_RANKED.replace('"is_ranked": lob["is_ranked"],',
                                              '"is_ranked": bool(lob["is_ranked"]),'))))

_INROOM = ('    if not pre_room and _is_in_room_exit_cause(cause):\n'
           '        plan.path = "departure"\n'
           '        return plan\n')
row("N12c", "test_n12_the_gated_leave_branch_order", [
    M("in_room_closed_in_its_own_transaction", "N12 in-room path", E(MAIN, _INROOM, ""),
      note="the in-room leave falls to the pre-T0+20 step, whose today's-path branch"
           " (fewer than three others) still keeps the lobby and appends the departure"
           " for an in-room cause (today's in-room veto), but records left_path 'kept'"
           " where the ordered step records 'departure'"),
], T("in_room_by_name",
     E(MAIN, _INROOM, "    _in_room_first = not pre_room and _is_in_room_exit_cause(cause)\n"
                      "    if _in_room_first:\n"
                      '        plan.path = "departure"\n'
                      "        return plan\n")))

# -- The closers' literal and the assembly pool ----------------------------------
row("census_literal", "test_the_census_fresh_literal_is_the_constant", [
    M("one_literal_drifts", "census literal",
      E(MAIN, "                                     AND pf.census_at >= NOW() - interval '6 seconds')\n",
        "                                     AND pf.census_at >= NOW() - interval '7 seconds')\n")),
], T("fragment_by_concatenation",
     E(MAIN, '_FFA_CLOSE_RECORD_SET = """\n', '_FFA_CLOSE_RECORD_SET = "" + """\n')))

_ASM_ARGS = '    args = {"timeout": ASM_CONNECT_TIMEOUT_S}\n'
row("asm_pool", "test_the_assembly_pool_and_its_connect_timeout", [
    M("no_connect_timeout", "connect timeout", E(DBPY, _ASM_ARGS, "    args = {}\n"),
      note="asyncpg's default 60 s connect timeout: the checkout fails after about 60 s"),
    M("pool_size_5", "pool arguments", E(DBPY, "ASM_POOL_SIZE = 4\n", "ASM_POOL_SIZE = 5\n")),
], T("args_through_dict", E(DBPY, _ASM_ARGS, "    args = dict(timeout=ASM_CONNECT_TIMEOUT_S)\n")))


# The client rows (K, WP and N11) are registered by their own module.
import cf_controls_client  # noqa: E402,F401
