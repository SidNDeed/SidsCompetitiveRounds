#!/usr/bin/env python3
"""Assemble the release-train lane's review pin, and classify every file in it.

Committed with the lane and path-free: every location it reads or writes is an
argument, and it writes nothing into the repository. It is the producer the pin's
provenance manifest names for every GENERATED file.

    python tools/train_pin/assemble_pin.py build --out PIN --round N --tip REV
        --round-base REV --merge-base REV --main REV --prior-pin DIR --docs DIR
        --harness DIR --harness-first DIR --review-log FILE --scratch DIR
        --wrapper FILE --live-logs DIR --live-prefix P [--historical REV ...] [--sidecar FILE]
    python tools/train_pin/assemble_pin.py notes --out PIN --round N --docs DIR
        [--sidecar FILE]

`build` writes, and classifies in provenance.json:
  TRACKED-COPY  every tool of tools/train_pin/ and the tests file, byte-equal to
                their blobs at --tip (the census re-reads the blob and compares), and
                (R11-L1, round 12) the snapshot wrapper's GATED copy tracked beside the
                tools: --wrapper names its repository copy, and the build refuses unless
                the gate of that copy (train_pin_needles.wrapper_gate) is the tracked
                blob byte for byte -- which the census proves again;
  GENERATED     the tests patches, the commit lists, the tests file's blob ids across
                the landing range (R11: where each blob the object census names came
                from), the numstat, the tracked-file listing (`git ls-tree -r` of
                the pin commit), the ignore proof (the pin commit's own .gitignore
                blobs, asked in an empty scratch repository) and, per --historical
                commit, which remote-tracking refs contain it, each described by what
                it holds (R11-L6: the merge base is the POSITIVE control, nonempty, and
                an empty answer there refuses): each the exact output of a read-only recipe over the pin
                commit's objects (or, for the two ref-state recipes, over the refs
                that exist), recorded in the manifest, which the census re-runs and
                compares byte for byte (R10-H4, R10-L3);
  TYPED         the gitignored train and its diffs, the prior pin's history, the
                documents, the six summaries, the FIRST harness run's two summaries
                (R11: the bar runs the harness twice back to back; --harness names
                the second run, --harness-first the first, and assembly.log compares
                the two control by control and lists the controls retired and added
                since the prior pin's run), the live runs' logs (R10-L2) and the logs.
                (Round 11's typed excerpt of the snapshot wrapper is gone: R11-L1.)
Every git read goes through train_pin_needles' door, replacement objects off
(R10-H3). Every file of every class is needle-scanned before it is written, and the
census reads every one of them again, needles and shapes alike (R10-H1).
Every summary is validated by train_pin_schema.py and every rendered field of it is
needle-scanned (A4) BEFORE it is written; one finding and nothing is written.
A document written by a person or an agent is copied with every known needle it
holds replaced by a neutral token; assembly.log records the count per file and per
token, never a value, and the census re-reads the result. `build` then runs every
tool's own controls into tools-self-test.log.

`notes` copies the round's notes into an assembled pin the same way, then runs the
citation check and the schema check into their logs. The census
(`train_pin_needles.py pin PIN --tip REV --not REV --scratch DIR --write`) runs last
and judges the whole pin.
"""
import argparse
import collections
import difflib
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOLS = ("train_pin_needles.py", "assemble_pin.py", "train_pin_scan.py", "train_pin_schema.py",
         "train_pin_cite.py", "train_mutations.py", "train_controls.py")
TESTS = "backend/tests/test_pc_steam_server.py"
TRAIN = "scripts/deploy/release_train.py"
SEAT = "scripts/deploy/release_train.conf.json"
PRODUCER = "tools/train_pin/assemble_pin.py"
DERIVER = "tools/train_pin/train_pin_needles.py"
WRAPPER = "scripts/cc-snapshot-wrapper.sh"
LATER = ("tools-self-test.log", "pin-census.log", "pin-path-scan.log", "pin-schema-check.log",
         "notes-citation-check.log")
PLACEHOLDER = (b"This file is written by a later step of the assembly. If this line is what "
               b"you are reading, that step did not run.\n")
