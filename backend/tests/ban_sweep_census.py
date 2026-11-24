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
import os
import re

API = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))


# The ONE reader of statement text for the ban sweep's census files (RULING
# CENSUS-1, ORDER 3). A statement argument is the first argument of a bare
# text(...) call, or of a call whose first argument is not a text() call
# (db.execute("...")). It reads as text when it is a string constant, a name
# bound once at module level to such a text, or a + chain of those. Every
# census function below reads statement text through call_text(); one that
# cannot read an argument as text still reads its parts (the string constants
# under it, and every name in it that reads), as each place read before.
class StatementTexts:
    def __init__(self, sources):
        """sources: {module: source text or parsed module}."""
        self.binds = {}
        for mod, src in sources.items():
            self.binds[mod] = _module_bindings(src if isinstance(src, ast.AST) else ast.parse(src))

    def _bound(self, mod, name):
        if mod is not None:
            return self.binds.get(mod, {}).get(name, [])
        return [v for b in self.binds.values() for v in b.get(name, [])]

    def read(self, mod, x, _seen=()):
        """The text of x, or None when the rule cannot read it."""
        if isinstance(x, ast.Constant) and isinstance(x.value, str):
            return x.value
        if isinstance(x, ast.BinOp) and isinstance(x.op, ast.Add):
            a = self.read(mod, x.left, _seen)
            b = self.read(mod, x.right, _seen) if a is not None else None
            return None if b is None else a + b
        if isinstance(x, ast.Name) and x.id not in _seen:
            vals = self._bound(mod, x.id)
            if len(vals) == 1 and vals[0] is not None:
                v = vals[0]
                if isinstance(v, ast.Call) and _name_of(v) == "text" and isinstance(v.func, ast.Name) \
                        and len(v.args) == 1 and not v.keywords:
                    v = v.args[0]               # NAME = text(<readable>): the wrapper adds no text
                return self.read(mod, v, _seen + (x.id,))
        return None

    def parts(self, mod, x):
        """What the census reads of x: its text, or its readable parts."""
        t = self.read(mod, x)
        if t is not None:
            return t
        if isinstance(x, ast.BinOp) and isinstance(x.op, ast.Add):
            return self.parts(mod, x.left) + self.parts(mod, x.right)
        if isinstance(x, ast.JoinedStr):
            return "".join(v.value if isinstance(v, ast.Constant) else self.parts(mod, v.value)
                           for v in x.values if isinstance(v, (ast.Constant, ast.FormattedValue)))
        return "".join(c.value for c in ast.walk(x) if isinstance(c, ast.Constant) and isinstance(c.value, str))

    def call_text(self, mod, call):
        """What the census reads of a call's statement argument ("" for none)."""
        a = statement_argument(call)
        return "" if a is None else self.parts(mod, a)


def statement_argument(call):
    """A call's statement argument: X of text(X), or of execute(X) when X is
    not itself a text() call (that call is read as itself); None for none."""
    if not isinstance(call, ast.Call) or not call.args:
        return None
    a = call.args[0]
    if isinstance(a, ast.Call) and _name_of(a) == "text" and a.args:
        a = a.args[0]
    return a


def _module_bindings(tree):
    """{name: [value or None, ...]}: every binding of a name at module level
    (outside functions and classes), with its value when it is a plain
    `name = value` or `name: T = value`; None for any other binding."""
    out = {}
    stack = list(tree.body)
    while stack:
        st = stack.pop()
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.setdefault(st.name, []).append(None)
            continue
        if isinstance(st, (ast.Import, ast.ImportFrom)):
            for a in st.names:
                out.setdefault((a.asname or a.name).split(".")[0], []).append(None)
            continue
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            out.setdefault(st.targets[0].id, []).append(st.value)
            continue
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
            out.setdefault(st.target.id, []).append(st.value)
            continue
        for field in ("body", "orelse", "finalbody", "handlers"):
            stack.extend(x for x in getattr(st, field, []) if isinstance(x, ast.stmt))
        for h in getattr(st, "handlers", []):
            stack.extend(h.body)
            if h.name:
                out.setdefault(h.name, []).append(None)
        heads = [getattr(st, f) for f in ("targets", "target", "items") if hasattr(st, f)]
        for head in heads:
            for n in ast.walk(ast.Module(body=[], type_ignores=[]) if head is None else
                              (ast.Tuple(elts=list(head), ctx=ast.Load()) if isinstance(head, list) else head)):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    out.setdefault(n.id, []).append(None)
    return out


