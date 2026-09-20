# -*- coding: utf-8 -*-
"""Acceptance for the r2 remediation of the September 16 CLIENT batch
(commit 886bed8, reports #355-#385) -- one test per closed finding.

WHAT THESE TESTS ARE, AND WHAT THEY ARE NOT.  The client is C# running inside
ROUNDS; nothing here launches the game, so no test in this file witnesses a
Harmony patch attaching, an IMGUI keystroke, or a Photon round trip.  What it
CAN do is exactly two things, and both are done deliberately:

  * SOURCE CLAIMS.  Each closed finding names a property the source must now
    have.  The property is expressed as a predicate over the file's text, and
    every predicate is paired with a MUTATION that removes the fix and a
    control asserting the predicate then goes False (#391).  A predicate that
    passes on a stub source, or that cannot be made to fail, is a check that
    cannot fail and is worse than no check (#342) -- `_assert_discriminating`
    refuses both.

  * EXECUTABLE MODELS.  Three pieces of decision logic decide integrity
    outcomes rather than text: the 2v2 DC reporter election, the spectate
    reason precedence, and the chat-fit decision.  Those are transliterated
    here and exercised over their whole input space, including the degenerate
    seats the report named.  A model is evidence about the DESIGN, not about
    the compiled method; each model test therefore also pins the C# it
    mirrors, so the two cannot drift apart silently.

Run: python -m pytest backend/tests/test_sept16_client_r2.py -q
"""
import itertools
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"


def _src(name):
    return (PLUGIN / name).read_text(encoding="utf-8")


def _mutate(src, old, new, label):
    assert src.count(old) >= 1, "mutation anchor vanished: " + label
    return src.replace(old, new, 1)


def _assert_discriminating(predicate, real, mutated, label):
    """The three properties every claim in this file must have: it holds on the
    tree, it does NOT hold once the fix is removed, and it does not hold on a
    source that never had it."""
    assert predicate(real), label + ": the claim does not hold on the tree"
    assert not predicate(mutated), label + ": the claim survives its own mutation"
    assert not predicate("// nothing here\n"), label + ": the claim holds on a stub"


# A member declaration at class-member indentation: what a single method's text
# must not contain, because containing one means the window is not one method's.
_MEMBER_DECL = re.compile(
    r"^ {8}(?:internal|private|public|protected)\s+[A-Za-z_<]", re.M)


def _method_body(src, signature):
    """The text of ONE C# method, or "" when that cannot be established.

    The first cut of this file took a body as "everything from the signature to
    the first line that is exactly eight spaces and a closing brace".  That
    window is the method's own only while the method is written across lines.
    For a ONE-LINE member -- `internal static void X() { Y(); }`, which is
    exactly how DropChatDraftOnRevoke looked BEFORE the fix M5 is about -- there
    is no such line inside it, so the window ran on into the NEXT member and the
    predicate read a neighbour's statements as the fix's.  test_m5 therefore
    passed on the unfixed tree: a check that cannot fail is worse than no check
    (#342).  The control beside it never caught that, because the synthetic
    mutation is the one source where the anchor does sit in the right method --
    which is why the control below this file's M5 test is the PRE-FIX SHAPE and
    not another synthetic edit (#391).

    Two rules close it.  A one-line member returns that line and nothing else.
    A multi-line one still ends at its eight-space brace, but the window is
    REJECTED (returns "") when another member declaration appears inside it,
    which is exactly the footprint of a window that ran past its own method.
    """
    if signature not in src:
        return ""
    rest = src[src.index(signature):]
    line_end = rest.find("\n")
    first_line = rest if line_end < 0 else rest[:line_end]
    if "{" in first_line and first_line.count("{") == first_line.count("}"):
        return first_line                      # a complete one-line member
    end = rest.find("\n        }")
    if end < 0:
        return ""
    body = rest[:end + 10]
    if _MEMBER_DECL.search(body[len(signature):]):
        return ""                              # ran past this method: not evidence
    return body


# ══════════════════════════════════════════════════════════════════════════
# H1 / L3 -- the 2v2 DC reporter election
# ══════════════════════════════════════════════════════════════════════════
#
# The deployed endpoint (main.py team_series_report_dc) completes the series
# with ratings and gold when the non-DC team already had a win AND
# t1_points_total + t2_points_total >= 2; otherwise it records dc_incomplete.
# Those totals ride the query string outside the DC signature, and the first
# accepted report wins the row lock.  So the client half must produce exactly
# one reporter whenever it claims the right to send real totals.


def retry_budget_seconds():
    """The prompt report's transport budget, DERIVED from the source instead of
    written down.  The previous round's control hardcoded 34 seconds, so raising
    any transport term -- attempts, timeout or backoff -- left the named control
    green: a check that cannot fail (#342).

    Nothing in the client depends on this number any more, and that is the
    point: it is computed here so a test can assert the ABSENCE of any bound
    derived from it.
    """
    api = _src("ApiClient.cs")
    body = _method_body(api, "private static IEnumerator PostRequestWithRetry")
    assert body, "the retry helper's own text could not be delimited"
    attempts = int(re.search(r"int maxRetries = (\d+)", body).group(1))
    backoff = float(re.search(r"float retryDelay = ([\d.]+)f", body).group(1))
    timeout = int(re.search(r"request\.timeout = (\d+);", body).group(1))
    return attempts * timeout + (attempts - 1) * backoff


# ── the deployed endpoint, transliterated from the PRODUCTION pin ────────────
#
# backend/api/main.py at 0cc7f75, team_series_report_dc.  Three facts decide
# everything below:
#   * the row is re-read FOR NO KEY UPDATE and a status outside
#     (active, dc_paused) returns {"ignored": true} WITHOUT writing;
#   * the lead-forfeit branch needs other_team_existing_wins >= 1 AND
#     t1_points_total + t2_points_total >= 2, and only that branch reaches
#     _complete_team_series_with_ratings;
#   * every other path writes status='dc_incomplete'.

def endpoint(status, other_team_wins, points):
    """The series status AFTER this report.  `points` is the report's t1+t2."""
    if status not in ("active", "dc_paused"):
        return status                      # {"ignored": true}; nothing is written
    if other_team_wins >= 1 and points >= 2:
        return "completed"                 # ratings + gold
    return "dc_incomplete"


def elect(seats, leaver, capable=None):
    """Transliteration of Plugin.OnPlayerLeftRoom's election.

    `seats` is the list of SURVIVORS as every seat sees them (Photon has
    already removed the leaver), each a dict {uid, team, local}.  `leaver` is
    {uid, team}.  `capable` is the set of uids advertising cr_dc2 -- None means
    the whole room advertises it, which is the case the census arm needs.

    Returns one entry per seat that ACTS, as (uid, totals, role).

    `totals` is always "REAL": the arm-(2) zeros were withdrawn a round ago, and
    a test asserting a seat can produce "ZERO" here would be asserting the defect
    (a seat on the LEAVER's team could force every other seat's report to zero by
    withholding one property, turning a forfeit the other team had earned into
    dc_incomplete).

    `role` is "prompt" for a seat that POSTS NOW, and "watch" for the census
    arm's other non-DC survivor, which posts NOTHING and arms a watch on the
    elected seat's TERMINAL outcome.  There is no delay in this model because
    there is no delay in the client: the +45 s net this replaces was an
    elapsed-time guess about another seat's transaction, and what the watch
    eventually posts (if anything) is decided by `fallback` below.
    """
    posts = []
    for me in seats:
        my_val, my_team = me["uid"], me["team"]
        if my_val is None:
            continue                      # no local steam id: the client returns
        dc_team = leaver["team"]
        teams_known = dc_team is not None and my_team is not None

        # arm (1) preconditions, including the room-wide one: every survivor
        # advertising cr_dc2, i.e. every seat that could report is evaluating
        # THIS rule rather than the previous OR'd election.
        room_wide = all(capable is None or s["uid"] in capable for s in seats)
        unique = teams_known and len(seats) == 3 and room_wide
        seen, lowest_non_dc, non_dc, dc_count, saw_self = set(), None, 0, 1, False
        if unique:
            if leaver["uid"] is None:
                unique = False
            else:
                seen.add(leaver["uid"])
        if unique:
            for s in seats:
                sid, st = s["uid"], s["team"]
                if sid is None or st is None or sid in seen:
                    unique = False
                    break
                seen.add(sid)
                if s["local"] is me["local"] and s is me:
                    saw_self = True
                if st == dc_team:
                    dc_count += 1
                else:
                    non_dc += 1
                    if lowest_non_dc is None or sid < lowest_non_dc:
                        lowest_non_dc = sid
        if unique and (not saw_self or dc_count != 2 or non_dc != 2):
            unique = False

        if unique:
            if my_team == dc_team:
                continue                  # the other team elects; the server refuses us
            posts.append((my_val, "REAL",
                          "prompt" if my_val == lowest_non_dc else "watch"))
            continue

        # arm (2): the floor election, unchanged, with this seat's own snapshot
        lowest_overall = True
        lowest_on_my_team = teams_known and my_team != dc_team
        other_eligible = False
        for pp in seats:
            if pp is me:
                continue
            pv = pp["uid"]
            if pv is None:
                continue
            if teams_known and pp["team"] is not None and pp["team"] != dc_team:
                other_eligible = True
            if pv >= my_val:
                continue
            lowest_overall = False
            if lowest_on_my_team and pp["team"] == my_team:
                lowest_on_my_team = False
        if teams_known and my_team == dc_team and other_eligible:
            continue
        if not lowest_overall and not lowest_on_my_team:
            continue
        posts.append((my_val, "REAL", "prompt"))
    return posts


def _prompt(posts):
    return [p for p in posts if p[2] == "prompt"]


def _watch(posts):
    return [p for p in posts if p[2] == "watch"]


# ── the fallback's own rule, transliterated from DcReportSync.Evaluate ───────

def fallback(outcome, gone, server_status):
    """What the WATCHING seat does.

    `outcome` is the last cr_dcr value it latched for this series: "" (the
    elected seat has said nothing), "send", "ok" or "no".  `gone` is whether
    that seat has left the room.  `server_status` is what
    GET /team/series/{id}/state answered, or None when the read FAILED.

    Returns "nothing", "stand-down", or "post" -- and "post" always means the
    zero-total form.
    """
    if outcome == "ok":
        return "stand-down"                       # terminal: the server answered
    if outcome == "no" or (gone and outcome == ""):
        # terminal the other way: nothing landed, or nothing was ever dispatched.
        # Ask the server before writing anything.
        if server_status is None:
            return "nothing"                      # UNKNOWN state: never post on it
        if server_status not in ("active", "dc_paused"):
            return "stand-down"
        return "post"
    # everything else -- still in the room, or gone with a request in flight --
    # is NOT terminal, and where no terminal outcome is known this seat posts
    # nothing at all.
    return "nothing"


