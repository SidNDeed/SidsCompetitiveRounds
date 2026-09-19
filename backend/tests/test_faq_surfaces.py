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

The Postgres test is skipped unless FAQ_TEST_PG_DSN points at a database, the
same convention test_a1_predicate_sql.py uses so the ordinary suite stays
hermetic:

    FAQ_TEST_PG_DSN="postgresql://postgres@127.0.0.1:55432/faqtest" \
        python -m pytest backend/tests/test_faq_surfaces.py -q
"""
import io
import json
import os
import re
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
        if not c.get("surfaces"):
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
    of labels the tier line carries — in the rendered article and in the
    migration that re-keys it, which must also agree with each other."""
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

    article = _ladder_tiers(_read(_INFO_LIBRARY))
    migration = _ladder_tiers(_read(MIG_340))
    assert article, "InfoLibrary.cs no longer carries the gold-tier ladder"
    assert article == migration, (
        "the rendered article and 340's re-keyed source list different tier "
        "members — one of them is describing a ladder nobody ships")
    assert paid == article, (
        "the code pays %s; the article lists %s. Every achievement has to sit "
        "on the line that pays it, or a re-priced key silently keeps its old "
        "tier in three surfaces."
        % ({g: sorted(v) for g, v in sorted(paid.items())},
           {g: sorted(v) for g, v in sorted(article.items())}))


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
    for node in ast.walk(ast.parse(_read(API_MAIN), API_MAIN)):
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
    unconditional one is how "every ~6 weeks" survived for months, so both
    numbers are read out of the gate itself and both must appear on every
    surface that describes the cadence."""
    src = _read("backend/api/tournaments.py")
    start = src.index("async def _ensure_next_tournament")
    body = src[start:src.index("\nasync def ", start + 1)]
    net = re.search(r"\(now - last_async\.created_at\) < timedelta\(hours=(\d+)\)",
                    body)
    assert net, "the 24-hour safety net is no longer a timedelta on created_at"
    assert 'last_async.status == "completed" and last_async.ended_at' in body, (
        "the post-completion wait is no longer conditional, so the surfaces "
        "below now describe a gate that is not there")

    for path in ("docs/FAQ.md",
                 "backend/sql/338_faq_channel_post_revisions.sql"):
        text_ = _read(path)
        assert "only **%s hours** after it was created" % net.group(1) in text_, (
            "%s does not state the gate that holds a cancelled bracket" % path)
        assert "cancelled" in text_, (
            "%s does not say WHICH brackets the two-day wait skips" % path)


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
    the error text is wrong."""
    native = _read(NATIVE_UI)
    png = re.search(r"bytes\.Length > ([\d_]+)\)\s*\n\s*return [^\n]*?"
                    r"PNG missing or too large - ([\d.]+) MB max", native)
    assert png, ("NativeUI's PNG refusal and its size check are no longer "
                 "adjacent, so nothing here reads the message it produces")
    limit, stated = int(png.group(1).replace("_", "")), float(png.group(2))
    assert abs(stated * 1_000_000 - limit) < 50_000, (
        "the client refuses PNGs over %d bytes and calls that %s MB"
        % (limit, png.group(2)))

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
# What counts as routing a reader to a PERSON. An @handle and the word DM were
# round two's whole test, which missed a sentence that names somebody without
# either — "ping <name> in #bug-reports" with the @ dropped reads identically
# to a player and was invisible here. The verbs are the ones a routing
# sentence in this sheet can plausibly use; anything this cannot recognise as
# routing is not judged, and that bound is stated rather than implied (a guard
# is worth what its refusal costs, #430).
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
    for col in ("message_id", "revision", "posted_revision", "adopt_fingerprint",
                "claimed_at"):
        assert re.search(
            r"ADD COLUMN IF NOT EXISTS %s\b" % col, sql), (
            "338 no longer adds %s" % col)
    assert "IF cols <> 5 THEN" in sql, (
        "338's post-check no longer counts all five columns it adds, so a "
        "dropped ALTER would commit silently")
    assert "CREATE INDEX IF NOT EXISTS idx_pending_channel_posts_unrendered" in sql
    assert "WHERE posted_revision IS DISTINCT FROM revision" in sql, (
        "338's index is no longer the partial one the bot's poll relies on")
    assert sql.count("BEGIN;") == 1 and sql.rstrip().endswith("COMMIT;"), (
        "psql -f autocommits statement by statement; the file needs its own "
        "transaction (#340)")


