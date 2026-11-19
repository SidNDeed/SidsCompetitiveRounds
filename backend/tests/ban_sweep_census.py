"""Bans part 2a: how every state-changing route refuses an actively banned
account. The data of test_ban_sweep_census.py and its classifier.

A route is in scope when it is a POST, PUT, PATCH or DELETE route of the app,
the chat websocket, or a GET named in read_gate.WRITE_ON_GET. Its handler, and
every dependency FastAPI resolves for it, is classed by HOW it refuses, read
from the module's AST:

  a refusing call statement   `await _check_steam_session(...)`,
                              `await _check_ban_or_raise(...)`,
                              `_require_admin(...)`, `_require_internal_key(...)`,
                              or a call of a module-level function that is
                              itself classed (the class is inherited);
  a refusing `if`             an `if` whose body raises and whose test refuses
                              on the strict session (`not await
                              _strict_steam_session_ok(...)`, a
                              `_seat_attestation_verdict(...)` compared unequal),
                              on the admin signature (`not
                              _verify_admin_hmac(...)`), on the internal key
                              (`x_internal_key` compared, `not
                              internal_key_valid(...)`), or on a ban read
                              (`_is_banned(...)`, `_active_ban_details(...)`).

Only statements every call of the function executes count: the function's own
body, and the bodies of `with`, `async with` and `try` blocks in it, never the
body of an `if`, a loop or an exception handler. A check whose answer only
grants something (the bug report's rate exemption reads the strict session and
raises on nothing) is therefore no refusal.

Classes: STRICT (refuses without a verified session in every mode; a ban
deletes the account's sessions and sign-in refuses it), SOFT
(`_check_steam_session` without `banned_ok`, which refuses an actively banned
claimed id where it would admit an unverified request), BAN (refuses an
actively banned acting account by models.player_ban_active_sql), ADMIN (the
admin signature and `_is_admin`, which refuses an actively banned admin),
INTERNAL (the internal credential). A route with none of these is OPEN and
must be in OPEN with its reason; a route whose only gate is a SOFT call with
`banned_ok=True` must be in OPEN as well.

INTERNAL alone does not say for whom the route acts. Every route whose only
class is INTERNAL is listed in INTERNAL_ONLY with what it acts on; a route of
that list that acts for a player names the player read in BAN as well, so it
is not INTERNAL alone.
"""
from __future__ import annotations

import ast
import re

STRICT, SOFT, BAN, ADMIN, INTERNAL, OPEN = "STRICT", "SOFT", "BAN", "ADMIN", "INTERNAL", "OPEN"
# the two halves of an inline admin check: the roster (`not await
# _is_admin(...)`, which refuses an actively banned admin) and the admin
# signature (`not _verify_admin_hmac(...)`); a route is ADMIN only with both
ADMIN_MEMBER, ADMIN_SIG = "admin-roster", "admin-signature"
# the class a route is counted under when it holds more than one
PRECEDENCE = (BAN, STRICT, ADMIN, SOFT, INTERNAL)

RAISING_CALLS = {
    "_check_ban_or_raise": BAN,
    "_ban_gate_or_raise": BAN,
    "_ban_lock_and_gate": BAN,
    "_settle_writer_ban_check": BAN,
    "_ban_gate_any_or_raise": BAN,
    "_require_admin": ADMIN,
    "_require_internal_key": INTERNAL,
}
SOFT_CALL = "_check_steam_session"
BANNED_OK_KW = "banned_ok"

# Every function that calls the soft check with banned_ok=True: the exits of
# BAN-R4 / BAN-R17. Each removes only the caller's own queue or lobby state.
# The census asserts the derived set of callers equals this exactly.
BANNED_OK = {
    ("main", "queues_escape"): "the queue escape: removes the caller's own queue rows in every mode",
    ("main", "queue_leave"): "the 1v1 queue leave: removes the caller's own queue row",
    ("main", "queue_decline"): (
        "the 1v1 queue decline: the caller's own row and, only while it still points back at the"
        " caller, the matched partner's row back to searching"),
    ("main", "team_queue_leave"): "the team queue leave (the assembly abandon uses it too): the caller's own row",
    ("main", "ovt_queue_leave"): "the 1v2 queue leave: the caller's own row",
    ("main", "ffa_queue_leave"): "the FFA queue leave: the caller's own row; a banned caller records no departure",
    ("main", "_lobby_leave_impl"): "the team and 1v2 lobby leave (both routes call it): the caller's own seat",
}

# BAN-R17's list, typed from RULINGS.md (ban-part2-design): the calls a locked
# client may still send. "A locked client may still send its own leave, decline
# and escape calls: the queue escape, the 1v1 queue leave and decline, the team
# queue leave (the assembly abandon uses it too), the 1v2 queue leave, the FFA
# queue leave, the lobby leave and the direct queue leave of each mode, and the
# spectate leave." The server's exits (server_exits) must equal it both ways.
BAN_R17_EXITS = {
    ("POST", "/api/v1/queues/escape"): "the queue escape",
    ("POST", "/api/v1/queue/leave"): "the 1v1 queue leave",
    ("POST", "/api/v1/queue/decline"): "the 1v1 queue decline",
    ("POST", "/api/v1/team/queue/leave"): "the team queue leave (the assembly abandon uses it too)",
    ("POST", "/api/v1/ovt/queue/leave"): "the 1v2 queue leave",
    ("POST", "/api/v1/ffa/queue/leave"): "the FFA queue leave",
    ("POST", "/api/v1/team/lobby/leave"): "the 2v2 lobby leave",
    ("POST", "/api/v1/ovt/lobby/leave"): "the 1v2 lobby leave",
    ("POST", "/api/v1/spectate/leave"): "the spectate leave",
}