def _seats(ids_teams):
    return [{"uid": u, "team": t, "local": i} for i, (u, t) in enumerate(ids_teams)]


def test_h1_healthy_2v2_elects_exactly_one_prompt_reporter_plus_a_watcher():
    # leaver on team 0; survivors: its teammate (team 0) and both of team 1.
    seats = _seats([(10, 0), (20, 1), (30, 1)])
    posts = elect(seats, {"uid": 40, "team": 0})
    assert _prompt(posts) == [(20, "REAL", "prompt")], posts
    assert _watch(posts) == [(30, "REAL", "watch")], posts
    # the leaver's own team-mate is silent either way: the server refuses it
    assert 10 not in [u for u, _t, _d in posts]


def test_h1_every_healthy_permutation_yields_one_prompt_report():
    for ids in itertools.permutations([11, 22, 33, 44]):
        leaver_id, a, b, c = ids
        for dc_team in (0, 1):
            other = 1 - dc_team
            seats = _seats([(a, dc_team), (b, other), (c, other)])
            posts = elect(seats, {"uid": leaver_id, "team": dc_team})
            prompt = _prompt(posts)
            assert len(prompt) == 1, (ids, dc_team, posts)
            uid, totals, role = prompt[0]
            assert totals == "REAL" and role == "prompt"
            assert uid == min(b, c)
            # and exactly one seat behind it, never a second prompt report
            assert [u for u, _t, _d in _watch(posts)] == [max(b, c)], posts


def test_h1_no_elapsed_time_arms_the_fallback():
    """The METHOD change.  The previous round put the second non-DC survivor on
    a +45 s timer, sized against the prompt seat's NOMINAL retry budget.  That
    is a guess about another seat's transaction: Unity's request timeout is not
    a hard ceiling under a stalled socket, so a last attempt completing after the
    delayed post makes arrival order decide a rated completion versus
    dc_incomplete -- the defect the census arm exists to remove, landing inside
    its own fix.

    The bar is an ABSENCE: no duration, anywhere on this path, may decide
    whether the second seat posts.  Asserted against the retry budget DERIVED
    from source rather than a number written here, so raising a transport term
    cannot leave this green (#342)."""
    plug = _src("Plugin.cs")
    api = _src("ApiClient.cs")

    budget = retry_budget_seconds()
    assert budget > 0
    # Scoped to the DC callback's own span, not the whole file: "34" occurs as a
    # substring of unrelated bug numbers, and a file-wide absence check for a
    # two-digit string is a claim the tree cannot satisfy -- which is how such a
    # check gets weakened until it cannot fail (#342; #432 says to assert the
    # occurrence count within the FUNCTION span, never file-wide).
    dc = plug[plug.index("// Reporter election: exactly ONE PROMPT report"):]
    dc = dc[:dc.index('Plugin.Log.LogWarning($"[2v2-DC] report error')]
    # ...and over the CODE, with the comment lines removed.  The prose above the
    # election says what the +45 s net was and why it is gone; deleting that
    # sentence to satisfy a text search would delete the record of the change.
    code = "\n".join(l for l in dc.splitlines() if not l.strip().startswith("//"))
    for magic in (str(int(budget)), str(int(budget) + 11), "DC_SAFETY_NET_SEC",
                  "WaitForSeconds", "delaySec"):
        assert magic not in code, magic
    assert "delaySeconds" not in _method_body(api, "public static void ReportTeamSeriesDc")
    dispatch = _method_body(api, "private static IEnumerator SendTeamSeriesDcReport")
    assert dispatch, "the dispatch method's own text could not be delimited"
    assert "WaitForSeconds" not in dispatch

    def claim(s):
        b = _method_body(s, "private static IEnumerator SendTeamSeriesDcReport")
        return bool(b) and "WaitForSeconds" not in b and "PostRequestWithRetry(url" in b

    _assert_discriminating(
        claim, api,
        _mutate(api,
                "            yield return Plugin.Instance.StartCoroutine(PostRequestWithRetry(url",
                "            yield return new WaitForSecondsRealtime(45f);\n"
                "            yield return Plugin.Instance.StartCoroutine(PostRequestWithRetry(url",
                "H1 elapsed-time net"),
        "H1 no elapsed-time arming")


def test_h1_the_fallback_fires_only_on_a_terminal_outcome():
    """Every state the watching seat can be in, and what it does there.  The one
    that carries the whole method change is (gone, "send"): the elected seat left
    with a request possibly in flight, no terminal outcome is known, and this
    seat posts NOTHING."""
    # terminal: the server answered the prompt report
    for gone in (False, True):
        assert fallback("ok", gone, "active") == "stand-down"
        assert fallback("ok", gone, None) == "stand-down"
    # terminal: every attempt failed
    assert fallback("no", False, "active") == "post"
    assert fallback("no", True, "dc_paused") == "post"
    # terminal: it left having dispatched nothing at all
    assert fallback("", True, "active") == "post"
    # NOT terminal, in either of its two shapes
    assert fallback("", False, "active") == "nothing"      # still here, silent so far
    assert fallback("send", False, "active") == "nothing"  # still here, in flight
    assert fallback("send", True, "active") == "nothing"   # gone, in flight: UNKNOWN
    # a terminal trigger still defers to the server's own answer
    assert fallback("no", False, "completed") == "stand-down"
    assert fallback("no", False, "dc_incomplete") == "stand-down"
    assert fallback("no", False, None) == "nothing"        # unreadable: post nothing

    # and the source runs the same table
    ra = _src("RoomActors.cs")
    body = ra[ra.index("private static void Evaluate(string why)"):]
    body = body[:body.index("private static void Fire(")]
    assert "_watchOutcome == OutcomeAnswered" in body
    assert "_watchOutcome == OutcomeFailed" in body
    assert '_watchGone && _watchOutcome.Length == 0' in body
    assert "_watchGone && _watchOutcome == OutcomeSent" in body

    def claim(s):
        if "private static void Evaluate(string why)" not in s:
            return False
        b = s[s.index("private static void Evaluate(string why)"):]
        b = b[:b.index("private static void Fire(")] if "private static void Fire(" in b else b
        return ("_watchGone && _watchOutcome == OutcomeSent" in b
                and "_watchOutcome == OutcomeFailed" in b)

    _assert_discriminating(
        claim, ra,
        _mutate(ra, "            if (_watchGone && _watchOutcome == OutcomeSent)",
                "            if (false)", "H1 terminal table"),
        "H1 terminal-outcome table")


def test_h1_no_ordering_of_prompt_and_fallback_can_select_the_rated_completion():
    """The proof the round is judged on, over the DEPLOYED endpoint.

    Two things make it hold, and the harness separates them.  First, the two
    requests never coexist: a fallback is emitted only from a state in which the
    prompt transaction is terminal, so the set of schedules containing both an
    in-flight prompt report and a fallback is EMPTY.  Second -- belt and braces,
    because the first rests on a client-side observation -- the fallback's FORM
    carries zero totals, and the endpoint's lead-forfeit branch needs >= 2, so
    even if the two were somehow interleaved the fallback could never be the
    report that completes a series with ratings and gold."""
    coexist = []
    for outcome in ("", "send", "ok", "no"):
        for gone in (False, True):
            for server_status in ("active", "dc_paused", "completed",
                                  "dc_incomplete", "canceled", None):
                act = fallback(outcome, gone, server_status)
                # a prompt request is still live exactly while the elected seat
                # has dispatched and not announced a terminal answer
                prompt_in_flight = (outcome == "send")
                if act == "post" and prompt_in_flight:
                    coexist.append((outcome, gone, server_status))
    assert coexist == [], coexist

    # ...and the form, against the endpoint itself.  Over every series state and
    # every series-lead the endpoint distinguishes, in BOTH arrival orders.
    for other_team_wins in (0, 1, 2):
        for prompt_points in (0, 1, 2, 5):
            # prompt first, then a fallback that the endpoint sees second
            after_prompt = endpoint("active", other_team_wins, prompt_points)
            after_both = endpoint(after_prompt, other_team_wins, 0)
            assert after_both == after_prompt, (other_team_wins, prompt_points)
            # fallback first, then the prompt report
            after_fallback = endpoint("active", other_team_wins, 0)
            assert after_fallback == "dc_incomplete"
            assert endpoint(after_fallback, other_team_wins, prompt_points) == "dc_incomplete"
            # in NEITHER order is the fallback the report that rates the series
            assert endpoint("active", other_team_wins, 0) != "completed"

    # the negative control: a fallback carrying the prompt seat's real totals
    # DOES select the rated completion, which is what the zero form removes
    assert endpoint("active", 1, 3) == "completed"

    # and the client forces the form rather than trusting its caller
    api = _src("ApiClient.cs")

    def claim(s):
        return "if (fallback) { t1PointsTotal = 0; t2PointsTotal = 0; }" in s

    _assert_discriminating(
        claim, api,
        _mutate(api, "if (fallback) { t1PointsTotal = 0; t2PointsTotal = 0; }",
                "// the caller is trusted to zero them", "H1 fallback form"),
        "H1 fallback form")


def test_h1_the_fallback_asks_the_server_before_it_writes_anything():
    """report-dc is not a probe: for an OPEN series it WRITES.  The read is
    GET /team/series/{id}/state, and a read that fails is an UNKNOWN server
    state on which nothing is posted -- which is why it cannot reuse
    PollTeamSeriesState, whose callback never fires on a failure at all."""
    ra = _src("RoomActors.cs")
    api = _src("ApiClient.cs")
    fire = ra[ra.index("private static void Fire(string reason)"):]
    assert "ApiClient.ReadTeamSeriesStatusOnce(series" in fire
    assert 'if (!ok)' in fire
    assert 'status != "active" && status != "dc_paused"' in fire
    # the post is the LAST thing, after both refusals
    assert fire.index("if (!ok)") < fire.index("ApiClient.ReportTeamSeriesDc(")
    assert fire.index('status != "active"') < fire.index("ApiClient.ReportTeamSeriesDc(")

    read = _method_body(api, "public static void ReadTeamSeriesStatusOnce")
    assert read, "the read helper's own text could not be delimited"
    assert "onDone(false, \"\")" in read          # a failure is REPORTED, not dropped

    def claim(s):
        if "private static void Fire(string reason)" not in s:
            return False
        f = s[s.index("private static void Fire(string reason)"):]
        if ("ApiClient.ReadTeamSeriesStatusOnce(series" not in f
                or "if (!ok)" not in f
                or "ApiClient.ReportTeamSeriesDc(" not in f):
            return False
        return f.index("if (!ok)") < f.index("ApiClient.ReportTeamSeriesDc(")

    _assert_discriminating(
        claim, ra,
        _mutate(ra, "                        if (!ok)", "                        if (false)",
                "H1 unknown state"),
        "H1 fallback server read")


