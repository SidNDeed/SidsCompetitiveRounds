"""The rules this directory enforces on its own reports, in ONE place.

The evidence check in `backend/tests/test_ffa_game_number_anchor.py` reads
these, and so does the re-pin wrapper, which has to apply them to the one file
that cannot be covered by a pytest run: its own output, written after that run
by construction. A rule with two implementations is a rule that drifts, and
the half nobody re-reads is the half that stops matching (#432), so there is
one implementation and two callers.

THE INVOCATION RULE (round 10, the r6 LOW). A committed report that shows a
result with no record of the command that produced it is a number from a
selection nobody can rebuild -- a different selection prints the same shape.
The check before this round asked only that a report carry SOME executed
result, so a later log could drop its command line and stay green, which is a
check that cannot fail on the class it exists for (#342).

It applies to the VERBATIM RUN SECTION of a report, not to its prose: a
narrative legitimately quotes a number in a sentence, and demanding a command
line above every such sentence would be a rule about writing rather than about
evidence.
"""
import re

# A line that records what was run.
INVOCATION = re.compile(r"^\s*(command\b|INVOCATION\b)")

# A line that reports a result. Broader than the evidence check's
# `result_token`, deliberately: THAT pattern decides whether a file carries an
# executed result at all, so widening it makes a check easier to satisfy. This
# one decides which lines DEMAND an invocation, so widening it makes the rule
# stricter. Two patterns, opposite directions, one job each.
RESULT = re.compile(r"\d+ passed|\d+ paths|RED:|rows rewritten now"
                    r"|rows identical|second run")

# What may legitimately sit BETWEEN an invocation and the result it produced:
# a tool's own frame and its detail lines, and nothing else. A `=== phase ===`
# marker is deliberately NOT here -- it starts a new run, so a result whose
# nearest substantive line above it is a phase marker is a result whose own
# command is missing. A heavily `=`-framed line WITH text in it is pytest's
# own section frame and is skipped, which is why the assembler's block banner
# is written in that shape rather than as a phase marker.
BETWEEN = re.compile(
    r"^\s*$"
    r"|^[=\-]{3,}\s*$"
    r"|^={10,} [^=]+ ={10,}\s*$"
    r"|^\s*\S+ rc=-?\d+"
    r"|^\s*(mutant|inert)\s+rc="
    r"|^\s*RED: "
    r"|^-- Docs:"
    # pytest's own header keys. `collecting ` is here as well as
    # `collected `, because a verbose run prints one line that begins
    # `collecting ... collected N items / M deselected / K selected` -- and
    # a pattern that only knew the second spelling stopped the upward scan
    # on pytest's own frame and reported the summary below it as a result
    # with no command. The line is the tool's, not the author's.
    r"|^(platform |rootdir:|plugins:|collecting |collected |configfile:"
    r"|cachedir:|asyncio)"
    # A pytest -v NODE line: `tests/x.py::test_name PASSED [ 42%]`. Two things
    # about this shape, both read off a log rather than guessed. It carries the
    # node prefix rather than being a bare `(PASSED|...)` alternative, because
    # this pattern is applied with `re.match`, which anchors the whole
    # alternation at position 0 -- so an alternative with no `^` of its own is
    # anchored anyway and never matches a line that begins with the node id.
    # And the part after `::` is `.*` rather than `\S+`, because a
    # PARAMETRISED id can contain spaces (`...[ yes -True]`), which was the one
    # line in a verbose run of this suite that the tighter form could not see.
    # The bare form below is kept for a line that really does start with the
    # verdict.
    r"|^\S+::.*(PASSED|SKIPPED|XFAIL|XPASS)"
    r"|^(PASSED|SKIPPED|XFAIL|XPASS)"
    r"|^[.sxXfFEup]+\s*\[\s*\d+%\]\s*$"
    r"|^\s*[0-9a-f]{32}\s+\S+\s*$"
    r"|^\s*(file|cwd|python|script|dsn|started|controls|pytest|selection)\s"
    r"|^\s*(manifest rows|fingerprinted|MOVED vs HEAD|ENTRY POINTS|\(dry run)")

MARKER = re.compile(r"^THE RUNS?, verbatim from here down\s*$", re.MULTILINE)


def run_section(body: str):
    """The verbatim part of a report, or None when it declares none."""
    hit = MARKER.search(body)
    if hit is None:
        return None
    return body[hit.end():]


def results_without_an_invocation(body: str):
    """[(line number, text)] for every result whose command is not above it.

    Scanning upward from the result, the lines a tool prints between a command
    and its output are skipped, and everything else has to BE the command."""
    section = run_section(body)
    if section is None:
        return []
    lines = section.splitlines()
    bad = []
    for i, line in enumerate(lines):
        if not RESULT.search(line) or INVOCATION.match(line):
            continue
        j = i - 1
        while j >= 0 and (BETWEEN.match(lines[j])
                          and not INVOCATION.match(lines[j])):
            j -= 1
        if j < 0 or not INVOCATION.match(lines[j]):
            bad.append((i + 1, line.strip()[:70]))
    return bad


# The fabricated pair the rule is proved on, kept here so the test and the
# re-pin wrapper assert the SAME two directions rather than two hand-written
# approximations of them (#391: a control with a negative control, and both
# of them about the rule rather than about whatever the directory holds).
FABRICATED_WITH = (
    "THE RUN, verbatim from here down\n"
    "----------------------------------------\n"
    "command   python -m pytest tests/ -q\n"
    "opt-out rc=0\n"
    "collecting ... collected 3 items / 0 deselected / 3 selected\n"
    # A -v node line and a wrapped one, because an instrument that runs pytest
    # verbosely puts one of these per test between the command and the summary
    # and the rule has to read past them. They are the lines the first version
    # of this pattern could not see.
    "tests/test_x.py::test_a_name PASSED [ 33%]\n"
    "tests/test_x.py::test_another_name SKIPPED [ 66%]\n"
    "tests/test_x.py::test_parametrised[ yes -True] PASSED [100%]\n"
    "-- Docs: https://docs.pytest.org/\n"
    "1734 passed, 42 skipped, 1 xfailed in 566.55s\n")
FABRICATED_WITHOUT = FABRICATED_WITH.replace(
    "command   python -m pytest tests/ -q\n",
    "the command for this half is not recorded\n")


def selftest():
    """Both directions on the rule itself: 0 clean, 1 with the reason."""
    problems = []
    if results_without_an_invocation(FABRICATED_WITH):
        problems.append("a log WITH its invocation was refused")
    missing = [text for _n, text in
               results_without_an_invocation(FABRICATED_WITHOUT)]
    if missing != ["1734 passed, 42 skipped, 1 xfailed in 566.55s"]:
        problems.append("a log WITHOUT its invocation was not refused: %r"
                        % (missing,))
    if run_section("no marker here\n") is not None:
        problems.append("a report with no marker reported a run section")
    if run_section(FABRICATED_WITH) is None:
        problems.append("a report with a marker reported no run section")
    # ...and a line that is NOT part of any tool's frame must still break the
    # chain, or the two directions above pass on a rule that skips everything.
    # This is the negative control for the widening the node line needed.
    opaque = FABRICATED_WITH.replace(
        "tests/test_x.py::test_a_name PASSED [ 33%]\n",
        "a note somebody typed into the log\n")
    if not results_without_an_invocation(opaque):
        problems.append("a line that is not a tool's own frame was skipped, "
                        "so the rule would pass over an edited log")
    return problems
