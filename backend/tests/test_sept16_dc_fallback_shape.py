"""Structural pins for the deferred 2v2 disconnect fallback (886bed8 round 4).

The orderings themselves are proved against a real PostgreSQL in
test_sept16_dc_fallback_orderings.py, which skips without a DSN. This file
carries the claims that are properties of the SOURCE rather than of a run, and
it runs everywhere:

  * the deferred branch is positioned so that no rating, gold or team_matches
    write is REACHABLE with is_fallback set -- a property of where the branch
    sits, not of the zero point totals a fallback happens to carry (#342);
  * the marker is stamped with clock_timestamp() and not NOW();
  * the sweep re-locks and re-checks, and cannot rate anything;
  * the sweep is registered as a PRIMARY-only scheduler and as a janitor
    self-test root;
  * nothing awaits between the sweep's post-lock live-game veto and its
    settlement write, so the veto cannot be read stale (round-4 HIGH);
  * a caller that must not mutate has its own ROUTE rather than a flag on the
    mutating one -- the route holds no write, and the state endpoint has no
    lifecycle parameter left to ignore;
  * the docstrings that describe these paths say what the tree does (#302).
"""

import ast
import os
import pathlib
import re
import subprocess

import pytest


API = pathlib.Path(__file__).resolve().parents[1] / "api" / "main.py"
SRC = API.read_text(encoding="utf-8")
LINES = SRC.splitlines()
TREE = ast.parse(SRC)


def span(name):
    """Source lines of one top-level def, as a list. Fails loudly if absent.

    A span, never the whole file: an occurrence count taken file-wide answers a
    different question than the one being asked and cannot fail usefully
    (#432).
    """
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return LINES[node.lineno - 1:node.end_lineno]
    raise AssertionError(f"{name} is not a top-level def in main.py")


def code_only(lines):
    """Drop comment-only lines, so a count measures code and not prose."""
    return [ln for ln in lines if not ln.lstrip().startswith("#")]


def first_index(lines, needle):
    for i, ln in enumerate(lines):
        if needle in ln:
            return i
    return -1


def absent_at(needle, haystack, where=""):
    """An `x not in <whole file>` check whose FAILURE is bounded.

    pytest explains a failed `x not in y` for two strings by diffing y against
    y with x cut out (`_notin_text` -> `_diff_text` -> difflib). The haystacks
    here are whole source files, and several are collapsed onto ONE line
    first, so that diff is a character-level pass over a pair of 2.5 MB lines:
    quadratic. The round-7 control that reddens the marker-clear claim spent
    24 minutes at 100% of a core inside that diff and printed nothing before
    it was stopped -- red, eventually, is not evidence anyone can run.

    So the comparison is reduced to an INDEX: the failing assertion compares
    two integers, and the excerpt a reader needs is supplied here instead of
    being reconstructed by a diff. Use it in pairs:

        at, why = absent_at(needle, haystack, "main.py")
        assert at < 0, why

    Returns (index, detail); index is -1 when the needle is absent, which is
    the passing case.
    """
    at = haystack.find(needle)
    if at < 0:
        return -1, (where, needle, "")
    return at, (where, needle, haystack[max(0, at - 70):at + len(needle) + 70])


# ── The report endpoint ──────────────────────────────────────────────────


def test_report_dc_takes_is_fallback_as_an_unsigned_default_false_input():
    body = span("team_series_report_dc")
    sig = [ln.strip() for ln in body if "is_fallback" in ln and "Query(" in ln]
    assert sig == ["is_fallback: bool = Query(False),"], sig
    # Unsigned: the DC canonical is frozen at reporter:series:dc_player:dc, so
    # the flag must NOT appear in the signature check's input.
    verify = span("_verify_team_dc_hmac")
    assert "is_fallback" not in "\n".join(verify)


def test_the_deferred_branch_precedes_every_rating_and_gold_write():
    body = code_only(span("team_series_report_dc"))
    branch = first_index(body, "if is_fallback:")
    assert branch >= 0, "the deferred branch is gone"
    ret = first_index(body, '"status": "deferred"')
    assert branch < ret
    for later in ("_complete_team_series_with_ratings(",
                  "INSERT INTO team_matches",
                  "SET status = 'dc_incomplete'"):
        at = first_index(body, later)
        assert at > ret, f"{later} is not after the deferred return (at {at}, return at {ret})"


def test_the_deferred_branch_sits_after_every_validation_it_must_keep():
    body = code_only(span("team_series_report_dc"))
    branch = first_index(body, "if is_fallback:")
    for earlier in (
        "FOR NO KEY UPDATE",                      # the row lock
        'reason": "dc_room_mismatch"',            # room fence
        'reason": "dc_after_resume"',             # post-relock fence
        "_assert_no_service_subject(",            # service-subject assertion
        "DC'd player isn't part of this series",  # dc-team resolution
        "reporter must be a member of the non-DC team",   # membership bind
    ):
        at = first_index(body, earlier)
        assert 0 <= at < branch, f"{earlier} does not precede the deferred branch"


def test_the_marker_is_stamped_on_the_post_lock_clock():
    body = span("team_series_report_dc")
    marker = [ln for ln in body if "dc_fallback_at = COALESCE" in ln]
    assert len(marker) == 1, marker
    assert "clock_timestamp()" in marker[0]
    # NOW() is frozen at transaction start and this handler waits on a row
    # lock; the marker must not carry a pre-wait time (#277).
    assert "NOW()" not in marker[0]


def test_the_deferred_return_is_distinguishable_from_an_old_servers_answer():
    # An api that predates the flag answers 200 and IGNORES the flag (bug #266,
    # learning #422). What that 200 proves is ONE thing: the answering box
    # predates the field. It proves nothing about settlement -- the old build
    # took whichever of its own branches the report matched, and on this build
    # two of the five non-deferring exits settle while the other three decide
    # nothing. The caller's only discriminator is the response body, so the
    # deferred status string must not be one the old code returns.
    body = "\n".join(span("team_series_report_dc"))
    assert '"status": "deferred"' in body
    assert '"deferred": True' in body
    assert body.count('"status": "deferred"') == 1


def test_the_report_docstring_no_longer_claims_two_outcomes():
    # The endpoint has a third disposition now; a docstring asserting the old
    # count is a claim the tree does not keep (#302, #351).
    doc = ast.get_docstring(
        next(n for n in TREE.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == "team_series_report_dc"))
    assert "Two outcomes" not in doc
    assert "Three outcomes" in doc
    assert "DEFERRED" in doc


# ── The sweep ────────────────────────────────────────────────────────────


def test_the_sweep_relocks_and_rechecks_inside_the_transaction():
    body = code_only(span("_team_dc_fallback_sweep_once"))
    joined = "\n".join(body)
    # One locked re-read, in the same mode the report handler takes (#202).
    # Comment lines are stripped first: the prose above the statement names the
    # mode deliberately, and a count that included it would measure the
    # comment (#432).
    assert joined.count("FOR NO KEY UPDATE") == 1
    assert "FOR UPDATE\n" not in joined and "FOR UPDATE " not in joined
    # The predicate is re-checked under that lock, and again in the UPDATE's
    # own WHERE -- two independent guards, both required (#208).
    assert 'locked["status"] not in ("active", "dc_paused")' in joined
    assert 'not locked["past_bound"]' in joined
    assert joined.count("AND status IN ('active', 'dc_paused')") == 1


def test_the_sweep_measures_the_bound_on_the_same_clock_as_the_marker():
    joined = "\n".join(span("_team_dc_fallback_sweep_once"))
    # Discovery and the locked re-read, both on clock_timestamp().
    assert joined.count("clock_timestamp() - make_interval(secs => :bound)") == 2
    assert "NOW()" not in joined


def test_the_sweep_keeps_the_live_game_veto():
    joined = "\n".join(span("_team_dc_fallback_sweep_once"))
    # TWO evaluations: a cheap pre-lock filter and the post-lock decision. The
    # ORDER of the two is pinned separately, in
    # test_the_liveness_veto_is_re_evaluated_after_the_lock_is_held.
    assert joined.count("_group_game_in_progress(str(sid))") == 2
    # The conservative variant, per that helper's own caller contract: a
    # janitor closer that re-fires every tick must veto on a young process.
    assert "_group_game_positively_live" not in joined


def test_the_service_subject_refusal_skips_the_row_not_the_batch():
    # Letting it propagate would abort the rest of the batch every tick for as
    # long as the offending row is due, which starves the other candidates.
    body = code_only(span("_team_dc_fallback_sweep_once"))
    at = first_index(body, "await _assert_no_service_subject(")
    assert at > 0
    assert body[at - 1].strip() == "try:"
    after = body[at:at + 10]
    assert any("except HTTPException:" in ln for ln in after), after
    assert any(ln.strip() == "continue" for ln in after), after
    # It now runs with the row lock HELD, so skipping the row has to release
    # it: a bare `continue` would carry the lock through the rest of the batch
    # and into the caller's session.
    refusal = after[first_index(after, "except HTTPException:"):]
    assert any(ln.strip() == "await db.commit()" for ln in refusal), refusal


def test_the_sweep_cannot_rate_or_pay_anything():
    joined = "\n".join(span("_team_dc_fallback_sweep_once"))
    for forbidden in ("_complete_team_series_with_ratings",
                      "_reconcile_team_series_bets",
                      "status = 'completed'",
                      "glicko"):
        assert forbidden not in joined, forbidden
    # The only status it can write.
    writes = re.findall(r"SET status = '(\w+)'", joined)
    assert writes == ["dc_incomplete"], writes


def test_the_sweep_is_a_primary_only_scheduler():
    lifespan = "\n".join(span("lifespan"))
    assert lifespan.count('_supervised("team_dc_fallback_sweep"') == 1
    primary = lifespan.index("booting as PRIMARY")
    reg = lifespan.index('_supervised("team_dc_fallback_sweep"')
    assert reg > primary, "the sweep is registered outside the primary branch"
    # It must not also be started on the replica path.
    replica = lifespan.index("BOOTING AS READ REPLICA")
    assert replica < primary


def test_the_sweep_is_a_janitor_selftest_root():
    # Its SQL names a column migration 326 adds; the boot-time EXPLAIN is what
    # makes a migration-after-api deploy loud instead of silent.
    roots = next(n for n in TREE.body
                 if isinstance(n, ast.Assign)
                 and getattr(n.targets[0], "id", "") == "_JANITOR_SELFTEST_ROOTS")
    names = {e.elts[1].value for e in roots.value.elts}
    assert "team_dc_fallback_sweep_loop" in names


# ── The read-only status ROUTE (H1 server side) ──────────────────────────
#
# Round 4 made the read-only guarantee a PARAMETER of the mutating endpoint,
# and an unknown parameter is exactly what a box that predates it answers 200
# while ignoring (bug #266, learning #422). Round 5 makes it a separate route,
# because a box that lacks a route cannot answer on it.

ROUTE = '@app.get("/api/v1/team/series/{series_id}/status", tags=["Team Matches"])'
WRITE_TOKENS = ("UPDATE ", "INSERT ", "DELETE ", "db.commit(", "begin_nested(",
                "_reconcile_team_series_bets(", "_complete_team_series_with_ratings(")


def test_the_read_only_route_is_registered():
    assert ROUTE in SRC, "the read-only status route is not registered"
    # And it is a distinct path from the mutating one, not a rewrite of it.
    assert '@app.get("/api/v1/team/series/{series_id}/state", tags=["Team Matches"])' in SRC


@pytest.mark.parametrize("token", WRITE_TOKENS)
def test_the_read_only_route_performs_no_write(token):
    """No write of any shape inside the route's own span (#432).

    Parametrized so a failure NAMES the token that appeared rather than
    reporting a boolean. The live half -- that the statements the route
    actually puts on a connection are all SELECTs -- is in the orderings file,
    with the mutating state GET under the same recorder as the control that
    the recorder can see a write at all (#391).
    """
    code = code_only(span("team_series_status_readonly"))
    hits = [ln.strip() for ln in code if token in ln]
    assert hits == [], hits


def test_the_read_only_route_states_the_capability_in_its_own_body():
    code = code_only(span("team_series_status_readonly"))
    joined = "\n".join(code)
    # The client treats an answer without this key as no answer. It is the
    # whole capability negotiation: proven per RESPONSE, by the box that
    # produced it, never advertised in advance.
    assert '"readonly": True,' in joined, joined


# ── The deferral state on the read-only route (the banner's whole input) ─
#
# The three names below are the CROSS-LANE CONTRACT's, written once on this
# lane. The client reads exactly these and carries no name of its own; a name
# that appears on one lane and not the other is a finding on both (#341, #444).

BANNER_FIELDS = ("dc_deferred", "dc_deferred_seconds_remaining",
                 "dc_deferred_bound_seconds")


def status_route_response_keys():
    """Every key the read-only route's response literal carries, in order."""
    code = code_only(span("team_series_status_readonly"))
    return [m.group(1) for m in
            (re.match(r'\s*"([a-z0-9_]+)":', ln) for ln in code) if m]


