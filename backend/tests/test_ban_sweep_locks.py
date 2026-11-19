"""Bans part 2a, FIX-2 classes V and VI: the identity key's lock protocol,
judged by TRANSACTION over the syntax tree of backend/api (ban_sweep_locks).

The protocol. P1: the first taking call of a transaction is ONE call, in
identity_lock_key order, and may block. P2: every later taking call either
(a) asks only for keys the transaction already holds, in the same or a weaker
mode, or (b) is bounded (a lock_timeout budget: 55P03, rollback, the route's
contended answer). Shared then exclusive on one key is an upgrade and counts
as a new key. Under P2 a member of a wait cycle that holds a key and waits out
of order waits a bounded time, so no wait is permanent.

Every segment of a transaction with more than one taking call is in PROOFS,
keyed by its sequence of taking frames, with the entries that reach it. A P2a
proof is a list of syntax facts (the same key expression, no rebinding
between, the mode of each take); a P2b proof names the bounded taker and the
fact that bounds it. A fact the syntax cannot state is a TYPED entry naming the
PostgreSQL test that is red when it is false. Each fact form has a mutant
here: another key expression, a stronger mode, an unbounded new key.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ban_sweep_locks as K  # noqa: E402

_CACHE = {}


def _funcs():
    if "f" not in _CACHE:
        _CACHE["f"] = K.functions(K.api_sources())
    return _CACHE["f"]


def _walk():
    if "w" not in _CACHE:
        _CACHE["w"] = K.walk_all(_funcs())
    return _CACHE["w"]


# ---------------------------------------------------------------- the facts

def _fn(name, mod="main", funcs=None):
    return (funcs or _funcs())[mod][name]


def _calls(fn, callee):
    return [c for c in ast.walk(fn) if isinstance(c, ast.Call) and K._name_of(c) == callee]


def _arg(call, sel):
    if isinstance(sel, int):
        return call.args[sel] if len(call.args) > sel else None
    return next((k.value for k in call.keywords if k.arg == sel), None)


def _raw_takes(fn):
    """(sid expression, mode) of every taking statement in fn's own body."""
    out = []
    for c in K._own_nodes(fn):
        if isinstance(c, ast.Call) and K.is_taking_statement(c):
            sql = K._sql_text(c)
            params = next((a for a in c.args[1:] if isinstance(a, ast.Dict)), None)
            expr = None
            if params is not None:
                for k, v in zip(params.keys, params.values):
                    if isinstance(k, ast.Constant) and k.value == "sid":
                        expr = ast.unparse(v)
            out.append((expr, "shared" if "_shared" in sql.lower() else "exclusive"))
    return out


def _stores(fn, name):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == name
            and isinstance(n.ctx, ast.Store)]


def check_fact(fact, funcs=None):
    """None when the fact holds, else the reason it does not."""
    kind, fname = fact[0], fact[1]
    mod = "match_hold" if fname.startswith("mh:") else "main"
    fn = _fn(fname.split(":")[-1], mod, funcs)
    if kind == "arg":                      # every call of callee passes `expect` at sel
        _, _, callee, sel, expect = fact
        cs = _calls(fn, callee)
        got = sorted({ast.unparse(_arg(c, sel)) if _arg(c, sel) is not None else None for c in cs},
                     key=str)
        return None if cs and got == [expect] else f"{fname}: {callee}[{sel}] is {got}, not {expect!r}"
    if kind == "argcall":                  # ... passes a call of `inner` whose kw is `expect`
        _, _, callee, pos, inner, kw, expect = fact
        cs = _calls(fn, callee)
        bad = [c for c in cs if not (isinstance(_arg(c, pos), ast.Call)
                                     and K._name_of(_arg(c, pos)) == inner
                                     and _arg(_arg(c, pos), kw) is not None
                                     and ast.unparse(_arg(_arg(c, pos), kw)) == expect)]
        return None if cs and not bad else f"{fname}: {callee}({inner}({kw}=...)) is not {expect!r}"
    if kind == "nokw":                     # no call of callee passes kw (a gate asks shared only)
        _, _, callee, kw = fact
        cs = _calls(fn, callee)
        return None if cs and all(_arg(c, kw) is None for c in cs) else f"{fname}: {callee} passes {kw}="
    if kind == "raw":                      # every own take keys `expect` in `mode`
        _, _, expect, mode = fact
        takes = _raw_takes(fn)
        return None if takes and set(takes) == {(expect, mode)} else f"{fname}: takes {takes}"
    if kind == "src":                      # the statement stands in the function
        _, _, snippet = fact
        return None if snippet in ast.unparse(fn) else f"{fname}: no {snippet!r}"
    if kind == "bound":                    # its waits run under a lock_timeout budget
        src = ast.unparse(fn)
        missing = [n for n in fact[2:] if n not in src]
        return None if not missing else f"{fname}: no {missing}"
    if kind == "unbound":                  # the name is never rebound in the function
        _, _, name = fact
        n = _stores(fn, name)
        return None if not n else f"{fname}: {name} rebound at {[x.lineno for x in n]}"
    if kind == "once":                     # bound exactly once
        _, _, name = fact
        n = _stores(fn, name)
        return None if len(n) == 1 else f"{fname}: {name} bound {len(n)} times"
    raise AssertionError(fact)


