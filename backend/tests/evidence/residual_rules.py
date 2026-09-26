"""A residual list states its integrity reach per item, and counts it once.

A round's residual list is the one place the round says what it did NOT close,
and a reader sizes the round from it. So the list is the place a summary
sentence is most expensive to get wrong: it is read by somebody who is
deliberately not reading the rest.

THE DEFECT THIS EXISTS FOR. One list carried two statements sixteen lines
apart. An item said two seats one number apart "can still both settle" -- a
second settlement of one physical game, which pays a second time -- and a later
item said it was "the one item in this list that can move a rating". Both were
written by the same hand in the same pass, and nothing could compare them,
because one was an item's prose and the other was a count somebody carried in
their head (#351: a sentence asserting a property of the whole state space is
usually written from the one state its author had in mind).

THE RULE. The reach is stated ONCE PER ITEM, in a pinned shape, and any count
of it is DERIVED from those tags rather than asserted beside them:

    - **An item.** Its prose, which describes the mechanism and not the reach.
      **Integrity reach:** can move a rating.

    **Can move a rating: 2 of 5.** ...the definition paragraph...

and nothing else in the section may make a claim in that vocabulary. That last
clause is the one that reds on the defect above: a sentence carrying the phrase
outside a tag and outside the tally paragraph is exactly the hand-counted
summary that went stale.

    python backend/tests/evidence/residual_rules.py --selftest
    python backend/tests/evidence/residual_rules.py <document>

THE DOCUMENT IS AN ARGUMENT AND IS NOT NAMED HERE. The list this lane checks
lives under the gitignored scratch, and a committed file may not send a reader
to a path this repository does not contain -- the same reason the citation pin
takes both of its documents as arguments. The rule is committed; the
invocation that ran it is recorded in this round's report.

It reads the document and writes nothing.
"""
import io
import re
import sys

# The pinned shapes. Each is WRITTEN for this purpose: a rule keyed on ordinary
# prose is a rule that fires on a sentence nobody meant as a claim, and one
# keyed on a shape nobody writes by accident fires on exactly the claim (#306).
TALLY = re.compile(r"^\*\*Can move a rating: (\d+) of (\d+)\.\*\*")
TAG = re.compile(r"^\s*\*\*Integrity reach:\*\*\s+(can|cannot) move a rating\.\s*$")
BULLET = re.compile(r"^- ")
HEADING = re.compile(r"^#{1,6} ")

# The vocabulary the tags own. Collapsed across line breaks before it is
# searched for, because a claim that wrapped between "move a" and "rating"
# would otherwise pass a per-line search -- and wrapping is what a text editor
# does to every long sentence in a document like this.
PHRASE = re.compile(r"move[sd]?\s+(?:a|the|any)\s+rating", re.I)


def _section_of(lines, tally_index):
    """The heading block the tally sits in: (start, end) over `lines`."""
    start = 0
    for i in range(tally_index, -1, -1):
        if HEADING.match(lines[i]):
            start = i
            break
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if HEADING.match(lines[i]):
            end = i
            break
    return start, end


def _tally_paragraph(lines, tally_index, end):
    """The tally line and the lines under it up to the next blank line.

    The definition of the tag lives here, immediately under the count it
    explains, so the one paragraph that is allowed to use the vocabulary is
    the one the reader is looking at when they read the number."""
    out = [tally_index]
    for i in range(tally_index + 1, end):
        if not lines[i].strip():
            break
        out.append(i)
    return out


def reach_problems(doc):
    """[] when the list is as stated, else one string per problem."""
    lines = doc.splitlines()
    hits = [i for i, line in enumerate(lines) if TALLY.match(line)]
    if len(hits) != 1:
        return ["the document carries %d reach tallies in the pinned shape "
                "`**Can move a rating: N of M.**`, and the rule needs exactly "
                "one" % len(hits)]
    tally_index = hits[0]
    start, end = _section_of(lines, tally_index)
    exempt = set(_tally_paragraph(lines, tally_index, end))

    problems = []
    # Every bullet of the section carries exactly one tag. A bullet runs from
    # its own marker to the next one, to the tally, or to the end of the
    # section -- whichever comes first.
    starts = [i for i in range(start, end)
              if BULLET.match(lines[i]) and i < tally_index]
    for n, first in enumerate(starts):
        last = starts[n + 1] if n + 1 < len(starts) else tally_index
        tags = [i for i in range(first, last) if TAG.match(lines[i])]
        if len(tags) != 1:
            problems.append(
                "the item at line %d carries %d integrity-reach tags and the "
                "rule needs exactly one: %s"
                % (first + 1, len(tags), lines[first].strip()[:60]))
    if not starts:
        problems.append("the section around the tally carries no items, so "
                        "the tally counts nothing")

    tagged = [TAG.match(lines[i]) for i in range(start, end)]
    tagged = [m for m in tagged if m]
    can = sum(1 for m in tagged if m.group(1) == "can")
    claimed = TALLY.match(lines[tally_index])
    want_can, want_total = int(claimed.group(1)), int(claimed.group(2))
    if (want_can, want_total) != (can, len(starts)):
        problems.append(
            "the tally says %d of %d and the tags say %d of %d"
            % (want_can, want_total, can, len(starts)))

    # ...and the vocabulary is the tags'. Anything else in the section that
    # speaks it is a second statement of the same fact, which is the pair that
    # went stale.
    rest = [lines[i] for i in range(start, end)
            if i not in exempt and not TAG.match(lines[i])]
    collapsed = re.sub(r"\s+", " ", " ".join(rest))
    for hit in PHRASE.finditer(collapsed):
        lo = max(0, hit.start() - 60)
        problems.append(
            "the section states the reach outside a tag and outside the tally "
            "paragraph: ...%s..." % collapsed[lo:hit.end() + 10].strip())
    return problems