# ── 5. ...and it applies, twice, against a real server ───────────────────────

DSN = os.environ.get("FAQ_TEST_PG_DSN")
PSQL = os.environ.get("FAQ_TEST_PSQL", r"C:/pg16/pgsql/bin/psql.exe")

# These tests DROP and recreate the tables they exercise. A DSN is a string
# somebody types, and the cost of typing the wrong one here is a production
# i18n corpus, so the database NAME has to say it is a scratch one. The guard
# fails closed: an unrecognised DSN skips rather than proceeding.
if DSN and not re.search(r"/[^/?]*test[^/?]*(\?|$)", DSN):
    DSN = None
    _DSN_REASON = ("FAQ_TEST_PG_DSN does not name a *test* database; refusing "
                   "to run the destructive migration checks against it")
else:
    _DSN_REASON = "FAQ_TEST_PG_DSN unset; live-Postgres migration check"

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
    assert marker in sql or marker in ("pollerhold", "reviewhold")
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
        "('message_id','revision','posted_revision','adopt_fingerprint','claimed_at');"
    ).stdout
    assert ("adopt_fingerprint,claimed_at,message_id,posted_revision,revision"
            in cols), cols

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

    before = _psql("SELECT sum(revision) FROM pending_channel_posts;").stdout
    _psql_file(MIGRATION)
    after = _psql("SELECT sum(revision) FROM pending_channel_posts;").stdout
    assert before == after, (
        "a second apply bumped revision again — the content guard is not "
        "convergent:\n%s\n%s" % (before, after))


# ── 5b. The two mixed-version windows, against a real server ────────────────
#
# Both are states the DATABASE can be left in by a fleet that is half
# upgraded, and both are resolved by SQL that lives in main.py. Reimplementing
# that SQL here would test this file's idea of it (#391), so the statements are
# lifted out of the deployed function and executed verbatim; only the bind
# parameters, which psql has no notion of, are substituted.

API_MAIN = os.path.join(REPO, "backend", "api", "main.py")


def _lift_sql(func_name, needle):
    tree = ast.parse(_read(API_MAIN), API_MAIN)
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
    tree = ast.parse(_read(API_MAIN), API_MAIN)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    val = ast.literal_eval(node.value)
                    assert isinstance(val, str) and val, name
                    return val
    raise AssertionError("main.py no longer defines %s at module level" % name)