FENCE_OPEN, FENCE_CLOSE = "<<<SCR-TRAIN-REVIEW-SUMMARY", "SCR-TRAIN-REVIEW-SUMMARY>>>"
# (source prefix, token, extend over the rest of the path component) -- first match wins
TOKENS = (
    ("user-path", "~", False),
    ("sidecar:workstation path", "<local path>", False),
    ("sidecar:worktree directory name", "<worktree>", True),
    ("sidecar:review pin directory name", "<review pin>", True),
    ("sidecar:temporary or scratch directory", "<scratch dir>", True),
    ("seat", "<seat value>", False),
    ("machine", "<machine name>", False),
    ("sidecar:backup host name", "<machine name>", False),
    ("sidecar:backend or broadcast machine name", "<machine name>", False),
    ("identity", "<account>", False),
    ("guard", "<withheld name>", False),
)
STOP = frozenset(b"/\\ \t\r\n'\"`<>|:;,)]}")


class Refusal(Exception):
    pass


def _load(name):
    spec = importlib.util.spec_from_file_location("assemble_pin_" + name,
                                                  str(HERE / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NEEDLES = _load("train_pin_needles")
SCHEMA = _load("train_pin_schema")


def _doc(stem):
    """A document's file name. Its stem is formatted and the suffix joined after,
    so no format string here leaves a dotted fragment for the shape census."""
    return stem + ".md"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _rank(item):
    for n, (prefix, token, extend) in enumerate(TOKENS):
        if any(s.startswith(prefix) for s in item["sources"]):
            return n, token, extend
    return len(TOKENS), "<withheld>", False


def sanitize(data, table):
    """(bytes with every FINDING span replaced by its token, Counter of tokens)."""
    marked = []
    for s, e, item in NEEDLES.finding_spans(data, table):
        rank, token, extend = _rank(item)
        if extend:
            while e < len(data) and data[e] not in STOP:
                e += 1
        marked.append([s, e, token, rank])
    marked.sort()
    merged = []
    for s, e, token, rank in marked:
        if merged and s < merged[-1][1]:
            last = merged[-1]
            last[1] = max(last[1], e)
            if rank < last[3]:
                last[2], last[3] = token, rank
        else:
            merged.append([s, e, token, rank])
    out, pos, counts = [], 0, collections.Counter()
    for s, e, token, _rank_ in merged:
        out += [data[pos:s], token.encode("utf-8")]
        pos = e
        counts[token] += 1
    out.append(data[pos:])
    clean = b"".join(out)
    if NEEDLES.finding_spans(clean, table):
        raise Refusal("a document still holds a needle after its tokens were placed")
    return clean, counts


def udiff(old, new, label):
    a = old.decode("utf-8").splitlines(keepends=True)
    b = new.decode("utf-8").splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile="a/" + label,
                                        tofile="b/" + label)).encode("utf-8")


