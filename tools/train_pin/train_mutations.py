"""Mutation controls for the release train: a reddening mutant AND an inert twin for every control.

Path-free. The train, the tests and the validator are found from this file's
own place in the repository; where the evidence goes is named on the command
line. Nothing here names a machine, a seat or a directory outside the tree.

1.  Every control in `train_controls.py` -- rounds 2 to 12 -- is executed at the
    tip this runs at. A closure certified on an earlier pin is not evidence on
    this one.
2.  Every control has an INERT TWIN: the same site, edited, with nothing
    removed (#391). The mutant must turn the named test RED; the twin must
    leave it GREEN.
3.  The train is copied aside before the first arm and restored FROM THAT COPY
    after every arm, its sha256 re-checked each time (never `git checkout --` /
    `git restore`, #290/#401 -- and the train is untracked anyway).
4.  The evidence is RENDERED against the schema `train_pin_schema.py` checks,
    never pasted: the TESTS document (each test's node id and outcome) and the
    MUTATIONS document (per arm: id, kind, expected, observed, restore and the
    exception TYPE; a message only when every token of it is in the synthetic
    vocabulary the tests module exports, else WITHHELD with its token count).
    Both are validated before they are written, and nothing is written when
    either is refused.

    python tools/train_pin/train_mutations.py --anchors
    python tools/train_pin/train_mutations.py --out DIR --logs DIR [--log-prefix P]
                                              [--base REV] [CONTROL_ID ...]

`--out` receives the aside copy, the junit file and the two staged documents;
`--logs` the raw run logs. With control ids, only those run and nothing is
staged.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TRAIN = ROOT / "scripts" / "deploy" / "release_train.py"
TESTS_REL = "backend/tests/test_pc_steam_server.py"
TESTS = ROOT / TESTS_REL
TESTDIR = TESTS.parent
TESTS_NODE_PREFIX = TESTS_REL + "::"
BATCH = "BUG392_MERGE"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V = _load("train_pin_schema_for_mutations", HERE / "train_pin_schema.py")
C = _load("train_controls_for_mutations", HERE / "train_controls.py")


def controls():
    return list(C.CONTROLS)


def schema_id(cid):
    """`R10-M1a` -> `R10_M1A`: the control id as the validator's CONTROL type spells it."""
    return cid.replace("-", "_").upper()


# --------------------------------------------------------------------------
# The inert twin: the SAME site, edited, with nothing removed.

TWIN_NOTE = "# twin: an edit at this site that removes nothing."


def twin_source(src, old):
    i = src.index(old)
    start = src.rfind("\n", 0, i) + 1
    if not src[start:i].strip():
        indent = re.match(r"[ \t]*", src[start:]).group(0)
        return src[:start] + indent + TWIN_NOTE + "\n" + src[start:]
    after = src.index("\n", i + len(old)) + 1
    indent = re.match(r"[ \t]*", src[after:]).group(0)
    return src[:after] + indent + TWIN_NOTE + "\n" + src[after:]