def statement_text_failures(sources):
    """sources: {module: source text}. The closed failure of ORDER 3: every
    statement argument, in every function of every module the census reads,
    that StatementTexts cannot read as text, as "module.function:line: form".
    A statement argument here is X of a bare text(X), or X of execute(X) or
    exec_driver_sql(X) when X is a string form (a constant, an f-string, a +,
    or a module-level name), never an ORM construct or a local holding one."""
    trees = {mod: ast.parse(src) for mod, src in sources.items()}
    texts = StatementTexts(trees)
    out = []
    for mod, tree in sorted(trees.items()):
        for fn in _functions(tree):
            for c in _own_nodes(fn):
                if not isinstance(c, ast.Call) or not c.args:
                    continue
                x = c.args[0]
                if isinstance(c.func, ast.Name) and c.func.id == "text":
                    pass
                elif _name_of(c) in ("execute", "exec_driver_sql") and not (
                        isinstance(x, ast.Call) and _name_of(x) == "text"):
                    if not (isinstance(x, (ast.Constant, ast.JoinedStr, ast.BinOp))
                            or isinstance(x, ast.Name) and x.id in texts.binds[mod]):
                        continue
                else:
                    continue
                if texts.read(mod, x) is None:
                    form = type(x).__name__ if not isinstance(x, ast.Name) else (
                        "module name" if x.id in texts.binds[mod] else "local name")
                    out.append(f"{mod}.{fn.name}:{c.lineno}: {form} {ast.unparse(x)[:80]!r}")
    return sorted(set(out))


_TEXTS = {}


def default_texts():
    """The reader over backend/api as it stands on disk."""
    if "api" not in _TEXTS:
        srcs = {}
        for fname in sorted(os.listdir(API)):
            if fname.endswith(".py"):
                with open(os.path.join(API, fname), encoding="utf-8") as fh:
                    srcs[fname[:-3]] = fh.read()
        _TEXTS["api"] = StatementTexts(srcs)
    return _TEXTS["api"]

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
    ("main", "submit_ovt_match"): (
        1, "a plain pre-check: the window's receipt takes the EXCLUSIVE identity guards of the "
           "game next, so a shared key here would be made exclusive there and two reporters of "
           "one game would wait for each other; the settle reads the ban again under the guards"),
    ("main", "submit_team_match"): (
        1, "a plain pre-check: the window's receipt takes the EXCLUSIVE identity guards of the "
           "game next, so a shared key here would be made exclusive there and two reporters of "
           "one game would wait for each other; the settle reads the ban again under the guards"),
    # FIX-2: reads made under identity keys a helper of the transaction's one
    # taking call already holds (exclusive), or a read that writes nothing.
    ("main", "steam_auth"): (
        1, "the early read before the Steam call takes no key and writes nothing: the transaction "
           "ends before the call, and the writing transaction reads the ban again under the "
           "account's exclusive key (_ban_lock_and_gate, exclusive=) before its first write"),
    ("auto_logs", "upload_auto_log"): (
        1, "the admission read takes no key and writes nothing: a refused upload takes no advisory "
           "lock and the scrub stays outside every lock (the route's rules before bans part 2a); "
           "the writing transaction (T2) reads the ban again under the account's shared key "
           "(_ban_lock_and_gate) before its INSERT"),
    ("main", "_report_window_receive"): (
        1, "the receipt's read, under the EXCLUSIVE identity guards _guard_identities took just "
           "before for every account of the report, before its first write"),
    ("main", "_moderation_case_act"): (
        1, "the actor's read, under the EXCLUSIVE identity key _mail_lock_identities took just "
           "before (actor and subject in one ordered pass), before its first write"),
    # STACK-SEAM-1 (R3): the held-report list's read form.
    ("main", "_qapply_verdict"): (
        1, "the held-report list's and digest's advisory read form (log=False): it takes no key and "
           "writes nothing; Accept and Credit read the same bans again under the shared identity keys "
           "(_ban_lock_and_gate, the body's call and Credit's) before their first write"),
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


def ban_writers_without_the_lock(rows, funcs_by_module, listed=None, lockers=None, texts=None):
    """Every BAN-class route that writes and reaches neither the locking
    helper nor an identity locker, unless listed; every listed route that
    no longer needs its entry; every locker whose own body executes no
    identity lock (a statement the reader reads, StatementTexts)."""
    listed = F4_LISTED if listed is None else listed
    lockers = IDENTITY_LOCKERS if lockers is None else lockers
    texts = default_texts() if texts is None else texts
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
        fns = [(m, f) for m, fs in funcs_by_module.items() for n, f in fs.items() if n == name]
        if not fns or not any(
                (isinstance(c, ast.Call) and _name_of(c) != "text"
                 and _IDENTITY_LOCK_SQL.search(texts.call_text(m, c)))
                or (isinstance(c, ast.Call) and _name_of(c) in lockers and _name_of(c) != name)
                for m, f in fns for c in _own_nodes(f)):
            out.append(f"{name}: listed as an identity locker and takes no identity lock")
    return out


