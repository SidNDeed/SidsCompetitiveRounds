"""Bar B7 over every file the FAQ refresh's client lane touches: no
drive-letter or home-directory path, no reference into the gitignored scratch
tree or a local sandbox checkout, no tester's handle, and no attribution to
anybody but the maintainer, on any line of any of those files.

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
shapes unchanged, so the two lanes refuse the same things. Three differences,
each stated where it lives below: words are Unicode words; one handle is
added; and shipped product strings that name a community member on purpose
are exempt by their exact English text, on catalogue lines only.

THE DETECTOR DOES NOT SPELL ITS OWN TARGET. This module is in the scope, so a
pattern written as a literal would match its own source, and the only way to
keep it green would be to exclude it, which is how a check stops being able
to fail. Tokens are assembled from pieces, paths are written as patterns and
never as examples, and handles and product strings appear only as digests.
A hit is reported by file, line and class, never by quoting it.
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
# Words the shapes meet in these files that are not people: the server lane's
# list, plus the maintainer's second test seat, the C# types that precede
# "found" in declarations ("ClickHandler found = null;"), the update method a
# comment says it is called from ("(from Tick, ..."), the generic noun in
# "User reported", and the tab a bug title names ("Bug #130: My Stats").
_NOT_PEOPLE = frozenset([
    "Sid",
    "Aug", "GameStateWatcher", "Games", "Match", "None", "Not", "Nothing",
    "Question", "Queue", "That", "The",
    "Sid2", "ClickHandler", "Component", "CardInfo", "Tick", "User", "My",
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
            if who in _NOT_PEOPLE or len(who) == 1 or who.isupper():
                continue
            hits.append("%s an attribution to a word (%d characters) that is not on the "
                        "list of words that are not people" % (where, len(who)))
    return hits


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
    assert not refused("// Sid reported it twice"), "the maintainer was refused"
    assert not refused("ClickHandler found = null;"), "a declaration was read as a person"
    assert not refused("Nästan svarta block på svart bakgrund"), (
        "a non-ASCII word was split into a handle")
    assert not refused("// " + "Us" + "ers send via hotkey T"), "a bare word was read as a path"
    assert not refused("see docs/faq-refresh-client-contract.md"), "a tracked path was refused"


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
