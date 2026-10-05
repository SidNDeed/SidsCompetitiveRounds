"""The redirect class in the client resync contract, scanned over the WHOLE
document rather than over the sentences somebody thought to select.

THE DEFECT THIS EXISTS FOR. The lane's ruling is that a refusal carrying
`settled_game` ends the entry that carried it -- dropped, kept for review,
never re-signed -- and that a retryable answer is retried with the SAME body,
unchanged, whatever number it advertised. Round 14 wrote the ruling into the
arm table and two paragraphs, and the instrument that held it read exactly
those three statements. The document still carried the refuted design in other
sections: a precedent passage calling the client's one-shot re-signed resend
"precisely the shape" the report path needs, and a redelivery rule that
re-signed a retryable entry at the number its answer advertised. Nothing read
those sections, so the class survived a control that could not fail on it
(#432: the flag names a LINE and the defect is a CLASS; #342: a check that
cannot fail).

So this reads everything outside a code fence and looks for the OPERATION, not
for a sentence: every place the document re-signs, re-keys, re-files or
redirects, names the client's `rewriteOnRefusal` channel, sends something at a
moved number (the advertised, free, next, new or N+1 number), or has an entry
adopt a number without saying it is the NEXT game's. Each occurrence has to be
admitted by what its own clause says about it, and the kinds that admit one
are few and written down:

  NEGATED     a negator within four words before it -- "never re-signed",
              "nothing is re-signed", "no retry ... re-keys";
  REFUTED     "refuted", "retired" or "removed" within three words of it --
              "the refuted redirect";
  HISTORICAL  a past round's reading named in the same clause -- "Round 8's
              reading ... under a new number";
  HARM        a modal in its clause and a stated harm in its sentence -- a
              second row, settlement, rating or payout, a second time, a game
              of its own, twice;
  CONTROL     its sentence names a mutation control, or says mutant/mutation;
  CHANNEL     its clause names the live-points path and nothing on the report
              path -- the fact about the client that stays true;
  NEXT-GAME   an adoption whose clause says the number is the NEXT game's.

Anything else is UNADMITTED, and one unadmitted occurrence anywhere is a
contradiction of the ruling.

WHAT IT CANNOT SEE, stated rather than implied. It reads vocabulary and
clause structure, not meaning: a sentence that IMPLIES a re-signed resend
without any of the operation's words (a retry "nobody asked to" re-sign,
which implies retries somebody did ask to) is outside it, and so is a
redirect sentence placed inside a clause that also carries an admitting word
for some other reason. Those are why the round's notes rule every swept line
by hand as well. What this adds is that the class cannot come back through
the vocabulary it was written in without reddening.

    python backend/tests/evidence/contract_arm_rules.py [--all] <document>
    python backend/tests/evidence/contract_arm_rules.py --plant <site> <kind> <document> <copy>

THE DOCUMENT IS AN ARGUMENT AND IS NOT NAMED HERE: it lives under the
gitignored scratch, and a committed file may not send a reader to a path this
repository does not contain. It reads the document and writes nothing except
the copy `--plant` is asked for.
"""
import re
import sys

FENCE = re.compile(r"^\s*```")
HEADING = re.compile(r"^#{1,6} ")
TABLE_ROW = re.compile(r"^\s*\|")
LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")

# THE OPERATION. Each one is a way the refuted design is written; a sentence
# that states that design as a rule cannot avoid all of them.
VERB_OPS = (
    ("re-sign", re.compile(r"\bre-?sign(?:s|ed|ing)?\b", re.I)),
    ("re-key", re.compile(r"\bre-?key(?:s|ed|ing)?\b", re.I)),
    ("re-file", re.compile(r"\bre-?fil(?:e|es|ed|ing)\b", re.I)),
    ("re-identify", re.compile(r"\bre-?identif(?:y|ies|ied|ying)\b", re.I)),
    ("redirect", re.compile(r"\bredirect(?:s|ed|ing|ion)?\b", re.I)),
    ("rewriteOnRefusal", re.compile(r"rewriteOnRefusal")),
)
# A send at a MOVED number: the verb and the target in one clause, either
# order. The target names a number other than the one the entry was first
# written with.
SEND_VERB = re.compile(
    r"\b(?:re-?sen[dt]s?|re-?sending|re-?deliver\w*|re-?submi\w*"
    r"|retr(?:y|ies|ied|ying)|sen[dt]s?|sending|deliver\w*|submi\w*)\b", re.I)