# FIX-1B point 4: a transaction after the first reads its row again and
# checks the condition again. A BAN-class writer that can commit more than
# once on one path reads the ban under the lock (LOCK_CALLERS or an identity
# locker) in the transaction that ends at its LAST commit on that path, or is
# listed with its reason. The walk follows each path through the statements of
# the route and of the census's functions it calls (its own module's first) (if/else, loops, try,
# raise and return), carrying a small state: commits so far (0, 1, 2+),
# whether the open transaction has read the ban, and whether the transaction
# the last commit closed had. A savepoint's commit closes no transaction.
# Helpers whose transaction only removes the caller's live rows or prunes its
# own old rows are TRAILING_REMOVALS: their commits close no writing
# transaction. A commit of a session the function opens itself
# (`async with async_session() as x`) is that session's, not the route's. F4_LISTED routes read no ban under a lock at all and carry
# their reason there.
TRAILING_REMOVALS = {
    "_evict_other_queue_searching": (
        "after the caller's own commit, deletes the account's still-searching rows in the other "
        "queues (and returns a pre-room 1v1 partner to searching): it only ends live state, so a "
        "ban that commits first leaves it nothing to create"),
    "prune_auto_logs": "deletes the account's own auto logs past the keep count; it creates nothing",
}
MULTI_COMMIT_LISTED = {
    ("POST", "/api/v1/matches"): (
        "the closing transaction after the match commit advances a tournament bracket "
        "(advance_tournament_match); the ban core reads and writes no tournament row, so a ban "
        "committed between the two transactions leaves the bracket as one committed after both, "
        "and the result, rating and gold were written in the first transaction under the read"),
    ("GET", "/api/v1/team/queue/poll/{steam_id}"): (
        "after the preflight commit every writing transaction (a resume, the fresh formation) "
        "takes _identity_lock_many over the caller and the roster and revalidates their rows under "
        "it, and the ban core deletes a banned account's team_queue row under the same key. The "
        "walk also follows two paths that do not run: the formation loop with no pass (it runs "
        "at least once: max(_form_left, 1)) and its unlocked `break` with fewer than three, "
        "after which `if len(others) < 3` returns"),
    ("POST", "/api/v1/ffa/matches"): (
        "the transactions before the route's own are other due windows' settles: each is "
        "submit_ffa_match in journal mode, which reads the ban under the lock itself (the walk "
        "sees that recursion as its entry state), and the write after its 4xx only marks that "
        "report superseded, which moves no result, rating, gold or other player's game"),
    ("POST", "/api/v1/admin/quarantine/{qid}/accept"): (
        "the walk follows submit_ffa_match's settle of the lobby's due windows "
        "(_ffa_settle_due_windows_for_report), which runs only when neither the journal mode nor "
        "the held-report replay is set; the route runs submit_ffa_match inside _qapply_run, which "
        "sets the replay, so that settle does not run and the route's writes are the body's one "
        "commit, which reads the ban under the lock as on the report route"),
}
# Helpers whose paths that drop the lock or commit end in a value every caller
# returns at once; the walk cannot tie that value to the caller's test, so it
# keeps only the helper's paths the caller continues on. Each entry names the
# test its callers make, and return_guard_failures checks every caller makes it.
RETURN_GUARDED = {
    "_lock_group_snapshot": (
        "locked", "returns None after a rollback (no lock) and the caller returns at once on None; "
        "every row it returns is read under _identity_lock_many"),
    "_ffa_report_gate": (
        "uncommitted", "its commit (a journal row) returns mode 'answer' and the caller returns "
        "that answer at once; the path the caller continues on commits nothing"),
}
_END = "end"


def _is_txn_commit(c):
    if not (isinstance(c, ast.Call) and _name_of(c) == "commit" and isinstance(c.func, ast.Attribute)):
        return False
    base = c.func.value
    nm = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
    return "savepoint" not in nm.lower() and "nested" not in nm.lower()


def _runs_once(loop):
    it = getattr(loop, "iter", None)
    if not (isinstance(it, ast.Call) and _name_of(it) == "range" and it.args):
        return False
    vals = [a.value if isinstance(a, ast.Constant) else None for a in it.args]
    if len(vals) == 1:
        return isinstance(vals[0], int) and vals[0] >= 1
    lo, hi = vals[0], vals[1]
    if isinstance(lo, int) and isinstance(it.args[1], ast.BinOp) and isinstance(it.args[1].op, ast.Add):
        # range(1, x + 1) with a positive constant x
        l, r = it.args[1].left, it.args[1].right
        if isinstance(r, ast.Constant) and r.value == 1 and lo == 1:
            return True     # range(1, n + 1): n is a positive attempt count wherever it is used here
    return isinstance(lo, int) and isinstance(hi, int) and hi > lo


