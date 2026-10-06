"""The no-tunables guard for the public review code.

The public review code describes evidence and evaluates rules generically;
every value that decides an outcome belongs to the rules revision, which is
not part of this repository. This guard checks that, as a transitive analysis
over the source of every tree it is given:

  * JUDGING modules (review_measures, review_rules, review_module,
    review_module_runner, combat_measures, and any local module one of them
    imports) are scanned whole: code, module-level constants, string
    constants (SQL and text included) and comments;
  * seat_evidence and combat_evidence are scanned from their REVIEW ROOTS
    (every function that
    touches the review modules or a loaded ruleset) through every module
    -level function and constant they reach, and main.py from its review
    worker functions the same way; any local module either imports is
    followed and scanned whole.

Within that reach it refuses:
  number   a numeric constant (after folding constant arithmetic) other than
           the structural ones, unless it is a subscript index on a computed
           value or sits inside a PINNED contract bound whose value matches;
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
           layout is pinned by the sha256 of its literal value's repr).

Modes:
  python backend/tools/review_guard.py tree <repo dir>
  python backend/tools/review_guard.py range <repo dir> <base> <tip>
        every commit of base..tip, each tree checked on its own (a value
        that lived only in an earlier commit is still in the landing range)

Output: one line per finding, `<commit|tree> <path>:<line> <class>` (never
the offending text), then `review_guard: <n> finding(s) in <m> tree(s)`.
Exit 0 clean, 1 findings, 2 usage or a tree that could not be read.
"""

from __future__ import annotations

import ast
import hashlib
import io
import os
import re
import subprocess
import sys
import tokenize

API = "backend/api/"
JUDGING = ("review_measures", "review_rules", "review_module", "review_module_runner",
           "combat_measures")
ROOTED = {"seat_evidence": None, "combat_evidence": None,
          "main": ("review_worker_loop", "review_rules_refresh_loop", "_review_pass_line")}
REVIEW_NAMES = {"rm", "rr", "_review_rules", "review_measures", "review_rules"}
REVIEW_PARAMS = {"rs", "state", "ruleset"}
# Plumbing a rooted function may import without it being followed: the
# session factory and the table declarations decide nothing.
INFRA = {"database", "models"}

ALLOWED_NUMBERS = {0, 1, -1, 2, 2 ** 31, 2 ** 32, 1000}
INDEX_MAX = 15

# Contract bounds and scheduling: pinned BY VALUE. A deciding value added to
# one of these makes the pin differ, and the guard refuses it.
PINNED = {
    ("review_measures", "CONTRACT_BOUNDS"): {"ready_lag_s": 120, "edges_max": 8, "label_max": 16,
                                             "show_max": 16, "eval_hex": 8},
    ("review_measures", "WINDOW_KINDS"): (0, 2, 3),
    ("review_rules", "CONTRACT_BOUNDS"): {
        "files_max": 64, "total_bytes_max": 16777216, "rules_bytes_max": 1048576,
        "selftest_bytes_max": 4194304, "data_bytes_max": 8388608, "rules_max": 200,
        "pred_depth_max": 6, "cases_max": 256, "work_max": 200000, "deadline_s": 10,
        "line_max": 400, "places_default": 3, "round_places": 4, "render_items_max": 6,
        "id_hex": 8, "rev_hex": 12, "nonce_bytes": 16, "digest_hex": 64, "data_name_max": 40,
        "pointer_bytes_max": 64, "frame_bytes": 8, "format": 1},
    ("review_module", "CONTRACT_BOUNDS"): {"api": 1, "start_s": 20, "call_s": 2,
                                           "line_bytes_max": 65536, "nobody_uid": 65534,
                                           "reason_max": 32},
    ("seat_evidence", "GAME_EXPIRY_DAYS"): 14,
    ("seat_evidence", "GAMES_PER_PASS"): 500,
    ("seat_evidence", "SITTINGS_PER_PASS"): 500,
    ("seat_evidence", "MARK_ROWS_PER_PASS"): 5000,
    ("seat_evidence", "DETAILS_MAX_BYTES"): 2048,
    ("seat_evidence", "COMPAT_ROWS_SHOWN"): 10,
    ("combat_evidence", "GAME_EXPIRY_DAYS"): 14,
    ("combat_evidence", "GAMES_PER_PASS"): 500,
    ("main", "REVIEW_PASS_S"): 600,
    ("main", "REVIEW_FIRST_PASS_S"): 90,
    ("main", "REVIEW_PURGE_EVERY_S"): 72000,
    ("main", "REVIEW_REFRESH_S"): 60,
}
# The combat wire layout (field bounds, list caps, tier order, enum codes):
# pinned by the sha256 of repr(ast.literal_eval(value)). A value added to or
# changed in it makes the digest differ, and the guard refuses it. The wire
# amendment's layout is pinned the same way, beside it.
PINNED_SHA = {
    ("combat_measures", "COMBAT_WIRE"):
        "cf51bb58df95b57e062ad4dcbfc90c6d34b57469d58012e85108c308561b295f",
    ("combat_measures", "COMBAT_WIRE_A1"):
        "644aaae92623587f5cfc2d814edb3351d89b159032073ce9451d7dd9501a135c",
}
SWITCHES = {"seat_evidence_accept", "seat_evidence_worker", "seat_evidence_purge",
            "combat_evidence_accept", "combat_evidence_worker", "combat_evidence_purge"}
