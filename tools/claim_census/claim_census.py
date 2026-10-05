#!/usr/bin/env python3
"""Claim census (V7, F3): list every closure claim about the commit bound; zero required.

Usage: python claim_census.py FILE [FILE ...]
Prints one line per hit, "file:line: rule: sentence", then a total.
Exit 0 when there is no hit, 1 when there is one or more, 3 when a file cannot be read.

What is exempt, and why: fenced code blocks (this script's own patterns), blockquote lines (a
verbatim judgement quotes the phrases it withdraws) and inline code spans (a withdrawn phrase
recorded as history is quoted in backticks). Everything else is prose and is censused.

Rules (case-insensitive, per sentence; a table cell counts as a sentence):
  NOEXC   "no exceptions", "no-exceptions", "without (an|any) exception", "with no exception"
          (not "no exception text/type", which is about exception strings)
  COMPL   "completion deadline", "completion bound", "bounds every commit"
  UNCOND  "unconditional(ly)" in a sentence that also names the bound: deadline, commit, COMMIT,
          bound, threshold, round trip, timeout or "T0+" (not "unconditional UPDATE" or
          "unconditional-grant", which name a SQL write, nor a backticked span)
  PROMPT  "what a prompt one would" (an equivalence between a late COMMIT and a prompt one)
  FIG     a numeric commit, decision or read figure: committed/commits/commit/decided/decides/
          decide/read/reads, then by/at/in/within/before/after, then a figure ("+49", "T0+55",
          "theta+9", "commit + 9", "[+40, +49]", optionally in bold, or a duration "9 s"), in a
          sentence that does not also say "completed" (the completed eligible round trip every
          figure is conditioned on, sec3.3)
"""
import re
import sys

RULES = [
    ("NOEXC", re.compile(r"\bno[ -]exceptions?\b(?!\s+(?:text|type|types|string))|\bwithout (?:an |any )?exceptions?\b|\bwith no exceptions?\b", re.I)),
    ("COMPL", re.compile(r"\bcompletion (?:deadline|bound)s?\b|\bbounds every commit\b", re.I)),
    ("PROMPT", re.compile(r"\bwhat a prompt one would\b", re.I)),
]
UNCOND = re.compile(r"\bunconditional(?:ly)?\b(?!\s*(?:UPDATE|CODE|-?grant))", re.I)
BOUNDWORD = re.compile(r"\b(?:deadline|commit\w*|bound\w*|threshold|round trips?|timeout)\b|T0 ?\+", re.I)
FIG = re.compile(r"\b(?:committed|commits|commit|decided|decides|decide|read|reads)\s+"
                 r"(?:by|at|in|within|before|after)\s+(?:\*\*)?\[?\s*"
                 r"(?:(?:T0|theta|\u03b8|commit)\s*)?(?:\+\s*\d+|\d+(?:\.\d+)?\s*s\b)", re.I)
COMPLETED = re.compile(r"\bcompleted\b", re.I)
INLINE = re.compile(r"`[^`]*`")
SPLIT = re.compile(r"(?<=[.;!?])(?:\*\*)?\s+(?=[A-Z(*\[])|\s\|\s|^\||\|$")


def sentences(line):
    for part in SPLIT.split(line):
        if part and part.strip():
            yield part.strip()


def census_text(text):
    hits = []
    fenced = False
    for no, raw in enumerate(text.split("\n"), 1):
        s = raw.strip()
        if s.startswith("```"):
            fenced = not fenced
            continue
        if fenced or s.startswith(">"):
            continue
        line = INLINE.sub(" CODE ", raw)
        for sent in sentences(line):
            for name, rx in RULES:
                if rx.search(sent):
                    hits.append((no, name, sent))
            if UNCOND.search(sent) and BOUNDWORD.search(UNCOND.sub(" ", sent)):
                hits.append((no, "UNCOND", sent))
            if FIG.search(sent) and not COMPLETED.search(sent):
                hits.append((no, "FIG", sent))
    return hits


def main(paths):
    total = 0
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            print("cannot read %s: %s" % (p, exc))
            return 3
        for no, name, sent in census_text(text):
            total += 1
            print("%s:%d: %s: %s" % (p, no, name, sent[:220].encode("ascii", "replace").decode()))
    print("claim census: %d hit(s)" % total)
    return 1 if total else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(3)
    sys.exit(main(sys.argv[1:]))