class _TxnWalk:
    """State: (writing commits 0/1/2, read in the open transaction, wrote in
    the open transaction, read in the writing transaction the last writing
    commit closed or None). A commit of a transaction that wrote nothing
    counts no transaction; it still ends the open one's lock."""

    def __init__(self, funcs_by_module, module, lockers):
        self.funcs = funcs_by_module
        self.mods = [module]   # the module of the function being walked
        self.lockers = lockers
        self.memo = {}
        self.own = [set()]     # per function: names bound to a session it opens itself
        self.loops = []        # per loop being walked: [states at continue, states at break]
        self.where = {}
        for m, fs in funcs_by_module.items():
            for n in fs:
                self.where.setdefault(n, []).append(m)

    def resolve(self, name):
        """The module of a called name: the caller's own, else the one other
        module of the census that defines it."""
        if name in self.funcs.get(self.mods[-1], {}):
            return self.mods[-1]
        ms = self.where.get(name, [])
        return ms[0] if len(ms) == 1 else None

    def call(self, mod, name, states, stack):
        out = set()
        for st in states:
            key = (mod, name, st)
            if key not in self.memo:
                self.memo[key] = {st}    # a recursion sees its entry state
                if name not in stack and len(stack) <= 10:
                    fn = self.funcs[mod][name]
                    self.own.append(set())
                    self.mods.append(mod)
                    try:
                        nxt, ret, _raised = self.block(fn.body, {st}, stack + (name,))
                    finally:
                        self.own.pop()
                        self.mods.pop()
                    outs = nxt | ret
                    kind = RETURN_GUARDED.get(name, (None,))[0]
                    if kind == "locked":
                        outs = {o for o in outs if o[1]}
                    elif kind == "uncommitted":
                        outs = {o for o in outs if (o[0], o[4]) == (st[0], st[4])}
                    self.memo[key] = outs
            out |= self.memo[key]
        return out

    def expr(self, node, states, stack):
        calls = sorted((c for c in ast.walk(node) if isinstance(c, ast.Call)),
                       key=lambda c: (c.lineno, c.col_offset))
        for c in calls:
            cn = _name_of(c)
            if _is_txn_commit(c) and not (isinstance(c.func.value, ast.Name)
                                          and c.func.value.id in self.own[-1]):
                at = f"{stack[-1]}:{c.lineno}"
                states = {(min(n + 1, 2), False, False, r, at) if w else (n, False, False, p, a)
                          for n, r, w, p, a in states}
            elif cn == "rollback" and isinstance(c.func, ast.Attribute) and not (
                    isinstance(c.func.value, ast.Name) and c.func.value.id in self.own[-1]):
                states = {(n, False, False, p, a) for n, _r, _w, p, a in states}
            elif cn in LOCK_CALLERS or cn in self.lockers:
                states = {(n, True, w, p, a) for n, _r, w, p, a in states}
            elif _write_call(c, cn):
                states = {(n, r, True, p, a) for n, r, _w, p, a in states}
            elif isinstance(c.func, ast.Name) and cn not in TRAILING_REMOVALS and self.resolve(cn):
                states = self.call(self.resolve(cn), cn, states, stack)
        return states

    def block(self, stmts, states, stack):
        """-> (states falling through, states returned, states raised)"""
        ret, raised = set(), set()
        for st in stmts:
            if not states:
                break
            if isinstance(st, ast.Raise):
                states = self.expr(st, states, stack)
                raised |= states
                return set(), ret, raised
            if isinstance(st, ast.Return):
                states = self.expr(st, states, stack) if st.value is not None else states
                return set(), ret | states, raised
            if isinstance(st, (ast.Continue, ast.Break)) and self.loops:
                self.loops[-1][0 if isinstance(st, ast.Continue) else 1].update(states)
                return set(), ret, raised
            if isinstance(st, ast.If):
                states = self.expr(st.test, states, stack)
                a, ra, xa = self.block(st.body, states, stack)
                b, rb, xb = self.block(st.orelse, states, stack)
                states, ret, raised = a | b, ret | ra | rb, raised | xa | xb
            elif isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
                head = st.iter if hasattr(st, "iter") else st.test
                states = self.expr(head, states, stack)
                self.loops.append([set(), set()])
                try:
                    once, r1, x1 = self.block(st.body, states, stack)
                    once |= self.loops[-1][0]
                    twice, r2, x2 = self.block(st.body, once, stack)
                    twice |= self.loops[-1][0]
                finally:
                    brk = self.loops.pop()[1]
                # a loop over range(a, b) with b - a >= 1 known runs at least once
                entry = set() if _runs_once(st) else states
                e, r3, x3 = self.block(st.orelse, entry | once | twice, stack)
                states, ret, raised = e | brk, ret | r1 | r2 | r3, raised | x1 | x2 | x3
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                for it in st.items:
                    states = self.expr(it.context_expr, states, stack)
                    # a session the function opens itself: its commits are another transaction
                    if (isinstance(it.context_expr, ast.Call) and isinstance(it.optional_vars, ast.Name)
                            and "session" in (_name_of(it.context_expr) or "").lower()):
                        self.own[-1].add(it.optional_vars.id)
                states, r, x = self.block(st.body, states, stack)
                ret, raised = ret | r, raised | x
            elif isinstance(st, ast.Try) or type(st).__name__ == "TryStar":
                body, r, x = self.block(st.body, states, stack)
                ret, raised = ret | r, raised | x
                # a handler can start wherever the body could raise: approximate by
                # the entry, the body's end and its explicit raises
                h_in = states | body | x
                after = set()
                caught = set()
                for h in st.handlers:
                    hs, rh, xh = self.block(h.body, h_in, stack)
                    after |= hs
                    ret, caught = ret | rh, caught | xh
                el, re_, xe = self.block(st.orelse, body, stack)
                after |= el
                ret, raised = ret | re_, raised | xe | caught
                if st.finalbody:
                    fin, rf, xf = self.block(st.finalbody, after | ret, stack)
                    after = fin
                    ret, raised = ret | rf, raised | xf
                states = after
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            else:
                states = self.expr(st, states, stack)
        return states, ret, raised