def test_h1_a_peer_on_the_older_election_drops_the_room_to_the_floor_rule():
    """The census proves ONE reporter only among seats evaluating the census.  A
    seat that does not advertise cr_dc2 is running the previous OR'd election
    and will post regardless, so the rule is not room-wide and this seat must
    not act as though it were."""
    seats = _seats([(10, 0), (20, 1), (30, 1)])
    leaver = {"uid": 40, "team": 0}
    every = elect(seats, leaver, capable={10, 20, 30})
    assert len(_prompt(every)) == 1 and len(_watch(every)) == 1

    # one survivor on the old build: every seat falls to the floor election,
    # which is the rule that seat is already running.
    mixed = elect(seats, leaver, capable={20, 30})
    assert all(r == "prompt" for _u, _t, r in mixed), mixed
    assert _prompt(mixed), "the floor election still reports (#276)"
    assert all(t == "REAL" for _u, t, _d in mixed), mixed


def test_h1_the_leavers_own_team_cannot_downgrade_the_report():
    """#283 from the abandoned team's side.  Withholding a property, or
    advertising a team it is not on, is a leaver-side seat's only lever over the
    election.  It may move WHICH seats report; it must not change WHAT they
    report, because the alternative hands the party with the motive a one-property
    escape from a rated forfeit."""
    leaver = {"uid": 40, "team": 0}
    sabotage = [
        _seats([(10, 0), (20, 1), (30, 1)]),            # honest, for comparison
        _seats([(None, 0), (20, 1), (30, 1)]),          # no u_id
        _seats([(10, None), (20, 1), (30, 1)]),         # t_id outside {0,1}
        _seats([(10, 1), (20, 1), (30, 1)]),            # claims the other team
        _seats([(20, 0), (20, 1), (30, 1)]),            # duplicate id
    ]
    for seats in sabotage:
        for cap in (None, {20, 30}):                    # also with cr_dc2 withheld
            posts = elect(seats, leaver, capable=cap)
            assert posts, ("zero reporters", seats, cap)
            assert all(t == "REAL" for _u, t, _d in posts), (seats, cap, posts)
            # and someone reports without waiting, in every one of them
            assert _prompt(posts), (seats, cap, posts)


def test_h1_degenerate_seats_always_report_and_never_wait_for_a_seat_that_will_not():
    """Every way the census can be incomplete.  The bar: at least one PROMPT
    report in every one of them (#276 -- zero reporters is worse than the bug),
    and no seat sitting on a watch when no census elected anyone."""
    cases = [
        # a survivor with no advertised u_id
        (_seats([(10, 0), (None, 1), (30, 1)]), {"uid": 40, "team": 0}),
        # duplicate ids
        (_seats([(10, 0), (20, 1), (20, 1)]), {"uid": 40, "team": 0}),
        # a t_id outside {0,1} reads as unknown
        (_seats([(10, 0), (20, None), (30, 1)]), {"uid": 40, "team": 0}),
        # the leaver advertises no team
        (_seats([(10, 0), (20, 1), (30, 1)]), {"uid": 40, "team": None}),
        # the leaver advertises the WRONG team: the split is 3/1, not 2/2
        (_seats([(10, 0), (20, 1), (30, 1)]), {"uid": 40, "team": 1}),
        # a fourth survivor (roster mid-change): census is not 3
        (_seats([(10, 0), (20, 1), (30, 1), (50, 1)]), {"uid": 40, "team": 0}),
        # the leaver advertises no u_id
        (_seats([(10, 0), (20, 1), (30, 1)]), {"uid": None, "team": 0}),
    ]
    for seats, leaver in cases:
        posts = elect(seats, leaver)
        assert posts, ("zero reporters", seats, leaver)
        assert _prompt(posts), ("nobody reports promptly", seats, leaver, posts)
        assert not _watch(posts), ("a watch without an election", seats, leaver, posts)


def test_h1_mutation_dropping_the_split_check_reopens_the_race():
    """The negative control for the whole arm: without the 2/2 cross-check a
    leaver advertising the wrong team produces TWO seats posting real totals,
    which is precisely the straddle the finding describes."""
    seats = _seats([(10, 0), (20, 1), (30, 1)])
    leaver = {"uid": 40, "team": 1}          # lying: really on team 0

    def elect_without_split(seats, leaver):
        posts = []
        for me in seats:
            dc_team = leaver["team"]
            unique = dc_team is not None and me["team"] is not None and len(seats) == 3
            if unique and all(s["uid"] is not None and s["team"] is not None for s in seats):
                non_dc = [s["uid"] for s in seats if s["team"] != dc_team]
                if me["team"] != dc_team and me["uid"] == min(non_dc):
                    posts.append((me["uid"], "REAL"))
                continue
        return posts

    # the mutant elects team 0's lone survivor AND nothing cross-checks it
    mutant = elect_without_split(seats, leaver)
    assert mutant == [(10, "REAL")], mutant
    # the real election refuses the census (the split is 1 non-DC vs 3) and runs
    # the floor rule, which is what every peer in that room is running too.
    real = elect(seats, leaver)
    assert real and all(r == "prompt" for _u, _t, r in real), real


def test_h1_source_matches_the_model():
    src = _src("Plugin.cs")

    def claim(s):
        return ("bool roomWide = DcReportSync.AllCapable(survivors, out missingCap);" in s
                and "bool unique = teamsKnown && survivors.Count == 3 && roomWide;" in s
                and "dcTeamCount != 2 || nonDcCount != 2" in s
                and "PhotonNetwork.PlayerList" in s)

    _assert_discriminating(
        claim, src,
        _mutate(src,
                "bool unique = teamsKnown && survivors.Count == 3 && roomWide;",
                "bool unique = teamsKnown && survivors.Count == 3;", "H1 quorum"),
        "H1 room-wide quorum")


def test_h1_the_totals_are_this_seats_snapshot_in_both_arms():
    """The withdrawn zeros, asserted as an absence: no conditional may stand
    between the reported totals and what this seat observed.  A seat on the
    leaver's team could force the zero branch for the WHOLE room by withholding
    one property, which converts a forfeit the other team earned into
    dc_incomplete -- a client-attested cause moving the server AWAY from the
    conservative outcome (#283)."""
    src = _src("Plugin.cs")

    def claim(s):
        return ("int t1Points = GameStateWatcher.LastP1Points;" in s
                and "int t2Points = GameStateWatcher.LastP2Points;" in s
                and "conservativeOnly" not in s)

    _assert_discriminating(
        claim, src,
        _mutate(src, "int t1Points = GameStateWatcher.LastP1Points;",
                "int t1Points = conservativeOnly ? 0 : GameStateWatcher.LastP1Points;",
                "H1 honest totals"),
        "H1 honest totals")


def test_l3_dc_team_seat_stands_down_when_another_is_eligible():
    src = _src("Plugin.cs")

    def claim(s):
        return "if (teamsKnown && myTeam == dcTeam && otherEligible) return;" in s

    _assert_discriminating(
        claim, src,
        _mutate(src, "if (teamsKnown && myTeam == dcTeam && otherEligible) return;",
                "// stand-down removed", "L3"),
        "L3 DC-team stand-down")
    # and the model: with the split intact the DC-team survivor never posts
    seats = _seats([(10, 0), (20, 1), (30, 1)])
    assert 10 not in [u for u, _t, _d in elect(seats, {"uid": 40, "team": 0})]


# ══════════════════════════════════════════════════════════════════════════
# H2 / H3 / L8 -- the RPC dispatch guard
# ══════════════════════════════════════════════════════════════════════════

def test_h2_only_the_diagnosed_fault_class_is_contained():
    src = _src("VanillaFixes.cs")

    def claim(s):
        return ("if (!(__exception is NullReferenceException))" in s
                and s.count("return __exception;") >= 2)

    _assert_discriminating(
        claim, src,
        _mutate(src, "if (!(__exception is NullReferenceException))",
                "if (false)", "H2"),
        "H2 fault class")


def test_h3_the_local_send_leg_re_raises_and_the_discriminator_exists():
    src = _src("VanillaFixes.cs")

    def claim(s):
        return ("internal static class RpcLocalSendDepthPatch" in s
                and "if (!RpcLocalSendDepthPatch.Available || RpcLocalSendDepthPatch.InLocalSend)" in s
                and 'if (m.Name == "RPC" && !m.IsGenericMethodDefinition) list.Add(m);' in s)

    _assert_discriminating(
        claim, src,
        _mutate(src,
                "if (!RpcLocalSendDepthPatch.Available || RpcLocalSendDepthPatch.InLocalSend)",
                "if (false)", "H3"),
        "H3 entry path")


def test_h3_an_unavailable_discriminator_fails_toward_vanilla():
    """`Available` is only set from the class cleanup with no exception, so the
    default (never attached) is False and the guard contains nothing."""
    src = _src("VanillaFixes.cs")
    body = src[src.index("internal static class RpcLocalSendDepthPatch"):]
    body = body[:body.index("\n    }\n")]
    assert "internal static bool Available;" in body           # default false
    assert "if (exception == null) Available = true;" in body  # positive signal only
    assert body.count("Available = true") == 1


def test_h3_the_depth_counter_is_released_on_a_throwing_send():
    src = _src("VanillaFixes.cs")
    body = src[src.index("internal static class RpcLocalSendDepthPatch"):]
    body = body[:body.index("\n    }\n")]
    # a finalizer, not a postfix: a postfix does not run when the send throws,
    # and a pinned depth would disable the containment for the whole session.
    assert "[HarmonyFinalizer]" in body and "[HarmonyPostfix]" not in body
    assert "if (_depth > 0) _depth--;" in body