def test_the_status_route_emits_the_deferral_state():
    keys = status_route_response_keys()
    for f in BANNER_FIELDS:
        assert f in keys, (f, keys)
    # Still the one capability key, and still first: a reader that does not
    # see it parses nothing out of the body at all.
    assert keys[0] == "readonly", keys


def test_the_deferral_fields_are_derived_from_the_row_and_the_one_bound():
    """No second literal and no second clock (#342, #426).

    The bound reaches this route as the module constant, bound into the same
    SELECT that reads the marker; the remaining time is measured with
    clock_timestamp(), the clock that stamped dc_fallback_at and the clock the
    sweep measures the bound on. A copy of 420 here, or a Python-side
    subtraction against the api process clock, would make two numbers out of
    one (#431) -- and would drift by whatever the api-to-database skew is.
    """
    code = code_only(span("team_series_status_readonly"))
    joined = "\n".join(code)
    assert "_DC_FALLBACK_DEFER_SECONDS" in joined
    assert '"bound": float(_DC_FALLBACK_DEFER_SECONDS)' in joined, joined
    # No second spelling of the bound anywhere in the route.
    assert not re.search(r"(?<![\w.])420(?![\w.])", joined), joined
    # dc_deferred repeats the SWEEP's predicate, read off the same row.
    assert "dc_fallback_at IS NOT NULL" in joined
    assert "AND status IN ('active', 'dc_paused')) AS dc_deferred" in joined
    # The deadline is the marker plus the bound, measured on the row's clock.
    assert "make_interval(secs => :bound)" in joined, joined
    assert "clock_timestamp()" in joined, joined
    # Floored, not clamped afterwards in Python only: a negative remaining
    # time never leaves the database.
    assert "GREATEST(0, EXTRACT(EPOCH FROM (" in joined, joined
    # And the python side reads the two derived columns rather than
    # recomputing either of them.
    assert 'bool(r["dc_deferred"])' in joined, joined
    assert 'int(r["dc_deferred_seconds_remaining"] or 0)' in joined, joined
    assert "datetime.now" not in "\n".join(
        ln for ln in code if "dc_deferred" in ln)


def test_the_route_docstring_states_the_migration_dependency_it_created():
    """A guarantee in a comment is a claim about the whole state space (#351).

    The SELECT reads dc_fallback_at with no savepoint and no fallback branch,
    so an api carrying this route on a box without migration 326 answers 500.
    That is the deploy order's reason and it is stated where the reader of the
    SELECT is, not only in a notes file nobody re-reads.
    """
    doc = ast.get_docstring(node_named("team_series_status_readonly"))
    assert "MIGRATION 326" in doc.upper(), doc
    assert "UndefinedColumn" in doc, doc
    # And the refusal is priced at what it actually costs, not at "the banner".
    assert "WHAT A REFUSAL COSTS" in doc, doc
    # THE HEADING IS NOT THE CLAIM. A heading survives any rewrite underneath
    # it, so the superseded banner-only pricing could return with this check
    # still green -- a check keyed on something merely correlated with the
    # property it is named for (#732, #342). What is bound is the CONTENT: the
    # three things the tab refreshes from this answer, the latch, the explicit
    # statement that pricing the refusal at the banner alone understates it,
    # and the half that says what a refusal does NOT cost. A rewording that
    # keeps those meanings keeps this green; the banner-only claim carries
    # none of them.
    tail = re.sub(r"\s+", " ", doc[doc.upper().index("WHAT A REFUSAL COSTS"):])
    for needed in ("series status", "series score", "colour", "dark",
                   "understates", "banner"):
        assert needed in tail, (needed, tail)
    assert re.search(r"does NOT cost", tail), tail
    assert re.search(r"nothing here writes", tail), tail


# ── The cross-lane binding: one field list, read off BOTH trees ──────────
#
# This check was first written behind
#   @pytest.mark.skipif(not os.environ.get("SCR_CROSS_LANE_CLIENT_ROOT"))
# and nothing in this repository sets that name: not this directory's
# conftest, not a pytest.ini / setup.cfg / pyproject that does not exist, not
# a CI file. It was therefore a SKIP in every ordinary run -- it is the one
# skip both runs of the suite of record reported -- and it executed only
# inside the mutation harness, which set the variable itself. A test behind a
# skip has never run, so neither has any improvement made to it (#715), and a
# guard that is never collected reads exactly like one that passed (#664).
#
# What replaces it resolves a client tree AT RUN TIME and FAILS when it cannot
# find one. That is the direction the client lane's twin already fails in, so
# the two halves of one binding no longer fail in opposite directions (#341,
# #444). It matters most on the MERGED artifact, where this repository is
# itself a candidate: a field renamed in the route and left alone in the
# client parse reddens here, on main, with nothing set.
#
# The candidate ORDER and the branch-name rule below are the cross-lane
# contract's (§7.4.1c) and the other lane spells them the same way. A rule one
# lane keeps and the other does not is how two halves of one contract drift
# while each reads correct on its own (#341, #444).

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# The qualifying marker for "this tree carries the client half" is the ROUTE'S
# OWN PATH -- a contract literal both lanes must spell identically -- and
# never a field NAME. A name-keyed marker would step past the very tree whose
# rename this test exists to catch and measure some other checkout instead,
# which is a check bound to something merely correlated with the property
# (#732).
# Quotes are ALLOWED inside the span and newlines are not: a client that
# concatenates -- baseUrl + "/api/v1/team/series/" + id + "/status" -- builds
# the same URL as one that interpolates, and a discriminator that admitted
# only one spelling would answer "not the client half" about a tree that is
# (#441: a check keyed on formatting rather than on the operation).
_STATUS_ROUTE_CALL = re.compile(r'/api/v1/team/series/[^\r\n]{0,60}/status')
_CLIENT_LANE_BRANCH = "claude/sept16-client-r2"


# The two sources a supplied client representation must contain. A candidate
# the caller NAMED is answered about itself: if one of these is absent the
# resolver refuses by name instead of trying the next tree, because a
# fall-through answers about a checkout the caller never chose (#342, #447).
NAMED_CLIENT_SOURCES = ("ApiClient.cs", "NativeUI.cs")


def _client_sources_in(root):
    """(sources, layout) for one candidate tree, in either layout it can have.

    TWO LAYOUTS, because the two things this resolver is ever pointed at do
    not share one. A CHECKOUT carries the client half under `plugin/`. A
    frozen REVIEW COPY is a directory of .cs files and nothing else -- it has
    no repository around it and never had one. Round 6 knew only the first, so
    the frozen copy the review supplied resolved to zero sources, the binding
    fell through to the next candidate, and the check answered about a tree
    nobody had chosen while reading as a resolution error (#342).
    """
    root = pathlib.Path(root)
    try:
        nested = sorted((root / "plugin").glob("*.cs"))
    except OSError:
        nested = []
    if nested:
        return nested, "a checkout carrying plugin/"
    try:
        direct = sorted(root.glob("*.cs"))
    except OSError:
        direct = []
    if direct:
        return direct, "a directory of .cs sources, taken as itself"
    return [], "no .cs sources"


def _missing_named_sources(sources):
    have = {p.name for p in sources}
    return [n for n in NAMED_CLIENT_SOURCES if n not in have]


def _carries_the_client_half(root):
    """(sources, carries) for one candidate tree: do its sources call the route."""
    sources, _layout = _client_sources_in(root)
    for p in sources:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _STATUS_ROUTE_CALL.search(txt):
            return sources, True
    return sources, False


def _worktrees_on_branch(listing, branch):
    """The paths in a `git worktree list` listing that are ON `branch`.

    A pure function over the listing TEXT, so the rule can be exercised
    against lines this machine does not currently carry -- a rule that can
    only be checked by whatever worktrees happen to exist is a check that
    cannot fail on the case it exists for (#342).

    `git worktree list` prints `<path> <sha> [branch]` for an attached
    worktree and `<path> <sha> (detached HEAD)` for one checked out at a bare
    sha, so the bracket carries both the branch name and the attached/detached
    answer. The match is EXACT and never a substring: a substring also matches
    a branch whose name merely BEGINS with the client lane's -- an older or
    forked copy answering for the live one with nothing in the output to say
    so -- and a detached pin, which on this machine calls the status route
    while reading none of the fields, prints no bracket and is excluded by the
    same rule a second way.
    """
    out = []
    for ln in listing.splitlines():
        m = re.search(r"\[([^\]]+)\]\s*$", ln.strip())
        if m and m.group(1).strip() == branch:
            out.append(ln.split()[0])
    return out