def last_transaction_paths(funcs_by_module, module, name, lockers=None):
    """The end states of every path through module.name that ends without
    raising (see _TxnWalk)."""
    lockers = IDENTITY_LOCKERS if lockers is None else lockers
    w = _TxnWalk(funcs_by_module, module, lockers)
    fn = funcs_by_module.get(module, {}).get(name)
    if fn is None:
        return []
    end, ret, _x = w.block(fn.body, {(0, False, False, None, None)}, (name,))
    return sorted(end | ret, key=repr)


def last_transaction_failures(rows, funcs_by_module, listed=None, lockers=None):
    """Every BAN-class writer with a path that commits twice or more whose
    last transaction read no ban under the lock, unless listed; every listed
    route that no longer needs its entry; every TRAILING_REMOVALS helper that
    does not exist."""
    listed = MULTI_COMMIT_LISTED if listed is None else listed
    res, _clf = census(rows, funcs_by_module)
    out, need = [], set()
    for method, path, module, name, _deps in rows:
        if BAN not in res[(method, path)][1] or not reaches(funcs_by_module, module, name, _write_call):
            continue
        if (method, path) in F4_LISTED:
            continue
        ends = last_transaction_paths(funcs_by_module, module, name, lockers)
        bad_at = sorted({a for n, _r, _w, p, a in ends if n >= 2 and p is False})
        if not bad_at:
            continue
        need.add((method, path))
        if (method, path) not in listed:
            out.append(f"{method} {path}: a path commits twice or more and its last transaction "
                       f"(to {', '.join(bad_at)}) reads the ban under no lock")
    for key in sorted(set(listed) - need):
        out.append(f"{key[0]} {key[1]}: listed for the last transaction and needs no entry")
    names = {n for fs in funcs_by_module.values() for n in fs}
    for h in sorted(set(TRAILING_REMOVALS) - names):
        out.append(f"{h}: listed in TRAILING_REMOVALS and not defined")
    return out


def return_guard_failures(funcs_by_module, guarded=None):
    """Every call of a RETURN_GUARDED helper that is not `x = await h(...)`
    followed at once by an `if` on x whose body returns."""
    guarded = RETURN_GUARDED if guarded is None else guarded
    out, seen = [], set()
    for mod, fs in sorted(funcs_by_module.items()):
        for fname, fn in sorted(fs.items()):
            for n in [fn, *_own_nodes(fn)]:
                for field in ("body", "orelse", "finalbody"):
                    block = getattr(n, field, None)
                    if not isinstance(block, list):
                        continue
                    for i, st in enumerate(block):
                        calls = [c for c in ast.walk(st) if isinstance(c, ast.Call) and _name_of(c) in guarded]
                        if not calls or isinstance(st, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With,
                                                         ast.AsyncWith, ast.Try)):
                            continue
                        for c in calls:
                            seen.add(_name_of(c))
                        ok = (isinstance(st, ast.Assign) and len(st.targets) == 1
                              and isinstance(st.targets[0], ast.Name) and i + 1 < len(block)
                              and isinstance(block[i + 1], ast.If)
                              and any(isinstance(x, ast.Name) and x.id == st.targets[0].id
                                      for x in ast.walk(block[i + 1].test))
                              and isinstance(block[i + 1].body[-1], ast.Return))
                        if not ok:
                            out.append(f"{mod}.{fname}:{st.lineno}: calls {_name_of(calls[0])} "
                                       f"without returning on its answer at once")
    for h in sorted(set(guarded) - seen):
        out.append(f"{h}: listed in RETURN_GUARDED and never called")
    return out