def test_l8_the_batch_rescue_claim_is_gone():
    src = _src("VanillaFixes.cs")

    # The corrected paragraph QUOTES the old sentence in order to retract it,
    # so "the words are absent" is the wrong test -- what must be absent is the
    # sentence in its ASSERTING form, and what must be present is the mechanism
    # note it contradicted.
    def claim(s):
        return ("with the finalizer the body aborts at the same statement" not in s
                and "RECORDS the exception and KEEPS DRAINING" in s
                and "there was never a batch to rescue" in s)

    _assert_discriminating(
        claim, src,
        _mutate(src, "there was never a batch to rescue",
                "with the finalizer the body aborts at the same statement",
                "L8"),
        "L8 batch-rescue contradiction")


# ══════════════════════════════════════════════════════════════════════════
# M1 / M2 -- freeze timing
# ══════════════════════════════════════════════════════════════════════════

def test_m1_the_reported_50_to_199ms_band_is_observable_and_bounded():
    src = _src("GameStateWatcher.cs")

    def claim(s):
        return ("private const float FREEZE_BAND_SEC = 0.05f;" in s
                and "if (wallGap > FREEZE_BAND_SEC && !inPickPhase)" in s
                and "FREEZE_BAND_EXEMPLAR_CAP = 10" in s
                and "FREEZE_BAND_SUMMARY_CAP = 12" in s)

    _assert_discriminating(
        claim, src,
        _mutate(src, "if (wallGap > FREEZE_BAND_SEC && !inPickPhase)",
                "if (wallGap > FREEZE_LOG_SEC && !inPickPhase)", "M1"),
        "M1 band trip")


def test_m1_volume_cap_is_a_number_not_a_hope():
    """The stated bound is 10 exemplars + 12 summaries per match.  A model of
    the emitter over a hostile input (a gap every single tick) must not exceed
    it, and the control shows the cap is what holds it down."""
    def emit(ticks, cap_ex, cap_sum, interval, clock_step):
        lines, ex, summ, last, pending = 0, 0, 0, -999.0, 0
        for i in range(ticks):
            ex_now = ex < cap_ex
            if ex_now:
                ex += 1
                lines += 1
            pending += 1
            t = i * clock_step
            if pending and summ < cap_sum and t - last >= interval:
                last = t
                summ += 1
                pending = 0
                lines += 1
        return lines

    assert emit(100000, 10, 12, 60.0, 0.016) <= 22
    # negative control: without the caps the same input floods
    assert emit(100000, 10 ** 9, 10 ** 9, 60.0, 0.016) > 22


def test_m1_the_three_counters_keep_their_0_5s_definition():
    """Widening the band must not move local_freeze_* -- that would be a third
    era of numbers wearing the same column names."""
    src = _src("GameStateWatcher.cs")
    blk = src[src.index("bool counted = wallGap > FREEZE_COUNT_SEC;"):]
    blk = blk[:blk.index("_lastTickStopwatchMs = nowMs;")]
    assert blk.count("localFreezeCount++;") == 1
    assert "if (counted)" in blk
    # the band arm must not touch them
    band = blk[blk.index("_bandCount++;"):]
    for name in ("localFreezeCount", "localFreezeFocusedCount", "localFreezeTotalSec"):
        assert name not in band, name


def test_m2_a_counting_semantic_epoch_rides_every_carrier():
    gsw = _src("GameStateWatcher.cs")
    api = _src("ApiClient.cs")

    def claim(s):
        return ("internal const int FREEZE_COUNT_EPOCH = 2;" in s
                and 'localFreezeEpoch: FREEZE_COUNT_EPOCH,' in s
                and "$\"|{FREEZE_COUNT_EPOCH}\";" in s
                and "if (parts.Length >= 24)" in s)

    _assert_discriminating(
        claim, gsw,
        _mutate(gsw, "internal const int FREEZE_COUNT_EPOCH = 2;",
                "// epoch removed", "M2"),
        "M2 epoch")
    assert '"local_freeze_epoch\\":{localFreezeEpoch}' in api
    assert '"opp_freeze_epoch\\":{oppFreezeEpoch}' in api


def test_m2_an_untagged_peer_reads_as_unknown_not_as_ours():
    gsw = _src("GameStateWatcher.cs")
    assert "public static bool OppFreezeCountersUsable => OppFreezeEpoch == FREEZE_COUNT_EPOCH;" in gsw
    # a peer that never sent field 24 leaves the parse at 0, and 0 != 2
    assert "int _oppFreezeEra = 0;" in gsw
    assert gsw.count("OppFreezeEpoch = 0;") == 2          # both match resets
    # negative control: the model of the comparison
    for era, usable in ((0, False), (1, False), (2, True), (3, False)):
        assert (era == 2) is usable


# ══════════════════════════════════════════════════════════════════════════
# M3 -- every WATCH pre-dispatch refusal says something
# ══════════════════════════════════════════════════════════════════════════

def test_m3_no_silent_return_remains_before_the_grant_dispatch():
    src = _src("ApiClient.cs")
    head = src[src.index("private static int RequestSpectateGrantCore(string gameId, bool broadcastTicket)"):]
    head = head[:head.index("spectateGrantInFlight = true;")]

    def claim(s):
        if "private static int RequestSpectateGrantCore" not in s:
            return False
        h = s[s.index("private static int RequestSpectateGrantCore"):]
        h = h[:h.index("spectateGrantInFlight = true;")] if "spectateGrantInFlight = true;" in h else h
        # Every `return 0;` in the pre-dispatch head must SPEAK. The window is
        # the guard that owns the return -- from the last `if (` before it --
        # so a neighbouring arm's toast cannot vouch for a silent one.
        chunks = h.split("return 0;")[:-1]
        if len(chunks) < 4:
            return False
        for c in chunks:
            # The owner window is the GUARD that owns the return -- the last
            # statement-level `if (` before it, at the method's own indentation.
            # Taking the last `if (` of any depth would take the nested
            # `if (!broadcastTicket)` instead, which is precisely the conditional
            # voice this predicate has to see past.
            cut = c.rfind("\n            if (")
            owner = c[cut:] if cut >= 0 else c
            # It must speak to SOMEBODY, whoever asked.  The first version of
            # this predicate accepted a ShowNotification, full stop -- and the
            # broadcast-transport arm's only voice was a toast nested under
            # `if (!broadcastTicket)`, so with a broadcast ticket the method
            # returned zero in silence and this check stayed green.  A guard
            # whose only voice is conditional on the caller is a silent guard
            # for the other caller (#430).
            speaks_always = "Plugin.Log.Log" in owner
            toast_only = "ShowNotification" in owner and "if (!broadcastTicket)" not in owner
            if not (speaks_always or toast_only):
                return False
        return True

    mutated = _mutate(
        src,
        """            if (spectateGrantInFlight)
            {
                Plugin.Log.LogInfo("[SPECTATE] WATCH declined before dispatch: a grant is already in flight");
                if (!broadcastTicket)
                    CompetitiveUI.ShowNotification(I18n.Tr("Still finishing your last spectate request - try again in a moment."),
                                                   Color.yellow, 4f);
                return 0;
            }""",
        """            if (spectateGrantInFlight) return 0;""",
        "M3")
    _assert_discriminating(claim, src, mutated, "M3 silent refusals")
    assert "Still finishing your last spectate request" in head


# ══════════════════════════════════════════════════════════════════════════
# M5 / L2 / M4 -- chat drafts
# ══════════════════════════════════════════════════════════════════════════

def test_m5_consent_revocation_clears_the_live_line_too():
    src = _src("CompetitiveUI.cs")
    body = _method_body(src, "internal static void DropChatDraftOnRevoke()")
    assert body, "the revoke method's own text could not be delimited"

    def claim(s):
        b = _method_body(s, "internal static void DropChatDraftOnRevoke()")
        return bool(b) and "DropStash();" in b and 'chatInputText = "";' in b

    _assert_discriminating(
        claim, src,
        _mutate(src, 'DropStash();\n            chatInputText = "";',
                "DropStash();", "M5"),
        "M5 revoke clears live input")
    assert "chatResumeNoticeUntil = -999f;" in body

    # THE CONTROL THAT MATTERS, and the one this test did not have: the exact
    # PRE-FIX shape, a one-line stash-only method with the account-change hook
    # (which does clear the live line) right underneath it.  The predicate used
    # to answer True here -- the window ran past the one-liner and read the
    # neighbour's statements -- so the regression M5 exists to catch could land
    # with the suite green.  Reverting the fix must go RED, on the real shape of
    # the revert and not only on a synthetic edit.
    pre_fix = (
        "        internal static void DropChatDraftOnRevoke() { DropStash(); }\n"
        "\n"
        "        /// <summary>The resolved account CHANGED.</summary>\n"
        "        internal static void DropChatOnAccountChange()\n"
        "        {\n"
        "            DropStash();\n"
        '            chatInputText = "";\n'
        "            chatResumeNoticeUntil = -999f;\n"
        "        }\n")
    assert not claim(pre_fix), "the claim holds on the pre-fix tree: it is not evidence"

    def claim_before_this_round(s):
        """The predicate as it was written, kept as the negative control for the
        HARNESS fix itself: it must answer True on the pre-fix shape, or the
        defect being fixed here was not real (#391)."""
        if "internal static void DropChatDraftOnRevoke()" not in s:
            return False
        b = s[s.index("internal static void DropChatDraftOnRevoke()"):]
        b = b[:b.index("\n        }") + 10]
        return "DropStash();" in b and 'chatInputText = "";' in b

    assert claim_before_this_round(pre_fix), "the harness defect does not reproduce"
    assert claim(src), "the repaired predicate must still hold on the tree"


def test_l2_the_stash_reader_applies_the_identity_rule_its_comment_states():
    src = _src("CompetitiveUI.cs")

    def claim(s):
        b = _method_body(s, "private static string TakeStashedDraft()")
        return bool(b) and "chatDraftStashIdentity" in b and "MatchTracker.LocalSteamId" in b

    _assert_discriminating(
        claim, src,
        _mutate(src, "string writer = chatDraftStashIdentity;", "string writer = null;", "L2"),
        "L2 stash identity")
    # the writer is recorded where the stash is written, or the reader has nothing
    assert "chatDraftStashIdentity = who;" in src


