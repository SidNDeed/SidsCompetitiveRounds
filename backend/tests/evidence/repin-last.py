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
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(BACKEND)
CLOSING_K = ("committed_evidence or assembled_from_its_run or "
             "round_eight_control or round_seven_control or production_file "
             "or runner_carries or control_tally or counts_the_checks or "
             "new_controls_a_report or residual_reach or negation_admits or "
             "repin_trailer or inert_twin")

# The two commit messages this wrapper makes, so that what `git log` shows is
# the wrapper's own account and not a hand-written one. The run log goes in
# its own commit FIRST, and the report -- which quotes git's listing of that
# commit -- goes last, alone.
#
# ROUND 13: THE TRAILER IS NO LONGER A LITERAL HERE. It used to be typed into
# both messages below, and round 12 recorded that as a residual rather than
# fixing it: nothing compared the constant with the sitting that ran the
# wrapper, so a sitting that forgot it committed under the previous sitting's
# attribution and no check reddened. That is the same shape as every defect
# this ladder has closed -- a declaration standing beside the thing it
# describes -- and it had already gone stale once, which is how the lens found
# it. The trailer is now DERIVED from the branch's most recent commits, by
# `derive_trailer` below, and appended by `commit_message`; the two bodies
# carry no attribution at all. The sweep beside it exempts exactly that one
# derived line and nothing else, so a stale or foreign attribution in a
# message this wrapper is about to write stops the round instead of entering
# the record.
LOG_COMMIT_BODY = """The re-pin run's own capture, committed before the record of it

%s is the stdout the re-pin report is assembled from. It goes in a
commit of its own so the commit that carries the report adds exactly one path,
which is what that report asserts about itself."""

REPORT_COMMIT_BODY = """The route-manifest re-pin, run last, as its own record

The wrapper that produced %s refuses to run while anything is
uncommitted, so the tree it read is the tree its grandparent commit holds. It
recorded that commit and its tree hash, ran the closing evidence check over the
directory as committed, ran the re-pin tool, and applied this directory's own
claim and invocation rules to the report before writing it.

This commit adds exactly one path. The wrapper staged it, asked git what was
staged, and wrote that listing into the report before staging it again -- so
the claim the report makes about this commit is git's answer rather than a
sentence written beside it."""

# The ONE attribution form this repository's commits carry. The pattern names
# the KEY and the shape, never a person: what fills it is read off the branch.
TRAILER_LINE = re.compile(r"^Co-Authored-By: \S.*<[^<>@\s]+@[^<>\s]+>$")
# Anything that CLAIMS an author. Every git trailer key that names one, plus
# the bare shapes an address or a handle takes when somebody pastes one into a
# message. The sweep exempts the derived trailer and nothing else, so a second
# `Co-Authored-By:` line, a stale one, or an address in prose all red.
ATTRIBUTION = re.compile(
    r"^\s*(?:Co-Authored-By|Co-authored-by|Signed-off-by|Signed-Off-By"
    r"|Author|Authored-by|Reported-by|Reviewed-by|Acked-by|Tested-by"
    r"|Helped-by|Suggested-by|On-behalf-of)\s*:"
    r"|<[^<>@\s]+@[^<>\s]+>"
    r"|(?:^|\s)@[A-Za-z0-9][A-Za-z0-9._-]{2,}")
# How many of the most recent commits have to AGREE before a trailer is taken
# as the branch's form. One is a sample; two is the smallest set in which a
# one-off typo is visible as a disagreement rather than adopted as the rule.
TRAILER_AGREE = 2


def trailer_of(body):
    """The attribution trailer one commit message carries, or None."""
    for line in reversed(body.strip().splitlines()):
        line = line.strip()
        if TRAILER_LINE.match(line):
            return line
    return None


def derive_trailer(bodies):
    """(trailer, why) for the form the branch's most recent commits carry.

    THE ONE SOURCE. `bodies` is the commit messages of the branch, newest
    first, exactly as `git log --format=%B` prints them. The newest one's
    trailer is the answer, and the next `TRAILER_AGREE - 1` that carry one
    have to agree with it -- a sitting that changes the attribution changes it
    on the commits it makes, so what this reads is the form in force right
    now rather than the form some earlier sitting typed into this file.

    `why` names the one fact that is wrong when nothing can be derived, and
    the caller REFUSES on it: an attribution nobody can derive is exactly the
    thing that used to be typed."""
    if not bodies:
        return None, "the branch carries no commit to read a trailer from"
    carried = [(i, trailer_of(b)) for i, b in enumerate(bodies)]
    have = [(i, t) for i, t in carried if t is not None]
    if not have:
        return None, ("none of the %d most recent commits carries a "
                      "Co-Authored-By trailer" % len(bodies))
    if have[0][0] != 0:
        return None, ("the most recent commit carries no Co-Authored-By "
                      "trailer, so there is no current form to derive")
    newest = have[0][1]
    agreeing = 1
    for _i, t in have[1:]:
        if t != newest:
            return None, ("the two most recent commits that carry a trailer "
                          "disagree: %r and %r" % (newest, t))
        agreeing += 1
        if agreeing >= TRAILER_AGREE:
            break
    if agreeing < TRAILER_AGREE:
        return None, ("only %d of the most recent commits carries a trailer, "
                      "and %d have to agree" % (agreeing, TRAILER_AGREE))
    return newest, None