def _client_lane_candidates():
    """([(root, how, binding)], already_tried) -- the candidate list itself.

    EXTRACTED SO EXCLUSIVITY IS OBSERVABLE. The list used to be built inside
    the resolver, and the only way a check could see it was the resolution
    message -- which, when a binding candidate refuses, returns before any
    other candidate is ever named. So a change that put candidates 2 to 4 back
    on the list while $SCR_CROSS_LANE_CLIENT_ROOT was set moved nothing any
    check could read: the control aimed at that change could not turn red, and
    a check that cannot fail is worse than no check (#342, #391). The list is
    returned here and counted by a test, so the exclusivity is asserted on the
    thing itself rather than on a consequence of it.

    `already_tried` carries one line for EVERY state in which the sibling scan
    was on the candidate list and produced no listing, and those states are
    two rather than one. The switch is the first: the scan was never started,
    and the line says NOT RUN. The second is a scan that WAS started and did
    not finish -- git exits nonzero, or the child cannot be started at all and
    the exit is whatever the platform reports for that -- and there the line
    says ATTEMPTED AND FAILED and names the condition it observed. Of the
    resolutions that had the scan on their list at all, only one whose scan
    ran to completion leaves the line out. The distinction is the whole point:
    a run that did not scan may never read as a run that scanned and found
    nothing (#438), and a child that never ran is not a measurement of
    anything (#304).

    A resolution taken with $SCR_CROSS_LANE_CLIENT_ROOT set carries no such
    line and is not an exception to any of that: the scan was never on its
    candidate list, and what that resolution names instead is the one tree it
    was pointed at. The scoping is spelled out because the sentence without it
    would be a guarantee about the whole state space written from the branch
    its author had in mind -- which is the defect this round spent three
    sittings on, and it was in this docstring on the first attempt.
    """
    cands = []
    scan = False
    scan_failed = ""
    env = os.environ.get("SCR_CROSS_LANE_CLIENT_ROOT")
    if env:
        cands.append((pathlib.Path(env),
                      "the tree $SCR_CROSS_LANE_CLIENT_ROOT names", True))
    else:
        cands.append((REPO_ROOT / "REVIEW-INPUT" / "client-lane",
                      "the review pin's client-lane copy", True))
        cands.append((REPO_ROOT, "this repository itself -- the merged tree",
                      False))
        # THE SIBLING SCAN, AND THE TWO STATES IN WHICH IT LISTS NOTHING. While
        # the two lanes are under separate review rounds, the other lane's
        # WORKING tree is being written by its own builder: reading it answers
        # about a tree that is mid-edit, and the review supplies a frozen
        # representation as candidate 1 for exactly that reason. A review run
        # sets SCR_CROSS_LANE_NO_SIBLING_SCAN and names the frozen copy. The
        # switch removes candidate 4 ONLY -- 1 to 3 are untouched, so the
        # binding still executes and still fails rather than skipping -- and
        # the resolution SAYS which candidate list produced it, because a run
        # that does not name its own candidates cannot be read back (#438).
        scan = not os.environ.get("SCR_CROSS_LANE_NO_SIBLING_SCAN")
        if scan:
            # THE SCAN'S OWN OUTCOME IS TAKEN, not assumed. A blanket catch
            # over an unchecked return code makes "git listed no client-lane
            # worktree" and "git never produced a listing" the same empty
            # result, and the second is not a result at all: this seat spent a
            # run of the evidence bundle discovering that, when a burst of
            # process-creation failures gave every child the platform's launch
            # status and an empty stdout, and each one was scored as though it
            # had been measured.
            try:
                proc = subprocess.run(
                    ["git", "-C", str(REPO_ROOT), "worktree", "list"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc.returncode != 0:
                    scan_failed = ("`git worktree list` exited %d"
                                   % proc.returncode)
                else:
                    for path in _worktrees_on_branch(
                            proc.stdout.decode("utf-8", "replace"),
                            _CLIENT_LANE_BRANCH):
                        cands.append((pathlib.Path(path),
                                      "the client lane's worktree", False))
            except Exception as exc:
                scan_failed = ("`git worktree list` could not be started: "
                               + type(exc).__name__)
    if env or (scan and not scan_failed):
        tried = []
    elif scan_failed:
        tried = ["the sibling-worktree scan (ATTEMPTED AND FAILED -- "
                 + scan_failed + ", so this resolution is NOT a scan that ran "
                 "and found no client-lane worktree)"]
    else:
        tried = [
            "the sibling-worktree scan (NOT RUN -- "
            "SCR_CROSS_LANE_NO_SIBLING_SCAN "
            "is set, so no worktree of the other lane was read)"]
    return cands, tried


def _client_lane_sources():
    """(sources, how) for a client tree carrying the banner, resolved at run time.

    NEVER a hardcoded path: a hardcoded target is a check that cannot fail
    where it matters (#342), and a workstation path written into the
    repository is a privacy defect besides. The order is the cross-lane
    contract's (§7.4.1c), spelled the same on both lanes, and the first
    candidate that actually CALLS the route wins:

      1. $SCR_CROSS_LANE_CLIENT_ROOT -- what a control runner points at a COPY
         of a client tree, so a control can be exercised without ever writing
         to the other lane's checkout. EXCLUSIVE: when it is set nothing else
         is tried, because a runner that names a tree is measuring THAT tree
         and falling through on a miss would report a result about a checkout
         the control never chose;
      2. <root>/REVIEW-INPUT/client-lane -- the review pin's own layout. An
         explicitly supplied copy beats an implicit one, which is why it sits
         above the next candidate rather than below it;
      3. THIS repository -- once both halves are merged the tree under test IS
         the client tree, and this is the candidate that makes the check live
         on merged main, in a fresh clone, on another machine and on CI, where
         no review pin and no sibling worktree ever existed;
      4. `git worktree list` -- a sibling worktree whose branch is EXACTLY the
         client lane's, which is how this runs while the two lanes are apart.

    Candidate 4 matches the branch exactly and never as a substring: the
    listing prints `<path> <sha> [branch]`, and a substring match also matches
    every read-only review pin checked out from that lane at an older sha -- a
    stale tree answering for the live one with nothing in the output to say
    so. A DETACHED worktree prints no bracket at all and is therefore never a
    candidate, which is the same rule a second way.

    Returns ([], how) when nothing qualifies, and the caller FAILS. `how`
    names the candidate and never a path: the only absolute path any file in
    this bundle may print is the production pin.
    """
    cands, tried = _client_lane_candidates()
    for root, how, binding in cands:
        # A SUPPLIED representation -- candidates 1 and 2 -- is BINDING: the
        # caller named it, so it is the tree this check answers about and a
        # miss on it is a refusal, never a reason to measure the next one. The
        # discovered candidates are not binding, because a repository that
        # simply has no client half yet is the ordinary pre-merge state and
        # not a defect.
        if binding and pathlib.Path(root).is_dir():
            sources, _layout = _client_sources_in(root)
            missing = _missing_named_sources(sources)
            if missing:
                return [], ("REFUSED -- " + how + " is the representation this "
                            "check was pointed at, and "
                            + ", ".join(how + "/" + m for m in missing)
                            + " is absent. Nothing else is tried: falling "
                            "through here would answer about a tree the caller "
                            "never chose.")
            if not _carries_the_client_half(root)[1]:
                return [], ("REFUSED -- " + how + " carries "
                            + ", ".join(NAMED_CLIENT_SOURCES)
                            + " and none of them calls the status route, so it "
                            "is not the client half it was offered as.")
        sources, carries = _carries_the_client_half(root)
        if carries:
            return sources, how
        tried.append(how + (" (no client sources)" if not sources
                            else " (does not call the route)"))
    return [], "no candidate tree called the status route: " + "; ".join(tried)


def _deferral_names_in(sources):
    """Every dc_deferred* JSON key these C# sources read."""
    read = set()
    for p in sources:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        read |= set(re.findall(r'"(dc_deferred[A-Za-z0-9_]*)"', txt))
    return read


def _stable_deferral_names(sources, attempts=3):
    """(names, stable) -- the set read twice the same, or the last try.

    While the two lanes are apart this reads a tree whose OWN builder is
    editing it, and a read that lands mid-write returns a file that is short a
    field -- which at the assertion below is indistinguishable from the two
    lanes genuinely disagreeing about a name. The other lane reported exactly
    that while these two rounds ran: a controls run naming a field as missing
    which the same file carried minutes later. Taken here as a report from
    that lane, not as something measured on this one. A difference is evidence only when the thing
    read was COMPLETE (#304), so two consecutive identical reads are required
    before anything is asserted on them. This says nothing about behaviour; it
    is about the READ, and an unstable one is reported as an unstable read
    rather than as a disagreement.
    """
    prev = _deferral_names_in(sources)
    for _ in range(max(1, attempts - 1)):
        cur = _deferral_names_in(sources)
        if cur == prev:
            return cur, True
        prev = cur
    return prev, False


def _field_disagreement(how, unknown, unread):
    """The ONE message both directions of a name disagreement print.

    A rename is two facts, and round 6's message carried one of them. Renaming
    `dc_deferred_bound_seconds` to `dc_deferred_bound_secs` on the client makes
    the new spelling a name this route does not emit AND makes the contract's
    name one the client no longer reads; the assertion that fired first printed
    `['dc_deferred_bound_secs']` and nothing else, so the reader was told a
    name they had never seen and left to work out which field it displaced.
    A refusal that does not name what is missing is not a report (#447).

    Both sets are therefore computed before either is asserted and both are
    named here whichever direction fires, together with the statement that this
    is a disagreement about FIELD NAMES. That last part is not decoration: the
    other way this check goes red is a representation it could not resolve, and
    the two need different work -- one is a cross-lane finding, the other is a
    runner pointed at the wrong directory (L11).

    An empty direction prints `(none)` rather than nothing at all, so the
    reader can tell "this side agreed" from "this side was not computed".
    """
    return (
        "CROSS-LANE FIELD DISAGREEMENT on " + how
        + " -- read by the client and NOT emitted by this route: "
        + (", ".join(sorted(unknown)) if unknown else "(none)")
        + "; fixed by the contract and NOT read by the client: "
        + (", ".join(sorted(unread)) if unread else "(none)")
        + ". Both directions are stated because a rename produces one of each. "
        "This is a disagreement about FIELD NAMES between two trees that were "
        "both read whole; it is not a representation this check failed to "
        "resolve.")


def test_a_field_disagreement_names_both_directions_and_says_which_it_is():
    """L11's second half: the RED has to be readable, not merely red.

    Bound as a unit on the message builder rather than through the cross-lane
    test, because reaching that assertion needs two trees and this needs none:
    a check that can only be exercised by arranging a whole environment is one
    nobody re-runs (#391 wants the negative control to be cheap enough to keep).
    """
    msg = _field_disagreement("a copy of the frozen client representation",
                              ["dc_deferred_bound_secs"],
                              ["dc_deferred_bound_seconds"])
    # The spelling the client carries, and the contract name it displaced.
    assert "dc_deferred_bound_secs" in msg, msg
    assert "dc_deferred_bound_seconds" in msg, msg
    # ...and the reader is told which of this check's two failure kinds it is.
    assert "FIELD DISAGREEMENT" in msg, msg
    assert "not a representation this check failed to resolve" in msg, msg
    # An agreeing direction says so. The negative control for the sentence
    # above: with one side empty the message must still name the other.
    only_one = _field_disagreement("a copy", [], ["dc_deferred"])
    assert "(none)" in only_one, only_one
    assert "dc_deferred" in only_one, only_one


def test_every_deferral_field_the_client_reads_is_one_this_route_emits():
    """CROSS-LANE, AND IT FAILS RATHER THAN SKIPPING.

    The lenses grep both trees for the same literals; this makes that
    comparison a test, so a client reading `dc_deferred_remaining_seconds` --
    a plausible paraphrase this route does not emit -- reddens here instead of
    rendering a silent zero in front of a player. Neither lane can see the
    defect by reading its own half: the client would parse a key nobody sends,
    the server would ship a field nobody reads, and the feature would be inert
    with healthy logs at both ends (#438).

    WHAT A FAILURE HERE MEANS, in the three shapes it takes. "not checked" --
    no reachable tree calls this route, and the message says which candidates
    were tried; that is a real finding wherever the tree under test carries
    a `plugin/` directory at all, because on the merged artifact this
    repository is itself a candidate. A checkout of `backend/` alone has no
    client half to find and would report this for a reason that is not a
    defect -- which is the one place this message needs reading before it
    is believed. "not
    read whole" -- the tree changed under two consecutive reads, which while
    the lanes are apart means its own builder was mid-write. "checked and
    disagreed" -- a name lives on one lane only. All three are failures on
    purpose: a skip and a pass are one line apart in a summary and read the
    same way.
    """
    sources, how = _client_lane_sources()
    assert sources, (
        "THE CROSS-LANE BINDING WAS NOT CHECKED -- " + how + ". Offer a client "
        "checkout in $SCR_CROSS_LANE_CLIENT_ROOT, or run this where both "
        "halves live in one tree. This fails rather than skipping because a "
        "skip is indistinguishable from a pass once it is a summary line "
        "(#715, #664).")
    emitted = set(status_route_response_keys())
    read, stable = _stable_deferral_names(sources)
    assert stable, (
        "THE CROSS-LANE BINDING WAS NOT READ WHOLE -- two consecutive reads of "
        + how + " disagreed, so its builder is writing it. A difference is "
        "evidence only when the thing read was complete (#304); this is a "
        "statement about the read, not about the two lanes.")
    # This tree CALLS the route, so it must read the deferral state out of the
    # answer. Calling it and parsing none of the three is the inert shape: the
    # banner off for every deferred series, one warning line per series, and
    # nothing anywhere that errors (#438).
    assert read, ("this tree calls the read-only status route and reads no "
                  "dc_deferred* field out of the answer -- " + how)
    # Every name it reads is one this route emits, and all three names the
    # contract fixes are read -- not merely a subset of them. The second is the
    # other direction of the same disagreement: a field the route emits and the
    # client quietly stops reading leaves no name mismatched anywhere, so
    # nothing else in either tree would notice it. BOTH are computed before
    # either is asserted so that whichever fires prints the whole picture; the
    # rename this test was written for lands in both sets at once.
    unknown = read - emitted
    unread = set(BANNER_FIELDS) - read
    disagreement = _field_disagreement(how, unknown, unread)
    assert not unknown, disagreement
    assert not unread, disagreement


def test_the_cross_lane_binding_is_not_gated_on_an_unset_environment_variable():
    """A check that cannot fail is worse than no check (#342, #431, #441).

    Read off THIS file rather than off a summary line, because the summary
    line is what hid the defect: this file's own result was "46 passed, 1
    skipped" in both runs of the suite of record, with the database and
    without it, and the 1 was this binding. The decorator is gone, the body
    raises no skip, and the resolver it calls offers more than one way in --
    so no single unset name can take the check out of the run again.
    """
    tree = ast.parse(pathlib.Path(__file__).resolve()
                     .read_text(encoding="utf-8"))
    name = "test_every_deferral_field_the_client_reads_is_one_this_route_emits"
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == name), None)
    assert fn is not None, name
    decorated = [ast.unparse(d) for d in fn.decorator_list]
    assert not [d for d in decorated
                if "skip" in d or "xfail" in d], decorated
    body = ast.unparse(fn)
    for gate in ("pytest.skip", "pytest.xfail", "skipif", "os.environ"):
        assert gate not in body, (gate, name)
    # No module-level name gates it either: the old cut hung the decorator on
    # one, so the module read green while the assertion never executed.
    assigned = {t.id for n in tree.body if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}
    assert "CROSS_LANE_ROOT" not in assigned, sorted(assigned)
    # And more than one candidate, so the check does not simply hang on the
    # same variable under a new spelling.
    resolver = ast.unparse(next(n for n in tree.body
                                if isinstance(n, ast.FunctionDef)
                                and n.name == "_client_lane_candidates"))
    assert resolver.count("cands.append") >= 3, resolver
    # The branch is matched EXACTLY. `in` would also match every read-only
    # review pin checked out from that lane at an older sha, and a stale tree
    # answering for the live one leaves nothing in the output to say so.
    # The resolver DELEGATES the branch rule; the rule itself is held
    # behaviourally by the test below, against a synthetic listing.
    assert "_worktrees_on_branch(" in resolver, resolver


def test_only_a_worktree_on_the_client_lane_branch_is_a_candidate():
    """The worktree candidate reads a BRANCH NAME, exactly.

    Four lines, every one of which this repository has actually carried: the
    live client lane, a read-only review pin checked out DETACHED from that
    lane at an older sha, a branch whose name merely begins with the client
    lane's, and this lane's own worktree. Only the first is a candidate.

    The pin is the case that matters. It calls the status route and reads none
    of the deferral fields, so admitting it would turn the binding red against
    a tree nobody is merging -- a red that says "the lanes disagree" while the
    lanes agree.
    """
    listing = "\n".join([
        "/w/live    1111111 [" + _CLIENT_LANE_BRANCH + "]",
        "/w/pin     2222222 (detached HEAD)",
        "/w/older   3333333 [" + _CLIENT_LANE_BRANCH + "-r1]",
        "/w/server  4444444 [claude/sept16-dc-server]",
    ])
    assert _worktrees_on_branch(listing, _CLIENT_LANE_BRANCH) == ["/w/live"]
    assert _worktrees_on_branch(listing, "claude/sept16-dc-server") == ["/w/server"]
    assert _worktrees_on_branch("", _CLIENT_LANE_BRANCH) == []