# F2 b: every table that stands after the migrations, classed by name. A
# table is created by a numbered migration (NNN_*.sql; the rollback and resume
# files are not migrations) and not dropped or renamed away by a later one, or
# it is an ORM model's table that the bootstrap creates (ranked_series). Each
# is classed: LIVE, live account state a ban must end; LEFT, rows linked to an
# account that a ban leaves (history, ledgers, records, or state whose every
# use refuses a banned account); NO_LINK, no account link. TABLE_CLASSES lives
# in ban_sweep_tables.py (one line per table).
LIVE, LEFT, NO_LINK = "live", "left", "no_link"
_SQL_CREATE = re.compile(
    r"\bcreate\s+(?:unlogged\s+)?table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?([a-z_][a-z_0-9]*)\"?", re.I)
_SQL_TEMP = re.compile(r"\bcreate\s+(?:global\s+|local\s+)?(?:temp|temporary)\s+table\b", re.I)
_SQL_DROP = re.compile(
    r"\bdrop\s+table\s+(?:if\s+exists\s+)?((?:(?:public\.)?\"?[a-z_][a-z_0-9]*\"?\s*,\s*)*"
    r"(?:public\.)?\"?[a-z_][a-z_0-9]*\"?)", re.I)
_SQL_RENAME = re.compile(
    r"\balter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:public\.)?\"?([a-z_][a-z_0-9]*)\"?"
    r"\s+rename\s+to\s+\"?([a-z_][a-z_0-9]*)\"?", re.I)
_MIGRATION = re.compile(r"[0-9]{3}[a-z]?_.*\.sql$")


def standing_tables(sql_files, orm_source=""):
    """sql_files: {file name: text}; orm_source: models.py. The set of tables
    standing after the numbered migrations in name order, plus the ORM's."""
    events = []
    for f in sorted(sql_files):
        if not _MIGRATION.match(f):
            continue
        sql = re.sub(r"--[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", sql_files[f], flags=re.S))
        for m in _SQL_CREATE.finditer(sql):
            if not _SQL_TEMP.match(sql, m.start()):
                events.append((f, m.start(), "create", m.group(1).lower()))
        for m in _SQL_DROP.finditer(sql):
            for t in m.group(1).split(","):
                events.append((f, m.start(), "drop", t.strip().replace('"', "").split(".")[-1].lower()))
        for m in _SQL_RENAME.finditer(sql):
            events.append((f, m.start(), "rename", (m.group(1).lower(), m.group(2).lower())))
    out = set()
    for _f, _p, kind, t in sorted(events, key=lambda e: (e[0], e[1])):
        if kind == "create":
            out.add(t)
        elif kind == "drop":
            out.discard(t)
        elif t[0] in out:
            out.discard(t[0])
            out.add(t[1])
    out |= set(re.findall(r'__tablename__\s*=\s*"([a-z_0-9]+)"', orm_source))
    return out


def table_class_failures(standing, classes):
    """Both ways: a standing table not classed; a classed table not standing;
    an entry with a class outside the three or an empty reason."""
    out = [f"{t}: stands after the migrations and is not classed" for t in sorted(set(standing) - set(classes))]
    out += [f"{t}: classed and does not stand" for t in sorted(set(classes) - set(standing))]
    out += [f"{t}: class {c!r} or its reason is not valid" for t, (c, why) in sorted(classes.items())
            if c not in (LIVE, LEFT, NO_LINK) or not str(why).strip()]
    return out


VOID_ROOTS = ("_apply_ban_core",)


def void_sql_text(funcs_by_module, roots=VOID_ROOTS, module="main", module_source=""):
    """Every string the void can run: the constants of the ban core and of
    every function of its module it reaches, and the constants of the module
    level tables those functions name (the f-string table maps)."""
    local = funcs_by_module.get(module, {})
    seen, stack = set(), list(roots)
    while stack:
        n = stack.pop()
        if n in seen or n not in local:
            continue
        seen.add(n)
        for c in ast.walk(local[n]):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in local:
                stack.append(c.func.id)
    reader = StatementTexts({module: module_source}) if module_source else default_texts()
    texts, names = [], set()
    for n in seen:
        for c in ast.walk(local[n]):
            if isinstance(c, ast.Constant) and isinstance(c.value, str):
                texts.append(c.value)
            elif isinstance(c, ast.Name):
                names.add(c.id)
            elif isinstance(c, ast.Call) and _name_of(c) != "text":
                texts.append(reader.call_text(module, c))
    if module_source:
        for node in ast.parse(module_source).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names
                                                     for t in node.targets):
                texts += [c.value for c in ast.walk(node.value)
                          if isinstance(c, ast.Constant) and isinstance(c.value, str)]
    return "\n".join(texts), seen


def void_coverage_failures(classes, void_text):
    """Every LIVE table must be named by the void: a statement that reads it
    (its discovery) and one that writes it, or its name as a table-map value
    the void interpolates into both."""
    out = []
    for t, (c, _why) in sorted(classes.items()):
        if c != LIVE:
            continue
        word = re.compile(r"(?<![a-z_0-9])" + re.escape(t) + r"(?![a-z_0-9])")
        if not word.search(void_text):
            out.append(f"{t}: a LIVE table the void never names")
    return out


