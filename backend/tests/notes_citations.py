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

WHERE A BARE `:N` GETS ITS PATH
  The first version inherited a path only within ONE notes line, and its
  comment claimed the tables in these notes were written that way. They are
  not. A table names the module in one row and cites three more numbers in the
  next; a paragraph names it in its first sentence and cites four lines
  beneath. So a third of this file's citation-shaped references were not read
  as citations at all -- not checked, not counted, not refused -- while the
  count beside them was reported as the total the file makes. That is the
  defect this round was opened to close, one route over (#302, #342, #441).

  A bare `:N` now inherits the path most recently MENTIONED -- with or without
  a number of its own -- earlier on its line, or on an earlier line of the same
  BLOCK. A block is a run of lines carrying no blank line, heading or
  horizontal rule, which is what a paragraph and a table each are; a heading is
  a block of its own, so nothing leaks across it. Inheritance never crosses a
  break, so a path named eight paragraphs above cannot claim a number. A bare
  `:N` with nothing in scope is reported `NO-PATH-IN-SCOPE` rather than
  skipped: a citation nothing can resolve is a finding about the notes, not a
  licence to stop counting.

  THE ANCHOR SCOPE IS THE SAME BLOCK, and for the same reason. Anchors were
  offered only to citations on their own line, which is the identical defect
  one field over (#432): a paragraph that names `_INVOLUNTARY_CAUSE_CAPABILITY_ALIAS`
  in one sentence and cites its line in the next had an anchor the citation
  could not reach. While the bare citations were invisible this cost nothing;
  the moment they were read it produced six DRIFT records against numbers that
  are correct today -- a check reporting drift on correct citations, which is
  exactly how a check gets ignored (#342). Widening the scope does make an OK
  slightly easier to earn: an anchor from elsewhere in the paragraph can cover
  a citation it was not written for. That is why this verdict is reported as
  evidence to read and not as a gate standing alone, and why the drift control
  is executed against this file rather than asserted.

  What makes a bare `:N` a citation at all is what sits to the LEFT of the
  colon. `127.0.0.1:55432` and `postgres:16-alpine` bind the colon into a
  larger token -- a port, an image tag -- and `` `:45435` `` and `at :45318` do
  not. The first version used a three-digit floor as a proxy for that question;
  it admitted nothing this rule does not and it hid two perfectly good
  two-digit citations. Every `:N` the rule declines is still reported, as
  `NOT-A-CITATION` with its surrounding text, so the population is conserved
  and a reader can see what was set aside (#441).

A FENCE THAT NEVER CLOSES IS A REFUSAL, NOT A QUIET PASS
  The fenced-block skip is a toggle. One unmatched marker inverts the scanned
  region for the whole rest of the file: every real citation disappears from
  the record set and only the quoted material is read, with the count and the
  verdict both agreeing with whatever was left. The scan now RAISES on an
  unbalanced fence and names the line the last one opened at, and the caller
  turns that into a refusal. A parse that silently yields nothing must fail
  loudly rather than certify what it could not see (#342).

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
# `:N` inherits the path most recently MENTIONED earlier on its line or on an
# earlier line of the same block; see WHERE A BARE `:N` GETS ITS PATH above.
#
# `.cs` and the two client-lane directory prefixes are in the shape because the
# notes cite the other lane; see THE OTHER LANE'S SOURCES above.
_PATH = (r"(?:(?:backend|client-lane|plugin)/[A-Za-z0-9_./-]+"
         r"|[A-Za-z0-9_-]+\.(?:py|sql|cs))")
_CITE = re.compile(rf"(?P<path>{_PATH})?\s*:(?P<a>\d{{1,6}})(?:\s*[-–]\s*(?P<b>\d{{1,6}}))?")
# A path NAMED without a number of its own still enters scope. The commonest
# shape in these notes is a row or a sentence that names the module and then
# cites it by number on the lines beneath; a scanner that only remembered paths
# carrying a citation of their own could not see one of them.
_PATH_MENTION = re.compile(_PATH)
# What a bare `:N` must NOT be preceded by. A colon bound into a larger token
# belongs to that token -- a port, an image tag, a clock time -- and the thing
# after it is not a line number.
_BARE_BINDS_LEFT = re.compile(r"[A-Za-z0-9_./\\-]")
# A block: a run of lines with no blank line, heading or horizontal rule in it.
# A paragraph and a table are each one, and that is the unit a bare `:N`
# inherits inside.
_BLOCK_BREAK = re.compile(r"^\s*$|^\s*#{1,6}\s|^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")

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
_BLANK = re.compile(r"^\s*$")
# A heading or a horizontal rule is a block of its own: it separates what is
# above it from what is below, and a citation written INTO a heading is still
# read rather than dropped.
_STANDALONE = re.compile(r"^\s*#{1,6}\s|^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")


class UnbalancedFence(Exception):
    """A fenced block was opened and never closed.

    Raised rather than returned, because there is no honest record set to
    return: from the stray marker onward the scan read the COMPLEMENT of the
    file, and every citation after it is missing from whatever would be
    reported. The caller turns this into a refusal with its own exit code.
    """

    def __init__(self, opened_at: int):
        super().__init__(f"a fenced block opened at line {opened_at} is never closed")
        self.opened_at = opened_at


def blocks(notes_text: str) -> list[list[tuple[int, str]]]:
    """The notes outside fenced blocks, cut into blocks of [(lineno, line)].

    ONE definition of a block, used for both the path scope and the anchor
    scope, so the two cannot drift apart (#596). Raises `UnbalancedFence` when
    a marker is never matched -- see the note in `check`.
    """
    out: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    fenced = False
    opened_at = 0
    for lineno, line in enumerate(notes_text.splitlines(), 1):
        if _FENCE.match(line):
            fenced = not fenced
            opened_at = lineno if fenced else 0
            if cur:
                out.append(cur)
                cur = []
            continue
        if fenced:
            continue
        if _BLANK.match(line):
            if cur:
                out.append(cur)
                cur = []
            continue
        if _STANDALONE.match(line):
            if cur:
                out.append(cur)
            out.append([(lineno, line)])
            cur = []
            continue
        cur.append((lineno, line))
    if cur:
        out.append(cur)
    if fenced:
        raise UnbalancedFence(opened_at)
    return out


def check(notes_text: str, read_source) -> list[dict]:
    """One record per citation-shaped reference outside fenced blocks.

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
    fence and requires exactly one of them to be seen. An unmatched marker
    would invert that boundary for the rest of the file, so `blocks` raises
    `UnbalancedFence` rather than return a set that is quietly the complement
    of the intended one.

    A BLOCK IS THE SCOPE OF BOTH RULES. The path a bare `:N` inherits is the
    one most recently mentioned in its block; the anchors offered to a citation
    are every backticked token in its block. Scoping either to a single LINE --
    which is what the first version did, while the comment beside it claimed
    these notes' tables were written that way -- made a third of this file's
    citations invisible and then, once they were visible, reported drift on
    correct numbers. Nothing is set aside silently: a `:N` the predecessor rule
    declines is recorded `NOT-A-CITATION` with its surrounding text, and one
    with no path in scope is recorded `NO-PATH-IN-SCOPE`.

    Every anchor in the block is offered to every citation in it. Binding each
    anchor to its nearest citation instead was tried and is WORSE: the dense
    table rows in these notes carry five citations and five anchors, proximity
    gets the pairing wrong, and the tool then reports drift on correct numbers
    -- the failure mode that gets a check ignored (#342). The weaker rule can
    mask a wrong number when another anchor in the block happens to land in
    range; it is reported as evidence to read, not as a gate that stands alone.
    """
    results: list[dict] = []
    for block in blocks(notes_text):
        anchors: list[str] = []
        for _n, line in block:
            for _pos, needle in _anchors_on(line):
                if needle not in anchors:
                    anchors.append(needle)
        current: str | None = None
        for lineno, line in block:
            mentions = [(m.start(), m.group(0)) for m in _PATH_MENTION.finditer(line)]
            for m in _CITE.finditer(line):
                colon = m.start("a") - 1
                cited = m.group(0).strip()
                if m.group("path"):
                    current = m.group("path")
                else:
                    prev = line[colon - 1] if colon > 0 else ""
                    if prev and _BARE_BINDS_LEFT.match(prev):
                        results.append({"notes_line": lineno, "path": None,
                                        "cited": cited, "verdict": "NOT-A-CITATION",
                                        "text": line[max(0, colon - 24):colon + 8].strip()})
                        continue
                    named = [p for pos, p in mentions if pos < colon]
                    if named:
                        current = named[-1]
                if current is None:
                    results.append({"notes_line": lineno, "path": None,
                                    "cited": cited, "verdict": "NO-PATH-IN-SCOPE"})
                    continue
                src = read_source(current)
                if src is None:
                    # A client citation with no source named is NOT the same
                    # failure as a path that does not exist, and must not be
                    # reported as one: the first says the run could not check
                    # it, the second says the notes are wrong.
                    results.append({"notes_line": lineno, "path": current,
                                    "cited": cited,
                                    "verdict": "CLIENT-NOT-CONFIGURED"
                                    if is_client_path(current) else "NO-SUCH-FILE"})
                    continue
                a = int(m.group("a"))
                b = int(m.group("b")) if m.group("b") else a
                if a > len(src):
                    results.append({"notes_line": lineno, "path": current,
                                    "cited": cited, "verdict": "PAST-EOF"})
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
                       "cited": cited, "range": (a, b)}
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
            if mentions:
                current = mentions[-1][1]
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
        elif r["verdict"] == "NOT-A-CITATION":
            line = (f"{head} — reads: {r['text']} — the colon is bound into the "
                    "token on its left, so this is not a line number")
        elif r["verdict"] == "NO-PATH-IN-SCOPE":
            line = (f"{head} — no path is named on this line or earlier in its "
                    "block, so nothing can resolve it")
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


def _raises_unbalanced(text: str) -> bool:
    try:
        check(text, lambda rel: None)
    except UnbalancedFence:
        return True
    return False


def _unbalanced_at(text: str) -> int:
    try:
        check(text, lambda rel: None)
    except UnbalancedFence as exc:
        return exc.opened_at
    return 0


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
    # One BLOCK per case. The anchor scope is the block, so cases sharing one
    # would lend each other anchors and the planted BLANK would read as DRIFT
    # -- the planting would then be testing the wrong thing without saying so.
    notes = "\n\n".join([
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
        # The first version of this entry asserted `== []`: it REQUIRED the
        # citation after the unclosed fence to be swallowed and printed `ok`
        # when it was, under a name claiming the opposite property. A check
        # whose name denies its own assertion certifies the arrangement it is
        # named for (#342, #302).
        "a fence that never closes REFUSES rather than swallowing the rest":
            _raises_unbalanced("```\n`fake.py:900`"),
        "a BALANCED fence at the same site still skips what it encloses":
            check("```\n`fake.py:900`\n```", lambda rel: source) == [],
        "the refusal names the line the stray fence opened at":
            _unbalanced_at("text\n```\n`fake.py:900`") == 2,
        "a bare :N inherits the path named on the LINE ABOVE":
            [r["verdict"] for r in check(
                "the module is `fake.py`, and\n`:100` (`_persistable_exit_cause`)",
                lambda rel: source)] == ["OK"],
        "a bare :N inherits across a TABLE ROW boundary":
            [r["verdict"] for r in check(
                "| a | `fake.py:100` (`_persistable_exit_cause`) |\n"
                "| b | `:100` (`_persistable_exit_cause`) |",
                lambda rel: source)] == ["OK", "OK"],
        "inheritance does NOT cross a blank line":
            check("the module is `fake.py`\n\n`:100`",
                  lambda rel: source)[0]["verdict"] == "NO-PATH-IN-SCOPE",
        "inheritance does NOT cross a heading":
            check("the module is `fake.py`\n## next\n`:100`",
                  lambda rel: source)[0]["verdict"] == "NO-PATH-IN-SCOPE",
        "a port is declined, and REPORTED rather than dropped":
            [r["verdict"] for r in check("`fake.py` listens on 127.0.0.1:55432",
                                         lambda rel: source)] == ["NOT-A-CITATION"],
        "an image tag is declined at the same shape":
            [r["verdict"] for r in check("`fake.py` runs postgres:16-alpine",
                                         lambda rel: source)] == ["NOT-A-CITATION"],
        "a two-digit bare citation IS read now the floor is gone":
            check("`fake.py` window at `:44`",
                  lambda rel: source)[0]["verdict"] == "UNANCHORED",
        "an anchor one line ABOVE its citation is reached":
            check("the constant is `_persistable_exit_cause`, defined in `fake.py`\n"
                  "at `:100` and nowhere else", lambda rel: source)[0]["verdict"] == "OK",
        "an anchor one line BELOW its citation is reached too":
            check("`fake.py:100` is the line\n"
                  "that defines `_persistable_exit_cause`",
                  lambda rel: source)[0]["verdict"] == "OK",
        "an anchor does NOT reach across a blank line":
            check("the constant is `_persistable_exit_cause`\n\n`fake.py:103`",
                  lambda rel: source)[0]["verdict"] == "UNANCHORED",
        "a drifted citation is still DRIFT when its anchor is a line away":
            check("the constant is `_persistable_exit_cause`\n`fake.py:103`",
                  lambda rel: source)[0]["verdict"] == "DRIFT",
        "every citation-shaped reference produces exactly one record":
            len(check("`fake.py:100` and 127.0.0.1:55432 and `:102`",
                      lambda rel: source)) == 3,
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

    try:
        records = check(args.notes.read_text(encoding="utf-8"), read_source)
    except UnbalancedFence as exc:
        print(f"REFUSING a verdict: {exc}. From that marker on, the scan read "
              "the COMPLEMENT of this file: the citations it makes were skipped "
              "and the quoted material was checked instead. A count taken from "
              "an inverted scan is not evidence.")
        return 2
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
    declined = counts.get("NOT-A-CITATION", 0)
    print(f"population: {len(records)} citation-shaped references outside fences "
          f"= {len(records) - declined} read as citations "
          f"+ {declined} declined and listed above")
    print(f"listing: {printed} lines printed for {reportable} reportable records")
    bad = counts.get("DRIFT", 0) + counts.get("BLANK", 0) \
        + counts.get("PAST-EOF", 0) + counts.get("NO-SUCH-FILE", 0) \
        + counts.get("NO-PATH-IN-SCOPE", 0)
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
