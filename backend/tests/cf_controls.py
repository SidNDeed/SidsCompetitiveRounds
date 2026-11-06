"""The connect-failure controls (evidence V11 section 8.1; lore #391): each
S row's mutants and twin, run against this lane's tests.

A control has two parts. A MUTANT must turn the test red on the assertion the
row names, on a fixture that exercises it; a TWIN changes nothing observable.
The baseline comes first: the unmutated tree passes every control's test in
one recorded run (commit id and tree state in the result file's first line).
A mutant counts only when the baseline was green and the mutant turns EXACTLY
the named assertion red: the test's first failure is an AssertionError whose
message's first element is the tag the registry names. Anything else - a
pass, another assertion, an exception, an error in setup - is recorded as
what it is and never counted. A twin must pass, and the trace it writes
(CF_TRACE_DIR) must equal the baseline's byte for byte. A CLASS control
(cf_controls_rows.C, A7-R4-A1) is a near miss of a mutant that must leave
the test green; it executes something the baseline does not, so its trace
is not compared.

Every mutant and twin is a list of exact text replacements applied to a
scratch copy of the tree. Each replacement asserts how many times its old
text occurs before it applies, so a stale entry fails as STALE instead of
running an unmutated copy.

Usage (absolute paths; one lane database per concurrent run):
  python cf_controls.py check
  python cf_controls.py baseline --db cf_lane_w1 --out DIR [--rows S1,S2]
  python cf_controls.py run --db cf_lane_w2 --out DIR [--rows S1,S2] [--only mutants|twins|classes]
  python cf_controls.py table --out DIR
  python cf_controls.py sweep      (the generated raw-SQL-text sweep, A7-R5-A1 (2)(a))
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import cf_controls_rows as rows_mod  # noqa: E402

HOST = "postgresql+asyncpg://postgres@127.0.0.1:55432/"
COPY = ("backend",)  # the whole tree the tests reach, never a derived list (learning 915)
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "bin", "obj", ".pytest_cache")
TIMEOUT_S = 1800


class Stale(Exception):
    pass


def git_state():
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()
    return head, ("dirty" if dirty else "clean")


BASE_COMMIT = "9a1dd9d"   # the lane's base (test_ffa_assembly_pg.BASE_COMMIT)
PIN_COMMIT = "edf9aee"    # the production pin (test_ffa_assembly_pg.PIN_COMMIT)
# Edit targets outside the tree: the pin's and the base's main.py, which the
# tests import from CF_PIN_MAIN / CF_PRE_MAIN (the copies below).
SRC = {"@pin/main.py": ("main_pin.py", PIN_COMMIT, "CF_PIN_MAIN"),
       "@pre/main.py": ("main_pre.py", BASE_COMMIT, "CF_PRE_MAIN")}


def prepare_sources(out):
    """git show the pin's and the base's main.py into OUT/_src once."""
    d = os.path.join(out, "_src")
    os.makedirs(d, exist_ok=True)
    for name, commit, _ in SRC.values():
        path = os.path.join(d, name)
        if not os.path.exists(path):
            blob = subprocess.run(["git", "-C", ROOT, "show", commit + ":backend/api/main.py"],
                                  capture_output=True, check=True).stdout
            with open(path, "wb") as fh:
                fh.write(blob)
    return d


def source_env(src_dir):
    return {var: os.path.join(src_dir, name) for name, _, var in SRC.values()}


def apply_edits(base, edits):
    for rel, old, new, count in edits:
        if rel in SRC:
            path = os.path.join(base, "_src", SRC[rel][0])
        else:
            path = os.path.join(base, rel)
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8")
        # Anchors are written in their author's line ends (LF for the server
        # rows, CRLF for the client rows) and the checkout has its own: read
        # both sides in the checkout's convention, idempotently, so a row
        # matches on a CRLF seat and on an LF seat alike. (A blanket LF->CRLF
        # step doubles the CR of every CRLF-written anchor.)
        nl = "\r\n" if "\r\n" in text else "\n"
        old = old.replace("\r\n", "\n").replace("\n", nl)
        new = new.replace("\r\n", "\n").replace("\n", nl)
        found = text.count(old)
        if found != count:
            raise Stale("%s: %d occurrence(s) of %r, want %d" % (rel, found, old[:80], count))
        with open(path, "wb") as fh:
            fh.write(text.replace(old, new).encode("utf-8"))


def scratch(edits, src_dir, extra=()):
    d = tempfile.mkdtemp(prefix="cfctl_")
    for rel in COPY + tuple(extra):
        shutil.copytree(os.path.join(ROOT, rel), os.path.join(d, rel), ignore=IGNORE)
    shutil.copytree(src_dir, os.path.join(d, "_src"))
    apply_edits(d, edits)
    return d


def run_pytest(base, nodes, db, trace_dir=None, tag="run", src_dir=None):
    junit = os.path.join(tempfile.gettempdir(), "cfctl_%s_%d_%d.xml"
                         % (tag, os.getpid(), int(time.time() * 1000)))
    env = dict(os.environ)
    env["CF_TEST_PG_DSN"] = HOST + db
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # One hash seed for every run: a set's iteration order is then the same
    # in the baseline's process and each twin's.
    env["PYTHONHASHSEED"] = "0"
    env.update(source_env(src_dir))
    env.pop("CF_TRACE_DIR", None)
    if trace_dir:
        os.makedirs(trace_dir, exist_ok=True)
        env["CF_TRACE_DIR"] = trace_dir
    targets = [os.path.join(base, "backend", "tests", n) for n in nodes]
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q",
                            "-o", "junit_family=xunit1", "--junitxml", junit] + targets,
                           cwd=base, env=env, capture_output=True, text=True,
                           timeout=TIMEOUT_S)
        tail = (p.stdout or "")[-4000:]
    except subprocess.TimeoutExpired:
        return {n: ("timeout", "") for n in nodes}, time.time() - t0, "timeout"
    out = {}
    if os.path.exists(junit):
        for tc in ET.parse(junit).getroot().iter("testcase"):
            name = tc.get("name")
            kind, msg = "passed", ""
            for child in tc:
                if child.tag in ("failure", "error"):
                    kind = "failed" if child.tag == "failure" else "error"
                    msg = child.get("message") or ""
                    if kind == "failed" and "setup" in (child.get("type") or ""):
                        kind = "error"
                elif child.tag == "skipped":
                    kind, msg = "skipped", child.get("message") or ""
            out[name] = (kind, msg)
        os.remove(junit)
    return out, time.time() - t0, tail


_TUPLE_TAG = re.compile(r"^AssertionError: \((['\"])(.*?)\1[,)]", re.S)
_PLAIN_TAG = re.compile(r"^AssertionError: ([^\n]*)")


def first_tag(msg):
    m = _TUPLE_TAG.match(msg or "")
    if m:
        return m.group(2)
    m = _PLAIN_TAG.match(msg or "")
    return m.group(1).strip() if m else None


def node_name(node):
    return node.split("::", 1)[1] if "::" in node else node


def trace_file(node):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", node) + ".json"


def verdict_mutant(result, want):
    kind, msg = result
    if kind == "passed":
        return "GREEN", None
    if kind != "failed":
        return kind.upper(), (msg or "")[:300]
    tag = first_tag(msg)
    if tag is None:
        return "RED-EXCEPTION", (msg or "")[:300]
    ok = tag == want or (want.endswith("*") and tag.startswith(want[:-1]))
    return ("RED-NAMED" if ok else "RED-OTHER"), tag


def record(out, line):
    with open(os.path.join(out, "results.jsonl"), "a", encoding="ascii", newline="\n") as fh:
        fh.write(json.dumps(line, sort_keys=True) + "\n")


def selected(rows_arg):
    rows = rows_mod.ROWS
    if rows_arg:
        want = set(rows_arg.split(","))
        rows = [r for r in rows if r["row"] in want]
        missing = want - {r["row"] for r in rows}
        if missing:
            raise SystemExit("unknown rows: %s" % sorted(missing))
    return rows


def _compile_edited(data, path):
    """One edited file's compile, in a pool worker: None, or the error."""
    try:
        compile(data, path, "exec")
    except SyntaxError as exc:
        return str(exc)
    return None


