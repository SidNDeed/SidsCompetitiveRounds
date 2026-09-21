"""The route-manifest re-pin, run LAST, with the ordering as evidence.

B14 asks that `backend/tests/route_manifest_net_seat.json` be re-pinned by its
OWN tool after the last edit of any kind. Round 9 ran it and then EDITED the
report that recorded it, so the result it committed was no longer last -- the
r6 lens said so, and the answer is not to be more careful but to take the
editing away.

So this wrapper does the whole ending, and the report it produces is its
OUTPUT rather than a file anybody writes:

  1. it REFUSES unless `git status --porcelain` is empty, which is the
     ordering proof: every other edit of the round -- source, tests,
     instruments, the other evidence files -- is already committed, so there
     is nothing left that could be edited after the re-pin;
  2. it records the commit and the TREE HASH that state belongs to, so a
     reader can check that the tree the re-pin ran against is the tree the
     commit below it holds;
  3. it runs the closing evidence check over the directory as committed;
  4. it runs the re-pin tool -- the LAST thing that reads or touches the
     tree;
  5. it writes the report in one shot, and applies this directory's own rules
     to what it is about to write BEFORE writing it: the assembler's claim
     rules, and the invocation rule, both imported from where they live
     rather than restated here.

Step 5 is what ends the regress. A pytest run cannot cover the file that
records it, because that file is written afterwards by construction; the
answer is not a second pytest run (which needs a third) but a check the
generator applies to itself. Nothing is written unless it passes.

    python backend/tests/evidence/repin-last.py

The commit that follows adds exactly this one file, so `git log` shows the
order the wrapper asserts: the work, then the record of the run made over it.
"""
import datetime
import importlib.util
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(BACKEND)
REPORT = os.path.join(HERE, "r10-repin.txt")
LOG = os.path.join(HERE, "r10-repin-run.log")
CLOSING_K = ("committed_evidence or assembled_from_its_run or "
             "round_eight_control or round_seven_control or production_file "
             "or runner_carries or control_tally")


def load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, timeout=120)


