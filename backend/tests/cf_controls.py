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
(CF_TRACE_DIR) must equal the baseline's byte for byte.

Every mutant and twin is a list of exact text replacements applied to a
scratch copy of the tree. Each replacement asserts how many times its old
text occurs before it applies, so a stale entry fails as STALE instead of
running an unmutated copy.

Usage (absolute paths; one lane database per concurrent run):
  python cf_controls.py check
  python cf_controls.py baseline --db cf_lane_w1 --out DIR [--rows S1,S2]
  python cf_controls.py run --db cf_lane_w2 --out DIR [--rows S1,S2] [--only mutants|twins]
  python cf_controls.py table --out DIR
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
COPY = ("backend/api", "backend/sql", "backend/tests")
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
            for m in r["mutants"] + ([r["twin"]] if r["twin"] else []):
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
    total = sum(len(r["mutants"]) + (1 if r["twin"] else 0) for r in selected(args.rows))
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("check", "baseline", "run", "table"))
    ap.add_argument("--db", default="cf_lane_w1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--rows", default=None)
    ap.add_argument("--only", choices=("mutants", "twins"), default=None)
    ap.add_argument("--compile", action="store_true",
                    help="check: also compile every edited .py file (a process pool)")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.cmd != "check" and not args.out:
        raise SystemExit("--out is required")
    return {"check": cmd_check, "baseline": cmd_baseline, "run": cmd_run,
            "table": cmd_table}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