# Exits that keep the STRICT session requirement for everyone and read no ban:
# a banned account that holds a session reaches them, nobody without one does.
# server_exits counts one only while its handler reaches no ban read.
STRICT_EXITS = {
    ("POST", "/api/v1/spectate/leave"): (
        "revokes the caller's own spectate lease and writes its drain tombstone; strict session, no ban read"),
}

# Every call that reads an account's ban for a refusal.
BAN_READS = frozenset({
    "_is_banned", "_ban_gate_or_raise", "_ban_gate_any_or_raise", "_check_ban_or_raise",
    "_is_banned_via_session", "_active_ban_details", "_ban_lock_and_gate", "_settle_writer_ban_check",
})


# F4: the sweep's two ban reads. Outside the locking helper each call is a
# finding unless listed here with the row lock that serializes it against the
# ban core (which takes that row after the target's identity lock).
SWEEP_GATE_READS = frozenset({"_ban_gate_or_raise", "_ban_gate_any_or_raise"})
LOCK_HELPER = "_ban_lock_and_gate"
LOCK_CALLERS = frozenset({LOCK_HELPER, "_settle_writer_ban_check"})
ROW_SERIALIZED = {
    ("main", "team_series_report_dc"): (
        1, "the roster read under the team_series FOR NO KEY UPDATE row lock; an identity "
           "lock taken after that row lock would invert the ban core's order"),
}
# A row lock written before a locking-helper call in the same function, on a
# table the ban core never locks.
ROW_LOCK_BEFORE_OK = {
    ("main", "link_discord"): "the expired link_codes prune (FOR UPDATE SKIP LOCKED); "
                              "the ban core never locks link_codes",
}
_ROW_LOCK_SQL = re.compile(r"\bFOR\s+(UPDATE|NO\s+KEY\s+UPDATE|SHARE|KEY\s+SHARE)\b", re.I)


# F4: a BAN-class handler that writes reaches the locking helper, or one of
# these functions, each of which takes the identity lock of the same key
# itself (shared, or exclusive, which is stronger) before its ban read.
IDENTITY_LOCKERS = {
    "_identity_lock_many": "exclusive identity locks of a roster, in the canonical order",
    "_enrollment_identity_gate": "the exclusive identity lock, then the ban read",
    "_pc_verified_actor": "the shared identity lock, then the ban read (player cards)",
    "_pc_claim_daily": "the shared identity lock, then the ban read (the bot's daily claim)",
    "_pc_bot_actor": "the shared identity lock, then the ban read (the bot's pack open)",
}
_IDENTITY_LOCK_SQL = re.compile(r"pg_advisory_xact_lock(_shared)?\(hashtext\(")
_I18N = ("the translation portal: it writes the portal session (issue, refresh, touch) and translation "
         "content rows a reviewer judges; no gold, XP, rating, match or series record, stored report or "
         "another player's state")
_CHAT = ("a chat line of the account's own, which moderators remove; no gold, XP, rating, match or "
         "series record, stored report or another player's state")
F4_LISTED = {
    **{("GET", "/api/v1/i18n/" + p): _I18N for p in (
        "approved", "contributors", "grants/mine", "history", "keys", "progress", "proposals")},
    **{("POST", "/api/v1/i18n/" + p): _I18N for p in (
        "portal-session", "portal-session/refresh", "proposals", "revert", "review")},
    ("POST", "/api/v1/chat/post"): _CHAT,
    ("WS", "/api/v1/ws/chat"): _CHAT,
}


def ban_writers_without_the_lock(rows, funcs_by_module, listed=None, lockers=None):
    """Every BAN-class route that writes and reaches neither the locking
    helper nor an identity locker, unless listed; every listed route that
    no longer needs its entry; every locker whose own body holds no
    identity lock."""
    listed = F4_LISTED if listed is None else listed
    lockers = IDENTITY_LOCKERS if lockers is None else lockers
    res, _clf = census(rows, funcs_by_module)
    out, need = [], set()
    for method, path, module, name, _deps in rows:
        if BAN not in res[(method, path)][1] or not reaches(funcs_by_module, module, name, _write_call):
            continue
        if reaches(funcs_by_module, module, name, lambda c, cn: cn in LOCK_CALLERS or cn in lockers):
            continue
        need.add((method, path))
        if (method, path) not in listed:
            out.append(f"{method} {path}: a BAN-class writer that reads the ban under no identity lock")
    for key in sorted(set(listed) - need):
        out.append(f"{key[0]} {key[1]}: listed for F4 and needs no entry")
    for name in sorted(lockers):
        fns = [f for m in funcs_by_module.values() for n, f in m.items() if n == name]
        if not fns or not any(
                (isinstance(c, ast.Constant) and isinstance(c.value, str) and _IDENTITY_LOCK_SQL.search(c.value))
                or (isinstance(c, ast.Call) and _name_of(c) in lockers and _name_of(c) != name)
                for f in fns for c in _own_nodes(f)):
            out.append(f"{name}: listed as an identity locker and takes no identity lock")
    return out