def test_the_environment_candidate_is_exclusive(monkeypatch, tmp_path):
    """A runner that names a tree is measuring THAT tree (contract §7.4.1c).

    Falling through to another checkout on a miss would report a result about
    a tree the control never chose -- and on a workstation carrying the other
    lane's live worktree the fall-through would find it and go GREEN, which is
    exactly the reading a control that points somewhere else is trying not to
    get.
    """
    monkeypatch.setenv("SCR_CROSS_LANE_CLIENT_ROOT", str(tmp_path))
    sources, how = _client_lane_sources()
    assert sources == [], how
    assert "SCR_CROSS_LANE_CLIENT_ROOT" in how, how
    # THE EXCLUSIVITY ITSELF, read off the candidate list rather than off a
    # consequence of it. The two assertions above pass on this workstation
    # whether the list holds one entry or four: the binding candidate refuses
    # before any other is reached, and no other candidate here carries a client
    # half that calls this route anyway. So a change that put candidates 2 to 4
    # back on the list while the variable is set would move neither of them,
    # and the control aimed at that change could not turn red -- which is the
    # same defect as a check that cannot fail (#342, #391). What follows is the
    # property, not a symptom of it.
    cands, _tried = _client_lane_candidates()
    assert [h for _r, h, _b in cands] == [
        "the tree $SCR_CROSS_LANE_CLIENT_ROOT names"], cands
    assert cands[0][2] is True, cands
    # With it unset the same call consults more than that one tree, so the
    # emptiness above is the exclusivity and not simply this machine.
    monkeypatch.delenv("SCR_CROSS_LANE_CLIENT_ROOT", raising=False)
    _, how_unset = _client_lane_sources()
    assert how_unset != how, (how, how_unset)
    assert len(_client_lane_candidates()[0]) > 1, _client_lane_candidates()[0]


def test_the_client_half_discriminator_answers_its_three_cases(tmp_path):
    """The resolver's one judgement, unit-tested against synthetic trees.

    The rest of the cross-lane check depends on this function answering "does
    this tree call the route" correctly, and on a workstation it is only ever
    asked about trees that happen to be lying around. A discriminator that is
    never shown a negative is not known to discriminate (#391), and this is
    the piece that decides whether the binding measures the merged artifact or
    steps past it, so it gets the three cases in writing and they run
    everywhere (#715).
    """
    # 1. No plugin directory at all -- not a client tree.
    assert _carries_the_client_half(tmp_path / "nothing") == ([], False)

    # 2. A plugin directory whose sources do NOT call the route. This is the
    #    server lane's own tree before the merge, and it must NOT be mistaken
    #    for the client half: the state endpoint's path is deliberately close.
    plug = tmp_path / "pre" / "plugin"
    plug.mkdir(parents=True)
    (plug / "ApiClient.cs").write_text(
        'string url = $"{baseUrl}/api/v1/team/series/{seriesId}/state";\n',
        encoding="utf-8")
    sources, carries = _carries_the_client_half(tmp_path / "pre")
    assert sources and carries is False, (sources, carries)

    # 3. A plugin directory that calls it -- the merged artifact's shape, and
    #    the interpolated spelling the client actually builds the URL with.
    plug = tmp_path / "post" / "plugin"
    plug.mkdir(parents=True)
    (plug / "ApiClient.cs").write_text(
        'string url = $"{baseUrl}/api/v1/team/series/{seriesId}/status";\n',
        encoding="utf-8")
    sources, carries = _carries_the_client_half(tmp_path / "post")
    assert carries is True and len(sources) == 1, (sources, carries)

    # 4. And the concatenated spelling, because a client that builds the same
    #    URL without interpolation is the same client half.
    (plug / "ApiClient.cs").write_text(
        'string url = baseUrl + "/api/v1/team/series/" + seriesId + "/status";\n',
        encoding="utf-8")
    assert _carries_the_client_half(tmp_path / "post")[1] is True


def test_an_unstable_read_of_the_other_lane_is_reported_as_unstable(tmp_path):
    """A file being written must not read as a field disagreement (#304).

    While the two lanes are apart this binding reads a tree whose own builder
    is editing it, and a truncated read is short a name -- the same shape, at
    the assertion, as the two lanes disagreeing. The other lane REPORTED
    exactly that: a red naming a field its own file carried minutes later.
    That is its report, not a measurement taken here.
    The guard is two consecutive identical reads, and it is tested here rather
    than trusted, because on a workstation it would otherwise only ever be
    exercised by a race nobody can schedule.
    """
    src = tmp_path / "ApiClient.cs"
    src.write_text('HasJsonKey(resp, "dc_deferred_seconds_remaining")\n',
                   encoding="utf-8")
    names, stable = _stable_deferral_names([src])
    assert stable and names == {"dc_deferred_seconds_remaining"}, (names, stable)

    # A source that answers differently on every read is what a mid-write file
    # looks like. A plain list would hand the caller the last one it happened
    # to see; this reports that it could not read the tree whole.
    class Wobbling(object):
        def __init__(self):
            self.n = 0

        def read_text(self, **kw):
            self.n += 1
            return '"dc_deferred_%d"' % self.n

    names, stable = _stable_deferral_names([Wobbling()])
    assert stable is False, names
    # ...and the caller's own assertion is the one that fails on it, before
    # any comparison with the route's keys is attempted.
    body = ast.unparse(next(
        n for n in ast.parse(pathlib.Path(__file__).resolve()
                             .read_text(encoding="utf-8")).body
        if isinstance(n, ast.FunctionDef)
        and n.name == "test_every_deferral_field_the_client_reads_is_one_this_route_emits"))
    # The needle is the first line of the field comparison as it is SPELLED
    # now. It was `read <= emitted` until the disagreement message was made to
    # name both directions; an ordering assertion keyed on a spelling that no
    # longer exists raises instead of judging, which is how this one announced
    # the rename rather than passing through it (#469).
    assert body.index("NOT READ WHOLE") < body.index("unknown = read - emitted"), body


def test_the_state_endpoint_has_no_lifecycle_parameter_left():
    # code_lines_of, not code_only: the docstring NAMES the deleted parameter
    # on purpose, and prose about a removal is not the removal (#302).
    code = code_lines_of(node_named("team_series_state"))
    joined = "\n".join(code)
    # The two mutating arms and their commits are unchanged and UNGATED again:
    # this endpoint is the assembly poll's lifecycle operation and nothing
    # else. Counted within THIS function's span (#432).
    assert len([ln for ln in code if "UPDATE team_series" in ln]) == 2
    assert len([ln for ln in code if "await db.commit()" in ln]) == 2
    assert not [ln for ln in code if re.search(r"\blifecycle\b", ln)], joined
    assert '"lifecycle"' not in joined
    # The signature is back to what production 0cc7f75 carries.
    assert ("async def team_series_state(series_id: str, "
            "db: AsyncSession = Depends(get_db)):") in joined


def test_the_state_docstring_says_the_get_writes_and_sends_readers_elsewhere():
    doc = ast.get_docstring(node_named("team_series_state"))
    assert "THIS GET WRITES" in doc
    assert "PollAssemblyStateLoop" in doc
    # It must name the route a read-only caller uses instead, or the deletion
    # of the flag reads as the feature being withdrawn.
    assert "/api/v1/team/series/{series_id}/status" in doc


@pytest.mark.parametrize("token", ["dc_fallback_at", "dc_fallback_player_id"])
def test_the_marker_columns_are_added_by_a_migration_on_disk(token):
    sql = (pathlib.Path(__file__).resolve().parents[1] / "sql"
           / "326_team_series_dc_fallback_at.sql").read_text(encoding="utf-8")
    assert f"ADD COLUMN IF NOT EXISTS {token}" in sql
    assert sql.strip().startswith("--")
    assert "\nBEGIN;" in sql and sql.rstrip().endswith("COMMIT;")


# ── The revival operation, counted across the whole file ─────────────────
#
# The first cut of this change cleared the marker in ONE of the two same-four
# adoption funnels, and the test that was supposed to hold it read the span of
# that one function -- so it could not fail on the other (#432, #330). What
# follows asks the question of the FILE: which functions revive a series, and
# does each of them clear the marker.
#
# KEYED ON THE OPERATION, NOT ON ITS SPACING. The previous cut of this census
# searched for the exact string "SET status = 'active'," -- one spelling, with
# one space either side of the '=' and a trailing comma. A third funnel that
# wrote the same UPDATE as "SET status='active' ," or split it across string
# pieces differently was absent from the census, so the check stayed green
# while the drift it exists to catch stood in the file. A check that cannot
# fail is worse than no check (#342, #431, #441).
#
# What is read instead is the SQL the function CARRIES: every string literal
# in its body (its docstring excluded), joined and whitespace-collapsed, then
# the UPDATE ... team_series spans within it, then the SET list of each. The
# negative control below feeds this census a module whose answer is known --
# a third revival in different spacing, calling no helper -- and requires it
# to be seen, beside a record of what the old needle saw of the same text.

def node_named(name):
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} is not a top-level def in main.py")


def code_lines_of(node):
    """A def's own lines with its DOCSTRING and comment lines blanked out.

    Prose about an operation is not the operation. Without this, a docstring
    that merely names the SQL it governs joins the set of functions that
    perform it and the count stops meaning anything.
    """
    lines = LINES[node.lineno - 1:node.end_lineno]
    if ast.get_docstring(node) is not None:
        d = node.body[0]
        lo, hi = d.lineno - node.lineno, d.end_lineno - node.lineno
        lines = lines[:lo] + [""] * (hi - lo + 1) + lines[hi + 1:]
    return [ln for ln in lines if not ln.lstrip().startswith("#")]


def functions_performing(needle):
    """Every top-level def whose own CODE contains `needle`, by name.

    Retained for the checks whose subject really is a LINE (a helper call by
    name). The operation censuses below do not use it.
    """
    return sorted(
        n.name for n in TREE.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(needle in ln for ln in code_lines_of(n)))


# The old needle, kept as a NAMED value rather than deleted, because the
# negative control's whole job is to show what it could not see (#342).
ROUND5_REVIVAL_NEEDLE = "SET status = 'active',"

_WS = re.compile(r"\s+")
_UPDATE_TEAM_SERIES = re.compile(
    r"\bUPDATE\s+team_series\b(.*?)(?=\bUPDATE\b|\bINSERT\b|\bDELETE\b|$)",
    re.I | re.S)
_SET_LIST = re.compile(r"\bSET\b(.*?)(?=\bWHERE\b|\bRETURNING\b|$)", re.I | re.S)
_ASSIGNS_ACTIVE = re.compile(r"(?<![\w.])status\s*=\s*'active'", re.I)
_ASSIGNS_DC_PLAYER_NULL = re.compile(r"(?<![\w.])dc_player_id\s*=\s*NULL", re.I)
_ASSIGNS_MARKER_NULL = re.compile(r"(?<![\w.])dc_fallback_at\s*=\s*NULL", re.I)


def sql_carried_by(node):
    """Every string literal in a def's body, joined and whitespace-collapsed.

    The SQL a function carries, read as text rather than as source lines: a
    statement re-indented, re-wrapped, or split across a different number of
    adjacent string pieces is the SAME text here. The docstring is dropped
    first -- prose about an operation is not the operation.
    """
    body = node.body
    if ast.get_docstring(node) is not None:
        body = body[1:]
    parts = []
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                parts.append(sub.value)
    return _WS.sub(" ", " ".join(parts))


def functions_updating_team_series(assignment, tree=None):
    """Top-level defs whose SQL assigns `assignment` in an UPDATE team_series.

    Deliberately GENEROUS at the margins: two statements in one function are
    joined, so a SET list that runs into the next statement's text can pull in
    that statement's assignments, and a CASE arm inside a SET list that
    compares a column to a literal reads as an assignment. Both directions
    over-report, which surfaces a function for a human to look at; under-
    reporting is what let a second funnel ship unhandled.
    """
    out = []
    for n in (tree or TREE).body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        sql = sql_carried_by(n)
        if any(assignment.search(s.group(1))
               for u in _UPDATE_TEAM_SERIES.finditer(sql)
               for s in _SET_LIST.finditer(u.group(1))):
            out.append(n.name)
    return sorted(out)


