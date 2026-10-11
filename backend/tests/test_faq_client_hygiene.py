"""Bar B7 over every file the FAQ refresh's client lane touches: no
drive-letter or home-directory path, no reference into the gitignored scratch
tree or a local sandbox checkout, no tester's handle, no account label or
account number, and no attribution to anybody but the maintainer, on any line
of any of those files.

WHY WHOLE FILES. The FAQ server lane handed plugin/I18nCatalogues.cs and
plugin/NativeUI.cs back to the client lane carrying thirteen references into
the scratch tree (twelve and one): comments that send a reader to notes no
other checkout has. A file ships whole, so the bar is every line of every
file this lane changes, not the lines it adds.

THE SCOPE IS RECORDED (_SCOPE) and checked against history in both directions
by test_the_scope_is_every_file_this_lane_touches. The lane's commits are
measured by git and never recognised by a path they touch: every commit from
the merge-base of HEAD with the certified client base to HEAD, one that
touches no scope file included. Every path such a commit touches must be in
the scope, and every file in the scope must have been touched by one. A range
that holds a merge commit is no longer one lane's line (a fold into the
client lane merges other lanes' work, which git cannot tell from this
lane's), so the check skips there and says so. The sweep itself needs no
history and runs everywhere.

THE DETECTOR is the FAQ server lane's (backend/tests/test_faq_surfaces.py,
its section 3), ported with its salt, its handle digests and its attribution
shapes, so this lane refuses everything that one does. Five differences,
each stated where it lives below: words are Unicode words, and a handle or
an account label is matched in the folded text (NFKC-normalised and
casefolded), so every letter case and compatibility form of it is one form;
two handles are added; a catalogue row whose English key is a shipped product
string that names a community member on purpose may carry that key's own
handle words, in the key and in its translation, and no other handle (the
translated value is scanned like any line, and every class reads a
catalogue row both as written and decoded as the game reads it); an
attribution may carry the maintainer's name and no other name (the server
lane's escapes for any one-letter word and any word in capitals are gone, and
the words that are not people are listed one by one); and account labels and
account numbers are refused by their shape wherever they stand.

THE DETECTOR DOES NOT SPELL ITS OWN TARGET, AND EXEMPTS NO IDENTIFIER. This
module is in the scope, so a pattern written as a literal would match its own
source, and the only way to keep it green would be to exclude it, which is how
a check stops being able to fail. Tokens are assembled from pieces, paths are
written as patterns and never as examples, handles and product strings appear
only as digests, and an account label only as a shape built from the
maintainer's name. These files describe a seat by its role (the second seat),
never by its label, so the gate holds no label to let through, and
test_the_gate_lets_no_identifier_through keeps it so. A hit is reported by
file, line and class, never by quoting it, and the tests below assert on
counts and flags computed beforehand, so a failure quotes nothing either.
"""
import hashlib
import os
import re
import subprocess
import unicodedata

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SCOPE = (
    "backend/tests/test_faq_client_hygiene.py",
    "backend/tests/test_faq_client_ladder.py",
    "backend/tests/test_faq_client_upload_caps.py",
    "plugin/I18nCatalogues.cs",
    "plugin/NativeUI.cs",
)

# The certified client base this lane was cut from (its brief). The lane's
# range is every commit from git's merge-base of HEAD with it to HEAD; no
# listed path decides which commits are the lane's.
_CLIENT_BASE = "6c46b71e"

_DRIVE_PATH = re.compile(r"(?<!\w)[A-Za-z]:[\\/](?![\\/])")
_HOME_PATH = re.compile(
    r"(?<![\w.])/(?:" + "ho" + "me|" + "Us" + r"ers)/[A-Za-z0-9_.-]+")
_SCRATCH_TOKEN = "ai" + "-collab"
_SANDBOX_TOKENS = ("scr" + "-wt-", "scr" + "-codex")

# UNICODE WORDS (difference 1). The server lane's pattern is ASCII-only, which
# splits a word at its first non-ASCII letter: in a Swedish catalogue the word
# for "almost" broke into a one-letter head and a four-letter tail whose digest
# is a listed handle, eight times. A word starts with a letter of any script.
_WORD = re.compile(r"[^\W\d_]\w*")
# A word's letter runs: a handle joined to a digit or an underscore ("x_2",
# "x2") is a word of its own to _WORD, and its letter run is the handle.
_LETTERS = re.compile(r"[^\W\d_]+")


def _fold(text):
    """Text as the identifier classes compare it: NFKC-normalised (a
    full-width or otherwise compatibility-encoded letter or digit is the
    letter or digit it renders as) and casefolded (capitalised, lower-case,
    upper-case and mixed-case forms are one form)."""
    return unicodedata.normalize("NFKC", text).casefold()


_HANDLE_SALT = "scr-faq-item11-handle-blocklist-v1"
# The server lane's four digests, unchanged, plus two (difference 2): a
# community member whose handle stood in four comments of these files, in the
# shapes "(handle, date; ...)" and "batch (handle's charts)" that no
# attribution shape below recognises; and the second-seat identifier, which
# stood in three comments of NativeUI.cs in lower case, as the subject of a
# verb, as a possessive and inside a parenthesis. A digest is compared with
# the folded word (_fold), so every letter case and compatibility form of a
# listed handle is that handle.
_HANDLE_DIGESTS = frozenset([
    "422aec928bf8edfddc358c6f59ede0b2b7306bebcd6cf798e900044d0309e9f8",
    "4412d9ea108a8a78983534ec345969267c9e40b53c88b7a6079177a23c85a673",
    "73f5adebce4448ae85fc7f6c505207716e70f88e3b0bff43072afb7508850c04",
    "fe7ed63ab5330c6fe2cd7fa73aa921339026008bbd51adca63fda318c424eaee",
    "1836e76c09dd1c1847d37f79b79dafff0666da2c2b6d23bfa2462eebac56330e",
    "5f84341006e3c6c924b8595196c7a7ca32cb1d288e864b447eb0fbb2fbc2550e",
])

