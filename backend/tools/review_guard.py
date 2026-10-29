"""The no-tunables guard for the public review code.

The public review code describes evidence and evaluates rules generically;
every value that decides an outcome belongs to the rules revision, which is
not part of this repository. This guard checks that, as a transitive analysis
over the source of every tree it is given:

  * JUDGING modules (review_measures, review_rules, identity_clock_measures,
    card_measures, combat_measures, and any local module one of them imports) are
    scanned whole: code, module-level constants, string constants (SQL and
    text included) and comments;
  * seat_evidence, identity_clock_evidence, card_evidence and combat_evidence
    are scanned from their REVIEW ROOTS
    (every function that
    touches the review modules or a loaded ruleset) through every module
    -level function and constant they reach, and main.py from its review
    worker functions the same way; any local module either imports is
    followed and scanned whole.

Within that reach it refuses:
  number   a numeric constant (after folding constant arithmetic) unless its
           CONTEXT makes it structural (STRUCTURAL below: a subscript index
           or slice bound on a computed value; 0 in any comparison and 1 or -1
           only in an equality test; a step of 1, a halving, a millisecond
           conversion or an integer wrap in arithmetic; 0, 1, -1 or 2 as a
           call argument; 0, 1 or -1 anywhere else) or it sits inside a
           PINNED contract bound whose value matches. A structural value used
           as a threshold (`x > 2`, `x * 2 > y`) is therefore refused;
  select   a string constant compared against a value (==, !=, in, not in,
           including the members of a literal collection on the right of
           `in`) that is not one of the closed public SELECTORS, so a new
           kind, label or category cannot decide anything unseen;
  bool     a module-level True/False binding that is not PINNED, a
           comparison against True or False other than the three-valued
           identity test (`is True`, `is False`), and a True/False constant as an
           if, while-else, conditional-expression or boolean-operator operand
           (`while True:` is the one structural form);
  text     a digit inside a string constant or comment, other than a
           standalone 0 or 1 and the closed set of identifiers that carry one;
  call     a value decoded from a constant (int/float/Decimal/json of a
           constant string, len of a constant) and the dynamic forms
           (eval, exec, compile, chr, ord, getattr/globals/vars, base64,
           codecs, importlib, __import__, bytes.fromhex);
  setting  a runtime setting read other than the operational switches, or
           the settings table named outside the one reader;
  env      an environment read other than the allowlisted keys;
  pinned   a pinned bound whose value differs from its pin (a large wire
           layout is pinned by the sha256 of its literal value's repr);
  unresolved  a value with no runtime input that the guard cannot evaluate
           (a constant passed into code it does not follow, a comprehension
           over constants, a container written or aliased with constants)
           reaching a decision: the guard fails toward refusal, never
           passes such a value as unknown.
  ambiguous  a value that more than one binding of one name may hold (a
           name or attribute bound more than once, a method name with more
           than one definition a call may reach) with any closed member,
           reaching a decision: it does not resolve to one binding, so it is
           refused with the binding sites (`module:line`, its owners) listed.

Every value above is judged WHERE IT IS USED, following its binding within
the module: a constant assigned once to a name (module level or function
local) and used later, a class attribute (`self.X`, `cls.X`, `Klass.X`), a
value of a literal dict (`D["k"]`), a parameter default, and a function whose
every return is one constant (`f()`) each stand for their value at the use, so
`LIMIT = 1` ... `x > LIMIT` is judged as `x > 1`, `strict = True` ... `if
strict:` as `if True:`, and `KIND = "k"` ... `x == KIND` as `x == "k"`. A
parameter default is followed only when it is a boolean. A
PINNED name is judged by its pin, not at its uses; a name bound more than once
is decided over all its bindings (below).

Resolution is TRANSITIVE (fix pass 3): a binding whose value is another
binding, an annotated binding, arithmetic on constants, an entry or slice of
a constant tuple, list or dict (`T[1]`, `D.get("k")`), an attribute set once
in a method (`self.X = 1`), an attribute or name imported from another local
module (`rm.X`, `from m import X`) and a call to a function whose every
return is one constant (any arguments) are all followed to their value, in
any order and through any depth (`base = 1; cut = base; v > cut` is judged as
`v > 1`). A mutable container is a constant only while nothing writes or
aliases it.

Modes:
  python backend/tools/review_guard.py tree <repo dir>
  python backend/tools/review_guard.py range <repo dir> <base> <tip>
        every commit of base..tip, each tree checked on its own (a value
        that lived only in an earlier commit is still in the landing range)

Attributes and rebound names are resolved by OWNER and use site (fix pass
4): a read of `self.X` sees the bindings of X on its own class, the classes
it derives from and the classes deriving from it, plus every binding of X on
a receiver whose class cannot be named; a read on an unnamed receiver sees
every binding of X; bindings in the other judged modules count the same way.
Over the bindings a read sees, one assignment stands for its value, a single
constant moved only by augmented updates is a counter (runtime), bindings
that all read runtime input are runtime, and more than one binding with any
closed value is AMBIGUOUS (fix pass 5): the guard resolves a decision name to
one binding or refuses it -- at a decision it is the exit-3 refusal naming
every binding site, and anywhere else every closed member, a boolean
included, is judged at the use as if it stood alone. A name bound more than
once (module level, `global` stores included, or a local) is decided the same
way, and so is a method name with more than one definition a call may reach.
One function whose returns are different constants, and a conditional or a
boolean operator whose operands differ, are a CHOICE made by that code's own
control flow: every closed member is judged at the use (a boolean member of
such a choice is run-time state and is not judged). A value that cannot be
evaluated at all stays unresolved and is refused at a decision.

Output: one line per finding, `<commit|tree> <path>:<line> <class>` (never
the offending text), then `review_guard: <n> finding(s) in <m> tree(s)`.
Exit 0 clean, 1 findings, 2 usage or a tree that could not be read, 3 no
verdict: an unresolved or ambiguous value reaches a decision (precedence over
1).
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import io
import itertools
import os
import re
import subprocess
import sys
import tokenize

API = "backend/api/"
JUDGING = ("review_measures", "review_rules", "identity_clock_measures", "card_measures",
           "combat_measures")
ROOTED = {"seat_evidence": None, "identity_clock_evidence": None, "card_evidence": None,
          "combat_evidence": None, "main": ("review_worker_loop", "review_worker_pass",
                                          "review_rules_refresh_loop", "_review_pass_line")}
REVIEW_NAMES = {"rm", "rr", "_review_rules", "review_measures", "review_rules"}
REVIEW_PARAMS = {"rs", "state", "ruleset"}
# Plumbing a rooted function may import without it being followed: the
# session factory and the table declarations decide nothing.
INFRA = {"database", "models"}

INDEX_MAX = 15
# Structural numbers BY CONTEXT (see the module docstring). No value is
# allowed everywhere; each context names what it admits.
STRUCTURAL = {
    "compare_any": {0},
    "compare_eq": {0, 1, -1},
    "binop": {(ast.Add, 1), (ast.Sub, 1), (ast.Add, -1), (ast.Sub, -1),
              (ast.FloorDiv, 2), (ast.Mod, 2),
              (ast.Mult, 1000), (ast.Div, 1000), (ast.FloorDiv, 1000)},
    "wrap": {2 ** 31, 2 ** 32},
    "augassign": {1, -1},
    "call": {0, 1, -1, 2},
    "plain": {0, 1, -1},
}
_EQ_OPS = (ast.Eq, ast.NotEq, ast.Is, ast.IsNot)
_SEL_OPS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)
# The closed public selectors: every string a reached function compares a
# value against. Contract words only (record fields, rule scopes and effects,
# loader words, health words, file names of the public format). A string
# outside this set in a comparison is refused.
SELECTORS = frozenset({
    "1", "REVISION", "__main__", "__pycache__", "abs", "absent", "add", "all", "any", "b",
    "build", "core.game", "data", "dirty", "edges", "eq", "expr", "filters", "flag", "game",
    "ge", "gt", "honoured", "int", "json", "label", "le", "list", "literal", "lt", "m",
    "missing", "ne", "not", "note", "nt", "num", "open", "params", "pointer", "posix",
    "post_rows", "read", "refused", "identity", "rel", "reporter", "row", "rules-none", "seat", "side",
    "sitting", "card", "core.card",
    "sub", "unhonoured", "v", "validate", "window_days", "{", "}",
    # reached through followed bindings since fix pass 3 (the resolver now
    # sees a tuple's members): the public format's file names, the record's
    # list fields, the three operational switch names
    "rules.json", "selftest.json", "blk_sent", "hit_recv", "blk_recv", "hit_sent", "age_b",
    "seat_evidence_accept", "seat_evidence_worker", "seat_evidence_purge",
    # the two closure module names the source-only loader and the loader's
    # own identity check compare against (fix pass 4)
    "review_measures", "review_rules",
    # the case table's public class names (the admin view's counts), reached
    # since fix pass 4 judges every binding of a name at its use
    "a", "c", "disagree", "expired", "hit_unmatched", "incomplete", "no_reset", "other_window",
    "unkeyed_reset",
    # the identity-clock lane (re-land 2026-10-29): its three operational
    # switch names (ice_setting reads only ICE_SWITCHES), the identity
    # scope's two rule subjects (the loader checks ICM_SUBJECTS) and the
    # measures module's name (review_boot.SOURCE_ONLY, the source-only
    # loader's identity check)
    "identity_clock_evidence_accept", "identity_clock_evidence_worker",
    "identity_clock_evidence_purge", "ic.seat", "ic.point", "identity_clock_measures",
    # the card-draw lane (re-land 2026-10-29): the measures module's name
    # (review_boot.SOURCE_ONLY, the source-only loader's identity check)
    "card_measures",
    # the combat lane (re-land 2026-10-29): its three switch names, the
    # measures module's name (review_boot.SOURCE_ONLY), the rule scope word,
    # the wire's spec kinds and the field names its layout code compares,
    # the side letter, and the pairing case and not-run words of its views
    "combat_evidence_accept", "combat_evidence_worker", "combat_evidence_purge",
    "combat_measures", "combat",
    "rows", "enum", "hist", "groups", "omit",
    "caps", "mask", "p3top", "pt", "pid", "stamp", "d_gaps", "frc_transit", "gap_prev",
    "gap_prev_s", "len_g", "len_cg", "a1sum", "p3an0", "p3an1", "p3dp0", "p3dp1", "cx_s",
    "cx_o", "measuring_seat", "s",
    "both_agree", "both_differ", "only_owner", "only_measuring", "inconsistent", "uncounted",
    "trimmed", "missing_record", "not_collected", "not_run"})

# Card contract words are accepted only with provenance from the public
# binding that defines them; the same spelling from any other source is not.
SELECTOR_PROVENANCE = frozenset({
    ("card_evidence", "SWITCHES"),
    ("card_measures", "CARD_SUBJECTS"),
    ("card_measures", "WINDOW"),
    ("card_measures", "WINDOW_SUBJECT"),
    ("combat_evidence", "SWITCHES"),
    ("review_measures", "COMBAT_SUBJECTS"),
})

# Contract bounds and scheduling: pinned BY VALUE. A deciding value added to
# one of these makes the pin differ, and the guard refuses it.
PINNED = {
    ("review_measures", "CONTRACT_BOUNDS"): {"ready_lag_s": 120, "edges_max": 8, "label_max": 16,
                                             "show_max": 16, "eval_hex": 8},
    ("review_measures", "WINDOW_KINDS"): (0, 2, 3),
    # the closed last-reset enum of a sent hit and its entry length (contract B7, amended 2026-10-04)
    ("review_measures", "RESET_NONE"): 0,
    ("review_measures", "RESET_KEYED"): 1,
    ("review_measures", "RESET_UNKEYED"): 2,
    ("review_measures", "HIT_SENT_LEN"): 10,
    ("review_rules", "CONTRACT_BOUNDS"): {
        "files_max": 64, "total_bytes_max": 16777216, "rules_bytes_max": 1048576,
        "selftest_bytes_max": 4194304, "data_bytes_max": 8388608, "rules_max": 200,
        "pred_depth_max": 6, "cases_max": 256, "work_max": 200000, "deadline_s": 10,
        "line_max": 400, "places_default": 3, "round_places": 4, "render_items_max": 6,
        "id_hex": 8, "rev_hex": 12, "nonce_bytes": 16, "digest_hex": 64, "data_name_max": 40,
        "pointer_bytes_max": 64, "frame_bytes": 8, "format": 1},
    ("review_rules", "_NT"): {"read": 0x80000000, "share": 0x7, "existing": 3,
                              "no_follow": 0x00200000, "buffer": 32768},
    ("seat_evidence", "SEATS"): 2,
    ("review_measures", "SEATS"): 2,
    ("review_rules", "PAIR"): 2,
    ("review_rules", "EXIT_USAGE"): 2,
    ("seat_evidence", "GAME_EXPIRY_DAYS"): 14,
    ("seat_evidence", "GAMES_PER_PASS"): 500,
    ("seat_evidence", "SITTINGS_PER_PASS"): 500,
    ("seat_evidence", "MARK_ROWS_PER_PASS"): 5000,
    ("seat_evidence", "DETAILS_MAX_BYTES"): 2048,
    ("seat_evidence", "COMPAT_ROWS_SHOWN"): 10,
    ("main", "REVIEW_PASS_S"): 600,
    ("main", "REVIEW_FIRST_PASS_S"): 90,
    ("main", "REVIEW_PURGE_EVERY_S"): 72000,
    ("main", "REVIEW_REFRESH_S"): 60,
    ("identity_clock_evidence", "ICE_GAME_EXPIRY_DAYS"): 14,
    ("identity_clock_evidence", "ICE_LIST_RETENTION_DAYS"): 120,
    ("identity_clock_evidence", "ICE_GAMES_PER_PASS"): 500,
    ("identity_clock_evidence", "ICE_FIT_ROWS_MAX"): 500,
    ("identity_clock_evidence", "ICE_SEATS"): 2,
    ("identity_clock_measures", "ICM_UNITS"): {"ppm": 1000000, "cppm": 100, "s_ms": 1000},
    ("identity_clock_measures", "ICM_CODES"): {
        "pass": 0, "finding": 1, "not_run": 2, "ok": 0, "no_file": 1, "read_failed": 2,
        "not_yet": 3, "origin_game": 0, "origin_core": 1, "origin_plugins": 2,
        "origin_patchers": 3, "origin_other": 4, "origin_none": 5, "origin_unreadable": 6,
        "boot": 0, "start": 1, "pick": 2, "over": 3, "unknown": -1},
    ("identity_clock_measures", "ICM_GAME"): {"move_step_ms": 20, "hold_frames": 10},
    ("card_evidence", "CARD_LIMITS"): {"games_per_pass": 500, "expiry_days": 14,
                                       "list_retention_days": 120, "derived_retention_days": 400,
                                       "unregistered_days": 30, "admin_rows": 50},
    ("card_evidence", "CARD_FAULT_LIMITS"): {"attempts": 5, "word_chars": 40},
    ("card_evidence", "CARD_RETRY_LIMITS"): {"op_base_s": 30, "op_cap_s": 900, "reprobe_s": 3600},
    ("combat_evidence", "GAME_EXPIRY_DAYS"): 14,
    ("combat_evidence", "GAMES_PER_PASS"): 500,
    # the combat measures' structural constants (re-land 2026-10-29): the two
    # seats, the per-mille unit, the byte proof's separators per protected
    # group, the homing clamp bound and the wire's bounce wait in single
    # precision (a unit test holds it equal to f32 of the wire's value)
    ("combat_measures", "SEATS"): 2,
    ("combat_measures", "PER_MILLE"): 1000,
    ("combat_measures", "GROUP_SEPARATORS"): 2,
    ("combat_measures", "HOMING_CLAMP"): 1,
    ("combat_measures", "BOUNCE_WAIT_S"): 0.10000000149011612,
    ("card_measures", "WINDOW_DAYS_MAX"): 400,
}
# A wire layout too large to restate here: pinned by the sha256 of
# repr(ast.literal_eval(value)); any changed bound, code or word changes it.
PINNED_SHA = {
    ("card_measures", "CARD_WIRE"):
        "d6ded319fd6a81a1a5d6819412f7c2d6743256d0f78a98e0aaea82970818ba68",
    # The combat wire layout (field bounds, list caps, tier order, enum codes)
    # and its amendment, pinned the same way.
    ("combat_measures", "COMBAT_WIRE"):
        "cf51bb58df95b57e062ad4dcbfc90c6d34b57469d58012e85108c308561b295f",
    ("combat_measures", "COMBAT_WIRE_A1"):
        "d303b52f7c482bce35db16627a29380a364bb8acfe0230c358b594ffc007c412",
}
SWITCHES = {"seat_evidence_accept", "seat_evidence_worker", "seat_evidence_purge",
            "identity_clock_evidence_accept", "identity_clock_evidence_worker",
            "identity_clock_evidence_purge",
            "card_evidence_accept", "card_evidence_worker", "card_evidence_purge",
            "combat_evidence_accept", "combat_evidence_worker", "combat_evidence_purge"}
SETTINGS_READERS = {("seat_evidence", "setting"), ("identity_clock_evidence", "ice_setting"),
                    ("card_evidence", "setting"), ("combat_evidence", "setting")}
ENV_KEYS = {"SCR_REVIEW_ROOT", "SYSTEMROOT"}

# Identifiers that carry a digit and decide nothing: match-row columns of the
# two seats, their SQL aliases, digest and encoding names, the Windows
# system library the non-following open calls, the combat wire's own key
# names (a closed list) and its public vocabulary names (the dotted b-family
# names).
_SAFE_TEXT = re.compile(
    r"\bp[12]_\w+|\bplayer[12](?:_id)?\b|\b[ps][12]\b|sha256\b|\butf-8\b|\bint(?:32|64)\b"
    r"|\bkernel32\b"
    r"|\bb4(?:\.[a-z_]*)*|\bheld0\b"
    r"|\bnoqa: ?[A-Z]+\d+(?:, ?[A-Z]+\d+)*"
    r"|\bt0(?:_src)?\b|\bframe_p50_us\b|\ba1(?:s|p|m|n|sum)\b"
    r"|\bp3(?:n|dp0|an0|dp1|an1|hm|self|top|tb|ht)\b|\bb5_(?:tot|s|o|h|c|r)\b|\b(?:s0|pid0|b[135])\b"
    r"|\bb[1235](?:\.[a-z_]+)+")
_STANDALONE = re.compile(r"(?<![\w.])[01](?![\w.])")
_DIGIT = re.compile(r"\d")

_DYNAMIC_CALLS = {"eval", "exec", "compile", "chr", "ord", "getattr", "globals", "vars",
                  "__import__", "setattr", "locals"}
_DYNAMIC_MODULES = {"base64", "codecs", "importlib", "binascii", "pickle", "marshal", "zlib"}
# The one place dynamic forms are the mechanism rather than a disguise: the
# source-only loading path compiles and executes a closure module's source
# bytes (exec, compile, vars), names its import spec (importlib), and reads a
# module table entry's file name, which any object may lack (getattr). Each
# exemption names ONE function and the forms it may use; the same form
# anywhere else is still refused (test_review_guard).
DYNAMIC_ALLOWED = {
    ("review_boot", "SourceOnly.exec_module"): frozenset({"exec", "compile", "vars"}),
    ("review_boot", "SourceOnly.find_spec"): frozenset({"importlib"}),
    ("review_boot", "executed_elsewhere"): frozenset({"getattr"}),
}
# A value with no runtime input that the guard cannot evaluate (a closed input
# into code it does not follow, a comprehension over constants): refused
# wherever it reaches a decision, never passed as unknown.
_UNRESOLVED = object()
_SELECTOR_REFUSAL = object()
_CHOICE_MAX = 64        # members a choice may grow to through arithmetic; beyond it, unresolved


class _Bound:
    """A resolved closed value and the public binding that supplied it."""
    __slots__ = ("value", "origin")

    def __init__(self, value, origin):
        self.value, self.origin = value, origin

    def __eq__(self, other):
        return isinstance(other, _Bound) and self.value == other.value and self.origin == other.origin


class _Choice:
    """One of several values, which one chosen at run time: by the control
    flow of one function (a return or a branch), or -- AMBIGUOUS -- by which
    of several bindings of one name reaches the use. `vals` are its closed
    members; `runtime` says a binding, return or branch reads runtime input
    too; `owners` are the binding sites (`module:line`) when it is ambiguous,
    carried through every value computed from it. EVERY closed member is
    judged at each use, so a binding is never dropped because another one
    exists, and an ambiguous value at a decision is the exit-3 refusal."""
    __slots__ = ("vals", "runtime", "owners")

    def __init__(self, vals, runtime, owners=()):
        flat, owners = [], set(owners)
        for v in vals:
            if isinstance(v, _Choice):
                flat.extend(v.vals)
                runtime = runtime or v.runtime
                owners |= set(v.owners)
            else:
                flat.append(v)
        self.vals, self.runtime, self.owners = tuple(flat), runtime, tuple(sorted(owners))


_DECODERS = {"int", "float", "Decimal", "complex", "len", "loads", "literal_eval", "fromhex"}


def text_bad(s: str) -> bool:
    s = _SAFE_TEXT.sub(" ", s)
    s = _STANDALONE.sub(" ", s)
    return bool(_DIGIT.search(s))


def _fold(node):
    """The value of a constant numeric expression, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _fold(node.operand)
        return None if v is None else (-v if isinstance(node.op, ast.USub) else v)
    if isinstance(node, ast.BinOp):
        a, b = _fold(node.left), _fold(node.right)
        if a is None or b is None:
            return None
        try:
            return {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b,
                    ast.Pow: lambda: a ** b, ast.FloorDiv: lambda: a // b,
                    ast.Div: lambda: a / b, ast.Mod: lambda: a % b}[type(node.op)]()
        except (KeyError, ArithmeticError):
            return None
    return None