def test_every_funnel_that_revives_a_series_clears_the_deferral_marker():
    # The set is named, not counted loosely: a third funnel appearing here is a
    # thing to look at, not a number to bump.
    funnels = functions_updating_team_series(_ASSIGNS_ACTIVE)
    assert funnels == ["_team_relock_existing_series", "team_lobby_start"], funnels
    # "Revives a series" and "clears the DC fields" are ONE set, not two -- the
    # qualifier in the finding was 'the UPDATE ... that clears dc_player_id'.
    assert functions_updating_team_series(_ASSIGNS_DC_PLAYER_NULL) == funnels
    for name in funnels:
        code = code_lines_of(node_named(name))
        assert any("_team_clear_dc_fallback_marker(" in ln for ln in code), (
            f"{name} flips a series back to 'active' without clearing the "
            "deferral marker; the sweep will settle it again on its next tick")


# A third revival, written the way a different hand would write it: different
# spacing around every '=', no trailing comma after the first assignment, the
# statement split across string pieces at different points, and no call to the
# clearing helper. The census must SEE it; the round-5 needle must not.
_THIRD_FUNNEL_DECOY = '''
async def _team_rehost_revive_series(db, series_id):
    await db.execute(text(
        "UPDATE   team_series"
        "   SET   status='active'"
        "       , dc_player_id=NULL"
        "       , dc_team_remaining = NULL"
        " WHERE id = :sid"
    ), {"sid": series_id})
'''


def test_the_revival_census_sees_a_funnel_written_in_different_spacing():
    """NEGATIVE CONTROL for the census itself.

    A census is worth exactly what its filter can see, so the filter is run
    against a module whose answer is known. Without this, "the census reports
    two funnels" and "the census cannot report a third" are indistinguishable.
    """
    decoy_tree = ast.parse(_THIRD_FUNNEL_DECOY)
    seen = functions_updating_team_series(_ASSIGNS_ACTIVE, tree=decoy_tree)
    assert seen == ["_team_rehost_revive_series"], seen
    assert (functions_updating_team_series(_ASSIGNS_DC_PLAYER_NULL,
                                           tree=decoy_tree) == seen)
    # And the decoy carries no helper call, so the census finding it is what
    # makes the funnel test above go red on such a file.
    assert "_team_clear_dc_fallback_marker" not in _THIRD_FUNNEL_DECOY
    # What the round-5 needle saw of the same text: nothing. This is the
    # finding, stated as a measurement rather than as prose.
    assert ROUND5_REVIVAL_NEEDLE not in _THIRD_FUNNEL_DECOY


def test_no_revival_site_claims_the_marker_has_a_known_age():
    """The three copies of the revival claim say what the clear guarantees.

    Two of them used to assert the marker's age as an ABSOLUTE, in opposite
    directions -- the helper said it is never older than the bound, the
    migration header said it always is -- and neither followed from the
    revival. The clear reads no age, so the comments may not claim one. Both
    directions are NAMED at the two sites that reason about the age, which is
    what makes the claim a bound rather than an absolute: a site that reverts
    to one of them loses the other word and reddens here.
    """
    doc = ast.get_docstring(node_named("_team_clear_dc_fallback_marker"))
    assert "THE CLEAR IS UNCONDITIONAL" in doc, doc
    assert "YOUNGER than the bound" in doc and "leaves one OLDER" in doc, doc
    # Collapsed, because the claim wraps across comment lines and a sentence
    # is not less true for being re-wrapped.
    adopt = re.sub(r"[\s#]+", " ", "\n".join(span("team_lobby_start")))
    assert "The clear is unconditional for that reason" in adopt
    assert "the revival tells us nothing about the age" in adopt
    sql = (pathlib.Path(__file__).resolve().parents[1] / "sql"
           / "326_team_series_dc_fallback_at.sql").read_text(encoding="utf-8")
    assert "UNCONDITIONAL and reads no age" in sql, sql
    assert "a YOUNGER marker" in sql and "an OLDER one" in sql, sql


def test_the_liveness_helper_doc_matches_its_fresh_process_branch():
    """A doc that states the opposite of its own branch (#351, #302).

    The sweep's veto is built on this helper, and a reader who took the
    original first line at face value would expect a fresh process to settle
    rows immediately. It vetoes instead, deliberately -- the evidence map is
    empty after a restart because nothing has been heard yet, not because
    nobody is playing.

    AND THE CORRECTION MUST NOT BE A SECOND ABSOLUTE. The first cut of the
    fix replaced "returns false on a fresh process" with "Returns TRUE when
    the evidence is not yet trustworthy", stated without qualification, while
    the function's FIRST statement returns False for a falsy group id -- on a
    fresh process. Right about the case it was aimed at, wrong as the
    whole-state-space sentence it was written as, which is the same shape as
    the two revival-age absolutes deleted one row above (#351). So the doc is
    bound to the ORDER of the branches here, not merely to the existence of
    one of them: the falsy-id exit is the first statement, the age veto comes
    after it, and the doc says both in that order.
    """
    doc = ast.get_docstring(node_named("_group_game_in_progress"))
    node = node_named("_group_game_in_progress")
    # The TRUE claim is scoped to a named group -- never stated flat.
    m = re.search(r"returns TRUE while the evidence is not yet trustworthy",
                  doc, re.I)
    assert m, doc
    assert re.search(r"for a NAMED group", doc[:m.start()], re.I), doc
    # ...and the exit that makes the qualifier necessary is stated, with the
    # direction it answers in.
    assert re.search(r"empty group id is answered FALSE", doc), doc
    # THE ORDER, read off the AST rather than off a line number: the first
    # statement of the body is the falsy-id return, and the age veto is later.
    body = node.body[1:] if (node.body and isinstance(node.body[0], ast.Expr)
                             ) else node.body
    first = body[0]
    assert isinstance(first, ast.If), ast.unparse(first)
    assert ast.unparse(first) == "if not group_id:\n    return False", \
        ast.unparse(first)
    code = code_only(span("_group_game_in_progress"))
    i = first_index(code, "if not _in_match_evidence_trustworthy():")
    assert i >= 0, code
    assert any("return True" in ln for ln in code[i:i + 6]), code[i:i + 6]
    j = first_index(code, "if not group_id:")
    assert 0 <= j < i, (j, i)


def test_no_dc_file_names_a_superseded_bound():
    """Every "N s bound" in this batch's files is the bound that is committed.

    Two comments in the orderings file kept 120 after the constant moved to
    420, which is how a scenario described as past the bound is read as past
    the bound by the next person while being well inside it.
    """
    import main
    bound = str(main._DC_FALLBACK_DEFER_SECONDS)
    here = pathlib.Path(__file__).resolve().parent
    for name in ("test_sept16_dc_fallback_shape.py",
                 "test_sept16_dc_fallback_orderings.py"):
        txt = (here / name).read_text(encoding="utf-8")
        for m in re.finditer(r"(?<![\w.])(\d+)\s*s(?:econd)?s?\s+bound", txt,
                             re.I):
            assert m.group(1) == bound, (name, m.group(0))
        for m in re.finditer(r"bound is (\d+)", txt):
            assert m.group(1) == bound, (name, m.group(0))


def test_the_marker_clear_lives_in_one_savepointed_helper():
    code = code_lines_of(node_named("_team_clear_dc_fallback_marker"))
    joined = "\n".join(code)
    # Both columns, or a stale attribution survives the resume. Read off the
    # collapsed SQL rather than one spelling of the source line.
    helper_sql = sql_carried_by(node_named("_team_clear_dc_fallback_marker"))
    assert _ASSIGNS_MARKER_NULL.search(helper_sql), helper_sql
    assert re.search(r"(?<![\w.])dc_fallback_player_id\s*=\s*NULL", helper_sql,
                     re.I), helper_sql
    # Its own savepoint: a caught SQL error poisons the whole transaction under
    # asyncpg (#235), and neither resume may start failing because a deploy ran
    # before migration 326.
    at = first_index(code, "SET dc_fallback_at = NULL")
    assert any("begin_nested()" in ln for ln in code[max(0, at - 4):at]), code
    assert "begin_nested()" in joined
    # And the operation exists in exactly one place, so there is no second copy
    # to drift: the two call sites carry a call, never their own UPDATE.
    assert functions_updating_team_series(_ASSIGNS_MARKER_NULL) == [
        "_team_clear_dc_fallback_marker"]


# ── The bound ────────────────────────────────────────────────────────────


def test_the_bound_is_derived_from_the_assembly_ceiling_not_from_transport_alone():
    import main
    budget = main._DC_CLIENT_TRANSPORT_BUDGET_SECONDS
    hold = main._ASSEMBLY_DEADLINE_SECONDS
    # The bound covers the HOLD, the held report's own budget and one
    # re-election budget. The first cut was 120 s, derived from transport
    # alone; it fails this line, which is the point of having the line.
    assert main._DC_FALLBACK_DEFER_SECONDS >= hold + 2 * budget
    # The comment above the constant has to name the term it now includes,
    # because a derivation nobody can trace is a claim (#302).
    head = "\n".join(LINES[:node_named("_team_clear_dc_fallback_marker").lineno])
    assert "_ASSEMBLY_DEADLINE_SECONDS = 180" in head
    assert "WHAT THE DERIVATION DOES NOT COVER" in head


def test_the_sweep_does_not_consult_the_room_clock():
    """The 214 s "second refusal" is gone, constant and all.

    It could not refuse a row. An ordinary room is stamped when it is ISSUED,
    before the sitting that produces the marker, so a marker past 420 s always
    sat on a room past 214 s; and a continuation series carries a real room
    with a NULL room_issued_at, which made the term true on arrival. A check
    that cannot fail is worse than no check (#342, #431, #441), so it is
    deleted rather than patched (#310, #389).
    """
    import main
    assert not hasattr(main, "_DC_FALLBACK_ROOM_QUIET_SECONDS")
    code = code_only(span("_team_dc_fallback_sweep_once"))
    joined = "\n".join(code)
    assert "room_issued_at" not in joined, (
        "the sweep is reading the room clock again")
    assert "room_quiet" not in joined
    assert '"quiet"' not in joined
    # One time term remains, and it is named in both statements: the bound.
    assert joined.count("float(_DC_FALLBACK_DEFER_SECONDS)") == 2, joined


def flat_code_of(node):
    """A def's own code as ONE whitespace-normalized string.

    A per-LINE substring test answers "does any single line spell it this
    way", which is a question about formatting. The census below is about a
    COLUMN and the value written to it, so the span is flattened first: a
    respelling, a different amount of space around the `=`, or the column and
    its value landing on two lines of the same SQL string all still count
    (#619, #591 -- follow the value, never the spelling).
    """
    return re.sub(r"\s+", " ", " ".join(code_lines_of(node)))


# `room_issued_at` preceded by no word character and no dot, so `ts.room_issued_at`
# in a SELECT and `r["room_issued_at"]` in a read are not writes; then `=` and the
# bare token of whatever is written -- NOW, clock_timestamp, NULL, :bind.
ROOM_CLOCK_WRITE = re.compile(r"(?<![\w.])room_issued_at\s*=\s*([:\w]+)")


def functions_touching_the_room_clock():
    """{def name: the set of values it writes to room_issued_at}, file-wide.

    An SQL equality test on the column would land here too, as a value it
    appears to write. That is the direction this check is meant to fail in: a
    new use of the column shows up as an unexpected NAME and reddens the test,
    rather than being silently absent from a spelling-keyed census.
    """
    found = {}
    for n in TREE.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        vals = {m.group(1) for m in ROOM_CLOCK_WRITE.finditer(flat_code_of(n))}
        if vals:
            found[n.name] = vals
    return found


def test_every_room_issue_clears_the_deferral_marker():
    """What the room-issue operation OWES, asked of the FILE.

    What this test requires is that whoever stamps room_issued_at attempts the
    marker clear in the same breath. It is NOT what this docstring used to
    open with: an age relation between the marker and the room, held out as
    the property the sweep leans on now that its room term is gone. The clear
    is attempted under a savepoint that swallows what it raises, so no such
    relation is available to lean on, and the sweep's deletion of the room
    term is carried by the live-game veto instead. The requirement stands on
    its own without it: a funnel that stamps the clock without even attempting
    the clear is a funnel nothing would clear after. Counted file-wide,
    because the defect is a class and a span-local count could not see a third
    funnel (#432, #330, #351).

    Keyed on the COLUMN, not on one spelling of the statement that writes it.
    The first cut matched the literal line `room_issued_at = NOW()`, so a
    rematch or re-host funnel spelled `room_issued_at=clock_timestamp()`, or
    written across two lines of its SQL, would have left the census reading
    exactly ["team_queue_poll"] and the per-issuer check below would never
    have run on it -- silence for precisely the drift the test exists to
    catch (#342, #431, #441).
    """
    writers = functions_touching_the_room_clock()
    stampers = sorted(n for n, vals in writers.items() if vals != {"NULL"})
    clearers = sorted(n for n, vals in writers.items() if vals == {"NULL"})
    # The set is named, not counted: a new funnel is a thing to look at.
    assert stampers == ["team_queue_poll"], writers
    for name in stampers:
        code = code_lines_of(node_named(name))
        assert any("_team_clear_dc_fallback_marker(" in ln for ln in code), (
            f"{name} stamps room_issued_at without clearing the deferral "
            "marker; a marker filed against the previous sitting would then "
            "settle the new one")
    # And the only other writers of the column set it to NULL -- the two
    # resume funnels dropping the dead room. A third value would be a new
    # shape this reasoning has not been done for.
    assert clearers == ["_team_relock_existing_series", "team_lobby_start"], writers