def test_l2_the_null_writer_contract_is_enforced_and_is_not_symmetric():
    """The field's doc says "null means stashed before an identity was
    resolvable, and only matches another null".  The reader applied half of
    that: a known writer against a different reader destroyed the stash, but a
    NULL writer was handed to whatever account resolved afterwards, as long as
    the channel and the TTL still matched.

    The two unresolved cases are deliberately NOT symmetric.  An unresolved
    READER leaves the question open -- that is the first-resolution shape
    DropChatOnAccountChange also refuses to treat as a change.  An unresolved
    WRITER answers it against resuming: it is not evidence that the line was
    this account's, and a draft is not worth resuming into an account that
    cannot be shown to have written it."""
    def keeps(writer, reader):
        resolved = bool(reader) and reader != "unknown"
        if resolved and writer and writer != reader:
            return False
        if resolved and not writer:
            return False
        return True

    assert keeps("A", "A") is True
    assert keeps("A", "B") is False
    assert keeps("A", None) is True        # unresolved reader: keep
    assert keeps("A", "unknown") is True
    assert keeps(None, "B") is False       # unresolved WRITER, resolved reader: drop
    assert keeps(None, None) is True       # null matches null
    assert keeps(None, "unknown") is True

    src = _src("CompetitiveUI.cs")
    body = _method_body(src, "private static string TakeStashedDraft()")
    assert body, "the reader's own text could not be delimited"

    def claim(s):
        b = _method_body(s, "private static string TakeStashedDraft()")
        return bool(b) and "if (readerResolved && string.IsNullOrEmpty(writer))" in b

    _assert_discriminating(
        claim, src,
        _mutate(src, "if (readerResolved && string.IsNullOrEmpty(writer))",
                "if (false)", "L2 null writer"),
        "L2 null-writer contract")


def test_m4_the_351_citation_names_which_351():
    src = _src("CompetitiveUI.cs")

    def claim(s):
        return "LEARNING\n                // #351" in s and "NOT bug report #351" in s

    _assert_discriminating(
        claim, src,
        _mutate(src, "LEARNING\n                // #351", "#351", "M4"),
        "M4 mis-cite")


# ══════════════════════════════════════════════════════════════════════════
# M6 -- chat measurement failure
# ══════════════════════════════════════════════════════════════════════════

def fit(line, measure, max_h, single_h, per_line_chars, wrap_lines):
    """Model of ChatOverlayTmp.Measure's decision.  `measure` returns a height
    or None when the API gives no answer."""
    measured = measure(line)
    unmeasurable = measured is None
    disp, h = line, (max_h if unmeasurable else measured)
    marker = False
    if unmeasurable or h > max_h:
        min_cut = line.rfind(">") + 1 or 1
        if min_cut < len(line) - 1:
            if unmeasurable:
                best = max(min(min_cut + 1, len(line)),
                           min(per_line_chars * wrap_lines, len(line)))
            else:
                lo, hi, best = min(min_cut + 1, len(line)), len(line), min_cut + 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    probe = measure(line[:mid].rstrip() + " ... [see F5]")
                    if probe is not None and probe <= max_h:
                        best, lo = mid, mid + 1
                    else:
                        hi = mid - 1
            disp = line[:best].rstrip() + " ... [see F5]"
            marker = True
            fh = measure(disp)
            h = fh if fh is not None else max_h
    if h <= 0:
        h = single_h
    return disp, h, marker


def test_m6_a_wholesale_measurement_failure_truncates_and_marks():
    long_line = "<color=#fff>name</color>" + ("x" * 2000)
    disp, h, marker = fit(long_line, lambda _t: None, max_h=50.0, single_h=19.5,
                          per_line_chars=58, wrap_lines=3)
    assert marker, "no indicator on an unmeasurable line"
    assert disp.endswith("[see F5]")
    assert len(disp) < len(long_line)
    assert h == 50.0, "the rect must claim the full allowance, not one line"