def cmd_check(args):
    """Every edit set applies (each old string exactly once, in order); with
    --compile, every edited .py file also compiles (a process pool)."""
    import concurrent.futures
    bad = 0
    src_dir = prepare_sources(args.out or tempfile.mkdtemp(prefix="cfchk_src_"))
    pool = (concurrent.futures.ProcessPoolExecutor(max_workers=args.workers)
            if args.compile else None)
    jobs = []
    try:
        for r in selected(args.rows):
            for m in r["mutants"] + ([r["twin"]] if r["twin"] else []) + list(r.get("classes", ())):
                d = tempfile.mkdtemp(prefix="cfchk_")
                try:
                    shutil.copytree(src_dir, os.path.join(d, "_src"))
                    for rel in sorted({e[0] for e in m["edits"]}):
                        if rel in SRC:
                            continue
                        os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                        shutil.copy2(os.path.join(ROOT, rel), os.path.join(d, rel))
                    apply_edits(d, m["edits"])
                    for rel in sorted({e[0] for e in m["edits"]}):
                        if pool is None or not rel.endswith(".py"):
                            continue
                        path = (os.path.join(d, "_src", SRC[rel][0]) if rel in SRC
                                else os.path.join(d, rel))
                        with open(path, "rb") as fh:
                            data = fh.read()
                        jobs.append((r["row"], m["id"], rel,
                                     pool.submit(_compile_edited, data, path)))
                except Stale as exc:
                    bad += 1
                    print("STALE %s %s: %s" % (r["row"], m["id"], exc))
                finally:
                    shutil.rmtree(d, ignore_errors=True)
        for row_id, mid, rel, fut in jobs:
            err = fut.result()
            if err is not None:
                bad += 1
                print("STALE %s %s: %s does not compile after the edits: %s"
                      % (row_id, mid, rel, err))
    finally:
        if pool is not None:
            pool.shutdown()
    total = sum(len(r["mutants"]) + (1 if r["twin"] else 0) + len(r.get("classes", ()))
                for r in selected(args.rows))
    print("checked %d edit set(s), %d stale%s"
          % (total, bad, ", %d compile(s)" % len(jobs) if pool is not None else ""))
    return 1 if bad else 0