def sha256(path):
    with io.open(str(path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


_FAILED = re.compile(r"^FAILED\s+\S+::(\S+)\s+-\s+([A-Za-z_][\w.]*):?\s*(.*)$")
_E_LINE = re.compile(r"^E\s+([A-Za-z_][\w.]*)(?::\s*(.*))?$")
_COUNTS = re.compile(r"\d+ (?:passed|failed|error)")


def _pytest(args, cwd):
    # --no-header and --disable-warnings: the header names the root directory
    # and the warnings summary names installed packages by absolute path, and
    # neither is evidence about the train.
    return subprocess.run([sys.executable, "-m", "pytest"] + args
                          + ["--no-header", "--disable-warnings", "-p", "no:cacheprovider"],
                          cwd=str(cwd), capture_output=True, text=True)


def run_test(name):
    """(rc, the summary line, the exception type, the message) for one test."""
    p = _pytest([TESTS_REL, "-q", "-k", name, "--tb=line", "-rf", "--rootdir", str(ROOT)],
                ROOT)
    lines = [l.rstrip() for l in (p.stdout + p.stderr).splitlines()]
    summary = next((l for l in reversed(lines) if _COUNTS.search(l)), "").strip()
    kind, message = "NONE", ""
    for line in lines:
        m = _FAILED.match(line.strip())
        if m:
            kind, message = m.group(2), m.group(3)
            break
    if kind == "NONE":
        for line in lines:
            m = _E_LINE.match(line.rstrip())
            if m:
                kind, message = m.group(1), m.group(2) or ""
                break
    if p.returncode != 0 and kind == "NONE":
        kind = "UNPARSED"
    return p.returncode, summary, kind, message


def exception_type(kind):
    """The TYPE name, from a closed list, or UNPARSED -- never a dotted path."""
    name = (kind or "NONE").rsplit(".", 1)[-1]
    return name if name in V.EXCEPTIONS else "UNPARSED"


# --------------------------------------------------------------------------
# The synthetic vocabulary, read from the tests module's own export.

_NUM = re.compile(r"\A[+-]?[0-9]+\Z")
_STRIP = "\"'`.,:;!?()[]{}<>="
VOCAB = None


def exported_vocabulary():
    """The tests module's SYNTHETIC_VOCABULARY, by importing the module itself."""
    code = ("import sys, json; sys.path.insert(0, %r); import test_pc_steam_server as t; "
            "print(json.dumps(sorted(t.SYNTHETIC_VOCABULARY)))" % str(TESTDIR))
    p = subprocess.run([sys.executable, "-c", code], cwd=str(TESTDIR), capture_output=True,
                       text=True)
    if p.returncode != 0:
        raise SystemExit("the tests module could not be imported to read its vocabulary "
                         "export (rc=%d)" % p.returncode)
    return frozenset(json.loads(p.stdout.strip().splitlines()[-1]))


def message_tokens(message):
    """(INCLUDED / WITHHELD / NONE, the token count, [typed tokens] when INCLUDED)."""
    global VOCAB
    if VOCAB is None:
        VOCAB = exported_vocabulary()
    tokens = [t.strip(_STRIP) for t in (message or "").split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return "NONE", 0, []
    typed = []
    for t in tokens:
        if _NUM.match(t):
            typed.append(int(t))
        elif t in VOCAB or t in V.WORDS or t in V.SANCTIONED:
            typed.append(t)
        else:
            return "WITHHELD", len(tokens), []
    return "INCLUDED", len(tokens), typed


def vocabulary_self_test():
    """(control, twin): a message with one token outside the vocabulary (want WITHHELD),
    and the same message wholly inside it (want INCLUDED)."""
    inside = "MISSING 3 PRIMARY a-machine"
    outside = "MISSING 3 PRIMARY a-machine somewhere"
    return message_tokens(outside)[0], message_tokens(inside)[0]


# --------------------------------------------------------------------------
# The schema agreement: the train's tables and the validator's copy, compared
# in a separate process (importing the train installs its own hooks).

AGREE = r'''
import importlib.util, json, sys
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.argv = [path]
    spec.loader.exec_module(mod)
    return mod
rt = load("rt_agree", %(train)r)
v = load("v_agree", %(validator)r)
problems = []
if rt.SUMMARY_SCHEMA != v.SCHEMA or rt.SUMMARY_VERSION != v.VERSION:
    problems.append("schema name or version")
if tuple(rt.SUMMARY_ARTIFACTS) != tuple(v.TRAIN_ARTIFACTS):
    problems.append("artifacts")
if {k: tuple(t) for k, t in rt.SUMMARY_HEAD.items()} != {k: tuple(t) for k, t in v.TRAIN_HEAD.items()}:
    problems.append("head")
for a in rt.SUMMARY_ARTIFACTS:
    if {k: tuple(t) for k, t in rt.SUMMARY_SINGLES[a].items()} != {k: tuple(t) for k, t in v.SINGLES[a].items()}:
        problems.append("singles " + a)
    mine = {k: {kk: tuple(tt) for kk, tt in spec.items()} for k, (_s, spec) in rt.SUMMARY_ROWS[a].items()}
    theirs = {k: {kk: tuple(tt) for kk, tt in spec.items()} for k, spec in v.ROWS[a].items()}
    if mine != theirs:
        problems.append("rows " + a)
if set(rt.summary_words()) != set(v.FIXED_WORDS | v.PHASE_WORDS | v.BATCH_WORDS | {v.SCHEMA}):
    problems.append("words")
if set(rt.summary_sanctioned()) - set(v.SANCTIONED):
    problems.append("sanctioned")
if rt.UNRECORDED != v.UNRECORDED:
    problems.append("unrecorded")
print(json.dumps({"verdict": "MISMATCH" if problems else "MATCH", "problems": problems}))
'''


def schema_agreement():
    p = subprocess.run([sys.executable, "-c", AGREE % {"train": str(TRAIN),
                                                       "validator": str(HERE / "train_pin_schema.py")}],
                       capture_output=True, text=True)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"verdict": "MISMATCH", "problems": ["the comparison did not run (rc=%d)"
                                                     % p.returncode]}


# --------------------------------------------------------------------------

def git(*args):
    """Every git read here with replacement objects OFF, as the train reads (R10-H3)."""
    p = subprocess.run(["git", "--no-replace-objects", "-C", str(ROOT)] + list(args),
                       capture_output=True, text=True,
                       env=dict(os.environ, GIT_NO_REPLACE_OBJECTS="1"))
    if p.returncode != 0:
        raise SystemExit("git %s failed (rc=%d)" % (args[0], p.returncode))
    return p.stdout.strip()


def head_doc(artifact, tip, base):
    return {"schema": V.SCHEMA, "version": V.VERSION, "artifact": artifact,
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "batch": BATCH, "base": base, "tests_tip": tip}


def run_whole_file(tip, base, junit, tests_log):
    """The whole tests file once: the raw log written, the TESTS document returned."""
    if os.path.exists(junit):
        os.remove(junit)
    p = _pytest([TESTS_REL, "-q", "-rA", "--rootdir", str(ROOT), "--junitxml", str(junit)],
                ROOT)
    io.open(tests_log, "w", encoding="utf-8", newline="").write(
        "$ python -m pytest %s -q -rA --no-header --disable-warnings (rootdir = the "
        "worktree), at %s\n\n%s%s\nexit=%d\n" % (TESTS_REL, tip, p.stdout, p.stderr,
                                                 p.returncode))
    root = ET.parse(str(junit)).getroot()
    rows, counts = [], {"PASSED": 0, "FAILED": 0, "ERROR": 0, "SKIPPED": 0}
    for case in root.iter("testcase"):
        cls = case.get("classname") or ""
        if not cls.endswith("test_pc_steam_server"):
            raise SystemExit("a test case from another module: the TESTS document covers "
                             "one file")
        outcome = "PASSED"
        if case.find("failure") is not None:
            outcome = "FAILED"
        elif case.find("error") is not None:
            outcome = "ERROR"
        elif case.find("skipped") is not None:
            outcome = "SKIPPED"
        counts[outcome] += 1
        rows.append({"node": TESTS_NODE_PREFIX + case.get("name"), "outcome": outcome})
    doc = head_doc("TESTS", tip, base)
    doc.update(collected=len(rows), passed=counts["PASSED"], failed=counts["FAILED"],
               errors=counts["ERROR"], skipped=counts["SKIPPED"],
               tests=sorted(rows, key=lambda r: r["node"]))
    return doc, p.returncode


def arm(cid, kind, body, test, pristine, clean, rows, messages, out):
    """Apply one edit, run the named test, restore, record. Answers the rc."""
    sid = schema_id(cid)
    try:
        compile(body, str(TRAIN), "exec")
    except SyntaxError as e:
        out.append("=== %s %-6s DID NOT COMPILE: %s" % (cid, kind, e))
        rows.append({"id": sid, "kind": kind.upper(), "expected":
                     "RED" if kind == "mutant" else "GREEN",
                     "observed": "UNCOMPILABLE", "restore": "EQUAL",
                     "exception": "SyntaxError", "message": "NONE", "tokens": 0})
        return None
    io.open(str(TRAIN), "w", encoding="utf-8", newline="").write(body)
    try:
        rc, summary, exc, message = run_test(test)
    finally:
        shutil.copyfile(str(pristine), str(TRAIN))
    restore = "EQUAL" if sha256(TRAIN) == clean else "UNEQUAL"
    observed = "RED" if rc != 0 else "GREEN"
    verdict, count, typed = message_tokens(message)
    rows.append({"id": sid, "kind": kind.upper(),
                 "expected": "RED" if kind == "mutant" else "GREEN",
                 "observed": observed, "restore": restore,
                 "exception": exception_type(exc) if rc != 0 else "NONE",
                 "message": verdict, "tokens": count})
    for i, tok in enumerate(typed):
        messages.append({"id": sid, "kind": kind.upper(), "position": i, "token": tok})
    out.append("    %-6s : rc=%d  %s  [%s]  restore=%s  message=%s (%d token(s))"
               % (kind, rc, summary, exception_type(exc) if rc != 0 else "NONE", restore,
                  verdict, count))
    return rc


def check_anchors():
    src = io.open(str(TRAIN), encoding="utf-8", newline="").read()
    bad = 0
    for cid, _what, test, old, new in controls():
        n = src.count(old)
        ok = n == 1
        if ok:
            for body in (src.replace(old, new), twin_source(src, old)):
                try:
                    compile(body, str(TRAIN), "exec")
                except SyntaxError:
                    ok = False
        if not ok:
            bad += 1
        print("%-8s %-3s anchor x%d  %s" % (cid, "OK" if ok else "BAD", n, test))
    ids = [schema_id(c[0]) for c in controls()]
    for sid in ids:
        if not V.CONTROL.match(sid):
            bad += 1
            print("%s is not a CONTROL id the validator admits" % sid)
    if len(set(ids)) != len(ids):
        bad += 1
        print("duplicate control ids")
    print("\n%d control(s), %d problem(s)" % (len(ids), bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--anchors", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--logs")
    ap.add_argument("--log-prefix", default="train-")
    ap.add_argument("--base", default="f2f6402")
    args = ap.parse_args()
    if args.anchors:
        return check_anchors()
    if not args.out or not args.logs:
        ap.error("--out and --logs are required for a run")
    out_dir, logs = Path(args.out), Path(args.logs)
    out_dir.mkdir(parents=True, exist_ok=True)
    pristine = out_dir / "release_train.pristine.py"
    junit = out_dir / "junit-tests.xml"
    stage_tests, stage_mut = out_dir / "summary-tests.json", out_dir / "summary-mutations.json"
    mut_log = logs / (args.log_prefix + "mutations.log")
    tests_log = logs / (args.log_prefix + "tests.log")
    only = args.ids or None
    full = not only
    tip = git("rev-parse", "HEAD")
    base = git("rev-parse", args.base)
    dirty = git("status", "--porcelain", "--untracked-files=no")
    if full and dirty:
        raise SystemExit("the tracked tree is not clean: the documents would describe a tip "
                         "the tests did not run at. Commit first.")
    rows, messages, out = [], [], []
    out += [
        "MUTATION CONTROLS -- a reddening mutant AND an inert twin for every control.",
        "The mutant removes the behaviour and the named test must go RED; the twin edits",
        "the SAME site without removing anything and the same test must stay GREEN. The",
        "train is copied aside before the first arm and restored from that copy after",
        "every arm, with its sha256 re-checked (never `git checkout --`/`git restore`,",
        "#290/#401).",
        "",
        "tests tip %s over base %s" % (tip, base),
        "",
    ]
    tests_doc, tests_rc = None, None
    if full:
        tests_doc, tests_rc = run_whole_file(tip, base, junit, tests_log)
        out += ["whole tests file: %d collected, %d passed, %d failed, %d error(s), "
                "%d skipped (exit %d)" % (tests_doc["collected"], tests_doc["passed"],
                                          tests_doc["failed"], tests_doc["errors"],
                                          tests_doc["skipped"], tests_rc), ""]
    shutil.copyfile(str(TRAIN), str(pristine))
    clean = sha256(pristine)
    out += ["train as built: %d bytes, sha256 %s" % (os.path.getsize(str(TRAIN)), clean), ""]
    problems = 0
    todo = [c for c in controls() if not only or schema_id(c[0]) in only or c[0] in only]
    try:
        for n, (cid, what, test, old, new) in enumerate(todo, 1):
            src = io.open(str(pristine), encoding="utf-8", newline="").read()
            out.append("=== %s  (%d/%d)  mutation: %s" % (cid, n, len(todo), what))
            out.append("    test   : %s" % test)
            if src.count(old) != 1:
                out.append("    !!! MUTATION DID NOT APPLY: the anchor is present %d time(s)"
                           % src.count(old))
                rows.append({"id": schema_id(cid), "kind": "MUTANT", "expected": "RED",
                             "observed": "NOT_APPLIED", "restore": "EQUAL",
                             "exception": "NONE", "message": "NONE", "tokens": 0})
                problems += 1
                continue
            rc_red = arm(cid, "mutant", src.replace(old, new), test, pristine, clean, rows,
                         messages, out)
            rc_twin = arm(cid, "twin", twin_source(src, old), test, pristine, clean, rows,
                          messages, out)
            if rc_red is None or rc_twin is None or rc_red == 0 or rc_twin != 0:
                problems += 1
                out.append("    !!! this control did not behave: mutant rc=%s twin rc=%s"
                           % (rc_red, rc_twin))
            out.append("")
            sys.stderr.write("%d/%d %s\n" % (n, len(todo), cid))
            sys.stderr.flush()
    finally:
        shutil.copyfile(str(pristine), str(TRAIN))
    final = "EQUAL" if sha256(TRAIN) == clean else "UNEQUAL"
    reds = len([r for r in rows if r["kind"] == "MUTANT" and r["observed"] == "RED"])
    greens = len([r for r in rows if r["kind"] == "TWIN" and r["observed"] == "GREEN"])
    equal = len([r for r in rows if r["restore"] == "EQUAL"])
    vocab_control, vocab_twin = vocabulary_self_test()
    vocab_agree = "MATCH" if VOCAB == V.SYNTHETIC_VOCABULARY else "MISMATCH"
    agreement = schema_agreement()
    out += [
        "the vocabulary rule, over itself: a message with one token outside it -> %s "
        "(want WITHHELD); a message wholly inside it -> %s (want INCLUDED)"
        % (vocab_control, vocab_twin),
        "the vocabulary the tests module exports vs the validator's copy: %s" % vocab_agree,
        "the train's schema tables vs the validator's copy: %s %s"
        % (agreement["verdict"], ", ".join(agreement["problems"])),
        "",
        "controls: %d   arms: %d   mutant RED: %d   twin GREEN: %d   restores EQUAL: %d/%d"
        % (len(todo), len(rows), reds, greens, equal, len(rows)),
        "messages: %d INCLUDED, %d WITHHELD, %d NONE"
        % tuple(len([r for r in rows if r["message"] == w])
                for w in ("INCLUDED", "WITHHELD", "NONE")),
        "final restore to the train as built: %s" % final,
        "controls with a problem: %d" % problems,
    ]
    if vocab_control != "WITHHELD" or vocab_twin != "INCLUDED" or vocab_agree != "MATCH" \
            or agreement["verdict"] != "MATCH":
        problems += 1
    if full:
        doc = head_doc("MUTATIONS", tip, base)
        doc.update(control_count=len(todo), arms=len(rows), mutant_red=reds, twin_green=greens,
                   restores_equal=equal, problems=problems, final_restore=final,
                   vocabulary_control=vocab_control, vocabulary_twin=vocab_twin,
                   vocabulary_agreement=vocab_agree, schema_agreement=agreement["verdict"],
                   controls=rows, messages=messages)
        refused = []
        for d in (tests_doc, doc):
            refused += ["%s: %s" % (d["artifact"], p) for p in V.document_problems(d)]
        if refused:
            out += ["", "REFUSED: the validator refuses the rendered documents; nothing "
                        "is staged:"] + ["    " + r for r in refused]
            problems += 1
        else:
            for path, d in ((stage_tests, tests_doc), (stage_mut, doc)):
                io.open(str(path), "w", encoding="utf-8", newline="\n").write(
                    json.dumps(d, indent=1, sort_keys=True) + "\n")
            out += ["", "staged: summary-tests.json and summary-mutations.json, both "
                        "validated by the schema before they were written"]
        io.open(str(mut_log), "w", encoding="utf-8", newline="").write("\n".join(out) + "\n")
    print("\n".join(out))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