def comment_block_above(func_name, needle):
    """The comment lines immediately ABOVE a line inside one def.

    A file-wide grep answers "does this sentence exist somewhere", which is a
    different question from "is this the sentence standing over that call".
    Walking up from the call establishes the adjacency by construction, so a
    paragraph that drifts to the other end of the function stops satisfying
    the check rather than continuing to (#432).
    """
    lines = span(func_name)
    hits = [i for i, ln in enumerate(lines) if needle in ln]
    assert len(hits) == 1, (func_name, needle, hits)
    out, j = [], hits[0] - 1
    while j >= 0 and lines[j].lstrip().startswith("#"):
        out.append(lines[j])
        j -= 1
    assert out, (func_name, needle, "no comment block above the call")
    return list(reversed(out))


def test_the_room_issue_clear_is_introduced_as_an_attempt_not_an_invariant():
    """The sentence standing over the room-issue clear, priced to the code.

    The block used to open with an absolute -- issuing a room clears the
    marker, therefore an age relation holds between marker and room -- and
    then contradict itself nine lines down with "expected", not "guaranteed".
    The helper attempts its UPDATE inside a savepoint and swallows what that
    raises, so the opening was the same defect the marker-clear doc had to be
    narrowed for, one screen away and in the file the claim check scans
    (#351, #432). What the block may say is what the call does, and what the
    sweep's room-term deletion actually rests on.
    """
    block = _collapsed("\n".join(comment_block_above(
        "team_queue_poll", "_team_clear_dc_fallback_marker(")))
    assert "ISSUING A ROOM ATTEMPTS THE DEFERRAL-MARKER CLEAR" in block, block
    assert ("NO READER MAY TREAT A MARKER AS NECESSARILY YOUNGER THAN THE "
            "ROOM") in block, block
    # The positive half is not enough on its own: the block has to say what
    # the sweep's deleted room term rested on, or the next reader is left
    # with a refusal and no replacement (#331). TWO sentences, because the
    # block has now carried two different WRONG attributions for that
    # deletion -- first this clear, then the live-game veto -- and the
    # correct answer is neither: the term could not refuse a row.
    assert ("WHAT MAKES THAT DELETION SAFE IS THE DELETED TERM'S OWN VACUITY"
            in block), block
    assert "LIVE-GAME VETO" in block, block
    # ...and the veto is priced as a bound, not offered as the replacement
    # guarantee the previous cut made of it.
    assert "a BOUND and not a guarantee" in block, block
    assert "swallows every exception" in block, block


# Which role in migration 326's writer enumeration each caller of the clearing
# helper plays. The two revival funnels are ONE role in that list; the
# room-issue write is its own. A caller that is not in this map is a role
# nobody has written the sentence for, which is the state the check refuses.
ROLE_OF_CLEARING_CALLER = {
    "_team_relock_existing_series": "a revival funnel clearing the marker",
    "team_lobby_start": "a revival funnel clearing the marker",
    "team_queue_poll": "the room-issue write in the queue poll",
}
# The two writers that end a deferral WITHOUT going through the helper: the
# in-bound real-totals report, which overwrites the attribution, and the sweep
# tick, which settles the row.
WRITERS_NOT_THROUGH_THE_HELPER = 2
_COUNT_WORD = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}


def test_the_migration_enumerates_every_writer_that_ends_a_deferral():
    """326's writer list, counted from the tree instead of remembered.

    The header enumerated three -- report, revival funnel, sweep tick -- and
    left out the room-issue write, which calls the same helper on the
    statement that stamps room_issued_at. A guard, test or runbook step
    derived from the short list would treat that path as one that cannot end
    a deferral, and a marker it cleared would leave a reader with no fourth
    candidate to look at.

    The COUNT WORD is derived here rather than typed: the helper's callers are
    read out of main.py, mapped to the roles the sentence names, and the total
    is those roles plus the two writers that never touch the helper. A fifth
    caller reddens this test instead of being quietly missing from the prose.
    """
    callers = [n for n in functions_performing("_team_clear_dc_fallback_marker(")
               if n != "_team_clear_dc_fallback_marker"]
    assert set(callers) == set(ROLE_OF_CLEARING_CALLER), (
        callers, sorted(ROLE_OF_CLEARING_CALLER))
    flat = _collapsed(_dc_claim_sources()["326_team_series_dc_fallback_at.sql"])
    roles = sorted({ROLE_OF_CLEARING_CALLER[c] for c in callers})
    want = _COUNT_WORD[len(roles) + WRITERS_NOT_THROUGH_THE_HELPER]
    assert ("%s writers end it" % want) in flat, (want, callers, roles)
    for phrase in roles + ["a real-totals report inside the bound",
                           "a sweep tick after the bound"]:
        assert flat.count(phrase) >= 1, phrase
    # And the header prices the fourth honestly: it is a writer that sometimes
    # ends a deferral, not one guaranteed to run its UPDATE.
    assert "is not guaranteed to run its UPDATE" in flat, flat[:600]


def test_the_bound_sentence_is_one_sentence_in_every_copy():
    """The cross-lane sentence, character for character, in both server copies.

    The client lane carries the same string; the lens greps both trees for it
    (#341, #444). A paraphrase is how two lanes start describing different
    behaviour while each looks correct on its own.
    """
    sentence_words = (
        "A real-totals report wins while the deferred marker is younger than "
        "420 seconds, and after that only until a sweep tick finds no "
        "live-game evidence for the series and settles the row; once a row is "
        "settled, a later report is refused at the settled-row exit and is "
        "not rated.")

    def normalized(text):
        return re.sub(r"\s+", " ", re.sub(r"(?m)^\s*(--|#)\s?", " ", text))

    api_norm = normalized(SRC)
    assert api_norm.count(sentence_words) == 3, (
        "main.py must carry the bound sentence three times: the derivation "
        "beside _DC_FALLBACK_DEFER_SECONDS, the deferral branch of report-dc, "
        "and the sweep loop's docstring")
    sql = (pathlib.Path(__file__).resolve().parents[1] / "sql"
           / "326_team_series_dc_fallback_at.sql").read_text(encoding="utf-8")
    assert sentence_words in normalized(sql)
    # And the claim it replaced is gone from both.
    for where, text_ in (("main.py", SRC),
                         ("326_team_series_dc_fallback_at.sql", sql)):
        at, why = absent_at("at ANY later moment still finds", text_, where)
        assert at < 0, why


# ── The lock, the veto and the attribution ───────────────────────────────


def test_the_sweep_never_queues_behind_a_holder():
    code = code_only(span("_team_dc_fallback_sweep_once"))
    joined = "\n".join(code)
    # There is no lock_timeout on the engine and none set here, so an
    # unqualified lock is an unbounded wait that starves the rest of the batch
    # (the loop is sleep-then-one-pass). Every sibling janitor in this file
    # takes the weakest lock WITH SKIP LOCKED for exactly that reason.
    assert joined.count("FOR NO KEY UPDATE SKIP LOCKED") == 1
    assert joined.count("FOR NO KEY UPDATE") == 1, (
        "an unqualified FOR NO KEY UPDATE is still in the sweep")
    assert "FOR UPDATE\n" not in joined


def test_the_liveness_veto_is_re_evaluated_after_the_lock_is_held():
    code = code_only(span("_team_dc_fallback_sweep_once"))
    vetoes = [i for i, ln in enumerate(code) if "_group_game_in_progress(" in ln]
    assert len(vetoes) == 2, vetoes
    lock = first_index(code, "FOR NO KEY UPDATE SKIP LOCKED")
    settle = first_index(code, "SET status = 'dc_incomplete'")
    # One before the lock as a cheap filter, one after it as the decision. The
    # in-transaction re-check covers COLUMNS; liveness is in-process evidence
    # and no SQL predicate can re-read it.
    assert vetoes[0] < lock < vetoes[1] < settle, (vetoes, lock, settle)


def test_nothing_awaits_between_the_post_lock_veto_and_the_settlement_write():
    """The round-4 HIGH, as a property of the source.

    Liveness is in-process evidence, so it is only as current as the last
    moment this coroutine held the event loop. Round 4 ran the awaited
    service-subject lookup AFTER the post-lock veto; on a cold or hourly-
    expired cache that lookup issues its own SELECT, and any await lets the
    presence ping that publishes in-match evidence for this very series run to
    completion. The veto's answer was then a reading of the past and the
    settlement write acted on it as current.

    So: the veto is the LAST thing read before the write, and between them
    there is no await of any kind. Asserted over this function's own span
    (#432) and on the AST rather than on a line count, so a helper call that
    happens to be written across two lines cannot slip through.
    """
    node = node_named("_team_dc_fallback_sweep_once")

    def veto_calls(stmt):
        return [n for n in ast.walk(stmt)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_group_game_in_progress"]

    assert len(veto_calls(node)) == 2, "the sweep no longer has two vetoes"
    loops = [n for n in ast.walk(node) if isinstance(n, ast.For)]
    assert len(loops) == 1, "the per-row loop is not where it was"
    body = loops[0].body

    # The post-lock veto is the LAST top-level `if` in the loop whose own test
    # calls the veto. Its own branch is the vetoed path -- awaits in there
    # happen instead of the write, not before it -- so the question is only
    # about the SIBLINGS that follow it.
    veto_idx = [i for i, st in enumerate(body)
                if isinstance(st, ast.If) and veto_calls(st.test)]
    assert veto_idx, "no `if` in the per-row loop tests the live-game veto"
    after = body[veto_idx[-1] + 1:]
    assert after, "nothing follows the post-lock veto"

    first_await = None
    for stmt in after:
        awaits = sorted(n.lineno for n in ast.walk(stmt)
                        if isinstance(n, ast.Await))
        if awaits:
            first_await = (stmt, awaits[0])
            break
    assert first_await is not None, "the settlement write disappeared"
    stmt, lineno = first_await
    text_of = "\n".join(LINES[stmt.lineno - 1:stmt.end_lineno])
    assert "SET status = 'dc_incomplete'" in text_of, (
        "the first thing awaited after the post-lock live-game veto is not "
        f"the settlement write but line {lineno}: {LINES[lineno - 1].strip()!r}"
        " -- the veto is stale by however long that await takes")

    # And the service-subject lookup -- the await that used to be there -- now
    # runs BEFORE the veto, where its cost is paid while nothing is decided.
    service = [n.lineno for n in ast.walk(node)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "_assert_no_service_subject"]
    assert len(service) == 1, service
    assert service[0] < body[veto_idx[-1]].lineno, (service, veto_idx)


def test_every_value_the_settle_writes_is_read_from_the_locked_row():
    code = code_only(span("_team_dc_fallback_sweep_once"))
    joined = "\n".join(code)
    # Discovery carries the id and nothing else.
    assert any(ln.strip() == "SELECT ts.id" for ln in code), code[:20]
    for key in ("dc_fallback_player_id", "t1a_id", "t1b_id", "t2a_id", "t2b_id"):
        assert f'locked["{key}"]' in joined, key
        assert f'row["{key}"]' not in joined, (
            f"{key} is carried from the UNLOCKED discovery pass into a write")
    # The service-subject refusal judges the same four ids the settle
    # attributes to, with the lock held.
    assert first_index(code, "FOR NO KEY UPDATE SKIP LOCKED") < first_index(
        code, "_assert_no_service_subject(")


# ── /mod-version advertises no capability ────────────────────────────────


def test_mod_version_advertises_no_capability():
    """The advertisement is deleted, not merely unused.

    An answer from /mod-version cannot speak for the box that answers a LATER
    request: the edge chooses an upstream per request and the two boxes are
    deployed independently (learning #422). Leaving the key in place while the
    client stopped reading it would leave the next reader a mechanism to
    revive.
    """
    code = code_lines_of(node_named("get_mod_version"))
    joined = "\n".join(code)
    assert "series_status_readonly" not in joined, joined
    # The two version numbers, and nothing else.
    assert '"version": LATEST_MOD_VERSION' in joined
    assert '"min_version": MIN_MOD_VERSION_EFFECTIVE}' in joined
    doc = ast.get_docstring(node_named("get_mod_version"))
    # The docstring must say WHY, or the next pass re-adds it.
    assert "NO CAPABILITY IS ADVERTISED HERE" in doc
    assert "/status" in doc


# ── The report endpoint's build discriminator ────────────────────────────


def test_every_200_exit_of_report_dc_carries_the_deferred_field():
    """W23 is a measurement only if the field rides the non-deferring exits.

    Absent from a 200, "deferred" means the answering box predates the flag;
    present and false, it means this build did not park the report -- which is
    NOT the same as "this call settled the series", and the next test holds
    the file's wording to that difference. With the field only on the deferral
    branch a client could not tell false from absent, and its log line would
    measure nothing (r4 client L4).
    """
    node = node_named("team_series_report_dc")
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    assert len(returns) == 6, len(returns)
    for r in returns:
        assert isinstance(r.value, ast.Dict), ast.dump(r.value)
        keys = [k.value for k in r.value.keys if isinstance(k, ast.Constant)]
        assert "deferred" in keys, (r.lineno, keys)
    # Exactly one of them defers; the other five say so explicitly.
    src = "\n".join(code_only(span("team_series_report_dc")))
    assert src.count('"deferred": True') == 1
    assert src.count('"deferred": False') == 5


# The ONE definition of the field, as it stands in main.py. One copy, not four:
# a rule restated in several places is re-derived in several places, and round
# 5 shipped three restatements of this one that each said something the code
# does not do (#660, #701, #351).
FIELD_SENTENCE = (
    '"deferred" says only whether THIS call parked the report: true when it '
    'did, false on the five exits that do not park one -- two of which settle '
    'the series while the other three, the settled-row exit and the two room '
    'fences, decide nothing and say so with "ignored": true -- and absent '
    'only from a box that predates the flag.')


def test_the_deferred_definition_is_single_and_its_arithmetic_matches_the_exits():
    """The field's definition is a claim about all six exits; count them.

    The round-5 wording said false meant "this box carries the deferral build
    and settled it". Three of the five false exits settle nothing: the
    settled-row exit answers for a row somebody else had already terminated,
    and the two room fences DISCARD a stale report and leave the series
    'active' and open. A maintainer who built the next guard on "false means
    settled" would close a series that is still expecting a real-totals
    report.

    So the definition now names the split, and this test binds its arithmetic
    to the AST: change what an exit does, or add a sixth, and the sentence
    stops being true and this goes red.
    """
    def normalized(text_):
        return re.sub(r"\s+", " ", re.sub(r"(?m)^\s*#\s?", " ", text_))

    # ONE definition in the file, at the branch that creates the deferral.
    assert normalized(SRC).count(FIELD_SENTENCE) == 1, (
        "the field is defined zero times, or restated in a second place "
        "where the two copies can drift")
    branch = "\n".join(span("team_series_report_dc"))
    assert FIELD_SENTENCE in normalized(branch)

    node = node_named("team_series_report_dc")
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]

    def key(r, name):
        for k, v in zip(r.value.keys, r.value.values):
            if isinstance(k, ast.Constant) and k.value == name:
                return v
        return None

    deferring = [r for r in returns
                 if isinstance(key(r, "deferred"), ast.Constant)
                 and key(r, "deferred").value is True]
    not_deferring = [r for r in returns if r not in deferring]
    # "decide nothing and say so with ignored: true"
    ignoring = [r for r in not_deferring
                if isinstance(key(r, "ignored"), ast.Constant)
                and key(r, "ignored").value is True]
    # "two of which settle the series" -- a settling exit names the terminal
    # status it wrote as a literal; the three that decide nothing echo the
    # status they READ (s["status"]) or carry no terminal status at all.
    settling = [r for r in not_deferring
                if isinstance(key(r, "status"), ast.Constant)
                and key(r, "status").value in ("completed", "dc_incomplete")]

    assert len(deferring) == 1, [r.lineno for r in deferring]
    assert len(not_deferring) == 5, [r.lineno for r in not_deferring]
    assert len(ignoring) == 3, [r.lineno for r in ignoring]
    assert len(settling) == 2, [r.lineno for r in settling]
    # The two sets partition the five: no exit both settles and says it
    # decided nothing, and none of the five is unaccounted for.
    assert not set(id(r) for r in ignoring) & set(id(r) for r in settling)
    assert len(ignoring) + len(settling) == len(not_deferring)

    # A literal backstop for the exact claims round 5 carried. It catches a
    # revert of the wording and nothing cleverer -- the arithmetic above is
    # what catches a NEW overclaim, because a new one has to contradict a
    # count (#441: a grep for a common spelling answers a weaker question
    # than the one being asked).
    for gone in ("carries the deferral build and settled it",
                 "knows this build settled its report",
                 "false on each settling exit",
                 "present and false, it means this build settled the report"):
        at, why = absent_at(gone, SRC, "main.py")
        assert at < 0, why


