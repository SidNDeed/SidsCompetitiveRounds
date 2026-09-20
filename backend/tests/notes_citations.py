"""Check the `file:line` citations in a lane's review notes against the tree.

WHY THIS EXISTS
  The notes for bug 392 said, in their own header, that their line numbers were
  the ones on this branch after the change. They were not, twice over and for
  two different reasons: one set was correct when it was written and was
  invalidated by a later pass, and another set was shifted by sixteen lines by
  a comment the SAME round added. Both survived a cold external gate that had
  traced rows through them, and the second one sat inside the very row it was
  written to close.

  That is not a proof-reading failure. A line number is a claim about the whole
  file and is falsified by any edit above it -- the same property that makes a
  source fingerprint need re-pinning after the last edit of any kind (#752).
  Prose cannot hold it. So the citations get the treatment every other claim in
  this lane gets: a mechanical check, with a control (#302, #391).

HOW A CITATION IS CHECKED
  A citation is ANCHORED when the same notes line carries a backticked token
  that occurs in the cited source -- `_persistable_exit_cause`, `"lei"`,
  `game_live_now`. The anchor is what the citation is really about; the number
  is only where it was last seen. The check resolves the anchor in the source
  and requires the cited line, or cited range, to contain one of its
  occurrences.

  An UNANCHORED citation cannot be checked that way, so it gets the one check
  that still bites: the cited line must not be blank. A citation landing on a
  blank line is the exact shape that reached the gate. Its text is printed so a
  reader can judge the rest without opening the file.

  `--require-anchors` turns every unanchored citation into a failure. It is the
  ratchet: once a notes file is fully anchored it can be kept that way.

Usage:

    python backend/tests/notes_citations.py --notes <file> [--require-anchors]
    python backend/tests/notes_citations.py --self-test

Exit codes: 0 every citation resolved, 1 at least one did not, 2 the self-test
failed or an input was unreadable.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent

# A citation: an optional path, then `:N` or `:N-M` (hyphen or en dash). A bare
# `:N` inherits the path most recently named on the SAME notes line, which is
# how the tables in these notes are written.
_PATH = r"(?:backend/[A-Za-z0-9_./-]+|[A-Za-z0-9_-]+\.(?:py|sql))"
_CITE = re.compile(rf"(?P<path>{_PATH})?\s*:(?P<a>\d{{3,6}})(?:\s*[-–]\s*(?P<b>\d{{3,6}}))?")
_BACKTICKED = re.compile(r"`([^`\n]+)`")
# `main.py` on its own means the api module in these notes.
_ALIASES = {"main.py": "backend/api/main.py",
            "discord_bot.py": "backend/discord_bot.py"}


def _resolve(path_text: str) -> Path | None:
    """The file a citation names, whether it was written full or bare.

    The notes write the same file both ways -- `backend/tests/x.py` in one
    table and `x.py` in the next paragraph -- so a resolver that only accepts
    the full form reports NO-SUCH-FILE for a citation that is perfectly good,
    and a reader learns to ignore the verdict.
    """
    rel = _ALIASES.get(path_text, path_text)
    candidate = REPO / rel
    if candidate.is_file():
        return candidate
    if "/" not in rel:
        for parent in ("backend/tests", "backend/sql", "backend/api",
                       "backend/tests/fixtures", "backend"):
            candidate = REPO / parent / rel
            if candidate.is_file():
                return candidate
    return None


# An anchor has to look like something a source names: an identifier, a dotted
# or attribute form, or a quoted literal. Prose does not qualify.
_ANCHOR_SHAPE = re.compile(r"""^(?:[A-Za-z_][A-Za-z0-9_.]*|"[^"]+"|'[^']+')$""")
# ...and it has to be RARE enough to mean a place. A token the file uses
# everywhere -- `true`, `ffa_match_players` -- resolves to a list of lines and
# therefore to none of them, so it is not evidence that a citation is wrong.
# Calling drift on such an anchor is a check that fires on correct citations,
# which is how a check gets ignored (#342).
_ANCHOR_MAX_OCCURRENCES = 12


def _anchors_on(line: str) -> list[tuple[int, str]]:
    """[(position in the line, needle)] for each backticked token that could
    anchor a citation.

    Three kinds are dropped. A token carrying a citation inside it is not an
    anchor, it IS the citation. A token naming a FILE is not one either --
    `main.py` occurs inside `discord_bot.py`, so a table row citing both files
    would resolve one file's NAME against the other's text and report drift on
    a citation that is perfectly correct. And prose is not an anchor unless it
    is quoted, in which case it is a string literal and the quotes come off
    before the search.
    """
    out: list[tuple[int, str]] = []
    for m in _BACKTICKED.finditer(line):
        tok = m.group(1).strip()
        if not tok or re.search(r":\d{2,6}", tok):
            continue
        if "/" in tok or tok.endswith((".py", ".sql", ".cs", ".json", ".md")):
            continue
        if not _ANCHOR_SHAPE.match(tok):
            continue
        needle = tok[1:-1] if tok[:1] in "\"'" else tok
        if needle:
            out.append((m.start(), needle))
    return out


