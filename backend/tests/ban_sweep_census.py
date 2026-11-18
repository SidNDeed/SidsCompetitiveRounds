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
    ("main", "team_queue_leave"): "the team queue leave (the assembly abandon uses it too): the caller's own row",
    ("main", "ovt_queue_leave"): "the 1v2 queue leave: the caller's own row",
    ("main", "ffa_queue_leave"): "the FFA queue leave: the caller's own row; a banned caller records no departure",
    ("main", "_lobby_leave_impl"): "the team and 1v2 lobby leave (both routes call it): the caller's own seat",
}

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
        "stamps last_seen and presence only under the caller's verified session, which a ban"
        " deletes; otherwise answers the online count and writes no row"),
    ("GET", "/api/v1/tournaments/players/{steam_id}/penalty"): (
        "a read of a player's penalty state; no caller identity, acts for no one"),
    ("GET", "/api/v1/series/active"): "a read of the open series list; no caller identity, acts for no one",
    ("GET", "/api/v1/team/series/{series_id}/state"): (
        "a read of one series' state; no caller identity, acts for no one"),
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