def _lift_py(*names):
    """Execute the named module-level functions of main.py in isolation.

    main.py cannot be imported in a test process (it builds the whole api on
    import), and a rule that is only re-implemented here is a test agreeing
    with itself (#391). These functions are self-contained, so lifting the
    real definitions and running them is the honest version."""
    tree = ast.parse(_read(API_MAIN), API_MAIN)
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

    "Stale" means the compare-and-set declined the revision the caller named,
    so the caller is handed the current revision and content and edits forward
    in the same tick. A caller that named NO revision — the pre-338 bot, which
    cannot edit at all — is never told stale: it would read a normal delivery
    as a failure and log one every tick, and there is nothing it could do
    about it anyway."""
    reply = _lift_py("_channel_post_ack_reply")["_channel_post_ack_reply"]

    # Rendered the current revision: done.
    assert reply(7, 2, {"revision": 2, "posted_revision": 2, "content": "x"}) == {
        "status": "acked", "id": 7, "revision": 2}
    # Rendered revision 1 while the row moved to 2: stale, with the newer text.
    assert reply(7, 1, {"revision": 2, "posted_revision": 1, "content": "new"}) == {
        "status": "stale", "id": 7, "revision": 2, "content": "new"}
    # Named nothing (a pre-338 bot): acked, whatever the row says.
    assert reply(7, None, {"revision": 2, "posted_revision": None,
                           "content": "new"}) == {
        "status": "acked", "id": 7, "revision": None}


def _pending_sql(revisions=True, lease=None):
    """The deployed pending statement, bound for psql.

    Both halves come out of main.py: the statement, and the WHERE literal the
    endpoint selects with its bool. Writing either one here would let the
    deployed pair drift while this file stayed green."""
    where = _lift_module_str("_CHANNEL_POST_WHERE_UNRENDERED" if revisions
                             else "_CHANNEL_POST_WHERE_UNPOSTED")
    if lease is None:
        lease = int(re.search(r"^CHANNEL_POST_CLAIM_SECONDS = (\d+)$",
                              _read(API_MAIN), re.M).group(1))
    sql = _lift_module_str("_CHANNEL_POST_PENDING_SQL").format(where=where)
    return sql.replace(":lease", str(lease))


def _bind(sql, pid, rev="NULL", mid="NULL"):
    out = (sql.replace("CAST(:rev AS INTEGER)", "CAST(%s AS INTEGER)" % rev)
              .replace("CAST(:mid AS TEXT)", "CAST(%s AS TEXT)" % mid)
              .replace(":pid", str(pid)))
    # A bare ":" is not the test — the statement carries '[MODCASE:%' and
    # ::casts, and a guard that tripped on those would be turned off rather
    # than fixed. A SQLAlchemy bind is a colon that starts a word.
    leftover = re.search(r"(?<![:\w]):[a-z_]{2,}", out)
    assert not leftover, "unbound parameter %r left in %r" % (leftover.group(0), out)
    return out


def _state(order):
    return _psql(
        "SELECT COALESCE(posted_revision::text,'null') || '|' || "
        "       COALESCE(adopt_fingerprint,'null') || '|' || "
        "       COALESCE(message_id,'null') || '|' || "
        "       CASE WHEN posted_at IS NULL THEN 'unposted' ELSE 'posted' END "
        "  FROM pending_channel_posts WHERE sort_order = %d;" % order
    ).stdout.strip()


def _hand_out(revisions=True, lease=None, project=None):
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
    sql = _pending_sql(revisions=revisions, lease=lease)
    return _psql("CREATE TEMP TABLE handed AS " + sql + "; "
                 "SELECT " + project + ";").stdout.strip()


def _pending_rows(revisions=True, lease=None):
    """sort_order|posted_revision|adopt_fingerprint for one hand-out."""
    return _hand_out(revisions=revisions, lease=lease)


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_the_pending_read_derives_a_legacy_fingerprint_and_writes_nothing():
    """WINDOW ONE — 338 applied, old api, old bot still running.

    The pre-338 ack writes posted_at and nothing else, so every row that bot
    delivers afterwards reads, by the revision columns alone, exactly like a
    row that was never posted, and nobody recorded the text it was sent with.

    Round two resolved those rows with an UPDATE on this GET: posted_revision
    = 1 for every one of them. That is a statement about what is on Discord
    made by the side that cannot see Discord, and on a row corrected since
    delivery it recorded a revision while capturing no fingerprint — a row
    findable by neither handle. Now nothing is written. The fingerprint is
    DERIVED in the projection instead, and only where it is provable: any
    rewrite bumps revision, so revision = 1 on a delivered row proves the
    stored content is still the text that was sent. A row already past
    revision 1 is handed over with no fingerprint and no revision, and the bot
    leaves its message alone."""
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
    _psql("UPDATE pending_channel_posts SET claimed_at = NULL;")
    assert _hand_out(revisions=False, project="count(*) FROM handed") == "1"
    assert _psql("SELECT count(*) FROM pending_channel_posts "
                 "WHERE posted_at IS NULL AND claimed_at IS NOT NULL;"
                 ).stdout.strip() == "1", (
        "the hand-out locked the row but never claimed it — a poller one tick "
        "later is handed it again and sends a second copy")
    assert _hand_out(revisions=False, project="count(*) FROM handed") == "0", (
        "the same row was handed out twice in a row")

    # ...and the claim is a LEASE, not a lock: a poller that died mid-batch
    # must not strand the row. With the lease expired the row comes back.
    _psql("UPDATE pending_channel_posts SET claimed_at = now() "
          "WHERE posted_at IS NULL;")
    assert _hand_out(revisions=False, project="count(*) FROM handed") == "0"
    assert _hand_out(revisions=False, lease=0,
                     project="count(*) FROM handed") == "1", (
        "an expired claim still hides the row — a dead poller would strand it")


_ACK_NEEDLE = "RETURNING revision, posted_revision, content"


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_a_legacy_ack_records_only_what_it_can_prove():
    """WINDOW TWO — new api, old bot still running.

    That bot cannot name the revision it rendered, and it can never report a
    message id. Round two filled the gap with COALESCE(:rev, revision), i.e.
    "whatever the row says now" — so a correction landing between that bot's
    send and its ack was CONSUMED by the ack: the row read "revision 2
    rendered" while Discord still showed revision 1, and nothing ever
    delivered the correction.

    Now the ack records only the provable. A rewrite bumps revision, so a
    delivered row still at revision 1 has content that is still the text that
    was sent: revision 1 and the fingerprint are both written. A row already
    past revision 1 gets neither — posted_revision stays NULL, which reads as
    "delivered, revision unknown" and keeps the row pending for a bot that can
    say what it rendered."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _lift_sql("ack_channel_post", _ACK_NEEDLE)

    pid = _psql("SELECT id FROM pending_channel_posts WHERE sort_order = 9;").stdout.strip()
    _psql(_bind(full, pid))
    assert _state(9) == "1|never posted|null|posted", _state(9)

    # THE HIGH: a correction lands between the old bot's send and its ack.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'corrected while in flight', 14);")
    _psql("UPDATE pending_channel_posts SET revision = 2 WHERE sort_order = 14;")
    pid14 = _psql("SELECT id FROM pending_channel_posts WHERE sort_order = 14;").stdout.strip()
    _psql(_bind(full, pid14))
    assert _state(14) == "null|null|null|posted", (
        "a legacy ack claimed a revision the bot never displayed, or "
        "fingerprinted content that was not what it sent: %s" % _state(14))

    # A bot that CAN report an id needs no fingerprint — the id is the better
    # handle, and a fingerprint nothing consults is a claim about the channel
    # that nothing maintains.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'delivered by a current bot', 12);")
    pid12 = _psql("SELECT id FROM pending_channel_posts WHERE sort_order = 12;").stdout.strip()
    _psql(_bind(full, pid12, rev="1", mid="'7788'"))
    assert _state(12) == "1|null|7788|posted", _state(12)

    # A moderation case's stored content is not what was posted for it, so it
    # gets no fingerprint however it is acked (338's exclusion).
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('777', '[MODCASE:0af1c0de-0000-4000-8000-000000000001]"
          "\nReport: spam', 13);")
    pid13 = _psql("SELECT id FROM pending_channel_posts WHERE sort_order = 13;").stdout.strip()
    _psql(_bind(full, pid13))
    assert _state(13) == "1|null|null|posted", _state(13)


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_an_ack_persists_the_revision_it_names_and_no_other():
    """Compare-and-set, all four directions.

    The ack's own number is the only one that may be written; it may not
    exceed the row's revision, because nobody renders a future text; and it
    may not move posted_revision backwards, because a stale in-flight ack
    would otherwise re-open a correction that is already on Discord."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _lift_sql("ack_channel_post", _ACK_NEEDLE)

    # A correction lands while this tick is rendering revision 1.
    _psql("INSERT INTO pending_channel_posts (channel_id, content, sort_order) "
          "VALUES ('999', 'now at rev 2', 21);")
    _psql("UPDATE pending_channel_posts SET revision = 2 WHERE sort_order = 21;")
    pid = _psql("SELECT id FROM pending_channel_posts WHERE sort_order = 21;").stdout.strip()
    _psql(_bind(full, pid, rev="1", mid="'100'"))
    assert _state(21) == "1|null|100|posted", (
        "the ack did not record the revision it named: %s" % _state(21))

    # The row is therefore still pending, which is what drives the re-edit.
    assert _psql("SELECT count(*) FROM pending_channel_posts "
                 "WHERE sort_order = 21 AND posted_revision IS DISTINCT FROM "
                 "revision;").stdout.strip() == "1"

    # Forward to the current revision: accepted.
    _psql(_bind(full, pid, rev="2", mid="'100'"))
    assert _state(21) == "2|null|100|posted", _state(21)

    # Backwards: refused, or a late duplicate ack would re-open a delivered
    # correction and the bot would edit the same text again every tick.
    _psql(_bind(full, pid, rev="1", mid="'100'"))
    assert _state(21) == "2|null|100|posted", (
        "posted_revision moved backwards: %s" % _state(21))

    # Past the row's own revision: refused. Nobody renders a future text, so
    # an ack claiming one is a bug in the caller, not an instruction.
    _psql(_bind(full, pid, rev="9", mid="'100'"))
    assert _state(21) == "2|null|100|posted", (
        "an ack advanced the row past its own revision: %s" % _state(21))


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_an_ack_releases_the_claim():
    """A row the bot finished with must not sit under its own lease: the next
    correction would wait out the claim before anyone could render it."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    full = _lift_sql("ack_channel_post", _ACK_NEEDLE)
    pid = _psql("SELECT id FROM pending_channel_posts WHERE sort_order = 9;").stdout.strip()
    _psql("UPDATE pending_channel_posts SET claimed_at = now() WHERE sort_order = 9;")
    _psql(_bind(full, pid, rev="1", mid="'55'"))
    assert _psql("SELECT claimed_at IS NULL FROM pending_channel_posts "
                 "WHERE sort_order = 9;").stdout.strip() == "t"


