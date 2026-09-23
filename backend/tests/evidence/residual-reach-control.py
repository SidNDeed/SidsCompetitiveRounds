"""MUTATION CONTROL for the residual list's integrity-reach rule (#391).

    python backend/tests/evidence/residual-reach-control.py <document>

THE DOCUMENT IS AN ARGUMENT and is not named here. The residual list this lane
keeps lives under the gitignored scratch, and a committed file may not send a
reader to a path this repository does not contain -- the same reason the
citation pin takes its two documents as arguments. What ran is recorded in this
round's report, beside this output.

WHAT IT CHECKS. `residual_rules.py` asks three things of a residual list: every
item carries exactly one integrity-reach tag, the count stated under the list
is the tags' own count, and nothing else in the section states a reach. The
third clause is the one the round is for. A list said, in one item, that two
seats one number apart "can still both settle" -- a second settlement of one
physical game, which pays twice -- and said sixteen lines later that a
different item was "the one item in this list that can move a rating". Neither
sentence was wrong about its own subject; the second was a count of the first.

So the control puts that exact sentence back, and requires a refusal. It also
removes one tag, and requires a refusal for a different reason. And it changes
the wording beside a tag without touching a claim, and requires the check to
stay quiet -- without that half, a rule that refused every document would pass
both mutations and say nothing (#391).

EVERY EDIT IS MADE TO A COPY IN A TEMPORARY DIRECTORY. The document is read and
never written. The temporary path is this machine's and is printed as a
placeholder, for the same reason every other instrument here prints
repository-relative paths.
"""
import datetime
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RULES = os.path.join(HERE, "residual_rules.py")
SHOWN_RULES = "backend/tests/evidence/residual_rules.py"
SHOWN_DOC = "<the lane's contract, under the gitignored scratch>"
SHOWN_COPY = "<a copy of it, in a temporary directory>"

# The claim this control exists for, written exactly as it stood, and WRAPPED
# the way the document wraps it -- the wrap is the reason a per-line search
# would not have found it.
STALE_CLAIM = ("  by hand. This is the one item in this list that can move a\n"
               "  rating.\n")
TAG_CAN = "  **Integrity reach:** can move a rating.\n"


def run(path, label):
    """Run the rule over one file and report what it said."""
    argv = [sys.executable, RULES, path]
    print("  command   python %s %s" % (SHOWN_RULES,
                                        SHOWN_DOC if label == "live"
                                        else SHOWN_COPY))
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                          timeout=120)
    body = (proc.stdout + proc.stderr).replace("\r\n", "\n").strip()
    for line in body.splitlines():
        print("  %-8s %s" % (label, line.strip()))
    return proc.returncode


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[0])
        print("usage: residual-reach-control.py <document>")
        return 2
    doc_path = argv[1]
    if not os.path.isfile(doc_path):
        print("REFUSED: the named document is not a file")
        return 2

    print("script    <repo>/backend/tests/evidence/residual-reach-control.py")
    print("cwd       <repo>")
    print("rule      <repo>/%s" % SHOWN_RULES)
    print("document  %s" % SHOWN_DOC)
    print("python    %s" % sys.version.split()[0])
    # The capture this run is redirected into, named by the producer --
    # see the .gitignore block for this directory.
    print("capture   <repo>/backend/tests/evidence/<round>-residual-reach.log")
    print("started   %s UTC"
          % datetime.datetime.now(datetime.timezone.utc)
                    .strftime("%Y-%m-%d %H:%M:%S"))
    print("")

    with io.open(doc_path, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()

    rc = 0
    tmp = tempfile.mkdtemp()

    def write_copy(name, body):
        path = os.path.join(tmp, name)
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(body)
        return path

    def expect(label, path, want, why):
        nonlocal rc
        got = run(path, label)
        if got != want:
            print("  *** %s: rc=%d, expected %d -- %s ***" % (label, got, want, why))
            rc = 1
        return got

    try:
        print("LIVE   the document as it stands")
        expect("live", doc_path, 0, "the committed list has to pass its own rule")
        print("")

        print("MUTANT A  the superseded prose count, put back where it stood")
        # THE ANCHOR IS DERIVED, and round 14 is why. It used to be a quoted
        # slice of the item's closing sentence, which made it an anchor on the
        # line BREAKS as much as on the words: this round reflowed that
        # paragraph without touching a claim in it, and the control refused
        # with "the anchor for mutation A does not resolve". The refusal was
        # correct and it was about the wrap.
        #
        # What the mutation actually needs is the END of the item that carries
        # the "can move a rating" tag -- the place a second statement of the
        # reach would sit -- and that is exactly where the tag itself begins.
        # So the insertion point is found from the tag, which the rule under
        # test already requires to be there, and no prose is quoted at all.
        pos = text.find(TAG_CAN)
        if pos < 0:
            print("  REFUSED: no item carries the can-move tag, so there is "
                  "no item for mutation A to state the reach in twice")
            rc = 1
        else:
            mutant = text[:pos] + STALE_CLAIM + text[pos:]
            if mutant == text:
                print("  REFUSED: mutation A changed nothing")
                rc = 1
            else:
                expect("mutant A", write_copy("mutant_a.md", mutant), 1,
                       "a second statement of the reach has to be refused")
        print("")

        print("MUTANT B  one item's tag removed, the count left as it was")
        if text.count(TAG_CAN) < 1:
            print("  REFUSED: the anchor for mutation B does not resolve")
            rc = 1
        else:
            mutant = text.replace(TAG_CAN, "", 1)
            expect("mutant B", write_copy("mutant_b.md", mutant), 1,
                   "an item with no tag has to be refused")
        print("")

        print("INERT  a wording change beside a tag, no claim touched")
        inert_from = "head. The revision this replaces stated a reach in prose"
        if inert_from not in text:
            print("  REFUSED: the anchor for the inert edit does not resolve")
            rc = 1
        else:
            inert = text.replace(
                inert_from,
                "head. The revision this replaces  stated a reach in prose", 1)
            if inert == text:
                print("  REFUSED: the inert edit changed nothing, so it is not "
                      "a control")
                rc = 1
            else:
                expect("inert", write_copy("inert.md", inert), 0,
                       "an edit that states no claim must leave the check quiet")
        print("")
    finally:
        for name in os.listdir(tmp):
            os.remove(os.path.join(tmp, name))
        os.rmdir(tmp)

    if rc == 0:
        print("RESULT: live CLEAN, mutant A REFUSED, mutant B REFUSED, inert")
        print("        CLEAN. The rule reds on a second statement of the reach")
        print("        and on an item that states none, and stays quiet on a")
        print("        reword beside them. The document was read, never written.")
    else:
        print("RESULT: FAILURES above")
    print("finished  %s UTC"
          % datetime.datetime.now(datetime.timezone.utc)
                    .strftime("%Y-%m-%d %H:%M:%S"))
    return rc


def lf_stdout():
    """Write LF. The reason in full is in mutation-runner.py's copy of this:
    this instrument's stdout is a committed file, every file under this
    directory is LF, and a Windows text stream writes CRLF -- which would
    make the report that quotes it mixed, and a mixed report cannot be
    restored byte-for-byte by the control that mutates it."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(newline="\n")


if __name__ == "__main__":
    lf_stdout()
    sys.exit(main(sys.argv))