class _Scan:
    def __init__(self, modname, label, src, peers=None):
        self.mod = modname
        self.peers = peers
        self.foreign = None             # (attr, class names or None) -> bindings in peer modules
        self.foreign_methods = None     # method name -> defs in peer modules
        self._attr_loads = None         # attribute name -> every Load of it in this module (lazy)
        self._module_binds = None       # name -> the module scope's binding statements (lazy)
        self.label = label
        self.src = src
        self.tree = ast.parse(src)
        self.findings = []
        self.defs = {}
        self.assigns = {}
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.defs[node.name] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        self.assigns[t.id] = node
        self.str_consts = {}
        for name, node in self.assigns.items():
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                self.str_consts[name] = node.value.value
        self._bind_module()

    # -- bindings followed to their uses --
    _NONE = object()           # depends on runtime input: not a constant
    _BUSY = object()           # being evaluated (a cycle reads as runtime)

    @staticmethod
    def _stores(nodes):
        """name -> number of times the statements bind it (assignment,
        augmented assignment, loop or with target, import, def, parameter)."""
        out = {}

        def hit(n):
            out[n] = out.get(n, 0) + 1
        for top in nodes:
            for n in ast.walk(top):
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                    hit(n.id)
                elif isinstance(n, ast.arg):
                    hit(n.arg)
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    hit(n.name)
                elif isinstance(n, (ast.Import, ast.ImportFrom)):
                    for a in n.names:
                        hit((a.asname or a.name).split(".")[0])
        return out

    _SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

    def _scope_info(self, body):
        """(own nodes, name -> bindings in this scope, global names) of the
        statements `body`: every node not inside a nested def, lambda, class
        or comprehension scope; each binding counted once."""
        own, counts, glob = [], {}, set()

        def hit(n):
            counts[n] = counts.get(n, 0) + 1
        todo = []

        def push(c):
            # a statement of `body` itself and a child of a node are classified
            # alike: a def, class or lambda binds its name here and only its
            # decorators, defaults and bases are in this scope (a def that is a
            # statement of `body` never contributes its own body's bindings)
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                hit(c.name)
                todo.extend(c.decorator_list)
                if not isinstance(c, ast.ClassDef):
                    todo.extend(x for x in c.args.defaults + c.args.kw_defaults if x is not None)
                else:
                    todo.extend(c.bases)
                    todo.extend(part.value for part in c.keywords)
            elif isinstance(c, ast.Lambda):
                todo.extend(x for x in c.args.defaults + c.args.kw_defaults if x is not None)
            elif isinstance(c, ast.comprehension):
                # its targets bind in the comprehension's own scope
                todo.append(c.iter)
                todo.extend(c.ifs)
                own.append(c)
                todo.extend(x for x in ast.walk(c.target)
                            if isinstance(x, ast.NamedExpr))
            else:
                todo.append(c)
        for c in body:
            push(c)
        while todo:
            n = todo.pop()
            own.append(n)
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                hit(n.id)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    hit((a.asname or a.name).split(".")[0])
            elif isinstance(n, ast.Global):
                glob.update(n.names)
            for c in ast.iter_child_nodes(n):
                push(c)
        for g in glob:
            counts.pop(g, None)
        return own, counts, glob

    def _bind_module(self):
        """Index every binding the resolver may follow; values are computed
        lazily, at their first use, so chains resolve in any order."""
        self._parents_all = {}
        self.fn_defs = {}
        self._names = {}             # identifier -> every Load of it
        fns, attr_stores, globals_in = [], [], []
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                self._parents_all[id(child)] = node
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.fn_defs.setdefault(node.name, []).append(node)
                fns.append(node)
            elif isinstance(node, ast.Lambda):
                fns.append(node)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self._names.setdefault(node.id, []).append(node)
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
                attr_stores.append(node)
            elif isinstance(node, ast.Global):
                globals_in.append(node)
        self._outer = {}            # a function -> the function directly enclosing it
        for fn in fns:
            p = self._parents_all.get(id(fn))
            while p is not None and not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                p = self._parents_all.get(id(p))
            if p is not None:
                self._outer[id(fn)] = p
        self._own_cache = {}
        self._locals_cache = {}
        # every binding of a module name: at module level in any block, and
        # through a `global` declaration inside any function
        _own, counts, _g = self._scope_info(self.tree.body)
        self.top_stores = dict(counts)
        for gnode in globals_in:
            fn = self._fn_around(gnode)
            if fn is None:
                continue
            for n in self._own(fn):
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)) and n.id in gnode.names:
                    self.top_stores[n.id] = self.top_stores.get(n.id, 0) + 1
        self._mv = {}
        self.mod_alias, self.from_imports = {}, {}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.mod_alias[a.asname or a.name.split(".")[0]] = a.name
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for a in node.names:
                    self.from_imports[a.asname or a.name] = (node.module, a.name)
        self.class_names = {n.name for n in self.tree.body if isinstance(n, ast.ClassDef)}
        # Attributes are resolved by OWNER (fix pass 4): every binding of an
        # attribute is indexed under the class it binds on -- a class-body
        # binding, `self.X`/`cls.X` in that class's methods, `Klass.X` -- or
        # under None when the receiver's class cannot be named (`obj.X = ...`).
        # A read collects the bindings its use site can see (_attr_value).
        self.classes = {}           # class name -> every ClassDef of that name
        self._method_of = {}        # id(function) -> the ClassDef whose body defines it
        self.methods = {}           # method name -> [(id(ClassDef), def)]
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                self.classes.setdefault(node.name, []).append(node)
                for s in node.body:
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._method_of[id(s)] = node
                        self.methods.setdefault(s.name, []).append((id(node), s))
        self.attr_sites = {}        # attribute -> [(owner id or None, kind, expr, fns, line)]
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                for s in node.body:
                    if isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                        targets = s.targets if isinstance(s, ast.Assign) else [s.target]
                        for t in targets:
                            if isinstance(t, ast.Name):
                                self._site(t.id, id(node), s, [], line=s.lineno)
        for n in attr_stores:
            fn = self._fn_around(n)
            fns = [fn] + self._chain(fn) if fn is not None else []
            owner = None
            if isinstance(n.value, ast.Name) and n.value.id in ("self", "cls"):
                cls_node = self._class_around(fns)
                owner = id(cls_node) if cls_node is not None else None
            elif isinstance(n.value, ast.Name) and len(self.classes.get(n.value.id, ())) == 1:
                owner = id(self.classes[n.value.id][0])
            self._site(n.attr, owner, self._parents_all.get(id(n)), fns, target=n, line=n.lineno)
        self.site_spans = None      # a rooted module: only the reached code's bindings count
        self._av = {}
        self._rv = {}
        self._lv = {}
        self._params_runtime = False
        self._selector_mode = False
        self._selector_refused = False

    def _fn_around(self, node):
        p = self._parents_all.get(id(node))
        while p is not None and not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            p = self._parents_all.get(id(p))
        return p

    def _site(self, attr, owner, stmt, fns, target=None, line=0):
        """Index one binding of an attribute: `assign` (its value expression),
        `aug` (an augmented update, or an assignment whose value reads the
        same attribute: a step) or `runtime` (a loop, with, delete or
        unpacking target: what it binds is not one expression)."""
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and stmt.value is not None \
                and (target is None or any(t is target for t in
                                           (stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]))):
            kind, expr = "assign", stmt.value
            if any(isinstance(x, ast.Attribute) and x.attr == attr for x in ast.walk(stmt.value)):
                kind = "aug"
        elif isinstance(stmt, ast.AugAssign) and (target is None or stmt.target is target):
            kind, expr = "aug", stmt.value
        else:
            kind, expr = "runtime", None
        self.attr_sites.setdefault(attr, []).append((owner, kind, expr, fns, line))

    def in_spans(self, line):
        """Whether a binding at `line` is one the scan reads (every line of a
        whole module; only the reached code of a rooted module)."""
        return self.site_spans is None or any(a <= line <= b for a, b in self.site_spans)

    def _class_around(self, fns):
        """The class whose method encloses the innermost of fns (a `self` in a
        nested function is its method's), or None."""
        for fn in fns:
            if id(fn) in self._method_of:
                return self._method_of[id(fn)]
        return None

    def related(self, cls_nodes):
        """ids of the classes a read on these classes can see: each class, its
        bases and its subclasses defined in this module, transitively; None
        when one of them derives from a class this module does not define (a
        base in another module may bind the attribute: the receiver's
        bindings cannot be named, so the read sees every binding)."""
        out, todo = set(), list(cls_nodes)
        while todo:
            c = todo.pop()
            if id(c) in out:
                continue
            out.add(id(c))
            for b in c.bases:
                if isinstance(b, ast.Name) and b.id in self.classes:
                    todo.extend(self.classes[b.id])
                elif not (isinstance(b, ast.Name) and hasattr(builtins, b.id)):
                    return None
            for others in self.classes.values():
                for o in others:
                    if any(isinstance(b, ast.Name) and b.id == c.name for b in o.bases):
                        todo.append(o)
        return out

    def decide(self, vals, n_aug, n_runtime, owners):
        """One value from every binding a use can see. Only bindings by
        assignment carry a candidate value; with none of them, or when every
        one reads runtime input, the value is runtime (_NONE). One constant
        start moved only by augmented updates is a counter (its start and each
        step are judged where they stand): runtime. One assignment and nothing
        else stands for its value. More than one binding where any assignment
        is closed does NOT resolve to one binding: it is AMBIGUOUS, a _Choice
        carrying `owners` (every binding site), refused at a decision and
        judged member by member, booleans included, anywhere else; a binding
        whose value the guard cannot evaluate makes it _UNRESOLVED."""
        N, U = self._NONE, _UNRESOLVED
        if not vals or all(v is N for v in vals):
            return N
        if len(vals) == 1 and n_runtime == 0:
            return N if n_aug and vals[0] is not U else vals[0]
        if any(v is U for v in vals):
            return U
        closed = [v for v in vals if v is not N]
        return _Choice(closed, bool(n_runtime or n_aug or len(closed) < len(vals)),
                       owners=tuple(owners) or ("%s:?" % self.mod,))

    def _chain(self, fn):
        """The functions enclosing fn, innermost first (fn excluded)."""
        out, p = [], self._outer.get(id(fn))
        while p is not None:
            out.append(p)
            p = self._outer.get(id(p))
        return out

    def _own(self, fn):
        """The nodes of a function's own scope (not of a nested def, lambda,
        class or comprehension scope)."""
        if id(fn) not in self._own_cache:
            body = [fn.body] if isinstance(fn, ast.Lambda) else fn.body
            self._own_cache[id(fn)] = self._scope_info(body)
        return self._own_cache[id(fn)][0]

    def _locals(self, fn):
        """(value expressions of the locals bound exactly once by an assignment,
        boolean parameter defaults never rebound, every bound name) of one
        function. A number default is a starting value every caller may move,
        not a decision; a boolean default is a switch."""
        if id(fn) in self._locals_cache:
            return self._locals_cache[id(fn)]
        self._own(fn)
        own, counts, _glob = self._own_cache[id(fn)]
        a = fn.args
        params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs] + \
            [x.arg for x in (a.vararg, a.kwarg) if x is not None]
        stores = dict(counts)
        for p in params:
            stores[p] = stores.get(p, 0) + 1
        exprs = {}
        if not isinstance(fn, ast.Lambda):
            for n in own:
                if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None:
                    targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                    for t in targets:
                        if isinstance(t, ast.Name) and stores.get(t.id, 0) == 1:
                            exprs[t.id] = n.value
        defaults = {}
        pos = a.posonlyargs + a.args
        for arg, d in list(zip(pos[len(pos) - len(a.defaults):], a.defaults)) + \
                list(zip(a.kwonlyargs, a.kw_defaults)):
            if isinstance(d, ast.Constant) and isinstance(d.value, bool) and stores.get(arg.arg, 0) == 1:
                defaults[arg.arg] = d.value
        out = (exprs, defaults, set(stores), stores)
        self._locals_cache[id(fn)] = out
        return out

    def _memo(self, cache, key, compute):
        if key in cache:
            v = cache[key]
            return _UNRESOLVED if v is self._BUSY else v          # a cycle: no value, not runtime
        cache[key] = self._BUSY
        v = compute()
        cache[key] = v
        return v

    @staticmethod
    def _plain(v):
        return v.value if isinstance(v, _Bound) else v

    def _binding_value(self, v, binding):
        """Reset inherited provenance at an approved public binding."""
        if binding not in SELECTOR_PROVENANCE or v is self._NONE or v is _UNRESOLVED:
            return v
        if isinstance(v, _Choice):
            return _Choice([self._binding_value(m, binding) for m in v.vals],
                           v.runtime, v.owners)
        return _Bound(self._plain(v), binding)

    def module_value(self, name):
        """The constant a module-level name stands for, or _NONE (a PINNED
        name is judged by its pin, never at its uses)."""
        if (self.mod, name) in PINNED or (self.mod, name) in PINNED_SHA:
            return self._NONE
        if name in self.assigns and self.top_stores.get(name, 0) == 1:
            node = self.assigns[name]
            if node.value is None:
                return self._NONE
            return self._memo(self._mv, name, lambda: self._binding_value(
                self._container(name, self._ev(node.value, []), None), (self.mod, name)))
        if self.top_stores.get(name, 0) > 1:
            return self._memo(self._mv, name, lambda: self._binding_value(
                self._rebound(name, None), (self.mod, name)))
        if name in self.from_imports and name not in self.defs and name not in self.assigns:
            m, attr = self.from_imports[name]
            peer = self.peer(m.split(".")[0])
            if peer is None:
                return self._NONE
            return self._selector_peer_value(peer, attr) if self._selector_mode \
                else peer.module_value(attr)
        return self._NONE

    def _selector_peer_value(self, peer, name):
        """Read a peer binding in the same isolated selector evaluation."""
        if peer is self or peer._selector_mode:
            return peer.module_value(name)
        keep_mode, keep_refused = peer._selector_mode, peer._selector_refused
        keep_caches = peer._mv, peer._lv, peer._rv, peer._av
        peer._selector_mode, peer._selector_refused = True, False
        peer._mv, peer._lv, peer._rv, peer._av = {}, {}, {}, {}
        try:
            value = peer.module_value(name)
            self._selector_refused = self._selector_refused or peer._selector_refused
            return value
        finally:
            peer._mv, peer._lv, peer._rv, peer._av = keep_caches
            peer._selector_mode, peer._selector_refused = keep_mode, keep_refused

    def peer(self, m):
        if m == self.mod:
            return self
        return self.peers(m) if self.peers is not None else None

    def _name(self, name, fns):
        for fn in fns:
            exprs, defaults, bound = self._locals(fn)[:3]
            if name in defaults and not self._params_runtime:
                return defaults[name]
            if name in exprs:
                return self._memo(self._lv, (id(fn), name), lambda fn=fn: self._container(
                    name, self._ev(exprs[name], [fn] + self._chain(fn)), fn))
            if name in bound:
                if name in self._own_cache[id(fn)][2]:
                    return self.module_value(name)              # a `global` name
                return self._memo(self._lv, (id(fn), name), lambda fn=fn: self._rebound(name, fn))
        return self.module_value(name)

    def _rebound(self, name, fn):
        """A name bound more than once (in fn's scope, or at module level when
        fn is None, `global` stores included): decided over every binding."""
        if fn is None and self._module_binds is None:
            # the module scope's binding statements by name, indexed once
            self._module_binds = {}
            for n in self._scope_info(self.tree.body)[0]:
                if isinstance(n, (ast.Assign, ast.AnnAssign)):
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                        if isinstance(t, ast.Name):
                            self._module_binds.setdefault(t.id, []).append(n)
                elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                    self._module_binds.setdefault(n.target.id, []).append(n)
        scopes = [(fn, self._own(fn))] if fn is not None else \
            [(None, self._module_binds.get(name, []))] + \
            [(f, self._own(f)) for f in self._global_fns(name)]
        vals, n_aug, n_assign, sites = [], 0, 0, []
        for f, own in scopes:
            fns = [f] + self._chain(f) if f is not None else []
            for n in own:
                if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None:
                    targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                    if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                        sites.append("%s:%d" % (self.mod, n.lineno))
                        if any(isinstance(x, ast.Name) and x.id == name for x in ast.walk(n.value)):
                            n_aug += 1                  # `n = n + 1`: a step, judged where it stands
                            continue
                        vals.append(self._container(name, self._ev(n.value, fns), fn))
                        n_assign += 1
                elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
                    sites.append("%s:%d" % (self.mod, n.lineno))
                    n_aug += 1
        if fn is not None:
            total = self._locals(fn)[3].get(name, 0)
        else:
            total = self.top_stores.get(name, 0)
        return self.decide(vals, n_aug, max(0, total - n_assign - n_aug), sites)

    def _global_fns(self, name):
        out = []
        for fns in self.fn_defs.values():
            for f in fns:
                self._own(f)
                if name in self._own_cache[id(f)][2]:
                    out.append(f)
        return out

    def _attr_value(self, attr, owners):
        """The value of a read of attribute `attr` on an instance or class of
        the classes `owners` (ids; None: the receiver's class cannot be
        named), over every binding that read can see: those of its owners,
        every binding on a receiver whose class cannot be named, in this
        module and in every peer module (a peer subclass's bindings too); for
        an unnamed receiver, every binding of the name anywhere. decide()
        turns them into one value or a choice of closed values."""
        key = (attr, None if owners is None else frozenset(owners))

        def compute():
            sites = [(self, s) for s in self.attr_sites.get(attr, ())
                     if (owners is None or s[0] is None or s[0] in owners) and self.in_spans(s[4])]
            names = None if owners is None else {c.name for cs in self.classes.values() for c in cs
                                                 if id(c) in owners}
            sites += self.foreign(attr, names) if self.foreign is not None else []
            vals, n_aug, n_runtime = [], 0, 0
            for scan, (_owner, kind, expr, fns, _line) in sites:
                if kind == "aug":
                    n_aug += 1
                elif kind == "runtime":
                    n_runtime += 1
                else:
                    # an attribute set from a parameter holds what the CALLER
                    # passed, whatever the parameter's default
                    scan._params_runtime, keep = True, scan._params_runtime
                    try:
                        v = scan._ev(expr, fns)
                    finally:
                        scan._params_runtime = keep
                    vals.append(scan._attr_container(attr, v))
            return self.decide(vals, n_aug, n_runtime,
                               ["%s:%d" % (scan.mod, s[4]) for scan, s in sites])
        return self._memo(self._av, key, compute)

    def foreign_sites(self, attr, class_names):
        """This module's bindings of `attr` another module's read can see: on
        an unnamed receiver always; with class_names None (that read's
        receiver is unnamed too) every binding; else those of a class here
        whose bases name one of class_names."""
        out = []
        for s in self.attr_sites.get(attr, ()):
            if not self.in_spans(s[4]):
                continue
            if s[0] is None or class_names is None:
                out.append((self, s))
                continue
            for cs in self.classes.values():
                for c in cs:
                    if id(c) == s[0] and any(
                            (isinstance(b, ast.Name) and b.id in class_names)
                            or (isinstance(b, ast.Attribute) and b.attr in class_names) for b in c.bases):
                        out.append((self, s))
        return out

    # Uses of a mutable container that only read it. Anything else is a write
    # (the container's value then depends on what was written) or an escape
    # (an alias or a callee may write it): a container that escapes, or is
    # written only with constants, is _UNRESOLVED; written with runtime input,
    # _NONE.
    _READ_METHODS = frozenset({"get", "keys", "values", "items", "index", "count", "copy"})
    _MUTATORS = frozenset({"append", "extend", "insert", "pop", "remove", "clear", "update",
                           "setdefault", "popitem", "add", "discard", "sort", "reverse",
                           "difference_update", "intersection_update", "symmetric_difference_update"})
    _COPIERS = frozenset({"len", "sorted", "tuple", "list", "min", "max", "sum", "any", "all",
                          "set", "frozenset", "enumerate", "zip", "iter", "reversed", "dict", "bool"})

    def _owner(self, node, name):
        """The function whose binding of `name` a Load at node reads (None:
        the module's)."""
        for fn in self._scope_fns(node):
            if name in self._locals(fn)[2] and name not in self._own_cache[id(fn)][2]:
                return fn
        return None

    def _container(self, name, v, owner):
        if not isinstance(v, (list, dict, set)):
            return v
        return self._container_uses([n for n in self._names.get(name, ()) if self._owner(n, name) is owner], v)

    def _attr_container(self, attr, v):
        """A container bound to an attribute, judged by every use of that
        attribute name in this module, on any receiver (the receiver's class is
        not narrowed here: any use may be this binding's): a write with runtime
        input makes it runtime; constant writes or an escape leave it
        _UNRESOLVED; with neither it is the bound value."""
        if not isinstance(v, (list, dict, set)):
            return v
        if self._attr_loads is None:
            self._attr_loads = {}
            for n in ast.walk(self.tree):
                if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
                    self._attr_loads.setdefault(n.attr, []).append(n)
        return self._container_uses(self._attr_loads.get(attr, []), v)

    def _container_uses(self, uses, v):
        """The value of a container `v` given every use of its binding: the
        state after its writes and escapes."""
        parents = self._all_parents()
        state = v
        for n in uses:
            p = parents.get(id(n))
            g = parents.get(id(p))
            if isinstance(p, ast.Subscript) and p.value is n:
                if isinstance(p.ctx, ast.Load):
                    continue
                if isinstance(p.ctx, ast.Del):
                    state = _UNRESOLVED if state is not self._NONE else state
                    continue
                w = g.value if isinstance(g, (ast.Assign, ast.AugAssign, ast.AnnAssign)) else None
                if w is None or self._runtime(self._ev(w, self._scope_fns(n))):
                    return self._NONE
                state = _UNRESOLVED
                continue
            if isinstance(p, ast.Attribute) and p.value is n and isinstance(g, ast.Call) and g.func is p:
                if p.attr in self._READ_METHODS:
                    continue
                if p.attr in self._MUTATORS:
                    fns = self._scope_fns(n)
                    if any(self._runtime(self._ev(a, fns)) for a in g.args):
                        return self._NONE
                    state = _UNRESOLVED
                    continue
                state = _UNRESOLVED
                continue
            if isinstance(p, ast.Compare) or (isinstance(p, ast.BinOp)
                                              and not isinstance(g, ast.AugAssign)):
                continue                        # a comparison, or an operator making a new value
            if isinstance(p, ast.Call) and n in p.args and isinstance(p.func, ast.Name) \
                    and p.func.id in self._COPIERS:
                continue
            if isinstance(p, (ast.For, ast.AsyncFor, ast.comprehension)) and p.iter is n:
                continue
            state = _UNRESOLVED                 # an escape: an alias or a callee may write it
        return state

    _SELECTOR_CONSUMER_COMPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

    def _selector_consumer_scope_facts(self, scope, name):
        """The direct bindings and declarations for one lexical scope."""
        cache = getattr(self, "_selector_consumer_scope_cache", None)
        if cache is None:
            cache = self._selector_consumer_scope_cache = {}
        key = id(scope) if scope is not None else None, name
        if key in cache:
            return cache[key]
        if isinstance(scope, self._SELECTOR_CONSUMER_COMPS):
            bindings = [part for gen in scope.generators for part in ast.walk(gen.target)
                        if isinstance(part, ast.Name) and part.id == name]
            out = bindings, False, False
            cache[key] = out
            return out
        if scope is None:
            body = self.tree.body
        elif isinstance(scope, ast.Lambda):
            body = [scope.body]
        else:
            body = scope.body
        own, _counts, globals_ = self._scope_info(body)
        nonlocals = {item for part in own if isinstance(part, ast.Nonlocal)
                     for item in part.names}
        bindings = []
        for part in own:
            if isinstance(part, ast.Name) and part.id == name \
                    and isinstance(part.ctx, (ast.Store, ast.Del)):
                bindings.append(part)
            elif isinstance(part, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and part.name == name:
                bindings.append(part)
            elif isinstance(part, (ast.Import, ast.ImportFrom)) and any(
                    (alias.asname or alias.name).split(".")[len(())] == name
                    for alias in part.names):
                bindings.append(part)
            elif isinstance(part, ast.ImportFrom) and any(
                    alias.name == "*" for alias in part.names):
                bindings.append(part)
            elif isinstance(part, ast.ExceptHandler) and part.name == name:
                bindings.append(part)
            elif isinstance(part, (ast.MatchAs, ast.MatchStar)) and part.name == name:
                bindings.append(part)
            elif isinstance(part, ast.MatchMapping) and part.rest == name:
                bindings.append(part)
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = scope.args
            bindings.extend(part for part in
                            args.posonlyargs + args.args + args.kwonlyargs
                            if part.arg == name)
            if args.vararg is not None and args.vararg.arg == name:
                bindings.append(args.vararg)
            if args.kwarg is not None and args.kwarg.arg == name:
                bindings.append(args.kwarg)
        for top in body:
            for part in ast.walk(top):
                if isinstance(part, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                        and part.name == name \
                        and self._selector_consumer_use_scopes(part)[len(())] is scope:
                    bindings.append(part)
        seen = set()
        bindings = [part for part in bindings
                    if id(part) not in seen and not seen.add(id(part))]
        out = bindings, name in globals_, name in nonlocals
        cache[key] = out
        return out

    def _selector_consumer_outer_fns(self, scope):
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return self._chain(scope)
        fn = self._fn_around(scope)
        return [] if fn is None else [fn] + self._chain(fn)

    def _selector_consumer_binding_owner(self, scope, name):
        """The scope whose binding a direct store in `scope` changes."""
        _bindings, global_, nonlocal_ = self._selector_consumer_scope_facts(scope, name)
        if scope is None or global_:
            return None
        if nonlocal_:
            for fn in self._selector_consumer_outer_fns(scope):
                bindings, outer_global, outer_nonlocal = \
                    self._selector_consumer_scope_facts(fn, name)
                if bindings and not outer_global and not outer_nonlocal:
                    return fn
            return None
        return scope

    def _selector_consumer_use_scopes(self, node):
        """Lexical scopes active where `node` executes, innermost first."""
        out, parent, skip_class = [], self._parents_all.get(id(node)), False
        while parent is not None:
            if isinstance(parent, self._SELECTOR_CONSUMER_COMPS):
                first, *_rest = parent.generators
                if not self._selector_within(node, first.iter):
                    out.append(parent)
                    skip_class = True
            elif isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(self._selector_within(node, part) for part in parent.body):
                    out.append(parent)
                    skip_class = True
            elif isinstance(parent, ast.Lambda):
                if self._selector_within(node, parent.body):
                    out.append(parent)
                    skip_class = True
            elif isinstance(parent, ast.ClassDef):
                if any(self._selector_within(node, part) for part in parent.body):
                    if not skip_class:
                        out.append(parent)
                    skip_class = True
            parent = self._parents_all.get(id(parent))
        out.append(None)
        return out

    def _selector_consumer_owner(self, node, name):
        """The lexical binding read by a Name at one selector use site."""
        for scope in self._selector_consumer_use_scopes(node):
            bindings, global_, nonlocal_ = self._selector_consumer_scope_facts(scope, name)
            if global_:
                return None
            if nonlocal_:
                return self._selector_consumer_binding_owner(scope, name)
            if bindings:
                if isinstance(scope, ast.ClassDef) \
                        and not self._selector_prior_shadow(node, name, scope.body):
                    continue
                return self._selector_consumer_binding_owner(scope, name)
        return None

    def _selector_consumer_binding_sites(self, owner, name):
        """Every binding site whose store can change `owner`'s binding."""
        scopes = [None] + [part for part in ast.walk(self.tree)
                           if isinstance(part, self._SCOPES + self._SELECTOR_CONSUMER_COMPS)]
        out = []
        for scope in scopes:
            bindings, _global, _nonlocal = self._selector_consumer_scope_facts(scope, name)
            if bindings and self._selector_consumer_binding_owner(scope, name) is owner:
                out.extend((scope, part) for part in bindings)
        return out

    def _selector_consumer_assignments(self, owner, name):
        """Direct simple assignments that may establish approved provenance."""
        if isinstance(owner, self._SELECTOR_CONSUMER_COMPS):
            return []
        if owner is None:
            body = self.tree.body
        elif isinstance(owner, ast.Lambda):
            body = [owner.body]
        else:
            body = owner.body
        own, _counts, _globals = self._scope_info(body)
        out = []
        for part in own:
            if not isinstance(part, (ast.Assign, ast.AnnAssign)) or part.value is None:
                continue
            targets = part.targets if isinstance(part, ast.Assign) else [part.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                out.append((part, self._scope_fns(part)))
        return sorted(out, key=lambda item: item[len(())].lineno)

    @staticmethod
    def _selector_consumer_import_origin(node, name):
        if isinstance(node, ast.Import):
            alias = next((part for part in reversed(node.names)
                          if (part.asname or part.name.split(".")[len(())]) == name), None)
            return None if alias is None else (alias.name.split(".")[len(())], None)
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            alias = next((part for part in reversed(node.names)
                          if part.name != "*" and (part.asname or part.name) == name), None)
            return None if alias is None else (node.module.split(".")[len(())], alias.name)
        return None

    def _selector_consumer_module_source(self, owner, name, attr):
        for scope, part in self._selector_consumer_binding_sites(owner, name):
            source = self._selector_consumer_import_origin(part, name)
            if source is not None and source[len((None,))] is None \
                    and (source[len(())], attr) in SELECTOR_PROVENANCE:
                baseline = part if scope is owner else None
                return source[len(())], baseline
        return None

    def _selector_consumer_module_aliases(self, module):
        out = []
        for part in ast.walk(self.tree):
            if not isinstance(part, ast.Import):
                continue
            scope = self._selector_consumer_use_scopes(part)[len(())]
            seen = set()
            for alias in reversed(part.names):
                name = alias.asname or alias.name.split(".")[len(())]
                if name in seen:
                    continue
                seen.add(name)
                if alias.name.split(".")[len(())] != module:
                    continue
                owner = self._selector_consumer_binding_owner(scope, name)
                baseline = part if scope is owner and (
                    not isinstance(owner, ast.ClassDef) or part in owner.body) else None
                out.append((name, owner, baseline))
        return out

    def _selector_consumer_write(self, target):
        """The selector value after one write in the reading module."""
        if isinstance(target, (ast.arg, ast.ExceptHandler, ast.MatchAs,
                               ast.MatchStar, ast.MatchMapping)):
            return self._NONE
        if isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                               ast.Import, ast.ImportFrom)):
            return _UNRESOLVED
        parents, child = self._all_parents(), target
        while child is not None:
            parent = parents.get(id(child))
            if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
                if parent.value is None:
                    return None
                value = self._ev(parent.value, self._scope_fns(target))
                return self._NONE if self._runtime(value) else _UNRESOLVED
            if isinstance(parent, ast.Delete):
                return _UNRESOLVED
            if isinstance(parent, (ast.For, ast.AsyncFor, ast.With, ast.AsyncWith,
                                   ast.comprehension)):
                return self._NONE
            if isinstance(parent, self._SCOPES):
                break
            child = parent
        return _UNRESOLVED

    def _selector_consumer_uses(self, uses, value, skip=None, container=True):
        """Check reads, writes and escapes of one approved container value."""
        skipped = skip if isinstance(skip, frozenset) else frozenset((skip,))
        active = [use for use in uses if use not in skipped]
        parents = self._all_parents()
        unsafe_copier = any(
            isinstance(parents.get(id(use)), ast.Call)
            and use in parents[id(use)].args
            and isinstance(parents[id(use)].func, ast.Name)
            and parents[id(use)].func.id in self._COPIERS
            and (not container or not self._selector_builtin(
                parents[id(use)].func, parents[id(use)].func.id,
                self._scope_fns(parents[id(use)].func))) for use in active)
        state = self._container_uses(active, value.value)
        if state is self._NONE:
            return self._NONE
        if unsafe_copier:
            return _UNRESOLVED
        return value if state is value.value else state

    def _selector_consumer_bound(self, origin):
        """The declared approved container at `origin`, before consumer writes."""
        if origin not in SELECTOR_PROVENANCE:
            return None
        scan = self.peer(origin[len(())])
        if scan is None:
            return None
        for part in scan.tree.body:
            if not isinstance(part, (ast.Assign, ast.AnnAssign)) or part.value is None:
                continue
            targets = part.targets if isinstance(part, ast.Assign) else [part.target]
            if not any(isinstance(target, ast.Name) and target.id == origin[len((None,))]
                       for target in targets):
                continue
            value = scan._binding_value(scan._ev(part.value, []), origin)
            if isinstance(value, _Bound) and isinstance(value.value, (tuple, list, dict, set)):
                return value
        return None

    def _selector_consumer_origin(self, node, fns, seen=frozenset()):
        """The approved container source named by one consumer binding."""
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            owner = self._selector_consumer_owner(node.value, node.value.id)
            source = self._selector_consumer_module_source(owner, node.value.id, node.attr)
            if source is not None:
                return source[len(())], node.attr
        parts = None
        if isinstance(node, (ast.Tuple, ast.List)) \
                and not any(isinstance(part, ast.Starred) for part in node.elts):
            parts = node.elts
        elif isinstance(node, ast.BoolOp):
            parts = node.values
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in self._PURE \
                and self._selector_builtin(node.func, node.func.id, fns) \
                and not any(isinstance(part, ast.Starred) for part in node.args) \
                and all(part.arg is not None for part in node.keywords):
            parts = list(node.args) + [part.value for part in node.keywords]
        if parts is not None:
            origins = [self._selector_consumer_origin(part, fns, seen) for part in parts]
            return origins[len(())] if origins and all(
                origin is not None and origin == origins[len(())] for origin in origins) else None
        if not isinstance(node, ast.Name):
            return None
        owner = self._selector_consumer_owner(node, node.id)
        key = self.mod, id(owner) if owner is not None else None, node.id
        if key in seen:
            return None
        if owner is None and self._selector_consumer_bound((self.mod, node.id)) is not None:
            return self.mod, node.id
        for _scope, part in self._selector_consumer_binding_sites(owner, node.id):
            origin = self._selector_consumer_import_origin(part, node.id)
            if origin in SELECTOR_PROVENANCE:
                return origin
        for part, scope_fns in self._selector_consumer_assignments(owner, node.id):
            value = self._ev(part.value, scope_fns)
            if isinstance(value, _Bound) \
                    and self._selector_consumer_bound(value.origin) is not None:
                return value.origin
            origin = self._selector_consumer_origin(part.value, scope_fns, seen | {key})
            if origin is not None:
                return origin
        return None

    def _selector_consumer_result(self, value, states):
        if any(state is self._NONE for state in states):
            return self._NONE
        if any(state is _UNRESOLVED for state in states):
            return _UNRESOLVED
        return value

    def _selector_consumer_sources(self, source, origin, fns, seen):
        """The provenance-bearing reads inside one consumer alias binding."""
        reads = []
        for part in ast.walk(source):
            if isinstance(part, (ast.Name, ast.Attribute)) \
                    and isinstance(part.ctx, ast.Load) \
                    and self._selector_consumer_origin(part, fns, seen) == origin:
                reads.append((part, self._ev(part, fns)))
        skip = frozenset(part for part, _value in reads)
        return [self._selector_consumer_value(part, value, fns, skip, seen)
                for part, value in reads]

    def _selector_consumer_module(self, base, attr, value, bound, skip=None,
                                  owner=None, baseline=None):
        """Check a container read through a module alias in this module."""
        matching = [part for part in ast.walk(self.tree)
                    if isinstance(part, ast.Attribute) and isinstance(part.value, ast.Name)
                    and part.value.id == base and part.attr == attr
                    and self._selector_consumer_owner(part.value, base) is owner]
        states = [self._selector_consumer_uses(
            [part for part in matching if isinstance(part.ctx, ast.Load)], bound, skip)]
        states.extend(self._selector_consumer_write(part) for part in matching
                      if isinstance(part.ctx, (ast.Store, ast.Del)))
        parents, outside = self._all_parents(), []
        for part in self._names.get(base, ()):
            if self._selector_consumer_owner(part, base) is not owner:
                continue
            parent = parents.get(id(part))
            if isinstance(parent, ast.Attribute) and parent.value is part:
                if parent.attr == "__dict__":
                    subscript = parents.get(id(parent))
                    if isinstance(subscript, ast.Subscript) and subscript.value is parent:
                        key = self._ev(subscript.slice, self._scope_fns(subscript))
                        if key == attr and isinstance(subscript.ctx, (ast.Store, ast.Del)):
                            states.append(self._selector_consumer_write(subscript))
                        elif key is self._NONE:
                            states.append(self._NONE)
                        elif key is _UNRESOLVED:
                            states.append(_UNRESOLVED)
                    else:
                        states.append(_UNRESOLVED)
                continue
            outside.append(part)
        states.append(self._selector_consumer_uses(outside, bound, container=False))
        for _scope, target in self._selector_consumer_binding_sites(owner, base):
            if target is baseline:
                continue
            states.append(self._selector_consumer_write(target))
        return self._selector_consumer_result(value, states)

    def _selector_consumer_name(self, node, value, fns, skip, seen):
        name, owner = node.id, self._selector_consumer_owner(node, node.id)
        key = self.mod, id(owner) if owner is not None else None, name
        if key in seen:
            return _UNRESOLVED
        origin, imported = None, False
        sites = self._selector_consumer_binding_sites(owner, name)
        baseline = None
        if owner is None and (self.mod, name) in SELECTOR_PROVENANCE:
            origin = self.mod, name
        else:
            for scope, part in sites:
                candidate = self._selector_consumer_import_origin(part, name)
                if candidate in SELECTOR_PROVENANCE:
                    origin, imported = candidate, True
                    baseline = part if scope is owner else None
                    break
        bindings = self._selector_consumer_assignments(owner, name)
        if origin == (self.mod, name):
            baseline = next((part for part, _scope_fns in bindings), None)
        source = source_fns = None
        if origin is None and (len(bindings) == len((None,))
                               or isinstance(owner, ast.ClassDef)):
            for part, scope_fns in bindings:
                evaluated = self._ev(part.value, scope_fns)
                candidate = evaluated.origin if isinstance(evaluated, _Bound) \
                    and self._selector_consumer_bound(evaluated.origin) is not None \
                    else self._selector_consumer_origin(part.value, scope_fns, seen | {key})
                if candidate is not None:
                    origin, baseline = candidate, part
                    source, source_fns = part.value, scope_fns
                    break
        if origin is None and isinstance(value, _Bound) \
                and self._selector_consumer_bound(value.origin) is not None:
            origin = value.origin
        bound = self._selector_consumer_bound(origin)
        if bound is None:
            return value
        seed = bound if source is not None or baseline is not None else value
        baseline_certain = baseline is not None and (
            not isinstance(owner, ast.ClassDef) or baseline in owner.body)
        baseline_nodes = {id(part) for part in ast.walk(baseline)} if baseline_certain else set()
        states = [self._selector_consumer_uses(
            [part for part in self._names.get(name, ())
             if self._selector_consumer_owner(part, name) is owner],
            bound, skip)]
        states.extend(self._selector_consumer_write(target)
                      for _scope, target in sites
                      if id(target) not in baseline_nodes)
        if source is not None:
            states.extend(self._selector_consumer_sources(
                source, origin, source_fns, seen | {key}))
        if imported:
            for base, alias_owner, alias_baseline in \
                    self._selector_consumer_module_aliases(origin[len(())]):
                states.append(self._selector_consumer_module(
                    base, origin[len((None,))], bound, bound,
                    owner=alias_owner, baseline=alias_baseline))
        return self._selector_consumer_result(seed, states)

    def _selector_consumer_value(self, node, value, fns, skip=None, seen=frozenset()):
        """Validate approved container provenance in the selector's reading scope."""
        if isinstance(node, ast.Name):
            return self._selector_consumer_name(node, value, fns, skip, seen)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            owner = self._selector_consumer_owner(node.value, node.value.id)
            source = self._selector_consumer_module_source(owner, node.value.id, node.attr)
            if source is None:
                return self._selector_consumer_name(node.value, value, fns, skip, seen)
            module, baseline = source
            bound = self._selector_consumer_bound((module, node.attr))
            if bound is not None:
                states = [self._selector_consumer_module(
                    base, node.attr, bound, bound, skip,
                    owner=alias_owner, baseline=alias_baseline)
                    for base, alias_owner, alias_baseline in
                    self._selector_consumer_module_aliases(module)]
                seed = bound if baseline is not None else value
                return self._selector_consumer_result(seed, states)
        return value

    def _selector_consumer(self, node, fns):
        return self._selector_consumer_value(node, self._ev(node, fns), fns)

    def _all_parents(self):
        return self._parents_all

    def _scope_fns(self, node):
        parents = self._all_parents()
        out, p = [], parents.get(id(node))
        while p is not None:
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                out.append(p)
            p = parents.get(id(p))
        return out

    def return_value(self, fn):
        """What fn returns: the one constant every return yields; a _Choice of
        the closed values when the returns differ or some read runtime input
        (each closed value judged at the use); _UNRESOLVED when one cannot be
        evaluated; _NONE when every return reads runtime input."""
        def compute():
            rets = [r for r in self._own(fn) if isinstance(r, ast.Return)]
            if not rets:
                return self._NONE
            vals = [self._ev(r.value, [fn] + self._chain(fn)) if r.value is not None else self._NONE
                    for r in rets]
            if all(v is self._NONE for v in vals):
                return self._NONE
            if any(v is _UNRESOLVED for v in vals):
                return _UNRESOLVED
            closed = [v for v in vals if v is not self._NONE]
            if len(closed) == len(vals) and not any(isinstance(v, _Choice) for v in vals) \
                    and all(v == vals[0] and type(v) is type(vals[0]) for v in vals):
                return vals[0]
            return _Choice(closed, len(closed) < len(vals))
        if self._rv.get(id(fn)) is self._BUSY:
            # a recursive call: it yields one of fn's own returns, and every
            # one of those is judged where fn's value is used; the call adds
            # no value of its own
            return self._NONE
        return self._memo(self._rv, id(fn), compute)

    def _callee(self, f, fns):
        """The function definition a call names, when the guard can see it."""
        if isinstance(f, ast.Name):
            for fn in fns:
                if f.id in self._locals(fn)[2]:
                    return None, None
            if f.id in self.defs and isinstance(self.defs[f.id], (ast.FunctionDef, ast.AsyncFunctionDef)):
                return self, self.defs[f.id]
            if f.id in self.from_imports:
                m, attr = self.from_imports[f.id]
                peer = self.peer(m.split(".")[0])
                if peer is not None and isinstance(peer.defs.get(attr), (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return peer, peer.defs[attr]
            return None, None
        if isinstance(f, ast.Attribute):
            owners = self._owners(f.value.id, fns) if isinstance(f.value, ast.Name) else None
            if owners is False:
                peer = self.peer(self.mod_alias[f.value.id].split(".")[0])
                if peer is not None and isinstance(peer.defs.get(f.attr), (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return peer, peer.defs[f.attr]
                return None, None
            defs = [(self, d) for o, d in self.methods.get(f.attr, ())
                    if (owners is None or o in owners) and self.in_spans(d.lineno)]
            if owners is None and self.foreign_methods is not None:
                defs += self.foreign_methods(f.attr)
            if len(defs) == 1:
                return defs[0]
            if defs:
                return self, defs                 # several candidates: decided in _ev_call
        return None, None

    def _ev(self, node, fns):
        """The value of an expression: a constant (number, string, boolean, or a
        tuple, list, set or dict of them), _NONE when it reads runtime input,
        _UNRESOLVED when it reads none but the guard cannot evaluate it."""
        N, U = self._NONE, _UNRESOLVED
        if node is None:
            return N
        if isinstance(node, ast.Constant):
            v = node.value
            return v if isinstance(v, (int, float, str, bool)) else N
        if isinstance(node, ast.Name):
            return self._name(node.id, fns)
        if isinstance(node, ast.Attribute):
            return self._ev_attr(node, fns)
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            vals = [self._ev(e, fns) for e in node.elts]
            if any(v is N for v in vals) or any(isinstance(e, ast.Starred) for e in node.elts):
                return N
            if any(v is U for v in vals):
                return U
            make = {ast.Tuple: tuple, ast.List: list, ast.Set: set}[type(node)]
            return self._lift(lambda *xs: make(xs), vals)
        if isinstance(node, ast.Dict):
            if any(k is None for k in node.keys):
                return N
            ks = [self._ev(k, fns) for k in node.keys]
            vs = [self._ev(v, fns) for v in node.values]
            if any(x is N for x in ks + vs):
                return N
            if any(x is U for x in ks + vs):
                return U
            n = len(ks)
            return self._lift(lambda *xs: dict(zip(xs[:n], xs[n:])), ks + vs)
        if isinstance(node, (ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.IfExp, ast.Compare, ast.Subscript)):
            return self._ev_op(node, fns)
        if isinstance(node, ast.Call):
            return self._ev_call(node, fns)
        if isinstance(node, ast.NamedExpr):
            return self._ev(node.value, fns)
        if isinstance(node, (ast.JoinedStr, ast.FormattedValue)):
            return self._ev_string(node, fns)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Lambda,
                             ast.Starred)):
            return self._closed(node, fns)
        return N

    def _ev_string(self, node, fns):
        """A formatted string, retaining an origin only when every part has it."""
        N, U = self._NONE, _UNRESOLVED
        if isinstance(node, ast.JoinedStr):
            vals = [self._ev(v, fns) for v in node.values]
            if any(v is N for v in vals):
                return N
            if any(v is U for v in vals):
                return U
            return self._lift(lambda *xs: "".join(xs), vals)
        value = self._ev(node.value, fns)
        if value is N or value is U:
            return value
        conversions = {ord("s"): str, ord("r"): repr, ord("a"): ascii}
        convert = conversions.get(node.conversion, lambda v: v)
        if node.format_spec is None:
            return self._lift(lambda v: format(convert(v)), [value])
        spec = self._ev(node.format_spec, fns)
        if spec is N or spec is U:
            return spec
        return self._lift(lambda v, s: format(convert(v), s), [value, spec])

    def _owners(self, base, fns):
        """The class ids a read `base.X` can see, None when the receiver's
        class cannot be named, or False for a module alias (handled apart)."""
        if base in ("self", "cls"):
            c = self._class_around(fns)
            return self.related([c]) if c is not None else None
        if base in self.classes and not any(base in self._locals(fn)[2] for fn in fns):
            return self.related(self.classes[base])
        if base in self.mod_alias and not any(base in self._locals(fn)[2] for fn in fns):
            return False
        return None

    def _ev_attr(self, node, fns):
        N = self._NONE
        if isinstance(node.value, ast.Name):
            owners = self._owners(node.value.id, fns)
            if owners is False:
                peer = self.peer(self.mod_alias[node.value.id].split(".")[0])
                if peer is None:
                    return N                              # a library's own value
                return self._selector_peer_value(peer, node.attr) if self._selector_mode \
                    else peer.module_value(node.attr)
            return self._attr_value(node.attr, owners)
        return self._attr_value(node.attr, None)

    _UNARY = {ast.USub: lambda a: -a, ast.UAdd: lambda a: +a, ast.Not: lambda a: not a,
              ast.Invert: lambda a: ~a}
    _BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
            ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
            ast.Pow: lambda a, b: a ** b, ast.BitAnd: lambda a, b: a & b, ast.BitOr: lambda a, b: a | b,
            ast.BitXor: lambda a, b: a ^ b, ast.LShift: lambda a, b: a << b, ast.RShift: lambda a, b: a >> b}
    _CMP = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b, ast.Lt: lambda a, b: a < b,
            ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
            ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
            ast.Is: lambda a, b: a is b, ast.IsNot: lambda a, b: a is not b}

    def _runtime(self, v) -> bool:
        """Whether a value reads runtime input: _NONE, or a choice one of
        whose bindings, returns or arms does."""
        v = self._plain(v)
        return v is self._NONE or (isinstance(v, _Choice) and v.runtime)

    def _lift(self, fn, vals, receiver_origin=False):
        """fn over closed values; with a _Choice among them, over every
        combination of members (a _Choice of the results, at most
        _CHOICE_MAX of them, else _UNRESOLVED). A failure is _UNRESOLVED."""
        def apply(xs):
            if receiver_origin:
                receiver, *_rest = xs
                origin = receiver.origin if isinstance(receiver, _Bound) else None
            else:
                bound = [v for v in xs if isinstance(v, _Bound)]
                origin = bound.pop().origin if bound and len(bound) == len(xs) else None
                if origin is not None and any(v.origin != origin for v in bound):
                    origin = None
            out = fn(*[self._plain(v) for v in xs])
            return _Bound(out, origin) if origin is not None else out

        if not any(isinstance(v, _Choice) for v in vals):
            try:
                return apply(vals)
            except Exception:                   # noqa: BLE001 -- any evaluation failure: no value
                return _UNRESOLVED
        members = [v.vals if isinstance(v, _Choice) else (v,) for v in vals]
        total = 1
        for m in members:
            total *= len(m)
        if total > _CHOICE_MAX:
            return _UNRESOLVED
        out = []
        for combo in itertools.product(*members):
            try:
                out.append(apply(combo))
            except Exception:                   # noqa: BLE001 -- any evaluation failure: no value
                return _UNRESOLVED
        return _Choice(out, any(isinstance(v, _Choice) and v.runtime for v in vals),
                       owners=[o for v in vals if isinstance(v, _Choice) for o in v.owners])

    def _combine(self, outs):
        """The value of an expression that is one of `outs`, which one chosen
        at run time (the two arms of a conditional expression)."""
        N, U = self._NONE, _UNRESOLVED
        if all(v is N for v in outs):
            return N
        if any(v is U for v in outs):
            return U
        closed = [v for v in outs if v is not N]
        if len(closed) == len(outs) and not any(isinstance(v, _Choice) for v in closed) \
                and all(v == closed[0] and type(v) is type(closed[0]) for v in closed):
            return closed[0]
        return _Choice(closed, len(closed) < len(outs))

    def _ev_op(self, node, fns):
        N, U = self._NONE, _UNRESOLVED
        if isinstance(node, ast.IfExp):
            t = self._ev(node.test, fns)
            if t is U:
                return U
            if t is N:                              # either arm, chosen at run time
                return self._combine([self._ev(node.body, fns), self._ev(node.orelse, fns), N])
            if isinstance(t, _Bound):
                t = t.value
            if isinstance(t, _Choice):
                arms = {bool(self._plain(m)) for m in t.vals}
                outs = [self._ev(node.body if a else node.orelse, fns) for a in sorted(arms)]
                if t.runtime:
                    outs += [self._ev(node.body, fns), self._ev(node.orelse, fns), N]
                return self._combine(outs)
            return self._ev(node.body if t else node.orelse, fns)
        if isinstance(node, ast.Subscript):
            if not isinstance(getattr(node, "ctx", ast.Load()), ast.Load):
                return N
            c = self._ev(node.value, fns)
            if isinstance(node.slice, ast.Slice):
                parts = [self._ev(p, fns) if p is not None else None
                         for p in (node.slice.lower, node.slice.upper, node.slice.step)]
            else:
                parts = [self._ev(node.slice, fns)]
            if c is N or any(p is N for p in parts):
                return N
            if c is U or any(p is U for p in parts):
                return U
            if isinstance(node.slice, ast.Slice):
                return self._lift(lambda cv, *ps: cv[slice(*ps)], [c] + parts)
            return self._lift(lambda cv, p: cv[p], [c, parts[0]])
        if isinstance(node, ast.UnaryOp):
            ops, vals, fn = [node.op], [self._ev(node.operand, fns)], self._UNARY.get(type(node.op))
        elif isinstance(node, ast.BinOp):
            ops, vals, fn = [node.op], [self._ev(node.left, fns), self._ev(node.right, fns)], \
                self._BIN.get(type(node.op))
        elif isinstance(node, ast.BoolOp):
            vals = [self._ev(v, fns) for v in node.values]
            if all(v is N for v in vals):
                return N
            if any(v is U for v in vals):
                return U
            if any(v is N for v in vals):           # the result is one of the operands
                return self._combine(vals)
            and_ = isinstance(node.op, ast.And)

            def fold(*xs):
                out = xs[0]
                for x in xs[1:]:
                    out = (out and x) if and_ else (out or x)
                return out
            return self._lift(fold, vals)
        else:
            vals = [self._ev(node.left, fns)] + [self._ev(c, fns) for c in node.comparators]
            ops, fn = node.ops, None
        if any(v is N for v in vals):
            return N
        if any(v is U for v in vals):
            return U
        if isinstance(node, ast.Compare):
            cmps = [self._CMP[type(o)] for o in ops]
            return self._lift(lambda *xs: all(c(a, b) for c, a, b in zip(cmps, xs, xs[1:])), vals)
        if fn is None:
            return U
        return self._lift(fn, vals)

    _PURE = {"min": min, "max": max, "abs": abs, "round": round, "sum": sum, "sorted": sorted,
             "tuple": tuple, "list": list, "frozenset": frozenset, "set": set, "bool": bool,
             "int": int, "float": float, "str": str, "len": len, "dict": dict, "format": format,
             "reversed": tuple}

    _SELECTOR_STRING_METHODS = frozenset({
        "capitalize", "casefold", "center", "expandtabs", "ljust", "lower", "lstrip",
        "removeprefix", "removesuffix", "replace", "rjust", "rstrip", "strip",
        "swapcase", "title", "translate", "upper", "zfill",
    })
    _SELECTOR_NONSTRING_METHODS = frozenset({
        "encode", "endswith", "find", "isalnum", "isalpha", "isascii", "isdecimal",
        "isdigit", "isidentifier", "islower", "isnumeric", "isprintable", "isspace",
        "istitle", "isupper", "partition", "rfind", "rindex", "rpartition", "rsplit",
        "split", "splitlines", "startswith",
    })

    @staticmethod
    def _selector_within(node, root):
        return root is node or any(part is node for part in ast.walk(root))

    @staticmethod
    def _selector_captures(nodes, name):
        for part in nodes:
            if isinstance(part, ast.ExceptHandler) and part.name == name:
                return True
            if isinstance(part, (ast.MatchAs, ast.MatchStar)) and part.name == name:
                return True
            if isinstance(part, ast.MatchMapping) and part.rest == name:
                return True
        return False

    def _selector_scope_binds(self, nodes, name):
        own, counts, _glob = self._scope_info(nodes)
        annotations = [part for part in own if isinstance(part, ast.AnnAssign)
                       and part.value is None and isinstance(part.target, ast.Name)
                       and part.target.id == name]
        captured = self._selector_captures(own, name)
        imported = any(isinstance(part, ast.ImportFrom)
                       and any(alias.name == "*" for alias in part.names) for part in own)
        return counts.get(name, len(())) > len(annotations) or captured or imported

    def _selector_prior_shadow(self, node, name, body):
        position = node.lineno, node.col_offset
        for statement in body:
            if not self._selector_within(node, statement):
                if self._selector_scope_binds([statement], name):
                    return True
                continue
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and any(self._selector_within(node, part) for part in statement.body):
                return False
            own, _counts, _glob = self._scope_info([statement])
            for part in own:
                if isinstance(part, ast.NamedExpr) and isinstance(part.target, ast.Name) \
                        and part.target.id == name:
                    end = (getattr(part, "end_lineno", part.lineno),
                           getattr(part, "end_col_offset", part.col_offset))
                    if end <= position:
                        return True
            current = node
            while current is not statement:
                parent = self._parents_all.get(id(current))
                if parent is None:
                    break
                for _field, parts in ast.iter_fields(parent):
                    if isinstance(parts, list) and current in parts:
                        prefix = parts[:parts.index(current)]
                        if self._selector_scope_binds(prefix, name):
                            return True
                if isinstance(parent, (ast.For, ast.AsyncFor)) \
                        and any(self._selector_within(node, part)
                                for part in parent.body + parent.orelse) \
                        and any(isinstance(part, ast.Name) and part.id == name
                                for part in ast.walk(parent.target)):
                    return True
                if isinstance(parent, (ast.With, ast.AsyncWith)):
                    for item in parent.items:
                        if self._selector_within(node, item.context_expr):
                            break
                        if item.optional_vars is not None and any(
                                isinstance(part, ast.Name) and part.id == name
                                for part in ast.walk(item.optional_vars)):
                            return True
                if isinstance(parent, ast.ExceptHandler) and parent.name == name \
                        and any(self._selector_within(node, part) for part in parent.body):
                    return True
                if isinstance(parent, ast.match_case) \
                        and not self._selector_within(node, parent.pattern) \
                        and self._selector_captures([parent.pattern], name):
                    return True
                current = parent
            return False
        return False

    def _selector_lexical_shadow(self, node, name, fns):
        for fn in fns:
            _exprs, _defaults, bound, _stores = self._locals(fn)
            if name in bound or self._selector_captures(self._own(fn), name):
                return True
        parent, skip_class = self._parents_all.get(id(node)), False
        while parent is not None:
            if isinstance(parent, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                first, *_rest = parent.generators
                inner = not self._selector_within(node, first.iter)
                visible = set()
                for gen in parent.generators:
                    if self._selector_within(node, gen.iter):
                        break
                    visible.update(part.id for part in ast.walk(gen.target)
                                   if isinstance(part, ast.Name))
                    if any(self._selector_within(node, part) for part in gen.ifs):
                        break
                if name in visible:
                    return True
                if inner:
                    skip_class = True
            elif isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                body = [parent.body] if isinstance(parent, ast.Lambda) else parent.body
                if any(self._selector_within(node, part) for part in body):
                    skip_class = True
            elif isinstance(parent, ast.ClassDef):
                if not skip_class and self._selector_prior_shadow(node, name, parent.body):
                    return True
                skip_class = True
            parent = self._parents_all.get(id(parent))
        return False

    def _selector_builtin(self, node, name, fns):
        if not isinstance(node, ast.Name) or node.id != name or not hasattr(builtins, name):
            return False
        if self._selector_consumer_owner(node, name) is not None:
            return False
        if any(scope is not None for scope, _target in
               self._selector_consumer_binding_sites(None, name)):
            return False
        if self._selector_lexical_shadow(node, name, fns):
            return False
        _own, counts, _glob = self._scope_info(self.tree.body)
        global_write = self.top_stores.get(name, len(())) > counts.get(name, len(()))
        if global_write:
            return False
        if fns:
            return not self._selector_scope_binds(self.tree.body, name)
        return not self._selector_prior_shadow(node, name, self.tree.body)

    def _selector_fail(self):
        self._selector_refused = True
        return _UNRESOLVED

    def _selector_inputs(self, nodes, fns):
        values = [self._ev(node.value if isinstance(node, ast.Starred) else node, fns)
                  for node in nodes]
        if any(self._runtime(value) for value in values):
            return self._NONE
        if any(value is _UNRESOLVED for value in values):
            return self._selector_fail()
        return self._BUSY

    def _selector_method(self, node, fns):
        f = node.func
        if not isinstance(f, ast.Attribute) or f.attr in ("format", "format_map", "join") \
                or f.attr in self._READ_METHODS:
            return self._BUSY
        base = self._ev(f.value, fns)
        supplied = list(node.args) + [part.value for part in node.keywords]
        if base is self._NONE:
            return self._NONE
        if base is _UNRESOLVED:
            value = self._selector_inputs(supplied, fns)
            return value if value is self._NONE else self._selector_fail()
        members = base.vals if isinstance(base, _Choice) else (base,)
        if not members or not all(isinstance(self._plain(value), str) for value in members):
            return self._BUSY
        expanded = any(isinstance(part, ast.Starred) for part in node.args) \
            or any(part.arg is None for part in node.keywords)
        if expanded:
            value = self._selector_inputs(supplied, fns)
            return value if value is self._NONE else self._selector_fail()
        args = [self._ev(part, fns) for part in node.args]
        kws = {part.arg: self._ev(part.value, fns) for part in node.keywords}
        values = args + list(kws.values())
        if any(self._runtime(value) for value in values):
            return self._NONE
        if any(value is _UNRESOLVED for value in values):
            return self._selector_fail()
        if f.attr in self._SELECTOR_NONSTRING_METHODS:
            return self._BUSY
        if f.attr not in self._SELECTOR_STRING_METHODS:
            return self._selector_fail()
        names, positional = list(kws), len(args)

        def invoke(receiver, *parts):
            positional_values = parts[:positional]
            named_values = dict(zip(names, parts[positional:]))
            return getattr(receiver, f.attr)(*positional_values, **named_values)
        value = self._lift(invoke, [base] + args + [kws[name] for name in names],
                           receiver_origin=True)
        return self._selector_fail() if value is _UNRESOLVED else value

    def _selector_take(self, value, reverse, default):
        if value is self._NONE:
            return self._NONE
        if value is _UNRESOLVED:
            return self._selector_fail()
        if isinstance(value, _Choice):
            selected, runtime = [], value.runtime
            for member in value.vals:
                result = self._selector_take(member, reverse, default)
                if result is self._NONE:
                    runtime = True
                elif result is _UNRESOLVED:
                    return result
                else:
                    selected.append(result)
            if not selected:
                return self._NONE if runtime else self._selector_fail()
            try:
                only, = selected
            except ValueError:
                only = self._BUSY
            if only is not self._BUSY and not runtime and not value.owners:
                return only
            return _Choice(selected, runtime, value.owners)
        origin = value.origin if isinstance(value, _Bound) else None
        plain = self._plain(value)
        if isinstance(plain, dict):
            items = list(plain)
        elif isinstance(plain, (tuple, list, str)):
            items = list(plain)
        else:
            return self._selector_fail()
        if reverse:
            items.reverse()
        if not items:
            return self._selector_fail() if default is self._BUSY else default
        item, *_rest = items
        return _Bound(item, origin) if origin is not None else item

    def _selector_container_source(self, node, fns, seen=frozenset()):
        """The single visible literal-container binding behind node, if any."""
        if isinstance(node, ast.Name):
            for fn in fns:
                exprs, _defaults, bound, _stores = self._locals(fn)
                if node.id in exprs:
                    key = self.mod, id(fn), node.id
                    if key in seen:
                        return None
                    value = exprs[node.id]
                    if isinstance(value, (ast.Tuple, ast.List, ast.Dict)):
                        return self, value, [fn] + self._chain(fn)
                    if isinstance(value, (ast.Name, ast.Attribute)):
                        return self._selector_container_source(
                            value, [fn] + self._chain(fn), seen | {key})
                    return None
                if node.id in bound:
                    return None
            assignment = self.assigns.get(node.id)
            if assignment is not None and assignment.value is not None \
                    and self.top_stores.get(node.id) == len((node.id,)):
                key = self.mod, None, node.id
                if key in seen:
                    return None
                if isinstance(assignment.value, (ast.Tuple, ast.List, ast.Dict)):
                    return self, assignment.value, []
                if isinstance(assignment.value, (ast.Name, ast.Attribute)):
                    return self._selector_container_source(assignment.value, [], seen | {key})
            if node.id in self.from_imports and node.id not in self.defs \
                    and node.id not in self.assigns:
                module, attr = self.from_imports[node.id]
                peer = self.peer(module.split(".")[len(())])
                return peer._selector_module_container(attr, seen) if peer is not None else None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and self._owners(node.value.id, fns) is False:
            peer = self.peer(self.mod_alias[node.value.id].split(".")[len(())])
            return peer._selector_module_container(node.attr, seen) if peer is not None else None
        return None

    def _selector_module_container(self, name, seen):
        key = self.mod, None, name
        if key in seen:
            return None
        assignment = self.assigns.get(name)
        if assignment is not None and assignment.value is not None \
                and self.top_stores.get(name) == len((name,)):
            if isinstance(assignment.value, (ast.Tuple, ast.List, ast.Dict)):
                return self, assignment.value, []
            if isinstance(assignment.value, (ast.Name, ast.Attribute)):
                return self._selector_container_source(assignment.value, [], seen | {key})
        if name in self.from_imports and name not in self.defs and name not in self.assigns:
            module, attr = self.from_imports[name]
            peer = self.peer(module.split(".")[len(())])
            return peer._selector_module_container(attr, seen | {key}) if peer is not None else None
        return None

    def _selector_peer_ordered(self, peer, node, fns, reverse, default):
        if peer is self or peer._selector_mode:
            return peer._selector_ordered(node, fns, reverse, default)
        keep_mode, keep_refused = peer._selector_mode, peer._selector_refused
        keep_caches = peer._mv, peer._lv, peer._rv, peer._av
        peer._selector_mode, peer._selector_refused = True, False
        peer._mv, peer._lv, peer._rv, peer._av = {}, {}, {}, {}
        try:
            value = peer._selector_ordered(node, fns, reverse, default)
            self._selector_refused = self._selector_refused or peer._selector_refused
            return value
        finally:
            peer._mv, peer._lv, peer._rv, peer._av = keep_caches
            peer._selector_mode, peer._selector_refused = keep_mode, keep_refused

    def _selector_ordered(self, node, fns, reverse, default):
        source = self._selector_container_source(node, fns)
        if source is not None:
            resolved = self._selector_consumer(node, fns)
            if self._runtime(resolved):
                return self._NONE
            if resolved is _UNRESOLVED:
                return self._selector_fail()
            scan, expression, source_fns = source
            return self._selector_take(resolved, reverse, default) if isinstance(resolved, _Bound) \
                else self._selector_peer_ordered(scan, expression, source_fns, reverse, default)
        if isinstance(node, (ast.Tuple, ast.List)):
            if any(isinstance(part, ast.Starred) for part in node.elts):
                value = self._selector_inputs(node.elts, fns)
                return value if value is self._NONE else self._selector_fail()
            values = [self._ev(part, fns) for part in node.elts]
            if any(self._runtime(value) for value in values):
                return self._NONE
            if any(value is _UNRESOLVED for value in values):
                return self._selector_fail()
            pairs = list(zip(node.elts, values))
            if reverse:
                pairs.reverse()
            if not pairs:
                return self._selector_fail() if default is self._BUSY else default
            (_part, selected), *_rest = pairs
            return selected
        if isinstance(node, ast.Dict) and all(key is not None for key in node.keys):
            values = [self._ev(part, fns) for part in node.keys + node.values]
            if any(self._runtime(value) for value in values):
                return self._NONE
            if any(value is _UNRESOLVED for value in values):
                return self._selector_fail()
            keys = [self._ev(part, fns) for part in node.keys]
            if reverse:
                keys.reverse()
            if not keys:
                return self._selector_fail() if default is self._BUSY else default
            selected, *_rest = keys
            return selected
        return self._selector_take(self._selector_consumer(node, fns), reverse, default)

    def _selector_next(self, node, fns):
        if not self._selector_builtin(node.func, "next", fns):
            return self._BUSY
        supplied = list(node.args) + [part.value for part in node.keywords]
        if node.keywords or any(isinstance(part, ast.Starred) for part in node.args):
            value = self._selector_inputs(supplied, fns)
            return value if value is self._NONE else self._selector_fail()
        try:
            inner, = node.args
            default = self._BUSY
        except ValueError:
            try:
                inner, default_node = node.args
            except ValueError:
                value = self._selector_inputs(supplied, fns)
                return value if value is self._NONE else self._selector_fail()
            default = self._ev(default_node, fns)
            if self._runtime(default):
                return self._NONE
            if default is _UNRESOLVED:
                return self._selector_fail()
        if not isinstance(inner, ast.Call):
            return self._BUSY
        inner_supplied = list(inner.args) + [part.value for part in inner.keywords]
        if inner.keywords or any(isinstance(part, ast.Starred) for part in inner.args):
            value = self._selector_inputs(inner_supplied, fns)
            return value if value is self._NONE else self._selector_fail()
        direction = next((name for name in ("iter", "reversed")
                          if self._selector_builtin(inner.func, name, fns)), None)
        if direction is None:
            return self._BUSY
        try:
            source, = inner.args
        except ValueError:
            value = self._selector_inputs(inner_supplied, fns)
            return value if value is self._NONE else self._selector_fail()
        value = self._selector_ordered(source, fns, direction == "reversed", default)
        if value in (self._NONE, _UNRESOLVED):
            return value
        members = value.vals if isinstance(value, _Choice) else (value,)
        return value if any(isinstance(self._plain(member), str) for member in members) else self._NONE

    def _selector_call(self, node, fns):
        value = self._selector_next(node, fns)
        if value is not self._BUSY:
            return value
        return self._selector_method(node, fns)

    def _ev_call(self, node, fns):
        N, U = self._NONE, _UNRESOLVED
        if self._selector_mode:
            value = self._selector_call(node, fns)
            if value is not self._BUSY:
                return value
        if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
            return N
        args = [self._ev(a, fns) for a in node.args]
        kws = {k.arg: self._ev(k.value, fns) for k in node.keywords}
        closed = all(v is not N for v in args + list(kws.values()))
        f = node.func
        if isinstance(f, ast.Name) and f.id in self._PURE and f.id not in self.defs \
                and not any(f.id in self._locals(fn)[2] for fn in fns) and f.id not in self.assigns:
            if not closed:
                return N
            if any(v is U for v in args + list(kws.values())):
                return U
            pure, names = self._PURE[f.id], list(kws)
            n = len(args)

            def call(*xs):
                out = pure(*xs[:n], **dict(zip(names, xs[n:])))
                return tuple(out) if f.id == "reversed" else out
            return self._lift(call, args + [kws[k] for k in names])
        if isinstance(f, ast.Attribute) and f.attr in ("format", "format_map", "join"):
            base = self._ev(f.value, fns)
            if base is N or any(v is N for v in args + list(kws.values())):
                return N
            if base is U or any(v is U for v in args + list(kws.values())):
                return U
            plain = self._plain(base)
            if isinstance(plain, str) or (isinstance(base, _Choice)
                    and all(isinstance(self._plain(m), str) for m in base.vals)):
                names, n, attr = list(kws), len(args), f.attr

                def string_call(b, *xs):
                    positional, named = xs[:n], dict(zip(names, xs[n:]))
                    if attr == "format":
                        return b.format(*positional, **named)
                    if attr == "format_map":
                        return b.format_map(*positional, **named)
                    if named or any(isinstance(x, (set, frozenset)) for x in positional):
                        raise TypeError
                    return b.join(*positional)
                return self._lift(string_call, [base] + args + [kws[k] for k in names])
        if isinstance(f, ast.Attribute) and f.attr in self._READ_METHODS:
            base = self._ev(f.value, fns)
            containers = (dict, tuple, list, str)
            if isinstance(self._plain(base), containers) or (isinstance(base, _Choice)
                    and all(isinstance(self._plain(m), containers) for m in base.vals)):
                if not closed:
                    return N
                if any(v is U for v in args + list(kws.values())):
                    return U
                names, n, attr = list(kws), len(args), f.attr

                def read(b, *xs):
                    out = getattr(b, attr)(*xs[:n], **dict(zip(names, xs[n:])))
                    return tuple(out) if attr in ("keys", "values", "items") else out
                return self._lift(read, [base] + args + [kws[k] for k in names])
            if base is U or isinstance(base, _Choice):
                return U
        scan, fn = self._callee(f, fns)
        if isinstance(fn, list):                  # one name, several methods it may be
            v = self.decide([s.return_value(d) for s, d in fn], 0, 0,
                            ["%s:%d" % (s.mod, d.lineno) for s, d in fn])
            if v is not N:
                return v
            fn = None
        if fn is not None:
            v = scan.return_value(fn)
            if v is not N:
                return v
        no_input = not any(self._runtime(v) for v in args + list(kws.values()))
        if no_input and (args or kws) and (scan is not None or self._library_callee(f, fns)):
            return U              # a closed input into code the guard cannot evaluate
        return N

    def _library_callee(self, f, fns):
        """Whether a call names a function of an imported module the guard
        does not read (`math.sqrt`, `from datetime import timedelta`): with
        closed arguments its result has no runtime input (fix pass 4). A
        method of a runtime object is not one."""
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            return self._owners(f.value.id, fns) is False and \
                self.peer(self.mod_alias[f.value.id].split(".")[0]) is None
        if isinstance(f, ast.Name) and f.id in self.from_imports and f.id not in self.defs \
                and not any(f.id in self._locals(fn)[2] for fn in fns):
            return self.peer(self.from_imports[f.id][0].split(".")[0]) is None
        return False

    def _closed(self, node, fns):
        """_UNRESOLVED when every name the expression reads from outside it is
        a constant (no runtime input reaches it), else _NONE."""
        inner = set()
        for n in ast.walk(node):
            if isinstance(n, ast.comprehension):
                inner.update(x.id for x in ast.walk(n.target) if isinstance(x, ast.Name))
            elif isinstance(n, ast.Lambda):
                inner.update(a.arg for a in n.args.args + n.args.kwonlyargs)
            elif isinstance(n, ast.NamedExpr):
                inner.add(n.target.id)
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in inner:
                if hasattr(builtins, n.id) and n.id not in self.defs and n.id not in self.assigns:
                    continue
                if self._runtime(self._ev(n, fns)):
                    return self._NONE
            elif isinstance(n, (ast.Attribute, ast.Call, ast.Await, ast.Yield, ast.YieldFrom)) \
                    and not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id in self._PURE):
                if isinstance(n, ast.Attribute) and not self._runtime(self._ev(n, fns)):
                    continue
                return self._NONE
        return _UNRESOLVED

    def _enclosing_fns(self, node, parents):
        p = parents.get(id(node))
        out = []
        while p is not None:
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                out.append(p)
            p = parents.get(id(p))
        return out

    def resolve(self, node, parents):
        """The resolved constant, carrying approved binding provenance when
        present, or _UNRESOLVED or _NONE."""
        if not isinstance(node, ast.expr) \
                or not isinstance(getattr(node, "ctx", ast.Load()), ast.Load):
            return self._NONE
        fns = self._enclosing_fns(node, parents)
        v = self._ev(node, fns)
        if v is self._NONE and not isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)):
            closed = self._closed(node, fns)
            if closed is _UNRESOLVED:
                return closed
        return v

    def _selector_resolve(self, node, parents):
        """Resolve one decision operand with call-shaped values enabled."""
        if not isinstance(node, ast.expr) \
                or not isinstance(getattr(node, "ctx", ast.Load()), ast.Load):
            return self._NONE
        keep_mode, keep_refused = self._selector_mode, self._selector_refused
        keep_caches = self._mv, self._lv, self._rv, self._av
        self._selector_mode, self._selector_refused = True, False
        self._mv, self._lv, self._rv, self._av = {}, {}, {}, {}
        try:
            fns = self._enclosing_fns(node, parents)
            value = self._ev(node, fns)
            if value is self._NONE \
                    and not isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)):
                closed = self._closed(node, fns)
                if closed is _UNRESOLVED:
                    value = closed
            return _SELECTOR_REFUSAL if self._selector_refused else value
        finally:
            self._mv, self._lv, self._rv, self._av = keep_caches
            self._selector_mode, self._selector_refused = keep_mode, keep_refused

    def _decides(self, node, parents):
        """Whether a value reaches a decision: a comparison, a branch or loop
        test, a boolean operator, an assertion or a comprehension filter,
        through any arithmetic around it."""
        n, p = node, parents.get(id(node))
        while isinstance(p, (ast.BinOp, ast.UnaryOp)) and not (isinstance(p, ast.UnaryOp)
                                                               and isinstance(p.op, ast.Not)):
            n, p = p, parents.get(id(p))
        if isinstance(p, (ast.Compare, ast.BoolOp)) or (isinstance(p, ast.UnaryOp) and isinstance(p.op, ast.Not)):
            return True
        if isinstance(p, (ast.If, ast.IfExp, ast.While, ast.Assert)) and p.test is n:
            return True
        return isinstance(p, ast.comprehension) and n in p.ifs

    def _alias(self, node, parents):
        """Judge a followed binding at its use."""
        v = self.resolve(node, parents)
        if v is self._NONE:
            return
        if v is _UNRESOLVED:
            if self._decides(node, parents):
                self.add(node.lineno, "unresolved")
            return
        if isinstance(v, _Choice):
            if v.owners:
                # AMBIGUOUS: several bindings may reach this use. At a decision
                # it does not resolve to one binding: the exit-3 refusal, the
                # binding sites listed. Anywhere else every member, a boolean
                # included, is judged as if it were the value.
                if self._decides(node, parents):
                    self.add(node.lineno, "ambiguous (%s)" % " ".join(v.owners))
                for m in v.vals:
                    self._judge(m, node, parents)
                return
            # one function's own control flow chose it: every closed member is
            # judged as if it were the value; a boolean chosen at run time by
            # that flow is state, never a constant toggle
            for m in v.vals:
                if not isinstance(m, bool):
                    self._judge(m, node, parents)
            return
        self._judge(v, node, parents)

    def _judge(self, v, node, parents):
        """Judge one closed value at its use."""
        v = self._plain(v)
        p = parents.get(id(node))
        if isinstance(v, (tuple, list, frozenset, set)):
            if isinstance(p, ast.Compare) and node is not p.left:
                ops = [o for o, x in zip(p.ops, p.comparators) if x is node]
                if ops and isinstance(ops[0], (ast.In, ast.NotIn)):
                    for x in v:
                        if isinstance(x, (int, float)) and not isinstance(x, bool) \
                                and x not in STRUCTURAL["compare_eq"]:
                            self.add(node.lineno, "number")
                        elif isinstance(x, bool):
                            self.add(node.lineno, "bool")
            return
        if isinstance(v, (dict, str)):
            return                                   # strings: judged in _compare
        if isinstance(v, bool):
            if (isinstance(p, (ast.If, ast.IfExp, ast.While)) and p.test is node) \
                    or isinstance(p, ast.BoolOp) \
                    or (isinstance(p, ast.UnaryOp) and isinstance(p.op, ast.Not)):
                self.add(node.lineno, "bool")
            elif isinstance(p, ast.Compare):
                ops = p.ops
                if not all(isinstance(o, (ast.Is, ast.IsNot)) for o in ops):
                    self.add(node.lineno, "bool")
            return
        if not isinstance(v, (int, float)):
            return
        if isinstance(p, ast.Subscript) and p.slice is node and isinstance(v, int) \
                and -1 <= v <= INDEX_MAX:
            return
        if not self._number_ok(v, node, parents):
            self.add(node.lineno, "number")

    def add(self, line, cls):
        self.findings.append((self.label, line, cls))

    # -- the node checks --
    def check_nodes(self, nodes, pinned_ok=frozenset()):
        for top in nodes:
            pinned_node = None
            if isinstance(top, (ast.Assign, ast.AnnAssign)):
                targets = top.targets if isinstance(top, ast.Assign) else [top.target]
                names = [t.id for t in targets if isinstance(t, ast.Name)]
                for n in names:
                    if (self.mod, n) in PINNED_SHA:
                        pinned_node = top.value
                        try:
                            digest = hashlib.sha256(
                                repr(ast.literal_eval(top.value)).encode()).hexdigest()
                        except ValueError:
                            digest = None
                        if digest != PINNED_SHA[(self.mod, n)]:
                            self.add(top.lineno, "pinned")
                    if (self.mod, n) in PINNED:
                        pinned_node = top.value
                        try:
                            val = ast.literal_eval(top.value)
                        except ValueError:
                            val = _fold(top.value)
                        if val != PINNED[(self.mod, n)]:
                            self.add(top.lineno, "pinned")
            self._walk(top, pinned_node)

    def _walk(self, top, pinned_node):
        skip = set()
        if pinned_node is not None:
            skip = {id(n) for n in ast.walk(pinned_node)}
        index_ok = set()
        folded = set()
        parents = {}
        for node in ast.walk(top):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node
        for node in ast.walk(top):
            if isinstance(node, ast.Subscript) and not isinstance(node.value, (ast.Constant, ast.List,
                                                                               ast.Tuple, ast.Dict)):
                parts = ([node.slice.lower, node.slice.upper, node.slice.step]
                         if isinstance(node.slice, ast.Slice) else [node.slice])
                for part in parts:
                    v = _fold(part) if part is not None else None
                    if isinstance(v, int) and -1 <= v <= INDEX_MAX:
                        index_ok.update(id(n) for n in ast.walk(part))
        if top is self.tree or isinstance(top, (ast.Assign, ast.AnnAssign)):
            self._module_bool(top)
        for node in ast.walk(top):
            nid = id(node)
            if nid in skip:
                continue
            if isinstance(node, (ast.BinOp, ast.UnaryOp)) and nid not in folded:
                v = _fold(node)
                if v is not None:
                    folded.update(id(n) for n in ast.walk(node))
                    if nid not in index_ok and not self._number_ok(v, node, parents):
                        self.add(node.lineno, "number")
                    continue
            if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)) \
                    and not isinstance(getattr(node, "ctx", ast.Load()), (ast.Store, ast.Del)):
                self._alias(node, parents)
            if isinstance(node, ast.Compare):
                self._compare(node, parents)
            elif isinstance(node, (ast.If, ast.IfExp, ast.While)):
                t = node.test
                if isinstance(t, ast.Constant) and isinstance(t.value, bool) \
                        and not (isinstance(node, ast.While) and t.value is True and not node.orelse):
                    self.add(node.lineno, "bool")
            elif isinstance(node, ast.BoolOp):
                if any(isinstance(x, ast.Constant) and isinstance(x.value, bool) for x in node.values):
                    self.add(node.lineno, "bool")
            if isinstance(node, ast.Constant):
                if nid in folded:
                    continue
                v = node.value
                if isinstance(v, bool) or v is None:
                    continue
                if isinstance(v, (int, float, complex)):
                    if nid not in index_ok and not self._number_ok(v, node, parents):
                        self.add(node.lineno, "number")
                elif isinstance(v, (str, bytes)):
                    t = v.decode("latin-1") if isinstance(v, bytes) else v
                    if text_bad(t):
                        self.add(node.lineno, "text")
                    if "runtime_settings" in t and (self.mod, self._fn_of(node)) not in SETTINGS_READERS:
                        self.add(node.lineno, "setting")
            elif isinstance(node, ast.JoinedStr):
                pass  # its literal parts are Constants, checked above
            elif isinstance(node, ast.Call):
                self._call(node)
            elif isinstance(node, ast.Subscript):
                self._env_subscript(node)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                        else [node.module or ""])
                allowed = DYNAMIC_ALLOWED.get((self.mod, self._fn_of(node)), frozenset())
                for m in mods:
                    if m.split(".")[0] in _DYNAMIC_MODULES and m.split(".")[0] not in allowed:
                        self.add(node.lineno, "call")

    def _number_ok(self, v, node, parents) -> bool:
        """Whether numeric value v at node is structural IN ITS CONTEXT."""
        p = parents.get(id(node))
        while isinstance(p, ast.Tuple) and isinstance(parents.get(id(p)), ast.Compare):
            p = parents.get(id(p))          # `x in (0, 1)` is judged as the comparison
        if isinstance(p, ast.Compare):
            if v in STRUCTURAL["compare_any"]:
                return True
            return v in STRUCTURAL["compare_eq"] and all(isinstance(o, _EQ_OPS + (ast.In, ast.NotIn))
                                                         for o in p.ops)
        if isinstance(p, ast.BinOp):
            if v in STRUCTURAL["wrap"] and isinstance(p.op, (ast.Mod, ast.Sub, ast.Add, ast.BitAnd)):
                return True
            return (type(p.op), v) in STRUCTURAL["binop"]
        if isinstance(p, ast.AugAssign):
            return v in STRUCTURAL["augassign"] and isinstance(p.op, (ast.Add, ast.Sub))
        if isinstance(p, ast.keyword) or (isinstance(p, ast.Call) and node in p.args):
            return v in STRUCTURAL["call"]
        return v in STRUCTURAL["plain"]

    def _compare(self, node, parents=None):
        operands = [node.left] + list(node.comparators)
        for i, op in enumerate(node.ops):
            pair = (operands[i], operands[i + 1])
            # `v is True` / `v is False` is the three-valued identity test
            # (unknown stays unknown); every other comparison with a boolean
            # constant is a toggle and is refused.
            for x in pair:
                if isinstance(x, ast.Constant) and isinstance(x.value, bool) \
                        and not isinstance(op, (ast.Is, ast.IsNot)):
                    self.add(node.lineno, "bool")
            if not isinstance(op, _SEL_OPS):
                continue
            strings = []
            selector_refused = False
            _left, right = pair
            for x in pair:
                r = self._selector_resolve(x, parents) if parents is not None else self._NONE
                if isinstance(x, ast.Constant) and isinstance(x.value, str):
                    strings.append((x.value, None))
                elif isinstance(op, (ast.In, ast.NotIn)) and x is right \
                        and isinstance(x, (ast.Tuple, ast.List, ast.Set, ast.Dict)):
                    members = x.keys if isinstance(x, ast.Dict) else x.elts
                    for member in members:
                        if member is None:
                            continue
                        mv = self._selector_resolve(member, parents)
                        if mv is _SELECTOR_REFUSAL:
                            selector_refused = True
                            continue
                        found = self._selector_values(mv)
                        refusal = self._selector_refusal(member, mv, parents, found)
                        if refusal is not None:
                            self.add(node.lineno, refusal)
                        strings.extend(found)
                else:
                    descend = isinstance(x, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)) \
                        or (isinstance(op, (ast.In, ast.NotIn)) and x is right)
                    if r is _SELECTOR_REFUSAL:
                        selector_refused = True
                        continue
                    found = self._selector_values(r, descend=descend)
                    refusal = self._selector_refusal(x, r, parents, found)
                    if refusal is not None:
                        self.add(node.lineno, refusal)
                    strings.extend(found)
            if selector_refused:
                self.add(node.lineno, "unresolved")
            if any(not self._selector_ok(s, origin) for s, origin in strings):
                self.add(node.lineno, "select")

    def _selector_values(self, v, origin=None, descend=True):
        """String values with their individual approved-binding provenance."""
        if isinstance(v, _Bound):
            v, origin = v.value, v.origin
        if isinstance(v, _Choice):
            return tuple(item for m in v.vals
                         for item in self._selector_values(m, origin, descend))
        if isinstance(v, str):
            return ((v, origin),)
        if descend and isinstance(v, (tuple, list, frozenset, set, dict)):
            return tuple(item for m in v
                         for item in self._selector_values(m, origin, descend))
        return ()

    def _selector_refusal(self, node, v, parents, strings):
        """A compound string operand must resolve to one decision binding."""
        if v is _UNRESOLVED:
            if not self._string_expression(node, parents):
                return None
            refusal = "unresolved"
        elif isinstance(v, _Choice) and v.owners and strings:
            refusal = "ambiguous (%s)" % " ".join(v.owners)
        else:
            return None
        simple = (ast.Name, ast.Attribute, ast.Subscript, ast.Call)
        for part in ast.walk(node):
            if part is node or not isinstance(part, simple) or not self._decides(part, parents):
                continue
            resolved = self.resolve(part, parents)
            if (v is _UNRESOLVED and resolved is _UNRESOLVED) or \
                    (isinstance(v, _Choice) and isinstance(resolved, _Choice) and resolved.owners):
                return None
        if isinstance(node, simple) and self._decides(node, parents):
            return None
        return refusal

    def _string_expression(self, node, parents):
        """Whether an unevaluable expression is nevertheless string-shaped."""
        for part in ast.walk(node):
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                return True
            if isinstance(part, ast.JoinedStr):
                return True
            if isinstance(part, ast.Call) and ((isinstance(part.func, ast.Name)
                    and part.func.id == "format") or (isinstance(part.func, ast.Attribute)
                    and part.func.attr in ("format", "format_map", "join"))):
                return True
            if part is not node and isinstance(part, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)):
                if self._selector_values(self.resolve(part, parents)):
                    return True
        return False

    def _selector_ok(self, word, origin):
        if word in SELECTORS:
            return True
        if origin not in SELECTOR_PROVENANCE:
            return False
        mod, name = origin
        scan = self.peer(mod)
        if scan is None:
            return False
        values = scan._selector_values(scan.module_value(name))
        return any(candidate == word for candidate, _binding in values)

    def _module_bool(self, top):
        nodes = self.tree.body if top is self.tree else [top]
        for n in nodes:
            if isinstance(n, (ast.Assign, ast.AnnAssign)) and isinstance(n.value, ast.Constant) \
                    and isinstance(n.value.value, bool) and n in self.tree.body:
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                if not all(isinstance(t, ast.Name) and ((self.mod, t.id) in PINNED
                                                        or (self.mod, t.id) in PINNED_SHA)
                           for t in targets):
                    self.add(n.lineno, "bool")

    def _fn_of(self, node):
        """The ONE function a node is in: a module-level function's name, or
        `Class.method` for a method (never the bare class name, so an
        exemption keyed on a method covers that method only)."""
        line = getattr(node, "lineno", 0)
        for name, d in self.defs.items():
            if d.lineno <= line <= getattr(d, "end_lineno", d.lineno):
                if isinstance(d, ast.ClassDef):
                    for m in d.body:
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                                and m.lineno <= line <= getattr(m, "end_lineno", m.lineno):
                            return name + "." + m.name
                return name
        return None

    def _const_arg(self, a):
        return isinstance(a, ast.Constant) and isinstance(a.value, (str, bytes))

    def _call(self, node):
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        allowed = DYNAMIC_ALLOWED.get((self.mod, self._fn_of(node)), frozenset())
        if isinstance(f, ast.Name) and name in _DYNAMIC_CALLS and name not in allowed:
            self.add(node.lineno, "call")
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                and f.value.id in _DYNAMIC_MODULES and f.value.id not in allowed:
            self.add(node.lineno, "call")
        if name in _DECODERS and node.args and self._const_arg(node.args[0]):
            self.add(node.lineno, "call")
        if name in _DECODERS and node.args and isinstance(node.args[0], (ast.List, ast.Tuple)) \
                and name == "len":
            self.add(node.lineno, "call")
        if name in ("setting", "ice_setting") and len(node.args) >= 2:
            k = node.args[1]
            key = k.value if isinstance(k, ast.Constant) else self.str_consts.get(getattr(k, "id", ""))
            if key not in SWITCHES:
                self.add(node.lineno, "setting")
        if name in ("getenv",) or (name == "get" and isinstance(f, ast.Attribute)
                                   and isinstance(f.value, ast.Attribute)
                                   and f.value.attr == "environ"):
            self._env_key(node, node.args[0] if node.args else None)

    def _env_subscript(self, node):
        if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
            self._env_key(node, node.slice)

    def _env_key(self, node, k):
        key = None
        if isinstance(k, ast.Constant):
            key = k.value
        elif isinstance(k, ast.Name):
            key = self.str_consts.get(k.id)
        if key not in ENV_KEYS:
            self.add(node.lineno, "env")

    def check_comments(self, spans=None):
        try:
            toks = tokenize.generate_tokens(io.StringIO(self.src).readline)
            for tok in toks:
                if tok.type == tokenize.COMMENT:
                    line = tok.start[0]
                    if spans is not None and not any(a <= line <= b for a, b in spans):
                        continue
                    if text_bad(tok.string):
                        self.add(line, "text")
        except (tokenize.TokenError, SyntaxError):
            self.add(0, "text")

    # -- reach --
    def names_in(self, node):
        out = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                out.add(n.id)
            elif isinstance(n, ast.arg):
                out.add("arg:" + n.arg)
        return out

    def roots(self, explicit):
        if explicit is not None:
            return {n for n in explicit if n in self.defs}
        out = set()
        for name, d in self.defs.items():
            names = self.names_in(d)
            if names & REVIEW_NAMES or {"arg:" + p for p in REVIEW_PARAMS} & names:
                out.add(name)
        return out

    def reach(self, roots):
        seen, todo = set(), list(roots)
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            node = self.defs.get(n) or self.assigns.get(n)
            if node is None:
                continue
            for m in self.names_in(node):
                if (m in self.defs or m in self.assigns) and m not in seen:
                    todo.append(m)
        return seen

    def local_imports(self, available, nodes=None):
        out = set()
        for node in ast.walk(self.tree) if nodes is None else [x for n in nodes for x in ast.walk(n)]:
            if isinstance(node, ast.Import):
                out.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                out.add(node.module.split(".")[0])
        return {m for m in out if m in available and m not in INFRA}