_PC_RAW = lambda route: [  # noqa: E731
    ("raw", route, "steam_id", "exclusive"),
    ("arg", route, "_pc_verified_actor", 1, "steam_id"),
    ("unbound", route, "steam_id"),
    ("raw", "_pc_verified_actor", "steam_id", "shared"),
    ("unbound", "_pc_verified_actor", "steam_id"),
]

_MAIL = [
    ("src", "_mail_lock_identities", "ids = sorted({str(s) for s in steam_ids if s})"),
    ("src", "_mail_lock_identities", "await _identity_lock_many(db, ids)"),
    ("once", "_mail_lock_identities", "ids"),
]

PROOFS = {
    ("pc_dance_select", "_pc_verified_actor"): dict(
        how="P2a", base=True, entries={"main.pc_dance_select"}, facts=_PC_RAW("pc_dance_select")),
    ("pc_motion_upload", "_pc_verified_actor"): dict(
        how="P2a", base=True, entries={"main.pc_motion_upload"}, facts=_PC_RAW("pc_motion_upload")),
    ("pc_portrait_upload", "_pc_verified_actor"): dict(
        how="P2a", base=True, entries={"main.pc_portrait_upload"}, facts=_PC_RAW("pc_portrait_upload")),
    ("_pc_verified_actor", "_pc_claim_daily"): dict(
        how="P2a", base=True, entries={"main.pc_daily_claim"}, facts=[
            ("raw", "_pc_verified_actor", "steam_id", "shared"),
            ("src", "_pc_verified_actor", "select(Player).where(Player.steam_id == steam_id)"),
            ("once", "_pc_verified_actor", "player"),
            ("arg", "pc_daily_claim", "_pc_claim_daily", 1, "player"),
            ("once", "pc_daily_claim", "player"),
            ("src", "_pc_claim_daily", "steam_id = player.steam_id"),
            ("once", "_pc_claim_daily", "steam_id"),
            ("raw", "_pc_claim_daily", "steam_id", "shared")]),
    ("_enrollment_identity_gate", "_enrollment_identity_gate"): dict(
        how="P2a", base=True, entries={"main.invite_accept"}, facts=[
            ("arg", "invite_accept", "_enrollment_identity_gate", 1, "me['steam_id']"),
            ("arg", "invite_accept", "_invite_join_core", 2, "me"),
            ("once", "invite_accept", "me"),
            ("argcall", "_invite_join_core", "_ffa_lobby_join_core", 0, "_FfaLobbyJoinReq",
             "steam_id", "me['steam_id']"),
            ("unbound", "_invite_join_core", "me"),
            ("arg", "_ffa_lobby_join_core", "_enrollment_identity_gate", 1, "req.steam_id"),
            ("unbound", "_ffa_lobby_join_core", "req"),
            ("raw", "_enrollment_identity_gate", "steam_id", "exclusive")]),
    ("_identity_lock_many", "_enrollment_identity_gate"): dict(
        how="P2a", base=True, entries={"main.invite_send"}, facts=_MAIL + [
            ("arg", "invite_send", "_mail_lock_identities", 1, "me['steam_id']"),
            ("arg", "invite_send", "_invite_challenge_core", 2, "me"),
            ("once", "invite_send", "me"),
            ("argcall", "_invite_challenge_core", "_ffa_lobby_create_core", 0, "_FfaLobbyCreateReq",
             "steam_id", "me['steam_id']"),
            ("unbound", "_invite_challenge_core", "me"),
            ("arg", "_ffa_lobby_create_core", "_enrollment_identity_gate", 1, "req.steam_id"),
            ("unbound", "_ffa_lobby_create_core", "req"),
            ("raw", "_enrollment_identity_gate", "steam_id", "exclusive")]),
    ("_identity_lock_many", "_apply_ban_core"): dict(
        how="P2a", base=False,
        entries={"main.admin_ban", "main.admin_moderation_case_act", "main.internal_moderation_case_act"},
        facts=_MAIL + [
            ("arg", "admin_ban", "_mail_lock_identities", 2, "req.target_steam_id"),
            ("arg", "admin_ban", "_apply_ban_core", "target_steam_id", "req.target_steam_id"),
            ("unbound", "admin_ban", "req"),
            ("arg", "_moderation_case_act", "_mail_lock_identities", 2, "subject_sid_pre"),
            ("arg", "_moderation_case_act", "_apply_ban_core", "target_steam_id", "subject_sid_pre"),
            ("once", "_moderation_case_act", "subject_sid_pre"),
            ("raw", "_apply_ban_core", "target_steam_id", "exclusive"),
            ("unbound", "_apply_ban_core", "target_steam_id")]),
    ("_identity_lock_many", "_ban_lock_and_gate"): dict(
        how="P2a", base=False, entries={"main.submit_match"}, facts=[
            ("arg", "submit_match", "_identity_lock_many", 1, "_sids"),
            ("arg", "submit_match", "_ban_lock_and_gate", 1, "_sids"),
            ("arg", "submit_match", "_ban_lock_and_gate", "actor", "report.reported_by_steam_id"),
            ("nokw", "submit_match", "_ban_lock_and_gate", "exclusive"),
            ("src", "submit_match", "if report.reported_by_steam_id not in _sids:\n"
                                    "        raise HTTPException(status_code=400"),
            ("once", "submit_match", "_sids")]),
    ("_ban_lock_and_gate", "place_lobby_bet"): dict(
        how="P2a", base=True, entries={"main.place_lobby_bet", "main.place_discord_lobby_bet"},
        facts=[("arg", "place_lobby_bet", "_ban_lock_and_gate", 1, "[steam_id]"),
               ("arg", "place_lobby_bet", "_ban_lock_and_gate", "exclusive", "[steam_id]"),
               ("raw", "place_lobby_bet", "steam_id", "exclusive"),
               ("unbound", "place_lobby_bet", "steam_id")]),
    ("_identity_lock_many", "_identity_lock_many"): dict(
        how="P2b", base=True,
        entries={"main.ffa_lobby_assembly", "main.ffa_lobby_connect", "main.ffa_lobby_readmit",
                 "main.ffa_lobby_release", "main.ffa_queue_leave", "main.ffa_queue_poll"},
        facts=[("bound", "_identity_lock_many", "SET LOCAL lock_timeout", "55P03",
                "status_code=503")]),
    ("_guard_identities", "_guard_identities"): dict(
        how="P2b", base=True,
        entries={"match_hold.match_hold_bind", "match_hold.match_hold_claim",
                 "match_hold.match_hold_entered", "match_hold.match_hold_mine"},
        facts=[("bound", "mh:_install_database_timeouts", "set_config('lock_timeout'"),
               ("bound", "mh:_bounded_match_db", "async with database_deadline(db)")]
        + [("src", "mh:" + r, "Depends(_bounded_match_db)") for r in
           ("match_hold_bind", "match_hold_claim", "match_hold_entered", "match_hold_mine")]),
    ("_guard_identities", "_ban_lock_and_gate"): dict(
        how="P2a-typed", base=False, entries={"main.submit_ovt_match", "main.submit_team_match"},
        typed=("the report window's guard (_guard_identities, exclusive) holds every id the settle's "
               "gate asks for: the report's players and its reporter",
               "test_ban_sweep_locks_pg.py::test_v_the_settle_gate_asks_only_keys_the_window_guard_holds"),
        facts=[("arg", "_settle_ovt_report", "_settle_writer_ban_check", 1, "steams"),
               ("arg", "_settle_team_report", "_settle_writer_ban_check", 1, "steams"),
               ("nokw", "_settle_writer_ban_check", "_ban_lock_and_gate", "exclusive")]),
}