def check(notes_text: str, read_source) -> list[dict]:
    """One record per citation found. `read_source(rel) -> list[str] | None`.

    Every anchor on a notes line is offered to every citation on that line.
    Binding each anchor to its nearest citation instead was tried and is
    WORSE: the dense table rows in these notes carry five citations and five
    anchors, proximity gets the pairing wrong, and the tool then reports drift
    on correct numbers -- which is the failure mode that gets a check ignored
    (#342). The weaker rule can mask a wrong number when a neighbouring
    anchor on the same line happens to land in range; it is reported as
    evidence to read, not as a gate that stands alone.
    """
    results: list[dict] = []
    for lineno, line in enumerate(notes_text.splitlines(), 1):
        current: str | None = None
        anchors = [needle for _pos, needle in _anchors_on(line)]
        for m in _CITE.finditer(line):
            if m.group("path"):
                current = m.group("path")
            if current is None:
                continue
            src = read_source(current)
            if src is None:
                results.append({"notes_line": lineno, "path": current,
                                "cited": m.group(0).strip(), "verdict": "NO-SUCH-FILE"})
                continue
            a = int(m.group("a"))
            b = int(m.group("b")) if m.group("b") else a
            if a > len(src):
                results.append({"notes_line": lineno, "path": current,
                                "cited": m.group(0).strip(), "verdict": "PAST-EOF"})
                continue
            hit_anchor, anchor_lines = None, []
            for anchor in anchors:
                occurrences = [i for i, t in enumerate(src, 1) if anchor in t]
                if not occurrences or len(occurrences) > _ANCHOR_MAX_OCCURRENCES:
                    continue
                anchor_lines.append((anchor, occurrences))
                if any(a <= o <= b for o in occurrences):
                    hit_anchor = anchor
                    break
            rec = {"notes_line": lineno, "path": current,
                   "cited": m.group(0).strip(), "range": (a, b)}
            if hit_anchor:
                rec["verdict"] = "OK"
                rec["anchor"] = hit_anchor
            elif anchor_lines:
                anchor, occurrences = anchor_lines[0]
                rec["verdict"] = "DRIFT"
                rec["anchor"] = anchor
                rec["anchor_at"] = occurrences[:4]
            elif not src[a - 1].strip():
                rec["verdict"] = "BLANK"
            else:
                rec["verdict"] = "UNANCHORED"
                rec["text"] = src[a - 1].strip()[:100]
            results.append(rec)
    return results


def _self_test() -> int:
    """Plant one citation of every verdict and require each to be reached.

    A checker that returned OK for everything would have agreed with the notes
    exactly as the gate did (#342), so the control asserts the failing verdicts
    as hard as the passing one.
    """
    # Line numbers in these notes are three digits and up, so the planted file
    # is padded to put its anchors there: a control that exercises a shape the
    # real input cannot contain proves nothing about the real input.
    source = ["# filler"] * 100
    source[99] = "def _persistable_exit_cause(cause):"   # line 100
    source += [
        "    return cause",                              # 101
        "",                                              # 102
        "x = 1  # unrelated",                            # 103
        "common = common + 1",                           # 104
    ]
    source += ["common = common + 1"] * 20               # a token used everywhere
    notes = "\n".join([
        "ok      `fake.py:100` (`_persistable_exit_cause`)",
        "drift   `fake.py:103` (`_persistable_exit_cause`)",
        "blank   `fake.py:102` with no anchor",
        "unanch  `fake.py:103` with no anchor",
        "eof     `fake.py:900` with no anchor",
        "range   `fake.py:100-101` (`_persistable_exit_cause`)",
        "weak    `fake.py:103` (`common`)",
    ])
    got = check(notes, lambda rel: source if rel == "fake.py" else None)
    verdicts = [r["verdict"] for r in got]
    expected = ["OK", "DRIFT", "BLANK", "UNANCHORED", "PAST-EOF", "OK", "UNANCHORED"]
    checks = {
        "one record per citation": len(got) == len(expected),
        "every verdict as planted": verdicts == expected,
        "the drifted one names where the anchor really is":
            got[1].get("anchor_at") == [100],
        "a token used everywhere is not treated as an anchor":
            got[6]["verdict"] == "UNANCHORED",
        "a missing file is refused, not passed":
            check("`nope.py:100`", lambda rel: None)[0]["verdict"] == "NO-SUCH-FILE",
    }
    for k, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {k}")
    print("  planted:", expected)
    print("  got    :", verdicts)
    bad = [k for k, ok in checks.items() if not ok]
    print("SELF-TEST:", "every verdict reachable" if not bad else f"FAILED: {bad}")
    return 2 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--notes", type=Path)
    ap.add_argument("--require-anchors", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.notes:
        ap.error("--notes is required unless --self-test is given")
    if not args.notes.is_file():
        print(f"REFUSING: not a file: {args.notes}")
        return 2

    cache: dict[str, list[str] | None] = {}

    def read_source(rel: str):
        if rel not in cache:
            p = _resolve(rel)
            cache[rel] = p.read_text(encoding="utf-8").splitlines() if p else None
        return cache[rel]

    records = check(args.notes.read_text(encoding="utf-8"), read_source)
    counts: dict[str, int] = {}
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    notes_rel = args.notes.name
    for r in records:
        if r["verdict"] == "OK":
            continue
        head = f"{notes_rel}:{r['notes_line']}: {r['verdict']} {r['cited']}"
        if r["verdict"] == "DRIFT":
            print(f"{head} — anchor `{r['anchor']}` is at {r['anchor_at']}")
        elif r["verdict"] == "UNANCHORED":
            print(f"{head} — cited line reads: {r['text']}")
        else:
            print(head)
    print("citations: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    bad = counts.get("DRIFT", 0) + counts.get("BLANK", 0) \
        + counts.get("PAST-EOF", 0) + counts.get("NO-SUCH-FILE", 0)
    if args.require_anchors:
        bad += counts.get("UNANCHORED", 0)
    print("VERDICT:", "every citation resolved" if not bad else f"{bad} unresolved")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