# ── the fixtures the rule is proved on, both directions ─────────────────────
CLEAN = """# A document

## Another section

Nothing here.

### 9.9 What this does not close

- **An item that loses a result.** Nothing is paid and nothing is recorded.
  **Integrity reach:** cannot move a rating.
- **An item that settles one game twice.** Two answers a moment apart name two
  numbers, and each is accepted as its own game, so one sitting pays out
  twice.
  **Integrity reach:** can move a rating.
- **An item that needs an operator.** The row waits until somebody settles it
  by hand, and settling it pays a second time.
  **Integrity reach:** can move a rating.

**Can move a rating: 2 of 3.** The count is derived from the tags above; "can
move a rating" means the case can produce a rating, gold or XP award the rules
do not intend, or a second one for a game already paid.

### 9.10 The next section

Not part of the list.
"""

# The defect itself: a hand-counted summary beside the tags, and WRAPPED, so a
# per-line search would not see it.
DIRTY_CLAIM = CLEAN.replace(
    "- **An item that needs an operator.** The row waits until somebody settles"
    " it\n  by hand, and settling it pays a second time.\n",
    "- **An item that needs an operator.** The row waits until somebody settles"
    " it\n  by hand. This is the one item in this list that can move a\n"
    "  rating.\n")
DIRTY_UNTAGGED = CLEAN.replace(
    "  by hand, and settling it pays a second time.\n"
    "  **Integrity reach:** can move a rating.\n",
    "  by hand, and settling it pays a second time.\n")
DIRTY_COUNT = CLEAN.replace("**Can move a rating: 2 of 3.**",
                            "**Can move a rating: 1 of 3.**")
DIRTY_NO_TALLY = CLEAN.replace("**Can move a rating: 2 of 3.** The count",
                               "The count")
# The negative control: an edit at the same site that changes no claim.
INERT = CLEAN.replace("Two answers a moment apart name two",
                      "Two answers a moment apart  name two")


def selftest_checks():
    """Every check this rule makes about itself, as (name, ok, detail).

    Returned as records rather than counted afterwards, so the number this
    instrument prints is the number of checks it ran. A count written as a
    constant beside the checks is a number the run did not produce, which is
    the defect one of this round's other findings is about."""
    checks = []

    def expect(name, got, want):
        checks.append((name, got == want,
                       None if got == want else "%r, expected %r" % (got, want)))

    expect("a list as stated is clean", len(reach_problems(CLEAN)), 0)
    expect("an inert reword is still clean", len(reach_problems(INERT)), 0)
    expect("a prose reach claim is refused",
           len(reach_problems(DIRTY_CLAIM)), 1)
    expect("an untagged item is refused",
           len(reach_problems(DIRTY_UNTAGGED)), 2)
    expect("a tally that disagrees is refused",
           len(reach_problems(DIRTY_COUNT)), 1)
    expect("a list with no tally is refused",
           len(reach_problems(DIRTY_NO_TALLY)), 1)
    # ...and each refusal is about the thing it names, rather than merely
    # non-empty: a rule that refuses everything for one reason would pass the
    # six counts above and say nothing true.
    expect("the prose refusal quotes the claim it found",
           "one item in this list" in " ".join(reach_problems(DIRTY_CLAIM)),
           True)
    expect("the tally refusal states the two counts",
           "1 of 3" in " ".join(reach_problems(DIRTY_COUNT)), True)
    return checks


def selftest():
    """Both directions on the rule itself: [] clean, else the reasons."""
    return ["%s: %s" % (name, detail)
            for name, ok, detail in selftest_checks() if not ok]


def main(argv):
    if len(argv) == 2 and argv[1] == "--selftest":
        checks = selftest_checks()
        bad = [(n, d) for n, ok, d in checks if not ok]
        if bad:
            print("SELFTEST FAILED: %d" % len(bad))
            for name, detail in bad:
                print("  %s: %s" % (name, detail))
            return 1
        print("selftest: %d rule checks, all as stated" % len(checks))
        return 0
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[0])
        print("usage: residual_rules.py <document> | --selftest")
        return 2
    bad = selftest()
    if bad:
        print("REFUSED: the rule does not hold in both directions:")
        for line in bad:
            print("  " + line)
        return 2
    with io.open(argv[1], "r", encoding="utf-8", errors="replace") as fh:
        doc = fh.read()
    found = reach_problems(doc)
    if found:
        print("REFUSED: %d problem(s) in the residual list:" % len(found))
        for line in found:
            print("  " + line)
        return 1
    print("CLEAN: every item carries one integrity-reach tag, the tally is "
          "the tags' own count, and no other line states a reach")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
