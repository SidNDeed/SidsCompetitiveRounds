"""The evidence assembler: a report's numbers come from its run, or it refuses.

Round 6's gate (B17) asked for this by name. Every report under this directory
CLAIMS to be generated from the stdout of the run it describes, and until now
that claim rested on the author having done it -- round 9's suites report
carried a file count its own run never printed, sitting in a sentence that
looked exactly like every sentence around it that WAS quoted. Nothing in the
directory could tell the two apart, because nothing compared a report against
the bytes it came from.

This does, and it REFUSES rather than transcribes: it exits non-zero, naming
how many claims it could not derive and printing each one, whenever a number
in a report's prose is absent from the stdout that report names.

    python backend/tests/evidence/assemble-evidence.py --assemble <report>
    python backend/tests/evidence/assemble-evidence.py --check <report>
    python backend/tests/evidence/assemble-evidence.py --selftest

A REPORT'S SHAPE. Everything above the marker line is the NARRATIVE -- prose
the author writes. Everything below it is the RUN, and the author does not
write it at all: `--assemble` replaces it with the exact bytes of the logs the
report names. `--check` rebuilds the same file and compares, so a report whose
verbatim block was edited by hand after the run reds here. Each report names
its logs in a header line of its own, near the top:

    stdout: r10-suite-run.log r10-suite-optout.log

resolved against this directory, so a committed report names a committed file
and a reader on a fresh clone can re-derive every number in it.

WHAT COUNTS AS A CLAIM, stated rather than left to taste. Two rules, and they
are complementary -- neither catches what the other does:

  R1, the counting terms. An integer immediately followed by one of the terms
      a run reports in (`passed`, `skipped`, `deselected`, `paths`, `tracked
      files`, `controls`, ...) is a count. It must appear in the stdout as the
      same integer next to the same term. This is the rule that catches round
      9's `all 12 tracked files`: two digits, so no size rule would see it, and
      a count all the same.

  R2, the big numbers. Any integer of three digits or more that survives the
      typed exemptions below must appear SOMEWHERE in the stdout. This is the
      rule that catches a summary line's totals being quoted with a digit
      changed, which R1 would pass whenever the term is right.

THE EXEMPTIONS ARE TYPED, NOT PER-NUMBER. A list of individually excused
numbers is a list that grows until the check cannot fail (#342), so what is
exempt here is a SHAPE -- a numbered lesson, a date, a clock time, a bar row,
an evidence-file round tag, a version, a migration number, an HTTP status.
Adding a number to a report never silences the check; only writing it in one
of those shapes does, and each shape is something a run genuinely does not
print. The self-test asserts every rule fires AND stays quiet, in both
directions, so a typo in any pattern reds at `--selftest` rather than passing
for ever.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

MARKER = "THE RUN, verbatim from here down"
STDOUT_HEADER = re.compile(r"^stdout:\s*(.+?)\s*$", re.MULTILINE)

# The terms a run reports in. Both directions are asserted in the self-test:
# each one matches a real line, and prose that merely describes a run does not.
TERMS = [
    "passed", "failed", "skipped", "xfailed", "xpassed", "deselected",
    "warnings", "errors", "error", "paths", "tracked files", "controls",
    "rows", "routes",
]
COUNT_RE = re.compile(r"(\d+)\s+(" + "|".join(TERMS) + r")\b")

# Shapes a run does not print, each one a KIND rather than a number.
EXEMPT = [
    (r"#\d+", "a numbered lesson"),
    (r"\d{4}-\d{2}-\d{2}", "a date"),
    (r"\d{1,2}:\d{2}(:\d{2})?", "a clock time"),
    (r"\br\d+-[a-z0-9-]+", "an evidence-file round tag"),
    (r"\b[BHMLSGRFDP]\d+(-\d+)?\b", "a bar or finding row"),
    (r"\bround \d+\b", "a round of this ladder"),
    (r"\b\d+\.\d+(\.\d+)*\b", "a version or a section number"),
    (r"\b(?:migration|Migration|SQL|sql)\s+\d+\b", "a migration"),
    (r"\b(?:200|400|401|403|404|409|500|502|503)\b", "an HTTP status"),
    (r"\b\d+\.\.\d+\b", "an inclusive range"),
]
EXEMPT_RE = re.compile("|".join("(?:%s)" % p for p, _ in EXEMPT))
BIG_RE = re.compile(r"\b(\d{3,})\b")


def read(path):
    with io.open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def rel(path):
    """Repository-relative and POSIX-style. Everything this prints goes
    through here: a committed log naming an absolute path names one machine's
    checkout, which a clone cannot follow."""
    try:
        out = os.path.relpath(path, ROOT)
    except ValueError:
        return "(outside the repository)"
    if out.startswith(".."):
        return "(outside the repository)"
    return out.replace(os.sep, "/")


def split_report(text):
    """(narrative, run) around the marker line, or (text, None)."""
    idx = text.find(MARKER)
    if idx < 0:
        return text, None
    line_end = text.find("\n", idx)
    # The ruler line under the marker belongs to the narrative's frame, so the
    # run starts after it when there is one.
    rest = text[line_end + 1:]
    nxt = rest.find("\n")
    if nxt >= 0 and set(rest[:nxt].strip()) <= {"-", "="} and rest[:nxt].strip():
        return text[:line_end + 1 + nxt + 1], rest[nxt + 1:]
    return text[:line_end + 1], rest


def named_logs(narrative):
    names = []
    for hit in STDOUT_HEADER.finditer(narrative):
        names.extend(hit.group(1).split())
    return names


def claims(narrative):
    """Every number the narrative asserts, as (kind, text) pairs."""
    out = []
    for hit in COUNT_RE.finditer(narrative):
        out.append(("count", "%s %s" % (hit.group(1), hit.group(2))))
    masked = EXEMPT_RE.sub(lambda m: "#" * len(m.group(0)), narrative)
    for hit in BIG_RE.finditer(masked):
        out.append(("number", hit.group(1)))
    return out


def derivable(kind, claim, stdout):
    """Is this claim present in the stdout AS THE SAME NUMBER?

    The leading `(?<!\\d)` is the difference between a check and a check that
    cannot fail: without it `12 tracked files` is satisfied by a run that
    printed `112 tracked files`, and a claim is then derivable from a number
    it is not (#342)."""
    if kind == "count":
        number, term = claim.split(" ", 1)
        return re.search(r"(?<!\d)" + re.escape(number) + r"\s+"
                         + re.escape(term) + r"\b", stdout) is not None
    return re.search(r"(?<!\d)" + re.escape(claim) + r"\b",
                     stdout) is not None


def undrivable(narrative, stdout):
    return [(k, c) for k, c in claims(narrative)
            if not derivable(k, c, stdout)]


def assemble(report_path, check_only):
    text = read(report_path)
    narrative, run = split_report(text)
    if run is None:
        print("REFUSED: %s carries no %r marker, so it names no run"
              % (rel(report_path), MARKER))
        return 2
    names = named_logs(narrative)
    if not names:
        print("REFUSED: %s names no stdout file, so none of its numbers can "
              "be derived" % rel(report_path))
        return 2

    blocks = []
    stdout = []
    for name in names:
        path = os.path.join(HERE, name)
        if not os.path.isfile(path):
            print("REFUSED: %s names %s, which is not in this directory"
                  % (rel(report_path), name))
            return 2
        body = read(path)
        stdout.append(body)
        # Ten `=` on each side, deliberately. The evidence check's invocation
        # rule skips a heavily `=`-framed line as a tool's own frame (pytest
        # prints several) and REFUSES to skip a `=== phase ===` line, which is
        # a section boundary. A banner in the second shape would read as a
        # boundary and hide the command line below it.
        blocks.append("========== %s ==========\n%s" % (name, body))
    joined = "".join(stdout)
    rebuilt = narrative + "".join(blocks)

    bad = undrivable(narrative, joined)
    if bad:
        print("REFUSED: %d claim(s) in %s are absent from the run stdout it "
              "names (%s):" % (len(bad), rel(report_path), " ".join(names)))
        for kind, claim in bad:
            print("  %-7s %s" % (kind, claim))
        return 1

    if check_only:
        if rebuilt != text:
            print("REFUSED: %s does not equal what its own logs assemble to; "
                  "the verbatim block was edited after the run"
                  % rel(report_path))
            return 1
        print("OK: %s -- %d claim(s) all derived from %s; the verbatim block "
              "is the named stdout, byte for byte"
              % (rel(report_path), len(claims(narrative)), " ".join(names)))
        return 0

    write(report_path, rebuilt)
    print("ASSEMBLED: %s -- %d claim(s) derived from %s"
          % (rel(report_path), len(claims(narrative)), " ".join(names)))
    return 0


# ── the self-test: every rule fires, and every rule stays quiet ──────────
CLEAN = """A report.

stdout: x.log

The run says 7 passed and hashed 9 paths, on round 9, per #342, on
2026-09-21 at 03:08:29, for B17 and R4-13, version 1.40.3, migration 327,
answering 503 over the range 1..999. The total was 1761.
"""

DIRTY_COUNT = CLEAN.replace("hashed 9 paths", "hashed 12 paths")
DIRTY_BIG = CLEAN.replace("The total was 1761.", "The total was 1762.")
LOG = "7 passed, 3 skipped\n9 paths differ\n1761 passed\n"


def run_checks():
    """Every rule check this instrument makes, as (name, ok, detail) records.

    The records are what the printed count is taken from. It used to be
    written as `len(TERMS) + 19` -- a constant beside a body that runs two
    loops and thirteen standalone checks -- and it printed one fewer than the
    run made, on the one instrument whose whole purpose is to refuse a number
    a run did not produce (#342). Adding or removing a check now moves the
    printed number by construction, and the paired test compares that number
    against the invocations the run actually made rather than against a second
    constant."""
    checks = []

    def expect(name, got, want):
        checks.append((name, got == want,
                       None if got == want
                       else "%r, expected %r" % (got, want)))

    expect("a clean narrative has nothing undrivable",
           undrivable(CLEAN, LOG), [])
    expect("a count the run never printed is refused",
           [c for _, c in undrivable(DIRTY_COUNT, LOG)], ["12 paths"])
    expect("a big number the run never printed is refused",
           [c for _, c in undrivable(DIRTY_BIG, LOG)], ["1762"])
    # Each exemption shape really is exempt, and really is a shape rather than
    # a number: the same digits WITHOUT the shape are not exempt.
    for text, shape in [("#342", "a numbered lesson"),
                        ("2026-09-21", "a date"),
                        ("03:08:29", "a clock time"),
                        ("r10-suites.txt", "an evidence-file round tag"),
                        ("B17", "a bar row"),
                        ("round 9", "a round"),
                        ("1.40.3", "a version"),
                        ("migration 327", "a migration"),
                        ("503", "an HTTP status"),
                        ("1..999", "a range")]:
        expect("%s is exempt" % shape, undrivable(text + "\n", ""), [])
    expect("the same digits without the shape are not exempt",
           [c for _, c in undrivable("342 and 327 and 999\n", "")],
           ["342", "327", "999"])
    # Both directions on the counting terms: each term matches a real line,
    # and prose describing a run without reporting one does not.
    for term in TERMS:
        expect("the term %r is matched" % term,
               bool(COUNT_RE.search("5 %s" % term)), True)
    expect("prose is not a count",
           bool(COUNT_RE.search("the suite was green and nothing was wrong")),
           False)
    # A two-digit count is caught by R1 although R2 cannot see it, which is
    # why both rules are here.
    expect("R2 alone would miss a two-digit count",
           bool(BIG_RE.search("12 tracked files")), False)
    expect("R1 catches it", [c for _, c in undrivable("12 tracked files\n", "")],
           ["12 tracked files"])
    # A claim is derivable from ITS OWN number and not from one that merely
    # ends in the same digits, in either rule.
    expect("a count is not satisfied by a longer number",
           [c for _, c in undrivable("12 tracked files\n",
                                     "112 tracked files\n")],
           ["12 tracked files"])
    expect("a big number is not satisfied by a longer one",
           [c for _, c in undrivable("761 things\n", "1761 passed\n")],
           ["761"])
    expect("...and IS satisfied by itself",
           undrivable("761 things\n", "761 passed\n"), [])
    return checks


def selftest():
    checks = run_checks()
    failures = ["%s: %s" % (name, detail)
                for name, ok, detail in checks if not ok]
    if failures:
        print("SELFTEST FAILED: %d" % len(failures))
        for f in failures:
            print("  " + f)
        return 1
    print("selftest: %d rule checks, all as stated" % len(checks))
    return 0


def main(argv):
    if len(argv) == 2 and argv[1] == "--selftest":
        return selftest()
    if len(argv) == 3 and argv[1] in ("--assemble", "--check"):
        rc = selftest()
        if rc:
            return rc
        return assemble(argv[2], argv[1] == "--check")
    print(__doc__.strip().splitlines()[0])
    print("usage: assemble-evidence.py --assemble|--check <report> | --selftest")
    return 2


def lf_stdout():
    """Write LF. The reason in full is in mutation-runner.py's copy of this:
    this instrument's stdout is quoted into a committed report, every file
    under this directory is LF, and a Windows text stream writes CRLF --
    which would make that report mixed, and a mixed report cannot be restored
    byte-for-byte by the control that mutates it."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(newline="\n")


if __name__ == "__main__":
    lf_stdout()
    sys.exit(main(sys.argv))