def cmd_baseline(args):
    head, state = git_state()
    os.makedirs(args.out, exist_ok=True)
    nodes = []
    for r in selected(args.rows):
        for n in r["nodes"]:
            if n not in nodes:
                nodes.append(n)
    res, dt, tail = run_pytest(ROOT, nodes, args.db, os.path.join(args.out, "baseline"),
                               "baseline", prepare_sources(args.out))
    line = {"kind": "baseline", "head": head, "tree": state, "db": args.db,
            "at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seconds": round(dt, 1),
            "nodes": {node_name(n): res.get(node_name(n), ("missing", ""))[0] for n in nodes}}
    record(args.out, line)
    bad = {k: v for k, v in line["nodes"].items() if v != "passed"}
    print("baseline %s (%s): %d node(s), %d not passed %s"
          % (head, state, len(nodes), len(bad), sorted(bad.items())))
    if bad:
        print(tail)
    return 1 if bad else 0


def cmd_run(args):
    head, state = git_state()
    base_trace = os.path.join(args.out, "baseline")
    src_dir = prepare_sources(args.out)
    for r in selected(args.rows):
        extra = r.get("extra", ())
        parts = []
        if args.only in (None, "mutants"):
            parts += [("mutant", m) for m in r["mutants"]]
        if args.only in (None, "twins") and r["twin"]:
            parts.append(("twin", r["twin"]))
        if args.only in (None, "classes"):
            parts += [("class", m) for m in r.get("classes", ())]
        for kind, m in parts:
            line = {"row": r["row"], "kind": kind, "id": m["id"], "head": head, "tree": state,
                    "db": args.db, "note": m.get("note", "")}
            if m.get("equivalent"):
                line.update(verdict="EQUIVALENT", detail=m["equivalent"])
                record(args.out, line)
                print("%s %s %s EQUIVALENT" % (r["row"], kind, m["id"]))
                continue
            try:
                d = scratch(m["edits"], src_dir, extra)
            except Stale as exc:
                line.update(verdict="STALE", detail=str(exc))
                record(args.out, line)
                print("%s %s %s STALE %s" % (r["row"], kind, m["id"], exc))
                continue
            try:
                nodes = m.get("nodes") or r["nodes"]
                if kind == "mutant":
                    res, dt, tail = run_pytest(d, nodes[:1], args.db, None, "mut",
                                               os.path.join(d, "_src"))
                    v, detail = verdict_mutant(res.get(node_name(nodes[0]), ("missing", "")),
                                               m["tag"])
                    line.update(verdict=v, detail=detail, want=m["tag"], seconds=round(dt, 1),
                                node=node_name(nodes[0]))
                elif kind == "class":
                    res, dt, tail = run_pytest(d, nodes, args.db, None, "class",
                                               os.path.join(d, "_src"))
                    kinds = {node_name(n): res.get(node_name(n), ("missing", ""))[0]
                             for n in nodes}
                    ok = all(k == "passed" for k in kinds.values())
                    line.update(verdict="GREEN" if ok else "NOT-GREEN", detail={"nodes": kinds},
                                seconds=round(dt, 1))
                else:
                    tdir = os.path.join(args.out, "twin_%s" % r["row"])
                    shutil.rmtree(tdir, ignore_errors=True)
                    res, dt, tail = run_pytest(d, nodes, args.db, tdir, "twin",
                                               os.path.join(d, "_src"))
                    kinds = {node_name(n): res.get(node_name(n), ("missing", ""))[0]
                             for n in nodes}
                    diffs = []
                    for n in nodes:
                        # env.trace names the file after the node id (the
                        # rootdir is the tests directory in both runs).
                        x = trace_file(n)
                        a = os.path.join(base_trace, x)
                        b = os.path.join(tdir, x)
                        if not os.path.exists(b):
                            diffs.append("%s: no twin trace" % x)
                        elif not os.path.exists(a):
                            diffs.append("%s: no baseline trace" % x)
                        else:
                            with open(a, "rb") as fa, open(b, "rb") as fb:
                                if fa.read() != fb.read():
                                    diffs.append("%s: trace differs" % x)
                    ok = all(k == "passed" for k in kinds.values()) and not diffs
                    line.update(verdict="INERT" if ok else "NOT-INERT",
                                detail={"nodes": kinds, "diffs": diffs}, seconds=round(dt, 1))
                record(args.out, line)
                print("%s %s %s %s %s" % (r["row"], kind, m["id"], line["verdict"],
                                          line.get("detail")))
            finally:
                shutil.rmtree(d, ignore_errors=True)
    return 0


def cmd_table(args):
    lines = []
    with open(os.path.join(args.out, "results.jsonl"), encoding="ascii") as fh:
        for ln in fh:
            lines.append(json.loads(ln))
    last = {}
    for ln in lines:
        if ln.get("kind") == "baseline":
            print("baseline %s %s %s nodes=%d not-passed=%d" % (
                ln["head"], ln["tree"], ln["at"], len(ln["nodes"]),
                sum(1 for v in ln["nodes"].values() if v != "passed")))
            continue
        last[(ln["row"], ln["kind"], ln["id"])] = ln
    for key in sorted(last, key=lambda k: (rows_mod.ORDER.get(k[0], 999), k[1], k[2])):
        ln = last[key]
        print("%s\t%s\t%s\t%s\t%s" % (ln["row"], ln["kind"], ln["id"], ln["verdict"],
                                      json.dumps(ln.get("detail"))[:160]))
    return 0