SETTINGS_READERS = {("seat_evidence", "setting"), ("combat_evidence", "setting")}
ENV_KEYS = {"SCR_REVIEW_ROOT", "SYSTEMROOT"}

# Identifiers that carry a digit and decide nothing: match-row columns of the
# two seats, their SQL aliases, digest and encoding names, the combat wire's
# own key names (a closed list) and its public vocabulary names (the dotted
# b-family names).
_SAFE_TEXT = re.compile(
    r"\bp[12]_\w+|\bplayer[12](?:_id)?\b|\b[ps][12]\b|sha256\b|\butf-8\b|\bint(?:32|64)\b"
    r"|\bnoqa: ?[A-Z]+\d+(?:, ?[A-Z]+\d+)*"
    r"|\bt0(?:_src)?\b|\bframe_p50_us\b|\ba1(?:s|p|m|n|sum)\b"
    r"|\bp3(?:n|dp0|an0|dp1|an1|hm|self|top|tb|ht)\b|\bb5_(?:tot|s|o|h|c|r)\b|\b(?:s0|pid0|b[135])\b"
    r"|\bb[1235](?:\.[a-z_]+)+")
_STANDALONE = re.compile(r"(?<![\w.])[01](?![\w.])")
_DIGIT = re.compile(r"\d")

_DYNAMIC_CALLS = {"eval", "exec", "compile", "chr", "ord", "getattr", "globals", "vars",
                  "__import__", "setattr", "locals"}
_DYNAMIC_MODULES = {"base64", "codecs", "importlib", "binascii", "pickle", "marshal", "zlib"}
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
    def __init__(self, modname, label, src):
        self.mod = modname
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
        for node in ast.walk(top):
            if isinstance(node, ast.Subscript) and not isinstance(node.value, (ast.Constant, ast.List,
                                                                               ast.Tuple, ast.Dict)):
                v = _fold(node.slice)
                if isinstance(v, int) and -1 <= v <= INDEX_MAX:
                    index_ok.update(id(n) for n in ast.walk(node.slice))
        for node in ast.walk(top):
            nid = id(node)
            if nid in skip:
                continue
            if isinstance(node, (ast.BinOp, ast.UnaryOp)) and nid not in folded:
                v = _fold(node)
                if v is not None:
                    folded.update(id(n) for n in ast.walk(node))
                    if nid not in index_ok and v not in ALLOWED_NUMBERS:
                        self.add(node.lineno, "number")
                    continue
            if isinstance(node, ast.Constant):
                if nid in folded:
                    continue
                v = node.value
                if isinstance(v, bool) or v is None:
                    continue
                if isinstance(v, (int, float, complex)):
                    if nid not in index_ok and v not in ALLOWED_NUMBERS:
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
                for m in mods:
                    if m.split(".")[0] in _DYNAMIC_MODULES:
                        self.add(node.lineno, "call")

    def _fn_of(self, node):
        line = getattr(node, "lineno", 0)
        for name, d in self.defs.items():
            if d.lineno <= line <= getattr(d, "end_lineno", d.lineno):
                return name
        return None

    def _const_arg(self, a):
        return isinstance(a, ast.Constant) and isinstance(a.value, (str, bytes))

    def _call(self, node):
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if isinstance(f, ast.Name) and name in _DYNAMIC_CALLS:
            self.add(node.lineno, "call")
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                and f.value.id in _DYNAMIC_MODULES:
            self.add(node.lineno, "call")
        if name in _DECODERS and node.args and self._const_arg(node.args[0]):
            self.add(node.lineno, "call")
        if name in _DECODERS and node.args and isinstance(node.args[0], (ast.List, ast.Tuple)) \
                and name == "len":
            self.add(node.lineno, "call")
        if name == "setting" and len(node.args) >= 2:
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
    whole = [m for m in JUDGING if m in available]
    done = set()
    queue = list(whole)
    rooted = [m for m in ROOTED if m in available]
    for m in rooted:
        src = read(m)
        s = _Scan(m, "%s %s%s.py" % (label_prefix, API, m), src)
        reached = s.reach(s.roots(ROOTED[m]))
        nodes = [s.defs.get(n) or s.assigns.get(n) for n in sorted(reached)]
        nodes = [n for n in nodes if n is not None]
        s.check_nodes(nodes)
        spans = [(n.lineno, getattr(n, "end_lineno", n.lineno)) for n in nodes]
        s.check_comments(spans)
        # a module-level import the rooted code relies on is followed whole
        queue.extend(s.local_imports(available, nodes) | (s.local_imports(available) & set(JUDGING)))
        findings.extend(s.findings)
    while queue:
        m = queue.pop()
        if m in done or m in ROOTED:
            continue
        done.add(m)
        src = read(m)
        if src is None:
            continue
        s = _Scan(m, "%s %s%s.py" % (label_prefix, API, m), src)
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
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