@pytest.mark.skipif(not DSN, reason=_DSN_REASON)
def test_the_bind_only_ack_advances_nothing_but_the_id():
    """The whole reason a correction can survive a restart: the id becomes
    durable without the row being marked delivered. If this arm advanced
    posted_revision, the correction would be recorded as rendered before the
    edit had been attempted."""
    _psql(_BASE_TABLE)
    _psql_file(MIGRATION)
    bind = _lift_sql("ack_channel_post", "SET message_id = COALESCE")

    _psql("UPDATE pending_channel_posts SET revision = 2 WHERE sort_order = 1;")
    pid = _psql("SELECT id FROM pending_channel_posts WHERE sort_order = 1;").stdout.strip()
    before = _psql("SELECT revision || '|' || posted_revision || '|' || "
                   "posted_at::text FROM pending_channel_posts "
                   "WHERE sort_order = 1;").stdout.strip()
    _psql(_bind(bind, pid, mid="'4242'"))
    after = _psql("SELECT revision || '|' || posted_revision || '|' || "
                  "posted_at::text FROM pending_channel_posts "
                  "WHERE sort_order = 1;").stdout.strip()
    assert before == after, (
        "bind_only moved a delivery column: %s -> %s" % (before, after))
    assert _state(1) == "1|stale message one|4242|posted", _state(1)