# FIX-1B point 3: ONE order for the identity advisory key. A call that takes
# the bare identity key (hashtext of the steam id, shared or exclusive) inside
# a loop must sit in a function that sorts by identity_order.identity_lock_key;
# a function that takes one account's key is listed with its reason. Every
# other advisory key carries a literal prefix, so it is another family.
ORDER_KEY = "identity_lock_key"
_ADVISORY = re.compile(r"pg_advisory_xact_lock(_shared)?\(\s*hashtext\(", re.I)
_IDENTITY_KEY = re.compile(
    r"pg_advisory_xact_lock(_shared)?\(\s*hashtext\(\s*(:sid|CAST\(\s*:sid\s+AS\s+text\s*\))\s*\)\s*\)", re.I)
_ONE = "takes the key of one account per transaction; it orders nothing"
SINGLE_KEY_TAKERS = {
    ("main", "_enrollment_identity_gate"): _ONE,
    ("main", "_region_pings_store_task"): _ONE,
    ("main", "_portal_auth"): _ONE,
    ("main", "i18n_portal_session"): _ONE,
    ("main", "admin_i18n_sync_keys"): _ONE,
    ("main", "_pc_verified_actor"): _ONE,
    ("main", "_pc_claim_daily"): _ONE,
    ("main", "_pc_bot_actor"): _ONE,
    ("main", "_pc_steam_write"): _ONE,
    ("main", "pc_portrait_upload"): _ONE,
    ("main", "pc_motion_upload"): _ONE,
    ("main", "pc_dance_select"): _ONE,
    ("main", "admin_pc_portrait_clear"): _ONE,
    ("main", "music_rate"): _ONE,
    ("main", "delete_player_data"): _ONE,
    ("main", "_grant_translator_achievements"): _ONE,
    ("main", "_apply_ban_core"): _ONE,
    ("main", "ffa_readmit_offer"): _ONE,
    ("main", "place_lobby_bet"): _ONE,
    ("main", "cancel_lobby_bet"): _ONE,
    ("main", "set_allow_spectators"): _ONE,
    ("main", "_invite_identity_lock"): _ONE,
    # MDPL-GATE-REREAD-1 (b), round mdplg-r2: the four routes of part (b) and
    # their helper, main._player_deletion_key_shared_bounded, take no identity
    # key; the helper takes the two-key PLAYER_DELETION_LOCK_CLASS key, another
    # family, so it is not listed here (test_mdpl_gate_bound_pg.py holds its takers).
    ("tournaments", "signup"): _ONE,
}

# FIX-1B point 3: functions that reach both the shared read (LOCK_CALLERS) and an
# EXCLUSIVE identity key. A shared key later asked for exclusive waits for every
# other shared holder; two such transactions wait for each other. Each entry
# says why that cannot happen there.
_EXCL_FIRST = "the key it takes exclusive later is taken exclusive in the helper's own ordered pass (exclusive=)"
SHARED_AND_EXCLUSIVE = {
    ("main", "submit_match"): "every player's key is taken exclusive first (_identity_lock_many); the "
                              "shared read then finds its keys held",
    ("main", "place_lobby_bet"): _EXCL_FIRST,
    ("main", "place_discord_lobby_bet"): _EXCL_FIRST + " (through place_lobby_bet)",
    ("main", "submit_ovt_match"): "the receipt's exclusive guards come before the settle's shared read; "
                                  "the route's own read is plain (ROW_SERIALIZED)",
    ("main", "submit_team_match"): "the receipt's exclusive guards come before the settle's shared read; "
                                   "the route's own read is plain (ROW_SERIALIZED)",
}
_EXCLUSIVE_KEY = re.compile(
    r"pg_advisory_xact_lock\(\s*hashtext\(\s*(:sid|CAST\(\s*:sid\s+AS\s+text\s*\))\s*\)\s*\)", re.I)
EXCLUSIVE_TAKERS_BY_NAME = frozenset({"_identity_lock_many", "_guard_identities", "_guard_player_ids"})


def shared_and_exclusive_failures(sources, listed=None):
    """sources: {module: text}. Every function (other than the helpers) that
    reaches a LOCK_CALLERS call and an exclusive identity key, against the
    list, both ways."""
    listed = SHARED_AND_EXCLUSIVE if listed is None else listed
    funcs, trees = {}, {}
    for mod, src in sources.items():
        tree = trees[mod] = ast.parse(src)
        funcs[mod] = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    texts = StatementTexts(trees)
    takers = set(EXCLUSIVE_TAKERS_BY_NAME)
    for mod, fs in funcs.items():
        for n, fn in fs.items():
            if any(isinstance(c, ast.Call) and _name_of(c) != "text"
                   and _EXCLUSIVE_KEY.search(texts.call_text(mod, c))
                   for c in _own_nodes(fn)):
                takers.add(n)
    # The helper's own exclusive keys (exclusive=) are taken in its one ordered
    # pass, never after a shared key of the same transaction.
    takers -= LOCK_CALLERS
    found = set()
    for mod, fs in funcs.items():
        for n in fs:
            if n in LOCK_CALLERS:
                continue
            if (reaches(funcs, mod, n, lambda c, cn: cn in LOCK_CALLERS)
                    and (n in takers or reaches(funcs, mod, n, lambda c, cn: cn in takers))):
                found.add((mod, n))
    out = [f"{m}.{n}: reaches the shared read and an exclusive identity key, not listed"
           for m, n in sorted(found - set(listed))]
    out += [f"{m}.{n}: listed and no longer reaches both" for m, n in sorted(set(listed) - found)]
    return out