# F1 c: each mode's insert core, and every place the code names it. Each core
# reads the ban itself (a LOCK_CALLERS call in its own body), so every site
# reaches the writer's check; a site not listed here turns the census red.
INSERT_CORES = {
    "submit_match": "1v1", "submit_ffa_match": "FFA",
    "_settle_ovt_report": "1v2", "_settle_team_report": "2v2",
}
INSERT_CORE_SITES = {
    ("main", "submit_ovt_match", "_settle_ovt_report", "call"): (1, "the 1v2 report route"),
    ("main", "_report_window_settle", "_settle_ovt_report", "ref"): (
        1, "the report window's settle: route receipt, janitor, horizon and release settle through it"),
    ("main", "<module>", "_settle_ovt_report", "ref"): (2, "constant checks on its code object; no call"),
    ("main", "submit_team_match", "_settle_team_report", "call"): (1, "the 2v2 report route"),
    ("main", "_report_window_settle", "_settle_team_report", "ref"): (
        1, "the report window's settle: route receipt, janitor, horizon and release settle through it"),
    ("main", "<module>", "_settle_team_report", "ref"): (1, "the ladder hook sites tuple; no call"),
    ("main", "_ffa_settle_report", "submit_ffa_match", "call"): (
        1, "the FFA report journal: the janitor and the report route's due windows"),
    ("main", "<module>", "submit_ffa_match", "ref"): (
        6, "route-table, ladder-hook, writer and gate lists and code-object checks; no call"),
    ("main", "<module>", "submit_match", "ref"): (1, "the ladder hook sites tuple; no call"),
}


def insert_core_failures(sources, sites=None, cores=None):
    """sources: {module: source text}. A core whose own body does not call a
    LOCK_CALLERS function, and every naming of a core whose (module,
    enclosing function, core, call|ref) count differs from the list."""
    sites = INSERT_CORE_SITES if sites is None else sites
    cores = INSERT_CORES if cores is None else cores
    out, seen = [], {}
    for mod, src in sorted(sources.items()):
        tree = ast.parse(src)
        parent = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        for fn in _functions(tree):
            if fn.name in cores and not any(isinstance(c, ast.Call) and _name_of(c) in LOCK_CALLERS
                                            for c in _own_nodes(fn)):
                out.append(f"{mod}.{fn.name}: the {cores[fn.name]} insert core reads no ban under the lock")
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Name) and n.id in cores and isinstance(n.ctx, ast.Load)):
                continue
            p, q, enc = parent.get(n), n, None
            while q in parent and enc is None:
                q = parent[q]
                if isinstance(q, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    enc = q.name
            kind = "call" if isinstance(p, ast.Call) and p.func is n else "ref"
            key = (mod, enc or "<module>", n.id, kind)
            seen[key] = seen.get(key, 0) + 1
    for key, n in sorted(seen.items()):
        want = sites.get(key, (0, ""))[0]
        if n != want:
            out.append(f"{key}: named {n} time(s), {want} listed")
    for key in sorted(set(sites) - set(seen)):
        out.append(f"{key}: listed and not found")
    return out


def _own_nodes(fn):
    """The nodes of fn's body, nested function definitions left out (each is
    a function of its own)."""
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield n
        stack.extend(ast.iter_child_nodes(n))


def _functions(tree):
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _name_of(call):
    f = call.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)


def unlocked_gate_reads(sources, row_serialized=None):
    """sources: {module: source text}. Every function that calls a sweep gate
    read itself (not through the locking helper) more often than
    row_serialized allows, and every listed entry that no longer matches."""
    row_serialized = ROW_SERIALIZED if row_serialized is None else row_serialized
    out, seen = [], {}
    for mod, src in sorted(sources.items()):
        for fn in _functions(ast.parse(src)):
            if fn.name == LOCK_HELPER or fn.name in SWEEP_GATE_READS:
                continue
            n = sum(1 for c in _own_nodes(fn) if isinstance(c, ast.Call) and _name_of(c) in SWEEP_GATE_READS)
            if not n:
                continue
            seen[(mod, fn.name)] = n
            allowed = row_serialized.get((mod, fn.name), (0, ""))[0]
            if n != allowed:
                out.append(f"{mod}.{fn.name}: {n} ban read(s) outside {LOCK_HELPER}, {allowed} listed")
    for key, (n, _why) in sorted(row_serialized.items()):
        if key not in seen:
            out.append(f"{key[0]}.{key[1]}: listed as row-serialized and calls no gate read")
    return out


