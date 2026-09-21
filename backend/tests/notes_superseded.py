"""A superseded claim must carry its marker ON THE LINE, not twelve pages away.

WHY THIS EXISTS
  A lens pass over round 2 of bug 392 found a paragraph still stating, word for
  word, a property the round had replaced. The replacement WAS recorded -- in a
  later section, twelve pages on. The reading order the notes themselves give
  sends a cold reader through that later section and then back through the
  earlier one, so the reader finishes on the refuted version.

  That was repaired by hand, in prose, with no check under it. Which means the
  repair holds exactly until someone re-flows the file, restores an older
  paragraph, or quotes the old wording in a new section without thinking. The
  gate said so: a claim whose only witness is a paragraph is not closed (#391).

THE RULE
  Each entry below is a phrase that a round RETIRED. Wherever a phrase still
  occurs, the marker word must be on the SAME line or within a short run of
  lines above it -- close enough that a reader meets the marker before the
  claim, which is the whole property. Anything further away does not count,
  because distance is the defect.

  The window is deliberately small. A rule that accepted a marker anywhere in
  the file would pass the exact arrangement this exists to catch (#342).

Usage:

    python backend/tests/notes_superseded.py --notes <file>
    python backend/tests/notes_superseded.py --self-test

Exit codes: 0 every superseded phrase is marked, 1 at least one is not, 2 the
self-test failed or the input was unreadable.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MARKER = "SUPERSEDED"
# How many lines above an occurrence the marker may sit and still be read
# first. Two covers a marked block whose quoted text begins on the next line;
# it does not cover a marker in another section.
WINDOW = 3

# (rule name, the retired phrase). The phrases are the ones a round replaced;
# each is narrow enough that ordinary prose cannot trip it.
RETIRED = (
    ("site-counter-is-main-only", re.compile(r"counts the sites in `main\.py`")),
    ("no-site-is-a-branch", re.compile(r"asserts none of them is a branch")),
)


def offences(lines: list[str]) -> list[tuple[int, str]]:
    """[(line number, rule name)] for every retired phrase with no marker near it."""
    out = []
    for i, line in enumerate(lines):
        for name, rx in RETIRED:
            if not rx.search(line):
                continue
            window = lines[max(0, i - WINDOW):i + 1]
            if not any(MARKER in w for w in window):
                out.append((i + 1, name))
    return out


def _self_test() -> int:
    """Plant the marked and the unmarked arrangement and require them apart."""
    unmarked = ["intro", "the test counts the sites in `main.py` and is current", "outro"]
    same_line = ["intro",
                 "SUPERSEDED: it counts the sites in `main.py` — not what ships",
                 "outro"]
    block = ["> **SUPERSEDED in round 2** — this paragraph used to read:",
             "> the test counts the sites in `main.py` (one INSERT column)",
             "> and asserts none of them is a branch."]
    far_away = ["SUPERSEDED, somewhere else entirely"] + ["filler"] * 10 + \
               ["the test counts the sites in `main.py` and is current"]
    similar = ["intro", "the census counts the sites across the repository", "outro"]

    checks = {
        "an unmarked retired phrase is reported": offences(unmarked) == [
            (2, "site-counter-is-main-only")],
        "the marker on the same line clears it": not offences(same_line),
        "a marked block clears the lines inside it": not offences(block),
        "a marker in another section does NOT clear it":
            offences(far_away) == [(12, "site-counter-is-main-only")],
        "a similar sentence that is not the retired phrase stays green":
            not offences(similar),
        "both rules are reachable":
            {n for _i, n in offences(["counts the sites in `main.py`",
                                      "asserts none of them is a branch"])}
            == {"site-counter-is-main-only", "no-site-is-a-branch"},
        "the rule table parses to something": bool(RETIRED),
    }
    for k, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {k}")
    bad = [k for k, ok in checks.items() if not ok]
    print("SELF-TEST:", "marked and unmarked separated" if not bad else f"FAILED: {bad}")
    return 2 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--notes", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.notes or not args.notes.is_file():
        ap.error("--notes must name a file, or give --self-test")
    if not RETIRED:
        print("REFUSING: the rule table is empty; this check would pass anything.")
        return 2
    lines = args.notes.read_text(encoding="utf-8").splitlines()
    bad = offences(lines)
    print(f"notes   : {args.notes.name}, {len(lines)} lines")
    print(f"rules   : {len(RETIRED)} retired phrases, marker {MARKER!r}, "
          f"window {WINDOW} lines")
    for lineno, name in bad:
        print(f"{args.notes.name}:{lineno}: UNMARKED {name}")
    print(f"UNMARKED: {len(bad)}")
    print("VERDICT:", "every superseded phrase carries its marker in place"
          if not bad else f"{len(bad)} superseded phrases stand unmarked")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
