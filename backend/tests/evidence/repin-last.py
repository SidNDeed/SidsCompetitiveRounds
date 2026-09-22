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
     rather than restated here;
  6. it MAKES THE TWO COMMITS ITSELF, run log first and report last, each
     adding exactly ONE path, and it quotes git's own listing of what each
     one contains.

Step 5 is what ends the regress. A pytest run cannot cover the file that
records it, because that file is written afterwards by construction; the
answer is not a second pytest run (which needs a third) but a check the
generator applies to itself. Nothing is written unless it passes.

STEP 6 IS ROUND 12'S CORRECTION, and it is the same shape as step 5. Round 11
said "the commit that adds this file adds only this file" while the commit it
described added two -- the report AND the run log it quotes -- because the two
files were written together and staged together by hand. A sentence about a
commit, written before the commit exists and by somebody other than the thing
that makes it, is a claim nothing checks. So the wrapper makes them: the run
log goes in its OWN EARLIER commit, the report goes in the last one alone, and
both listings below are git's output rather than a description of it.

    python backend/tests/evidence/repin-last.py

Nothing is committed unless the report passes the checks of step 5 first, and
the run log's commit is made before the report is written because the report
QUOTES the listing of it. The report is staged, git is asked what is staged,
and the answer is written into the report before it is staged again and
committed: one path, named by git, in the commit that carries this file.
"""
import datetime
import fnmatch
import importlib.util
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(BACKEND)
CLOSING_K = ("committed_evidence or assembled_from_its_run or "
             "round_eight_control or round_seven_control or production_file "
             "or runner_carries or control_tally or counts_the_checks or "
             "new_controls_a_report or residual_reach or negation_admits")

# The two commit messages this wrapper makes, so that what `git log` shows is
# the wrapper's own account and not a hand-written one. The run log goes in
# its own commit FIRST, and the report -- which quotes git's listing of that
# commit -- goes last, alone.
#
# THE TRAILER IS STILL A LITERAL, and that is a known residual rather than a
# thing this file pretends to have solved: it names the author of the sitting
# that runs the wrapper, and a sitting with a different author has to change
# it here. It is the same shape as the defects this round closes -- a
# declaration standing beside the thing it describes -- and the honest
# statement is that it is carried, not derived. Deriving it from the commit
# the wrapper runs on top of would be the fix, and that needs a control of its
# own.
LOG_COMMIT_MESSAGE = """The re-pin run's own capture, committed before the record of it

%s is the stdout the re-pin report is assembled from. It goes in a
commit of its own so the commit that carries the report adds exactly one path,
which is what that report asserts about itself.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"""

REPORT_COMMIT_MESSAGE = """The route-manifest re-pin, run last, as its own record

The wrapper that produced %s refuses to run while anything is
uncommitted, so the tree it read is the tree its grandparent commit holds. It
recorded that commit and its tree hash, ran the closing evidence check over the
directory as committed, ran the re-pin tool, and applied this directory's own
claim and invocation rules to the report before writing it.