# ── 6. The i18n pair: three re-keyed articles, four locales each ─────────────

MIG_340 = os.path.join(REPO, "backend", "sql", "340_i18n_keys_item11.sql")
MIG_341 = os.path.join(REPO, "backend", "sql", "341_seed_machine_translations_item11.sql")
CATALOGUES = os.path.join(REPO, "plugin", "I18nCatalogues.cs")
I18N_SOURCE = os.path.join(REPO, "tools", "i18n_source.json")

# The three articles item 11 corrected, each identified by a phrase that only
# the corrected text contains.
REKEYED = {
    "ranked 1v1 article": "a warning at 15 seconds",
    "economy article": "Bodycount, Sync Champion",
    "cosmetics article": "or up to 16 numbered PNG frames",
}


def _csharp_escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\r", "\\r").replace("\n", "\\n"))


def _locale_blocks():
    lines = _read(CATALOGUES).split("\n")
    bounds, cur = {}, None
    for i, line in enumerate(lines):
        m = re.match(
            r"\s*private static readonly Dictionary<string, string> (ES|RU|UK|SV) = ",
            line)
        if m:
            if cur:
                bounds[cur[0]] = (cur[1], i)
            cur = (m.group(1), i)
    bounds[cur[0]] = (cur[1], len(lines))
    return {loc: "\n".join(lines[lo:hi]) for loc, (lo, hi) in bounds.items()}