def _prefixed(v):
    if isinstance(v, ast.BinOp) and isinstance(v.left, ast.Constant) and isinstance(v.left.value, str):
        return bool(v.left.value) and not v.left.value.startswith("%")
    if isinstance(v, ast.JoinedStr) and v.values and isinstance(v.values[0], ast.Constant):
        return bool(v.values[0].value)
    return False


def _in_loop(fn, node):
    for n in _own_nodes(fn):
        if isinstance(n, (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp,
                          ast.GeneratorExp, ast.DictComp)):
            if any(c is node for c in ast.walk(n)):
                return True
    return False


def _orders_by_the_key(fn):
    return any(isinstance(c, ast.Call) and _name_of(c) in ("sorted", "min", "max")
               and any(k.arg == "key" and (getattr(k.value, "id", None) == ORDER_KEY
                                           or getattr(k.value, "attr", None) == ORDER_KEY)
                       for k in c.keywords)
               for c in _own_nodes(fn))


def identity_lock_failures(sources, single=None):
    """sources: {module: text}. Takers of several identity keys that do not
    order by the one key; single takers not listed (and listed ones that are
    not single takers); other advisory keys without a literal prefix."""
    single = SINGLE_KEY_TAKERS if single is None else single
    out, seen = [], set()
    trees = {mod: ast.parse(src) for mod, src in sources.items()}
    texts = StatementTexts(trees)
    for mod, tree in sorted(trees.items()):
        for fn in _functions(tree):
            for c in _own_nodes(fn):
                if not isinstance(c, ast.Call) or _name_of(c) == "text":
                    continue
                sql = texts.call_text(mod, c)
                if not _ADVISORY.search(sql):
                    continue
                if _IDENTITY_KEY.search(sql):
                    if _in_loop(fn, c):
                        if not _orders_by_the_key(fn):
                            out.append(f"{mod}.{fn.name}: takes several identity keys and does not order "
                                       f"by {ORDER_KEY}")
                    else:
                        seen.add((mod, fn.name))
                        if (mod, fn.name) not in single:
                            out.append(f"{mod}.{fn.name}: takes one identity key and is not listed")
                    continue
                if re.search(r"hashtext\(\s*'[^']+'", sql):
                    continue
                binds = [a for a in c.args[1:] if isinstance(a, ast.Dict)]
                vals = [v for d in binds for k, v in zip(d.keys, d.values)
                        if isinstance(k, ast.Constant) and f":{k.value}" in sql]
                if not vals or not all(_prefixed(v) for v in vals):
                    out.append(f"{mod}.{fn.name}: an advisory key that is neither the identity key "
                               f"nor prefixed")
    for key in sorted(set(single) - seen):
        out.append(f"{key[0]}.{key[1]}: listed as a single identity-key taker and takes none")
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
    ("main", "admin_accept_quarantine", "submit_ffa_match", "call"): (
        1, "the held-report Accept (QAPPLY-1): the stored body runs through the report route's body under _qapply_run"),
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
    trees = {mod: ast.parse(src) for mod, src in sources.items()}
    texts = StatementTexts(trees)
    for mod, tree in sorted(trees.items()):
        for fn in _functions(tree):
            if fn.name in LOCK_CALLERS:
                continue
            nodes = list(_own_nodes(fn))
            at = [c.lineno for c in nodes if isinstance(c, ast.Call) and _name_of(c) in LOCK_CALLERS]
            if not at:
                continue
            first = min(at)
            locks = sorted(c.lineno for c in nodes
                           if (isinstance(c, ast.Constant) and isinstance(c.value, str)
                               and _ROW_LOCK_SQL.search(c.value)
                               or isinstance(c, ast.Call) and _name_of(c) != "text"
                               and _ROW_LOCK_SQL.search(texts.call_text(mod, c)))
                           and c.lineno < first)
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
        # the module is not known here: a name reads when it is bound once
        # at module level across backend/api (StatementTexts, module None)
        return any(isinstance(c, ast.Constant) and isinstance(c.value, str) and _WRITE_SQL.search(c.value)
                   for c in ast.walk(call)) or bool(
            call.args and _WRITE_SQL.search(default_texts().parts(None, call.args[0])))
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