This commit adds exactly one path. The wrapper staged it, asked git what was
staged, and wrote that listing into the report before staging it again -- so
the claim the report makes about this commit is git's answer rather than a
sentence written beside it.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"""


def load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, timeout=120)


def capture_name(number):
    """The capture this wrapper OPENS, for round `number`.

    THE ONE PLACE THAT NAME IS DECIDED. It used to exist twice -- in the
    expression that opened the file, and in a comment above it that said what
    the expression produced -- and nothing compared the two. Every other
    producer in this directory is redirected into its capture by its caller
    and prints the name in its own stdout header, so the `.gitignore` pattern
    paired with it is paired with something a run emits; this one writes the
    file itself and offered the pairing a sentence instead. A declaration that
    can be left behind when the code moves is prose (#351).

    So everything that needs the name calls this: the path opened below, the
    `capture` header written INTO that log, the admission check that runs
    before anything is written, and the pairing check in
    test_the_evidence_log_negation_admits_only_produced_logs, which loads this
    module and CALLS this function rather than reading the source around it.
    """
    return "r%d-repin-run.log" % number


def capture_is_admitted(name, gitignore_text):
    """True when `.gitignore` re-includes `name` under this directory.

    `*.log` is ignored repository-wide and this directory re-includes one
    pattern per producer. A capture written under a name no pattern admits
    cannot be committed: `git add` refuses it at the LAST step of the round,
    with the run it was supposed to record already spent. This is that
    question asked before the file is opened, so the answer can be a refusal
    that says why.
    """
    prefix = "!backend/tests/evidence/"
    for line in gitignore_text.splitlines():
        line = line.strip()
        if not line.startswith(prefix):
            continue
        if fnmatch.fnmatch(name, line[len(prefix):]):
            return True
    return False


def main():
    rules = load("_scr_evidence_rules", "evidence_rules.py")
    assembler = load("_scr_assembler", "assemble-evidence.py")

    # WHICH ROUND THIS RECORD BELONGS TO, derived from the reports already in
    # the directory rather than written here. A round number in a path is a
    # thing to remember to bump, and the failure it produces is the worst
    # shape available: the wrapper would overwrite the PREVIOUS round's re-pin
    # record with this round's run, under that round's name, and report
    # success. Every other report of this round is committed before this runs
    # -- the wrapper refuses otherwise -- so the newest round in the directory
    # is this one by construction.
    names = [n for n in os.listdir(HERE) if n.endswith(".txt")]
    number = rules.newest_round(names)
    if number is None:
        print("REFUSED: this directory carries no round-numbered report, so "
              "the round this re-pin belongs to cannot be derived")
        return 2
    report = os.path.join(HERE, "r%d-repin.txt" % number)
    log_name = capture_name(number)
    log_path = os.path.join(HERE, log_name)

    # THE CAPTURE HAS TO BE ONE THIS REPOSITORY CAN CARRY, and that is asked
    # here rather than discovered at the end. The .gitignore block for this
    # directory re-includes one pattern per producer; a name no pattern admits
    # is refused by `git add` after the run, which is the worst moment to find
    # out. The check runs against the same value the file is opened under.
    with io.open(os.path.join(ROOT, ".gitignore"), "r",
                 encoding="utf-8") as fh:
        ignores = fh.read()
    if not capture_is_admitted(log_name, ignores):
        print("REFUSED: %s is the capture this wrapper opens and no negation "
              "in .gitignore re-includes it, so this round's re-pin record "
              "could not be committed" % log_name)
        return 2

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

    # ── the run first, because the report quotes it ──────────────────────
    log = io.StringIO()
    # THE CAPTURE THIS WRAPPER OPENS, named by the producer -- from the one
    # function that decided it, which is also the value the file was opened
    # under and the value the admission check ran against. The other seven
    # instruments here print this header because a caller redirects them into
    # a file; this one prints it because it writes the file. The pairing in
    # .gitignore is checked against that function, never against this line.
    log.write("script    backend/tests/evidence/repin-last.py\n")
    log.write("cwd       <repo>\n")
    log.write("capture   backend/tests/evidence/%s\n" % log_name)
    log.write("\n")

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
    with io.open(log_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)

    # ── the run log's OWN commit, made here so the report can quote it ────
    # Round 11's report said "the commit that adds this file adds only this
    # file" about a commit that added two, because both files were written
    # together and staged together by hand. The wrapper stages them, one
    # commit each, and asks git what each one contains.
    log_rel = "backend/tests/evidence/" + log_name
    report_rel = "backend/tests/evidence/" + os.path.basename(report)
    staged = git("add", "--", log_rel)
    if staged.returncode != 0:
        print("REFUSED: could not stage %s: %s" % (log_rel, staged.stderr.strip()))
        return 2
    made = git("commit", "-m", LOG_COMMIT_MESSAGE % log_name)
    if made.returncode != 0:
        print("REFUSED: the run log's commit failed: %s"
              % (made.stderr.strip() or made.stdout.strip()))
        return 2
    log_listing = [ln for ln in git("show", "--name-only", "--format=",
                                    "HEAD").stdout.splitlines() if ln.strip()]

    # ── the report, built around what git said ───────────────────────────
    def build(staged_listing):
        out = io.StringIO()

        def say(line=""):
            out.write(line + "\n")

        say("The route manifest re-pin, RUN LAST, with the order as evidence")
        say("===============================================================")
        say()
        say("stdout: %s" % log_name)
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
        say("edited after it.")
        say()
        say("  HEAD at the re-pin     %s" % head)
        say("  tree of that commit    %s" % tree)
        say("  subject                %s" % subject)
        say("  run at                 %s UTC" % now)
        say()
        say("== which commit carries which file, from git rather than from me ==")
        say("Round 11's report said the commit that added it added only it. That")
        say("commit added two paths -- the report and the run log it quotes --")
        say("because both were written together and staged together by hand, and")
        say("a sentence about a commit written before that commit exists is a")
        say("claim nothing checks. The wrapper makes both commits now, one path")
        say("each, and the two listings below are git's own.")
        say()
        say("The run log went FIRST, in a commit of its own. Immediately after")
        say("making it the wrapper ran `git show --name-only --format= HEAD`,")
        say("which printed:")
        say()
        for line in log_listing:
            say("  " + line)
        say()
        say("Then it wrote this file, staged it with `git add -- %s`," % report_rel)
        say("and ran `git diff --cached --name-only`, which printed:")
        say()
        if staged_listing is None:
            say("  (this file is being staged; the listing is written in below")
            say("  before it is staged again and committed)")
        else:
            for line in staged_listing:
                say("  " + line)
        say()
        say("That listing is what the last commit of this round contains: this")
        say("report, and nothing else. The run log is in the commit before it,")
        say("and the round's source, tests, instruments and other evidence are in")
        say("the commit before that -- which is the HEAD named above, the tree")
        say("the re-pin actually ran against.")
        say()
        say("== the capture this report is assembled from, and who names it ==")
        say("The log named in the header above is OPENED by this wrapper rather")
        say("than redirected into it by a caller, so its name is decided in one")
        say("function and used in three places: the file that is opened, the")
        say("`capture` header written into that file, and the check that this")
        say("repository's ignore rules re-include it. That check runs before")
        say("anything is written, so a name this tree could not carry stops the")
        say("round here instead of at the `git add` that ends it. The test that")
        say("pairs producers with patterns reads the name by CALLING that")
        say("function, which is why the pairing cannot drift from the file.")
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
        return out.getvalue()

    def vet(text):
        """This directory's own rules, applied to what is about to be written."""
        rebuilt = text + ("========== %s ==========\n" % log_name) + body
        bad = assembler.undrivable(text, body)
        if bad:
            print("REFUSED: %d claim(s) in this report are absent from its own "
                  "run:" % len(bad))
            for kind, claim in bad:
                print("  %-7s %s" % (kind, claim))
            return None
        missing = rules.results_without_an_invocation(rebuilt)
        if missing:
            print("REFUSED: %d result line(s) in this report have no invocation "
                  "above them:" % len(missing))
            for n, line in missing:
                print("  line %d: %s" % (n, line))
            return None
        return rebuilt

    # PASS 1: write the report, stage it, and ask git what is staged. The
    # answer is a fact about the commit that is about to be made, and the only
    # way to have it INSIDE that commit is to write it in and stage again.
    first = vet(build(None))
    if first is None:
        return 1
    with io.open(report, "w", encoding="utf-8", newline="") as fh:
        fh.write(first)
    staged = git("add", "--", report_rel)
    if staged.returncode != 0:
        print("REFUSED: could not stage %s: %s"
              % (report_rel, staged.stderr.strip()))
        return 2
    staged_listing = [ln for ln in git("diff", "--cached", "--name-only")
                      .stdout.splitlines() if ln.strip()]

    # PASS 2: the same report with git's listing in it. The listing does not
    # change between the passes -- the same one path is staged either way --
    # so what is written is true of the commit that carries it.
    final = vet(build(staged_listing))
    if final is None:
        return 1
    with io.open(report, "w", encoding="utf-8", newline="") as fh:
        fh.write(final)
    staged = git("add", "--", report_rel)
    if staged.returncode != 0:
        print("REFUSED: could not re-stage %s: %s"
              % (report_rel, staged.stderr.strip()))
        return 2
    made = git("commit", "-m", REPORT_COMMIT_MESSAGE % os.path.basename(report))
    if made.returncode != 0:
        print("REFUSED: the report's commit failed: %s"
              % (made.stderr.strip() or made.stdout.strip()))
        return 2
    print("written and committed %s "
          "(closing check rc=%d, re-pin rc=%d)"
          % (report_rel, closing_rc, repin_rc))
    for line in git("show", "--name-only", "--format=", "HEAD").stdout.splitlines():
        if line.strip():
            print("  last commit adds: " + line)
    return 0 if (closing_rc == 0 and repin_rc == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