def test_m6_negative_control_the_old_one_line_floor_never_cuts():
    """The behaviour the finding describes: floor a failed measurement to one
    line and the cut can never trigger."""
    long_line = "<color=#fff>name</color>" + ("x" * 2000)

    def old_fit(line, single_h, max_h):
        h = single_h                       # Height()'s old failure floor
        if h > max_h:
            return line[:10] + " ... [see F5]", True
        return line, False

    disp, marker = old_fit(long_line, 19.5, 50.0)
    assert not marker and disp == long_line

    # and a healthy measurement still binary-searches to a real cut
    def healthy(text):
        return 19.5 * (1 + len(text) // 58)

    disp2, _h2, marker2 = fit(long_line, healthy, max_h=50.0, single_h=19.5,
                              per_line_chars=58, wrap_lines=3)
    assert marker2 and len(disp2) < len(long_line)


def test_m6_a_failed_probe_inside_the_search_is_not_a_fit():
    src = _src("ChatOverlayTmp.cs")

    def claim(s):
        return ("private static float HeightOrFail(object tmp, string text)" in s
                and "if (h >= 0f && h <= maxH) { best = cut; lo = mid + 1; }" in s
                and "WarnMeasurementUnavailable();" in s)

    _assert_discriminating(
        claim, src,
        _mutate(src, "if (h >= 0f && h <= maxH) { best = cut; lo = mid + 1; }",
                "if (h <= maxH) { best = cut; lo = mid + 1; }", "M6"),
        "M6 failed probe")


# ══════════════════════════════════════════════════════════════════════════
# M7 -- #380 corpse targeting, gated whole-room
# ══════════════════════════════════════════════════════════════════════════

def test_m7_a_corpse_never_holds_the_slot_while_a_live_target_is_in_range():
    """Model of vanilla's selector over the filtered list."""
    def vanilla_pick(players, owner, in_range):
        chosen = None
        for p in players:
            if p is owner or not in_range(p):
                continue
            chosen = p                      # last in list wins, no break, no dead check
        return chosen

    owner = {"id": 0, "dead": False}
    corpse = {"id": 1, "dead": True}
    live = {"id": 2, "dead": False}
    roster = [owner, live, corpse]          # the corpse sorts LAST: vanilla picks it
    assert vanilla_pick(roster, owner, lambda p: True) is corpse

    filtered = [p for p in roster if not p["dead"]]
    assert vanilla_pick(filtered, owner, lambda p: True) is live


def test_m7_rng_phase_is_preserved_because_the_swap_needs_a_live_target():
    """One draw is taken iff the target branch is entered.  The swap engages
    only when a live target is in range, so both worlds enter the branch; when
    only a corpse is in range nothing is swapped, so both worlds still agree."""
    def draws(players, owner, swap_enabled):
        in_range = [p for p in players if p is not owner]
        corpse_in = any(p["dead"] for p in in_range)
        live_in = any(not p["dead"] for p in in_range)
        if swap_enabled and corpse_in and live_in:
            in_range = [p for p in in_range if not p["dead"]]
        return 1 if in_range else 0

    owner = {"id": 0, "dead": False}
    for roster in ([owner, {"id": 1, "dead": True}],
                   [owner, {"id": 1, "dead": False}],
                   [owner, {"id": 1, "dead": True}, {"id": 2, "dead": False}],
                   [owner]):
        assert draws(roster, owner, True) == draws(roster, owner, False), roster


def test_m7_the_change_is_gated_on_a_whole_room_quorum():
    src = _src("VanillaFixes.cs")

    def claim(s):
        return ('internal const string CapabilityProp = "cr_saw1";' in s
                and "if (!SawTargetSync.ShouldApply()) return;" in s
                and "if (!corpseInRange || !liveInRange) return;" in s)

    _assert_discriminating(
        claim, src,
        _mutate(src, "if (!SawTargetSync.ShouldApply()) return;", "// ungated", "M7"),
        "M7 quorum gate")


def test_m7_the_quorum_fails_closed_on_every_arm():
    src = _src("VanillaFixes.cs")
    body = src[src.index("internal static class SawTargetSync"):]
    body = body[:body.index("\n    /// <summary>Bug #380, second half")]
    assert "if (list == null || list.Length == 0) return false;" in body   # every(empty)
    assert "if (fighterCount == 0) return false;" in body
    assert "if (Plugin.modDisabled || !PatchesLive) return false;" in body
    # the replicated read, never the first-sight cache: see the class sweep test
    assert "if (RoomActors.IsSpectatorReplicated(actor)) continue;" in body
    # the basis is the replicated list, never the locally frozen roster
    assert "PhotonNetwork.PlayerList" in body
    assert "RoomActors.ActiveFighters" not in body
    # no refuted predicate anywhere in the gate
    assert "IsCompetitiveRoom" not in body and "mod_version" not in body

    def model(fighters):
        return bool(fighters) and all(fighters)

    assert model([]) is False
    assert model([True, True]) is True
    assert model([True, False]) is False


def test_m7_the_restore_runs_even_when_the_original_throws():
    src = _src("VanillaFixes.cs")
    body = src[src.index("internal static class SawLiveTargetPatch"):]
    body = body[:body.index("\n    }\n") + 6]
    assert "[HarmonyFinalizer]" in body
    assert "RestoreOrder();" in body
    assert "return __exception;" in body        # observes, never contains


def test_m7_the_window_changes_order_and_never_membership():
    """The roster field stays changed for the WHOLE of Saw.Update -- the inline
    damage call and everything ROUNDS reaches from it included -- so what that
    window holds is the property that matters.  A live-only list would put the
    game in a state it never otherwise has (a lookup by id returning null, a
    short count) for code this patch has not modelled.  A reorder of the game's
    own list cannot: same object, same members, same count."""
    src = _src("VanillaFixes.cs")
    body = src[src.index("internal static class SawLiveTargetPatch"):]
    body = body[:body.index("\n    }\n") + 6]

    # no substitution of the roster field anywhere in the patch
    assert "PlayerManager.instance.players =" not in body
    assert "players[w++] = q;" in body          # written in place, by index

    def claim(s):
        if "internal static class SawLiveTargetPatch" not in s:
            return False
        b = s[s.index("internal static class SawLiveTargetPatch"):]
        b = b[:b.index("\n    }\n") + 6]
        return "PlayerManager.instance.players =" not in b and "players[w++] = q;" in b

    _assert_discriminating(
        claim, src,
        _mutate(src, "                _masked = true;",
                "                PlayerManager.instance.players = _order;\n                _masked = true;",
                "M7 in place"),
        "M7 reorder in place")


def test_m7_a_membership_change_inside_the_window_is_not_overwritten():
    """Restoring an order is safe; restoring a stale MEMBERSHIP is not.  If the
    frame's own bookkeeping rewrote the roster while the window was open, the
    list is its business and the patch leaves it alone -- and says so, because a
    silent refusal here would be indistinguishable from a restore that worked."""
    src = _src("VanillaFixes.cs")
    body = src[src.index("private static void RestoreOrder()"):]
    body = body[:body.index("\n        [HarmonyFinalizer]")]
    assert "players.Count == _order.Count" in body
    assert "players.Contains(_order[i])" in body
    assert "DiagLimited(" in body

    def claim(s):
        if "private static void RestoreOrder()" not in s:
            return False
        b = s[s.index("private static void RestoreOrder()"):]
        b = b[:b.index("\n        [HarmonyFinalizer]")]
        return "players.Count == _order.Count" in b and "players.Contains(_order[i])" in b

    _assert_discriminating(
        claim, src,
        _mutate(src, "bool sameCount = players != null && players.Count == _order.Count;",
                "bool sameCount = players != null;", "M7 membership"),
        "M7 membership guard")


def test_m7_the_ungated_postfix_stands_down_inside_the_window():
    """Harmony runs every postfix before any finalizer, so the corpse-particle
    postfix executes inside the fall-through patch's window, over the order that
    patch arranged.  Without the stand-down its verdict is a function of the
    OTHER patch's quorum -- benign today, because the chosen target is alive, and
    exactly the kind of coupling that stops being benign silently."""
    src = _src("VanillaFixes.cs")

    def claim(s):
        if "internal static class SawDeadTargetPatch" not in s:
            return False
        b = s[s.index("internal static class SawDeadTargetPatch"):]
        b = b[:b.index("\n    }\n") + 6]
        # the stand-down is BEFORE the selector re-run, or it is not a stand-down
        anchor = "if (SawLiveTargetPatch.WindowOpen) {"
        if anchor not in b or "Player vanillaTarget = Select(" not in b:
            return False
        return b.index(anchor) < b.index("Player vanillaTarget = Select(")

    _assert_discriminating(
        claim, src,
        _mutate(src,
                "                if (SawLiveTargetPatch.WindowOpen) "
                "{ SawLiveTargetPatch.NotePostfixStoodDown(); return; }",
                "                // postfix runs inside the window", "M7 stand-down"),
        "M7 postfix stand-down")


def test_m7_the_verdict_line_is_per_room_and_not_per_process():
    """SawTargetSync.ResetForRoomChange existed with NO caller, so the [SAW-TARGET]
    verdict -- the only positive signal that the whole-room gate was evaluated --
    was de-duplicated for the life of the PROCESS.  A player's second room of a
    session logged nothing, and a bundle cannot then tell "the gate applied in that
    room" from "the patch never attached"."""
    plug = _src("Plugin.cs")
    vf = _src("VanillaFixes.cs")
    assert "internal static void ResetForRoomChange()" in vf
    assert plug.count("SawTargetSync.ResetForRoomChange();") >= 2   # join AND leave edges

    def claim(s):
        return "SawTargetSync.ResetForRoomChange();" in s

    _assert_discriminating(
        claim, plug,
        plug.replace("SawTargetSync.ResetForRoomChange();", "// no caller"),
        "M7 per-room verdict")


# ══════════════════════════════════════════════════════════════════════════
# L1 -- the spectate reason is decided by the detail field
# ══════════════════════════════════════════════════════════════════════════

KEYS = ["spectator_full", "spectating_disabled", "game_not_live", "already_in_game",
        "room_not_ready", "mode_not_ready", "spectator_upgrade_required", "session_required"]


def reason(body, detail=None, ordered=KEYS):
    """Model of ApiClient.SpectateReason's three readings."""
    if body.strip() in ordered:
        return body.strip()
    if detail and detail.strip() in ordered:
        return detail.strip()
    for k in ordered:
        if k in body:
            return k
    return "unavailable"


def test_l1_a_body_with_two_keys_resolves_by_the_detail_field():
    body = '{"detail":"mode_not_ready","room":"room_not_ready pending"}'
    assert reason(body, detail="mode_not_ready") == "mode_not_ready"
    # negative control: the ordered chain alone answers with whatever sits higher
    assert reason(body, detail=None) == "room_not_ready"


def test_l1_a_bare_listing_token_still_resolves_exactly():
    for k in KEYS:
        assert reason(k) == k


def test_l1_the_source_reads_detail_before_the_ordered_chain():
    src = _src("ApiClient.cs")

    def claim(s):
        if "private static string SpectateReason(string reason, bool full)" not in s:
            return False
        b = s[s.index("private static string SpectateReason(string reason, bool full)"):]
        if "private static string SpectateReasonExact" not in b:
            return False
        b = b[:b.index("private static string SpectateReasonExact")]
        if 'ExtractJsonString(r, "detail")' not in b:
            return False
        if 'if (r.Contains("spectator_full"))' not in b:
            return False
        return (b.index('ExtractJsonString(r, "detail")')
                < b.index('if (r.Contains("spectator_full"))'))

    _assert_discriminating(
        claim, src,
        _mutate(src, 'try { detail = ExtractJsonString(r, "detail"); } catch { }',
                "detail = null;", "L1"),
        "L1 detail precedence")


def test_l1_every_ordered_key_has_an_exact_arm():
    src = _src("ApiClient.cs")
    exact = _method_body(src, "private static string SpectateReasonExact")
    assert exact, "the exact-arm method's own text could not be delimited"
    for k in KEYS:
        assert 'case "%s":' % k in exact, k


# ══════════════════════════════════════════════════════════════════════════
# L4 / L5 / L6 / L7 / L9 / L10
# ══════════════════════════════════════════════════════════════════════════

def test_l4_the_dc_comments_match_the_deployed_contract():
    api = _src("ApiClient.cs")
    plug = _src("Plugin.cs")

    def claim(s):
        return ("5-min sticky-team requeue grace window" not in s
                and "any\n        /// match abandoned with >=2 total points" not in s)

    assert claim(api) and claim(plug)
    assert "dc_manual_pending" in api and "dc_manual_pending" in plug
    assert "already won at least one game" in api
    # negative control: the old sentence would fail the claim
    assert not claim("starts\n// the 5-min sticky-team requeue grace window.")


def test_l5_a_half_built_portrait_row_is_not_frozen_for_the_process():
    src = _src("PortraitRender.cs")

    def claim(s):
        return ("if (slots < PresetSlotsFallback)" in s
                and "_presetProvisional = slots;" in s
                and "_presetSweptAt" in s)

    _assert_discriminating(
        claim, src,
        _mutate(src, "if (slots < PresetSlotsFallback)", "if (false)", "L5"),
        "L5 provisional count")

    def model(discoveries, fallback=8):
        """The cached value over a row that finishes building."""
        cached = 0
        for d in discoveries:
            if cached:
                continue
            if d >= fallback:
                cached = d
        return cached

    assert model([3, 5, 8]) == 8            # self-heals
    # negative control: caching the first positive answer strands it at 3
    def old(discoveries):
        for d in discoveries:
            if d > 0:
                return d
        return 0
    assert old([3, 5, 8]) == 3


def test_l6_the_minus_one_claim_is_stated_as_what_holds():
    src = _src("PortraitRender.cs")

    def claim(s):
        return ("never crosses the wire, never reaches a filename" in s
                and '"-1 never enters a cache\n        /// key"' in s)

    _assert_discriminating(
        claim, src,
        _mutate(src, "never crosses the wire, never reaches a filename",
                "never enters a cache key", "L6"),
        "L6 corrected claim")
    # the key still carries the preset, which is the behaviour the claim protects
    assert '+ "|" + CurrentPreset()' in src


def test_l7_the_mapcolor_count_is_stated_truthfully():
    src = _src("Plugin.cs")

    def claim(s):
        return ("108 emissions counted twice" in s
                and "this wrote 216 lines in one" not in s)

    _assert_discriminating(
        claim, src,
        _mutate(src, "108 emissions counted twice", "216 emissions", "L7"),
        "L7 216/108")


def test_l9_every_changed_key_reaches_all_four_embedded_locales():
    cat = _src("I18nCatalogues.cs")
    keys = [
        "Account changed — message not sent.",
        "Chat [{0}]  —  Enter to send, Esc keeps your draft, Alt switches channel",
        "Game ended", "Mode closed", "Not ready yet", "Player opted out",
        "Seats full", "Session expired",
        "Steam session expired — try again in a moment.",
        "That game is not ready to watch yet.",
        "That mode is not accepting spectators right now.",
        "Unavailable", "Update required", "Update the mod to watch this game.",
        "You're in a game", "draft restored",
        "Still finishing your last spectate request - try again in a moment.",
    ]
    blocks = cat.split("private static readonly Dictionary<string, string> ")[1:]
    assert [b[:2] for b in blocks] == ["ES", "RU", "UK", "SV"]
    for k in keys:
        for b in blocks:
            assert ('["%s"] =' % k) in b, (b[:2], k)
    # every one of them is also in the extracted source registry
    gen = _src("I18nSourceKeys.g.cs")
    for k in keys:
        assert ('"%s",' % k) in gen, k
    # negative control: a key that was never added is absent from both
    assert '["Seats full but invented"] =' not in cat


def test_l9_the_drafts_preserve_the_tag_and_placeholder_sequence():
    import re
    cat = _src("I18nCatalogues.cs")
    entry = re.compile(r'^\s+\["((?:[^"\\]|\\.)*)"\] = "((?:[^"\\]|\\.)*)",$', re.M)
    tag = re.compile(r"<[^<>]+>")
    checked = 0
    for src_s, dst_s in entry.findall(cat):
        if "spectate" not in src_s and "Seats full" not in src_s and "{0}" not in src_s:
            continue
        assert tag.findall(src_s) == tag.findall(dst_s), src_s
        assert src_s.count("{0}") == dst_s.count("{0}"), src_s
        checked += 1
    assert checked > 0


def test_l10_the_changed_files_carry_role_terminology_not_a_maintainer_name():
    src = _src("VanillaFixes.cs")
    doc = src[src.index("/// <summary>Bug #380 —"):src.index("internal static class SawDeadTargetPatch")]

    def claim(s):
        return "Sid" not in s and "product decision" in s

    _assert_discriminating(
        claim, doc,
        _mutate(doc, "a product decision", "Sid's call", "L10"),
        "L10 role terminology")


# ══════════════════════════════════════════════════════════════════════════
# Round-2 lens findings -- the class sweeps and the delivery half
# ══════════════════════════════════════════════════════════════════════════

def test_every_cross_seat_roster_filter_reads_the_replicated_property():
    """#432: the flag named the census, the defect is the class.  Three rules
    have to agree across seats -- the DC census, the saw quorum, the grow quorum
    -- and all three filtered spectators through RoomActors.IsSpectator, which
    caches its answer at THIS seat's first sight of an actor and never re-reads
    the property.  Two seats that first look at different moments can hold
    different rosters for the whole room, which is two rules, not one.

    PoisonSync was ruled OUT of that sweep one round ago, on the reading that
    its roster GRANTS authority.  It does not: ScanRoster decides a fail-closed
    capability REFUSAL, and an actor read as a fighter on one seat and a
    spectator on another splits the sticky incapability flag, the roster
    quarantine and victim-side block honouring -- which reaches fighter damage.
    It is swept now, together with the two room-edge gates that feed it, and the
    helper's own doc no longer names it as a cache caller (#302, #432)."""
    plug = _src("Plugin.cs")
    vf = _src("VanillaFixes.cs")
    ps = _src("PoisonSync.cs")

    # the census
    census = plug[plug.index("var survivors = new List<Photon.Realtime.Player>();"):]
    census = census[:census.index("catch { survivors.Clear(); }")]
    assert "RoomActors.IsSpectatorReplicated(a)" in census
    assert "RoomActors.IsSpectator(a)" not in census

    # both quorums
    assert vf.count("RoomActors.IsSpectatorReplicated(actor)") == 2
    assert "RoomActors.IsSpectator(actor)" not in vf

    # PoisonSync's own capability roster, both halves of it
    assert ps.count("RoomActors.IsSpectatorReplicated(list[i])") == 2
    assert "RoomActors.IsSpectator(list[i])" not in ps

    # the two room-edge gates that arm the same rule.  Each is asserted inside
    # the span of the statement it belongs to, not file-wide: Plugin.cs keeps
    # LOCAL IsSpectator callers on purpose (the master's spectator validation,
    # the face re-send), and a file-wide absence check would be a claim the tree
    # cannot satisfy and would have to be weakened into one that cannot fail.
    entry = plug[plug.index("bool entrantIsSpectatorReplicated = false;"):]
    entry = entry[:entry.index("PoisonSync.NoteRosterChange(\"PlayerEntered\");") + 45]
    assert "RoomActors.IsSpectatorReplicated(p)" in entry
    assert "if (!entrantIsSpectatorReplicated)" in entry

    leave = plug[plug.index("bool leaverIsSpectatorReplicated = false;"):]
    leave = leave[:leave.index("catch { }")]
    assert "RoomActors.IsSpectatorReplicated(p)" in leave
    assert "RoomActors.IsSpectator(p)" not in leave

    # and the helper itself reads the property every call -- no cache to fall back on
    ra = _src("RoomActors.cs")
    body = _method_body(ra, "internal static bool IsSpectatorReplicated(PhotonPlayer actor)")
    assert body and "props.ContainsKey(SPEC_PROP)" in body
    assert "_roleByActor" not in body

    # the doc that told the next caller which one to pick no longer sends them
    # to the cache for this case
    doc = ra[ra.index("/// <para>WHICH ONE A CALLER WANTS."):
             ra.index("internal static bool IsSpectatorReplicated(PhotonPlayer actor)")]
    assert "PoisonSync" in doc and "authority roster" not in doc

    def claim(s):
        return ("RoomActors.IsSpectatorReplicated(actor)" in s
                and "RoomActors.IsSpectator(actor)" not in s)

    _assert_discriminating(
        claim, vf,
        _mutate(vf, "if (RoomActors.IsSpectatorReplicated(actor)) continue;",
                "if (RoomActors.IsSpectator(actor)) continue;", "sweep"),
        "cross-seat roster basis")

    def poison_claim(s):
        return (s.count("RoomActors.IsSpectatorReplicated(list[i])") == 2
                and "RoomActors.IsSpectator(list[i])" not in s)

    _assert_discriminating(
        poison_claim, ps,
        _mutate(ps, "if (list[i] != null && !RoomActors.IsSpectatorReplicated(list[i])) n++;",
                "if (list[i] != null && !RoomActors.IsSpectator(list[i])) n++;", "poison sweep"),
        "PoisonSync roster basis")


def test_the_dc_report_is_retried_and_carries_the_room_it_was_observed_in():
    """A single un-retried request was the whole mechanism, on the path whose
    failure leaves the series open and every survivor holding a 2v2 lease.  The
    retry is safe against the DEPLOYED endpoint, which re-reads the row under
    FOR NO KEY UPDATE and answers {"ignored": true} unless the status is still
    active/dc_paused -- so a repeat cannot double-apply ratings or gold."""
    src = _src("ApiClient.cs")
    body = _method_body(src, "private static IEnumerator SendTeamSeriesDcReport")
    assert body, "the dispatch method's own text could not be delimited"
    assert "PostRequestWithRetry(url" in body
    # the lock mode is the DEPLOYED one, read off production 0cc7f75 rather than
    # remembered: the row re-read takes FOR NO KEY UPDATE; FOR UPDATE is what the
    # completion helper beneath it takes, and the doc used to name the wrong one.
    assert "FOR NO KEY UPDATE" in src
    doc = src[src.index("/// <para>DELIVERY."):src.index("public static void ReportTeamSeriesDc")]
    assert "FOR NO KEY UPDATE" in doc and "re-reads the row under FOR UPDATE" not in doc

    def claim(s):
        b = _method_body(s, "private static IEnumerator SendTeamSeriesDcReport")
        return bool(b) and "PostRequestWithRetry(url" in b

    _assert_discriminating(
        claim, src,
        _mutate(src, "PostRequestWithRetry(url, \"\", (ok, resp) =>\n            {\n                if (ok) Plugin.Log.LogInfo($\"[2v2-DC] report accepted",
                "PostRequest(url, \"\", (ok, resp) =>\n            {\n                if (ok) Plugin.Log.LogInfo($\"[2v2-DC] report accepted",
                "DC retry"),
        "DC report retry")

    # the room is the observation's, not the dispatch's: a delayed send can have
    # left the room, and an empty hint reads to the endpoint as an old client and
    # passes straight through the bug-245 resume fence.
    def room_claim(s):
        return ("string dcRoom = observedRoom;" in s
                and "string observedRoom = null, bool fallback = false)" in s)

    _assert_discriminating(
        room_claim, src,
        _mutate(src, "string dcRoom = observedRoom;", "string dcRoom = null;", "DC room"),
        "DC observed room")

    plug = _src("Plugin.cs")
    assert "ApiClient.ReportTeamSeriesDc(seriesId, myId, dcSteamId, t1Points, t2Points,\n                                             observedRoom, false);" in plug
    # and the room is captured at the OBSERVATION, before either arm can leave:
    # the watch arm returns without posting, so its eventual fallback carries the
    # room the disconnect was seen in and not whatever room it is in by then.
    head = plug[plug.index("string observedRoom = \"\";"):]
    assert head.index("DcReportSync.ArmFallback(") < head.index("ApiClient.ReportTeamSeriesDc(")


def test_the_dc_election_capability_follows_the_pre_join_protocol():
    """cr_dc2 says "this seat elects from the census".  Staged pre-join only: an
    in-room write is present locally at once and may reach peers after they have
    already evaluated a census, which is a seat advertising a rule it is not
    running at the moment that matters."""
    ra = _src("RoomActors.cs")
    body = ra[ra.index("internal static class DcReportSync"):]

    assert 'internal const string CapabilityProp = "cr_dc2";' in body
    assert "if (PhotonNetwork.InRoom)" in body            # refuses an in-room write
    assert "if (Plugin.modDisabled) { _stageFailedPermanently = true; return; }" in body
    assert "if (survivors == null || survivors.Count == 0) return false;" in body   # every(empty)
    # ...and not before the compatibility verdict: a capability staged inside
    # that window by a seat the verdict then disables can only be withdrawn with
    # an IN-ROOM write, which is the path the line above refuses.
    stage = body[body.index("internal static void StageCapability(string source)"):]
    stage = stage[:stage.index("internal static void RevokeCapability()")]
    assert "if (!Plugin.compatCheckComplete)" in stage
    assert stage.index("if (!Plugin.compatCheckComplete)") < stage.index("if (PhotonNetwork.InRoom)")
    assert "deferred staging" in stage                    # the refusal SPEAKS

    plug = _src("Plugin.cs")
    vf = _src("VanillaFixes.cs")
    assert 'DcReportSync.StageCapability("tick");' in plug
    assert 'DcReportSync.StageCapability("pre-join");' in vf
    assert "DcReportSync.RevokeCapability();" in plug     # withdrawn on compat-disable

    def claim(s):
        if "internal static class DcReportSync" not in s:
            return False
        b = s[s.index("internal static class DcReportSync"):]
        return "if (PhotonNetwork.InRoom)" in b and "_stageFailedPermanently" in b

    _assert_discriminating(
        claim, ra,
        _mutate(ra, "                if (PhotonNetwork.InRoom)\n                {\n                    Plugin.Log.LogError(\"[2v2-DC] refusing to stage \" + CapabilityProp",
                "                if (false)\n                {\n                    Plugin.Log.LogError(\"[2v2-DC] refusing to stage \" + CapabilityProp",
                "cr_dc2 staging"),
        "cr_dc2 pre-join protocol")


def test_the_freeze_log_budget_is_spent_per_match_not_per_process():
    """FREEZE_LOG_CAP was described as a per-match budget in the comment beside
    it and was implemented as a per-PROCESS one: _freezeLogged had no reset.  A
    player's first match could spend all 60 lines, and the bundle from the match
    they actually complained about then reads exactly like a match with no stalls
    in it -- the same shape as the [SAW-TARGET] line that only spoke once."""
    src = _src("GameStateWatcher.cs")
    assert src.count("_freezeLogged = 0;   // the >0.2s cap is per MATCH") == 2

    def claim(s):
        return s.count("_freezeLogged = 0;   // the >0.2s cap is per MATCH") == 2

    _assert_discriminating(
        claim, src,
        _mutate(src, "_freezeLogged = 0;   // the >0.2s cap is per MATCH, like the two below it\n",
                "", "freeze cap"),
        "freeze log budget per match")

    # the band's own caps were already per match; all three now share the unit
    assert src.count("_bandSummaries = 0; _bandSummarisedCount = 0;") == 2


# ══════════════════════════════════════════════════════════════════════════
# Round-3 -- the class sweeps behind the round-2 findings
# ══════════════════════════════════════════════════════════════════════════

def test_every_capability_stage_waits_for_the_compatibility_verdict():
    """The flag named cr_dc2 and cr_saw1; the defect is the OPERATION (#432).

    Four protocols stage a per-seat capability property, and every one of them
    stages PRE-JOIN because an in-room write reaches peers after they have
    already evaluated the census it feeds.  The compatibility verdict lands
    about three seconds into the process, and a join inside that window used to
    snapshot a capability from a seat the verdict then disabled -- leaving an
    in-room revoke as the only correction, i.e. the exact write all four refuse.

    All four now refuse before the verdict, and all four SAY SO once: a silent
    refusal and a stage that was never attempted read identically in a bundle
    (#342)."""
    protocols = [
        ("VanillaFixes.cs", "GrowNormalize", "[GROW-CAP]"),
        ("VanillaFixes.cs", "SawTargetSync", "[SAW-CAP]"),
        ("RoomActors.cs", "DcReportSync", "[2v2-DC]"),
        ("PoisonSync.cs", "PoisonSync", "[POISON-CAP]"),
    ]
    for fname, cls, tag in protocols:
        src = _src(fname)
        cut = src[src.index("class " + cls):] if ("class " + cls) in src else src
        stage = cut[cut.index("internal static void StageCapability(string source)"):]
        stage = stage[:stage.index("internal static void RevokeCapability()")]
        assert "if (!Plugin.compatCheckComplete)" in stage, cls
        assert "deferred staging" in stage, cls
        assert tag in stage, cls
        # the verdict gate precedes the in-room refusal it exists to avoid
        assert (stage.index("if (!Plugin.compatCheckComplete)")
                < stage.index("if (PhotonNetwork.InRoom)")), cls

    # a control per FILE, because the three files are three separate edits
    for fname in ("RoomActors.cs", "VanillaFixes.cs", "PoisonSync.cs"):
        src = _src(fname)
        want = 2 if fname == "VanillaFixes.cs" else 1

        def claim(s, _w=want):
            return s.count("if (!Plugin.compatCheckComplete)") >= _w

        _assert_discriminating(
            claim, src,
            src.replace("if (!Plugin.compatCheckComplete)", "if (false)"),
            "compat gate in " + fname)


def test_the_dc_outcome_property_is_scoped_to_the_series_it_describes():
    """cr_dcr is retained on the actor and a sitting can run several series, so
    an outcome published for the PREVIOUS series must not read as a terminal
    answer about this one -- that would stand a watch down over a report that
    was never sent."""
    ra = _src("RoomActors.cs")
    body = _method_body(ra, "internal static string OutcomeOf(PhotonPlayer actor, string seriesId)")
    assert body, "OutcomeOf's own text could not be delimited"
    assert "Tag(seriesId)" in body
    assert "s.Substring(0, i), tag" in body
    # and an unrecognised token is NOT terminal
    assert "OutcomeSent || o == OutcomeAnswered || o == OutcomeFailed" in body

    # the model of the same rule, including the three ways it must answer ""
    def outcome_of(prop, series):
        tag = series[:8].lower()
        if not prop or ":" not in prop:
            return ""
        head, _, rest = prop.partition(":")
        if head != tag or rest not in ("send", "ok", "no"):
            return ""
        return rest

    assert outcome_of("abcdef12:ok", "ABCDEF12-1111") == "ok"
    assert outcome_of("99999999:ok", "abcdef12-1111") == ""      # a previous series
    assert outcome_of("abcdef12:maybe", "abcdef12-1111") == ""   # unrecognised
    assert outcome_of("", "abcdef12-1111") == ""
    # and the watch treats "" as NOT terminal while the seat is still present
    assert fallback(outcome_of("99999999:no", "abcdef12"), False, "active") == "nothing"

    def claim(s):
        b = _method_body(s, "internal static string OutcomeOf(PhotonPlayer actor, string seriesId)")
        return bool(b) and "s.Substring(0, i), tag" in b

    _assert_discriminating(
        claim, ra,
        _mutate(ra, "if (!string.Equals(s.Substring(0, i), tag, StringComparison.Ordinal)) return " + '""' + ";",
                "// any series' answer will do", "outcome scope"),
        "DC outcome series scope")


def test_the_dc_fallback_watch_dies_with_the_room():
    """A watch carried across a room edge waits on an ACTOR NUMBER that now
    names somebody else.  Same lifetime, and the same three edges, as the
    [SAW-TARGET] verdict line beside it."""
    plug = _src("Plugin.cs")
    ra = _src("RoomActors.cs")
    assert "internal static void ResetForRoomChange()" in ra
    assert plug.count("DcReportSync.ResetForRoomChange();") >= 3   # join, leave, disconnect
    assert "DcReportSync.NoteActorLeft(p);" in plug
    assert "DcReportSync.NoteActorProps(target);" in plug

    def claim(s):
        return s.count("DcReportSync.ResetForRoomChange();") >= 3

    _assert_discriminating(
        claim, plug,
        plug.replace("DcReportSync.ResetForRoomChange();", "// no reset"),
        "DC watch per room")

    # the property hook runs BEFORE the null-payload return that ends the method
    upd = plug[plug.index("public void OnPlayerPropertiesUpdate("):]
    upd = upd[:upd.index("RoomActors.NoteRosterIdentityChange();")]
    assert upd.index("DcReportSync.NoteActorProps(target);") < upd.index("if (changedProps == null) return;")


def test_the_masking_witness_line_is_measured_and_bounded():
    """[SAW-TARGET] apply says the quorum was evaluated; it says nothing about
    whether a frame was ever masked or put back.  The positive line that does
    must MEASURE its terms rather than assert them: same-list is a reference
    comparison against the object the window opened over, and the postfix
    stand-down is that postfix's own count inside this window (#342)."""
    vf = _src("VanillaFixes.cs")
    restore = vf[vf.index("private static void RestoreOrder()"):]
    restore = restore[:restore.index("[HarmonyFinalizer]")]
    assert "ReferenceEquals(players, _maskedList)" in restore
    assert "[SAW-TARGET] masked/restored same-list=true same-count=true" in restore
    assert "postfix-stand-down=" in restore
    assert "_maskedLines < 3" in restore                     # bounded, per room
    # identity is part of the restore GUARD, not only of the line
    assert restore.index("bool sameSet = sameList && sameCount;") < restore.index("players[i] = _order[i];")
    # the postfix COUNTS its stand-down rather than the line claiming it
    assert ("if (SawLiveTargetPatch.WindowOpen) { SawLiveTargetPatch.NotePostfixStoodDown(); return; }"
            in vf)
    # and the budget is reset on the same room edge as the verdict line
    reset = vf[vf.index("internal static void ResetForRoomChange()"):]
    reset = reset[:reset.index("\n    }")]
    assert "SawLiveTargetPatch.ResetForRoomChange();" in reset

    def claim(s):
        if "private static void RestoreOrder()" not in s:
            return False
        r = s[s.index("private static void RestoreOrder()"):]
        r = r[:r.index("[HarmonyFinalizer]")] if "[HarmonyFinalizer]" in r else r
        return "ReferenceEquals(players, _maskedList)" in r and "_maskedLines < 3" in r

    _assert_discriminating(
        claim, vf,
        _mutate(vf, "bool sameList = players != null && ReferenceEquals(players, _maskedList);",
                "bool sameList = players != null;", "saw witness"),
        "saw masking witness")


def test_the_broadcast_transport_refusal_speaks_whoever_asked():
    """The one pre-dispatch refusal whose only voice was a toast nested under
    `if (!broadcastTicket)`.  On the seat where that guard is the only one that
    can arm at all, the method returned zero and the bundle showed nothing --
    so "a grant was declined" and "no grant was ever requested" read alike."""
    src = _src("ApiClient.cs")
    arm = src[src.index("if (BroadcastGrantTransportUnsettled)"):]
    arm = arm[:arm.index("return 0;")]
    assert "[SPECTATE] WATCH declined before dispatch: a broadcast-issued" in arm
    # the log precedes the conditional toast, and is not inside it
    assert arm.index("Plugin.Log.LogInfo") < arm.index("if (!broadcastTicket)")

    def claim(s):
        if "if (BroadcastGrantTransportUnsettled)" not in s:
            return False
        a = s[s.index("if (BroadcastGrantTransportUnsettled)"):]
        a = a[:a.index("return 0;")] if "return 0;" in a else a
        if "Plugin.Log.Log" not in a or "if (!broadcastTicket)" not in a:
            return False
        return a.index("Plugin.Log.Log") < a.index("if (!broadcastTicket)")

    _assert_discriminating(
        claim, src,
        _mutate(src,
                'Plugin.Log.LogInfo("[SPECTATE] WATCH declined before dispatch: a broadcast-issued "',
                "// silent", "broadcast diag"),
        "broadcast transport refusal speaks")


def test_the_epoch_guarantee_is_narrowed_to_what_the_client_emits():
    """The audit's correction told a reader to PARTITION on local_freeze_epoch.
    Nothing on the deployed server stores it, so there is no column to group by
    and the instruction described a capability that does not exist (#302).  The
    client's guarantee stops at the wire; the storage half is a server pass."""
    raw = (ROOT / "docs" / "performance-audit-2026-07-23.md").read_text(encoding="utf-8")
    doc = " ".join(raw.split())          # the claims are sentences, not lines
    assert "0cc7f75" in doc
    assert "does not declare, store or classify either field" in doc
    assert "no epoch column to group by" in doc
    assert "Partition on `local_freeze_epoch`" not in doc

    def claim(s):
        return ("0cc7f75" in s
                and "does not declare, store or classify either field" in s)

    _assert_discriminating(
        claim, doc,
        _mutate(doc, "does not declare, store or classify either field",
                "stores both fields", "epoch doc"),
        "epoch doc narrowed")


def test_the_schema_note_names_the_deployed_pin():
    """A contract note pinned to a retired, never-deployed tail validates against
    a model production does not run."""
    sch = (ROOT / "backend" / "api" / "schemas.py").read_text(encoding="utf-8")
    note = sch[sch.index("local_freeze_epoch, opp_freeze_epoch"):sch.index("local_ping_avg")]
    assert "PRODUCTION 0cc7f75" in note
    assert "THE CLIENT" in note and "STOPS AT THE WIRE" in note
    # the retired tail may only appear as the thing being corrected
    for line in note.splitlines():
        if "cc92498" in line and "0cc7f75" not in line:
            assert "used to name" in line or "tail" in line, line

    def claim(s):
        return "PRODUCTION 0cc7f75" in s and "STOPS AT THE WIRE" in s

    _assert_discriminating(
        claim, sch,
        _mutate(sch, "PRODUCTION 0cc7f75", "the deployed main.py at cc92498", "schema pin"),
        "schema note pin")