# ── The comment-claim surface, held as a class ───────────────────────────
#
# Round 6 corrected seven claims and shipped four more. A claim is corrected
# HERE, with its superseded form named, so a revert reddens instead of reading
# like prose nobody measures (#302, #351, #459).


def _collapsed(text_):
    """Comment markers and wrapping removed, so a claim is one string."""
    return re.sub(r"\s+", " ", re.sub(r"(?m)^\s*(--|#)\s?", " ", text_))


_CLAIM_TABLE_NAMES = ("SUPERSEDED_CLAIMS", "CORRECTED_CLAIMS",
                      "PRE_FIELD_MISREADINGS", "PRE_FIELD_SENTENCE")


def _without_claim_tables(text_):
    """A claim checker must not read its own evidence table.

    This file QUOTES every superseded sentence, so a scan that included the
    tables below would find each one in the file that hunts for it and redden
    for ever -- a check that cannot pass, which is the same defect as one that
    cannot fail (#342). The two spans are removed by AST line range rather
    than by a marker comment, so a table that moves or grows stays excluded
    with nothing re-typed.
    """
    if not any(n in text_ for n in _CLAIM_TABLE_NAMES):
        return text_
    try:
        tree = ast.parse(text_)
    except SyntaxError:
        return text_
    drop = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in _CLAIM_TABLE_NAMES
                for t in node.targets):
            drop |= set(range(node.lineno, node.end_lineno + 1))
    assert drop, _CLAIM_TABLE_NAMES
    return "\n".join(ln for i, ln in enumerate(text_.splitlines(), 1)
                      if i not in drop)


def _dc_claim_sources():
    here = pathlib.Path(__file__).resolve().parent
    sql = (here.parents[0] / "sql" / "326_team_series_dc_fallback_at.sql")
    return {
        "main.py": SRC,
        "326_team_series_dc_fallback_at.sql": sql.read_text(encoding="utf-8"),
        "test_sept16_dc_fallback_shape.py":
            (here / "test_sept16_dc_fallback_shape.py").read_text(encoding="utf-8"),
        "test_sept16_dc_fallback_orderings.py":
            (here / "test_sept16_dc_fallback_orderings.py").read_text(encoding="utf-8"),
    }


# Every superseded sentence this round replaced, and the file it lived in. A
# form that returns anywhere in the batch reddens, not only at the line it was
# found on: the defect is the CLAIM, and a claim moves between files (#432).
SUPERSEDED_CLAIMS = (
    "the only thing it guarantees is the thing it does",
    "after it runs, that row carries no marker, whatever the marker's age was",
    "The deferred-fallback sweep is the only thing that ever settles a series",
    "only the state-poll's expiry sweep still reads it",
    "Nothing has to run for the deferral to end",
    "EXPIRES BY DEFAULT. Nothing has to run",
    "zero-total disconnect fallback",
    "answers 200 and ignores it, having already settled",
    "is the one line a resolution must carry when the sibling scan did not run",
    "THE SIBLING SCAN, AND THE ONE STATE IN WHICH IT DOES NOT RUN",
    "Only a scan that ran to completion leaves the line out",
    # The room-age absolute, in BOTH files it stood in. It is the L6 defect
    # wearing a different subject: an unconditional guarantee resting on a
    # call that attempts its UPDATE and swallows what that raises.
    # Each of these is ONE source line on purpose: the negative control below
    # looks for every superseded form in this file's own RAW text, and an
    # implicit concatenation across two lines is not the string it names.
    "a marker can never be older than the room",
    "is that a marker is never older than the room",
    # ...and the account that REPLACED the first of those, which was wrong in
    # the other direction: it attributed the room-term deletion's safety to
    # the live-game veto where the round's own reason is that the deleted
    # term could not refuse a row. Two attributions for one deletion means
    # neither was read off the code (#405), so both are named here.
    "What carries that deletion is the sweep's LIVE-GAME VETO",
    # ...and the writer enumeration that counted three of the four.
    "Three writers end it",
)

# ...and the sentence that replaced each one, which must be present exactly
# once. A correction that is merely a deletion leaves the next reader with no
# statement at all, which is how the first of these got written twice in
# opposite directions.
CORRECTED_CLAIMS = (
    ("main.py",
     "it ATTEMPTS the clear inside its own savepoint and swallows every "
     "exception the attempt raises"),
    ("main.py",
     "a swallowed database error"),
    ("main.py",
     "The deferred-fallback sweep is the only UNATTENDED writer that settles a "
     "series a fallback report declined to settle"),
    ("main.py",
     "legacy in its WRITER -- no statement in this api sets that status any "
     "more"),
    # A separate row, because _collapsed strips a LINE-LEADING "--" (it has to:
    # the migration's prose is a SQL comment) and this sentence wraps straight
    # onto one. Two rows say the same thing about the same paragraph without
    # the check depending on where the line happens to break.
    ("main.py", "and it has many READERS still"),
    ("326_team_series_dc_fallback_at.sql",
     "THE MARKER PERSISTS; THE DEFERRAL IS ENDED BY A WRITER, NEVER BY THE "
     "CLOCK."),
    ("326_team_series_dc_fallback_at.sql",
     "its point totals are whatever the client sent and are NOT read on this "
     "path"),
    ("test_sept16_dc_fallback_shape.py",
     "What that 200 proves is ONE thing: the answering box predates the field. "
     "It proves nothing about settlement"),
    ("test_sept16_dc_fallback_shape.py",
     "carries one line for EVERY state in which the sibling scan was on the "
     "candidate list and produced no listing"),
    ("test_sept16_dc_fallback_shape.py",
     "only one whose scan ran to completion leaves the line out"),
    ("test_sept16_dc_fallback_shape.py",
     "A resolution taken with $SCR_CROSS_LANE_CLIENT_ROOT set carries no such "
     "line and is not an exception"),
    ("test_sept16_dc_fallback_shape.py",
     "THE SIBLING SCAN, AND THE TWO STATES IN WHICH IT LISTS NOTHING"),
    ("main.py", "ISSUING A ROOM ATTEMPTS THE DEFERRAL-MARKER CLEAR"),
    ("main.py",
     "NO READER MAY TREAT A MARKER AS NECESSARILY YOUNGER THAN THE ROOM it "
     "would be settled against"),
    ("main.py",
     "WHAT MAKES THAT DELETION SAFE IS THE DELETED TERM'S OWN VACUITY"),
    ("main.py",
     "a BOUND and not a guarantee, since a resumed series with no live game "
     "in evidence at the tick is outside it"),
    ("326_team_series_dc_fallback_at.sql",
     "Four writers end it: a real-totals report inside the bound, a revival "
     "funnel clearing the marker, a sweep tick after the bound, and the "
     "room-issue write in the queue poll"),
    ("test_sept16_dc_fallback_shape.py",
     "the sweep's deletion of the room term is carried by the live-game veto "
     "instead"),
)


def test_no_dc_file_carries_a_superseded_claim():
    """Every claim this round corrected, named by its superseded form.

    The correction and the check are written together on purpose: a comment
    corrected without one is a sentence the next pass can revert with nothing
    anywhere to notice (#302, #351). Each string below was in the tree at a
    tip this round READ -- the round-6 one for all but the last, and this
    round's own first commit for that one -- and is not in it now. A
    sentence this round wrote and then had to narrow is corrected under the
    same guard as one it inherited; the table is not a record of whose
    claim it was.
    """
    for name, text_ in _dc_claim_sources().items():
        flat = _collapsed(_without_claim_tables(text_))
        for gone in SUPERSEDED_CLAIMS:
            at, why = absent_at(gone, flat, name)
            assert at < 0, why
    # ...and the exclusion is not a hole: with the tables left in, this same
    # scan MUST find them. A filter that discarded the line it measures would
    # make the check above unfailable (#441, #342).
    own = _collapsed(_dc_claim_sources()["test_sept16_dc_fallback_shape.py"])
    assert all(g in own for g in SUPERSEDED_CLAIMS), [
        g for g in SUPERSEDED_CLAIMS if g not in own]


def test_every_correction_this_round_made_is_stated_once():
    """The other direction: the replacement exists, in the file it belongs to.

    A superseded claim can be satisfied by deleting the paragraph, which
    leaves the reader of the code with no statement about the case at all --
    and the two revival-age absolutes are what happens next (#351).
    """
    sources = _dc_claim_sources()
    for name, sentence in CORRECTED_CLAIMS:
        flat = _collapsed(_without_claim_tables(sources[name]))
        assert flat.count(sentence) >= 1, (name, sentence)


