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
by test_the_scope_is_every_file_this_lane_touches: this lane's commits are the
ones after the branch point that touch one of this lane's three test modules,
every file such a commit touched must be in the scope, and every file in the
scope must have been touched by one. The sweep itself needs no history.

THE DETECTOR is the FAQ server lane's (backend/tests/test_faq_surfaces.py,
its section 3), ported with its salt, its handle digests and its attribution
shapes unchanged, so this lane refuses everything that one does. Five
differences, each stated where it lives below: words are Unicode words; one
handle is added; shipped product strings that name a community member on
purpose are exempt by their exact English text, on catalogue lines only; an
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

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SCOPE = (
    "backend/tests/test_faq_client_hygiene.py",
    "backend/tests/test_faq_client_ladder.py",
    "backend/tests/test_faq_client_upload_caps.py",
    "plugin/I18nCatalogues.cs",
    "plugin/NativeUI.cs",
)

# The commit this lane's first commit sits on, and the files every commit of
# the lane touches one of (so the lane's commits stay identifiable after it
# merges, when everything after the branch point also holds other lanes' work).
_BRANCH_POINT = "6c46b71e"
_LANE_ANCHORS = (
    "backend/tests/test_faq_client_hygiene.py",
    "backend/tests/test_faq_client_ladder.py",
    "backend/tests/test_faq_client_upload_caps.py",
)

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

_HANDLE_SALT = "scr-faq-item11-handle-blocklist-v1"
# The server lane's four digests, unchanged, plus one (difference 2): a
# community member whose handle stood in four comments of these files, in the
# shapes "(handle, date; ...)" and "batch (handle's charts)" that no
# attribution shape below recognises.
_HANDLE_DIGESTS = frozenset([
    "422aec928bf8edfddc358c6f59ede0b2b7306bebcd6cf798e900044d0309e9f8",
    "4412d9ea108a8a78983534ec345969267c9e40b53c88b7a6079177a23c85a673",
    "73f5adebce4448ae85fc7f6c505207716e70f88e3b0bff43072afb7508850c04",
    "fe7ed63ab5330c6fe2cd7fa73aa921339026008bbd51adca63fda318c424eaee",
    "1836e76c09dd1c1847d37f79b79dafff0666da2c2b6d23bfa2462eebac56330e",
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
# English KEY is exactly one of these is product content, translated, and its
# handle words are not refused. Exact text, so a new sentence naming either
# person is refused until somebody decides it is product content too and
# lists it. Each digest is sha256(salt + "string:" + the English source).
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
# sees a label inside a parenthesis). The shape: the name capitalised or in
# capitals, then a digit, joined directly or by an underscore or a hyphen, or
# after one space when the digit does not begin a number, a time or a range.
# The lower-case form is not a name: in these files it is the code's own
# steam-id variables. An account number is any 17-digit run, the class every
# evidence log of this lane masks.
_ACCOUNT_LABEL = re.compile(
    r"(?<![A-Za-z0-9_])(?:" + _MAINTAINER + "|" + _MAINTAINER.upper() + r")"
    r"(?:[_-]?[0-9]|\s[0-9](?![0-9:/-]))")
_ACCOUNT_NUMBER = re.compile(r"(?<![0-9])[0-9]{17}(?![0-9])")

_NAME = r"([A-Z][A-Za-z0-9_]*)"
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
    return hashlib.sha256((_HANDLE_SALT + text.lower()).encode("utf-8")).hexdigest()


def _cs_literal(body):
    out, i = [], 0
    simple = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "0": "\0"}
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            n = body[i + 1]
            if n == "u":
                out.append(chr(int(body[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(simple.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _product_line(text):
    m = _CATALOGUE_ENTRY.match(text)
    if not m:
        return False
    key = _cs_literal(m.group(1))
    digest = hashlib.sha256((_HANDLE_SALT + "string:" + key).encode("utf-8")).hexdigest()
    return digest in _PRODUCT_STRING_DIGESTS


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
    if _ACCOUNT_LABEL.search(text):
        hits.append(where + " an account label (the maintainer's name joined to a seat number): "
                    "a seat is described by its role, never by its label")
    if _ACCOUNT_NUMBER.search(text):
        hits.append(where + " a 17-digit run, the form of an account number")
    words = _WORD.findall(text)
    product = {a.lower() for a, b in zip(words, words[1:]) if _salted(a + " " + b) in _HANDLE_PHRASE_DIGESTS}
    if not _product_line(text):
        for w in words:
            if _salted(w) in _HANDLE_DIGESTS and w.lower() not in product:
                hits.append("%s a personal handle (%d characters): the maintainer is 'Sid' "
                            "in every artifact that leaves this machine, and testers are not "
                            "named at all" % (where, len(w)))
                break
    for shape in _ATTRIBUTION_SHAPES:
        for m in shape.finditer(text):
            who = m.group(1)
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
    labels = sum(1 for w in _NOT_PEOPLE if _ACCOUNT_LABEL.search(w))
    assert labels == 0, "%d entries of the list of words that are not people are account labels" % labels
    handles = sum(1 for w in _NOT_PEOPLE if _salted(w) in _HANDLE_DIGESTS)
    assert handles == 0, "%d entries of the list of words that are not people are listed handles" % handles
    met = set()
    for _rel, _lineno, text in _swept_lines():
        for shape in _ATTRIBUTION_SHAPES:
            met.update(m.group(1) for m in shape.finditer(text))
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


def test_the_scope_is_every_file_this_lane_touches():
    """Both directions against the history the record summarises. A clone
    without the branch point, or a copy that is not a repository at all,
    skips this half and says why; the sweep itself needs no history."""
    def git(*args):
        return subprocess.run(["git", "-C", REPO] + list(args), capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    probe = git("rev-parse", "--verify", _BRANCH_POINT + "^{commit}")
    if probe.returncode != 0:
        pytest.skip("the branch point %s is not reachable here (%s), so this lane's "
                    "commits cannot be listed" % (_BRANCH_POINT, (probe.stderr or "").strip()[:80]))
    log = git("log", "--no-merges", "--format=%H", _BRANCH_POINT + "..HEAD", "--", *_LANE_ANCHORS)
    assert log.returncode == 0, log.stderr or log.stdout
    commits = log.stdout.split()
    assert len(commits) >= 3, (
        "git log found %d commits of this lane after %s; it has at least three "
        "(one per item)" % (len(commits), _BRANCH_POINT))
    touched = set()
    for sha in commits:
        shown = git("show", "--format=", "--name-only", sha)
        assert shown.returncode == 0, shown.stderr or shown.stdout
        touched.update(n.strip() for n in shown.stdout.split("\n") if n.strip())
    unrecorded = sorted(touched - set(_SCOPE))
    assert not unrecorded, "a commit of this lane touched %s, which the scope does not record" % unrecorded
    untouched = sorted(set(_SCOPE) - touched)
    assert not untouched, "the scope records %s, which no commit of this lane touched" % untouched