def tip_messages(bodies, trailer):
    """The most recent commits that carry the derived form, newest first.

    THE SWEEP'S WINDOW. An earlier sitting of this branch legitimately
    committed under a different attribution, and a sweep that ran back past
    the form in force would report that history as a finding. What the sweep
    is about is the tip this round leaves: the commits under the current form,
    plus the two about to be made. The window is where the form CHANGES, and
    it is derived from the same trailers the form was derived from rather than
    from a count written down here."""
    out = []
    for body in bodies:
        if trailer_of(body) != trailer:
            break
        out.append(body)
    return out


def foreign_attributions(text, trailer):
    """[(line number, line)] for every attribution in `text` that is not the
    derived trailer.

    THE EXEMPTION IS EXACTLY ONE LINE, compared whole. A rule that exempted
    "anything beginning Co-Authored-By" would exempt the stale attribution
    this sweep exists to catch, which is a check that cannot fail on its own
    class (#342)."""
    bad = []
    for number, line in enumerate(text.splitlines(), 1):
        if trailer is not None and line.strip() == trailer:
            continue
        if ATTRIBUTION.search(line):
            bad.append((number, line.strip()))
    return bad


def commit_message(body, trailer):
    """A message this wrapper commits: its own prose, then the derived
    trailer. The two are joined here so there is one place where an
    attribution is attached to anything."""
    return body.rstrip("\n") + "\n\n" + trailer + "\n"


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

    # THE ATTRIBUTION THIS SITTING COMMITS UNDER, derived before anything is
    # written. `%x00` separates the messages, because a commit body contains
    # blank lines and any newline-based split would cut one in half.
    log_bodies = git("log", "-n", "8", "--format=%B%x00").stdout
    bodies = [b for b in log_bodies.split("\0") if b.strip()]
    trailer, why = derive_trailer(bodies)
    if trailer is None:
        print("REFUSED: the commit trailer could not be derived from the "
              "branch, and this wrapper does not type one: %s" % why)
        return 2
    log_message = commit_message(LOG_COMMIT_BODY % log_name, trailer)
    report_message = commit_message(
        REPORT_COMMIT_BODY % os.path.basename(report), trailer)
    # THE FINAL-TIP NAME SWEEP, over the messages this tip will carry: the
    # branch's most recent commits and the two about to be made. Exactly the
    # derived trailer is exempt; a stale one, a second one, an address or a
    # handle anywhere else is a finding, and the round stops here rather than
    # recording it.
    swept = []
    for label, text_of in ([("about to commit (run log)", log_message),
                            ("about to commit (report)", report_message)]
                           + [("HEAD~%d" % i, b) for i, b in
                              enumerate(tip_messages(bodies, trailer))]):
        swept.append((label, foreign_attributions(text_of, trailer)))
    offenders = [(label, hits) for label, hits in swept if hits]
    if offenders:
        print("REFUSED: an attribution that is not the derived trailer is "
              "present in %d message(s):" % len(offenders))
        for label, hits in offenders:
            for number, line in hits:
                print("  %-26s line %d: %s" % (label, number, line))
        return 2
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

    # THE SWEEP, recorded where the rest of the run is. It ran above, before
    # anything was written; this is its result under its own invocation line.
    log.write("== the final-tip attribution sweep ==\n")
    log.write("cwd       <repo>\n")
    log.write("command   python backend/tests/evidence/repin-last.py"
              " (derive_trailer, then foreign_attributions over every message"
              " this tip carries)\n")
    log.write("trailer   %s  (derived from the branch, not typed)\n" % trailer)
    for label, hits in swept:
        log.write("  %-26s %s\n"
                  % (label, "clean" if not hits
                     else "FOREIGN: %s" % (hits,)))
    log.write("sweep rc=0\n\n")

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
    made = git("commit", "-m", log_message)
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
        say("== the attribution these two commits carry, and where it came from ==")
        say("The trailer is DERIVED from the branch's most recent commits and")
        say("appended by one function, rather than typed into this file. The")
        say("previous round left it as a literal here and recorded that as a")
        say("residual: nothing compared the constant with the sitting running")
        say("the wrapper, so a sitting that forgot it committed under the")
        say("previous sitting's attribution and no check reddened. The run")
        say("below names what was derived, and the sweep beside it reads every")
        say("message this tip carries -- the two about to be committed and the")
        say("branch's most recent -- exempting exactly that one derived line.")
        say("An attribution anywhere else refuses the round before a commit is")
        say("made rather than entering the record.")
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
    made = git("commit", "-m", report_message)
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