def _segments():
    out = {}
    for (entry, tk), _lines in _walk().segments.items():
        out.setdefault(tk, set()).add(entry)
    return out


def test_v_every_multi_call_segment_is_proved_and_every_proof_is_used():
    seg = _segments()
    unproved = {tk: sorted(e) for tk, e in seg.items() if tk not in PROOFS}
    moved = {tk: (sorted(e), sorted(PROOFS[tk]["entries"])) for tk, e in seg.items()
             if tk in PROOFS and e != PROOFS[tk]["entries"]}
    stale = sorted(set(PROOFS) - set(seg))
    assert (unproved, moved, stale) == ({}, {}, []), (unproved, moved, stale)


def test_v_every_proof_fact_holds():
    bad = {tk: r for tk, p in PROOFS.items() for r in [[check_fact(f) for f in p["facts"]]]
           if any(r)}
    assert bad == {}, bad
    # a lane-made sequence ends P1 or P2a only, never by a bound
    assert all(p["how"] != "P2b" for p in PROOFS.values() if not p["base"])


# ---------------------------------------------------------------- mutants

def _mutated(fname, old, new, mod="main"):
    """funcs with fname's source text changed (old must occur once)."""
    src = ast.unparse(_fn(fname, mod))
    assert src.count(old) >= 1, (fname, old)
    node = ast.parse(src.replace(old, new)).body[0]
    funcs = {m: dict(fs) for m, fs in _funcs().items()}
    funcs[mod][fname] = node
    return funcs