def row_locks_before_the_gate(sources, ok=None):
    """Every function in which SQL text that locks rows is written before its
    first locking-helper call (by source position), unless listed."""
    ok = ROW_LOCK_BEFORE_OK if ok is None else ok
    out, seen = [], set()
    for mod, src in sorted(sources.items()):
        for fn in _functions(ast.parse(src)):
            if fn.name in LOCK_CALLERS:
                continue
            nodes = list(_own_nodes(fn))
            at = [c.lineno for c in nodes if isinstance(c, ast.Call) and _name_of(c) in LOCK_CALLERS]
            if not at:
                continue
            first = min(at)
            locks = sorted(c.lineno for c in nodes
                           if isinstance(c, ast.Constant) and isinstance(c.value, str)
                           and _ROW_LOCK_SQL.search(c.value) and c.lineno < first)
            if not locks:
                continue
            seen.add((mod, fn.name))
            if (mod, fn.name) not in ok:
                out.append(f"{mod}.{fn.name}: a row lock at line {locks[0]} before the identity lock at {first}")
    for key in sorted(set(ok) - seen):
        out.append(f"{key[0]}.{key[1]}: listed and takes no row lock before the identity lock")
    return out


def _calls_in(fn):
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            yield n, (n.func.id if isinstance(n.func, ast.Name) else (
                n.func.attr if isinstance(n.func, ast.Attribute) else None))


def reaches(funcs_by_module, module, name, pred, _seen=None):
    """Whether module.name, or a function of its module it calls (at any
    position), holds a call for which pred(call node, call name) is true."""
    seen = set() if _seen is None else _seen
    if (module, name) in seen:
        return False
    seen.add((module, name))
    fn = funcs_by_module.get(module, {}).get(name)
    if fn is None:
        return False
    local = funcs_by_module.get(module, {})
    for call, cn in _calls_in(fn):
        if cn is not None and pred(call, cn):
            return True
        if isinstance(call.func, ast.Name) and cn in local and reaches(funcs_by_module, module, cn, pred, seen):
            return True
    return False


def _soft_ok_call(call, cn):
    return cn == SOFT_CALL and any(
        k.arg == BANNED_OK_KW and not (isinstance(k.value, ast.Constant) and k.value.value is False)
        for k in call.keywords)


def server_exits(rows, funcs_by_module, strict_exits=None):
    """The routes a banned account may still call: every route whose handler or
    dependency reaches the soft check with banned_ok, and every STRICT_EXITS
    route whose handler reaches no ban read. Returns ({key}, [problems])."""
    strict_exits = STRICT_EXITS if strict_exits is None else strict_exits
    out, bad = set(), []
    for method, path, module, name, deps in rows:
        key = (method, path)
        targets = [(module, name), *deps]
        if any(reaches(funcs_by_module, m, n, _soft_ok_call) for m, n in targets):
            out.add(key)
        if key in strict_exits:
            if any(reaches(funcs_by_module, m, n, lambda c, cn: cn in BAN_READS) for m, n in targets):
                bad.append(f"{key}: a STRICT_EXITS route that reads a ban")
            else:
                out.add(key)
    for key in sorted(set(strict_exits) - {(r[0], r[1]) for r in rows}):
        bad.append(f"{key}: a STRICT_EXITS entry no route matches")
    return out, bad


# M2: the READ class. A route outside the write scope (a GET that
# read_gate.WRITE_ON_GET does not name) and refused by no class is READ, and a
# READ handler may reach no writing statement: a text() statement that inserts,
# updates, deletes, truncates or merges, a SQLAlchemy insert/update/delete
# construct, or a session add/delete/merge/commit. Followed through every
# function of the handler's own module that it calls, at any position.
READ = "READ"
_WRITE_SQL = re.compile(
    r"\bINSERT\s+INTO\b|\bDELETE\s+FROM\b|\bTRUNCATE\b|\bMERGE\s+INTO\b"
    r"|\bUPDATE\s+[\w.\"]+(?:\s+(?:AS\s+)?\w+)?\s+SET\b", re.I)
_WRITE_NAMES = frozenset({"insert", "update", "delete", "pg_insert"})
_WRITE_METHODS = frozenset({"add", "add_all", "delete", "merge", "commit"})


def _write_call(call, cn):
    if cn == "text":
        return any(isinstance(c, ast.Constant) and isinstance(c.value, str) and _WRITE_SQL.search(c.value)
                   for c in ast.walk(call))
    if isinstance(call.func, ast.Name) and cn in _WRITE_NAMES:
        return True
    if not (isinstance(call.func, ast.Attribute) and cn in _WRITE_METHODS):
        return False
    # the receiver must be a database session (db, session, conn, ...), not a
    # Python set or dict
    recv = call.func.value
    rname = recv.id if isinstance(recv, ast.Name) else (recv.attr if isinstance(recv, ast.Attribute) else "")
    return bool(re.search(r"(^|_)(db|session|sess|conn)$", rname))


# READ routes whose handler reaches a write, each with what it writes. None
# writes for the caller's account: each write is a function of the clock or of
# standings, or an audit row of the read itself.
_PODIUM_SYNC = (
    "the podium holder sync (_podium_player_ids -> _sync_podium_holders): grants and revokes the"
    " podium title by the leaderboard's top three, the same for every caller and none, in its own"
    " session; skipped on the read-only standby")