def scan_tree(read, available, label_prefix):
    """read(modname) -> source text or None; available = local module names."""
    findings = []
    cache = {}

    def peer(m):
        """The one scan of a local module (judged, rooted, or read only for
        the values of its imported attributes)."""
        if m not in available:
            return None
        if m not in cache:
            src = read(m)
            cache[m] = None if src is None else _Scan(m, "%s %s%s.py" % (label_prefix, API, m), src, peer)
        return cache[m]
    whole = [m for m in JUDGING if m in available]
    done = set()
    queue = list(whole)
    rooted = [m for m in ROOTED if m in available]
    reached_nodes = {}
    for m in rooted:
        s = peer(m)
        reached = s.reach(s.roots(ROOTED[m]))
        nodes = [s.defs.get(n) or s.assigns.get(n) for n in sorted(reached)]
        reached_nodes[m] = [n for n in nodes if n is not None]
        s.site_spans = [(n.lineno, getattr(n, "end_lineno", n.lineno)) for n in reached_nodes[m]]
    # every module this scan judges (the rooted modules' reached code, every
    # module followed whole), so a read of an attribute or a method sees the
    # bindings of that name in each of them, by owner
    judged, todo = set(rooted), list(whole)
    for m in rooted:
        todo.extend(peer(m).local_imports(available, reached_nodes[m])
                    | (peer(m).local_imports(available) & set(JUDGING)))
    while todo:
        m = todo.pop()
        if m in judged or peer(m) is None:
            continue
        judged.add(m)
        todo.extend(peer(m).local_imports(available))
    for m in judged:
        s = peer(m)
        s.foreign = (lambda attr, names, me=m: [x for o in sorted(judged) if o != me
                                                for x in peer(o).foreign_sites(attr, names)])
        s.foreign_methods = (lambda name, me=m: [(peer(o), d) for o in sorted(judged) if o != me
                                                 for _c, d in peer(o).methods.get(name, ())
                                                 if peer(o).in_spans(d.lineno)])
    for m in rooted:
        s = peer(m)
        nodes = reached_nodes[m]
        s.check_nodes(nodes)
        s.check_comments(s.site_spans)
        # a module-level import the rooted code relies on is followed whole
        queue.extend(s.local_imports(available, nodes) | (s.local_imports(available) & set(JUDGING)))
        findings.extend(s.findings)
    while queue:
        m = queue.pop()
        if m in done or m in ROOTED:
            continue
        done.add(m)
        s = peer(m)
        if s is None:
            continue
        s.check_nodes(s.tree.body)
        s.check_comments()
        queue.extend(s.local_imports(available))
        findings.extend(s.findings)
    return findings


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True).stdout