def test_v_mutant_another_key_expression_breaks_the_proof():
    m = _mutated("pc_dance_select", "_pc_verified_actor(request, steam_id,",
                 "_pc_verified_actor(request, other_id,")
    facts = PROOFS[("pc_dance_select", "_pc_verified_actor")]["facts"]
    assert [check_fact(f, m) for f in facts if check_fact(f, m)], "another expression went unseen"
    m2 = _mutated("submit_match", "_ban_lock_and_gate(db, _sids,", "_ban_lock_and_gate(db, [x],")
    assert check_fact(("arg", "submit_match", "_ban_lock_and_gate", 1, "_sids"), m2)
    # control: the unchanged tree proves both
    assert not any(check_fact(f) for f in facts)


def test_v_mutant_a_stronger_mode_breaks_the_proof():
    m = _mutated("_pc_verified_actor", "pg_advisory_xact_lock_shared(", "pg_advisory_xact_lock(")
    assert check_fact(("raw", "_pc_verified_actor", "steam_id", "shared"), m)
    m2 = _mutated("submit_match", "actor=report.reported_by_steam_id)",
                  "actor=report.reported_by_steam_id, exclusive=_sids)")
    assert check_fact(("nokw", "submit_match", "_ban_lock_and_gate", "exclusive"), m2)


def test_v_mutant_an_unbounded_new_key_turns_the_census_red():
    """A later raw take of another id after the gate: the walk finds a sequence
    no proof names, and the bound fact fails without its budget."""
    planted = ast.parse(
        "async def planted_route(db, a, b):\n"
        "    await _ban_lock_and_gate(db, [a], exclusive=[a])\n"
        "    await db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:sid))'), {'sid': b})\n"
        "    await db.commit()\n").body[0]
    planted.decorator_list = ast.parse("@app.post('/x')\ndef f(): pass").body[0].decorator_list
    funcs = {m: dict(fs) for m, fs in _funcs().items()}
    funcs["main"]["planted_route"] = planted
    w = K.KeyWalk(funcs)
    w.mods = ["main"]
    w.walk_entry("main", "planted_route")
    assert {tk for (_e, tk) in w.segments} == {("_ban_lock_and_gate", "planted_route")}
    assert ("_ban_lock_and_gate", "planted_route") not in PROOFS
    m = _mutated("_identity_lock_many", "lock_timeout", "lock_wait")
    assert check_fact(PROOFS[("_identity_lock_many", "_identity_lock_many")]["facts"][0], m)
    assert check_fact(PROOFS[("_identity_lock_many", "_identity_lock_many")]["facts"][0]) is None
    # control: the commit between two takes ends the segment
    ok = ast.parse(
        "async def planted_ok(db, a, b):\n"
        "    await _ban_lock_and_gate(db, [a], exclusive=[a])\n"
        "    await db.commit()\n"
        "    await db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:sid))'), {'sid': b})\n"
        "    await db.commit()\n").body[0]
    funcs["main"]["planted_ok"] = ok
    w2 = K.KeyWalk(funcs)
    w2.mods = ["main"]
    w2.walk_entry("main", "planted_ok")
    assert w2.segments == {}


# ---------------------------------------------------------------- savepoints, sorts

def test_v_no_identity_key_is_taken_in_a_savepoint_body():
    assert K.savepoint_taker_failures(_funcs()) == []