READ_WRITES: dict = {
    ("GET", "/api/v1/achievements/{key}/earners"): _PODIUM_SYNC,
    ("GET", "/api/v1/chat/recent"): _PODIUM_SYNC,
    ("GET", "/api/v1/ffa/leaderboard"): _PODIUM_SYNC,
    ("GET", "/api/v1/ffa/lobbies"): _PODIUM_SYNC,
    ("GET", "/api/v1/ffa/recent"): _PODIUM_SYNC,
    ("GET", "/api/v1/leaderboard"): _PODIUM_SYNC,
    ("GET", "/api/v1/ovt/leaderboard"): _PODIUM_SYNC,
    ("GET", "/api/v1/ovt/lobbies"): _PODIUM_SYNC,
    ("GET", "/api/v1/players/{steam_id}"): _PODIUM_SYNC,
    ("GET", "/api/v1/players/{steam_id}/matches"): _PODIUM_SYNC,
    ("GET", "/api/v1/presence/online"): _PODIUM_SYNC,
    ("GET", "/api/v1/records"): _PODIUM_SYNC,
    ("GET", "/api/v1/spectate/games"): _PODIUM_SYNC,
    ("GET", "/api/v1/team/all-series-paged"): _PODIUM_SYNC,
    ("GET", "/api/v1/team/leaderboard"): _PODIUM_SYNC,
    ("GET", "/api/v1/team/lobbies"): _PODIUM_SYNC,
    ("GET", "/api/v1/admin/quarantine/triage"): (
        "_triage_read_txn commits its read-only transaction (lock and idle timeouts set); no row is written"),
    ("GET", "/api/v1/admin/quarantine/triage/{mode}/{group_id}"): (
        "_triage_read_txn commits its read-only transaction (lock and idle timeouts set); no row is written"),
    ("GET", "/api/v1/chat/moderate/mutes"): (
        "the session check's backfill of steam_auth_seen_at on the caller's own player row (a verified"
        " mint's stamp); no game state"),
    ("GET", "/api/v1/internal/evidence-report/game/{code}"): (
        "the admin evidence report's audit row of the read (admin_evidence._audit)"),
    ("GET", "/api/v1/internal/evidence-report/pair"): (
        "the admin evidence report's audit row of the read (admin_evidence._audit)"),
    ("GET", "/api/v1/internal/evidence-report/player/{steam_id}"): (
        "the admin evidence report's audit row of the read (admin_evidence._audit)"),
    ("GET", "/api/v1/internal/evidence-report/series/{code}"): (
        "the admin evidence report's audit row of the read (admin_evidence._audit)"),
    ("GET", "/api/v1/music/ratings"): (
        "the ratings fold: deletes rating rows already folded into the published figures, by the clock"),
}


def read_failures(read_rows, funcs_by_module, read_writes=None, by_hand=None):
    """The READ census: (rows, [problems]). Each read route is classed as the
    write census classes it, and one refused by no class is READ; a READ route
    that reaches a write and is not on READ_WRITES is a problem."""
    read_writes = READ_WRITES if read_writes is None else read_writes
    result, _ = census(read_rows, funcs_by_module, by_hand)
    rowmap = {(r[0], r[1]): r for r in read_rows}
    out, bad = {}, []
    for key, (prim, cls) in sorted(result.items()):
        if prim != OPEN:
            out[key] = prim
            continue
        out[key] = READ
        _, _, module, name, deps = rowmap[key]
        if any(reaches(funcs_by_module, m, n, _write_call) for m, n in [(module, name), *deps]):
            if key not in read_writes:
                bad.append(f"{key}: a READ route that reaches a writing statement and is not on READ_WRITES")
        elif key in read_writes:
            bad.append(f"{key}: on READ_WRITES but reaches no writing statement")
    for key in sorted(set(read_writes) - set(result)):
        bad.append(f"{key}: a READ_WRITES entry no read route matches")
    return out, bad


def exits_vs_r17(server, r17=None):
    """Both directions of BAN-R17's list against the server's exits."""
    r17 = BAN_R17_EXITS if r17 is None else r17
    return ([f"{k}: on BAN-R17's list and not an exit of the server" for k in sorted(set(r17) - set(server))]
            + [f"{k}: an exit of the server and not on BAN-R17's list" for k in sorted(set(server) - set(r17))])


# Conditional refusals the AST walk does not model, each held to the call it
# names: (method, path) -> (class, (calls an `if` that refuses must test), why).
# An entry whose named call no refusing `if` of the handler tests adds nothing.
BY_HAND: dict = {
    ("WS", "/api/v1/ws/chat"): (
        BAN, ("_is_banned_via_session",),
        "each message is dropped when its sender is actively banned (`continue`), the socket stays open"),
    ("POST", "/api/v1/chat/post"): (
        BAN, ("_is_banned_via_session",),
        "the bot's Discord relay: a message whose linked account is actively banned is dropped"),
    ("POST", "/api/v1/admin/team/series/{series_id}/resolve"): (
        ADMIN, ("internal_ok", "admin_ok"),
        "the internal key, or admin_ok = _is_admin (which refuses a banned admin) and the admin signature"),
}