# The server lane's product phrase (an achievement named after a community
# member), unchanged: a LINE that carries it may use the word elsewhere too.
_HANDLE_PHRASE_DIGESTS = frozenset([
    "ebb19cba72cc945dea5699e279070c7c66564fb432113301a04ab69627d3d0a6",
])

# SHIPPED PRODUCT STRINGS that name a community member on purpose
# (difference 3): that achievement's description, the shop title's
# description, the articles that mention the achievement, and the research the
# Info library reproduces under its author's credit. A catalogue line whose
# English KEY is exactly one of these is product content, translated: the
# handle words of that key are the product's own and pass wherever they stand
# on the row, its translated value included. Nothing else on the row is
# exempt: any other listed handle, in the key or in the translated value, is
# refused like anywhere else, and the value is read both as written and
# decoded (a handle spelled with escapes is a word too). Exact text, so a new
# sentence naming either person is refused until somebody decides it is
# product content too and lists it. Each digest is sha256(salt + "string:" +
# the English source).
_PRODUCT_STRING_DIGESTS = frozenset([
    "cefbde002b74d7bdf2a13678a5c3d80f07c40c0b92c6cd3ed6a797f95aaaedc4",
    "c7c9ffdf362b3781593d3712ebc4eb5778c1592c355189ab93e085188d082f82",
    "ba5f30f40c82ad23261c2e47c49bca98c501d5e3c10c172eeb94e9ac2fe41736",
    "2d49e5f0c33ec898441d0bd81d68280dc24405fb970e89083dc71adea4e9abd6",
    "245093003badd59c84b1ec3575daf6e32866e09c58b59f69ea65b62d09976407",
    "9a23f7a928ad8efa2c8ac2e95812d40c5cd77ab2752c46000d6e6f101a2807b1",
    "5fc5d3b0dd05cdb6df36ecc938ac380e095cd15d6937b09377d90204b6773187",
    "846e455520cde90bc296413ad407693330ef3bb346bcd7e08b53e6126f43f485",
    "d255076ba7305f6eb98440205da5b95b0f05fb8c6640deef0aa7d3263a109e61",
    "bea897e32d8dffbe0eb97c2769040cc351234e7db76ddece3ead4458098e8250",
    "1ef54f70e82d18a69517bc7faceb52f338049d85153b94dd417b4faf3f0a1fa8",
])

# THE MAINTAINER (difference 4): the one name an attribution may carry, alone.
_MAINTAINER = "Sid"

# ACCOUNT LABELS AND NUMBERS (difference 5). A seat's account is labelled with
# the maintainer's name joined to the seat's number. Such a label names a
# seat, and these files describe a seat by its role, so the label is refused
# wherever it stands, not only where an attribution shape meets it (no shape
# sees a label inside a parenthesis). The shape is applied to the folded
# text (_fold), so it holds in every letter case and compatibility form: the
# name not preceded by a letter, then a digit, joined directly or by an
# underscore or a hyphen, or after one space. After a space-joined digit the
# label ends at anything but a number's continuation: a further digit, or a
# colon, slash, hyphen, period or comma followed by a digit (a time, a range,
# a decimal) is a number; any other delimiter (a colon, comma, period,
# bracket, quote, slash, hyphen or underscore before a non-digit) and the end
# of the line end a label. No code identifier of these files has the shape
# in any case (the one local variable that had it was renamed). An account
# number is any 17-digit run, the class every evidence log of this lane masks.
_ACCOUNT_LABEL = re.compile(
    r"(?<![^\W\d_])" + re.escape(_fold(_MAINTAINER))
    + r"(?:[_-]?\d|\s\d(?!\d)(?![:/\-.,]\d))")
_ACCOUNT_NUMBER = re.compile(r"(?<![0-9])[0-9]{17}(?![0-9])")