MOVED_TARGET = re.compile(
    r"\b(?:at|to|under|with|onto)\s+(?:the\s+|that\s+|a\s+|an\s+|its\s+|this\s+)?"
    r"(?:advertised|free|next|new|different|second|another|later|higher)\s+"
    # The backticked field is its own alternative: a word boundary after its
    # closing backtick is never there, so inside the group it never matched.
    r"(?:(?:number|key|room id|expected_game)\b|`expected_game`)"
    r"|\bN\s?\+\s?1\b", re.I)
# An entry that ADOPTS a number, in a clause that does not say the number is
# the NEXT game's. "keep the entry, adopt the advertised number" was the 503
# table's wording, and it reads both ways.
ADOPT = re.compile(r"\badopt(?:s|ed|ing)?\b", re.I)
NUMBER_WORD = re.compile(r"\bnumber\b|expected_game", re.I)
ENTRY_WORD = re.compile(r"\b(?:entry|entries|body|delivery|parked)\b", re.I)
NEXT_GAME = re.compile(r"\bnext\b", re.I)

# WHAT ADMITS ONE.
NEGATORS = {"never", "not", "no", "nor", "nothing", "none", "neither",
            "cannot", "can't", "without", "nobody", "isn't", "doesn't",
            "don't", "won't", "aren't"}
NEGATING_PAIRS = ("instead of", "rather than")
REFUTED_WORDS = {"refuted", "retired", "removed"}
HISTORICAL = re.compile(
    r"\bround[s]?\s+\d+(?:\s+and\s+\d+)?(?:'s)?\s+"
    r"(?:reading|rule|wording|version|design|stated|shipped|said)\b", re.I)
MODAL = re.compile(r"\b(?:would|could|can|may|might)\b", re.I)
HARM = re.compile(
    r"second\s+(?:row|settlement|rating|payout|physical game|time"
    r"|`ffa_matches` row)|game of its own|paid twice|twice|double", re.I)
CONTROL_NAME = re.compile(r"`[a-z0-9]+(?:-[a-z0-9]+){2,}`")
MUTANT_WORD = re.compile(r"\bmutant|\bmutation", re.I)
CHANNEL = re.compile(r"live-points|live points|LIVE_POINT", re.I)
REPORT_PATH = re.compile(
    r"\breport|\bparked\b|\bdelivery\b|\bredelivery\b|\boutbox entry", re.I)

SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"')\]*]*\s+(?=[A-Z0-9`\"'(\[§*_])")
CLAUSE_BREAK = re.compile(r"\s+[—–]\s+|\s+--\s+|;\s+|:\s+|\(|\)")
WORD = re.compile(r"[A-Za-z0-9_'`+’-]+")


def units(text):
    """Every unit of prose outside a code fence: (first line, text, line map).

    A table row is split into its cells, a heading is its own unit, and a
    paragraph or list item is joined across its lines. The map turns a
    character offset in the joined text back into the document line it came
    from, so a finding names the line a reader would open."""
    out = []
    lines = text.split("\n")
    in_fence = False
    block, starts = [], []

    def flush():
        if block:
            joined, offsets, pos = "", [], 0
            for ln, s in zip(starts, block):
                if joined:
                    joined += " "
                    pos += 1
                offsets.append((pos, ln))
                joined += s.strip()
                pos = len(joined)
            out.append((starts[0], joined, offsets))
        del block[:]
        del starts[:]

    for i, line in enumerate(lines, 1):
        if FENCE.match(line):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            flush()
            continue
        if HEADING.match(line):
            flush()
            out.append((i, line.strip(), [(0, i)]))
            continue
        if TABLE_ROW.match(line):
            flush()
            for cell in line.strip().strip("|").split("|"):
                if cell.strip() and not set(cell.strip()) <= set("-: "):
                    out.append((i, cell.strip(), [(0, i)]))
            continue
        if LIST_ITEM.match(line):
            flush()
        block.append(line)
        starts.append(i)
    flush()
    return out


