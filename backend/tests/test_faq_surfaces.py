"""Item 11 — the FAQ's numbers, checked against the code that produces them.

The mod tells players the same facts in four places: docs/FAQ.md, the Discord
responder's FAQ_ENTRIES, the in-game Info library, and the already-posted
#scr-faq messages (which carry docs/FAQ.md's text through a migration). They
drifted independently because nothing failed when they disagreed — the artist
answer still said animated cosmetics were unsupported weeks after the uploader
shipped GIF and frame submission, and the async-tournament cadence still quoted
a 6-week calendar the scheduler had stopped using.

So the table of claims is a FIXTURE, not prose: fixtures/faq_claims.json names
each number, the one line of code that decides it, and every surface that
states it. A prose table nobody executes decays into a false "verified"
(#302 — a documentation line is a claim; #342/#431 — a check that cannot fail
certifies nothing).

Where this file corrects a GUARANTEE in a comment, that sentence is pinned by
the behavioural test covering the code beneath it: _states_at for a docstring,
_function_source for an inline comment, and a plain substring for the two
migration headers that make a claim about the client lane. Otherwise a
prose-only reversion of something like "the ack records only what the caller
rendered" stays green while the file goes back to being wrong about itself.
The bound: migration 338's header is NOT pinned sentence by sentence. What it
describes is the hand-out and ack behaviour the Postgres tests below already
own, so a reversion there produces a comment that disagrees with tested
behaviour rather than one that hides untested behaviour.

The Postgres tests are skipped unless FAQ_TEST_PG_DSN points at a database, the
same convention test_a1_predicate_sql.py uses so the ordinary suite stays
hermetic:

    FAQ_TEST_PG_DSN="postgresql://postgres@127.0.0.1:55432/faqtest" \
        python -m pytest backend/tests/test_faq_surfaces.py -q

The client is psql, found on PATH or named by FAQ_TEST_PSQL; with neither,
the Postgres tests skip and say so.

55432 is this seat's standing port for that PostgreSQL 16.9 instance and the
port the other two DSN-gated test files document. It is NOT a property of the
data directory: that cluster's postgresql.conf leaves `port` commented out, so
the port is whatever the server was LAUNCHED with, and one round's runs went
against the same instance started on the built-in 5432. A documented DSN that
refuses to connect is worse than no line at all, because the runs then happen
against some other string and the evidence stops naming the server that
produced it. test_the_harness_names_the_server_it_ran_on pins the connection
instead of the prose: it reports what actually answered, reds if that is not
the server the DSN asked for, and reds if the line above does not reach that
same server. It does NOT compare port literals — the port is a correlate of
the server, not the server (#732).
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "faq_claims.json")
MIGRATION = os.path.join(REPO, "backend", "sql", "338_faq_channel_post_revisions.sql")
FAQ_MD = os.path.join(REPO, "docs", "FAQ.md")
BOT = os.path.join(REPO, "backend", "discord_bot.py")
NATIVE_UI = os.path.join(REPO, "plugin", "NativeUI.cs")


def _read(rel_or_abs):
    path = rel_or_abs if os.path.isabs(rel_or_abs) else os.path.join(REPO, rel_or_abs)
    # newline="" then an explicit replace: the plugin sources are checked out
    # CRLF on Windows and the fixture's literals are written LF, exactly the
    # trap tools/i18n_extract.py documents.
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n")


_FIXTURE_CACHE = None


def claims():
    global _FIXTURE_CACHE
    if _FIXTURE_CACHE is None:
        with io.open(FIXTURE, encoding="utf-8") as fh:
            _FIXTURE_CACHE = json.load(fh)["claims"]
    return _FIXTURE_CACHE


def ids():
    return [c["id"] for c in claims()]


# ── 1. Every claim is pinned to code that still exists ───────────────────────

def test_every_claim_has_an_anchor():
    """The anchor regex must match its file EXACTLY once.

    Zero matches means the knob was renamed or deleted and the claim is now
    unpinned. More than one means the pattern is loose enough to be reading a
    different line than the author meant — both are the failure this file
    exists to catch, so neither is tolerated (#432: assert the occurrence
    count, do not assume it).

    `also` carries the DUPLICATES of the same number: a second enforcement of
    one rule, on the other side of the wire or in another row of the same
    table. A number the player meets is often checked twice — the frame cap by
    the server AND by the client's own scan, the FFA point target by the SQL
    column default AND by the server map AND by the client field, an
    achievement tier by every key priced at it — and a claim anchored on one
    copy goes green while the copy the player actually hits moves. Each
    `also` pattern is held to the same exactly-once rule and to the SAME
    value, so there is no copy of the number this fixture does not read."""
    problems = []
    for c in claims():
        sites = [c["anchor"]] + list(c.get("also", []))
        for site in sites:
            body = _read(site["file"])
            found = re.findall(site["pattern"], body, re.M)
            if len(found) != 1:
                problems.append(
                    "%s: pattern matched %d times in %s (expected exactly 1)"
                    % (c["id"], len(found), site["file"]))
                continue
            if found[0] != c["value"]:
                problems.append(
                    "%s: %s says %r, the fixture claims %r"
                    % (c["id"], site["file"], found[0], c["value"]))
    assert not problems, "\n".join(problems)


# ── 2. Every surface states the same number ──────────────────────────────────

def test_surfaces_agree():
    """Each surface sentence must be present verbatim AND contain the number.

    The second half is what makes this more than a grep: a surface cannot pass
    by mentioning the subject. The achievement payout is the worked example —
    docs/FAQ.md said a flat 100g each, the Info library said 100 by default
    with a 1000 ceiling, and the responder named two trophy keys at 1000 and
    implied everything else paid 100. Three phrasings of one fact, two of them
    wrong, and the true shape is a four-value ladder
    (ACHIEVEMENT_GOLD_OVERRIDES, pinned by the tier claims and by
    test_achievement_tiers_are_exhaustive)."""
    problems = []
    for c in claims():
        display = c.get("display", c["value"])
        for surface in c["surfaces"]:
            body = _read(surface["file"])
            text = surface["text"]
            if display not in text:
                problems.append(
                    "%s: fixture surface text for %s does not contain %r — the row "
                    "would pass without stating the number"
                    % (c["id"], surface["file"], display))
                continue
            if text not in body:
                problems.append(
                    "%s: %s no longer contains %r"
                    % (c["id"], surface["file"], text))
    assert not problems, "\n".join(problems)


def test_a_client_lane_surface_is_recorded_as_owed_not_as_present():
    """Five of item 11's numbers live in text only plugin/InfoLibrary.cs can
    state, and round four restored every plugin/ file to the branch base: that
    half is the client lane's step, written down for it in
    docs/faq-refresh-client-contract.md. Listing those as surfaces would
    assert an edit this branch deliberately does not carry, so they sit in
    `owed_to_client_lane` instead — and this is the tripwire that fires the
    moment the client lane applies them, so the row moves back into `surfaces`
    in the same change instead of being forgotten there.

    THE TWO GOLD-LADDER ROWS ARE HERE FOR A SECOND REASON. They used to sit
    under `surfaces`, asserting a PREFIX of the ladder line — the part the
    correction does not touch. That is true before the client lane's edit and
    equally true after it, so nothing in this file could fire for the ladder at
    all: the tripwire existed for three of the five numbers and not for the two
    where the edit is an append (#342 — a check that cannot fail). As owed rows
    they carry the whole line, before and after, so the predecessor is pinned
    and the successor fires.

    THIS FIXTURE ROW IS THE HAND-OFF, and the fuller note with the code
    anchors is TRACKED beside it in docs/. It used to live in the gitignored
    scratch tree, so every file that pointed at it pointed at nothing on every
    other checkout — the row said work was owed and the document saying WHAT
    was owed did not exist there.
    test_no_file_this_item_touches_names_a_person_a_local_path_or_the_scratch_tree
    is what holds that now. The row still carries what the client lane needs on
    its own — the file, the sentence to write and the sentence it replaces — so
    it remains checkable without reading any prose.

    Each owed row is held to four things: it states the claim's number, it
    names a file under plugin/ (the lane that owes it), that file still carries
    the text the correction replaces and NOT the corrected text, and exactly
    one edit of REKEY_EDITS — the same table 340's bijection is checked
    against — turns the row's own predecessor into it. That last check is
    applied to the ROW's strings, never to the client file: the file is what
    is being judged, and a check that applied the table to it first would
    repair a partial application before looking at it. It is what keeps the
    fixture and the migration describing ONE edit rather than two independent
    guesses. Each row is judged on its own, so a ladder applied in part reds
    on the row that was applied."""
    every_edit = [pair for edits in REKEY_EDITS.values() for pair in edits]

    owed = 0
    problems = []
    for c in claims():
        display = c.get("display", c["value"])
        for row in c.get("owed_to_client_lane", []):
            owed += 1
            if display not in row["text"]:
                problems.append(
                    "%s: owed text %r for %s does not contain %r — the row "
                    "would pass without stating the number"
                    % (c["id"], row["text"], row["file"], display))
                continue
            if not row["file"].startswith("plugin/"):
                problems.append(
                    "%s: %s is not a client-lane file — a surface this branch "
                    "owns may not be recorded as owed to another lane"
                    % (c["id"], row["file"]))
                continue
            body = _read(row["file"])
            if row["replaces"] not in body:
                problems.append(
                    "%s: %s no longer contains %r, the text this correction "
                    "replaces" % (c["id"], row["file"], row["replaces"]))
            if row["text"] in body:
                problems.append(
                    "%s: %s ALREADY contains %r — the client lane has applied "
                    "its half, so this row belongs under `surfaces` where "
                    "test_surfaces_agree holds it"
                    % (c["id"], row["file"], row["text"]))
            # The row's two strings are tied to the table by ONE edit applied
            # to the row's own predecessor — never to the client file, which
            # is the thing being judged here and may not be repaired before it
            # is judged (#342/#391).
            produced = [after for before, after in every_edit
                        if before in row["replaces"]
                        and row["text"] in row["replaces"].replace(before, after)]
            if len(produced) != 1:
                problems.append(
                    "%s: %d of the correction table's edits turn the row's "
                    "predecessor into %r (expected exactly one) — the fixture "
                    "and 340 describe different edits"
                    % (c["id"], len(produced), row["text"]))
    assert not problems, "\n".join(problems)
    assert owed == 5, (
        "expected item 11's five client-lane surfaces to be recorded as "
        "owed, found %d" % owed)


# ── 3. No file this item touches carries a local path, a scratch reference
#       or an attribution────────────────────────────────────────────────────
#
# THE SCOPE IS EVERY LINE OF EVERY FILE THIS ITEM TOUCHES. Round 4's control
# swept only the lines the range ADDED, read off `git diff <branch point>`,
# and left the lines other lanes had written into the same files to a scrub
# lane that was never opened. Both halves fell short of the review's bar. A
# file ships whole: a scratch reference or an attribution another lane wrote
# into main.py ships with this item's merge exactly as much as one written
# here, and round 4's review found unresolved scratch references and an
# attribution in precisely that gap. And a range read from the branch point
# does not stay this item's: once the branch merges, `git diff <branch point>`
# on main names every file every other lane has changed since (427 under the
# shipped trees at the time of writing), so the control would go red on work
# it never saw — the kind of guard somebody turns off rather than fixes (#430).
#
# So the files are RECORDED, and the record is checked against the history it
# summarises by test_the_hygiene_scope_is_every_file_this_item_touches: every
# file a commit of this item touched is either swept or handed back, and
# nothing is swept that no commit of this item touched. The sweep reads the
# working tree, so it is live while a change is being written, and it needs
# no history, so it runs on any checkout, a shallow clone included.
#
# THE HANDED-BACK FILES are the client lane's. Earlier commits of this item
# edited them and later ones restored each byte-for-byte to the branch point
# (a diff of plugin/ and tools/ against it is empty), so this item's net
# change to them is nothing and their content is not its to rewrite: they ship
# with the client lane, under that lane's review.
#
# THE DETECTOR DOES NOT SPELL ITS OWN TARGET. This file is in the scope, so a
# pattern written out as a literal would match its own source, and the only
# way to keep the control green would then be to exclude the control — which
# is how a check stops being able to fail (#342). Every token below is
# assembled from pieces, the path patterns are written as patterns and never
# as examples, and the handles are present only as digests.
_HYGIENE_SCOPE = (
    "backend/api/main.py",
    "backend/api/tournaments.py",
    "backend/discord_bot.py",
    "backend/sql/338_faq_channel_post_revisions.sql",
    "backend/sql/340_i18n_keys_item11.sql",
    "backend/sql/341_seed_machine_translations_item11.sql",
    "backend/tests/fixtures/faq_claims.json",
    "backend/tests/route_manifest_net_seat.json",
    "backend/tests/test_faq_surfaces.py",
    "backend/tests/test_mail_bot.py",
    "docs/FAQ.md",
    "docs/faq-refresh-client-contract.md",
)

_HANDED_BACK = (
    "plugin/I18nCatalogues.cs",
    "plugin/I18nSourceKeys.g.cs",
    "plugin/InfoLibrary.cs",
    "plugin/NativeUI.cs",
    "tools/i18n_source.json",
)

# The commit this item's first commit sits on. Only the scope check needs it.
_BRANCH_POINT = "0266237"

# Every commit of this item that changes code or prose touches one of these,
# which is how its commits are told apart from other lanes' once the branch
# has merged. A re-pin of the route manifest is committed alone and touches
# neither, so it is not counted — and needs no counting, because the manifest
# is in the scope by record.
_ITEM_ANCHORS = ("backend/tests/test_faq_surfaces.py",
                 "backend/tests/fixtures/faq_claims.json")

# A DRIVE-LETTER PATH, any of them and not only one under a home directory: a
# path that resolves on one seat is wrong on every other (round 4's psql
# default was one, and a fresh checkout with only the DSN set selected a client
# that was not there). Not preceded by a word character, so a seeded locale's
# "word:\n" is prose; not followed by a second separator, so a URL scheme is
# not a drive.
_DRIVE_PATH = re.compile(r"(?<!\w)[A-Za-z]:[\\/](?![\\/])")
_HOME_PATH = re.compile(
    r"(?<![\w.])/(?:" + "ho" + "me|" + "Us" + r"ers)/[A-Za-z0-9_.-]+")
_SCRATCH_TOKEN = "ai" + "-collab"
_SANDBOX_TOKENS = ("scr" + "-wt-", "scr" + "-codex")

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

# A PUBLIC salt and the salted sha256 of each handle that may not appear in a
# tracked file. The plaintext list is not in the repo: a blocklist written out
# is the disclosure it exists to prevent, and a scrub that signposts itself is
# not a scrub (#133/#134). The salt is not doing a secret's work — it only
# stops the digests being readable straight off a table of bare words — and a
# short word's digest can be recovered by brute force, so nothing the pre-push
# guard protects is ever listed here: that class is the guard's
# (test_the_privacy_oracle_is_the_pre_push_hook). "Sid" is the sanctioned
# maintainer name and is not among them.
_HANDLE_SALT = "scr-faq-item11-handle-blocklist-v1"
_HANDLE_DIGESTS = frozenset([
    "422aec928bf8edfddc358c6f59ede0b2b7306bebcd6cf798e900044d0309e9f8",
    "4412d9ea108a8a78983534ec345969267c9e40b53c88b7a6079177a23c85a673",
    "73f5adebce4448ae85fc7f6c505207716e70f88e3b0bff43072afb7508850c04",
    "fe7ed63ab5330c6fe2cd7fa73aa921339026008bbd51adca63fda318c424eaee",
])

# PRODUCT TERMS THAT CONTAIN ONE OF THOSE WORDS, and are allowed anyway,
# hashed the same way as two-word phrases. One of the mod's shipped
# achievements is named after a community member; the name is a product noun
# that every locale of 340 and 341 carries and that the in-game ladder prints,
# so a guard refusing it would be a guard somebody turns off rather than fixes
# (#430 — a guard is worth what its refusal costs). The exception is a LINE's:
# a line that carries the product name may use the word elsewhere on it too,
# because the achievement's own description says whom the player beats. A
# line that does not carry it is refused, which is the case that matters: an
# attribution.
_HANDLE_PHRASE_DIGESTS = frozenset([
    "ebb19cba72cc945dea5699e279070c7c66564fb432113301a04ab69627d3d0a6",
])

# AN ATTRIBUTION TO SOMEBODY THE DIGESTS DO NOT KNOW. A closed list cannot
# name everybody, so the shapes attributions in these files have taken are
# refused whatever the word in them: a capitalised word before reported,
# asked, noticed and the like; after "reported by", "thanks to" and the like;
# before a possessive report, ask or question; inside "Bug N (" and "(per ".
# Such a word has to be on the list below of words that are NOT people — the
# maintainer, and the sentence openers and nouns those shapes meet in these
# files. An all-capitals word or a single letter is a term or a variable,
# never a handle here. The list is what the guard costs, and it stays short
# because the shapes are narrow.
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
_NOT_PEOPLE = frozenset([
    "Sid",
    "Aug", "GameStateWatcher", "Games", "Match", "None", "Not", "Nothing",
    "Question", "Queue", "That", "The",
])


def _git(*args):
    # utf-8 explicitly: git emits the tree's own bytes, the FAQ bodies and the
    # seeded locales are not ASCII, and Python's default on this platform is
    # cp1252 — which raises halfway through the diff and leaves the sweep with
    # nothing to read rather than with something to judge (#441).
    return subprocess.run(["git", "-C", REPO] + list(args),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


_SALTED = {}


def _salted(word):
    # Cached: the sweep hashes every word of tens of thousands of lines, and
    # the same few thousand words make up nearly all of them.
    key = word.lower()
    if key not in _SALTED:
        _SALTED[key] = hashlib.sha256(
            (_HANDLE_SALT + key).encode("utf-8")).hexdigest()
    return _SALTED[key]


def _hygiene_hits(rel, lineno, text):
    """What is wrong with one line, said WITHOUT quoting the thing that is
    wrong with it. A guard that prints the identifier it found writes it into
    every CI log and every pasted failure, which is the leak again by another
    route."""
    where = "%s:%d" % (rel, lineno)
    hits = []
    if _DRIVE_PATH.search(text):
        hits.append(where + " a drive-letter path, which resolves on one seat "
                    "only")
    if _HOME_PATH.search(text):
        hits.append(where + " a path under a home directory")
    if _SCRATCH_TOKEN in text:
        hits.append(where + " names the gitignored scratch tree, which exists "
                    "on no other checkout")
    if any(token in text for token in _SANDBOX_TOKENS):
        hits.append(where + " names a local sandbox checkout")
    words = _WORD.findall(text)
    product = {a.lower() for a, b in zip(words, words[1:])
               if _salted(a + " " + b) in _HANDLE_PHRASE_DIGESTS}
    for w in words:
        if _salted(w) in _HANDLE_DIGESTS and w.lower() not in product:
            hits.append("%s a personal handle (%d characters) — the maintainer "
                        "is 'Sid' in every artifact that leaves this machine, "
                        "and testers are not named at all" % (where, len(w)))
            break
    for shape in _ATTRIBUTION_SHAPES:
        for m in shape.finditer(text):
            who = m.group(1)
            if who in _NOT_PEOPLE or len(who) == 1 or who.isupper():
                continue
            hits.append("%s an attribution to a word (%d characters) that is "
                        "not on the list of words that are not people"
                        % (where, len(who)))
    return hits


def _swept_lines():
    """(path, line number, text) for every line of every file in the scope,
    read from the working tree."""
    out = []
    for rel in _HYGIENE_SCOPE:
        assert os.path.isfile(os.path.join(REPO, rel)), (
            "%s is in the hygiene scope and is not on disk — the record and the "
            "tree disagree, and the sweep would pass by not reading it" % rel)
        out += [(rel, i, text)
                for i, text in enumerate(_read(rel).split("\n"), 1)]
    return out


def test_no_file_this_item_touches_names_a_person_a_local_path_or_the_scratch_tree():
    """The hygiene control, over every line of every file this item touches.

    Five classes, one sweep, because a flag names a line and the defect is a
    class (#432): a drive-letter or home-directory path resolves on one
    machine, and under a home directory is a personal identifier besides; a
    scratch-tree reference points at reasoning that exists on no other
    checkout, so the file ships claiming its rationale is recorded while the
    record is local (#302); a sandbox checkout's name is the same leak spelt
    another way; and a tester's handle, or an attribution to anybody but the
    maintainer, is the one thing that has had to be force-pushed away twice.

    The POSITIVE half is below the sweep: deleting every scratch reference
    satisfies the rule exactly as well as tracking the document does, so the
    document the client lane is sent to has to be present, has to carry the
    corrections the fixture records as owed, and must not be excluded by
    name."""
    swept = _swept_lines()
    # The sweep is evidence only if it read the files. main.py alone runs to
    # tens of thousands of lines, so a short count means the scope was read
    # wrong, not that nothing in it was wrong (#304).
    assert len(swept) > 50000, (
        "the sweep read only %d lines from the %d files in its scope"
        % (len(swept), len(_HYGIENE_SCOPE)))
    problems = []
    for rel, lineno, text in swept:
        problems += _hygiene_hits(rel, lineno, text)
    assert not problems, (
        "a file this item touches carries something that may not ship:\n"
        + "\n".join(sorted(set(problems))))

    # The positive half.
    contract = os.path.join(REPO, "docs", "faq-refresh-client-contract.md")
    assert os.path.isfile(contract), (
        "docs/faq-refresh-client-contract.md is gone — the owed_to_client_lane "
        "rows in the fixture no longer have a tracked specification")
    body = _read(contract)
    for c in claims():
        for row in c.get("owed_to_client_lane", []):
            assert row["text"] in body, (
                "%s: the contract does not carry the owed text %r, so the "
                "fixture row names work no tracked document specifies"
                % (c["id"], row["text"]))
            assert row["replaces"] in body, (
                "%s: the contract does not carry the text %r this row says "
                "the client lane replaces, so the lane is told what to write "
                "but not where" % (c["id"], row["replaces"]))
    ignored =[ln.strip() for ln in _read(".gitignore").splitlines()]
    assert "docs/faq-refresh-client-contract.md" not in ignored, (
        ".gitignore excludes the client contract by name — it would be local "
        "again with every reference to it still in shipped files")


def test_the_hygiene_scope_is_every_file_this_item_touches():
    """The recorded scope, checked in both directions against the history it
    summarises.

    This item's commits are the ones after the branch point that touch this
    module or the claims fixture. Every commit of the item that changes code
    or prose does (a route-manifest re-pin, committed alone, does not, and the
    manifest is in the scope by record), and the path
    filter is what keeps the answer the same after the branch merges, when
    everything after the branch point on main also holds every other lane's
    work. A file one of those commits touched is either swept or handed back,
    so the scope cannot silently miss one; and a recorded file is one a commit
    of the item touched, so the scope cannot be padded with files it does not
    own. A clone without the branch point skips this half and says why; the
    sweep itself needs no history."""
    if _git("rev-parse", "--verify", _BRANCH_POINT + "^{commit}").returncode != 0:
        pytest.skip("the branch point %s is not in this clone, so this item's "
                    "commits cannot be listed" % _BRANCH_POINT)
    proc = _git("log", "--no-merges", "--format=%H",
                _BRANCH_POINT + "..HEAD", "--", *_ITEM_ANCHORS)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    commits = proc.stdout.split()
    # Seven commits of this item precede round 5. Fewer means the log read
    # the wrong range, and both assertions below would hold vacuously (#304).
    assert len(commits) >= 7, (
        "git log found %d commits of this item after %s; it has at least seven"
        % (len(commits), _BRANCH_POINT))
    touched = set()
    for sha in commits:
        shown = _git("show", "--format=", "--name-only", sha)
        assert shown.returncode == 0, shown.stderr or shown.stdout
        touched.update(n.strip() for n in shown.stdout.split("\n") if n.strip())
    recorded = set(_HYGIENE_SCOPE) | set(_HANDED_BACK)
    assert not set(_HYGIENE_SCOPE) & set(_HANDED_BACK), (
        "a file is recorded as both swept and handed back")
    unrecorded = sorted(touched - recorded)
    assert not unrecorded, (
        "a commit of this item touched %s, which the hygiene scope neither "
        "sweeps nor records as handed back" % unrecorded)
    unowned = sorted(recorded - touched)
    assert not unowned, (
        "the hygiene scope records %s, which no commit of this item touched"
        % unowned)


def test_the_hygiene_sweep_can_actually_fail():
    """Every detector shown rejecting and shown accepting.

    Each is a pattern this file may not contain, so none of them can be
    demonstrated by the sweep's own corpus: a detector that has never matched
    anything is indistinguishable from one whose pattern is wrong (#342/#391 —
    a mutation, and a negative control). These are synthetic lines, each
    assembled from pieces so that the line in this file is not itself what it
    demonstrates, run through the same _hygiene_hits the sweep uses.

    The handle case is built by hashing, not by spelling: the test states that
    a word whose digest is listed is rejected, without the word."""
    global _HANDLE_DIGESTS, _HANDLE_PHRASE_DIGESTS
    colon, back = ":", "\\"

    def refused(line):
        return bool(_hygiene_hits("x.py", 1, line))

    # Drive-letter paths: either separator, under a home directory or not.
    assert refused("PSQL = " + "D" + colon + "/pg/bin/psql.exe"), (
        "a drive-letter path outside any home directory was accepted")
    assert refused("copy it to " + "E" + colon + back + "builds" + back + "x.dll"), (
        "a backslash drive-letter path was accepted")
    assert not refused("see https" + colon + "//example.org/x"), (
        "a URL scheme was taken for a drive")
    assert not refused("om den inte listas här" + colon + back + "n"), (
        "a seeded locale's escaped newline was taken for a drive")
    # Home directories on the other platforms.
    assert refused("see /" + "ho" + "me/someone/notes.md"), (
        "a POSIX home-directory path was accepted")
    assert refused("see /" + "Us" + "ers/someone/notes.md"), (
        "a macOS home-directory path was accepted")
    assert not refused("GET /api/v1/users/42/stats"), (
        "an API route was taken for a home directory")
    # The scratch tree, with a path after it and bare.
    assert refused("designed in " + _SCRATCH_TOKEN + "/v1410/NOTES.md section 4"), (
        "a scratch-tree reference was accepted")
    assert refused("the reasoning is in the " + _SCRATCH_TOKEN + " notes"), (
        "a bare mention of the scratch tree was accepted")
    assert not refused("designed in docs/NOTES.md section 4"), (
        "a tracked path was rejected as a scratch reference")
    for token in _SANDBOX_TOKENS:
        assert refused("built in " + token + "item11"), (
            "a sandbox checkout's name was accepted")

    # Attribution shapes, with a probe word that is nobody's handle: the
    # shapes refuse it although no digest lists it.
    probe = "Zzprobeword"
    for line in (probe + " reported the crash",
                 "reported by " + probe,
                 "thanks to " + probe + " for the repro",
                 probe + "'s report",
                 "Bug 12 (" + probe + ", Aug 1)",
                 "(per " + probe + ")"):
        assert refused(line), "an attribution shape was accepted: %r" % line
    for line in ("Sid asked for the floor",
                 "Match found — set both to matched",
                 "the ROW's question",
                 "game N's report",
                 "thanks, " + probe):
        assert not refused(line), (
            "a line with no attribution shape and no listed handle was "
            "refused: %r" % line)
    assert not [w for w in _NOT_PEOPLE if _salted(w) in _HANDLE_DIGESTS], (
        "a listed handle is on the list of words that are not people, which "
        "would let the attribution half admit it")

    # The handle detector, with the PROBE as the handle: the blocklist is
    # extended for the length of these assertions with the digest of a word
    # invented here, so what is demonstrated is the mechanism — a word whose
    # salted digest is listed is refused where no shape applies, an ordinary
    # one is not — and no handle enters this file to demonstrate it.
    assert _HANDLE_DIGESTS, "the handle blocklist is empty"
    original, original_phrases = _HANDLE_DIGESTS, _HANDLE_PHRASE_DIGESTS
    try:
        _HANDLE_DIGESTS = frozenset(original | {_salted(probe)})
        assert refused("thanks, %s" % probe), (
            "a word whose salted digest is on the blocklist was accepted")
        assert not refused("thanks, a tester"), (
            "a neutral word was rejected as a handle")
        # The product-name exception is exactly as wide as a line that
        # carries the phrase it lists.
        _HANDLE_PHRASE_DIGESTS = frozenset(
            original_phrases | {_salted(probe + " widget")})
        assert not refused("the %s Widget pays 500g" % probe), (
            "an allowed two-word product name was refused")
        assert not refused("the %s Widget: beat %s in a ranked series"
                           % (probe, probe)), (
            "the product's own description was refused on its own line")
        assert refused("the %s gadget pays 500g" % probe), (
            "the exception admitted a pairing it does not list")
        assert refused("thanks, %s" % probe), (
            "the exception admitted the bare word on a line without the "
            "product name")
    finally:
        _HANDLE_DIGESTS = original
        _HANDLE_PHRASE_DIGESTS = original_phrases
    assert _HANDLE_DIGESTS is original, "the blocklist was not restored"
    assert _HANDLE_PHRASE_DIGESTS is original_phrases, (
        "the product-name exception was not restored")


# ── A test a file names is a test that exists ──────────────────────────────
#
# The files this item touches cite tests by name: as the pin for a sentence,
# or as the guard a comment sends the next reader to. A rename leaves such a
# citation pointing at nothing, and it still reads exactly like a working pin
# — round five renamed this file's hygiene sweep, and 338's header went on
# naming it by its old name. So every test_* identifier on a swept line has to
# name a test function, or a test module, under backend/tests. A name wrapped
# across two comment lines (one ending in an underscore, the next carrying the
# rest) is joined before it is looked up.
_CITED_TEST = re.compile(r"(?<![A-Za-z0-9_])(test_[A-Za-z0-9_]+)")
_CITED_TAIL = re.compile(r"^[\s#*/-]*([A-Za-z0-9_]+)")


def _tests_defined():
    names = set()
    for root, _dirs, files in os.walk(os.path.join(REPO, "backend", "tests")):
        for fn in files:
            if fn.endswith(".py"):
                names.add(fn[:-3])
                names.update(re.findall(
                    r"^[ \t]*(?:async[ \t]+)?def[ \t]+(test_[A-Za-z0-9_]+)",
                    _read(os.path.join(root, fn)), re.M))
    return names


def _unresolved_citations(lines, defined):
    """One entry per cited test name that names nothing. `lines` is
    (path, line number, text) in file order, as _swept_lines() returns it."""
    out = []
    for i, (rel, lineno, text) in enumerate(lines):
        for m in _CITED_TEST.finditer(text):
            name = m.group(1)
            if (name.endswith("_") and not text[m.end():].strip()
                    and i + 1 < len(lines) and lines[i + 1][0] == rel):
                tail = _CITED_TAIL.match(lines[i + 1][2])
                if tail:
                    name += tail.group(1)
            if name not in defined:
                out.append("%s:%d names %s" % (rel, lineno, name))
    return out


def test_every_test_a_touched_file_cites_exists():
    """A citation of a test is a claim that the test is there to run.

    Checked over the same lines the hygiene sweep reads, against every test
    function and test module under backend/tests, and shown to be able to
    fail before it is believed (#342): a citation of a test that does not
    exist is reported, and a wrapped name is joined rather than reported or
    accepted by its first half."""
    defined = _tests_defined()
    assert len(defined) > 1000, (
        "only %d test names were found under backend/tests — the lookup is "
        "reading the wrong tree, and every citation would be judged against "
        "almost nothing" % len(defined))
    swept = _swept_lines()
    cited = sum(len(_CITED_TEST.findall(text)) for _rel, _n, text in swept)
    assert cited > 100, (
        "only %d test citations were found in the touched files — the "
        "pattern is not matching what the files spell" % cited)
    bad = _unresolved_citations(swept, defined)
    assert not bad, (
        "a touched file cites a test that does not exist, so the sentence it "
        "supports reads as pinned and is not:\n" + "\n".join(bad))

    head = "test" + "_every_test_a_touched_file_"
    gone = "test" + "_every_test_a_touched_file_cites_nothing"
    assert _unresolved_citations([("probe", 1, "pinned by %s." % gone)], defined), (
        "a citation of a test that does not exist was accepted")
    assert not _unresolved_citations(
        [("probe", 1, "pinned by " + head), ("probe", 2, "# cites_exists.")],
        defined), "a name wrapped across two comment lines was not joined"
    assert _unresolved_citations(
        [("probe", 1, "pinned by " + head), ("probe", 2, "-- cites_nothing.")],
        defined), "a wrapped name was accepted by its first half alone"


def test_no_claim_unknown():
    """'unknown' is not a verdict this fixture may carry.

    A row nobody resolved is worse than no row: it reads as coverage. The
    brief's one genuinely unresolved claim — 'returns you after ~60s' in
    docs/FAQ.md against 'warns at 90 seconds ... returns after 6 minutes' in
    the Info library — turned out to be two different rooms rather than a
    contradiction, and is now two anchored claims."""
    problems = []
    for c in claims():
        if c.get("verdict") != "verified":
            problems.append("%s: verdict is %r" % (c["id"], c.get("verdict")))
        if not c.get("surfaces") and not c.get("owed_to_client_lane"):
            problems.append("%s: no surface states this claim" % c["id"])
        if not c.get("anchor", {}).get("pattern"):
            problems.append("%s: no code anchor" % c["id"])
    assert not problems, "\n".join(problems)
    assert len(claims()) >= 28, "the fixture lost rows: %d left" % len(claims())
    assert len(ids()) == len(set(ids())), "duplicate claim id"


# ── 2b. The achievement ladder has no tier the FAQ does not name ─────────────

def _achievement_overrides():
    """ACHIEVEMENT_GOLD_OVERRIDES as {key: gold}, read from main.py.

    Parsed rather than imported: importing main.py needs the whole api
    dependency tree, and the point is to read the literal the deployed file
    carries."""
    body = _read("backend/api/main.py")
    start = body.index("ACHIEVEMENT_GOLD_OVERRIDES = {")
    end = body.index("\n}", start)
    block = body[start:end]
    return {k: int(v) for k, v in re.findall(r'"([a-z0-9_]+)":\s*(\d+)', block)}


def test_achievement_tiers_are_exhaustive():
    """The FAQ names the ladder, so the ladder may not grow a rung in silence.

    Anchoring one key per tier catches a tier that MOVES. It does not catch a
    tier that is ADDED — price one new achievement at 750 and every anchored
    claim stays green while three surfaces tell players a number that is no
    longer the whole truth. So the set of distinct payouts is asserted against
    the set the fixture pins, which is the occurrence-count discipline applied
    to the ladder instead of to a line (#432)."""
    overrides = _achievement_overrides()
    assert len(overrides) >= 25, (
        "only %d overrides parsed out of main.py — the block moved or the "
        "shape changed, and this test would be reading nothing" % len(overrides))
    default = int(re.search(r"^ACHIEVEMENT_GOLD = (\d+)$",
                            _read("backend/api/main.py"), re.M).group(1))
    live = set(overrides.values()) | {default}
    pinned = {int(c["value"]) for c in claims()
              if c["id"].startswith("achievement_gold_")}
    assert live == pinned, (
        "the achievement ladder pays %s; the FAQ fixture pins %s. Every tier a "
        "player can be paid has to be a claim, or the surfaces describe a "
        "ladder that no longer exists." % (sorted(live), sorted(pinned)))


_INFO_LIBRARY = os.path.join(REPO, "plugin", "InfoLibrary.cs")
_LADDER_LINE = re.compile(r"- <color=#7FD4FF>(\d+)g</color> - (.+)")


def _ladder_tiers(body):
    """{gold: {label, ...}} from the article's own tier lines."""
    out = {}
    for gold, line in _LADDER_LINE.findall(body):
        items = [re.sub(r"\s*\([^)]*\)\s*$", "", i.strip().rstrip("."))
                 for i in line.split(",")]
        out[int(gold)] = {i for i in items if i}
    return out


def test_every_achievement_is_on_the_tier_line_that_pays_it():
    """Membership, not just the set of prices.

    test_achievement_tiers_are_exhaustive catches a tier that is ADDED or
    REMOVED, because it compares the set of distinct payouts. It cannot catch
    a key MOVING between two tiers that both still exist: re-price Bodycount
    from 500 to 300 and the set {100,300,500,1000} is unchanged, every
    anchored claim still finds its literal, and three surfaces go on listing
    it under 500. The article names its tiers by MEMBER, so the members are
    what this holds to the code: for every non-default payout, the set of
    labels ACHIEVEMENT_DEFS ships for the keys priced at it must equal the set
    of labels the tier line carries.

    THE BINDING SURFACE HERE IS 340, not the in-game article. plugin/
    InfoLibrary.cs is the client lane's file and this branch restored it, so
    the article in this tree is still the PREDECESSOR — it lists the ladder
    without the four tournament achievements. It is checked anyway, and
    against the same correction the contract hands the client lane
    (REKEY_EDITS["economy article"], docs/faq-refresh-client-contract.md
    section 1b): every tier line, as declared, must list exactly 340's members.
    So the two lanes are still held to one list — this one just says which
    lane owes which half instead of pretending both have landed.

    THE LADDER IS APPLIED WHOLE OR NOT AT ALL, and that is asserted before any
    comparison. An earlier version applied the correction table to the article
    in memory and then compared, which is blind to a PARTIAL application:
    `replace` is a no-op for a step the client lane has already made, so a
    tree carrying only the 500g append was repaired before it was judged and
    read as green, with the 300g line left short in the article, in its
    translations and in the game. So every step is first classified against the
    article as it stands — applied, or still owed — and a tree holding some of
    each is the failure. After that NOTHING is applied to the article: an
    applied ladder is judged on the article's own lines, an owed one on the
    successor lines the fixture records for it, each tier against 340's
    (#342/#391 — a test may not supply the value the thing under test is
    missing and then compare against what it supplied)."""
    overrides = _achievement_overrides()
    names = _achievement_names()
    default = int(re.search(r"^ACHIEVEMENT_GOLD = (\d+)$",
                            _read("backend/api/main.py"), re.M).group(1))
    missing = [k for k in overrides if k not in names]
    assert not missing, (
        "ACHIEVEMENT_GOLD_OVERRIDES prices %s, which ACHIEVEMENT_DEFS does not "
        "name — one of the two parsers is reading the wrong block" % missing)

    paid = {}
    for key, gold in overrides.items():
        if gold == default:
            continue          # priced at the default: the article says "unless
        paid.setdefault(gold, set()).add(names[key])   # listed here", so it is not

    article_src = _read(_INFO_LIBRARY)
    assert _ladder_tiers(article_src), (
        "InfoLibrary.cs no longer carries the gold-tier ladder")

    # Every step of the ladder correction, classified against the article as
    # it stands — before anything is applied to it in memory.
    ladder = ECONOMY_LADDER
    assert ladder and all(pair in REKEY_EDITS["economy article"] for pair in ladder), (
        "the contract's economy-article ladder table is empty or not in the correction table")
    owed = [(b, a) for b, a in ladder if b in article_src and a not in article_src]
    applied = [(b, a) for b, a in ladder if a in article_src and b not in article_src]
    assert len(owed) + len(applied) == len(ladder), (
        "%d of the %d ladder steps match the article neither as owed nor as "
        "applied — the contract and the article describe different lines"
        % (len(ladder) - len(owed) - len(applied), len(ladder)))
    assert not (owed and applied), (
        "the gold ladder is %d step(s) applied and %d still owed. A ladder "
        "half-corrected is the state this test exists to catch: the finished "
        "steps read as done, a check that repaired the rest in memory would "
        "read them as done too, and the article, its translations and the "
        "game go on listing a tier line that is short" % (len(applied), len(owed)))

    # Then each tier line is compared with 340's as it is DECLARED, and nothing
    # is applied to the article to get there. Once the client lane's half has
    # landed, the article itself is what is judged. While it is still owed, a
    # tier the correction does not touch is judged on the article, and a tier
    # it does touch on the successor line the fixture's owed row records. That
    # row is tied to this table and to the article's predecessor line by
    # test_a_client_lane_surface_is_recorded_as_owed_not_as_present, and to
    # the tracked contract by the hygiene test's positive half; the article's
    # own copy of the tier is never edited here to look like the successor.
    article = _ladder_tiers(article_src)
    migration = _ladder_tiers(_read(MIG_340))
    assert set(article) == set(migration), (
        "the article prices tiers %s and 340 prices %s — a tier was added or "
        "removed on one side only" % (sorted(article), sorted(migration)))
    successors = {}
    if owed:
        successors = _ladder_tiers("\n".join(
            row["text"] for c in claims()
            for row in c.get("owed_to_client_lane", [])
            if row["file"] == "plugin/InfoLibrary.cs"
            and _LADDER_LINE.search(row["text"])))
        assert len(successors) == len(owed), (
            "%d ladder steps are owed but the fixture records successor lines "
            "for %d tiers (%s)" % (len(owed), len(successors), sorted(successors)))
    for gold in sorted(migration):
        declared = successors.get(gold, article[gold])
        assert declared == migration[gold], (
            "the %dg tier: %s lists %s, 340's re-keyed source lists %s — the "
            "two lanes would ship two different ladders"
            % (gold, "the owed successor line" if gold in successors
               else "the article", sorted(declared), sorted(migration[gold])))
    assert paid == migration, (
        "the code pays %s; the ladder lists %s. Every achievement has to sit "
        "on the line that pays it, or a re-priced key silently keeps its old "
        "tier in three surfaces."
        % ({g: sorted(v) for g, v in sorted(paid.items())},
           {g: sorted(v) for g, v in sorted(migration.items())}))


def _prune_stale_series_body():
    src = _read("backend/api/main.py")
    start = src.index("async def _prune_stale_series")
    return src[start:src.index("\nasync def ", start + 1)]


def test_refund_surfaces_state_the_tournament_exemption():
    """Both timed refund modes exclude tournament series, and every surface
    that states the two clocks has to say so.

    The responder's betting answer told players their stakes come back after
    30 or 60 minutes with no exception, which for a tournament series is
    simply false: mode 1 and mode 2 both select `rs.is_tournament = FALSE`,
    and a tournament stake is settled by mode 3 off the bracket's own terminal
    row instead. The predicate is read out of the deployed function here, so
    dropping it from either mode fails this test rather than making three
    surfaces quietly correct again."""
    # Every TIMED statement in the function, not a count of the literal: a
    # count passes a new unguarded arm, and the defect is a class, not a line
    # (#432). "Timed" is the interval arithmetic itself — the two mode
    # selections use (:m || ' minutes')::interval and the two under-lock
    # re-checks use make_interval(mins => ...), and all four are places a
    # tournament series must not be selected by a clock.
    fn = None
    for node in ast.walk(_parsed(API_MAIN)[1]):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_prune_stale_series"):
            fn = node
    assert fn is not None, "main.py no longer defines _prune_stale_series"
    timed = [n.value for n in ast.walk(fn)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and "FROM ranked_series" in n.value
             and ("minutes')::interval" in n.value
                  or "make_interval(mins =>" in n.value)]
    assert len(timed) >= 4, (
        "found %d timed ranked_series statements in _prune_stale_series; the "
        "two mode selections and their two under-lock re-checks are all of "
        "them, so this is reading the wrong block" % len(timed))
    unguarded = [s for s in timed if "rs.is_tournament = FALSE" not in s]
    assert not unguarded, (
        "a timed refund statement selects tournament series, which every "
        "surface now tells players it does not:\n%s"
        % "\n".join(s[:120] for s in unguarded))
    body = _prune_stale_series_body()
    assert "rs.is_tournament = TRUE" in body, (
        "mode 3 — the bracket-settled refund the surfaces point tournament "
        "players at — is no longer there")

    surfaces = {
        "docs/FAQ.md": "Tournament series sit outside both clocks",
        "backend/sql/338_faq_channel_post_revisions.sql":
            "Tournament series sit outside both clocks",
        # The responder's answers wrap mid-sentence, so the phrase that exists
        # in the SOURCE stops at the line break — matching on the rendered
        # sentence would be matching on something no file contains.
        "backend/discord_bot.py": "sit outside both ",
    }
    for path, sentence in surfaces.items():
        assert sentence in _read(path), (
            "%s states the 30/60-minute refund windows without the tournament "
            "exemption the code enforces" % path)
    # Both responder answers that quote the windows, not just the first.
    assert _read(BOT).count("sit outside both ") == 2, (
        "one of the two responder answers quoting the refund windows lost the "
        "exemption")


def test_async_cadence_surfaces_state_both_gates():
    """The FAQ said the two-day wait applies, full stop.

    It applies to a COMPLETED bracket carrying an ended_at; a cancelled one,
    or a completed one whose ended_at was never written, is held only by the
    24-hour net from the previous creation. Stating the conditional rule as an
    unconditional one is how "every ~6 weeks" survived for months, so BOTH
    numbers are read out of the gate itself — the 24-hour net from its own
    timedelta, and the post-completion wait from the constant the gate applies
    — and both must appear on every surface that describes the cadence,
    including the bot's own tournaments answer. Changing either constant
    therefore reds here rather than leaving three surfaces quietly wrong."""
    src = _read("backend/api/tournaments.py")
    start = src.index("async def _ensure_next_tournament")
    body = src[start:src.index("\nasync def ", start + 1)]
    net = re.search(r"\(now - last_async\.created_at\) < timedelta\(hours=(\d+)\)",
                    body)
    assert net, "the 24-hour safety net is no longer a timedelta on created_at"
    assert 'last_async.status == "completed" and last_async.ended_at' in body, (
        "the post-completion wait is no longer conditional, so the surfaces "
        "below now describe a gate that is not there")
    # The two-day value, read where it is APPLIED and then where it is SET.
    # Round three pinned only the 24-hour clause here, so changing the bot's
    # "2 days" to three left every assertion in this file unchanged.
    assert re.search(r"\(now - last_async\.ended_at\) < timedelta\("
                     r"days=ASYNC_POST_COMPLETION_DAYS\)", body), (
        "the post-completion wait is no longer ASYNC_POST_COMPLETION_DAYS "
        "applied to ended_at — the surfaces below quote a constant the gate "
        "does not read")
    days = int(re.search(r"^ASYNC_POST_COMPLETION_DAYS = (\d+)", src, re.M).group(1))

    for path in ("docs/FAQ.md",
                 "backend/sql/338_faq_channel_post_revisions.sql",
                 "backend/discord_bot.py"):
        text_ = _read(path)
        wait = "%d days after the previous one finishes" % days
        assert wait in text_, (
            "%s does not state the post-completion wait the gate enforces "
            "(%d days)" % (path, days))
        phrase = "only **%s hours** after it was created" % net.group(1)
        assert phrase in text_, (
            "%s does not state the gate that holds a cancelled bracket" % path)
        # "cancelled" has to be in the SAME sentence, not merely somewhere in
        # the file: discord_bot.py is 12k lines and says "cancelled" in a
        # dozen unrelated answers, so a file-wide substring would pass on a
        # surface that never named which brackets skip the two-day wait.
        near = text_[max(0, text_.index(phrase) - 400):text_.index(phrase)]
        assert "cancelled" in near, (
            "%s states the 24-hour gate without saying WHICH brackets the "
            "two-day wait skips" % path)


def test_async_cadence_docstring_matches_its_own_gate():
    """The FAQ's "every ~6 weeks" came from a docstring, not from the code.

    That docstring now describes the post-completion rule, which makes it a
    claim about the function below it — and the claim is CONDITIONAL: the
    two-day wait applies to a completed bracket with an ended_at, while
    anything else is held only by the 24-hour net. A docstring that states the
    two-day rule flatly is the same defect one release later, so both the gate
    and the prose are asserted, and either drifting fails this."""
    src = _read("backend/api/tournaments.py")
    start = src.index("async def _ensure_next_tournament")
    body = src[start:src.index("\nasync def ", start + 1)]
    doc = body[body.index('"""') + 3:body.index('"""', body.index('"""') + 3)]

    assert 'last_async.status == "completed" and last_async.ended_at' in body, (
        "the post-completion wait is no longer conditional on a completed "
        "bracket with an ended_at; the docstring below describes a gate that "
        "is not there")
    assert "timedelta(hours=24)" in body, (
        "the 24-hour safety net the docstring names is gone")
    assert "ASYNC_POST_COMPLETION_DAYS" in body

    low = doc.lower()
    assert "24" in low, "the docstring omits the gate that always applies"
    assert "cancelled" in low, (
        "the docstring does not say which rows bypass the two-day wait, which "
        "is how it reads as one rule covering every row")
    assert "ASYNC_CADENCE_DAYS is legacy" in doc, (
        "the docstring no longer says the knob it used to name drives nothing")


# ── 3. The Discord responder's artist answer describes the shipped uploader ──

def test_artist_entry_current():
    """The artist answer contradicted shipped code in three ways at once: it
    said the uploader submits one static PNG, that it does not bundle
    animation frames, and it routed animated work to a side channel. GIF and
    __fN frame submission have been in NativeUI.ValidateAndNameCosmetic since
    Aug 7 and the server has accepted frame_count 2..COSMETIC_MAX_FRAMES ever
    since."""
    bot = _read(BOT)
    start = bot.index('"key": "artist"')
    answer = bot[start:bot.index('"key": "bug_report"', start)]

    retired = [
        "does **not** bundle animation frames",
        "submits **one static PNG**",
        "send the remaining frames plus the",
    ]
    for phrase in retired:
        assert phrase not in answer, (
            "the artist answer still carries %r, which the uploader refuted" % phrase)

    for required in ["GIF", "myitem__f2.png", "16 frames", "30% royalty"]:
        assert required in answer, "the artist answer no longer mentions %r" % required

    # The frame convention is quoted from the picker the artist actually reads,
    # so a rename there fails this rather than leaving two conventions live.
    picker = _read(NATIVE_UI)
    assert "wizard.png + wizard__f2.png + wizard__f3.png" in picker, (
        "NativeUI's artist picker no longer states the __fN convention this "
        "answer quotes")


def test_the_uploader_error_texts_quote_the_limits_they_enforce():
    """A refusal message is a claim about the check beside it.

    The client refused a PNG over 1,200,000 bytes and told the artist "1 MB
    max"; the endpoint refused over COSMETIC_MAX_B64 base64 characters and
    said "1 MB max" too. Both numbers were wrong in the same direction — an
    artist shrinking a 1.1 MB file that would have been accepted — and neither
    was readable from the check it describes. Each message is now held to its
    own constant, so moving a limit without its message fails here.

    The FAQ surfaces are pinned separately by the fixture; this is the pair
    the artist meets in the product, which the FAQ can be right about while
    the error text is wrong.

    SCOPE, and why one half of the pair is missing. Only the SERVER's refusal
    is pinned. plugin/NativeUI.cs still refuses a PNG over 1,200,000 bytes
    while telling the artist "1 MB max", this branch does not change that file,
    and nothing here goes red for it. That is a residual, not a fix: the file
    belongs to the client lane and the required change is written down for it
    in docs/faq-refresh-client-contract.md. The two alternatives were both
    worse — asserting the text this tree carries would PIN the defect, and
    asserting only that the message sits near its check would be a check that
    cannot fail on the thing it is for (#342). The GIF pair below is a
    different literal, is already consistent with its own check, and is pinned
    so it stays that way."""
    native = _read(NATIVE_UI)
    gif = re.search(r"bytes\.Length > ([\d_]+)\)\s*\n\s*\{ ShowArtistResult"
                    r"[^\n]*?GIF too large - about (\d+) MB max", native)
    assert gif, "NativeUI's GIF refusal no longer sits with its size check"
    assert abs(int(gif.group(2)) * 1_000_000
               - int(gif.group(1).replace("_", ""))) < 300_000, gif.groups()

    main = _read("backend/api/main.py")
    b64 = int(re.search(r"^COSMETIC_MAX_B64 = ([\d_]+)", main, re.M)
              .group(1).replace("_", ""))
    assert "%s base64 characters max" % "{:,}".format(b64) in main, (
        "the upload endpoint's refusal does not quote COSMETIC_MAX_B64 (%d)" % b64)

    # The missing half is a RESIDUAL, and the comment beside the server check
    # is where the next reader meets it. Round three's comment there said the
    # client twin had been swept with it, which was false the moment the
    # client hunk was withdrawn — so the sentence is pinned rather than left
    # to be quietly tidied back (#302: a line that cannot be traced to code is
    # a finding). This asserts what main.py SAYS about the other file, never
    # what NativeUI.cs contains: asserting that would pin the defect.
    assert "THE CLIENT TWIN IS NOT SWEPT WITH IT" in _function_source(
        API_MAIN, "artist_submit_cosmetic"), (
        "main.py's PNG refusal no longer records that the client's own "
        "message is still wrong about its own check — the residual is real "
        "whether or not it is written down")


_THIS_FILE = os.path.abspath(__file__)


def test_the_scoped_residuals_are_stated_where_the_next_reader_meets_them():
    """A residual this branch chose to carry has to survive a tidy-up.

    The uploader residual is a sentence rather than code, and a sentence with
    nothing asserting it is deleted by the next person who reads it as waffle.
    That is exactly the state it was in: its whole SCOPE paragraph could be
    removed and every assertion in the test carrying it stayed green, so the
    branch would have shipped saying the client half was swept when it is not
    (#302 — a claim that cannot be traced to the tree is a finding).

    So the paragraph is pinned from OUTSIDE the test that carries it: this
    reds when only the SCOPE paragraph goes, while the uploader test goes on
    asserting the limits themselves."""
    scope = re.sub(r"\s+", " ", _docstring(
        _THIS_FILE, "test_the_uploader_error_texts_quote_the_limits_they_enforce"))
    for sentence in (
            "SCOPE, and why one half of the pair is missing.",
            "Only the SERVER's refusal is pinned.",
            "this branch does not change that file, and nothing here goes red "
            "for it.",
            "the file belongs to the client lane and the required change is "
            "written down for it in docs/faq-refresh-client-contract.md"):
        assert sentence in scope, (
            "the uploader test no longer states the scope of what it pins. "
            "The half it does NOT pin — the client's own refusal message, "
            "still wrong about its own check — is a residual whether or not "
            "anybody writes it down, and that paragraph is where the next "
            "reader meets it. Missing: %r" % sentence[:56])


def _hooks_dir():
    """The hook directory this checkout actually uses.

    A linked worktree's .git is a file pointing at that worktree's gitdir, and
    hooks live in the COMMON dir rather than there — so the path is asked of
    git instead of constructed, and a checkout with no hooks is reported as
    that rather than passing quietly."""
    proc = _git("rev-parse", "--git-common-dir")
    if proc.returncode != 0:
        return None
    common = (proc.stdout or "").strip()
    if not common:
        return None
    if not os.path.isabs(common):
        common = os.path.join(REPO, common)
    hooks = os.path.join(common, "hooks")
    return hooks if os.path.isdir(hooks) else None


def test_the_privacy_oracle_is_the_pre_push_hook():
    """WHICH hook is authoritative, asked of the hooks rather than remembered.

    The comment above _MENTION used to call the staged pre-commit hook the
    oracle for the identifier class. It is not, and its own first line says
    so: it is a fast local catch. The authoritative gate is pre-push, because
    it is the only one that sees a RANGE — a rebase, a cherry-pick, an amended
    merge or a squash produces commits with no staged-hook run at all, and a
    tip that is clean can still carry an identifier in a blob the push makes
    reachable.

    Hooks are not tracked content, so a clone that has not installed them
    skips and says so. What is not allowed is this file naming one hook while
    both hooks sit there declaring the other.

    Both markers are assembled from fragments here. A test that searched for a
    literal it also contains would find its own source and pass whatever the
    comment said (#342)."""
    hooks = _hooks_dir()
    if hooks is None:
        pytest.skip("no hooks directory in this checkout, so which hook is "
                    "authoritative cannot be read from it")
    pre_push = os.path.join(hooks, "pre-push")
    pre_commit = os.path.join(hooks, "pre-commit")
    if not os.path.isfile(pre_push) or not os.path.isfile(pre_commit):
        pytest.skip("the privacy hooks are not installed in this checkout")

    push_body = _read(pre_push)
    commit_body = _read(pre_commit)

    assert "authoritative" in push_body.lower(), (
        "the pre-push hook no longer declares itself the authoritative gate, "
        "which is what this file's comment says it is")
    assert "outgoing" in push_body, (
        "the pre-push hook no longer runs the guard over the outgoing range — "
        "the range is the only reason it is the authoritative one")
    assert "NOT the authoritative" in commit_body, (
        "the pre-commit hook no longer says it is the fast local catch. If it "
        "has become the gate, this test and the comment above _MENTION are "
        "both now wrong about which hook to trust")
    assert "staged" in commit_body, (
        "the pre-commit hook no longer scans the staged set")

    src = _read(_THIS_FILE)
    wanted = "THE IDENTIFIER CLASS IS THE PRE-" + "PUSH GUARD'S JOB"
    wrong = "THE IDENTIFIER CLASS IS THE PRE-" + "COMMIT GUARD'S JOB"
    assert src.count(wanted) == 1, (
        "the comment above _MENTION names the authoritative hook %d times, "
        "expected once" % src.count(wanted))
    assert wrong not in src, (
        "the comment above _MENTION is back to naming the staged hook as the "
        "oracle for the identifier class; a rebased or cherry-picked commit "
        "is created without that hook running at all")


# ── 4. docs/FAQ.md and the migration that posts it cannot drift ──────────────

_SECTION = re.compile(r"^## Message (\d+)[^\n]*$", re.M)


def _faq_sections():
    parts = _SECTION.split(_read(FAQ_MD))
    return [(int(parts[i]), parts[i + 1].strip()) for i in range(1, len(parts), 2)]


def test_faq_md_matches_migration_338():
    """Migration 338 carries docs/FAQ.md's six sections as the text the bot
    edits into #scr-faq. Before 338 the only way to correct a posted message
    was to append a new one under the wrong text (134's Part C), and the doc
    and the channel had already diverged. Nothing enforces the copy, so this
    does."""
    sql = _read(MIGRATION)
    sections = _faq_sections()
    assert [n for n, _ in sections] == [1, 2, 3, 4, 5, 6], (
        "docs/FAQ.md no longer has six '## Message N' sections: %s"
        % [n for n, _ in sections])
    for n, body in sections:
        assert len(body) <= 2000, (
            "message %d is %d chars; Discord truncates at 2000 and the bot "
            "sends content[:2000]" % (n, len(body)))
        quoted = "$faq%d$%s$faq%d$" % (n, body, n)
        assert quoted in sql, (
            "migration 338 does not carry docs/FAQ.md's message %d verbatim" % n)


SEED_110 = os.path.join(REPO, "backend", "sql", "110_faq_channel_post.sql")
# WHAT THIS PATTERN ACTUALLY MATCHES, stated exactly, because the next reader
# will otherwise assume it is the privacy guard and it is not.
#
# It matches two things and only two: an @handle, and one of five routing verbs
# (DM / ping / contact / reach out / message me-us-him-her-them). A sentence
# that routes a reader to a person WITHOUT either — "talk to <name> in
# #bug-reports", or any bare identifier at all — is invisible to it. So is any
# name that appears as prose rather than as a destination.
#
# THE IDENTIFIER CLASS IS THE PRE-PUSH GUARD'S JOB, not this test's. The
# pre-push hook is the oracle for "a personal identifier reached a repo
# artifact": it scans every commit in the range being pushed, together with
# every blob those commits make reachable, so it still sees the histories a
# creation-time hook cannot — a rebase or cherry-pick sequencer commit, a
# fast-forward, an amended merge, a tip that is clean because the identifier
# was added and removed again on the way. The pre-commit hook runs the same
# body over the STAGED files only and says so in its own first line: a fast
# local catch, explicitly not the authoritative gate. An earlier version of
# this comment named that one, which is the narrower of the two and the one a
# rebase walks around. test_the_privacy_oracle_is_the_pre_push_hook holds the
# two to what they declare.
#
# What this test adds is narrower and different again: 338 REWRITES all six
# bodies, so every sentence is re-stated whether or not it changed, and "did
# this file author a new way to reach a person, or state an existing one
# twice" cannot be answered by reading the diff. This answers that
# mechanically, over the multiset, against 110's own bodies.
#
# A guard is worth what its refusal costs (#430), and the cost of this one
# refusing wrongly is a false failure on a legitimate rewording — so it judges
# only what it can recognise, and says so here instead of implying more.
_MENTION = re.compile(
    r"@[A-Za-z0-9_]+"
    r"|\bDM(?:s|ed|ing)?\b"
    r"|\bping(?:s|ed|ing)?\b"
    r"|\bcontact(?:s|ed|ing)?\b"
    r"|\breach out\b"
    r"|\bmessage (?:me|us|him|her|them)\b",
    re.I)


def _faq_bodies():
    """The six dollar-quoted message bodies migration 338 writes."""
    return re.findall(r"\$faq(\d)\$(.*?)\$faq\1\$", _read(MIGRATION), re.S)


def _seed_110_bodies():
    """110's own message bodies — it quotes all six with the same $faq$ tag."""
    return re.findall(r"\$faq\$(.*?)\$faq\$", _read(SEED_110), re.S)


def _contact_lines(bodies):
    from collections import Counter
    return Counter(ln.strip() for body in bodies for ln in body.split("\n")
                   if _MENTION.search(ln))


def test_no_new_contact_line_is_introduced():
    """338 REPLACES the six rows 110 seeded; it may not author a new way to
    reach a person, and it may not state an existing one TWICE.

    The bodies are a full rewrite of each row's content, so every sentence in
    them is re-stated by this file whether or not it changed — which makes
    "did this add a contact route" unanswerable by reading the diff alone.
    Answer it mechanically instead, and over the MULTISET: round two compared
    each line against the whole seed file as a substring, so a second copy of
    the inherited sentence — in another message, where it would read to a
    player as a second routing instruction — passed exactly as the first one
    did. Every contact line 338 states must be one 110 states, AND no more
    often than 110 states it."""
    bodies = _faq_bodies()
    assert [n for n, _ in bodies] == ["1", "2", "3", "4", "5", "6"], (
        "338 no longer carries six dollar-quoted bodies: %s"
        % [n for n, _ in bodies])
    seed_bodies = _seed_110_bodies()
    assert len(seed_bodies) == 6, (
        "110's six bodies no longer extract (%d found) — the comparison would "
        "have nothing to hold 338 against" % len(seed_bodies))

    new = _contact_lines([b for _, b in bodies])
    old = _contact_lines(seed_bodies)
    # A guard that finds nothing to check certifies nothing (#342): the sheet
    # does contain contact wording, so an empty result means the extraction
    # broke, not that the file is clean.
    assert new, ("no contact line found in 338's bodies at all — the body "
                 "extraction or the mention pattern is broken")
    assert old, "no contact line found in 110's bodies — same breakage"
    problems = []
    for line, n in new.items():
        if line not in old:
            problems.append("NEW routing sentence: %s" % line)
        elif n > old[line]:
            problems.append(
                "stated %d times, 110 states it %d: %s" % (n, old[line], line))
    assert not problems, (
        "338 states contact wording 110_faq_channel_post.sql does not:\n"
        + "\n".join(problems))


def test_338_revision_columns():
    """Static half of the migration check: the shape the bot depends on.

    Executing it is test_338_applies_twice below; this half still fails loudly
    on a box with no Postgres, so a dropped column cannot ride in behind a
    skip."""
    sql = _read(MIGRATION)
    cols = ("message_id", "revision", "posted_revision", "adopt_fingerprint",
            "claimed_at", "claimed_token", "handed_revision",
            "handed_fingerprint", "handed_revisionless")
    for col in cols:
        assert re.search(
            r"ADD COLUMN IF NOT EXISTS %s\b" % col, sql), (
            "338 no longer adds %s" % col)
    assert "IF cols <> %d THEN" % len(cols) in sql, (
        "338's post-check no longer counts all %d columns it adds, so a "
        "dropped ALTER would commit silently" % len(cols))
    assert "CREATE INDEX IF NOT EXISTS idx_pending_channel_posts_unrendered" in sql
    assert "WHERE posted_revision IS DISTINCT FROM revision" in sql, (
        "338's index is no longer the partial one the bot's poll relies on")
    assert sql.count("BEGIN;") == 1 and sql.rstrip().endswith("COMMIT;"), (
        "psql -f autocommits statement by statement; the file needs its own "
        "transaction (#340)")


# ── 5. ...and it applies, twice, against a real server ───────────────────────

DSN = os.environ.get("FAQ_TEST_PG_DSN")


def _resolve_psql():
    """The client these tests drive, FOUND rather than assumed.

    This used to fall back to one seat's unpacked install. On any other
    checkout — a fresh clone, another seat, a CI runner — setting only
    FAQ_TEST_PG_DSN therefore selected a path that is not there, and every
    Postgres test below died with FileNotFoundError instead of saying what was
    missing. A guard whose failure mode is an error about a path nobody
    configured tells the next reader nothing (#438: acceptance is a positive
    signal, and so is a refusal that names its own cause).

    So the environment wins, then whatever is on PATH, and nothing else: no
    path in this file names a seat (the hygiene sweep refuses one), and
    test_the_psql_client_is_found_not_assumed holds the order. A FAQ_TEST_PSQL
    that names nothing runnable counts as nothing found. Nothing found means
    the Postgres tests skip with a reason naming both ways to supply one,
    rather than erroring."""
    named = os.environ.get("FAQ_TEST_PSQL")
    if named:
        return named if (os.path.isfile(named) or shutil.which(named)) else None
    return shutil.which("psql")


PSQL = _resolve_psql()

# These tests DROP and recreate the tables they exercise. A DSN is a string
# somebody types, and the cost of typing the wrong one here is a production
# i18n corpus, so the database NAME has to say it is a scratch one. The guard
# fails closed: an unrecognised DSN skips rather than proceeding.
if DSN and not re.search(r"/[^/?]*test[^/?]*(\?|$)", DSN):
    DSN = None
    _DSN_REASON = ("FAQ_TEST_PG_DSN does not name a *test* database; refusing "
                   "to run the destructive migration checks against it")
elif DSN and not PSQL:
    DSN = None
    _DSN_REASON = ("no psql client found: set FAQ_TEST_PSQL, or put psql on "
                   "PATH — these tests drive a real client rather than "
                   "connecting from Python")
else:
    _DSN_REASON = "FAQ_TEST_PG_DSN unset; live-Postgres migration check"


def test_the_psql_client_is_found_not_assumed(monkeypatch, tmp_path):
    """A checkout with only FAQ_TEST_PG_DSN set finds psql the way a shell
    would, or says it found none: it never falls back to a path that exists on
    one seat. The stand-in client is an empty file — found, never run."""
    monkeypatch.delenv("FAQ_TEST_PSQL", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assumed = _resolve_psql()
    assert assumed is None, (
        "with FAQ_TEST_PSQL unset and nothing on PATH a client was still "
        "chosen (%r) — a path assumed, not found" % assumed)

    name = "psql.exe" if os.name == "nt" else "psql"
    on_path = tmp_path / name
    on_path.write_bytes(b"")
    on_path.chmod(0o755)
    found = _resolve_psql()
    assert found and (os.path.normcase(os.path.abspath(found))
                      == os.path.normcase(str(on_path))), (
        "the psql on PATH was not the client chosen: %r" % found)

    named = tmp_path / "named" / name
    named.parent.mkdir()
    named.write_bytes(b"")
    named.chmod(0o755)
    monkeypatch.setenv("FAQ_TEST_PSQL", str(named))
    assert _resolve_psql() == str(named), "FAQ_TEST_PSQL did not win over PATH"

    monkeypatch.setenv("FAQ_TEST_PSQL", str(tmp_path / "absent" / name))
    assert _resolve_psql() is None, (
        "a FAQ_TEST_PSQL naming nothing runnable was accepted, so the tests "
        "below would die on a missing file instead of skipping with a reason")

# 109's shape, reduced to the columns 338 touches. Built here rather than by
# running 109 so this test says what it depends on.
_BASE_TABLE = """
DROP TABLE IF EXISTS pending_channel_posts;
CREATE TABLE pending_channel_posts (
    id         BIGSERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL,
    content    TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_at  TIMESTAMPTZ
);
INSERT INTO pending_channel_posts (channel_id, content, sort_order, posted_at)
VALUES ('1159243585309384805', 'stale message one', 1, now()),
       ('1159243585309384805', 'stale message two', 2, now()),
       ('777', '[MODCASE:0af1c0de-0000-4000-8000-000000000000]
Report: spam', 5, now()),
       ('999', 'never posted', 9, NULL);
"""


def _psql(sql, expect_ok=True):
    # -t -A: tuples only, unaligned — so an assertion reads the value and not
    # psql's column header, which is exactly the "the filter hid the field you
    # were judging by" shape (#441).
    proc = subprocess.run(
        [PSQL, "-v", "ON_ERROR_STOP=1", "-q", "-X", "-t", "-A", "-d", DSN, "-c", sql],
        capture_output=True, text=True)
    if expect_ok:
        assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc


def _psql_file(path, expect_ok=True):
    proc = subprocess.run(
        [PSQL, "-v", "ON_ERROR_STOP=1", "-q", "-X", "-d", DSN, "-f", path],
        capture_output=True, text=True)
    if expect_ok:
        assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc


# ── A second, concurrent session ────────────────────────────────────────────
#
# Two of the defects closed here are races: two pollers handed the same row,
# and a review approving between a count and the retirement it justifies. A
# single-session test cannot see either, and reasoning about lock modes on
# paper is how the first versions of both were written. So these run a real
# second backend and synchronise on the SERVER's own view of it rather than on
# a sleep, which would be a check that passes or fails by timing (#342).


def _psql_background(sql, marker):
    """Start a psql that holds a transaction open. `marker` must appear in the
    SQL so _await_session can find this backend in pg_stat_activity."""
    assert marker in sql or marker in ("pollerhold", "reviewhold", _RACE_MARKER)
    tagged = "/* %s */ %s" % (marker, sql)
    return subprocess.Popen(
        [PSQL, "-v", "ON_ERROR_STOP=1", "-q", "-X", "-t", "-A", "-d", DSN,
         "-c", tagged],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _await_session(marker, want="active", timeout=30.0):
    """Block until the marked backend is in `want`, or fail.

    The poll's own query must not match the marker, or the check answers
    itself — so the literal is split and re-joined by the server (#342: a
    check that cannot fail). Bounded: never an unbounded wait loop (#361)."""
    head, tail = marker[:4], marker[4:]
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = _psql(
            "SELECT count(*) FROM pg_stat_activity "
            " WHERE pid <> pg_backend_pid() AND state = '%s' "
            "   AND query LIKE '%%' || '%s' || '%s' || '%%';"
            % (want, head, tail)).stdout.strip()
        if n and int(n) >= 1:
            return
        time.sleep(0.2)
    raise AssertionError(
        "the %s session never reached state %r within %ss" % (marker, want, timeout))


def _channel_post_table():
    """Every column 338 writes, for every row, as one string.

    "Applies twice" is a claim about the whole table, so the thing compared
    across the second run has to be the whole table. An earlier version of the
    test below read all of this BEFORE the second apply and then compared only
    SUM(revision) afterwards — which is blind to a backfill that rewrote a
    fingerprint, re-stamped handed_revision, or moved a message id, i.e. to
    exactly the non-convergence the second run exists to catch (#441: never let
    the projection hide the field you are judging by). content is hashed rather
    than quoted because the FAQ bodies are kilobytes; any rewrite moves the
    hash."""
    return _psql(
        "SELECT string_agg(sort_order || ':' || revision"
        "       || ':' || COALESCE(posted_revision::text, '-')"
        "       || ':' || COALESCE(adopt_fingerprint, '-')"
        "       || ':' || COALESCE(handed_revision::text, '-')"
        "       || ':' || COALESCE(handed_fingerprint, '-')"
        "       || ':' || handed_revisionless"
        "       || ':' || COALESCE(message_id, '-')"
        "       || ':' || COALESCE(posted_at::text, '-')"
        "       || ':' || COALESCE(claimed_at::text, '-')"
        "       || ':' || COALESCE(claimed_token::text, '-')"
        "       || ':' || md5(content), E'\\n' ORDER BY sort_order) "
        "  FROM pending_channel_posts;").stdout


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_338_applies_twice():
    """A migration is not reviewed until its statements have RUN (#340/#465),
    and the deploy wrapper re-runs a whole file on retry (#243), so 'applies
    twice with the same result' is the bar rather than 'parses'."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)

    cols = _psql(
        "SELECT string_agg(column_name, ',' ORDER BY column_name) "
        "FROM information_schema.columns "
        "WHERE table_name = 'pending_channel_posts' "
        "AND column_name IN "
        "('message_id','revision','posted_revision','adopt_fingerprint',"
        "'claimed_at','claimed_token','handed_revision','handed_fingerprint',"
        "'handed_revisionless');"
    ).stdout
    assert ("adopt_fingerprint,claimed_at,claimed_token,handed_fingerprint,"
            "handed_revision,handed_revisionless,message_id,posted_revision,"
            "revision" in cols), cols
    # handed_revisionless decides whether a tokenless ack may read the
    # handed_* pair back, so it must never be NULL: a three-valued flag would
    # make that test neither true nor false and the ack would quietly refuse
    # every pre-338 delivery.
    assert _psql(
        "SELECT is_nullable || '/' || COALESCE(column_default,'-') "
        "FROM information_schema.columns "
        "WHERE table_name = 'pending_channel_posts' "
        "AND column_name = 'handed_revisionless';").stdout.strip() == "NO/false"
    # claimed_token has to be a uuid, not free text: the ack CASTs it, and a
    # TEXT column would compare a malformed token as merely unequal instead of
    # refusing it.
    assert _psql(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'pending_channel_posts' "
        "AND column_name = 'claimed_token';").stdout.strip() == "uuid"

    idx = _psql(
        "SELECT indexdef FROM pg_indexes "
        "WHERE indexname = 'idx_pending_channel_posts_unrendered';").stdout
    assert "posted_revision IS DISTINCT FROM revision" in idx, idx

    # An already-delivered row must read as delivered, or the bot would treat
    # the whole archive as un-posted and re-send it.
    state = _psql(
        "SELECT sort_order || ':' || COALESCE(posted_revision::text, 'null') "
        "|| ':' || COALESCE(adopt_fingerprint, 'null') "
        "FROM pending_channel_posts ORDER BY sort_order;").stdout
    assert "1:1:stale message one" in state, state
    assert "9:null:null" in state, state
    # The same capture under the hand-out column names. A row delivered before
    # this file ran WAS handed LEFT(content, 2000) at revision 1 by the pre-338
    # api, which is what makes the backfill a statement of fact rather than a
    # convenience — and it is what a revisionless ack reads back.
    assert _claim(1) == "null|1|stale message one", _claim(1)
    assert _claim(5) == "null|null|null", _claim(5)   # moderation case: neither
    assert _claim(9) == "null|null|null", _claim(9)   # never delivered: neither
    # A moderation post's stored content opens with the marker the bot strips
    # before sending, so LEFT(content, 2000) is NOT what is on Discord. It is
    # fire-once and never corrected, so it gets no fingerprint rather than a
    # wrong one that would read as an adoption this row cannot do.
    assert "5:1:null" in state, state
    # message_id stays NULL: nobody has the ids of the messages posted before
    # this migration, and the bot adopts them from the fingerprint instead.
    assert _psql(
        "SELECT count(*) FROM pending_channel_posts "
        "WHERE message_id IS NOT NULL;").stdout.strip() == "0"

    # The convergence bar, measured over every column the file writes rather
    # than over one aggregate of one of them. A relaxed backfill guard — say
    # keying section 1 on handed_fingerprint instead of adopt_fingerprint —
    # re-derives the fingerprints from the content section 2 already replaced
    # and re-stamps handed_revision = 1 on rows now at revision 2, which
    # SUM(revision) cannot see at all.
    before = _channel_post_table()
    _psql_file(MIGRATION)
    after = _channel_post_table()
    assert before == after, (
        "a second apply changed the table — the guards are not convergent:\n"
        "%s\n---\n%s" % (before, after))

    # The header's claim about the state it CANNOT rescue, pinned with the
    # behaviour: a prose-only reversion that quietly promises to recover a
    # corrected pre-338 delivery would otherwise stay green (#302/#351).
    header = _read(MIGRATION)
    assert "The one state neither capture reaches" in header, (
        "338 no longer states the mixed-version state it does not cover")
    assert "handed_revision /" in header and "handed_fingerprint" in header, (
        "338's header no longer explains what the hand-out record is for")


# ── 5b. The two mixed-version windows, against a real server ────────────────
#
# Both are states the DATABASE can be left in by a fleet that is half
# upgraded, and both are resolved by SQL that lives in main.py. Reimplementing
# that SQL here would test this file's idea of it (#391), so the statements are
# lifted out of the deployed function and executed verbatim; only the bind
# parameters, which psql has no notion of, are substituted.

API_MAIN = os.path.join(REPO, "backend", "api", "main.py")

_PARSED = {}


def _parsed(path):
    """(source, ast.parse of it) for one file, parsed once per CONTENT.

    main.py runs to tens of thousands of lines and one parse of it takes
    seconds; every lift below used to parse it again, which made the Postgres
    tests spend most of their time parsing and once put that time inside a
    race test's timed window. The key is a digest of the text that was just
    read, never the name or a modification time, so a file that changed on
    disk — a mutation control, an edit between two runs — is parsed afresh.
    One tree is kept per path. Callers read the tree and never edit it: the
    two that remove a decorator do it on a deep copy."""
    src = _read(path)
    digest = hashlib.sha256(src.encode("utf-8")).hexdigest()
    hit = _PARSED.get(path)
    if hit is None or hit[0] != digest:
        hit = (digest, src, ast.parse(src, path))
        _PARSED[path] = hit
    return hit[1], hit[2]


def _lift_sql(func_name, needle):
    tree = _parsed(API_MAIN)[1]
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == func_name):
            found = [n.value for n in ast.walk(node)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)
                     and needle in n.value]
            assert len(found) == 1, (
                "%s holds %d SQL literals containing %r (expected exactly 1)"
                % (func_name, len(found), needle))
            return found[0]
    raise AssertionError("main.py no longer defines %s" % func_name)


def _lift_module_str(name):
    """A module-level string constant of main.py, by name.

    The pending statement is held as a module constant with one `{where}`
    placeholder precisely so it exists as ONE literal: a statement assembled
    from fragments at the call site can only be re-assembled here, and a test
    that re-assembles the thing it is checking is checking itself (#391)."""
    tree = _parsed(API_MAIN)[1]
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    val = ast.literal_eval(node.value)
                    assert isinstance(val, str) and val, name
                    return val
    raise AssertionError("main.py no longer defines %s at module level" % name)


def _docstring(path, name):
    """The docstring of one function of `path`, by name.

    A comment is a claim, and the highest-risk comment is one a fix authored
    about its own new rule (#351/#366). The behavioural tests below red when
    the CODE regresses; these lift the docstring so a prose-only reversion —
    putting back a sentence the code no longer supports — reds too. Scoped to
    the one function, never a file-wide substring: discord_bot.py is 12k lines
    and main.py 57k, so a file-wide check would pass on a sentence that had
    moved somewhere it is no longer true (#432)."""
    tree = _parsed(path)[1]
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name):
            doc = ast.get_docstring(node)
            assert doc, "%s:%s has no docstring at all" % (path, name)
            return doc
    raise AssertionError("%s no longer defines %s" % (path, name))


def _function_source(path, name):
    """The SOURCE of one function of `path`, by name — body and comments.

    _states_at pins a docstring; a residual is sometimes written where the
    reader will meet it instead, as an inline comment beside the check it is
    about. Scoped to the one function for _docstring's reason (#432): main.py
    is 57k lines, so a file-wide substring would pass on a sentence that had
    moved somewhere it is no longer true."""
    src, tree = _parsed(path)
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name):
            seg = ast.get_source_segment(src, node)
            assert seg, "%s:%s has no readable source segment" % (path, name)
            return seg
    raise AssertionError("%s no longer defines %s" % (path, name))


def _states_at(path, name, *sentences):
    doc = _docstring(path, name)
    missing = [s for s in sentences if s not in doc]
    assert not missing, (
        "%s:%s no longer states %s — the rule below it is tested, but the "
        "comment that tells the next reader what the rule IS was reverted"
        % (path, name, missing))


def _lift_py(*names):
    """Execute the named module-level functions of main.py in isolation.

    main.py cannot be imported in a test process (it builds the whole api on
    import), and a rule that is only re-implemented here is a test agreeing
    with itself (#391). These functions are self-contained, so lifting the
    real definitions and running them is the honest version."""
    tree = _parsed(API_MAIN)[1]
    picked, seen = [], set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            picked.append(fn)
            seen.add(node.name)
    missing = set(names) - seen
    assert not missing, "main.py no longer defines %s" % sorted(missing)
    ns = {}
    exec(compile(ast.Module(body=picked, type_ignores=[]), API_MAIN, "exec"), ns)
    return ns


def test_an_ack_is_only_called_stale_when_the_caller_can_act_on_it():
    """The reply rule, executed.

    NOT_CLAIMANT comes FIRST and is decided by whether THIS caller's write
    happened, never by what the row looks like afterwards. That ordering is the
    round-three HIGH: a losing poller's ack was answered by re-reading the row,
    and if the winner had already advanced it to the state the loser asked for,
    the loser was told "acked" and the database then looked finished to
    everybody.

    "Stale" means the row is still behind its own revision after the write, so
    the caller — which still holds the claim — is handed the current revision
    and content and edits forward in the same tick. A caller that named NO
    revision, the pre-338 bot which cannot edit at all, is never told stale: it
    would read a normal delivery as a failure and log one every tick, and there
    is nothing it could do about it anyway."""
    reply = _lift_py("_channel_post_ack_reply")["_channel_post_ack_reply"]

    # Rendered the current revision: done.
    assert reply(7, 2, {"revision": 2, "posted_revision": 2, "content": "x",
                        "authorized": True}) == {
        "status": "acked", "id": 7, "revision": 2}
    # Rendered revision 1 while the row moved to 2: stale, with the newer text.
    assert reply(7, 1, {"revision": 2, "posted_revision": 1, "content": "new",
                        "authorized": True}) == {
        "status": "stale", "id": 7, "revision": 2, "content": "new"}
    # Named nothing (a pre-338 bot): acked, whatever the row says.
    assert reply(7, None, {"revision": 2, "posted_revision": None,
                           "content": "new", "authorized": True}) == {
        "status": "acked", "id": 7, "revision": None}
    # NOT the claimant. The row here reads EXACTLY like the finished case
    # above, because the poller that does hold the claim finished it — and the
    # answer must still be a refusal, or the caller records a render it never
    # performed and nothing ever repairs the message.
    assert reply(7, 2, {"revision": 2, "posted_revision": 2, "content": "x",
                        "authorized": False}) == {
        "status": "not_claimant", "id": 7, "revision": 2}
    # ...and the refusal does not depend on the caller naming a revision.
    assert reply(7, None, {"revision": 1, "posted_revision": 1, "content": "x",
                           "authorized": False})["status"] == "not_claimant"


def test_the_reply_revision_means_what_the_status_says_it_means():
    """One key, three questions — so the answer is pinned per status.

    `revision` reports the row's CURRENT revision on a stale answer, because
    that is the number the caller must edit forward to. On acked and on
    not_claimant it reports posted_revision, which is how far the row is
    actually rendered. Every case above happens to be a row where those two
    numbers are equal or where only one of them is interesting, so none of
    them can tell the meanings apart; these rows make them differ.

    The NULL matters most. A refused caller on a row nothing has ever rendered
    is told revision=None, and a consumer that read the key as "how far behind
    is this row" without branching on status would take that as an answer
    rather than as a refusal — it would skip the row instead of retrying under
    a fresh claim. The bot branches on status alone and would never catch it,
    so the contract is stated in the docstring and pinned here."""
    reply = _lift_py("_channel_post_ack_reply")["_channel_post_ack_reply"]
    behind = {"revision": 5, "posted_revision": 1, "content": "new"}

    assert reply(7, 1, dict(behind, authorized=True)) == {
        "status": "stale", "id": 7, "revision": 5, "content": "new"}, (
        "a stale answer must hand back the revision the caller has to reach")
    assert reply(7, 1, dict(behind, authorized=False)) == {
        "status": "not_claimant", "id": 7, "revision": 1}, (
        "a refusal must report how far the row is RENDERED, not where it is")
    assert reply(7, 5, {"revision": 5, "posted_revision": 5, "content": "n",
                        "authorized": True}) == {
        "status": "acked", "id": 7, "revision": 5}, (
        "an acked answer must report what this caller's write recorded")
    assert reply(7, 2, {"revision": 4, "posted_revision": None, "content": "n",
                        "authorized": False}) == {
        "status": "not_claimant", "id": 7, "revision": None}, (
        "a refusal on a row nothing has rendered must say so with NULL, not "
        "borrow the row's current revision and look like progress")

    _states_at(API_MAIN, "_channel_post_ack_reply",
               "WHAT `revision` REPORTS DEPENDS ON `status`")


TOKEN_A = "aaaaaaaa-0000-4000-8000-00000000000a"
TOKEN_B = "bbbbbbbb-0000-4000-8000-00000000000b"


def _lease():
    return int(re.search(r"^CHANNEL_POST_CLAIM_SECONDS = (\d+)$",
                         _read(API_MAIN), re.M).group(1))


def _pending_sql(revisions=True, lease=None, token=TOKEN_A):
    """The deployed pending statement, bound for psql.

    Both halves come out of main.py: the statement, and the WHERE literal the
    endpoint selects with its bool. Writing either one here would let the
    deployed pair drift while this file stayed green."""
    where = _lift_module_str("_CHANNEL_POST_WHERE_UNRENDERED" if revisions
                             else "_CHANNEL_POST_WHERE_UNPOSTED")
    if lease is None:
        lease = _lease()
    sql = _lift_module_str("_CHANNEL_POST_PENDING_SQL").format(where=where)
    # `revisionless` is the endpoint's own `not revisions`, bound here the way
    # the endpoint binds it, so a hand-out in this file records the same kind
    # of caller a real poll of that shape would.
    out = (sql.replace("CAST(:token AS uuid)", "CAST('%s' AS uuid)" % token)
              .replace("CAST(:revisionless AS BOOLEAN)",
                       "CAST(%s AS BOOLEAN)" % ("false" if revisions else "true"))
              .replace(":lease", str(lease)))
    leftover = re.search(r"(?<![:\w]):[a-z_]{2,}", out)
    assert not leftover, "unbound parameter %r left in %r" % (leftover.group(0), out)
    return out


def _bind(sql, pid, rev="NULL", mid="NULL", token="NULL", bind="false",
          release="false", lease=None):
    out = (sql.replace("CAST(:rev AS INTEGER)", "CAST(%s AS INTEGER)" % rev)
              .replace("CAST(:mid AS TEXT)", "CAST(%s AS TEXT)" % mid)
              .replace("CAST(:token AS uuid)", "CAST(%s AS uuid)" % token)
              .replace("CAST(:bind AS BOOLEAN)", "CAST(%s AS BOOLEAN)" % bind)
              .replace("CAST(:release AS BOOLEAN)", "CAST(%s AS BOOLEAN)" % release)
              .replace(":lease", str(_lease() if lease is None else lease))
              .replace(":pid", str(pid)))
    # A bare ":" is not the test — the statement carries '[MODCASE:%' and
    # ::casts, and a guard that tripped on those would be turned off rather
    # than fixed. A SQLAlchemy bind is a colon that starts a word.
    leftover = re.search(r"(?<![:\w]):[a-z_]{2,}", out)
    assert not leftover, "unbound parameter %r left in %r" % (leftover.group(0), out)
    return out


def _ack_sql():
    """The deployed ack, as ONE literal. It is a module constant for the same
    reason the hand-out is: a statement assembled at its call site can only be
    re-assembled here, and a test that re-assembles the thing it checks is
    checking itself (#391)."""
    return _lift_module_str("_CHANNEL_POST_ACK_SQL")


def _state(order):
    return _psql(
        "SELECT COALESCE(posted_revision::text,'null') || '|' || "
        "       COALESCE(adopt_fingerprint,'null') || '|' || "
        "       COALESCE(message_id,'null') || '|' || "
        "       CASE WHEN posted_at IS NULL THEN 'unposted' ELSE 'posted' END "
        "  FROM pending_channel_posts WHERE sort_order = %d;" % order
    ).stdout.strip()


def _handed_kind(order):
    """handed_revisionless — WHICH KIND of poller the row was last handed to.

    Read on its own rather than folded into _claim, whose three-field shape is
    asserted verbatim in a dozen places. It decides whether a tokenless ack may
    read the handed_* pair back at all, so a test that means "a pre-338 bot
    answering its own hand-out" and a test that means "a tokenless call after a
    revision-capable poller took the row" differ in exactly this column."""
    return _psql("SELECT handed_revisionless FROM pending_channel_posts "
                 "WHERE sort_order = %d;" % order).stdout.strip()


def _claim(order):
    """claimed_token|handed_revision|handed_fingerprint — the columns the
    DELIVERY state deliberately excludes, read separately so a test can say
    which of the two sets it expects to have moved."""
    return _psql(
        "SELECT COALESCE(claimed_token::text,'null') || '|' || "
        "       COALESCE(handed_revision::text,'null') || '|' || "
        "       COALESCE(handed_fingerprint,'null') "
        "  FROM pending_channel_posts WHERE sort_order = %d;" % order
    ).stdout.strip()


def _hand_out(revisions=True, lease=None, project=None, token=TOKEN_A):
    """Run the deployed hand-out once and read what it returned.

    A data-modifying CTE may only sit at the top level, so the statement
    cannot be wrapped in a subquery; it is materialised into a temp table in
    the SAME psql session instead and read from there. The statement itself is
    never rewritten — the point of lifting it is that the thing executed is
    the thing deployed (#391)."""
    # sort_order is what the fixture rows are named by here; the endpoint does
    # not return it, so the hand-out is joined back to the table by id.
    project = project or (
        "string_agg(p.sort_order || '|' || "
        "COALESCE(h.posted_revision::text,'null') || '|' || "
        "COALESCE(h.adopt_fingerprint,'null'), ' ; ' ORDER BY p.sort_order) "
        "FROM handed h JOIN pending_channel_posts p ON p.id = h.id")
    sql = _pending_sql(revisions=revisions, lease=lease, token=token)
    return _psql("CREATE TEMP TABLE handed AS " + sql + "; "
                 "SELECT " + project + ";").stdout.strip()


def _pending_rows(revisions=True, lease=None, token=TOKEN_A):
    """sort_order|posted_revision|adopt_fingerprint for one hand-out."""
    return _hand_out(revisions=revisions, lease=lease, token=token)


_AMBIGUITY_PROJECT = (
    "COALESCE(string_agg(p.sort_order || '=' || h.ambiguous, ' ; ' "
    "ORDER BY p.sort_order), '') "
    "FROM handed h JOIN pending_channel_posts p ON p.id = h.id")

_ORDERS_PROJECT = (
    "COALESCE(string_agg(p.sort_order::text, ',' ORDER BY p.sort_order), '') "
    "FROM handed h JOIN pending_channel_posts p ON p.id = h.id")


def _handed_orders(token=TOKEN_A, revisions=True, lease=None):
    """The sort_orders one hand-out took, as a list.

    Scoped by sort_order rather than counted: 338 corrects the seeded FAQ rows
    in the fixture table too, so a bare count answers a question about those
    rows as much as about the one under test (#441 — never let the filter hide
    the field you are judging by)."""
    got = _hand_out(revisions=revisions, lease=lease, token=token,
                    project=_ORDERS_PROJECT)
    return [x for x in got.split(",") if x]


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_the_pending_read_derives_a_legacy_fingerprint_and_writes_no_delivery_fact():
    """WINDOW ONE — 338 applied, old api, old bot still running.

    The pre-338 ack writes posted_at and nothing else, so every row that bot
    delivers afterwards reads, by the revision columns alone, exactly like a
    row that was never posted, and nobody recorded the text it was sent with.

    Round two resolved those rows with an UPDATE on this GET: posted_revision
    = 1 for every one of them. That is a statement about what is on Discord
    made by the side that cannot see Discord, and on a row corrected since
    delivery it recorded a revision while capturing no fingerprint — a row
    findable by neither handle. Now no DELIVERY fact is written here. The
    fingerprint is DERIVED in the projection instead, and only where it is
    provable: any rewrite bumps revision, so revision = 1 on a delivered row
    proves the stored content is still the text that was sent. A row already
    past revision 1 is handed over with no fingerprint and no revision, and the
    bot leaves its message alone.

    THE STATEMENT IS NOT READ-ONLY, and the assertions below say which columns
    are which. It claims every row it hands out (claimed_at, claimed_token) and
    records what it served (handed_revision, handed_fingerprint). Round three's
    version of this test hashed only the delivery columns while its docstring
    said "writes nothing", so the claim was wider than the check — the exact
    shape this file exists to remove. Both halves are asserted here: the
    delivery hash must NOT move, and the claim columns MUST."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    # A row the OLD bot delivered after 338 landed: stamp only.
    _psql("UPDATE pending_channel_posts SET posted_at = now() WHERE sort_order = 9;")
    # ...and one that was delivered and then corrected before the upgrade, so
    # nobody holds the text that is actually on Discord.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order, posted_at) "
          "VALUES ('999', 'rewritten since delivery', 11, now());")
    _psql("UPDATE pending_channel_posts SET revision = 2 WHERE sort_order = 11;")
    # ...and a moderation case delivered the same way. Its stored content
    # opens with the marker the bot strips before sending, so LEFT(content,
    # 2000) is NOT what is on Discord and must not be offered as one.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order, posted_at) "
          "VALUES ('777', '[MODCASE:0af1c0de-0000-4000-8000-000000000002]"
          "\nReport: spam', 15, now());")

    before = _psql(
        "SELECT md5(string_agg(sort_order || ':' || "
        "COALESCE(posted_revision::text,'-') || ':' || "
        "COALESCE(adopt_fingerprint,'-'), '|' ORDER BY sort_order)) "
        "FROM pending_channel_posts;").stdout

    handed = _pending_rows()
    # sort_order 9 was delivered and never rewritten, so its sent text is
    # recoverable and offered; 11 was rewritten, so it is not.
    assert "9|null|never posted" in handed, handed
    assert "11|null|null" in handed, handed
    # 338 backfilled this one, so the column answers directly and the
    # derivation is not what is being read here.
    assert "1|1|stale message one" in handed, handed
    # A moderation row's stored content is not what was posted for it: the
    # projection excludes it exactly as 338's backfill did, so this row is
    # handed over with nothing to adopt by rather than with a string that
    # could never match.
    assert "15|null|null" in handed, handed
    # ...and the moderation row 338 DID resolve is not pending at all.
    assert "5" not in [e.split("|")[0] for e in handed.split(" ; ")], handed

    after = _psql(
        "SELECT md5(string_agg(sort_order || ':' || "
        "COALESCE(posted_revision::text,'-') || ':' || "
        "COALESCE(adopt_fingerprint,'-'), '|' ORDER BY sort_order)) "
        "FROM pending_channel_posts;").stdout
    assert before == after, (
        "the pending read recorded a delivery fact. Only an ack, from the side "
        "that can see the channel, may do that")

    # ...and the POSITIVE half: the hand-out did write, and a test that only
    # checked the hash above would pass just as well on a statement that had
    # silently stopped claiming or stopped recording what it served (#438 —
    # acceptance is a positive signal the feature emits).
    assert _claim(9) == "%s|1|never posted" % TOKEN_A, _claim(9)
    assert _claim(11).startswith(TOKEN_A), _claim(11)
    assert _claim(11).endswith("|2|rewritten since delivery"), _claim(11)
    # A moderation row is claimed like any other but gets no handed
    # fingerprint: its marker is stripped before sending, so LEFT(content,
    # 2000) is not what a bot would put on Discord for it.
    assert _claim(15) == "%s|1|null" % TOKEN_A, _claim(15)
    # ...and the hand-out records WHICH KIND of caller it served. This one
    # asked for revisions, so a later tokenless ack is not the poller this row
    # was handed to and may not read the pair above back as its own.
    assert _handed_kind(9) == "f", _handed_kind(9)
    assert _handed_kind(11) == "f", _handed_kind(11)

    _states_at(API_MAIN, "pending_channel_posts",
               "THIS ENDPOINT RECORDS NO DELIVERY FACT. It DOES write",
               "WHAT IT HANDED IS RECORDED HERE")


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_two_pollers_cannot_both_receive_one_row():
    """The claim, against two real concurrent sessions.

    The previous pending SELECT was a plain read with no claim: two pollers
    each got the same never-posted row, each sent it, and the ack — which
    happens after the send — was the only thing between them and two copies.
    Session A holds its claim open; session B must come back empty rather than
    with A's rows."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    _psql("DELETE FROM pending_channel_posts WHERE posted_at IS NOT NULL;")
    n_fresh = _psql("SELECT count(*) FROM pending_channel_posts "
                    "WHERE posted_at IS NULL;").stdout.strip()
    assert n_fresh == "1", n_fresh   # a claim with nothing to claim proves nothing

    held = _psql_background(
        "BEGIN; " + _pending_sql(revisions=False) + "; SELECT pg_sleep(30);",
        marker="pollerhold")
    try:
        _await_session("pollerhold")
        second = _hand_out(revisions=False, project="count(*) FROM handed")
        assert second == "0", (
            "a second poller received %s row(s) another poller is already "
            "sending — the hand-out is not a claim" % second)
    finally:
        held.kill()
        held.wait(timeout=20)

    # The hand-out must also RECORD the claim, not merely hold a row lock for
    # the length of one statement. The two pollers that matter most are the
    # ones a tick APART, where no lock is held any more and only the column
    # says the row is already being sent.
    _psql("UPDATE pending_channel_posts SET claimed_at = NULL, claimed_token = NULL;")
    assert _hand_out(revisions=False, project="count(*) FROM handed") == "1"
    assert _psql("SELECT count(*) FROM pending_channel_posts "
                 "WHERE posted_at IS NULL AND claimed_at IS NOT NULL "
                 "AND claimed_token = CAST('%s' AS uuid);" % TOKEN_A
                 ).stdout.strip() == "1", (
        "the hand-out locked the row but never claimed it for the CALLER — a "
        "poller one tick later is handed it again and sends a second copy, and "
        "a claim with no holder cannot tell two pollers apart at ack time")
    assert _hand_out(revisions=False, project="count(*) FROM handed") == "0", (
        "the same row was handed out twice in a row")
    # ...and the token returned to the caller is the token written on the row.
    # A hand-out that returned a different one would refuse its own holder's
    # ack and nothing could ever be rendered.
    assert _hand_out(revisions=False, lease=0,
                     project="string_agg(DISTINCT h.claim_token, ',') "
                             "FROM handed h") == TOKEN_A

    # ...and the claim is a LEASE, not a lock: a poller that died mid-batch
    # must not strand the row. With the lease expired the row comes back —
    # this is the ONLY route out of a claim a crashed poller can take.
    _psql("UPDATE pending_channel_posts SET claimed_at = now(), "
          "claimed_token = CAST('%s' AS uuid) WHERE posted_at IS NULL;" % TOKEN_B)
    assert _hand_out(revisions=False, project="count(*) FROM handed") == "0"
    assert _hand_out(revisions=False, lease=0,
                     project="count(*) FROM handed") == "1", (
        "an expired claim still hides the row — a dead poller would strand it")


def _pid(order):
    return _psql("SELECT id FROM pending_channel_posts "
                 "WHERE sort_order = %d;" % order).stdout.strip()


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_a_legacy_ack_records_what_the_hand_out_gave_it():
    """WINDOW TWO — new api, old bot still running.

    That bot cannot name the revision it rendered, and it can never report a
    message id. Round two filled the gap with COALESCE(:rev, revision), i.e.
    "whatever the row says now" — so a correction landing between that bot's
    send and its ack was CONSUMED by the ack: the row read "revision 2
    rendered" while Discord still showed revision 1, and nothing ever
    delivered the correction. Round three refused to record anything for that
    row instead, which left it delivered with NEITHER handle and needing a
    message id supplied by hand.

    Now the hand-out records what it SERVED, and this ack reads that back: a
    bot that cannot name a revision rendered what it was handed, whatever the
    row says by the time the ack arrives. So the corrected row keeps an exact
    fingerprint for the text that is actually on Discord, stays pending, and
    is finished by the upgraded bot with no manual step anywhere."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _ack_sql()

    # The nominal legacy delivery: handed at revision 1, acked at revision 1.
    # The hand-out is the revisionless shape, which is what authorizes the
    # tokenless ack below — the shape of the ACK alone does not.
    _hand_out(revisions=False)
    assert _handed_kind(9) == "t", _handed_kind(9)
    _psql(_bind(full, _pid(9)))
    assert _state(9) == "1|never posted|null|posted", _state(9)

    # THE R2-1 STATE: a correction commits between the hand-out and the ack.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'as it went out', 14);")
    _hand_out(revisions=False)                     # handed at revision 1
    _psql("UPDATE pending_channel_posts SET revision = 2, "
          "content = 'corrected while in flight' WHERE sort_order = 14;")
    _psql(_bind(full, _pid(14)))
    assert _state(14) == "1|as it went out|null|posted", (
        "the legacy ack did not record what the bot was handed: %s" % _state(14))
    # ...and that row is STILL PENDING, with an exact handle on its message.
    assert _psql("SELECT count(*) FROM pending_channel_posts "
                 "WHERE sort_order = 14 AND posted_revision IS DISTINCT FROM "
                 "revision;").stdout.strip() == "1", (
        "the correction was recorded as delivered by a bot that never saw it")

    # A bot that CAN report an id records the id AND the fingerprint: the id
    # is the better handle for editing, but the fingerprint has a second
    # reader — the hand-out's ambiguity test, which asks whether any other row
    # in the channel would scan for this text. Left unwritten (or left stale)
    # that test answers about text this row's message does not carry. So the
    # ack that names the row's current revision refreshes it to what it just
    # rendered.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'delivered by a current bot', 12);")
    _hand_out(revisions=False)
    _psql(_bind(full, _pid(12), rev="1", mid="'7788'", token="'%s'" % TOKEN_A))
    assert _state(12) == "1|delivered by a current bot|7788|posted", _state(12)

    # A moderation case's stored content is not what was posted for it, so it
    # gets no fingerprint however it is acked (338's exclusion, carried into
    # handed_fingerprint by the hand-out).
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('777', '[MODCASE:0af1c0de-0000-4000-8000-000000000001]"
          "\nReport: spam', 13);")
    _hand_out(revisions=False)
    _psql(_bind(full, _pid(13)))
    assert _state(13) == "1|null|null|posted", _state(13)

    _states_at(API_MAIN, "ack_channel_post",
               "WHEN THE ACK NAMES NO REVISION (a pre-338 bot, which cannot), "
               "NEITHER\nBINDS NOR RELEASES (that bot sends a post id and "
               "nothing else) AND THE ROW\nWAS HANDED TO A REVISIONLESS POLLER, "
               "the row is recorded at WHAT IT WAS\nHANDED.",
               "BOTH HALVES ARE REQUIRED, and handed_revisionless is the second.")


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_a_tokenless_ack_is_the_pre_338_bot_only_when_the_hand_out_agrees():
    """The revisionless arm is authorized by a PAIR, not by a call shape.

    handed_revision / handed_fingerprint describe the LAST hand-out. Reading
    them back on the strength of the call's shape alone means any tokenless
    ack takes whichever pair happens to be on the row — including one recorded
    for a revision-capable poller that is still inside its render. That caller
    would then stamp a revision nobody rendered, capture a fingerprint for
    text it never sent, and clear a live claim; the row would satisfy
    posted_revision = revision and carry posted_at, which removes it from BOTH
    poll sets, so an announcement nobody delivered is never delivered by
    anyone and nothing says so.

    The hand-out records which kind of caller it served, and the two must
    agree. What a tokenless ack can always do is report a DELIVERY — that is
    not the claim's to refuse — and this test pins the boundary between the
    two."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _ack_sql()

    # Handed to a poller that asked for revisions: it will ack with its token.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'rendered by the current bot', 20);")
    _hand_out(token=TOKEN_A)
    assert _handed_kind(20) == "f", _handed_kind(20)
    claim_before = _claim(20)

    out = _psql(_bind(full, _pid(20)) + " ;").stdout.strip()
    assert out.endswith("|f"), (
        "a tokenless ack was authorized on a row handed to a revision-capable "
        "poller: %r" % out)
    assert _state(20) == "null|null|null|posted", (
        "the tokenless ack took the other poller's handed record: %s"
        % _state(20))
    assert _claim(20) == claim_before, (
        "the tokenless ack cleared a claim it does not hold: %s -> %s"
        % (claim_before, _claim(20)))
    # ...and the row is still owed a render, which is the difference between
    # "recorded as delivered at a revision nobody rendered" and "delivered,
    # still behind". A row that satisfied both poll predicates would be in
    # neither set and would simply stop existing for the bus.
    assert "20" in _handed_orders(TOKEN_A, lease=0), (
        "the row left the correction set after a tokenless ack — nothing "
        "will ever render it again")

    # The negative control: the SAME call shape, on a row whose hand-out was
    # revisionless, is the pre-338 bot answering its own hand-out and is
    # recorded in full. A predicate that refused every tokenless ack would
    # pass everything above.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'rendered by an old bot', 21);")
    _hand_out(revisions=False, token=TOKEN_A)
    assert _handed_kind(21) == "t", _handed_kind(21)
    _psql(_bind(full, _pid(21)))
    assert _state(21) == "1|rendered by an old bot|null|posted", _state(21)
    assert _claim(21).startswith("null|"), (
        "the revisionless ack did not release the claim: %s" % _claim(21))


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_a_refused_ack_records_the_delivery_and_nothing_else():
    """THE ROUND-THREE HIGH at its root — and the cost of over-correcting it.

    A claim that says only "somebody is rendering" cannot tell two pollers
    apart at ack time. Round three therefore answered a losing ack by
    re-reading the ROW — and if the winner had already advanced it to exactly
    the state the loser asked for, the loser was told "acked". The database
    then looked finished to everyone and suppressed every repair.

    The claim carries its holder now, and an ack that does not present it
    records NO revision, moves NO fingerprint, replaces NO stored id and
    releases NO claim. What it DOES record is the delivery it reports:
    posted_at, and an id for a row that has none. That half was never the
    claim's to refuse. A tick whose lease expires inside ch.send has already
    put the message in the channel; refusing its report whole leaves the row
    reading "never posted" while the only other memory of that send is the
    bot's in-process dict, so the next restart posts a second copy (#105) —
    the exact duplicate this bus exists to remove.

    Round four refused the whole ack, and this test asserted that as correct
    with mid='999001' on an unposted row. That is what a check written from
    the state you had in mind looks like (#351)."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _ack_sql()
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'one renderer only', 30);")
    _hand_out(revisions=False, token=TOKEN_A)      # A holds the claim

    claim_before = _claim(30)
    # B acks with ITS token, naming the revision it thinks it rendered.
    out = _psql(_bind(full, _pid(30), rev="1", mid="'999001'",
                      token="'%s'" % TOKEN_B) +
                " ;").stdout.strip()
    assert out.endswith("|f"), (
        "the statement reported the non-claimant's ack as authorized: %r" % out)
    assert _claim(30) == claim_before, (
        "a non-claimant's ack moved the claim: %s -> %s"
        % (claim_before, _claim(30)))
    # No revision and no fingerprint — and the delivery it reported IS kept.
    assert _state(30) == "null|null|999001|posted", (
        "a refused ack must record the message it reported and nothing else: "
        "%s" % _state(30))
    # The consequence that matters, as a positive signal: the row has left the
    # SEND set, so a restarted bot with an empty sent-memory cannot post a
    # second copy. lease=0 is what makes this a real question — with the lease
    # live, A's claim would hide the row whether or not the delivery landed,
    # and the assertion could not fail for the reason it names (#342).
    assert "30" not in _handed_orders(TOKEN_B, revisions=False, lease=0), (
        "a row whose send was reported by a refused ack is still visible to "
        "the SEND path — the next restart posts a second copy of it")

    # The same rule for the case it exists for: the holder's OWN lease running
    # out while it was inside Discord.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'sent while the lease ran out', 31);")
    _hand_out(revisions=False, token=TOKEN_A)
    out = _psql(_bind(full, _pid(31), rev="1", mid="'999031'",
                      token="'%s'" % TOKEN_A, lease=0) + " ;").stdout.strip()
    assert out.endswith("|f"), (
        "an expired claim still authorized its holder: %r" % out)
    assert _state(31) == "null|null|999031|posted", (
        "the message this tick had already sent was not recorded: %s"
        % _state(31))
    assert "31" not in _handed_orders(TOKEN_B, revisions=False, lease=0), (
        "the row whose send was refused is still in the SEND set")

    # The two shapes that report NO delivery write nothing at all from a
    # non-claimant: a bind has rendered nothing yet, and a pure hand-back is a
    # decision not to render. Neither may leave a mark on a row it does not
    # hold — and a bind in particular must not be able to point a row somebody
    # else is rendering at a message of its own choosing.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'held by somebody else', 32);")
    _hand_out(revisions=False, token=TOKEN_A)
    before32 = _state(32) + "//" + _claim(32)
    _psql(_bind(full, _pid(32), mid="'999032'", bind="true",
                token="'%s'" % TOKEN_B))
    _psql(_bind(full, _pid(32), token="'%s'" % TOKEN_B, release="true"))
    assert _state(32) + "//" + _claim(32) == before32, (
        "a bind or a pure hand-back from a non-claimant changed a row it does "
        "not hold: %s -> %s" % (before32, _state(32) + "//" + _claim(32)))

    # ...and an id a row ALREADY carries is not the refused caller's to
    # replace. A first-writer-wins column is the difference between "fill in
    # what nobody recorded" and "point this row at my message instead".
    _psql("UPDATE pending_channel_posts SET message_id = '555000' "
          "WHERE sort_order = 32;")
    _psql(_bind(full, _pid(32), rev="1", mid="'999032'",
                token="'%s'" % TOKEN_B))
    assert _state(32).split("|")[2] == "555000", (
        "a non-claimant replaced the id the row already had: %s" % _state(32))

    # The negative control for every refusal above: the HOLDER, inside its
    # lease, writes the whole set — including the id, which it may correct
    # where the refused caller could only fill an empty one. That asymmetry is
    # the point: the holder is the caller that can see the channel. A
    # predicate that refused everyone would pass every assertion above.
    _psql(_bind(full, _pid(32), rev="1", mid="'999032'", token="'%s'" % TOKEN_A))
    assert _state(32) == "1|held by somebody else|999032|posted", _state(32)
    assert _claim(32).startswith("null|"), (
        "the completing ack did not release the claim: %s" % _claim(32))

    # A token presented against a row whose claim is already GONE compares
    # NULL, not false — three-valued logic, and an authorized column that
    # answered NULL would reach the caller as an empty third answer that
    # _channel_post_ack_reply reads as a refusal by accident rather than by
    # rule. It has to say f.
    out = _psql(_bind(full, _pid(32), rev="1", mid="'999032'",
                      token="'%s'" % TOKEN_A) + " ;").stdout.strip()
    assert out.endswith("|f"), (
        "an ack against a released claim answered neither true nor false: %r"
        % out)

    _states_at(API_MAIN, "ack_channel_post",
               "THE CLAIM IS THE UNIT OF EXCLUSIVE RENDERING",
               "A REFUSAL IS NOT A REASON TO FORGET A MESSAGE.")
    # ...and the loop's own copy. The bot is the side that decides a refused
    # ack is a failure and stops; if its docstring goes back to "writes
    # nothing", the next reader re-derives the duplicate this test rules out.
    _states_at(BOT, "poll_channel_posts",
               "A REFUSED ACK STILL RECORDS THE MESSAGE.")
    # ...and the reply's, which is what tells the caller what a refusal means.
    # If it goes back to saying a refused ack wrote nothing, it contradicts the
    # delivery this test has just watched persist.
    _states_at(API_MAIN, "_channel_post_ack_reply",
               "IT DOES NOT MEAN NOTHING WAS WRITTEN.")


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_a_stale_ack_keeps_the_claim_so_one_renderer_finishes_the_row():
    """The transition round three got backwards, against two real sessions.

    Poller A renders revision 2. A correction commits. A acks 2 and is told
    "stale" — and round three released the claim on that answer, so poller B
    could be handed the row and render 3 while A was still inside its tick,
    two renderers writing two revisions to one message in an order nobody
    controls. A stale answer now keeps the claim: B is handed nothing, and A
    renders forward under the same token until the row is current, at which
    point the claim is released for everybody."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _ack_sql()
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order, "
          "posted_at, message_id, posted_revision, revision) "
          "VALUES ('999', 'rev 2 text', 40, now(), '4242', 1, 2);")
    _hand_out(token=TOKEN_A)

    # A correction lands while A is rendering revision 2.
    _psql("UPDATE pending_channel_posts SET revision = 3, content = 'rev 3 text' "
          "WHERE sort_order = 40;")
    out = _psql(_bind(full, _pid(40), rev="2", mid="'4242'",
                      token="'%s'" % TOKEN_A)).stdout.strip()
    assert "|rev 3 text|t" in out, out          # authorized, handed the newer text
    assert _state(40) == "2|null|4242|posted", _state(40)
    assert _claim(40).startswith(TOKEN_A), (
        "a stale ack released the claim — another poller can now render the "
        "same message: %s" % _claim(40))

    # B polls. It must not be handed this row: it is still being rendered.
    assert "40" not in _handed_orders(TOKEN_B), (
        "a second poller was handed a row the first is still rendering")

    # A renders forward and acks what it rendered. NOW the claim goes — and
    # the fingerprint moves with it, because the message on Discord now reads
    # 'rev 3 text' and that is the text any other row's adoption scan would
    # find on it.
    _psql(_bind(full, _pid(40), rev="3", mid="'4242'", token="'%s'" % TOKEN_A))
    assert _state(40) == "3|rev 3 text|4242|posted", _state(40)
    assert _claim(40).startswith("null|"), (
        "the claim survived a completing ack: %s" % _claim(40))


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_the_render_cap_hands_the_claim_back_with_what_it_rendered():
    """Two renders per tick is the cap, and the way OUT of it is an explicit
    release naming the revision that WAS rendered — never the newer one the
    stale answer carried.

    Without the release the row would sit under a claim nobody is using until
    the 120 s lease expired. With it, the next poll continues from exactly what
    is on Discord. Nothing is re-sent by the hand-off: posted_at and the
    message id are both recorded, so the next poll takes the correction path."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _ack_sql()
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order, "
          "posted_at, message_id, posted_revision, revision) "
          "VALUES ('999', 'rev 4 text', 41, now(), '4343', 1, 4);")
    _hand_out(token=TOKEN_A)
    # The tick rendered 2 and then 3; the row is already at 4.
    _psql(_bind(full, _pid(41), rev="3", mid="'4343'", token="'%s'" % TOKEN_A,
                release="true"))
    assert _state(41) == "3|null|4343|posted", (
        "the release recorded something other than the revision it named: %s"
        % _state(41))
    assert _claim(41).startswith("null|"), (
        "release=true did not hand the claim back: %s" % _claim(41))
    # The next poll gets it, and it is a CORRECTION (posted_at set), not a send.
    assert "41" in _handed_orders(TOKEN_B)
    assert "41" not in _handed_orders(TOKEN_B, revisions=False), (
        "a row at the render cap is still visible to the SEND path")

    # A pure hand-back — release with no revision — writes no delivery fact at
    # all. It is what the bot sends when it decides not to render, and it must
    # never be able to mark an undelivered row delivered.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'never sent', 42);")
    _hand_out(revisions=False, token=TOKEN_A)
    _psql(_bind(full, _pid(42), token="'%s'" % TOKEN_A, release="true"))
    assert _state(42) == "null|null|null|unposted", (
        "a pure hand-back wrote a delivery fact: %s" % _state(42))
    assert _claim(42).startswith("null|"), _claim(42)


# ── 5c. Ownership ambiguity, computed by the server ─────────────────────────

_AMBIG_ROWS = """
INSERT INTO pending_channel_posts
       (channel_id, content, sort_order, posted_at, posted_revision, revision,
        adopt_fingerprint)
VALUES ('901', 'first corrected',  51, now(), 1, 2, 'the shared body'),
       ('901', 'second corrected', 52, now(), 1, 2, 'the shared body'),
       ('901', 'third corrected',  53, now(), 1, 2, 'a body of its own'),
       ('902', 'other channel',    54, now(), 1, 2, 'the shared body');
"""


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_ambiguity_is_a_property_of_the_channel_not_of_the_response():
    """Whose message is this? The server answers it, over the whole channel.

    Two rows whose recorded text is byte-identical are indistinguishable from
    outside, so neither may bind: the one that scanned first would take a
    message on an exactly-one match that is only exactly-one because it was
    evaluated one row at a time. But a row whose text is unique must still
    bind, or the guard is a refusal of everything — and equal text in two
    unrelated channels is not a collision at all, because the scan that would
    use it never leaves its own channel.

    The mutation that has to red HERE is dropping the fingerprint comparison
    from the EXISTS, i.e. "ambiguous if this channel holds any other row".
    Every X/X case survives that; only the X/X/Y row below catches it."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    _psql("DELETE FROM pending_channel_posts;")
    _psql(_AMBIG_ROWS)

    got = _hand_out(project=_AMBIGUITY_PROJECT)
    assert "51=t" in got, got
    assert "52=t" in got, got
    assert "53=f" in got, (
        "a row whose recorded text is unique in its channel was refused — the "
        "flag is answering 'is there another row here', not 'does another row "
        "want this message': %s" % got)
    assert "54=f" in got, (
        "equal text in an INDEPENDENT channel was treated as a collision, "
        "which blocks both corrections forever: %s" % got)


_TWIN_ROWS = """
INSERT INTO pending_channel_posts
       (channel_id, content, sort_order, posted_at, posted_revision, revision,
        adopt_fingerprint, message_id)
VALUES ('903', 'first corrected',  61, now(), 1, 2, 'the shared body', '6101'),
       ('903', 'second corrected', 62, now(), 1, 2, 'the shared body', NULL);
"""


_BOUND_IDS_PROJECT = (
    "COALESCE(string_agg(p.sort_order || '=' || h.ambiguous || '/' || "
    "COALESCE(ARRAY_TO_STRING(h.bound_message_ids, '+'), ''), ' ; ' "
    "ORDER BY p.sort_order), '') "
    "FROM handed h JOIN pending_channel_posts p ON p.id = h.id")


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_a_bound_twin_is_not_a_rival_for_its_siblings_message():
    """A row that holds an id does not scan, so it cannot be scanned INTO.

    Two rows in one channel were posted with the same text — two sheets
    differing only past Discord's 2,000-character ceiling is enough — so 338
    backfills both with the same fingerprint. While both are unbound that is a
    real collision and both must refuse; that case is
    test_ambiguity_is_a_property_of_the_channel_not_of_the_response. This is
    the other one: row 61 already HOLDS its message id, so it will never scan
    for anything — it edits 6101 directly. Treating it as a rival left its
    sibling blocked for the life of the row, and nothing the sibling or anyone
    else could do would clear it, because 61 need never be corrected again.

    BOTH HALVES ARE ASSERTED HERE, because either alone is wrong. Excluding 61
    from the flag says the sibling may scan; publishing 6101 in
    bound_message_ids is what stops that scan adopting 61's message and
    leaving two rows editing one message. If a later change drops the array
    while keeping the exclusion, this reds — which is the failure that would
    otherwise be silent and destructive."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    _psql("DELETE FROM pending_channel_posts;")
    _psql(_TWIN_ROWS)

    got = _hand_out(project=_BOUND_IDS_PROJECT)
    assert got == "61=true/ ; 62=false/6101", (
        "a bound twin is still being treated as a rival for its sibling's "
        "message, or its id is not being handed to the sibling's scan — the "
        "first blocks the sibling's correction for ever, the second lets the "
        "sibling adopt the twin's message: %s" % got)

    _states_at(API_MAIN, "pending_channel_posts",
               "A ROW THAT HOLDS AN ID DOES NOT SCAN, AND ITS MESSAGE IS OFF "
               "THE TABLE FOR")


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_the_ack_that_finishes_a_row_refreshes_its_fingerprint():
    """adopt_fingerprint must describe the text the row's message CARRIES.

    The column was written once — by 338's backfill or by a revisionless ack —
    and then left alone, which made it a claim about Discord that went stale
    the moment its holder edited the message. The ack that takes a row to its
    current revision knows exactly what it just rendered, and is the only
    caller that does.

    This is now an INVARIANT rather than the thing that unblocks a sibling:
    since a bound row is no longer a rival in the ambiguity test, a stale
    fingerprint on a bound row no longer blocks anybody. It is kept, and
    tested, because the column is documented as describing the live message
    and two readers are entitled to rely on that — the scan compares it byte
    for byte, and the ambiguity test derives from it. A column whose stated
    meaning is false is the comment-shaped defect (#351), not a spare part.

    A STALE ack must NOT move it: that caller rendered a revision whose text
    nobody stored, so writing its content would make the column describe
    neither the message nor the row."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    _psql("DELETE FROM pending_channel_posts;")
    _psql(_TWIN_ROWS)
    full = _ack_sql()

    # The hand-out is what makes the acks below AUTHORIZED. Without it the
    # statement refuses them both and the row simply stays as the fixture left
    # it — which looks exactly like "the stale ack did not move the
    # fingerprint" and would pass the first assertion for the wrong reason.
    _hand_out(token=TOKEN_A)

    _psql(_bind(full, _pid(61), rev="1", mid="'6101'", token="'%s'" % TOKEN_A))
    assert _state(61) == "1|the shared body|6101|posted", (
        "an ack behind the row's revision moved the fingerprint: %s"
        % _state(61))

    _psql(_bind(full, _pid(61), rev="2", mid="'6101'", token="'%s'" % TOKEN_A))
    assert _state(61) == "2|first corrected|6101|posted", (
        "the ack that finished the row did not refresh the fingerprint, so "
        "the column still describes text the message no longer carries: %s"
        % _state(61))

    _states_at(API_MAIN, "ack_channel_post",
               "THE FINGERPRINT IS REFRESHED BY THE ACK THAT FINISHES THE ROW.")


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_a_duplicate_split_across_two_limit_pages_is_still_ambiguous():
    """The reason this cannot live in the bot.

    The bot sees one 20-row response. With the twins on either side of that
    boundary — or taken by a concurrent poller — a batch-local computation
    finds no duplicate at all and binds confidently. The server's answer does
    not depend on where the page fell, so the row that is handed out is told
    the truth about a row that is not."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    _psql("DELETE FROM pending_channel_posts;")
    # 25 rows in one channel: the twins at 1 and 25, 23 unique rows between.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order, "
          "posted_at, posted_revision, revision, adopt_fingerprint) "
          "SELECT '903', 'row ' || g, g, now(), 1, 2, "
          "       CASE WHEN g IN (1, 25) THEN 'the shared body' "
          "            ELSE 'unique ' || g END "
          "  FROM generate_series(1, 25) g;")

    got = _hand_out(project=_AMBIGUITY_PROJECT)
    orders = [e.split("=")[0] for e in got.split(" ; ")]
    assert "1" in orders and "25" not in orders, (
        "the fixture does not split the twins across the LIMIT: %s" % orders)
    assert "1=t" in got, (
        "the row on this page was called unambiguous because its twin fell on "
        "the next one — which is exactly the state a bot-side computation "
        "cannot see: %s" % got)


_LEASE_ROW = """
INSERT INTO pending_channel_posts (channel_id, content, sort_order, revision)
VALUES ('905', 'a queued announcement', 81, 1);
"""


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_a_live_lease_is_not_voided_by_a_missing_token():
    """The pick asks about the LEASE, and about nothing else.

    The endpoint documents four routes out of a claim — the row is current,
    the caller asks for release at its render cap, the revisionless poller it
    was handed to acks, or the lease expires. The predicate used to admit a
    fifth by reading claimed_token: a row whose claim was live but whose token
    was absent was handed straight back out, lease or no lease. No writer
    produces that state — claimed_at and claimed_token are written together
    here and cleared together by the ack, and the token is a uuid minted per
    call — so this forces it by hand, which is the only way to reach it.

    The direction is what matters. Respecting an unexplained claim costs one
    lease, after which the row is driven again; ignoring it costs a second
    renderer on a row whose posted_at is NULL, i.e. the announcement posted
    twice, which is the duplicate the claim exists to prevent (#276).

    The second half is the one that keeps this from becoming a deadlock: the
    row must still come free on expiry. A predicate that refuses forever would
    be worse than the one being replaced."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    _psql("DELETE FROM pending_channel_posts;")
    _psql(_LEASE_ROW)

    assert _handed_orders() == ["81"], "the fixture row is not handed out at all"

    _psql("UPDATE pending_channel_posts SET claimed_at = NOW(), "
          "claimed_token = NULL WHERE sort_order = 81;")
    assert _handed_orders(token=TOKEN_B) == [], (
        "a row whose lease is live was handed to a second poller because its "
        "token was absent — on a row that has never been posted, that is the "
        "announcement sent twice")

    assert _handed_orders(token=TOKEN_B, lease=0) == ["81"], (
        "the row never comes free: refusing on a missing token is only safe "
        "because expiry still releases it")

    _states_at(API_MAIN, "pending_channel_posts",
               "asking only whether the LEASE is live")
    # The four routes are the ACK endpoint's claim, and the paragraph at the
    # top of this test repeats it. Prose that restates a rule without
    # asserting it is how the rule gets reverted in one file and kept in the
    # other, so the sentences are pinned where they live (#302/#351). Without
    # this the reference was decoration: the ack's docstring could say
    # anything and every assertion here stayed green.
    _states_at(API_MAIN, "ack_channel_post",
               "RELEASE, and the whole list of routes",
               "Everything else is lease expiry")


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_the_harness_names_the_server_it_ran_on():
    """Evidence that does not name its server is not reproducible evidence.

    For several rounds nothing recorded which server answered, and the name
    guard above only asks that the DATABASE be a scratch one — which a tunnel,
    a pooler or a second instance satisfies just as well.

    So the connection is asserted against the DSN it was asked for, rather
    than described: a server that answers on another port reds here instead of
    quietly producing results attributed to the documented one. The version and
    directory are printed so the log of a run says what produced it (#438 —
    acceptance is a positive signal, and an unnamed server is not one).

    The second half asks the same question of the INSTRUCTION at the top of
    this file, and asks it by connecting. It used to compare the documented
    port to the port that answered, which is a correlate and not the property
    (#732): the data directory's postgresql.conf leaves `port` commented out,
    so the port is chosen when the server is launched, and pinning the
    documented literal to one round's launch turned this test red the next
    time the same instance came up on this seat's standing 55432. What has to
    hold is that following the documented line lands on the server these
    results came from, so that is what is asked — the documented endpoint is
    dialled and its cluster identity compared. A line that refuses to connect,
    or that reaches a different cluster, reds; a relaunch on a different port
    reds only until the line is corrected to match."""
    m = re.search(r":(\d+)/", DSN)
    assert m, (
        "FAQ_TEST_PG_DSN names no port, so a run cannot say which server "
        "produced it: %r" % DSN)
    got = _psql("SELECT inet_server_port() || '|' || current_database() "
                "|| '|' || current_setting('server_version');").stdout.strip()
    port, dbname, version = got.split("|")
    assert port == m.group(1), (
        "the DSN asked for port %s and the server that answered is on %s — "
        "the results of this run would be attributed to a server that did "
        "not produce them" % (m.group(1), port))
    assert ("/" + dbname) in DSN, (
        "connected to database %r, which the DSN does not name: %r"
        % (dbname, DSN))
    # ...and the line at the top of this file that tells the next person how to
    # run these must reach that same server. That line is the only instruction
    # anybody has; when it drifts, runs move to a string typed somewhere else
    # and the evidence stops being reproducible from the repo — which is the
    # defect this test exists for, so it is checked rather than described, and
    # checked by DIALLING the endpoint rather than by comparing its port to the
    # one that answered (#732 — the port is a correlate; the server is the
    # property, and this data directory's port is a launch argument).
    ident = _psql("SELECT system_identifier FROM pg_control_system();"
                  ).stdout.strip()
    doc = re.search(r"FAQ_TEST_PG_DSN=\"([^\"]+)\"", __doc__ or "")
    assert doc, "this file no longer shows how to run its Postgres tests"
    doc_dsn = doc.group(1)
    assert re.search(r"/[^/?]*test[^/?]*(\?|$)", doc_dsn), (
        "the DSN this file documents does not name a *test* database, so "
        "following it would point the destructive migration checks somewhere "
        "this file refuses to run: %r" % doc_dsn)
    doc_ep = re.match(r"([A-Za-z0-9+]+)://([^/]+)/", doc_dsn)
    assert doc_ep, (
        "the DSN this file documents is not a URL an endpoint can be read "
        "out of: %r" % doc_dsn)
    # The documented ENDPOINT, carrying the database this run actually used —
    # so a scratch database that exists only on somebody else's seat cannot
    # red this, while an endpoint that is dead or is a different cluster does.
    probe = subprocess.run(
        [PSQL, "-v", "ON_ERROR_STOP=1", "-q", "-X", "-t", "-A",
         "-d", "%s://%s/%s" % (doc_ep.group(1), doc_ep.group(2), dbname),
         "-c", "SELECT system_identifier FROM pg_control_system();"],
        capture_output=True, text=True)
    assert probe.returncode == 0, (
        "the DSN this file documents does not reach a server at all (%r), so "
        "following the only instruction in the repo would not reproduce this "
        "run: %s" % (doc_dsn, (probe.stderr or probe.stdout).strip()))
    assert probe.stdout.strip() == ident, (
        "the DSN this file documents reaches cluster %s and these tests ran "
        "against cluster %s — the documented line would reproduce this run "
        "somewhere else" % (probe.stdout.strip(), ident))

    datadir = _psql("SELECT current_setting('data_directory');",
                    expect_ok=False).stdout.strip() or "(not readable)"
    print("[FAQ-DSN] PostgreSQL %s on port %s, database %s, data_directory %s"
          % (version, port, dbname, datadir))


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_an_ack_persists_the_revision_it_names_and_no_other():
    """Compare-and-set, all four directions.

    The ack's own number is the only one that may be written; it may not
    exceed the row's revision, because nobody renders a future text; and it
    may not move posted_revision backwards, because a stale in-flight ack
    would otherwise re-open a correction that is already on Discord."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _ack_sql()

    # A correction lands while this tick is rendering revision 1.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'now at rev 2', 21);")
    _hand_out(revisions=False, token=TOKEN_A)
    _psql("UPDATE pending_channel_posts SET revision = 2 WHERE sort_order = 21;")
    pid = _pid(21)
    tok = "'%s'" % TOKEN_A
    _psql(_bind(full, pid, rev="1", mid="'100'", token=tok))
    assert _state(21) == "1|null|100|posted", (
        "the ack did not record the revision it named: %s" % _state(21))

    # The row is therefore still pending, which is what drives the re-edit.
    assert _psql("SELECT count(*) FROM pending_channel_posts "
                 "WHERE sort_order = 21 AND posted_revision IS DISTINCT FROM "
                 "revision;").stdout.strip() == "1"

    # Forward to the current revision: accepted — and THAT ack, the one that
    # leaves the row current, is also the one that refreshes the fingerprint
    # to the text it just put on Discord.
    _psql(_bind(full, pid, rev="2", mid="'100'", token=tok))
    assert _state(21) == "2|now at rev 2|100|posted", _state(21)

    # ...and that completing ack released the claim, so the re-claims below
    # are the caller taking it again rather than never having lost it.
    assert _claim(21).startswith("null|"), _claim(21)
    _hand_out(token=TOKEN_A)

    # Backwards: refused, or a late duplicate ack would re-open a delivered
    # correction and the bot would edit the same text again every tick.
    _psql(_bind(full, pid, rev="1", mid="'100'", token=tok))
    assert _state(21) == "2|now at rev 2|100|posted", (
        "posted_revision moved backwards: %s" % _state(21))

    # Past the row's own revision: refused. Nobody renders a future text, so
    # an ack claiming one is a bug in the caller, not an instruction.
    _psql(_bind(full, pid, rev="9", mid="'100'", token=tok))
    assert _state(21) == "2|now at rev 2|100|posted", (
        "an ack advanced the row past its own revision: %s" % _state(21))

    _states_at(API_MAIN, "ack_channel_post", "COMPARE-AND-SET, NOT COALESCE")


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_an_ack_releases_the_claim_when_and_only_when_the_row_is_current():
    """A row the bot finished with must not sit under its own lease: the next
    correction would wait out the claim before anyone could render it. A row
    the bot is still rendering must not be released either, which is the other
    half and the one round three got wrong."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _ack_sql()
    tok = "'%s'" % TOKEN_A

    # Current after the write -> released.
    _hand_out(revisions=False, token=TOKEN_A)
    _psql(_bind(full, _pid(9), rev="1", mid="'55'", token=tok))
    assert _claim(9).startswith("null|"), _claim(9)

    # Still behind after the write -> retained.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order, "
          "posted_at, message_id, posted_revision, revision) "
          "VALUES ('999', 'behind', 22, now(), '66', 1, 3);")
    _hand_out(token=TOKEN_A)
    _psql(_bind(full, _pid(22), rev="2", mid="'66'", token=tok))
    assert _claim(22).startswith(TOKEN_A), (
        "the claim was released while the row was still behind: %s" % _claim(22))


# ── The ack's authorization is a condition of the write, not a value ────────
#
# These two are the control for the method, and they are deliberately a pair:
# the first reads the deployed statement and says what shape it has, the second
# drives two real backends through the interleaving the shape exists for. The
# first alone would be a spelling check; the second alone would leave the next
# editor free to re-introduce a derived boolean anywhere the interleaving does
# not happen to reach.

# The two authorization terms, spelled as they must appear AGAINST THE ROW THE
# UPDATE IS WRITING. Written out here rather than lifted, because a test that
# re-derives the thing it checks is checking itself (#391); the counts below
# are what stops one of the copies drifting (#432).
_ACK_HOLDS_CLAIM = (
    "(CAST(:token AS uuid) IS NOT NULL AND p.claimed_token = "
    "CAST(:token AS uuid) AND p.claimed_at > NOW() - "
    "make_interval(secs => :lease))")
_ACK_LEGACY_CALLER = (
    "(CAST(:token AS uuid) IS NULL AND CAST(:rev AS INTEGER) IS NULL AND NOT "
    "CAST(:bind AS BOOLEAN) AND NOT CAST(:release AS BOOLEAN) AND "
    "p.handed_revisionless)")


def test_the_ack_decides_authorization_in_the_statement_that_writes():
    """No authorization value may be computed before the write and used by it.

    The defect this is the control for was not a wrong predicate: it was a
    RIGHT predicate, evaluated once into a CTE column and then consumed by the
    UPDATE beneath it. Under READ COMMITTED an UPDATE that meets a row another
    transaction has changed re-checks its own conditions against the new
    version — and a boolean already computed is not a condition, so it is not
    re-checked. A caller whose claim had lapsed was admitted by that frozen
    value and could clear the claim a second poller had taken.

    So the shape is asserted, not just the behaviour: the row is taken FOR NO
    KEY UPDATE before anything reads it; every authorization term appears
    against `p`, the row being written, at each of the sites that depends on
    it; nothing inside the UPDATE reads a column through the locking CTE; and
    no derived authorization column exists to be read. The occurrence counts
    are exact, so a copy that drifts to a different spelling reds here rather
    than becoming a second rule nobody compares (#432).

    test_an_ack_cannot_clear_a_claim_taken_while_it_was_in_flight is the other
    half: this one says the statement has the shape, that one says the shape
    does the work."""
    sql = re.sub(r"\s+", " ", _ack_sql()).strip()

    assert "FOR NO KEY UPDATE" in sql, (
        "the ack no longer locks the row before reading it, so everything it "
        "reads is a snapshot that a concurrent hand-out can invalidate before "
        "the write lands (#202/#208)")
    assert "FOR UPDATE" not in sql.replace("FOR NO KEY UPDATE", ""), (
        "the ack takes a stronger row lock than its own write needs; "
        "FOR UPDATE conflicts with the FOR KEY SHARE every foreign-key insert "
        "takes (#202)")

    for name in ("AS holds_claim", "AS legacy_caller", "AS reports_delivery",
                 "AS target", "target AS ("):
        assert name not in sql, (
            "the ack derives %r before the write. That is the round-four "
            "shape: a value, not a condition, and not re-checked when the "
            "write meets a row somebody else has changed" % name)

    assert sql.count(_ACK_HOLDS_CLAIM) == 6, (
        "the holds-claim term appears against the written row %d times, not "
        "the 6 sites that depend on it (message_id, posted_revision, "
        "adopt_fingerprint, claimed_token, claimed_at, and the WHERE)"
        % sql.count(_ACK_HOLDS_CLAIM))
    assert sql.count(_ACK_LEGACY_CALLER) == 8, (
        "the legacy-caller term appears against the written row %d times, not "
        "the 8 sites that depend on it (message_id, posted_revision, "
        "adopt_fingerprint, the two release arms twice each, and the WHERE)"
        % sql.count(_ACK_LEGACY_CALLER))

    # The WHERE admits three kinds and no more: the two authorized ones and
    # the delivery shape, which reads no column at all.
    where = sql.split("FROM locked k WHERE ")[1].split(" RETURNING ")[0]
    assert _ACK_HOLDS_CLAIM in where and _ACK_LEGACY_CALLER in where, (
        "the WHERE of the ack no longer carries both authorization terms, so "
        "admission is decided somewhere the write does not re-check")

    # Nothing in the write reads the locked CTE except the key it joins on.
    written = sql.split("), written AS (")[1].split(") SELECT k.id AS id")[0]
    refs = sorted(set(re.findall(r"k\.[a-z_]+", written)))
    assert refs == ["k.id"], (
        "the UPDATE reads %s from the locking CTE. The write is decided "
        "against the row it writes so that it stays right on its own: a "
        "column read through `locked` makes the lock the only thing standing "
        "between the write and a value read before it, which is the "
        "round-four shape the moment that lock is weakened" % refs)

    _states_at(API_MAIN, "ack_channel_post",
               "AUTHORIZATION IS DECIDED INSIDE THE STATEMENT THAT WRITES",
               "RELEASE, and the whole list of routes")


_RACE_MARKER = "ackrace"
_RACE_ROW = """
INSERT INTO pending_channel_posts (channel_id, content, sort_order,
                                   posted_at, message_id, posted_revision, revision)
VALUES ('907', 'the row two pollers want', 77, now(), '700', 1, 2);
"""


def _await_row_lock(marker, timeout=30.0):
    """Block until the marked backend holds its transaction's own lock.

    Waiting for the backend to be `active` is not enough here: it is active
    from the BEGIN onwards, and the interleaving this sets up needs the UPDATE
    to have RUN and not yet committed. A write holds an exclusive lock on its
    own transaction id for exactly that window, so that is what is waited for
    — the server's view of the state, never a sleep (#342). The poll's own
    query must not match the marker or the check answers itself, so the
    literal is split and re-joined by the server. Bounded (#361)."""
    head, tail = marker[:4], marker[4:]
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = _psql(
            "SELECT count(*) FROM pg_locks l "
            "  JOIN pg_stat_activity a ON a.pid = l.pid "
            " WHERE l.locktype = 'transactionid' AND l.mode = 'ExclusiveLock' "
            "   AND l.granted AND a.pid <> pg_backend_pid() "
            "   AND a.query LIKE '%%' || '%s' || '%s' || '%%';"
            % (head, tail)).stdout.strip()
        if n and int(n) >= 1:
            return
        time.sleep(0.2)
    raise AssertionError(
        "the %s transaction never took a row lock within %ss" % (marker, timeout))


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_an_ack_cannot_clear_a_claim_taken_while_it_was_in_flight():
    """Two backends, one row, and the ack arriving through the other's lock.

    THE INTERLEAVING, which is the whole test: poller A is handed the row and
    takes token A. Before A's ack lands, poller B claims the row — its lease
    had run out, or the hand-out re-took it — in a transaction it has not
    committed. A's ack then starts, meets the row through B's lock, and
    finishes after B commits. The question is what A's ack does with a claim
    that is no longer A's.

    It must record what an unauthorized caller may record — the delivery — and
    it must leave B's claim exactly where it found it. The round-four
    statement did not: it read the row at its own snapshot, where the claim was
    still A's, derived "authorized" there, and the UPDATE beneath consumed that
    value without re-checking it, so A cleared B's claim while B was rendering
    and a third poller became eligible for the same row.

    Nothing about this is provable from a single session, and reasoning about
    it on paper is how the shape got written twice. The elapsed time is
    asserted for the same reason: if A's statement did not WAIT, the
    interleaving did not happen and a green result would mean nothing (#342).

    THE STATEMENT IS BOUND BEFORE B STARTS, and only the ack itself is timed.
    Lifting it parses main.py, which takes seconds on a loaded seat. Round
    five found this test lifting it INSIDE the window: B committed while the
    parse ran, A's ack met a row that was already B's and refused correctly
    on any statement, and the elapsed time, which included the parse, still
    read as a wait. The round-four statement passed it. So the window now
    holds nothing but the ack, B is checked to be still open the moment the
    ack is sent, and the time measured is the ack's own."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    _psql("DELETE FROM pending_channel_posts;")
    _psql(_RACE_ROW)
    ack = _bind(_ack_sql(), _pid(77), rev="2", mid="'700'",
                token="'%s'" % TOKEN_A)

    assert _handed_orders(token=TOKEN_A) == ["77"], (
        "the fixture row was not handed to the first poller: %s" % _claim(77))

    holder = _psql_background(
        "BEGIN; UPDATE pending_channel_posts SET claimed_at = NOW(), "
        "claimed_token = '%s' WHERE sort_order = 77; "
        "SELECT pg_sleep(6); COMMIT;" % TOKEN_B, _RACE_MARKER)
    try:
        _await_row_lock(_RACE_MARKER)
        still_open = holder.poll() is None
        started = time.time()
        out = _psql(ack).stdout.strip()
        waited = time.time() - started
    finally:
        holder.wait(timeout=30)

    assert still_open, (
        "the other transaction had already finished when the ack was sent, "
        "so the ack never met the row through its lock and this run proves "
        "nothing about the interleaving")
    assert waited > 1.0, (
        "the ack did not wait for the other transaction (%.2fs), so it never "
        "met the row through another writer's lock and this run proves "
        "nothing about the interleaving" % waited)

    assert _claim(77).startswith(TOKEN_B), (
        "the ack of the poller whose claim had been taken released the claim "
        "the SECOND poller holds. That row is now free while somebody is "
        "rendering it, and a third poller can be handed it: %s" % _claim(77))

    assert out.endswith("|f"), (
        "the ack reported itself authorized against a claim it does not "
        "hold: %s" % out)

    # ...and the one thing it MAY record, it did: the delivery it reported.
    assert _state(77).endswith("|700|posted"), _state(77)
    assert _state(77).startswith("1|"), (
        "the refused ack advanced posted_revision, which only the claim "
        "holder may do: %s" % _state(77))


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_a_tokenless_release_is_refused_and_writes_nothing():
    """The pre-338 call is a post id and nothing else; a release is not it.

    legacy_caller authorizes the old bot by the PAIR — its call shape, and a
    row whose last hand-out was revisionless — because that bot cannot hold a
    claim. The shape used to be "no token, no revision, not a bind", which
    also admitted a tokenless RELEASE: a call that bot cannot make, since it
    predates the parameter. Admitted, that hand-back wrote the handed_*
    revision and fingerprint onto a row nothing had rendered and cleared the
    claim, so a never-delivered row read as rendered and dropped out of the
    revision-capable poll for good.

    It also kept the ack's WHERE from being safe to read on the statement's
    snapshot: a hand-back is not a delivery, so its admission rested on
    handed_revisionless alone, a column a concurrent revisionless hand-out can
    flip between the snapshot and the lock — and a row the snapshot refuses is
    never re-checked. Excluding the release puts the old bot's admission back
    behind the delivery term, which reads no column.

    So the row is handed to a revisionless poller, a tokenless release
    arrives, and nothing may move: not the delivery columns, not the claim,
    and the answer is a refusal. The last assertion is the consequence the
    defect had in the field: the row must still be in the poll that delivers
    it."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    _psql("DELETE FROM pending_channel_posts;")
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('908', 'a row an old bot was handed', 78);")

    assert _handed_orders(token=TOKEN_A, revisions=False) == ["78"], (
        "the fixture row was not handed to the revisionless poller: %s"
        % _claim(78))
    assert _handed_kind(78) == "t", (
        "the hand-out did not record a revisionless poller: %s" % _handed_kind(78))
    state, claim = _state(78), _claim(78)
    assert state == "null|null|null|unposted", state
    assert claim.startswith(TOKEN_A + "|1|"), claim

    out = _psql(_bind(_ack_sql(), _pid(78), release="true")).stdout.strip()

    assert out.endswith("|f"), (
        "a tokenless release was answered as authorized: %s" % out)
    assert _state(78) == state, (
        "a tokenless release wrote onto a row nothing rendered: %s -> %s"
        % (state, _state(78)))
    assert _claim(78) == claim, (
        "a tokenless release moved the claim: %s -> %s" % (claim, _claim(78)))
    assert _handed_orders(token=TOKEN_B, revisions=True, lease=0) == ["78"], (
        "the never-delivered row is no longer handed to the revision-capable "
        "poller, so nothing will ever deliver it: %s" % _state(78))


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_the_bind_only_ack_advances_nothing_but_the_id():
    """The whole reason a correction can survive a restart: the id becomes
    durable without the row being marked delivered. If this arm advanced
    posted_revision, the correction would be recorded as rendered before the
    edit had been attempted — and if it RELEASED the claim, another poller
    could be handed a row this one is about to edit."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _ack_sql()

    _psql("UPDATE pending_channel_posts SET revision = 2 WHERE sort_order = 1;")
    _hand_out(token=TOKEN_A)
    pid = _pid(1)
    before = _psql("SELECT revision || '|' || posted_revision || '|' || "
                   "posted_at::text FROM pending_channel_posts "
                   "WHERE sort_order = 1;").stdout.strip()
    _psql(_bind(full, pid, mid="'4242'", token="'%s'" % TOKEN_A, bind="true"))
    after = _psql("SELECT revision || '|' || posted_revision || '|' || "
                  "posted_at::text FROM pending_channel_posts "
                  "WHERE sort_order = 1;").stdout.strip()
    assert before == after, (
        "bind_only moved a delivery column: %s -> %s" % (before, after))
    assert _state(1) == "1|stale message one|4242|posted", _state(1)
    assert _claim(1).startswith(TOKEN_A), (
        "bind_only released the claim on a row that is mid-render: %s" % _claim(1))

    # A bind from a caller that does not hold the claim writes no id either.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order, "
          "posted_at, posted_revision, revision) "
          "VALUES ('999', 'someone else is on it', 23, now(), 1, 2);")
    _hand_out(token=TOKEN_A)
    _psql(_bind(full, _pid(23), mid="'7777'", token="'%s'" % TOKEN_B, bind="true"))
    assert _state(23) == "1|null|null|posted", (
        "a non-claimant bound a message id: %s" % _state(23))

    # ...and a bind on a row that was NEVER DELIVERED leaves it undelivered.
    # Every row above already carried posted_at, so a statement that stamped
    # it on a bind was invisible to all of them — the mutation that does
    # exactly that survived this test until this block existed. posted_at is
    # what keeps the send path away from a delivered row, so stamping it here
    # would retire a message nobody has sent.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'not sent yet', 24);")
    _hand_out(revisions=False, token=TOKEN_A)
    _psql(_bind(full, _pid(24), mid="'8888'", token="'%s'" % TOKEN_A, bind="true"))
    assert _state(24) == "null|null|8888|unposted", (
        "bind_only marked an undelivered row delivered: %s" % _state(24))
    # ...and it is still the SEND path's, which is the consequence that
    # matters: a row that left it would sit pending for good with no message.
    assert "24" in _handed_orders(TOKEN_B, revisions=False, lease=0), (
        "a bound but unsent row is no longer offered to the send path")


# ── 6. The i18n pair: three re-keyed articles, four locales each ─────────────

MIG_340 = os.path.join(REPO, "backend", "sql", "340_i18n_keys_item11.sql")
MIG_341 = os.path.join(REPO, "backend", "sql", "341_seed_machine_translations_item11.sql")
# The three articles item 11 corrected, each identified by a phrase that only
# the corrected text contains.
REKEYED = {
    "ranked 1v1 article": "a warning at 15 seconds",
    "economy article": "Bodycount, Sync Champion",
    "cosmetics article": "or up to 16 numbered PNG frames",
}

# The item-11 corrections, as before -> after. These are the ONLY differences
# between the article 251 registered and the one 340 registers in its place, so
# they are what makes "this successor replaces that predecessor" a checkable
# claim rather than an assertion about two opaque 16-hex ids. The same three
# edits are what the client lane owes plugin/InfoLibrary.cs
# (docs/faq-refresh-client-contract.md); this file cannot see that lane, so
# it holds the migration to them instead.
# The economy article's gold-ladder steps (the tier lines), the table the
# ladder test classifies as applied or owed.
ECONOMY_LADDER = [
    ("Hostile Takeover, Bodycount.",
     "Hostile Takeover, Bodycount, Sync Champion, Async Champion."),
    ("Heartbreak, Dragoman.",
     "Heartbreak, Dragoman, Sync Finalist, Async Finalist.")]
# Merged hold 3 (Codex client merged round 1 LOW 4): the client lane replaced
# the shutout sentence after 340 was derived, so the economy successor is
# re-derived from the CURRENT client English (340 and 341 are applied nowhere:
# the read-only query in the hold-3 notes found none of the three keys on the
# primary, so both are edited in place). That replacement is the third edit.
ECONOMY_SENTENCE = [
    ("one 5-0 win in a 5-player lobby pays",
     "one 5-0 win with 5 players finishing pays")]
REKEY_EDITS = {
    "ranked 1v1 article": [
        ("a warning at 25 seconds", "a warning at 15 seconds")],
    "economy article": ECONOMY_LADDER + ECONOMY_SENTENCE,
    "cosmetics article": [
        ("a PNG or animated frames",
         "one 512x512 PNG, a GIF, or up to 16 numbered PNG frames")],
}


# plugin/I18nCatalogues.cs is NOT read from here any more. Round four
# restored every plugin/ file and tools/i18n_source.json to the branch
# base: the client half of this re-key is the client lane's step, listed
# for it in docs/faq-refresh-client-contract.md. The helpers that
# parsed the catalogue went with them rather than being left as a reader
# trap (#432) — what this file can still hold the migration to is below.


def test_the_client_keys_340_registers_are_derived_from_the_text_it_carries():
    """The re-key, checked against the only half of it this branch owns.

    The catalogue key IS the English source, so changing one sentence orphans
    that article in every locale unless the key moves with it — the #578
    failure, where an English-only pass shipped English to four locales with
    every gate green, and #583's point that the DLL-bundled catalogue is the
    artifact a player renders.

    THE CLIENT HALF IS NOT IN THIS BRANCH. plugin/InfoLibrary.cs,
    plugin/I18nSourceKeys.g.cs, plugin/I18nCatalogues.cs and their extraction
    artifact tools/i18n_source.json are the client lane's, and round four
    restored all four to the branch base; the exact edits and the catalogue
    entries they need are written out in
    docs/faq-refresh-client-contract.md. So there is nothing in this tree
    to assert the four locale entries against, and a test that asserted them
    against the tree as it stands would be asserting the client lane HAS NOT
    done its half — a check that passes by pinning the gap (#342).

    What this branch does own is the derivation: the key id is
    sha1("client\\0" + source)[:16], 340 carries the corrected English inline,
    so each id it registers must be computable from the body beside it. That
    ties the migration to its own text with no external artifact, and it fails
    if either the id or the body is edited alone — which is the drift that
    would silently seed twelve translations against keys no client ever asks
    for."""
    sql = _read(MIG_340)
    rows = re.findall(r"\('([0-9a-f]{16})', 'client', \$k340\$(.*?)\$k340\$",
                      sql, re.S)
    assert len(rows) == 3, (
        "340 no longer registers exactly three client keys: %d found"
        % len(rows))
    problems = []
    for key_id, source in rows:
        derived = _client_key_id(source)
        if derived != key_id:
            problems.append(
                "340 registers %s for a body that hashes to %s — the id and "
                "the English beside it were edited apart" % (key_id, derived))
    assert not problems, "\n".join(problems)

    # ...and the three bodies are the CORRECTED articles, not the predecessors.
    for label, probe in REKEYED.items():
        assert sum(probe in body for _, body in rows) == 1, (
            "%s: 340 does not carry exactly one body containing %r"
            % (label, probe))


def test_i18n_pair_shape():
    """340 registers the three keys, 341 seeds 3 x 4 = 12 proposal pairs, and
    both carry their own transaction (#340)."""
    keys_sql = _read(MIG_340)
    seed_sql = _read(MIG_341)
    assert "v_expected INT := 3;" in keys_sql, (
        "340's post-check no longer expects three keys")
    assert seed_sql.count("'es',") == 3 and seed_sql.count("'sv',") == 3, (
        "341 no longer seeds one row per locale per key")
    assert "of 12 seed pairs did not land" in seed_sql
    # What each file SAYS about the client half, pinned. Both headers used to
    # state that plugin/I18nCatalogues.cs had been re-keyed in the same pass;
    # round four restored every plugin/ file to the branch base, which made
    # both sentences false, and nothing in the suite could tell. This is the
    # SQL twin of _states_at — scoped to the file whose claim it is.
    assert "THIS FILE AND 341 ARE THE PORTAL HALF" in keys_sql, (
        "340's header no longer says the client half ships separately, so it "
        "is back to describing a re-key this branch does not carry")
    assert "are owed to plugin/I18nCatalogues.cs" in seed_sql, (
        "341's header no longer says the catalogue entries are OWED rather "
        "than shipped with it")
    # ...and WHAT the twelve strings are. The header used to call each target
    # "the PREVIOUS approved article with only the corrected sentence
    # rewritten" — a claim no state this pair can run against satisfies: 340
    # goes first and REFUSES if a predecessor key carries an approved entry,
    # so there is never an approved predecessor left to carry forward. A
    # reviewer who believes it approves twelve unreviewed machine strings as
    # human work somebody already signed off.
    assert "ALL TWELVE ARE UNREVIEWED MACHINE OUTPUT" in seed_sql, (
        "341's header no longer says its targets are unreviewed machine "
        "output, so a reviewer can read them as carried-forward human work")
    assert "PREVIOUS approved article" not in seed_sql, (
        "341's header claims its targets preserve a previous approved "
        "translation, which 340's own guard refuses to run alongside")
    # The guard that makes the sentence above true rather than merely stated.
    # If 340 stopped refusing, an approved predecessor could survive into this
    # state and 341's claim would need re-deciding, not re-wording.
    assert re.search(r"IF v_approved <> 0 THEN\s*\n\s*RAISE EXCEPTION",
                     keys_sql), (
        "340 no longer refuses when a predecessor carries approved work, "
        "which is what 341's header rests on")
    for name, sql in (("340", keys_sql), ("341", seed_sql)):
        assert sql.count("BEGIN;") == 1 and sql.rstrip().endswith("COMMIT;"), (
            "%s needs its own explicit transaction (#340)" % name)
    # The key ids in 341 must be the ones 340 registers, or the seed lands
    # against nothing and only the RAISE tells anyone.
    ids_340 = set(re.findall(r"^  \('([0-9a-f]{16})', 'client',", keys_sql, re.M))
    ids_341 = set(re.findall(r"\('([0-9a-f]{16})', '(?:es|ru|uk|sv)',", seed_sql))
    assert len(ids_340) == 3, ids_340
    assert ids_341 == ids_340, "341 seeds %s, 340 registers %s" % (ids_341, ids_340)


MIG_251 = os.path.join(REPO, "backend", "sql", "251_i18n_keys_info_library.sql")
_LADDER = re.compile(r"- <color=#7FD4FF>\d+g</color> - (.+)")


def _achievement_names():
    """key -> shipped display label, from ACHIEVEMENT_DEFS in main.py."""
    body = _read("backend/api/main.py")
    start = body.index("ACHIEVEMENT_DEFS")
    return dict(re.findall(r'"([a-z0-9_]+)":\s*\{"name":\s*"([^"]+)"',
                           body[start:start + 16000]))


def test_the_payout_ladder_names_only_shipped_achievement_labels():
    """The gold-tier article lists achievements by their LABEL, and those
    labels are people-facing product strings.

    340 re-keys that article, which means the whole English source is
    re-stated by the migration whether or not a given line changed — so "did
    this invent a name" cannot be answered by reading the diff. Answer it
    mechanically: every label on every tier line must be a name
    ACHIEVEMENT_DEFS already ships, so the migration can only repeat strings
    the product already renders in-game. And 341's locale proposals may carry
    no shipped label that the English source does not, so a translation
    cannot introduce one either.

    Labels are looked up through the code rather than written here, which is
    also why this test states none of them."""
    shipped = set(_achievement_names().values())
    assert len(shipped) >= 40, "ACHIEVEMENT_DEFS parsed as %d names" % len(shipped)

    keys_sql = _read(MIG_340)
    tiers = _LADDER.findall(keys_sql)
    assert len(tiers) >= 3, "340 no longer carries the gold-tier ladder: %s" % tiers
    unknown = []
    for line in tiers:
        for item in line.split(","):
            item = re.sub(r"\s*\([^)]*\)\s*$", "", item.strip().rstrip("."))
            if item and item not in shipped:
                unknown.append(item)
    assert not unknown, (
        "340's gold-tier ladder names %s, which ACHIEVEMENT_DEFS does not "
        "ship — the migration is authoring product nouns rather than "
        "repeating them" % sorted(set(unknown)))

    in_340 = {n for n in shipped if n in keys_sql}
    in_341 = {n for n in shipped if n in _read(MIG_341)}
    assert in_341 <= in_340, (
        "341 seeds locale rows naming %s, which the English source it "
        "translates does not contain" % sorted(in_341 - in_340))


def _client_key_id(source):
    """The client namespace's key derivation, from tools/i18n_sync_keys.py."""
    import hashlib
    return hashlib.sha1(("client\0" + source).encode("utf-8")).hexdigest()[:16]


def _predecessors_340():
    """The ids 340's retire statement names, read from the statement itself."""
    sql = _read(MIG_340)
    start = sql.index("UPDATE i18n_keys")
    return set(re.findall(r"'([0-9a-f]{16})'", sql[start:sql.index(";", start)]))


def test_340_retires_the_keys_its_successors_replace():
    """A re-key that only registers the successors leaves the predecessors
    live: three articles' worth of English that no client can render, offered
    to translators in four locales each. That is the state 251 left behind and
    255 had to clean up, and 340 says in its own header that it completes the
    re-key — so the claim is checked against the statements below it.

    Each retired id is verified to BE the key of a source 251 registered (the
    id is recomputed from that text, not trusted), and that source is verified
    to be gone from the extracted catalogue, which is what makes retiring it
    correct rather than merely asserted. The successors must conversely still
    be extracted, so a mix-up that retired the live keys fails here."""
    sql = _read(MIG_340)
    # The retire UPDATE alone — the post-check below it lists the successors
    # too, and a slice that ran to the end of the file would count those as
    # retired and pass whatever 340 did.
    retired = _predecessors_340()
    assert len(retired) == 3, (
        "expected 3 retired predecessor ids in 340, found %s" % sorted(retired))

    old_sources = dict(re.findall(r"\('([0-9a-f]{16})', 'client', \$k251\$(.*?)\$k251\$",
                                  _read(MIG_251), re.S))
    for kid in sorted(retired):
        assert kid in old_sources, (
            "340 retires %s, which 251 never registered — nobody can say what "
            "text that id is" % kid)
        assert _client_key_id(old_sources[kid]) == kid, (
            "251's source for %s does not hash to it; the id is not that "
            "article's key" % kid)

    successors = dict(re.findall(
        r"^  \('([0-9a-f]{16})', 'client', \$k340\$(.*?)\$k340\$", sql, re.M | re.S))
    assert not (set(successors) & retired), "340 retires a key it just registered"
    for kid, source in successors.items():
        assert _client_key_id(source) == kid, (
            "340's own key id %s does not hash from the source beside it" % kid)

    # EVERY RETIREMENT IS MATCHED TO THE SUCCESSOR THAT REPLACES IT, and the
    # match is the item-11 correction itself. Round three checked this through
    # tools/i18n_source.json — "the old English is no longer extracted, the new
    # one is" — which asks the CLIENT lane's artifact a question this branch no
    # longer has any business asking: it restored all four client files, so
    # that check would now be asserting the client lane has not done its half
    # (#342). Applying the edits to the predecessor and requiring the
    # successor, one-to-one both ways, is self-contained and strictly narrower:
    # a retirement of an article nobody replaced, or a successor that corrects
    # something else as well, fails here.
    pairs = {}
    for label, edits in REKEY_EDITS.items():
        matched = None
        for kid in sorted(retired):
            want = old_sources[kid]
            # A predecessor this label does not describe is SKIPPED, not
            # failed: the three labels each speak for one article, so two of
            # the three ids carry none of an edit's before-text by design. The
            # power to catch a wrong correction table sits in "assert matched"
            # below — if no predecessor carries the text, nothing matches.
            if not all(before in want for before, _ in edits):
                continue
            for before, after in edits:
                want = want.replace(before, after)
            hit = [s for s, body in successors.items() if body == want]
            if hit:
                assert matched is None, (
                    "%s: two predecessors produce one successor" % label)
                matched = (kid, hit[0])
        assert matched, (
            "%s: no retired predecessor carries %s and becomes a 340 successor "
            "by applying it — either the retirement names the wrong article, "
            "the correction table describes text 251 never had, or the "
            "successor changes more than item 11's correction"
            % (label, [b for b, _ in edits]))
        pairs[matched[0]] = matched[1]
    assert set(pairs) == retired, (
        "340 retires %s but only %s are replaced by one of its successors"
        % (sorted(retired), sorted(pairs)))
    assert set(pairs.values()) == set(successors), (
        "340 registers %s but only %s replace a retired predecessor"
        % (sorted(successors), sorted(set(pairs.values()))))

    # The header's claim about what a client renders during the window, pinned
    # with the behaviour so a prose-only reversion reds too.
    assert "bundled" in sql, (
        "340 no longer says what an un-upgraded client renders for a retired "
        "key while the client lane's half is outstanding")

    assert "SET retired_at = NOW()" in sql and "AND retired_at IS NULL" in sql, (
        "the retire UPDATE is not predicated on the state it leaves, so a "
        "re-run would rewrite retired_at")
    assert "state = 'approved'" in sql, (
        "340 retires keys without 255's refusal on translator-approved work")
    # The refusal has to be ONE operation with the retirement, and it has to
    # be re-asked afterwards. The executable proof that the lock works is
    # test_340_refuses_a_review_that_approves_during_the_retirement; these two
    # keep the structure from being quietly dismantled on a box with no
    # Postgres, where that test only skips.
    assert "FOR NO KEY UPDATE" in sql, (
        "340 reads the approved count without locking the rows a concurrent "
        "review would write, so the count and the retirement are two "
        "snapshots (#208)")
    post = sql[sql.index("-- ── 3. Post-check"):]
    assert "v_old_approved" in post and "IF v_old_approved <> 0 THEN" in post, (
        "340's post-check no longer re-reads the approved count AFTER the "
        "retirement, so it can only confirm what the migration itself wrote "
        "(#342: a check that cannot fail)")
    # The conflict arm must not rewrite a row it does not change.
    arm = sql[sql.index("ON CONFLICT (key_id)"):]
    assert "IS DISTINCT FROM EXCLUDED" in arm, (
        "340's conflict arm advances updated_at unconditionally, so every "
        "re-run reports work it did not do")


# ── 6b. Merged hold 3: the economy successor IS the client's current English ──
#
# On the merged v1.41.0 client branch both halves are present, so the server's
# economy successor (340) and its four seeds (341) are held to what a player
# renders: the Rewards article of plugin/InfoLibrary.cs and its four bundled
# values in plugin/I18nCatalogues.cs, byte for byte (Codex client merged round
# 1 LOW 4: translator work must attach to a key a current client renders).

_CS_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'", "0": "\0"}


def _cs_verbatim_after(src, marker):
    i = src.index(marker) + len(marker)
    out = []
    while True:
        c = src[i]
        if c == '"':
            if src[i + 1] == '"':
                out.append('"')
                i += 2
                continue
            return "".join(out)
        out.append(c)
        i += 1


def _unescape(body, quote_doubling):
    """A C# regular string body (quote_doubling False) or a PostgreSQL E''
    body (True: '' is one quote), backslash escapes decoded."""
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if quote_doubling and c == "'" and body[i + 1:i + 2] == "'":
            out.append("'")
            i += 2
        elif c == "\\":
            n = body[i + 1]
            if n == "u":
                out.append(chr(int(body[i + 2:i + 6], 16)))
                i += 6
            else:
                assert n in _CS_ESCAPES, "unknown escape \\%s" % n
                out.append(_CS_ESCAPES[n])
                i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _economy_halves(info_src, cat_src, sql340, sql341):
    """(client English, {locale: catalogue value}, (340 id, hash, body),
    {locale: (341 id, hash, target)}) for the economy article."""
    english = _cs_verbatim_after(info_src, 'private static string Rewards => I18n.Tr(@"')
    starts = sorted((cat_src.index("Dictionary<string, string> %s = new" % L), L) for L in ("ES", "RU", "UK", "SV"))
    entry = re.compile(r'^\s*\["((?:[^"\\]|\\.)*)"\]\s*=\s*"((?:[^"\\]|\\.)*)",?\s*$', re.M)
    cat = {}
    for n, (a, L) in enumerate(starts):
        b = starts[n + 1][0] if n + 1 < len(starts) else len(cat_src)
        vals = [_unescape(m.group(2), False) for m in entry.finditer(cat_src, a, b)
                if _unescape(m.group(1), False) == english]
        assert len(vals) <= 1, "two %s catalogue entries for the economy English" % L
        if vals:
            cat[L.lower()] = vals[0]
    rows = [r for r in re.findall(r"\('([0-9a-f]{16})', 'client', \$k340\$(.*?)\$k340\$, '([0-9a-f]{40})'",
                                  sql340, re.S) if REKEYED["economy article"] in r[1]]
    assert len(rows) == 1, "340 carries %d economy bodies" % len(rows)
    seeds = {}
    for kid, lang, sh, tgt in re.findall(
            r"\('([0-9a-f]{16})', '(es|ru|uk|sv)', '([0-9a-f]{40})', E'((?:[^'\\]|\\.|'')*)'\)", sql341):
        if kid == rows[0][0]:
            seeds[lang] = (kid, sh, _unescape(tgt, True))
    return english, cat, (rows[0][0], rows[0][2], rows[0][1]), seeds


def _economy_equal(halves):
    english, cat, (kid, sh, body), seeds = halves
    return (body == english and kid == _client_key_id(english)
            and sh == hashlib.sha1(english.encode("utf-8")).hexdigest()
            and sorted(cat) == sorted(seeds) == ["es", "ru", "sv", "uk"]
            and all(seeds[L] == (kid, sh, cat[L]) for L in cat))


def test_hold3_the_economy_successor_is_the_client_english_and_its_seeds_the_catalogues():
    info, cat = _read(_INFO_LIBRARY), _read(os.path.join(REPO, "plugin", "I18nCatalogues.cs"))
    sql340, sql341 = _read(MIG_340), _read(MIG_341)
    halves = _economy_halves(info, cat, sql340, sql341)
    english, catv, (kid, sh, body), seeds = halves
    assert ECONOMY_SENTENCE[0][1] in english and ECONOMY_SENTENCE[0][0] not in english, (
        "the client's economy article no longer carries the replacement shutout sentence")
    assert body == english, "340's economy successor is not the client's current English"
    assert kid == _client_key_id(english), "340's economy key is not the client English's key"
    assert sorted(catv) == ["es", "ru", "sv", "uk"], "the bundled catalogues lack a locale: %s" % sorted(catv)
    for L in ("es", "ru", "uk", "sv"):
        assert L in seeds, "341 seeds no %s row for the economy key %s" % (L, kid)
        assert seeds[L][:2] == (kid, sh), "341's %s row names another key or hash" % L
        assert seeds[L][2] == catv[L], "341's %s seed is not the bundled %s value byte for byte" % (L, L)
    assert _economy_equal(halves)
    # NEGATIVE CONTROLS: the round-1 state (340 and 341 derived from the
    # predecessor sentence) fails, and so does one locale's seed alone reverted.
    before, after = ECONOMY_SENTENCE[0]
    old340 = sql340.replace(after, before)
    old340 = old340.replace(kid, _client_key_id(english.replace(after, before)))
    assert not _economy_equal(_economy_halves(info, cat, old340, sql341)), "the predecessor sentence passes"
    sv_new = "en 5-0-vinst med 5 spelare som spelar klart betalar"
    assert sql341.count(sv_new) == 1
    reverted = sql341.replace(sv_new, "en 5-0-vinst i en 5-spelarlobby betalar")
    assert not _economy_equal(_economy_halves(info, cat, sql340, reverted)), "a reverted Swedish seed passes"


_I18N_SCHEMA = [
    os.path.join(REPO, "backend", "sql", "181_i18n_infrastructure.sql"),
    os.path.join(REPO, "backend", "sql", "212_i18n_key_context.sql"),
]


_I18N_SNAPSHOT = (
    "SELECT md5(string_agg(k.key_id || '|' || k.source_hash || '|' || "
    "           COALESCE(k.retired_at::text,'-') || '|' || k.updated_at::text, "
    "           ',' ORDER BY k.key_id)) FROM i18n_keys k;")
_PROPOSAL_SNAPSHOT = (
    "SELECT md5(string_agg(p.key_id || '|' || p.language_code || '|' || "
    "           p.status, ',' ORDER BY p.key_id, p.language_code)) "
    "FROM i18n_proposals p;")


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_340_341_apply_twice():
    """Run both halves for real, in order, twice. 341 RAISEs when its keys are
    not present, so applying it against a database that has 340 is also the
    proof that the two files agree on every key_id.

    "Applies twice" is not enough on its own: an INSERT ... ON CONFLICT DO
    UPDATE re-runs happily while rewriting every row it touches, and a table
    whose updated_at advances on each deploy reports work that did not happen
    and destroys the column's meaning for anyone reading it afterwards. So the
    second pass is held to CHANGING NOTHING — the state before it and after it
    is hashed and compared, retired_at and updated_at included.

    The three predecessor keys are SEEDED first, with a pending machine
    proposal on one of them. Against an empty table 340's retire half has
    nothing to retire and its post-check passes vacuously, which is the shape
    of a check that cannot fail (#342); with the rows present, retiring them
    is something the run has to actually do."""
    _psql("DROP TABLE IF EXISTS i18n_proposals, i18n_entries, i18n_keys CASCADE;")
    for path in _I18N_SCHEMA:
        _psql_file(path)

    pred = sorted(_predecessors_340())
    assert len(pred) == 3, pred
    _psql("INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, "
          "sensitive, context, updated_at) VALUES "
          + ", ".join("('%s', 'client', '', 'deadbeef', TRUE, 'x', NOW())" % k
                      for k in pred) + ";")
    _psql("INSERT INTO i18n_proposals (key_id, language_code, source_hash, "
          "proposed_target, proposer_steam_id, status) VALUES "
          "('%s', 'es', 'deadbeef', 'stale machine draft', 'claude-mt', "
          "'pending');" % pred[0])

    _psql_file(MIG_340)
    _psql_file(MIG_341)

    assert _psql(
        "SELECT count(*) FROM i18n_keys WHERE retired_at IS NOT NULL "
        "AND key_id IN (%s);" % ", ".join("'%s'" % k for k in pred)
    ).stdout.strip() == "3", "340 left a predecessor key live"
    assert _psql(
        "SELECT status FROM i18n_proposals WHERE key_id = '%s' "
        "AND language_code = 'es';" % pred[0]
    ).stdout.strip() == "superseded", (
        "a predecessor's pending proposal still offers translators work on "
        "text no client renders")

    before_keys = _psql(_I18N_SNAPSHOT).stdout.strip()
    before_props = _psql(_PROPOSAL_SNAPSHOT).stdout.strip()
    assert before_keys and before_props, "the snapshot read nothing to compare"

    _psql_file(MIG_340)
    _psql_file(MIG_341)

    assert _psql(_I18N_SNAPSHOT).stdout.strip() == before_keys, (
        "the second apply of 340 rewrote i18n_keys — an unchanged row must "
        "not be touched (updated_at / retired_at moved)")
    assert _psql(_PROPOSAL_SNAPSHOT).stdout.strip() == before_props, (
        "the second apply of 341 rewrote i18n_proposals")

    live = _psql(
        "SELECT count(*) FROM i18n_keys "
        "WHERE namespace = 'client' AND retired_at IS NULL;").stdout.strip()
    assert live == "3", live
    pairs = _psql(
        "SELECT count(*) FROM i18n_proposals "
        "WHERE proposer_steam_id = 'claude-mt' AND status = 'pending';").stdout.strip()
    assert pairs == "12", (
        "expected 12 pending seed pairs after two applies, got %s — the second "
        "apply duplicated them" % pairs)
    langs = _psql(
        "SELECT string_agg(DISTINCT language_code, ',' ORDER BY language_code) "
        "FROM i18n_proposals;").stdout.strip()
    assert langs == "es,ru,sv,uk", langs


def _fresh_i18n_schema():
    _psql("DROP TABLE IF EXISTS i18n_proposals, i18n_entries, i18n_keys CASCADE;")
    for path in _I18N_SCHEMA:
        _psql_file(path)


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_341_before_340_raises_and_rolls_back():
    """The deploy order, EXECUTED in the wrong order.

    "341 RAISEs when its keys are missing" was asserted by reading the file.
    A wrong-order apply is a thing a deploy can actually do, and the only
    acceptable outcome is a loud failure that leaves the database exactly as
    it was — not a partial seed against keys that do not exist yet."""
    _fresh_i18n_schema()
    proc = _psql_file(MIG_341, expect_ok=False)
    assert proc.returncode != 0, (
        "341 applied against a database without 340's keys and reported "
        "success:\n%s" % (proc.stdout or proc.stderr))
    assert _psql("SELECT count(*) FROM i18n_keys;").stdout.strip() == "0"
    assert _psql("SELECT count(*) FROM i18n_proposals;").stdout.strip() == "0", (
        "341 left proposals behind after failing — its transaction did not "
        "roll back (#340: psql -f autocommits without an explicit BEGIN)")
    # ...and the right order still works from that same state, so the failure
    # is not a state nobody can recover from.
    _psql_file(MIG_340)
    _psql_file(MIG_341)
    assert _psql("SELECT count(*) FROM i18n_proposals "
                 "WHERE status = 'pending';").stdout.strip() == "12"


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_340_refuses_a_review_that_approves_during_the_retirement():
    """The retirement and the count that justifies it are ONE operation.

    255's refusal — never silently retire translator-approved work — was a
    COUNT followed by an UPDATE on a second snapshot. /i18n/review/{id} can
    approve in the gap, and both the refusal and the post-check then look at a
    state that no longer holds: the migration retires the key and supersedes
    the proposals of work a reviewer had just accepted, and reports success.

    This runs the real interleaving. A second session takes the same
    FOR NO KEY UPDATE on the same key rows that the review endpoint takes
    first, inserts an approved entry, and waits until 340 is demonstrably
    blocked behind it before committing. 340 must then see the approval, RAISE
    and leave the database untouched — successors included, because the whole
    file is one transaction."""
    _fresh_i18n_schema()
    pred = sorted(_predecessors_340())
    _psql("INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, "
          "sensitive, context, updated_at) VALUES "
          + ", ".join("('%s', 'client', '', 'deadbeef', TRUE, 'x', NOW())" % k
                      for k in pred) + ";")

    ids = ", ".join("'%s'" % k for k in pred)
    # The reviewer's shape: lock the key row first (main.py's stated lock
    # order), write the approval, and only release once somebody is waiting.
    # The wait is capped — never an unbounded loop (#361) — and its failure
    # mode is to commit anyway, which makes the test red rather than hang.
    reviewer = _psql_background(
        "BEGIN;"
        " SELECT 1 FROM i18n_keys WHERE key_id IN (%s) ORDER BY key_id"
        "   FOR NO KEY UPDATE;"
        " INSERT INTO i18n_entries (key_id, language_code, target, state,"
        "        updated_at) VALUES ('%s', 'es', 'approved work', 'approved', NOW());"
        " DO $w$ DECLARE i INT := 0; BEGIN"
        "   WHILE i < 75 AND NOT EXISTS ("
        "         SELECT 1 FROM pg_stat_activity"
        "          WHERE pid <> pg_backend_pid() AND wait_event_type = 'Lock')"
        "   LOOP PERFORM pg_sleep(0.2); i := i + 1; END LOOP;"
        " END $w$;"
        " COMMIT;" % (ids, pred[0]),
        marker="reviewhold")
    try:
        _await_session("reviewhold")
        proc = _psql_file(MIG_340, expect_ok=False)
    finally:
        reviewer.wait(timeout=40)

    said = proc.stderr + proc.stdout
    assert proc.returncode != 0, (
        "340 retired keys a reviewer approved during the run, and reported "
        "success:\n%s" % (proc.stdout or proc.stderr))
    # WHICH refusal fired says whether the lock did its job. Under the lock
    # the migration waits, then reads the count and declines BEFORE writing
    # anything — section 2's message. Without it the count is a stale snapshot
    # (the approval is still uncommitted), section 2 passes, the writes happen
    # and only the post-check catches it — a different message, and a
    # migration that did work it had no right to do before finding out. Both
    # roll back; only one of them never started.
    assert "investigate first" in said, (
        "340 did not refuse at the count — it got as far as the post-check, "
        "so the count and the retirement are still two snapshots:\n%s" % said)
    assert _psql("SELECT count(*) FROM i18n_keys "
                 "WHERE retired_at IS NOT NULL;").stdout.strip() == "0", (
        "340 failed but left a predecessor retired — the file is not one "
        "transaction")
    assert _psql("SELECT count(*) FROM i18n_keys;").stdout.strip() == "3", (
        "340 failed but registered its successors anyway")


# ── 7. The bot's correction path, EXECUTED ──────────────────────────────────
#
# discord_bot.py cannot be imported in a test process (it builds the bot at
# import), so the loop is lifted out of its AST and run against fakes — the
# technique test_mail_bot.py established for this same function. That file
# covers the fire-once half; this covers the half migration 338 added, where
# the only failure worth preventing is a correction that appears as a NEW
# message under the text it was meant to replace.

import ast          # noqa: E402  (kept beside the harness it belongs to)
import asyncio      # noqa: E402
import copy         # noqa: E402
import types        # noqa: E402

_BOT_SRC = os.path.join(REPO, "backend", "discord_bot.py")
_WANT_FUNC = {"_modcase_parse", "poll_channel_posts", "_channel_post_ack_params",
              "_adopt_channel_post_message", "_release_channel_post_claim"}
# _CHANNEL_POST_MAX_RENDERS is LIFTED, never re-declared here: it is the cap
# both render paths are bound by, so a test that supplied its own number would
# be exercising a bot whose cap is not the deployed one (#391).
_WANT_ASSIGN = {"MODCASE_MARKER", "_channel_post_sent",
                "_CHANNEL_POST_MAX_RENDERS"}


class _Forbidden(Exception):
    pass


class _NotFound(Exception):
    pass


class _AllowedMentions:
    def __init__(self, **kw):
        self.kw = kw

    @classmethod
    def none(cls):
        return cls(none=True)


_FAKE_DISCORD = types.SimpleNamespace(
    AllowedMentions=_AllowedMentions, Forbidden=_Forbidden, NotFound=_NotFound,
    ui=types.SimpleNamespace(View=object, Button=object),
    ButtonStyle=types.SimpleNamespace(secondary="s", primary="p", danger="d", success="ok"))


class _Msg:
    def __init__(self, mid, content, author_id, trace=None):
        self.id, self.content, self.edits = mid, content, []
        self.author = types.SimpleNamespace(id=author_id)
        # Shared with the fake api so a test can assert the ORDER of a write
        # to Discord against the order of a write to the database.
        self.trace = trace if trace is not None else []

    async def edit(self, **kw):
        self.edits.append(kw)
        self.trace.append(("edit", self.id))
        self.content = kw.get("content", self.content)


class _Channel:
    """Holds the messages a channel already contains, in post order."""

    BOT_ID = 7

    def __init__(self, cid, existing=(), history_forbidden=False, trace=None):
        self.id = cid
        self.trace = trace if trace is not None else []
        self.messages = list(existing)
        for m in self.messages:
            m.trace = self.trace
        self.sent = []
        self.history_forbidden = history_forbidden
        self.scans = 0

    async def send(self, content, **kw):
        m = _Msg(9000 + len(self.messages), content, self.BOT_ID, trace=self.trace)
        self.messages.append(m)
        self.sent.append(m)
        self.trace.append(("send", m.id))
        return m

    async def fetch_message(self, mid):
        for m in self.messages:
            if m.id == int(mid):
                return m
        raise _NotFound()

    def history(self, limit=100, oldest_first=False):
        self.scans += 1
        forbidden = self.history_forbidden
        msgs = list(self.messages if oldest_first else reversed(self.messages))[:limit]

        class _It:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if forbidden:
                    raise _Forbidden()
                if not msgs:
                    raise StopAsyncIteration
                return msgs.pop(0)
        return _It()


class _Bot:
    def __init__(self, channels):
        self.channels = channels
        self.user = types.SimpleNamespace(id=_Channel.BOT_ID)

    def get_channel(self, cid):
        return self.channels.get(cid)

    async def fetch_channel(self, cid):
        return self.channels.get(cid)


class _Api:
    def __init__(self, posts, ack_ok=True, trace=None, fail_full_ack=False,
                 ack_script=()):
        self.posts, self.calls, self.ack_ok = list(posts), [], ack_ok
        self.trace = trace if trace is not None else []
        # The crash this bus has to survive: the id-binding ack commits and
        # the revision ack does not.
        self.fail_full_ack = fail_full_ack
        # Answers for the revision acks, in order, before the default. This is
        # how the endpoint's "stale" reply — the row moved on while the bot was
        # rendering — is put in front of the loop.
        self.ack_script = list(ack_script)

    async def get(self, path, timeout=8.0):
        self.calls.append(("GET", path, None))
        return {"posts": copy.deepcopy(self.posts)}

    async def post(self, path, params=None, timeout=None):
        self.calls.append(("POST", path, params))
        bind = bool((params or {}).get("bind_only"))
        # A release is an ack CALL but not an ack: it hands the claim back and,
        # without a revision, records nothing at all. It must not consume a
        # scripted answer, or a test's second answer would be eaten by the
        # hand-back that follows its first.
        rel = bool((params or {}).get("release"))
        self.trace.append(
            ("release" if rel else ("bind" if bind else "ack"),
             (params or {}).get("post_id")))
        if rel:
            return {"status": "acked", "id": (params or {}).get("post_id")}
        if self.fail_full_ack and not bind:
            return {"error": "boom"}
        if not bind and self.ack_script:
            return self.ack_script.pop(0)
        return {"status": "acked"} if self.ack_ok else {"error": "boom"}


def _acks(api):
    """The ack calls that RECORD something, release hand-backs excluded.

    A release is an ack call too — same endpoint — but it is the loop giving
    the claim back, not a statement about what is on Discord. Counting it as an
    ack would make "nothing was recorded for this row" unanswerable, which is
    the assertion most of the tests below turn on (#441)."""
    return [c[2] for c in api.calls
            if c[1].endswith("/ack") and not (c[2] or {}).get("release")]


def _releases(api):
    return [c[2] for c in api.calls
            if c[1].endswith("/ack") and (c[2] or {}).get("release")]


def _lift_bot():
    tree = _parsed(_BOT_SRC)[1]
    picked, seen = [], set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in _WANT_ASSIGN:
                    picked.append(node)
                    seen.add(t.id)
        elif (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
              and node.target.id in _WANT_ASSIGN):
            picked.append(node)
            seen.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _WANT_FUNC:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            picked.append(fn)
            seen.add(node.name)
    missing = (_WANT_FUNC | _WANT_ASSIGN) - seen
    assert not missing, "discord_bot.py no longer defines %s" % sorted(missing)
    return picked


def _bot_ns(api, bot, out=None):
    out = [] if out is None else out
    ns = {"discord": _FAKE_DISCORD, "bot": bot, "api_get": api.get, "api_post": api.post,
          "http_session": object(), "API_SECRET_KEY": "internal-key", "re": re,
          "print": lambda *a, **k: out.append(" ".join(str(x) for x in a))}
    exec(compile(ast.Module(body=_lift_bot(), type_ignores=[]), _BOT_SRC, "exec"), ns)
    return ns


_DELIVERED_AT = "2026-09-19T00:00:00+00:00"
# One token per POLL, which is what the api mints. Every ack the loop makes
# under one _Api must carry exactly this.
_TOK = "aaaaaaaa-0000-4000-8000-00000000000a"


def _row(pid, channel, content, revision, posted_revision, message_id=None,
         fingerprint=None, posted_at="derive", ambiguous=False,
         claim_token=_TOK, bound_message_ids=()):
    # posted_at is the delivery fact and the loop's send/edit decision, so the
    # default mirrors the ordinary states rather than being left absent: a row
    # with a rendered revision was delivered, one without was not. The
    # mixed-version tests pass it explicitly, because the whole point of those
    # states is that the two columns disagree.
    #
    # `ambiguous` and `claim_token` are the api's, not this file's: the
    # server computes ownership over the whole channel and mints the claim, and
    # the loop obeys both. The DSN tests above are what prove the endpoint
    # really produces them, so these fixtures are states the endpoint makes
    # rather than states this file invented.
    if posted_at == "derive":
        posted_at = _DELIVERED_AT if posted_revision is not None else None
    return {"id": pid, "channel_id": str(channel), "content": content,
            "revision": revision, "posted_revision": posted_revision,
            "posted_at": posted_at, "ambiguous": ambiguous,
            "claim_token": claim_token,
            "bound_message_ids": [str(b) for b in bound_message_ids],
            "message_id": message_id, "adopt_fingerprint": fingerprint}


def test_loop_asks_for_revisions():
    """The flag is what keeps a pre-338 bot and a pre-338 api both safe;
    dropping it silently reverts this loop to fire-once delivery."""
    api = _Api([])
    ns = _bot_ns(api, _Bot({}))
    asyncio.run(ns["poll_channel_posts"]())
    assert api.calls == [("GET", "/internal/channel-posts/pending?revisions=true", None)]


def test_correction_edits_the_stored_message_and_sends_nothing():
    live = _Msg(4242, "old FAQ text", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live])
    api = _Api([_row(1, 555, "new FAQ text", revision=2, posted_revision=1,
                     message_id="4242")])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == [], "a correction must never post a second message"
    assert len(live.edits) == 1 and live.content == "new FAQ text"
    assert ("POST", "/internal/channel-posts/ack",
            {"post_id": 1, "revision": 2, "message_id": "4242",
             "claim_token": _TOK}) in api.calls
    assert ch.scans == 0, "a stored id must not trigger a history scan"


def test_correction_adopts_the_pre_338_message_by_its_exact_text():
    """The six #scr-faq messages predate the id column. Adoption is by full
    content, not by position: a positional guess would confidently edit the
    wrong message, which is the check-that-cannot-fail shape (#342)."""
    noise = _Msg(1, "someone else's message", 99)
    mine_a = _Msg(2, "message one as posted", _Channel.BOT_ID)
    mine_b = _Msg(3, "message two as posted", _Channel.BOT_ID)
    ch = _Channel(555, existing=[noise, mine_a, mine_b])
    api = _Api([_row(9, 555, "message two, corrected", revision=2, posted_revision=1,
                     message_id=None, fingerprint="message two as posted")])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert mine_a.edits == [], "adoption matched the wrong message"
    assert mine_b.content == "message two, corrected"
    assert ("POST", "/internal/channel-posts/ack",
            {"post_id": 9, "revision": 2, "message_id": "3",
             "claim_token": _TOK}) in api.calls


def test_an_unadoptable_correction_changes_nothing_at_all():
    """The whole point of the item: when the live message cannot be found, the
    old text stays up. It must NOT degrade into the append this migration
    exists to stop (#276 — choose which direction the unhandled case fails)."""
    ch = _Channel(555, existing=[_Msg(2, "some other text entirely", _Channel.BOT_ID)])
    api = _Api([_row(9, 555, "corrected", revision=2, posted_revision=1,
                     message_id=None, fingerprint="message two as posted")])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == [], "an unadoptable correction posted a new message"
    assert [m.edits for m in ch.messages] == [[]]
    assert not _acks(api), "the row was acked without rendering anything"
    assert _releases(api) == [{"post_id": 9, "release": "true",
                              "claim_token": _TOK}], (
        "the tick decided not to render and kept the claim anyway — the "
        "row waits out a 120 s lease for a decision already made")
    assert any("correction skipped" in line for line in out)


def test_a_deleted_message_is_not_reposted():
    ch = _Channel(555, existing=[])
    api = _Api([_row(9, 555, "corrected", revision=2, posted_revision=1,
                     message_id="4242")])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())
    assert ch.sent == []
    assert not _acks(api)
    # A message that is GONE is a decision, not a failure: hand the claim
    # back rather than making the next tick wait out the lease.
    assert _releases(api) == [{"post_id": 9, "release": "true",
                              "claim_token": _TOK}]


def test_two_identical_MESSAGES_are_ambiguous_and_adopt_nothing():
    """ONE row, TWO matching messages: which of them is this row's?

    Nothing outside can tell them apart, so the honest answer is neither. The
    companion case — two ROWS and one message — is the next two tests; round
    two's fixture for this only ever built this one, which is why the
    ownership half went unnoticed."""
    twin_a = _Msg(11, "the same body", _Channel.BOT_ID)
    twin_b = _Msg(12, "the same body", _Channel.BOT_ID)
    ch = _Channel(555, existing=[twin_a, twin_b])
    api = _Api([_row(9, 555, "corrected", revision=2, posted_revision=1,
                     message_id=None, fingerprint="the same body")])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert twin_a.edits == [] and twin_b.edits == []
    assert not _acks(api)
    assert any("ambiguous" in line for line in out), out


def test_the_scan_skips_a_message_another_row_in_the_channel_owns():
    """The other half of excluding a bound twin from `ambiguous`.

    The api stops treating a row that holds an id as a rival for the same
    text, which is what lets this row scan at all. That is only safe because
    the same response hands over every id the channel's other rows already
    own, and the scan takes them out of the running. Message 41 is the bound
    twin's; 42 is this row's; both carry the shared body. Skipping 41 leaves
    exactly one hit and the row adopts its own message.

    Drop the bound-id skip and the scan sees two hits, calls it ambiguous and
    adopts nothing — so the correction never renders. That is the benign
    direction of the same mistake; the destructive one is the fixture below,
    where the row's OWN message is gone and the only hit left is the twin's."""
    twins = _Channel(555, existing=[
        _Msg(41, "the shared body", _Channel.BOT_ID),
        _Msg(42, "the shared body", _Channel.BOT_ID)])
    api = _Api([_row(9, 555, "corrected", revision=2, posted_revision=1,
                     message_id=None, fingerprint="the shared body",
                     bound_message_ids=[41])])
    out = []
    ns = _bot_ns(api, _Bot({555: twins}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert [m.id for m in twins.messages if m.edits] == [42], (
        "the scan did not skip the id another row in the channel owns: %s"
        % [(m.id, m.edits) for m in twins.messages])


def test_the_scan_adopts_nothing_when_the_only_hit_is_another_rows_message():
    """The destructive direction, refused.

    Same shape as above, except this row's own message is gone — deleted, or
    never sent. The single surviving message carrying the shared body belongs
    to the bound twin. Without the skip the scan finds exactly one hit and
    adopts confidently, and the twin's message is then edited into this row's
    text: one correct message destroyed and two rows pointing at one id.

    With the skip there are no hits, the row refuses, and the channel is left
    as it is — which is the answer a scan that cannot identify its own message
    has to give (#276/#430)."""
    ch = _Channel(555, existing=[_Msg(41, "the shared body", _Channel.BOT_ID)])
    api = _Api([_row(9, 555, "corrected", revision=2, posted_revision=1,
                     message_id=None, fingerprint="the shared body",
                     bound_message_ids=[41])])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.messages[0].edits == [], (
        "the row adopted a message another row owns and edited it into its "
        "own text: %s" % ch.messages[0].edits)
    assert ch.sent == [], "a correction re-sent the sheet instead of refusing"
    assert not _acks(api), (
        "a row that adopted nothing still reported a render: %s" % _acks(api))


def test_two_identical_ROWS_with_one_message_bind_nothing():
    """TWO rows whose sent text is byte-identical, and ONE message left.

    Exactly-one is only exactly-one because it is evaluated one row at a time:
    each row's own scan sees a single hit, and the row that happens to run
    first takes the message. It has a 50% chance of being right and no way to
    tell, and the wrong half edits a correct message into another entry's
    text. Ownership is what is ambiguous, so BOTH rows refuse: the ONE
    surviving message stays exactly as it is, nothing is sent, nothing is
    bound. (Round three's prose said "two correct old messages stay up" here —
    the two-message scenario written over the one-message one, which is the
    case this test exists for.)

    The flag is the SERVER's, computed over the whole channel — see
    test_ambiguity_is_a_property_of_the_channel_not_of_the_response, which is
    what proves the endpoint really answers `t` for this pair. This test is
    about what the loop does with the answer."""
    only = _Msg(31, "the shared body", _Channel.BOT_ID)
    ch = _Channel(555, existing=[only])
    api = _Api([
        _row(1, 555, "first correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body", ambiguous=True),
        _row(2, 555, "second correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body", ambiguous=True),
    ])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert only.edits == [], (
        "one of two indistinguishable rows took the surviving message: %s"
        % only.edits)
    assert not _acks(api), (
        "a row was bound or acked although its ownership is unknowable")
    assert sum("ambiguous" in line for line in out) == 2, out
    assert ch.scans == 0, (
        "an ambiguous row scanned the channel anyway — the refusal has to come "
        "before the scan, or its outcome depends on what the scan happens to "
        "find")
    _states_at(BOT, "_adopt_channel_post_message",
               "AMBIGUITY REFUSES, AND THE SERVER IS WHAT DECIDES IT",
               "REFUSING LEAVES THE CHANNEL EXACTLY AS IT")
    # The loop's own copy of the same sentence, and the direction a failure
    # takes the claim. Both are round-four rules about the whole state space,
    # which is exactly the kind of sentence that gets reverted to a tidier
    # false one (#351/#366).
    _states_at(BOT, "poll_channel_posts",
               "REFUSING LEAVES THE CHANNEL EXACTLY AS IT",
               "ANYTHING THAT IS NOT A DECISION")   # the sentence wraps
                                                    # in the source, so the
                                                    # pin stops at the line


def test_two_identical_ROWS_with_two_messages_bind_nothing():
    """The same pair with BOTH messages still there.

    Round two refused this case for the wrong reason — each row's own scan saw
    two hits — which is why removing one message was enough to make it bind
    arbitrarily. The refusal does not depend on the channel at all now, so the
    number of surviving messages cannot change the answer."""
    twin_a = _Msg(41, "the shared body", _Channel.BOT_ID)
    twin_b = _Msg(42, "the shared body", _Channel.BOT_ID)
    ch = _Channel(555, existing=[twin_a, twin_b])
    api = _Api([
        _row(1, 555, "first correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body", ambiguous=True),
        _row(2, 555, "second correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body", ambiguous=True),
    ])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert twin_a.edits == [] and twin_b.edits == []
    assert not _acks(api)


def test_the_unambiguous_row_of_a_batch_still_binds():
    """X / X / Y — the negative control for the two tests above.

    A guard that refused every row in a batch containing a duplicate would pass
    both of them and quietly stop the bus. The server marks only the twins, and
    the third row binds, edits and acks exactly as if they were not there. The
    SQL that decides this is exercised directly by
    test_ambiguity_is_a_property_of_the_channel_not_of_the_response, where
    dropping the fingerprint comparison from the EXISTS — "ambiguous if this
    channel holds any other row" — reds on this row's twin."""
    only = _Msg(31, "the shared body", _Channel.BOT_ID)
    mine = _Msg(32, "a body of its own", _Channel.BOT_ID)
    ch = _Channel(555, existing=[only, mine])
    api = _Api([
        _row(1, 555, "first correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body", ambiguous=True),
        _row(2, 555, "second correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body", ambiguous=True),
        _row(3, 555, "third corrected", revision=2, posted_revision=1,
             message_id=None, fingerprint="a body of its own", ambiguous=False),
    ])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert only.edits == []
    assert mine.content == "third corrected", (
        "the unambiguous row was refused too — the guard has become a refusal "
        "of everything, which is a check that cannot fail (#342)")
    assert [c["post_id"] for c in _acks(api)] == [3, 3], _acks(api)

    # WHERE the decision lives, pinned on BOTH sides of the wire. Round three
    # moved ambiguity out of the bot and into the hand-out, and the bot kept
    # no implementation of it to anchor on — so a reader looking for one in
    # discord_bot.py lands in whatever prose happens to sit at the old line.
    # These two sentences are the anchor, asserted rather than remembered.
    _states_at(API_MAIN, "pending_channel_posts",
               "`ambiguous` IS COMPUTED HERE, NOT IN THE BOT")
    _states_at(BOT, "_adopt_channel_post_message",
               "Neither list is the ownership rule")


def test_equal_text_in_two_channels_binds_both():
    """Two channels that happen to carry the same sentence are not a
    collision: an adoption scan never leaves its own channel, so each row has
    exactly one candidate. Treating them as ambiguous blocked both corrections
    for good — a refusal with an unbounded cost (#430)."""
    a = _Msg(61, "the shared body", _Channel.BOT_ID)
    b = _Msg(62, "the shared body", _Channel.BOT_ID)
    ch_a = _Channel(555, existing=[a])
    ch_b = _Channel(556, existing=[b])
    api = _Api([
        _row(1, 555, "corrected in A", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body", ambiguous=False),
        _row(2, 556, "corrected in B", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body", ambiguous=False),
    ])
    ns = _bot_ns(api, _Bot({555: ch_a, 556: ch_b}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch_a.sent == [] and ch_b.sent == []
    assert a.content == "corrected in A" and b.content == "corrected in B"
    assert sorted(c["post_id"] for c in _acks(api)) == [1, 1, 2, 2]


def test_a_fingerprint_matches_byte_for_byte_or_not_at_all():
    """Two bodies that differ only in edge whitespace are two bodies.

    Round two compared both operands stripped, which widened the set of
    messages a row would accept in order to tolerate a difference that, if it
    existed, would mean the recorded text is not what was posted. The right
    answer to "almost matches" is to refuse and leave the old text up (#276),
    so the message with the trailing newline is NOT this row's."""
    near = _Msg(51, "the body\n", _Channel.BOT_ID)
    ch = _Channel(555, existing=[near])
    api = _Api([_row(9, 555, "corrected", revision=2, posted_revision=1,
                     message_id=None, fingerprint="the body")])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert near.edits == [], "a normalized comparison adopted a different body"
    assert any("correction skipped" in line for line in out), out


def test_a_correction_that_moves_mid_tick_is_rendered_forward():
    """The ack names what was rendered, so the api can say "that is not the
    current text any more" — and the loop acts on it in the same tick.

    Without this the channel sits on a revision the database already knows is
    superseded until the next poll, for no reason other than that the writer
    won a race with the renderer."""
    live = _Msg(61, "old text", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live])
    api = _Api([_row(9, 555, "rev 2 text", revision=2, posted_revision=1,
                     message_id="61")],
               ack_script=[{"status": "stale", "id": 9, "revision": 3,
                            "content": "rev 3 text"},
                           {"status": "acked", "id": 9, "revision": 3}])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert [e["content"] for e in live.edits] == ["rev 2 text", "rev 3 text"]
    assert _acks(api) == [
        {"post_id": 9, "revision": 2, "message_id": "61", "claim_token": _TOK},
        {"post_id": 9, "revision": 3, "message_id": "61", "claim_token": _TOK},
    ]


def test_a_row_that_keeps_moving_is_left_pending_not_chased():
    """The re-render is CAPPED at two per row per tick.

    A writer this loop does not control could otherwise hold it in an
    unbounded chase (#361), starving every row behind it. The third revision
    simply waits for the next poll, with the id stored and nothing sent."""
    live = _Msg(62, "old text", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live])
    api = _Api([_row(9, 555, "rev 2 text", revision=2, posted_revision=1,
                     message_id="62")],
               ack_script=[{"status": "stale", "id": 9, "revision": 3,
                            "content": "rev 3 text"},
                           {"status": "stale", "id": 9, "revision": 4,
                            "content": "rev 4 text"},
                           {"status": "acked", "id": 9, "revision": 4}])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert len(live.edits) == 2, [e["content"] for e in live.edits]
    assert len(_acks(api)) == 2
    assert any("still behind" in line for line in out), out
    # THE CAP HANDS THE CLAIM BACK, naming the revision it RENDERED (3),
    # never the newer one the stale answer carried (4). Recording 4 would
    # mark a text delivered that nobody has put on Discord.
    assert _releases(api) == [{"post_id": 9, "revision": 3, "release": "true",
                              "claim_token": _TOK}], _releases(api)


def test_a_fresh_post_corrected_between_send_and_ack_is_edited_not_duplicated():
    """The same race on the SEND path, where getting it wrong costs a message.

    The api records the revision that was sent — so nothing reads as delivered
    that is not — and hands back the newer text. The bot holds the message it
    just created, so it corrects it in place. The one thing it must never do
    is post the newer revision as a second message."""
    ch = _Channel(555, existing=[])
    api = _Api([_row(7, 555, "first text", revision=1, posted_revision=None,
                     posted_at=None)],
               ack_script=[{"status": "stale", "id": 7, "revision": 2,
                            "content": "second text"},
                           {"status": "acked", "id": 7, "revision": 2}])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert len(ch.sent) == 1, "the correction was posted as a second message"
    assert ch.sent[0].content == "second text"
    assert _acks(api) == [
        {"post_id": 7, "revision": 1, "message_id": str(ch.sent[0].id),
         "claim_token": _TOK},
        {"post_id": 7, "revision": 2, "message_id": str(ch.sent[0].id),
         "claim_token": _TOK},
    ]


def test_the_render_cap_is_one_rule_and_both_paths_are_bound_by_it():
    """One cap, one place — asserted as a property of the source, not hoped for.

    The correction path's comment has said for three rounds that its cap is
    "the ONLY thing bounding that, deliberately in one place — a second copy
    would let one of them be lifted while the other held, and the test could
    not tell". The send path carried the second copy anyway, spelled as
    control flow: a single `if` admitting exactly one corrective edit, which
    is the number 2 written as a shape. Nothing named it, so nothing could
    compare the two, and raising the constant would have moved one path only.

    This is the class sweep the comment implies (#432): the constant is
    defined once, both loops are bound by that name, and no local cap
    survives anywhere in the loop."""
    src = _read(BOT)
    defined = re.findall(r"^_CHANNEL_POST_MAX_RENDERS = (\d+)$", src, re.M)
    assert len(defined) == 1, (
        "_CHANNEL_POST_MAX_RENDERS is defined %d times; a cap with two "
        "definitions is two caps" % len(defined))

    loop = _function_source(BOT, "poll_channel_posts")
    bounds = re.findall(r"renders < _CHANNEL_POST_MAX_RENDERS", loop)
    assert len(bounds) == 2, (
        "%d of the two render paths are bound by the named cap. The one that "
        "is not has a cap of its own, and the two can be moved apart without "
        "anything going red" % len(bounds))
    assert "max_renders" not in loop, (
        "a local render cap is back in the loop beside the module constant")


def test_the_send_path_stops_at_the_same_cap_and_hands_the_claim_back():
    """The send path's own chase, bounded and then handed back.

    Send revision 1; the ack comes back stale at revision 2; edit forward;
    that ack comes back stale at revision 3. Two renders have happened — the
    send and one edit — so the cap is reached and this tick stops, exactly as
    the correction path does at the same number. The row is delivered and
    carries its id, so the next poll edits it rather than sending again.

    THE HAND-BACK IS PURE: no revision is named. The delivery ack already
    recorded the revision that went out, and naming one here could only repeat
    it or name a revision nobody rendered. Naming the newer one would mark a
    text delivered that is not on Discord.

    This is the case the second, unnamed cap used to answer: it stopped at the
    same count, but by the shape of the code rather than by the constant."""
    ch = _Channel(555, existing=[])
    api = _Api([_row(7, 555, "first text", revision=1, posted_revision=None,
                     posted_at=None)],
               ack_script=[{"status": "stale", "id": 7, "revision": 2,
                            "content": "second text"},
                           {"status": "stale", "id": 7, "revision": 3,
                            "content": "third text"}])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert len(ch.sent) == 1, (
        "a correction was posted as a second message: %d sends"
        % len(ch.sent))
    assert ch.sent[0].content == "second text", (
        "the send path's chase ended on %r, not on the second text — the one "
        "render the cap allows after the send" % ch.sent[0].content)
    assert len(_acks(api)) == 2, (
        "the send path rendered past the cap: %s" % _acks(api))
    assert any("still behind" in line for line in out), out
    assert _releases(api) == [{"post_id": 7, "release": "true",
                               "claim_token": _TOK}], (
        "the send path's cap did not hand the claim back as a PURE hand-back: "
        "%s" % _releases(api))


def test_one_batch_never_adopts_the_same_message_for_two_rows():
    """A message another row in the SAME batch already owns is not a
    candidate. The six FAQ rows arrive together, so this is the tick on which
    a stored id and an adoption could otherwise collide."""
    shared = _Msg(21, "one body", _Channel.BOT_ID)
    ch = _Channel(555, existing=[shared])
    # The adopting row is processed FIRST, while the message still reads as
    # the text it would adopt on. Only the claim taken from the other row's
    # stored id can stop it; if the later row's edit were what stopped it, the
    # order would decide who wins and this would pass by accident.
    api = _Api([
        _row(2, 555, "second correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="one body"),
        _row(1, 555, "first correction", revision=2, posted_revision=1,
             message_id="21"),
    ])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    # Row 1 owns the message by its stored id; row 2 must not take it too.
    assert [e["content"] for e in shared.edits] == ["first correction"]
    acked = [c["post_id"] for c in _acks(api)]
    assert acked == [1], acked


# ── 7b. The four mixed-version states ───────────────────────────────────────
#
# 338, the api and the bot are deployed in that order, so at any moment one of
# four combinations is live. Each gets its own test, named for the state, so a
# reader can check the set is complete rather than infer it:
#
#   OLD api + OLD bot   the rows that state LEAVES BEHIND, met by the new pair
#                       -> test_state_old_api_old_bot_leaves_a_row_the_new_pair_adopts
#   NEW api + OLD bot   a bot that cannot name a revision or report an id, and
#                       a correction that lands while its ack is in flight
#                       -> test_state_new_api_old_bot_is_recorded_at_what_it_was_handed
#                          (and its DSN half, test_a_legacy_ack_records_what_the_hand_out_gave_it)
#   OLD api + NEW bot   a payload with none of the new keys at all
#                       -> test_state_old_api_new_bot_still_sends_and_acks_as_before
#   NEW api + NEW bot   the nominal correction
#                       -> test_state_new_api_new_bot_corrects_in_place
#
# Two of the four leave a row whose revision columns describe it wrongly, and
# in one of those the wrong reading is a duplicate post.

def test_state_old_api_old_bot_leaves_a_row_the_new_pair_adopts():
    """OLD api + OLD bot, met by the upgraded pair.

    That bot fetches `posted_at IS NULL` rows, so it never meets a correction;
    that api's ack writes only posted_at. Every row the pair delivers
    therefore ends up with posted_at set and posted_revision NULL — which is
    exactly what a never-posted row looks like to the revision columns, and
    re-sending it puts a second copy in the channel.

    posted_at is the delivery fact, so the loop keys on it and ADOPTS instead.
    The fingerprint in this payload is the one the upgraded api DERIVES for
    such a row (test_the_pending_read_derives_a_legacy_fingerprint_and_writes_
    no_delivery_fact asserts the endpoint really returns it, so this fixture is
    a state the endpoint produces rather than one this file invented)."""
    live = _Msg(4242, "announcement as delivered", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live])
    api = _Api([_row(1, 555, "announcement as delivered", revision=1,
                     posted_revision=None, message_id=None,
                     fingerprint="announcement as delivered",
                     posted_at=_DELIVERED_AT)])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == [], (
        "a row an old bot already delivered was posted a second time — the "
        "loop is reading posted_revision as the delivery signal")
    assert _acks(api) == [
        {"post_id": 1, "message_id": "4242", "bind_only": "true",
         "claim_token": _TOK},
        {"post_id": 1, "revision": 1, "message_id": "4242",
         "claim_token": _TOK},
    ], "the row was not bound and acked at the revision that is on Discord"
    _states_at(BOT, "poll_channel_posts",
               "THE SEND/EDIT DECISION IS posted_at")


def test_state_new_api_old_bot_is_recorded_at_what_it_was_handed():
    """NEW api + OLD bot, with the correction landing MID-ACK.

    That bot sends no `revisions` flag, so this api answers it with the
    fire-once set and it behaves exactly as before — it acks with the post id
    and nothing else. What the api does with that ack is asserted against the
    real statement in test_a_legacy_ack_records_what_the_hand_out_gave_it: the
    hand-out recorded what it served, so the ack records THAT, not whatever the
    row says by the time it arrives.

    THE FIXTURE ROUND THREE COULD NOT BUILD. Its version of this test handed
    the loop a row at revision 2 carrying a fingerprint derived from revision
    1's text — a payload the endpoint could not produce, because the derivation
    it used was gated on `revision = 1`. That is the state this window actually
    leaves, and it is now reachable: the row is at revision 2 (the correction
    committed), posted_revision is 1 (what the old bot was handed and
    displayed), and adopt_fingerprint is the exact revision-1 text the ack
    persisted from handed_fingerprint. The upgraded bot meets exactly that and
    finishes it with no message id supplied by hand."""
    live = _Msg(77, "sent by the old bot", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live])
    api = _Api([_row(3, 555, "corrected while that ack was in flight",
                     revision=2, posted_revision=1, message_id=None,
                     fingerprint="sent by the old bot",
                     posted_at=_DELIVERED_AT)])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == [], "the correction was posted as a second message"
    assert live.content == "corrected while that ack was in flight"
    assert _acks(api) == [
        {"post_id": 3, "message_id": "77", "bind_only": "true",
         "claim_token": _TOK},
        {"post_id": 3, "revision": 2, "message_id": "77",
         "claim_token": _TOK},
    ]


def test_state_new_api_new_bot_corrects_in_place():
    """NEW api + NEW bot — the nominal state, stated here so the set of four
    is visible in one place. Its detail is in section 7 above."""
    live = _Msg(4242, "old FAQ text", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live])
    api = _Api([_row(1, 555, "new FAQ text", revision=2, posted_revision=1,
                     message_id="4242")])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())
    assert ch.sent == [] and live.content == "new FAQ text"


def test_a_row_an_old_bot_delivered_without_a_fingerprint_is_still_not_resent():
    """Same window, worst case: the api's adoption UPDATE has not run yet and
    nothing can identify the live message. The row must still not be sent —
    the old text staying up is the acceptable outcome, a duplicate is not
    (#276)."""
    ch = _Channel(555, existing=[_Msg(4242, "announcement as delivered",
                                      _Channel.BOT_ID)])
    api = _Api([_row(1, 555, "announcement as delivered", revision=1,
                     posted_revision=None, message_id=None, fingerprint=None,
                     posted_at=_DELIVERED_AT)])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert not _acks(api)
    assert any("correction skipped" in line for line in out), out


def test_a_never_delivered_row_is_still_sent():
    """The negative control for the two above: posted_at NULL still means
    send. A guard that refused everything would pass those tests and break the
    bus."""
    ch = _Channel(555, existing=[])
    api = _Api([_row(1, 555, "a fresh announcement", revision=1,
                     posted_revision=None, posted_at=None)])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())
    assert [m.content for m in ch.sent] == ["a fresh announcement"]


def test_state_old_api_new_bot_still_sends_and_acks_as_before():
    """OLD api + NEW bot — a pre-338 api answers without any of the new keys
    at all, and ignores the unknown `revisions` query parameter. .get() reads
    None for every one of them, and that build only ever returns rows it
    considers un-posted, so each is a genuine first post."""
    ch = _Channel(555, existing=[])
    api = _Api([{"id": 1, "channel_id": "555", "content": "legacy payload"}])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())
    assert [m.content for m in ch.sent] == ["legacy payload"]
    assert _acks(api) == [{"post_id": 1, "message_id": str(ch.sent[0].id)}]


# ── 7c. A correction is crash-recoverable at every step ──────────────────────

def test_a_correction_persists_its_message_id_before_editing():
    """The edit is what destroys the fingerprint's subject, so it must not be
    the first durable thing that happens.

    Order asserted directly against a shared trace: bind, then edit, then the
    revision ack. Nothing in the loop's own return values distinguishes
    'edited then acked' from 'acked then edited', so the ordering is the
    assertion."""
    trace = []
    live = _Msg(4242, "message two as posted", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live], trace=trace)
    api = _Api([_row(9, 555, "message two, corrected", revision=2,
                     posted_revision=1, message_id=None,
                     fingerprint="message two as posted")], trace=trace)
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert trace == [("bind", 9), ("edit", 4242), ("ack", 9)], trace


def test_a_restart_between_the_edit_and_the_ack_still_finds_the_message():
    """The recovery this ordering buys.

    Tick one adopts, binds the id, edits, and then loses the revision ack —
    the bot dies, or the api does. Tick two runs in a fresh process, so the
    in-memory id is gone, and the fingerprint no longer describes the live
    message because tick one already replaced its text. The durable id is the
    only thing left, and it is enough: the row is edited to the same content
    and acked, with no second message anywhere."""
    live = _Msg(4242, "message two as posted", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live])
    row = _row(9, 555, "message two, corrected", revision=2, posted_revision=1,
               message_id=None, fingerprint="message two as posted")
    api = _Api([row], fail_full_ack=True)
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    bound = [c for c in _acks(api) if c.get("bind_only")]
    assert bound == [{"post_id": 9, "message_id": "4242",
                      "bind_only": "true", "claim_token": _TOK}]
    assert live.content == "message two, corrected"

    # Tick two: fresh process (new namespace => empty _channel_post_sent), and
    # the row as the database now holds it — the bind committed, the revision
    # ack did not, and the fingerprint is stale.
    reloaded = _row(9, 555, "message two, corrected", revision=2,
                    posted_revision=1, message_id="4242",
                    fingerprint="message two as posted")
    api2 = _Api([reloaded])
    ns2 = _bot_ns(api2, _Bot({555: ch}))
    asyncio.run(ns2["poll_channel_posts"]())

    assert ch.sent == [], "the restart produced a second message"
    assert ch.scans == 1, (
        "tick two rescanned history — it should have used the persisted id, "
        "and the stale fingerprint would not have matched anything")
    assert _acks(api2) == [
        {"post_id": 9, "revision": 2, "message_id": "4242",
         "claim_token": _TOK}]


def test_a_failed_bind_leaves_the_message_and_the_fingerprint_intact():
    """If the id cannot be made durable, do not edit. An edit whose id was
    never recorded is the unrecoverable state this ordering exists to remove,
    so the correction waits for the next tick with the old text still up and
    the fingerprint still true."""
    live = _Msg(4242, "message two as posted", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live])
    api = _Api([_row(9, 555, "message two, corrected", revision=2,
                     posted_revision=1, message_id=None,
                     fingerprint="message two as posted")], ack_ok=False)
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert live.edits == [], "edited although the id was never persisted"
    assert live.content == "message two as posted"
    assert ch.sent == []
    assert any("could not persist message id" in line for line in out), out


def test_a_correction_that_cannot_render_does_not_block_a_new_post():
    """226's header warns that a stuck row on this bus stalls everything queued
    behind it. A correction has no position, so skipping it is free; a
    never-posted row keeps the strict ordering it always had."""
    ch = _Channel(555, existing=[])
    api = _Api([
        _row(1, 555, "corrected", revision=2, posted_revision=1, message_id="4242"),
        _row(2, 555, "a fresh announcement", revision=1, posted_revision=None),
    ])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())
    assert [m.content for m in ch.sent] == ["a fresh announcement"]
    assert _acks(api) == [
        {"post_id": 2, "revision": 1, "message_id": str(ch.sent[0].id),
         "claim_token": _TOK}]
