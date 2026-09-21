"""Check that a round's evidence log obeys the round's own evidence law.

WHY THIS EXISTS
  The law this lane runs under says: every invocation is PRINTED ABOVE its
  result, and a result with no invocation above it is not evidence. Round 3
  wrote five logs under that law and broke it twice. One section -- an INERT
  TWIN, half of a specificity control -- carried no invocation at all: its
  "result" was a re-quotation of the section above it, so the twin's green
  rested on prose. Another verified a file whose name never appeared in the
  step that produced it.

  Both were caught by a reader, afterwards. A law that only a reader enforces
  is a convention, and conventions decay exactly where the work is dullest --
  the twin, the control, the section nobody expects to move. So the law gets
  what every other claim in this lane gets: a check, with a mutation that
  reddens and an inert twin that does not (#391, #302).

THE THREE LAWS, AS THE CHECKER READS THEM
  1. Every result marker `[exit N]` has a `$ ` invocation above it, with no
     other result marker in between. A result no command produced is prose.
  2. Every invocation is followed by a result marker before the next
     invocation. A command printed and never run is worse than prose: it looks
     reproducible.
  3. Every section that ASSERTS an outcome -- a control, a twin, a verdict --
     contains at least one invocation. This is the one that catches the case
     the round actually produced: a section whose text says RED or GREEN while
     nothing in it was run.

  Commentary between an invocation and its result is fine: these logs write
  `-- ` notes, and a note is not a result. The check is about what PRODUCED a
  result, never about how much prose sits around it.

WHAT IT DELIBERATELY DOES NOT DO
  It does not judge whether a result is the RIGHT one, or whether a control
  reddened for the right reason. It answers one question -- can each result be
  traced to a command -- and answers it mechanically. A checker that tried to
  judge the content would need the tree the log was written against, which is
  the thing a log exists to outlive.

Usage:

    python backend/tests/evidence_log.py <log> [<log> ...]
    python backend/tests/evidence_log.py --self-test

Exit codes: 0 every result traces to an invocation, 1 at least one does not,
2 an input was unreadable or the self-test failed.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

INVOCATION = re.compile(r"^\$ \S")
RESULT = re.compile(r"^\[exit (-?\d+)\]\s*$")
SECTION = re.compile(r"^#{2,3} .*")
# A line that asserts an outcome. These are the words this lane's logs use to
# close a control, a twin or a run. A section carrying one of them is claiming
# something happened, and something that happened has an invocation.
ASSERTION = re.compile(
    r"^(?:CONTROL|TWIN|VERDICT|SELF-TEST|GUARD CONTROL [A-Z]|EXTRACT|VERIFY|SEAL)\b"
    r"|\b(?:RED as required|GREEN as required|DID NOT FIRE)\b")


def offences(text: str) -> list[str]:
    """Every place the log departs from the three laws, in order.

    Returned rather than counted: a count of departures with no listing under
    it is the same shape of evidence this file exists to refuse (#304).
    """
    bad: list[str] = []
    lines = text.splitlines()
    pending_invocation: tuple[int, str] | None = None
    section = (0, "<before the first section>")
    section_had_invocation = False
    section_assertions: list[tuple[int, str]] = []

    def close_section():
        if section_assertions and not section_had_invocation:
            n, t = section_assertions[0]
            bad.append(f"{section[0]}: section {section[1]!r} asserts an outcome "
                       f"at line {n} ({t[:60]!r}) and carries no invocation -- "
                       "a result with no invocation above it is not evidence")

    for n, line in enumerate(lines, 1):
        if SECTION.match(line):
            close_section()
            section = (n, line.strip("# ").strip())
            section_had_invocation = False
            section_assertions = []
            continue
        if INVOCATION.match(line):
            if pending_invocation is not None:
                bad.append(f"{pending_invocation[0]}: invocation "
                           f"{pending_invocation[1][:60]!r} has no result marker "
                           "beneath it before the next invocation")
            pending_invocation = (n, line)
            section_had_invocation = True
            continue
        if RESULT.match(line):
            if pending_invocation is None:
                bad.append(f"{n}: result marker {line.strip()!r} has no invocation "
                           "above it -- it cannot be traced to a command")
            pending_invocation = None
            continue
        if ASSERTION.search(line):
            section_assertions.append((n, line.strip()))
    close_section()
    if pending_invocation is not None:
        bad.append(f"{pending_invocation[0]}: invocation "
                   f"{pending_invocation[1][:60]!r} has no result marker beneath it")
    return bad


def _self_test() -> int:
    """Plant each shape and require the checker to separate it from its twin.

    Every mutation here has an INERT TWIN at the same site: the same section,
    the same assertion, differing only in the thing the law is about. A checker
    that reddened for both would say only that the text changed (#391).
    """
    traced = "### 3. a control ###\n$ python tool.py --flag\nsome output\n[exit 1]\nCONTROL: RED as required\n"
    untraced = "### 3. a control ###\nsome output\nCONTROL: RED as required\n"
    noted = ("### 3. a control ###\n$ python tool.py --flag\n"
             "-- a note between the invocation and its result\nsome output\n[exit 1]\n"
             "CONTROL: RED as required\n")
    orphan_result = "### 4. ###\nsome output\n[exit 0]\n"
    orphan_invocation = "### 4. ###\n$ python tool.py\n$ python other.py\n[exit 0]\n"
    quiet_section = "### 5. notes only ###\nthis section asserts nothing at all.\n"
    trailing = "### 6. ###\n$ python tool.py\n"

    checks = {
        # LAW 3, the shape round 3 produced, and its twin.
        "a section asserting an outcome with no invocation is caught":
            bool(offences(untraced)),
        "the SAME section with its invocation restored is green":
            not offences(traced),
        "a note between an invocation and its result is not an offence":
            not offences(noted),
        # LAW 1 and its twin.
        "a result marker with no invocation above it is caught":
            bool(offences(orphan_result)),
        "the same result marker WITH one above it is green":
            not offences("### 4. ###\n$ python tool.py\n[exit 0]\n"),
        # LAW 2 and its twin.
        "an invocation with no result before the next one is caught":
            bool(offences(orphan_invocation)),
        "two invocations each carrying a result are green":
            not offences("### 4. ###\n$ a\n[exit 0]\n$ b\n[exit 0]\n"),
        "an invocation at the end of the log with no result is caught":
            bool(offences(trailing)),
        # The other direction of #342: a section that claims nothing needs
        # nothing, or every prose section in every log would be an offence and
        # the check would be ignored.
        "a section that asserts nothing needs no invocation":
            not offences(quiet_section),
        "the offence names the line it is about":
            offences(orphan_result)[0].startswith("3:"),
        "a listing is returned, not a count":
            isinstance(offences(orphan_invocation), list),
    }
    for k, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {k}")
    bad = [k for k, ok in checks.items() if not ok]
    print("SELF-TEST:", "every shape separated" if not bad else f"FAILED: {bad}")
    return 2 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="*", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="strict")
        except (AttributeError, ValueError, OSError):
            pass
    if args.self_test:
        return _self_test()
    if not args.logs:
        ap.error("name at least one log, or give --self-test")
    total = 0
    for log in args.logs:
        if not log.is_file():
            print(f"REFUSING: not a file: {log.name}")
            return 2
        bad = offences(log.read_text(encoding="utf-8", errors="replace"))
        total += len(bad)
        for line in bad:
            print(f"{log.name}:{line}")
        print(f"{log.name}: {len(bad)} offences")
    print("EVIDENCE LAW:", "every result traces to an invocation" if not total
          else f"{total} results or invocations cannot be traced")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
