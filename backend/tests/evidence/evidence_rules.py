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

WHO THE INVOCATION RULE BINDS (round 11, and it is the correction of round
10's own scope). Round 10 applied the rule to the reports that DECLARED a
`stdout:` header, and required that a round which had one such report have
nothing but such reports. Earlier rounds stay exempt for a reason that holds --
their reports are the record of rounds already judged, on the shapes their
instruments printed at the time, and rewriting one now would be editing a log
to satisfy a rule written after it. But the newest round was identified from
the reports that had ALREADY OPTED IN, so a later round whose reports all
omitted the header moved the answer to that question with them: it was not the
newest adopting round, nothing of it was checked, and the whole rule was
satisfied by a directory that had abandoned it. A check that cannot fail on
the class it exists for is worse than no check (#342).

So the round is derived from the FILE NAMES, which no report can opt out of,
and every report of that round is bound: it names its stdout, it carries a
verbatim run section, and every result in that section has its command above
it. `scope_problems` is that rule and `newest_round` is where the derivation
lives.

WHAT A REPORT MAY CLAIM ABOUT ITS OWN ROUND (round 11, the second correction).
A mutation-controls report lists the controls that are new in its round. That
list was written by hand next to a set that grows, and round 10's credited
itself with a control that a previous round had added and this one had not
touched -- while the module inventory, which tags every control with its
round, said eight. Two statements of one set, and nothing compared them.
`new_control_problems` compares them: what a report lists as new has to be
exactly what the inventory tags for that round, in both directions.
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
    # The invocation frame's own keys. `reports` and `swap` are round 11's:
    # the runner now prints the two reports it DERIVED and the name swap it
    # derived from one of them, and both lines sit in the same frame as
    # `controls` and `started`. A frame key missing from this list is not
    # harmless -- the upward scan stops on the first line it does not
    # recognise, so an unlisted key turns a result whose command IS above it
    # into a reported violation the moment a run prints one after the frame.
    # This list is itself a hand-written set beside a growing one, which is
    # the defect this round is about, so it is extended in the same commit
    # that adds a key rather than when something reds.
    r"|^\s*(file|cwd|python|script|dsn|started|controls|pytest|selection"
    r"|reports|swap)\s"
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


# ── WHO THE RULE BINDS: the round, derived from the file names ──────────────
ROUND = re.compile(r"^r(\d+)-")
STDOUT_HEADER = re.compile(r"^stdout:", re.MULTILINE)


def round_of(name):
    """The round a report's FILE NAME puts it in, or None."""
    hit = ROUND.match(name)
    return int(hit.group(1)) if hit else None


def newest_round(names):
    """The highest round any report name carries.

    Over EVERY name, not over the ones that already satisfy the rule. The
    difference is the whole of round 11's correction: a set derived from the
    reports that opted in moves when they do, so the round that opted out of
    everything moved the scope with it."""
    numbered = [round_of(n) for n in names]
    numbered = [n for n in numbered if n is not None]
    return max(numbered) if numbered else None


def scope_problems(reports):
    """[(name, reason)] for every report of the NEWEST round that is not one
    the assembler built. `reports` is {file name: body}."""
    latest = newest_round(reports)
    if latest is None:
        return [("(the directory)", "carries no round-numbered report, so no "
                                    "round can be bound by this rule")]
    bad = []
    for name in sorted(reports):
        # A report with no round in its NAME would be bound by no round at
        # all, which is the same escape one spelling over: the rule derives
        # the round from the name precisely so that no report can opt out of
        # it, and a name carrying no round opts out by being unparseable. So
        # the naming is part of the rule rather than an assumption under it.
        if round_of(name) is None:
            bad.append((name, "carries no round number in its name, so no "
                              "round's scope reaches it"))
            continue
        if round_of(name) != latest:
            continue
        body = reports[name]
        if not STDOUT_HEADER.search(body):
            bad.append((name, "is a report of round %d and names no stdout of "
                              "its own" % latest))
            continue
        if run_section(body) is None:
            bad.append((name, "names its stdout and carries no verbatim run "
                              "section, so nothing it says traces to a run"))
            continue
        for number, line in results_without_an_invocation(body):
            bad.append((name, "line %d states a result with no invocation "
                              "above it: %s" % (number, line)))
    return bad


# ── WHAT A REPORT MAY CLAIM ABOUT ITS OWN ROUND ─────────────────────────────
# Both shapes are pinned: a heading a report writes for this purpose, and the
# inventory line every control already has. Neither is ordinary prose, so
# neither fires on a sentence nobody meant as a claim (#306).
NEW_CONTROLS_HEADING = re.compile(r"^== this round's [^=]*controls ==\s*$",
                                  re.MULTILINE)
SECTION_BREAK = re.compile(r"^== ", re.MULTILINE)
CONTROL_LINE = re.compile(r"^  ([a-z0-9]+(?:-[a-z0-9]+){2,})\s*$")
INVENTORY_LINE = re.compile(r"^  ([a-z0-9-]+) \(r(\d+)\)")


def controls_claimed_new(body):
    """The control names a report lists as new in its own round, or None when
    it lists none. Read from the NARRATIVE only: the verbatim run below
    carries a `CONTROL <name> -> <test>` line for every control of every
    round, and those are the run's, not the report's claim."""
    narrative = body
    hit = MARKER.search(body)
    if hit is not None:
        narrative = body[:hit.start()]
    heading = NEW_CONTROLS_HEADING.search(narrative)
    if heading is None:
        return None
    rest = narrative[heading.end():]
    end = SECTION_BREAK.search(rest)
    section = rest[:end.start()] if end else rest
    names = []
    for line in section.splitlines():
        found = CONTROL_LINE.match(line)
        if found:
            names.append(found.group(1))
    return names


def inventory_tags(doc, number):
    """The control names the module inventory tags with round `number`."""
    tagged = set()
    for line in doc.splitlines():
        hit = INVENTORY_LINE.match(line)
        if hit and int(hit.group(2)) == number:
            tagged.add(hit.group(1))
    return tagged


def new_control_problems(body, inventory, number):
    """[(name, reason)] where a report's new-control list and the inventory's
    round tags disagree, in either direction."""
    claimed = controls_claimed_new(body)
    if claimed is None:
        return [("(the report)", "lists no controls as new in its round, so "
                                 "it claims nothing this rule can check")]
    tagged = inventory_tags(inventory, number)
    bad = []
    for name in sorted(set(claimed)):
        if claimed.count(name) > 1:
            bad.append((name, "is listed twice as new this round"))
        if name not in tagged:
            bad.append((name, "is listed as new in round %d and the inventory "
                              "tags it for another round, or not at all"
                              % number))
    for name in sorted(tagged - set(claimed)):
        bad.append((name, "is tagged (r%d) in the inventory and the report "
                          "does not list it as new" % number))
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

# THE INVOCATION FRAME, with the keys round 11 added to it. The runner prints
# the two reports it derived and the swap it derived from one of them, in the
# same frame as `controls` and `started`, and a result may follow that frame.
# So the frame is proved to be READ PAST, and -- the half that makes it a
# control rather than a demonstration -- a key the list does NOT know is
# proved to STOP the scan. Without the second half the first would pass
# whatever the list contained, including a list that named nothing (#391).
FABRICATED_FRAMED = (
    "THE RUN, verbatim from here down\n"
    "----------------------------------------\n"
    "command   python backend/tests/evidence/mutation-runner.py\n"
    "  cwd       <repo>\n"
    "  started   2026-09-22 00:00:00 UTC\n"
    "  controls  38, each RED under its mutation and GREEN under an inert edit\n"
    "  reports   <a>-suites.txt (suites), <b>-mutation-controls.txt (controls)\n"
    "  swap      one-name-here -> another-name-here (derived)\n"
    "1734 passed, 42 skipped in 566.55s\n")
# ...and the same frame with one line whose key this list does not carry.
FABRICATED_FRAMED_UNKNOWN = FABRICATED_FRAMED.replace(
    "  swap      one-name-here -> another-name-here (derived)\n",
    "  narrator  a line whose key this rule has never been told about\n")

# A fabricated DIRECTORY, for the scope rule, in the three shapes that matter.
# The reports are keyed by name because the name is what the rule derives the
# round from.
_ADOPTED = "stdout: r2-run.log\n\n" + FABRICATED_WITH
_ADOPTED_EARLIER = "stdout: r1-run.log\n\n" + FABRICATED_WITH
FABRICATED_DIRECTORY = {
    # An early round, kept exactly as its own instruments printed it: no
    # stdout header, and exempt because rewriting it now would edit a log to
    # satisfy a rule written after it.
    "r1-suites.txt": "an early round's report, written before the rule\n",
    "r2-suites.txt": _ADOPTED,
    "r2-mutation-controls.txt": _ADOPTED,
}
# The class round 10's scope could not see: a LATER round that declares no
# stdout anywhere, so it never joined the set the scope was derived from.
FABRICATED_DIRECTORY_OPTED_OUT = dict(FABRICATED_DIRECTORY)
FABRICATED_DIRECTORY_OPTED_OUT.update({
    "r3-suites.txt": "a later round's report, with no stdout header\n",
    "r3-mutation-controls.txt": "and neither has this one\n",
})
# ...and half of one, which round 10's clause did catch and this one still has
# to.
FABRICATED_DIRECTORY_HALF = dict(FABRICATED_DIRECTORY)
FABRICATED_DIRECTORY_HALF.update({
    "r3-suites.txt": "stdout: r3-run.log\n\n" + FABRICATED_WITH,
    "r3-mutation-controls.txt": "no stdout header on this half\n",
})
# ...and the escape one spelling over: a report whose NAME carries no round.
FABRICATED_DIRECTORY_UNNAMED = dict(FABRICATED_DIRECTORY)
FABRICATED_DIRECTORY_UNNAMED["summary.txt"] = "a report belonging to no round\n"

# The fabricated report and inventory the new-controls rule is proved on.
FABRICATED_REPORT = (
    "A mutation controls report.\n"
    "\n"
    "stdout: r3-run.log\n"
    "\n"
    "== this round's new controls ==\n"
    "  a-thing-that-broke\n"
    "      What it mutates.\n"
    "\n"
    "  another-thing-that-broke\n"
    "      What that one mutates.\n"
    "\n"
    "== a later section ==\n"
    "  not-a-claim-about-this-round\n"
    "\n" + FABRICATED_WITH)
FABRICATED_INVENTORY = (
    "  an-older-control (r2)  what it does\n"
    "  a-thing-that-broke (r3)  what it does\n"
    "  another-thing-that-broke (r3)  what it does\n")


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

    # ── the invocation frame's keys, both directions ────────────────────────
    if results_without_an_invocation(FABRICATED_FRAMED):
        problems.append(
            "a result below the runner's own invocation frame was reported as "
            "having no command above it, so a frame key is missing from "
            "BETWEEN: %r" % (results_without_an_invocation(FABRICATED_FRAMED),))
    if not results_without_an_invocation(FABRICATED_FRAMED_UNKNOWN):
        problems.append(
            "a frame carrying a key this rule does not know was read past "
            "anyway, so the key list is not what stops the upward scan and "
            "the direction above proves nothing")

    # ── the scope rule, both directions, on a fabricated directory ──────────
    if newest_round(FABRICATED_DIRECTORY_OPTED_OUT) != 3:
        problems.append("the newest round was not derived from the file names")
    if scope_problems(FABRICATED_DIRECTORY):
        problems.append("a round whose reports all name their stdout was "
                        "refused, and an earlier round's report that names "
                        "none has to stay exempt: %r"
                        % (scope_problems(FABRICATED_DIRECTORY),))
    opted_out = sorted(n for n, _why in
                       scope_problems(FABRICATED_DIRECTORY_OPTED_OUT))
    if opted_out != ["r3-mutation-controls.txt", "r3-suites.txt"]:
        problems.append("a later round that declared no stdout at all was not "
                        "refused, which is the scope round 10 could not see: "
                        "%r" % (opted_out,))
    half = sorted(n for n, _why in scope_problems(FABRICATED_DIRECTORY_HALF))
    if half != ["r3-mutation-controls.txt"]:
        problems.append("a round that adopted the rule for one report and not "
                        "the other was not refused: %r" % (half,))
    unnamed = sorted(n for n, _why in
                     scope_problems(FABRICATED_DIRECTORY_UNNAMED))
    if unnamed != ["summary.txt"]:
        problems.append("a report whose name carries no round was not "
                        "refused, so the scope could be left by naming: %r"
                        % (unnamed,))
    # ...and a result with no invocation is still refused inside the scope,
    # or the scope rule would pass a report that named a stdout and nothing
    # else.
    broken = dict(FABRICATED_DIRECTORY)
    broken["r2-suites.txt"] = "stdout: r2-run.log\n\n" + FABRICATED_WITHOUT
    if not scope_problems(broken):
        problems.append("a bound report whose result has no invocation above "
                        "it was accepted")

    # ── the new-controls rule, both directions ──────────────────────────────
    if new_control_problems(FABRICATED_REPORT, FABRICATED_INVENTORY, 3):
        problems.append(
            "a report listing exactly the controls the inventory tags for its "
            "round was refused: %r"
            % (new_control_problems(FABRICATED_REPORT, FABRICATED_INVENTORY,
                                    3),))
    # A control from ANOTHER round credited to this one -- the defect itself.
    credited = FABRICATED_REPORT.replace("  another-thing-that-broke\n",
                                         "  an-older-control\n")
    named = sorted(n for n, _why in
                   new_control_problems(credited, FABRICATED_INVENTORY, 3))
    if named != ["an-older-control", "another-thing-that-broke"]:
        problems.append("a control of another round listed as new was not "
                        "refused, in both directions: %r" % (named,))
    # ...and a control added to the inventory and left out of the report.
    missing_one = FABRICATED_REPORT.replace("  a-thing-that-broke\n", "")
    named = sorted(n for n, _why in
                   new_control_problems(missing_one, FABRICATED_INVENTORY, 3))
    if named != ["a-thing-that-broke"]:
        problems.append("a control the inventory tags for this round and the "
                        "report does not list was not refused: %r" % (named,))
    # ...and the names under a LATER heading are not this round's claim.
    if "not-a-claim-about-this-round" in str(
            controls_claimed_new(FABRICATED_REPORT)):
        problems.append("the claim reader ran past the end of its section")
    # ...and a report that makes no claim at all is refused rather than exempt,
    # which is the same hole the scope rule closes one level up.
    if not new_control_problems("no heading here\n", FABRICATED_INVENTORY, 3):
        problems.append("a report that lists no new controls was treated as "
                        "making no claim to check")
    return problems