def test_v_savepoint_planted_case_and_control():
    planted = ast.parse(
        "async def planted_sp(db, s):\n"
        "    async with db.begin_nested():\n"
        "        await _grant_translator_achievements(db, s)\n").body[0]
    control = ast.parse(
        "async def control_sp(db, s):\n"
        "    await _grant_translator_achievements(db, s)\n"
        "    async with db.begin_nested():\n"
        "        await db.execute(text('SELECT 1'))\n").body[0]
    funcs = {m: dict(fs) for m, fs in _funcs().items()}
    funcs["main"]["planted_sp"] = planted
    funcs["main"]["control_sp"] = control
    got = K.savepoint_taker_failures(funcs)
    assert [g for g in got if "planted_sp" in g] and not [g for g in got if "control_sp" in g], got


def test_v_no_unkeyed_sort_over_ids_that_are_then_locked():
    assert K.unkeyed_sorts(_funcs()) == []
    planted = ast.parse(
        "async def planted_sort(db, ids):\n"
        "    for s in sorted(ids):\n"
        "        await _grant_translator_achievements(db, s)\n").body[0]
    control = ast.parse(
        "async def control_sort(db, ids):\n"
        "    for s in sorted(ids, key=identity_lock_key):\n"
        "        await _grant_translator_achievements(db, s)\n").body[0]
    funcs = {m: dict(fs) for m, fs in _funcs().items()}
    funcs["main"]["planted_sort"] = planted
    funcs["main"]["control_sort"] = control
    got = K.unkeyed_sorts(funcs)
    assert [g for g in got if "planted_sort" in g] and not [g for g in got if "control_sort" in g], got


# ---------------------------------------------------------------- class VI: slow steps

# Sites that stand at the base unchanged (not changed in this lane): the step,
# the key held across it and its mode, and the step's own time bound.
SLOW_LISTED = {
    ("_pc_lease_drain", "sleep"): (
        "the ban core's (or deletion's) EXCLUSIVE identity key on the target",
        "LEASE_SECONDS + 5 s, plus one sleep of at most 0.25 s"),
    ("_pc_steam_prime", "wait"): (
        "the bot actor's SHARED identity key (_pc_bot_actor)",
        "_PC_STEAM_PRIME_DEADLINE_S = 4.0 s"),
}


def _slow_sites(w):
    return {(where.split(":")[0], step) for (where, step) in K.slow_report(w)}


def test_vi_no_slow_step_under_a_key_but_the_listed_base_sites():
    got = _slow_sites(_walk())
    assert got <= set(SLOW_LISTED), sorted(got - set(SLOW_LISTED))
    assert ("_pc_lease_drain", "sleep") in got     # the list is not stale


def test_vi_planted_slow_step_is_found_and_control_is_not():
    planted = ast.parse(
        "async def planted_slow(db, sid):\n"
        "    await _ban_lock_and_gate(db, [sid], exclusive=[sid])\n"
        "    await asyncio.to_thread(_steam_http_get_json, 'u', 6.0)\n"
        "    await db.commit()\n").body[0]
    control = ast.parse(
        "async def control_slow(db, sid):\n"
        "    await _ban_gate_or_raise(db, sid)\n"
        "    await db.rollback()\n"
        "    await asyncio.to_thread(_steam_http_get_json, 'u', 6.0)\n"
        "    await _ban_lock_and_gate(db, [sid], exclusive=[sid])\n"
        "    await db.commit()\n").body[0]
    funcs = {m: dict(fs) for m, fs in _funcs().items()}
    for f in (planted, control):
        f.decorator_list = ast.parse("@app.post('/x')\ndef f(): pass").body[0].decorator_list
        funcs["main"][f.name] = f
    w = K.KeyWalk(funcs)
    for name in ("planted_slow", "control_slow"):
        w.mods = ["main"]
        w.walk_entry("main", name)
    got = _slow_sites(w)
    assert ("planted_slow", "to_thread") in got and ("control_slow", "to_thread") not in got, got


def test_vi_steam_auth_holds_no_key_across_the_steam_call():
    fn = _fn("steam_auth")
    src = ast.unparse(fn)
    assert "_ban_lock_and_gate(db, [req.steam_id], exclusive=[req.steam_id])" in src
    assert src.index("asyncio.to_thread(_steam_http_get_json") < src.index("_ban_lock_and_gate(")
    assert src.index("await db.rollback()") < src.index("asyncio.to_thread(")
    assert _raw_takes(fn) == []