def tree_mode(repo):
    base = os.path.join(repo, *API.split("/"))
    available = {f[:-3] for f in os.listdir(base) if f.endswith(".py")}

    def read(m):
        p = os.path.join(base, m + ".py")
        with open(p, encoding="utf-8") as fh:
            return fh.read()
    return scan_tree(read, available, "tree"), 1


def range_mode(repo, base, tip):
    commits = _git(repo, "rev-list", "--reverse", "%s..%s" % (base, tip)).decode().split()
    findings = []
    for c in commits:
        listing = _git(repo, "ls-tree", "--name-only", c, API).decode().splitlines()
        available = {p[len(API):-3] for p in listing if p.endswith(".py") and "/" not in p[len(API):]}

        def read(m, c=c):
            try:
                return _git(repo, "show", "%s:%s%s.py" % (c, API, m)).decode("utf-8")
            except subprocess.CalledProcessError:
                return None
        findings.extend(scan_tree(read, available, c[:12]))
    return findings, len(commits)


def main(argv):
    if len(argv) == 2 and argv[0] == "tree":
        findings, n = tree_mode(argv[1])
    elif len(argv) == 4 and argv[0] == "range":
        findings, n = range_mode(argv[1], argv[2], argv[3])
    else:
        print(__doc__.split("Modes:")[1].split("Output:")[0].rstrip())
        return 2
    for label, line, cls in findings:
        print("%s:%d %s" % (label, line, cls))
    print("review_guard: %d finding(s) in %d tree(s)" % (len(findings), n))
    if any(cls == "unresolved" or cls.startswith("ambiguous") for _l, _n, cls in findings):
        # a decision whose value the guard cannot settle to one binding is no
        # verdict, never a pass
        print("review_guard: no verdict (an unresolved or ambiguous value reaches a decision)")
        return 3
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