# Routes open to an actively banned account, one reason each. An entry no
# route matches fails the census, and so does a route classed otherwise.
OPEN_ROUTES = {
    ("POST", "/api/v1/queue/leave"): "an exit (BAN-R4): removes the caller's own 1v1 queue row",
    ("POST", "/api/v1/queue/decline"): (
        "an exit (BAN-R17): the 1v1 decline; a mismatched pair writes nothing, and the ban removed"
        " the account's queue row"),
    ("POST", "/api/v1/queues/escape"): "an exit (BAN-R4): removes the caller's own rows in every mode",
    ("POST", "/api/v1/team/queue/leave"): "an exit (BAN-R4): the caller's own 2v2 row",
    ("POST", "/api/v1/ovt/queue/leave"): "an exit (BAN-R4): the caller's own 1v2 row",
    ("POST", "/api/v1/ffa/queue/leave"): (
        "an exit (BAN-R4): the caller's own FFA row; a departure is recorded only from an 'active'"
        " lobby and the ban has voided every lobby the account is in, so the exit records no count"),
    ("POST", "/api/v1/team/lobby/leave"): "an exit (BAN-R17): the caller's own 2v2 lobby seat",
    ("POST", "/api/v1/ovt/lobby/leave"): "an exit (BAN-R17): the caller's own 1v2 lobby seat",
    ("POST", "/api/v1/tournaments/{tournament_id}/unsignup"): (
        "an exit: withdraws the caller's own signup; a banned signup is forfeited at activation"),
    ("DELETE", "/api/v1/players/{steam_id}/data"): (
        "account data deletion (BAN-R11): open to a banned account by design"),
    ("GET", "/api/v1/presence/ping"): (
        "WRITES: stamps last_seen and presence only under the caller's verified session, which a ban"
        " deletes; otherwise answers the online count and writes no row"),
    ("GET", "/api/v1/series/active"): (
        "WRITES: _prune_stale_series marks a ranked series older than 30 minutes with no reported game"
        " 'abandoned' and refunds its bets, and commits. No caller identity: the 1.41.0 client's bet UI"
        " (ApiClient /series/active) and the bot poll it with none, so there is no account to refuse."
        " Any request, a banned caller's too, can only run that clock-earned prune earlier"),
    ("GET", "/api/v1/team/series/{series_id}/state"): (
        "WRITES: an 'active' series past its assembly deadline with fewer than four spawn-confirms"
        " becomes 'canceled' (assembly_timeout) with its bets reconciled, and a 'dc_paused' series past"
        " its deadline becomes 'dc_incomplete'; both commit. No caller identity: the 1.41.0 client polls"
        " it after ready_join as the lifecycle route (there is no read-only probe), so there is no"
        " account to refuse. Any request can only run those clock-earned transitions earlier, and a"
        " series a ban voided is terminal, so neither arm finds it"),
}

# Routes whose only class is INTERNAL: what each acts on. None acts for a
# player account; each that does names the player read in BAN instead.
INTERNAL_ONLY = {
    ("POST", "/api/v1/internal/mail/reply-from-discord"): (
        "the Discord relay of a mail reply; the reply core's sender gates refuse a banned sender"
        " (_mail_sender_gates reads _is_banned)"),
    ("POST", "/api/v1/internal/mail/relay-threads"): "the bot's relay thread bookkeeping (mail_discord bind contract)",
    ("POST", "/api/v1/internal/mail/relay-pref"): (
        "a player's Discord relay preference: delivery plumbing, not a game action (mail_discord bind contract)"),
    ("POST", "/api/v1/internal/logs/auto/prune"): "retention prune of uploaded logs",
    ("POST", "/api/v1/internal/recent-flags/ack"): "the bot's acknowledgement of a posted flag",
    ("POST", "/api/v1/internal/release-posts"): "release announcement posts",
    ("POST", "/api/v1/internal/rank-role-colors"): "Discord rank role colours",
    ("POST", "/api/v1/admin/set-discord-username"): "the bot's sync of a linked Discord name into the player row",
    ("POST", "/api/v1/internal/chat/bridge"): "stream-platform chat relay; its authors are platform identities",
    ("POST", "/api/v1/internal/chat/mirrors"): "the bot's mirror bookkeeping of chat messages",
    ("POST", "/api/v1/internal/chat/bridge-moderation"): "stream-platform moderators' actions; no player account acts",
    ("POST", "/api/v1/internal/chat/discord-deleted"): "the bot reports a Discord-side deletion",
    ("POST", "/api/v1/internal/chat/discord-mute"): "a Discord moderator's mute, proved by the bot; no player account acts",
    ("POST", "/api/v1/internal/chat/lockdown"): "a chat lockdown toggle by the bot",
    ("POST", "/api/v1/internal/chat/mod-actions/ack"): "the bot's acknowledgement of relayed moderation actions",
    ("POST", "/api/v1/internal/pc/events/ack"): "the bot's acknowledgement of delivery events",
    ("POST", "/api/v1/internal/pc/lease"): "the bot's delivery lease; a ban drains these leases itself",
    ("DELETE", "/api/v1/internal/pc/lease/{lease_id}"): "release of the bot's delivery lease",
    ("POST", "/api/v1/internal/channel-posts/ack"): "the bot's acknowledgement of channel posts",
    ("POST", "/api/v1/internal/stream-posts/ack"): "the bot's acknowledgement of stream posts",
    ("POST", "/api/v1/internal/tournament-notices/ack"): "the bot's acknowledgement of tournament notices",
    ("POST", "/api/v1/internal/pending-dms/ack"): "the bot's acknowledgement of sent DMs",
    ("POST", "/api/v1/internal/lfp-pings/ack"): "the bot's acknowledgement of looking-for-players pings",
    ("POST", "/api/v1/internal/bug-reports/events/ack"): "the bot's acknowledgement of bug-report events",
    ("POST", "/api/v1/internal/bug-reports/{report_id}/channel-posted"): "the bot records a bug report's channel post",
    ("POST", "/api/v1/internal/bug-reports/{report_id}/comment"): "a staff or system comment; no player account acts",
    ("POST", "/api/v1/admin/maintenance/start"): "maintenance mode, operator only",
    ("POST", "/api/v1/admin/maintenance/stop"): "maintenance mode, operator only",
    ("POST", "/api/v1/admin/team/rebuild-glicko"): "a ratings rebuild, operator only",
    ("POST", "/api/v1/internal/quarantine/digest/posted"): "the bot records a posted quarantine digest",
    ("POST", "/api/v1/internal/moderation-cases/{case_id}/notified"): "the bot records a case notice",
}