class Pin:
    def __init__(self, out, repo, tip, ns, table, scratch):
        self.out, self.repo, self.tip, self.ns, self.table = out, repo, tip, ns, table
        self.scratch = scratch
        self.entries, self.log = [], []

    def put(self, name, data, entry):
        if NEEDLES.finding_spans(data, self.table):
            raise Refusal("%s would enter the pin holding a needle" % name)
        (self.out / name).write_bytes(data)
        entry = dict(entry, file=name)
        self.entries.append(entry)
        return entry

    def tracked(self, name, path, extra=None):
        blob = NEEDLES._git(self.repo, ["rev-parse", "%s:%s" % (self.tip, path)]).strip()
        data = NEEDLES._git(self.repo, ["cat-file", "blob", blob], binary=True)
        self.put(name, data, dict(extra or {}, **{"class": "TRACKED-COPY", "path": path,
                                                  "blob": blob}))
        self.log.append("TRACKED-COPY %-44s <- %s at the pin commit, blob %s%s"
                        % (name, path, blob[:12],
                           ("; the gate (%s) of %s" % (extra["gate"], extra["gated_from"]))
                           if extra and extra.get("gated_from") else ""))

    def generated(self, name, recipe, inputs, what, producer=PRODUCER, data=None):
        # The same function the census re-runs: the recipe is checked first
        # (R10-H4) and answers about this pin commit, through the door (R10-H3).
        # R12-L1: ONE execution per recipe. When the caller has already run the
        # recipe -- to derive `what` from what the file HOLDS -- it passes that
        # exact output as `data`, so the description and the pinned bytes are
        # provably the same run; a mutable ref moving between two runs can no
        # longer make the description describe run one while the file holds run
        # two. When `data` is None the recipe is run here, once.
        if data is None:
            data = NEEDLES.run_recipe(self.repo, recipe, self.tip, inputs, self.scratch)
        self.put(name, data, {"class": "GENERATED", "recipe": recipe, "producer": producer,
                              "run_log": "assembly.log", "inputs": inputs, "what": what})
        if isinstance(recipe, dict):
            shown = "derive %s at %s over %d path(s)" % (
                recipe["derive"], recipe["tip"][:12], len(recipe["paths"]))
        else:
            shown = "git " + " ".join(a if len(a) != 40 else a[:12] for a in recipe)
        self.log.append("GENERATED    %-44s <- %s (%d bytes)" % (name, shown, len(data)))

    def typed(self, name, data, what, sanitise=False):
        counts = collections.Counter()
        if sanitise:
            data, counts = sanitize(data, self.table)
        self.put(name, data, {"class": "TYPED", "what": what, "sha256": sha256(data),
                              "tokens_placed": dict(counts)})
        self.log.append("TYPED        %-44s <- %s%s" % (
            name, what, ("; tokens placed: " + ", ".join(
                "%s x%d" % kv for kv in sorted(counts.items()))) if counts else ""))

    def manifest(self):
        doc = {"schema": "SCR_TRAIN_PIN_PROVENANCE", "version": 1, "tip": self.tip,
               "needles": self.ns.line(), "files": self.entries}
        (self.out / "provenance.json").write_bytes(
            (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def gated_wrapper(repo, tip, source):
    """The snapshot wrapper's gated copy as tracked at the pin commit, proven to be the gate of
    its repository copy (R11-L1). Refuses when the repository copy is not readable, when the
    pin commit does not track the gated copy, or when the two disagree by one byte."""
    src = NEEDLES.wrapper_source(repo, source)
    if src is None:
        raise Refusal("the snapshot wrapper's repository copy is not readable, so its gated "
                      "copy cannot be proven")
    tracked = subprocess.run(NEEDLES.git_argv(repo, ["cat-file", "blob", "%s:%s" % (
        tip, NEEDLES.WRAPPER_GATED)]), capture_output=True, env=NEEDLES.git_env())
    if tracked.returncode != 0:
        raise Refusal("the pin commit does not track the snapshot wrapper's gated copy (%s)"
                      % NEEDLES.WRAPPER_GATED)
    if NEEDLES.wrapper_gate(src.read_bytes()) != tracked.stdout:
        raise Refusal("the gated copy tracked at the pin commit is not the gate of the "
                      "wrapper's repository copy: re-derive it with "
                      "train_pin_needles.wrapper_gate and commit it")
    return tracked.stdout


def _summary(doc, table, name):
    problems = SCHEMA.document_problems(doc)
    if problems:
        raise Refusal("%s: the validator refuses it (%d problem(s))" % (name, len(problems)))
    found = NEEDLES.field_findings(doc, table)
    if found:
        raise Refusal("%s: %d rendered field(s) hold a needle: %s"
                      % (name, len(found), ", ".join(found[:5])))
    return (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8")


def harness_twice(first, second, prior_mutations, tip):
    """R11: the bar's two back-to-back harness runs, compared, and the control count
    set against the prior pin's run. Lines for assembly.log. A difference is printed
    as a line, never raised: the pin carries what the runs found."""
    def kills(doc):
        return sorted((r["id"], r["kind"], r["expected"], r["observed"], r["restore"])
                      for r in doc["controls"])

    def raised(doc):
        return sorted((r["id"], r["kind"], r["exception"]) for r in doc["controls"])

    def outcomes(doc):
        return sorted((t["node"], t["outcome"]) for t in doc["tests"])

    def ids(doc):
        return {r["id"] for r in doc["controls"]}

    def same(a, b):
        if a == b:
            return "IDENTICAL"
        differ = sorted(set(a) ^ set(b))
        return "DIFFER in %d row(s): %s" % (len(differ), "; ".join(" ".join(r) for r in
                                                                   differ[:12]))

    out = ["", "# The bar's two back-to-back harness runs (R11): run 1 is run1-summary-*.json,",
           "# run 2 is summary-*.json. Compared control by control and test by test; the",
           "# control count is set against the prior pin's summary-mutations.json.", ""]
    for label, docs in (("run 1", first), ("run 2", second)):
        t, m = docs["TESTS"], docs["MUTATIONS"]
        out.append("HARNESS %s: tests at %s -- %d collected, %d passed, %d failed, %d error(s), "
                   "%d skipped; mutations at %s -- %d control(s), %d arm(s), mutant RED %d, "
                   "twin GREEN %d, restores EQUAL %d, problems %d; both at the pin commit: %s"
                   % (label, t["generated_utc"], t["collected"], t["passed"], t["failed"],
                      t["errors"], t["skipped"], m["generated_utc"], m["control_count"],
                      m["arms"], m["mutant_red"], m["twin_green"], m["restores_equal"],
                      m["problems"], "yes" if t["tests_tip"] == m["tests_tip"] == tip else
                      "NO"))
    out.append("HARNESS KILL SETS, run 1 vs run 2 (id, kind, expected, observed, restore): %s"
               " -- %d and %d row(s)" % (same(kills(first["MUTATIONS"]),
                                              kills(second["MUTATIONS"])),
                                         len(first["MUTATIONS"]["controls"]),
                                         len(second["MUTATIONS"]["controls"])))
    out.append("HARNESS EXCEPTIONS, run 1 vs run 2 (id, kind, exception): %s"
               % same(raised(first["MUTATIONS"]), raised(second["MUTATIONS"])))
    out.append("HARNESS TESTS, run 1 vs run 2 (node, outcome): %s -- %d and %d test(s)"
               % (same(outcomes(first["TESTS"]), outcomes(second["TESTS"])),
                  len(first["TESTS"]["tests"]), len(second["TESTS"]["tests"])))
    before, one, two = ids(prior_mutations), ids(first["MUTATIONS"]), ids(second["MUTATIONS"])
    retired, added = sorted(before - two), sorted(two - before)
    out.append("HARNESS CONTROL COUNT: the prior pin's run %d, retired %d, added %d; run 1 %d, "
               "run 2 %d; run 1 and run 2 hold the same controls: %s"
               % (len(before), len(retired), len(added), len(one), len(two),
                  "yes" if one == two else "NO"))
    out.append("  retired since the prior pin's run: %s" % (", ".join(retired) or "none"))
    out.append("  added since the prior pin's run: %s" % (", ".join(added) or "none"))
    return out


def _run(argv, title):
    p = subprocess.run(argv, capture_output=True)
    text = (p.stdout + p.stderr).decode("utf-8", "replace").rstrip()
    return ["$ " + title, text, "exit %d" % p.returncode, ""], p.returncode


def build(a):
    repo = Path(a.repo)
    out = Path(a.out)
    if out.exists():
        raise Refusal("the pin directory exists already; a pin is assembled once, into a "
                      "directory nothing else has written")
    ns = NEEDLES.derive(None, repo, a.sidecar)
    table = NEEDLES.Table(ns.items)
    git = lambda args: NEEDLES._git(repo, args).strip()           # noqa: E731
    tip = git(["rev-parse", "--verify", a.tip + "^{commit}"])
    head = git(["rev-parse", "HEAD"])
    if tip != head:
        raise Refusal("the pin commit is not the checked-out commit, so the working "
                      "train and tools are not the ones at the pin commit")
    if git(["status", "--porcelain", "--untracked-files=all", "--", "tools/train_pin",
            TESTS]):
        raise Refusal("the tools or the tests differ from the pin commit")
    rb = git(["rev-parse", "--verify", a.round_base + "^{commit}"])
    mb = git(["rev-parse", "--verify", a.merge_base + "^{commit}"])
    main = git(["rev-parse", "--verify", a.main + "^{commit}"])
    n = a.round
    prior, docs = Path(a.prior_pin), Path(a.docs)
    historical = [git(["rev-parse", "--verify", h + "^{commit}"]) for h in a.historical]
    gated_wrapper(repo, tip, a.wrapper)
    live = sorted(p for p in Path(a.live_logs).iterdir()
                  if p.is_file() and p.name.startswith(a.live_prefix) and p.suffix == ".log")
    if not live:
        raise Refusal("no live-run log carries the prefix named by --live-prefix")
    out.mkdir(parents=True)
    pin = Pin(out, repo, tip, ns, table, a.scratch)
    pin.log += ["# The assembly of this pin, file by file. No value of any needle appears",
                "# here: a document's placed tokens are counted, never quoted.",
                ns.line(), "pin commit %s; round %d" % (tip, n), ""]

    for tool in TOOLS:
        pin.tracked(tool, "tools/train_pin/" + tool)
    pin.tracked(os.path.basename(TESTS), TESTS)
    # R11-L1: the snapshot wrapper, as a TRACKED-COPY -- its gated copy, which the census
    # proves is the gate of the repository copy (train_pin_needles.wrapper_problems)
    pin.tracked(os.path.basename(NEEDLES.WRAPPER_GATED), NEEDLES.WRAPPER_GATED,
                extra={"gated_from": NEEDLES.WRAPPER_SOURCE,
                       "gate": "train_pin_needles.wrapper_gate"})

    t7 = tip[:7]
    for base, what in ((rb, "the tests file's change in this round"),
                       (mb, "every tracked test line the branch adds over its merge base")):
        pin.generated("tests-%s-over-%s.patch" % (t7, base[:7]),
                      ["diff", "--src-prefix=a/", "--dst-prefix=b/", "%s..%s" % (base, tip),
                       "--", "backend/tests"],
                      [{"commit": base}, {"commit": tip}, {"path": "backend/tests"}], what)
    pin.generated("tools-%s-over-%s.patch" % (t7, rb[:7]),
                  ["diff", "--src-prefix=a/", "--dst-prefix=b/", "%s..%s" % (rb, tip),
                   "--", "tools/train_pin"],
                  [{"commit": rb}, {"commit": tip}, {"path": "tools/train_pin"}],
                  "the lane's tools as this round adds them")
    pin.generated("commits-landing-range.txt", ["log", "--format=%H %s", "%s..%s" % (main, tip)],
                  [{"commit": main}, {"commit": tip}],
                  "every commit a merge of the branch into main would carry")
    pin.generated("commits-this-round.txt", ["log", "--format=%H %s", "%s..%s" % (rb, tip)],
                  [{"commit": rb}, {"commit": tip}], "the commits this round added")
    pin.generated("tests-blobs-landing-range.txt",
                  ["log", "--format=%H %s", "--raw", "--no-abbrev", "%s..%s" % (main, tip), "--",
                   TESTS],
                  [{"commit": main}, {"commit": tip}],
                  "every commit of the landing range that changed the tests file, with the "
                  "file's blob id before and after it: which commit made each blob the object "
                  "census names")
    pin.generated("numstat.txt", ["diff", "--numstat", "%s..%s" % (mb, tip)],
                  [{"commit": mb}, {"commit": tip}],
                  "the tracked delta of the branch over its merge base")
    pin.generated("gitignore.txt", {"derive": "ignore-proof", "tip": tip,
                                    "paths": [TRAIN, SEAT, WRAPPER]},
                  [{"commit": tip}], "the train, the seat configuration and the snapshot "
                  "wrapper's repository copy, asked of the pin commit's own tree and "
                  ".gitignore blobs: untracked and ignored", producer=DERIVER)
    pin.generated("tracked-lane-files.txt", ["ls-tree", "-r", "--name-only", tip, "--",
                                             "tools/train_pin", TESTS, "scripts/deploy"],
                  [{"commit": tip}], "what the pin commit's tree holds of the lane: the "
                                     "tools and the tests, never the train")
    # R11-L6: each description is derived from what the file HOLDS, never typed ahead of it.
    # The branch's merge base is the POSITIVE control -- main contains it, so its answers are
    # nonempty -- and an empty answer there refuses: the query itself would be broken, and
    # every empty answer for a historical commit would mean nothing.
    for h in historical:
        control = h == mb
        for name, recipe, asked in (
                ("remote-refs-containing-%s.txt" % h[:7],
                 ["for-each-ref", "--format=%(refname)", "--contains", h, "refs/remotes/"],
                 "every remote-tracking ref that contains %s" % h[:7]),
                ("remote-branches-containing-%s.txt" % h[:7],
                 ["branch", "-r", "--contains", h],
                 "`git branch -r --contains %s`" % h[:7])):
            held = NEEDLES.run_recipe(repo, recipe, tip, [{"commit": h}], a.scratch)
            lines = len(held.splitlines())
            if control and not lines:
                raise Refusal("the positive control is empty: %s answers nothing for the "
                              "branch's merge base, which main contains" % asked)
            if control:
                what = ("%s -- the branch's merge base, the POSITIVE control: nonempty, %d "
                        "line(s), so the query finds what it is asked for" % (asked, lines))
            elif lines:
                what = "%s -- nonempty: %d line(s)" % (asked, lines)
            else:
                what = "%s -- an empty file: none does" % asked
            # R12-L1: pass the run we already made, so the pinned bytes and the
            # description above are the same single execution of this mutable ref.
            pin.generated(name, recipe, [{"commit": h}], what, data=held)

    new = (repo / TRAIN).read_bytes()
    prev = (prior / "release_train-NEW.py").read_bytes()
    old = (prior / "release_train-OLD.py").read_bytes()
    pin.typed("release_train-NEW.py", new, "the gitignored train in the pin commit's working "
              "tree, verbatim (sha256 %s)" % sha256(new))
    pin.typed("release_train-OLD.py", old, "the prior pin's OLD train, unchanged")
    pin.typed("release_train.diff", udiff(old, new, "release_train.py"),
              "OLD -> NEW, labelled a/ and b/")
    pin.typed("release_train-r%d-to-r%d.diff" % (n - 1, n), udiff(prev, new, "release_train.py"),
              "the prior pin's NEW -> this NEW, labelled a/ and b/")
    for k in range(1, n - 1):
        name = "release_train-r%d-to-r%d.diff" % (k, k + 1)
        pin.typed(name, (prior / name).read_bytes(), "the prior pin's copy, unchanged")
    pin.typed("release_train.conf.example.json",
              (prior / "release_train.conf.example.json").read_bytes(),
              "the prior pin's example seat file (placeholders only), unchanged")
    for p in live:
        pin.typed(p.name, p.read_bytes(), "a live read-only run of the train at the pin "
                  "commit, or the digests taken around those runs", sanitise=True)

    for k in range(1, n - 1):
        for kind in ("BRIEF", "REPORT"):
            name = _doc("CODEX-TRAIN-BUG392-MERGE-R%d-%s" % (k, kind))
            pin.typed(name, (prior / name).read_bytes(), "the prior pin's copy", sanitise=True)
    for kind in ("BRIEF", "REPORT"):
        name = _doc("CODEX-TRAIN-BUG392-MERGE-R%d-%s" % (n - 1, kind))
        pin.typed(name, (docs / name).read_bytes(), "the round-%d review document" % (n - 1),
                  sanitise=True)
    for k in range(6, n):
        name = _doc("TRAIN-BUG392-MERGE-R%d-NOTES" % k)
        pin.typed(name, (prior / name).read_bytes(), "the prior pin's copy", sanitise=True)
    name = _doc("TRAIN-BUG392-MERGE-R%d-BUILD-BRIEF" % n)
    pin.typed(name, (docs / name).read_bytes(), "this round's build brief", sanitise=True)
    notes = _doc("TRAIN-BUG392-MERGE-R%d-NOTES" % n)
    pin.put(notes, PLACEHOLDER, {"class": "TYPED", "what": "this round's notes (the `notes` "
                                 "step writes them)"})

    # the six summaries: validated, every rendered field needle-scanned, then written
    text = Path(a.review_log).read_bytes().decode("utf-8")
    if text.count(FENCE_OPEN) != 1 or text.count(FENCE_CLOSE) != 1:
        raise Refusal("the review-summary transcript does not carry exactly one fence pair")
    docs_ = json.loads(text.split(FENCE_OPEN, 1)[1].split(FENCE_CLOSE, 1)[0])
    by = {d.get("artifact"): d for d in docs_}
    if sorted(by) != sorted(SCHEMA.TRAIN_ARTIFACTS) or len(docs_) != len(by):
        raise Refusal("the fenced text is not exactly one document per train artifact")
    harness = Path(a.harness)
    for art in SCHEMA.HARNESS_ARTIFACTS:
        by[art] = json.loads((harness / SCHEMA.PIN_FILES[art]).read_bytes().decode("utf-8"))
    for art in SCHEMA.ARTIFACTS:
        name = SCHEMA.PIN_FILES[art]
        data = _summary(by[art], table, name)
        pin.typed(name, data, "the %s document: validated, every rendered field needle-scanned"
                  % art)

    # R11: the FIRST of the two back-to-back harness runs, validated and scanned
    # like the second, then the two compared into assembly.log.
    first = {}
    for art in SCHEMA.HARNESS_ARTIFACTS:
        first[art] = json.loads((Path(a.harness_first) / SCHEMA.PIN_FILES[art])
                                .read_bytes().decode("utf-8"))
        name = "run1-" + SCHEMA.PIN_FILES[art]
        pin.typed(name, _summary(first[art], table, name), "the %s document of the FIRST "
                  "of the two back-to-back harness runs: validated, every rendered field "
                  "needle-scanned" % art)
    prior_mutations = json.loads((prior / SCHEMA.PIN_FILES["MUTATIONS"]).read_bytes()
                                 .decode("utf-8"))
    pin.log += harness_twice(first, by, prior_mutations, tip)

    for name in LATER:
        pin.put(name, PLACEHOLDER, {"class": "TYPED", "what": "a log a later step writes"})
    pin.entries.append({"class": "TYPED", "file": "provenance.json",
                        "what": "this manifest"})
    pin.entries.append({"class": "TYPED", "file": "assembly.log",
                        "what": "the run log of this assembly"})
    pin.manifest()
    (out / "assembly.log").write_bytes(("\n".join(pin.log) + "\n").encode("utf-8"))

    # every tool's own controls, over the tools as they are in this pin
    py = sys.executable
    t = str(HERE)
    runs = [
        ("train_pin_needles.py describe",
         [py, t + "/train_pin_needles.py", "describe", "--sidecar", a.sidecar, "--repo",
          str(repo)]),
        ("train_pin_needles.py self-test --tip %s --not %s --pin <this pin>" % (t7, main[:7]),
         [py, t + "/train_pin_needles.py", "self-test", "--scratch", a.scratch, "--tip", tip,
          "--not", main, "--pin", str(out), "--sidecar", a.sidecar, "--repo", str(repo)]),
        ("train_pin_scan.py <this pin> --self-test",
         [py, t + "/train_pin_scan.py", str(out), "--self-test", "--needles", a.sidecar,
          "--repo", str(repo)]),
        ("train_pin_schema.py --self-test", [py, t + "/train_pin_schema.py", "--self-test"]),
        ("train_pin_cite.py --self-test", [py, t + "/train_pin_cite.py", "--self-test"]),
        ("train_mutations.py --anchors", [py, t + "/train_mutations.py", "--anchors"]),
        ("assemble_pin.py --self-test", [py, t + "/assemble_pin.py", "--self-test"]),
    ]
    lines = ["# Every pin tool's own controls, run by the assembler over the tools as they",
             "# are in this pin. Each block ends with its exit status.", ""]
    failed = []
    for title, argv in runs:
        block, rc = _run(argv, title)
        lines += block
        if rc:
            failed.append(title)
    (out / "tools-self-test.log").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print("\n".join(pin.log))
    print("files: %d; self-test blocks failed: %d%s" % (
        len(pin.entries), len(failed), ("  (" + "; ".join(failed) + ")") if failed else ""))
    return 1 if failed else 0


def notes(a):
    out = Path(a.out)
    ns = NEEDLES.derive(None, a.repo, a.sidecar)
    table = NEEDLES.Table(ns.items)
    name = _doc("TRAIN-BUG392-MERGE-R%d-NOTES" % a.round)
    data, counts = sanitize((Path(a.docs) / name).read_bytes(), table)
    (out / name).write_bytes(data)
    manifest = json.loads((out / "provenance.json").read_bytes().decode("utf-8"))
    for e in manifest["files"]:
        if e["file"] == name:
            e.update(what="this round's notes", sha256=sha256(data), tokens_placed=dict(counts))
    (out / "provenance.json").write_bytes(
        (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    with open(out / "assembly.log", "ab") as f:
        f.write(("TYPED        %-44s <- this round's notes%s\n" % (
            name, ("; tokens placed: " + ", ".join("%s x%d" % kv for kv in
                                                   sorted(counts.items()))) if counts else "")
                 ).encode("utf-8"))
    py = sys.executable
    block, rc_cite = _run([py, str(HERE / "train_pin_cite.py"), str(out), name, "--write"],
                          "train_pin_cite.py <this pin> %s --write" % name)
    print("\n".join(block))
    p = subprocess.run([py, str(HERE / "train_pin_schema.py"), str(out)], capture_output=True)
    (out / "pin-schema-check.log").write_bytes(p.stdout + p.stderr)
    print("schema check exit %d" % p.returncode)
    return 1 if (rc_cite or p.returncode) else 0


def self_test():
    """L1 (R12-L1): Pin.generated() executes a recipe at most once. Nothing of any ref is
    printed; only whether the pinned bytes are the run the description was derived from.

    The two call sites the assembler used were the caller's run (to derive `what` from what
    the file HOLDS) and generated()'s own run (to pin the bytes). A mutable ref answering
    differently between them made the description describe run one while the file held run two.
    The control models a run_recipe that answers a different nonempty value each call."""
    import shutil
    import tempfile
    results = []

    def check(cid, what, want_red, got_red, detail):
        ok = bool(want_red) == bool(got_red)
        results.append("CONTROL %-24s got %-5s want %-5s %s  %s"
                       % (cid, "RED" if got_red else "GREEN", "RED" if want_red else "GREEN",
                          "PASS" if ok else "FAIL", detail))

    def counter(answers):
        it = iter(answers)
        return lambda *a, **k: next(it)

    A, B = b"ref-answer-one\n", b"ref-answer-two-different\n"
    saved = NEEDLES.run_recipe
    tmp = Path(tempfile.mkdtemp(prefix="scr-l1-selftest-"))
    try:
        table = NEEDLES.Table([])

        def pin_for(sub):
            d = tmp / sub
            d.mkdir(parents=True, exist_ok=True)
            return Pin(d, ROOT, "HEAD", None, table, str(tmp))

        # MUTANT: the old two-run pattern -- the caller derives `what` from run one (A), then
        # generated() with no data re-runs the mutable ref and pins run two (B). The file
        # disagrees with the run the description was derived from.
        NEEDLES.run_recipe = counter([A, B])
        p = pin_for("mutant")
        held = NEEDLES.run_recipe(ROOT, ["x"], "HEAD", [], str(tmp))
        p.generated("m.txt", ["x"], [], "derived from run one", data=None)
        got = (p.out / "m.txt").read_bytes()
        check("L1-TWO-RUN", "two executions pin a run the description did not describe",
              True, got != held, "the pinned file %s the run the description was derived from"
              % ("differs from" if got != held else "equals"))

        # TWIN: the fixed one-run pattern -- generated(data=held) never reads the swapped
        # second answer, so the file is the single run the description described, and nonempty.
        NEEDLES.run_recipe = counter([A, B])
        p = pin_for("twin")
        held = NEEDLES.run_recipe(ROOT, ["x"], "HEAD", [], str(tmp))
        p.generated("t.txt", ["x"], [], "derived from run one", data=held)
        got = (p.out / "t.txt").read_bytes()
        check("L1-ONE-RUN-NEG", "negative: data passed, the file is the one run described and "
              "is nonempty", False, (got != held) or (not got),
              "the pinned file %s held, %d byte(s)"
              % ("equals" if got == held else "differs from", len(got)))

        # TWIN: an unrelated GENERATED recipe with a STABLE ref -- both runs equal, so
        # generated(data=None) is unchanged by the fix.
        NEEDLES.run_recipe = counter([A, A])
        p = pin_for("stable")
        held = NEEDLES.run_recipe(ROOT, ["x"], "HEAD", [], str(tmp))
        p.generated("s.txt", ["x"], [], "a stable ref", data=None)
        got = (p.out / "s.txt").read_bytes()
        check("L1-STABLE-REF-NEG", "negative: a stable ref pins the same bytes with or without "
              "data", False, got != held,
              "the pinned file %s held" % ("equals" if got == held else "differs from"))
    finally:
        NEEDLES.run_recipe = saved
        shutil.rmtree(tmp, ignore_errors=True)

    failed = sum(1 for r in results if "FAIL" in r)
    results.append("CONTROLS %d: %d PASS, %d FAIL" % (len(results), len(results) - failed, failed))
    return results, (1 if failed else 0)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in argv:
        block, rc = self_test()
        print("\n".join(block))
        return rc
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("build", "notes"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--tip", default="HEAD")
    ap.add_argument("--round-base")
    ap.add_argument("--merge-base")
    ap.add_argument("--main", default="main")
    ap.add_argument("--prior-pin")
    ap.add_argument("--docs")
    ap.add_argument("--harness")
    ap.add_argument("--harness-first")
    ap.add_argument("--review-log")
    ap.add_argument("--scratch")
    ap.add_argument("--wrapper")
    ap.add_argument("--live-logs")
    ap.add_argument("--live-prefix")
    ap.add_argument("--historical", action="append", default=[])
    ap.add_argument("--sidecar", default=os.environ.get("SCR_PIN_NEEDLES"))
    a = ap.parse_args(argv)
    try:
        if a.command == "build":
            for need in ("round_base", "merge_base", "prior_pin", "docs", "harness",
                         "harness_first", "review_log", "scratch", "wrapper", "live_logs", "live_prefix"):
                if not getattr(a, need):
                    raise Refusal("--%s is required" % need.replace("_", "-"))
            return build(a)
        if not a.docs:
            raise Refusal("--docs is required")
        return notes(a)
    except (Refusal, NEEDLES.Refusal) as r:
        print("REFUSED: %s" % r)
        return 2


if __name__ == "__main__":
    sys.exit(main())