# -- The generated sweep (A7-R5-A1 (2)(a)) ---------------------------------------
#
# Every place in this lane's four test files that searches, counts, matches,
# compares or slices a statement's RAW TEXT, found by the operation and not by
# the names of the readers known today. Static taint over the files' ASTs:
#   SOURCES (statement text): the third positional parameter of a function
#     with the cursor-execute event signature (six positional parameters
#     after an optional self) or passed to event.listen; NAME read as an
#     attribute where main.py's module-level NAME is SQL text (main.X,
#     pre.X or any alias: by the constant's name; test_the_only_raw_sql_
#     reader_is_the_scanner checks every main.X against the imported module);
#     getattr(x, 'NAME') likewise; cf_pg.read_*() and an open() or Path() of a
#     .sql file; inspect.getsource() and co_consts (a product function's
#     constants); and the scanner's text renderers sql_tokens, sql_code and
#     sql_split_top.
#   PROPAGATION: assignment and unpacking, augmented assignment, for and
#     comprehension targets, with-as, the walrus, container mutators
#     (append, extend, add, insert, update, setdefault, ...), arguments into
#     the parameters of any function of the four files with that name,
#     returns and lambdas, self.attr stores (by attribute name), subscripts,
#     attribute reads (all but AST navigation names), every other call with a
#     tainted argument or receiver (zip, list, sorted, str methods, ...),
#     operators, f-strings and containers. A call that hands text to the
#     database (execute, fetch, fetchval, fetchrow, scalar) returns the
#     database's answer, and a token-model call (code_tokens, statements,
#     shape, mentions, insert_parts, find_all, ...) returns tokens: neither
#     result is statement text.
#   SINKS (operations): every comparison (in, not in, ==, !=, is, <, ...)
#     with a tainted side; every str search, count, split, partition,
#     replace, case, strip, translate or encode method on a tainted receiver;
#     every re.* call and every compiled-pattern match, search, findall,
#     finditer, sub or split with a tainted argument; every slice of a
#     tainted value.
# EXPECTED: cf_asm.py's scanner region (SWEEP_REGION's two markers) and the
# scanner's own probe tests (SWEEP_PROBES). Everything else is a finding.

SWEEP_FILES = ("cf_asm.py", "test_ffa_assembly_pg.py", "cf_controls_rows.py", "cf_controls.py")
SWEEP_REGION = ("# -- The one SQL lexer", "# -- end of the scanner region")
SWEEP_PROBES = ("test_sql_code_strips_comments_and_keeps_literals", "test_sql_scanner_classes")
_SW_TEXT_API = {"sql_tokens", "sql_code", "sql_split_top"}
_SW_TOKEN_API = {"code_tokens", "statements", "shape", "mentions", "insert_parts", "find_all",
                 "split_depth0", "name_of", "_model", "_words", "_paren_end"}
_SW_EXECUTE = {"execute", "exec_driver_sql", "executemany", "fetch", "fetchrow", "fetchval",
               "scalar", "scalars"}
_SW_NO_TAINT = {"isinstance", "issubclass", "type", "id", "bool", "callable", "hasattr", "print"}
_SW_NAV = {"func", "id", "attr", "ctx", "lineno", "col_offset", "end_lineno", "end_col_offset",
           "arg", "name", "asname", "module", "level",
           "__name__", "__qualname__", "__module__", "__class__"}
_SW_MUTATORS = {"append", "extend", "add", "insert", "update", "setdefault", "appendleft",
                "extendleft", "put", "put_nowait"}
_SW_STR = {"find", "rfind", "index", "rindex", "count", "startswith", "endswith", "split", "rsplit",
           "partition", "rpartition", "replace", "lower", "upper", "casefold", "swapcase", "title",
           "capitalize", "strip", "lstrip", "rstrip", "splitlines", "translate", "encode",
           "removeprefix", "removesuffix", "expandtabs", "isdigit", "isalpha", "isalnum",
           "isspace", "isupper", "islower", "isidentifier", "format"}
_SW_RE = {"match", "fullmatch", "search", "findall", "finditer", "sub", "subn", "split", "compile"}
_SW_SQL_WORD = re.compile(r"(?i)\b(select|insert|update|delete|from|where|join|values|returning|"
                          r"interval|alter\s+table|create\s+table)\b")
_SW_SCOPES = None


def _sw_sql_text(v):
    """Whether a main.py constant is SQL text: a string holding an SQL word."""
    return isinstance(v, str) and bool(_SW_SQL_WORD.search(v))


def _sw_const(node):
    import ast
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _sw_const(node.left), _sw_const(node.right)
        return a + b if a is not None and b is not None else None
    if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "text" \
            and node.args:
        return _sw_const(node.args[0])
    return None


def sweep_main_sources(main_path=None):
    """main.py's module-level names whose value is SQL text (AST-evaluated)."""
    import ast
    main_path = main_path or os.path.join(ROOT, "backend", "api", "main.py")
    tree = ast.parse(open(main_path, encoding="utf-8").read())
    out = set()
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else \
            [node.target] if isinstance(node, ast.AnnAssign) and node.value is not None else []
        if not targets:
            continue
        v = _sw_const(node.value)
        if v is not None and _sw_sql_text(v):
            out.update(t.id for t in targets if isinstance(t, ast.Name))
    return out


