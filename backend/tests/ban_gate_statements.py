"""The statements the ban gate (bans part 2a) adds to a route's path, read
from the product's own source, never retyped.

A scripted session (a test double that answers each statement a route may
issue) that models one fault must answer these with what a database with no
active ban answers: the identity key is granted and the ban read finds no
row. Doubles match a statement by its whitespace-normalised text against the
sets below, so a change of the product's text changes what they match, and a
statement the gate does not issue is never answered by them.

Read from: main._ban_lock_and_gate (the identity key, shared and exclusive),
main._ban_gate_any_or_raise (the read of several ids) and main._is_banned
(the read of one id).
"""
import ast
import inspect
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import main  # noqa: E402


def norm(sql) -> str:
    return " ".join(str(sql).split())


def text_statements(fn):
    """Every `text(<expr>)` argument of fn, evaluated in main's namespace
    (string constants, concatenations and calls of main's SQL builders).
    An argument that cannot be evaluated so raises: nothing is left out."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "text" and node.args:
            code = compile(ast.Expression(node.args[0]), "<gate statement>", "eval")
            out.append(norm(eval(code, dict(vars(main)))))
    return out


_LOCK_WORDS = ("pg_advisory_xact_lock(", "pg_advisory_xact_lock_shared(")
GATE_LOCKS = frozenset(s for s in text_statements(main._ban_lock_and_gate)
                       if any(w in s for w in _LOCK_WORDS))
BAN_READS = frozenset([*text_statements(main._is_banned),
                       *text_statements(main._ban_gate_any_or_raise)])


def ban_lobby_read_nodes():
    """The f-string argument(s) of text() in main._apply_ban_core that read an
    account's open lobbies (they name host_player_id): the ban core's lobby
    read, one statement per entry of main._BAN_LOBBY_TABLES."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(main._apply_ban_core)))
    return [node.args[0] for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "text" and node.args
            and "host_player_id" in ast.unparse(node.args[0])]


def _ban_lobby_reads():
    nodes = ban_lobby_read_nodes()
    assert len(nodes) == 1, len(nodes)
    code = compile(ast.Expression(nodes[0]), "<ban lobby read>", "eval")
    out = []
    for mode, qt, lt in main._BAN_LOBBY_TABLES:
        ns = dict(vars(main))
        ns.update(_lmode=mode, _lqt=qt, _llt=lt)
        out.append(norm(eval(code, ns)))
    return frozenset(out)


# the ban core's read of the open lobbies an account hosts or sits in (one per
# lobby kind); a double that seats nobody answers it with no row
BAN_LOBBY_READS = _ban_lobby_reads()
assert len(BAN_LOBBY_READS) == 3, BAN_LOBBY_READS


def _void_reads():
    """main._ban_void_lock's reads of the live series and started lobbies an
    account is in (one per kind): every text() argument of that function but
    its row lock, the one f-string (it runs only for a row a read found)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(main._ban_void_lock)))
    args = [node.args[0] for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "text" and node.args]
    locks = [a for a in args if isinstance(a, ast.JoinedStr)]
    assert len(locks) == 1 and "FOR NO KEY UPDATE" in ast.unparse(locks[0]), \
        [ast.unparse(a) for a in locks]
    out = []
    for a in args:
        if a is not locks[0]:
            code = compile(ast.Expression(a), "<ban void read>", "eval")
            out.append(norm(eval(code, dict(vars(main)))))
    return frozenset(out)


# the ban core's reads of the live series and started lobbies the account is
# in (bans part 2a, S4); a double whose account is in none answers no row
BAN_VOID_READS = _void_reads()
assert len(BAN_VOID_READS) == 4, BAN_VOID_READS


_PURGE_SELECTORS = ("lfp_pings", "_INVITE_END_INVITEE_SQL",
                    "DELETE FROM queue_leases WHERE player_id = :pid")


def _core_purges():
    """The ban core's purges that bans part 2a added and that run for every
    account with a players row (each selected by a word of its source, its
    text evaluated from the product): the queued looking-for-players post,
    the invites the account received, the account's queue leases."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(main._apply_ban_core)))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "text" and node.args:
            src = ast.unparse(node.args[0])
            if any(w in src for w in _PURGE_SELECTORS):
                code = compile(ast.Expression(node.args[0]), "<ban core purge>", "eval")
                out.append(norm(eval(code, dict(vars(main)))))
    assert len(out) == len(_PURGE_SELECTORS), out
    return frozenset(out)


BAN_CORE_PURGES = _core_purges()


def _spectate_leave_all():
    """main._spectate_leave_rows's statements in the form the ban takes (F2 d:
    lease_id None, every lease of the account not yet revoked): `pick` is the
    else arm of its own conditional, read from the source."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(main._spectate_leave_rows)))
    picks = [n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "pick" for t in n.targets)]
    assert len(picks) == 1 and isinstance(picks[0], ast.IfExp), picks
    pick = ast.literal_eval(picks[0].orelse)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "text" and node.args:
            ns = dict(vars(main))
            ns["pick"] = pick
            code = compile(ast.Expression(node.args[0]), "<spectate leave>", "eval")
            out.append(norm(eval(code, ns)))
    assert len(out) == 2, out
    return frozenset(out)


# the ban's spectate leave of every live lease of the account (F2 d); a double
# whose account spectates nothing answers no row
BAN_SPECTATE_LEAVE = _spectate_leave_all()
assert len(GATE_LOCKS) == 2, GATE_LOCKS
assert all("FROM player_bans" in s for s in BAN_READS) and len(BAN_READS) == 2, BAN_READS


class NoBanResult:
    """What the ban read answers on a database with no active ban."""
    def first(self):
        return None

    def all(self):
        return []

    def scalar(self):
        return None

    def scalar_one_or_none(self):
        return None

    def mappings(self):
        return self


class KeyGranted(NoBanResult):
    """What a granted pg_advisory_xact_lock[_shared] answers (one void row)."""
    def first(self):
        return (None,)

    def all(self):
        return [(None,)]