def test_rekeyed_articles_have_all_four_locales():
    """An English edit inside a translated literal re-keys it.

    The catalogue key IS the English source, so changing one sentence orphans
    that article in every locale unless the key moves with it — the #578
    failure, where an English-only pass shipped English to four locales with
    every gate green, and #583's point that the DLL-bundled catalogue is the
    artifact a player renders.

    Asserted against the escaped key, not a substring, so a re-key that lands
    a NEARLY-right source (a stray space, a CRLF) fails here instead of
    silently falling back to English in front of the player."""
    with io.open(I18N_SOURCE, encoding="utf-8") as fh:
        sources = json.load(fh)["strings"]
    blocks = _locale_blocks()
    problems = []
    for label, probe in REKEYED.items():
        hits = [s for s in sources if probe in s]
        if len(hits) != 1:
            problems.append(
                "%s: %d extracted source strings carry %r (expected 1) — re-run "
                "tools/i18n_extract.py" % (label, len(hits), probe))
            continue
        key = '["' + _csharp_escape(hits[0]) + '"] = "'
        for loc in ("ES", "RU", "UK", "SV"):
            if key not in blocks[loc]:
                problems.append(
                    "%s: %s has no catalogue entry for the corrected English "
                    "source" % (label, loc))
    assert not problems, "\n".join(problems)


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
    with io.open(I18N_SOURCE, encoding="utf-8") as fh:
        extracted = set(json.load(fh)["strings"])
    for kid in sorted(retired):
        assert kid in old_sources, (
            "340 retires %s, which 251 never registered — nobody can say what "
            "text that id is" % kid)
        assert _client_key_id(old_sources[kid]) == kid, (
            "251's source for %s does not hash to it; the id is not that "
            "article's key" % kid)
        assert old_sources[kid] not in extracted, (
            "340 retires %s but its English is still extracted, so a client "
            "still renders it" % kid)

    successors = set(re.findall(r"^  \('([0-9a-f]{16})', 'client',", sql, re.M))
    assert not (successors & retired), "340 retires a key it just registered"
    for kid, source in re.findall(r"^  \('([0-9a-f]{16})', 'client', \$k340\$(.*?)\$k340\$",
                                  sql, re.M | re.S):
        assert _client_key_id(source) == kid, (
            "340's own key id %s does not hash from the source beside it" % kid)
        assert source in extracted, (
            "340 registers %s but tools/i18n_source.json does not carry that "
            "source — re-run tools/i18n_extract.py" % kid)

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
              "_adopt_channel_post_message"}