# A name an attribution shape captures: a word that starts with a letter
# other than an ASCII lower-case one (so a capitalised name in any script is
# seen), kept only when its first letter is upper-case or title-case
# (_attribution_captures); the shapes read the NFKC-normalised line. A
# lower-case name is no shape's subject (it is indistinguishable from an
# ordinary word): the listed handles and the label class are matched in
# every case instead.
_NAME = r"([^\W\d_a-z]\w*)"
_ATTRIBUTION_SHAPES = (
    re.compile(_NAME + r"(?:/[A-Za-z0-9_]+)*\s+(?:reported|noticed|asked|"
               r"suggested|proposed|requested|spotted|flagged|found|wanted|"
               r"said|saw)\b"),
    re.compile(r"\b(?:reported|requested|suggested|proposed|found|spotted|"
               r"flagged|noticed|asked)\s+by\s+" + _NAME),
    re.compile(r"\b(?:[Tt]hanks to|[Cc]redit to|[Cc]ourtesy of)\s+" + _NAME),
    re.compile(_NAME + r"'s\s+(?:report|request|question|idea|suggestion|"
               r"bug|ask|proposal|repro|clip|screenshot|log)s?\b"),
    re.compile(r"\b[Bb]ug\s*#?\d+\s*[(,:\-—]\s*" + _NAME),
    re.compile(r"\((?:per|via|from|thanks|h/t|cc)\s+" + _NAME + r"\s*[),]"),
)
# Words the shapes meet in these files that are not people (difference 4).
# The server lane lets through any one-letter word and any word in capitals,
# and so would let through a name written that way; here every capture is
# refused unless it is the maintainer or one of these, and each of these is a
# word the shapes actually meet in these files (the test that keeps the gate
# free of identifiers fails on one they do not): the C# types that precede
# "found" in declarations ("ClickHandler found = null;"), the noun in "Match
# found", the "Not" of "Not found", the generic noun in "User reported", the
# update method a comment says it is called from ("(from Tick, ..."), the tab
# a bug title names ("Bug #130: My Stats"), the article in an article's "A
# saw's spinning loop" (the tool), and three words in capitals for emphasis:
# "ARE wanted", and "NO" and "ONE" opening a bug title.
_NOT_PEOPLE = frozenset([
    "CardInfo", "ClickHandler", "Component", "Match", "Not", "User",
    "Tick", "My", "A", "ARE", "NO", "ONE",
])

_CATALOGUE_ENTRY = re.compile(r'^\s*\["((?:[^"\\]|\\.)*)"\]\s*=\s*"((?:[^"\\]|\\.)*)",?\s*$')


def _read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
        return fh.read()


def _salted(text):
    return hashlib.sha256((_HANDLE_SALT + _fold(text)).encode("utf-8", "surrogatepass")).hexdigest()


def _handle_words(reading):
    """Every word of a reading the handle digests are compared with: the
    folded reading's words and their letter runs."""
    folded = _fold(reading)
    return _WORD.findall(folded) + [r for w in _WORD.findall(folded) for r in _LETTERS.findall(w) if r != w]


def _attribution_captures(reading):
    """The names the attribution shapes capture in a reading (NFKC-normalised),
    those whose first letter is upper-case or title-case."""
    normal = unicodedata.normalize("NFKC", reading)
    return [m.group(1) for shape in _ATTRIBUTION_SHAPES for m in shape.finditer(normal)
            if m.group(1)[:1].isupper() or m.group(1)[:1].istitle()]