def test_the_marker_clear_states_what_a_swallowed_error_leaves():
    """L6. The helper catches every exception; its doc must price that.

    The implementation is `try: ... except Exception: pass`, so "after it runs
    that row carries no marker" is a claim about a state space the code does
    not cover. What the doc may say is what the call does: it attempts the
    clear under a savepoint, and a swallowed error leaves the revived row
    carrying its marker -- runtime residual 2, recorded rather than implied.
    """
    doc = ast.get_docstring(node_named("_team_clear_dc_fallback_marker"))
    flat = _collapsed(doc)
    assert "ATTEMPTS the clear inside its own savepoint" in flat, doc
    assert "leaves the revived row still carrying its marker" in flat, doc
    # And the implementation this doc describes is still the swallowing one:
    # a doc that described a re-raise would be equally wrong the other way.
    code = code_lines_of(node_named("_team_clear_dc_fallback_marker"))
    assert any("except Exception:" in ln for ln in code), code
    assert any(ln.strip() == "pass" for ln in code), code


# Every reading of an absent `deferred` that contract item 6 forbids. A
# module-level table because the checker excludes its own tables by NAME: an
# inline tuple inside the test body is evidence the scan would then find in
# the file that hunts for it.
PRE_FIELD_MISREADINGS = (
    "having already settled",
    "absent means the series settled",
    "an absent deferred field means it settled",
)

# ...and the reading that replaced them, counted rather than merely found: a
# claim stated twice is a claim that can be corrected once (#660). The string
# is a table entry, never an inline literal in the assertion, because the
# checker excludes its own tables by name and an inline copy would be counted.
PRE_FIELD_SENTENCE = (
    "What that 200 proves is ONE thing: the answering box predates the field. "
    "It proves nothing about settlement")


def test_no_dc_file_reads_an_absent_deferred_field_as_a_settlement():
    """Contract item 6, the server lane's half.

    A 200 from a box that predates the field proves that the box predates the
    field. It is not evidence about the row: of the five non-deferring exits
    on this build two settle and three decide nothing, and the old build's
    behaviour was its own. A reader who priced an absent field as settlement
    would stop waiting for real totals on a series still expecting them.
    """
    for name, text_ in _dc_claim_sources().items():
        flat = _collapsed(_without_claim_tables(text_))
        for gone in PRE_FIELD_MISREADINGS:
            at, why = absent_at(gone, flat, name)
            assert at < 0, why
    flat = _collapsed(_without_claim_tables(
        _dc_claim_sources()["test_sept16_dc_fallback_shape.py"]))
    assert flat.count(PRE_FIELD_SENTENCE) == 1, flat.count(PRE_FIELD_SENTENCE)


# ── L11: the supplied client representation is bound, or refused ─────────


def test_a_flat_directory_of_client_sources_is_taken_as_itself(tmp_path):
    """The frozen review copy's layout, which round 6 could not read.

    A review pin hands this check a DIRECTORY OF .cs FILES -- no repository
    around it, no `plugin/` under it. Round 6 globbed `<root>/plugin/*.cs`
    only, so that directory resolved to zero sources and the binding moved on
    to another tree while reporting a resolution error. Both layouts are
    answered here, and the nested one still wins where both exist, so a
    checkout is never read as a flat directory of strays.
    """
    flat = tmp_path / "frozen"
    flat.mkdir()
    (flat / "ApiClient.cs").write_text(
        'string url = $"{baseUrl}/api/v1/team/series/{seriesId}/status";\n',
        encoding="utf-8")
    sources, layout = _client_sources_in(flat)
    assert [p.name for p in sources] == ["ApiClient.cs"], sources
    assert "taken as itself" in layout, layout
    assert _carries_the_client_half(flat)[1] is True

    # Both layouts present: the checkout's plugin/ wins, so a tree that also
    # has stray .cs files at its root is still read as a checkout.
    both = tmp_path / "both"
    (both / "plugin").mkdir(parents=True)
    (both / "stray.cs").write_text("// not the client half\n", encoding="utf-8")
    (both / "plugin" / "ApiClient.cs").write_text(
        'string url = $"{baseUrl}/api/v1/team/series/{seriesId}/status";\n',
        encoding="utf-8")
    sources, layout = _client_sources_in(both)
    assert [p.name for p in sources] == ["ApiClient.cs"], sources
    assert "plugin/" in layout, layout


def test_a_supplied_representation_missing_a_named_source_is_refused(
        monkeypatch, tmp_path):
    """A named candidate that is short a source REFUSES; it never falls through.

    The failure this closes: the resolver was handed the frozen client copy,
    read nothing in it, and quietly measured the next tree on the list. The
    answer then describes a checkout nobody chose, and on this workstation
    that is a tree another builder is editing. Two things are required of the
    refusal -- that it happens at all, and that it NAMES the missing source,
    so the reader is not left guessing which half of the representation was
    short (#447).
    """
    root = tmp_path / "short"
    root.mkdir()
    (root / "ApiClient.cs").write_text(
        'string url = $"{baseUrl}/api/v1/team/series/{seriesId}/status";\n'
        'HasJsonKey(resp, "dc_deferred");\n', encoding="utf-8")
    monkeypatch.setenv("SCR_CROSS_LANE_CLIENT_ROOT", str(root))
    sources, how = _client_lane_sources()
    assert sources == [], sources
    assert how.startswith("REFUSED"), how
    assert "NativeUI.cs" in how, how
    # The named source that IS present is not reported missing.
    assert "/ApiClient.cs is absent" not in how, how

    # ...and with both named sources present the same call resolves, so the
    # refusal is specific and not simply this function's only answer (#391).
    (root / "NativeUI.cs").write_text(
        'HasJsonKey(resp, "dc_deferred_seconds_remaining");\n'
        'HasJsonKey(resp, "dc_deferred_bound_seconds");\n', encoding="utf-8")
    sources, how = _client_lane_sources()
    assert [p.name for p in sources] == ["ApiClient.cs", "NativeUI.cs"], sources
    assert not how.startswith("REFUSED"), how


def test_a_supplied_representation_that_never_calls_the_route_is_refused(
        monkeypatch, tmp_path):
    """The second refusal: both sources present, neither calls the route.

    That is a representation offered as the client half which is not one, and
    trying the next candidate would answer about a different tree with nothing
    in the message to say so.
    """
    root = tmp_path / "wrongtree"
    root.mkdir()
    (root / "ApiClient.cs").write_text(
        'string url = $"{baseUrl}/api/v1/team/series/{seriesId}/state";\n',
        encoding="utf-8")
    (root / "NativeUI.cs").write_text("// nothing\n", encoding="utf-8")
    monkeypatch.setenv("SCR_CROSS_LANE_CLIENT_ROOT", str(root))
    sources, how = _client_lane_sources()
    assert sources == [], sources
    assert how.startswith("REFUSED"), how
    assert "calls the status route" in how, how


def test_the_sibling_scan_switch_removes_only_that_candidate(monkeypatch):
    """The switch takes out candidate 4 and leaves 1 to 3 standing.

    A switch that could take the whole binding out of the run would be the
    skipif this file deleted, under a new name (#715, #664). What it removes
    is one candidate, and the resolution says so in words a log carries: a run
    that did not scan may never read as a run that scanned and found nothing.
    """
    monkeypatch.delenv("SCR_CROSS_LANE_CLIENT_ROOT", raising=False)
    monkeypatch.setenv("SCR_CROSS_LANE_NO_SIBLING_SCAN", "1")
    _sources, how = _client_lane_sources()
    assert "NOT RUN" in how, how
    assert "sibling-worktree scan" in how, how
    # The other three are still tried, by name, in the same message.
    assert "the review pin's client-lane copy" in how, how
    assert "this repository itself" in how, how
    # And the resolver's source still carries all four candidates: the switch
    # is a run-time state, not a deletion.
    resolver = ast.unparse(next(n for n in ast.parse(
        pathlib.Path(__file__).resolve().read_text(encoding="utf-8")).body
        if isinstance(n, ast.FunctionDef)
        and n.name == "_client_lane_candidates"))
    assert resolver.count("cands.append") == 4, resolver
    assert "_worktrees_on_branch(" in resolver, resolver


def test_a_sibling_scan_that_did_not_complete_is_not_a_scan_that_found_nothing(
        monkeypatch, tmp_path):
    """The other state in which the scan produces no listing.

    The switch above is the state everyone remembers. The one that actually
    cost this lane a run of its evidence bundle is the other one: the child
    was started and did not finish -- or could not be started at all -- and
    the blanket catch over an unchecked return code turned that into an empty
    candidate list, which at the resolution message is the same text as a scan
    that ran and listed nothing. An unrun child is not a measurement (#304),
    and the resolution has to say which of the two it is holding.

    All five arms drive the same site. The first three are the controls -- git
    refusing, the child exiting with a launch status and no output, and the
    child raising before it starts -- and each must be named. The fourth is
    the INERT TWIN: a scan that RAN and listed no client-lane worktree leaves
    the line out, because that one IS a measurement. A resolver that cried
    ATTEMPTED AND FAILED on every run would be this same defect inverted, and
    it would fail this test just as surely.

    The fifth is the branch the resolver's docstring has to scope itself
    against: with the tree named in the environment the scan is never on the
    candidate list, so no line is carried and none is owed. It is driven here
    rather than left to the prose, because the first version of that
    docstring made completion the only way the line is left out and this
    branch falsifies it.
    """
    monkeypatch.delenv("SCR_CROSS_LANE_CLIENT_ROOT", raising=False)
    monkeypatch.delenv("SCR_CROSS_LANE_NO_SIBLING_SCAN", raising=False)

    class _Result(object):
        def __init__(self, rc, out=b""):
            self.returncode = rc
            self.stdout = out
            self.stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result(128))
    _cands, tried = _client_lane_candidates()
    assert any("ATTEMPTED AND FAILED" in t for t in tried), tried
    assert any("exited 128" in t for t in tried), tried
    # ...and it reaches the resolution a log carries, not only the helper.
    _sources, how = _client_lane_sources()
    assert "ATTEMPTED AND FAILED" in how, how
    assert "NOT a scan that ran" in how, how

    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _Result(3221225794))
    _cands, tried = _client_lane_candidates()
    assert any("exited 3221225794" in t for t in tried), tried

    def _cannot_start(*_a, **_k):
        raise OSError("the child could not be created")

    monkeypatch.setattr(subprocess, "run", _cannot_start)
    _cands, tried = _client_lane_candidates()
    assert any("could not be started: OSError" in t for t in tried), tried

    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _Result(0, b"/somewhere abcdef0 [some-other-branch]\n"))
    _cands, tried = _client_lane_candidates()
    assert tried == [], tried

    # ...and the branch the docstring has to SCOPE itself against, asserted
    # rather than taken on the prose's word: with the tree named in the
    # environment the scan is never on the candidate list, so there is no
    # line about it and none is owed. The first version of that docstring
    # made completion the ONLY way the line is left out, which is false
    # here -- no scan ran and the line is still out. A guarantee is a
    # claim about the whole state space (#351), so the state it excludes is
    # named in the sentence AND driven here.
    monkeypatch.setattr(subprocess, "run", _cannot_start)
    monkeypatch.setenv("SCR_CROSS_LANE_CLIENT_ROOT", str(tmp_path))
    cands, tried = _client_lane_candidates()
    assert tried == [], tried
    assert len(cands) == 1, cands
    assert cands[0][2] is True, cands


# Names bound to a WHOLE SOURCE FILE in this module, or to one collapsed onto a
# single line. A `not in` against one of them is the shape that made a control
# unusable, and it is refused here rather than remembered: the flag named one
# line, the defect is the class (#432).
WHOLE_FILE_NAMES = ("SRC", "flat", "sql", "own", "text_")


def test_no_check_here_asks_pytest_to_diff_a_whole_file():
    """The failure path of a check is part of the check.

    A check that reddens only after 24 minutes of quadratic diffing is not
    evidence a reviewer can run, and that is what `assert needle not in SRC`
    costs when it fires (see absent_at). Every such site compares an index
    instead. The shape is refused through the AST rather than by grepping for
    a spelling, and the scan is shown to see the shape at all -- a guard whose
    walk silently matched nothing would pass for ever (#342, #441).
    """
    own_src = pathlib.Path(__file__).read_text(encoding="utf-8")

    def offenders_in(tree_):
        out = []
        for node in ast.walk(tree_):
            if not isinstance(node, ast.Assert):
                continue
            t = node.test
            if not isinstance(t, ast.Compare) or len(t.ops) != 1:
                continue
            if not isinstance(t.ops[0], ast.NotIn):
                continue
            right = t.comparators[0]
            if isinstance(right, ast.Name) and right.id in WHOLE_FILE_NAMES:
                out.append((node.lineno, right.id))
        return out

    assert offenders_in(ast.parse(own_src)) == [], offenders_in(
        ast.parse(own_src))
    # The negative control: the same walk over a sample that HAS the shape
    # must find exactly it, so a pass above means "absent" and not "not
    # looked for".
    planted = offenders_in(ast.parse(
        "def f():\n    assert 'x' not in " + WHOLE_FILE_NAMES[0] + "\n"))
    assert planted == [(2, WHOLE_FILE_NAMES[0])], planted