def _line_at(offsets, pos):
    line = offsets[0][1]
    for start, ln in offsets:
        if start <= pos:
            line = ln
    return line


def _words(s):
    return [w.strip("`'’").lower() for w in WORD.findall(s)]


def _admitted(kind, clause, at, sentence):
    """Which rule admits the operation found at `at` in `clause`, or None."""
    before = _words(clause[:at])
    after = _words(clause[at:])[1:]
    window = before[-4:]
    if any(w in NEGATORS or w.endswith("n't") for w in window):
        return "NEGATED"
    if any(p in " ".join(before[-5:]) for p in NEGATING_PAIRS):
        return "NEGATED"
    if any(w in REFUTED_WORDS for w in before[-3:] + after[:3]):
        return "REFUTED"
    if HISTORICAL.search(clause[:at]):
        return "HISTORICAL"
    if MODAL.search(clause) and HARM.search(sentence):
        return "HARM"
    if CONTROL_NAME.search(sentence) or MUTANT_WORD.search(sentence):
        return "CONTROL"
    if CHANNEL.search(clause) and not REPORT_PATH.search(clause):
        return "CHANNEL"
    if kind == "adopt" and NEXT_GAME.search(clause):
        return "NEXT-GAME"
    return None


def scan(text):
    """Every operation in the document: (line, kind, admitted-by, clause)."""
    found = []
    for _first, body, offsets in units(text):
        cursor = 0
        for sentence in SENTENCE_BREAK.split(body):
            s_at = body.find(sentence, cursor)
            cursor = s_at + len(sentence)
            c_cursor = 0
            for clause in CLAUSE_BREAK.split(sentence):
                if not clause or not clause.strip():
                    continue
                c_at = sentence.find(clause, c_cursor)
                c_cursor = c_at + len(clause)
                hits = []
                for kind, rx in VERB_OPS:
                    for m in rx.finditer(clause):
                        hits.append((m.start(), kind))
                target = MOVED_TARGET.search(clause)
                if target:
                    # The verb that governs the moved number is the nearest one
                    # BEFORE it, or the nearest after it when none precedes
                    # ("N+1 must not be submitted"). When that nearest verb is
                    # itself a re-sign or re-key, the occurrence is already
                    # judged as that operation and is not counted twice.
                    ops = [(m.start(), True) for _k, rx in VERB_OPS
                           for m in rx.finditer(clause)]
                    sends = [(m.start(), False) for m in SEND_VERB.finditer(clause)]
                    before = [v for v in ops + sends if v[0] < target.start()]
                    after = [v for v in sends if v[0] > target.start()]
                    near = (max(before) if before
                            else (min(after) if after else None))
                    if near is not None and not near[1]:
                        hits.append((near[0], "moved-number"))
                adopt = ADOPT.search(clause)
                if adopt and NUMBER_WORD.search(clause) and ENTRY_WORD.search(clause):
                    hits.append((adopt.start(), "adopt"))
                for at, kind in sorted(hits):
                    line = _line_at(offsets, s_at + c_at + at)
                    found.append((line, kind,
                                  _admitted(kind, clause, at, sentence),
                                  clause.strip()))
    return found


# THE PLANTS. Each writes the refuted design as a RULE, in the words a drift
# back to it would use, at a site the round-14 instrument never read. Each has
# a TWIN at the same site that states the ruling instead -- the same body,
# unchanged -- in as much of the same vocabulary as it can carry, so a scan
# that reds on the vocabulary rather than the rule reds on the twin too
# (#391).
PLANTS = {
    "A": ("inside section 4's precedent passage",
          "A report entry refused with `settled_game` takes this same channel:"
          " it is re-signed once at the advertised number and sent again.",
          "A report entry answered by a retryable status is sent again later"
          " as the same body, unchanged, under the key and number it was first"
          " sent with."),
    "B": ("inside the redelivery table, the parked-body row",
          "on a RETRYABLE answer that advertised a number, redeliver the entry"
          " re-signed at the advertised number.",
          "on a RETRYABLE answer that advertised a number, redeliver the entry"
          " as the same body, unchanged; the advertised number keys the next"
          " game."),
    "C": ("in the last hundred lines",
          "Recovery re-keys a parked delivery to the advertised `expected_game`"
          " and submits it once more.",
          "Recovery resends a parked delivery as the same body, unchanged, and"
          " the advertised `expected_game` keys the seat's next game."),
}