def _unconditional(body):
    """The statements of `body` every execution reaches, descending into
    with/try blocks only."""
    for st in body:
        yield st
        if isinstance(st, (ast.With, ast.AsyncWith)):
            yield from _unconditional(st.body)
        elif isinstance(st, ast.Try) or type(st).__name__ == "TryStar":
            yield from _unconditional(st.body)
            yield from _unconditional(st.finalbody)
        elif (isinstance(st, ast.For) and isinstance(st.iter, ast.Call)
              and isinstance(st.iter.func, ast.Name) and st.iter.func.id == "range"):
            # a bounded retry loop, `for attempt in range(N)`: its first pass
            # runs (every such loop in the app counts from a positive
            # module constant)
            yield from _unconditional(st.body)


def _unawait(node):
    return node.value if isinstance(node, ast.Await) else node


def _call_name(node):
    node = _unawait(node)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id, node
        if isinstance(node.func, ast.Attribute):
            return node.func.attr, node
    return None, None


def _kw_true(call, name):
    for k in call.keywords:
        if k.arg == name and isinstance(k.value, ast.Constant) and k.value.value is True:
            return True
    return False


def _negated_calls(test):
    """Names of calls the test refuses on when they answer false: `not f(...)`
    anywhere in a boolean `or`."""
    out = set()
    parts = test.values if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or) else [test]
    for p in parts:
        if isinstance(p, ast.UnaryOp) and isinstance(p.op, ast.Not):
            n, _ = _call_name(p.operand)
            if n:
                out.add(n)
    return out