# Every character escape of a C# regular string literal: the simple escapes,
# \u with four hex digits, \U with eight (at most U+10FFFF), and \x with one
# to four (greedy, as the compiler reads it).
_SIMPLE_ESCAPES = {"'": "'", '"': '"', "\\": "\\", "0": "\0", "a": "\a", "b": "\b", "e": "\x1b",
                   "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
_HEX = frozenset("0123456789abcdefABCDEF")


class Undecodable(ValueError):
    """A literal holds an escape this decoder does not decode."""


def _cs_literal(body):
    """The characters a C# regular string literal's body compiles to. Raises
    Undecodable on any escape it does not decode, so a gate that scans the
    decoded text never scans other characters than the game shows."""
    out, i, n = [], 0, len(body)
    while i < n:
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        e = body[i + 1] if i + 1 < n else ""
        if e in _SIMPLE_ESCAPES and e:
            out.append(_SIMPLE_ESCAPES[e])
            i += 2
        elif e in ("u", "U"):
            width = 4 if e == "u" else 8
            digits = body[i + 2:i + 2 + width]
            if len(digits) != width or not set(digits) <= _HEX or int(digits, 16) > 0x10FFFF:
                raise Undecodable("a \\%s escape without %d hex digits of a code point" % (e, width))
            out.append(chr(int(digits, 16)))
            i += 2 + width
        elif e == "x":
            j = i + 2
            while j < n and j < i + 6 and body[j] in _HEX:
                j += 1
            if j == i + 2:
                raise Undecodable("a \\x escape without a hex digit")
            out.append(chr(int(body[i + 2:j], 16)))
            i = j
        else:
            raise Undecodable("an escape C# does not define")
    # A surrogate pair written as two escapes is one character.
    return "".join(out).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")


def _catalogue_text(text):
    """A catalogue row's key and translated value as the game reads them
    (escapes decoded), one per line; empty for any other line. Raises
    Undecodable when either holds an escape the decoder does not decode."""
    m = _CATALOGUE_ENTRY.match(text)
    if not m:
        return ""
    return _cs_literal(m.group(1)) + "\n" + _cs_literal(m.group(2))


def _key_handles(text):
    """The listed handle words a catalogue row may carry (difference 3): those
    of its own English key, lower-cased, when that key is exactly a listed
    product string; none for any other line."""
    m = _CATALOGUE_ENTRY.match(text)
    if not m:
        return frozenset()
    try:
        key = _cs_literal(m.group(1))
    except Undecodable:
        return frozenset()
    digest = hashlib.sha256((_HANDLE_SALT + "string:" + key).encode("utf-8")).hexdigest()
    if digest not in _PRODUCT_STRING_DIGESTS:
        return frozenset()
    return frozenset(_fold(w) for w in _handle_words(key) if _salted(w) in _HANDLE_DIGESTS)


def _phrase_handles(reading):
    """The handle word of the product phrase on a reading that carries it, as
    words or as letter runs (the achievement's id joins the phrase's two
    words with an underscore)."""
    out = set()
    for words in (_WORD.findall(_fold(reading)), _LETTERS.findall(_fold(reading))):
        out |= {a for a, b in zip(words, words[1:]) if _salted(a + " " + b) in _HANDLE_PHRASE_DIGESTS}
    return out


def _escaped(word):
    """A word as a C# literal spells it with \\u escapes only (the probes' form)."""
    return "".join("\\u%04x" % ord(c) for c in word)


def _escaped_x(word):
    """The same with \\x escapes of four hex digits (so no following letter
    can extend one)."""
    return "".join("\\x%04x" % ord(c) for c in word)


def _escaped_big_u(word):
    """The same with \\U escapes of eight hex digits."""
    return "".join("\\U%08X" % ord(c) for c in word)


def hygiene_hits(rel, lineno, text):
    """What is wrong with one line, said without quoting it."""
    where = "%s:%d" % (rel, lineno)
    hits = []
    if _DRIVE_PATH.search(text):
        hits.append(where + " a drive-letter path, which resolves on one seat only")
    if _HOME_PATH.search(text):
        hits.append(where + " a path under a home directory")
    if _SCRATCH_TOKEN in text:
        hits.append(where + " names the gitignored scratch tree, which exists on no other checkout")
    if any(token in text for token in _SANDBOX_TOKENS):
        hits.append(where + " names a local sandbox checkout")
    try:
        decoded = _catalogue_text(text)
    except Undecodable as why:
        # Fails closed: a row whose escapes this gate cannot decode could
        # compile to text it never scanned, so the row is refused.
        hits.append("%s a catalogue row with an undecodable escape (%s): refused, since the "
                    "gate cannot read what it compiles to" % (where, why))
        decoded = ""
    if _ACCOUNT_LABEL.search(_fold(text)) or _ACCOUNT_LABEL.search(_fold(decoded)):
        hits.append(where + " an account label (the maintainer's name joined to a seat number): "
                    "a seat is described by its role, never by its label")
    if _ACCOUNT_NUMBER.search(text) or _ACCOUNT_NUMBER.search(decoded):
        hits.append(where + " a 17-digit run, the form of an account number")
    # The handle words this line may carry: the server lane's product phrase
    # (its word, on the line that carries the phrase) and, on an exempt
    # catalogue row, its own key's handle words. Every other listed handle is
    # refused, in the key and in the translated value alike, in every letter
    # case and compatibility form (_handle_words folds the reading).
    allowed = _phrase_handles(text) | _phrase_handles(decoded) | _key_handles(text)
    for w in _handle_words(text) + _handle_words(decoded):
        if _salted(w) in _HANDLE_DIGESTS and w not in allowed:
            hits.append("%s a personal handle (%d characters): the maintainer is 'Sid' "
                        "in every artifact that leaves this machine, and testers are not "
                        "named at all" % (where, len(w)))
            break
    # Attributions are read in the line as written and, on a catalogue row, in
    # its key and translated value as the game reads them (an attribution
    # spelled with escapes is one too); a word the written reading already
    # captured is not reported a second time.
    raw_who = _attribution_captures(text)
    decoded_who = _attribution_captures(decoded)
    for who in raw_who + [w for w in decoded_who if w not in raw_who]:
        if who == _MAINTAINER or who in _NOT_PEOPLE:
            continue
        hits.append("%s an attribution to a word (%d characters) that is neither the "
                    "maintainer's name nor on the list of words that are not people"
                    % (where, len(who)))
    return hits


def _file_hits(path, rel):
    """Every hit of one file on disk, with its line count."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    return [h for i, t in enumerate(lines, 1) for h in hygiene_hits(rel, i, t)], len(lines)


def _swept_lines():
    out = []
    for rel in _SCOPE:
        assert os.path.isfile(os.path.join(REPO, rel)), (
            "%s is in the scope and is not on disk: the record and the tree "
            "disagree, and the sweep would pass by not reading it" % rel)
        out += [(rel, i, t) for i, t in enumerate(_read(rel).split("\n"), 1)]
    return out


def test_no_file_this_lane_touches_carries_a_path_a_scratch_reference_or_a_name():
    swept = _swept_lines()
    # NativeUI.cs alone is tens of thousands of lines: a short count means the
    # scope was read wrong, not that nothing in it was wrong.
    n_lines = len(swept)
    assert n_lines > 40000, "the sweep read only %d lines" % n_lines
    problems = []
    for rel, lineno, text in swept:
        problems += hygiene_hits(rel, lineno, text)
    assert not problems, (
        "a file this lane touches carries something that may not ship:\n"
        + "\n".join(sorted(set(problems))))


def test_the_detector_refuses_each_class_it_exists_for():
    """The sweep is only as good as the detector, so each class is shown to
    fire on a constructed line (built from pieces, like the detector), and the
    allowed forms are shown not to."""
    def refused(text):
        return bool(hygiene_hits("probe", 1, text))
    drive = "Z" + ":" + "\\" + "work"
    assert refused("// copied from " + drive), "a drive-letter path was accepted"
    assert refused("// see /" + "Us" + "ers/" + "someone/notes"), "a home path was accepted"
    assert refused("// See " + _SCRATCH_TOKEN + "/sept8-polish/ for the source set."), (
        "a scratch-tree reference was accepted")
    assert refused("// the " + _SCRATCH_TOKEN + " notes"), "a bare scratch mention was accepted"
    assert refused("// built in " + _SANDBOX_TOKENS[0] + "x"), "a sandbox name was accepted"
    who = "Some" + "body"
    assert refused("/* Bug #12 (" + who + "): the bar overflowed */"), "a bug attribution was accepted"
    assert refused("// " + who + " reported it twice"), "a reported-by shape was accepted"
    assert refused("// reported by " + who), "a by-shape was accepted"
    assert refused("/* (per " + who + ") */"), "a per-shape was accepted"
    # Difference 4: a name in capitals and a one-letter name are names too.
    capitals = refused("// " + who.upper() + " reported it twice")
    assert capitals, "an attribution to a name in capitals was accepted"
    one_letter = refused("// " + "Q" + " reported it twice")
    assert one_letter, "an attribution to a one-letter name was accepted"
    # Difference 5, each built from its parts: a label for a seat other than
    # the second (the planted-copy test covers the second), and an account
    # number.
    label = refused("// seen on " + _MAINTAINER + str(3) + " only")
    assert label, "an account label was accepted"
    number = refused("// account " + "7" * 17)
    assert number, "a 17-digit account number was accepted"
    # A catalogue value is read as the game reads it: a label written with
    # escapes is a label (difference 3's decoded reading).
    escaped = refused('["Probe"] = "seen on ' + _escaped(_MAINTAINER[0]) + _MAINTAINER[1:] + str(3)
                      + ' only",')
    assert escaped, "an account label written with escapes in a catalogue value was accepted"
    escaped_attribution = any(" an attribution to a word " in h for h in hygiene_hits(
        "probe", 1, '["Probe"] = "' + _escaped(who) + ' reported it twice",'))
    assert escaped_attribution, "an attribution written with escapes in a catalogue value was accepted"
    assert not refused("// Sid reported it twice"), "the maintainer was refused"
    possessive = refused("/// " + _MAINTAINER + "'s screenshot shows it")
    assert not possessive, "the maintainer's screenshot was refused"
    assert not refused("ClickHandler found = null;"), "a declaration was read as a person"
    assert not refused("Nästan svarta block på svart bakgrund"), (
        "a non-ASCII word was split into a handle")
    assert not refused("// " + "Us" + "ers send via hotkey T"), "a bare word was read as a path"
    assert not refused("see docs/faq-refresh-client-contract.md"), "a tracked path was refused"
    sixteen = refused("// a 16-digit run " + "7" * 16 + " and a date 2026-10-11 12:00")
    assert not sixteen, "a 16-digit run or a date was read as an account"


def test_the_gate_lets_no_identifier_through():
    """The gate stores no identifier to exempt. An attribution may carry the
    maintainer's name and nothing else: the list of words that are not people
    holds neither him nor an account label nor a listed handle, and each of its
    words is one the attribution shapes actually meet in these files, so the
    list cannot carry a name no line needs. Counts only on failure."""
    maintainer_listed = _MAINTAINER in _NOT_PEOPLE
    assert not maintainer_listed, "the maintainer is on the list of words that are not people"
    labels = sum(1 for w in _NOT_PEOPLE if _ACCOUNT_LABEL.search(_fold(w)))
    assert labels == 0, "%d entries of the list of words that are not people are account labels" % labels
    handles = sum(1 for w in _NOT_PEOPLE if _salted(w) in _HANDLE_DIGESTS)
    assert handles == 0, "%d entries of the list of words that are not people are listed handles" % handles
    met = set()
    for _rel, _lineno, text in _swept_lines():
        for reading in (text, _catalogue_text(text)):
            met.update(_attribution_captures(reading))
    unmet = len(_NOT_PEOPLE - met)
    assert unmet == 0, (
        "%d entries of the list of words that are not people are met by no attribution "
        "shape in these files: the list may hold only words a line needs" % unmet)


def test_a_second_seat_label_planted_in_a_scratch_copy_is_refused(tmp_path):
    """Bar B7's seat clause on the sweep itself. A scratch copy of
    plugin/NativeUI.cs gains planted lines carrying the second seat's account
    label in the two shapes it stood in before this pass (inside a
    parenthesis, and as the owner of a screenshot) and in the attribution and
    bare forms; also in capitals, joined by an underscore, a hyphen and a
    space, and for every other seat number. The sweep refuses exactly the
    planted lines, each as an account label. The same lines carrying the
    maintainer's name alone pass. Every label is built from its parts at run
    time, so this file spells none, and a failure reports counts only."""
    rel = "plugin/NativeUI.cs"
    source = _read(rel)
    n_source = len(source.split("\n"))
    second = str(1 + 1)
    labels = [_MAINTAINER + second, _MAINTAINER.upper() + second, _MAINTAINER + "_" + second,
              _MAINTAINER + "-" + second, _MAINTAINER + " " + second]
    labels += [_MAINTAINER + str(n) for n in range(1, 10) if str(n) != second]
    forms = (
        "/* the fade must never survive a close (%s in-game check) */",
        "/// <summary>%s's screenshot shows the page title over live gameplay",
        "// %s reported it twice",
        "// seen on %s only",
    )
    planted = [form % label for label in labels for form in forms]
    copy = tmp_path / "NativeUI.planted.cs"
    copy.write_text(source + "\n" + "\n".join(planted) + "\n", encoding="utf-8")
    hits, _n = _file_hits(str(copy), rel)
    where = re.compile(re.escape(rel) + r":([0-9]+) ")
    hit_lines = sorted({int(where.match(h).group(1)) for h in hits})
    label_lines = sorted({int(where.match(h).group(1)) for h in hits if " an account label " in h})
    expected = list(range(n_source + 1, n_source + 1 + len(planted)))
    exact = hit_lines == expected and label_lines == expected
    assert exact, (
        "the sweep of the planted copy: %d planted lines, %d lines refused, %d of them as an "
        "account label, %d refused lines outside the planted ones"
        % (len(planted), len(hit_lines), len(label_lines), len(set(hit_lines) - set(expected))))
    clean = tmp_path / "NativeUI.maintainer.cs"
    clean.write_text(source + "\n" + "\n".join(form % _MAINTAINER for form in forms) + "\n",
                     encoding="utf-8")
    clean_hits, _n = _file_hits(str(clean), rel)
    n_clean = len(clean_hits)
    assert n_clean == 0, "the maintainer's name alone was refused (%d hits on the copy)" % n_clean


def _fullwidth(text):
    """ASCII text in its full-width compatibility form (NFKC maps it back)."""
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)


def test_a_planted_label_is_refused_in_every_case_and_at_every_delimiter():
    """The label class in every letter case and at every delimiter. A planted
    second-seat label, built from its parts at run time, is refused as an
    account label in the bare, possessive and lower-case-subject forms; in
    capitals, mixed case and full width; joined directly, by an underscore, a
    hyphen and one space; and space-joined before every delimiter that ends
    it (colon, semicolon, comma, period, the closing brackets, both quotes,
    slash, hyphen, underscore, question and exclamation marks) and at the end
    of a line. A time, a range, a decimal and a two-digit number after the
    maintainer's name are not labels, and neither is his name alone. A
    failure reports form indices and counts only."""
    second = str(1 + 1)
    joined = _MAINTAINER + second
    spaced = _MAINTAINER + " " + second
    mixed = joined[0].lower() + joined[1:].upper()

    def label_hit(text):
        return any(" an account label " in h for h in hygiene_hits("probe", 1, text))

    forms = [
        "// seen on %s only" % joined,
        "/// <summary>%s's screenshot shows the page title" % joined,
        "// %s reported it twice" % joined.lower(),
        "// %s reported it twice" % spaced.lower(),
        "// %s's report" % joined.lower(),
        "// seen on %s only" % joined.upper(),
        "// seen on %s only" % mixed,
        "// seen on %s only" % _fullwidth(joined),
        "// seen on %s only" % (_MAINTAINER.lower() + "_" + second),
        "// seen on %s only" % (_MAINTAINER.upper() + "-" + second),
        "// seen on " + spaced,
        "// seen on " + spaced.lower(),
        "// seen on " + joined.lower(),
    ]
    for delimiter in (":", ";", ",", ".", ")", "]", "}", ">", '"', "'", "/", "-", "_", "?", "!"):
        forms.append("// seen on %s%s then on the first" % (spaced, delimiter))
        forms.append("// seen on %s%s" % (spaced.lower(), delimiter))
    missed = [i for i, form in enumerate(forms) if not label_hit(form)]
    assert not missed, "%d of %d planted label forms were not refused as a label (forms %s)" % (
        len(missed), len(forms), missed)
    numbers = [_MAINTAINER + " " + second + tail for tail in (":30", "-3", "/3", ".5", ",5", "0")]
    numbers += ["// " + _MAINTAINER + " asked twice", "// per " + _MAINTAINER + ", " + second + " runs"]
    read = [i for i, form in enumerate(numbers) if label_hit(form)]
    assert not read, "%d of %d number or name forms were read as a label (forms %s)" % (
        len(read), len(numbers), read)


def test_a_listed_handle_is_refused_in_every_case_and_form(monkeypatch):
    """The handle digests in every letter case and form. A synthetic word,
    listed for this test only, is refused as a personal handle capitalised,
    in lower case, in capitals, in mixed case and full width; as the subject
    of a verb, a possessive, inside a parenthesis before a number, after a
    dash, joined to a digit or an underscore, and in a catalogue value
    spelled with escapes. Unlisted, the same lines carry no personal handle,
    so the refusals are the digest's. A failure reports form indices only."""
    word = "Quil" + "lonax"
    forms = [
        "// %s reported it twice" % word,
        "// %s reported it twice" % word.lower(),
        "// %s reported it twice" % word.upper(),
        "// %s reported it twice" % (word[:3].lower() + word[3:].upper()),
        "// %s reported it twice" % _fullwidth(word),
        "// so the colour reverted (%s's report)" % word.lower(),
        "// clicks hit the buttons behind it (%s #14)" % word.lower(),
        "// narrower than before — %s wanted it shorter" % word.lower(),
        "// seen on %s_%d only" % (word.lower(), 1 + 1),
        "// seen on %s%d only" % (word.lower(), 1 + 1),
        '["Probe"] = "seen by %s",' % _escaped(word.lower()),
    ]

    def handle_hit(text):
        return any(" a personal handle " in h for h in hygiene_hits("probe", 1, text))

    unlisted = [i for i, form in enumerate(forms) if handle_hit(form)]
    assert not unlisted, "the unlisted word was refused as a handle (forms %s)" % unlisted
    monkeypatch.setitem(globals(), "_HANDLE_DIGESTS", _HANDLE_DIGESTS | {_salted(word)})
    missed = [i for i, form in enumerate(forms) if not handle_hit(form)]
    assert not missed, "%d of %d forms of a listed handle were not refused (forms %s)" % (
        len(missed), len(forms), missed)


def test_every_csharp_escape_is_decoded_or_the_row_is_refused():
    """The catalogue decoder against every C# character escape. A planted
    second-seat label (built from its parts) appended to a real catalogue
    row's translated value is refused as an account label when spelled with
    \\u, \\x (four digits, and the shortest form) and \\U escapes; each
    simple escape decodes to its character; an escape the decoder cannot
    decode refuses the row by name (fails closed); and every row of the real
    catalogue decodes, so the production catalogue reads as it did. Counts
    and indices only on failure."""
    label = _MAINTAINER + str(1 + 1)
    rel = "plugin/I18nCatalogues.cs"
    rows = [(i, t) for i, t in enumerate(_read(rel).split("\n"), 1) if _CATALOGUE_ENTRY.match(t)]
    assert len(rows) > 1000, "only %d catalogue rows were read" % len(rows)
    undecodable = [i for i, t in rows if any(" an undecodable escape " in h for h in hygiene_hits(rel, i, t))]
    assert not undecodable, "%d real catalogue rows do not decode (lines %s)" % (len(undecodable), undecodable[:10])
    lineno, text = rows[len(rows) // 2]
    at = _CATALOGUE_ENTRY.match(text).end(2)
    shortest_x = "".join("\\x%x" % ord(c) for c in label[:-1]) + "\\x%04x" % ord(label[-1])
    spellings = [_escaped(label), _escaped_x(label), shortest_x, _escaped_big_u(label),
                 label[:1] + _escaped_x(label[1:2]) + label[2:]]
    missed = [k for k, spelled in enumerate(spellings)
              if not any(" an account label " in h for h in hygiene_hits(rel, lineno, text[:at] + " " + spelled + text[at:]))]
    assert not missed, "%d of %d escaped spellings of a planted label were not refused (spellings %s)" % (
        len(missed), len(spellings), missed)
    simple = {"\\'": "'", '\\"': '"', "\\\\": "\\", "\\0": "\0", "\\a": "\a", "\\b": "\b",
              "\\f": "\f", "\\n": "\n", "\\r": "\r", "\\t": "\t", "\\v": "\v", "\\e": "\x1b"}
    wrong = [k for k, v in simple.items() if _cs_literal("a" + k + "b") != "a" + v + "b"]
    assert not wrong, "%d simple escapes decode wrongly" % len(wrong)
    pair = _cs_literal("\\ud83d\\ude00") == _cs_literal("\\U0001F600") == chr(0x1F600)
    assert pair, "a surrogate pair and its \\U form do not decode to the same character"
    bad = ["\\q", "\\u12G4", "\\u12", "\\x", "\\xg", "\\U0011FFFF", "\\U0001F60", "\\"]
    passed = [k for k, b in enumerate(bad)
              if not any(" an undecodable escape " in h for h in hygiene_hits(
                  rel, lineno, '["Probe"] = "x' + b + 'y",'))]
    assert not passed, "%d of %d undecodable escapes were not refused (escapes %s)" % (
        len(passed), len(bad), passed)


def test_an_exempt_row_lets_only_its_own_key_s_handle_words_through():
    """Difference 3 on the real catalogue. Every exempt row passes as it
    stands, and its own product token appended to its translated value again
    still passes; the same row with a listed handle its key does not carry
    appended to its translated value is refused, written plainly or with
    escapes only. The foreign handle is taken from another exempt row by its
    digest at run time, so this file spells none, and every mutated row is
    built in memory, never written. A failure reports line numbers and counts
    only."""
    rel = "plugin/I18nCatalogues.cs"
    rows = []
    for lineno, text in enumerate(_read(rel).split("\n"), 1):
        own = _key_handles(text)
        if own:
            rows.append((lineno, text, own))
    n_rows = len(rows)
    assert n_rows > 0, "no exempt catalogue row was read: this probe has no subject"
    handles = set()
    for _lineno, _text, own in rows:
        handles |= own
    n_handles = len(handles)
    assert n_handles >= 2, (
        "the exempt rows carry %d listed handle(s); appending one row's to another's "
        "translation needs two" % n_handles)
    refused_as_is, passed_foreign, refused_own, foreign_tries = [], [], [], 0
    for lineno, text, own in rows:
        if hygiene_hits(rel, lineno, text):
            refused_as_is.append(lineno)
        at = _CATALOGUE_ENTRY.match(text).end(2)
        for word in sorted(handles - own):
            for spelled in (word, _escaped(word)):
                foreign_tries += 1
                mutated = text[:at] + " " + spelled + text[at:]
                if not any(" a personal handle " in h for h in hygiene_hits(rel, lineno, mutated)):
                    passed_foreign.append(lineno)
        for word in sorted(own):
            for spelled in (word, _escaped(word)):
                again = text[:at] + " " + spelled + text[at:]
                if hygiene_hits(rel, lineno, again):
                    refused_own.append(lineno)
    n_as_is, n_foreign, n_own = len(refused_as_is), len(passed_foreign), len(refused_own)
    assert n_as_is == 0, "%d exempt rows refused as they stand (lines %s)" % (n_as_is, refused_as_is[:10])
    assert foreign_tries > 0, "no foreign handle could be appended to any exempt row"
    assert n_foreign == 0, (
        "%d of %d exempt rows passed with a listed handle their key does not carry appended to "
        "the translated value (lines %s)" % (n_foreign, foreign_tries, passed_foreign[:10]))
    assert n_own == 0, (
        "%d exempt rows were refused with their own product token appended again (lines %s)"
        % (n_own, refused_own[:10]))


def lane_range(repo, base):
    """The lane's range as git measures it in `repo`: every commit from the
    merge-base of HEAD with `base` to HEAD, whatever it touches, and every
    path each of them touches (a rename counted as a deletion and an
    addition). Returns (state, detail, commits, touched): "absent" when
    `base` is not a commit there (detail says why); "merged" when the range
    holds a merge commit (detail lists them); else "linear" (detail is the
    merge-base)."""
    def git(*args):
        return subprocess.run(["git", "-C", repo, "-c", "core.quotePath=false"] + list(args),
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    probe = git("rev-parse", "--verify", "--quiet", base + "^{commit}")
    if probe.returncode != 0:
        return "absent", ((probe.stderr or "").strip() or "not a commit here")[:80], [], set()
    mb = git("merge-base", "HEAD", base)
    assert mb.returncode == 0, mb.stderr or mb.stdout
    start = mb.stdout.strip()
    merges = git("rev-list", "--merges", start + "..HEAD")
    assert merges.returncode == 0, merges.stderr or merges.stdout
    if merges.stdout.split():
        return "merged", merges.stdout.split(), [], set()
    listed = git("rev-list", "--reverse", start + "..HEAD")
    assert listed.returncode == 0, listed.stderr or listed.stdout
    commits = listed.stdout.split()
    touched = set()
    for sha in commits:
        shown = git("diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", sha)
        assert shown.returncode == 0, shown.stderr or shown.stdout
        touched.update(n.strip() for n in shown.stdout.split("\n") if n.strip())
    return "linear", start, commits, touched


def test_the_scope_is_every_file_this_lane_touches():
    """Both directions against the lane's range as git measures it
    (lane_range): every path a commit of the range touches must be recorded
    in the scope, and every recorded file must be touched by one. A clone
    without the certified client base, or a copy that is not a repository,
    skips and says why; so does a range that holds a merge commit, where HEAD
    has merged another line whose commits git cannot tell from this lane's
    (the fold into the client lane does that). The sweep needs no history
    and runs in every case."""
    state, detail, commits, touched = lane_range(REPO, _CLIENT_BASE)
    if state == "absent":
        pytest.skip("the certified client base %s is not reachable here (%s), so this "
                    "lane's range cannot be measured" % (_CLIENT_BASE, detail))
    if state == "merged":
        pytest.skip("the range from the merge-base of HEAD with %s holds %d merge commit(s) "
                    "(%s): HEAD has merged another line, so the range is no longer this "
                    "lane's alone" % (_CLIENT_BASE, len(detail),
                                      ", ".join(c[:8] for c in detail[:4])))
    n_commits = len(commits)
    assert n_commits >= 3, (
        "git measured %d commits from the merge-base %s to HEAD; this lane has at "
        "least three (one per item)" % (n_commits, detail[:8]))
    unrecorded = sorted(touched - set(_SCOPE))
    assert not unrecorded, (
        "a commit of the lane range touched %s, which the scope does not record" % unrecorded)
    untouched = sorted(set(_SCOPE) - touched)
    assert not untouched, (
        "the scope records %s, which no commit of the lane range touched" % untouched)


def test_the_range_check_sees_a_commit_that_touches_no_scope_file(tmp_path):
    """lane_range on a repository built here, so the property is shown on a
    history whose every commit is known. Three lane commits touching the five
    scope files make a linear range that is exactly the scope; one more
    commit touching only a new path (no scope file, no anchor of any kind)
    is in the range with its path, so the scope check refuses it; and a
    merge in the range reports the range as merged, never as the lane's."""
    repo = tmp_path / "lane"
    repo.mkdir()

    def git(*args):
        r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=lane-probe",
                            "-c", "user.email=lane-probe@example.invalid",
                            "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"] + list(args),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, "git %s failed: %s" % (args[0], (r.stderr or r.stdout).strip()[:200])
        return r.stdout.strip()

    def commit(paths, message):
        for rel in paths:
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(message + "\n", encoding="utf-8")
        git("add", "--", *paths)
        git("commit", "-q", "-m", message)
        return git("rev-parse", "HEAD")

    git("init", "-q")
    base = commit(["README.txt"], "the base")
    commit(list(_SCOPE[:2]), "lane item one")
    commit(list(_SCOPE[2:4]), "lane item two")
    commit(list(_SCOPE[4:]), "lane item three")
    state, start, commits, touched = lane_range(str(repo), base)
    exact = state == "linear" and start == base and len(commits) == 3 and touched == set(_SCOPE)
    assert exact, "the three-commit range read %s, %d commits, %d paths" % (state, len(commits), len(touched))
    commit(["docs/elsewhere.txt"], "a commit that touches no scope file")
    state, start, commits, touched = lane_range(str(repo), base)
    unrecorded = sorted(touched - set(_SCOPE))
    seen = state == "linear" and len(commits) == 4 and unrecorded == ["docs/elsewhere.txt"]
    assert seen, "the commit that touches no scope file was not seen: %s, %d commits, %d unrecorded" % (
        state, len(commits), len(unrecorded))
    git("checkout", "-q", "-b", "another-line", base)
    commit(["another.txt"], "another line")
    git("checkout", "-q", "-")
    git("merge", "-q", "--no-ff", "-m", "merge another line", "another-line")
    state, detail, _commits, _touched = lane_range(str(repo), base)
    merged = state == "merged" and len(detail) == 1
    assert merged, "a range holding a merge commit read as %s" % state