def _heading_before(lines, index):
    for i in range(index, -1, -1):
        if HEADING.match(lines[i]):
            return lines[i].strip()
    return "(no heading)"


def plant(text, site, kind):
    """The document with one sentence planted: (new text, planted line)."""
    where, redirect, unchanged = PLANTS[site]
    sentence = redirect if kind == "redirect" else unchanged
    lines = text.split("\n")
    if site == "A":
        # Inside the passage: found by the line that opens it, and the
        # sentence goes in as the last line of that same paragraph, so it is
        # read as one more sentence of the precedent rather than as a
        # paragraph of its own.
        hits = [i for i, ln in enumerate(lines)
                if ln.startswith("A 409 marks a live-points entry permanent")]
        if len(hits) != 1:
            raise SystemExit("REFUSED: the precedent passage resolves %d times"
                             % len(hits))
        at = hits[0]
        while at + 1 < len(lines) and lines[at + 1].strip():
            at += 1
        at += 1
        lines.insert(at, sentence)
    elif site == "B":
        hits = [i for i, ln in enumerate(lines)
                if ln.startswith("| **a seat holding a parked body** | ")]
        if len(hits) != 1:
            raise SystemExit("REFUSED: the parked-body row resolves %d times"
                             % len(hits))
        at = hits[0]
        head = "| **a seat holding a parked body** | "
        lines[at] = head + sentence + " " + lines[at][len(head):]
    else:
        # Its own paragraph, immediately before the document's LAST one, so it
        # is inside the final hundred lines however long the document grows.
        end = len(lines) - 1
        while end > 0 and not lines[end].strip():
            end -= 1
        start = end
        while start > 0 and lines[start - 1].strip():
            start -= 1
        at = start
        lines[at:at] = [sentence, ""]
    return "\n".join(lines), at + 1, where, _heading_before(lines, at)


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def main(argv):
    if len(argv) == 6 and argv[1] == "--plant":
        site, kind, src, dst = argv[2], argv[3], argv[4], argv[5]
        if site not in PLANTS or kind not in ("redirect", "unchanged"):
            print("REFUSED: site is one of %s and kind is redirect or unchanged"
                  % "/".join(sorted(PLANTS)))
            return 2
        text = _read(src)
        new, line, where, heading = plant(text, site, kind)
        total = new.count("\n") + 1
        with open(dst, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
        print("  planted  %s sentence at line %d of %d (%s; under %s)"
              % (kind, line, total, where, heading))
        return 0
    listing = len(argv) == 3 and argv[1] == "--all"
    if not (len(argv) == 2 or listing):
        print("usage: contract_arm_rules.py [--all] <document>")
        return 2
    found = scan(_read(argv[-1]))
    total = len(found)
    unadmitted = [f for f in found if f[2] is None]
    kinds = {}
    for f in found:
        kinds[f[2] or "UNADMITTED"] = kinds.get(f[2] or "UNADMITTED", 0) + 1
    print("  operations found: %d; %s" % (
        total, ", ".join("%s %d" % (k, kinds[k]) for k in sorted(kinds))))
    # --all prints every occurrence and what admitted it, which is what lets a
    # reader audit the admitted set instead of trusting a count of it.
    for line, kind, how, clause in found:
        if how is None or listing:
            print("  %s line %d [%s]: %s"
                  % (how or "UNADMITTED", line, kind, clause[:150]))
    # A scan that found nothing is a scan that matched nothing, and it would
    # pass on any document at all (#342).
    if total == 0:
        print("  REFUSED: no operation anywhere, so this scan read nothing")
        return 2
    return 1 if unadmitted else 0


def lf_stdout():
    """UTF-8 and LF, on the platform whose text streams write neither.

    The document is UTF-8 and full of section signs and dashes; a console code
    page would turn every one of them into a byte no UTF-8 reader accepts, and
    a text stream here writes CRLF, which is not what a capture assembled from
    this output is compared against."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")


if __name__ == "__main__":
    lf_stdout()
    sys.exit(main(sys.argv))
