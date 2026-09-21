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

THE OTHER LANE'S SOURCES
  These notes cite the client lane as well as this tree -- the constant the
  wire name is transcribed from, the capability probe, the call site that uses
  it. Round 2's checker could not see those citations at all: its path shape
  admitted `backend/...` and bare `.py`/`.sql` names and nothing else, so every
  client citation was silently not a citation. One of them was pointing at a
  blank line at the time, and the gate found it by hand.

  A client citation is now resolved against a source the caller NAMES with
  `--client-source <as-written>=<file>`. Two readings are wanted, and the
  option is repeatable so a run can take either: the committed blob, which is
  what the client lane actually says, and the EXTRACT the review bundle
  carries, which is what the reviewer can actually read. Both are run in the
  certifying pass, because they can differ in exactly one way and it is the way
  that matters -- a citation landing on a line blanked out of the extract
  resolves against the blob and gets the `BLANK` verdict against the extract.
  `BLANK` is a failure. That is precisely the shape that reached the gate.

  A notes file carrying a client citation with no source named for it REFUSES a
  verdict and exits 2. Reporting those citations as "fine" because the file was
  not to hand is the failure this section exists to end (#342).

THE LISTING IS PART OF THE VERDICT
  Round 2's runs reported fifteen non-OK records and printed one or two lines.
  The count was right and the listing was not: the checker writes an em dash
  per line and a redirected run died in the console code page partway through,
  after the lines already written. The tool now forces utf-8 on its own output
  stream, and COUNTS WHAT IT PRINTED: a run whose printed lines do not equal
  the records it reports exits non-zero and says so. A count with an incomplete
  listing beneath it is not evidence (#304).

Usage:

    python backend/tests/notes_citations.py --notes <file> [--require-anchors] \\
        [--client-source <as-written>=<file> ...]
    python backend/tests/notes_citations.py --self-test

Exit codes: 0 every citation resolved, 1 at least one did not, 2 the self-test
failed, an input was unreadable, a client source was not named, or the listing
was shorter than the count.
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
#
# `.cs` and the two client-lane directory prefixes are in the shape because the
# notes cite the other lane; see THE OTHER LANE'S SOURCES above.
_PATH = (r"(?:(?:backend|client-lane|plugin)/[A-Za-z0-9_./-]+"
         r"|[A-Za-z0-9_-]+\.(?:py|sql|cs))")
_CITE = re.compile(rf"(?P<path>{_PATH})?\s*:(?P<a>\d{{1,6}})(?:\s*[-–]\s*(?P<b>\d{{1,6}}))?")
# A citation that NAMES its file is read at any line number; a bare `:N`
# continuation, which inherits the path most recently named on the line, is
# read only from three digits up. The floor exists for the bare form alone,
# where a clock time or a version string on a line that happens to have named
# a source file earlier would otherwise be read as a citation. The first
# version applied the floor to BOTH forms and therefore skipped five citations
# in these notes -- a migration line and a fixture line among them -- while the
# prose beside it claimed every citation was checked. A checker narrower than
# the sentence describing it is the defect this whole round is about.
_BARE_CITATION_MIN_DIGITS = 3
_BACKTICKED = re.compile(r"`([^`\n]+)`")
# `main.py` on its own means the api module in these notes.
_ALIASES = {"main.py": "backend/api/main.py",
            "discord_bot.py": "backend/discord_bot.py"}
# A citation names the OTHER lane only when it says so, by the prefix the
# review bundle's own directory carries. Everything else -- `plugin/...`
# included -- is relative to THIS tree, which has a production `plugin/` folder
# of its own holding files of the same names at different numbers.
#
# That ambiguity is not hypothetical and not cheap: the notes carry citations
# of both kinds, and until the prefix was made to decide it, `plugin/X.cs` in a
# paragraph about the client lane and `plugin/X.cs` in a paragraph about this
# tree's production plugin were the same string. Resolving by the surrounding
# prose was tried and rejected -- the disambiguating sentence sits on a
# different line from the citation in most of these rows, so the rule would
# have been a guess with a window around it (#342).
_CLIENT_PREFIX = "client-lane/"


def is_client_path(path_text: str) -> bool:
    return path_text.startswith(_CLIENT_PREFIX)


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
                       "backend/tests/fixtures", "backend", "plugin"):
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

    A QUOTED token is judged only by its extension, not by whether it contains
    a separator. A route path -- `"/api/v1/mod-version"` -- is a string literal
    in the source and is the only rare thing on the lines that carry it; the
    separator rule was rejecting it as a file name, so the two citations naming
    those lines could not be anchored at all. A quoted token ending in a source
    extension is still dropped, which is the case the separator rule was there
    for.
    """
    out: list[tuple[int, str]] = []
    for m in _BACKTICKED.finditer(line):
        tok = m.group(1).strip()
        if not tok or re.search(r":\d{2,6}", tok):
            continue
        quoted = tok[:1] in "\"'" and tok[-1:] == tok[:1] and len(tok) > 2
        inner = tok[1:-1] if quoted else tok
        # The extension test reads the token WITHOUT its quotes, so a quoted
        # file name is dropped exactly like a bare one.
        if inner.endswith((".py", ".sql", ".cs", ".json", ".md")):
            continue
        if "/" in inner and not quoted:
            continue
        if not _ANCHOR_SHAPE.match(tok):
            continue
        if inner:
            out.append((m.start(), inner))
    return out


_FENCE = re.compile(r"^\s*(?:```|~~~)")


def check(notes_text: str, read_source) -> list[dict]:
    """One record per citation found, outside fenced blocks.

    `read_source(rel) -> list[str] | None`.

    FENCED BLOCKS ARE NOT SCANNED. A fenced block is a VERBATIM quotation --
    a command, a slab of source, the text of a ruling this file is answering.
    The `path:line` strings inside one are the quoted author's, not this file's,
    and checking them would report drift against a tree the quotation was never
    about. Marking them by hand is not available either: the text is verbatim,
    so an anchor cannot be added to it without making it something else.

    This is a boundary, not a filter on the measurement (#441): everything
    outside a fence is still read, and a citation this file MAKES belongs
    outside one. The control plants the same citation inside and outside a
    fence and requires exactly one of them to be seen.

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
    fenced = False
    for lineno, line in enumerate(notes_text.splitlines(), 1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        current: str | None = None
        anchors = [needle for _pos, needle in _anchors_on(line)]
        for m in _CITE.finditer(line):
            if m.group("path"):
                current = m.group("path")
            elif len(m.group("a")) < _BARE_CITATION_MIN_DIGITS:
                continue
            if current is None:
                continue
            src = read_source(current)
            if src is None:
                # A client citation with no source named is NOT the same
                # failure as a path that does not exist, and must not be
                # reported as one: the first says the run could not check it,
                # the second says the notes are wrong.
                results.append({"notes_line": lineno, "path": current,
                                "cited": m.group(0).strip(),
                                "verdict": "CLIENT-NOT-CONFIGURED"
                                if is_client_path(current) else "NO-SUCH-FILE"})
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


def emit(records: list[dict], notes_rel: str, write) -> tuple[int, int]:
    """Print one line per non-OK record. Returns (printed, reportable).

    The two numbers come back separately so the caller can compare them. They
    can differ: `write` is whatever the output stream turns out to be, and a
    stream that drops a line -- the console code page killing an em dash
    mid-listing, as happened in round 2 -- leaves a count with no listing under
    it. The comparison is the finding; this function only supplies the numbers
    (#304, #441).
    """
    printed = 0
    reportable = 0
    for r in records:
        if r["verdict"] == "OK":
            continue
        reportable += 1
        head = f"{notes_rel}:{r['notes_line']}: {r['verdict']} {r['cited']}"
        if r["verdict"] == "DRIFT":
            line = f"{head} — anchor `{r['anchor']}` is at {r['anchor_at']}"
        elif r["verdict"] == "UNANCHORED":
            line = f"{head} — cited line reads: {r['text']}"
        else:
            line = head
        if write(line):
            printed += 1
    return printed, reportable


def _listing_control() -> dict[str, bool]:
    """A writer that drops a line must be caught; one that drops none must not.

    The mutation and its inert twin at the same site: same records, same
    function, two writers. A check that reddened for both would say only that
    the writer changed.
    """
    records = [
        {"verdict": "BLANK", "notes_line": 1, "cited": "a.py:1"},
        {"verdict": "BLANK", "notes_line": 2, "cited": "a.py:2"},
        {"verdict": "OK", "notes_line": 3, "cited": "a.py:3"},
    ]
    kept: list[str] = []

    def honest(line):
        kept.append(line)
        return True

    dropped: list[str] = []

    def lossy(line):
        if len(dropped) == 1:          # the second line dies in the codec
            return False
        dropped.append(line)
        return True

    ok_printed, ok_reported = emit(records, "n.md", honest)
    bad_printed, bad_reported = emit(records, "n.md", lossy)
    return {
        "an honest writer prints every reportable record":
            (ok_printed, ok_reported) == (2, 2),
        "a writer that drops a line is caught by the comparison":
            bad_printed != bad_reported and bad_printed == 1 and bad_reported == 2,
        "an OK record is not counted as reportable": ok_reported == 2,
    }


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
        "a client citation is SEEN at all":
            check("`client-lane/ApiClient.cs:1874`", lambda rel: None)[0]["path"]
            == "client-lane/ApiClient.cs",
        "an unnamed client source refuses rather than resolving":
            check("`client-lane/ApiClient.cs:1874`",
                  lambda rel: None)[0]["verdict"] == "CLIENT-NOT-CONFIGURED",
        "a citation inside a fenced block is not read":
            check("```\n`fake.py:900`\n```", lambda rel: source) == [],
        "the SAME citation outside the fence still is":
            [r["verdict"] for r in check("`fake.py:900`", lambda rel: source)]
            == ["PAST-EOF"],
        "a fence that never closes does not swallow the rest silently":
            check("```\n`fake.py:900`", lambda rel: source) == [],
        "a quoted route path anchors":
            [n for _p, n in _anchors_on('`"/api/v1/mod-version"`')]
            == ["/api/v1/mod-version"],
        "an unquoted path-shaped token still does NOT anchor":
            _anchors_on("`backend/api/main.py`") == [],
        "a quoted SOURCE FILE name still does not anchor":
            _anchors_on('`"backend/api/main.py"`') == [],
        "a plugin/ citation is THIS tree's, not the other lane's":
            check("`plugin/ApiClient.cs:1`", lambda rel: None)[0]["verdict"]
            == "NO-SUCH-FILE",
        "a client citation landing on a blanked line is BLANK, not OK":
            check("`client-lane/ApiClient.cs:2`",
                  lambda rel: ["kept", "", "kept"])[0]["verdict"] == "BLANK",
        "a client citation on a surviving line is checked like any other":
            check("`client-lane/ApiClient.cs:1` (`kept`)",
                  lambda rel: ["kept", "", "kept"])[0]["verdict"] == "OK",
    }
    checks.update(_listing_control())
    for k, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {k}")
    print("  planted:", expected)
    print("  got    :", verdicts)
    bad = [k for k, ok in checks.items() if not ok]
    print("SELF-TEST:", "every verdict reachable" if not bad else f"FAILED: {bad}")
    return 2 if bad else 0


def _force_utf8() -> None:
    """The listing must survive the console code page.

    Strict, not `errors="replace"`: a listing that quietly substitutes
    characters is a different failure from one that dies, and both are worth
    seeing. If the stream cannot be reconfigured the run continues and the
    printed-versus-reported comparison catches whatever is lost.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="strict")
        except (AttributeError, ValueError, OSError):
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--notes", type=Path)
    ap.add_argument("--require-anchors", action="store_true")
    ap.add_argument("--client-source", action="append", default=[],
                    metavar="AS-WRITTEN=FILE",
                    help="resolve a client-lane citation path against this file; "
                         "repeatable. Give the EXTRACT the bundle carries to check "
                         "what a reviewer can read, or the committed blob to check "
                         "what the lane says.")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    _force_utf8()
    if args.self_test:
        return _self_test()
    if not args.notes:
        ap.error("--notes is required unless --self-test is given")
    if not args.notes.is_file():
        print(f"REFUSING: not a file: {args.notes}")
        return 2

    client: dict[str, Path] = {}
    for spec in args.client_source:
        name, _, target = spec.partition("=")
        if not name or not target:
            print(f"REFUSING: --client-source wants AS-WRITTEN=FILE, got {spec!r}")
            return 2
        p = Path(target)
        if not p.is_file():
            print(f"REFUSING: not a file: {p.name}")
            return 2
        client[name] = p
        client.setdefault(Path(name).name, p)

    cache: dict[str, list[str] | None] = {}

    def read_source(rel: str):
        if rel not in cache:
            if is_client_path(rel):
                p = client.get(rel) or client.get(Path(rel).name)
            else:
                p = _resolve(rel)
            cache[rel] = p.read_text(encoding="utf-8").splitlines() if p else None
        return cache[rel]

    records = check(args.notes.read_text(encoding="utf-8"), read_source)
    counts: dict[str, int] = {}
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    notes_rel = args.notes.name

    def write(line: str) -> bool:
        try:
            print(line)
            return True
        except (UnicodeEncodeError, OSError):
            return False

    printed, reportable = emit(records, notes_rel, write)
    for name in sorted(set(client)):
        if "/" in name:
            print(f"client source: {name} -> {client[name].name}")
    print("citations: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"listing: {printed} lines printed for {reportable} reportable records")
    bad = counts.get("DRIFT", 0) + counts.get("BLANK", 0) \
        + counts.get("PAST-EOF", 0) + counts.get("NO-SUCH-FILE", 0)
    if args.require_anchors:
        bad += counts.get("UNANCHORED", 0)
    print("ANCHOR RATCHET:", "ENFORCED" if args.require_anchors
          else "not enforced — unanchored citations are reported, not failed")
    unconfigured = counts.get("CLIENT-NOT-CONFIGURED", 0)
    if unconfigured:
        print(f"REFUSING a verdict: {unconfigured} client-lane citations had no "
              "source named — those citations were NOT checked. Supply "
              "--client-source.")
        return 2
    if printed != reportable:
        print(f"REFUSING a verdict: the listing is short by {reportable - printed} "
              "lines — a count with an incomplete listing beneath it is not evidence.")
        return 2
    print("VERDICT:", "every citation resolved" if not bad else f"{bad} unresolved")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