def main():
    rules = load("_scr_evidence_rules", "evidence_rules.py")
    assembler = load("_scr_assembler", "assemble-evidence.py")

    problems = rules.selftest()
    if problems:
        print("REFUSED: the invocation rule does not hold in both directions:")
        for p in problems:
            print("  " + p)
        return 2
    if assembler.selftest():
        return 2

    status = git("status", "--porcelain")
    if status.returncode != 0:
        print("REFUSED: git status failed: %s" % status.stderr.strip())
        return 2
    dirty = [ln for ln in status.stdout.splitlines() if ln.strip()]
    if dirty:
        print("REFUSED: the tree is not clean, so this re-pin would not be "
              "the last thing that happened. Uncommitted:")
        for ln in dirty[:20]:
            print("  " + ln)
        return 2

    head = git("rev-parse", "HEAD").stdout.strip()
    tree = git("rev-parse", "HEAD^{tree}").stdout.strip()
    subject = git("log", "-1", "--format=%s").stdout.strip()
    now = (datetime.datetime.now(datetime.timezone.utc)
           .strftime("%Y-%m-%d %H:%M:%S"))

    out = io.StringIO()

    def say(line=""):
        out.write(line + "\n")

    say("The route manifest re-pin, RUN LAST, with the order as evidence")
    say("===============================================================")
    say()
    say("stdout: r10-repin-run.log")
    say()
    say("Instrument: backend/tests/evidence/repin-last.py, which produces this")
    say("file as its OUTPUT. Nothing here is typed and nothing is appended")
    say("afterwards -- the r6 lens found the previous round's report edited")
    say("after its own tool had run, which left the manifest result no longer")
    say("last, and an instrument that writes the record is the only shape that")
    say("cannot regress to that.")
    say()
    say("== the ordering, as something a reader can check ==")
    say("The wrapper refuses to run at all while `git status --porcelain` has")
    say("any line in it. It was empty, so every other edit of this round --")
    say("source, tests, instruments, the other evidence files -- was already")
    say("committed before the re-pin ran, and nothing was left that could be")
    say("edited after it. The commit that adds this file adds only this file,")
    say("so `git log` shows the same order from the other side.")
    say()
    say("  HEAD at the re-pin     %s" % head)
    say("  tree of that commit    %s" % tree)
    say("  subject                %s" % subject)
    say("  run at                 %s UTC" % now)
    say()
    say("`git rev-parse HEAD~1^{tree}` from the commit that adds this file is")
    say("the tree hash above. That is the check: the re-pin ran against the")
    say("tree its parent commit holds, and the only difference between that")
    say("tree and the committed one is this record.")
    say()
    say("== what the wrapper checked before it wrote this ==")
    say("A pytest run cannot cover the file that records it: the file is")
    say("written after the run, by construction. So the closing check below")
    say("covers every other report in this directory, and the rules this")
    say("directory enforces are applied by the wrapper to THIS file before it")
    say("is written -- the assembler's claim rules and the invocation rule,")
    say("imported from evidence_rules.py and assemble-evidence.py rather than")
    say("restated here, because a rule with two implementations drifts. If")
    say("either refuses, nothing is written.")
    say()
    say("== what a clean result means here ==")
    say("`rows rewritten now : 0` is the result this round requires. The")
    say("manifest already held every fingerprint the committed tree produces,")
    say("so the tool changed nothing -- the positive statement that the")
    say("committed manifest and the committed code agree. A non-zero count")
    say("here would mean the tree moved after the suites certified it.")
    say()
    say("-" * 78)
    say("THE RUN, verbatim from here down")
    say("-" * 78)

    log = io.StringIO()

    def run_block(tag, title, argv, cwd):
        # The command line goes LAST of the three header lines, immediately
        # above the output it produced. The invocation rule this directory
        # enforces reads upward from a result and requires the command to be
        # the nearest substantive line above it, so a header that ended with
        # a timestamp would put a line between them that is not part of any
        # tool's own frame.
        log.write("== %s ==\n" % title)
        log.write("cwd       %s\n" % ("<repo>" if cwd == ROOT
                                      else "<repo>/backend"))
        log.write("started   %s UTC\n"
                  % (datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%d %H:%M:%S")))
        log.write("command   %s\n" % " ".join(["python"] + list(argv[1:])))
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              timeout=1800)
        body = (proc.stdout + proc.stderr).replace("\r\n", "\n")
        log.write(body if body.endswith("\n") else body + "\n")
        log.write("%s rc=%d\n\n" % (tag, proc.returncode))
        return proc.returncode

    # The closing check FIRST: it reads the tree, and the re-pin has to be the
    # last thing that does.
    closing_rc = run_block(
        "closing",
        "closing evidence check, over this directory as committed",
        [sys.executable, "-m", "pytest",
         "tests/test_ffa_game_number_anchor.py", "-q", "-p", "no:cacheprovider",
         "-k", CLOSING_K],
        BACKEND)

    # ...and the re-pin LAST.
    repin_rc = run_block(
        "repin",
        "route manifest re-pin, by its own tool",
        [sys.executable, os.path.join("backend", "tests",
                                      "repin_route_manifest.py")],
        ROOT)

    body = log.getvalue()
    with io.open(LOG, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)

    text = out.getvalue()
    # The directory's own rules, applied to what is about to be written.
    rebuilt = text + "========== r10-repin-run.log ==========\n" + body
    bad = assembler.undrivable(text, body)
    if bad:
        os.remove(LOG)
        print("REFUSED: %d claim(s) in this report are absent from its own "
              "run:" % len(bad))
        for kind, claim in bad:
            print("  %-7s %s" % (kind, claim))
        return 1
    missing = rules.results_without_an_invocation(rebuilt)
    if missing:
        os.remove(LOG)
        print("REFUSED: %d result line(s) in this report have no invocation "
              "above them:" % len(missing))
        for n, line in missing:
            print("  line %d: %s" % (n, line))
        return 1

    with io.open(REPORT, "w", encoding="utf-8", newline="") as fh:
        fh.write(rebuilt)
    print("written backend/tests/evidence/r10-repin.txt "
          "(closing check rc=%d, re-pin rc=%d)" % (closing_rc, repin_rc))
    return 0 if (closing_rc == 0 and repin_rc == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