_SQL, _PY, _PYAST = 1, 2, 4      # taint labels: statement text; Python source; its parsed tree


def _sw_flat(v):
    return v if isinstance(v, int) else _sw_or(_sw_flat(x) for x in v[1])


def _sw_or(xs):
    m = 0
    for x in xs:
        m |= x
    return m


def _sw_join(a, b):
    if isinstance(a, int) and isinstance(b, int):
        return a | b
    if not isinstance(a, int) and not isinstance(b, int) and len(a[1]) == len(b[1]):
        return ("tup", tuple(_sw_join(x, y) for x, y in zip(a[1], b[1])))
    if a == 0:
        return b
    if b == 0:
        return a
    return _sw_flat(a) | _sw_flat(b)


class _Sweep:
    """Flow-insensitive taint over the four files, with Python's scoping for
    names, tuple shapes for unpacking (a, b = f() and for a, b in zip(x, y)
    keep each element's taint) and three labels: SQL statement text, Python
    source (inspect.getsource) and its parsed tree, whose string constants
    (an ast Constant's .value) are SQL text again. A sink counts when its
    operand carries the SQL label; one over Python source only is listed
    apart (it reads product code, not a statement)."""

    def __init__(self, files, sources):
        import ast
        self.ast = ast
        self.sources = sources
        self.trees, self.lines = {}, {}
        for path in files:
            text = open(path, encoding="utf-8").read()
            self.trees[path] = ast.parse(text)
            self.lines[path] = text.splitlines()
        self.chain, self.owner, self.locals = {}, {}, {}
        self.defs, self.defs_at, self.mod_defs, self.methods, self.cls_of = {}, {}, {}, {}, {}
        self.values, self.modules, self.re_names = set(), {}, {"re"}
        self.nodes = []
        for path, tree in self.trees.items():
            self._walk(path, tree, (tree,), None)
        self.tv, self.tattr, self.tparam, self.tret = {}, {}, {}, {}

    # scopes ------------------------------------------------------------------
    def _scope_locals(self, scope):
        ast = self.ast
        names = set()
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = scope.args
            for p in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg]:
                if p is not None:
                    names.add(p.arg)
            body = scope.body if isinstance(scope.body, list) else [scope.body]
        elif isinstance(scope, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for g in scope.generators:
                for n in ast.walk(g.target):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
            return names
        else:
            body = scope.body
        glob = set()
        stack = list(body)
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(n.name)
                stack.extend(n.decorator_list)
                continue
            if isinstance(n, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                continue
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                names.add(n.id)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for al in n.names:
                    names.add((al.asname or al.name).split(".")[0])
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                glob.update(n.names)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                names.add(n.name)
            stack.extend(ast.iter_child_nodes(n))
        return names - glob

    def _walk(self, path, node, chain, fn):
        ast = self.ast
        self.chain[id(node)] = chain
        self.owner[id(node)] = (path, fn)
        self.nodes.append((path, node))
        if isinstance(node, ast.Import):
            for al in node.names:
                if al.name == "re":
                    self.re_names.add(al.asname or "re")
                if al.name + ".py" in SWEEP_FILES:
                    self.modules[al.asname or al.name] = al.name + ".py"
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.defs.setdefault(node.name, []).append(node)
            scope = chain[-1]
            self.defs_at[(id(scope), node.name)] = node
            if isinstance(scope, ast.Module):
                self.mod_defs[(os.path.basename(path), node.name)] = node
            if isinstance(scope, ast.ClassDef):
                self.methods.setdefault(node.name, []).append(node)
                self.cls_of[id(node)] = id(scope)
        if isinstance(node, ast.Call):
            for a in list(node.args) + [k.value for k in node.keywords]:
                if isinstance(a, ast.Name):
                    self.values.add(a.id)
                elif isinstance(a, ast.Attribute):
                    self.values.add(a.attr)
        new = isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                                ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.ClassDef))
        if new and id(node) not in self.locals:
            self.locals[id(node)] = self._scope_locals(node)
        inner = chain + (node,) if new and not isinstance(node, ast.Module) else chain
        infn = node if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) else fn
        for child in ast.iter_child_nodes(node):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                    (child in node.decorator_list or child is node.returns):
                self._walk(path, child, chain, fn)
            else:
                self._walk(path, child, inner, infn)

    def key(self, node, name):
        ast = self.ast
        chain = self.chain[id(node)]
        for i in range(len(chain) - 1, -1, -1):
            sc = chain[i]
            if isinstance(sc, ast.ClassDef) and i != len(chain) - 1:
                continue
            if name in self.locals.get(id(sc), ()):
                return (id(sc), name)
        return (id(chain[0]), name)

    def callees(self, call, at=None):
        """The functions of the four files a call can reach: a bare name by
        Python's scoping (the nearest enclosing def of that name, else a
        module-level def of any of the files); mod.f by the module's file;
        self.f by the enclosing class; obj.f by every method named f."""
        ast = self.ast
        f = call.func
        here = self.chain[id(at if at is not None else call)]
        if isinstance(f, ast.Name):
            for sc in reversed(here):
                d = self.defs_at.get((id(sc), f.id))
                if d is not None:
                    return [d]
            return [d for (_b, n), d in self.mod_defs.items() if n == f.id]
        if isinstance(f, ast.Attribute):
            if isinstance(f.value, ast.Name) and f.value.id in self.modules:
                d = self.mod_defs.get((self.modules[f.value.id], f.attr))
                return [d] if d is not None else []
            if isinstance(f.value, ast.Name) and f.value.id in ("self", "cls"):
                own = [sc for sc in here if isinstance(sc, ast.ClassDef)]
                if own:
                    hit = [d for d in self.methods.get(f.attr, []) if self.cls_of[id(d)] == id(own[-1])]
                    if hit:
                        return hit
            return list(self.methods.get(f.attr, []))
        return []

    def fname(self, call):
        f = call.func
        return f.id if isinstance(f, self.ast.Name) else f.attr if isinstance(f, self.ast.Attribute) else None

    def has_sql_file(self, node):
        ast = self.ast
        return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith(".sql")
                   for n in ast.walk(node))

    # taint ---------------------------------------------------------------------
    def T(self, e):
        return _sw_flat(self.S(e))

    def S(self, e):
        """The taint shape of an expression: a label mask, or ("tup", parts)."""
        ast = self.ast
        if e is None:
            return 0
        if isinstance(e, ast.Name):
            return self.tv.get(self.key(e, e.id), 0)
        if isinstance(e, ast.Tuple):
            return ("tup", tuple(self.S(x) for x in e.elts)) if e.elts else 0
        if isinstance(e, ast.Await):
            return self.S(e.value)
        if isinstance(e, ast.Call):
            return self.Scall(e)
        if isinstance(e, ast.Attribute):
            if e.attr in self.sources or e.attr == "co_consts":
                return _SQL
            m = self.tattr.get(e.attr, 0)
            if e.attr in _SW_NAV:
                return m
            base = self.T(e.value)
            if base & _PYAST and e.attr in ("value", "s"):
                base |= _SQL
            return m | base
        if isinstance(e, ast.Subscript):
            v = self.S(e.value)
            if not isinstance(v, int) and isinstance(e.slice, ast.Constant) \
                    and isinstance(e.slice.value, int) and -len(v[1]) <= e.slice.value < len(v[1]):
                return v[1][e.slice.value]
            return _sw_flat(v)
        if isinstance(e, ast.BinOp):
            return self.T(e.left) | self.T(e.right)
        if isinstance(e, ast.BoolOp):
            return _sw_or(self.T(v) for v in e.values)
        if isinstance(e, ast.IfExp):
            return _sw_join(self.S(e.body), self.S(e.orelse))
        if isinstance(e, (ast.List, ast.Set)):
            return _sw_or(self.T(v) for v in e.elts)
        if isinstance(e, ast.Dict):
            return _sw_or(self.T(v) for v in list(e.keys) + list(e.values) if v is not None)
        if isinstance(e, ast.JoinedStr):
            return _sw_or(self.T(v) for v in e.values)
        if isinstance(e, (ast.FormattedValue, ast.Starred, ast.NamedExpr)):
            return self.T(e.value)
        if isinstance(e, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return self.T(e.elt)
        if isinstance(e, ast.DictComp):
            return self.T(e.key) | self.T(e.value)
        if isinstance(e, ast.UnaryOp):
            return 0 if isinstance(e.op, ast.Not) else self.T(e.operand)
        return 0

    def Scall(self, e):
        ast = self.ast
        name = self.fname(e)
        args = list(e.args) + [k.value for k in e.keywords]
        if name in _SW_NO_TAINT:
            return 0
        if name in _SW_TEXT_API:
            return _SQL
        if name == "getsource":
            return _PY
        if name == "parse" and any(self.T(a) & _PY for a in args):
            return _PYAST
        if name == "dump" and any(self.T(a) & _PYAST for a in args):
            return _PYAST                         # ast.dump: a tree's structure
        if name in _SW_TOKEN_API or name in _SW_EXECUTE:
            return 0
        if name == "getattr" and len(e.args) >= 2 and isinstance(e.args[1], ast.Constant) \
                and e.args[1].value in self.sources:
            return _SQL
        f = e.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "cf_pg" \
                and f.attr.startswith("read_"):
            return _SQL
        if name in ("open", "Path", "read_text") and self.has_sql_file(e):
            return _SQL
        targets = self.callees(e)
        if targets:
            out = 0
            for d in targets:
                out = _sw_join(out, self.tret.get(id(d), 0))
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                    and f.value.id not in self.modules:
                out = _sw_join(out, self.T(f.value))
            return out
        m = _sw_or(self.T(a) for a in args)
        if isinstance(f, ast.Attribute):
            m |= self.T(f.value)
        return m

    def elem(self, it):
        """The shape of one element of iterating `it`."""
        ast = self.ast
        if isinstance(it, ast.Call):
            name = self.fname(it)
            if name == "zip" and isinstance(it.func, ast.Name):
                return ("tup", tuple(self.T(a) for a in it.args))
            if name == "enumerate" and isinstance(it.func, ast.Name) and it.args:
                return ("tup", (0, self.T(it.args[0])))
        return self.T(it)

    def mark(self, t, val):
        ast = self.ast
        if val == 0:
            return False
        if isinstance(t, ast.Name):
            k = self.key(t, t.id)
            old = self.tv.get(k, 0)
            new = _sw_join(old, val)
            if new == old:
                return False
            self.tv[k] = new
            return True
        if isinstance(t, (ast.Tuple, ast.List)):
            if not isinstance(val, int) and len(val[1]) == len(t.elts) \
                    and not any(isinstance(x, ast.Starred) for x in t.elts):
                return any([self.mark(x, v) for x, v in zip(t.elts, val[1])])
            return any([self.mark(x, _sw_flat(val)) for x in t.elts])
        if isinstance(t, ast.Starred):
            return self.mark(t.value, _sw_flat(val))
        if isinstance(t, ast.Attribute):
            old = self.tattr.get(t.attr, 0)
            new = old | _sw_flat(val)
            if new == old:
                return False
            self.tattr[t.attr] = new
            return True
        if isinstance(t, ast.Subscript):
            return self.mark(t.value, _sw_flat(val))
        return False

    def params(self, d, method):
        a = d.args
        ps = [p.arg for p in a.posonlyargs + a.args]
        if method and ps and ps[0] in ("self", "cls"):
            ps = ps[1:]
        return ps

    def taint_param(self, d, pname, m):
        k = (id(d), pname)
        old = self.tparam.get(k, 0)
        if m == 0 or old | m == old:
            return False
        self.tparam[k] = old | m
        return True

    def step(self):
        ast = self.ast
        ch = False
        for path, n in self.nodes:
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                if getattr(n, "value", None) is not None:
                    v = self.S(n.value)
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                        ch |= bool(self.mark(t, v))
            elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
                ch |= bool(self.mark(n.target, self.elem(n.iter)))
            elif isinstance(n, ast.withitem):
                if n.optional_vars is not None:
                    ch |= bool(self.mark(n.optional_vars, self.S(n.context_expr)))
            elif isinstance(n, ast.NamedExpr):
                ch |= bool(self.mark(n.target, self.S(n.value)))
            elif isinstance(n, (ast.Return, ast.Yield, ast.YieldFrom)):
                fn = self.owner[id(n)][1]
                if fn is not None and n.value is not None:
                    old = self.tret.get(id(fn), 0)
                    new = _sw_join(old, self.S(n.value))
                    if new != old:
                        self.tret[id(fn)] = new
                        ch = True
            elif isinstance(n, ast.Lambda):
                old = self.tret.get(id(n), 0)
                new = _sw_join(old, self.S(n.body))
                if new != old:
                    self.tret[id(n)] = new
                    ch = True
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                ps = [p.arg for p in n.args.posonlyargs + n.args.args]
                own = ps[1:] if ps and ps[0] in ("self", "cls") else ps
                hook = (len(own) == 6 and n.name in self.values) or \
                    (len(own) >= 3 and any(isinstance(dec, ast.Call) and self.fname(dec) == "listens_for"
                                           for dec in n.decorator_list))
                if hook:                          # the cursor-execute event signature
                    ch |= self.taint_param(n, own[2], _SQL)
                for p in n.args.posonlyargs + n.args.args + n.args.kwonlyargs + \
                        [x for x in (n.args.vararg, n.args.kwarg) if x is not None]:
                    m = self.tparam.get((id(n), p.arg), 0)
                    if m:
                        k = (id(n), p.arg)
                        old = self.tv.get(k, 0)
                        new = _sw_join(old, m)
                        if new != old:
                            self.tv[k] = new
                            ch = True
            elif isinstance(n, ast.Call):
                f, name = n.func, self.fname(n)
                args = list(n.args)
                kws = [k.value for k in n.keywords]
                if isinstance(f, ast.Attribute) and name in _SW_MUTATORS:
                    ch |= bool(self.mark(f.value, _sw_or(self.T(a) for a in args + kws)))
                if name == "listen" and len(args) >= 3:
                    cb = args[2]
                    if isinstance(cb, ast.Name):
                        hooks = self.callees(ast.Call(func=cb, args=[], keywords=[]), at=n)
                    elif isinstance(cb, ast.Attribute):
                        hooks = list(self.methods.get(cb.attr, []))
                    else:
                        hooks = []
                    for d in hooks:
                        ps = self.params(d, True)
                        if len(ps) >= 3:
                            ch |= self.taint_param(d, ps[2], _SQL)
                for d in self.callees(n):
                    meth = isinstance(f, ast.Attribute) and not (
                        isinstance(f.value, ast.Name) and f.value.id in self.modules)
                    ps = self.params(d, meth)
                    kwo = [x.arg for x in d.args.kwonlyargs]
                    for i, a in enumerate(args):
                        if isinstance(a, ast.Starred):
                            m = self.T(a.value)
                            for p in ps[i:]:
                                ch |= self.taint_param(d, p, m)
                            if d.args.vararg is not None:
                                ch |= self.taint_param(d, d.args.vararg.arg, m)
                            continue
                        m = self.T(a)
                        if i < len(ps):
                            ch |= self.taint_param(d, ps[i], m)
                        elif d.args.vararg is not None:
                            ch |= self.taint_param(d, d.args.vararg.arg, m)
                    for k in n.keywords:
                        m = self.T(k.value)
                        if k.arg is None:
                            for p in ps + kwo:
                                ch |= self.taint_param(d, p, m)
                        elif k.arg in ps or k.arg in kwo:
                            ch |= self.taint_param(d, k.arg, m)
                        elif d.args.kwarg is not None:
                            ch |= self.taint_param(d, d.args.kwarg.arg, m)
        return ch

    def sinks(self):
        ast = self.ast
        out = []
        for path, n in self.nodes:
            op, m = None, 0
            if isinstance(n, ast.Compare):
                sides = [n.left] + list(n.comparators)
                for i, o in enumerate(n.ops):
                    if isinstance(o, (ast.Is, ast.IsNot)):
                        continue                  # identity: never the text
                    m = self.T(sides[i]) | self.T(sides[i + 1])
                    if m:
                        op = "compare " + type(o).__name__
                        break
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                f = n.func
                args = list(n.args) + [k.value for k in n.keywords]
                am = _sw_or(self.T(a) for a in args)
                if f.attr in _SW_STR and self.T(f.value):
                    op, m = "str ." + f.attr, self.T(f.value)
                elif isinstance(f.value, ast.Name) and f.value.id in self.re_names \
                        and f.attr in _SW_RE and am:
                    op, m = "re." + f.attr, am
                elif f.attr in _SW_RE and am:
                    op, m = "pattern ." + f.attr, am
                elif isinstance(f.value, ast.Name) and f.value.id == "str" and f.attr in _SW_STR and am:
                    op, m = "str." + f.attr, am
            elif isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice) and self.T(n.value):
                op, m = "slice", self.T(n.value)
            if op is None:
                continue
            fn = self.owner[id(n)][1]
            top = None
            for sc in self.chain[id(n)]:
                if isinstance(sc, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    top = sc.name
                    break
            out.append({"file": os.path.basename(path), "line": n.lineno, "op": op,
                        "subject": "sql" if m & _SQL else "python source",
                        "where": top or "<module>",
                        "inner": getattr(fn, "name", "<lambda>") if fn is not None else "<module>"})
        return out


def raw_sql_sweep(files=None, main_path=None):
    """The generated sweep: (findings, main names read, main SQL sources).
    Each finding is {file, line, op, subject, where, inner, expected}; a
    finding over Python source only (subject "python source") reads product
    code, not a statement, and is listed, never expected or refused."""
    import ast
    files = files or [os.path.join(HERE, f) for f in SWEEP_FILES]
    sources = sweep_main_sources(main_path)
    sw = _Sweep(files, sources)
    for _ in range(60):
        if not sw.step():
            break
    else:
        raise RuntimeError("sweep did not reach a fixpoint")
    region = None
    for path in files:
        if os.path.basename(path) == "cf_asm.py":
            lines = sw.lines[path]
            a = [i + 1 for i, ln in enumerate(lines) if ln.startswith(SWEEP_REGION[0])]
            b = [i + 1 for i, ln in enumerate(lines) if ln.startswith(SWEEP_REGION[1])]
            assert len(a) == 1 and len(b) == 1 and a[0] < b[0], ("sweep region markers", a, b)
            region = (a[0], b[0])
    found = sw.sinks()
    for f in found:
        f["expected"] = bool((f["file"] == "cf_asm.py" and region and region[0] <= f["line"] <= region[1])
                             or (f["file"] == "test_ffa_assembly_pg.py" and f["where"] in SWEEP_PROBES))
    names = set()
    for path, tree in sw.trees.items():
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "main":
                names.add(n.attr)
    return found, sorted(names), sources


def sweep_line(f):
    return "%s:%d %s [%s]%s" % (f["file"], f["line"], f["where"], f["op"],
                                "" if f["inner"] == f["where"] else " in " + f["inner"])


def cmd_sweep(args):
    found, names, sources = raw_sql_sweep()
    sql = [f for f in found if f["subject"] == "sql"]
    py = [f for f in found if f["subject"] != "sql"]
    print("# raw SQL text sweep (A7-R5-A1 (2)(a)): %d SQL site(s); main.py SQL constants taken as "
          "sources: %d; main.X names read: %d" % (len(sql), len(sources), len(names)))
    for f in sorted(sql, key=lambda x: (x["file"], x["line"])):
        print("%s\t%s" % ("EXPECTED" if f["expected"] else "OUTSIDE ", sweep_line(f)))
    outside = [f for f in sql if not f["expected"]]
    print("# outside the scanner region and its probe tests: %d" % len(outside))
    print("# readers of product PYTHON source (inspect.getsource; not statement text): %d" % len(py))
    for f in sorted(py, key=lambda x: (x["file"], x["line"])):
        print("PYSRC\t%s" % sweep_line(f))
    return 1 if outside else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("check", "baseline", "run", "table", "sweep"))
    ap.add_argument("--db", default="cf_lane_w1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--rows", default=None)
    ap.add_argument("--only", choices=("mutants", "twins", "classes"), default=None)
    ap.add_argument("--compile", action="store_true",
                    help="check: also compile every edited .py file (a process pool)")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.cmd not in ("check", "sweep") and not args.out:
        raise SystemExit("--out is required")
    return {"check": cmd_check, "baseline": cmd_baseline, "run": cmd_run,
            "table": cmd_table, "sweep": cmd_sweep}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