def _if_classes(st):
    """The classes a refusing `if` statement holds."""
    if not any(isinstance(b, (ast.Raise, ast.Return)) for b in st.body):
        return set()
    out = set()
    test = st.test
    neg = _negated_calls(test)
    if "_strict_steam_session_ok" in neg:
        out.add(STRICT)
    if "_verify_admin_hmac" in neg:
        out.add(ADMIN_SIG)
    if "_is_admin" in neg:
        out.add(ADMIN_MEMBER)
    if "internal_key_valid" in neg:
        out.add(INTERNAL)
    parts = test.values if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or) else [test]
    for p in parts:
        if isinstance(p, ast.Compare):
            names = {n.id for n in ast.walk(p) if isinstance(n, ast.Name)}
            consts = {n.value.lower() for n in ast.walk(p)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            if (("x_internal_key" in names or "x-internal-key" in consts)
                    and any(isinstance(o, (ast.NotEq, ast.IsNot)) for o in p.ops)):
                out.add(INTERNAL)
            cn, _ = _call_name(p.left)
            if cn == "_seat_attestation_verdict" and any(isinstance(o, (ast.NotEq, ast.IsNot)) for o in p.ops):
                out.add(STRICT)
            if cn in ("_is_banned", "_active_ban_details") and any(isinstance(o, ast.IsNot) for o in p.ops):
                out.add(BAN)
        else:
            cn, _ = _call_name(p)
            if cn in ("_is_banned", "_active_ban_details"):
                out.add(BAN)
    return out


class Classifier:
    """Classes of module-level functions, memoised, over {module: {name: def}}."""

    def __init__(self, funcs_by_module):
        self.funcs = funcs_by_module
        self.memo = {}
        self.soft_ok_callers = set()

    def classes(self, module, name, _stack=()):
        key = (module, name)
        if key in self.memo:
            return self.memo[key]
        fn = self.funcs.get(module, {}).get(name)
        if fn is None or key in _stack:
            return set()
        out = set()
        for st in _unconditional(fn.body):
            if isinstance(st, ast.If):
                out |= _if_classes(st)
                continue
            if isinstance(st, (ast.For, ast.AsyncFor)):
                # a roster loop: an `if` in its body that refuses on a ban
                # read refuses for every member it walks
                for inner in st.body:
                    if isinstance(inner, ast.If):
                        out |= _if_classes(inner) & {BAN}
                continue
            value = getattr(st, "value", None)
            if not isinstance(st, (ast.Expr, ast.Assign, ast.AnnAssign, ast.Return)) or value is None:
                continue
            cn, call = _call_name(value)
            if cn is None:
                continue
            if cn == SOFT_CALL:
                if _kw_true(call, BANNED_OK_KW):
                    self.soft_ok_callers.add(key)
                else:
                    out.add(SOFT)
            elif cn in RAISING_CALLS:
                out.add(RAISING_CALLS[cn])
            elif isinstance(_unawait(value).func, ast.Name) and cn in self.funcs.get(module, {}):
                out |= self.classes(module, cn, _stack + (key,))
            # a coroutine handed to a runner as its argument
            # (`return await _guarded(db, _work_tx(...))`) runs inside it
            for arg in call.args:
                an, acall = _call_name(arg)
                if an and isinstance(_unawait(arg).func, ast.Name) and an in self.funcs.get(module, {}):
                    out |= self.classes(module, an, _stack + (key,))
        self.memo[key] = out
        return out

    def all_soft_ok_callers(self):
        """Every function anywhere that calls the soft check with banned_ok=True,
        conditional positions included."""
        found = set()
        for module, funcs in self.funcs.items():
            for name, fn in funcs.items():
                for n in ast.walk(fn):
                    if isinstance(n, ast.Call):
                        cn = n.func.id if isinstance(n.func, ast.Name) else (
                            n.func.attr if isinstance(n.func, ast.Attribute) else None)
                        # any banned_ok value but a literal False counts (an
                        # expression may be true)
                        if cn == SOFT_CALL and any(
                                k.arg == BANNED_OK_KW and not (
                                    isinstance(k.value, ast.Constant) and k.value.value is False)
                                for k in n.keywords):
                            found.add((module, name))
        return found


def primary(classes):
    for c in PRECEDENCE:
        if c in classes:
            return c
    return OPEN


def _hand_holds(funcs_by_module, module, name, call):
    """Whether module.name holds an `if` whose test calls `call` and whose body
    raises, returns or continues: the refusal a BY_HAND entry claims."""
    fn = funcs_by_module.get(module, {}).get(name)
    if fn is None:
        return False
    for n in ast.walk(fn):
        if not isinstance(n, ast.If):
            continue
        named = {_call_name(c)[0] for c in ast.walk(n.test) if isinstance(c, ast.Call)}
        named |= {c.id for c in ast.walk(n.test) if isinstance(c, ast.Name)}
        if call not in named:
            continue
        if any(isinstance(b, (ast.Raise, ast.Return, ast.Continue)) for s in n.body for b in ast.walk(s)):
            return True
    return False


def census(rows, funcs_by_module, by_hand=None):
    """rows: [(method, path, module, endpoint_name, [(module, dependency name)])].
    Returns ({(method, path): (primary class, sorted classes)}, classifier)."""
    by_hand = BY_HAND if by_hand is None else by_hand
    clf = Classifier(funcs_by_module)
    out = {}
    for method, path, module, name, deps in rows:
        cls = set(clf.classes(module, name))
        for dmod, d in deps:
            cls |= clf.classes(dmod, d)
        if {ADMIN_MEMBER, ADMIN_SIG} <= cls:
            cls.add(ADMIN)
        cls -= {ADMIN_MEMBER, ADMIN_SIG}
        hand = by_hand.get((method, path))
        if hand is not None:
            for call in hand[1]:
                if not _hand_holds(funcs_by_module, module, name, call):
                    break
            else:
                cls.add(hand[0])
        out[(method, path)] = (primary(cls), tuple(sorted(cls)))
    return out, clf


def failures(rows, funcs_by_module, open_routes=None, internal_only=None, banned_ok=None,
             by_hand=None):
    """Every way the census fails, as text lines (empty = it holds)."""
    open_routes = OPEN_ROUTES if open_routes is None else open_routes
    internal_only = INTERNAL_ONLY if internal_only is None else internal_only
    banned_ok = BANNED_OK if banned_ok is None else banned_ok
    by_hand = BY_HAND if by_hand is None else by_hand
    result, clf = census(rows, funcs_by_module, by_hand)
    bad = []
    for key in sorted(set(by_hand) - set(result)):
        bad.append(f"{key}: a BY_HAND entry no route matches")
    for key, (prim, cls) in sorted(result.items()):
        if prim == OPEN and key not in open_routes:
            bad.append(f"{key}: refuses no banned account and is not in OPEN_ROUTES")
        if prim != OPEN and key in open_routes:
            bad.append(f"{key}: is in OPEN_ROUTES but is classed {prim}")
        if cls == (INTERNAL,) and key not in internal_only:
            bad.append(f"{key}: INTERNAL alone and not in INTERNAL_ONLY")
        if cls != (INTERNAL,) and key in internal_only:
            bad.append(f"{key}: in INTERNAL_ONLY but classed {cls}")
    for key in sorted(set(open_routes) - set(result)):
        bad.append(f"{key}: an OPEN_ROUTES entry no route matches")
    for key in sorted(set(internal_only) - set(result)):
        bad.append(f"{key}: an INTERNAL_ONLY entry no route matches")
    callers = clf.all_soft_ok_callers()
    for c in sorted(callers - set(banned_ok)):
        bad.append(f"{c}: calls the soft check with banned_ok and is not in BANNED_OK")
    for c in sorted(set(banned_ok) - callers):
        bad.append(f"{c}: in BANNED_OK but makes no banned_ok call")
    return bad