_WANT_ASSIGN = {"MODCASE_MARKER", "_channel_post_sent"}


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
        self.trace.append(("bind" if bind else "ack", (params or {}).get("post_id")))
        if self.fail_full_ack and not bind:
            return {"error": "boom"}
        if not bind and self.ack_script:
            return self.ack_script.pop(0)
        return {"status": "acked"} if self.ack_ok else {"error": "boom"}


def _lift_bot():
    tree = ast.parse(_read(_BOT_SRC), _BOT_SRC)
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


def _row(pid, channel, content, revision, posted_revision, message_id=None,
         fingerprint=None, posted_at="derive"):
    # posted_at is the delivery fact and the loop's send/edit decision, so the
    # default mirrors the ordinary states rather than being left absent: a row
    # with a rendered revision was delivered, one without was not. The
    # mixed-version tests pass it explicitly, because the whole point of those
    # states is that the two columns disagree.
    if posted_at == "derive":
        posted_at = _DELIVERED_AT if posted_revision is not None else None
    return {"id": pid, "channel_id": str(channel), "content": content,
            "revision": revision, "posted_revision": posted_revision,
            "posted_at": posted_at,
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
            {"post_id": 1, "revision": 2, "message_id": "4242"}) in api.calls
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
            {"post_id": 9, "revision": 2, "message_id": "3"}) in api.calls


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
    assert not [c for c in api.calls if c[1].endswith("/ack")], (
        "the row was acked without rendering anything")
    assert any("correction skipped" in line for line in out)


def test_a_deleted_message_is_not_reposted():
    ch = _Channel(555, existing=[])
    api = _Api([_row(9, 555, "corrected", revision=2, posted_revision=1,
                     message_id="4242")])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())
    assert ch.sent == []
    assert not [c for c in api.calls if c[1].endswith("/ack")]


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
    assert not [c for c in api.calls if c[1].endswith("/ack")]
    assert any("ambiguous" in line for line in out), out


def test_two_identical_ROWS_with_one_message_bind_nothing():
    """TWO rows whose sent text is byte-identical, and ONE message left.

    Exactly-one is only exactly-one because it is evaluated one row at a time:
    each row's own scan sees a single hit, and the row that happens to run
    first takes the message. It has a 50% chance of being right and no way to
    tell, and the wrong half edits a correct message into another entry's
    text. Ownership is what is ambiguous, so BOTH rows refuse: two correct old
    messages stay up, nothing is sent, nothing is bound."""
    only = _Msg(31, "the shared body", _Channel.BOT_ID)
    ch = _Channel(555, existing=[only])
    api = _Api([
        _row(1, 555, "first correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body"),
        _row(2, 555, "second correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body"),
    ])
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert only.edits == [], (
        "one of two indistinguishable rows took the surviving message: %s"
        % only.edits)
    assert not [c for c in api.calls if c[1].endswith("/ack")], (
        "a row was bound or acked although its ownership is unknowable")
    assert sum("ambiguous" in line for line in out) == 2, out


def test_two_identical_ROWS_with_two_messages_bind_nothing():
    """The same pair with BOTH messages still there.

    Round two refused this case for the wrong reason — each row's own scan saw
    two hits — which is why removing one message was enough to make it bind
    arbitrarily. The refusal is now decided over the batch, so the number of
    surviving messages does not change the answer."""
    twin_a = _Msg(41, "the shared body", _Channel.BOT_ID)
    twin_b = _Msg(42, "the shared body", _Channel.BOT_ID)
    ch = _Channel(555, existing=[twin_a, twin_b])
    api = _Api([
        _row(1, 555, "first correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body"),
        _row(2, 555, "second correction", revision=2, posted_revision=1,
             message_id=None, fingerprint="the shared body"),
    ])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert twin_a.edits == [] and twin_b.edits == []
    assert not [c for c in api.calls if c[1].endswith("/ack")]


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
    assert [c[2] for c in api.calls if c[1].endswith("/ack")] == [
        {"post_id": 9, "revision": 2, "message_id": "61"},
        {"post_id": 9, "revision": 3, "message_id": "61"},
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
    assert len([c for c in api.calls if c[1].endswith("/ack")]) == 2
    assert any("still behind" in line for line in out), out


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
    assert [c[2] for c in api.calls if c[1].endswith("/ack")] == [
        {"post_id": 7, "revision": 1, "message_id": str(ch.sent[0].id)},
        {"post_id": 7, "revision": 2, "message_id": str(ch.sent[0].id)},
    ]


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
    acked = [c[2]["post_id"] for c in api.calls if c[1].endswith("/ack")]
    assert acked == [1], acked


# ── 7b. The four mixed-version states ───────────────────────────────────────
#
# 338, the api and the bot are deployed in that order, so at any moment one of
# four combinations is live. Each gets its own test, named for the state, so a
# reader can check the set is complete rather than infer it:
#
#   OLD api + OLD bot   the rows that state LEAVES BEHIND, met by the new pair
#                       -> test_state_old_api_old_bot_leaves_a_row_the_new_pair_adopts
#   NEW api + OLD bot   a bot that cannot name a revision or report an id
#                       -> test_state_new_api_old_bot_is_recorded_without_a_revision
#                          (and its DSN half, test_a_legacy_ack_records_only_what_it_can_prove)
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
    nothing asserts the endpoint really returns it, so this fixture is a state
    the endpoint produces rather than one this file invented)."""
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
    assert [c[2] for c in api.calls if c[1].endswith("/ack")] == [
        {"post_id": 1, "message_id": "4242", "bind_only": "true"},
        {"post_id": 1, "revision": 1, "message_id": "4242"},
    ], "the row was not bound and acked at the revision that is on Discord"


def test_state_new_api_old_bot_is_recorded_without_a_revision():
    """NEW api + OLD bot, from the bot side of the wire.

    That bot sends no `revisions` flag, so this api answers it with the
    fire-once set and it behaves exactly as before — it acks with the post id
    and nothing else. What the api does with that ack (record the delivery,
    record revision 1 only while the content proves it, and never claim a
    correction the bot could not have seen) is asserted against the real
    statement in test_a_legacy_ack_records_only_what_it_can_prove.

    Here the upgraded bot then MEETS the row that ack produced — delivered, no
    revision, no id — with the fingerprint the api derives, and finishes it."""
    live = _Msg(77, "sent by the old bot", _Channel.BOT_ID)
    ch = _Channel(555, existing=[live])
    api = _Api([_row(3, 555, "sent by the old bot", revision=1,
                     posted_revision=None, message_id=None,
                     fingerprint="sent by the old bot",
                     posted_at=_DELIVERED_AT)])
    ns = _bot_ns(api, _Bot({555: ch}))
    asyncio.run(ns["poll_channel_posts"]())

    assert ch.sent == []
    assert [c[2] for c in api.calls if c[1].endswith("/ack")] == [
        {"post_id": 3, "message_id": "77", "bind_only": "true"},
        {"post_id": 3, "revision": 1, "message_id": "77"},
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
    assert not [c for c in api.calls if c[1].endswith("/ack")]
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
    assert [c[2] for c in api.calls if c[1].endswith("/ack")] == [
        {"post_id": 1, "message_id": str(ch.sent[0].id)}]


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

    bound = [c[2] for c in api.calls
             if c[1].endswith("/ack") and c[2].get("bind_only")]
    assert bound == [{"post_id": 9, "message_id": "4242", "bind_only": "true"}]
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
    assert [c[2] for c in api2.calls if c[1].endswith("/ack")] == [
        {"post_id": 9, "revision": 2, "message_id": "4242"}]


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
    assert [c for c in api.calls if c[1].endswith("/ack")] == [
        ("POST", "/internal/channel-posts/ack",
         {"post_id": 2, "revision": 1, "message_id": str(ch.sent[0].id)})]
